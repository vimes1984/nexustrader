# MEMORY.md - Keith's Long-Term Memory

## Chris preferences
- Chris dislikes silent long-running work.
- Chris wants the bot making money — profit-first mindset, compound growth. During active work, give concise progress updates when a task takes more than a short moment or has multiple steps.
- Be careful with paid/limited APIs. Prefer config/static verification first, avoid unnecessary live model/test calls, and say when a verification would spend API quota.

## NexusTrader Quant Team (2026-07-20)
Four OpenClaw cron agents manage the trading bot autonomously:
- 📊 **Quant Optimizer** (daily 1AM): tunes TP/SL, signal threshold, learning rate from trade outcomes
- 🛡️ **Risk Auditor** (daily 3AM): monitors drawdown, correlation, position sizing, risk of ruin
- ⚖️ **Allocator** (daily 4AM): rebalances ticker activation, Kelly ceilings, capital rotation
- 🔍 **Asset Selector** (every 14d): scans Kraken for new assets, disables delisted pairs

All agents SSH to 192.168.0.144 and can read/write DB + restart bot. Reports go to `blog/daily_summaries/`. Dashboard tab-agents shows status badges per agent. Quant Team system prompt is DB-saved at `quant_team_prompt` setting — editable from dashboard.

## Risk Auditor Prompt Revision (2026-07-20)
The Risk Auditor prompt was revised to add NN hyperparameter validation (LR, weight floor, entropy, gradient norm), statistical significance checks, correlation matrix analysis, hedging requirements, and an expanded JSON settings block.

## Risk Auditor Prompt Second Revision (2026-07-20)
Re-revised the Risk Auditor prompt after receiving Developer/Quant output revealing NN LR of 0.15 (catastrophic), harmful weight floor of 0.05, and only 2 training samples. New prompt demands:
- NN hyperparameter ranges (LR 1e-4 to 1e-2, gradient norm clipping <= 1.0, entropy bonus coefficient, no hard weight floors)
- Minimum training data diversity check (>= 50 samples across multiple regimes)
- Hedging effectiveness (min 0.7 correlation offset)
- Convergence criteria checklist
- Expanded JSON with learning_rate, gradient_clip_norm, entropy_coef, min_training_samples, max_position_size_usd, hedging_min_coverage, is_converged
- $1K/day throughput constraint
- Reject zero/same-data training sets

## NN Optimizer Agent Prompt Revision (2026-07-20)
The NN Optimizer agent prompt was rewritten to focus tightly on $1K/day scaling. Key changes:
- Now demands gradient norm diagnostics, entropy tracking, and weight distribution analysis
- Links NN parameters to market regime adaptability explicitly
- Requires quantitative $1K/day throughput constraints and justification for any LR change
- Added adaptive learning rate recommendation as a required output field
- Structured to reject no-data/no-signal answers unless rigorous math supports them
- Added convergence criteria checklist before accepting any setting as "stable"

## Risk Auditor Prompt Revision (2026-07-20 23:00)
The Risk Auditor prompt was rewritten to incorporate NN hyperparameter validation (LR, weight floor, entropy, gradient norm) from the Developer/Quant analysis, statistical significance checks, correlation matrix analysis, hedging requirements, and expanded JSON output fields for immediate application.

## NN Optimizer Prompt Revision (2026-07-20 23:14)
The NN Optimizer prompt was rewritten based on self-evaluation against Developer/Quant outputs. Key changes:
- Now demands gradient norm diagnostics, entropy tracking, and weight distribution analysis
- Links NN parameters to market regime adaptability explicitly
- Requires quantitative $1K/day throughput constraints and justification for any LR change
- Added adaptive learning rate recommendation as a required output field
- Structured to reject no-data/no-signal answers unless rigorous math supports them
- Added convergence criteria checklist before accepting any setting as "stable"
