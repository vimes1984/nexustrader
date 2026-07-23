import time
import logging
import json
import os
import threading
import database

# Global lock protecting shared execution state (active_positions, balance, pending_limit_orders)
_exec_lock = threading.RLock()

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
        
        # Restart recovery: if balance is much lower than initial_balance + closed_trades_pnl
        # and there are no active positions (lost on restart), the balance was saved with
        # position costs deducted. Recalculate to recover orphaned position capital.
        _closed_pnl = sum(float(t.get('pnl', 0.0) or 0.0) for t in self.closed_trades)
        _expected_balance = self.initial_balance + _closed_pnl
        if len(self.active_positions) == 0 and abs(self.balance - _expected_balance) > 1.0 and self.balance < _expected_balance:
            diff = _expected_balance - self.balance
            if diff > 1.0:
                self.balance = _expected_balance
                database.save_setting("portfolio_balance", self.balance)
                logging.info(f"[RESTART RECOVERY] Restored balance from ${self.balance - diff:.2f} to ${self.balance:.2f} (orphaned position costs recovered)")
        
        self.learning_callback = None
        self.pending_limit_orders = {}  # symbol -> pending order dict

    def _get_asset_balance(self, asset):
        """Get the balance of a specific asset from latest Kraken sync.
        Assets are normalized (e.g. 'XBT' -> 'BTC').
        """
        if not hasattr(self, '_last_raw_balances') or not self._last_raw_balances:
            return 0.0
        # Try direct match first
        if asset in self._last_raw_balances:
            return float(self._last_raw_balances[asset])
        # Try common Kraken alternate names
        alt_names = {'BTC': 'XBT', 'XBT': 'BTC', 'DOGE': 'XDG', 'XDG': 'DOGE'}
        if asset in alt_names and alt_names[asset] in self._last_raw_balances:
            return float(self._last_raw_balances[alt_names[asset]])
        return 0.0

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
            self._last_raw_balances = total_bal  # Cache for balance checks
            
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
            # BUGFIX: Recheck min amount after precision rounding (can round below min)
            if amount < min_amount:
                logging.warning(f"[LIVE TRADING MIN] Amount {amount} below min {min_amount} after precision rounding — using min amount")
                amount = float(exchange.amount_to_precision(ccxt_symbol, min_amount))
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
        with _exec_lock:
            return self._open_position_internal(symbol, evaluation, strategy_signals)

    def _open_position_internal(self, symbol, evaluation, strategy_signals):
        """Internal: called with _exec_lock held."""
        # Check Loss Cooldown
        try:
            cooldown_end = float(database.load_setting(f"cooldown_end_{symbol}", "0.0"))
        except (ValueError, TypeError):
            cooldown_end = 0.0
        if time.time() < cooldown_end:
            remaining_minutes = int((cooldown_end - time.time()) / 60)
            logging.warning(f"[LOSS COOLDOWN] Ticker {symbol} is in a loss cooldown period. {remaining_minutes} mins remaining. Skipping.")
            return False

        # Portfolio-level risk checks — reload limits each time so optimizer/prompt changes take effect
        self.max_open_positions = int(database.load_setting("max_open_positions", str(self.max_open_positions)))
        self.max_concentration = float(database.load_setting("max_concentration_pct", str(self.max_concentration * 100))) / 100.0
        self.max_total_exposure = float(database.load_setting("max_total_exposure_pct", str(self.max_total_exposure * 100))) / 100.0
        
        if len(self.active_positions) >= self.max_open_positions:
            logging.warning(f"[PORTFOLIO RISK] Max open positions ({self.max_open_positions}) reached. Skipping {symbol}.")
            return False
        
        # Concentration limit: prevent too much capital in one position
        # BUGFIX: In paper mode, last_known_prices is empty {} so get_equity() only returns balance.
        # This underestimates equity by ignoring unrealized PnL when a position is in profit.
        # Fall back to a try: get current prices from any caller-provided context.
        _prices_for_equity = getattr(self, 'last_known_prices', {})
        total_equity = self.get_equity(_prices_for_equity)
        kf = evaluation.get("kelly_fraction", 0.05)
        edir = evaluation.get("direction", "BUY")
        eprice = evaluation.get("entry_price", 0.0)
        esl = evaluation.get("stop_loss", 0.0)
        
        # Calculate committed capital from existing positions
        existing_exposure = 0.0
        for pos in self.active_positions.values():
            existing_exposure += pos.get('quantity', 0) * pos.get('entry_price', 0)
        
        # Available balance = cash balance (position costs already deducted from balance on entry)
        # BUGFIX: Do NOT subtract committed_capital again — balance already reflects position deductions.
        # Double-counting would underestimate free capital and prevent new positions.
        committed_capital = existing_exposure
        available_balance = max(0.0, self.balance)
        
        # Multi-asset Kelly: fraction of REMAINING capital, not total balance
        # This prevents over-betting when multiple concurrent positions exist
        # Pre-compute the actual Kelly position value (same formula as below) to avoid
        # a dual-estimate bug: position_value_est was computed one way for risk limits and
        # position_value was computed differently for execution. A tight stop makes the
        # Kelly-converted position much larger than the simple fraction check thinks.
        stop_loss_pct_est = abs(eprice - esl) / eprice if eprice > 0 else 0.1
        if stop_loss_pct_est < 0.001:
            stop_loss_pct_est = 0.001
        kelly_position_value = (available_balance * kf) / min(stop_loss_pct_est, 0.5)
        
        if total_equity > 0 and kelly_position_value > 0:
            new_total_exposure = (existing_exposure + kelly_position_value) / total_equity
            if new_total_exposure > self.max_total_exposure:
                logging.warning(f"[PORTFOLIO RISK] Total exposure {new_total_exposure:.1%} would exceed {self.max_total_exposure:.1%}. Skipping {symbol}.")
                return False
            single_exposure = kelly_position_value / total_equity
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

        # Calculate position size: Kelly fraction * available_balance / stop_distance
        # Kelly f* gives the fraction of capital to RISK, not the position size.
        # Convert: stop_loss_pct = distance from entry to stop as fraction of entry.
        # position_value = (available_balance * kelly_fraction) / stop_loss_pct
        # Using available_balance (balance - committed_capital) prevents multi-asset over-betting
        stop_loss_pct = abs(entry_price - sl) / entry_price if entry_price > 0 else 0.1
        if stop_loss_pct < 0.001:
            stop_loss_pct = 0.001  # At least 0.1% stop distance
        position_value = (available_balance * kelly_fraction) / min(stop_loss_pct, 0.5)  # cap stop at 50%
        
        # For SELL orders, cap position value by actual base asset holdings
        if direction == "SELL":
            base_asset = symbol.split('-')[0] if '-' in symbol else symbol
            try:
                base_bal = self._get_asset_balance(base_asset)
                # BUGFIX: In paper mode _last_raw_balances is None, so _get_asset_balance returns 0.
                # This caused ALL SELL signals to silently return None (max_sell_value = 0 < $5).
                # Paper mode should not require exchange balance — assume the position's notional value.
                if self.trading_mode != "live" or base_bal <= 0:
                    # Paper mode: SELL position is opened assuming we hold the asset synthetically.
                    max_sell_qty = position_value / entry_price if entry_price > 0 else 0
                    max_sell_value = position_value
                else:
                    max_sell_qty = base_bal * 0.995  # Reserve 0.5% for fees/slippage
                    max_sell_value = max_sell_qty * entry_price
                if max_sell_value < 5.0:
                    return None  # skip — cannot meet $5 minimum
                if position_value > max_sell_value:
                    position_value = max_sell_value
                    logging.info("[SIZE CAP] SELL %s capped to $%.2f (hold %.6f %s)" % (symbol, max_sell_value, base_bal, base_asset))
            except Exception as e:
                logging.warning("[SIZE CAP] Could not cap SELL size: %s" % str(e))
        
        # Hard cap position value to max_position_pct% of total equity
        max_pos_pct = float(database.load_setting("max_position_pct", "15")) / 100.0
        max_allowed_position = total_equity * max_pos_pct
        if position_value > max_allowed_position:
            logging.info("[SIZE CAP] Position ${:.2f} exceeds {:.0f}% of equity (${:.2f}). Capped to ${:.2f}.".format(
                position_value, max_pos_pct*100, total_equity, max_allowed_position))
            position_value = max_allowed_position

        # Minimum position floor: $5 to allow small-account trading
        if position_value < 5.0:
            logging.warning(f"[MIN SIZE] Position value ${position_value:.2f} below $5 minimum. Skipping {symbol}.")
            return False
        quantity = position_value / entry_price

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

        # Balance check for spot trading: SELL requires holding the base asset
        base_asset = symbol.split('-')[0] if '-' in symbol else symbol
        if direction == "SELL" and self.trading_mode == "live":
            try:
                base_balance = self._get_asset_balance(base_asset)
                needed = quantity * (1.0 + self.transaction_fee_rate)
                if base_balance < needed:
                    logging.warning(f"[BALANCE] Insufficient {base_asset} balance (have {base_balance:.6f}, need {needed:.6f}). Skipping SELL on {symbol}.")
                    return False
            except Exception as e:
                logging.warning(f"[BALANCE] Could not check {base_asset} balance: {e}. Proceeding anyway.")
        
        # Execute order (live broker or paper simulation)
        if self.trading_mode == "live":
            success, actual_qty = self.execute_order_on_broker(symbol, direction.lower(), quantity, entry_price)
            if not success:
                logging.error(f"Could not execute entry order for {symbol} on live broker. Position aborted. Placing on temporary 5-minute retry cooldown.")
                database.save_setting(f"cooldown_end_{symbol}", str(time.time() + 300))
                return False
            exec_label = "live"
        else:
            actual_qty = quantity
            exec_label = "paper"
            
        position_cost = actual_qty * effective_entry
        # BUGFIX: Compute fee from actual execution cost (effective_entry * qty), not from
        # the pre-slippage position_value estimate. Inconsistent fee calc caused micro-balance drift.
        fee = position_cost * self.transaction_fee_rate
        if direction == "BUY":
            self.balance -= (position_cost + fee)
        else:
            self.balance -= fee  # SELL: only fee (position margin covered by holdings)
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
            "fee_paid": fee,
            # Store evaluation metadata for trade recording on close
            "predicted_win_probability": evaluation.get("win_probability"),
            "expected_value": evaluation.get("expected_value"),
            "risk_reward_ratio": evaluation.get("risk_reward_ratio"),
            "kelly_fraction": evaluation.get("kelly_fraction"),
        }
        logging.info(f"Opened {exec_label} {direction} position for {symbol}: Qty {actual_qty:.6f} at {effective_entry:.2f} (incl. slippage). Fee: {fee:.2f}")
        return True

    def update_positions(self, symbol, current_price):
        """Checks active positions for TP/SL hits. Uses slippage-adjusted exit prices."""
        with _exec_lock:
            return self._update_positions_internal(symbol, current_price)

    def _update_positions_internal(self, symbol, current_price):
        """Internal: called with _exec_lock held."""
        # Evaluate active positions for this symbol (TP/SL check)
        if symbol not in self.active_positions:
            return None

        pos = self.active_positions[symbol]
        direction = pos["direction"]
        entry_price = pos["entry_price"]
        quantity = pos["quantity"]
        tp = pos["take_profit"]
        sl = pos["stop_loss"]

        # Track current price on position for API / dashboard display
        pos["current_price"] = current_price

        # Compute unrealized PnL for display
        if direction == "BUY":
            pos["unrealized_pnl"] = (current_price - entry_price) * quantity
        else:
            pos["unrealized_pnl"] = (entry_price - current_price) * quantity
        entry_value = entry_price * quantity if entry_price > 0 else 1e-9
        pos["unrealized_pnl_pct"] = pos["unrealized_pnl"] / entry_value

        # Trailing Stop-Loss logic — config-driven
        trailing_stop_enabled = database.load_setting("trailing_stop_enabled", "true").lower() == "true"
        if trailing_stop_enabled:
            # Default trail offset widened from 0.5% to 1.5% for crypto noise tolerance
            trail_offset_pct = float(database.load_setting("trailing_stop_offset_pct", "0.015"))
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
                
            # Handle trade closure — include both exit fee and entry fee in net PnL
            exit_fee = (exit_price * quantity) * self.transaction_fee_rate
            entry_fee = pos.get("fee_paid", 0.0)
            pnl_after_fee = pnl - exit_fee - entry_fee
            
            # Trigger Loss Cooldown if PnL is negative — and clear on win
            if pnl_after_fee < 0:
                cooldown_hours = float(database.load_setting("loss_cooldown_hours", "4.0"))
                if cooldown_hours > 0:
                    cooldown_end = time.time() + (cooldown_hours * 3600)
                    database.save_setting(f"cooldown_end_{symbol}", str(cooldown_end))
                    logging.info(f"[LOSS COOLDOWN] Placed {symbol} on cooldown for {cooldown_hours} hours until {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(cooldown_end))}")
            else:
                # BUGFIX: Clear cooldown on winning trade so a winning streak isn't interrupted
                # by stale cooldown from a previous loss on the same symbol.
                existing_cooldown = database.load_setting(f"cooldown_end_{symbol}", "0")
                if existing_cooldown and float(existing_cooldown) > time.time():
                    database.save_setting(f"cooldown_end_{symbol}", "0")
                    logging.info(f"[WIN COOLDOWN CLEAR] Cleared cooldown for {symbol} after winning trade.")
            
            # Update balance — net effect must equal pnl_after_fee (including both fees)
            original_value = quantity * entry_price
            if direction == "SELL":
                # SELL: original_value was never deducted on open (spot sell), only fee was
                # Net: -entry_fee (open) + pnl - exit_fee (close) = pnl_after_fee
                self.balance += pnl - exit_fee  # entry_fee already subtracted on open
            else:
                # BUY: original_value deducted on open, add back plus profit minus exit fee
                # Net: -(position_cost + entry_fee) + (original_value + pnl - exit_fee)
                # position_cost ≈ original_value (paper), so net ≈ pnl - exit_fee - entry_fee = pnl_after_fee
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
                "trading_mode": self.trading_mode,
                # Include evaluation metadata stored on entry for calibration/tracking
                "predicted_win_probability": pos.get("predicted_win_probability"),
                "expected_value": pos.get("expected_value"),
                "risk_reward_ratio": pos.get("risk_reward_ratio"),
                "kelly_fraction": pos.get("kelly_fraction"),
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
        with _exec_lock:
            return self._get_equity_internal(current_prices)

    def _get_equity_internal(self, current_prices=None):
        """Internal: requires _exec_lock held by caller."""
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
