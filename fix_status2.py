#!/usr/bin/env python3
"""Fix /api/status to include trading_mode, total_pnl, closed_trades."""
import os
os.chdir("/root/nexustrader")

with open("main.py") as f:
    c = f.read()

old = '        "tickers": orchestrator.tickers\n    }'
new = '        "tickers": orchestrator.tickers,\n        "total_pnl": round(sum(float(t.get("pnl", 0.0) or 0.0) for t in __import__("database").load_trades()), 2),\n        "closed_trades": len(__import__("database").load_trades()),\n        "trading_mode": getattr(orchestrator.execution_engine, "trading_mode", "paper"),\n        "open_positions": len(orchestrator.execution_engine.active_positions),\n    }'

if c.count(old) == 1:
    c = c.replace(old, new)
    print("Enhanced /api/status")
else:
    print(f"Pattern appears {c.count(old)} times, not replacing")
    # Show context for each
    idx = 0
    for _ in range(c.count(old)):
        idx = c.find(old, idx)
        print(f"  Occurrence at {idx}: {repr(c[idx-30:idx+30])}")
        idx += 1

try:
    compile(c, "main.py", "exec")
    print("Syntax OK!")
    with open("main.py", "w") as f:
        f.write(c)
    print("Saved")
except SyntaxError as e:
    print(f"ERROR: {e}")
