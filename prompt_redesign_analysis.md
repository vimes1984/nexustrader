# Allocator Prompt Redesign Analysis

## Current Prompt Weaknesses
1. **No $1K/day throughput math** — mentions scaling goal but doesn't require allocation decisions to prove they achieve it
2. **No Kelly fraction formula enforcement** — says "Kelly Ceiling caps" but doesn't demand the actual calculation
3. **No portfolio diversification floor** — doesn't enforce minimum active assets or max single-asset exposure
4. **No convergence criteria** — no check for minimum trades (N >= 30) before adjusting allocations
5. **No statistical significance** — accepts point estimates instead of Bayesian credible intervals
6. **No DB error handling** — "no such table: active_assets" crash shows no resilience

## Quant Recommendations to Incorporate
- Bayesian Beta-Binomial win-rate estimation (credible interval < 15% before tuning)
- ½ Kelly until N > 100
- Max 30% per asset, min 3 uncorrelated assets
- SL = 1.5× ATR (calibrated to noise std dev)
- SL width = √(σ_noise · R) formula
- Minimum 50 training samples across multiple regimes (from earlier Risk Auditor notes)

## Design Constraints for New Prompt
- Every allocation adjustment must include a $/day throughput projection
- Kelly ceilings must be computed from win-rate + risk/reward ratio
- Asset activation requires N >= 30 trades + credible interval < 15%
- Final JSON must include throughput_projection_usd field
- Must handle DB errors gracefully and report them in output
