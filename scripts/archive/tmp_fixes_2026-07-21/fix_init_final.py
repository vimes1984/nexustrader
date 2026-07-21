#!/usr/bin/env python3
"""Fix /api/init to use correct orchestrator attribute names"""
B = "/root/nexustrader"
with open(B + "/main.py") as f:
    m = f.read()

# The key fixes:
# 1. Use orc.tickers (not orc.active_tickers)
# 2. Get live prices from data_ingestions (has live_price attr)
# 3. Use execution_engine fields directly for balance/equity

old_init = '''@app.get("/api/init")
async def api_init_state(request: Request):
    """Primary dashboard initialization - single source of truth."""
    import json as _json
    import time as _time
    import traceback as _traceback
    import database as _db
    try:
        orc = orchestrator

        # Active tickers (needed first for equity calc)
        tickers = getattr(orc, "active_tickers", [])
        if not tickers:
            tickers = _json.loads(_db.load_setting("active_tickers", "[]"))
        default_ticker = tickers[0] if tickers else "BTC-USD"
        
        # Balance / Equity
        ee = getattr(orc, "execution_engine", None)
        try:
            balance = ee.balance if ee else float(_db.load_setting("initial_balance", "219.74"))
        except Exception:
            balance = float(_db.load_setting("initial_balance", "219.74"))
        
        # Build current_prices dict from live tickers for get_equity()
        current_prices = {}
        live_streams = getattr(orc, "live_tickers", {}) or {}
        for t in tickers:
            stream = live_streams.get(t)
            if stream and hasattr(stream, "last_price"):
                current_prices[t] = stream.last_price
        
        try:
            equity = ee.get_equity(current_prices) if ee and current_prices else balance
        except Exception:
            equity = balance

        # Trades
        trades = []
        try:
            trades = _db.load_trades()
        except Exception:
            pass

        # Total PnL
        total_pnl = sum(t.get("pnl", 0) or 0 for t in trades)

        # Live ticker prices (reuse current_prices already built)
        ticker_prices = current_prices.copy()
        
        # Active brains
        active_brains = []
        brains_dict = getattr(orc, "learning_engines", {}) or {}
        for ticker_name, learner in brains_dict.items():
            try:
                brain_name = getattr(learner, "active_brain_name", None)
                if brain_name:
                    active_brains.append({"name": brain_name, "ticker": ticker_name, "version": getattr(learner, "brain_version", 1)})
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
        return {"status": "error", "error": str(e)}'''

# Rewrite with correct attribute names
new_init = r'''@app.get("/api/init")
async def api_init_state(request: Request):
    """Primary dashboard initialization - single source of truth."""
    import json as _json
    import time as _time
    import traceback as _traceback
    import database as _db
    try:
        orc = orchestrator
        ee = getattr(orc, "execution_engine", None)

        # Tickers: use orc.tickers (the actual orchestrator attribute)
        tickers = getattr(orc, "tickers", [])
        if not tickers:
            tickers = _json.loads(_db.load_setting("active_tickers", "[]"))
        default_ticker = tickers[0] if tickers else "BTC-USD"

        # Balance
        try:
            balance = ee.balance if ee else float(_db.load_setting("initial_balance", "219.74"))
        except Exception:
            balance = float(_db.load_setting("initial_balance", "219.74"))

        # Build current_prices from data_ingestions (has live_price attr)
        current_prices = {}
        ticker_prices = {}
        ingestions = getattr(orc, "data_ingestions", {}) or {}
        for t in tickers:
            ing = ingestions.get(t)
            if ing and hasattr(ing, "live_price") and ing.live_price:
                current_prices[t] = ing.live_price
                ticker_prices[t] = ing.live_price

        # Equity
        try:
            if ee and current_prices:
                equity = ee.get_equity(current_prices)
            elif ee:
                equity = ee.balance
            else:
                equity = balance
        except Exception:
            equity = balance

        # Trades from DB
        trades = []
        try:
            trades = _db.load_trades()
        except Exception:
            try:
                rows = _db._execute("SELECT * FROM trades ORDER BY exit_time DESC LIMIT 50")
                if rows:
                    trades = [dict(r) for r in rows]
            except Exception:
                pass

        total_pnl = sum(t.get("pnl", 0) or 0 for t in trades)

        # Active brains from learning_engines
        active_brains = []
        brains_dict = getattr(orc, "learning_engines", {}) or {}
        for ticker_name, learner in brains_dict.items():
            try:
                brain_name = getattr(learner, "active_brain_name", None)
                if brain_name:
                    active_brains.append({
                        "name": brain_name,
                        "ticker": ticker_name,
                        "version": getattr(learner, "brain_version", 1)
                    })
            except Exception:
                pass

        # Open positions
        positions = []
        try:
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
            "initial_balance": float(_db.load_setting("initial_balance", "219.74")),
            "lifetime_steps": int(_db.load_setting("lifetime_steps", "0")),
            "model_dna": _db.load_setting("model_dna", "genesis"),
            "positions": positions,
            "risk_mode": _db.load_setting("risk_mode", "conservative"),
            "trading_mode": _db.load_setting("trading_mode", "paper"),
            "live_holdings": getattr(orc, "live_holdings", {}) or {},
        }
    except Exception as e:
        _traceback.print_exc()
        return {"status": "error", "error": str(e)}'''

m = m.replace(old_init, new_init)
compile(m, "main.py", "exec")
print("Compile OK")
with open(B + "/main.py", "w") as f:
    f.write(m)
print("DONE: /api/init rewritten with correct attribute names (orc.tickers, data_ingestions.live_price)")
