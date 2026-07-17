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
            logging.info(f"Loaded existing portfolio balance from DB: ${self.balance:.2f}")
        else:
            self.balance = initial_balance
            database.save_setting("portfolio_balance", self.balance)
            logging.info(f"Initialized portfolio balance in DB: ${self.balance:.2f}")
            
        db_init_balance = database.load_setting("initial_portfolio_balance")
        if db_init_balance is not None:
            self.initial_balance = float(db_init_balance)
        else:
            self.initial_balance = self.balance
            database.save_setting("initial_portfolio_balance", str(self.balance))
            
        # Load closed trades from DB
        self.closed_trades = database.load_trades()
        logging.info(f"Loaded {len(self.closed_trades)} closed trades from DB.")
        
        self.learning_callback = None
        self.pending_limit_orders = {}  # symbol -> pending order dict

    def sync_live_balance(self):
        """Syncs the balance with the live broker if trading_mode is 'live'."""
        if self.trading_mode != "live":
            return
            
        broker_type = self.config.get("broker", "kraken").lower()
        creds = self.config.get("api_credentials", {})
        api_key = creds.get("api_key", "")
        api_secret = creds.get("api_secret", "")
        
        if not api_key or not api_secret:
            return
            
        try:
            import ccxt
            exchange_class = getattr(ccxt, broker_type)
            exchange = exchange_class({
                'apiKey': api_key,
                'secret': api_secret,
                'enableRateLimit': True,
            })
            balance_info = exchange.fetch_balance()
            total_bal = balance_info.get('total', {})
            
            # 1. Quote Currency Balance (cash ready to invest)
            usd_cash = float(total_bal.get('USD', total_bal.get('EUR', 0.0)))
            if usd_cash >= 0:
                self.balance = usd_cash
                database.save_setting("portfolio_balance", str(self.balance))
                
            # 2. Total Portfolio Value (USD cash + holdings value)
            total_value_usd = usd_cash
            try:
                # Fetch live rates for conversions
                tickers = exchange.fetch_tickers(['BTC/USD', 'ETH/USD', 'SOL/USD', 'DOGE/USD', 'XRP/USD'])
                prices = {sym.split('/')[0]: float(tick['last']) for sym, tick in tickers.items() if tick.get('last') is not None}
            except Exception as pe:
                logging.error(f"[LIVE VALUE SYNC] Failed to fetch conversion tickers: {pe}")
                prices = {}
                
            for asset, qty in total_bal.items():
                qty = float(qty)
                if qty <= 0 or asset in ['USD', 'EUR']:
                    continue
                if asset in prices:
                    total_value_usd += qty * prices[asset]
                    
            self.live_equity = total_value_usd
            self.live_holdings = {k: float(v) for k, v in total_bal.items() if float(v) > 0.000001}
            self.last_known_prices = prices
            
            # Update initial balance if not set
            db_init_balance = database.load_setting("initial_portfolio_balance")
            if db_init_balance is None or float(db_init_balance) == 100.0:
                self.initial_balance = total_value_usd
                database.save_setting("initial_portfolio_balance", str(total_value_usd))
                logging.info(f"[LIVE BALANCE] Set initial portfolio baseline to: ${total_value_usd:.2f}")
                
            logging.info(f"[LIVE BALANCE SYNC] Cash: ${self.balance:.2f} | Total Value (Equity): ${self.live_equity:.2f}")
        except Exception as e:
            logging.error(f"[LIVE BALANCE SYNC ERROR] Failed to fetch live balance: {e}")

    def execute_order_on_broker(self, symbol, side, qty, price):
        """Sends order to live broker API if trading_mode is 'live'. Returns (success, actual_qty)."""
        if self.trading_mode != "live":
            logging.info(f"[PAPER TRADING] Simulating order execution: {side.upper()} {qty:.4f} {symbol} @ {price:.2f}")
            return True, qty
            
        broker_type = self.config.get("broker", "kraken").lower()
        creds = self.config.get("api_credentials", {})
        api_key = creds.get("api_key", "")
        api_secret = creds.get("api_secret", "")
        
        if not api_key or not api_secret:
            logging.error("[LIVE TRADING ERROR] Missing API credentials in config.json. Aborting order execution!")
            return False, qty
            
        ccxt_symbol = symbol.replace("-", "/")
        logging.info(f"[LIVE TRADING] Preparing order for {broker_type.upper()}: {side.upper()} {qty:.4f} {ccxt_symbol} @ {price:.2f}")
        try:
            import ccxt
            if not hasattr(ccxt, broker_type):
                logging.error(f"[LIVE TRADING ERROR] Broker '{broker_type}' is not supported by ccxt library.")
                return False, qty
                
            exchange_class = getattr(ccxt, broker_type)
            exchange = exchange_class({
                'apiKey': api_key,
                'secret': api_secret,
                'enableRateLimit': True,
            })
            
            # Load markets to obtain asset precisions and limits
            exchange.load_markets()
            
            if ccxt_symbol not in exchange.markets:
                logging.error(f"[LIVE TRADING ERROR] Market symbol '{ccxt_symbol}' not found on exchange {broker_type.upper()}.")
                return False, qty
                
            market = exchange.markets[ccxt_symbol]
            min_amount = market.get('limits', {}).get('amount', {}).get('min', 0.0) or 0.0
            min_cost = market.get('limits', {}).get('cost', {}).get('min', 0.0) or 0.0
            
            # Adjust qty to meet min amount
            adjusted_qty = max(qty, min_amount)
            
            # Adjust qty to meet min cost
            if price > 0:
                cost = adjusted_qty * price
                if cost < min_cost:
                    adjusted_qty = min_cost / price
            
            # Round quantity to exchange precision
            amount = float(exchange.amount_to_precision(ccxt_symbol, adjusted_qty))
            if amount <= 0:
                logging.error(f"[LIVE TRADING ERROR] Calculated execution quantity {amount} rounded to 0. Order aborted.")
                return False, qty
                
            if amount != qty:
                logging.info(f"[LIVE TRADING LIMITS] Adjusted execution quantity from {qty:.6f} to {amount:.6f} to meet exchange limits (Min Amt: {min_amount}, Min Cost: {min_cost})")
                
            # Execute market order on live exchange
            logging.info(f"[LIVE TRADING EXECUTE] Routing market {side.upper()} order for {amount} {ccxt_symbol}...")
            order = exchange.create_order(ccxt_symbol, 'market', side.lower(), amount)
            
            logging.info(f"[LIVE TRADING SUCCESS] Placed order on {broker_type.upper()}: ID={order.get('id')}, Status={order.get('status')}, Filled={order.get('filled')}")
            return True, amount
        except Exception as e:
            logging.error(f"[LIVE TRADING EXCEPTION] Failed to place live order: {e}")
            return False, qty

    def set_learning_callback(self, callback):
        """Callback to execute when a trade closes, returning learning results."""
        self.learning_callback = callback

    def open_position(self, symbol, evaluation, strategy_signals):
        """Opens a position or queues a limit order based on trade viability."""
        # Check Loss Cooldown
        cooldown_end = float(database.load_setting(f"cooldown_end_{symbol}", "0.0"))
        if time.time() < cooldown_end:
            remaining_minutes = int((cooldown_end - time.time()) / 60)
            logging.warning(f"[LOSS COOLDOWN] Ticker {symbol} is in a loss cooldown period. {remaining_minutes} mins remaining. Skipping.")
            return False

        if symbol in self.active_positions or symbol in self.pending_limit_orders:
            logging.warning(f"Position or pending order already exists for {symbol}. Skipping.")
            return False

        direction = evaluation["direction"]
        entry_price = evaluation["entry_price"]
        tp = evaluation["take_profit"]
        sl = evaluation["stop_loss"]
        kelly_fraction = evaluation["kelly_fraction"]

        # Calculate position size in Euros
        position_value = self.balance * kelly_fraction
        quantity = position_value / entry_price
        fee = position_value * self.transaction_fee_rate

        if self.trading_mode == "live":
            # For live trading, execute immediately on the broker API
            success, actual_qty = self.execute_order_on_broker(symbol, direction.lower(), quantity, entry_price)
            if not success:
                logging.error(f"Could not execute entry order for {symbol} on live broker. Position aborted. Placing on temporary 5-minute retry cooldown.")
                # Set a 5-minute retry cooldown to prevent tight infinite loop API spamming
                database.save_setting(f"cooldown_end_{symbol}", str(time.time() + 300))
                return False
                
            self.balance -= fee
            database.save_setting("portfolio_balance", self.balance)
            
            self.active_positions[symbol] = {
                "symbol": symbol,
                "direction": direction,
                "entry_price": entry_price,
                "quantity": actual_qty,
                "take_profit": tp,
                "stop_loss": sl,
                "entry_time": time.time(),
                "strategy_signals": strategy_signals,
                "sentiment_sources": evaluation.get("sentiment_sources", {}),
                "fee_paid": fee
            }
            logging.info(f"Opened live {direction} position for {symbol}: Qty {actual_qty:.6f} at {entry_price:.2f}. Fee: {fee:.2f}")
            return True
        else:
            # For paper trading, place a simulated limit order
            self.pending_limit_orders[symbol] = {
                "symbol": symbol,
                "direction": direction,
                "limit_price": entry_price,
                "quantity": quantity,
                "take_profit": tp,
                "stop_loss": sl,
                "entry_time": time.time(),
                "strategy_signals": strategy_signals,
                "sentiment_sources": evaluation.get("sentiment_sources", {}),
                "fee": fee
            }
            logging.info(f"[LIMIT ORDER PLACED] Placed pending limit {direction} order for {symbol} at {entry_price:.2f}")
            return True

    def update_positions(self, symbol, current_price):
        """Checks pending limit orders for fills and active positions for TP/SL hits."""
        # 1. Evaluate pending limit orders for this symbol (fill check)
        if symbol in self.pending_limit_orders:
            order = self.pending_limit_orders[symbol]
            direction = order["direction"]
            limit_price = order["limit_price"]
            
            fill_order = False
            if direction == "BUY" and current_price <= limit_price:
                fill_order = True
            elif direction == "SELL" and current_price >= limit_price:
                fill_order = True
                
            if fill_order:
                # Deduct fee and open active position
                self.balance -= order["fee"]
                database.save_setting("portfolio_balance", self.balance)
                
                pos = {
                    "symbol": symbol,
                    "direction": direction,
                    "entry_price": limit_price,
                    "quantity": order["quantity"],
                    "take_profit": order["take_profit"],
                    "stop_loss": order["stop_loss"],
                    "entry_time": time.time(),
                    "strategy_signals": order["strategy_signals"],
                    "sentiment_sources": order.get("sentiment_sources", {}),
                    "fee_paid": order["fee"]
                }
                self.active_positions[symbol] = pos
                logging.info(f"[LIMIT ORDER FILLED] Filled pending limit {direction} order for {symbol} at {limit_price:.2f}. Fee: {order['fee']:.2f}")
                del self.pending_limit_orders[symbol]
                
                return {"event": "filled", "data": pos}
                
        # 2. Evaluate active positions for this symbol (TP/SL check)
        if symbol not in self.active_positions:
            return None

        pos = self.active_positions[symbol]
        direction = pos["direction"]
        entry_price = pos["entry_price"]
        quantity = pos["quantity"]
        tp = pos["take_profit"]
        sl = pos["stop_loss"]

        # Trailing Stop-Loss logic
        trailing_stop_enabled = database.load_setting("trailing_stop_enabled", "false") == "true"
        if trailing_stop_enabled:
            if direction == "BUY":
                if "original_sl" not in pos:
                    pos["original_sl"] = sl
                    pos["trail_offset"] = entry_price - sl
                
                new_sl = current_price - pos["trail_offset"]
                if new_sl > sl:
                    sl = new_sl
                    pos["stop_loss"] = new_sl
                    logging.info(f"[TRAILING STOP-LOSS] Trailed stop-loss for {symbol} upward to {new_sl:.4f}")
            else: # SELL
                if "original_sl" not in pos:
                    pos["original_sl"] = sl
                    pos["trail_offset"] = sl - entry_price
                
                new_sl = current_price + pos["trail_offset"]
                if new_sl < sl:
                    sl = new_sl
                    pos["stop_loss"] = new_sl
                    logging.info(f"[TRAILING STOP-LOSS] Trailed stop-loss for {symbol} downward to {new_sl:.4f}")

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
            
            # Trigger Loss Cooldown if PnL is negative
            if pnl_after_fee < 0:
                cooldown_hours = float(database.load_setting("loss_cooldown_hours", "4.0"))
                if cooldown_hours > 0:
                    cooldown_end = time.time() + (cooldown_hours * 3600)
                    database.save_setting(f"cooldown_end_{symbol}", str(cooldown_end))
                    logging.info(f"[LOSS COOLDOWN] Placed {symbol} on cooldown for {cooldown_hours} hours until {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(cooldown_end))}")
            
            # Update balance
            original_value = quantity * entry_price
            self.balance += (original_value + pnl) - exit_fee
            
            # Save updated balance to DB
            database.save_setting("portfolio_balance", self.balance)
            
            # If live mode, sync balance directly from the exchange
            if self.trading_mode == "live":
                self.sync_live_balance()
            
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
                "strategy_signals": pos["strategy_signals"],
                "sentiment_sources": pos.get("sentiment_sources", {})
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
                        symbol,
                        pos["strategy_signals"],
                        direction,
                        pnl_percent
                    )
                except Exception as e:
                    logging.error(f"Error in learning callback during trade closure: {e}")

            return {"event": "closed", "data": closed_trade_record}

        return None

    def get_equity(self, current_prices):
        """Calculates current total portfolio equity across all active positions.
        
        current_prices: dict of symbol -> current_price
        """
        if self.trading_mode == "live":
            holdings = getattr(self, "live_holdings", {})
            if not holdings:
                return float(getattr(self, "live_equity", self.balance))
                
            total_value = 0.0
            last_prices = getattr(self, "last_known_prices", {})
            
            for asset, qty in holdings.items():
                if asset in ["EUR", "USD"]:
                    total_value += qty
                else:
                    price = None
                    for key in [f"{asset}-USD", f"{asset}/USD", f"{asset}-EUR", f"{asset}/EUR", f"XXBT-USD", f"XETH-USD", f"XXRP-USD", f"XXBT-EUR", f"XETH-EUR", f"XXRP-EUR"]:
                        if key in current_prices and current_prices[key] is not None:
                            price = float(current_prices[key])
                            break
                    if price is None or price == 0.0:
                        price = float(last_prices.get(asset, 0.0))
                    
                    total_value += qty * price
            return float(total_value)
            
        equity = self.balance
        for symbol, pos in self.active_positions.items():
            qty = pos["quantity"]
            entry = pos["entry_price"]
            price = current_prices.get(symbol, entry)
            
            if pos["direction"] == "BUY":
                unrealized = (price - entry) * qty
            else:
                unrealized = (entry - price) * qty
                
            equity += unrealized
        return float(equity)
