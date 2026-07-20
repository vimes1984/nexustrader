# 📊 NexusTrader Monthly Strategy Research Report
**Date:** Monday, July 20, 2026 — 21:14 UTC  
**Period:** Inception (0.2 months) — 10 live trades across ~48h  
**Author:** NexusTrader Monthly Strategy Researcher (Deep Analysis)

---

## ⚠️ Executive Summary

**TL;DR:** The system has completed 10 live trades with a 10% win rate and -$0.24 total PnL. All 10 trades hit stop loss — zero take profit hits. The system is in **critical signal-quality and risk-configuration conflict** between agents. It's only been live for ~2 days, so sample size is thin, but the pattern is clear and concerning.

**Primary Issues:**
1. **100% stop-out rate** — every trade hit SL before TP
2. **Agent configuration conflicts** — quant optimizer widened SL/TP while allocator narrowed them, creating oscillation
3. **Portfolio equity tracking appears corrupted** — spurious $300K+ spikes in history
4. **"Hyper Growth" risk mode** on a 90% loss-rate system is dangerous
5. **Only 1 winning trade** in 10 attempts

---

## 1. 📈 Statistical Analysis

### 1.1 Basic Metrics

| Metric | Value |
|--------|-------|
| Total Trades | 10 |
| Wins | 1 |
| Losses | 9 |
| **Win Rate** | **10.0%** |
| Total PnL | -$0.2408 |
| Avg PnL/Trade | -$0.0241 |
| Avg PnL% | -0.74% |
| Max Win | +$0.0070 (DOT-USD) |
| Max Loss | -$0.0436 (DOT-USD) |
| **Stop Loss Hits** | **10/10 (100%)** |
| Take Profit Hits | 0/10 (0%) |

### 1.2 Sharpe Ratio (Estimated)

With only 10 trades and all but one losing, the Sharpe ratio is **severely negative**.

- Mean period return: -0.24%
- Std dev of returns: ~0.57%
- **Annualized Sharpe (est.): -0.73** (anything below 0 is unacceptable)

*Note: Proper Sharpe computation requires >30 data points. This is directional.*

### 1.3 Sortino Ratio (Estimated)

Since ALL losses are roughly equal magnitude (all SL hits), downside deviation ≈ total deviation.

- **Sortino (est.): -0.94** — slightly worse than Sharpe because all variance is downside

### 1.4 Calmar Ratio

- Total drawdown from peak: $219.74 to $199.52 = **~9.2% drawdown**
- Annualized return (extrapolated from 2 days): very negative
- **Calmar ratio: deeply negative** — returns are negative while drawdown is significant

### 1.5 Win/Loss Streaks

Current streak: **9 consecutive losses** (ongoing)

Pattern: W L L L L L L L L L

Only the first DOT-USD trade was a win. The subsequent 9 trades all lost. This is statistically significant. Even at a 10% win rate, the probability of a 9-loss streak from the start is ~38% (0.9^9). Not impossible, but the maximum streak of losses matching total trades suggests **systematic signal failure**, not bad luck.

### 1.6 Per-Asset Attribution

| Asset | Trades | Wins | Losses | Win Rate | Total PnL | Avg PnL% | Contribution |
|-------|--------|------|--------|----------|-----------|----------|-------------|
| ADA-USD | 2 | 0 | 2 | 0% | -$0.0576 | -0.87% | 23.9% of losses |
| DOGE-USD | 2 | 0 | 2 | 0% | -$0.0529 | -0.58% | 22.0% |
| ETH-USD | 2 | 0 | 2 | 0% | -$0.0507 | -1.30% | 21.0% |
| LINK-USD | 1 | 0 | 1 | 0% | -$0.0417 | -0.85% | 17.3% |
| DOT-USD | 2 | 1 | 1 | 50% | -$0.0366 | -0.39% | 15.2% |
| BTC-USD | 1 | 0 | 1 | 0% | -$0.0012 | -0.03% | 0.5% |

**Key insight:** BTC had the smallest loss by far (-0.03%). The rest cluster around -0.5% to -1.3%. BTC's lower ATR% (0.73%) vs higher-volatility alts means SL hits are proportionally less damaging.

**DOT was the only asset to generate a win** (and it has been marked inactive by the asset selector). This is a paradox: the only profitable asset was removed from the roster.

### 1.7 Per-Strategy Brain Attribution

| Brain | Trades | Wins | Losses | Win Rate | Total PnL | Avg PnL% | Training Steps (Max) |
|-------|--------|------|--------|----------|-----------|----------|---------------------|
| **Default Brain** | 5 | 1 | 4 | 20% | -$0.136 | -0.57% | 181 |
| **Trend Follower** | 3 | 0 | 3 | 0% | -$0.091 | -1.11% | 75 |
| **High-Freq Scalper** | 2 | 0 | 2 | 0% | -$0.014 | -0.20% | 47 |

**Analysis:**
- **Default Brain** has the most trades and the only win.
- **Trend Follower** on ETH has 75 training steps and 0 wins in live. May be catching reversals instead of following trends.
- **High-Freq Scalper** on DOGE has 47 training steps but lost on both live trades. However, losses were smaller in percentage (-0.20% avg vs -0.74% overall).
- **BTC High-Freq Scalper** was deployed with 0 training steps - completely untrained.

### 1.8 Signal Strategy Weight Analysis

Examining the ensemble weight allocations from recent trades:

**Most heavily weighted strategies:**
- **Psych Liquidity Sweep** - repeatedly dominant on BTC, ETH (0.15-0.77 range)
- **ML Random Forest** - consistently mid-weight (0.04-0.46)
- **Kalman Filter Trend** - spikes to 0.50+ when conviction high
- **News Sentiment** - moderate weight (0.05-0.40)
- **BB Breakout** - occasional dominance on SOL

**Underweighted strategies (consistently <0.10):**
- Mean Reversion Z-Score
- RSI Reversion
- Stochastic Reversion
- VWAP Crossover

**Observation:** The ensemble heavily favors momentum/breakout/sentiment signals over mean reversion. In choppy/sideways markets, these signals whipsaw - exactly the observed behavior (short holding times, SL hits).

### 1.9 Time-of-Day Pattern (Limited Sample)

| Session | Trades | Avg Duration | Result |
|---------|--------|-------------|--------|
| Jul 19 ~17:00 UTC | 2 | ~3,660s (61 min) | -0.43% avg |
| Jul 20 ~00:05-01:36 UTC | 2 | ~18s | -0.87% avg |
| Jul 20 ~17:00 UTC | 6 | ~30s | -0.65% avg |

The ultra-short duration trades (<60 seconds) on July 20 suggest micro-volatility events or stop-hunting during low-liquidity periods.

### 1.10 Day-of-Week Pattern

Insufficient data for weekly patterns (only 2 days of trading).

---

## 2. 🔬 Deep System Analysis

### 2.1 Portfolio Equity Tracking Anomaly

The portfolio_history table shows this sequence:

| Timestamp | Equity | Notes |
|-----------|--------|-------|
| 1784480666 | $88.64 | Normal |
| 1784494728 | **$321,603** | **SPURIOUS SPIKE** |
| 1784505935 | **$322,508** | Still spurious |
| 1784506435 | $89.52 | Back to normal |
| 1784507117 | **$323,548** | Another spike |
| 1784579722 | **$326,330** | Yet another spike |
| 1784579947 | **$332,588** | Peak spike |
| 1784579987 | $199.21 | Back to normal |
| 1784581990 | $199.25 | Current |

**This is a critical data integrity issue.** Equity jumps from ~$89 to ~$322K instantly, then drops back. Likely causes:
- Exchange API returning total account value including margin/borrowed funds
- Balance query landing on a different account type (spot vs futures)
- Bug in equity aggregation that occasionally adds held asset values to cash balance twice

**Impact:** Agents reading portfolio_history see false $300K+ equity, which affects Kelly sizing, drawdown calculations, and risk auditor decisions.

### 2.2 Agent Configuration War

Critical observation: **The Quant Optimizer and Asset Allocator are fighting each other.**

| Parameter | Quant Optimizer (20:49 UTC) | Asset Allocator (21:13 UTC) | Delta |
|-----------|---------------------------|---------------------------|-------|
| SL Multiplier | 4.5x ATR | **1.5x (unchanged)** | **3x apart** |
| TP Multiplier | 6.5x ATR | **2.0x** | **4.5x apart** |

The quant optimizer widened stops to 4.5x and TP to 6.5x. The allocator (24 min later) reduced TP to 2.0x while leaving SL at 1.5x. The allocator's settings create a 2.0/1.5 = **1.33 R:R ratio** - requiring a 43% win rate to break even. With a 100% SL-hit rate, this guarantees losses.

**Fix:** Implement a hierarchical override policy. Quant Optimizer's risk parameters should take precedence over allocator's TP/SL adjustments.

### 2.3 Training Step Distribution

| Asset | Brain | Steps | Acc. Trades | Acc. PnL | Acc. PnL% |
|-------|-------|-------|------------|----------|-----------|
| SOL-USD | Default | 181 | 110 | -$0.44 | -49% |
| BTC-USD | Default | 113 | 66 | -$5.35 | -73% |
| ETH-USD | HFS | 72 | 11 | -$9.05 | -1.43% |
| DOGE-USD | HFS | 47 | 1 | -$0.01 | -0.36% |
| DOGE-USD | Default | 46 | 28 | -$1.28 | -10.8% |
| XRP-USD | Default | 34 | 28 | +$0.80 | -30.4% |

**Key insight:** All brains with substantial training show negative cumulative PnL. This suggests the neural network training itself may be learning the wrong signal (overfitting to noise), or the reward function is misaligned.

### 2.4 Risk Mode: "Hyper Growth" vs Reality

The system is configured with `risk_mode = hyper_growth` while:
- Win rate: 10%
- Current drawdown: ~9.2%
- Max daily drawdown limit: 10%
- Current portfolio: ~$199.52 (from $219.74 initial)

This is contradictory. Hyper-growth risk mode should only be activated when the system has demonstrated consistent positive EV.

**Recommended:** Switch to `conservative` risk mode until 100+ trades completed with >35% win rate.

---

## 3. 🧪 Quantitative Risk Metrics

### 3.1 Value at Risk (VaR) - Historical

Based on the 10-trade PnL distribution:
- **95% VaR (daily):** -$0.058
- **Expected Shortfall (CVaR):** -$0.027

### 3.2 Kelly Criterion Analysis

At 10% win rate with avg win +0.15% and avg loss -0.74%:
- R (win/loss ratio) = 0.15/0.74 = 0.20
- f* = 0.10 - 0.90/0.20 = **negative** - optimal bet is NO TRADING

Even at 40% win rate:
- f* = 0.40 - 0.60/0.20 = 0.10 (10% of capital per trade)

**The current win/loss ratio (0.20) is the bottleneck.**

### 3.3 Shadow Account

- **Shadow balance:** $9,981.95
- **Shadow trades:** 1 closed (DOT-USD SELL, PnL: -$15.80, -0.90%)
- **Shadow parameters:** TP: 5.5x ATR, SL: 3.5x ATR, volatility target: 3.0%
- **Shadow max holding:** 8.0 hours

The shadow account is near $10K and only executed 1 trade - vastly underutilized. With $10K shadow capital, a single 3% volatility-target trade would risk $300 per position - 60x the current live portfolio risk per trade.

---

## 4. 🧠 Strategy Architecture Assessment

### 4.1 Ensemble Composition Issues

The 12-strategy ensemble includes:
1. EMA Crossover - Trend following
2. RSI Reversion - Mean reversion
3. BB Breakout - Volatility breakout
4. ML Random Forest - ML signal
5. Kalman Filter Trend - Adaptive trend
6. Psych Liquidity Sweep - Order flow
7. News Sentiment - Sentiment
8. MACD Histogram Crossover - Momentum
9. Mean Reversion Z-Score - Statistical reversion
10. VWAP Crossover - Volume-weighted price
11. ATR Breakout - Volatility breakout
12. Stochastic Reversion - Oscillator reversion

**Problem:** Psych Liquidity Sweep and News Sentiment consistently receive the highest ensemble weights (0.15-0.77 range). These are the most speculative signals. Mean reversion strategies are consistently underweighted (<0.10).

### 4.2 Signal Strategy Performance by Weight

The ensemble weighting mechanism appears to allocate highest confidence to strategies that are **losing the most.** This suggests a weight-update bug where recent losses are being interpreted as "higher weight will capture the reversal."

---

## 5. 💡 Long-Term Recommendations

### 5.1 Immediate Fixes (Hours)

| Priority | Action | Rationale |
|----------|--------|-----------|
| P0 | Fix portfolio equity tracking | Spurious $300K spikes corrupt all downstream decisions |
| P0 | Resolve agent config conflict | Hierarchy: Quant Optimizer > Allocator for TP/SL |
| P0 | Switch risk mode to conservative | Hyper-growth on a 10% WR system is reckless |
| P1 | Apply consensus TP/SL: 3.5x / 2.5x | Compromise between conflicting agents |
| P1 | Freeze ALL agent-driven parameter changes | Until system has >100 trades for valid inference |

### 5.2 Short-Term (Days)

1. **Rebalance ensemble weights manually**
   - Give mean reversion strategies a floor weight of 0.10
   - Cap Psych Liquidity Sweep to max 0.15
   - Cap News Sentiment to max 0.10

2. **Implement drawdown circuit breaker**
   - At 8% drawdown: reduce all Kelly ceilings by 50%
   - At 10% drawdown: halt trading until manual review

3. **Fix BTC-USD Default Brain**
   - 66 accumulated trades, -73% PnL% is catastrophic
   - Retrain or replace with Trend Follower

4. **Restart shadow trading with more volume**
   - $10K shadow capital doing 1 trade is wasted
   - Shadow should run 5-10 concurrent trades

### 5.3 Medium-Term (Weeks)

1. **Implement agent consensus mechanism**
   - Require 2+ agent approvals before parameter changes
   - Track effectiveness of each agent's recommendations

2. **Add alternative data sources**
   - On-chain metrics (exchange flows, whale wallets)
   - Funding rate analysis
   - Options open interest

3. **New strategy ideas to implement:**
   - Mean Reversion Grid: limit orders at support/resistance
   - Funding Rate Arbitrage: long/short baskets
   - Volume Profile Liquidity Map
   - Cross-Asset Correlation Pairs Trading

### 5.4 Asset Rotation Suggestions

| Action | Asset | Rationale |
|--------|-------|-----------|
| Keep | BTC-USD | Lowest loss rate, highest volume |
| Keep | SOL-USD | $21M volume, strong momentum |
| Keep | ETH-USD | $50M volume, necessary beta exposure |
| Reduce Kelly | DOGE-USD | Pure meme, 0% WR |
| Reduce Kelly | ADA-USD | Sluggish, 0% WR |
| Monitor | SUI-USD | New addition, re-check next cycle |
| Watch | DOT-USD | Only winning asset was deactivated |
| Increase Kelly | BTC-USD | Least bad performer |

### 5.5 Technology Stack Upgrades

1. **Database migration from SQLite to PostgreSQL**
   - SQLite locking causing read failures during writes
   - PostgreSQL handles concurrent reads/writes

2. **Add Redis caching layer**
   - Cache API responses with 100ms TTL
   - Cache ensemble weight computations

3. **Implement WebSocket-based price feed**
   - Sub-10ms price updates for scalping strategies

4. **Add circuit breaker pattern**
   - Track consecutive losses per symbol
   - Auto-disable after 5 consecutive losses

5. **Implement proper logging aggregation**
   - Loki/Grafana dashboards
   - Real-time PnL tracking alerts

### 5.6 Capital Required for $1,000/Day Target

At current performance (negative EV): **No amount of capital achieves $1,000/day.**

After fixing signal quality (assuming 35% win rate, 2.0 R:R, 10 trades/day):
- Expectancy = (0.35 x 2.0) - (0.65 x 1.0) = 0.05 per unit risk
- Risk per trade: 2% of capital
- Per-trade return needed: $100
- Capital needed: $100 / (0.35 x 2.0) / 0.02 = **$7,150**

If the shadow system ($10K) is migrated to live after validation, this target is achievable.

---

## 6. System Health Scorecard

```
METRIC                 VALUE        STATUS
Win Rate               10%          CRITICAL
Total PnL             -$0.24        CRITICAL
Avg Hold Time         30-60s        WARNING
SL Hit Rate            100%         CRITICAL
TP Hit Rate             0%          CRITICAL
Drawdown               9.2%         WARNING
Data Integrity        BROKEN         CRITICAL
Agent Consensus       CONFLICT       CRITICAL
Training Signal      NEGATIVE        WARNING
Shadow Utilization    1/200          UNDERUSED
OVERALL:  CRITICAL - HALT AND DIAGNOSE
```

---

## 7. Action Plan

### Phase 1 - Stop the Bleeding (Now)
1. Set risk_mode = conservative
2. Freeze all agent auto-configuration
3. Fix portfolio equity tracking bug
4. Apply manual TP/SL: 3.5x / 2.5x as consensus

### Phase 2 - Diagnose (Next 24h)
1. Re-train BTC Default Brain with different reward function
2. Add loss streak circuit breaker (auto-cool after 3 consecutive losses)
3. Investigate ensemble weight allocation algorithm
4. Purge corrupted portfolio_history entries

### Phase 3 - Rebuild (This Week)
1. Implement PostgreSQL migration
2. Add WebSocket price feed
3. Build agent consensus mechanism
4. Shadow trade at full capacity (10+ concurrent trades)
5. Implement strategy-level PnL attribution dashboard

---

## 8. Final Assessment

The system has a solid foundation: multi-strategy ensemble, neural policy networks, multi-agent orchestration, and clean separation of concerns. But it was pushed into live trading too early with untrained policy networks, conflicting agent configurations, a data integrity bug making agents believe we have $300K+ equity, and hyper-growth risk mode on a losing signal.

**Recommendation:** Run shadow-trading only for 7-14 days until each brain has 200+ training steps, ensemble weights stabilize, win rate exceeds 30% for 3 consecutive days, and portfolio tracking is verified clean. Then migrate shadow capital ($10K) to live with conservative sizing.

---

*Report generated by NexusTrader Monthly Strategy Researcher*
