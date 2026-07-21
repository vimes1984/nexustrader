#!/usr/bin/env python3
"""Analyze current state of the bot — DB, signals, strategies, learning."""
import sqlite3, json, os

DB = os.path.expanduser("~/.nexustrader/nexustrader.db")
db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row

print("=== TRADE HISTORY ===")
trades = db.execute("SELECT * FROM trades ORDER BY exit_time DESC LIMIT 15").fetchall()
for t in trades:
    print(f"  {t['exit_time']} | {t['ticker']} {t['direction']} | PnL: ${t.get('pnl',0):.4f} | Pct: {t.get('pnl_percent',0):.4f}% | Qty: {t.get('quantity',0)} | Strategy: {t.get('strategy','?') or '?'} | Exit: {t.get('exit_reason','?')}")

print(f"\n=== STRATEGY BREAKDOWN ===")
strat = db.execute("SELECT strategy, COUNT(*) as cnt, SUM(pnl) as total_pnl, AVG(pnl_percent) as avg_pct FROM trades GROUP BY strategy ORDER BY total_pnl").fetchall()
for s in strat:
    print(f"  {s['strategy'] or 'None'}: {s['cnt']} trades, PnL=${s['total_pnl']:.4f}, Avg {s['avg_pct']:.4f}%")

print(f"\n=== TICKER BREAKDOWN ===")
tick = db.execute("SELECT ticker, COUNT(*) as cnt, SUM(pnl) as total_pnl, AVG(pnl_percent) as avg_pct FROM trades GROUP BY ticker ORDER BY total_pnl").fetchall()
for t in tick:
    print(f"  {t['ticker']}: {t['cnt']} trades, PnL=${t['total_pnl']:.4f}, Avg {t['avg_pct']:.4f}%")

print(f"\n=== SETTINGS ===")
settings = db.execute("SELECT key, value FROM settings").fetchall()
for s in settings:
    print(f"  {s['key']}: {s['value']}")

print(f"\n=== BRAINS ===")
brains = db.execute("SELECT DISTINCT brain_name FROM policy_brains").fetchall()
for b in brains:
    print(f"  Brain: {b['brain_name']}")

print(f"\n=== WEIGHTS HISTORY (last 5) ===")
weights = db.execute("SELECT * FROM weights_history ORDER BY timestamp DESC LIMIT 5").fetchall()
for w in weights:
    print(f"  {dict(w)}")

print(f"\n=== TICK COUNT ===")
tc = db.execute("SELECT COUNT(*) as c FROM ticks").fetchone()
print(f"  Total ticks: {tc['c']}")

print(f"\n=== PORTFOLIO HISTORY (last 5) ===")
ph = db.execute("SELECT * FROM portfolio_history ORDER BY timestamp DESC LIMIT 5").fetchall()
for p in ph:
    print(f"  {dict(p)}")

db.close()
