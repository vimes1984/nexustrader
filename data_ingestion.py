import traceback
import pandas as pd
import numpy as np
import yfinance as yf
import time
import threading
import logging
import json
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class DataIngestion:
    def __init__(self, ticker="ETH-USD", interval="1h", period="60d"):
        self.ticker = ticker
        self.interval = interval
        self.period = period
        self.data = pd.DataFrame()
        self.live_price = None
        self.streaming = False
        self.stream_thread = None
        self.subscribers = []

    def _require_lock(self):
        """Ensure thread lock exists for thread-safe data access."""
        if not hasattr(self, '_data_lock'):
            self._data_lock = threading.Lock()
    
    def fetch_historical_data(self):
        """Fetches historical market data from Yahoo Finance."""
        logging.info(f"Fetching historical data for {self.ticker} ({self.interval}, period={self.period})...")
        try:
            df = yf.download(tickers=self.ticker, period=self.period, interval=self.interval, auto_adjust=True, progress=False)
            if df.empty:
                raise ValueError("No data returned from yfinance.")
            
            # Reset columns structure in case of MultiIndex
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            df = df.reset_index()
            # Ensure standard naming
            df = df.rename(columns={
                'Datetime': 'timestamp',
                'Date': 'timestamp',
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume'
            })
            
            # Cast column values to float/string to prevent issues
            df['open'] = df['open'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            df['close'] = df['close'].astype(float)
            df['volume'] = df['volume'].astype(float)
            
            self._require_lock()
            with self._data_lock:
                self.data = df
            logging.info(f"Successfully loaded {len(self.data)} rows of historical data.")
            self.compute_technical_indicators()
            with self._data_lock:
                return self.data.copy()
        except Exception as e:
            logging.error(f"Error fetching historical data: {e}")
            raise e

    def compute_technical_indicators(self):
        """Computes technical indicators on the historical dataset.
        
        Locks are held for the full read-compute-write cycle to prevent
        TOCTOU data corruption: another thread may append/update rows between
        the copy and the write-back.
        """
        self._require_lock()
        with self._data_lock:
            if self.data.empty:
                return
            df = self.data.copy()
            
            # Guard against short DataFrames — RSI/ATR seeding requires 14+ rows
            if len(df) < 14:
                return

        # Simple Moving Averages (SMA)
        df['sma_20'] = df['close'].rolling(window=20).mean()
        df['sma_50'] = df['close'].rolling(window=50).mean()

        # Exponential Moving Averages (EMA)
        df['ema_12'] = df['close'].ewm(span=12, adjust=False).mean()
        df['ema_26'] = df['close'].ewm(span=26, adjust=False).mean()
        
        # MACD
        df['macd'] = df['ema_12'] - df['ema_26']
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']

        # Relative Strength Index (RSI) — Wilder's Smoothed RMA (14-period)
        # Wilder's method: avg_gain[13] = SMA(gain, 14), then RMA: avg_t = avg_{t-1} + (val_t - avg_{t-1})/14
        # pd.ewm(alpha=1/14, adjust=False) does NOT seed with SMA — it seeds with the first value.
        # We must manually implement Wilder's RMA for correctness.
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta.where(delta < 0, 0.0))
        
        # Wilder's smoothing: first avg = SMA(14), subsequent values = RMA (alpha=1/14)
        sma14_gain = gain.rolling(window=14).mean()
        sma14_loss = loss.rolling(window=14).mean()
        avg_gain = gain.copy()
        avg_loss = loss.copy()
        # First 13 values: undefined (set to 0, RSI will be NaN until period 14)
        avg_gain.iloc[:13] = np.nan
        avg_loss.iloc[:13] = np.nan
        # Period 14 (index 13): SMA(14)
        avg_gain.iloc[13] = sma14_gain.iloc[13]
        avg_loss.iloc[13] = sma14_loss.iloc[13]
        # Periods 15+: RMA (Wilder's recursive smoothing)
        for i in range(14, len(df)):
            avg_gain.iloc[i] = avg_gain.iloc[i-1] + (gain.iloc[i] - avg_gain.iloc[i-1]) / 14.0
            avg_loss.iloc[i] = avg_loss.iloc[i-1] + (loss.iloc[i] - avg_loss.iloc[i-1]) / 14.0
        
        rs = avg_gain / (avg_loss + 1e-9)
        df['rsi'] = 100.0 - (100.0 / (1.0 + rs))

        # Bollinger Bands (20-period, 2 std dev, uses POPULATION std ddof=0)
        # Standard Bollinger uses population standard deviation, not sample
        df['bb_mid'] = df['close'].rolling(window=20).mean()
        df['bb_std'] = df['close'].rolling(window=20).std(ddof=0)
        df['bb_upper'] = df['bb_mid'] + (2 * df['bb_std'])
        df['bb_lower'] = df['bb_mid'] - (2 * df['bb_std'])

        # Average True Range (ATR) — Wilder's Smoothed (14-period)
        high_low = df['high'] - df['low']
        high_close_prev = (df['high'] - df['close'].shift()).abs()
        low_close_prev = (df['low'] - df['close'].shift()).abs()
        
        # Standard ATR using maximum of the three ranges
        tr = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
        # Wilder's ATR: first value = SMA(TR, 14), then RMA with alpha=1/14
        sma14_tr = tr.rolling(window=14).mean()
        atr = tr.copy()
        atr.iloc[:13] = np.nan
        atr.iloc[13] = sma14_tr.iloc[13]
        for i in range(14, len(df)):
            atr.iloc[i] = atr.iloc[i-1] + (tr.iloc[i] - atr.iloc[i-1]) / 14.0
        df['atr'] = atr
        
        # Volume Weighted Moving Average (VWMA)
        df['vwma_20'] = (df['close'] * df['volume']).rolling(window=20).sum() / (df['volume'].rolling(window=20).sum() + 1e-9)
        
        # Stochastic Oscillator (14, 3)
        low_14 = df['low'].rolling(window=14).min()
        high_14 = df['high'].rolling(window=14).max()
        df['stoch_k'] = 100 * ((df['close'] - low_14) / (high_14 - low_14 + 1e-9))
        df['stoch_d'] = df['stoch_k'].rolling(window=3).mean()
        
        # Use expanding mean for early NaN windows instead of ffill
        # (ffill produces flat lines at trim boundaries; expanding.mean() gives smooth initialization)
        for col in ['sma_20', 'sma_50', 'ema_12', 'ema_26', 'macd', 'macd_signal', 'macd_hist',
                    'bb_mid', 'bb_std', 'bb_upper', 'bb_lower', 'vwma_20', 'stoch_d']:
            if col in df.columns:
                df[col] = df[col].fillna(df[col].expanding().mean())
        # RSI, ATR, stoch_k are bounded and harder to expanding-fill; use ffill as last resort
        df['rsi'] = df['rsi'].fillna(50.0)  # neutral RSI for warmup gaps
        df['atr'] = df['atr'].fillna(method='ffill')
        df['stoch_k'] = df['stoch_k'].fillna(method='ffill')
        # Assign back under lock
        self._require_lock()
        with self._data_lock:
            self.data = df

    def subscribe(self, callback):
        """Subscribe to live/simulated price ticks."""
        self.subscribers.append(callback)

    def start_simulation_stream(self, speed_seconds=1.0, start_index=100, start_date=None, end_date=None):
        """Simulates live streaming by feeding historical data row-by-row in real-time."""
        if self.data.empty:
            self.fetch_historical_data()

        # Apply date filters to target dataset if specified
        sim_data = self.data
        start_idx = start_index
        
        if not self.data.empty and 'timestamp' in self.data.columns:
            try:
                # Convert timestamps to timezone-naive datetimes or timezone-aware matching inputs
                ts_series = pd.to_datetime(self.data['timestamp'], errors='coerce')
                # Check if input date is provided and convert
                mask = pd.Series(True, index=self.data.index)
                if start_date:
                    mask = mask & (ts_series >= pd.to_datetime(start_date))
                if end_date:
                    mask = mask & (ts_series <= pd.to_datetime(end_date))
                
                filtered = self.data[mask]
                if not filtered.empty:
                    sim_data = filtered
                    start_idx = 0
                    logging.info(f"[SIMULATION FILTER] Sliced dataset to {len(sim_data)} rows between {start_date} and {end_date}.")
            except Exception as e:
                logging.error(f"Error filtering simulation dates: {e}")

        self.streaming = True
        self.stream_thread = threading.Thread(
            target=self._run_simulation,
            args=(speed_seconds, start_idx, sim_data),
            daemon=True
        )
        self.stream_thread.start()
        logging.info("Simulation stream started.")

    def _run_simulation(self, speed, start_index, sim_data):
        idx = start_index
        total_len = len(sim_data)
        while self.streaming and idx < total_len:
            row = sim_data.iloc[idx].to_dict()
            row['_sim_index'] = idx
            row['_sim_total'] = total_len
            self.live_price = float(row['close'])
            
            # Notify subscribers
            for callback in self.subscribers:
                try:
                    callback(row)
                except Exception as e:
                    logging.error(f"Error in subscriber callback: {e}")
                    
            idx += 1
            time.sleep(speed)
        self.streaming = False
        logging.info("Simulation stream finished.")

    def start_live_stream(self, interval_seconds=10):
        """Polls exchange/yfinance for live price updates with automatic reconnection."""
        self.streaming = True
        self.stream_thread = threading.Thread(
            target=self._run_live_polling,
            args=(interval_seconds,),
            daemon=True
        )
        self.stream_thread.start()
        logging.info(f"Live data stream started. Polling every {interval_seconds}s...")

    def _run_live_polling(self, interval):
        config_path = os.path.expanduser("~/.nexustrader/config.json")
        use_ccxt = False
        broker_type = "kraken"
        api_key = ""
        api_secret = ""
        
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    cfg = json.load(f)
                if cfg.get("trading_mode") == "live":
                    broker_type = cfg.get("broker", "kraken").lower()
                    creds = cfg.get("api_credentials", {})
                    api_key = creds.get("api_key", "")
                    api_secret = creds.get("api_secret", "")
                    if api_key and api_secret:
                        use_ccxt = True
            except Exception:
                pass

        # Track exchange health for reconnection
        exchange = None
        exchange_failures = 0
        max_exchange_failures = 3
        reconnect_delay = 5
        
        def init_exchange():
            """Initialize or reinitialize the exchange client."""
            nonlocal exchange_failures
            if not use_ccxt:
                return None
            try:
                import ccxt
                if hasattr(ccxt, broker_type):
                    exchange_class = getattr(ccxt, broker_type)
                    ex = exchange_class({
                        'apiKey': api_key,
                        'secret': api_secret,
                        'enableRateLimit': True,
                        'timeout': 15000,
                    })
                    exchange_failures = 0
                    logging.info(f"[LIVE POLLING] Initialized live ticker polling from exchange: {broker_type.upper()}")
                    return ex
            except Exception as e:
                logging.error(f"[LIVE POLLING ERROR] Failed to initialize ccxt: {e}")
                return None
        
        exchange = init_exchange()

        while self.streaming:
            try:
                price = None
                row = None
                
                # Try live exchange polling via CCXT
                if exchange is not None:
                    try:
                        ccxt_symbol = self.ticker.replace("-", "/")
                        ticker_data = exchange.fetch_ticker(ccxt_symbol)
                        price = float(ticker_data['last'])
                        self.live_price = price
                        exchange_failures = 0  # reset on success
                        
                        # Fetch OHLCV or construct from history
                        if not self.data.empty:
                            last_row = self.data.iloc[-1]
                            row = {
                                'timestamp': pd.Timestamp.now(),
                                'open': float(last_row['close']),
                                'high': max(float(last_row['close']), price),
                                'low': min(float(last_row['close']), price),
                                'close': price,
                                'volume': 0.0
                            }
                    except Exception as e:
                        exchange_failures += 1
                        logging.error(f"[LIVE EXCHANGE POLLING FAILED #{exchange_failures}] {e}")
                        if exchange_failures >= max_exchange_failures:
                            # Cap retry count to prevent exponential overflow
                            retry_num = min(exchange_failures - max_exchange_failures + 1, 10)
                            backoff = min(reconnect_delay * (2 ** retry_num), 120)
                            logging.warning(f"[EXCHANGE RECONNECT] Attempting reconnection in {backoff}s (retry #{retry_num})")
                            time.sleep(backoff)
                            exchange = init_exchange()
                        else:
                            time.sleep(1)
                        price = None
                
                # Fallback to yfinance if exchange failed or unavailable
                if price is None:
                    ticker_obj = yf.Ticker(self.ticker)
                    df = ticker_obj.history(period="1d", interval="1m")
                    if not df.empty:
                        last_row = df.iloc[-1]
                        price = float(last_row['Close'])
                        self.live_price = price
                        row = {
                            'timestamp': df.index[-1],
                            'open': float(last_row['Open']),
                            'high': float(last_row['High']),
                            'low': float(last_row['Low']),
                            'close': price,
                            'volume': float(last_row['Volume'])
                        }
                
                if row is not None:
                    self._require_lock()
                    with self._data_lock:
                        if not self.data.empty:
                            max_rows = 1000
                            if len(self.data) > max_rows:
                                # Trim to prevent unbounded memory growth
                                self.data = self.data.iloc[-max_rows:].reset_index(drop=True)
                            
                            last_idx = self.data.index[-1]
                            last_ts = self.data.loc[last_idx, 'timestamp']
                            
                            # Parse last timestamp
                            if isinstance(last_ts, str):
                                last_ts_dt = pd.to_datetime(last_ts)
                            else:
                                last_ts_dt = last_ts
                                
                            now_dt = pd.Timestamp.now(tz=last_ts_dt.tz if hasattr(last_ts_dt, 'tz') else None)
                            
                            # Calculate interval duration limit in seconds
                            seconds_limit = 3600
                            if self.interval == '1m':
                                seconds_limit = 60
                            elif self.interval == '5m':
                                seconds_limit = 300
                            elif self.interval == '15m':
                                seconds_limit = 900
                            elif self.interval == '1d':
                                seconds_limit = 86400
                                
                            # If pandas Timestamps are timezone-naive/aware, strip tz for simple comparison
                            now_naive = now_dt.tz_localize(None) if hasattr(now_dt, 'tz_localize') and now_dt.tz is not None else now_dt
                            last_naive = last_ts_dt.tz_localize(None) if hasattr(last_ts_dt, 'tz_localize') and last_ts_dt.tz is not None else last_ts_dt
                            time_diff = (now_naive - last_naive).total_seconds()
                            
                            if time_diff < seconds_limit:
                                # Update the last candle
                                self.data.loc[last_idx, 'close'] = price
                                self.data.loc[last_idx, 'high'] = max(self.data.loc[last_idx, 'high'], price)
                                self.data.loc[last_idx, 'low'] = min(self.data.loc[last_idx, 'low'], price)
                            else:
                                # Append new candle
                                row['timestamp'] = last_ts_dt + pd.Timedelta(seconds=seconds_limit)
                                self.data = pd.concat([self.data, pd.DataFrame([row])], ignore_index=True)
                        else:
                            self.data = pd.DataFrame([row])
                        
                    self.compute_technical_indicators()
                    self._require_lock()
                    with self._data_lock:
                        updated_row = self.data.iloc[-1].to_dict()
                    
                    # Convert pandas Timestamp to string format for JSON serialization
                    if 'timestamp' in updated_row and not isinstance(updated_row['timestamp'], str):
                        updated_row['timestamp'] = str(updated_row['timestamp'])
                        
                    for callback in self.subscribers:
                        callback(updated_row)
                        
            except Exception as e:
                logging.error(f"Error in live polling loop: {e}\n{traceback.format_exc()}")
            time.sleep(interval)

    def stop_stream(self):
        self.streaming = False
        if self.stream_thread:
            self.stream_thread.join(timeout=3)
        logging.info("Stream stopped.")
