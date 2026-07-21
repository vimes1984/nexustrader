#!/usr/bin/env python3
B = "/root/nexustrader"
with open(B + "/main.py") as f:
    m = f.read()

# The bug: current_prices loop iterates over 'tickers' but it's defined later
# Fix: move tickers definition BEFORE current_prices loop
old = """        # Balance / Equity
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
            equity = balance"""

new = """        # Active tickers (needed first for equity calc)
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
            equity = balance"""

# Also remove the duplicate tickers block later
m = m.replace(old, new)

# Now remove the duplicate tickers block that comes after
dup = """        # Active tickers
        tickers = getattr(orc, "active_tickers", [])
        if not tickers:
            tickers = _json.loads(_db.load_setting("active_tickers", "[]"))
        default_ticker = tickers[0] if tickers else "BTC-USD"
        
        # Live ticker prices (reuse current_prices already built)"""
m = m.replace(dup, """        # Live ticker prices (reuse current_prices already built)""")

compile(m, "main.py", "exec")
print("Compile OK")
with open(B + "/main.py", "w") as f:
    f.write(m)
print("Fixed: tickers now defined before use")
