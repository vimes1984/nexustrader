# Prompt Evaluation

## Current Prompt Analysis

**Strengths:**
- Clear persona: PhD Quantitative Risk Officer & Long-Term Strategy Architect
- Explicit target: $1K/day profit
- Specific levers to tune: volatility sizing, Kalman filter, neural gating
- Structured JSON output schema

**Weaknesses:**
- Vague persona that encourages wordy "I'm a PhD" preamble instead of direct analysis
- No explicit methodology for how to compute win rates, expectancy, or required capital
- Missing guardrails: no minimum data requirements, no convergence checks, no regime detection
- No agentic workflow: doesn't tell the agent to chain through analysis steps before producing JSON
- No range bounds on output parameters — risk of unfiltered suggestions (e.g., TP at 50 ATR)
- No self-critique/validation step before final output
- Static persona doesn't adapt to market regime changes
- No explicit instruction to handle edge cases (no trades, NaN values, zero capital)
- Lacks a "stop and reject" clause for low-confidence settings

## Key Improvements Needed
1. **Structured chain-of-thought** — enforce step-by-step analysis before JSON
2. **Statistical rigor** — require confidence intervals, min sample sizes, correlation checks
3. **Bound constraints** — clamp all output parameters to safe ranges
4. **Regime context** — force explicit identification of current market regime
5. **Self-validation** — agent must verify its own math (expectancy check, Kelly consistency)
6. **Edge case handling** — explicit handling of missing/insufficient data
7. **Safety-first** — reject changes that increase risk of ruin regardless of profit target
