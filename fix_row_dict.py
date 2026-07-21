#!/usr/bin/env python3
"""Fix sqlite3.Row dict conversion in process_tick."""
import os
os.chdir("/root/nexustrader")

with open("main.py") as f:
    content = f.read()

old = '        # Feature engineering for probabilities at process_tick level\n        row["sentiment"] = self.latest_sentiments.get(ticker, 0.0)'
new = '        # Convert sqlite3.Row to dict if needed\n        if hasattr(row, "keys") and not isinstance(row, dict):\n            row = dict(row)\n        # Feature engineering for probabilities at process_tick level\n        row["sentiment"] = self.latest_sentiments.get(ticker, 0.0)'

if old in content:
    content = content.replace(old, new)
    print("Fixed sqlite3.Row -> dict conversion")
else:
    print("Pattern not found")
    idx = content.find('row["sentiment"]')
    if idx >= 0:
        print(f"Bracket style found at {idx}")
        ctx = content[max(0,idx-150):idx+50]
        print(repr(ctx))

try:
    compile(content, "main.py", "exec")
    print("Syntax OK!")
    with open("main.py", "w") as f:
        f.write(content)
except SyntaxError as e:
    print(f"ERROR: {e}")
