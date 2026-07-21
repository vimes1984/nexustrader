#!/usr/bin/env python3
"""Fix /api/trading/signals to compute signals from actual ensemble data."""
import os
os.chdir("/root/nexustrader")

with open("main.py") as f:
    c = f.read()

old_endpoint = '''@app.get("/api/trading/signals")
async def api_trading_signals():
    """Get current signal overview for all tickers."""
    try:
        orb = globals().get("orchestrator")
        if not orb:
            return {"error": "Not initialized", "signals": []}
        sigs = {}
        for ticker in orb.tickers:
            try:
                latest = orb.latest_ticks.get(ticker, {})
                ws = latest.get("weighted_signal", 0.0)
                dir_str = "BULLISH" if ws > 0.05 else ("BEARISH" if ws < -0.05 else "NEUTRAL")
                sigs[ticker] = {
                    "weighted_signal": ws,
                    "direction": dir_str,
                    "price": latest.get("close", latest.get("price", 0)),
                }
            except Exception:
                sigs[ticker] = {"weighted_signal": 0, "direction": "NEUTRAL", "price": 0}
        return sigs'''

new_endpoint = '''@app.get("/api/trading/signals")
async def api_trading_signals():
    """Get current signal overview for all tickers using actual ensemble computations."""
    try:
        orb = globals().get("orchestrator")
        if not orb:
            return {"error": "Not initialized", "signals": []}
        sigs = {}
        for ticker in orb.tickers:
            try:
                latest = orb.latest_ticks.get(ticker, {})
                price = latest.get("close", latest.get("price", 0))
                
                # Compute weighted signal from ensemble if possible
                ws = 0.0
                ensemble = orb.strategy_ensembles.get(ticker)
                ingestor = orb.data_ingestions.get(ticker)
                if ensemble and ingestor and ingestor.data is not None and latest:
                    try:
                        ws, _ = ensemble.get_weighted_signal(latest, ingestor.data)
                    except Exception:
                        pass
                
                # Fallback: check latest evaluation
                if ws == 0.0 and hasattr(orb, "latest_signals"):
                    ws = orb.latest_signals.get(ticker, 0.0)
                
                dir_str = "BULLISH" if ws > 0.05 else ("BEARISH" if ws < -0.05 else "NEUTRAL")
                sigs[ticker] = {
                    "weighted_signal": round(ws, 4),
                    "direction": dir_str,
                    "price": price,
                }
            except Exception:
                sigs[ticker] = {"weighted_signal": 0, "direction": "NEUTRAL", "price": 0}
        return sigs'''

if old_endpoint in c:
    c = c.replace(old_endpoint, new_endpoint)
    print("Fixed /api/trading/signals to compute signals from ensembles")
else:
    print("Pattern not found")
    idx = c.find("api_trading_signals")
    if idx >= 0:
        print(f"Found at {idx}")

try:
    compile(c, "main.py", "exec")
    print("Syntax OK!")
    with open("main.py", "w") as f:
        f.write(c)
    print("Saved")
except SyntaxError as e:
    print(f"ERROR: {e}")
