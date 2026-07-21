#!/usr/bin/env python3
"""Restore reasoning + fix endpoints removed by PPO sub-agent."""
import os
os.chdir("/root/nexustrader")

with open("main.py") as f:
    c = f.read()

# Add reasoning + fix endpoints right before /api/init
marker = '@app.get("/api/init")'

reasoning_endpoints = '''
@app.get("/api/trading/reasoning")
async def api_trading_reasoning():
    """Diagnostic reasoning: per-ticker strategy counts and health."""
    try:
        orb = globals().get("orchestrator")
        if not orb:
            return {"error": "Not initialized", "items": []}
        items = []
        
        # Strategy counts per ticker
        for t in orb.tickers:
            ensemble = orb.strategy_ensembles.get(t)
            n_strats = len(ensemble.strategies) if ensemble else 0
            active_brain = database.load_setting("active_policy_brain_" + t, "Default Brain")
            
            signal_info = "neutral"
            latest = orb.latest_ticks.get(t, {})
            price = latest.get("close", 0) or latest.get("price", 0)
            
            ws = orb.latest_signals.get(t, 0.0)
            if ws > 0.05: signal_info = "bullish"
            elif ws < -0.05: signal_info = "bearish"
            
            items.append({
                "id": "strat_" + t.replace("-", "_").lower(),
                "severity": "info",
                "title": t + ": " + str(n_strats) + " strategies",
                "detail": "Brain: " + active_brain + " | Signal: " + signal_info + " (ws=" + str(round(ws, 4)) + ")",
                "fix": None,
            })
        
        # KillSwitch status
        safe, reason = kill_switch.check()
        if not safe:
            items.append({
                "id": "killswitch",
                "severity": "critical",
                "title": "KillSwitch TRIPPED",
                "detail": "Reason: " + (reason or "unknown"),
                "fix": {"action": "reset_killswitch", "label": "Reset KillSwitch"},
            })
        else:
            items.append({
                "id": "killswitch",
                "severity": "success",
                "title": "KillSwitch is safe",
                "detail": "No safety violations detected",
                "fix": None,
            })
        
        # Trade count
        all_trades = database.load_trades()
        live_trades = [t for t in all_trades if t.get("trading_mode") == "live"]
        items.append({
            "id": "trades",
            "severity": "info",
            "title": str(len(all_trades)) + " total trades (" + str(len(live_trades)) + " live)",
            "detail": "Last trade: " + (str(all_trades[-1].get("symbol", "N/A")) + " " + str(all_trades[-1].get("direction", "")) + " PnL: " + str(round(all_trades[-1].get("pnl", 0), 4)) if all_trades else "No trades"),
            "fix": None,
        })
        
        # Balance / Mode
        ee = orb.execution_engine
        items.append({
            "id": "mode",
            "severity": "info",
            "title": "Mode: " + getattr(ee, "trading_mode", "paper"),
            "detail": "Balance: $" + str(round(ee.balance, 2)) + " | Equity: $" + str(round(getattr(ee, "live_equity", ee.balance), 2)),
            "fix": {"action": "toggle_mode", "label": "Switch mode"} if getattr(ee, "trading_mode", "paper") == "live" else None,
        })
        
        # EUR balance warning
        if hasattr(ee, "live_holdings") and ee.live_holdings:
            eur = float(ee.live_holdings.get("EUR", 0) or 0)
            if eur > 5.0:
                items.append({
                    "id": "eur_balance",
                    "severity": "warning",
                    "title": "EUR balance: " + str(round(eur, 2)) + " EUR",
                    "detail": "Convert EUR to USD for more trading power",
                    "fix": {"action": "convert_eur", "label": "Convert EUR to USD"},
                })
        
        # Stream status
        stream_active = getattr(orb, "is_simulating", False) or getattr(orb, "mode", None) in ("live", "simulation")
        if stream_active:
            items.append({
                "id": "stream",
                "severity": "success",
                "title": "Data stream active",
                "detail": "Polling live data every 5s",
                "fix": None,
            })
        
        return {"items": items, "status": "ok"}
    except Exception as e:
        return {"items": [{"id": "error", "severity": "error", "title": str(e), "detail": "", "fix": None}], "status": "error"}


@app.post("/api/trading/fix")
async def api_trading_fix(request: Request):
    """Execute a fix action."""
    data = await request.json()
    action = data.get("action", "")
    try:
        orb = globals().get("orchestrator")
        if not orb:
            return {"status": "error", "message": "Not initialized"}
        
        if action == "toggle_mode":
            import threading
            def do_toggle():
                try:
                    old = orb.execution_engine.trading_mode
                    orb.execution_engine.trading_mode = "simulation" if old == "live" else "live"
                    database.save_setting("trading_mode", orb.execution_engine.trading_mode)
                    logging.info("Trading mode toggled: " + old + " -> " + orb.execution_engine.trading_mode)
                except Exception as e:
                    logging.error("Toggle failed: " + str(e))
            threading.Thread(target=do_toggle, daemon=True).start()
            return {"status": "ok", "message": "Toggling mode..."}
        
        elif action == "reset_killswitch":
            kill_switch.reset()
            database.save_setting("killswitch_state", json.dumps(kill_switch.to_dict()))
            return {"status": "ok", "message": "KillSwitch reset"}
        
        elif action == "convert_eur":
            import threading
            def do_convert():
                try:
                    ee = orb.execution_engine
                    if hasattr(ee, "convert_fiat_to_usd"):
                        ee.convert_fiat_to_usd()
                except Exception as e:
                    logging.error("FIAT conversion failed: " + str(e))
            threading.Thread(target=do_convert, daemon=True).start()
            return {"status": "ok", "message": "Converting EUR to USD..."}
        
        elif action == "reload_strategies":
            import threading
            def do_reload():
                for t in orb.tickers:
                    if t in orb.data_ingestions:
                        ing = orb.data_ingestions[t]
                        try:
                            ing.fetch_historical_data()
                        except Exception as e:
                            logging.error("Reload failed for " + t + ": " + str(e))
            threading.Thread(target=do_reload, daemon=True).start()
            return {"status": "ok", "message": "Reloading strategies..."}
        
        elif action == "start_stream":
            import threading
            def do_start():
                orb.start_stream(mode="live", poll_interval=5)
            threading.Thread(target=do_start, daemon=True).start()
            return {"status": "ok", "message": "Starting stream..."}
        
        else:
            return {"status": "error", "message": "Unknown action: " + action}
    except Exception as e:
        return {"status": "error", "message": str(e)}

'''

if marker in c:
    c = c.replace(marker, reasoning_endpoints + "\n" + marker)
    print("Restored reasoning + fix endpoints")
else:
    print("Marker not found")
    idx = c.find("api/init")
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
