#!/usr/bin/env python3
"""Rebuild /api/init and critical dashboard endpoints in main.py"""
B = "/root/nexustrader"

with open(B + "/main.py") as f:
    m = f.read()

# Endpoint 1: /api/init - the core dashboard bootstrap
init_ep = r'''
@app.get("/api/init")
async def api_init_state(request: Request):
    """Primary dashboard initialization - single source of truth."""
    import json as _json
    import time as _time
    import traceback as _traceback
    import database as _db
    try:
        orc = orchestrator

        # Balance / Equity
        try:
            balance = orc.get_balance()
        except Exception:
            balance = float(_db.load_setting("initial_balance", "219.74"))
        try:
            equity = orc.get_equity()
        except Exception:
            equity = balance

        # Trades
        trades = []
        try:
            trades = _db.get_trades(limit=50)
        except Exception:
            pass

        # Total PnL
        total_pnl = sum(t.get("pnl", 0) or 0 for t in trades)

        # Active tickers
        tickers = getattr(orc, "active_tickers", [])
        if not tickers:
            tickers = _json.loads(_db.load_setting("active_tickers", "[]"))
        default_ticker = tickers[0] if tickers else "BTC-USD"

        # Live ticker prices
        ticker_prices = {}
        live_streams = getattr(orc, "live_tickers", {}) or {}
        for t in tickers:
            stream = live_streams.get(t)
            if stream and hasattr(stream, "last_price"):
                ticker_prices[t] = stream.last_price

        # Active brains
        active_brains = []
        try:
            learning = getattr(orc, "learning_engine", None)
            if learning and hasattr(learning, "brains"):
                for name, brain in learning.brains.items():
                    active_brains.append({"name": name, "version": getattr(brain, "version", 1)})
        except Exception:
            pass

        # Initial balance
        initial_balance = float(_db.load_setting("initial_balance", "219.74"))

        # Neural metadata
        lifetime_steps = int(_db.load_setting("lifetime_steps", "0"))
        model_dna = _db.load_setting("model_dna", "genesis")

        # Open positions
        positions = []
        try:
            ee = getattr(orc, "execution_engine", None)
            if ee:
                open_pos = getattr(ee, "open_positions", {})
                for sym, pos in open_pos.items():
                    positions.append({
                        "symbol": sym,
                        "direction": getattr(pos, "direction", "BUY"),
                        "entry_price": getattr(pos, "entry_price", 0),
                        "current_price": getattr(pos, "current_price", 0),
                        "quantity": getattr(pos, "quantity", 0),
                        "entry_time": getattr(pos, "entry_time", int(_time.time())),
                        "unrealized_pnl": getattr(pos, "unrealized_pnl", 0),
                        "unrealized_pnl_pct": getattr(pos, "unrealized_pnl_pct", 0),
                        "age_seconds": int(_time.time()) - getattr(pos, "entry_time", int(_time.time())),
                    })
        except Exception:
            pass

        # Risk mode
        risk_mode = _db.load_setting("risk_mode", "conservative")

        # Trading mode
        trading_mode = _db.load_setting("trading_mode", "paper")

        # Holdings
        live_holdings = getattr(orc, "live_holdings", {}) or {}

        return {
            "status": "ok",
            "balance": balance,
            "equity": equity,
            "trades": trades,
            "total_pnl": total_pnl,
            "tickers": tickers,
            "ticker": default_ticker,
            "ticker_prices": ticker_prices,
            "active_brains": active_brains,
            "initial_balance": initial_balance,
            "lifetime_steps": lifetime_steps,
            "model_dna": model_dna,
            "positions": positions,
            "risk_mode": risk_mode,
            "trading_mode": trading_mode,
            "live_holdings": live_holdings,
        }
    except Exception as e:
        _traceback.print_exc()
        return {"status": "error", "error": str(e)}
'''

# Endpoint 2: /api/positions
pos_ep = r'''
@app.get("/api/positions")
async def api_positions():
    """Open positions + fiat breakdown."""
    import time as _time
    positions = []
    try:
        ee = getattr(orchestrator, "execution_engine", None)
        if ee:
            open_pos = getattr(ee, "open_positions", {})
            for sym, pos in open_pos.items():
                positions.append({
                    "symbol": sym,
                    "direction": getattr(pos, "direction", "BUY"),
                    "entry_price": getattr(pos, "entry_price", 0),
                    "current_price": getattr(pos, "current_price", 0),
                    "quantity": getattr(pos, "quantity", 0),
                    "entry_time": getattr(pos, "entry_time", int(_time.time())),
                    "unrealized_pnl": getattr(pos, "unrealized_pnl", 0),
                    "unrealized_pnl_pct": getattr(pos, "unrealized_pnl_pct", 0),
                    "age_seconds": int(_time.time()) - getattr(pos, "entry_time", int(_time.time())),
                })
    except Exception:
        pass
    fiat_breakdown = {}
    crypto_count = 0
    try:
        live_holdings = getattr(orchestrator, "live_holdings", {}) or {}
        for asset, amt in live_holdings.items():
            if asset in ("USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD"):
                fiat_breakdown[asset] = amt
            elif float(amt) > 0:
                crypto_count += 1
    except Exception:
        pass
    return {"positions": positions, "fiat_breakdown": fiat_breakdown, "crypto_asset_count": crypto_count}
'''

# Endpoint 3: /api/trades/all
trades_ep = r'''
@app.get("/api/trades/all")
async def api_trades_all():
    """All completed trades."""
    import database as _db
    try:
        trades = _db.get_trades(limit=100)
        return {"trades": trades}
    except Exception as e:
        return {"trades": [], "error": str(e)}
'''

# Endpoint 4: /api/health (lightweight watchdog)
health_ep = r'''
@app.get("/api/health")
async def api_health():
    """Lightweight health check - no heavy DB access."""
    import sys, os
    try:
        import psutil
        mem = round(psutil.Process().memory_info().rss / 1024 / 1024, 1)
    except Exception:
        mem = 0
    return {
        "status": "ok",
        "uptime_seconds": getattr(orchestrator, "start_time", 0),
        "pid": os.getpid(),
        "python": sys.version.split()[0],
        "memory_mb": mem,
    }
'''

# Insert all endpoints just before /api/quant/prompt/save
marker = '\n@app.post("/api/quant/prompt/save")'
all_eps = init_ep + pos_ep + trades_ep + health_ep
m = m.replace(marker, all_eps + marker)

# Verify compiles
compile(m, "main.py", "exec")
print("Compile OK")

# Backup current
import shutil
shutil.copy(B + "/main.py", B + "/main.py.bak_init_restore")
print("Backed up")

with open(B + "/main.py", "w") as f:
    f.write(m)
print("DONE: /api/init + /api/positions + /api/trades/all + /api/health added")

# Count routes
route_count = sum(1 for line in m.split('\n') if '@app.get(' in line or '@app.post(' in line or '@app.websocket(' in line)
print(f"Total routes: {route_count}")
