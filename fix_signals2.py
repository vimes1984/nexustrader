#!/usr/bin/env python3
"""Add latest_signals tracking to process_tick."""
import os
os.chdir("/root/nexustrader")

with open("main.py", "rb") as f:
    data = f.read()

# Find the latest_ticks assignment  
pattern = b"self.latest_ticks[ticker] = dict(row) if hasattr(row, "
idx = data.find(pattern)
if idx >= 0:
    end_of_line = data.find(b"\n", idx)
    after = data[end_of_line:end_of_line+100]
    print(f"Found at byte {idx}")
    print(f"Line: {data[idx:end_of_line]}")
    print(f"After line: {after[:80]}")
    
    # Insert latest_signals tracking after the line
    insert_point = end_of_line + 1  # after newline
    insertion = b"        self.latest_signals[ticker] = weighted_signal\n"
    data = data[:insert_point] + insertion + data[insert_point:]
    print("Added latest_signals tracking")
else:
    print("Pattern not found in binary")
    # Try alternate encodings
    sdata = data.decode("utf-8")
    for kw in ["latest_ticks[ticker]", "hasattr(row", '"keys"']:
        i2 = sdata.find(kw)
        if i2 >= 0:
            print(f"Found '{kw}' at char {i2}")

try:
    compile(data, "main.py", "exec")
    print("Syntax OK!")
    with open("main.py", "wb") as f:
        f.write(data)
    print("Saved")
except SyntaxError as e:
    print(f"ERROR: {e}")
