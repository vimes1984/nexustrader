import json
import logging
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
import numpy as np
import pandas as pd
import sys
import os

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

# Central orchestrator state
class NexusTraderOrchestrator:
    def __init__(self, ticker="ETH-EUR"):
        self.ticker = ticker
        self.data_ingestion = DataIngestion(ticker=ticker, interval="1h", period="60d")
        
        # We will initialize strategies and engines once historical data is loaded
        self.strategy_ensemble = None
        self.probability_engine = ProbabilityEngine(kelly_fraction=0.2)
        self.learning_engine = None
        self.execution_engine = ExecutionEngine(initial_balance=100.0)
        
        # State tracking
        self.latest_tick = None
        self.connected_websockets = []
        self.running_task = None
        self.playback_speed = 0.2  # delay in seconds between simulated bars
        self.is_simulating = False
        self.loop = None
        
        # Setup learning callback connection
        self.execution_engine.set_learning_callback(self.on_trade_closed)

    def select_best_ticker(self, candidates):
        """Scans the candidate assets and selects the one with the highest volatility (profit potential)."""
        import yfinance as yf
        best_ticker = "ETH-EUR"
        highest_vol = 0.0
        
        for ticker in candidates:
            try:
                # Fetch last 30 daily bars
                df = yf.download(ticker, period="30d", interval="1d", progress=False)
                if not df.empty:
                    if isinstance(df.columns, pd.MultiIndex):
                        close_series = df['Close'].iloc[:, 0].dropna()
                    else:
                        close_series = df['Close'].dropna()
                        
                    if len(close_series) > 1:
                        close = close_series.values.astype(float)
                        returns = np.diff(close) / (close[:-1] + 1e-9)
                        volatility = np.std(returns)
                        logging.info(f"Scan Ticker: {ticker} | 30-Day Volatility: {volatility*100:.2f}%")
                        if volatility > highest_vol:
                            highest_vol = volatility
                            best_ticker = ticker
            except Exception as e:
                logging.error(f"Error scanning volatility for {ticker}: {e}")
                
        logging.info(f"Dynamic Asset Selector choice: {best_ticker} (Daily standard deviation: {highest_vol*100:.2f}%)")
        return best_ticker

    async def initialize(self):
        """Fetches initial data and trains ML strategies."""
        # Capture the running event loop from the main FastAPI thread
        self.loop = asyncio.get_running_loop()
        
        # 1. Dynamically select the best asset with highest daily volatility (profit potential)
        logging.info("Scanning market for asset with highest daily volatility...")
        candidates = ['ETH-EUR', 'SOL-EUR', 'BTC-EUR', 'DOGE-EUR', 'XRP-EUR']
        try:
            self.ticker = self.select_best_ticker(candidates)
            self.data_ingestion = DataIngestion(ticker=self.ticker, interval="1h", period="60d")
        except Exception as e:
            logging.error(f"Error dynamically selecting asset: {e}. Falling back to default.")
        
        # 2. Fetch initial data
        df = self.data_ingestion.fetch_historical_data()
        
        # 2. Train strategy ensemble
        self.strategy_ensemble = StrategyEnsemble(history_df=df)
        
        # 3. Setup learning engine
        num_strats = len(self.strategy_ensemble.strategies)
        self.learning_engine = LearningEngine(num_strategies=num_strats, learning_rate=0.15)
        
        # Load saved Policy Gradient Neural Network parameters if they exist
        db_net_str = database.load_setting("policy_net_weights")
        if db_net_str:
            try:
                self.learning_engine.policy_net.from_json(db_net_str)
                # Select initial weights based on starting state
                state = self.learning_engine.get_state_vector(
                    df.iloc[-1].to_dict(),
                    list(df['close'].values[-60:]),
                    self.execution_engine.closed_trades
                )
                self.strategy_ensemble.weights = self.learning_engine.select_weights(state)
                logging.info("Loaded Policy Gradient Neural Network weights from database.")
            except Exception as e:
                logging.error(f"Error loading Policy Network weights from DB: {e}")
        else:
            # Fallback to simple equal weights if no DB model is found
            self.strategy_ensemble.weights = np.ones(num_strats) / num_strats

        # Load risk mode from database if it exists
        db_risk_mode = database.load_setting("risk_mode")
        if db_risk_mode:
            try:
                self.probability_engine.set_risk_mode(db_risk_mode)
                logging.info(f"Loaded risk mode from database: {db_risk_mode}")
            except Exception as e:
                logging.error(f"Error loading risk mode from DB: {e}")
        
        logging.info("NexusTrader Orchestrator initialized successfully.")

    def _run_async(self, coro):
        """Safely schedule a coroutine to run on the main FastAPI event loop from any thread."""
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, self.loop)

    def on_trade_closed(self, strategy_signals, direction, pnl_percent):
        """Callback from ExecutionEngine when a trade is closed."""
        logging.info(f"Trade closed with PnL%: {pnl_percent*100:.2f}%. Training Policy Network...")
        
        # Reconstruct the state vector when the trade was evaluated
        state = self.learning_engine.get_state_vector(
            self.latest_tick or {}, 
            self.strategy_ensemble.price_history, 
            self.execution_engine.closed_trades
        )
        
        # Run backpropagation on neural network weights
        new_weights = self.learning_engine.learn_from_trade(
            state,
            strategy_signals,
            direction,
            pnl_percent
        )
        
        # Write back to strategy ensemble
        self.strategy_ensemble.weights = new_weights
        
        # Save updated network parameters to database
        database.save_setting("policy_net_weights", self.learning_engine.policy_net.to_json())
        
        # Push update to WebSocket clients immediately
        self._run_async(self.broadcast_message({
            "type": "learning_update",
            "weights": {
                self.strategy_ensemble.strategies[i].name: new_weights[i]
                for i in range(len(new_weights))
            },
            "pnl": pnl_percent
        }))

    def process_tick(self, row):
        """Orchestrates single price tick logic."""
        self.latest_tick = row
        current_price = float(row['close'])
        atr = row.get('atr', None)
        
        # Save tick to database for future analysis / machine learning training
        database.save_tick(row)
        
        # 1. Query the Policy Gradient Neural Network to allocate base strategy weights
        state = self.learning_engine.get_state_vector(
            row,
            self.strategy_ensemble.price_history,
            self.execution_engine.closed_trades
        )
        base_weights = self.learning_engine.select_weights(state)
        self.strategy_ensemble.weights = base_weights
        
        # 2. Update existing positions (check if TP/SL hit)
        closed_trade = self.execution_engine.update_positions(self.ticker, current_price)
        if closed_trade:
            # Broadcast closed trade
            self._run_async(self.broadcast_message({
                "type": "trade_closed",
                "trade": closed_trade,
                "balance": self.execution_engine.balance,
                "equity": self.execution_engine.get_equity(self.ticker, current_price)
            }))
            
        # 2. If no position is open, check strategy ensemble signals
        pos_open = self.ticker in self.execution_engine.active_positions
        
        weighted_signal, strategy_breakdown = self.strategy_ensemble.get_weighted_signal(row, self.data_ingestion.data)
        
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
                    history_df=self.data_ingestion.data
                )
                
                # If viable, open position
                if evaluation["is_viable"]:
                    # Gather the active signals at entry
                    signals_at_entry = [
                        strat.generate_signal(row)
                        for strat in self.strategy_ensemble.strategies
                    ]
                    
                    opened = self.execution_engine.open_position(
                        self.ticker,
                        evaluation,
                        signals_at_entry
                    )
                    
                    if opened:
                        trade_opened = True
                        self._run_async(self.broadcast_message({
                            "type": "trade_opened",
                            "position": self.execution_engine.active_positions[self.ticker],
                            "balance": self.execution_engine.balance
                        }))

        # 3. Broadcast real-time update to all clients
        self._run_async(self.broadcast_message({
            "type": "tick",
            "price": current_price,
            "timestamp": str(row['timestamp']),
            "weighted_signal": weighted_signal,
            "strategy_breakdown": strategy_breakdown,
            "evaluation": evaluation if not pos_open else None,
            "balance": self.execution_engine.balance,
            "equity": self.execution_engine.get_equity(self.ticker, current_price),
            "position": self.execution_engine.active_positions.get(self.ticker, None),
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
        """Starts real-time live trading feed or simulation playback."""
        if self.is_simulating:
            self.stop_stream()
            
        self.mode = mode
        self.is_simulating = True
        self.data_ingestion.subscribe(self.process_tick)
        
        if mode == "live":
            self.data_ingestion.start_live_stream(interval_seconds=poll_interval)
            logging.info(f"Live real-time polling stream started for {self.ticker}.")
        else:
            self.playback_speed = speed
            self.data_ingestion.start_simulation_stream(
                speed_seconds=speed,
                start_index=150
            )
            logging.info(f"Simulation playback stream started for {self.ticker}.")

    def stop_stream(self):
        self.is_simulating = False
        self.data_ingestion.stop_stream()
        self.data_ingestion.subscribers = []
        logging.info("Stream stopped.")

# Instantiate Orchestrator
orchestrator = NexusTraderOrchestrator()

@app.on_event("startup")
async def startup_event():
    await orchestrator.initialize()
    # Auto-start live stream on startup (true live data)
    orchestrator.start_stream(mode="live", poll_interval=5)

@app.on_event("shutdown")
async def shutdown_event():
    orchestrator.stop_stream()

# API Endpoints
@app.get("/api/status")
def get_status():
    price = orchestrator.data_ingestion.live_price or 0.0
    return {
        "balance": orchestrator.execution_engine.balance,
        "equity": orchestrator.execution_engine.get_equity(orchestrator.ticker, price),
        "position": orchestrator.execution_engine.active_positions.get(orchestrator.ticker, None),
        "ticker": orchestrator.ticker
    }

@app.get("/api/trades")
def get_trades():
    return orchestrator.execution_engine.closed_trades

@app.get("/api/weights")
def get_weights():
    if not orchestrator.strategy_ensemble:
        return {}
    return {
        orchestrator.strategy_ensemble.strategies[i].name: float(orchestrator.strategy_ensemble.weights[i])
        for i in range(len(orchestrator.strategy_ensemble.weights))
    }

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
        orchestrator.execution_engine = ExecutionEngine(initial_balance=100.0)
        orchestrator.execution_engine.set_learning_callback(orchestrator.on_trade_closed)
        # Reset weights to equal
        num_strats = len(orchestrator.strategy_ensemble.strategies)
        orchestrator.strategy_ensemble.weights = [1.0/num_strats] * num_strats
        orchestrator.learning_engine = LearningEngine(num_strategies=num_strats, learning_rate=0.15)
        orchestrator.start_stream(mode=mode, speed=speed, poll_interval=5)
        return {"status": "reset_completed", "mode": mode}
    return {"error": "Invalid action"}

@app.post("/api/config")
def update_config(risk_mode: str):
    if risk_mode in ["conservative", "aggressive", "hyper_growth"]:
        orchestrator.probability_engine.set_risk_mode(risk_mode)
        # Save setting in SQLite DB
        database.save_setting("risk_mode", risk_mode)
        logging.info(f"Risk Profile updated to: {risk_mode}")
        return {"status": "success", "risk_mode": risk_mode}
    return {"error": "Invalid risk mode"}

# Websocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    orchestrator.connected_websockets.append(websocket)
    try:
        # Send initial configuration and state
        init_state = {
            "type": "init",
            "ticker": orchestrator.ticker,
            "balance": orchestrator.execution_engine.balance,
            "weights": {
                orchestrator.strategy_ensemble.strategies[i].name: float(orchestrator.strategy_ensemble.weights[i])
                for i in range(len(orchestrator.strategy_ensemble.weights))
            },
            "risk_mode": orchestrator.probability_engine.risk_mode,
            "strategies": [s.name for s in orchestrator.strategy_ensemble.strategies],
            "trades": orchestrator.execution_engine.closed_trades
        }
        await websocket.send_text(json.dumps(init_state))
        
        while True:
            # Keep connection alive, listen for messages
            data = await websocket.receive_text()
            # Handle client commands if any
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
    return FileResponse(get_resource_path("dashboard/index.html"))

app.mount("/dashboard", StaticFiles(directory=get_resource_path("dashboard")), name="dashboard")

if __name__ == "__main__":
    import sys
    # Check if a graphical display environment is available and headless mode is not requested
    is_headless = "--headless" in sys.argv
    has_display = ("DISPLAY" in os.environ or "WAYLAND_DISPLAY" in os.environ) and not is_headless
    
    if has_display:
        import threading
        import time
        
        # 1. Start uvicorn server in a separate thread
        def run_server():
            logging.info("Starting backend server thread...")
            try:
                # Bind to 0.0.0.0 to support external/forwarded port connections
                uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
            except Exception as e:
                logging.error(f"Uvicorn server crashed: {e}")

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        
        # Wait for uvicorn to boot up
        time.sleep(1.2)
        
        # 2. Start webview GUI loop on the main thread
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
        # Headless server environment: Run uvicorn directly on the main thread
        logging.info("Headless environment detected (no DISPLAY). Running server on main thread...")
        try:
            uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
        except KeyboardInterrupt:
            logging.info("Shutting down server.")
