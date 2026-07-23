import numpy as np
from sklearn.ensemble import RandomForestClassifier
import logging
import math
from collections import defaultdict
import database

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
        # Check for actual EMA values in the row first
        # Row may contain pre-computed ema_fast / ema_slow from data ingestion
        close = row.get('close', 0)
        ema_fast = row.get('ema_fast', None)
        ema_slow = row.get('ema_slow', None)
        
        if ema_fast is not None and ema_slow is not None and ema_slow > 0:
            # True EMA crossover
            if ema_fast > ema_slow:
                return 1.0
            elif ema_fast < ema_slow:
                return -1.0
            return 0.0
        
        # Fallback: MACD line is EMA(12) - EMA(26), so MACD crossing zero
        # is equivalent to EMA fast crossing EMA slow
        macd = row.get('macd', 0)
        # Guard against None / non-numeric MACD
        if macd is None:
            macd = 0
        # Use MACD crossing zero = EMA crossover
        if macd > 0:
            return 1.0
        elif macd < 0:
            return -1.0
        return 0.0

class RSIStrategy(TradingStrategy):
    def __init__(self, oversold=35, overbought=65):
        super().__init__("RSI Reversion")
        self.regime = "mean_reversion"
        self.default_oversold = oversold
        self.default_overbought = overbought
        # Cache optimized thresholds to avoid DB query per signal
        self._cached_oversold = None
        self._cached_overbought = None

    def _refresh_cache(self):
        """Called externally when optimization settings change."""
        self._cached_oversold = float(database.load_setting("opt_rsi_oversold", str(self.default_oversold)))
        self._cached_overbought = float(database.load_setting("opt_rsi_overbought", str(self.default_overbought)))

    def generate_signal(self, row, history=None):
        if self._cached_oversold is None:
            self._refresh_cache()
        oversold = self._cached_oversold
        overbought = self._cached_overbought
        rsi = row.get('rsi', 50)
        if rsi is None:
            rsi = 50
        try:
            rsi = float(rsi)
        except (ValueError, TypeError):
            rsi = 50
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
        if close is None:
            close = 0
        lower = row.get('bb_lower', 0)
        if lower is None:
            lower = 0
        upper = row.get('bb_upper', 0)
        if upper is None:
            upper = 0
        
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
        self._cached_threshold = None

    def _refresh_cache(self):
        self._cached_threshold = float(database.load_setting("opt_kalman_threshold", "0.001"))

    def generate_signal(self, row, history=None):
        close = row.get('close', 0)
        if close is None:
            close = 0
        kf_price = self.kf.update(close)
        
        if self._cached_threshold is None:
            self._refresh_cache()
        threshold = self._cached_threshold
        
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
        # Create normalized features — operate on a COPY to avoid mutating caller's data
        df_copy = df.copy()
        
        rsi = df_copy['rsi'].values
        macd = df_copy['macd'].values
        macd_sig = df_copy['macd_signal'].values
        
        # Avoid division by zero
        close = df_copy['close'].values + 1e-9
        close_series = df_copy['close']
        # Compute rolling SMAs if not already present
        if 'sma_20' not in df_copy.columns:
            df_copy['sma_20'] = df_copy['close'].rolling(20).mean()
        if 'sma_50' not in df_copy.columns:
            df_copy['sma_50'] = df_copy['close'].rolling(50).mean()
        sma_20_ratio = df_copy['sma_20'].fillna(close_series).values / close
        sma_50_ratio = df_copy['sma_50'].fillna(close_series).values / close
        bb_upper_ratio = df_copy['bb_upper'].values / close
        bb_lower_ratio = df_copy['bb_lower'].values / close
        
        return np.column_stack([
            rsi, macd, macd_sig, sma_20_ratio, sma_50_ratio, bb_upper_ratio, bb_lower_ratio
        ])

    def generate_signal(self, row, history=None):
        if not self.is_trained:
            return 0.0
        
        close = row.get('close', 1e-9)
        # Compute rolling SMA from history if available (row keys may not have them)
        sma_20 = row.get('sma_20', None)
        sma_50 = row.get('sma_50', None)
        if sma_20 is None and history is not None and len(history) >= 20:
            sma_20 = np.mean([h.get('close', close) for h in history[-20:]])
        if sma_50 is None and history is not None and len(history) >= 50:
            sma_50 = np.mean([h.get('close', close) for h in history[-50:]])
        sma_20 = sma_20 or close
        sma_50 = sma_50 or close
        
        feat = np.array([[
            row.get('rsi', 50),
            row.get('macd', 0),
            row.get('macd_signal', 0),
            sma_20 / close,
            sma_50 / close,
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
        sent_val = row.get("sentiment", 0.0)
        if sent_val is None:
            sent_val = 0.0
        try:
            sentiment = float(sent_val)
        except (ValueError, TypeError):
            sentiment = 0.0
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
        if macd_hist is None:
            macd_hist = 0
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
        # Guard against near-zero std dev (e.g., flat price, minimal data)
        if bb_std <= 1e-9:
            return 0.0
        z_score = (close - bb_mid) / bb_std
        # Clip z-score to prevent overflow from extreme values
        z_score = np.clip(z_score, -10.0, 10.0)
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
        if close is None:
            close = 0
        vwap = row.get('vwma_20', close)
        if vwap is None:
            vwap = close
        # Use ATR-adaptive threshold instead of flat 0.15%
        # Threshold = max(0.10%, ATR/close * 0.5) — adjusts to volatility regime
        atr = row.get('atr', 0)
        pct_atr = (atr / close) * 0.5 if atr > 0 and close > 0 else 0.0015
        threshold = max(pct_atr, 0.0010)  # floor at 0.10% to avoid noise in ultra-low vol
        if close > vwap * (1.0 + threshold):
            return 1.0
        elif close < vwap * (1.0 - threshold):
            return -1.0
        return 0.0

class ATRBreakoutStrategy(TradingStrategy):
    def __init__(self, multiplier=1.5):
        super().__init__("ATR Breakout")
        self.regime = "trend"
        self.multiplier = multiplier

    def generate_signal(self, row, history=None):
        close = row.get('close', 0)
        if close is None:
            close = 0
        sma = row.get('sma_20', close)
        if sma is None:
            sma = close
        atr = row.get('atr', 0)
        if atr is None:
            atr = 0
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
            RSIStrategy(),
            BollingerBandsStrategy(),
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
        Stored data is used for IC tracking, alpha decay, and weight updates.
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
                # Keep rolling window of 50 trades (larger window for IC stability)
                if len(self.strategy_performance[strat.name]) > 100:
                    self.strategy_performance[strat.name].pop(0)
    
    def compute_information_coefficient(self, lookback: int = 30) -> dict:
        """Compute the Information Coefficient (IC) for each strategy.
        
        IC = Spearman rank correlation between signal magnitude and actual pnl_pct.
        A positive IC means the strategy's signal strength correctly ranks outcomes.
        
        Also tracks over time: returns a time series of IC for decay analysis.
        """
        results = {}
        for strat in self.strategies:
            perf = self.strategy_performance.get(strat.name, [])
            if len(perf) < 10:
                results[strat.name] = {
                    "ic": 0.0,
                    "ic_rank": 0.0,
                    "hit_rate": 0.0,
                    "n_obs": 0,
                }
                continue
            
            recent = perf[-lookback:]
            signals = np.array([p['signal'] for p in recent], dtype=np.float64)
            pnls = np.array([p['pnl_pct'] for p in recent], dtype=np.float64)
            hits = np.array([1.0 if p['correct'] else 0.0 for p in recent], dtype=np.float64)
            
            n = len(signals)
            if n < 5:
                continue
            
            # Pearson IC: correlation between signal and pnl
            sig_std = np.std(signals)
            pnl_std = np.std(pnls)
            if sig_std > 1e-12 and pnl_std > 1e-12:
                sig_d = signals - np.mean(signals)
                pnl_d = pnls - np.mean(pnls)
                ic_pearson = float(np.sum(sig_d * pnl_d) / (n * sig_std * pnl_std))
                ic_pearson = float(np.clip(ic_pearson, -1.0, 1.0))
            else:
                ic_pearson = 0.0
            
            # Rank IC (Spearman): more robust to outliers
            sig_ranks = np.argsort(np.argsort(signals))
            pnl_ranks = np.argsort(np.argsort(pnls))
            if np.std(sig_ranks) > 0 and np.std(pnl_ranks) > 0:
                sr = sig_ranks - np.mean(sig_ranks)
                pr = pnl_ranks - np.mean(pnl_ranks)
                ic_spearman = float(
                    np.sum(sr * pr) / (n * np.std(sig_ranks) * np.std(pnl_ranks))
                )
                ic_spearman = float(np.clip(ic_spearman, -1.0, 1.0))
            else:
                ic_spearman = 0.0
            
            hit_rate = float(np.mean(hits))
            
            results[strat.name] = {
                "ic": round(ic_pearson, 4),
                "ic_rank": round(ic_spearman, 4),
                "hit_rate": round(hit_rate, 4),
                "n_obs": n,
            }
        return results

    def get_ic_report(self) -> str:
        """Return a human-readable report of Information Coefficient per strategy."""
        ic_data = self.compute_information_coefficient()
        lines = ["### Information Coefficient per Strategy"]
        for sname, d in ic_data.items():
            if d['n_obs'] > 0:
                lines.append(
                    f"  {sname}: IC(pearson)={d['ic']:.4f}, IC(rank)={d['ic_rank']:.4f}, "
                    f"hit_rate={d['hit_rate']:.2%}, n={d['n_obs']}"
                )
            else:
                lines.append(f"  {sname}: no data")
        return "\n".join(lines)

    def train_ml_strategy(self, history_df):
        for strat in self.strategies:
            if isinstance(strat, MLPredictorStrategy):
                strat.train(history_df)

    # ------------------------------------------------------------------
    # Alpha decay / signal half-life estimation
    # ------------------------------------------------------------------

    def estimate_alpha_decay(self, lookback: int = 50) -> dict:
        """Estimate the half-life of each strategy's predictive signal by
        computing the autocorrelation of recent correct/incorrect labels.
        
        The Information Coefficient (IC) at lag k is approximated by the
        autocorrelation of the binary correctness series.  Half-life is
        the lag at which autocorrelation decays below 0.5.
        
        Returns:
            dict: {strategy_name: {"half_life": int, "ic_1": float, "ic_decay": float}}
        """
        results = {}
        for strat in self.strategies:
            perf = self.strategy_performance.get(strat.name, [])
            if len(perf) < 10:
                results[strat.name] = {"half_life": 1, "ic_1": 0.0, "ic_decay": 0.0}
                continue
            
            # Convert correct/incorrect to 1/0 series
            series = np.array([1.0 if p['correct'] else 0.0 for p in perf[-lookback:]])
            n = len(series)
            if n < 5:
                results[strat.name] = {"half_life": 1, "ic_1": 0.0, "ic_decay": 0.0}
                continue
            
            mean_s = np.mean(series)
            demeaned = series - mean_s
            var_s = np.sum(demeaned ** 2)
            if var_s < 1e-12:
                results[strat.name] = {"half_life": 1, "ic_1": 0.0, "ic_decay": 0.0}
                continue
            
            # Autocorrelation at lag 1
            acf_1 = np.sum(demeaned[:-1] * demeaned[1:]) / var_s
            acf_1 = float(np.clip(acf_1, -1.0, 1.0))
            
            # Autocorrelation at lag 2 (multi-step decay)
            if n >= 3:
                acf_2 = np.sum(demeaned[:-2] * demeaned[2:]) / var_s
                acf_2 = float(np.clip(acf_2, -1.0, 1.0))
            else:
                acf_2 = 0.0
            
            # Half-life: lag at which ACF crosses 0.5 via exponential decay model
            # If ACF(1) > 0.5, half-life = log(0.5) / log(acf_1), rounded up
            if acf_1 > 0.5:
                half_life = max(1, int(math.ceil(math.log(0.5) / math.log(acf_1))))
            elif acf_1 > 0.0:
                half_life = 1
            else:
                half_life = 0  # negative autocorrelation = no persistence
            
            # Decay rate: how fast IC drops from lag 1 to lag 2
            decay = acf_1 - acf_2 if acf_1 > 0 else 0.0
            
            results[strat.name] = {
                "half_life": half_life,
                "ic_1": round(acf_1, 4),
                "ic_decay": round(decay, 4)
            }
        return results

    def get_alpha_decay_report(self) -> str:
        """Return a human-readable report of alpha decay per strategy."""
        decay = self.estimate_alpha_decay()
        lines = ["### Alpha Decay / Signal Half-Life Estimation"]
        for sname, d in decay.items():
            lines.append(f"  {sname}: half-life={d['half_life']} bars, IC(1)={d['ic_1']:.4f}, decay={d['ic_decay']:.4f}")
        return "\n".join(lines)

    def update_base_weights(self):
        """Persists performance-biased weights back to self.weights after each trade.
        
        This ensures the weight decay/boost from trade outcomes is remembered
        across calls, not recomputed fresh each time from equal weights.
        """
        active = np.array(self.weights)
        
        for i, strat in enumerate(self.strategies):
            perf = self.strategy_performance.get(strat.name, [])
            if len(perf) >= 10:
                recent = perf[-20:]
                win_rate = sum(1 for r in recent if r['correct']) / len(recent)
                # Moderate exponential adjustment: max ±20% per update
                adjustment = 1.0
                if win_rate > 0.60:
                    adjustment = 1.0 + min((win_rate - 0.60) * 0.5, 0.20)
                elif win_rate < 0.40 and len(perf) >= 15:
                    adjustment = 1.0 - min((0.40 - win_rate) * 0.5, 0.20)
                active[i] *= adjustment
        
        # Normalize
        s = np.sum(active)
        if s > 0:
            active = active / s
        
        # Exponential smoothing: blend 70% old, 30% new to prevent oscillation
        self.weights = self.weights * 0.7 + active * 0.3
        # Re-normalize after blend
        s = np.sum(self.weights)
        if s > 0:
            self.weights = self.weights / s

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
            # Guard against NaN or None signals from strategies
            if sig is None or (isinstance(sig, float) and sig != sig):
                sig = 0.0
            signals.append(sig)
        
        signals = np.array(signals, dtype=np.float64)
        
        # Compute active weights starting from performance-updated base weights
        active_weights = np.array(self.weights)
        
        # NEWER: Ensure active_weights matches signals length BEFORE any indexing loops.
        # Policy network may output different action_dim than current strategy count.
        if len(active_weights) != len(signals):
            import logging as _log
            _log.warning(f"[MIGRATION] Weights {len(active_weights)} vs strategies {len(signals)} — resizing")
            active_weights = active_weights[:len(signals)] if len(active_weights) > len(signals) else np.pad(active_weights, (0, len(signals) - len(active_weights)), constant_values=1.0/len(signals))
            s = np.sum(active_weights)
            active_weights = active_weights / s if s > 0 else np.ones(len(signals)) / len(signals)
        
        # Layer 1: OU Regime Detection (trending vs mean-reverting vs chop)
        from quant_utils import estimate_ou_process
        if len(self.price_history) >= 20:
            theta, mu, is_mr = estimate_ou_process(self.price_history)
            
            # Chop index: volatility clustering / trend strength quantification
            # When abs(theta) is very small, price follows random walk (chop)
            # When theta is moderately positive → mean-reversion
            # When theta is near zero or negative → trending regime
            # A chop zone exists when theta is near zero AND vol is normal
            recent_rets = np.diff(self.price_history[-20:]) / np.array(self.price_history[-20:-1])
            chop_vol = float(np.std(recent_rets)) if len(recent_rets) > 1 else 0.0
            # Chop index: low when trend is strong, high when noise dominates
            if chop_vol > 0:
                price_range = max(self.price_history[-20:]) - min(self.price_history[-20:])
                mean_price = np.mean(self.price_history[-20:])
                chop_idx = chop_vol / (price_range / max(mean_price, 1e-9)) if price_range > 1e-9 else 1.0
            else:
                chop_idx = 1.0
            is_chop = abs(theta) < 0.02 and chop_idx > 0.6
            
            if is_mr and theta > 0.03 and not is_chop:
                # Mean-Reversion Regime: boost mean-reversion, suppress trend
                real_mr_strength = min((theta - 0.03) / 0.05, 1.5)
                for i, strat in enumerate(self.strategies):
                    regime = getattr(strat, 'regime', None)
                    if regime == 'mean_reversion':
                        active_weights[i] *= 1.0 + 0.3 * real_mr_strength
                    elif regime == 'trend':
                        active_weights[i] *= max(1.0 - 0.5 * real_mr_strength, 0.1)
            elif is_chop:
                # Chop Regime: suppress all directional strategies, boost neutral/predictive
                for i, strat in enumerate(self.strategies):
                    regime = getattr(strat, 'regime', None)
                    if regime in ('mean_reversion', 'trend'):
                        active_weights[i] *= 0.5  # halve directional bets
                    elif regime == 'predictive':
                        active_weights[i] *= 1.2  # slight boost to ML/news signals
            else:
                # Trend Regime: boost trend, suppress mean-reversion
                trend_strength = min(abs(theta) * 3.0, 1.5) if abs(theta) > 0.001 else 0.5
                for i, strat in enumerate(self.strategies):
                    regime = getattr(strat, 'regime', None)
                    if regime == 'trend':
                        active_weights[i] *= 1.0 + 0.3 * trend_strength
                    elif regime == 'mean_reversion':
                        active_weights[i] *= max(1.0 - 0.5 * trend_strength, 0.1)
        
        # Layer 2: Signal Correlation Penalty — diversify correlated strategies
        # Compute pairwise signal correlation and penalize highly-correlated pairs
        # by reducing the weight of the lower-performing correlated strategy.
        n_strats = len(signals)
        if n_strats > 1 and np.any(signals != 0):
            sig_matrix = np.tile(signals, (n_strats, 1))
            # Pairwise dot-product similarity (direction agreement)
            sim = (sig_matrix == sig_matrix.T).astype(float)
            np.fill_diagonal(sim, 0.0)
            # Average similarity for each strategy (excluding self)
            avg_sim = sim.sum(axis=1) / max(n_strats - 1, 1)
            # Penalize strategies with > 50% signal overlap: reduce weight proportional to similarity
            for i in range(n_strats):
                if avg_sim[i] > 0.5:
                    overlap_penalty = 1.0 - (avg_sim[i] - 0.5)
                    active_weights[i] *= overlap_penalty
        
        # Normalize
        weight_sum = np.sum(active_weights)
        if weight_sum > 0:
            active_weights = active_weights / weight_sum
        
        # Weighted signal — active_weights length already guaranteed to match signals
        weighted_signal = np.dot(active_weights, signals)
        
        # Strategy breakdown for transparency/logging
        breakdown = {
            self.strategies[i].name: {
                "signal": float(signals[i]),
                "weight": float(active_weights[i])
            } for i in range(len(self.strategies))
        }
        
        return float(weighted_signal), breakdown
