# PhD Quant Optimizer — Prompt Self-Optimization Analysis

## Observed Failures in Current Prompt

### 1. No Hard Capital Floor
Current prompt asks for capital adequacy CHECK but has no STOP condition. With €5.80 capital, the bot keeps churning parameters when $1K/day is mathematically impossible (requires 15,384% daily return). The prompt must **reject optimization** below a capital threshold.

### 2. No Throughput Feasibility Gate
$1K/day requires solving: `win_rate × avg_win × trades_per_day = 1000`. Current prompt doesn't compute this equation or compare it against historical stats. It should reject parameter suggestions that can't mathematically reach $1K throughput.

### 3. Statistical Gate Too Weak
"Trades < 30 → insufficient data" is a warning, not a blocker. With N=10 (all losing except 2), the prompt should **refuse to optimize hyperparameters** and instead demand a different approach.

### 4. No Regime Signal Calibration
The Kalman filter at 0.0005 threshold was flagged by Developer as destructive, but the prompt doesn't check signal filter parameters (Kalman threshold, RSI period) for compatibility with regime. The Kalman is set to respond to 0.05% moves in a market with 4% ATR.

### 5. No Min-Capital Escalation Path
There's no "if capital < $100" special case. The prompt treats $6 the same as $60,000. Tiny capital needs **aggressive positioning just to be meaningful**, but the current prompt might push conservative on small capital — which guarantees zero revenue forever.

### 6. Strategy Disqualification Is Too Lenient
EMA Crossover at 12.5% win rate with N=8 is NOT "insufficient data" — it's 8 consecutive failures with a statistically significant negative bias. The prompt should apply Bayesian priors: with prior expectation of ~50%, 1/8 wins is strong evidence of a broken strategy.

### 7. No Signal-to-Noise Ratio Check
The Kalman and RSI operate at incompatible time scales (sub-minute vs 14-period). The prompt doesn't detect or flag conflicting signal filter calibrations.

### 8. JSON Output Lacks Critical Fields
No `capital_emergency_stop`, no `throughput_feasibility`, no `signal_calibration_checks`, no `min_capital_for_target`.

## Required Prompt Redesign Principles

1. **Absolute capital floor**: If capital < $1K, optimization is pointless. Demand deposit or accept that $1K/day is unreachable.
2. **Throughput equation required**: Compute `(capital × win_rate × avg_return × trades_per_day) ≥ 1000`. If not, flag impossible.
3. **Signal filter audit**: Require Kalman threshold, RSI periods, and BB deviation to be checked for time-scale compatibility.
4. **Bayesian strategy disqualification**: Use prior + likelihood for small samples instead of frequentist gates.
5. **Tiny-capital special mode**: Below $500, override to hyper-aggressive (full Kelly, 3x ATR SL, 3-5x TP) because eating 2% of $6 accomplishes nothing.
6. **Capital injection recommendation**: If impossible to reach $1K/day, explicitly recommend deposit amount and new target.
7. **Phase-gated recommendations**: Phase 1 = survival/calibration (N<100), Phase 2 = optimization (N<500), Phase 3 = throughput tuning (N≥500).
