#!/usr/bin/env python3
"""Fix dashboard truth: websocket weights crash, trades/all stale DB, missing reasoning endpoint."""
B = "/root/nexustrader"
MAIN = f"{B}/main.py"
with open(MAIN) as f:\n    m = f.read()\n\nold_weights = '''            "weights": {
                ensemble.strategies[i].name: float(ensemble.weights[i])
                for i in range(len(ensemble.weights))
            } if ensemble else {},'''
new_weights = '''            "weights": {
                ensemble.strategies[i].name: float(ensemble.weights[i])
                for i in range(min(len(ensemble.weights), len(ensemble.strategies)))
            } if ensemble else {},'''
if old_weights not in m:\n    print("WARN: exact WS weights block not found")
else:
    m = m.replace(old_weights, new_weights, 1)
    print("Fixed WS weights length mismatch")

if '"entry_time": pos["timestamp"],' not in m:\n    m = m.replace('''                            "exit_time": timestamp,
                            "symbol": dash_symbol,''', '''                            "entry_time": pos["timestamp"],
                            "exit_time": timestamp,
                            "symbol": dash_symbol,''')
    print("Added entry_time to reconstructed exchange trades")
else:
    print("entry_time already present in reconstructed exchange trades")

start = m.find('@app.get("/api/trades/all")')
if start == -1:
    raise SystemExit("ERROR: /api/trades/all not found")
end = m.find('\n@app.', start + 10)
if end == -1:
    raise SystemExit("ERROR: cannot find end of /api/trades/all")
trades_all = '''@app.get("/api/trades/all")
async def api_trades_all():
    """All completed trades: DB truth merged with live Kraken fills when available."""
    try:
        db_trades = database.load_trades()
    except Exception as e:\n        logging.error(f"/api/trades/all DB load failed: {e}")
        db_trades = []

    exchange_trades = []
    try:
        cfg_path = os.path.expanduser("~/.nexustrader/config.json")
        if os.path.exists(cfg_path):
            with open(cfg_path, "r") as f:\n                cfg = json.load(f)\n            if cfg.get("trading_mode", "paper") == "live":
                creds = cfg.get("api_credentials", {})
                api_key = creds.get("api_key")
                api_secret = creds.get("api_secret")
                broker = cfg.get("broker", "kraken").lower()
                if api_key and api_secret:
                    import ccxt
                    exchange_class = getattr(ccxt, broker)
                    exchange = exchange_class({"apiKey": api_key, "secret": api_secret, "enableRateLimit": True, "timeout": 20000})
                    exchange_trades = reconstruct_trades_from_exchange(exchange)
    except Exception as e:\n        logging.error(f"/api/trades/all exchange fetch failed: {e}")

    merged = []
    seen = set()
    def key(t):
        return (str(t.get("symbol", "")), str(t.get("direction", "")), round(float(t.get("entry_time", 0) or 0), 3), round(float(t.get("exit_time", 0) or 0), 3), round(float(t.get("quantity", 0) or 0), 12))
    for t in exchange_trades + db_trades:
        k = key(t)
        if k not in seen:
            seen.add(k)
            merged.append(t)
    merged.sort(key=lambda x: float(x.get("exit_time", 0) or 0), reverse=True)
    return {"trades": merged, "db_count": len(db_trades), "exchange_count": len(exchange_trades), "count": len(merged)}

'''
m = m[:start] + trades_all + m[end+1:]
print("Replaced /api/trades/all")

if '@app.get("/api/trading/reasoning")' not in m:\n    reasoning = '''\n@app.get("/api/trading/reasoning")
def get_trading_reasoning():
    """Human-readable bot reasoning/status cards for dashboard."""
    items = []
    status = "active"
    try:
        ee = orchestrator.execution_engine
        signals = getattr(orchestrator, "latest_signals", {}) or {}
        tickers = getattr(orchestrator, "tickers", []) or []
        current_prices = {}
        stale = []
        now = time.time()
        for t in tickers:
            ing = getattr(orchestrator, "data_ingestions", {}).get(t)
            price = getattr(ing, "live_price", 0.0) if ing else 0.0
            current_prices[t] = price or 0.0
            sig = signals.get(t, {})
            ts = float(sig.get("timestamp", 0) or 0)
            if ts and now - ts > 600:
                stale.append(t)
        equity = ee.get_equity(current_prices)
        balance = float(getattr(ee, "balance", 0.0) or 0.0)
        open_pos = getattr(ee, "active_positions", {}) or {}
        db_trades = database.load_trades()
        wins = sum(1 for tr in db_trades if float(tr.get("pnl", 0) or 0) > 0)
        losses = sum(1 for tr in db_trades if float(tr.get("pnl", 0) or 0) < 0)
        win_rate = (wins / (wins + losses) * 100.0) if wins + losses else 0.0
        bullish = sum(1 for s in signals.values() if s.get("direction") == "BULLISH")
        bearish = sum(1 for s in signals.values() if s.get("direction") == "BEARISH")
        neutral = max(0, len(signals) - bullish - bearish)
        items.append({"id":"mode", "severity":"info", "title":"Mode", "detail":f"Trading mode: {ee.trading_mode}. Risk mode: {getattr(orchestrator.probability_engine, 'risk_mode', 'unknown')}."})
        items.append({"id":"capital", "severity":"info", "title":"Capital", "detail":f"Cash ${balance:.2f}, equity ${equity:.2f}, open positions {len(open_pos)}."})
        items.append({"id":"signals", "severity":"success" if signals else "warning", "title":"Live signals", "detail":f"{len(signals)}/{len(tickers)} tickers reporting. Bullish {bullish}, bearish {bearish}, neutral {neutral}."})
        items.append({"id":"performance", "severity":"warning" if win_rate < 35 and wins + losses >= 5 else "info", "title":"Closed trade performance", "detail":f"DB has {len(db_trades)} closed trades: {wins}W/{losses}L, win rate {win_rate:.1f}%."})
        if stale:
            status = "idle"
            items.append({"id":"stale", "severity":"warning", "title":"Stale signal data", "detail":"No fresh signal update for: " + ", ".join(stale[:8])})
        if "SUI-USD" in tickers:
            items.append({"id":"sui", "severity":"warning", "title":"SUI-USD data risk", "detail":"SUI-USD has had yfinance/delisting-style failures. Consider disabling if live prices stay missing."})
        if balance < 20:
            status = "warning"
            items.append({"id":"cash-low", "severity":"warning", "title":"Low deployable USD", "detail":f"USD cash is ${balance:.2f}. Min trade floor is $10, so only a few positions can open."})
    except Exception as e:\n        status = "error"
        items.append({"id":"reasoning-error", "severity":"error", "title":"Reasoning failed", "detail":str(e)})
    return {"status": status, "items": items, "timestamp": time.time()}

'''
    marker = '@app.get("/api/trading/signals")'
    if marker in m:\n        m = m.replace(marker, reasoning + marker, 1)\n    else:
        marker = '@app.get("/api/init")'
        m = m.replace(marker, reasoning + marker, 1)
    print("Added /api/trading/reasoning")
else:
    print("Reasoning endpoint already exists")

compile(m, MAIN, "exec")
with open(MAIN, "w") as f:\n    f.write(m)\nprint("main.py compile OK")
