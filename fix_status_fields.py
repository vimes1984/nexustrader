#!/usr/bin/env python3
"""Enhance /api/status with total_pnl, trading_mode, closed_trades."""
import os
os.chdir("/root/nexustrader")

with open("main.py") as f:
    c = f.read()

old = '        "tickers": orchestrator.tickers\n    }'
new = '''        "tickers": orchestrator.tickers,
        "total_pnl": round(sum(float(t.get("pnl", 0.0) or 0.0) for t in (lambda: (__import__("database")).load_trades())()), 2),
        "closed_trades": len((lambda: (__import__("database")).load_trades())()),
        "trading_mode": getattr(orchestrator.execution_engine, "trading_mode", "paper"),
        "open_positions": len(orchestrator.execution_engine.active_positions),
    }'''

if old in c:
    c = c.replace(old, new)
    print("Enhanced /api/status")
else:
    print("Pattern not found")
    idx = c.find('"tickers": orchestrator.tickers')
    if idx >= 0:
        print(f"Found at {idx}")
        print(repr(c[idx-5:idx+50]))

try:
    compile(c, "main.py", "exec")
    print("Syntax OK!")
    with open("main.py", "w") as f:
        f.write(c)
    print("Saved")
except SyntaxError as e:
    print(f"ERROR: {e}")
