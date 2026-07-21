# Prompt Self-Improvement Analysis

## Critical Gaps Identified

1. **Account equity is unstated in current prompt** — Blog data shows ~€5.80 equity. $1,000/day = 17,241% daily return. The prompt must force a viability gate.

2. **No minimum sample size** — 10 trades, 10% win rate is statistically meaningless. Need confidence interval enforcement.

3. **No throughput feasibility check** — Expected daily return = expectancy × trades_per_day. Must be ≥ $1,000 or the JSON must state `is_feasible: false` and explain bridge.

4. **No cross-source reconciliation** — Developer audit flags 5% loss limit as dangerous. Blogger shows systematic losses. Session data shows 3 trades cleaned. The prompt must force synthesis.

5. **JSON is too narrow** — Missing: daily_loss_limit, cooldown_hours, kelly_fraction, max_concurrent_positions, min_sharpe_ratio, is_feasible, feasibility_gap_usd, required_equity_increase.
