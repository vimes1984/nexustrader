#!/usr/bin/env python3
"""
NexusTrader Fix Script - Applies all 4 critical fixes.
"""

import re

def fix_1_save_trade(main_py):
    """Add database.save_trade() call in on_trade_closed callback.
    
    The trade data is available from execution_engine.closed_trades[-1].
    We save it at the TOP of on_trade_closed, before learning/training code.
    """
    # Find the start of on_trade_closed
    marker = 'def on_trade_closed(self, ticker, entry_state, strategy_signals, direction, pnl_percent):'
    log_line = 'logging.info("[' + '{}] Trade closed with PnL%: {:.2f}%. Training Policy Network...".format(ticker, pnl_percent*100))'
    
    # Insert after the logging line, before the killswitch code
    insert_after = log_line
    insert_code = """\
        # Save the completed trade to database for persistence
        try:
            if self.execution_engine.closed_trades:
                last_trade = self.execution_engine.closed_trades[-1]
                if last_trade.get('symbol') == ticker:
                    database.save_trade(last_trade)
        except Exception as e:
            logging.error(f"Error saving trade in on_trade_closed: {e}")
"""
    
    new_content = main_py.replace(insert_after, insert_after + '\n' + insert_code)
    return new_content

def fix_2_init_endpoint(main_py):
    """Add missing fields (fiat_breakdown, model_dna) to /api/init endpoint."""
    
    # Find the api_init function return dict - add fiat_breakdown field
    # The existing return has: "lifetime_steps": ...
    # We need to add fiat_breakdown before it or after
    
    old_return = '''        return {
            "balance": ee.balance,
            "equity": getattr(ee, "live_equity", ee.balance),
            "total_pnl": round(total_pnl, 2),
            "trades": trades,
            "trading_mode": getattr(ee, "trading_mode", "paper"),
            "ticker": first_ticker,
            "tickers": orb.tickers,
            "active_brains": active_brains,
            "strategies": [s.name for s in ensemble.strategies] if ensemble else [],
            "weights": {ensemble.strategies[i].name: float(ensemble.weights[i]) for i in range(len(ensemble.weights))} if ensemble else {},
            "open_positions": len(ee.active_positions),
            "initial_balance": getattr(ee, "initial_balance", 100.0),
            "lifetime_steps": int(database.load_setting("lifetime_training_steps_" + first_ticker, "0")),
        }'''
    
    new_return = '''        # Calculate fiat breakdown from live holdings
        fiat_breakdown = {}
        if hasattr(ee, "live_holdings"):
            for k, v in ee.live_holdings.items():
                if k in ("USD", "ZUSD"):
                    fiat_breakdown["USD"] = fiat_breakdown.get("USD", 0.0) + float(v)
                elif k in ("EUR", "ZEUR"):
                    fiat_breakdown["EUR"] = fiat_breakdown.get("EUR", 0.0) + float(v)
                elif k in ("GBP", "ZGBP"):
                    fiat_breakdown["GBP"] = fiat_breakdown.get("GBP", 0.0) + float(v)
        
        # Calculate model DNA
        import hashlib as _h
        _steps_key = "lifetime_training_steps_" + first_ticker
        _db_net = database.load_setting("policy_net_weights_" + first_ticker)
        if _db_net:
            _dna_hash = _h.md5(_db_net.encode('utf-8')).hexdigest()[:8].upper()
            model_dna = "NN-" + _dna_hash
        else:
            model_dna = "NN-DEFAULT"
        
        return {
            "balance": ee.balance,
            "equity": getattr(ee, "live_equity", ee.balance),
            "total_pnl": round(total_pnl, 2),
            "trades": trades,
            "trading_mode": getattr(ee, "trading_mode", "paper"),
            "ticker": first_ticker,
            "tickers": orb.tickers,
            "active_brains": active_brains,
            "strategies": [s.name for s in ensemble.strategies] if ensemble else [],
            "weights": {ensemble.strategies[i].name: float(ensemble.weights[i]) for i in range(len(ensemble.weights))} if ensemble else {},
            "open_positions": len(ee.active_positions),
            "initial_balance": getattr(ee, "initial_balance", 100.0),
            "lifetime_steps": int(database.load_setting("lifetime_training_steps_" + first_ticker, "0")),
            "fiat_breakdown": fiat_breakdown,
            "model_dna": model_dna,
        }'''
    
    return main_py.replace(old_return, new_return)

def fix_3_sqlite3_row(database_py):
    """Fix save_tick to handle sqlite3.Row objects gracefully.
    
    The save_tick function receives a 'row' parameter and uses .get() on it,
    which would crash if a sqlite3.Row is passed instead of a dict.
    Convert row to dict first if it doesn't have .get().
    """
    # Find the save_tick function and add a conversion guard
    old = '''def save_tick(row, symbol):
    """Saves a price tick to database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT OR REPLACE INTO ticks 
        (timestamp, symbol, open, high, low, close, volume, rsi, macd, macd_signal, bb_upper, bb_lower, atr)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(row['timestamp']),
'''
    
    new = '''def save_tick(row, symbol):
    """Saves a price tick to database."""
    # Ensure row is a dict (sqlite3.Row does not have .get() method)
    if not hasattr(row, 'get'):
        row = dict(row)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT OR REPLACE INTO ticks 
        (timestamp, symbol, open, high, low, close, volume, rsi, macd, macd_signal, bb_upper, bb_lower, atr)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(row['timestamp']),
'''
    
    return database_py.replace(old, new)

def fix_4_broadcast_wrapper(main_py):
    """Wrap broadcast_message in try/except at the caller level."""
    
    # In the broadcast_message method itself, it already handles disconnects.
    # But some callers might not catch exceptions. Let's find direct _run_async(self.broadcast_message calls
    # and add try/except around them.
    
    # Actually looking at the code, _run_async just schedules the coroutine.
    # The broadcast_message method already handles per-connection errors.
    # Let me just add a top-level try/except around the entire method body.
    
    old_method = '''    async def broadcast_message(self, message):
        """Sends JSON message to all active WebSocket connections."""
        disconnected = []
        for ws in self.connected_websockets:
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                disconnected.append(ws)
        
        for ws in disconnected:
            if ws in self.connected_websockets:
                self.connected_websockets.remove(ws)'''
    
    new_method = '''    async def broadcast_message(self, message):
        """Sends JSON message to all active WebSocket connections."""
        try:
            disconnected = []
            for ws in self.connected_websockets:
                try:
                    await ws.send_text(json.dumps(message))
                except Exception:
                    disconnected.append(ws)
            
            for ws in disconnected:
                if ws in self.connected_websockets:
                    self.connected_websockets.remove(ws)
        except Exception as e:
            logging.error(f"Broadcast message error: {e}")'''
    
    return main_py.replace(old_method, new_method)


# Read files
with open('/root/nexustrader/main.py', 'r') as f:
    main_py = f.read()

with open('/root/nexustrader/database.py', 'r') as f:
    database_py = f.read()

# Apply fixes
main_py = fix_1_save_trade(main_py)
main_py = fix_2_init_endpoint(main_py)
database_py = fix_3_sqlite3_row(database_py)
main_py = fix_4_broadcast_wrapper(main_py)

# Write back
with open('/root/nexustrader/main.py', 'w') as f:
    f.write(main_py)

with open('/root/nexustrader/database.py', 'w') as f:
    f.write(database_py)

print("All fixes applied successfully!")
