import pandas as pd
import numpy as np
import yfinance as yf
import time
import threading
import logging

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

    def fetch_historical_data(self):
        """Fetches historical market data from Yahoo Finance."""
        logging.info(f"Fetching historical data for {self.ticker} ({self.interval}, period={self.period})...")
        try:
            df = yf.download(tickers=self.ticker, period=self.period, interval=self.interval)
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
            
            self.data = df
            logging.info(f"Successfully loaded {len(self.data)} rows of historical data.")
            self.compute_technical_indicators()
            return self.data
        except Exception as e:
            logging.error(f"Error fetching historical data: {e}")
            raise e

    def compute_technical_indicators(self):
        """Computes technical indicators on the historical dataset."""
        df = self.data
        if df.empty:
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

        # Relative Strength Index (RSI)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        df['rsi'] = 100 - (100 / (1 + rs))

        # Bollinger Bands
        df['bb_mid'] = df['close'].rolling(window=20).mean()
        df['bb_std'] = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_mid'] + (2 * df['bb_std'])
        df['bb_lower'] = df['bb_mid'] - (2 * df['bb_std'])

        # Average True Range (ATR)
        high_low = df['high'] - df['low']
        high_close_prev = (df['high'] - df['close'].shift()).abs()
        low_close_prev = (df['low'] - df['close'].shift()).abs()
        
        # Standard ATR using maximum of the three ranges
        tr = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
        df['atr'] = tr.rolling(window=14).mean()
        
        # Clean up NaNs
        self.data = df.bfill().ffill()

    def subscribe(self, callback):
        """Subscribe to live/simulated price ticks."""
        self.subscribers.append(callback)

    def start_simulation_stream(self, speed_seconds=1.0, start_index=100):
        """Simulates live streaming by feeding historical data row-by-row in real-time."""
        if self.data.empty:
            self.fetch_historical_data()

        self.streaming = True
        self.stream_thread = threading.Thread(
            target=self._run_simulation,
            args=(speed_seconds, start_index),
            daemon=True
        )
        self.stream_thread.start()
        logging.info("Simulation stream started.")

    def _run_simulation(self, speed, start_index):
        idx = start_index
        total_len = len(self.data)
        while self.streaming and idx < total_len:
            row = self.data.iloc[idx].to_dict()
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
        """Polls yfinance for live price updates in a background thread."""
        self.streaming = True
        self.stream_thread = threading.Thread(
            target=self._run_live_polling,
            args=(interval_seconds,),
            daemon=True
        )
        self.stream_thread.start()
        logging.info(f"Live data stream started. Polling every {interval_seconds}s...")

    def _run_live_polling(self, interval):
        import json
        import os
        
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

        # If ccxt is available and we want live mode, initialize exchange client
        exchange = None
        if use_ccxt:
            try:
                import ccxt
                if hasattr(ccxt, broker_type):
                    exchange_class = getattr(ccxt, broker_type)
                    exchange = exchange_class({
                        'apiKey': api_key,
                        'secret': api_secret,
                        'enableRateLimit': True,
                    })
                    logging.info(f"[LIVE POLLING] Initialized live ticker polling from exchange: {broker_type.upper()}")
            except Exception as e:
                logging.error(f"[LIVE POLLING ERROR] Failed to initialize ccxt for polling: {e}")
                exchange = None

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
                        
                        # Fetch OHLCV or construct from history
                        if not self.data.empty:
                            last_row = self.data.iloc[-1]
                            row = {
                                'timestamp': pd.Timestamp.now(),
                                'open': float(last_row['close']), # current open is previous close
                                'high': max(float(last_row['close']), price),
                                'low': min(float(last_row['close']), price),
                                'close': price,
                                'volume': 0.0
                            }
                    except Exception as e:
                        logging.error(f"[LIVE EXCHANGE POLLING FAILED] {e}. Falling back to yfinance.")
                        price = None
                
                # Fallback to yfinance if not CCXT or CCXT failed
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
                    # Append and recompute technical indicators
                    self.data = pd.concat([self.data, pd.DataFrame([row])]).drop_duplicates(subset=['timestamp'])
                    self.compute_technical_indicators()
                    
                    updated_row = self.data.iloc[-1].to_dict()
                    # Notify subscribers
                    for callback in self.subscribers:
                        callback(updated_row)
                        
            except Exception as e:
                logging.error(f"Error in live polling loop: {e}")
            time.sleep(interval)

    def stop_stream(self):
        self.streaming = False
        if self.stream_thread:
            self.stream_thread.join(timeout=3)
        logging.info("Stream stopped.")
