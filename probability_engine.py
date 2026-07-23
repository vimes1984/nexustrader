import numpy as np
import logging
from evaluation.position_sizing import compute_safe_fraction, estimate_metrics_from_trades

class ProbabilityEngine:
    def __init__(self, kelly_fraction=0.1, min_win_rate=0.45):
        self.min_win_rate = min_win_rate
        self.signal_history = {}
        self.set_risk_mode("conservative")
        # Cache for historical trade metrics (fetched once per risk mode change)
        self._cached_metrics = None

    def set_risk_mode(self, mode):
        self.risk_mode = mode
        if mode == "conservative":
            self.kelly_fraction = 0.1
            self.max_cap = 0.05
        elif mode == "aggressive":
            self.kelly_fraction = 0.3
            self.max_cap = 0.20
        elif mode == "hyper_growth":
            self.kelly_fraction = 0.5
            self.max_cap = 0.50
        else:
            raise ValueError(f"Invalid risk mode: {mode}")

    def calculate_atr_bounds(self, price, atr, direction, symbol=None):
        """Calculates Volatility-Adjusted Take-Profit (TP) and Stop-Loss (SL) using ATR."""
        import database
        tp_multiplier = 5.0
        sl_multiplier = 3.0
        
        if symbol:
            try:
                conn = database.get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT tp_multiplier, sl_multiplier FROM active_assets WHERE ticker = ?", (symbol,))
                db_row = cursor.fetchone()
                conn.close()
                if db_row:
                    tp_multiplier = float(db_row[0])
                    sl_multiplier = float(db_row[1])
            except Exception:
                tp_multiplier = float(database.load_setting("opt_tp_multiplier", "2.5"))
                sl_multiplier = float(database.load_setting("opt_sl_multiplier", "1.5"))
        else:
            tp_multiplier = float(database.load_setting("opt_tp_multiplier", "2.5"))
            sl_multiplier = float(database.load_setting("opt_sl_multiplier", "1.5"))

        if atr is None or np.isnan(atr) or atr == 0:
            # Fallback to percentage-based bounds (1.5% TP, 1.0% SL)
            atr = price * 0.01

        sl_distance = atr * sl_multiplier
        tp_distance = atr * tp_multiplier

        if direction == "BUY":
            tp = price + tp_distance
            sl = price - sl_distance
            # SL can't go below 0 (price can't go negative) and max loss = entry
            sl = max(sl, 0.01 * price)  # Clamp to 1% of price minimum
        else: # SELL
            tp = price - tp_distance
            sl = price + sl_distance
            # TP can't go below 0 (max gain on short = full price decline to 0)
            tp = max(tp, 0.01 * price)  # Clamp to 1% of price minimum

        return float(tp), float(sl)

    def estimate_win_probability(self, weighted_signal, row, history_df=None):
        """Estimates the probability of a trade being successful (P_win).
        
        Uses signal strength and current market regime indicators (like RSI and ATR).
        If history_df is provided, performs a localized statistical check.
        """
        # Guard against NaN/None signals — works for all numeric types (float, np.float32, np.float64)
        if weighted_signal is None or (isinstance(weighted_signal, (float, int)) and weighted_signal != weighted_signal):
            weighted_signal = 0.0
        
        # Guard against None row
        if row is None:
            row = {}
        
        # Base probability mapping from weighted signal magnitude [0.0, 1.0]
        signal_magnitude = abs(weighted_signal)
        
        # Sigmoid scaling: map [0, 1] to base win rate [0.40, 0.70]
        base_p = 0.40 + (signal_magnitude * 0.30)
        
        # Adjust based on RSI regime — require favorable regime for trade direction
        rsi = row.get('rsi', 50)
        rsi_adjustment = 0.0
        
        if weighted_signal > 0:  # BUY
            if rsi < 35:
                rsi_adjustment = 0.10
            elif rsi < 45:
                rsi_adjustment = 0.05
            elif rsi < 55:
                rsi_adjustment = 0.0
            elif rsi < 70:
                rsi_adjustment = -0.08
            else:
                rsi_adjustment = -0.15
        elif weighted_signal < 0:  # SELL
            if rsi > 65:
                rsi_adjustment = 0.10
            elif rsi > 55:
                rsi_adjustment = 0.05
            elif rsi > 45:
                rsi_adjustment = 0.0
            elif rsi > 30:
                rsi_adjustment = -0.08
            else:
                rsi_adjustment = -0.15
                
        p_win = np.clip(base_p + rsi_adjustment, 0.30, 0.80)
        
        # Simple historical refinement if history is available
        if history_df is not None and len(history_df) > 50:
            try:
                # FUTURE INFO WARNING: history_df may contain all data up to present.
                # We only use data that is strictly BEFORE the current row to avoid
                # look-ahead bias when a full history dataframe is passed.
                close_series = history_df['close']
                # Forward return: close 5 periods ahead (only valid for historical data)
                forward_close = close_series.shift(-5)
                valid_idx = close_series.notna() & forward_close.notna()
                
                # Find historical instances with similar RSI — EXCLUDING current position
                rsi_series = history_df['rsi']
                similar_mask = rsi_series.between(rsi - 10, rsi + 10) & valid_idx
                # Exclude last 5 rows to avoid look-ahead from shift(-5) NaN values
                # shift(-5) creates NaN for the 5 most recent rows
                similar_mask = similar_mask & (close_series.index < len(close_series) - 5)
                similar_count = similar_mask.sum()
                
                if similar_count > 10:
                    # Mean of boolean True=1, False=0 gives win rate
                    hist_win_rate = float(forward_close[similar_mask].gt(close_series[similar_mask]).mean())
                    # Blend 70% model / 30% empirical historical win rate
                    p_win = 0.7 * p_win + 0.3 * hist_win_rate
            except Exception as e:
                logging.error(f"Error in empirical odds estimation: {e}")

        return float(p_win)

    def evaluate_trade(self, price, atr, direction, weighted_signal, row, history_df=None, symbol=None):
        """Evaluates trade parameters including entry, SL, TP, Win Probability, EV, and size."""
        # Guard against None row
        if row is None:
            row = {}
        
        # Guard against NaN/None price or direction — handles all numeric types
        if price is None or (isinstance(price, (float, int)) and price != price):
            price = 0.0
        if direction is None:
            direction = "BUY"
        
        # 1. Calc SL/TP
        tp, sl = self.calculate_atr_bounds(price, atr, direction, symbol)
        
        # 2. Get win probability
        p_win = self.estimate_win_probability(weighted_signal, row, history_df)
        
        # 3. Calculate Risk and Reward absolute sizes
        if direction == "BUY":
            reward = tp - price
            risk = price - sl
        else:
            reward = price - tp
            risk = sl - price
            
        risk = max(risk, 1e-9)
        # Guard against NaN/Inf reward or risk (should not happen, but be defensive)
        if reward is None or (isinstance(reward, (float, int)) and reward != reward):
            reward = risk  # fallback: 1:1
        if risk is None or (isinstance(risk, (float, int)) and risk != risk):
            risk = reward if reward > 0 else 1e-9
        
        # Cap reward:risk ratio to prevent numerical issues with extreme values
        # Also guard division-by-zero: when reward=0, edge doesn't exist, ratio=0
        risk_reward_ratio = reward / risk if risk > 0 and reward > 0 else 0.0
        risk_reward_ratio = min(risk_reward_ratio, 20.0)
        
        # 4. Calculate Expected Value (EV) per unit size
        ev = (p_win * reward) - ((1 - p_win) * risk)
        
        # 5. Position Sizing via Kelly Criterion
        # f* = p - (q / b) = p - (1-p)/R
        # where b = win_amount/loss_amount = R
        # Guard against division by zero when R = 0 (no reward edge)
        if risk_reward_ratio > 0:
            kelly_size = p_win - ((1.0 - p_win) / risk_reward_ratio)
        else:
            kelly_size = 0.0  # No edge: zero position
        # Kelly must be in [0, 1]; clamp both sides
        kelly_size = max(0.0, min(kelly_size, 1.0))
        
        # Apply fractional Kelly
        final_fraction = kelly_size * self.kelly_fraction
        
        # Cap max position size based on risk profile or custom kelly ceiling
        max_cap = self.max_cap
        if symbol:
            try:
                import database
                conn = database.get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT kelly_ceiling FROM active_assets WHERE ticker = ?", (symbol,))
                db_row = cursor.fetchone()
                conn.close()
                if db_row:
                    max_cap = float(db_row[0])
            except Exception:
                pass
        
        final_fraction = min(final_fraction, max_cap)
        
        # Layer 2: Drawdown-aware & calibration-aware safe fraction
        # Uses historical trade metrics to cap position size when underwater
        try:
            import database as _db
            trades = _db.load_trades()
            if len(trades) >= 5:
                metrics = estimate_metrics_from_trades(trades)
                # Get calibration cap from evaluation singletons
                try:
                    from evaluation.singletons import kill_switch, drawdown_tracker
                    from probability_calibration import kelly_cap_from_calibration
                    calibration_cap = 0.15  # default
                    if hasattr(kill_switch, 'calibration_brier') and kill_switch.calibration_brier is not None:
                        brier = kill_switch.calibration_brier
                        calibration_cap = kelly_cap_from_calibration(brier, n_samples=len(trades))
                    current_dd = drawdown_tracker.current_drawdown if hasattr(drawdown_tracker, 'current_drawdown') else 0.0
                except Exception:
                    calibration_cap = 0.15
                    current_dd = 0.0
                
                sizing = compute_safe_fraction(
                    win_rate=metrics['win_rate'],
                    avg_win=metrics['avg_win'],
                    avg_loss=metrics['avg_loss'],
                    n_trades=metrics['count'],
                    calibration_cap=calibration_cap,
                    current_drawdown_pct=current_dd * 100.0,
                    drawdown_limit_pct=15.0
                )
                # Cap position by safe fraction
                final_fraction = min(final_fraction, sizing['safe_fraction'])
        except Exception:
            pass
        
        # Entry quality check: RSI must align with direction
        # Relaxed threshold: allow trend-following entries up to RSI 75
        # because breakouts often trigger at elevated/ depressed RSI levels
        entry_ok = True
        rsi_v = row.get('rsi', 50)
        if direction == "BUY" and rsi_v > 75:
            entry_ok = False
        elif direction == "SELL" and rsi_v < 25:
            entry_ok = False
        
        # Volume confirmation — only reject if we have enough data to compute a baseline
        volume = row.get('volume', 0)
        avg_volume = row.get('avg_volume', 0)
        # Compute rolling avg volume from history if available
        if avg_volume is None or avg_volume <= 0:
            if history_df is not None and 'volume' in history_df.columns and len(history_df) >= 20:
                avg_volume = history_df['volume'].tail(20).mean()
        # Threshold relaxed from 0.5 to 0.3: avoid false rejection in low-vol periods
        if avg_volume is not None and avg_volume > 0 and volume > 0 and volume / avg_volume < 0.08:
            entry_ok = False
        
        # Dynamic sizing based on recent performance (not min_win_rate gating)
        # DO NOT gate trades by raising dyn_min — position sizing already handles risk.
        # Gating trades during cold starts creates a paradox: you can't improve WR without taking trades.
        dyn_min = self.min_win_rate
        death_spiral_risk_mult = 1.0  # Position size multiplier when on a losing streak
        try:
            import database as _db2
            recent_trades = _db2.load_trades()
            recent_n = min(len(recent_trades), 20)
            if recent_n >= 3:
                wins = sum(1 for t in recent_trades[-recent_n:] if t.get('pnl', 0) > 0)
                wr = wins / recent_n
                # ONLY adjust position size — never gate trades with dyn_min.
                # The cold-start paradox: a 10-trade bot with 10% WR needs to trade to improve.
                # Gating all trades prevents any path to profitability.
                if wr < 0.3:
                    death_spiral_risk_mult = 0.25  # Micro-sizing on cold streak (was 0.4)
                elif wr < 0.5:
                    death_spiral_risk_mult = 0.5  # Half-size on choppy streak (was 0.7)
                elif wr > 0.7:
                    death_spiral_risk_mult = 1.15  # Slight increase when crushing it
        except:
            pass
        
        # Apply death spiral position size reduction
        final_fraction = final_fraction * death_spiral_risk_mult
        
        # Ensure minimum allocation for small accounts (at least 2.5% = $5 on $200)
        # Prevents cold-start paradox where sizing rounds to zero
        if final_fraction < 0.025 and final_fraction > 0 and p_win >= 0.40 and ev > 0:
            final_fraction = 0.025
        
        # Cold-start override: relax dyn_min for accounts with < 20 trades
        # Small samples produce unreliable WR; need trades to gather data
        actual_dyn_min = dyn_min
        try:
            import database as _db3
            ct = _db3.load_trades()
            if len(ct) < 20:
                actual_dyn_min = max(0.35, dyn_min * 0.70)  # relaxed for trading
        except:
            pass
        
        is_viable = (p_win >= actual_dyn_min) and (ev > 0) and (final_fraction > 0) and entry_ok
        
        return {
            "direction": direction,
            "entry_price": float(price),
            "take_profit": float(tp),
            "stop_loss": float(sl),
            "risk_reward_ratio": float(risk_reward_ratio),
            "win_probability": float(p_win),
            "expected_value": float(ev),
            "kelly_fraction": float(final_fraction),
            "is_viable": bool(is_viable)
        }
