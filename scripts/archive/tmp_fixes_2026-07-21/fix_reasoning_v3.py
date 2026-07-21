"""
Fix /api/init to actually populate strategies/weights/brains from orchestrator
Rewrite /api/trading/reasoning with fix-it actions
Add POST /api/trading/fix endpoint
"""
import os
os.chdir("/root/nexustrader")

with open("main.py") as f:
    content = f.read()

# ============ FIX 1: /api/init - populate strategies from orchestrator ============

old_init_strategies = """    # Collect weights and strategies (simple version)
    weights = {}
    strategies = []

    return {
        "type": "init",
        "tickers": orchestrator.tickers,
        "ticker": active_ticker,
        "balance": balance,
        "equity": equity,
        "total_pnl": round(total_pnl, 2),
        "trading_mode": trading_mode,
        "trades": db_trades,
        "ticker_prices": current_prices,
        "initial_balance": orchestrator.execution_engine.initial_balance or 100,
        "weights": weights,
        "strategies": strategies,
        "active_brains": {},
        "risk_mode": "moderate",
        "broker": "kraken",
        "lifetime_steps": 0,
        "model_dna": "REST",
    }"""

new_init_strategies = """    # Collect weights and strategies from orchestrator
    weights = {}
    strategies = []
    active_brains = {}
    for ticker in orchestrator.tickers:
        ensemble = orchestrator.strategy_ensembles.get(ticker)
        if ensemble:
            weight_map = {}
            for i, s in enumerate(ensemble.strategies):
                w = ensemble.weights[i] if i < len(ensemble.weights) else 0
                weight_map[s.name] = float(w)
            weights[ticker] = weight_map
            strategies.append({
                "ticker": ticker,
                "names": [s.name for s in ensemble.strategies],
                "count": len(ensemble.strategies)
            })
        active_name = database.load_setting(f"active_policy_brain_{ticker}", "Default Brain")
        if active_name:
            active_brains[ticker] = active_name

    return {
        "type": "init",
        "tickers": orchestrator.tickers,
        "ticker": active_ticker,
        "balance": balance,
        "equity": equity,
        "total_pnl": round(total_pnl, 2),
        "trading_mode": trading_mode,
        "trades": db_trades,
        "ticker_prices": current_prices,
        "initial_balance": orchestrator.execution_engine.initial_balance or 100,
        "weights": weights,
        "strategies": strategies,
        "active_brains": active_brains,
        "risk_mode": "moderate",
        "broker": "kraken",
        "lifetime_steps": 0,
        "model_dna": "REST",
    }"""

content = content.replace(old_init_strategies, new_init_strategies)

# ============ FIX 2: Rewrite trading/reasoning with fix actions ============

old_reasoning = '''@app.get("/api/trading/reasoning")
def get_trading_reasoning():
    import datetime
    try:
        reasons = []
        summary = "active"
        last_trade_ts = 0
        ee = orchestrator.execution_engine
        
        if hasattr(ee, "strategies") and ee.strategies:
            reasons.append({"type": "info", "message": f"{len(ee.strategies)} strategy(ies) loaded."})
        else:
            reasons.append({"type": "warning", "message": "No strategies loaded in ensemble. No signals generated. This is why no trades."})
            summary = "idle"
        
        ks = getattr(ee, "kill_switch", {})
        if isinstance(ks, dict) and ks.get("tripped"):
            reasons.append({"type": "critical", "message": "KillSwitch TRIPPED: " + str(ks.get("trigger_reason", "unknown"))})
            summary = "halted"
        else:
            reasons.append({"type": "success", "message": "KillSwitch safe."})
        
        trades = getattr(ee, "closed_trades", [])
        for t in trades:
            et = t.get("exit_time", 0)
            if et > last_trade_ts:
                last_trade_ts = et
        if last_trade_ts:
            last_str = datetime.datetime.fromtimestamp(last_trade_ts, tz=datetime.timezone.utc).strftime("%b %d %H:%M UTC")
            hours = (time.time() - last_trade_ts) / 3600
            if hours > 3:
                reasons.append({"type": "warning", "message": f"Last trade: {last_str} ({hours:.0f}h ago). Idle since."})
                if summary == "active":
                    summary = "inactive"
            else:
                reasons.append({"type": "success", "message": f"Last trade: {last_str}."})
        else:
            reasons.append({"type": "info", "message": "No completed trades yet."})
        
        pos = getattr(ee, "active_positions", {})
        if pos:
            reasons.append({"type": "info", "message": f"{len(pos)} open position(s)."})
        else:
            reasons.append({"type": "info", "message": "No open positions. Waiting for entry signals."})
        
        mode = getattr(ee, "trading_mode", "unknown")
        reasons.append({"type": "info", "message": "Mode: " + mode.upper()})
        
        return {
            "status": summary,
            "trading_mode": mode,
            "open_positions": len(pos),
            "reasons": reasons,
            "last_trade_time": int(last_trade_ts),
        }
    except Exception as e:
        logging.error(f"Trading reasoning error: {e}")
        return {"status": "error", "reasons": [{"type": "error", "message": str(e)}]}'''

new_reasoning = '''@app.get("/api/trading/reasoning")
def get_trading_reasoning():
    import datetime
    try:
        ee = orchestrator.execution_engine
        items = []
        summary = "active"
        last_trade_ts = 0
        
        # === STRATEGIES ===
        # Check per-ticker ensembles for actual strategy loading
        total_strats = 0
        strat_issues = []
        for ticker in orchestrator.tickers:
            ensemble = orchestrator.strategy_ensembles.get(ticker)
            if ensemble and hasattr(ensemble, "strategies") and ensemble.strategies:
                total_strats += len(ensemble.strategies)
            else:
                strat_issues.append(ticker)
        
        if strat_issues:
            items.append({
                "id": "no_strategies",
                "severity": "critical",
                "title": "No trading strategies loaded",
                "detail": f"{len(strat_issues)} ticker(s) have no strategies loaded: {', '.join(strat_issues)}. Without strategies, no buy/sell signals can be generated — the bot is just watching prices.",
                "fix": {"action": "reload_strategies", "label": "Fix: Reload strategy ensembles for all tickers", "destructive": False}
            })
            summary = "idle"
        elif total_strats > 0:
            items.append({
                "id": "strategies_ok",
                "severity": "info",
                "title": f"{total_strats} strategies loaded across {len(orchestrator.tickers)} ticker(s)",
                "detail": "Strategies are active and generating signals.",
                "fix": None
            })
        else:
            items.append({
                "id": "no_strategies",
                "severity": "warning",
                "title": "No strategies available",
                "detail": "Strategy ensembles exist but contain zero strategies. Try reloading ticker data.",
                "fix": {"action": "reload_strategies", "label": "Fix: Reload strategy ensembles", "destructive": False}
            })
        
        # === KILL SWITCH ===
        ks = getattr(ee, "kill_switch", {})
        if isinstance(ks, dict) and ks.get("tripped"):
            reason = ks.get("trigger_reason", "Unknown trigger")
            items.append({
                "id": "killswitch_tripped",
                "severity": "critical",
                "title": "KillSwitch is TRIPPED — trading halted",
                "detail": f"The kill switch was triggered: {reason}. The bot will not open any new positions until the kill switch is reset.",
                "fix": {"action": "reset_killswitch", "label": "Fix: Reset KillSwitch and resume trading", "destructive": False}
            })
            summary = "halted"
        else:
            items.append({
                "id": "killswitch_ok",
                "severity": "success",
                "title": "KillSwitch is safe — not tripped",
                "detail": "The safety switch is disengaged. Trading is allowed.",
                "fix": None
            })
        
        # === LAST TRADE ===
        trades = getattr(ee, "closed_trades", [])
        for t in trades:
            et = t.get("exit_time", 0)
            if et > last_trade_ts:
                last_trade_ts = et
        if last_trade_ts:
            last_str = datetime.datetime.fromtimestamp(last_trade_ts, tz=datetime.timezone.utc).strftime("%b %d %H:%M UTC")
            hours = (time.time() - last_trade_ts) / 3600
            if hours > 6:
                items.append({
                    "id": "stale_trading",
                    "severity": "warning",
                    "title": f"No trades since {last_str} ({hours:.0f}h ago)",
                    "detail": f"The last trade completed {hours:.0f} hours ago. The bot is running and watching prices but hasn't found any favorable entries. This is normal if the strategy ensemble needs tuning or market conditions aren't meeting your criteria.",
                    "fix": None
                })
                if summary == "active":
                    summary = "inactive"
            elif hours > 2:
                items.append({
                    "id": "low_activity",
                    "severity": "info",
                    "title": f"Last trade: {last_str} ({hours:.0f}h ago)",
                    "detail": f"No recent trades in the last {hours:.0f} hours.",
                    "fix": None
                })
            else:
                items.append({
                    "id": "recent_trade",
                    "severity": "success",
                    "title": "Recent trade activity",
                    "detail": f"Last trade completed at {last_str} ({hours:.1f}h ago).",
                    "fix": None
                })
        else:
            items.append({
                "id": "no_trades",
                "severity": "info",
                "title": "No completed trades yet",
                "detail": "The bot hasn't closed any trades yet. It needs strategy signals and favorable market conditions.",
                "fix": None
            })
        
        # === OPEN POSITIONS ===
        pos = getattr(ee, "active_positions", {})
        if pos:
            pos_details = []
            for symbol, pdata in pos.items():
                qty = pdata.get("quantity", 0)
                entry = pdata.get("entry_price", 0)
                pos_details.append(f"{symbol}: {qty} @ ${entry}")
            items.append({
                "id": "open_positions",
                "severity": "info",
                "title": f"{len(pos)} open position(s)",
                "detail": "Currently holding: " + "; ".join(pos_details),
                "fix": {"action": "close_all_positions", "label": "Fix: Close all open positions now", "destructive": True}
            })
        else:
            items.append({
                "id": "no_positions",
                "severity": "info",
                "title": "No open positions",
                "detail": "No positions currently held. The bot is ready to enter trades when signals fire.",
                "fix": None
            })
        
        # === BALANCE / EQUITY ===
        balance = getattr(ee, "balance", 0)
        mode = getattr(ee, "trading_mode", "unknown")
        
        current_prices = {}
        for t in orchestrator.tickers:
            if t in orchestrator.data_ingestions:
                current_prices[t] = orchestrator.data_ingestions[t].live_price or 0.0
        equity = ee.get_equity(current_prices)
        
        items.append({
            "id": "financial_status",
            "severity": "info",
            "title": f"Mode: {mode.upper()} | Balance: ${balance:.2f} | Equity: ${equity:.2f}",
            "detail": f"Running in {mode.upper()} mode with ${balance:.2f} cash and ${equity:.2f} total equity. Mode switch available.",
            "fix": {"action": "toggle_mode", "label": "Fix: Switch to " + ("SIMULATION" if mode == "live" else "LIVE") + " mode", "destructive": mode == "live"}
        })
        
        # === STREAM STATUS ===
        stream_active = getattr(orchestrator, "is_simulating", False)
        if stream_active:
            items.append({
                "id": "stream_ok",
                "severity": "success",
                "title": "Data stream is active",
                "detail": "Price feeds are connected and processing ticks.",
                "fix": None
            })
        else:
            items.append({
                "id": "stream_inactive",
                "severity": "critical",
                "title": "Price stream is NOT running",
                "detail": "The data stream has stopped. No price updates are being processed.",
                "fix": {"action": "start_stream", "label": "Fix: Restart LIVE data stream", "destructive": False}
            })
            if summary == "active":
                summary = "error"
        
        return {
            "status": summary,
            "trading_mode": mode,
            "open_positions": len(pos),
            "items": items,
            "last_trade_time": int(last_trade_ts),
        }
    except Exception as e:
        logging.error(f"Trading reasoning error: {e}")
        return {"status": "error", "items": [{"id": "error", "severity": "critical", "title": "Analysis error", "detail": str(e), "fix": None}]}'''

content = content.replace(old_reasoning, new_reasoning)

# ============ FIX 3: Add POST /api/trading/fix endpoint ============

old_main_guard = '\nif __name__ == "__main__":'

fix_endpoint = '''

@app.post("/api/trading/fix")
def execute_trading_fix(data: dict):
    """Execute a fix action for a trading problem."""
    from fastapi import HTTPException
    action = data.get("action", "")
    if not action:
        return {"status": "error", "message": "No action specified"}
    
    try:
        if action == "reload_strategies":
            for ticker in orchestrator.tickers:
                if ticker not in orchestrator.data_ingestions:
                    orchestrator.init_ticker(ticker)
                elif ticker in orchestrator.strategy_ensembles:
                    se = orchestrator.strategy_ensembles[ticker]
                    if not se.strategies:
                        # Re-init just this ensemble
                        ingestor = orchestrator.data_ingestions[ticker]
                        df = ingestor.get_recent_bars(100)
                        if df is not None:
                            from strategy_ensemble import StrategyEnsemble
                            new_se = StrategyEnsemble(history_df=df)
                            orchestrator.strategy_ensembles[ticker] = new_se
                            logging.info(f"Reloaded strategy ensemble for {ticker}: {len(new_se.strategies)} strategies")
            return {"status": "ok", "message": f"Strategies reloaded for {len(orchestrator.tickers)} tickers"}
        
        elif action == "reset_killswitch":
            if isinstance(ks, dict):
                ks["tripped"] = False
                ks["trigger_reason"] = ""
            database.save_setting("killswitch_state", json.dumps(ks))
            return {"status": "ok", "message": "KillSwitch reset. Trading is now allowed."}
        
        elif action == "close_all_positions":
            count = 0
            current_prices = {}
            for t in orchestrator.tickers:
                if t in orchestrator.data_ingestions:
                    current_prices[t] = orchestrator.data_ingestions[t].live_price or 0.0
            for ticker in list(getattr(ee, "active_positions", {}).keys()):
                price = current_prices.get(ticker, 0)
                if price > 0:
                    ee.close_position(ticker, price)
                    count += 1
            return {"status": "ok", "message": f"Closed all {count} open position(s)"}
        
        elif action == "toggle_mode":
            ee = orchestrator.execution_engine
            current = getattr(ee, "trading_mode", "live")
            new_mode = "simulation" if current == "live" else "live"
            ee.trading_mode = new_mode
            database.save_setting("trading_mode", new_mode)
            ee.config["trading_mode"] = new_mode
            logging.info(f"Trading mode toggled: {current} -> {new_mode}")
            return {"status": "ok", "message": f"Switched to {new_mode.upper()} mode"}
        
        elif action == "start_stream":
            orchestrator.start_stream(mode="live", poll_interval=5)
            return {"status": "ok", "message": "Price stream started in LIVE mode"}
        
        else:
            return {"status": "error", "message": f"Unknown action: {action}"}
    
    except Exception as e:
        logging.error(f"Fix action '{action}' failed: {e}")
        return {"status": "error", "message": str(e)}
'''

content = content.replace(old_main_guard, fix_endpoint + old_main_guard)

with open("main.py", "w") as f:
    f.write(content)

print("OK - All 3 fixes applied")
print("1. /api/init now populates strategies/weights/brains from orchestrator")
print("2. /api/trading/reasoning rewritten with fix actions and plain English")
print("3. POST /api/trading/fix endpoint added")
