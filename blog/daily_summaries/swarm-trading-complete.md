# Swarm Trading Batch — Complete

**Date:** 2026-07-23  
**Iterations:** 21 (plus ~28 analysis passes without commit)  
**Files targeted:** main.py, execution_engine.py, evaluation/safety.py, probability_engine.py, strategy_engine.py, database.py, learning_engine.py, sentiment_analyzer.py

## Root Cause Analysis — "Bot NOT Trading"

The bot was blocked from trading by a cascading set of bugs, not a single root cause:

### 1. KillSwitch Position Limit (Iter 2) — Fixed
**Bug:** `main.py` passed raw coin quantities (e.g., 396 ADA) to KillSwitch's position limit check, but `max_per_pos` is a dollar value ($247 for $990 account). With 396 ADA > $247 threshold, *every* non-ADA trade was blocked because the ADA position "exceeded" the per-symbol limit — it was comparing apples to oranges.

**Fix:** Changed `open_positions` dict to compute `qty * entry_price` — dollar exposure per symbol.

### 2. Signal Threshold Starvation (Iter 3 & 9) — Fixed
**Bug:** Signal threshold was computed from cash balance, not total equity. When ADA position opened at $198, balance dropped from $990 → $792, making the threshold `1/(1+792/500) = 0.387`. Most ensemble signals (0.10–0.25) were below this. Bot could never open a second position.

**Fix:** Use `current_equity` (includes unrealized PnL + open positions value). Also lowered denominator from 500→350 and floor 0.20→0.15 so signals pass more readily as the account grows.

### 3. Double-Counting Committed Capital (Iter 1) — Fixed
**Bug:** `available_balance = self.balance - committed_capital` double-counted position costs. The balance already had ADA's $198 deducted — subtracting `committed_capital` (= $198) again gave `available_balance = $594` instead of `$792`. This halved position sizing for the next trade.

**Fix:** Removed `- committed_capital` from `available_balance`.

### 4. Dual Position-Size Estimation (Iter 10) — Fixed
**Bug:** Risk limits used a *different* position-size formula than order execution. The concentration check used `available_balance * kelly_cap` (e.g., $3.96) while execution used `available_balance * kelly / stop_loss_pct` (e.g., $132). A tight stop-loss could make the actual position 33x larger than what the concentration check validated.

**Fix:** Replaced both estimates with a single `kelly_position_value` formula, used consistently for both risk limits and execution.

### 5. SELL Signals Silently Skipped (Iter 4) — Fixed
**Bug:** `_get_asset_balance()` returns 0 in paper mode (`_last_raw_balances` is None). For SELL orders, `max_sell_value = 0 * 0.995 * price = 0 < $5 → return None`. Every SELL signal in paper mode silently returned without trading.

**Fix:** Paper mode now computes `max_sell_value = position_value` (synthetic holdings), bypassing the exchange balance check.

### 6. Fee Mismatch (Iter 6, 17) — Fixed
**Bug:** Entry fee was `position_value * rate` (pre-slippage) while exit fee was `exit_price * qty * rate` (post-slippage). Inconsistent bases caused micro-balance drift accumulating over trades. Also, net PnL only deducted exit fee, missing entry fee from profit calculation.

**Fix:** Entry fee = `position_cost * rate` (post-slippage). Net PnL now = `pnl - exit_fee - entry_fee`.

### 7. Cooldown Never Cleared (Iter 8) — Fixed
**Bug:** Loss cooldown was set on losing trades but never cleared on winning trades. A single loss could permanently block a symbol (4h cooldown persists across wins).

**Fix:** Clear `cooldown_end_{symbol}` on winning trade close.

### 8. PnL Passed to KillSwitch (Iter 11) — Fixed
**Bug:** `pnl_abs = pnl_percent * total_balance` — multiplied a *ratio of position cost* by the *total balance*, producing a meaningless absolute PnL for KillSwitch tracking. Would either under- or over-shoot daily loss limits.

**Fix:** Extract actual absolute PnL from the closed trade record.

### 9. Paper Mode Broadcast Crash (Iter 21) — Fixed
**Bug:** `pending_limit_orders[ticker]` raises KeyError because the dict is never populated by `open_position`. Paper mode broadcast would crash with 500 error on every trade open.

**Fix:** Use `.get(ticker, active_positions.get(ticker, {}))` fallback.

### 10. Stale Risk Limits (Iter 15) — Fixed
**Bug:** `max_open_positions`, `max_concentration`, and `max_total_exposure` were loaded once in `__init__`. If the optimizer changed these settings, the engine ignored them until restart.

**Fix:** Re-read limits from DB at every position open.

## Remaining Observations (not bugs)

- **Stuck ADA position:** Most likely caused by the TP/SL levels being based on ATR at entry. If the market was volatile at entry, the TP/SL may be far from current price. The 48h time stop hard-close will eventually resolve it.
- **Pending_limit_orders:** The entire `pending_limit_orders` subsystem appears to be dead code — it's populated only in tests and never in production. The paper-mode "limit order" broadcast is misleading (the position is already active).
- **MutationFreeze memory:** Capped suggestions at 500 (iter 16). Previously unbounded.
- **Live broker min amount:** Added re-check after precision rounding (iter 20).
- **Evaluation metadata:** Position records now store `predicted_win_probability`, `expected_value`, etc. for calibration tracking (iter 14).

## Files Modified

| File | Bugfixes |
|------|----------|
| `main.py` | KillSwitch position limit (qty→Dollar), signal threshold (balance→equity), PnL to KillSwitch (pct→abs), cooldown guard, exposure warm-up, paper broadcast crash |
| `execution_engine.py` | Available balance double-count, dual position-size, SELL paper mode, fee consistency, cooldown clear, stale risk limits, net PnL includes entry fee, live broker min amount |
| `evaluation/safety.py` | MutationFreeze memory cap |
| `evaluation/position_sizing.py` | (analysis only) |
| `probability_engine.py` | (analysis only) |
| `strategy_engine.py` | (analysis only) |
| `database.py` | (analysis only) |
