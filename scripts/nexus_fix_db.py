#!/usr/bin/env python3
"""Apply database-level fixes for NexusTrader strategy tuning."""
import sqlite3, os, sys

db_path = os.path.expanduser('~/.nexustrader/nexustrader.db')
if not os.path.exists(db_path):
    print(f'DB not found at {db_path}')
    sys.exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

# 1. risk_mode -> moderate (was hyper_growth, too aggressive given 10% win rate)
c.execute("UPDATE settings SET value=? WHERE key=?", ('moderate', 'risk_mode'))
c.execute("UPDATE settings SET value=? WHERE key=?", ('moderate', 'research:risk_mode'))

# 2. SL multiplier 1.0 -> 2.0 (was ultra-tight, killing positions by noise)
c.execute("UPDATE settings SET value=? WHERE key=?", ('2.0', 'opt_sl_multiplier'))
c.execute("UPDATE settings SET value=? WHERE key=?", ('2.0', 'research:opt_sl_multiplier'))

# 3. Loss cooldown 2h -> 4h
c.execute("UPDATE settings SET value=? WHERE key=?", ('4.0', 'loss_cooldown_hours'))
c.execute("UPDATE settings SET value=? WHERE key=?", ('4.0', 'research:loss_cooldown_hours'))

# 4. Per-asset SL from 1.5 -> 2.0 of ATR
c.execute("UPDATE active_assets SET sl_multiplier=? WHERE sl_multiplier < ?", (2.0, 2.0))

# 5. TP multiplier from 2.0 -> 3.0 of ATR (better risk:reward ratio)
c.execute("UPDATE active_assets SET tp_multiplier=? WHERE tp_multiplier < ?", (3.0, 3.0))

# 6. Cap kelly ceilings at 12% for moderate risk mode
c.execute("UPDATE active_assets SET kelly_ceiling=? WHERE kelly_ceiling > ?", (0.12, 0.12))
# Ensure minimum 3% so small positions can still trade
c.execute("UPDATE active_assets SET kelly_ceiling=? WHERE kelly_ceiling < ?", (0.03, 0.03))

conn.commit()

# Verify
print('=== SETTINGS ===')
for row in c.execute("SELECT key, value FROM settings WHERE key LIKE '%sl%' OR key LIKE '%tp%' OR key LIKE '%risk%' OR key LIKE '%cooldown%' OR key LIKE '%trailing%' ORDER BY key"):
    print(f'{row["key"]:40s} = {row["value"]}')

print('\n=== ACTIVE ASSETS ===')
for row in c.execute("SELECT * FROM active_assets ORDER BY ticker"):
    print(f'{row["ticker"]:12s} active={row["is_active"]}  tp={row["tp_multiplier"]}  sl={row["sl_multiplier"]}  kelly_ceil={row["kelly_ceiling"]}')

conn.close()
print('\nDB fixes applied successfully.')
