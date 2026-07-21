#!/usr/bin/env python3
"""Add fiat_breakdown + holdings to /api/status, show them in position card."""
import os, json
os.chdir("/root/nexustrader")

# ========== 1. Fix /api/status endpoint ==========
with open("main.py") as f:
    c = f.read()

old_status = '''    return {
        "balance": orchestrator.execution_engine.balance,
        "equity": orchestrator.execution_engine.get_equity(current_prices),
        "positions": orchestrator.execution_engine.active_positions,
        "tickers": orchestrator.tickers,
        "total_pnl": round(sum(float(t.get("pnl", 0.0) or 0.0) for t in __import__("database").load_trades()), 2),
        "closed_trades": len(__import__("database").load_trades()),
        "trading_mode": getattr(orchestrator.execution_engine, "trading_mode", "paper"),
        "open_positions": len(orchestrator.execution_engine.active_positions),
    }'''

new_status = '''    # Extract fiat breakdown from live_holdings
    ee = orchestrator.execution_engine
    fiat_breakdown = {}
    holdings = getattr(ee, "live_holdings", {})
    if holdings:
        for k, v in holdings.items():
            if k in ("USD", "ZUSD"):
                fiat_breakdown["USD"] = fiat_breakdown.get("USD", 0.0) + float(v)
            elif k in ("EUR", "ZEUR"):
                fiat_breakdown["EUR"] = fiat_breakdown.get("EUR", 0.0) + float(v)
            elif k in ("GBP", "ZGBP"):
                fiat_breakdown["GBP"] = fiat_breakdown.get("GBP", 0.0) + float(v)
    
    return {
        "balance": orchestrator.execution_engine.balance,
        "equity": orchestrator.execution_engine.get_equity(current_prices),
        "positions": orchestrator.execution_engine.active_positions,
        "tickers": orchestrator.tickers,
        "total_pnl": round(sum(float(t.get("pnl", 0.0) or 0.0) for t in __import__("database").load_trades()), 2),
        "closed_trades": len(__import__("database").load_trades()),
        "trading_mode": getattr(orchestrator.execution_engine, "trading_mode", "paper"),
        "open_positions": len(orchestrator.execution_engine.active_positions),
        "holdings": holdings,
        "fiat_breakdown": fiat_breakdown,
    }'''

if old_status in c:
    c = c.replace(old_status, new_status)
    print("Added holdings + fiat_breakdown to /api/status")
else:
    print("Pattern not found! Looking...")
    idx = c.find('"balance": orchestrator.execution_engine.balance')
    if idx >= 0:
        print(f"Found at {idx}")
        end_idx = c.find("}", idx)
        print(f"Block: {c[idx:end_idx+1]}")

try:
    compile(c, "main.py", "exec")
    print("Syntax OK")
    with open("main.py", "w") as f:
        f.write(c)
    print("Saved main.py")
except SyntaxError as e:
    print(f"ERROR: {e}")

# ========== 2. Update enhancer.js position card ==========
with open("dashboard/enhancer.js") as f:
    ej = f.read()

# Update updatePositionDetails to show fiat when no positions
old_pos_empty = """        if (!positions || positions.length === 0) {
            container.innerHTML = '<p style="font-size: 13px; color: var(--text-muted); text-align: center; padding: 20px;">No Active Position Open</p>';
            return;
        }"""

new_pos_empty = """        if (!positions || positions.length === 0) {
            // Show fiat holdings breakdown instead
            fetch('/api/status')
                .then(function(r) { return r.json(); })
                .then(function(d) {
                    var fb = d.fiat_breakdown || {};
                    var h = d.holdings || {};
                    var html = '<p style="font-size: 13px; color: var(--text-muted); text-align: center; padding: 10px; margin: 0;">No Active Trading Position</p>';
                    html += '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 8px;">';
                    for (var cur in fb) {
                        html += '<div style="background: rgba(255,255,255,0.03); border-radius: 6px; padding: 8px; text-align: center;">';
                        html += '<div style="font-size: 11px; color: var(--text-muted);">' + cur + '</div>';
                        html += '<div style="font-size: 16px; font-weight: 700; color: var(--neon-blue);">' + fb[cur].toFixed(2) + '</div>';
                        html += '</div>';
                    }
                    // Also show non-fiat balances
                    var others = 0;
                    for (var cur2 in h) {
                        if (cur2 !== "USD" && cur2 !== "EUR" && cur2 !== "GBP" && cur2 !== "ZUSD" && cur2 !== "ZEUR" && cur2 !== "ZGBP") {
                            others++;
                        }
                    }
                    if (others > 0) {
                        html += '<div style="grid-column: 1 / -1; font-size: 11px; color: var(--text-muted); text-align: center; border-top: 1px solid var(--border-color); padding-top: 8px; margin-top: 4px;">';
                        html += 'Crypto holdings: ' + others + ' assets</div>';
                    }
                    html += '</div>';
                    container.innerHTML = html;
                })
                .catch(function(err) {
                    container.innerHTML = '<p style="font-size: 13px; color: var(--text-muted); text-align: center; padding: 20px;">No Active Position Open</p>';
                });
            return;
        }"""

if old_pos_empty in ej:
    ej = ej.replace(old_pos_empty, new_pos_empty)
    print("Updated position card to show fiat holdings when no active positions")
else:
    print("Pattern not found, checking...")
    idx = ej.find("No Active Position Open")
    if idx >= 0:
        print(f"Found at {idx}")
        print(ej[idx-100:idx+100])

with open("dashboard/enhancer.js", "w") as f:
    f.write(ej)
print("Saved enhancer.js")

# Bump version
with open("dashboard/index.html") as f:
    html = f.read()
html = html.replace("enhancer.js?v=2.2", "enhancer.js?v=2.3")
with open("dashboard/index.html", "w") as f:
    f.write(html)
print("Bumped to v=2.3")

print("\nDONE")
