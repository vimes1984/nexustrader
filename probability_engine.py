import numpy as np
import logging

class ProbabilityEngine:
    def __init__(self, kelly_fraction=0.1, min_win_rate=0.45):
        self.min_win_rate = min_win_rate
        self.set_risk_mode("conservative")

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

    def calculate_atr_bounds(self, price, atr, direction, tp_multiplier=2.5, sl_multiplier=1.5):
        """Calculates Volatility-Adjusted Take-Profit (TP) and Stop-Loss (SL) using ATR."""
        if atr is None or np.isnan(atr) or atr == 0:
            # Fallback to percentage-based bounds (1.5% TP, 1.0% SL)
            atr = price * 0.01

        sl_distance = atr * sl_multiplier
        tp_distance = atr * tp_multiplier

        if direction == "BUY":
            tp = price + tp_distance
            sl = price - sl_distance
        else: # SELL
            tp = price - tp_distance
            sl = price + sl_distance

        return float(tp), float(sl)

    def estimate_win_probability(self, weighted_signal, row, history_df=None):
        """Estimates the probability of a trade being successful (P_win).
        
        Uses signal strength and current market regime indicators (like RSI and ATR).
        If history_df is provided, performs a localized statistical check.
        """
        # Base probability mapping from weighted signal magnitude [0.0, 1.0]
        signal_magnitude = abs(weighted_signal)
        
        # Sigmoid scaling from signal strength: map [0, 1] to base win rate [0.45, 0.65]
        base_p = 0.5 + (signal_magnitude * 0.15)
        
        # Adjust based on RSI oversold/overbought extremity (mean-reversion support)
        rsi = row.get('rsi', 50)
        rsi_adjustment = 0.0
        
        if weighted_signal > 0:  # BUY
            if rsi < 30:
                rsi_adjustment = 0.05  # Oversold boosts buy success odds
            elif rsi > 70:
                rsi_adjustment = -0.05 # Overbought reduces buy success odds
        elif weighted_signal < 0:  # SELL
            if rsi > 70:
                rsi_adjustment = 0.05  # Overbought boosts sell success odds
            elif rsi < 30:
                rsi_adjustment = -0.05 # Oversold reduces sell success odds
                
        p_win = np.clip(base_p + rsi_adjustment, 0.35, 0.75)
        
        # Simple historical refinement if history is available
        if history_df is not None and len(history_df) > 50:
            try:
                # Find historical instances with similar signals
                similar_signals = history_df[
                    (history_df['rsi'].between(rsi - 10, rsi + 10))
                ]
                if len(similar_signals) > 10:
                    # Look at next-5-period forward returns
                    forward_returns = similar_signals['close'].shift(-5) > similar_signals['close']
                    hist_win_rate = forward_returns.mean()
                    # Blend 70% model / 30% empirical historical win rate
                    p_win = 0.7 * p_win + 0.3 * hist_win_rate
            except Exception as e:
                logging.error(f"Error in empirical odds estimation: {e}")

        return float(p_win)

    def evaluate_trade(self, price, atr, direction, weighted_signal, row, history_df=None):
        """Evaluates trade parameters including entry, SL, TP, Win Probability, EV, and size."""
        # 1. Calc SL/TP
        tp, sl = self.calculate_atr_bounds(price, atr, direction)
        
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
        risk_reward_ratio = reward / risk
        
        # 4. Calculate Expected Value (EV) per unit size
        ev = (p_win * reward) - ((1 - p_win) * risk)
        
        # 5. Position Sizing via Kelly Criterion
        # f* = p - (q / b) = p - (1-p)/R
        kelly_size = p_win - ((1.0 - p_win) / risk_reward_ratio)
        kelly_size = max(0.0, kelly_size)  # No negative sizes
        
        # Apply fractional Kelly
        final_fraction = kelly_size * self.kelly_fraction
        # Cap max position size based on risk profile
        final_fraction = min(final_fraction, self.max_cap)
        
        is_viable = (p_win >= self.min_win_rate) and (ev > 0) and (final_fraction > 0)
        
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
