#!/usr/bin/env python3
"""Add traceback to WS error log so we can find the IndexError source"""
B = "/root/nexustrader"
with open(f"{B}/main.py") as f:
    m = f.read()

old = '        logging.error(f"WebSocket error: {e}")'
new = '''        import traceback
        logging.error(f"WebSocket error: {e}\\n{traceback.format_exc()}")'''

if old not in m:
    print("ERROR: handler not found")
    exit(1)
m = m.replace(old, new)
compile(m, "main.py", "exec")
print("Compile OK")
with open(f"{B}/main.py", "w") as f:
    f.write(m)
print("Traceback logging added")
