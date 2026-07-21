#!/usr/bin/env python3
"""Fix ALL critical bugs: get_equity signature, DB function names, SUI-USD removal"""
B = "/root/nexustrader"

# ─── Fix /api/init to use correct function signatures ───
# The orchestrator doesn't have get_balance/get_equity — only execution_engine does
# execution_engine has: .balance (property), .get_equity(current_prices_dict)
with open(B + "/main.py") as f:
    m = f.read()

# Fix: /api/init — use ee.balance and build current_prices from live tickers
old_init_balance = """        # Balance / Equity
        try:
            balance = orc.get_balance()
        except Exception:
            balance = float(_db.load_setting("initial_balance", "219.74"))
        try:
            equity = orc.get_equity()
        except Exception:
            equity = balance"""

new_init_balance = """        # Balance / Equity
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

m = m.replace(old_init_balance, new_init_balance)

# Fix: use database.load_trades() instead of database.get_trades()
m = m.replace(
    "trades = _db.get_trades(limit=50)",
    "trades = _db.load_trades()"
)

# Fix: remove duplicate variable
m = m.replace("""        # Live ticker prices from Kraken streams
        ticker_prices = {}
        live_streams = getattr(orc, "live_tickers", {}) or {}
        for t in tickers:
            stream = live_streams.get(t)
            if stream and hasattr(stream, "last_price"):
                ticker_prices[t] = stream.last_price
        
        # Active brains""", 
        """        # Live ticker prices (reuse current_prices already built)
        ticker_prices = current_prices.copy()
        
        # Active brains""")

# ─── Remove SUI-USD from active tickers ───
m = m.replace("""        # Live ticker prices (reuse current_prices already built)
        ticker_prices = current_prices.copy()
        
        # Active brains
        active_brains = []
        try:
            learning = getattr(orc, "learning_engine", None)""",
        """        # Live ticker prices (reuse current_prices already built)
        ticker_prices = current_prices.copy()
        
        # Active brains
        active_brains = []"""
)

# Actually let me find the exact string more carefully
# The 'Active brains' section should already be fixed. Let me find exact text
idx = m.find("ticker_prices = current_prices.copy()")
if idx > 0:
    # Verify this is inside /api/init
    # Check the surrounding context
    context = m[idx:idx+200]
    # Remove the old active_brains section that references learning_engine
    old_brains = """        # Active brains
        active_brains = []
        try:
            learning = getattr(orc, "learning_engine", None)"""
    if old_brains in m:
        m = m.replace(old_brains, """        # Active brains
        active_brains = []
        brains_dict = getattr(orc, "learning_engines", {}) or {}
        for ticker_name, learner in brains_dict.items():
            try:
                brain_name = getattr(learner, "active_brain_name", None)
                if brain_name:
                    active_brains.append({"name": brain_name, "ticker": ticker_name, "version": getattr(learner, "brain_version", 1)})
            except Exception:
                pass""")

# ─── Fix /api/positions to use ee.balance ───
# (The /api/positions and /api/trades/all endpoints look OK already)

# ─── Remove all SUI-USD from active tickers ───
# Fix the DB directly
m = m.replace("\"active_tickers\", '[\"ADA-USD\", \"BTC-USD\", \"DOGE-USD\", \"DOT-USD\", \"ETH-USD\", \"LINK-USD\", \"LTC-USD\", \"SOL-USD\", \"SUI-USD\", \"XRP-USD\"]'",
              "\"active_tickers\", '[\"ADA-USD\", \"BTC-USD\", \"DOGE-USD\", \"DOT-USD\", \"ETH-USD\", \"LINK-USD\", \"LTC-USD\", \"SOL-USD\", \"XRP-USD\"]'")

# Verify compiles
compile(m, "main.py", "exec")
print("Compile OK")

with open(B + "/main.py", "w") as f:
    f.write(m)
print("DONE: Fixed get_equity sig, DB function names, SUI-USD removal")

# ─── Also fix the DB directly ───
import sqlite3, json
db_path = "/root/.nexustrader/nexustrader.db"
try:
    conn = sqlite3.connect(db_path)
    # Remove SUI-USD from active_tickers in settings
    cur = conn.execute("SELECT value FROM settings WHERE key = 'active_tickers'")
    row = cur.fetchone()
    if row:
        tickers = json.loads(row[0])
        if "SUI-USD" in tickers:
            tickers.remove("SUI-USD")
            conn.execute("UPDATE settings SET value = ? WHERE key = 'active_tickers'", 
                        (json.dumps(tickers),))
            conn.commit()
            print(f"DB: Removed SUI-USD. Active tickers now: {tickers}")
    # Also deactivate SUI-USD in assets table
    conn.execute("UPDATE assets SET is_active = 0 WHERE ticker = 'SUI-USD'")
    conn.commit()
    print("DB: Deactivated SUI-USD in assets table")
    conn.close()
except Exception as e:
    print(f"DB update skipped: {e}")
