#!/usr/bin/env python3
"""Fix sqlite3.Row dict conversion and restart bot."""
import os
os.chdir("/root/nexustrader")

with open("main.py") as f:
    content = f.read()

old = '        # Inject cached sentiment score and source breakdowns into row dictionary\n        row[\x27sentiment\x27] = self.latest_sentiments.get(ticker, 0.0)'
new = '        # Ensure row is a proper dict (not sqlite3.Row from DB)\n        if hasattr(row, "keys") and not isinstance(row, dict):\n            row = dict(row)\n        # Inject cached sentiment score and source breakdowns into row dictionary\n        row["sentiment"] = self.latest_sentiments.get(ticker, 0.0)'

if old in content:
    content = content.replace(old, new)
    print("Fixed sqlite3.Row conversion")
else:
    print("Pattern NOT found")
    idx = content.find("Inject cached sentiment")
    if idx >= 0:
        print("Found at", idx, repr(content[idx:idx+80]))

try:
    compile(content, "main.py", "exec")
    print("Syntax OK!")
    with open("main.py", "w") as f:
        f.write(content)
    print("Saved")
except SyntaxError as e:
    print("ERROR:", e)
