# Analysis: Current Prompt Gaps

1. **No scaling target baked in** — "safely scale to $1K/day" is aspirational, not operational. No capital requirement, no asset count targets.
2. **No data adequacy gate** — prompt says "analyze" regardless of sample size. Both quant and dev notes show it produced cargo-cult output because the prompt doesn't gate on minimum data.
3. **No tiered response logic** — should be: <10 trades = expansion priority; 10-50 = coarse tuning; 50+ = full Kelly/vol regime tuning.
4. **No capital projection** — doesn't compute: "at current avg win of $15, need X trades/day = impossible without leverage or more assets."
5. **No asset acquisition directive** — the #1 bottleneck is 1 asset. Prompt doesn't instruct to track asset pipeline, signal quality scores, or onboarding criteria.
6. **No risk-of-ruin vs target analysis** — $1K/day with 1 asset means extreme position sizing risk. Prompt should flag when path to target requires dangerous leverage.
7. **JSON output too narrow** — only per-ticker adjustments. Missing scaling_plan, data_quality flags, capital_projection.
