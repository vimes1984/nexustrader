import numpy as np
from sklearn.ensemble import RandomForestClassifier
import logging
from collections import defaultdict

class TradingStrategy:
    def __init__(self, name):
        self.name = name

    def generate_signal(self, row, history=None):
        """Generates a signal: 1.0 (Buy), -1.0 (Sell), or 0.0 (Hold)."""
        raise NotImplementedError

class EMACrossoverStrategy(TradingStrategy):
    def __init__(self, fast_window=12, slow_window=26):
        super().__init__("EMA Crossover")
        self.regime = "trend"
        self.fast_window = fast_window
        self.slow_window = slow_window

    def generate_signal(self, row, history=None):
        macd = row.get('macd', 0)
        macd_signal = row.get('macd_signal', 0)
        
        # Simple crossover: MACD crosses signal line
        if macd > macd_signal:
            return 1.0
        elif macd < macd_signal:
            return -1.0
        return 0.0

class RSIStrategy(TradingStrategy):
    def __init__(self, oversold=35, overbought=65):
        super().__init__("RSI Reversion")
        self.regime = "mean_reversion"
        self.default_oversold = oversold
        self.default_overbought = overbought

    def generate_signal(self, row, history=None):
        import database
        oversold = float(database.load_setting("opt_rsi_oversold", str(self.default_oversold)))
        overbought = float(database.load_setting("opt_rsi_overbought", str(self.default_overbought)))
        rsi = row.get('rsi', 50)
        if rsi < oversold:
            return 1.0  # Oversold -> Buy
        elif rsi > overbought:
            return -1.0  # Overbought -> Sell
        return 0.0

class BollingerBandsStrategy(TradingStrategy):
    def __init__(self):
        super().__init__("BB Breakout")
        self.regime = "mean_reversion"

    def generate_signal(self, row, history=None):
        close = row.get('close', 0)
        lower = row.get('bb_lower', 0)
        upper = row.get('bb_upper', 0)
        
        if close < lower:
            return 1.0  # Price broke below lower band -> expectation of bounce buy
        elif close > upper:
            return -1.0  # Price broke above upper band -> overextended sell
        return 0.0

class KalmanTrendStrategy(TradingStrategy):
    def __init__(self):
        super().__init__("Kalman Filter Trend")
        self.regime = "trend"
        from quant_utils import KalmanFilterPrice
        self.kf = KalmanFilterPrice(process_variance=1e-5, measurement_variance=1e-2)

    def generate_signal(self, row, history=None):
        import database
        close = row.get('close', 0)
        kf_price = self.kf.update(close)
        
        # Load optimized threshold parameter (default to 0.001 / 0.1%)
        threshold = float(database.load_setting("opt_kalman_threshold", "0.001"))
        
        # Kalman crossover signal with trend confirmation filter
        if close > kf_price * (1.0 + threshold):
            return 1.0  # Price above Kalman line -> Buy Trend
        elif close < kf_price * (1.0 - threshold):
            return -1.0  # Price below Kalman line -> Sell Trend
        return 0.0

class PsychologicalSweepStrategy(TradingStrategy):
    def __init__(self):
        super().__init__("Psych Liquidity Sweep")
        self.regime = "mean_reversion"

    def generate_signal(self, row, history=None):
        # We need historical rows to detect swing high/low sweeps
        if history is None or len(history) < 25:
            return 0.0
        
        from quant_utils import detect_psychological_sweep
        # Check sweep using last 24 periods
        return detect_psychological_sweep(history, lookback=24)

class MLPredictorStrategy(TradingStrategy):
    def __init__(self, lookahead=5):
        super().__init__("ML Random Forest")
        self.regime = "predictive"
        self.lookahead = lookahead
        self.model = RandomForestClassifier(n_estimators=50, max_depth=5, random_state=42)
        self.is_trained = False

    def train(self, df):
        """Trains a random forest model on historical technical features."""
        if len(df) < 50:
            logging.warning("Not enough data to train ML Strategy.")
            return
        
        # Features: RSI, MACD, MACD Signal, SMA/Close ratios
        features = []
        labels = []
        
        df_clean = df.copy()
        # Define target: close in N periods is higher than current close
        df_clean['target'] = (df_clean['close'].shift(-self.lookahead) > df_clean['close']).astype(int)
        df_clean = df_clean.dropna()

        if len(df_clean) < 30:
            return

        X = self._extract_features(df_clean)
        y = df_clean['target'].values

        self.model.fit(X, y)
        self.is_trained = True
        logging.info("ML Strategy trained successfully.")

    def _extract_features(self, df):
        # Create normalized features
        rsi = df['rsi'].values
        macd = df['macd'].values
        macd_sig = df['macd_signal'].values
        
        # Avoid division by zero
        close = df['close'].values + 1e-9
        sma_20_ratio = df['sma_20'].values / close
        sma_50_ratio = df['sma_50'].values / close
        bb_upper_ratio = df['bb_upper'].values / close
        bb_lower_ratio = df['bb_lower'].values / close
        
        return np.column_stack([
            rsi, macd, macd_sig, sma_20_ratio, sma_50_ratio, bb_upper_ratio, bb_lower_ratio
        ])

    def generate_signal(self, row, history=None):
        if not self.is_trained:
            return 0.0
        
        close = row.get('close', 1e-9)
        feat = np.array([[
            row.get('rsi', 50),
            row.get('macd', 0),
            row.get('macd_signal', 0),
            row.get('sma_20', close) / close,
            row.get('sma_50', close) / close,
            row.get('bb_upper', close) / close,
            row.get('bb_lower', close) / close
        ]])
        
        # Predict probability of upward movement
        try:
            prob = self.model.predict_proba(feat)[0][1]
            if prob > 0.58:
                return 1.0
            elif prob < 0.42:
                return -1.0
        except Exception as e:
            logging.error(f"Error generating ML signal: {e}")
        return 0.0

class NewsSentimentStrategy(TradingStrategy):
    def __init__(self):
        super().__init__("News Sentiment")
        self.regime = "predictive"

    def generate_signal(self, row, history_df=None):
        sentiment = float(row.get("sentiment", 0.0))
        if sentiment >= 0.15:
            return 1.0
        elif sentiment <= -0.15:
            return -1.0
        return 0.0

class MACDHistogramCrossoverStrategy(TradingStrategy):
    def __init__(self):
        super().__init__("MACD Histogram Crossover")
        self.regime = "trend"

    def generate_signal(self, row, history=None):
        macd_hist = row.get('macd_hist', 0)
        if macd_hist > 0:
            return 1.0
        elif macd_hist < 0:
            return -1.0
        return 0.0

class MeanReversionZScoreStrategy(TradingStrategy):
    def __init__(self, entry_threshold=2.0):
        super().__init__("Mean Reversion Z-Score")
        self.regime = "mean_reversion"
        self.entry_threshold = entry_threshold

    def generate_signal(self, row, history=None):
        close = row.get('close', 0)
        bb_mid = row.get('bb_mid', close)
        bb_std = row.get('bb_std', 0)
        if bb_std <= 0:
            return 0.0
        z_score = (close - bb_mid) / bb_std
        if z_score < -self.entry_threshold:
            return 1.0
        elif z_score > self.entry_threshold:
            return -1.0
        return 0.0

class VWAPCrossoverStrategy(TradingStrategy):
    def __init__(self):
        super().__init__("VWAP Crossover")
        self.regime = "trend"

    def generate_signal(self, row, history=None):
        close = row.get('close', 0)
        vwap = row.get('vwma_20', close)
        if close > vwap * 1.0005:
            return 1.0
        elif close < vwap * 0.9995:
            return -1.0
        return 0.0

class ATRBreakoutStrategy(TradingStrategy):
    def __init__(self, multiplier=1.5):
        super().__init__("ATR Breakout")
        self.regime = "trend"
        self.multiplier = multiplier

    def generate_signal(self, row, history=None):
        close = row.get('close', 0)
        sma = row.get('sma_20', close)
        atr = row.get('atr', 0)
        if atr <= 0:
            return 0.0
        upper_band = sma + self.multiplier * atr
        lower_band = sma - self.multiplier * atr
        if close > upper_band:
            return 1.0
        elif close < lower_band:
            return -1.0
        return 0.0

class StochasticOscillatorStrategy(TradingStrategy):
    def __init__(self, overbought=80, oversold=20):
        super().__init__("Stochastic Reversion")
        self.regime = "mean_reversion"
        self.overbought = overbought
        self.oversold = oversold

    def generate_signal(self, row, history=None):
        stoch_k = row.get('stoch_k', 50)
        stoch_d = row.get('stoch_d', 50)
        if stoch_k < self.oversold and stoch_k > stoch_d:
            return 1.0
        elif stoch_k > self.overbought and stoch_k < stoch_d:
            return -1.0
        return 0.0

class StrategyEnsemble:
    def __init__(self, history_df=None):
        self.strategies = [
            EMACrossoverStrategy(),
            MLPredictorStrategy(),
            KalmanTrendStrategy(),
            MACDHistogramCrossoverStrategy(),
            VWAPCrossoverStrategy(),
            ATRBreakoutStrategy()
        ]
        
        # Initialize strategy weights equally
        self.weights = np.ones(len(self.strategies)) / len(self.strategies)
        
        # Keep track of recent close prices to estimate the Ornstein-Uhlenbeck process parameters
        self.price_history = []
        
        # Performance tracker: each strategy's recent directional accuracy
        self.strategy_performance = defaultdict(list)
        
        # Train ML strategy if history is provided
        if history_df is not None:
            self.train_ml_strategy(history_df)
            self.price_history = list(history_df['close'].values[-60:])

    def record_trade_outcome(self, strategy_signals, trade_direction, pnl_percent):
        """Records trade outcome for each strategy's performance tracker.
        
        Called after a trade closes. Feeds back which strategies were right/wrong
        so future weightings can favor winning strategies.
        """
        if not strategy_signals or not trade_direction:
            return
        dir_val = 1.0 if trade_direction == "BUY" else -1.0
        for i, strat in enumerate(self.strategies):
            if i < len(strategy_signals):
                sig = strategy_signals[i]
                # Strategy is "correct" if signal direction matches trade direction
                correct = (sig * dir_val) > 0
                self.strategy_performance[strat.name].append({
                    'correct': bool(correct),
                    'signal': float(sig),
                    'direction': trade_direction,
                    'pnl_pct': pnl_percent
                })
                # Keep rolling window of 50 trades
                if len(self.strategy_performance[strat.name]) > 50:
                    self.strategy_performance[strat.name].pop(0)

    def train_ml_strategy(self, history_df):
        for strat in self.strategies:
            if isinstance(strat, MLPredictorStrategy):
                strat.train(history_df)

    def get_weighted_signal(self, row, history_df=None):
        """Calculates the weighted ensemble signal with performance-biased weighting.
        
        1. OU process regime detection (trending vs mean-reverting)
        2. Base weights from policy network
        3. Performance boost: strategies with >60% recent accuracy get boosted
        4. Weighted average of signals
        """
        # Append current close to history
        close = row.get('close')
        if close is not None:
            self.price_history.append(float(close))
            if len(self.price_history) > 100:
                self.price_history.pop(0)

        # Generate individual signals
        signals = []
        for strat in self.strategies:
            sig = strat.generate_signal(row, history_df)
            signals.append(sig)
        
        signals = np.array(signals)
        
        # Compute active weights starting from policy network weights
        active_weights = np.array(self.weights)
        
        # Layer 1: OU Regime Detection (trending vs mean-reverting)
        from quant_utils import estimate_ou_process
        if len(self.price_history) >= 20:
            theta, mu, is_mr = estimate_ou_process(self.price_history)
            regime_strength = min(abs(theta) * 5.0, 1.5)
            
            if is_mr and theta > 0.05:
                # Mean-Reversion Regime: boost mean-reversion, suppress trend
                for i, strat in enumerate(self.strategies):
                    regime = getattr(strat, 'regime', None)
                    if regime == 'mean_reversion':
                        active_weights[i] *= 1.0 + 0.3 * regime_strength
                    elif regime == 'trend':
                        active_weights[i] *= 1.0 - 0.4 * regime_strength
            else:
                # Trend Regime: boost trend, suppress mean-reversion
                for i, strat in enumerate(self.strategies):
                    regime = getattr(strat, 'regime', None)
                    if regime == 'trend':
                        active_weights[i] *= 1.0 + 0.3 * regime_strength
                    elif regime == 'mean_reversion':
                        active_weights[i] *= 1.0 - 0.4 * regime_strength
        
        # Layer 2: Recent Performance Biasing
        for i, strat in enumerate(self.strategies):
            perf = self.strategy_performance.get(strat.name, [])
            if len(perf) >= 10:
                recent = perf[-20:]
                win_rate = sum(1 for r in recent if r['correct']) / len(recent)
                if win_rate > 0.60:
                    active_weights[i] *= 1.0 + (win_rate - 0.60) * 1.5
                elif win_rate < 0.35 and len(perf) >= 20:
                    active_weights[i] *= 1.0 - (0.35 - win_rate) * 2.0
        
        # Normalize
        weight_sum = np.sum(active_weights)
        if weight_sum > 0:
            active_weights = active_weights / weight_sum
        
        # Weighted signal
        # Handle weight migration if saved weights are from old 12-strategy system
        if len(active_weights) != len(signals):
            import logging as _log
            _log.debug(f"[MIGRATION] Weights {len(active_weights)} vs strategies {len(signals)} — truncating")
            active_weights = active_weights[:len(signals)] if len(active_weights) > len(signals) else np.pad(active_weights, (0, len(signals) - len(active_weights)), constant_values=1.0/len(signals))
            s = np.sum(active_weights)
            active_weights = active_weights / s if s > 0 else np.ones(len(signals)) / len(signals)
        
        weighted_signal = np.dot(active_weights, signals)
        
        # Strategy breakdown for transparency/logging
        breakdown = {
            self.strategies[i].name: {
                "signal": float(signals[i]),
                "weight": float(active_weights[i])
            } for i in range(len(self.strategies))
        }
        
        return float(weighted_signal), breakdown
