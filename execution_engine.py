import time
import logging
import json
import os
import database

class ExecutionEngine:
    def __init__(self, initial_balance=100.0, transaction_fee_rate=0.001):
        self.initial_balance = initial_balance
        self.transaction_fee_rate = transaction_fee_rate
        self.active_positions = {}  # symbol -> position dict
        
        # Load configuration settings
        self.config = {}
        home = os.path.expanduser("~")
        data_dir = os.path.join(home, ".nexustrader")
        os.makedirs(data_dir, exist_ok=True)
        config_path = os.path.join(data_dir, "config.json")
        
        if not os.path.exists(config_path):
            default_config = {
                "trading_mode": "paper",
                "broker": "kraken",
                "risk_profile": "conservative",
                "api_credentials": {
                    "api_key": "",
                    "api_secret": ""
                }
            }
            try:
                with open(config_path, "w") as f:
                    json.dump(default_config, f, indent=2)
                logging.info(f"Created default credentials config template at: {config_path}")
            except Exception as e:
                logging.error(f"Error creating default config.json: {e}")
                
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    self.config = json.load(f)
            except Exception as e:
                logging.error(f"Error reading config.json: {e}")
        
        self.trading_mode = self.config.get("trading_mode", "paper")
        logging.info(f"Execution Engine initialized in '{self.trading_mode}' mode.")
        
        # Initialize database and tables
        database.init_db()

        # Load portfolio balance from SQLite if it exists
        db_balance = database.load_setting("portfolio_balance")
        if db_balance is not None:
            self.balance = float(db_balance)
            logging.info(f"Loaded existing portfolio balance from DB: €{self.balance:.2f}")
        else:
            self.balance = initial_balance
            database.save_setting("portfolio_balance", self.balance)
            logging.info(f"Initialized portfolio balance in DB: €{self.balance:.2f}")
            
        # Load closed trades from DB
        self.closed_trades = database.load_trades()
        logging.info(f"Loaded {len(self.closed_trades)} closed trades from DB.")
        
        self.learning_callback = None

    def execute_order_on_broker(self, symbol, side, qty, price):
        """Sends order to live broker API if trading_mode is 'live'."""
        if self.trading_mode != "live":
            logging.info(f"[PAPER TRADING] Simulating order execution: {side.upper()} {qty:.4f} {symbol} @ {price:.2f}")
            return True
            
        # Live broker integration placeholder
        broker_type = self.config.get("broker", "kraken")
        creds = self.config.get("api_credentials", {})
        api_key = creds.get("api_key", "")
        api_secret = creds.get("api_secret", "")
        
        if not api_key or not api_secret:
            logging.error("[LIVE TRADING ERROR] Missing API credentials in config.json. Aborting order execution!")
            return False
            
        logging.info(f"[LIVE TRADING] Sending order to {broker_type.upper()}: {side.upper()} {qty:.4f} {symbol} @ {price:.2f}")
        try:
            # Implementation point for exchange client library (e.g. ccxt or direct broker API)
            # example:
            # import ccxt
            # exchange = getattr(ccxt, broker_type)({'apiKey': api_key, 'secret': api_secret})
            # order = exchange.create_order(symbol, 'market', side, qty)
            # return True
            logging.info(f"[LIVE TRADING SUCCESS] Simulated successful routing to {broker_type.upper()} API.")
            return True
        except Exception as e:
            logging.error(f"[LIVE TRADING EXCEPTION] Failed to place live order: {e}")
            return False

    def set_learning_callback(self, callback):
        """Callback to execute when a trade closes, returning learning results."""
        self.learning_callback = callback

    def open_position(self, symbol, evaluation, strategy_signals):
        """Opens a position based on an evaluation dict from the ProbabilityEngine."""
        if symbol in self.active_positions:
            logging.warning(f"Position already open for {symbol}. Skipping.")
            return False

        direction = evaluation["direction"]
        entry_price = evaluation["entry_price"]
        tp = evaluation["take_profit"]
        sl = evaluation["stop_loss"]
        kelly_fraction = evaluation["kelly_fraction"]

        # Calculate position size in Euros (e.g. 5% of account balance)
        position_value = self.balance * kelly_fraction
        
        # Calculate quantity
        quantity = position_value / entry_price
        
        # Place order on live broker if live mode is enabled
        success = self.execute_order_on_broker(symbol, direction.lower(), quantity, entry_price)
        if not success:
            logging.error(f"Could not execute entry order for {symbol} on live broker. Position aborted.")
            return False
            
        # Calculate transaction fee
        fee = position_value * self.transaction_fee_rate
        self.balance -= fee
        
        # Save updated balance to DB
        database.save_setting("portfolio_balance", self.balance)

        self.active_positions[symbol] = {
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry_price,
            "quantity": quantity,
            "take_profit": tp,
            "stop_loss": sl,
            "entry_time": time.time(),
            "strategy_signals": strategy_signals,  # Keep record of strategy signals at entry
            "fee_paid": fee
        }

        logging.info(f"Opened {direction} position for {symbol}: Qty {quantity:.4f} at {entry_price:.2f}. Fee: {fee:.2f}")
        return True

    def update_positions(self, symbol, current_price):
        """Checks if active positions have hit TP or SL at the current price tick."""
        if symbol not in self.active_positions:
            return None

        pos = self.active_positions[symbol]
        direction = pos["direction"]
        entry_price = pos["entry_price"]
        quantity = pos["quantity"]
        tp = pos["take_profit"]
        sl = pos["stop_loss"]

        close_trade = False
        exit_reason = None
        pnl = 0.0

        if direction == "BUY":
            pnl = (current_price - entry_price) * quantity
            if current_price >= tp:
                close_trade = True
                exit_reason = "Take Profit"
            elif current_price <= sl:
                close_trade = True
                exit_reason = "Stop Loss"
        else: # SELL
            pnl = (entry_price - current_price) * quantity
            if current_price <= tp:
                close_trade = True
                exit_reason = "Take Profit"
            elif current_price >= sl:
                close_trade = True
                exit_reason = "Stop Loss"

        if close_trade:
            # Place exit order on live broker if live mode is enabled
            exit_side = "sell" if direction == "BUY" else "buy"
            success = self.execute_order_on_broker(symbol, exit_side, quantity, current_price)
            if not success:
                logging.error(f"Could not execute exit order for {symbol} on live broker. Keeping position open.")
                return None
                
            # Handle trade closure
            exit_fee = (current_price * quantity) * self.transaction_fee_rate
            pnl_after_fee = pnl - exit_fee
            
            # Update balance
            original_value = quantity * entry_price
            self.balance += (original_value + pnl) - exit_fee
            
            # Save updated balance to DB
            database.save_setting("portfolio_balance", self.balance)
            
            pnl_percent = (pnl_after_fee) / (original_value + 1e-9)

            closed_trade_record = {
                "symbol": symbol,
                "direction": direction,
                "entry_price": entry_price,
                "exit_price": float(current_price),
                "quantity": quantity,
                "pnl": float(pnl_after_fee),
                "pnl_percent": float(pnl_percent),
                "exit_reason": exit_reason,
                "entry_time": pos["entry_time"],
                "exit_time": time.time(),
                "strategy_signals": pos["strategy_signals"]
            }

            # Save trade to DB
            database.save_trade(closed_trade_record)

            self.closed_trades.append(closed_trade_record)
            del self.active_positions[symbol]

            logging.info(f"Closed {direction} position for {symbol} at {current_price:.2f} due to {exit_reason}. PnL: {pnl_after_fee:.2f} ({pnl_percent*100:.2f}%)")

            # Trigger online learning callback
            if self.learning_callback:
                try:
                    self.learning_callback(
                        pos["strategy_signals"],
                        direction,
                        pnl_percent
                    )
                except Exception as e:
                    logging.error(f"Error in learning callback during trade closure: {e}")

            return closed_trade_record

        return None

    def get_equity(self, symbol, current_price):
        """Calculates current total portfolio equity."""
        equity = self.balance
        if symbol in self.active_positions:
            pos = self.active_positions[symbol]
            qty = pos["quantity"]
            entry = pos["entry_price"]
            
            if pos["direction"] == "BUY":
                unrealized = (current_price - entry) * qty
            else:
                unrealized = (entry - current_price) * qty
                
            equity += unrealized
        return float(equity)
