import json
import logging
import asyncio
import sqlite3
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
import numpy as np
import pandas as pd
import sys
import os
import time

def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

from data_ingestion import DataIngestion
from strategy_engine import StrategyEnsemble
from probability_engine import ProbabilityEngine
from learning_engine import LearningEngine
from execution_engine import ExecutionEngine
import database

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI(title="NexusTrader API", version="1.0.0")

@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith(".html") or path.endswith(".js") or path.endswith(".css"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Central orchestrator state supporting multi-asset portfolio operations
class NexusTraderOrchestrator:
    def __init__(self):
        self.tickers = ['ETH-USD', 'SOL-USD', 'BTC-USD', 'DOGE-USD', 'XRP-USD']
        self.data_ingestions = {}
        self.strategy_ensembles = {}
        self.learning_engines = {}
        self.latest_ticks = {}
        self.latest_sentiments = {t: 0.0 for t in self.tickers}
        self.latest_source_sentiments = {t: {} for t in self.tickers}
        self.last_sentiment_times = {t: 0.0 for t in self.tickers}
        
        self.probability_engine = ProbabilityEngine(kelly_fraction=0.2)
        self.execution_engine = ExecutionEngine(initial_balance=100.0)
        
        # State tracking
        self.connected_websockets = []
        self.running_task = None
        self.playback_speed = 0.2  # delay in seconds between simulated bars
        self.is_simulating = False
        self.loop = None
        
        # Setup learning callback connection
        self.execution_engine.set_learning_callback(self.on_trade_closed)

    async def initialize(self):
        """Fetches initial data and trains ML strategies for all tickers."""
        self.loop = asyncio.get_running_loop()
        
        # Load risk mode from database if it exists
        db_risk_mode = database.load_setting("risk_mode")
        if db_risk_mode:
            try:
                self.probability_engine.set_risk_mode(db_risk_mode)
                logging.info(f"Loaded risk mode from database: {db_risk_mode}")
            except Exception as e:
                logging.error(f"Error loading risk mode from DB: {e}")
                
        # Sync cash balance with live broker if in live mode
        try:
            self.execution_engine.sync_live_balance()
        except Exception as e:
            logging.error(f"Error synchronizing live balance at startup: {e}")
        
        # Initialize each ticker independently
        for ticker in self.tickers:
            logging.info(f"Initializing assets and models for {ticker}...")
            ingestor = DataIngestion(ticker=ticker, interval="1h", period="60d")
            try:
                df = ingestor.fetch_historical_data()
            except Exception as e:
                logging.error(f"Error fetching data for {ticker}: {e}. Skipping ticker.")
                continue
                
            ensemble = StrategyEnsemble(history_df=df)
            num_strats = len(ensemble.strategies)
            learner = LearningEngine(num_strategies=num_strats, learning_rate=0.15)
            
            # Load saved Policy Gradient Neural Network weights if they exist
            db_net_str = database.load_setting(f"policy_net_weights_{ticker}")
            if db_net_str:
                try:
                    learner.policy_net.from_json(db_net_str)
                    state = learner.get_state_vector(
                        df.iloc[-1].to_dict(),
                        list(df['close'].values[-60:]),
                        [t for t in self.execution_engine.closed_trades if t['symbol'] == ticker]
                    )
                    ensemble.weights = learner.select_weights(state)
                    logging.info(f"Loaded Policy Network weights for {ticker} from database.")
                except Exception as e:
                    logging.error(f"Error loading Policy Network weights for {ticker}: {e}")
            else:
                ensemble.weights = (np.ones(num_strats) / num_strats).tolist()

            # Save initial weights history point if empty to ensure the line chart displays
            try:
                if not database.load_weights_history(ticker, limit=1):
                    # Point 1: Baseline equal weights 2 hours ago
                    equal_weights = {
                        ensemble.strategies[i].name: float(1.0 / num_strats)
                        for i in range(num_strats)
                    }
                    database.save_weights_history(time.time() - 7200, ticker, equal_weights)
                    
                    # Point 2: Loaded weights now
                    start_weights = {
                        ensemble.strategies[i].name: float(ensemble.weights[i])
                        for i in range(len(ensemble.weights))
                    }
                    database.save_weights_history(time.time(), ticker, start_weights)
            except Exception as e:
                logging.error(f"Error pre-populating weights history: {e}")
                
            self.data_ingestions[ticker] = ingestor
            self.strategy_ensembles[ticker] = ensemble
            self.learning_engines[ticker] = learner
            
        logging.info("NexusTrader Orchestrator initialized successfully for all tickers.")

    def _run_async(self, coro):
        """Safely schedule a coroutine to run on the main FastAPI event loop from any thread."""
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, self.loop)

    def on_trade_closed(self, ticker, strategy_signals, direction, pnl_percent):
        """Callback from ExecutionEngine when a trade is closed."""
        logging.info(f"[{ticker}] Trade closed with PnL%: {pnl_percent*100:.2f}%. Training Policy Network...")
        
        learner = self.learning_engines[ticker]
        ensemble = self.strategy_ensembles[ticker]
        
        # Reconstruct the state vector when the trade was evaluated
        latest_tick = self.latest_ticks.get(ticker, {})
        state = learner.get_state_vector(
            latest_tick or {},
            ensemble.price_history,
            [t for t in self.execution_engine.closed_trades if t['symbol'] == ticker]
        )
        
        # Run backpropagation on neural network weights using PnL as reward
        new_weights = learner.learn_from_trade(
            state,
            strategy_signals,
            direction,
            pnl_percent
        )
        
        # Write back to strategy ensemble
        ensemble.weights = new_weights
        
        # Save updated network parameters to database and track training statistics
        weights_json = learner.policy_net.to_json()
        database.save_setting(f"policy_net_weights_{ticker}", weights_json)
        
        # Calculate unique Model DNA signature from network weight parameters
        import hashlib
        dna_hash = hashlib.md5(weights_json.encode('utf-8')).hexdigest()[:8].upper()
        model_dna = f"NN-{dna_hash}"
        
        # Increment and save lifetime training steps
        steps_key = f"lifetime_training_steps_{ticker}"
        steps = int(database.load_setting(steps_key, "0")) + 1
        database.save_setting(steps_key, str(steps))
        last_save_time = time.strftime('%H:%M:%S', time.localtime())
        
        # Save weights to weights history table
        weights_dict = {
            ensemble.strategies[i].name: float(new_weights[i])
            for i in range(len(new_weights))
        }
        database.save_weights_history(time.time(), ticker, weights_dict)
        
        # Push update to WebSocket clients immediately
        self._run_async(self.broadcast_message({
            "type": "learning_update",
            "ticker": ticker,
            "weights": {
                ensemble.strategies[i].name: new_weights[i]
                for i in range(len(new_weights))
            },
            "pnl": pnl_percent,
            "lifetime_steps": steps,
            "model_dna": model_dna,
            "last_save_time": last_save_time
        }))

    def process_tick(self, row, ticker):
        """Orchestrates single price tick logic for a specific ticker."""
        # Periodically refresh news sentiment in a background thread to prevent loop blocking
        curr_time = time.time()
        if curr_time - self.last_sentiment_times.get(ticker, 0.0) >= 300.0:
            self.last_sentiment_times[ticker] = curr_time
            
            async def update_sentiment(t=ticker):
                try:
                    loop = asyncio.get_running_loop()
                    from sentiment_analyzer import fetch_ticker_sentiment
                    weighted_score, source_averages = await loop.run_in_executor(None, fetch_ticker_sentiment, t)
                    self.latest_sentiments[t] = weighted_score
                    self.latest_source_sentiments[t] = source_averages
                except Exception as ex:
                    logging.error(f"Error updating news sentiment for {t}: {ex}")
            
            self._run_async(update_sentiment(ticker))

        # Inject cached sentiment score and source breakdowns into row dictionary
        row['sentiment'] = self.latest_sentiments.get(ticker, 0.0)
        row['sentiment_sources'] = self.latest_source_sentiments.get(ticker, {})
        
        # Periodically sync live balance (every 30 ticks across tickers)
        if not hasattr(self, "_tick_count"):
            self._tick_count = 0
        self._tick_count += 1
        if self._tick_count % 30 == 0:
            try:
                self.execution_engine.sync_live_balance()
            except Exception as e:
                logging.error(f"Error in periodic live balance sync: {e}")

        self.latest_ticks[ticker] = row
        current_price = float(row['close'])
        atr = row.get('atr', None)
        
        # Save tick to database for future analysis / machine learning training
        database.save_tick(row, ticker)
        
        learner = self.learning_engines[ticker]
        ensemble = self.strategy_ensembles[ticker]
        ingestor = self.data_ingestions[ticker]
        
        # 1. Query the Policy Gradient Neural Network to allocate base strategy weights
        state = learner.get_state_vector(
            row,
            ensemble.price_history,
            [t for t in self.execution_engine.closed_trades if t['symbol'] == ticker]
        )
        base_weights = learner.select_weights(state)
        ensemble.weights = base_weights
        
        # 2. Update existing positions (check if TP/SL hit or limit orders filled)
        update_event = self.execution_engine.update_positions(ticker, current_price)
        
        # Calculate current total equity across all tickers
        current_prices = {t: float(r['close']) for t, r in self.latest_ticks.items()}
        current_equity = self.execution_engine.get_equity(current_prices)
        
        # Periodic equity history logging (every 1 hour)
        now_time = time.time()
        if not hasattr(self, "last_equity_log_time") or now_time - self.last_equity_log_time >= 3600:
            self.last_equity_log_time = now_time
            try:
                init_bal_str = database.load_setting("initial_portfolio_balance")
                init_bal = float(init_bal_str) if init_bal_str else 100.0
                conn = sqlite3.connect(database.DB_PATH)
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO portfolio_history (timestamp, equity, pnl) VALUES (?, ?, ?)",
                    (now_time, current_equity, current_equity - init_bal)
                )
                conn.commit()
                conn.close()
            except Exception as e:
                logging.error(f"Error logging portfolio history point: {e}")
        
        if update_event:
            if update_event["event"] == "closed":
                # Broadcast closed trade
                self._run_async(self.broadcast_message({
                    "type": "trade_closed",
                    "trade": update_event["data"],
                    "balance": self.execution_engine.balance,
                    "equity": current_equity
                }))
            elif update_event["event"] == "filled":
                # Broadcast filled order to open trade
                self._run_async(self.broadcast_message({
                    "type": "trade_opened",
                    "ticker": ticker,
                    "position": update_event["data"],
                    "balance": self.execution_engine.balance,
                    "equity": current_equity
                }))
            
        # 3. If no position is open for this ticker, check strategy ensemble signals
        pos_open = ticker in self.execution_engine.active_positions
        weighted_signal, strategy_breakdown = ensemble.get_weighted_signal(row, ingestor.data)
        
        evaluation = None
        trade_opened = False
        
        if not pos_open:
            # Threshold to trigger evaluation: signal strength > 0.25 (out of -1.0 to 1.0 scale)
            if abs(weighted_signal) >= 0.25:
                direction = "BUY" if weighted_signal > 0 else "SELL"
                
                # Evaluate probability and risk
                evaluation = self.probability_engine.evaluate_trade(
                    price=current_price,
                    atr=atr,
                    direction=direction,
                    weighted_signal=weighted_signal,
                    row=row,
                    history_df=ingestor.data
                )
                
                # If viable, open position
                if evaluation["is_viable"]:
                    evaluation["sentiment_sources"] = row.get("sentiment_sources", {})
                    # Gather the active signals at entry
                    signals_at_entry = [
                        strat.generate_signal(row)
                        for strat in ensemble.strategies
                    ]
                    
                    opened = self.execution_engine.open_position(
                        ticker,
                        evaluation,
                        signals_at_entry
                    )
                    
                    if opened:
                        trade_opened = True
                        if self.execution_engine.trading_mode == "live":
                            self._run_async(self.broadcast_message({
                                "type": "trade_opened",
                                "ticker": ticker,
                                "position": self.execution_engine.active_positions[ticker],
                                "balance": self.execution_engine.balance,
                                "equity": current_equity
                            }))
                        else:
                            self._run_async(self.broadcast_message({
                                "type": "limit_order_placed",
                                "ticker": ticker,
                                "order": self.execution_engine.pending_limit_orders[ticker],
                                "balance": self.execution_engine.balance,
                                "equity": current_equity
                            }))

        # Check Loss Cooldown status
        cooldown_end = float(database.load_setting(f"cooldown_end_{ticker}", "0.0"))
        cooldown_active = time.time() < cooldown_end
        cooldown_remaining = max(0, int((cooldown_end - time.time()) / 60)) if cooldown_active else 0

        # Load lifetime steps and model DNA for visual confirmation
        steps_key = f"lifetime_training_steps_{ticker}"
        steps = int(database.load_setting(steps_key, "0"))
        db_net_str = database.load_setting(f"policy_net_weights_{ticker}")
        if db_net_str:
            import hashlib
            dna_hash = hashlib.md5(db_net_str.encode('utf-8')).hexdigest()[:8].upper()
            model_dna = f"NN-{dna_hash}"
        else:
            model_dna = "NN-DEFAULT"

        # 4. Broadcast real-time update to all clients
        self._run_async(self.broadcast_message({
            "type": "tick",
            "ticker": ticker,
            "price": current_price,
            "timestamp": str(row['timestamp']),
            "weighted_signal": weighted_signal,
            "strategy_breakdown": strategy_breakdown,
            "evaluation": evaluation if not pos_open else None,
            "balance": self.execution_engine.balance,
            "equity": current_equity,
            "position": self.execution_engine.active_positions.get(ticker, None),
            "neural_state": state,
            "cooldown_active": cooldown_active,
            "cooldown_remaining": cooldown_remaining,
            "trading_mode": self.execution_engine.trading_mode,
            "broker": self.execution_engine.config.get("broker", "kraken"),
            "lifetime_steps": steps,
            "model_dna": model_dna,
            "indicators": {
                "rsi": float(row.get('rsi', 50)),
                "macd": float(row.get('macd', 0)),
                "macd_signal": float(row.get('macd_signal', 0)),
                "bb_upper": float(row.get('bb_upper', current_price)),
                "bb_lower": float(row.get('bb_lower', current_price)),
                "atr": float(row.get('atr', 0))
            }
        }))

    async def broadcast_message(self, message):
        """Sends JSON message to all active WebSocket connections."""
        disconnected = []
        for ws in self.connected_websockets:
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                disconnected.append(ws)
        
        for ws in disconnected:
            if ws in self.connected_websockets:
                self.connected_websockets.remove(ws)

    def start_stream(self, mode="live", speed=0.2, poll_interval=5):
        """Starts real-time live trading feed or simulation playback for all tickers."""
        if self.is_simulating:
            self.stop_stream()
            
        self.mode = mode
        self.is_simulating = True
        
        for ticker in self.tickers:
            if ticker in self.data_ingestions:
                # Bind lambda capturing the current ticker
                self.data_ingestions[ticker].subscribe(
                    lambda row, t=ticker: self.process_tick(row, t)
                )
                if mode == "live":
                    self.data_ingestions[ticker].start_live_stream(interval_seconds=poll_interval)
                else:
                    self.data_ingestions[ticker].start_simulation_stream(
                        speed_seconds=speed,
                        start_index=150
                    )
        logging.info(f"Multi-asset streaming started in {mode} mode.")

    def stop_stream(self):
        self.is_simulating = False
        for ticker in self.tickers:
            if ticker in self.data_ingestions:
                self.data_ingestions[ticker].stop_stream()
                self.data_ingestions[ticker].subscribers = []
        logging.info("All ticker streams stopped.")

# Instantiate Orchestrator
orchestrator = NexusTraderOrchestrator()

@app.on_event("startup")
async def startup_event():
    await orchestrator.initialize()
    # Auto-start live stream on startup (true live data)
    orchestrator.start_stream(mode="live", poll_interval=5)
    try:
        update_crontab_schedule()
    except Exception as e:
        logging.error(f"Failed to initialize crontab on startup: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    orchestrator.stop_stream()

# API Endpoints
@app.get("/api/status")
def get_status():
    current_prices = {}
    for t in orchestrator.tickers:
        if t in orchestrator.data_ingestions:
            current_prices[t] = orchestrator.data_ingestions[t].live_price or 0.0
            
    return {
        "balance": orchestrator.execution_engine.balance,
        "equity": orchestrator.execution_engine.get_equity(current_prices),
        "positions": orchestrator.execution_engine.active_positions,
        "tickers": orchestrator.tickers
    }

def reconstruct_trades_from_exchange(exchange):
    try:
        raw_trades = exchange.fetch_my_trades(limit=100)
        if not raw_trades:
            return []
        # Sort raw trades chronologically
        raw_trades.sort(key=lambda x: x.get('timestamp', 0))
        
        # FIFO inventory tracking per symbol
        inventories = {} # symbol -> list of dicts: {"price": float, "qty": float, "timestamp": float}
        completed_trades = []
        
        for rt in raw_trades:
            symbol = rt.get('symbol', '')
            side = rt.get('side', '').upper() # BUY or SELL
            price = float(rt.get('price', 0.0))
            qty = float(rt.get('amount', 0.0))
            timestamp = rt.get('timestamp', 0) / 1000.0
            
            # Convert slash symbol (e.g. BTC/EUR) to dash (e.g. BTC-EUR)
            dash_symbol = symbol.replace("/", "-")
            
            if dash_symbol not in inventories:
                inventories[dash_symbol] = []
                
            if side == 'BUY':
                inventories[dash_symbol].append({"price": price, "qty": qty, "timestamp": timestamp})
            elif side == 'SELL':
                # Pair with BUY inventory (FIFO)
                remaining_qty = qty
                matched_cost = 0.0
                matched_qty = 0.0
                
                while remaining_qty > 0 and inventories[dash_symbol]:
                    buy_node = inventories[dash_symbol][0]
                    if buy_node["qty"] <= remaining_qty:
                        matched_cost += buy_node["qty"] * buy_node["price"]
                        matched_qty += buy_node["qty"]
                        remaining_qty -= buy_node["qty"]
                        inventories[dash_symbol].pop(0)
                    else:
                        matched_cost += remaining_qty * buy_node["price"]
                        matched_qty += remaining_qty
                        buy_node["qty"] -= remaining_qty
                        remaining_qty = 0
                        
                if matched_qty > 0:
                    avg_entry = matched_cost / matched_qty
                    pnl = (price - avg_entry) * matched_qty
                    pnl_pct = pnl / matched_cost if matched_cost > 0 else 0.0
                    completed_trades.append({
                        "exit_time": timestamp,
                        "symbol": dash_symbol,
                        "direction": "BUY",
                        "quantity": matched_qty,
                        "entry_price": avg_entry,
                        "exit_price": price,
                        "pnl": pnl,
                        "pnl_percent": pnl_pct,
                        "exit_reason": "EXCHANGE FILL"
                    })
        completed_trades.sort(key=lambda x: x['exit_time'], reverse=True)
        return completed_trades
    except Exception as e:
        logging.error(f"Error reconstructing trades from exchange: {e}")
        return []

@app.get("/api/trades")
def get_trades():
    local_trades = database.load_trades()
    config_path = os.path.expanduser("~/.nexustrader/config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                cfg = json.load(f)
            if cfg.get("trading_mode") == "live":
                creds = cfg.get("api_credentials", {})
                api_key = creds.get("api_key")
                api_secret = creds.get("api_secret")
                broker = cfg.get("broker", "kraken").lower()
                
                if api_key and api_secret:
                    import ccxt
                    exchange_class = getattr(ccxt, broker)
                    exchange = exchange_class({
                        'apiKey': api_key,
                        'secret': api_secret,
                        'enableRateLimit': True,
                    })
                    exchange_trades = reconstruct_trades_from_exchange(exchange)
                    if exchange_trades:
                        merged = list(local_trades)
                        for et in exchange_trades:
                            matched = False
                            et_time = int(et["exit_time"])
                            for lt in merged:
                                if abs(int(lt["exit_time"]) - et_time) < 15:
                                    matched = True
                                    break
                            if not matched:
                                merged.append(et)
                        merged.sort(key=lambda x: x["exit_time"], reverse=True)
                        return merged
        except Exception as e:
            logging.error(f"Error merging exchange trades: {e}")
            
    return local_trades

@app.get("/api/portfolio/history")
def get_portfolio_history(timeframe: str = "1W"):
    try:
        init_bal_str = database.load_setting("initial_portfolio_balance")
        init_bal = float(init_bal_str) if init_bal_str else 100.0
        
        now = time.time()
        if timeframe == "1D":
            cutoff = now - 86400
            label_format = "%H:%M"
        elif timeframe == "1W":
            cutoff = now - 7 * 86400
            label_format = "%m-%d %H:%M"
        elif timeframe == "1M":
            cutoff = now - 30 * 86400
            label_format = "%m-%d"
        elif timeframe == "1Y":
            cutoff = now - 365 * 86400
            label_format = "%Y-%m"
        else:
            conn_temp = sqlite3.connect(database.DB_PATH)
            cursor_temp = conn_temp.cursor()
            cursor_temp.execute("SELECT MIN(exit_time) FROM trades")
            row = cursor_temp.fetchone()
            first_trade_time = row[0] if row and row[0] else None
            conn_temp.close()
            
            if first_trade_time:
                cutoff = float(first_trade_time)
            else:
                cutoff = now - 86400
            label_format = "%Y-%m-%d"
            
        conn = sqlite3.connect(database.DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT timestamp, equity, pnl FROM portfolio_history ORDER BY timestamp ASC"
        )
        rows = cursor.fetchall()
        
        event_points = []
        if len(rows) > 1:
            for r_time, r_eq, r_pnl in rows:
                event_points.append({
                    "timestamp": float(r_time),
                    "equity": float(r_eq),
                    "pnl": float(r_pnl)
                })
        else:
            cursor.execute("SELECT exit_time, pnl FROM trades ORDER BY exit_time ASC")
            trades = cursor.fetchall()
            
            current_equity = init_bal
            event_points = [{"timestamp": 0.0, "equity": init_bal, "pnl": 0.0}]
            
            cumulative_pnl = 0.0
            for t_time, pnl in trades:
                if not t_time:
                    continue
                cumulative_pnl += pnl
                current_equity = init_bal + cumulative_pnl
                event_points.append({
                    "timestamp": float(t_time),
                    "equity": current_equity,
                    "pnl": cumulative_pnl
                })
                
        conn.close()
        
        # Resample logic to prevent X axis distortion and speed up rendering
        num_points = 50
        resampled_points = []
        
        if event_points:
            # Find the starting equity at cutoff
            starting_equity = event_points[0]["equity"]
            starting_pnl = event_points[0]["pnl"]
            for p in event_points:
                if p["timestamp"] <= cutoff:
                    starting_equity = p["equity"]
                    starting_pnl = p["pnl"]
            
            points_after = [p for p in event_points if p["timestamp"] > cutoff]
            step = (now - cutoff) / (num_points - 1)
            
            current_idx = 0
            current_equity = starting_equity
            current_pnl = starting_pnl
            
            for i in range(num_points):
                target_t = cutoff + i * step
                while current_idx < len(points_after) and points_after[current_idx]["timestamp"] <= target_t:
                    current_equity = points_after[current_idx]["equity"]
                    current_pnl = points_after[current_idx]["pnl"]
                    current_idx += 1
                
                resampled_points.append({
                    "timestamp": target_t,
                    "equity": current_equity,
                    "pnl": current_pnl
                })
                
        formatted = []
        for p in resampled_points:
            t_struct = time.localtime(p["timestamp"])
            label = time.strftime(label_format, t_struct)
            formatted.append({
                "label": label,
                "equity": round(p["equity"], 2),
                "pnl": round(p["pnl"], 2)
            })
            
        return formatted
    except Exception as e:
        logging.error(f"Error in portfolio history: {e}")
        return []

@app.get("/api/history")
def get_ticker_history(ticker: str = "ETH-USD"):
    if ticker not in orchestrator.data_ingestions:
        return []
    
    ingest = orchestrator.data_ingestions[ticker]
    df = ingest.data.tail(40)
    history = []
    for idx, r in df.iterrows():
        # Handle index timestamp or column timestamp
        ts = str(idx)
        if 'timestamp' in r:
            ts = str(r['timestamp'])
        
        history.append({
            "timestamp": ts,
            "close": float(r['close']),
            "bb_upper": float(r.get('bb_upper', r['close'])),
            "bb_lower": float(r.get('bb_lower', r['close'])),
            "rsi": float(r.get('rsi', 50))
        })
    return history

@app.get("/api/weights")
def get_weights(ticker: str = "ETH-USD"):
    if ticker not in orchestrator.strategy_ensembles:
        return {}
    ensemble = orchestrator.strategy_ensembles[ticker]
    
    # Calculate DNA and load steps
    steps_key = f"lifetime_training_steps_{ticker}"
    steps = int(database.load_setting(steps_key, "0"))
    
    db_net_str = database.load_setting(f"policy_net_weights_{ticker}")
    if db_net_str:
        import hashlib
        dna_hash = hashlib.md5(db_net_str.encode('utf-8')).hexdigest()[:8].upper()
        model_dna = f"NN-{dna_hash}"
    else:
        model_dna = "NN-DEFAULT"
        
    return {
        "weights": {
            ensemble.strategies[i].name: float(ensemble.weights[i])
            for i in range(len(ensemble.weights))
        },
        "lifetime_steps": steps,
        "model_dna": model_dna
    }

@app.get("/api/weights/history")
def get_weights_history(ticker: str = "ETH-USD"):
    try:
        return database.load_weights_history(ticker)
    except Exception as e:
        logging.error(f"Error loading weights history: {e}")
        return []

@app.post("/api/control")
def control_simulation(action: str, speed: float = 0.2, mode: str = "live"):
    if action == "start":
        orchestrator.start_stream(mode=mode, speed=speed, poll_interval=5)
        return {"status": "started", "mode": mode, "speed": speed}
    elif action == "stop":
        orchestrator.stop_stream()
        return {"status": "stopped"}
    elif action == "reset":
        orchestrator.stop_stream()
        
        # Reset the balance setting in SQLite database
        database.save_setting("portfolio_balance", "100.00")
        database.save_setting("initial_portfolio_balance", "100.00")
        
        # Completely clear trades and ticks history from SQLite
        conn = database.get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM trades")
            cursor.execute("DELETE FROM ticks")
            conn.commit()
            logging.info("Cleared all trades and ticks tables in DB reset.")
        except Exception as e:
            logging.error(f"Error clearing DB tables on reset: {e}")
        finally:
            conn.close()
            
        # Instantiate fresh execution engine
        orchestrator.execution_engine = ExecutionEngine(initial_balance=100.0)
        orchestrator.execution_engine.set_learning_callback(orchestrator.on_trade_closed)
        
        # Reset weights & learning engines for all tickers
        for ticker in orchestrator.tickers:
            if ticker in orchestrator.strategy_ensembles:
                ensemble = orchestrator.strategy_ensembles[ticker]
                num_strats = len(ensemble.strategies)
                ensemble.weights = [1.0/num_strats] * num_strats
                orchestrator.learning_engines[ticker] = LearningEngine(num_strategies=num_strats, learning_rate=0.15)
                # Delete saved weight states from database
                database.save_setting(f"policy_net_weights_{ticker}", "")
                
        # Start stream in original running mode
        run_mode = orchestrator.mode if hasattr(orchestrator, "mode") else "live"
        orchestrator.start_stream(mode=run_mode, speed=speed, poll_interval=5)
        return {"status": "reset_completed", "mode": run_mode}
    return {"error": "Invalid action"}

@app.get("/api/system/config")
def get_system_config():
    config_path = os.path.expanduser("~/.nexustrader/config.json")
    trading_mode = "paper"
    broker = "kraken"
    api_key = ""
    api_secret = ""
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                cfg = json.load(f)
                trading_mode = cfg.get("trading_mode", "paper")
                broker = cfg.get("broker", "kraken")
                api_key = cfg.get("api_credentials", {}).get("api_key", "")
                api_secret = cfg.get("api_credentials", {}).get("api_secret", "")
        except Exception:
            pass
            
    return {
        "trading_mode": trading_mode,
        "broker": broker,
        "api_key": api_key,
        "api_secret": api_secret,
        "trailing_stop": database.load_setting("trailing_stop_enabled", "false") == "true",
        "cooldown": float(database.load_setting("loss_cooldown_hours", "4.0")),
        "tp_multiplier": float(database.load_setting("opt_tp_multiplier", "2.5")),
        "sl_multiplier": float(database.load_setting("opt_sl_multiplier", "1.5")),
        "risk_mode": database.load_setting("risk_mode", "conservative"),
        "max_drawdown": float(database.load_setting("max_daily_drawdown", "5.0"))
    }

@app.post("/api/system/config")
def update_system_config(trading_mode: str, risk_mode: str, max_drawdown: float, broker: str = "kraken", api_key: str = "", api_secret: str = "", trailing_stop: bool = False, cooldown: float = 4.0, tp_multiplier: float = 2.5, sl_multiplier: float = 1.5):
    # 1. Update config.json
    config_path = os.path.expanduser("~/.nexustrader/config.json")
    cfg = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                cfg = json.load(f)
        except Exception:
            pass
            
    cfg["trading_mode"] = trading_mode
    cfg["broker"] = broker
    if "api_credentials" not in cfg:
        cfg["api_credentials"] = {}
    cfg["api_credentials"]["api_key"] = api_key
    cfg["api_credentials"]["api_secret"] = api_secret
    
    try:
        with open(config_path, "w") as f:
            json.dump(cfg, f, indent=2)
        
        # Hot-reload in execution engine
        orchestrator.execution_engine.trading_mode = trading_mode
        orchestrator.execution_engine.config = cfg
        logging.info(f"System configuration and API credentials updated for: {broker}")
    except Exception as e:
        logging.error(f"Error updating config.json: {e}")
        
    # 2. Update Risk Mode
    if risk_mode in ["conservative", "aggressive", "hyper_growth"]:
        orchestrator.probability_engine.set_risk_mode(risk_mode)
        database.save_setting("risk_mode", risk_mode)
        logging.info(f"System Risk Mode updated to: {risk_mode}")
        orchestrator._run_async(orchestrator.broadcast_message({
            "type": "risk_mode_updated",
            "risk_mode": risk_mode
        }))
        
    # 3. Update Max Drawdown
    database.save_setting("max_daily_drawdown", str(max_drawdown))
    logging.info(f"Max Daily Drawdown updated to: {max_drawdown}%")

    # 4. Update Trailing Stop, Cooldown, and ATR Multipliers
    database.save_setting("trailing_stop_enabled", "true" if trailing_stop else "false")
    database.save_setting("loss_cooldown_hours", str(cooldown))
    database.save_setting("opt_tp_multiplier", str(tp_multiplier))
    database.save_setting("opt_sl_multiplier", str(sl_multiplier))
    logging.info(f"Trailing Stop: {trailing_stop}, Cooldown: {cooldown}h, TP mult: {tp_multiplier}x, SL mult: {sl_multiplier}x updated.")
    
    return {"status": "success"}

@app.get("/api/exchange/status")
def get_exchange_status():
    config_path = os.path.expanduser("~/.nexustrader/config.json")
    if not os.path.exists(config_path):
        return {"error": "Config not found"}
        
    try:
        with open(config_path, "r") as f:
            cfg = json.load(f)
            
        creds = cfg.get("api_credentials", {})
        api_key = creds.get("api_key")
        api_secret = creds.get("api_secret")
        broker = cfg.get("broker", "kraken").lower()
        
        if not api_key or not api_secret:
            return {"holdings": [], "open_orders": [], "message": "API credentials missing."}
            
        import ccxt
        exchange_class = getattr(ccxt, broker)
        exchange = exchange_class({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
        })
        
        # 1. Fetch balances
        balance_info = exchange.fetch_balance()
        total_bal = balance_info.get('total', {})
        
        # Fetch conversion rates
        prices = {}
        try:
            tickers = exchange.fetch_tickers(['BTC/EUR', 'ETH/EUR', 'SOL/EUR', 'DOGE/EUR', 'XRP/EUR'])
            prices = {sym.split('/')[0]: float(tick['last']) for sym, tick in tickers.items() if tick.get('last') is not None}
        except Exception:
            pass
            
        holdings = []
        for asset, qty in total_bal.items():
            qty = float(qty)
            if qty > 0.000001:
                price_eur = 1.0
                if asset != 'EUR':
                    price_eur = prices.get(asset, 0.0)
                val_eur = qty * price_eur
                holdings.append({
                    "asset": asset,
                    "quantity": qty,
                    "price_eur": price_eur,
                    "value_eur": val_eur
                })
                
        # Sort holdings: EUR always first, then others by value desc
        holdings.sort(key=lambda x: (x["asset"] != "EUR", -x["value_eur"]))
        # 2. Fetch Open Positions
        open_positions = []
        try:
            if hasattr(exchange, 'has') and exchange.has.get('fetchPositions', False):
                pos = exchange.fetch_positions()
                for p in pos:
                    contracts = float(p.get("contracts", p.get("size", 0.0) or 0.0))
                    if contracts > 0 or p.get("side") is not None:
                        open_positions.append({
                            "id": p.get("id"),
                            "symbol": p.get("symbol", "").replace("/", "-"),
                            "side": p.get("side", "").upper(),
                            "contracts": contracts,
                            "entryPrice": p.get("entryPrice"),
                            "markPrice": p.get("markPrice", p.get("currentPrice")),
                            "unrealizedPnl": p.get("unrealizedPnl"),
                            "leverage": p.get("leverage")
                        })
        except Exception as pe:
            logging.error(f"Error fetching open positions: {pe}")

        # 3. Fetch Open Orders
        open_orders = []
        try:
            orders = exchange.fetch_open_orders()
            for o in orders:
                open_orders.append({
                    "id": o.get("id"),
                    "symbol": o.get("symbol", "").replace("/", "-"),
                    "side": o.get("side", "").upper(),
                    "type": o.get("type", "").upper(),
                    "price": o.get("price"),
                    "amount": o.get("amount"),
                    "filled": o.get("filled"),
                    "remaining": o.get("remaining"),
                    "cost": o.get("cost"),
                    "timestamp": o.get("timestamp")
                })
        except Exception as oe:
            logging.error(f"Error fetching open orders: {oe}")
            
        return {
            "holdings": holdings,
            "open_positions": open_positions,
            "open_orders": open_orders
        }
    except Exception as e:
        logging.error(f"Error in get_exchange_status API: {e}")
        return {"error": str(e)}

@app.post("/api/system/risk_mode")
def update_system_risk_mode(risk_mode: str):
    if risk_mode in ["conservative", "aggressive", "hyper_growth"]:
        orchestrator.probability_engine.set_risk_mode(risk_mode)
        database.save_setting("risk_mode", risk_mode)
        logging.info(f"System Risk Mode updated to: {risk_mode}")
        orchestrator._run_async(orchestrator.broadcast_message({
            "type": "risk_mode_updated",
            "risk_mode": risk_mode
        }))
    return {"error": "Invalid risk mode"}

@app.get("/api/system/test_broker")
def test_broker_connection():
    config_path = os.path.expanduser("~/.nexustrader/config.json")
    if not os.path.exists(config_path):
        return {"status": "error", "message": "No configuration file found."}
        
    try:
        with open(config_path, "r") as f:
            cfg = json.load(f)
    except Exception as e:
        return {"status": "error", "message": f"Failed to read config.json: {e}"}
        
    broker_type = cfg.get("broker", "kraken").lower()
    creds = cfg.get("api_credentials", {})
    api_key = creds.get("api_key", "")
    api_secret = creds.get("api_secret", "")
    
    if not api_key or not api_secret:
        return {"status": "error", "message": "API Key or Secret is missing in config."}
        
    try:
        import ccxt
        if not hasattr(ccxt, broker_type):
            return {"status": "error", "message": f"Broker '{broker_type}' is not supported by CCXT."}
            
        exchange_class = getattr(ccxt, broker_type)
        exchange = exchange_class({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
        })
        
        # Test authenticating by fetching balance
        balance_info = exchange.fetch_balance()
        balances = {k: v for k, v in balance_info.get('total', {}).items() if v > 0}
        
        return {
            "status": "success",
            "message": f"Successfully connected to {broker_type.upper()} API!",
            "balances": balances
        }
    except Exception as e:
        logging.error(f"Broker test connection failed: {e}")
        return {
            "status": "error",
            "message": f"Connection failed: {str(e)}"
        }

@app.post("/api/system/reset_cooldowns")
def reset_all_cooldowns():
    try:
        for symbol in orchestrator.tickers:
            database.save_setting(f"cooldown_end_{symbol}", "0.0")
        logging.info("All ticker loss cooldown periods reset successfully.")
        return {"status": "success", "message": "All loss cooldowns reset. Ready to trade!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/system/optimize/sentiment")
def trigger_sentiment_optimization():
    try:
        from weekly_optimizer import optimize_sentiment_weights
        optimize_sentiment_weights()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        report_path = os.path.join(base_dir, "blog", "daily_summaries", "weekly_sentiment_optimization.md")
        if os.path.exists(report_path):
            with open(report_path, "r") as f:
                return {"status": "success", "log": f.read()}
        return {"status": "success", "log": "Sentiment source optimization completed successfully."}
    except Exception as e:
        logging.error(f"Error in manual sentiment optimization: {e}")
        return {"status": "error", "error": str(e)}

@app.post("/api/system/optimize/parameters")
def trigger_parameter_optimization():
    try:
        from self_improvement_agent import run_self_improvement
        run_self_improvement()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        report_path = os.path.join(base_dir, "blog", "daily_summaries", "weekly_self_improvement.md")
        if os.path.exists(report_path):
            with open(report_path, "r") as f:
                return {"status": "success", "log": f.read()}
        return {"status": "success", "log": "Parameter backtest optimization completed successfully."}
    except Exception as e:
        logging.error(f"Error in manual parameter optimization: {e}")
        return {"status": "error", "error": str(e)}

@app.post("/api/system/optimize/self_dev")
def trigger_self_development():
    try:
        from agent_self_developer import run_self_developer
        res = run_self_developer()
        if res.startswith("Success"):
            return {"status": "success", "log": res}
        else:
            return {"status": "error", "error": res}
    except Exception as e:
        logging.error(f"Error in manual AI self-development: {e}")
        return {"status": "error", "error": str(e)}

DEFAULT_PROMPT_QUANT = """You are a world-class Quantitative Researcher, PhD in Mathematical Finance, and elite risk manager critically evaluating the performance of the NexusTrader self-learning ensemble bot.

Our core operational mandate is to scale net returns to a stable, risk-adjusted target of $1,000 USD per day while strictly minimizing maximum drawdown (MDD) and tail risk.

Analyze the provided dataset using rigorous statistical methods:
1. Volatility Regime Profiling: Analyze the average true range (ATR), recent volatility shifts, and risk-reward ratios.
2. Trade Return Skewness: Critique the win/loss distribution. Are the losses fat-tailed? Is the Sharpe/Sortino ratio optimal?
3. Ensemble Synergy: Evaluate the interaction of the strategy ensemble (RSI Reversion, Kalman filter trends, ML models). Ensure weights do not create unhedged systemic beta exposure.
4. Optimal Stopping Theory: Review the Take Profit (TP) and Stop Loss (SL) ATR multipliers. Formulate if current boundaries reflect optimal stopping boundaries under a drift-diffusion model.

Provide a high-fidelity quantitative assessment, detailing:
- A mathematical critique of the current strategy parameters.
- 2-3 specific equations, models, or quantitative adjustments to enhance the bot's mathematical edge.

At the very end of your response, output a strict JSON block specifying the exact configuration parameters to save to our execution settings:
```json
{
  "recommended_risk_mode": "conservative" | "aggressive" | "hyper_growth",
  "recommended_tp_multiplier": float,
  "recommended_sl_multiplier": float
}
```"""

DEFAULT_PROMPT_DEV = """You are Antigravity, an elite autonomous AI software engineer. Your goal is to improve the NexusTrader algorithmic trading bot codebase.
Our mission is to build features and UI visualizations that help the bot consistently earn $1,000 USD a day by giving the trader better indicators, diagnostic data, or performance controls.

Identify ONE specific, clean, non-breaking improvement or feature to implement. 
Return your response STRICTLY in JSON format containing "explanation" and "modifications" find-and-replace rules.
"""

DEFAULT_PROMPT_BLOG = """You are an expert quantitative researcher, financial blogger, and algorithmic trading editor. 
Our mission is to help the NexusTrader bot scale to a target of earning $1,000 USD a day.

Rewrite the raw report data into a highly detailed, witty, professional, and engaging market-commentary blog post.
Analyze metrics, explain profit factors, detail policy weights, and discuss the bot's mathematical evolution.
Keep all quantitative tables intact."""

@app.get("/api/system/prompts")
def get_prompts():
    return {
        "prompt_quant": database.load_setting("prompt_self_improvement", DEFAULT_PROMPT_QUANT),
        "prompt_dev": database.load_setting("prompt_self_developer", DEFAULT_PROMPT_DEV),
        "prompt_blog": database.load_setting("prompt_blog_agent", DEFAULT_PROMPT_BLOG)
    }

@app.post("/api/system/prompts")
def update_prompts(prompt_quant: str, prompt_dev: str, prompt_blog: str):
    try:
        database.save_setting("prompt_self_improvement", prompt_quant)
        database.save_setting("prompt_self_developer", prompt_dev)
        database.save_setting("prompt_blog_agent", prompt_blog)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def update_crontab_schedule():
    try:
        daily_hour = int(database.load_setting("daily_agent_hour", "0"))
        weekly_day = int(database.load_setting("weekly_agent_day", "0"))  # 0=Sunday
        weekly_hour = int(database.load_setting("weekly_agent_hour", "23"))
        
        project_path = os.path.dirname(os.path.abspath(__file__))
        
        # Generate cron commands dynamically
        daily_line = f"0 {daily_hour} * * * cd {project_path} && ./daily_agent.sh >> daily_agent.log 2>&1"
        weekly_line = f"59 {weekly_hour} * * {weekly_day} cd {project_path} && /usr/bin/python3 blog_agent.py >> blog_agent.log 2>&1"
        
        # Read current crontab
        import subprocess
        try:
            res = subprocess.run(["/usr/bin/crontab", "-l"], capture_output=True, text=True)
            lines = res.stdout.splitlines() if res.returncode == 0 else []
        except Exception:
            lines = []
            
        new_lines = []
        for line in lines:
            if "daily_agent.sh" not in line and "blog_agent.py" not in line:
                new_lines.append(line)
                
        new_lines.append(daily_line)
        new_lines.append(weekly_line)
        
        # Write back to crontab
        cron_content = "\n".join(new_lines) + "\n"
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write(cron_content)
            temp_name = f.name
            
        try:
            subprocess.run(["/usr/bin/crontab", temp_name])
        finally:
            try:
                os.unlink(temp_name)
            except Exception:
                pass
    except Exception as e:
        logging.error(f"Error updating crontab schedule: {e}")

@app.get("/api/system/schedule")
def get_system_schedule():
    return {
        "daily_agent_hour": int(database.load_setting("daily_agent_hour", "0")),
        "weekly_agent_day": int(database.load_setting("weekly_agent_day", "0")),
        "weekly_agent_hour": int(database.load_setting("weekly_agent_hour", "23"))
    }

@app.post("/api/system/schedule")
def update_system_schedule(daily_agent_hour: int, weekly_agent_day: int, weekly_agent_hour: int):
    try:
        if not (0 <= daily_agent_hour <= 23):
            return {"status": "error", "error": "Daily hour must be between 0 and 23"}
        if not (0 <= weekly_agent_day <= 6):
            return {"status": "error", "error": "Weekly day must be between 0 and 6"}
        if not (0 <= weekly_agent_hour <= 23):
            return {"status": "error", "error": "Weekly hour must be between 0 and 23"}
            
        database.save_setting("daily_agent_hour", str(daily_agent_hour))
        database.save_setting("weekly_agent_day", str(weekly_agent_day))
        database.save_setting("weekly_agent_hour", str(weekly_agent_hour))
        
        # Update system crontab dynamically
        update_crontab_schedule()
        return {"status": "success"}
    except Exception as e:
        logging.error(f"Error in manual schedule update: {e}")
        return {"status": "error", "error": str(e)}

@app.get("/api/blog/config")
def get_blog_config():
    return {
        "blog_enabled": database.load_setting("blog_enabled", "true") == "true",
        "blog_ai_enabled": database.load_setting("blog_ai_enabled", "false") == "true",
        "blog_gemini_api_key": database.load_setting("blog_gemini_api_key", ""),
        "blog_git_push_enabled": database.load_setting("blog_git_push_enabled", "true") == "true"
    }

@app.post("/api/blog/config")
def update_blog_config(enabled: bool, ai_enabled: bool, api_key: str, git_push_enabled: bool):
    database.save_setting("blog_enabled", "true" if enabled else "false")
    database.save_setting("blog_ai_enabled", "true" if ai_enabled else "false")
    database.save_setting("blog_gemini_api_key", api_key)
    database.save_setting("blog_git_push_enabled", "true" if git_push_enabled else "false")
    return {"status": "success"}

@app.post("/api/blog/generate")
async def trigger_blog_generation(use_mock: bool = False):
    import subprocess
    import sys
    import os
    
    cmd = [sys.executable, get_resource_path("blog_agent.py")]
    if use_mock:
        cmd.append("--mock")
        
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            return {"status": "success", "output": stdout.decode()}
        else:
            return {"status": "error", "error": stderr.decode()}
    except Exception as e:
        return {"status": "error", "error": str(e)}

# Websocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    orchestrator.connected_websockets.append(websocket)
    try:
        # Send initial configuration and state (defaults to first ticker weights for basic UI compatibility)
        first_ticker = orchestrator.tickers[0]
        ensemble = orchestrator.strategy_ensembles.get(first_ticker, None)
        
        # Calculate DNA signature on startup for initial state
        steps_key = f"lifetime_training_steps_{first_ticker}"
        steps = int(database.load_setting(steps_key, "0"))
        db_net_str = database.load_setting(f"policy_net_weights_{first_ticker}")
        if db_net_str:
            import hashlib
            dna_hash = hashlib.md5(db_net_str.encode('utf-8')).hexdigest()[:8].upper()
            model_dna = f"NN-{dna_hash}"
        else:
            model_dna = "NN-DEFAULT"
            
        init_state = {
            "type": "init",
            "tickers": orchestrator.tickers,
            "ticker": first_ticker,
            "balance": orchestrator.execution_engine.balance,
            "initial_balance": orchestrator.execution_engine.initial_balance,
            "trading_mode": orchestrator.execution_engine.trading_mode,
            "broker": orchestrator.execution_engine.config.get("broker", "kraken"),
            "weights": {
                ensemble.strategies[i].name: float(ensemble.weights[i])
                for i in range(len(ensemble.weights))
            } if ensemble else {},
            "risk_mode": orchestrator.probability_engine.risk_mode,
            "strategies": [s.name for s in ensemble.strategies] if ensemble else [],
            "trades": orchestrator.execution_engine.closed_trades,
            "lifetime_steps": steps,
            "model_dna": model_dna
        }
        await websocket.send_text(json.dumps(init_state))
        
        while True:
            # Keep connection alive, listen for messages
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        logging.info("WebSocket disconnected.")
    except Exception as e:
        logging.error(f"WebSocket error: {e}")
    finally:
        if websocket in orchestrator.connected_websockets:
            orchestrator.connected_websockets.remove(websocket)

# Serve Frontend SPA
@app.get("/")
def read_root():
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    return FileResponse(get_resource_path("dashboard/index.html"), headers=headers)

@app.get("/sw.js")
def get_service_worker():
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    return FileResponse(get_resource_path("dashboard/sw.js"), media_type="application/javascript", headers=headers)

@app.get("/manifest.json")
def get_manifest():
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    return FileResponse(get_resource_path("dashboard/manifest.json"), media_type="application/json", headers=headers)

app.mount("/dashboard", StaticFiles(directory=get_resource_path("dashboard")), name="dashboard")

if __name__ == "__main__":
    import sys
    is_headless = "--headless" in sys.argv
    has_display = ("DISPLAY" in os.environ or "WAYLAND_DISPLAY" in os.environ) and not is_headless
    
    if has_display:
        import threading
        import time
        
        def run_server():
            logging.info("Starting backend server thread...")
            try:
                uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
            except Exception as e:
                logging.error(f"Uvicorn server crashed: {e}")

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        time.sleep(1.2)
        
        try:
            import webview
            logging.info("Launching standalone desktop window via pywebview...")
            webview.create_window(
                title="NexusTrader Desktop App",
                url="http://127.0.0.1:8000",
                width=1280,
                height=850,
                resizable=True
            )
            webview.start()
            logging.info("GUI window closed. Exiting application.")
        except Exception as e:
            logging.error(f"Native GUI window failed: {e}. Keeping server thread alive.")
            try:
                while server_thread.is_alive():
                    time.sleep(1.0)
            except KeyboardInterrupt:
                logging.info("Shutting down via KeyboardInterrupt.")
    else:
        logging.info("Headless environment detected (no DISPLAY). Running server on main thread...")
        try:
            uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
        except KeyboardInterrupt:
            logging.info("Shutting down server.")
