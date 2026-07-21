# Self-Analysis: Quant Optimizer Prompt Gaps

## Issues Found vs Current Prompt

| Gap | Current Prompt | Required Fix |
|-----|---------------|--------------|
| Min trade count | None | Reject if < 20 trades |
| Statistical significance | None | p-values, confidence intervals |
| Market regime detection | None | OU parameter classification |
| Per-strategy decomposition | None | Win rate + PnL per strategy |
| Correlation matrix | None | Flag >0.70 pairs, demand hedges |
| NN hyperparameter validation | None | LR, grad clip, entropy, convergence |
| Risk of ruin | None | Math-based RoR with survival prob |
| Position sizing | None | % of NAV tracking |
| Sharpe/Sortino/Calmar | None | Standard risk-adjusted metrics |
| $1K/day throughput | Implied only | Hard constraint with math check |
| Convergence criteria | None | Checklist before accepting stability |
| Rejection protocol | None | Mandatory if insufficient data |
| Adaptive LR recommendation | None | Required output field |
| Regime-parameter mapping | None | Different params per regime state |
