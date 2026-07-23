# Swarm Accounting Complete

## Summary

This batch focused on balance/equity accounting, PnL calculation, and portfolio tracking accuracy in NexusTrader.

## Issues Fixed

### 1. total_pnl_pct division by current balance (not initial)
- `/api/status`: `total_pnl_pct` now divides by `ee.initial_balance` instead of `ee.balance`
- `/api/init`: Same fix — uses `initial_portfolio_balance` from DB
- Dashboard client fallback: now correctly uses `data.initial_balance` and multiplies by 100 to match server percentage format (0.05 → 5.0%

### 2. SELL close balance arithmetic
- SELL positions only deduct entry fee on open (no position cost)
- On close, the `original_value` was incorrectly added back along with PnL, giving a cash windfall
- Fixed: SELL close now only adds `pnl - exit_fee` (original_value was never deducted)

### 3. WebSocket init state missing KPI fields
- Added `total_pnl`, `total_pnl_pct`, `winrate`, `win_count`, `loss_count`, `closed_trades` to WS init_state
- Allowed dashboard KPI display to render correctly on first load

### 4. WebSocket init used stale `live_equity` instead of `get_equity()`
- In paper mode, `live_equity` is never updated (only sync_live_balance populates it)
- Fixed to use `get_equity()` with live prices from data_ingestions

### 5. renderTrades field name mismatch
- Server sends `pnl_percent` but dashboard looked for `pnl_pct`
- PnL% column was never displaying; now reads `pnl_percent` with `pnl_pct` fallback

### 6. renderTrades direction color
- Server sends `BUY`/`SELL` but CSS rules checked for `long`/`short`
- Fixed to handle both naming conventions

### 7. `/api/init` trade ordering
- DB returns trades oldest-first (ASC)
- `/api/init` was sending oldest-first, `/api/status` was reversing to newest-first
- Fixed `/api/init` to also reverse

### 8. `/api/init live_holdings` source
- Was reading `orc.live_holdings` (orchestrator root) instead of `orc.execution_engine.live_holdings`
- Fixed to access via the execution engine

### 9. max_drawdown ignores unrealized PnL
- Previous trade-based calculation only used realized PnL
- Now uses `drawdown_tracker.max_drawdown` which includes unrealized PnL from open positions
- Falls back to trade-based calculation when drawdown_tracker has no data

### 10. Restart recovery for orphaned balance
- When server restarts with open positions, `active_positions` is lost but balance is already reduced by position costs
- Added recovery check: if balance < initial_balance + closed_trades_pnl with no active positions, restores balance to expected value

### Files Modified
- `main.py` (8 fixes)
- `execution_engine.py` (3 fixes: SELL close arithmetic, restart recovery, comment cleanup)
- `dashboard-v2/js/dashboard.js` (4 fixes: pnl_percent field, direction color, total_pnl_pct format, initial_balance preference)
- `database.py` (column migration already existed)

## Verification
- All fixes are backward-compatible
- No functionality removed
- No breaking API changes
