#!/usr/bin/env python3
"""
STRATEGY PURGE: 72 → 36 (6 strategies × 6 tickers)
Remove: 5 mean-reversion strats + News Sentiment + all EUR pairs
"""
import os, sys
os.chdir("/root/nexustrader")

with open("strategy_engine.py") as f:
    content = f.read()

# Original 12-strategy list
old_list = """        self.strategies = [
            EMACrossoverStrategy(),
            RSIStrategy(),
            BollingerBandsStrategy(),
            MLPredictorStrategy(),
            KalmanTrendStrategy(),
            PsychologicalSweepStrategy(),
            NewsSentimentStrategy(),
            MACDHistogramCrossoverStrategy(),
            MeanReversionZScoreStrategy(),
            VWAPCrossoverStrategy(),
            ATRBreakoutStrategy(),
            StochasticOscillatorStrategy()
        ]"""

# New 6-strategy list (keep only trend/momentum strats)
new_list = """        self.strategies = [
            # === ACTIVE: Trend/Momentum Strategies (4) ===
            EMACrossoverStrategy(),
            MLPredictorStrategy(),
            KalmanTrendStrategy(),
            MACDHistogramCrossoverStrategy(),
            # === ACTIVE: Volume/Volatility Strategies (2) ===
            VWAPCrossoverStrategy(),
            ATRBreakoutStrategy(),
            # === DISABLED (2026-07-20): Mean-reversion strats never fire ===
            # RSIStrategy() — 0/10 trades had non-zero RSI signal
            # BollingerBandsStrategy() — 0/10 trades
            # PsychologicalSweepStrategy() — 0/10 trades
            # MeanReversionZScoreStrategy() — 0/10 trades
            # StochasticOscillatorStrategy() — 0/10 trades
            # NewsSentimentStrategy() — sentiment injected separately
        ]"""

if old_list in content:
    content = content.replace(old_list, new_list)
    print("Strategy list purged: 12 → 6")
else:
    print("ERROR: Strategy list not found")
    sys.exit(1)

# Fix weight array size from 12 to 6
old_weights = "self.weights = np.ones(len(self.strategies)) / len(self.strategies)"
if old_weights in content:
    # This line is auto-sizing with len(), so it's already correct
    print("Weight array auto-sizes from len(strategies) — OK")

# Fix signal_history to match new strategy count
old_hist = "self.signal_history = [[] for _ in range(len(self.strategies))]"
if old_hist in content:
    print("Signal history auto-sizes from len(strategies) — OK")

compile(content, "strategy_engine.py", "exec")
with open("strategy_engine.py", "w") as f:
    f.write(content)
print("strategy_engine.py purged + syntax OK")

# Now fix long_term_strategy.py — hardcoded strategy index references
with open("long_term_strategy.py") as f:
    lts = f.read()

# Check for hardcoded index references
import re
indices = re.findall(r'ensemble\.strategies\[(\d+)\]', lts)
if indices:
    print(f"Found hardcoded indices in long_term_strategy.py: {indices}")
    for idx in sorted(set(indices), reverse=True):
        old_idx = int(idx)
        # Map old index to new index (after removing 5 mean-reversion + news)
        # Old: 0=EMA, 1=RSI, 2=BB, 3=ML, 4=Kalman, 5=Psych, 6=News, 7=MACD, 8=ZScore, 9=VWAP, 10=ATR, 11=Stoch
        # New: 0=EMA, 1=ML, 2=Kalman, 3=MACD, 4=VWAP, 5=ATR
        mapping = {0: 0, 3: 1, 4: 2, 7: 3, 9: 4, 10: 5}
        new_idx = mapping.get(old_idx)
        if new_idx is not None:
            lts = lts.replace(f"ensemble.strategies[{old_idx}]", f"ensemble.strategies[{new_idx}]")
            print(f"  strategies[{old_idx}] → strategies[{new_idx}]")
        else:
            print(f"  REMOVED: strategies[{old_idx}] — was a disabled strategy")

compile(lts, "long_term_strategy.py", "exec")
with open("long_term_strategy.py", "w") as f:
    f.write(lts)
print("long_term_strategy.py fixed + syntax OK")

print("\nSTRATEGY PURGE COMPLETE")
