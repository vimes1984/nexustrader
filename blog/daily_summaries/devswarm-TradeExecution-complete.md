# DevSwarm: TradeExecution Pipeline — Completion Report

**Date:** 2026-07-23  
**Repo:** /root/.openclaw/workspace/nexustrader  
**Focus:** Fix position sizing explosion, exposure calculation, and execution pipeline  

## Root Cause Analysis

The live bot (192.168.0.144) was stuck: **ZERO trades in 19+ hours**. Every signal was blocked with:
```
[PORTFOLIO RISK] Total exposure 125%-500% would exceed 60.0%. Skipping.
```

### The Explosion Chain

1. **Probability Engine** `evaluate_trade()` returned `final_fraction` (a risk fraction) of up to **0.50** in `hyper_growth` mode, limited only by `max_cap = 0.50`
2. **Execution Engine** used this as `(balance * kelly_fraction) / stop_loss_pct` where `stop_loss_pct` could be as low as **0.015** (1.5% ATR-based stop)
3. **Result:** `($100 × 0.50) / 0.015 = $3,333` — **3,333% of equity**
4. Portfolio risk check: `3,333 / 100 = 3,333% exposure >> 60% max` → **rejected every time**

No position could ever open because the computed size was always 5-50× total equity, exceeding every possible risk limit.

## Fixes Applied (10 iterations)

### Iter 1: Absolute Hard Cap (25% of equity)
- Added `ABSOLUTE_MAX_POSITION_PCT = 0.25` hard cap in `open_position()` as ultimate backstop
- Added micro-account mode (`< $50 equity`): max 10% per trade, max 20% concentration
- Added debug logging for all sizing parameters on every signal evaluation

### Iter 2: Kelly Risk Fraction Hard Cap (15%)
- Added `absolute_max_risk_fraction = 0.15` ceiling in `evaluate_trade()`
- Previously `max_cap = 0.50` from `hyper_growth` mode allowed betting 50% of capital on each trade

### Iter 3: Signal Starvation Guard + Exchange Minimum Fail-Fast
- Added starvation guard: WARNING if no trades in >1 hour, logs active positions and balance
- Added exchange minimum viability check: reject BEFORE risk math if min_qty × entry_price > balance
- Track `_last_trade_time` on both open and close

### Iter 4: Starvation-Aware Signal Threshold Relaxation
- `/api/health` endpoint: fixed uptime calculation, added balance/open_positions
- Added progressive threshold relaxation: after 60 minutes with no trades and no open positions, lower the signal threshold by 0.01 every 15 minutes (floor at 0.10)
- This prevents the death spiral where high thresholds + tight risk = 0 trades forever

### Iter 5: Minimum Stop Distance (1% of price)
- Added `min_stop_distance = price * 0.01` in `calculate_atr_bounds()`
- When ATR is tiny (stable coins, stale data), stop distances of 0.01-0.05% caused 50-100× leverage
- 1% minimum stop means max position = risk_budget / 0.01 = 15× capital maximum

### Iter 6: Balance Sanity Checks
- Added negative-balance clamp on both open and close with ERROR logging
- Prevents paper-mode balance corruption from cascading

### Iter 7: Equity Calculation Price Resolution
- Fixed `current_prices` resolution in `process_tick()` to use `live_price` fallback from data ingestion
- Prevents equity underestimation when latest_tick data hasn't arrived for a ticker

### Iter 8: `pending_limit_orders` KeyError Fix
- Batch signal path referenced `execution_engine.pending_limit_orders` — attribute didn't exist
- Fixed to use `execution_engine.active_positions` instead

### Iter 9: `sync_live_balance` Indentation Bug
- Critical bug: `cached_prices_dict` merge loop (lines 305-310) was outside the `try/except` block
- This caused the cached prices merge and DB persistence of balance to run in the wrong scope
- Fixed indentation to bring it inside the try block

## Key Metrics

| Metric | Before | After |
|--------|--------|-------|
| Max position size (% equity) | Unlimited (5000%+) | **25% hard cap** |
| Max Kelly risk fraction | 0.50 (hyper_growth) | **0.15 absolute max** |
| Minimum stop distance | 0.015% (ATR-driven) | **1% of price** |
| Balance sanity check | None | **Clamp to $0, log ERROR** |
| Starvation detection | Silent | **WARNING + threshold relax** |
| Signal threshold (stuck bot) | Fixed 0.45 | **Decays from 0.45 to 0.10** |
| sync_live_balance scope | Buggy | **Fixed indentation** |

## What Still Needs Attention

1. **Cold-start paradox:** With $100 equity, 25% cap = $25 max position. Many Kraken pairs have min order > $10, so only 2 positions max. System needs a min-balance gating mechanism.
2. **Dynamic leverage cap:** The 3× max_leverage is hard-coded. Should be configurable per ticker (stable pairs need less).
3. **Test coverage:** No unit tests for position sizing math. Critical for regression prevention.
4. **Kraken minimum order sizes:** Should be loaded dynamically from exchange markets and used as pre-filter.
