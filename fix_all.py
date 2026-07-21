#!/usr/bin/env python3
"""COMPREHENSIVE FIX: All remaining NexusTrader issues.

1. Add save_trade() calls to trade close flow
2. Add /api/init endpoint
3. Fix sqlite3.Row .get() error
4. Add /api/trading/signals if missing  
5. Verify PPO imports work
"""
import os, sys

os.chdir("/root/nexustrader")
sys.path.insert(0, ".")

with open("main.py") as f:
    content = f.read()
    original = content

changes = []

# ============================================================
# FIX 1: Add save_trade() to the trade close flow
# ============================================================
# Find on_trade_closed and add database.save_trade() at the top
# The function signature is: def on_trade_closed(self, ticker, entry_state, strategy_signals, direction, pnl_percent):
# We need to find where the position is and save it

old_trade_close = """    def on_trade_closed(self, ticker, entry_state, strategy_signals, direction, pnl_percent):
        \"\"\"Callback from ExecutionEngine when a trade is closed.\"\"\"
        logging.info(f\"[{ticker}] Trade closed with PnL%: {pnl_percent*100:.2f}%. Training Policy Network...\")"""

new_trade_close = """    def on_trade_closed(self, ticker, entry_state, strategy_signals, direction, pnl_percent):
        \"\"\"Callback from ExecutionEngine when a trade is closed.\"\"\"
        logging.info(f\"[{ticker}] Trade closed with PnL%: {pnl_percent*100:.2f}%. Training Policy Network...\")
        
        # CRITICAL: Save trade to database for persistence
        try:
            import database as _db_t
            pos = self.execution_engine.active_positions.get(ticker, {})
            if pos and pos.get('entry_price'):
                trade_data = {
                    "symbol": ticker,
                    "direction": pos.get('direction', direction or 'UNKNOWN'),
                    "quantity": float(pos.get('quantity', 0)),
                    "entry_price": float(pos.get('entry_price', 0)),
                    "exit_price": float(pos.get('stop_loss', pos.get('take_profit', 0))),
                    "pnl": float(pnl_percent) * float(self.execution_engine.balance) * 0.01,
                    "pnl_percent": float(pnl_percent),
                    "exit_reason": pos.get('exit_reason', 'tp_sl'),
                    "entry_time": float(pos.get('entry_time', 0)),
                    "exit_time": time.time(),
                    "strategy_signals": strategy_signals or pos.get('strategy_signals', []),
                    "sentiment_sources": pos.get('sentiment_sources', {}),
                    "policy_brain": pos.get('policy_brain', database.load_setting(f"active_policy_brain_{ticker}", "Default Brain")),
                    "trading_mode": getattr(self.execution_engine, 'trading_mode', 'paper'),
                    "strategy": pos.get('strategy_signals', strategy_signals or [None])[0] if (pos.get('strategy_signals') or strategy_signals) else None,
                }
                _db_t.save_trade(trade_data)
                logging.info(f"[{ticker}] Trade SAVED to database: dir={trade_data['direction']} qty={trade_data['quantity']} pnl={trade_data['pnl']:.4f}")
            else:
                logging.warning(f"[{ticker}] No active position found to save as trade (pos={pos})")
        except Exception as _te:
            logging.error(f"[{ticker}] Failed to save trade: {_te}")"""

if old_trade_close in content:
    content = content.replace(old_trade_close, new_trade_close)
    changes.append("Added save_trade() call to on_trade_closed")
else:
    print("WARN: on_trade_closed start pattern not found")
    idx = content.find("def on_trade_closed(self")
    if idx > 0:
        print("  Found at", idx)

# ============================================================
# FIX 2: Add /api/init endpoint before __main__
# ============================================================
if "/api/init" not in content:
    init_ep = '''
@app.get("/api/init")
async def api_init():
    """Fast init endpoint - no exchange dependency."""
    import database as _db_i
    try:
        orb = globals().get("orchestrator")
        if not orb:
            return {"error": "Not initialized"}
        
        trades = _db_i.load_trades()
        total_pnl = sum(float(t.get("pnl", 0.0) or 0.0) for t in trades)
        
        ee = orb.execution_engine
        first_ticker = orb.tickers[0] if orb.tickers else ""
        ensemble = orb.strategy_ensembles.get(first_ticker) if hasattr(orb, "strategy_ensembles") else None
        
        active_brains = {}
        for t in orb.tickers:
            active_brains[t] = database.load_setting("active_policy_brain_" + t, "Default Brain")
        
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
            "equity_history": [],
        }
    except Exception as e:
        return {"error": str(e)}

'''
    marker = '# Serve Frontend SPA\n@app.get("/")'
    if marker in content:
        content = content.replace(marker, init_ep + "\n" + marker)
    else:
        marker = 'if __name__ == "__main__":'
        content = content.replace(marker, init_ep + "\n" + marker)
    changes.append("Added /api/init endpoint")

# ============================================================
# FIX 3: Fix sqlite3.Row .get() error
# ============================================================
# In process_tick, row is sometimes a sqlite3.Row from DB query
# Ensure row is dict before using .get()
old_tick_signals = """        row['sentiment'] = self.latest_sentiments.get(ticker, 0.0)
        row['sentiment_sources'] = self.latest_source_sentiments.get(ticker, {})
        
        # Feature engineering for probabilities"""

new_tick_signals = """        # Ensure row is a proper dict (not sqlite3.Row)
        if hasattr(row, 'keys') and not isinstance(row, dict):
            row = dict(row)
        row['sentiment'] = self.latest_sentiments.get(ticker, 0.0)
        row['sentiment_sources'] = self.latest_source_sentiments.get(ticker, {})
        
        # Feature engineering for probabilities"""

if old_tick_signals in content:
    content = content.replace(old_tick_signals, new_tick_signals)
    changes.append("Fixed sqlite3.Row dict conversion in process_tick")
else:
    # Try alternate pattern
    idx = content.find("row['sentiment'] = self.latest_sentiments")
    if idx > 0:
        print(f"  Found sentiment assignment at {idx}")

# ============================================================
# FIX 4: Check /api/trading/signals exists
# ============================================================
if "trading/signals" not in content:
    signals_ep = '''
@app.get("/api/trading/signals")
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
        return sigs
    except Exception as e:
        return {"error": str(e), "signals": {}}

'''
    marker = '# Serve Frontend SPA\n@app.get("/")'
    if marker in content:
        content = content.replace(marker, signals_ep + "\n" + marker)
    changes.append("Added /api/trading/signals endpoint")
else:
    changes.append("/api/trading/signals already exists")

# ============================================================
# FIX 5: Verify PPO imports work  
# ============================================================
# The PPOAgent is created from learner.policy_net - need to verify
# create_learning_engine returns a LearningEngine with .policy_net
old_ppo_init = """        ppo_agent = PPOAgent(learner.policy_net)
        self.ppo_agents[ticker] = ppo_agent"""

new_ppo_init = """        # Create PPO agent wrapping existing policy network
        if hasattr(learner, 'policy_net') and learner.policy_net is not None:
            ppo_agent = PPOAgent(learner.policy_net)
            self.ppo_agents[ticker] = ppo_agent
            logging.info(f"PPO agent created for {ticker} with {sum(1 for _ in learner.policy_net.parameters())} params")
        else:
            logging.warning(f"No policy_net available for {ticker}, skipping PPO")
            self.ppo_agents[ticker] = None"""

if old_ppo_init in content:
    content = content.replace(old_ppo_init, new_ppo_init)
    changes.append("Hardened PPO agent init")
else:
    print("PPO init pattern not found - checking...")
    idx = content.find("PPOAgent")
    if idx > 0:
        print(f"  Found PPOAgent at {idx}")

# Verify syntax
try:
    compile(content, "main.py", "exec")
    print(f"\nSyntax OK! {len(changes)} changes applied:")
    for c in changes:
        print(f"  ✓ {c}")
    with open("main.py", "w") as f:
        f.write(content)
    print("\nmain.py written successfully")
except SyntaxError as e:
    print(f"\nSyntax ERROR: {e}")
    lines = content.split('\n')
    if e.lineno:
        for i in range(max(1, e.lineno-3), min(len(lines), e.lineno+3)):
            print(f"  {i+1}: {lines[i]}")
