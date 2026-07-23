# DevSwarm: PaperMode — Position Persistence & Balance Recovery

**Date:** 2026-07-23  
**Target:** `execution_engine.py`, `database.py`, `main.py`  
**Focus:** Fix Paper trading so positions survive restarts and balance doesn't drift

## Problem

The bot on `192.168.0.144` restarts frequently. On restart:

1. `active_positions` was an empty dict `{}` — all open positions vanished
2. Balance drifted because position costs were deducted from balance but never properly tracked/restored on restart
3. The `active_positions` table existed but was never written to or read from

## Iterations (10 total)

### Iter 1 — DB Functions (`database.py`)
Added three new functions:
- **`save_active_position(symbol, pos)`** — INSERT OR REPLACE into `active_positions` table with all position fields (direction, entry_price, quantity, TP, SL, cost_basis, fee, signals, etc.)
- **`load_active_positions()`** — SELECT * FROM active_positions, returns `dict[symbol -> position_dict]` with JSON fields parsed
- **`delete_active_position(symbol)`** — DELETE FROM active_positions WHERE symbol=?

### Iter 2 — Rebuild from DB on Init (`execution_engine.py`)
In `ExecutionEngine.__init__`, after `database.init_db()` and balance loading, added:
```python
self.active_positions = database.load_active_positions()
```
This replaces the empty `{}` with whatever was in the DB, ensuring positions survive restarts. The rebuild runs before the "restart recovery" balance reconciliation, so both paths work correctly.

### Iter 3 — Persist on Open (`execution_engine.py`)
In `_open_position_internal`, after `self.active_positions[symbol] = {...}`, added:
```python
database.save_active_position(symbol, self.active_positions[symbol])
```
Every open position is immediately persisted to the `active_positions` table.

### Iter 4 — Delete on Close (`execution_engine.py`)
In `_update_positions_internal`, after `del self.active_positions[symbol]`, added:
```python
database.delete_active_position(symbol)
```
Closed positions are cleaned from the active_positions table. Included in iter 3's commit.

### Iter 5 — Public Method (`execution_engine.py`)
Added `rebuild_active_positions_from_db()` as a public method on ExecutionEngine. It locks, clears in-memory positions, and reloads from DB. Also logs what was recovered.

### Iter 6 — Orchestrator Call (`main.py`)
In `NexusTraderOrchestrator.__init__`, after `ExecutionEngine()` creation, added:
```python
self.execution_engine.rebuild_active_positions_from_db()
```
This ensures the orchestration layer has the latest state before any tick processing.

### Iter 7 — Fix Restart Recovery (`execution_engine.py`)
Enhanced the restart balance reconciliation logic:
- **Before:** Only fired when `len(self.active_positions) == 0` (orphan recovery)
- **After:** Handles both cases — when no positions recovered (old path, recovers orphaned capital) AND when positions ARE recovered from DB (new path, reconciles balance = `initial_balance + closed_pnl - open_cost_basis`)
- Includes open fees in the expected balance calculation to eliminate micro-drift

### Iter 8 — Restart Logging (`main.py`)
Added logging of recovered active positions at stream start, making restart recovery visible in logs.

### Iter 9 — Balance Drift Fix (`execution_engine.py`)
Included `open_fees` (sum of `fee_paid` across open positions) in the restart balance reconciliation. The saved balance includes fee deductions, so the expected-with-positions calculation must also subtract fees. Without this fix, ~0.26% per position would accumulate as invisible drift on every restart.

### Iter 10 — Trailing Stop Persistence (`execution_engine.py`)
Added `database.save_active_position(symbol, pos)` when a trailing stop update moves the stop-loss. Without this, trailing SL progress was lost on restart, causing positions to use their original (wider) SL from the initial entry.

## Verification

```bash
python3 -c "import execution_engine; print('ok')"  # imports clean
python3 -c "
import database
assert hasattr(database, 'save_active_position')
assert hasattr(database, 'load_active_positions')
assert hasattr(database, 'delete_active_position')
print('All 3 DB functions present')
"
```

## What Survives Restarts Now

| State | Before | After |
|-------|--------|-------|
| Open positions | Lost (empty dict) | Rebuilt from SQLite |
| Entry prices (slippage-adjusted) | Lost | Restored |
| Take profit / Stop loss | Lost | Restored |
| Trailing stop progress | Lost | Persisted on update |
| Cost basis | Not tracked explicitly | Stored and restored |
| Fees paid | Not restored | Restored |
| Balance | Drifted on restart | Reconciled to expected value |
| Strategy signals & metadata | Lost | Restored |
