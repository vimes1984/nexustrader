with open("/root/nexustrader/main.py") as f:
    content = f.read()

old = '''    return {
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
        "ticker_prices": current_prices,
    }'''

new = '''    # Collect weights
    weights = {}
    if orchestrator.tickers:
        first = orchestrator.tickers[0]
        if first in orchestrator.strategy_ensembles:
            ens = orchestrator.strategy_ensembles[first]
            weights = getattr(ens, "weights", {})

    strategies = sorted(set(
        s for t in orchestrator.strategy_ensembles
        for s in orchestrator.strategy_ensembles[t].strategies
    )) if orchestrator.strategy_ensembles else []

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
    }'''

if old in content:
    content = content.replace(old, new)
    with open("/root/nexustrader/main.py", "w") as f:
        f.write(content)
    print("OK /api/init updated")
else:
    print("FAIL - return block not matched exactly")
    # Find the approximate location
    import re
    m = re.search(r'return \{.*?"initial_balance".*?\}', content, re.DOTALL)
    if m:
        print("Found approx match, length=%d" % len(m.group(0)))
        print("Match start:")
        print(m.group(0)[:100])
    else:
        print("No match at all")
