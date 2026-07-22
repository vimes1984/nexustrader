# Allocator Agent Meta-Cognition Audit — 2026-07-22

## Critical Failure Modes Identified in Current Prompt

1. **No diversification floor** — Prompt permits single-asset allocation. Quant warned 100% SOL-USD is narrative-leveraged and catastrophic on chain outages.

2. **No fee drag computation** — At 0.16% Kraken fees with high trade frequency, fees consume ~1% of $1K daily target. Prompt silent on this.

3. **No Kalman threshold validation** — Doesn't cross-check signal parameters from other agents. 0.0005 threshold produces hundreds of micro-trades bleeding spread.

4. **No fractional Kelly enforcement** — "kelly_ceiling" field has no guardrails. Optimal Kelly at 55% WR / 2:1 R:R = 32.5% — insane without fractioning.

5. **No $1K/day throughput math** — Doesn't compute required capital, trades/day, or position sizes needed to hit the revenue target.

6. **No correlation matrix requirement** — Can't detect if allocated assets all move together.

7. **No SL/TP multiplier range validation** — 1x ATR SL gets wicked out constantly in crypto.

8. **No infrastructure health checks** — Failed sentiment feeds and missing DB tables go undetected.

9. **No convergence criteria** — Can report "stable" without validating anything.

10. **JSON output too thin** — Missing correlation, throughput estimates, fee projections, diversification score, parameter validation results.

## Required Prompt Redesign

- Start with $1K/day as the binding constraint
- Enforce minimum 3 assets with max 30% single-asset cap
- Fractional Kelly at max 0.25×
- Kalman threshold minimum 0.002 cross-check
- SL minimum 1.5x ATR
- Explicit fee drag projection
- Cross-agent parameter validation section
- Infrastructure health pre-check
- Convergence checklist
- Expand JSON with 20+ fields
