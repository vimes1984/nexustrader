"""
historical_pipeline.py — Bulk download + simulated replay training pipeline

Phase 6: Builds a training dataset from Kraken 1h OHLCV candles,
replays them through the strategy ensemble, collects (state, alignment, reward)
training samples, and runs offline epoch-based policy gradient training.

Architecture:
  1. DataFetcher: downloads 1h candles from Kraken (up to 2 years)
  2. SimulatedTrader: replays candles through strategies, collects training data
  3. OfflineTrainer: epoch-based minibatch training on collected samples
  4. Pipeline orchestration: fetch → replay → train → save → deploy
"""

import numpy as np
import json
import logging
import time
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
_log = logging.getLogger("historical_pipeline")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TrainingSample:
    """A single training example for policy gradient."""
    state: np.ndarray          # feature vector or token sequence
    strategy_indices: List[int]  # which strategies were selected
    alignment: float            # how well the selected strat aligned with outcome [-1, 1]
    reward: float               # PnL realized from this decision
    ticker: str
    timestamp: str


@dataclass
class TrainingEpoch:
    """Results from one training epoch."""
    epoch: int
    samples: int
    avg_loss: float
    avg_reward: float
    policy_entropy: float       # higher = more exploration
    elapsed_sec: float


# ---------------------------------------------------------------------------
# 1. DataFetcher — Kraken historical candles
# ---------------------------------------------------------------------------

class DataFetcher:
    """Downloads 1h OHLCV candles from Kraken exchange via ccxt."""
    
    def __init__(self):
        import ccxt
        self.exchange = ccxt.kraken({'enableRateLimit': True})
    
    def fetch_candles(self, ticker: str, since_days: int = 730, 
                      limit: int = 720) -> List[Dict]:
        """Fetch 1h candles going back `since_days` days.
        
        Kraken returns max 720 candles per request, so we paginate.
        
        Args:
            ticker: e.g. 'BTC-USD' (converted to 'BTC/USD' for ccxt)
            since_days: How many days back to fetch (default 2 years)
            limit: Max candles per request (Kraken max = 720)
        
        Returns:
            List of OHLCV dicts sorted oldest→newest
        """
        symbol = ticker.replace('-', '/')
        since_ms = int((datetime.now() - timedelta(days=since_days)).timestamp() * 1000)
        
        all_candles = []
        current_since = since_ms
        
        _log.info(f"Fetching {symbol} 1h candles (up to {since_days}d back)...")
        
        while True:
            try:
                candles = self.exchange.fetch_ohlcv(
                    symbol, '1h', since=current_since, limit=limit
                )
                
                if not candles:
                    break
                
                # Filter out candles before our since_ms
                # (ccxt sometimes returns slightly earlier candles)
                valid = [c for c in candles if c[0] >= since_ms]
                if not valid and len(candles) < limit:
                    break
                
                all_candles.extend(valid or candles)
                
                # Advance since to after the last candle + 1ms
                current_since = candles[-1][0] + 1
                
                # If we got fewer than limit, we're done
                if len(candles) < limit:
                    break
                
                _log.debug(f"  {symbol}: {len(all_candles)} candles so far...")
                time.sleep(0.5)  # Rate limit courtesy
                
            except Exception as e:
                _log.error(f"Error fetching {symbol}: {e}")
                break
        
        # Deduplicate by timestamp
        seen = set()
        unique = []
        for c in all_candles:
            if c[0] not in seen:
                seen.add(c[0])
                unique.append(c)
        
        unique.sort(key=lambda c: c[0])
        
        # Convert to dict format
        result = []
        for c in unique:
            result.append({
                'timestamp': datetime.fromtimestamp(c[0] / 1000).isoformat(),
                'open': float(c[1]), 'high': float(c[2]),
                'low': float(c[3]), 'close': float(c[4]),
                'volume': float(c[5]),
            })
        
        _log.info(f"  {symbol}: {len(result)} candles fetched ({len(result)/24:.0f} days)")
        return result


# ---------------------------------------------------------------------------
# 2. SimulatedTrader — replay candles through strategies
# ---------------------------------------------------------------------------

class SimulatedTrader:
    """Replays historical candles through the strategy ensemble to collect
    training samples without touching live markets or real money.
    
    Uses look-ahead labeling: for each candle, computes the forward return
    over the next N candles as the reward signal. This generates one sample
    per candle (after warmup) instead of relying on sparse TP/SL hits.
    """
    
    def __init__(self, orchestrator, ticker: str, lookahead: int = 12):
        self.orc = orchestrator
        self.ticker = ticker
        self.lookahead = lookahead  # forward candles for reward calculation
        
        # Ensure ticker is initialized in the orchestrator before accessing ensembles
        ensembles = getattr(orchestrator, 'strategy_ensembles', {})
        if hasattr(orchestrator, 'init_ticker') and ticker not in ensembles:
            orchestrator.init_ticker(ticker)
        
        # Get the strategy ensemble and learning engine for this ticker
        self.ensemble = getattr(orchestrator, 'strategy_ensembles', {}).get(ticker)
        self.learner = (getattr(orchestrator, 'learning_engines', {}) or {}).get(ticker)
        
        # Simulated state
        self.balance = 1000.0
        self.closed_trades = []
        self.samples = []
        
        # Indicators buffer
        self.price_history = []
        self.indicator_buffer = []
        
    def add_indicator(self, row: Dict):
        """Pre-compute indicators for a candle row."""
        close = float(row['close'])
        self.price_history.append(close)
        
        # Keep last 50 candles for indicators
        if len(self.price_history) > 50:
            self.price_history.pop(0)
        
        # RSI (14-period) — EMA-like Wilder's smoothing
        # Uses exponential weighted average (alpha=1/14) not simple mean
        rsi = 50.0
        if len(self.price_history) >= 15:
            gains = []
            losses = []
            for i in range(-14, 0):
                delta = self.price_history[i] - self.price_history[i-1]
                gains.append(max(delta, 0))
                losses.append(max(-delta, 0))
            # First avg uses SMA, subsequent would use Wilder's EMA(alpha=1/14)
            # For single-shot computation, we approximate with SMA
            # (since we don't maintain running averages across candles)
            avg_gain = sum(gains) / 14
            avg_loss = sum(losses) / 14
            rs = avg_gain / (avg_loss + 1e-9)
            rsi = 100 - (100 / (1 + rs))
        
        # Simple MACD (12/26/9)
        macd = 0.0
        macd_signal = 0.0
        if len(self.price_history) >= 26:
            ema12 = self._ema(self.price_history, 12)
            ema26 = self._ema(self.price_history, 26)
            macd = ema12 - ema26
            
            # Signal line (9-period EMA of MACD)
            if not hasattr(self, '_macd_history'):
                self._macd_history = []
            self._macd_history.append(macd)
            macd_signal = self._ema(self._macd_history, 9) if len(self._macd_history) >= 9 else macd
            # Trim history to avoid unbounded growth
            if len(self._macd_history) > 20:
                self._macd_history = self._macd_history[-20:]
        
        macd_hist = macd - macd_signal
        
        # Bollinger Bands (20-period)
        bb_upper = close * 1.02
        bb_lower = close * 0.98
        if len(self.price_history) >= 20:
            recent = self.price_history[-20:]
            ma = sum(recent) / 20
            std = (sum((p - ma) ** 2 for p in recent) / 20) ** 0.5  # population std (Bollinger convention)
            bb_upper = ma + 2 * std
            bb_lower = ma - 2 * std
        
        # ATR (14-period) — simple SMA approximation
        # Store raw candle data for TR calculation (preserving high/low across calls)
        atr = close * 0.01
        if not hasattr(self, '_raw_candles'):
            self._raw_candles = []
        self._raw_candles.append({
            'high': float(row.get('high', close)),
            'low': float(row.get('low', close)),
            'close': close,
        })
        if len(self._raw_candles) >= 15:
            buf = self._raw_candles
            tr_values = []
            # Iterate over last 14 candles (buf[-14:])
            for j in range(-14, 0):
                c = buf[j]
                h, l = c['high'], c['low']
                # prev_c is the close of the candle BEFORE candle j
                prev_c = buf[j - 1]['close']  # candle j-1's close
                tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
                tr_values.append(tr)
            atr = sum(tr_values) / len(tr_values)
        
        # Trim to prevent unbounded growth
        if len(self._raw_candles) > 64:
            self._raw_candles = self._raw_candles[-50:]
        
        indicator = {
            'rsi': rsi,
            'macd': macd,
            'macd_hist': macd_hist,
            'macd_signal': macd_signal,
            'bb_upper': bb_upper,
            'bb_lower': bb_lower,
            'atr': atr,
            'close': close,
            'timestamp': row['timestamp'],
        }
        
        self.indicator_buffer.append(indicator)
        return indicator
    
    @staticmethod
    def _ema(prices: List[float], period: int) -> float:
        if len(prices) < period:
            return prices[-1]
        alpha = 2 / (period + 1)
        ema = prices[-period]
        for p in prices[-(period-1):]:
            ema = alpha * p + (1 - alpha) * ema
        return ema
    
    def simulate_trade(self, indicator: Dict, weighted_signal: float, 
                       strategy_breakdown: Dict, 
                       future_candles: List[Dict] = None) -> Optional[TrainingSample]:
        """Generate a training sample using look-ahead labeling.
        
        Instead of simulating live trades with TP/SL, this labels each candle
        by looking at the forward return over `lookahead` candles.
        
        Returns a TrainingSample with:
          - state: feature vector from this candle
          - strategy_indices: which strategies were active
          - alignment: whether signal direction matched actual outcome
          - reward: forward return (normalized)
        """
        if not future_candles or len(future_candles) < self.lookahead:
            return None
        
        close = indicator['close']
        
        # Compute forward return over lookahead candles
        future_close = future_candles[self.lookahead - 1]['close']
        forward_return = (future_close - close) / close
        
        # Normalize reward to [-1, 1] range via tanh
        reward = np.tanh(forward_return * 20)  # 5% move → ~0.76 reward
        
        # Alignment: did the signal direction match the forward return?
        if weighted_signal > 0 and forward_return > 0:
            alignment = min(1.0, abs(forward_return) * 10)   # Strong bullish signal + up = great
        elif weighted_signal < 0 and forward_return < 0:
            alignment = min(1.0, abs(forward_return) * 10)   # Strong bearish signal + down = great
        elif weighted_signal > 0 and forward_return < 0:
            alignment = -min(1.0, abs(forward_return) * 10)  # Bullish signal but down = wrong
        elif weighted_signal < 0 and forward_return > 0:
            alignment = -min(1.0, abs(forward_return) * 10)  # Bearish signal but up = wrong
        else:
            alignment = 0.0  # Flat signal or flat market
        
        # Build training sample
        state = self._build_state_vector(indicator)
        active_strategies = [
            i for i, (name, info) in enumerate(strategy_breakdown.items())
            if isinstance(info, dict) and abs(info.get('signal', 0)) > 0.01
        ]
        
        sample = TrainingSample(
            state=np.array(state),
            strategy_indices=active_strategies or [0],
            alignment=alignment,
            reward=reward,
            ticker=self.ticker,
            timestamp=indicator['timestamp'],
        )
        
        return sample
    
    def _build_state_vector(self, indicator: Dict) -> np.ndarray:
        """Build the 8-element state vector like LearningEngine.get_state_vector()."""
        close = indicator['close']
        rsi = (indicator['rsi'] - 50.0) / 50.0
        macd_norm = np.clip(indicator['macd_hist'] / close, -0.05, 0.05) * 20.0
        bb_range = indicator['bb_upper'] - indicator['bb_lower'] + 1e-9
        bb_pos = (close - indicator['bb_lower']) / bb_range - 0.5
        atr_ratio = np.clip(indicator['atr'] / close, 0.0, 0.1) * 10.0
        
        # Win trend from closed trades
        win_trend = 0.5
        if len(self.closed_trades) >= 5:
            recent = self.closed_trades[-10:]
            wins = sum(1 for t in recent if t['pnl'] > 0)
            win_trend = wins / len(recent)
        
        return np.array([0.0, 0.0, rsi, macd_norm, bb_pos, atr_ratio, win_trend, 0.0])


# ---------------------------------------------------------------------------
# 3. OfflineTrainer — epoch-based minibatch training
# ---------------------------------------------------------------------------

class OfflineTrainer:
    """Trains the policy network offline using collected historical samples.
    
    Unlike online training (one sample at a time), this runs multiple epochs
    over the full dataset with minibatch policy gradient, proper train/val split,
    and early stopping.
    """
    
    def __init__(self, learning_engine, val_split: float = 0.2,
                 batch_size: int = 32, epochs: int = 50,
                 early_stop_patience: int = 10):
        self.engine = learning_engine
        self.val_split = val_split
        self.batch_size = batch_size
        self.epochs = epochs
        self.early_stop_patience = early_stop_patience
        self.history: List[TrainingEpoch] = []
    
    def train(self, samples: List[TrainingSample]) -> List[TrainingEpoch]:
        """Run offline epoch-based training on collected samples.
        
        Args:
            samples: List of TrainingSample from SimulatedTrader
        
        Returns:
            List of TrainingEpoch records
        """
        if len(samples) < 50:
            _log.warning(f"Only {len(samples)} samples — need >= 50 for meaningful training")
            return []
        
        # Chronological split with embargo to prevent look-ahead leakage.
        # Samples are generated with look-ahead labeling (e.g., +12 candles forward),
        # so sample at time t contains information up to t+12.  Random shuffle would
        # leak future info into the training set.  We sort by timestamp, split
        # chronologically (~80/20), and apply an embargo of `self.lookahead` samples
        # to ensure no val sample's look-ahead window overlaps with train data.
        lookahead = getattr(getattr(self, 'engine', None), 'lookahead', 12)
        embargo = max(lookahead, 1)
        samples_sorted = sorted(samples, key=lambda s: s.timestamp)
        split_idx = int(len(samples_sorted) * (1 - self.val_split))
        # Apply embargo: val split starts at split_idx + embargo
        train_samples = samples_sorted[:split_idx]
        val_samples = samples_sorted[split_idx + embargo:]
        
        _log.info(f"Training on {len(train_samples)} samples, validating on {len(val_samples)} (embargo={embargo})")
        
        best_val_loss = float('inf')
        patience_counter = 0
        best_weights = None
        
        for epoch in range(1, self.epochs + 1):
            ep_start = time.time()
            
            # Train on minibatches — shuffle within train set is safe since
            # all train samples are before the embargo gap
            np.random.shuffle(train_samples)
            batch_losses = []
            batch_rewards = []
            batch_entropies = []
            
            for i in range(0, len(train_samples), self.batch_size):
                batch = train_samples[i:i + self.batch_size]
                loss, reward, entropy = self._train_batch(batch)
                batch_losses.append(loss)
                batch_rewards.append(reward)
                batch_entropies.append(entropy)
            
            avg_loss = float(np.mean(batch_losses))
            avg_reward = float(np.mean(batch_rewards))
            avg_entropy = float(np.mean(batch_entropies))
            elapsed = time.time() - ep_start
            
            ep_record = TrainingEpoch(
                epoch=epoch,
                samples=len(train_samples),
                avg_loss=avg_loss,
                avg_reward=avg_reward,
                policy_entropy=avg_entropy,
                elapsed_sec=elapsed,
            )
            self.history.append(ep_record)
            
            # Validation loss
            val_loss = self._compute_val_loss(val_samples) if val_samples else avg_loss
            
            if epoch % 5 == 0 or epoch == 1:
                _log.info(f"Epoch {epoch:3d}/{self.epochs} | loss={avg_loss:.4f} "
                         f"val_loss={val_loss:.4f} | reward={avg_reward:.3f} "
                         f"entropy={avg_entropy:.3f} | {elapsed:.1f}s")
            
            # Early stopping
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience_counter = 0
                best_weights = self._save_policy_state()
            else:
                patience_counter += 1
                if patience_counter >= self.early_stop_patience:
                    _log.info(f"Early stopping at epoch {epoch} (val_loss={val_loss:.4f})")
                    break
        
        # Restore best weights
        if best_weights:
            self._restore_policy_state(best_weights)
        
        _log.info(f"Training complete: {len(self.history)} epochs, best_val_loss={best_val_loss:.4f}")
        return self.history
    
    def _train_batch(self, batch: List[TrainingSample]) -> Tuple[float, float, float]:
        """Train on one minibatch using the policy network's own backward().
        
        The PolicyNetwork.backward(state, strategy_signals, trade_direction, reward)
        handles forward pass, gradient computation, and weight update internally.
        We adapt our training samples to match this interface.
        """
        if not batch:
            return 0.0, 0.0, 0.0
        
        action_dim = self.engine.policy_net.action_dim
        
        for sample in batch:
            # Build strategy_signals array matching action_dim
            # strategy_indices tells us which strategies were active
            strategy_signals = np.zeros(action_dim)
            for idx in sample.strategy_indices:
                if 0 <= idx < action_dim:
                    strategy_signals[idx] = sample.alignment
            
            # Reward: use alignment * |reward| as the training signal
            pnl_reward = sample.alignment * abs(sample.reward)
            
            # Trade direction: 1 for positive alignment, -1 for negative
            trade_direction = 1 if sample.alignment > 0 else (-1 if sample.alignment < 0 else 0)
            
            # Use the policy network's own training step
            self.engine.policy_net.backward(
                sample.state, 
                strategy_signals.tolist(), 
                trade_direction, 
                pnl_reward
            )
        
        # Compute metrics on the batch for logging (no separate forward needed)
        avg_reward = float(np.mean([s.reward for s in batch]))
        
        # Entropy estimate from a sample forward pass
        probs_all = self.engine.policy_net.forward(batch[0].state)
        entropy = float(-np.sum(probs_all * np.log(probs_all + 1e-8)))
        
        # We don't have per-step loss from the black-box backward(), so estimate
        avg_loss = 1.0 - abs(avg_reward)  # proxy: lower when rewards are stronger
        
        return avg_loss, avg_reward, entropy
    
    def _compute_val_loss(self, val_samples: List[TrainingSample]) -> float:
        """Compute validation loss as mean alignment error (no weight updates)."""
        if not val_samples:
            return 0.0
        total_err = 0.0
        for sample in val_samples:
            probs = self.engine.policy_net.forward(sample.state)
            # Expected probability mass on active strategies should correlate with alignment
            expected = max(0.0, sample.alignment)
            actual = sum(probs[idx] for idx in sample.strategy_indices if 0 <= idx < len(probs))
            total_err += abs(actual - expected)
        return total_err / len(val_samples)
    
    def _save_policy_state(self) -> str:
        """Export current policy network weights as JSON."""
        if hasattr(self.engine.policy_net, 'to_json'):
            return self.engine.policy_net.to_json()
        return ""
    
    def _restore_policy_state(self, json_str: str):
        """Restore policy network weights from JSON."""
        if hasattr(self.engine.policy_net, 'from_json') and json_str:
            self.engine.policy_net.from_json(json_str)
    
    def summary(self) -> Dict:
        """Return training summary as a dict for dashboard display."""
        if not self.history:
            return {'status': 'no_training'}
        
        last = self.history[-1]
        first = self.history[0]
        
        # Find best epoch
        best = min(self.history, key=lambda e: e.avg_loss)
        
        return {
            'status': 'complete',
            'epochs': len(self.history),
            'initial_loss': first.avg_loss,
            'final_loss': last.avg_loss,
            'best_loss': best.avg_loss,
            'best_epoch': best.epoch,
            'loss_reduction_pct': (first.avg_loss - last.avg_loss) / max(first.avg_loss, 1e-8) * 100,
            'final_entropy': last.policy_entropy,
            'final_reward': last.avg_reward,
            'total_samples': last.samples * len(self.history),
            'total_time_sec': sum(e.elapsed_sec for e in self.history),
        }


# ---------------------------------------------------------------------------
# 4. Pipeline — orchestrate everything
# ---------------------------------------------------------------------------

class HistoricalPipeline:
    """Complete pipeline: fetch data → simulate trades → train → save."""
    
    def __init__(self, orchestrator, output_dir: str = None):
        self.orc = orchestrator
        self.output_dir = output_dir or os.path.expanduser("~/.nexustrader/training_output")
        os.makedirs(self.output_dir, exist_ok=True)
        self.fetcher = DataFetcher()
    
    def run_ticker(self, ticker: str, since_days: int = 730,
                   epochs: int = 50) -> Dict:
        """Run the full pipeline for one ticker.
        
        Args:
            ticker: e.g. 'BTC-USD'
            since_days: Historical data range (default 2 years)
            epochs: Training epochs
        
        Returns:
            {ticker, candles, samples, training_summary}
        """
        _log.info(f"=== Pipeline: {ticker} ({since_days}d history, {epochs} epochs) ===")
        
        # Ensure ticker is initialized in the orchestrator before running pipeline
        ticker_ensembles = getattr(self.orc, 'strategy_ensembles', {})
        if hasattr(self.orc, 'init_ticker') and ticker not in ticker_ensembles:
            self.orc.init_ticker(ticker)
        
        # 1. Fetch historical data
        candles = self.fetcher.fetch_candles(ticker, since_days)
        if len(candles) < 100:
            _log.error(f"Insufficient data for {ticker}: {len(candles)} candles")
            return {'ticker': ticker, 'error': 'insufficient_data', 'candles': len(candles)}
        
        # Save raw data
        data_path = os.path.join(self.output_dir, f"{ticker}_1h_{since_days}d.json")
        with open(data_path, 'w') as f:
            json.dump(candles, f)
        _log.info(f"  Saved {len(candles)} candles to {data_path}")
        
        # 2. Simulate trading with look-ahead labeling
        trader = SimulatedTrader(self.orc, ticker, lookahead=12)
        warmup = 50  # candles needed for indicator calculation
        
        for i in range(len(candles) - trader.lookahead):
            candle = candles[i]
            indicator = trader.add_indicator(candle)
            
            if i < warmup:
                continue  # Skip warmup — not enough indicator data yet
            
            # Get strategy signal
            if trader.ensemble:
                weighted_signal, strategy_breakdown = trader.ensemble.get_weighted_signal(
                    indicator, {}
                )
            else:
                weighted_signal = 0.0
                strategy_breakdown = {}
            
            # Generate sample using look-ahead (current candle + next 12)
            future = candles[i+1 : i+1+trader.lookahead]
            sample = trader.simulate_trade(indicator, weighted_signal, strategy_breakdown, future)
            if sample:
                trader.samples.append(sample)
        
        _log.info(f"  Collected {len(trader.samples)} training samples from {len(candles)} candles")
        
        # 3. Train offline
        if trader.samples and trader.learner:
            trainer = OfflineTrainer(
                trader.learner,
                batch_size=32,
                epochs=epochs,
                early_stop_patience=10,
            )
            history = trainer.train(trader.samples)
            summary = trainer.summary()
            
            _log.info(f"  Training: {summary.get('epochs', 0)} epochs, "
                     f"loss {summary.get('initial_loss', 0):.4f} → {summary.get('final_loss', 0):.4f}")
        else:
            _log.warning(f"  No samples ({len(trader.samples)}) or learner ({trader.learner}) — skipping training")
            summary = {'status': 'no_samples', 'samples': len(trader.samples)}
            history = []
        
        # 4. Save trained weights
        if trader.learner and hasattr(trader.learner.policy_net, 'to_json'):
            weights_path = os.path.join(self.output_dir, f"{ticker}_policy_weights.json")
            with open(weights_path, 'w') as f:
                f.write(trader.learner.policy_net.to_json())
            _log.info(f"  Saved policy weights to {weights_path}")
        
        return {
            'ticker': ticker,
            'candles': len(candles),
            'samples': len(trader.samples),
            'training': summary,
        }
    
    def run_all(self, tickers: List[str] = None, since_days: int = 730,
                epochs: int = 50) -> List[Dict]:
        """Run pipeline for all tickers."""
        tickers = tickers or self.orc.tickers[:5]  # Default to first 5
        results = []
        for ticker in tickers:
            result = self.run_ticker(ticker, since_days, epochs)
            results.append(result)
        return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    
    # Quick test: fetch candles only
    if len(sys.argv) > 1:
        ticker = sys.argv[1]
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 365
        fetcher = DataFetcher()
        candles = fetcher.fetch_candles(ticker, days)
        print(f"Fetched {len(candles)} candles for {ticker}")
        if candles:
            print(f"  First: {candles[0]['timestamp']} @ ${candles[0]['close']}")
            print(f"  Last:  {candles[-1]['timestamp']} @ ${candles[-1]['close']}")
    else:
        print("Usage: python3 historical_pipeline.py <TICKER> [DAYS]")
        print("Example: python3 historical_pipeline.py BTC-USD 365")
