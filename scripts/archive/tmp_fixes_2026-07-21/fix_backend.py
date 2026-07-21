import re

# Fix main.py
with open("/root/nexustrader/main.py", "r") as f:
    main = f.read()

# 1. Fix /api/status to return PnL from trades table
old_status = """@app.get("/api/status")
def get_status():
    current_prices = {}
    for t in orchestrator.tickers:
        if t in orchestrator.data_ingestions:
            current_prices[t] = orchestrator.data_ingestions[t].live_price or 0.0
            
    return {
        "balance": orchestrator.execution_engine.balance,
        "equity": orchestrator.execution_engine.get_equity(current_prices),
        "positions": orchestrator.execution_engine.active_positions,
        "tickers": orchestrator.tickers
    }"""

new_status = """@app.get("/api/status")
def get_status():
    current_prices = {}
    for t in orchestrator.tickers:
        if t in orchestrator.data_ingestions:
            current_prices[t] = orchestrator.data_ingestions[t].live_price or 0.0
    
    # Calculate total PnL from closed trades
    total_pnl = 0.0
    total_closed = 0
    winning_trades = 0
    try:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), COALESCE(SUM(pnl),0) FROM trades WHERE trading_mode = 'live'")
        cnt, pnl_sum = cursor.fetchone()
        total_closed = cnt or 0
        total_pnl = float(pnl_sum or 0.0)
        cursor.execute("SELECT COUNT(*) FROM trades WHERE trading_mode = 'live' AND pnl > 0")
        winning_trades = cursor.fetchone()[0] or 0
        conn.close()
    except Exception:
        pass
    
    balance = orchestrator.execution_engine.balance
    equity = orchestrator.execution_engine.get_equity(current_prices)
    
    return {
        "balance": balance,
        "equity": equity,
        "total_pnl": round(total_pnl, 2),
        "closed_trades": total_closed,
        "winning_trades": winning_trades,
        "open_positions": len(orchestrator.execution_engine.active_positions),
        "daily_pnl": round(getattr(kill_switch, 'daily_pnl', 0.0), 2),
        "daily_pnl_pct": round((kill_switch.daily_pnl / equity * 100) if equity > 0 else 0.0, 4),
        "positions": orchestrator.execution_engine.active_positions,
        "tickers": orchestrator.tickers,
        "initial_balance": float(database.load_setting("initial_portfolio_balance", "100.0")),
    }"""

assert old_status in main, "Failed: /api/status endpoint not found"
main = main.replace(old_status, new_status)

# 2. Fix training mode reset to NOT nuke the execution engine state
old_training_init = """        orchestrator.execution_engine = ExecutionEngine(initial_balance=100.0)"""
new_training_init = """        # Reset sim state but keep actual balance for live mode
        if orchestrator.execution_engine:
            sim_balance = database.load_setting("simulation_starting_balance", "100.0")
            orchestrator.execution_engine.balance = float(sim_balance)"""

assert old_training_init in main, "Failed: training init endpoint not found"
main = main.replace(old_training_init, new_training_init)

# 3. Fix update_system_config to not overwrite initial_balance when not explicitly set
old_config_balance = """    if initial_balance is not None:
        database.save_setting("initial_portfolio_balance", str(initial_balance))
        database.save_setting("initial_balance_is_custom", "true")
        orchestrator.execution_engine.initial_balance = float(initial_balance)
        logging.info(f"Initial portfolio balance baseline updated to: ${initial_balance:.2f}")"""  
new_config_balance = """    if initial_balance is not None and initial_balance > 0:
        database.save_setting("initial_portfolio_balance", str(initial_balance))
        database.save_setting("initial_balance_is_custom", "true")
        if orchestrator.execution_engine:
            orchestrator.execution_engine.initial_balance = float(initial_balance)
            orchestrator.execution_engine.balance = float(initial_balance)
        database.save_setting("initial_balance_is_custom", "true")
        logging.info(f"Initial portfolio balance baseline updated to: ${initial_balance:.2f}")"""

assert old_config_balance in main, "Failed: config balance update not found"
main = main.replace(old_config_balance, new_config_balance)

with open("/root/nexustrader/main.py", "w") as f:
    f.write(main)

print("main.py fixed OK")
