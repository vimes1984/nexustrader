import time
import logging
import json
import os
import database

def normalize_kraken_asset(asset: str) -> str:
    asset = asset.upper()
    overrides = {
        "XXBT": "BTC",
        "XETH": "ETH",
        "XXRP": "XRP",
        "XLTC": "LTC",
        "XXLM": "XLM",
        "XDG": "DOGE",
        "ZEUR": "EUR",
        "ZUSD": "USD",
        "ZGBP": "GBP",
        "ZCAD": "CAD",
        "ZJPY": "JPY"
    }
    if asset in overrides:
        return overrides[asset]
        
    if asset.startswith("X") and len(asset) >= 4 and asset not in ["XLM", "XTZ", "XMR"]:
        return asset[1:]
    if asset.startswith("Z") and len(asset) >= 4:
        return asset[1:]
        
    return asset

class ExecutionEngine:
    def __init__(self, initial_balance=100.0, transaction_fee_rate=0.0026):
        self.initial_balance = initial_balance
        self.transaction_fee_rate = transaction_fee_rate  # Default: Kraken taker fee (0.26%)
        # Slippage estimation for realistic paper trading
        self.slippage_rate = 0.001  # 0.1% estimated market impact for small orders
        self.active_positions = {}  # symbol -> position dict
        self.max_open_positions = 3  # Hard limit: max concurrent positions
        self.max_concentration = 0.40  # Max portfolio % in a single ticker
        self.max_total_exposure = 0.60  # Max % of portfolio in all open positions
        
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
        # Load portfolio risk limits from DB
        try:
            self.max_open_positions = int(database.load_setting("max_open_positions", "3"))
            self.max_concentration = float(database.load_setting("max_concentration_pct", "40")) / 100.0
            self.max_total_exposure = float(database.load_setting("max_total_exposure_pct", "60")) / 100.0
        except Exception:
            self.max_open_positions = 3
            self.max_concentration = 0.40
            self.max_total_exposure = 0.60
        
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
            
        # Load live equity and holdings state cache
        db_live_equity = database.load_setting("portfolio_live_equity")
        self.live_equity = float(db_live_equity) if db_live_equity is not None else self.balance
        
        db_live_holdings = database.load_setting("portfolio_live_holdings")
        if db_live_holdings is not None:
            try:
                self.live_holdings = json.loads(db_live_holdings)
            except Exception:
                self.live_holdings = {}
        else:
            self.live_holdings = {}
            
        db_prices = database.load_setting("portfolio_last_known_prices")
        if db_prices is not None:
            try:
                self.last_known_prices = json.loads(db_prices)
            except Exception:
                self.last_known_prices = {}
        else:
            self.last_known_prices = {}

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
                'timeout': 15000,
            })
            balance_info = exchange.fetch_balance()
            total_bal = balance_info.get('total', {})
            
            # Load markets to check symbols
            try:
                if not exchange.markets:
                    exchange.load_markets()
            except Exception as le:
                logging.warning(f"Failed to load markets: {le}")

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
            
            # Identify held assets that need conversion rates
            for asset, qty in total_bal.items():
                qty = float(qty)
                if qty <= 0.000001:
                    continue
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
            
            # Always ensure baseline default tickers are queried
            for base in ["BTC", "ETH", "SOL", "DOGE", "LINK", "ADA", "XRP"]:
                symbol = f"{base}/USD"
                if not exchange.symbols or symbol in exchange.symbols:
                    held_assets.append(symbol)
                    
            held_assets = list(set(held_assets))
            
            prices = {}
            try:
                tickers = exchange.fetch_tickers(held_assets)
                prices = {sym.split('/')[0]: float(tick['last']) for sym, tick in tickers.items() if tick.get('last') is not None}
            except Exception as pe:
                logging.error(f"[LIVE VALUE SYNC] Failed to fetch specific conversion tickers: {pe}")
                # Fallback to fetching one by one
                for sym in held_assets:
                    try:
                        tick = exchange.fetch_ticker(sym)
                        if tick.get('last') is not None:
                            prices[sym.split('/')[0]] = float(tick['last'])
                    except Exception:
                        pass
            
            # Calculate Cash balance (in USD)
            total_cash_usd = 0.0
            for asset, qty in total_bal.items():
                qty = float(qty)
                if qty <= 0.000001:
                    continue
                norm = normalize_kraken_asset(asset)
                if norm in fiat_symbols:
                    fiat_name = fiat_symbols[norm]
                    if fiat_name == "USD":
                        total_cash_usd += qty
                    else:
                        rate = 1.0
                        if fiat_name in prices:
                            rate = prices[fiat_name]
                        elif norm in prices:
                            rate = prices[norm]
                        elif f"{fiat_name}/USD" in prices:
                            rate = prices[f"{fiat_name}/USD"]
                        else:
                            fallbacks = {"EUR": 1.09, "GBP": 1.30, "CAD": 0.73, "JPY": 0.0064, "AUD": 0.66, "CHF": 1.15}
                            rate = fallbacks.get(fiat_name, 1.0)
                        total_cash_usd += qty * rate
            
            self.balance = total_cash_usd
            
            # Calculate Holdings balance (in USD)
            total_value_usd = total_cash_usd
            for asset, qty in total_bal.items():
                qty = float(qty)
                if qty <= 0.000001:
                    continue
                norm = normalize_kraken_asset(asset)
                if norm in fiat_symbols:
                    continue
                    
                price_rate = 0.0
                if norm in prices:
                    price_rate = prices[norm]
                elif asset in prices:
                    price_rate = prices[asset]
                else:
                    db_last_prices = database.load_setting("portfolio_last_known_prices")
                    if db_last_prices:
                        try:
                            cached_prices = json.loads(db_last_prices)
                            price_rate = float(cached_prices.get(norm, cached_prices.get(asset, 0.0)))
                        except Exception:
                            pass
                            
                total_value_usd += qty * price_rate
                
            self.live_equity = total_value_usd
            self.live_holdings = {k: float(v) for k, v in total_bal.items() if float(v) > 0.000001}
            self.last_known_prices = prices
            
            # Save all values to persistent database cache
            database.save_setting("portfolio_balance", str(self.balance))
            database.save_setting("portfolio_live_equity", str(self.live_equity))
            database.save_setting("portfolio_live_holdings", json.dumps(self.live_holdings))
            database.save_setting("portfolio_last_known_prices", json.dumps(self.last_known_prices))
            
            # Update initial balance if not set
            is_custom = database.load_setting("initial_balance_is_custom") == "true"
            db_init_balance = database.load_setting("initial_portfolio_balance")
            if not is_custom and (db_init_balance is None or float(db_init_balance) == 100.0):
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
                'timeout': 15000,
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

        # Portfolio-level risk checks
        if len(self.active_positions) >= self.max_open_positions:
            logging.warning(f"[PORTFOLIO RISK] Max open positions ({self.max_open_positions}) reached. Skipping {symbol}.")
            return False
        
        # Concentration limit: prevent too much capital in one position
        total_equity = self.get_equity(getattr(self, 'last_known_prices', {}))
        kf = evaluation.get("kelly_fraction", 0.05)
        position_value_est = self.balance * kf
        existing_exposure = 0.0
        for pos in self.active_positions.values():
            existing_exposure += pos.get('quantity', 0) * pos.get('entry_price', 0)
        if total_equity > 0 and position_value_est > 0:
            new_total_exposure = (existing_exposure + position_value_est) / total_equity
            if new_total_exposure > self.max_total_exposure:
                logging.warning(f"[PORTFOLIO RISK] Total exposure {new_total_exposure:.1%} would exceed {self.max_total_exposure:.1%}. Skipping {symbol}.")
                return False
            single_exposure = position_value_est / total_equity
            if single_exposure > self.max_concentration:
                logging.warning(f"[PORTFOLIO RISK] Single position {single_exposure:.1%} exceeds {self.max_concentration:.1%}. Skipping {symbol}.")
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
        
        # Minimum position floor: $5 to allow small-account trading
        if position_value < 5.0:
            logging.warning(f"[MIN SIZE] Position value ${position_value:.2f} below $5 minimum. Skipping {symbol}.")
            return False
        quantity = position_value / entry_price
        fee = position_value * self.transaction_fee_rate

        # Apply slippage on entry for realistic simulation
        slippage_cost = entry_price * self.slippage_rate
        if direction == "BUY":
            effective_entry = entry_price + slippage_cost
        else:  # SELL
            effective_entry = entry_price - slippage_cost
        
        # Adjust TP/SL for slippage on entry
        if direction == "BUY":
            adjusted_tp = tp - slippage_cost  # Tougher to hit TP
            adjusted_sl = sl  # SL stays (worst case)
        else:
            adjusted_tp = tp + slippage_cost
            adjusted_sl = sl

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
                "entry_price": effective_entry,  # Use slippage-adjusted price
                "quantity": actual_qty,
                "take_profit": adjusted_tp,
                "stop_loss": adjusted_sl,
                "entry_time": time.time(),
                "strategy_signals": strategy_signals,
                "entry_state": evaluation.get("state", []),
                "sentiment_sources": evaluation.get("sentiment_sources", {}),
                "fee_paid": fee
            }
            logging.info(f"Opened live {direction} position for {symbol}: Qty {actual_qty:.6f} at {effective_entry:.2f} (slippage adj). Fee: {fee:.2f}")
            return True
        else:
            # Paper trading: simulate market order with slippage (immediate fill)
            actual_qty = quantity
            self.balance -= fee
            database.save_setting("portfolio_balance", self.balance)
            
            self.active_positions[symbol] = {
                "symbol": symbol,
                "direction": direction,
                "entry_price": effective_entry,  # Slippage-adjusted entry
                "quantity": actual_qty,
                "take_profit": adjusted_tp,
                "stop_loss": adjusted_sl,
                "entry_time": time.time(),
                "strategy_signals": strategy_signals,
                "entry_state": evaluation.get("state", []),
                "sentiment_sources": evaluation.get("sentiment_sources", {}),
                "fee_paid": fee
            }
            logging.info(f"Opened paper {direction} position for {symbol}: Qty {actual_qty:.6f} at {effective_entry:.2f} (incl. slippage). Fee: {fee:.2f}")
            return True

    def update_positions(self, symbol, current_price):
        """Checks active positions for TP/SL hits. Uses slippage-adjusted exit prices."""
        # Evaluate active positions for this symbol (TP/SL check)
        if symbol not in self.active_positions:
            return None

        pos = self.active_positions[symbol]
        direction = pos["direction"]
        entry_price = pos["entry_price"]
        quantity = pos["quantity"]
        tp = pos["take_profit"]
        sl = pos["stop_loss"]

        # Trailing Stop-Loss logic — config-driven
        trailing_stop_enabled = database.load_setting("trailing_stop_enabled", "true").lower() == "true"
        if trailing_stop_enabled:
            trail_offset_pct = float(database.load_setting("trailing_stop_offset_pct", "0.005"))
            if direction == "BUY":
                if "original_sl" not in pos:
                    pos["original_sl"] = sl
                # For BUY: trail SL upward as price rises
                trailed_sl = current_price * (1.0 - trail_offset_pct)
                if trailed_sl > sl:
                    sl = trailed_sl
                    pos["stop_loss"] = trailed_sl
                    logging.debug(f"[TRAILING SL] {symbol} BUY: trailed SL to {trailed_sl:.4f}")
            else: # SELL
                if "original_sl" not in pos:
                    pos["original_sl"] = sl
                # For SELL: trail SL downward as price falls
                trailed_sl = current_price * (1.0 + trail_offset_pct)
                if trailed_sl < sl:
                    sl = trailed_sl
                    pos["stop_loss"] = trailed_sl
                    logging.debug(f"[TRAILING SL] {symbol} SELL: trailed SL to {trailed_sl:.4f}")

        # Check for time-based stop (max position age)
        max_position_hours = 48  # Hard close after 48 hours
        exit_reason = None
        close_trade = False
        pnl = 0.0
        
        if pos.get("entry_time") and (time.time() - pos["entry_time"]) > (max_position_hours * 3600):
            close_trade = True
            exit_reason = "Time Stop ({}h max)".format(max_position_hours)

        # Apply slippage on exit for realistic simulation
        slippage_cost = current_price * self.slippage_rate
        if direction == "BUY":
            exit_price = current_price - slippage_cost  # Worse price when selling
        else:  # SELL
            exit_price = current_price + slippage_cost  # Worse price when buying to cover

        if direction == "BUY":
            pnl = (exit_price - entry_price) * quantity
            if current_price >= tp:
                close_trade = True
                exit_reason = "Take Profit"
            elif current_price <= sl:
                close_trade = True
                exit_reason = "Stop Loss"
        else: # SELL
            pnl = (entry_price - exit_price) * quantity
            if current_price <= tp:
                close_trade = True
                exit_reason = "Take Profit"
            elif current_price >= sl:
                close_trade = True
                exit_reason = "Stop Loss"

        if close_trade:
            # Place exit order on live broker if live mode is enabled
            exit_side = "sell" if direction == "BUY" else "buy"
            success = self.execute_order_on_broker(symbol, exit_side, quantity, exit_price)
            if not success:
                logging.error(f"Could not execute exit order for {symbol} on live broker. Keeping position open.")
                return None
                
            # Handle trade closure
            exit_fee = (exit_price * quantity) * self.transaction_fee_rate
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
            
            # Save updated balance to DB (batch if possible)
            database.save_setting("portfolio_balance", self.balance)
            
            # If live mode, sync balance directly from the exchange
            if self.trading_mode == "live":
                self.sync_live_balance()
            
            pnl_percent = (pnl_after_fee) / (original_value + 1e-9) if original_value != 0 else 0.0

            # Get active brain for symbol from DB settings
            active_brain_name = database.load_setting(f"active_policy_brain_{symbol}", "Default Brain")

            closed_trade_record = {
                "symbol": symbol,
                "direction": direction,
                "entry_price": entry_price,
                "exit_price": float(exit_price),
                "quantity": quantity,
                "pnl": float(pnl_after_fee),
                "pnl_percent": float(pnl_percent),
                "exit_reason": exit_reason,
                "entry_time": pos["entry_time"],
                "exit_time": time.time(),
                "strategy_signals": pos["strategy_signals"],
                "sentiment_sources": pos.get("sentiment_sources", {}),
                "policy_brain": active_brain_name,
                "trading_mode": self.trading_mode
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
                        pos.get("entry_state", []),
                        pos["strategy_signals"],
                        direction,
                        pnl_percent
                    )
                except Exception as e:
                    logging.error(f"Error in learning callback during trade closure: {e}")

            return {"event": "closed", "data": closed_trade_record}

        return None

    def get_equity(self, current_prices=None):
        """Calculates current total portfolio equity across all active positions.
        
        current_prices: dict of symbol -> current_price (default empty dict)
        """
        if current_prices is None:
            current_prices = {}
        if self.trading_mode == "live":
            holdings = getattr(self, "live_holdings", {})
            if not holdings:
                return float(getattr(self, "live_equity", self.balance))
                
            total_value = 0.0
            last_prices = getattr(self, "last_known_prices", {})
            
            # Find EUR/USD price rate to convert EUR cash
            eur_usd_rate = 1.09 # fallback
            if "EUR" in last_prices:
                eur_usd_rate = last_prices["EUR"]
            elif "ZEUR" in last_prices:
                eur_usd_rate = last_prices["ZEUR"]
            elif "EUR/USD" in last_prices:
                eur_usd_rate = last_prices["EUR/USD"]
                
            for asset, qty in holdings.items():
                if asset in ["USD", "ZUSD"]:
                    total_value += qty
                elif asset in ["EUR", "ZEUR"]:
                    total_value += qty * eur_usd_rate
                else:
                    norm_asset = normalize_kraken_asset(asset)
                    
                    price = None
                    # Try current price inputs for this specific asset only
                    for key in [f"{norm_asset}-USD", f"{norm_asset}/USD", f"{asset}-USD", f"{asset}/USD"]:
                        if key in current_prices and current_prices[key] is not None and current_prices[key] > 0:
                            price = float(current_prices[key])
                            break
                    # Fallback to last known price from DB (never cross-asset)
                    if price is None or price <= 0.0:
                        db_price = last_prices.get(norm_asset, last_prices.get(asset, 0.0))
                        price = float(db_price) if db_price else 0.0
                    
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
