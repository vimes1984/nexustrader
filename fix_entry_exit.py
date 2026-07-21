#!/usr/bin/env python3
"""Apply highest-impact fixes from Entry/Exit Audit."""
import os, sys
os.chdir("/root/nexustrader")

fix_count = 0

# ===== FIX 1: Min position value $10 (fee disaster fix) =====
with open("execution_engine.py") as f:
    ee = f.read()

old_min_pos = "# Calculate position size in Euros\n        position_value = self.balance * kelly_fraction"
new_min_pos = """# Calculate position size in Euros
        position_value = self.balance * kelly_fraction
        
        # Minimum position floor: $10 to beat fee-to-profit ratio
        if position_value < 10.0:
            logging.warning(f"[MIN SIZE] Position value ${position_value:.2f} below $10 minimum. Skipping {symbol}.")
            return False"""

if old_min_pos in ee:
    ee = ee.replace(old_min_pos, new_min_pos)
    fix_count += 1
    print("FIX 1: $10 minimum position floor")

# ===== FIX 2: Disable trailing stop (backwards for SELLs) =====
old_trail = "        trailing_stop_enabled = database.load_setting(\"trailing_stop_enabled\", \"false\") == \"true\""
new_trail = "        trailing_stop_enabled = False  # Disabled: backwards for SELL positions"

if old_trail in ee:
    ee = ee.replace(old_trail, new_trail)
    fix_count += 1
    print("FIX 2: Trailing stop disabled (was backwards for SELLs)")
else:
    print("FIX 2: trailing_stop_enabled not found, checking...")
    if "trailing_stop_enabled" in ee:
        print("  exists, pattern mismatch")

compile(ee, "execution_engine.py", "exec")
with open("execution_engine.py", "w") as f:
    f.write(ee)
print("  execution_engine.py OK")

# ===== FIX 3: Raise signal threshold from 0.10 → 0.50 in DB =====
import sqlite3
conn = sqlite3.connect(os.path.expanduser("~/.nexustrader/nexustrader.db"))
c = conn.cursor()
c.execute("SELECT value FROM settings WHERE key='signal_threshold'")
row = c.fetchone()
old_val = row[0] if row else "0.10"
c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('signal_threshold', '0.50')")
conn.commit()
conn.close()
print(f"FIX 3: DB signal_threshold = 0.50 (was {old_val})")
fix_count += 1

# ===== FIX 4: Verify db_row fix in probability_engine.py =====
with open("probability_engine.py") as f:
    pe = f.read()

# Check row[1] references
import re
row_idx = re.findall(r'row\[(\d+)\]', pe)
if row_idx:
    print(f"FIX 4: Found {len(row_idx)} row[idx] references: {row_idx}")
    # Should all be db_row[idx] now
    for m in re.finditer(r'(\w+)\[(\d+)\]', pe):
        var = m.group(1)
        idx = m.group(2)
        if var == 'row':
            print(f"  WARNING: row[{idx}] still exists at pos {m.start()}")
else:
    print("FIX 4: No row[idx] references — already converted to db_row")
    fix_count += 1

print(f"\nApplied {fix_count} fixes")
