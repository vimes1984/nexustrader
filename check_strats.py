import sys, os
os.chdir("/root/nexustrader")
sys.path.insert(0, "/root/nexustrader")

# Don't import main (starts app), just check the orchestrator
# The startup will have initialized it
from main import orchestrator

print("Tickers:", orchestrator.tickers)
print()
print("Strategy Ensembles:")
for ticker in orchestrator.strategy_ensembles:
    se = orchestrator.strategy_ensembles[ticker]
    s = se.strategies
    print(f"  {ticker}: {len(s)} strategies")
    for st in s:
        print(f"    - {st.name}")
print()
print("Data ingestions:", list(orchestrator.data_ingestions.keys()))
print("Learning engines:", list(orchestrator.learning_engines.keys()))
print("Active positions:", orchestrator.execution_engine.active_positions)
print("Balance:", orchestrator.execution_engine.balance)
print("Mode:", orchestrator.execution_engine.trading_mode)
