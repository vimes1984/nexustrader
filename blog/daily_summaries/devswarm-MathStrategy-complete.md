# DevSwarm MathStrategy — Complete Summary

**Date:** 2026-07-23  
**Target files:** strategy_engine.py, backtest_engine.py, risk_auditor.py, allocator_agent.py, performance_metrics.py, quant_utils.py  
**Shots:** 25 iterations across 6 files  

## What Was Found & Fixed

### 1. Signal Combination & Ensemble Math (strategy_engine.py)

| Iter | Fix | Impact | 
|------|-----|--------|
| 1 | **Duplicate weight-migration dead code** — `get_weighted_signal` had two identical resize/migration blocks; the second always resulted in a no-op | Eliminates confusion; pure readability |
| 8 | **Double-counted performance bias** — `update_base_weights` persisted boost/decay into `self.weights`. `get_weighted_signal` then applied a *second* boost to `active_weights` using the same performance data. Winning strategies got boosted twice. | Removed Layer 2 run-time bias; weight adjustments now apply exactly once |
| 10 | **Regime detection binary threshold** — Old code used `is_mr and theta > 0.05` with fixed multiplier regardless of theta magnitude. A theta of 0.06 vs 0.5 got the same adjustment. | Continuous scaling: `real_mr_strength = min((theta - 0.03) / 0.05, 1.5)`. Added `max(..., 0.1)` floor on suppression to prevent negative weights |
| 13 | **Missing chop/range regime** — Market could be neither trending nor mean-reverting (e.g. sideways chop). Old code would force-fit either trend or MR amplification. | Added chop index from volatility clustering + theta smallness. Chop regime *halves* directional strategy weights, *boosts* predictive/ML strategies |
| 15 | **No signal correlation penalty** — EMA + MACD are highly correlated. Their signals double-vote, crowding out uncorrelated strategies. | Added pairwise signal overlap detection. Strategies with >50% signal agreement get their weight reduced proportional to overlap |
| 18 | **No Information Coefficient tracking** — Alpha blending requires knowing which strategies predict rank-ordering of returns, not just direction. | Added `compute_information_coefficient()`: Pearson (linear) + Spearman rank (robust) IC. Window expanded from 50→100 trades |
| 5 | **No alpha decay/half-life estimation** — Signal persistence measure was absent. | Added autocorrelation-based half-life estimation from binary correctness series |
| 22 | **DB contention per signal call** — `RSIStrategy.generate_signal()` called `database.load_setting()` on every tick. Same for `KalmanTrendStrategy`. | Cached threshold parameters; `_refresh_cache()` called externally when settings change |
| 24 | **Flat VWAP threshold whipsaw** — 0.15% hardcoded deviated too much in low-vol, too little in high-vol. | ATR-adaptive: `threshold = max(atr/close * 0.5, 0.10%)` adjusts to current volatility regime |

### 2. Walk-Forward & Monte Carlo (backtest_engine.py)

| Iter | Fix | Impact |
|------|-----|--------|
| 2 | **PPO weighted_signal formula** — `sum((j/len(w)-0.5)*w for j,w in enumerate(weights))` used index position as directional proxy, which has no semantic mapping to long/short | Replaced with directional bucket: first half of weights = long, second half = short |
| 4 | **No bootstrap/Monte Carlo** — Strategy robustness was unknown; single return path with no confidence interval | Added: i.i.d. bootstrap (resample trades with replacement), block bootstrap (preserves autocorrelation), VaR/CVaR 95%, convergence diagnostics, prob_positive |
| 9 | **No walk-forward at all** — Optimizing on full dataset leads to overfitting | Added expanding-window walk-forward with purge_bars (remove stale indicator lookback from test) and embargo_bars (prevent test data leaking into next training window) |
| 12 | **Look-ahead bias in ensemble warmup** — `candles[:200]` trained ML strategy on future data relative to early candles | Reverted to `StrategyEnsemble()` with no warmup |
| 16 | **Flat cost in walk-forward** — All entries assumed 0.26% cost regardless of asset, market impact ignored | Now uses `apply_entry_cost()` / `apply_exit_cost()` with the full `CostModel` (taker fee + slippage + spread per asset) |
| 19 | **Non-reproducible Monte Carlo** — `np.random.randint()` used global RNG, no seed control | Added `random_seed` parameter + `np.random.default_rng(random_seed)`; both bootstrap variants now deterministic |
| 23 | **Look-ahead bias from warmup** — same as iter 12 but re-confirmed after merge conflict | Final verification: warmup removed |
| 25 | **Sliding window waste** — Each fold used only 2/n of data (one fold for train, one for test) | Switched to **expanding window**: training starts at min_train_pct of data and grows each fold |

### 3. Correlation Matrix & Hedging (risk_auditor.py)

| Iter | Fix | Impact |
|------|-----|--------|
| 2 | **No quantitative risk math** — Entire risk audit was LLM text generation with raw trade dumps. No correlation, no eigenvalue cleaning, no hedging ratios | Added: correlation matrix with **shrinkage estimation** (Marcenko-Pastur eigenvalue cleaning), **min-variance hedge portfolio weights** (f* = inv(Σ) · 1 / (1^T · inv(Σ) · 1)) |
| 6 | **Missing hedging metrics** — Hedge ratios, beta, dollar-neutral, cointegration checks were all described in prompts but never computed | Added: pairwise minimum variance hedge ratios, portfolio betas vs PC1 market proxy, dollar-neutral test, cointegration proxy via spread mean-reversion z-score |
| 14 | **No stress testing** — Scenario analysis was absent | Added: flash crash (-15%), vol spike (2σ adverse), historical max drawdown, consecutive loss streak analysis |

### 4. Capital Allocation (allocator_agent.py)

| Iter | Fix | Impact |
|------|-----|--------|
| 3 | **No multi-asset Kelly** — Single-asset Kelly formula used per-ticker, ignoring covariance between assets | Added: `f* = inv(Σ) * μ` multi-asset Kelly with regularization + fractional scaling. Also computes simple Kelly for comparison |
| 7 | **No turnover penalty** — Rebalancing decisions ignored transaction cost drag | Added: Kelly delta churn tracking (changes between current and previous settings), estimated round-trip cost (2 × taker fee + slippage + spread), turnover regime label |
| 11 | **No drift-based rebalancing** — Calendar-based or manual rebalancing only | Added: compares current allocation vs target Kelly, computes drift, only rebalances when drift > 2× cost/benefit ratio |
| 17 | **No risk parity** — Allocations were Kelly-focused, ignoring equal risk contribution | Added: diagonal risk parity (inv-vol) + full covariance iterative risk parity that equalizes marginal risk contributions |

### 5. Performance Metrics (performance_metrics.py)

| Iter | Fix | Impact |
|------|-----|--------|
| 21 | **Wrong Sharpe annualization** — Hardcoded `periods_per_year=252` (daily) was wrong for 5-min, hourly, or weekly data | Added `_infer_periods_per_year()` heuristic based on equity curve length. Auto-detects: 52 bars→weekly, 252→daily, ~6048→hourly, ~19656→5-min |

### 6. OU Process & Utilities (quant_utils.py)

| Iter | Fix (absorbed) | Impact |
|------|-----|--------|
| 10b | **Division guard for local_support=0** — `detect_psychological_sweep` could divide by zero when `local_support == 0` | Added `if local_support != 0` guard |

## Key Math Improvements Summary

```
1. Ensemble weighting:     double-count fixed → IC-weighted → correlation-penalized → regime-adaptive
2. Regime detection:       binary (trend/MR) → continuous + chop index
3. Walk-forward:           none → sliding → expanding windows + purge + embargo
4. Monte Carlo:            none → i.i.d. bootstrap + block bootstrap + VaR/CVaR
5. Correlation matrix:     none → eigenvalue-cleaned shrinkage
6. Hedging:                LLM-only → min-variance + beta-neutral + cointegration proxy  
7. Capital allocation:     single Kelly → multi-asset Kelly + risk parity + turnover cost
8. Rebalancing:            none → drift-based cost-aware threshold
9. Alpha decay:            none → autocorrelation half-life + IC tracking
10. Sharpe annualization:  hardcoded 252 → data-aware period inference
```

## Files Changed

| File | Lines Changed | Fixes |
|------|:------------:|:-----:|
| strategy_engine.py | +300 / -60 | 9 |
| backtest_engine.py | +330 / -20 | 7 |
| risk_auditor.py | +210 / -5 | 3 |
| allocator_agent.py | +230 / -15 | 4 |
| performance_metrics.py | +36 / -3 | 1 |
| quant_utils.py | +5 / -0 | 1 |
