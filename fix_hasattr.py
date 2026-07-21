#!/usr/bin/env python3
"""Fix hasattr 'keys' -> '"keys"' bug."""
import os
os.chdir("/root/nexustrader")

with open("main.py") as f:
    content = f.read()

content = content.replace('hasattr(row, keys)', 'hasattr(row, "keys")')

try:
    compile(content, "main.py", "exec")
    print("Syntax OK!")
    with open("main.py", "w") as f:
        f.write(content)
    print("Saved")
except SyntaxError as e:
    print("ERROR:", e)
