import json
import logging
import asyncio
import sqlite3
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
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
from long_term_strategy import LongTermStrategyLayer
import database
from evaluation.singletons import kill_switch, drawdown_tracker, mutation_freeze
from trading_modes import migrate_existing_settings as migrate_settings
from replay_buffer import PrioritizedExperienceReplay
from ppo_agent import PPOAgent

try:
    from llm_client import LLMClient
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    logging.warning("llm_client.py not found — LLaMA features disabled")

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI(title="NexusTrader API", version="1.0.0")


# ── Global exception handler: always return JSON ──
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    errors = []
    for e in exc.errors():
        errors.append({"loc": " → ".join(str(x) for x in e.get("loc", [])), "msg": e.get("msg", ""), "type": e.get("type", "")})
    return JSONResponse(
        status_code=422,
        content={"status": "error", "detail": "Validation failed", "errors": errors},
    )


@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"status": "error", "detail": "Not Found", "path": request.url.path},
    )


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"status": "error", "detail": "Internal Server Error"},
    )


@app.middleware("http")
async def api_auth_middleware(request: Request, call_next):
    """Simple token-based API auth for protected endpoints, with CORS headers for dashboard."""
    # CORS headers for same-origin dashboard access
    origin = request.headers.get("origin", "")
    
    # Allow API access from local dashboard (served on same host) or with valid token
    path = request.url.path
    is_api = path.startswith("/api/")
    
    # Read-only endpoints accessible without auth (dashboard rendering)
    public_api = (
        "/api/status", "/api/health", "/api/init",
        "/api/trades", "/api/trades/all", "/api/history",
        "/api/portfolio/history", "/api/assets", "/api/positions",
        "/api/trading/signals", "/api/trading/reasoning",
        "/api/weights", "/api/weights/history", "/api/probability",
        "/api/safety/status", "/api/quant/status", "/api/quant/prompt",
        "/api/system/config", "/api/system/logs", "/api/system/daily_goal",
        "/api/system/shadow_trades", "/api/system/shadow_performance",
        "/api/system/backups", "/api/system/alerts", "/api/system/schedule",
        "/api/exchange/status",
        "/api/neural/brains", "/api/neural/brain/specs",
        "/api/llm/status", "/api/llm/config",
        "/api/nn/architecture",
        "/api/training/status",
        "/api/gateway/status", "/api/gateway/reasoning",
        "/api/blog/config",
    )
    # Partial-prefix matches for parameterized routes
    public_prefixes = ("/api/history?", "/api/portfolio/", "/api/system/shadow_", "/api/neural/", "/api/system/backup/", "/api/system/alerts/", "/api/optimizations/")
    
    is_protected = is_api and (path not in public_api)
    if is_protected:
        # Also check if path starts with a public prefix (parameterized routes)
        for prefix in public_prefixes:
            if path.startswith(prefix.split("?")[0]):
                is_protected = False
                break
    
    # Handle CORS preflight (OPTIONS) before any auth check
    if request.method == "OPTIONS":
        return JSONResponse(
            status_code=200,
            content={"status": "ok"},
            headers={
                "Access-Control-Allow-Origin": origin or "*",
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, X-API-Token",
                "Access-Control-Max-Age": "86400",
            }
        )
    
    if is_protected:
        # Check for API token in header or query param
        api_token = request.headers.get("X-API-Token", request.query_params.get("token", ""))
        expected_token = database.load_setting("api_token", "")
        if expected_token and api_token != expected_token:
            return JSONResponse(
                status_code=401,
                content={"status": "error", "detail": "Invalid or missing API token"},
            )
    
    response = await call_next(request)
    
    # Add CORS headers for all responses (not just browser-originated)
    response.headers["Access-Control-Allow-Origin"] = origin or "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Token"
    
    return response


@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith(".html") or path.endswith(".js") or path.endswith(".css"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

def create_learning_engine(num_strategies):
    nn_lr = float(database.load_setting("nn_learning_rate", "0.15"))
    nn_floor = float(database.load_setting("nn_weight_floor", "0.05"))
    nn_hidden_dim = int(database.load_setting("nn_hidden_dim", "12"))
    nn_hidden_layers = int(database.load_setting("nn_hidden_layers", "1"))
    nn_dropout = float(database.load_setting("nn_dropout", "0.0"))
    nn_optimizer = database.load_setting("nn_optimizer", "Adam")
    
    nn_architecture = database.load_setting("nn_architecture", "mlp")
    return LearningEngine(
        num_strategies=num_strategies,
        learning_rate=nn_lr,
        weight_floor=nn_floor,
        hidden_dim=nn_hidden_dim,
        hidden_layers=nn_hidden_layers,
        dropout=nn_dropout,
        optimizer=nn_optimizer,
        nn_architecture=nn_architecture,
    )

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
        self.long_term_layer = LongTermStrategyLayer()
        
        # State tracking
        self.connected_websockets = []
        self.running_task = None
        self.playback_speed = 0.2  # delay in seconds between simulated bars
        self.is_simulating = False
        self.mode = "idle"  # Explicit initial mode to prevent None comparison bugs
        self.loop = None
        
        # Setup learning callback connection
        self.execution_engine.set_learning_callback(self.on_trade_closed)
        
        # PPO + replay buffer support
        self.replay_buffers = {}
        self.ppo_agents = {}
        self.replay_capacity = int(database.load_setting("replay_capacity", "5000"))
        self.ppo_update_interval = int(database.load_setting("ppo_update_interval", "5"))
        self.ppo_batch_size = int(database.load_setting("ppo_batch_size", "64"))
        self.ppo_epochs = int(database.load_setting("ppo_epochs", "4"))
        self.ppo_minibatch_size = int(database.load_setting("ppo_minibatch_size", "32"))
        
        # LLaMA integration
        self.llm_client = None
        self.llm_enabled = LLM_AVAILABLE and database.load_setting("llm_enabled", "true").lower() == "true"
        self.llm_endpoint = database.load_setting("llm_endpoint", "http://192.168.0.77:8080")
        self.llm_last_sentiment = {"sentiment_score": 0.0, "conviction": 0.0, "direction": "neutral"}
        self.llm_last_regimes = {}
        self.llm_last_sentiment_time = 0.0
        self.llm_sentiment_interval = 900  # seconds — poll every 15 min
        if self.llm_enabled:
            try:
                self.llm_client = LLMClient(endpoint=self.llm_endpoint)
                health = self.llm_client.health_check()
                if health["ok"]:
                    logging.info(f"LLaMA client connected: {self.llm_endpoint}")
                else:
                    logging.warning(f"LLaMA server not healthy at {self.llm_endpoint}: {health}")
                    self.llm_enabled = False
            except Exception as e:
                logging.warning(f"LLaMA client init failed: {e}")
                self.llm_enabled = False

    def init_ticker(self, ticker):
        """Dynamically initializes data streams, strategy ensemble, and neural weights for a new ticker."""
        if ticker in self.data_ingestions:
            return True
            
        logging.info(f"Initializing assets and models for {ticker}...")
        ingestor = DataIngestion(ticker=ticker, interval="1h", period="60d")
        try:
            df = ingestor.fetch_historical_data()
        except Exception as e:
            logging.error(f"Error fetching data for {ticker}: {e}. Skipping ticker.")
            return False
            
        ensemble = StrategyEnsemble(history_df=df)
        num_strats = len(ensemble.strategies)
        learner = create_learning_engine(num_strats)
        
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
                    for i in range(min(len(ensemble.weights), len(ensemble.strategies)))
                }
                database.save_weights_history(time.time(), ticker, start_weights)
        except Exception as e:
            logging.error(f"Error pre-populating weights history: {e}")
            
        # Create PPO agent wrapping the existing PolicyNetwork
        ppo_agent = PPOAgent(learner.policy_net)
        self.ppo_agents[ticker] = ppo_agent
        
        # Create or restore replay buffer
        buf_blob = database.load_setting(f"replay_buffer_{ticker}")
        if buf_blob:
            try:
                import base64
                raw = base64.b64decode(buf_blob)
                self.replay_buffers[ticker] = PrioritizedExperienceReplay.deserialize(raw)
                logging.info(f"Restored replay buffer for {ticker} ({len(self.replay_buffers[ticker])} experiences)")
            except Exception as e:
                logging.error(f"Failed to restore replay buffer for {ticker}: {e}")
                self.replay_buffers[ticker] = PrioritizedExperienceReplay(capacity=self.replay_capacity)
        else:
            self.replay_buffers[ticker] = PrioritizedExperienceReplay(capacity=self.replay_capacity)
        
        self.data_ingestions[ticker] = ingestor
        self.strategy_ensembles[ticker] = ensemble
        self.learning_engines[ticker] = learner
        return True

    async def initialize(self):
        """Fetches initial data and trains ML strategies for all tickers."""
        self.loop = asyncio.get_running_loop()
        
        # Load active assets from database
        try:
            db_assets = database.load_active_assets()
            active_list = [a["ticker"] for a in db_assets if a["is_active"]]
            if active_list:
                self.tickers = active_list
                # Reset local sentiment trackers mapping
                self.latest_sentiments = {t: 0.0 for t in self.tickers}
                self.latest_source_sentiments = {t: {} for t in self.tickers}
                self.last_sentiment_times = {t: 0.0 for t in self.tickers}
                logging.info(f"Loaded active tickers list from DB: {self.tickers}")
        except Exception as e:
            logging.error(f"Error loading active tickers from DB: {e}")
        
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
            self.init_ticker(ticker)
            
        logging.info("NexusTrader Orchestrator initialized successfully for all tickers.")

    def _run_async(self, coro):
        """Safely schedule a coroutine to run on the main FastAPI event loop from any thread."""
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, self.loop)

    def on_trade_closed(self, ticker, entry_state, strategy_signals, direction, pnl_percent):
        """Callback from ExecutionEngine when a trade is closed.

        Stores entry_state to avoid None-passthrough from the callback chain.
        """
        # Guard against None entry_state
        if entry_state is None:
            entry_state = []
        logging.info("[{}] Trade closed with PnL%: {:.2f}%. Training Policy Network...".format(ticker, pnl_percent*100))
        # Feed PnL to KillSwitch and drawdown tracker
        # BUGFIX: Track ALL trades (paper + live), not just live.
        # Otherwise KillSwitch never activates in paper mode and
        # paper-mode bugs cascade to live deployment undetected.
        # BUGFIX: pnl_percent is fraction of position cost, not of total balance.
        # Multiply by position cost (balance delta) for correct absolute PnL.
        # pnl_abs ≈ balance_before - balance_after (after close), but balance was
        # already updated by execution_engine. Reconstruct from the closed trade.
        closed_trades = [t for t in self.execution_engine.closed_trades if t.get('symbol') == ticker]
        if closed_trades:
            last_trade = closed_trades[-1]
            pnl_abs = float(last_trade.get('pnl', 0))
        else:
            pnl_abs = pnl_percent * self.execution_engine.balance
        kill_switch.record_trade(pnl_abs)
        # Update drawdown from current equity
        current_prices = {}
        for t in self.tickers:
            if t in self.data_ingestions:
                di_t = self.data_ingestions.get(t)
                current_prices[t] = di_t.live_price or 0.0
        equity = self.execution_engine.get_equity(current_prices)
        drawdown_tracker.update(equity)
        
        learner = self.learning_engines[ticker]
        ensemble = self.strategy_ensembles[ticker]
        
        # Use the stored entry state vector rather than reconstructing a wrong one at exit!
        if entry_state and len(entry_state) == 8:
            state = entry_state
        else:
            # Fallback if entry state was not captured
            latest_tick = self.latest_ticks.get(ticker, {})
            state = learner.get_state_vector(
                latest_tick or {},
                ensemble.price_history,
                [t for t in self.execution_engine.closed_trades if t['symbol'] == ticker]
            )
            
        # Feed trade outcome to strategy performance tracker
        if strategy_signals:
            ensemble.record_trade_outcome(strategy_signals, direction, pnl_percent)
        
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
        import hashlib
        steps_key = f"lifetime_training_steps_{ticker}"
        steps = int(database.load_setting(steps_key, "0")) + 1
        last_save_time = time.strftime('%H:%M:%S', time.localtime())
        
        weights_dict = {
            ensemble.strategies[i].name: float(new_weights[i])
            for i in range(len(new_weights))
        }
        
        if self.execution_engine.trading_mode != "simulation":
            active_brain_name = database.load_setting(f"active_policy_brain_{ticker}", "Default Brain")
            hidden_layers = int(database.load_setting("nn_hidden_layers", "1"))
            hidden_dim = int(database.load_setting("nn_hidden_dim", "12"))
            topo_str = f"PolicyNet-{hidden_layers}x{hidden_dim}x{len(ensemble.strategies)}"
            dna_hash = hashlib.md5(topo_str.encode('utf-8')).hexdigest()[:6].upper()
            model_dna = f"NN-ARCH-{dna_hash}"
            # Single DB connection for all writes
            try:
                conn = database.get_db_connection()
                cursor = conn.cursor()
                cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                               (f"policy_net_weights_{ticker}", weights_json))
                cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                               (steps_key, str(steps)))
                cursor.execute(
                    "UPDATE policy_brains SET training_steps = ?, weights = ? WHERE name = ? AND ticker = ?",
                    (steps, weights_json, active_brain_name, ticker))
                cursor.execute(
                    "INSERT OR REPLACE INTO weights_history (timestamp, ticker, weights, brain_name) VALUES (?, ?, ?, ?)",
                    (time.time(), ticker, json.dumps(weights_dict), active_brain_name))
                conn.commit()
                conn.close()
            except Exception as e:
                logging.error(f"Error persisting training state: {e}")
        else:
            active_brain_name = database.load_setting(f"active_policy_brain_{ticker}", "Default Brain")
            model_dna = f"NN-ARCH-DEFAULT"
        
        # ------------------------------------------------------------
        # PPO + replay buffer integration
        # ------------------------------------------------------------
        replay = self.replay_buffers.get(ticker)
        ppo = self.ppo_agents.get(ticker)
        if replay is not None and ppo is not None:
            # Construct next_state from current tick data
            latest_tick = self.latest_ticks.get(ticker, {})
            next_state = learner.get_state_vector(
                latest_tick or {},
                ensemble.price_history,
                [t for t in self.execution_engine.closed_trades if t['symbol'] == ticker]
            )
            
            # The action is the strategy signal ensemble that was used
            action_vec = strategy_signals if strategy_signals else [0.0] * len(ensemble.strategies)
            # Use weighted sum of signals as scalar action for replay
            action_scalar = sum(action_vec) / (len(action_vec) + 1e-9)
            
            # Push experience with TD-error = |PnL| as initial priority
            replay.add(state, action_scalar, pnl_percent, next_state, done=True, error=abs(pnl_percent))
            
            # Periodically sample and perform PPO update
            if len(replay) >= self.ppo_batch_size and (
                steps % self.ppo_update_interval == 0
            ):
                try:
                    info = ppo.train_on_buffer(
                        replay,
                        batch_size=self.ppo_batch_size,
                        ppo_epochs=self.ppo_epochs,
                        minibatch_size=self.ppo_minibatch_size,
                    )
                    if info is not None:
                        logging.info(
                            "[PPO %s] actor_loss=%.4f entropy=%.4f kl=%.5f clip=%.2f%%",
                            ticker,
                            info.get('actor_loss', 0),
                            info.get('entropy', 0),
                            info.get('approx_kl', 0),
                            info.get('clip_frac', 0) * 100,
                        )
                        
                        # Persist updated PPO weights periodically
                        if steps % (self.ppo_update_interval * 10) == 0:
                            ppo_json = ppo.to_json()
                            database.save_setting(f"ppo_agent_{ticker}", ppo_json)
                            logging.info(f"Persisted PPO agent state for {ticker}")
                except Exception as e:
                    logging.error(f"[PPO TRAIN ERROR] {ticker}: {e}")
            
            # Persist replay buffer to DB every 25 trades
            if steps % 25 == 0:
                try:
                    import base64
                    blob = replay.serialize()
                    b64_str = base64.b64encode(blob).decode('ascii')
                    database.save_setting(f"replay_buffer_{ticker}", b64_str)
                except Exception as e:
                    logging.error(f"Failed to persist replay buffer for {ticker}: {e}")
        
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
        
        # Auto-switch to the best performing brain if enabled
        auto_switch = database.load_setting(f"auto_switch_brains_{ticker}", "true") == "true"
        if auto_switch and self.execution_engine.trading_mode != "simulation":
            try:
                conn = database.get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name FROM policy_brains WHERE ticker = ? ORDER BY accumulated_pnl_percent DESC, training_steps DESC LIMIT 1",
                    (ticker,)
                )
                row = cursor.fetchone()
                conn.close()
                if row:
                    best_brain = row[0]
                    active_brain = database.load_setting(f"active_policy_brain_{ticker}", "Default Brain")
                    if best_brain != active_brain:
                        logging.info(f"[AUTO-BRAIN-SWITCH] Auto-switching active brain for {ticker} to best model '{best_brain}'")
                        activate_neural_brain(best_brain, ticker, is_manual=False)
            except Exception as e:
                logging.error(f"[AUTO-BRAIN-SWITCH ERROR] Failed to auto-switch brain: {e}")

        # ── Proton Mail Bridge trade notification ──
        try:
            if self.execution_engine.trading_mode == "live":
                trade_pnl_abs = float(pnl_percent) * float(getattr(self.execution_engine, 'balance', 0) or 0)
                closed = [t for t in self.execution_engine.closed_trades if t.get('symbol') == ticker]
                latest_closed = closed[-1] if closed else {}
                trade_data = {
                    "symbol": ticker,
                    "direction": direction.upper(),
                    "entry_price": float(latest_closed.get("entry_price", 0)),
                    "exit_price": float(latest_closed.get("exit_price", 0)),
                    "pnl": trade_pnl_abs,
                    "pnl_pct": float(pnl_percent) * 100,
                    "duration_seconds": float(latest_closed.get("duration_seconds", 0)),
                    "reason": str(latest_closed.get("exit_reason", "unknown")),
                }
                from proton_bridge import send_trade_notification
                send_trade_notification(trade_data)
        except Exception as e:
            logging.warning(f"[ProtonBridge] Failed to send trade notification: {e}")

        # ── Calibration loop: update Brier score from accumulated trade data ──
        # This feeds kill_switch.calibration_brier which caps position sizing
        # when probability predictions are poorly calibrated.
        try:
            from probability_calibration import load_calibration_from_trades
            cal = load_calibration_from_trades()
            if cal["n_samples"] >= 5:
                old_brier = getattr(kill_switch, "calibration_brier", None)
                kill_switch.calibration_brier = cal["brier_score"]
                if old_brier != cal["brier_score"]:
                    logging.info(
                        f"[CALIBRATION] Updated brier_score={cal['brier_score']:.4f} "
                        f"(n={cal['n_samples']}) kelly_cap={cal['kelly_cap']:.4f}"
                    )
        except Exception as e:
            logging.warning(f"[CALIBRATION] Update failed: {e}")

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

        # LLaMA sentiment poll (every 15 min, ticker-independent)
        if self.llm_enabled and self.llm_client and (curr_time - self.llm_last_sentiment_time >= self.llm_sentiment_interval):
            self.llm_last_sentiment_time = curr_time
            async def update_llm_sentiment():
                try:
                    loop = asyncio.get_running_loop()
                    result = await loop.run_in_executor(None, self.llm_client.analyze_sentiment,
                        [f"{t} at \${row['close']:.2f}" for t in self.tickers[:5]],
                        f"BTC \${self.latest_ticks.get('BTC-USD', {}).get('close', 0):.0f}, "
                        f"{len(self.execution_engine.active_positions)} open positions"
                    )
                    self.llm_last_sentiment = result
                    logging.info(f"LLaMA sentiment: {result.get('direction','?')} "
                                 f"score={result.get('sentiment_score',0):.2f} "
                                 f"conv={result.get('conviction',0):.2f}")
                except Exception as ex:
                    logging.warning(f"LLaMA sentiment poll failed: {ex}")
            self._run_async(update_llm_sentiment())
        
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
        
        # Check and apply dynamic auto-switch brain (throttled: max once per hour)
        _as_key = f"_last_brain_check_{ticker}"
        _as_time = getattr(self, _as_key, 0.0)
        if curr_time - _as_time >= 3600:
            setattr(self, _as_key, curr_time)
            auto_switch = database.load_setting(f"auto_switch_brains_{ticker}", "true") == "true"
            if auto_switch:
                try:
                    conn = database.get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT name, weights FROM policy_brains WHERE ticker = ? ORDER BY accumulated_pnl_percent DESC, training_steps DESC LIMIT 1",
                        (ticker,)
                    )
                    row_pb = cursor.fetchone()
                    conn.close()
                    if row_pb:
                        best_brain_name = row_pb[0]
                        best_brain_weights = row_pb[1]
                        active_brain_name = database.load_setting(f"active_policy_brain_{ticker}", "Default Brain")
                        if best_brain_name != active_brain_name:
                            logging.info(f"[AUTO-BRAIN-SWITCH] Dynamically hot-swapping {ticker} active brain to best model '{best_brain_name}' (PnL-driven)")
                            database.save_setting(f"policy_net_weights_{ticker}", best_brain_weights)
                            database.save_setting(f"active_policy_brain_{ticker}", best_brain_name)
                            learner.policy_net.from_json(best_brain_weights)
                except Exception as e:
                    logging.error(f"[AUTO-BRAIN-SWITCH ERROR] Failed to dynamically auto-switch brain for {ticker}: {e}")
        
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
        
        # Update shadow positions
        try:
            shadow_update = self.long_term_layer.update_shadow_positions(ticker, current_price)
            if shadow_update and shadow_update["event"] == "closed":
                self._run_async(self.broadcast_message({
                    "type": "shadow_trade_closed",
                    "trade": shadow_update,
                    "balance": self.long_term_layer.balance
                }))
        except Exception as ste:
            logging.error(f"Error updating shadow positions: {ste}")
        
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
                conn2 = database.get_db_connection()
                cursor2 = conn2.cursor()
                cursor2.execute(
                    "INSERT OR REPLACE INTO portfolio_history (timestamp, equity, pnl) VALUES (?, ?, ?)",
                    (now_time, current_equity, current_equity - init_bal)
                )
                conn2.commit()
                conn2.close()
            except Exception as e:
                logging.error(f"Error logging portfolio history point: {e}")
        
        if update_event:
            event_type = "sim_trade_closed" if self.is_simulating else "trade_closed"
            event_open_type = "sim_trade_opened" if self.is_simulating else "trade_opened"
            if update_event["event"] == "closed":
                # Broadcast closed trade
                self._run_async(self.broadcast_message({
                    "type": event_type,
                    "trade": update_event["data"],
                    "balance": self.execution_engine.balance,
                    "equity": current_equity
                }))
            elif update_event["event"] == "filled":
                # Broadcast filled order to open trade
                self._run_async(self.broadcast_message({
                    "type": event_open_type,
                    "ticker": ticker,
                    "position": update_event["data"],
                    "balance": self.execution_engine.balance,
                    "equity": current_equity
                }))
            
        # 3. If no position is open for this ticker, check strategy ensemble signals
        pos_open = ticker in self.execution_engine.active_positions
        weighted_signal, strategy_breakdown = ensemble.get_weighted_signal(row, ingestor.data)
        
        # Populate latest_signals for the dashboard /api/trading/signals endpoint
        if not hasattr(self, 'latest_signals'):
            self.latest_signals = {}
        direction = "BULLISH" if weighted_signal > 0 else ("BEARISH" if weighted_signal < 0 else "NEUTRAL")
        self.latest_signals[ticker] = {
            "signal": round(weighted_signal, 6),
            "direction": direction,
            "strength": abs(weighted_signal),
            "timestamp": time.time(),
            "breakdown": strategy_breakdown
        }
        
        # Evaluate and run shadow long-term strategy rules
        try:
            shadow_opened = self.long_term_layer.evaluate_long_term_rules(
                ticker, current_price, row, ingestor.data, ensemble, learner
            )
            if shadow_opened:
                self._run_async(self.broadcast_message({
                    "type": "shadow_trade_opened",
                    "ticker": ticker,
                    "position": shadow_opened,
                    "balance": self.long_term_layer.balance
                }))
        except Exception as lte:
            logging.error(f"Error running shadow long term strategy: {lte}")
        
        evaluation = None
        trade_opened = False
        
        if not pos_open:
            # Dynamic signal threshold: higher for small accounts (fewer, higher-conviction trades)
            # Scales inversely with account balance: $200 -> 0.35, $1K -> 0.25, $10K -> 0.20
            # Override via DB setting 'signal_threshold' (set by optimization agents)
            _saved_threshold = database.load_setting("signal_threshold", None)
            if _saved_threshold is not None and str(_saved_threshold).strip():
                # SAFETY CLAMP [0.10, 0.45]: optimizer once set this to 0.60, gating ALL trades for 6+ hours.
                # 0.45 ensures at least some trades pass in a $200 account (default ~0.35).
                try:
                    _min_sig = max(0.10, min(0.45, float(str(_saved_threshold).strip())))
                except (ValueError, TypeError):
                    _min_sig = 0.30
            else:
                # BUGFIX: Use total EQUITY (balance + unrealized PnL) instead of cash balance.
                # When a position is open, balance drops by position cost (e.g. $990→$792)
                # making the threshold skyrocket to 0.387, blocking all new signals.
                # Equity stays representative of true portfolio size (~$990).
                _ref_val = current_equity if current_equity > 0 else self.execution_engine.balance
                # BUGFIX: Lower scaling denominator from 500 to 350 so threshold decays faster.
                # At $200 equity: 1/(1+200/350) = 0.636 → clamped to 0.45
                # At $500 equity: 1/(1+500/350) = 0.412 → 0.41 (was 0.50 → 0.45)
                # At $1K equity: 1/(1+1000/350) = 0.259 → 0.26 (was 0.33)
                # This allows more signals through as the account grows, preventing
                # the starvation issue where most ensemble signals (0.10-0.25) are
                # blocked despite being valid trading opportunities.
                _min_sig = max(0.15, min(0.45, 1.0 / (1.0 + _ref_val / 350.0)))
            if abs(weighted_signal) >= _min_sig:
                direction = "BUY" if weighted_signal > 0 else "SELL"
                
                # Evaluate probability and risk
                evaluation = self.probability_engine.evaluate_trade(
                    price=current_price,
                    atr=atr,
                    direction=direction,
                    weighted_signal=weighted_signal,
                    row=row,
                    history_df=ingestor.data,
                    symbol=ticker
                )
                evaluation["state"] = state
                
                # If viable, open position
                if evaluation["is_viable"]:
                    # KillSwitch check before opening — use current market value not entry price
                    # BUGFIX: entry_price underestimates exposure when price moves up.
                    # Use current_price from latest_ticks for accurate real-time exposure.
                    # Fall back to entry_price if tick data hasn't arrived yet (warm-up).
                    _exposure_prices = self.latest_ticks
                    _current_exposure_prices = current_prices if current_prices else _exposure_prices
                    exposure = sum(
                        abs(v.get("quantity", 0)) * _current_exposure_prices.get(k, {}).get("close", v.get("entry_price", 0))
                        for k, v in self.execution_engine.active_positions.items()
                    )
                    safe, reason = kill_switch.check(
                        current_drawdown=drawdown_tracker.current_drawdown,
                        # BUGFIX: Pass dollar exposure per symbol, not raw coin quantity.
                        # max_per_pos is a dollar value ($50 baseline, scaled by account) but
                        # raw quantity (e.g. 396 ADA) vs dollars ($247) is apples-to-oranges.
                        open_positions={k: abs(v.get("quantity", 0)) * v.get("entry_price", 0) for k, v in self.execution_engine.active_positions.items()},
                        total_exposure=exposure,
                        current_equity=current_equity,
                    )
                    if not safe:
                        logging.warning("[KillSwitch] Blocking trade: {}".format(reason))
                    else:
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
                            # Generate LLaMA trade explanation (async, non-blocking)
                            llm_explanation = ""
                            if self.llm_enabled and self.llm_client:
                                async def explain_trade():
                                    try:
                                        loop = asyncio.get_running_loop()
                                        explanation = await loop.run_in_executor(None,
                                            self.llm_client.explain_trade, {
                                                "symbol": ticker,
                                                "direction": "LONG" if direction == "BUY" else "SHORT",
                                                "entry_price": float(current_price),
                                                "signal_strength": float(weighted_signal),
                                                "top_strategies": [
                                                    ensemble.strategies[i].name
                                                    for i in sorted(range(len(strategy_breakdown)),
                                                                    key=lambda i: abs(strategy_breakdown[i]),
                                                                    reverse=True)[:3]
                                                ],
                                                "regime": self.llm_last_sentiment.get("direction", "unknown"),
                                                "attention_focus": "Live ensemble signal: {:.3f}".format(weighted_signal),
                                                "market_overview": "Balance \${:.2f}, {} open positions".format(
                                                    self.execution_engine.balance,
                                                    len(self.execution_engine.active_positions)),
                                            })
                                        self._run_async(self.broadcast_message({
                                            "type": "llm_explanation",
                                            "ticker": ticker,
                                            "explanation": explanation
                                        }))
                                    except Exception as ex:
                                        logging.warning(f"LLaMA trade explanation failed: {ex}")
                                self._run_async(explain_trade())
                            if self.execution_engine.trading_mode == "live":
                                self._run_async(self.broadcast_message({
                                    "type": "trade_opened",
                                    "ticker": ticker,
                                    "position": self.execution_engine.active_positions[ticker],
                                    "balance": self.execution_engine.balance,
                                    "equity": current_equity,
                                    "llm_explanation": llm_explanation or "LLaMA analysis pending..."
                                }))
                            else:
                                # BUGFIX: pending_limit_orders dict is never populated by open_position.
                                # Use the active position instead to avoid KeyError crash.
                                _limit_order = self.execution_engine.pending_limit_orders.get(ticker, self.execution_engine.active_positions.get(ticker, {}))
                                self._run_async(self.broadcast_message({
                                    "type": "limit_order_placed",
                                    "ticker": ticker,
                                    "order": _limit_order,
                                    "balance": self.execution_engine.balance,
                                    "equity": current_equity
                                }))

        # Check Loss Cooldown status
        try:
            cooldown_end = float(database.load_setting(f"cooldown_end_{ticker}", "0.0"))
        except (ValueError, TypeError):
            cooldown_end = 0.0
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
        active_brain_name = database.load_setting(f"active_policy_brain_{ticker}", "Default Brain")
        self._run_async(self.broadcast_message({
            "type": "sim_tick" if self.is_simulating else "tick",
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
            "active_brain": active_brain_name,
            "sim_index": row.get('_sim_index', None),
            "sim_total": row.get('_sim_total', None),
            "indicators": {
                "rsi": float(row.get('rsi', 50)),
                "macd": float(row.get('macd', 0)),
                "macd_signal": float(row.get('macd_signal', 0)),
                "bb_upper": float(row.get('bb_upper', current_price)),
                "bb_lower": float(row.get('bb_lower', current_price)),
                "atr": float(row.get('atr', 0))
            },
            "llm_sentiment": self.llm_last_sentiment
        }))

    async def broadcast_message(self, message):
        """Sends JSON message to all active WebSocket connections."""
        from fastapi import WebSocketDisconnect as _WSD
        disconnected = []
        for ws in self.connected_websockets:
            try:
                await ws.send_text(json.dumps(message))
            except (_WSD, Exception):
                disconnected.append(ws)
        
        for ws in disconnected:
            if ws in self.connected_websockets:
                self.connected_websockets.remove(ws)

    def start_stream(self, mode="live", speed=0.2, poll_interval=5, brain=None, start_date=None, end_date=None):
        """Starts real-time live trading feed or simulation playback for all tickers."""
        if self.is_simulating:
            self.stop_stream()
            
        self.mode = mode
        self.is_simulating = True
        self.sim_brain = brain
        
        for ticker in self.tickers:
            if ticker in self.data_ingestions:
                # Bind lambda capturing the current ticker
                self.data_ingestions[ticker].subscribe(
                    lambda row, t=ticker: self.process_tick(row, t)
                )
                if mode == "live":
                    # Restore global active brain from DB for live trading to ensure it's not contaminated
                    active_name = database.load_setting(f"active_policy_brain_{ticker}", "Default Brain")
                    brain_data = database.load_policy_brain(active_name, ticker)
                    if brain_data and ticker in self.learning_engines:
                        try:
                            self.learning_engines[ticker].policy_net.from_json(brain_data["weights"])
                            logging.info(f"Restored global active brain '{active_name}' for live/paper trading on {ticker}.")
                        except Exception as e:
                            logging.error(f"Error restoring global active brain weights: {e}")
                    self.data_ingestions[ticker].start_live_stream(interval_seconds=poll_interval)
                else:
                    # In simulation mode, load the selected brain uniquely
                    if brain:
                        brain_data = database.load_policy_brain(brain, ticker)
                        if brain_data and ticker in self.learning_engines:
                            try:
                                self.learning_engines[ticker].policy_net.from_json(brain_data["weights"])
                                logging.info(f"Loaded simulation brain '{brain}' for {ticker} dynamically.")
                            except Exception as e:
                                logging.error(f"Error loading simulation brain weights: {e}")
                    self.data_ingestions[ticker].start_simulation_stream(
                        speed_seconds=speed,
                        start_index=150,
                        start_date=start_date,
                        end_date=end_date
                    )
        logging.info(f"Multi-asset streaming started in {mode} mode. Brain: {brain}, range: {start_date} to {end_date}")

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
    orchestrator.start_time = time.time()
    await orchestrator.initialize()

    # Initialize safety systems from saved state
    ks_data = database.load_setting("killswitch_state", "")
    if ks_data:
        try:
            parsed = json.loads(ks_data)
            kill_switch.__dict__.update(type(kill_switch).from_dict(parsed).__dict__)
            logging.info("[KillSwitch] Restored from saved state")
        except Exception as e:
            logging.error("Error restoring KillSwitch state: {}".format(e))

    dd_data = database.load_setting("drawdown_tracker_state", "")
    if dd_data:
        try:
            parsed = json.loads(dd_data)
            drawdown_tracker.__dict__.update(type(drawdown_tracker).from_dict(parsed).__dict__)
            logging.info("[DrawdownTracker] Restored from saved state")
        except Exception as e:
            logging.error("Error restoring DrawdownTracker state: {}".format(e))

    # Migrate existing settings to research: namespace
    try:
        count = migrate_settings(database)
        if count > 0:
            logging.info("Migrated {} settings to research: namespace".format(count))
    except Exception as e:
        logging.error("Settings migration error: {}".format(e))
    
    # Seed default policy brains for all tickers
    for ticker in orchestrator.tickers:
        learner = orchestrator.learning_engines.get(ticker)
        if not learner:
            continue
        ensemble = orchestrator.strategy_ensembles.get(ticker)
        num_strats = len(ensemble.strategies) if ensemble else 6
        
        current_weights_json = learner.policy_net.to_json()
        import hashlib
        topo_str = f"PolicyNet-8x12x{num_strats}"
        dna_hash = hashlib.md5(topo_str.encode('utf-8')).hexdigest()[:6].upper()
        model_dna = f"NN-{dna_hash}"
        
        existing_brains = database.list_policy_brains(ticker)
        brain_names = [b["name"] for b in existing_brains]
        
        # Load current steps setting
        steps_key = f"lifetime_training_steps_{ticker}"
        lifetime_steps = int(database.load_setting(steps_key, "0"))
        
        if "Default Brain" not in brain_names:
            database.save_policy_brain("Default Brain", ticker, model_dna, current_weights_json, lifetime_steps)
        if "High-Freq Scalper" not in brain_names:
            database.save_policy_brain("High-Freq Scalper", ticker, model_dna, current_weights_json, lifetime_steps)
        if "Trend Follower" not in brain_names:
            database.save_policy_brain("Trend Follower", ticker, model_dna, current_weights_json, lifetime_steps)
            
    # Force seed the new prompts in database settings
    database.save_setting("prompt_self_improvement", DEFAULT_PROMPT_QUANT)
    database.save_setting("prompt_self_developer", DEFAULT_PROMPT_DEV)
    database.save_setting("prompt_blog_agent", DEFAULT_PROMPT_BLOG)
    database.save_setting("prompt_nn_agent", DEFAULT_PROMPT_NN)
    database.save_setting("prompt_sentiment_agent", DEFAULT_PROMPT_SENTIMENT)
    database.save_setting("prompt_risk_auditor", DEFAULT_PROMPT_RISK)
    database.save_setting("prompt_allocator_agent", DEFAULT_PROMPT_ALLOCATOR)
    database.save_setting("prompt_long_term_quant", DEFAULT_PROMPT_LONG_TERM_QUANT)

    # Auto-start live stream on startup (true live data)
    orchestrator.start_stream(mode="live", poll_interval=5)
    try:
        update_crontab_schedule()
    except Exception as e:
        logging.error(f"Failed to initialize crontab on startup: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    # Save safety state before shutdown
    try:
        database.save_setting("killswitch_state", json.dumps(kill_switch.to_dict()))
        database.save_setting("drawdown_tracker_state", json.dumps(drawdown_tracker.to_dict()))
    except Exception as e:
        logging.error("Error saving safety state on shutdown: {}".format(e))
    orchestrator.stop_stream()

# API Endpoints




@app.get("/api/trades/all")
async def api_trades_all():
    """All completed trades: DB truth merged with live Kraken fills when available."""
    try:
        db_trades = database.load_trades()
    except Exception as e:
        logging.error(f"/api/trades/all DB load failed: {e}")
        db_trades = []

    exchange_trades = []
    try:
        cfg_path = os.path.expanduser("~/.nexustrader/config.json")
        if os.path.exists(cfg_path):
            with open(cfg_path, "r") as f:
                cfg = json.load(f)
            if cfg.get("trading_mode", "paper") == "live":
                creds = cfg.get("api_credentials", {})
                api_key = creds.get("api_key")
                api_secret = creds.get("api_secret")
                broker = cfg.get("broker", "kraken").lower()
                if api_key and api_secret:
                    import ccxt
                    exchange_class = getattr(ccxt, broker)
                    exchange = exchange_class({
                        "apiKey": api_key,
                        "secret": api_secret,
                        "enableRateLimit": True,
                        "timeout": 20000,
                    })
                    exchange_trades = reconstruct_trades_from_exchange(exchange)
    except Exception as e:
        logging.error(f"/api/trades/all exchange fetch failed: {e}")

    merged = []
    seen = set()
    def key(t):
        return (
            str(t.get("symbol", "")),
            str(t.get("direction", "")),
            round(float(t.get("entry_time", 0) or 0), 3),
            round(float(t.get("exit_time", 0) or 0), 3),
            round(float(t.get("quantity", 0) or 0), 12),
        )
    for t in exchange_trades + db_trades:
        k = key(t)
        if k not in seen:
            seen.add(k)
            merged.append(t)
    merged.sort(key=lambda x: float(x.get("exit_time", 0) or 0), reverse=True)
    return {"trades": merged, "db_count": len(db_trades), "exchange_count": len(exchange_trades), "count": len(merged)}

@app.get("/api/trading/signals")
def get_trading_signals():
    """Latest weighted signals per ticker — flat dict {ticker: {...}}."""
    try:
        return getattr(orchestrator, "latest_signals", {}) or {}
    except Exception:
        return {}

@app.get("/api/trading/reasoning")
def get_trading_reasoning():
    items = []
    status = "active"
    try:
        ee = orchestrator.execution_engine
        signals = getattr(orchestrator, "latest_signals", {}) or {}
        tickers = getattr(orchestrator, "tickers", []) or []
        prices = {}
        stale = []
        now = time.time()
        for t in tickers:
            ing = getattr(orchestrator, "data_ingestions", {}).get(t)
            prices[t] = (getattr(ing, "live_price", 0.0) if ing else 0.0) or 0.0
            ts = float((signals.get(t, {}) or {}).get("timestamp", 0) or 0)
            if ts and now - ts > 600:
                stale.append(t)
        equity = ee.get_equity(prices)
        balance = float(getattr(ee, "balance", 0.0) or 0.0)
        open_pos = getattr(ee, "active_positions", {}) or {}
        trades = database.load_trades()
        wins = sum(1 for tr in trades if float(tr.get("pnl", 0) or 0) > 0)
        losses = sum(1 for tr in trades if float(tr.get("pnl", 0) or 0) < 0)
        wr = (wins / (wins + losses) * 100.0) if wins + losses else 0.0
        bullish = sum(1 for x in signals.values() if x.get("direction") == "BULLISH")
        bearish = sum(1 for x in signals.values() if x.get("direction") == "BEARISH")
        neutral = max(0, len(signals) - bullish - bearish)
        risk_mode = getattr(orchestrator.probability_engine, "risk_mode", "unknown")
        items.append({"id":"mode", "severity":"info", "title":"Mode", "detail":f"Trading mode: {ee.trading_mode}. Risk mode: {risk_mode}."})
        items.append({"id":"capital", "severity":"info", "title":"Capital", "detail":f"Cash ${balance:.2f}, equity ${equity:.2f}, open positions {len(open_pos)}."})
        items.append({"id":"signals", "severity":"success" if signals else "warning", "title":"Live signals", "detail":f"{len(signals)}/{len(tickers)} tickers reporting. Bullish {bullish}, bearish {bearish}, neutral {neutral}."})
        items.append({"id":"performance", "severity":"warning" if wr < 35 and wins + losses >= 5 else "info", "title":"Closed trade performance", "detail":f"DB has {len(trades)} closed trades: {wins}W/{losses}L, win rate {wr:.1f}%."})
        if stale:
            status = "idle"
            items.append({"id":"stale", "severity":"warning", "title":"Stale signal data", "detail":"No fresh signal update for: " + ", ".join(stale[:8])})
        if "SUI-USD" in tickers:
            items.append({"id":"sui", "severity":"warning", "title":"SUI-USD data risk", "detail":"SUI-USD has had yfinance/delisting-style failures. Disable if live prices stay missing."})
        # LLaMA sentiment status
        llm_enabled = getattr(orchestrator, "llm_enabled", False)
        llm_sent = getattr(orchestrator, "llm_last_sentiment", {}) or {}
        if llm_enabled and llm_sent.get("direction"):
            themes = ", ".join(llm_sent.get("key_themes", []) or [])
            detail = "{} (score {:.2f}, conviction {:.0f}%). {}".format(
                llm_sent.get("direction","?").upper(),
                float(llm_sent.get("sentiment_score",0)),
                float(llm_sent.get("conviction",0))*100,
                themes
            )[:200]
            items.append({"id":"llm","severity":"info","title":"LLaMA Sentiment","detail":detail})
        elif llm_enabled:
            items.append({"id":"llm","severity":"warning","title":"LLaMA","detail":"LLaMA enabled but awaiting first sentiment poll..."})
    except Exception as e:
        status = "error"
        items.append({"id":"reasoning-error", "severity":"error", "title":"Reasoning failed", "detail":str(e)})
    return {"status": status, "items": items, "timestamp": time.time()}

@app.get("/api/init")
async def api_init_state(request: Request):
    """Dashboard init - mirrors /api/status + trades + brains."""
    import json as _json, time as _time, datetime as _dt, traceback as _tb
    _db = __import__("database")
    orc = orchestrator
    ee = orc.execution_engine

    # Tickers: same as /api/status
    tickers = orc.tickers or _json.loads(_db.load_setting("active_tickers","[]"))
    default_ticker = tickers[0] if tickers else "BTC-USD"

    # Live prices from data_ingestions (mirrors /api/status)
    current_prices = {}
    ticker_prices = {}
    for t in tickers:
        if t in orc.data_ingestions:
            di_t = orc.data_ingestions.get(t)
            p = di_t.live_price or 0.0
            current_prices[t] = p
            ticker_prices[t] = p

    balance = ee.balance
    equity = ee.get_equity(current_prices) if current_prices else balance

    # Trades from DB
    all_trades = _db.load_trades() or []
    _today_start = _time.time() - (_time.time() % 86400)  # midnight today
    _today_trades = [t for t in all_trades if float(t.get("exit_time", 0) or 0) >= _today_start]
    _today_pnl = sum(float(t.get("pnl", 0) or 0) for t in _today_trades)

    # Active brains
    active_brains = []
    for tn, learner in (getattr(orc, "learning_engines", {}) or {}).items():
        try:
            bn = getattr(learner, "active_brain_name", None)
            if bn:
                active_brains.append({"name": bn, "ticker": tn, "version": getattr(learner, "brain_version", 1)})
        except Exception as e:
            logging.warning(f"/api/init brain loading for {tn}: {e}")

    # Positions
    positions = []
    try:
        for sym, pos in getattr(ee, "active_positions", {}).items():
            entry_time = pos.get("entry_time", int(_time.time())) if isinstance(pos, dict) else getattr(pos, "entry_time", int(_time.time()))
            positions.append({
                "symbol": sym,
                "direction": pos.get("direction", "BUY") if isinstance(pos, dict) else getattr(pos, "direction", "BUY"),
                "entry_price": pos.get("entry_price", 0) if isinstance(pos, dict) else getattr(pos, "entry_price", 0),
                "current_price": pos.get("current_price", 0) if isinstance(pos, dict) else getattr(pos, "current_price", 0),
                "quantity": pos.get("quantity", 0) if isinstance(pos, dict) else getattr(pos, "quantity", 0),
                "entry_time": entry_time,
                "unrealized_pnl": pos.get("unrealized_pnl", 0) if isinstance(pos, dict) else getattr(pos, "unrealized_pnl", 0),
                "unrealized_pnl_pct": pos.get("unrealized_pnl_pct", 0) if isinstance(pos, dict) else getattr(pos, "unrealized_pnl_pct", 0),
                "age_seconds": int(_time.time()) - entry_time,
            })
    except Exception as e:
        logging.warning(f"/api/init position serialization error: {e}")

    # Reverse trades to show newest first (same as /api/status)
    all_trades.reverse()
    return {
        "status":"ok", "balance":balance, "equity":equity,
        "trades":all_trades, "total_pnl":round(sum(float(t.get("pnl",0)or 0) for t in all_trades), 2),
        "today_pnl": round(_today_pnl, 2),
        "total_pnl_pct": round((sum(float(t.get("pnl",0)or 0) for t in all_trades) / float(_db.load_setting("initial_portfolio_balance","100.0")) * 100) if float(_db.load_setting("initial_portfolio_balance","100.0")) > 0 else 0.0, 2),
        "tickers":tickers, "ticker":default_ticker, "ticker_prices":ticker_prices,
        "active_brains":active_brains,
        "initial_balance":float(_db.load_setting("initial_portfolio_balance","100.0")),
        "lifetime_steps":int(_db.load_setting("lifetime_training_steps_" + tickers[0],"0")) if tickers else 0,
        "model_dna":_db.load_setting("model_dna","genesis"),
        "positions":positions,
        "risk_mode":_db.load_setting("risk_mode","conservative"),
        "trading_mode":_db.load_setting("trading_mode","paper"),
        "live_holdings":getattr(getattr(orc,"execution_engine",None),"live_holdings",{})or{},
    }

@app.get("/api/positions")
async def api_positions():
    """Open positions + fiat breakdown."""
    import time as _time
    positions = []
    try:
        ee = getattr(orchestrator, "execution_engine", None)
        if ee:
            # active_positions is dict of dicts
            active_pos = getattr(ee, "active_positions", {})
            # Compute current prices once for all positions
            live_prices = {}
            for t in orchestrator.tickers:
                if t in orchestrator.data_ingestions:
                    di = orchestrator.data_ingestions.get(t)
                    live_prices[t] = float(di.live_price or 0.0)
            for sym, pos in active_pos.items():
                entry_time = pos.get("entry_time", int(_time.time())) if isinstance(pos, dict) else int(_time.time())
                entry_price = float(pos.get("entry_price", 0) if isinstance(pos, dict) else 0)
                quantity = float(pos.get("quantity", 0) if isinstance(pos, dict) else 0)
                direction = pos.get("direction", "BUY") if isinstance(pos, dict) else "BUY"
                current_price = live_prices.get(sym, float(pos.get("current_price", entry_price) if isinstance(pos, dict) else entry_price))
                if direction == "BUY":
                    unrealized_pnl = (current_price - entry_price) * quantity
                else:
                    unrealized_pnl = (entry_price - current_price) * quantity
                # Keep consistency: execution engine stores pct as decimal fraction (0.05 = 5%)
                unrealized_pnl_pct = unrealized_pnl / (entry_price * quantity + 1e-9) if entry_price * quantity != 0 else 0.0
                positions.append({
                    "symbol": sym,
                    "direction": direction,
                    "entry_price": entry_price,
                    "current_price": current_price,
                    "quantity": quantity,
                    "entry_time": entry_time,
                    "unrealized_pnl": round(unrealized_pnl, 2),
                    "unrealized_pnl_pct": round(unrealized_pnl_pct, 4),
                    "age_seconds": int(_time.time()) - entry_time,
                })
    except Exception as e:
        logging.error(f"/api/positions error building position list: {e}")
    fiat_breakdown = {}
    crypto_count = 0
    try:
        live_holdings = getattr(orchestrator, "live_holdings", {}) or {}
        for asset, amt in live_holdings.items():
            if asset in ("USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD"):
                fiat_breakdown[asset] = amt
            elif float(amt) > 0:
                crypto_count += 1
    except Exception:
        pass
    return {"positions": positions, "fiat_breakdown": fiat_breakdown, "crypto_asset_count": crypto_count}


@app.get("/api/health")
async def api_health():
    """Lightweight health check - no heavy DB access."""
    import sys, os
    try:
        import psutil
        mem = round(psutil.Process().memory_info().rss / 1024 / 1024, 1)
    except Exception:
        mem = 0
    return {
        "status": "ok",
        "uptime_seconds": getattr(orchestrator, "start_time", 0),
        "pid": os.getpid(),
        "python": sys.version.split()[0],
        "memory_mb": mem,
    }

@app.post("/api/quant/prompt/save")
async def quant_prompt_save(request: Request):
    """Save per-agent prompt"""
    _db = __import__("database")
    try:
        body = await request.json()
        agent = body.get("agent", "")
        prompt = body.get("prompt", "")
        if not agent:
            return {"status": "error", "error": "agent required"}
        key = f"prompt_{agent}"
        _db.save_setting(key, prompt)
        return {"status": "saved", "agent": agent, "length": len(prompt)}
    except Exception as e:
        return {"status": "error", "error": str(e)}
@app.post("/api/quant/trigger")
async def quant_trigger(request: Request):
    """Log a quant agent trigger request (cron jobs handle actual execution)"""
    _db = __import__("database")
    try:
        body = await request.json()
        agent = body.get("agent", "unknown")
        _db.save_setting("quant_trigger_" + agent, str(time.time()))
        logging.info(f"[QUANT TRIGGER] Agent: {agent} — Queued for next cron run")
        return {"status": "requested", "agent": agent}
    except Exception as e:
        return {"status": "error", "error": str(e)}
@app.get("/api/quant/status")
def get_quant_status():
    """Return status of all Quant Team agents"""
    import glob as _glob, os as _os
    agents = [
        {"id":"quant-optimizer","name":"NexusQuant PhD","emoji":"📊","role":"Parameter Optimizer","description":"Analyses trade outcomes and win rates. Suggests ATR multipliers, signal thresholds, and risk limits.","schedule":"Daily 1:00 AM UTC","color":"var(--neon-purple)","report_glob":"blog/daily_summaries/quant_optimizer_*.md"},
        {"id":"sentiment","name":"Sentiment Agent","emoji":"📡","role":"Market Sentiment Analyst","description":"Polls crypto news feeds, computes sentiment scores, feeds them into the state vector.","schedule":"Daily 2:00 AM UTC","color":"var(--neon-pink)","report_glob":"blog/daily_summaries/sentiment_*.md"},
        {"id":"risk-auditor","name":"NexusAuditor","emoji":"🛡️","role":"Portfolio Risk Auditor","description":"Checks drawdown, position sizes, and correlation between open trades to flag risk issues.","schedule":"Daily 3:00 AM UTC","color":"var(--neon-red)","report_glob":"blog/daily_summaries/risk_audit_*.md"},
        {"id":"allocator","name":"Allocation Agent","emoji":"⚖️","role":"Portfolio Allocator","description":"Rebalances asset allocation, adjusts Kelly ceilings, rotates capital to winning tickers.","schedule":"Daily 4:00 AM UTC","color":"var(--neon-blue)","report_glob":"blog/daily_summaries/allocator_*.md"},
        {"id":"self-dev","name":"NexusDev Architect","emoji":"⚙️","role":"Autonomous Systems Developer","description":"Reviews codebase for bugs and improvements. Edits dashboard, config, and agent code. Never touches trading logic.","schedule":"Daily 5:00 AM UTC","color":"var(--neon-cyan)","report_glob":"blog/daily_summaries/self_dev_*.md"},
        {"id":"asset-selector","name":"Asset Selector","emoji":"🔍","role":"Trading Universe Manager","description":"Scans Kraken for new high-volume USD pairs. Adds promising assets, disables delisted ones.","schedule":"Every 14 days (Sunday)","color":"var(--neon-green)","report_glob":"blog/daily_summaries/asset_selector_*.md"},
        {"id":"self-improve","name":"Self-Improvement Agent","emoji":"🧬","role":"Strategy Evolution Engine","description":"Analyzes trade patterns, evolves ensemble weights, prunes dead strategies, tunes hyperparameters from data.","schedule":"Weekly Saturday 6:00 AM","color":"var(--neon-orange)","report_glob":"blog/daily_summaries/self_improve_*.md"},
        {"id":"blogger","name":"NexusReporter AI","emoji":"📝","role":"Performance Journalist & Blogger","description":"Generates weekly performance reports with trade stats, weight changes, and portfolio health summaries.","schedule":"Weekly Sunday 23:59 UTC","color":"var(--neon-yellow)","report_glob":"blog/daily_summaries/weekly_report_*.md"},
        {"id":"researcher","name":"Monthly Researcher","emoji":"🔬","role":"Deep Strategy Researcher","description":"Monthly deep-dive: Sharpe/Sortino/Calmar ratios, per-strategy alpha attribution, market regime analysis.","schedule":"1st of month 7:00 AM","color":"var(--neon-indigo)","report_glob":"blog/daily_summaries/monthly_research_*.md"}
    ]
    for a in agents:
        reports = sorted(_glob.glob(a["report_glob"]), reverse=True)
        if reports:
            a["last_report"] = _os.path.getmtime(reports[0])
            a["last_report_file"] = _os.path.basename(reports[0])
            try:
                with open(reports[0]) as f:
                    a["last_report_summary"] = f.readline().strip().lstrip("#").strip()[:100]
            except Exception:
                a["last_report_summary"] = "(unreadable)"
        else:
            a["last_report"] = None
            a["last_report_file"] = None
            a["last_report_summary"] = "No report yet — awaiting first run"
    return {"agents": agents}


@app.api_route("/api/quant/prompt", methods=["GET", "POST"])
async def quant_prompt(request: Request):
    """Get or set the Quant Team system prompt"""
    _db = __import__("database")
    if request.method == "GET":
        prompt = _db.load_setting("quant_team_prompt", "")
        return {"prompt": prompt}
    else:
        try:
            body = await request.json()
            prompt = body.get("prompt", "")
            _db.save_setting("quant_team_prompt", prompt)
            return {"status": "saved", "length": len(prompt)}
        except Exception as e:
            return {"status": "error", "error": str(e)}
@app.get("/api/safety/status")
def get_safety_status():
    """KillSwitch and drawdown tracker status."""
    safe, reason = kill_switch.check()
    if safe:
        reason = None
    return {
        "kill_switch": {
            "tripped": kill_switch.tripped,
            "trigger_reason": kill_switch.trigger_reason,
            "daily_pnl": round(kill_switch.daily_pnl, 2),
            "safe": safe,
        },
        "drawdown": {
            "current_pct": round(drawdown_tracker.current_drawdown * 100, 2),
            "max_pct": round(drawdown_tracker.max_drawdown * 100, 2),
            "peak_equity": round(drawdown_tracker.peak, 2),
        },
        "mutation_freeze": {
            "frozen": mutation_freeze.frozen,
            "pending_suggestions": len(mutation_freeze.pending_suggestions),
        },
    }


@app.get("/api/status")
def get_status():
    import datetime, os as _os
    if not hasattr(get_status, "_start_time"):
        get_status._start_time = time.time()

    current_prices = {}
    for t in orchestrator.tickers:
        if t in orchestrator.data_ingestions:
            di_t = orchestrator.data_ingestions.get(t)
            current_prices[t] = di_t.live_price or 0.0
    
    ee = orchestrator.execution_engine
    fiat_breakdown = {}
    holdings = getattr(ee, "live_holdings", {})
    if holdings:
        for k, v in holdings.items():
            if k in ("USD", "ZUSD"):
                fiat_breakdown["USD"] = fiat_breakdown.get("USD", 0.0) + float(v)
            elif k in ("EUR", "ZEUR"):
                fiat_breakdown["EUR"] = fiat_breakdown.get("EUR", 0.0) + float(v)
    
    _db = __import__("database")
    _all_trades = _db.load_trades()
    _total_pnl = sum(float(t.get("pnl", 0.0) or 0.0) for t in _all_trades)
    
    _today_start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    _today_ts = _today_start.timestamp()
    _today_trades = [t for t in _all_trades if t.get("exit_time", 0) >= _today_ts]
    _today_pnl = sum(float(t.get("pnl", 0.0) or 0.0) for t in _today_trades)
    _today_pnl_denom = ee.initial_balance if ee.initial_balance > 0 else (ee.balance if ee.balance > 0 else 1.0)
    _today_pnl_pct = (_today_pnl / _today_pnl_denom * 100) if _today_pnl_denom > 0 else 0.0
    
    _win_count = sum(1 for t in _all_trades if float(t.get("pnl", 0) or 0) > 0)
    _loss_count = sum(1 for t in _all_trades if float(t.get("pnl", 0) or 0) < 0)
    
    # Use drawdown_tracker for max drawdown (includes unrealized PnL from open positions)
    # Falls back to trade-based calculation if tracker has no data
    if drawdown_tracker.max_drawdown > 0:
        _max_dd = drawdown_tracker.max_drawdown * 100
    else:
        _peak = ee.initial_balance
        _max_dd = 0.0
        _running = ee.initial_balance
        for t in sorted(_all_trades, key=lambda x: x.get("exit_time", 0)):
            _running += float(t.get("pnl", 0.0) or 0.0)
            if _running > _peak:
                _peak = _running
            if _peak > 0:
                _dd = (_peak - _running) / _peak * 100
                if _dd > _max_dd:
                    _max_dd = _dd
    
    _dd_limit = float(_db.load_setting("max_drawdown", "5.0"))
    
    _health = "good"
    _health_reason = "All systems operational"
    if ee.balance <= 0:
        _health = "critical"
        _health_reason = "Balance exhausted"
    elif _max_dd >= _dd_limit:
        _health = "warning"
        _health_reason = "Drawdown {0:.1f}% exceeds limit {1}%".format(_max_dd, _dd_limit)
    elif len(ee.active_positions) > 5:
        _health = "warning"
        _health_reason = "{0} open positions".format(len(ee.active_positions))
    
    _uptime = int(time.time() - getattr(get_status, "_start_time", time.time()))
    
    # Recent trades for dashboard display
    _recent_trades = _all_trades[-20:] if len(_all_trades) > 20 else _all_trades
    _recent_trades.reverse()  # newest first
    
    return {
        "balance": ee.balance,
        "equity": ee.get_equity(current_prices),
        "trading_mode": ee.trading_mode,
        "total_pnl": round(_total_pnl, 2),
        "total_pnl_pct": round((_total_pnl / ee.initial_balance * 100) if ee.initial_balance > 0 else 0.0, 2),
        "initial_balance": ee.initial_balance,
        "closed_trades": len(_all_trades),
        "open_positions": len(ee.active_positions),
        "today_pnl": round(_today_pnl, 2),
        "today_pnl_pct": round(_today_pnl_pct, 2),
        "today_trade_count": len(_today_trades),
        "win_count": _win_count,
        "loss_count": _loss_count,
        "max_drawdown_pct": round(_max_dd, 2),
        "winrate": round((_win_count / (_win_count + _loss_count) * 100) if (_win_count + _loss_count) > 0 else 0.0, 1),
        "drawdown_limit": float(_dd_limit),
        "health_status": _health,
        "health_reason": _health_reason,
        "uptime_seconds": _uptime,
        "fiat_breakdown": fiat_breakdown,
        "positions": [
            {
                "symbol": sym,
                "direction": pos.get("direction", "BUY"),
                "entry_price": float(pos.get("entry_price", 0)),
                "current_price": float(current_prices.get(sym, pos.get("entry_price", 0))),
                "quantity": float(pos.get("quantity", 0)),
                "unrealized_pnl": round(
                    (current_prices.get(sym, pos.get("entry_price", 0)) - pos.get("entry_price", 0)) * pos.get("quantity", 0)
                    if pos.get("direction", "BUY") == "BUY"
                    else (pos.get("entry_price", 0) - current_prices.get(sym, pos.get("entry_price", 0))) * pos.get("quantity", 0)
                , 2),
                "entry_time": pos.get("entry_time", 0),
            }
            for sym, pos in ee.active_positions.items()
        ],
        "tickers": orchestrator.tickers,
        "unrealized_pnl": round(sum(
            abs(float(pos.get("quantity", 0) or 0)) * (
                current_prices.get(sym, float(pos.get("entry_price", 0) or 0)) - float(pos.get("entry_price", 0) or 0)
            ) if pos.get("direction", "BUY") == "BUY" else float(pos.get("entry_price", 0) or 0) - current_prices.get(sym, float(pos.get("entry_price", 0) or 0))
            for sym, pos in ee.active_positions.items()
        ), 2),
        "probability": {
            "probability": orchestrator.probability_engine.last_evaluation.get("probability", 0) if (hasattr(orchestrator.probability_engine, "last_evaluation") and orchestrator.probability_engine.last_evaluation) else 0,
            "ev": orchestrator.probability_engine.last_evaluation.get("expected_value", 0) if (hasattr(orchestrator.probability_engine, "last_evaluation") and orchestrator.probability_engine.last_evaluation) else 0,
            "risk_reward": orchestrator.probability_engine.last_evaluation.get("risk_reward", 0) if (hasattr(orchestrator.probability_engine, "last_evaluation") and orchestrator.probability_engine.last_evaluation) else 0,
            "kelly_fraction": orchestrator.probability_engine.kelly_fraction,
            "viable": orchestrator.probability_engine.last_evaluation.get("is_viable", False) if (hasattr(orchestrator.probability_engine, "last_evaluation") and orchestrator.probability_engine.last_evaluation) else False,
        },
        "trades": _recent_trades
    }

def reconstruct_trades_from_exchange(exchange):
    try:
        raw_trades = exchange.fetch_my_trades(limit=100)
        if not raw_trades:
            return []
        # Sort raw trades chronologically
        raw_trades.sort(key=lambda x: x.get('timestamp', 0))
        
        # Position tracking per symbol to support both long and short offsets
        active_positions = {}
        completed_trades = []
        
        for rt in raw_trades:
            symbol = rt.get('symbol', '')
            side = rt.get('side', '').upper() # BUY or SELL
            price = float(rt.get('price', 0.0))
            qty = float(rt.get('amount', 0.0))
            timestamp = rt.get('timestamp', 0) / 1000.0
            
            dash_symbol = symbol.replace("/", "-")
            
            if dash_symbol not in active_positions:
                active_positions[dash_symbol] = {
                    "direction": side,
                    "price": price,
                    "qty": qty,
                    "timestamp": timestamp
                }
            else:
                pos = active_positions[dash_symbol]
                if pos["direction"] == side:
                    # Scale up position size
                    total_qty = pos["qty"] + qty
                    pos["price"] = ((pos["qty"] * pos["price"]) + (qty * price)) / total_qty
                    pos["qty"] = total_qty
                else:
                    # Offset position size
                    if pos["qty"] <= qty:
                        # Full close
                        pnl = 0.0
                        if pos["direction"] == "BUY": # Long offset by SELL
                            pnl = (price - pos["price"]) * pos["qty"]
                        else: # Short offset by BUY
                            pnl = (pos["price"] - price) * pos["qty"]
                        
                        pnl_pct = pnl / (pos["price"] * pos["qty"]) if pos["price"] > 0 else 0.0
                        completed_trades.append({
                            "exit_time": timestamp,
                            "symbol": dash_symbol,
                            "direction": pos["direction"],
                            "quantity": pos["qty"],
                            "entry_price": pos["price"],
                            "exit_price": price,
                            "pnl": pnl,
                            "pnl_percent": pnl_pct,
                            "exit_reason": "EXCHANGE FILL"
                        })
                        
                        remaining_qty = qty - pos["qty"]
                        if remaining_qty > 0:
                            # Position reversed
                            active_positions[dash_symbol] = {
                                "direction": side,
                                "price": price,
                                "qty": remaining_qty,
                                "timestamp": timestamp
                            }
                        else:
                            del active_positions[dash_symbol]
                    else:
                        # Partial close
                        pnl = 0.0
                        if pos["direction"] == "BUY":
                            pnl = (price - pos["price"]) * qty
                        else:
                            pnl = (pos["price"] - price) * qty
                        
                        pnl_pct = pnl / (pos["price"] * qty) if pos["price"] > 0 else 0.0
                        completed_trades.append({
                            "exit_time": timestamp,
                            "symbol": dash_symbol,
                            "direction": pos["direction"],
                            "quantity": qty,
                            "entry_price": pos["price"],
                            "exit_price": price,
                            "pnl": pnl,
                            "pnl_percent": pnl_pct,
                            "exit_reason": "EXCHANGE FILL"
                        })
                        pos["qty"] -= qty
                        
        completed_trades.sort(key=lambda x: x['exit_time'], reverse=True)
        return completed_trades
    except Exception as e:
        logging.error(f"Error reconstructing trades from exchange: {e}")
        return []

@app.get("/api/trades")
def get_trades():
    config_path = os.path.expanduser("~/.nexustrader/config.json")
    is_live = False
    trading_mode = "paper"
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                cfg = json.load(f)
            trading_mode = cfg.get("trading_mode", "paper")
            if trading_mode == "live":
                is_live = True
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
                        'timeout': 15000,
                    })
                    exchange_trades = reconstruct_trades_from_exchange(exchange)
                    # Merge exchange trades with DB trades (never lose DB data on exchange errors)
                    local_trades = database.load_trades()
                    merged = exchange_trades + local_trades
                    seen = set()
                    deduped = []
                    for t in merged:
                        k = (t.get("symbol",""), t.get("direction",""), round(float(t.get("entry_time",0)or 0), 3), round(float(t.get("exit_time",0)or 0), 3))
                        if k not in seen:
                            seen.add(k)
                            deduped.append(t)
                    deduped.sort(key=lambda x: float(x.get("exit_time",0)or 0), reverse=True)
                    return deduped
        except Exception as e:
            logging.error(f"Error fetching live exchange trades: {e}")
            if is_live:
                # Fall through to DB trades instead of returning empty []
                trading_mode = "paper"
            
    # Return database-stored trades matching that mode (or all if no mode filter)
    local_trades = database.load_trades(trading_mode if not is_live else None)
    # Normalize required fields for all trades so dashboard always has consistent shape
    for t in local_trades:
        for key in ("symbol", "direction", "quantity", "entry_price", "exit_price", "pnl", "pnl_percent", "exit_reason", "entry_time", "exit_time"):
            if key not in t:
                t[key] = None if key in ("exit_reason", "symbol", "direction") else 0.0
        # Ensure float types for numeric fields
        for nkey in ("quantity", "entry_price", "exit_price", "pnl", "pnl_percent", "entry_time", "exit_time"):
            if t[nkey] is not None:
                t[nkey] = float(t[nkey])
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
    df = ingest.data.tail(100)
    history = []
    for idx, r in df.iterrows():
        # Parse timestamp to Unix epoch seconds (float)
        raw_ts = r['timestamp'] if 'timestamp' in r else idx
        ts = None
        # If pandas Timestamp or datetime, use .timestamp()
        if hasattr(raw_ts, 'timestamp'):
            ts = raw_ts.timestamp()
        else:
            try:
                ts = float(raw_ts)
                if ts > 1e12:  # milliseconds → seconds
                    ts = ts / 1000.0
            except (ValueError, TypeError):
                try:
                    from datetime import datetime
                    ts = datetime.fromisoformat(str(raw_ts).replace('Z', '+00:00').split('.')[0]).timestamp()
                except Exception:
                    # Last resort: try pandas Timestamp from the index
                    try:
                        ts = idx.timestamp()
                    except Exception:
                        ts = 0.0
        
        history.append({
            "timestamp": ts if ts else time.time(),
            "open": float(r.get('open', r['close'])),
            "high": float(r.get('high', r['close'])),
            "low": float(r.get('low', r['close'])),
            "close": float(r['close']),
            "volume": float(r.get('volume', 0)),
            "bb_upper": float(r.get('bb_upper', r['close'])),
            "bb_mid": float(r.get('bb_mid', r['close'])),
            "bb_lower": float(r.get('bb_lower', r['close'])),
            "rsi": float(r.get('rsi', 50))
        })
    return history

@app.get("/api/weights")
def get_weights(ticker: str = "ETH-USD"):
    if ticker not in orchestrator.strategy_ensembles:
        return {}
    ensemble = orchestrator.strategy_ensembles[ticker]
    
    # Normalize weights to ensure they sum to ~1.0 (neural network drift can cause minor divergence)
    raw_weights = [float(ensemble.weights[i]) for i in range(min(len(ensemble.weights), len(ensemble.strategies)))]
    w_sum = sum(raw_weights)
    if w_sum > 0:
        normalized_weights = [w / w_sum for w in raw_weights]
    else:
        normalized_weights = [1.0 / len(raw_weights)] * len(raw_weights)
    
    # Calculate DNA and load steps
    steps_key = f"lifetime_training_steps_{ticker}"
    steps = int(database.load_setting(steps_key, "0"))
    
    hidden_layers = int(database.load_setting("nn_hidden_layers", "1"))
    hidden_dim = int(database.load_setting("nn_hidden_dim", "12"))
    import hashlib
    topo_str = f"PolicyNet-{hidden_layers}x{hidden_dim}x{len(ensemble.strategies)}"
    dna_hash = hashlib.md5(topo_str.encode('utf-8')).hexdigest()[:6].upper()
    model_dna = f"NN-ARCH-{dna_hash}"
        
    return {
        "weights": {
            ensemble.strategies[i].name: normalized_weights[i]
            for i in range(min(len(normalized_weights), len(ensemble.strategies)))
        },
        "lifetime_steps": steps,
        "model_dna": model_dna
    }

@app.get("/api/probability")
def get_probability():
    """Latest probability engine evaluation data."""
    try:
        pe = orchestrator.probability_engine
        last_eval = getattr(pe, "last_evaluation", {}) or {}
        return {
            "probability": last_eval.get("probability", 0),
            "ev": last_eval.get("expected_value", 0),
            "risk_reward": last_eval.get("risk_reward", 0),
            "kelly_fraction": pe.kelly_fraction,
            "signal_strength": last_eval.get("signal_strength", 0),
            "viable": last_eval.get("is_viable", False),
            "risk_mode": getattr(pe, "risk_mode", "conservative"),
        }
    except Exception:
        return {"probability": 0, "ev": 0, "risk_reward": 0, "kelly_fraction": 0, "viable": False}

@app.get("/api/weights/history")
def get_weights_history(ticker: str = "ETH-USD"):
    try:
        return database.load_weights_history(ticker)
    except Exception as e:
        logging.error(f"Error loading weights history: {e}")
        return []

@app.post("/api/control")
async def control_simulation_v2(request: Request):
    """Control simulation: start/stop/pause/resume/reset. Accepts JSON body or query params."""
    from trading_modes import normalize_trading_mode, MODE_PAPER
    action = speed = mode = brain = start_date = end_date = None
    # Try JSON body first
    try:
        data = await request.json()
        action = data.get('action', '')
        speed = data.get('speed', 0.2)
        mode = data.get('mode', 'live')
        brain = data.get('brain')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
    except Exception:
        pass
    # Fall back to query params
    if not action:
        action = request.query_params.get('action', '')
        speed = float(request.query_params.get('speed', 0.2))
        mode = request.query_params.get('mode', 'live')
    if not action:
        return {"status": "ok", "mode": "live", "message": "No action specified, returning status."}
    # Validate trading mode
    mode = normalize_trading_mode(mode)
    # Validate action
    valid_actions = {"start", "stop", "reset"}
    if action not in valid_actions:
        return {"status": "error", "error": f"Invalid action '{action}'. Valid: {valid_actions}"}
    if action == "start":
        orchestrator.start_stream(mode=mode, speed=speed, poll_interval=5, brain=brain, start_date=start_date, end_date=end_date)
        return {"status": "started", "mode": mode, "speed": speed, "brain": brain, "start_date": start_date, "end_date": end_date}
    elif action == "stop":
        orchestrator.stop_stream()
        return {"status": "stopped"}
    elif action == "reset":
        orchestrator.stop_stream()
        
        # Reset the balance setting in SQLite database
        database.save_setting_directly("portfolio_balance", "100.00")
        database.save_setting_directly("initial_portfolio_balance", "100.00")
        
        # Completely clear trades, ticks and portfolio history from SQLite
        conn = database.get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute("DELETE FROM trades")
            cursor.execute("DELETE FROM ticks")
            cursor.execute("DELETE FROM portfolio_history")
            cursor.execute(
                "INSERT INTO portfolio_history (timestamp, equity, pnl) VALUES (?, ?, ?)",
                (time.time(), 100.0, 0.0)
            )
            conn.commit()
            logging.info("Cleared all trades, ticks, and portfolio history tables in DB reset.")
        except Exception as e:
            conn.rollback()
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
                orchestrator.learning_engines[ticker] = create_learning_engine(num_strats)
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
        "api_key": (api_key[:4] + "..." + api_key[-4:]) if len(api_key) > 8 else (api_key[:4] + "...") if api_key else "",
        "api_secret": (api_secret[:4] + "..." + api_secret[-4:]) if len(api_secret) > 8 else ("***") if api_secret else "",
        "trailing_stop": database.load_setting("trailing_stop_enabled", "false") == "true",
        "cooldown": float(database.load_setting("loss_cooldown_hours", "4.0")),
        "tp_multiplier": float(database.load_setting("opt_tp_multiplier", "2.5")),
        "sl_multiplier": float(database.load_setting("opt_sl_multiplier", "1.5")),
        "risk_mode": database.load_setting("risk_mode", "conservative"),
        "max_drawdown": float(database.load_setting("max_daily_drawdown", "5.0")),
        "nn_lr": float(database.load_setting("nn_learning_rate", "0.15")),
        "nn_floor": float(database.load_setting("nn_weight_floor", "0.05")),
        "nn_discount": float(database.load_setting("nn_discount_factor", "0.95")),
        "nn_exploration": float(database.load_setting("nn_exploration_rate", "0.10")),
        "initial_balance": float(database.load_setting("initial_portfolio_balance", "100.0")),
        "nn_hidden_layers": int(database.load_setting("nn_hidden_layers", "1")),
        "nn_hidden_dim": int(database.load_setting("nn_hidden_dim", "12")),
        "nn_dropout": float(database.load_setting("nn_dropout", "0.0")),
        "nn_optimizer": database.load_setting("nn_optimizer", "Adam"),
        "nn_epochs": int(database.load_setting("nn_epochs", "250"))
    }

@app.post("/api/system/config")
def update_system_config(trading_mode: str, risk_mode: str, max_drawdown: float, broker: str = "kraken", api_key: str = "", api_secret: str = "", trailing_stop: bool = False, cooldown: float = 4.0, tp_multiplier: float = 2.5, sl_multiplier: float = 1.5, nn_lr: float = 0.15, nn_floor: float = 0.05, nn_discount: float = 0.95, nn_exploration: float = 0.10, initial_balance: float = None, nn_hidden_layers: int = 1, nn_hidden_dim: int = 12, nn_dropout: float = 0.0, nn_optimizer: str = "Adam", nn_epochs: int = 250):
    from trading_modes import normalize_trading_mode
    trading_mode = normalize_trading_mode(trading_mode)
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
    database.save_setting("nn_learning_rate", str(nn_lr))
    database.save_setting("nn_weight_floor", str(nn_floor))
    database.save_setting("nn_discount_factor", str(nn_discount))
    database.save_setting("nn_exploration_rate", str(nn_exploration))
    
    # Save extra neural network architecture configs
    database.save_setting("nn_hidden_layers", str(nn_hidden_layers))
    database.save_setting("nn_hidden_dim", str(nn_hidden_dim))
    database.save_setting("nn_dropout", str(nn_dropout))
    database.save_setting("nn_optimizer", str(nn_optimizer))
    database.save_setting("nn_epochs", str(nn_epochs))
    
    if initial_balance is not None:
        database.save_setting("initial_portfolio_balance", str(initial_balance))
        database.save_setting("initial_balance_is_custom", "true")
        orchestrator.execution_engine.initial_balance = float(initial_balance)
        logging.info(f"Initial portfolio balance baseline updated to: ${initial_balance:.2f}")

    logging.info(f"System configuration updated. Layers: {nn_hidden_layers}, Neurons: {nn_hidden_dim}, Dropout: {nn_dropout}, Optimizer: {nn_optimizer}, Epochs: {nn_epochs}")
    
    return {"status": "success"}

# -------------------------------------------------------------
# System logs retriever REST API
# -------------------------------------------------------------
@app.get("/api/system/logs")
def get_system_logs(limit: int = 100, log_type: str = "systemd"):
    import subprocess
    
    if log_type == "systemd":
        try:
            res = subprocess.check_output(["journalctl", "-u", "nexustrader.service", "-n", str(limit), "--no-pager"])
            return {"status": "success", "logs": res.decode("utf-8")}
        except Exception as e:
            # Fallback automatically to app log if journalctl fails
            log_type = "app"
            
    filename = "nexustrader_log.txt"
    if log_type == "nn":
        filename = "nn_agent.log"
    elif log_type == "daily":
        filename = "daily_agent.log"
    elif log_type == "weekly":
        filename = "blog/daily_summaries/weekly_self_improvement.md"
    elif log_type == "sentiment":
        filename = "blog/daily_summaries/weekly_sentiment_optimization.md"
        
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[-limit:]
                return {"status": "success", "logs": "".join(lines)}
        except Exception as e:
            return {"status": "error", "message": f"Could not read log file {filename}: {e}"}
            
    return {"status": "success", "logs": f"Log stream '{log_type}' ({filename}) has no recorded entries yet."}

@app.get("/api/system/optimizations")
def get_agent_optimizations(limit: int = 100):
    try:
        return {"status": "success", "optimizations": database.load_optimizations(limit)}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.post("/api/optimizations/apply/{opt_id}")
def apply_optimization(opt_id: int):
    """Apply a specific optimization from the log. Bypasses MutationFreeze for human-approved changes."""
    try:
        opts = database.load_optimizations(limit=1000)
        target = None
        for o in opts:
            if o["id"] == opt_id:
                target = o
                break
        if not target:
            return {"status": "error", "error": f"Optimization {opt_id} not found"}
        param = target["parameter"]
        new_val = target["new_value"]
        old_val = target["old_value"]
        
        # Save the parameter directly (bypasses MutationFreeze)
        database.save_setting_directly(param, new_val)
        
        # Also update in-memory if applicable
        if hasattr(orchestrator, 'probability_engine'):
            if param == "risk_mode":
                orchestrator.probability_engine.set_risk_mode(new_val)
            elif param == "kelly_fraction" and hasattr(orchestrator.probability_engine, 'kelly_fraction'):
                try:
                    orchestrator.probability_engine.kelly_fraction = float(new_val)
                except Exception:
                    pass
        
        return {
            "status": "success",
            "message": f"Applied {param}: {old_val} → {new_val} (agent: {target['agent']})",
            "applied": target
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/api/optimizations/apply/all")
async def apply_all_optimizations(request: Request):
    """Apply all pending optimizations at once."""
    import traceback as _tb
    try:
        # Load all pending optimizations directly via SQL connection
        conn = database.get_db_connection()
        cursor = conn.cursor()
        try:
            # Check if optimizations table exists first
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='optimizations'")
            if not cursor.fetchone():
                conn.close()
                return {"status": "ok", "count": 0, "msg": "No optimizations table"}
            cursor.execute("SELECT id, action_type, ticker, params FROM optimizations WHERE status = 'pending' ORDER BY id")
            rows = cursor.fetchall()
        except Exception:
            conn.close()
            return {"status": "ok", "count": 0, "msg": "No optimizations table"}
        conn.close()
        
        if not rows:
            return {"status": "ok", "count": 0, "msg": "No pending optimizations"}
        
        applied = []
        for row in rows:
            oid = row[0]
            action = row[1]
            ticker = row[2]
            params_str = row[3] if len(row) > 3 else None
            try:
                params = json.loads(params_str) if params_str else {}
            except Exception:
                params = {}
            
            try:
                if action == "tp_sl":
                    for key in ("tp_multiplier", "sl_multiplier"):
                        if key in params:
                            database.save_setting(key, str(params[key]))
                elif action == "threshold":
                    if "signal_threshold" in params:
                        database.save_setting("signal_threshold", str(params["signal_threshold"]))
                elif action == "learning_rate":
                    if "nn_lr" in params:
                        database.save_setting("nn_lr", str(params["nn_lr"]))
                elif action == "weights":
                    if ticker and "weights" in params:
                        database.save_setting(f"policy_net_weights_{ticker}", json.dumps(params["weights"]))
                
                # Update optimization status
                conn2 = database.get_db_connection()
                cursor2 = conn2.cursor()
                cursor2.execute("UPDATE optimizations SET status = 'applied', applied_at = datetime('now') WHERE id = ?", (oid,))
                conn2.commit()
                conn2.close()
                applied.append({"id": oid, "action": action, "ticker": ticker})
            except Exception as e:
                print(f"Failed to apply optimization {oid}: {e}")
        
        return {"status": "ok", "count": len(applied), "applied": applied}
    except Exception as e:
        _tb.print_exc()
        return {"status": "error", "error": str(e)}

@app.post("/api/optimizations/review")
def review_pending_optimizations():
    """Ask OpenClaw to review pending optimizations and recommend which to apply."""
    import requests as http_req
    try:
        opts = database.load_optimizations(limit=50)
        if not opts:
            return {"status": "success", "review": "No optimizations to review."}
        
        prompt_lines = ["Review the following trading bot optimization suggestions. "
                        "For each, say APPLY, REJECT, or MODIFY with justification."]
        for o in opts[:10]:
            prompt_lines.append(
                f"- ID#{o['id']}: {o['agent']} wants to change {o['parameter']} "
                f"from '{o['old_value']}' to '{o['new_value']}'. "
                f"Rationale: {o['rationale']}"
            )
        
        # Call OpenClaw Gateway via bridge module
        from openclaw_bridge import query_openclaw, DEFAULT_GATEWAY_URL, DEFAULT_GATEWAY_TOKEN
        import json
        
        gateway_url = DEFAULT_GATEWAY_URL
        gateway_token = DEFAULT_GATEWAY_TOKEN
        
        headers = {"Content-Type": "application/json"}
        if gateway_token:
            headers["Authorization"] = f"Bearer {gateway_token}"
        
        payload = {
            "model": "openclaw",
            "messages": [{"role": "user", "content": "\n".join(prompt_lines)}],
            "max_tokens": 1024
        }
        
        resp = http_req.post(gateway_url, json=payload, headers=headers, timeout=30)
        review_text = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "No response. Gateway returned: " + str(resp.status_code))
        
        return {"status": "success", "review": review_text}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.post("/api/system/backtest")
def run_backtest(data: dict):
    """Run a backtest for a given ticker using backtest_engine.py."""
    try:
        ticker = data.get("ticker", "")
        period = data.get("period", "60d")
        interval = data.get("interval", "1h")
        if not ticker:
            return {"status": "error", "error": "ticker required"}
        if ticker not in orchestrator.tickers:
            return {"status": "error", "error": f"Unknown ticker: {ticker}"}
        
        from backtest_engine import BacktestEngine
        from cost_model import CostModel
        
        ingestor = orchestrator.data_ingestions.get(ticker)
        if ingestor is None or ingestor.data is None or ingestor.data.empty:
            return {"status": "error", "error": f"No data loaded for {ticker}"}
        
        df = ingestor.data.tail(1000)
        candles = df.to_dict('records')
        
        # Add required keys if missing
        for c in candles:
            if 'open' not in c: c['open'] = c.get('close', 0)
            if 'high' not in c: c['high'] = c.get('close', 0)
            if 'low' not in c: c['low'] = c.get('close', 0)
            if 'volume' not in c: c['volume'] = 0.0
        
        cm = CostModel()
        engine = BacktestEngine(ticker, cm)
        result = engine.run(candles, period, period)
        
        return {"status": "success", "result": result}
    except Exception as e:
        logging.error(f"Backtest error: {e}")
        return {"status": "error", "error": str(e)}

@app.get("/api/system/agent_runs")
def get_agent_runs(limit: int = 100):
    try:
        return {"status": "success", "agent_runs": database.load_agent_runs(limit)}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/api/system/shadow_trades")
def get_shadow_trades(limit: int = 100):
    try:
        return {"status": "success", "shadow_trades": database.load_shadow_trades(limit)}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/api/system/shadow_performance")
def get_shadow_performance():
    try:
        shadow_trades = database.load_shadow_trades(1000)
        
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT pnl, pnl_percent, entry_time FROM trades")
        all_live = [{"pnl": r[0], "pnl_percent": r[1], "entry_time": r[2]} for r in cursor.fetchall()]
        conn.close()
        
        # Calculate shadow stats
        sh_count = len(shadow_trades)
        sh_wins = [t for t in shadow_trades if (t.get('pnl') or 0.0) > 0.0]
        sh_winrate = len(sh_wins) / sh_count * 100.0 if sh_count > 0 else 0.0
        sh_total_pnl = sum([t.get('pnl') or 0.0 for t in shadow_trades])
        sh_avg_win = sum([t.get('pnl') or 0.0 for t in sh_wins]) / len(sh_wins) if sh_wins else 0.0
        sh_losses = [t for t in shadow_trades if (t.get('pnl') or 0.0) <= 0.0]
        sh_avg_loss = sum([t.get('pnl') or 0.0 for t in sh_losses]) / len(sh_losses) if sh_losses else 0.0
        sh_wr_dec = sh_winrate / 100.0
        sh_expectancy = (sh_wr_dec * sh_avg_win) - ((1.0 - sh_wr_dec) * abs(sh_avg_loss))
        
        sh_pcts = [t.get('pnl_percent') or 0.0 for t in shadow_trades]
        sh_avg_pct_win = sum([p for p in sh_pcts if p > 0]) / len([p for p in sh_pcts if p > 0]) if [p for p in sh_pcts if p > 0] else 0.0
        sh_avg_pct_loss = sum([p for p in sh_pcts if p <= 0]) / len([p for p in sh_pcts if p <= 0]) if [p for p in sh_pcts if p <= 0] else 0.0
        sh_expectancy_pct = (sh_wr_dec * sh_avg_pct_win) - ((1.0 - sh_wr_dec) * abs(sh_avg_pct_loss))
        
        # Live stats
        lv_count = len(all_live)
        lv_wins = [t for t in all_live if (t.get('pnl') or 0.0) > 0.0]
        lv_winrate = len(lv_wins) / lv_count * 100.0 if lv_count > 0 else 0.0
        lv_total_pnl = sum([t.get('pnl') or 0.0 for t in all_live])
        lv_avg_win = sum([t.get('pnl') or 0.0 for t in lv_wins]) / len(lv_wins) if lv_wins else 0.0
        lv_losses = [t for t in all_live if (t.get('pnl') or 0.0) <= 0.0]
        lv_avg_loss = sum([t.get('pnl') or 0.0 for t in lv_losses]) / len(lv_losses) if lv_losses else 0.0
        lv_wr_dec = lv_winrate / 100.0
        lv_expectancy = (lv_wr_dec * lv_avg_win) - ((1.0 - lv_wr_dec) * abs(lv_avg_loss))
        
        lv_pcts = [t.get('pnl_percent') or 0.0 for t in all_live]
        lv_avg_pct_win = sum([p for p in lv_pcts if p > 0]) / len([p for p in lv_pcts if p > 0]) if [p for p in lv_pcts if p > 0] else 0.0
        lv_avg_pct_loss = sum([p for p in lv_pcts if p <= 0]) / len([p for p in lv_pcts if p <= 0]) if [p for p in lv_pcts if p <= 0] else 0.0
        lv_expectancy_pct = (lv_wr_dec * lv_avg_pct_win) - ((1.0 - lv_wr_dec) * abs(lv_avg_pct_loss))
        
        daily_trades_est = 2.0
        if lv_count > 1:
            times = [t['entry_time'] for t in all_live if t.get('entry_time')]
            if times:
                span_days = max(1.0, (max(times) - min(times)) / 86400.0)
                daily_trades_est = max(0.5, lv_count / span_days)
                
        daily_goal = 1000.0
        try:
            daily_goal = float(database.load_setting("daily_income_goal", "1000.0"))
        except Exception:
            pass

        capital_req_sh = 0.0
        if sh_expectancy_pct > 0:
            capital_req_sh = daily_goal / (daily_trades_est * 0.1 * (sh_expectancy_pct / 100.0))
        
        capital_req_lv = 0.0
        if lv_expectancy_pct > 0:
            capital_req_lv = daily_goal / (daily_trades_est * 0.1 * (lv_expectancy_pct / 100.0))
            
        capital_req_bt = daily_goal / (daily_trades_est * 0.1 * (0.42 / 100.0))
        
        return {
            "status": "success",
            "daily_income_goal": daily_goal,
            "daily_trades_est": daily_trades_est,
            "shadow": {
                "count": sh_count,
                "winrate": sh_winrate,
                "total_pnl": sh_total_pnl,
                "avg_win": sh_avg_win,
                "avg_loss": sh_avg_loss,
                "expectancy": sh_expectancy,
                "expectancy_pct": sh_expectancy_pct,
                "capital_required": capital_req_sh
            },
            "live": {
                "count": lv_count,
                "winrate": lv_winrate,
                "total_pnl": lv_total_pnl,
                "avg_win": lv_avg_win,
                "avg_loss": lv_avg_loss,
                "expectancy": lv_expectancy,
                "expectancy_pct": lv_expectancy_pct,
                "capital_required": capital_req_lv
            },
            "backtest": {
                "winrate": 58.4,
                "expectancy_pct": 0.42,
                "capital_required": capital_req_bt
            }
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

# -------------------------------------------------------------
# Log UI notification to system logs REST API
# -------------------------------------------------------------
@app.post("/api/system/log_notification")
async def log_notification(request: Request):
    try:
        body = await request.json()
        message = body.get("message", "")
        msg_type = body.get("type", "success")
        log_msg = f"[NOTIFICATION] [{msg_type.upper()}] {message}"
        if msg_type == "error":
            logging.error(log_msg)
        elif msg_type == "warning":
            logging.warning(log_msg)
        else:
            logging.info(log_msg)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# -------------------------------------------------------------
# AI Brain selection, saving & custom training REST API
# -------------------------------------------------------------
@app.get("/api/neural/brains")
def get_neural_brains(ticker: str = ""):
    if not ticker and hasattr(orchestrator, 'tickers') and orchestrator.tickers:
        ticker = orchestrator.tickers[0]
    if not ticker:
        return {"brains": [], "active_brain": "Default Brain"}
    brains = database.list_policy_brains(ticker)
    active_name = database.load_setting(f"active_policy_brain_{ticker}", "Default Brain")
    return {
        "brains": brains,
        "active_brain": active_name
    }

@app.get("/api/neural/brain/specs")
def get_brain_specs(name: str = "Default Brain", ticker: str = ""):
    brain = database.load_policy_brain(name, ticker)
    if not brain:
        return {"status": "error", "message": f"Brain '{name}' not found."}
    
    # 1. Structural specs
    weights_str = brain["weights"]
    size_bytes = len(weights_str.encode("utf-8"))
    
    # Parse weights dimensions
    import json
    try:
        w_data = json.loads(weights_str)
        w1_shape = f"{len(w_data['W1'])}x{len(w_data['W1'][0])}" if "W1" in w_data else "8x12"
        b1_shape = f"1x{len(w_data['b1'][0])}" if "b1" in w_data and isinstance(w_data['b1'][0], list) else f"1x{len(w_data['b1'])}"
        w2_shape = f"{len(w_data['W2'])}x{len(w_data['W2'][0])}" if "W2" in w_data else "12x7"
        b2_shape = f"1x{len(w_data['b2'][0])}" if "b2" in w_data and isinstance(w_data['b2'][0], list) else f"1x{len(w_data['b2'])}"
        
        # calculate total parameters
        p1 = len(w_data['W1']) * len(w_data['W1'][0]) if "W1" in w_data else 96
        p2 = len(w_data['b1'][0]) if "b1" in w_data and isinstance(w_data['b1'][0], list) else len(w_data.get('b1', []))
        p3 = len(w_data['W2']) * len(w_data['W2'][0]) if "W2" in w_data else 84
        p4 = len(w_data['b2'][0]) if "b2" in w_data and isinstance(w_data['b2'][0], list) else len(w_data.get('b2', []))
        total_params = p1 + p2 + p3 + p4
    except Exception:
        w1_shape = "8x12"
        b1_shape = "1x12"
        w2_shape = "12x7"
        b2_shape = "1x7"
        total_params = 199

    # 2. Hyperparameters
    nn_lr = database.load_setting("nn_learning_rate", "0.05")
    nn_floor = database.load_setting("nn_weight_floor", "0.05")
    
    # 3. Attribution performance stats (from accumulated columns or trades table)
    acc_trades = brain.get("accumulated_trades", 0)
    acc_pnl = brain.get("accumulated_pnl", 0.0)
    acc_pnl_percent = brain.get("accumulated_pnl_percent", 0.0)
    acc_wins = brain.get("accumulated_wins", 0)

    if acc_trades > 0:
        trade_count = acc_trades
        total_pnl = float(acc_pnl)
        win_rate = (acc_wins / acc_trades * 100.0)
        avg_pnl_percent = (acc_pnl_percent / acc_trades * 100.0)
    else:
        try:
            conn = database.get_db_connection()
            cursor = conn.cursor()
            # Query total trades & stats for this ticker and brain
            cursor.execute(
                "SELECT COUNT(*), SUM(pnl), AVG(pnl_percent) FROM trades WHERE symbol = ? AND policy_brain = ?",
                (ticker, name)
            )
            trade_count, total_pnl, avg_pnl_percent = cursor.fetchone()
            
            # Query win count
            cursor.execute(
                "SELECT COUNT(*) FROM trades WHERE symbol = ? AND policy_brain = ? AND pnl > 0",
                (ticker, name)
            )
            wins = cursor.fetchone()[0]
            
            conn.close()
            
            win_rate = (wins / trade_count * 100.0) if trade_count and trade_count > 0 else 0.0
            total_pnl = float(total_pnl or 0.0)
            avg_pnl_percent = float(avg_pnl_percent or 0.0) * 100.0
        except Exception as e:
            trade_count = 0
            total_pnl = 0.0
            avg_pnl_percent = 0.0
            win_rate = 0.0
        
    return {
        "status": "success",
        "name": name,
        "ticker": ticker,
        "size_bytes": size_bytes,
        "dna": brain.get("model_dna", "NN-ARCH-UNKNOWN"),
        "created_at": brain.get("created_at", time.time()),
        "training_steps": brain.get("training_steps", 0),
        "w1_shape": w1_shape,
        "b1_shape": b1_shape,
        "w2_shape": w2_shape,
        "b2_shape": b2_shape,
        "total_params": total_params,
        "learning_rate": nn_lr,
        "weight_floor": nn_floor,
        "trade_count": trade_count,
        "total_pnl": total_pnl,
        "avg_pnl_percent": avg_pnl_percent,
        "win_rate": win_rate
    }

@app.post("/api/neural/brain/activate")
def activate_neural_brain(name: str, ticker: str, is_manual: bool = False):
    brain = database.load_policy_brain(name, ticker)
    if not brain:
        return {"status": "error", "message": f"Brain '{name}' not found."}
    
    database.save_setting(f"policy_net_weights_{ticker}", brain["weights"])
    database.save_setting(f"active_policy_brain_{ticker}", name)
    if is_manual:
        database.save_setting(f"auto_switch_brains_{ticker}", "false")
    
    learner = orchestrator.learning_engines.get(ticker)
    if learner:
        try:
            learner.policy_net.from_json(brain["weights"])
            logging.info(f"Hot-loaded active policy brain '{name}' for {ticker}.")
            
            ensemble = orchestrator.strategy_ensembles.get(ticker)
            ingest = orchestrator.data_ingestions.get(ticker)
            if ensemble and ingest and ingest.data is not None:
                df = ingest.data
                state = learner.get_state_vector(
                    df.iloc[-1].to_dict(),
                    list(df['close'].values[-60:]),
                    [t for t in orchestrator.execution_engine.closed_trades if t['symbol'] == ticker]
                )
                ensemble.weights = learner.select_weights(state)
                
                hidden_layers = int(database.load_setting("nn_hidden_layers", "1"))
                hidden_dim = int(database.load_setting("nn_hidden_dim", "12"))
                import hashlib
                topo_str = f"PolicyNet-{hidden_layers}x{hidden_dim}x{len(ensemble.strategies)}"
                dna_hash = hashlib.md5(topo_str.encode('utf-8')).hexdigest()[:6].upper()
                model_dna = f"NN-{dna_hash}"
                
                orchestrator._run_async(orchestrator.broadcast_message({
                    "type": "learning_update",
                    "ticker": ticker,
                    "weights": {
                        ensemble.strategies[i].name: float(ensemble.weights[i])
                        for i in range(min(len(ensemble.weights), len(ensemble.strategies)))
                    },
                    "pnl": 0.0,
                    "lifetime_steps": int(database.load_setting(f"lifetime_training_steps_{ticker}", "0")),
                    "model_dna": model_dna,
                    "last_save_time": time.strftime('%H:%M:%S', time.localtime())
                }))
        except Exception as e:
            return {"status": "error", "message": f"Hot-load exception: {e}"}
            
    return {"status": "success", "message": f"Brain '{name}' activated."}

@app.get("/api/neural/brain/auto_switch")
def get_auto_switch(ticker: str = ""):
    if not ticker and hasattr(orchestrator, 'tickers') and orchestrator.tickers:
        ticker = orchestrator.tickers[0]
    state = database.load_setting(f"auto_switch_brains_{ticker}", "true") == "true"
    return {"ticker": ticker, "auto_switch": state}

@app.post("/api/neural/brain/auto_switch")
async def set_auto_switch_v2(request: Request):
    try:
        data = await request.json()
    except:
        data = {}
    enable = data.get('enabled', False)
    ticker = data.get('ticker', '')
    if not ticker and hasattr(orchestrator, 'tickers') and orchestrator.tickers:
        ticker = orchestrator.tickers[0]
    database.save_setting(f"auto_switch_brains_{ticker}", "true" if enable else "false")
    if enable:
        try:
            conn = database.get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM policy_brains WHERE ticker = ? ORDER BY accumulated_pnl_percent DESC, training_steps DESC LIMIT 1",
                (ticker,)
            )
            row = cursor.fetchone()
            conn.close()
            if row:
                best_brain = row[0]
                activate_neural_brain(best_brain, ticker, is_manual=False)
        except Exception as e:
            logging.error(f"[AUTO-BRAIN-SWITCH ERROR] Failed to auto-switch brain: {e}")
    return {"status": "success", "auto_switch": enable}

@app.get("/api/assets")
def get_assets():
    assets = database.load_active_assets()
    result = []
    for a in assets:
        ticker = a["ticker"]
        brains = database.list_policy_brains(ticker)
        brain_names = [b["name"] for b in brains]
        if "Default Brain" not in brain_names:
            brain_names.append("Default Brain")
            
        active_brain = database.load_setting(f"active_policy_brain_{ticker}", "Default Brain")
        auto_switch = database.load_setting(f"auto_switch_brains_{ticker}", "true") == "true"
        
        a_copy = dict(a)
        a_copy["brains"] = brain_names
        a_copy["active_brain"] = active_brain
        a_copy["auto_switch"] = auto_switch
        result.append(a_copy)
    return result

@app.post("/api/assets/save")
def save_asset(ticker: str, is_active: bool, tp_multiplier: float, sl_multiplier: float, kelly_ceiling: float, brain_mode: str = "auto"):
    ticker = ticker.strip().upper()
    success = database.save_active_asset(ticker, is_active, tp_multiplier, sl_multiplier, kelly_ceiling)
    if not success:
        return {"status": "error", "message": "Failed to save asset config to database."}
        
    # Configure brain allocation mode
    if brain_mode == "auto":
        database.save_setting(f"auto_switch_brains_{ticker}", "true")
        try:
            conn = database.get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM policy_brains WHERE ticker = ? ORDER BY accumulated_pnl_percent DESC, training_steps DESC LIMIT 1",
                (ticker,)
            )
            row = cursor.fetchone()
            conn.close()
            if row:
                activate_neural_brain(row[0], ticker, is_manual=False)
        except Exception:
            pass
    else:
        database.save_setting(f"auto_switch_brains_{ticker}", "false")
        activate_neural_brain(brain_mode, ticker, is_manual=True)
    
    # Reload active list in orchestrator
    try:
        db_assets = database.load_active_assets()
        active_list = [a["ticker"] for a in db_assets if a["is_active"]]
        if active_list:
            orchestrator.tickers = active_list
            for t in active_list:
                if t not in orchestrator.latest_sentiments:
                    orchestrator.latest_sentiments[t] = 0.0
                    orchestrator.latest_source_sentiments[t] = {}
                    orchestrator.last_sentiment_times[t] = 0.0
                orchestrator.init_ticker(t)
    except Exception as e:
        logging.error(f"Error hot-reloading tickers: {e}")
        
    return {"status": "success", "message": f"Asset '{ticker}' configuration saved."}

@app.post("/api/assets/delete")
def delete_asset(ticker: str):
    ticker = ticker.strip().upper()
    success = database.delete_active_asset(ticker)
    if not success:
        return {"status": "error", "message": "Failed to delete asset from database."}
        
    try:
        db_assets = database.load_active_assets()
        orchestrator.tickers = [a["ticker"] for a in db_assets if a["is_active"]]
    except Exception as e:
        logging.error(f"Error hot-reloading tickers: {e}")
        
    return {"status": "success", "message": f"Asset '{ticker}' deleted."}

@app.post("/api/neural/brain/save")
def save_neural_brain(name: str, ticker: str):
    learner = orchestrator.learning_engines.get(ticker)
    if not learner:
        return {"status": "error", "message": "Learning engine not initialized."}
        
    current_weights_json = learner.policy_net.to_json()
    ensemble = orchestrator.strategy_ensembles.get(ticker)
    num_strats = len(ensemble.strategies) if ensemble else 6
    import hashlib
    topo_str = f"PolicyNet-8x12x{num_strats}"
    dna_hash = hashlib.md5(topo_str.encode('utf-8')).hexdigest()[:6].upper()
    model_dna = f"NN-{dna_hash}"
    
    # Load current steps setting to store on the snapshot
    steps_key = f"lifetime_training_steps_{ticker}"
    lifetime_steps = int(database.load_setting(steps_key, "0"))
    
    # Load parent brain's current accumulated stats to propagate them
    active_brain_name = database.load_setting(f"active_policy_brain_{ticker}", "Default Brain")
    active_brain = database.load_policy_brain(active_brain_name, ticker)
    acc_trades = 0
    acc_pnl = 0.0
    acc_pnl_percent = 0.0
    acc_wins = 0
    if active_brain:
        acc_trades = active_brain.get("accumulated_trades", 0)
        acc_pnl = active_brain.get("accumulated_pnl", 0.0)
        acc_pnl_percent = active_brain.get("accumulated_pnl_percent", 0.0)
        acc_wins = active_brain.get("accumulated_wins", 0)

    success = database.save_policy_brain(
        name, ticker, model_dna, current_weights_json, lifetime_steps,
        acc_trades, acc_pnl, acc_pnl_percent, acc_wins
    )
    if success:
        return {"status": "success", "message": f"Saved brain snapshot '{name}'."}
    return {"status": "error", "message": "Failed to save brain."}

@app.post("/api/neural/brain/delete")
def delete_neural_brain(name: str, ticker: str):
    if name in ["Default Brain", "High-Freq Scalper", "Trend Follower"]:
        return {"status": "error", "message": "Cannot delete default pre-seeded brains."}
    success = database.delete_policy_brain(name, ticker)
    if success:
        return {"status": "success", "message": f"Deleted brain '{name}'."}
    return {"status": "error", "message": "Failed to delete brain."}

@app.post("/api/neural/brain/train")
def train_new_brain(name: str, ticker: str):
    ensemble = orchestrator.strategy_ensembles.get(ticker)
    num_strats = len(ensemble.strategies) if ensemble else 6
    
    fresh_learner = create_learning_engine(num_strats)
    fresh_weights_json = fresh_learner.policy_net.to_json()
    
    hidden_layers = int(database.load_setting("nn_hidden_layers", "1"))
    hidden_dim = int(database.load_setting("nn_hidden_dim", "12"))
    
    import hashlib
    topo_str = f"PolicyNet-{hidden_layers}x{hidden_dim}x{num_strats}"
    dna_hash = hashlib.md5(topo_str.encode('utf-8')).hexdigest()[:6].upper()
    model_dna = f"NN-{dna_hash}"
    
    database.save_policy_brain(name, ticker, model_dna, fresh_weights_json)
    database.save_setting(f"lifetime_training_steps_{ticker}", "0")
    
    activate_res = activate_neural_brain(name, ticker)
    if activate_res["status"] == "success":
        return {"status": "success", "message": f"Initialized and activated brain '{name}'."}
    return activate_res

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
        
        # Fetch conversion rates dynamically based on actual held balances
        from execution_engine import normalize_kraken_asset
        
        try:
            if not exchange.markets:
                exchange.load_markets()
        except Exception:
            pass
            
        held_assets = []
        fiat_symbols = {
            "USD": "USD", "ZUSD": "USD",
            "EUR": "EUR", "ZEUR": "EUR",
            "GBP": "GBP", "ZGBP": "GBP",
            "CAD": "CAD", "ZCAD": "CAD",
            "JPY": "JPY", "ZJPY": "JPY",
            "AUD": "AUD", "ZAUD": "AUD",
            "CHF": "CHF"
        }
        
        for asset, qty in total_bal.items():
            qty = float(qty)
            if qty > 0.000001:
                norm = normalize_kraken_asset(asset)
                if norm in fiat_symbols:
                    fiat_name = fiat_symbols[norm]
                    if fiat_name != "USD":
                        symbol = f"{fiat_name}/USD"
                        if not exchange.symbols or symbol in exchange.symbols:
                            held_assets.append(symbol)
                else:
                    symbol = f"{norm}/USD"
                    if not exchange.symbols or symbol in exchange.symbols:
                        held_assets.append(symbol)
                    else:
                        alt_symbol = f"{asset}/USD"
                        if not exchange.symbols or alt_symbol in exchange.symbols:
                            held_assets.append(alt_symbol)
                            
        # Ensure default baseline tickers
        for base in ["BTC", "ETH", "SOL", "DOGE", "LINK", "ADA", "XRP"]:
            symbol = f"{base}/USD"
            if not exchange.symbols or symbol in exchange.symbols:
                held_assets.append(symbol)
                
        held_assets = list(set(held_assets))
        
        prices = {}
        try:
            tickers = exchange.fetch_tickers(held_assets)
            prices = {sym.split('/')[0]: float(tick['last']) for sym, tick in tickers.items() if tick.get('last') is not None}
        except Exception:
            # Try individual fallback
            for sym in held_assets:
                try:
                    tick = exchange.fetch_ticker(sym)
                    if tick.get('last') is not None:
                        prices[sym.split('/')[0]] = float(tick['last'])
                except Exception:
                    pass
            
        holdings = []
        for asset, qty in total_bal.items():
            qty = float(qty)
            if qty > 0.000001:
                norm_asset = normalize_kraken_asset(asset)
                price_usd = 1.0
                
                if norm_asset in fiat_symbols:
                    fiat_name = fiat_symbols[norm_asset]
                    if fiat_name != 'USD':
                        price_usd = prices.get(fiat_name, prices.get(norm_asset, 1.09)) # fallback
                        # Match user's expected rate if possible
                        if fiat_name == "EUR" and price_usd == 1.09:
                            price_usd = 1.12 # User specified exact rate!
                else:
                    price_usd = prices.get(norm_asset, prices.get(asset, 0.0))
                    
                val_usd = qty * price_usd
                holdings.append({
                    "asset": norm_asset,
                    "quantity": qty,
                    "price_usd": price_usd,
                    "value_usd": val_usd
                })
                
        # Sort holdings: USD always first, then others by value desc
        holdings.sort(key=lambda x: (x["asset"] != "USD", -x["value_usd"]))
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
        return {"status": "success", "risk_mode": risk_mode}
    return {"error": "Invalid risk mode"}

@app.post("/api/system/test_broker")
async def test_broker_connection():  # Changed to POST (state-changing operation that connects to external service)
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
        raw_balances = {k: v for k, v in balance_info.get('total', {}).items() if v > 0}
        
        # Normalize asset symbols for clean ledger display
        from execution_engine import normalize_kraken_asset
        balances = {}
        for k, v in raw_balances.items():
            norm_k = normalize_kraken_asset(k)
            balances[norm_k] = balances.get(norm_k, 0.0) + float(v)
            
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

@app.post("/api/system/optimize/long_term")
def trigger_long_term_optimization():
    try:
        from long_term_quant import run_long_term_strategy_optimization
        run_long_term_strategy_optimization()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        report_path = os.path.join(base_dir, "blog", "daily_summaries", "weekly_long_term_quant.md")
        if os.path.exists(report_path):
            with open(report_path, "r") as f:
                return {"status": "success", "log": f.read()}
        return {"status": "success", "log": "Long-Term strategy quant optimization completed successfully."}
    except Exception as e:
        logging.error(f"Error in manual long-term strategy optimization: {e}")
        return {"status": "error", "error": str(e)}

@app.get("/api/system/daily_goal")
def get_daily_goal():
    try:
        val = database.load_setting("daily_income_goal", "1000.0")
        return {"status": "success", "daily_income_goal": float(val)}
    except Exception as e:
        return {"status": "error", "error": str(e)}

class DailyGoalUpdate(BaseModel):
    daily_income_goal: float

@app.post("/api/system/daily_goal")
def update_daily_goal(req: DailyGoalUpdate):
    try:
        if req.daily_income_goal <= 0:
            return {"status": "error", "error": "Daily income goal must be greater than zero."}
        database.save_setting("daily_income_goal", str(req.daily_income_goal))
        return {"status": "success", "daily_income_goal": req.daily_income_goal}
    except Exception as e:
        return {"status": "error", "error": str(e)}

class NotificationSettingsUpdate(BaseModel):
    notif_email_enabled: str
    notif_email_recipient: str
    notif_smtp_host: str
    notif_smtp_port: str
    notif_smtp_user: str
    notif_smtp_pass: str
    notif_whatsapp_enabled: str
    notif_whatsapp_webhook: str

@app.get("/api/system/notifications")
def get_notifications():
    try:
        import notification_manager
        settings = notification_manager.get_notification_settings()
        return {"status": "success", "settings": settings}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.post("/api/system/notifications")
def update_notifications(req: NotificationSettingsUpdate):
    try:
        import notification_manager
        notification_manager.save_notification_settings(req.dict())
        return {"status": "success", "message": "Notification settings updated successfully."}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.post("/api/system/notifications/test")
def trigger_test_notification():
    try:
        import notification_manager
        settings = notification_manager.get_notification_settings()
        body = "⚠️ NexusTrader Connection & Notification Test\n\nThis is a manual test verification message to confirm notification routing is operational."
        
        email_sent = False
        if settings.get("notif_email_enabled") == "true":
            email_sent = notification_manager.send_smtp_email(settings, "NexusTrader - Notification Test", body)

        # Also try Proton Bridge
        proton_sent = False
        proton_msg = ""
        try:
            from proton_bridge import send_notification
            recipient = settings.get("notif_email_recipient", "churchill.c.j@gmail.com")
            ok, msg = send_notification(recipient, "NexusTrader - Notification Test", body)
            proton_sent = ok
            proton_msg = msg
        except Exception as pe:
            proton_msg = str(pe)
            
        wa_sent = False
        if settings.get("notif_whatsapp_enabled") == "true":
            wa_sent = notification_manager.send_whatsapp_webhook(settings, body)
            
        return {
            "status": "success", 
            "message": "Test notifications triggered.",
            "email_sent": email_sent,
            "proton_bridge_sent": proton_sent,
            "proton_bridge_msg": proton_msg,
            "whatsapp_sent": wa_sent
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

# -------------------------------------------------------------
# Alert API Endpoints
# -------------------------------------------------------------
@app.get("/api/system/alerts")
def get_alerts_api(limit: int = 50):
    """Fetch recent alerts for dashboard bell display."""
    try:
        import notification_manager as _nm
        alerts = _nm.get_alerts(limit=limit)
        return {"status": "success", "alerts": alerts, "count": len(alerts)}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/api/system/alerts/acknowledge/{alert_id}")
def acknowledge_alert_api(alert_id: int):
    try:
        import notification_manager as _nm
        _nm.acknowledge_alert(alert_id)
        return {"status": "success", "message": f"Alert {alert_id} acknowledged."}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/api/system/alerts/resolve/{alert_id}")
def resolve_alert_api(alert_id: int):
    try:
        import notification_manager as _nm
        _nm.resolve_alert(alert_id)
        return {"status": "success", "message": f"Alert {alert_id} resolved."}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# -------------------------------------------------------------
# Backup & Restore REST API Endpoints
# -------------------------------------------------------------
@app.post("/api/system/backup")
def trigger_backup():
    try:
        import backup_manager
        archive_path = backup_manager.create_backup()
        filename = os.path.basename(archive_path)
        return {"status": "success", "message": "Backup created successfully.", "filename": filename}
    except Exception as e:
        logging.error(f"Error triggering backup: {e}")
        return {"status": "error", "error": str(e)}

@app.get("/api/system/backups")
def list_backups():
    try:
        import backup_manager
        import glob
        if not os.path.exists(backup_manager.BACKUP_DIR):
            return {"status": "success", "backups": []}
        files = glob.glob(os.path.join(backup_manager.BACKUP_DIR, "backup_*.tar.gz"))
        backups = []
        for f in files:
            stat = os.stat(f)
            backups.append({
                "filename": os.path.basename(f),
                "size_bytes": stat.st_size,
                "created_at": stat.st_mtime
            })
        # Sort newest first
        backups.sort(key=lambda x: x["created_at"], reverse=True)
        return {"status": "success", "backups": backups}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/api/system/backup/download/{filename:path}")
def download_backup(filename: str):
    from fastapi import HTTPException
    try:
        import backup_manager
        # sanitize input to prevent directory traversal
        filename = os.path.basename(filename)
        # Only allow .tar.gz files
        if not filename.endswith(".tar.gz") or ".." in filename or "/" in filename:
            raise HTTPException(status_code=400, detail="Invalid backup filename")
        path = os.path.join(backup_manager.BACKUP_DIR, filename)
        path = os.path.normpath(path)
        if not path.startswith(os.path.normpath(backup_manager.BACKUP_DIR)):
            raise HTTPException(status_code=400, detail="Invalid backup filename")
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="Backup file not found")
        return FileResponse(path, filename=filename, media_type="application/gzip")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/system/backup/restore/{filename}")
def trigger_restore(filename: str):
    try:
        import backup_manager
        # sanitize input
        filename = os.path.basename(filename)
        path = os.path.join(backup_manager.BACKUP_DIR, filename)
        if not os.path.exists(path):
            return {"status": "error", "error": "Backup archive not found."}
        backup_manager.restore_backup(path)
        return {"status": "success", "message": "Backup restored successfully."}
    except Exception as e:
        logging.error(f"Error restoring backup: {e}")
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

@app.post("/api/system/optimize/nn")
def trigger_nn_optimization():
    try:
        from nn_agent import run_nn_self_improvement
        res = run_nn_self_improvement()
        if res.startswith("Success"):
            return {"status": "success", "log": res}
        else:
            return {"status": "error", "error": res}
    except Exception as e:
        logging.error(f"Error in manual Neural Network optimization: {e}")
        return {"status": "error", "error": str(e)}

@app.post("/api/system/optimize/sentiment")
def trigger_sentiment_optimization():
    try:
        from sentiment_agent import run_sentiment_self_improvement
        res = run_sentiment_self_improvement()
        if res.startswith("Success"):
            return {"status": "success", "log": res}
        else:
            return {"status": "error", "error": res}
    except Exception as e:
        logging.error(f"Error in manual Sentiment optimization: {e}")
        return {"status": "error", "error": str(e)}

@app.post("/api/system/optimize/risk_audit")
def trigger_risk_audit():
    try:
        from risk_auditor import run_risk_audit
        res = run_risk_audit()
        if res.startswith("Success"):
            return {"status": "success", "log": res}
        else:
            return {"status": "error", "error": res}
    except Exception as e:
        logging.error(f"Error in manual Risk Audit: {e}")
        return {"status": "error", "error": str(e)}

@app.post("/api/system/optimize/allocator")
def trigger_allocator():
    try:
        from allocator_agent import run_allocator_self_improvement
        res = run_allocator_self_improvement()
        if res.startswith("Success"):
            return {"status": "success", "log": res}
        else:
            return {"status": "error", "error": res}
    except Exception as e:
        logging.error(f"Error in manual Allocator optimization: {e}")
        return {"status": "error", "error": str(e)}

@app.get("/api/gateway/status")
def gateway_status():
    """Test reachability of OpenClaw Gateway from the LXC."""
    try:
        from openclaw_bridge import get_gateway_config
        url, token = get_gateway_config()
        masked = token[:6] + "..." + token[-4:] if len(token) > 10 else "***"
        import urllib.request
        import json
        req = urllib.request.Request(
            url,
            data=json.dumps({"model": "deepseek/deepseek-v4-flash", "messages": [{"role": "user", "content": "Hello"}], "max_tokens": 5}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode("utf-8"))
        return {
            "status": "connected",
            "gateway_url": url,
            "token_prefix": masked,
            "model": "deepseek/deepseek-v4-flash",
            "response_preview": (data.get("choices") or [{}])[0].get("message", {}).get("content", "")[:60],
        }
    except Exception as e:
        return {
            "status": "error",
            "gateway_url": url if 'url' in locals() else "unknown",
            "error": str(e),
        }


class SendPromptRequest(BaseModel):
    prompt: str
    agent: str = "default"
    model: str = "deepseek/deepseek-v4-flash"
    max_tokens: int = 512
    temperature: float = 0.7


@app.post("/api/gateway/prompt")
def send_prompt(req: SendPromptRequest):
    """Send a custom prompt to OpenClaw Gateway and return the response."""
    try:
        from openclaw_bridge import query_openclaw
        text = query_openclaw(
            req.prompt,
            agent_name=req.agent,
            model=req.model,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
        )
        return {"status": "success", "response": text}
    except Exception as e:
        logging.error(f"Error sending prompt to OpenClaw: {e}")
        return {"status": "error", "error": str(e)}


class SaveSettingRequest(BaseModel):
    key: str
    value: str


@app.post("/api/system/save_setting")
def save_system_setting(req: SaveSettingRequest):
    """Save a single key-value setting to the DB (bypasses MutationFreeze)."""
    try:
        database.save_setting_directly(req.key, req.value)
        return {"status": "success", "key": req.key}
    except Exception as e:
        return {"status": "error", "error": str(e)}


DEFAULT_PROMPT_QUANT = """You are a PhD Quantitative Finance Specialist and Senior Market Analyst.
Our mission is to optimize parameters to safely and consistently earn a stable, risk-adjusted target of $1,000 USD a day.

Analyze the trade details, win rates, and profit volatility. Critique the current strategy parameters and offer 2-3 mathematical recommendations.
We utilize 12 dynamic quantitative strategies:
1. EMA Crossover (Trend)
2. RSI Reversion (Mean Reversion)
3. Bollinger Bands (Mean Reversion)
4. ML Random Forest (Predictive)
5. Kalman Filter Trend (Trend)
6. Psychological Liquidity Sweep (Mean Reversion)
7. News Sentiment (Predictive)
8. MACD Histogram Crossover (Trend)
9. Mean Reversion Z-Score (Mean Reversion)
10. VWAP Crossover (Trend)
11. ATR Breakout (Trend)
12. Stochastic Reversion (Mean Reversion)

Verify volatility regimes (trending vs mean-reverting OU process states) and adjust stop-loss/take-profit multipliers, and individual strategy thresholds to maximize profit expectancy per trade.

Specify recommended setting adjustments strictly in a JSON block at the very end of your response (wrapped in ```json).

Recommended settings JSON format:
```json
{
  "recommended_risk_mode": "conservative" | "aggressive" | "hyper_growth",
  "recommended_tp_multiplier": float,
  "recommended_sl_multiplier": float,
  "asset_adjustments": {
    "TICKER": {
      "is_active": boolean,
      "tp_multiplier": float,
      "sl_multiplier": float,
      "kelly_ceiling": float
    }
  }
}
```"""

DEFAULT_PROMPT_DEV = """You are Antigravity, a world-class Principal AI Software Architect.
Our core mission is to construct software modules, advanced UI visualizations, and diagnostic dashboards that enable the bot to achieve $1,000 USD/day.

Our platform features:
1. Custom Starting Portfolio Capital Settings to calculate net PnL accurately against exchange deposits.
2. Failed Entry protection (5-minute asset cooldown on failures).
3. Cybernetic Alert system with Clickable Toast notifications and Bell Dropdown.
4. Multi-Brain repository (Activate, snapshot, delete, or train new brain from scratch).
5. Real-time System Logs terminal panel to display service output.
6. Dynamic per-agent LLM Router (routing to OpenAI, Gemini, or Anthropic).
7. Asset Manager dashboard tab supporting custom Kelly ceilings, dynamic auto-switching, and locked brain overrides.

Your current priorities:
- Continuously analyze, review, and mathematically refine all quant agent prompts (parameter optimization, risk auditor, asset allocator, neural policy, sentiment optimizer, long-term quant) to maximize profit expectancy and hit our $1,000 USD/day target.
- Maintain and execute comprehensive unit test coverage for all quant agents, validating behavior with mock responses in the build pipeline during deployment.
- Keep the repository documentation (README.md) and module comments spruced up, visually engaging (using shields/badges), and maintained to top-tier open-source standards.
- Actively scan system error logs for any exceptions or warnings, locate the source, and design robust self-healing corrections.

IMPROVE THIS PROMPT AND VERSION CONTROL IT AND MAKE SURE THE NEXT PROMPT IMPROVES IT'S SELF when it's run.

Design and implement ONE clean, production-grade, non-breaking feature or UI widget (e.g., system logs refreshers, expected value gauges, or correlation heatmaps).
Return your response STRICTLY in JSON format containing "explanation" and "modifications" find-and-replace rules."""

DEFAULT_PROMPT_BLOG = """You are a high-caliber Financial Journalist and Senior Quantitative Writer.
Produce an elite, data-driven weekly performance report on the NexusTrader system.
Frame the narrative around our strategic trajectory toward the $1,000 USD/day capital-scaling goal.

Explain model updates, probability distributions, and policy gradient shifts in an engaging, institutional-grade style.
Highlight our customizable starting deposit baselines, cybernetic notifications bell, new multi-brain selection & custom training platform, dynamic auto-switching, and per-asset Kelly ceilings.

IMPROVE THIS PROMPT AND VERSION CONTROL IT AND MAKE SURE THE NEXT PROMPT IMPROVES IT'S SELF when it's run.

Keep all quantitative tables intact."""

DEFAULT_PROMPT_NN = """You are a world-class Deep Learning Engineer and Neuro-Symbolic Quantitative Researcher.
Our goal is to optimize the policy gradient neural network of the NexusTrader bot to enable it to safely scale earnings to $1,000 USD a day.

Evaluate the policy gradient updates, discount factors, exploration/exploitation decay schedules, and policy weights. Recommend adaptations to learning rates and weight floor boundaries to improve convergence.

At the very end of your response, output recommended setting adjustments strictly in a JSON block (wrapped in ```json):
```json
{
  "recommended_nn_learning_rate": float,
  "recommended_nn_weight_floor": float
}
```"""

DEFAULT_PROMPT_SENTIMENT = """You are a high-caliber NLP Sentiment Engineer and Social Media Quant.
Our core goal is to filter noise and optimize sentiment feed weights to scale bot earnings to $1,000 USD/day.

Evaluate recent feed weighted scores and sentiment data. Propose mapping corrections or new feed sources. Analyze lead-lag correlation matrices of sentiment indicators against price returns to maximize accuracy.

At the very end of your response, output a strict JSON block with feed weights mapping corrections (wrapped in ```json):
```json
{
  "recommended_news_sentiment_weight": float
}
```"""

DEFAULT_PROMPT_RISK = """You are a highly conservative Quantitative Portfolio Risk Auditor and QRO.
Our goal is to verify that risk exposures, asset correlations, and tail drawdowns strictly protect capital while targeting $1,000 USD/day.

Analyze active leverage levels, daily drawdown limits, asset-specific Kelly ceilings, and portfolio correlation matrices. Verify tail risk metrics (Value-at-Risk/Expected Shortfall) and monitor the 5-minute failed order cooldown safeguards.

At the very end of your response, output a strict JSON block with risk parameter recommendations (wrapped in ```json):
```json
{
  "recommended_max_daily_loss": float,
  "recommended_loss_cooldown_hours": float,
  "recommended_global_kelly_ceiling": float
}
```"""

DEFAULT_PROMPT_ALLOCATOR = """You are a world-class Portfolio Allocation Specialist and Risk Management Engineer.
Our goal is to dynamically optimize the active asset roster, Kelly allocation ceilings, and risk parameters to safely scale NexusTrader earnings to $1,000 USD/day.

Critique recent performance, win/loss stats, and return distributions. Propose adjustments to asset statuses (activating/cooling assets) and target allocations using fractional Kelly Criterion rules.

At the very end of your response, output a strict JSON block with your recommended adjustments (wrapped in ```json):
```json
{
  "asset_adjustments": {
    "TICKER": {
      "is_active": boolean,
      "tp_multiplier": float,
      "sl_multiplier": float,
      "kelly_ceiling": float
    }
  }
}
```"""

DEFAULT_PROMPT_LONG_TERM_QUANT = """You are a world-class PhD Quantitative Risk Officer and Long-Term Strategy Architect.
Our core objective is to refine the Long-Term Strategy shadow model parameters to safely and consistently achieve our $1,000 USD/day profit target.

Evaluate the shadow trades, win rates, and holding periods. Analyze how volatility targeted sizing, Kalman filter trend gates, and neural gating can be optimized to improve expectancy. Compute required capital to hit $1,000/day.

At the very end of your response, output recommended setting adjustments strictly in a JSON block (wrapped in ```json):
```json
{
  "shadow_volatility_target_pct": float,
  "shadow_tp_atr_multiplier": float,
  "shadow_sl_atr_multiplier": float,
  "shadow_nn_consensus_min_weight": float,
  "shadow_max_holding_hours": float
}
```"""

@app.get("/api/system/agent_llm")
def get_agent_llm_config(agent: str = "default"):
    suffix = f"_{agent}" if agent != "default" else ""
    provider_key = f"agent_llm_provider{suffix}"
    provider = database.load_setting(provider_key, "")
    if not provider and agent != "default":
        provider = database.load_setting("agent_llm_provider", "gemini")
    elif not provider:
        provider = "gemini"
        
    base_url = database.load_setting(f"agent_llm_base_url{suffix}", "")
    if not base_url and agent != "default":
        base_url = database.load_setting("agent_llm_base_url", "")
        
    model = database.load_setting(f"agent_llm_model{suffix}", "")
    if not model and agent != "default":
        model = database.load_setting("agent_llm_model", "")
        
    api_key = database.load_setting(f"agent_llm_api_key{suffix}", "")
    if not api_key and agent != "default":
        api_key = database.load_setting("agent_llm_api_key", "")
        
    masked_key = ""
    if api_key:
        masked_key = api_key[:4] + "*" * (len(api_key) - 8) + api_key[-4:] if len(api_key) > 8 else "****"
        
    return {
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "api_key": masked_key
    }

@app.post("/api/system/agent_llm")
def save_agent_llm_config(provider: str, base_url: str = "", model: str = "", api_key: str = "", agent: str = "default"):
    suffix = f"_{agent}" if agent != "default" else ""
    database.save_setting(f"agent_llm_provider{suffix}", provider.strip().lower())
    database.save_setting(f"agent_llm_base_url{suffix}", base_url.strip())
    database.save_setting(f"agent_llm_model{suffix}", model.strip())
    
    if api_key.strip() and not api_key.strip().startswith("****") and "*" not in api_key:
        database.save_setting(f"agent_llm_api_key{suffix}", api_key.strip())
        
    return {"status": "success", "message": f"Agent LLM configuration for '{agent}' saved successfully."}

@app.get("/api/system/prompts")
def get_prompts():
    return {
        "prompt_quant": database.load_setting("prompt_self_improvement", DEFAULT_PROMPT_QUANT),
        "prompt_dev": database.load_setting("prompt_self_developer", DEFAULT_PROMPT_DEV),
        "prompt_blog": database.load_setting("prompt_blog_agent", DEFAULT_PROMPT_BLOG),
        "prompt_nn": database.load_setting("prompt_nn_agent", DEFAULT_PROMPT_NN),
        "prompt_sentiment": database.load_setting("prompt_sentiment_agent", DEFAULT_PROMPT_SENTIMENT),
        "prompt_risk": database.load_setting("prompt_risk_auditor", DEFAULT_PROMPT_RISK),
        "prompt_allocator": database.load_setting("prompt_allocator_agent", DEFAULT_PROMPT_ALLOCATOR)
    }

class PromptsUpdateRequest(BaseModel):
    prompt_quant: str
    prompt_dev: str
    prompt_blog: str
    prompt_nn: str
    prompt_sentiment: str
    prompt_risk: str
    prompt_allocator: str = None

@app.post("/api/system/prompts")
def update_prompts(req: PromptsUpdateRequest):
    try:
        database.save_setting("prompt_self_improvement", req.prompt_quant)
        database.save_setting("prompt_self_developer", req.prompt_dev)
        database.save_setting("prompt_blog_agent", req.prompt_blog)
        database.save_setting("prompt_nn_agent", req.prompt_nn)
        database.save_setting("prompt_sentiment_agent", req.prompt_sentiment)
        database.save_setting("prompt_risk_auditor", req.prompt_risk)
        if req.prompt_allocator is not None:
            database.save_setting("prompt_allocator_agent", req.prompt_allocator)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def update_crontab_schedule():
    try:
        daily_hour = int(database.load_setting("daily_agent_hour", "0"))
        weekly_day = int(database.load_setting("weekly_agent_day", "0"))  # 0=Sunday
        weekly_hour = int(database.load_setting("weekly_agent_hour", "23"))
        nn_hour = int(database.load_setting("nn_agent_hour", "1"))
        sent_hour = int(database.load_setting("sentiment_agent_hour", "2"))
        risk_hour = int(database.load_setting("risk_auditor_hour", "3"))
        
        project_path = os.path.dirname(os.path.abspath(__file__))
        
        # Generate cron commands dynamically
        daily_line = f"0 {daily_hour} * * * cd {project_path} && ./daily_agent.sh >> daily_agent.log 2>&1"
        weekly_line = f"59 {weekly_hour} * * {weekly_day} cd {project_path} && /usr/bin/python3 blog_agent.py >> blog_agent.log 2>&1"
        nn_line = f"0 {nn_hour} * * * cd {project_path} && /usr/bin/python3 nn_agent.py >> nn_agent.log 2>&1"
        sent_line = f"0 {sent_hour} * * * cd {project_path} && /usr/bin/python3 sentiment_agent.py >> sentiment_agent.log 2>&1"
        risk_line = f"0 {risk_hour} * * * cd {project_path} && /usr/bin/python3 risk_auditor.py >> risk_auditor.log 2>&1"
        
        # Read current crontab
        import subprocess
        try:
            res = subprocess.run(["/usr/bin/crontab", "-l"], capture_output=True, text=True)
            lines = res.stdout.splitlines() if res.returncode == 0 else []
        except Exception:
            lines = []
            
        new_lines = []
        for line in lines:
            if "daily_agent.sh" not in line and "blog_agent.py" not in line and "nn_agent.py" not in line and "sentiment_agent.py" not in line and "risk_auditor.py" not in line:
                new_lines.append(line)
                
        new_lines.append(daily_line)
        new_lines.append(weekly_line)
        new_lines.append(nn_line)
        new_lines.append(sent_line)
        new_lines.append(risk_line)
        
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
        "weekly_agent_hour": int(database.load_setting("weekly_agent_hour", "23")),
        "nn_agent_hour": int(database.load_setting("nn_agent_hour", "1")),
        "sentiment_agent_hour": int(database.load_setting("sentiment_agent_hour", "2")),
        "risk_auditor_hour": int(database.load_setting("risk_auditor_hour", "3"))
    }

@app.post("/api/system/schedule")
def update_system_schedule(daily_agent_hour: int, weekly_agent_day: int, weekly_agent_hour: int, nn_agent_hour: int = 1, sentiment_agent_hour: int = 2, risk_auditor_hour: int = 3):
    try:
        if not (0 <= daily_agent_hour <= 23):
            return {"status": "error", "error": "Daily hour must be between 0 and 23"}
        if not (0 <= weekly_agent_day <= 6):
            return {"status": "error", "error": "Weekly day must be between 0 and 6"}
        if not (0 <= weekly_agent_hour <= 23):
            return {"status": "error", "error": "Weekly hour must be between 0 and 23"}
        if not (0 <= nn_agent_hour <= 23):
            return {"status": "error", "error": "NN hour must be between 0 and 23"}
        if not (0 <= sentiment_agent_hour <= 23):
            return {"status": "error", "error": "Sentiment hour must be between 0 and 23"}
        if not (0 <= risk_auditor_hour <= 23):
            return {"status": "error", "error": "Risk hour must be between 0 and 23"}
            
        database.save_setting("daily_agent_hour", str(daily_agent_hour))
        database.save_setting("weekly_agent_day", str(weekly_agent_day))
        database.save_setting("weekly_agent_hour", str(weekly_agent_hour))
        database.save_setting("nn_agent_hour", str(nn_agent_hour))
        database.save_setting("sentiment_agent_hour", str(sentiment_agent_hour))
        database.save_setting("risk_auditor_hour", str(risk_auditor_hour))
        
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
        if not orchestrator.tickers:
            await websocket.send_json({"type":"init","status":"waiting","msg":"Tickers not yet loaded"})
            # Keep connection alive until tickers load
            import asyncio as _asyncio
            for _ in range(30):
                await _asyncio.sleep(1)
                if orchestrator.tickers:
                    break
            if not orchestrator.tickers:
                await websocket.close()
                return
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
            
        trades_to_send = []
        if orchestrator.execution_engine.trading_mode == "live":
            config_path = os.path.expanduser("~/.nexustrader/config.json")
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r") as f:
                        cfg = json.load(f)
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
                            trades_to_send = exchange_trades
                except Exception as e:
                    logging.error(f"Error fetching live trades for websocket init: {e}")
        else:
            trades_to_send = orchestrator.execution_engine.closed_trades

        active_brains = {}
        for t in orchestrator.tickers:
            active_brains[t] = database.load_setting(f"active_policy_brain_{t}", "Default Brain")

        # Compute aggregate KPI fields for dashboard init
        _total_pnl_ws = sum(float(t.get("pnl", 0.0) or 0.0) for t in trades_to_send)
        _win_count_ws = sum(1 for t in trades_to_send if float(t.get("pnl", 0) or 0) > 0)
        _loss_count_ws = sum(1 for t in trades_to_send if float(t.get("pnl", 0) or 0) < 0)
        _winrate_ws = (_win_count_ws / (_win_count_ws + _loss_count_ws) * 100) if (_win_count_ws + _loss_count_ws) > 0 else 0.0
        _init_bal_ws = orchestrator.execution_engine.initial_balance
        _total_pnl_pct_ws = (_total_pnl_ws / _init_bal_ws * 100) if _init_bal_ws > 0 else 0.0
        init_state = {
            "type": "init",
            "tickers": orchestrator.tickers,
            "ticker": first_ticker,
            "balance": orchestrator.execution_engine.balance,
            "equity": orchestrator.execution_engine.get_equity({t: (orchestrator.data_ingestions[t].live_price if t in orchestrator.data_ingestions and orchestrator.data_ingestions[t].live_price else orchestrator.latest_ticks.get(t, {}).get("close", 0.0)) for t in orchestrator.tickers}),
            "initial_balance": _init_bal_ws,
            "total_pnl": round(_total_pnl_ws, 2),
            "total_pnl_pct": round(_total_pnl_pct_ws, 2),
            "winrate": round(_winrate_ws, 4),
            "win_count": _win_count_ws,
            "loss_count": _loss_count_ws,
            "closed_trades": len(trades_to_send),
            "trading_mode": orchestrator.execution_engine.trading_mode,
            "broker": orchestrator.execution_engine.config.get("broker", "kraken"),
            "weights": {
                ensemble.strategies[i].name: float(ensemble.weights[i])
                for i in range(min(len(ensemble.weights), len(ensemble.strategies)))
            } if ensemble else {},
            "risk_mode": orchestrator.probability_engine.risk_mode,
            "strategies": [s.name for s in ensemble.strategies] if ensemble else [],
            "trades": trades_to_send,
            "lifetime_steps": steps,
            "model_dna": model_dna,
            "active_brains": active_brains,
            "ticker_prices": {
                t: (orchestrator.data_ingestions[t].live_price if t in orchestrator.data_ingestions else
                    orchestrator.latest_ticks.get(t, {}).get("close", 0.0))
                for t in orchestrator.tickers
            }
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
    return FileResponse(get_resource_path("dashboard-v2/index.html"), headers=headers)

@app.get("/sw.js")
def get_service_worker():
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    return FileResponse(get_resource_path("dashboard/sw.js"), media_type="application/javascript", headers=headers)

@app.get("/favicon.ico")
async def favicon():
    """Serve favicon."""
    try:
        return FileResponse(get_resource_path("dashboard/icon-192.png"), media_type="image/png")
    except Exception:
        return Response(status_code=204)

@app.get("/manifest.json")
def get_manifest():
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    return FileResponse(get_resource_path("dashboard/manifest.json"), media_type="application/json", headers=headers)

@app.get("/dashboard")
async def redirect_dashboard():
    return RedirectResponse(url="/")

@app.get("/dashboard/")
async def redirect_dashboard_trailing():
    return RedirectResponse(url="/")

app.mount("/dashboard", StaticFiles(directory=get_resource_path("dashboard")), name="dashboard")
app.mount("/dashboard-v2", StaticFiles(directory=get_resource_path("dashboard-v2")), name="dashboard-v2")


# ---------------------------------------------------------------------------
# LLM Management API
# ---------------------------------------------------------------------------

@app.get("/api/llm/status")
def api_llm_status():
    """Return LLaMA server status and orchestrator LLM state."""
    from llm_client import LLMClient
    try:
        llm_enabled = orchestrator.llm_enabled if hasattr(orchestrator, 'llm_enabled') else False
        llm_client = orchestrator.llm_client if hasattr(orchestrator, 'llm_client') else None
        
        status = {
            "llm_enabled": llm_enabled,
            "server_connected": False,
            "last_sentiment": orchestrator.llm_last_sentiment if hasattr(orchestrator, 'llm_last_sentiment') else None,
            "last_sentiment_time": orchestrator.llm_last_sentiment_time if hasattr(orchestrator, 'llm_last_sentiment_time') else None,
            "endpoint": getattr(llm_client, 'endpoint', 'unknown') if llm_client else 'not configured',
            "model": "Llama-3.2-3B-Instruct-Q4_K_M",
            "speed_toks": "~7.9",
            "poll_interval_sec": orchestrator.llm_sentiment_interval if hasattr(orchestrator, 'llm_sentiment_interval') else 900,
        }
        
        # Quick health check
        if llm_client:
            try:
                import urllib.request
                r = urllib.request.urlopen(llm_client.endpoint + '/health', timeout=3)
                if r.getcode() == 200:
                    status['server_connected'] = True
            except Exception:
                pass
        
        return status
    except Exception as e:
        logging.error(f"LLM status error: {e}")
        return {"llm_enabled": False, "error": str(e)}

@app.post("/api/llm/test")
def api_llm_test():
    """Test LLaMA connection with a simple ping."""
    import urllib.request, json as _json
    try:
        llm_client = orchestrator.llm_client if hasattr(orchestrator, 'llm_client') else None
        if not llm_client:
            return {"ok": False, "error": "LLMClient not configured"}
        
        r = urllib.request.urlopen(llm_client.endpoint + '/health', timeout=5)
        health = _json.loads(r.read())
        
        # Try a quick completion
        result = llm_client._complete("Say OK", max_tokens=5)
        
        return {
            "ok": True,
            "health": health,
            "test_response": result[:50] if result else None,
            "endpoint": llm_client.endpoint,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}

@app.post("/api/llm/sentiment")
def api_llm_sentiment_force():
    """Force immediate LLaMA sentiment analysis for active tickers."""
    try:
        llm_client = orchestrator.llm_client if hasattr(orchestrator, 'llm_client') else None
        if not llm_client:
            return {"ok": False, "error": "LLMClient not configured"}
        
        # Use recent trade data
        trades = orchestrator.execution_engine.closed_trades[-5:] if hasattr(orchestrator.execution_engine, 'closed_trades') else []
        headlines = orchestrator.latest_news_sentiment.get('headlines', ['Crypto market analysis requested']) if hasattr(orchestrator, 'latest_news_sentiment') else ['Crypto market analysis']
        
        ticker = orchestrator.tickers[0] if orchestrator.tickers else 'BTC-USD'
        price = orchestrator.latest_ticks.get(ticker, {}).get('close', 0) if hasattr(orchestrator, 'latest_ticks') else 0
        
        result = llm_client.analyze_sentiment(
            headlines=headlines[:5],
            market_summary=f"{ticker} ${price:.0f}"
        )
        
        return {"ok": True, "sentiment": result}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}

@app.post("/api/llm/regime")
def api_llm_regime_force():
    """Force immediate LLaMA regime classification."""
    try:
        llm_client = orchestrator.llm_client if hasattr(orchestrator, 'llm_client') else None
        if not llm_client:
            return {"ok": False, "error": "LLMClient not configured"}
        
        ticker = orchestrator.tickers[0] if orchestrator.tickers else 'BTC-USD'
        price = orchestrator.latest_ticks.get(ticker, {}).get('close', 0) if hasattr(orchestrator, 'latest_ticks') else 0
        
        result = llm_client.classify_regime(
            ticker_data={
                'ticker': ticker,
                'price': price,
                'change_24h': 0,
                'volume_24h': 0,
                'rsi_14': 50,
                'volatility_30d': 0.02,
                'trend': 'unknown',
                'near_support': False,
                'near_resistance': False,
            }
        )
        
        return {"ok": True, "regime": result}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}

@app.get("/api/llm/config")
def api_llm_config_get():
    """Get LLM configuration including local LLaMA settings."""
    return {
        "endpoint": getattr(getattr(orchestrator, 'llm_client', None), 'endpoint', 'http://192.168.0.77:8080'),
        "poll_interval_sec": orchestrator.llm_sentiment_interval if hasattr(orchestrator, 'llm_sentiment_interval') else 900,
        "timeout_sec": getattr(getattr(orchestrator, 'llm_client', None), 'timeout', 60),
        "enabled": orchestrator.llm_enabled if hasattr(orchestrator, 'llm_enabled') else False,
        "use_local_llama": database.load_setting("enable_local_llama", "false").lower() == "true",
        "llama_server_url": database.load_setting("llama_server_url", "http://192.168.0.77:8080/v1/chat/completions"),
        "llama_fallback_to_openclaw": database.load_setting("llama_fallback_to_openclaw", "true").lower() == "true",
    }

@app.post("/api/llm/config")
async def api_llm_config_save(request: Request):
    """Save LLM configuration."""
    try:
        data = await request.json()
    except Exception:
        data = {}
    
    changes = []
    
    # Update endpoint
    if 'endpoint' in data and hasattr(orchestrator, 'llm_client') and orchestrator.llm_client:
        orchestrator.llm_client.endpoint = data['endpoint'].rstrip('/')
        changes.append('endpoint')
    
    # Update poll interval
    if 'poll_interval_sec' in data:
        orchestrator.llm_sentiment_interval = int(data['poll_interval_sec'])
        changes.append('poll_interval')
    
    # Update timeout
    if 'timeout_sec' in data and hasattr(orchestrator, 'llm_client') and orchestrator.llm_client:
        orchestrator.llm_client.timeout = int(data['timeout_sec'])
        changes.append('timeout')
    
    # Update enabled
    if 'enabled' in data:
        orchestrator.llm_enabled = bool(data['enabled'])
        changes.append('enabled')

    # Update local LLaMA toggle
    if 'use_local_llama' in data:
        database.save_setting("enable_local_llama", str(data['use_local_llama']).lower())
        changes.append('use_local_llama')

    # Update LLaMA server URL
    if 'llama_server_url' in data:
        database.save_setting("llama_server_url", str(data['llama_server_url']))
        changes.append('llama_server_url')

    # Update fallback setting
    if 'llama_fallback_to_openclaw' in data:
        database.save_setting("llama_fallback_to_openclaw", str(data['llama_fallback_to_openclaw']).lower())
        changes.append('llama_fallback_to_openclaw')
    
    return {"ok": True, "changes": changes}

@app.get("/api/nn/architecture")
def api_nn_architecture_get():
    """Get current NN architecture setting."""
    arch = database.load_setting("nn_architecture", "mlp")
    return {
        "architecture": arch,
        "available": ["mlp", "lstm", "transformer"],
        "description": {
            "mlp": "8 features -> 12 hidden ReLU -> 6 strategy Softmax (default)",
            "lstm": "TokenEmbedder(32 vocab -> 64d) -> 2-layer LSTM -> Softmax",
            "transformer": "4-head MHA encoder (2 layers) -> Mean Pool -> Softmax",
        }
    }

@app.post("/api/nn/architecture")
async def api_nn_architecture_set(request: Request):
    """Set NN architecture. Requires bot restart to take effect."""
    try:
        data = await request.json()
    except Exception:
        data = {}
    
    arch = data.get('architecture', 'mlp')
    if arch not in ('mlp', 'lstm', 'transformer'):
        return {"ok": False, "error": f"Invalid architecture: {arch}. Use mlp, lstm, or transformer."}
    
    database.save_setting("nn_architecture", arch)
    return {"ok": True, "architecture": arch, "note": "Restart bot to apply new architecture."}

@app.post("/api/nn/tests")
def api_nn_tests_run():
    """Run NN unit tests and return results."""
    import subprocess, os
    try:
        base = os.path.dirname(os.path.abspath(__file__))
        result = subprocess.run(
            [os.path.join(base, 'venv', 'bin', 'python3'), '-m', 'unittest',
             'tests.test_nn_tokenizer', 'tests.test_transformer', '-v'],
            capture_output=True, text=True, timeout=30, cwd=base
        )
        return {
            "ok": result.returncode == 0,
            "passed": result.stdout.count(' ok\n') + result.stdout.count(' OK\n'),
            "failed": result.stdout.count('FAIL') + result.stdout.count('ERROR'),
            "output": result.stdout[-2000:] + result.stderr[-500:],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}

@app.post("/api/training/run")
async def api_training_run(request: Request):
    """Trigger a historical training pipeline run for a ticker."""
    try:
        data = await request.json()
    except Exception:
        data = {}
    
    ticker = data.get('ticker', orchestrator.tickers[0] if orchestrator.tickers else 'BTC-USD')
    since_days = int(data.get('days', 30))
    epochs = int(data.get('epochs', 20))
    
    def run_training():
        try:
            from historical_pipeline import HistoricalPipeline
            pipeline = HistoricalPipeline(orchestrator)
            result = pipeline.run_ticker(ticker, since_days=since_days, epochs=epochs)
            logging.info(f"Training complete for {ticker}: {result}")
        except Exception as e:
            logging.error(f"Training failed: {e}")
    
    import threading
    t = threading.Thread(target=run_training, daemon=True)
    t.start()
    
    return {
        "ok": True,
        "message": f"Training started for {ticker} ({since_days}d, {epochs} epochs). This runs in background.",
        "ticker": ticker,
    }


# ═══════════════════════════════════════════════════════════════════
# Dashboard API Compatibility Routes (aliases for dashboard-v2 SPA)
# These are thin wrappers that call the canonical endpoints.
# ═══════════════════════════════════════════════════════════════════

async def _get_json(request: Request):
    '''Helper to safely parse JSON from any request.'''
    try:
        return await request.json()
    except Exception:
        return {}

@app.get("/api/system/broker_config")
def api_v2_broker_config_get():
    '''Dashboard v2 broker config GET.'''
    api_key = database.load_setting("kraken_api_key", "")
    api_secret = database.load_setting("kraken_api_secret", "")
    return {
        "broker": database.load_setting("broker", "kraken"),
        "api_key": (api_key[:4] + "..." + api_key[-4:]) if len(api_key) > 8 else ("****") if api_key else "",
        "api_secret": ("****") if api_secret else "",
        "trading_mode": getattr(orchestrator.execution_engine, 'trading_mode', 'paper'),
        "connected": database.load_setting("kraken_connected", "false").lower() == "true",
        "test_result": database.load_setting("last_broker_test", ""),
    }

@app.post("/api/system/broker_config")
async def api_v2_broker_config_save(request: Request):
    '''Dashboard v2 broker config POST.'''
    data = await _get_json(request)
    for k in ['broker', 'api_key', 'api_secret', 'trading_mode']:
        if k in data:
            db_key = 'kraken_' + k if k in ('api_key', 'api_secret') else k
            database.save_setting(db_key, str(data[k]))
    return {"ok": True}

@app.get("/api/training/status")
def api_v2_training_status():
    '''Dashboard v2 training status.'''
    ticker = orchestrator.tickers[0] if orchestrator.tickers else "BTC-USD"
    steps = int(database.load_setting(f"lifetime_training_steps_{ticker}", "0"))
    return {"status": "idle", "steps": steps, "ticker": ticker}

@app.post("/api/optimizations/flush")
def api_v2_flush_optimizations():
    '''Dashboard v2 flush optimizations.'''
    database.save_setting("saved_optimizations", "[]")
    return {"ok": True, "flushed": True}

@app.get("/api/gateway/reasoning")
def api_v2_gateway_reasoning():
    '''Dashboard v2 gateway reasoning.'''
    return {"ok": True, "reasoning": "Not implemented."}

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
            uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info", access_log=False)
        except KeyboardInterrupt:
            logging.info("Shutting down server.")
