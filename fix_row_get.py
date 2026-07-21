#!/usr/bin/env python3
"""Fix sqlite3.Row.get() in process_tick by converting row to dict properly."""
import os
os.chdir("/root/nexustrader")

with open("main.py") as f:
    c = f.read()

old = """        # Convert to dict before storing (sqlite3.Row .get() crash prevention)
        self.latest_ticks[ticker] = dict(row) if hasattr(row, "keys") and not isinstance(row, dict) else row
        self.latest_signals[ticker] = 0.0
        current_price = float(row['close'])
        atr = row.get('atr', None)"""

new = """        # Convert to dict before storing (sqlite3.Row .get() crash prevention)
        if hasattr(row, "keys") and not isinstance(row, dict):
            row = dict(row)
        self.latest_ticks[ticker] = row
        self.latest_signals[ticker] = 0.0
        current_price = float(row.get('close', 0.0))
        atr = row.get('atr', None)"""

if old in c:
    c = c.replace(old, new)
    print("Fixed row.get -> row dict conversion")
else:
    print("Pattern not found! Looking for alternatives...")
    idx = c.find("Convert to dict before storing")
    if idx >= 0:
        print(f"Found at {idx}:")
        print(repr(c[idx:idx+300]))
    else:
        print("The comment isn't there either")

try:
    compile(c, "main.py", "exec")
    print("Syntax OK!")
    with open("main.py", "w") as f:
        f.write(c)
    print("Saved")
except SyntaxError as e:
    print(f"ERROR: {e}")
