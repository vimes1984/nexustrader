import time
import logging
import sqlite3
import numpy as np
import database

class LongTermStrategyLayer:
    def __init__(self, initial_shadow_balance=10000.0, transaction_fee_rate=0.0015, slippage_rate=0.0005):
        self.initial_balance = initial_shadow_balance
        self.balance = float(database.load_setting("shadow_balance", str(initial_shadow_balance)))
        self.fee_rate = transaction_fee_rate
        self.slippage_rate = slippage_rate
        
        # Load active shadow positions from database on startup
        self.active_positions = {}
        self._load_active_positions_from_db()
        
        # Circuit breaker configuration
        self.max_shadow_drawdown = 0.10 # 10%
        self.peak_balance = float(database.load_setting("shadow_peak_balance", str(self.balance)))

    def _load_active_positions_from_db(self):
        conn = database.get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id, symbol, direction, quantity, entry_price, tp_price, sl_price, atr_at_entry, entry_time FROM shadow_trades WHERE status = 'active'")
            rows = cursor.fetchall()
            for r in rows:
                self.active_positions[r[1]] = {
                    "id": r[0],
                    "symbol": r[1],
                    "direction": r[2],
                    "quantity": r[3],
                    "entry_price": r[4],
                    "tp_price": r[5],
                    "sl_price": r[6],
                    "atr_at_entry": r[7],
                    "entry_time": r[8]
                }
            logging.info(f"Loaded {len(self.active_positions)} active shadow shadow positions from DB.")
        except Exception as e:
            logging.error(f"Error loading active shadow positions: {e}")
        finally:
            conn.close()

    def update_shadow_positions(self, ticker, current_price):
        """Checks active shadow positions for target exits (TP, SL, or max holding time of 2 days)."""
        if ticker not in self.active_positions:
            return None

        pos = self.active_positions[ticker]
        entry_price = pos["entry_price"]
        direction = pos["direction"]
        qty = pos["quantity"]
        tp = pos["tp_price"]
        sl = pos["sl_price"]
        trade_id = pos["id"]
        entry_time = pos["entry_time"]

        # Calculate holding duration
        duration_hours = (time.time() - entry_time) / 3600.0

        pnl = 0.0
        pnl_percent = 0.0
        exit_reason = None
        closed = False

        max_hold_hours = float(database.load_setting("shadow_max_holding_hours", "48.0"))

        if direction == "BUY":
            if current_price >= tp:
                # Slippage subtraction on sell (reduces exit price)
                exit_price = tp * (1.0 - self.slippage_rate)
                pnl = (exit_price - entry_price) * qty
                pnl_percent = (exit_price - entry_price) / entry_price * 100.0
                exit_reason = "Take Profit Hit"
                closed = True
            elif current_price <= sl:
                # Slippage subtraction on sell
                exit_price = sl * (1.0 - self.slippage_rate)
                pnl = (exit_price - entry_price) * qty
                pnl_percent = (exit_price - entry_price) / entry_price * 100.0
                exit_reason = "Stop Loss Hit"
                closed = True
            elif duration_hours >= max_hold_hours:
                exit_price = current_price * (1.0 - self.slippage_rate)
                pnl = (exit_price - entry_price) * qty
                pnl_percent = (exit_price - entry_price) / entry_price * 100.0
                exit_reason = f"Max Hold Time Reached ({max_hold_hours}h)"
                closed = True
        else: # SELL (Short position)
            if current_price <= tp:
                # Slippage addition on buy-to-cover (increases exit price)
                exit_price = tp * (1.0 + self.slippage_rate)
                pnl = (entry_price - exit_price) * qty
                pnl_percent = (entry_price - exit_price) / entry_price * 100.0
                exit_reason = "Take Profit Hit"
                closed = True
            elif current_price >= sl:
                # Slippage addition on buy-to-cover
                exit_price = sl * (1.0 + self.slippage_rate)
                pnl = (entry_price - exit_price) * qty
                pnl_percent = (entry_price - exit_price) / entry_price * 100.0
                exit_reason = "Stop Loss Hit"
                closed = True
            elif duration_hours >= max_hold_hours:
                exit_price = current_price * (1.0 + self.slippage_rate)
                pnl = (entry_price - exit_price) * qty
                pnl_percent = (entry_price - exit_price) / entry_price * 100.0
                exit_reason = f"Max Hold Time Reached ({max_hold_hours}h)"
                closed = True

        if closed:
            # Subtract simulated transaction fees on exit
            exit_fee = (exit_price * qty) * self.fee_rate
            pnl -= exit_fee
            
            # Update balance
            self.balance += pnl
            database.save_setting("shadow_balance", str(self.balance))
            
            # Update peak balance
            if self.balance > self.peak_balance:
                self.peak_balance = self.balance
                database.save_setting("shadow_peak_balance", str(self.peak_balance))

            # Database write
            database.update_shadow_trade_exit(trade_id, exit_price, pnl, pnl_percent, exit_reason)
            
            # Remove from local dictionary
            del self.active_positions[ticker]
            logging.info(f"[SHADOW TRADE CLOSED] Ticker: {ticker} | Exit: ${exit_price:.4f} | PnL: ${pnl:.2f} ({pnl_percent:.2f}%) | Reason: {exit_reason}")
            return {
                "event": "closed",
                "ticker": ticker,
                "pnl": pnl,
                "pnl_percent": pnl_percent,
                "exit_reason": exit_reason
            }

        return None

    def evaluate_long_term_rules(self, ticker, current_price, row, history_df, ensemble, learner):
        """Evaluates formal Long-Term rules and opens a shadow position if they pass."""
        if ticker in self.active_positions:
            return None

        # Check circuit breakers
        # 1. Shadow Mode Max Drawdown Circuit Breaker
        current_drawdown = 0.0
        if self.peak_balance > 0:
            current_drawdown = (self.peak_balance - self.balance) / self.peak_balance
            
        if current_drawdown >= self.max_shadow_drawdown:
            logging.warning(f"[SHADOW CIRCUIT BREAKER] Shadow Drawdown {current_drawdown*100:.1f}% >= Limit {self.max_shadow_drawdown*100:.1f}%. Halting new entries.")
            return None

        # 2. Main System Max Drawdown Circuit Breaker (respecting existing risk controls)
        max_drawdown_limit = float(database.load_setting("max_daily_drawdown", "5.0"))
        # (Assuming main live system handles its own active breaker, we check if it is active via a flag or setting)
        main_drawdown_active = database.load_setting("circuit_breaker_active", "false") == "true"
        if main_drawdown_active:
            logging.warning(f"[SHADOW SYSTEM BRIDGE] Main circuit breaker is active. Halting shadow entries.")
            return None

        # Collect Indicators
        close = float(row.get("close", current_price))
        atr = float(row.get("atr", close * 0.01))
        
        # Estimate OU process to verify regime
        from quant_utils import estimate_ou_process
        prices_list = list(history_df['close'].values[-60:]) if history_df is not None and len(history_df) >= 20 else []
        is_mr = False
        if len(prices_list) >= 20:
            _, _, is_mr = estimate_ou_process(prices_list)

        # Get signals & breakdown
        weighted_signal, strategy_breakdown = ensemble.get_weighted_signal(row, history_df)
        
        # Rule 1: Trend Filter Alignment (Kalman Filter Trend Strategy must output uptrend >= 0)
        # Index 4 in strategies is KalmanTrendStrategy
        kalman_trend_val = 0.0
        try:
            kalman_trend_val = ensemble.strategies[2].generate_signal(row, history_df)
        except Exception:
            pass

        # Load parameters dynamically from database settings
        shadow_volatility_target_pct = float(database.load_setting("shadow_volatility_target_pct", "1.5"))
        shadow_tp_atr_multiplier = float(database.load_setting("shadow_tp_atr_multiplier", "3.0"))
        shadow_sl_atr_multiplier = float(database.load_setting("shadow_sl_atr_multiplier", "1.5"))
        shadow_nn_consensus_min_weight = float(database.load_setting("shadow_nn_consensus_min_weight", "0.12"))

        # Rule 4: Neural Network Consensus Gate
        state = learner.get_state_vector(row, prices_list, [])
        nn_weights = learner.select_weights(state)
        # Index 4 corresponds to Kalman Trend strategy
        kalman_nn_weight = nn_weights[4] if len(nn_weights) > 4 else 0.1

        # Check signals
        direction = None
        if kalman_trend_val > 0 and weighted_signal >= 0.20 and kalman_nn_weight >= shadow_nn_consensus_min_weight and not is_mr:
            direction = "BUY"
        elif kalman_trend_val < 0 and weighted_signal <= -0.20 and kalman_nn_weight >= shadow_nn_consensus_min_weight and not is_mr:
            direction = "SELL"

        if not direction:
            return None

        # Rule 3: Volatility-Targeted Sizing
        # Target Volatility percent of price
        target_vol = close * (shadow_volatility_target_pct / 100.0)
        vol_scale = min(1.5, max(0.5, target_vol / (atr + 1e-9)))
        
        # Kelly Fraction from Probability Engine or baseline
        kelly_fraction = 0.10 * vol_scale # Default Kelly scaled by volatility target
        
        # Calculate sizing
        position_value = self.balance * kelly_fraction
        
        # Slippage addition on entry
        entry_slippage = close * self.slippage_rate
        execution_price = (close + entry_slippage) if direction == "BUY" else (close - entry_slippage)
        
        quantity = position_value / execution_price
        
        # Subtract entry transaction fees
        entry_fee = position_value * self.fee_rate
        self.balance -= entry_fee
        database.save_setting("shadow_balance", str(self.balance))

        # Set TP/SL bounds (Rule 2: Extended Hold Multi-Hour Target)
        # Long-term ATR target: TP at shadow_tp_atr_multiplierx ATR, SL at shadow_sl_atr_multiplierx ATR
        if direction == "BUY":
            tp_price = execution_price + (atr * shadow_tp_atr_multiplier)
            sl_price = execution_price - (atr * shadow_sl_atr_multiplier)
        else:
            tp_price = execution_price - (atr * shadow_tp_atr_multiplier)
            sl_price = execution_price + (atr * shadow_sl_atr_multiplier)

        # Log trade to DB as active
        conn = database.get_db_connection()
        cursor = conn.cursor()
        trade_id = None
        try:
            cursor.execute(
                """
                INSERT INTO shadow_trades (symbol, direction, quantity, entry_price, status, tp_price, sl_price, atr_at_entry, entry_time)
                VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?)
                """,
                (ticker, direction, quantity, execution_price, tp_price, sl_price, atr, time.time())
            )
            conn.commit()
            trade_id = cursor.lastrowid
        except Exception as e:
            logging.error(f"Error logging shadow trade to DB: {e}")
        finally:
            conn.close()

        if trade_id:
            # Store in-memory
            self.active_positions[ticker] = {
                "id": trade_id,
                "symbol": ticker,
                "direction": direction,
                "quantity": quantity,
                "entry_price": execution_price,
                "tp_price": tp_price,
                "sl_price": sl_price,
                "atr_at_entry": atr,
                "entry_time": time.time()
            }
            logging.info(f"[SHADOW TRADE OPENED] {direction} {quantity:.4f} {ticker} @ ${execution_price:.4f} | TP: ${tp_price:.4f} | SL: ${sl_price:.4f}")
            return {
                "event": "opened",
                "ticker": ticker,
                "direction": direction,
                "quantity": quantity,
                "entry_price": execution_price,
                "tp_price": tp_price,
                "sl_price": sl_price
            }
        
        return None
