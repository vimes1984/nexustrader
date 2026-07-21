#!/bin/bash
# ================================================================
# 🍌 KEVIN'S NEXUSTRADER AUDIT SWARM LAUNCHER
# ================================================================
# Spawns 5 parallel OpenClaw agents that audit every line of code,
# math formula, trading strategy, backend, DB, and dashboard over
# hundreds of iterative loops.
#
# Usage: bash audit-swarm.sh [--lite]
#   --lite: Reduced loops (dashboard only, no PhD math)
#
# Store this anywhere — it auto-finds the repo.
# ================================================================
set -euo pipefail

REPO="${NEXUSTRADER_REPO:-/root/.openclaw/workspace/nexustrader}"
BOT="${NEXUSTRADER_BOT:-192.168.0.144}"
DASHBOARD="${REPO}/dashboard-v2"

echo "🍌 MISSION AUDIT SWARM — LAUNCHING"
echo "   Repo:      $REPO"
echo "   Bot:       $BOT"
echo "   Dashboard: $DASHBOARD"
echo ""

# ---- Safety check: don't double-launch ----
RUNNING=$(openclaw ag list 2>/dev/null | grep -c 'audit\|loop\|phd\|holistic\|strategy\|backend\|dashboard' || echo 0)
if [ "$RUNNING" -gt 2 ]; then
  echo "⚠️  Looks like agents are already running ($RUNNING found)."
  echo "   If you want to re-launch, kill them first."
  exit 1
fi

MODE="${1:-full}"
if [ "$MODE" = "--lite" ]; then
  echo "Mode: LITE (dashboard only, 50 loops)"
  DASH_LOOPS=50
  BACKEND_LOOPS=0
  MATH_LOOPS=0
  STRATEGY_LOOPS=0
  HOLISTIC_LOOPS=0
else
  echo "Mode: FULL (all 5 agents, 800+ total loops)"
  DASH_LOOPS=100
  BACKEND_LOOPS=100
  MATH_LOOPS=100
  STRATEGY_LOOPS=100
  HOLISTIC_LOOPS=500
fi

echo ""

# ---- Launch Dashboard Agent ----
if [ "$DASH_LOOPS" -gt 0 ]; then
  echo "🎨 Launching Dashboard Agent ($DASH_LOOPS loops)..."
  openclaw agent run \
    --name "dashboard-audit-$(date +%s)" \
    --cwd "$DASHBOARD" \
    --prompt "You are completing a ${DASH_LOOPS}-loop design→develop→QA→test cycle on the NexusTrader dashboard-v2.

For each loop:
1. Read a module (pick from js/*.js, css/main.css, index.html)
2. Find UX/performance/a11y/bug issues
3. Fix them
4. Verify: node --check for JS, manual for CSS/HTML
5. Deploy: rsync to ${BOT}:/root/nexustrader/dashboard-v2/
6. Reload nginx: ssh ${BOT} 'nginx -s reload'
7. Verify: curl -sk https://${BOT}/dashboard-v2/ | head -3
8. Commit every 5-10 loops

KEY FOCUS: Cross-browser, mobile responsive, a11y, loading skeletons, error recovery, print styles, dark mode, keyboard nav, touch gestures, PWA, service worker, font loading, cache-bust.

WORKING DIR: ${DASHBOARD}" &
fi

# ---- Launch Backend + DB Agent ----
if [ "$BACKEND_LOOPS" -gt 0 ]; then
  echo "⚙️  Launching Backend+DB Agent ($BACKEND_LOOPS loops)..."
  openclaw agent run \
    --name "backend-db-audit-$(date +%s)" \
    --cwd "$REPO" \
    --prompt "You are auditing ${BACKEND_LOOPS} loops of NexusTrader backend + DB code.

FILES: main.py, execution_engine.py, database.py, data_ingestion.py, historical_pipeline.py, learning_engine.py, probability_engine.py, evaluation/*.py, llm_integration.py, openclaw_bridge.py, sentiment_engine.py, and all other .py files.

Do NOT restart the bot if it has open positions. Be surgical.

PER LOOP: Read → find issue → fix → py_compile verify → rsync if safe → commit

KEY FOCUS: SQL optimization, error handling, race conditions, input validation, resource leaks, thread safety, logging hygiene, API completeness, FinBERT integration, paper learnings from arxiv 2308.09485 + Oxford.

WORKING DIR: ${REPO}" &
fi

# ---- Launch PhD Math Agent ----
if [ "$MATH_LOOPS" -gt 0 ]; then
  echo "📐 Launching PhD Math Agent ($MATH_LOOPS loops)..."
  openclaw agent run \
    --name "phd-math-audit-$(date +%s)" \
    --cwd "$REPO" \
    --prompt "You are a PhD mathematician auditing ${MATH_LOOPS} loops of all math in NexusTrader.

Rigorously verify EVERY formula against academic definitions:
- RSI (Wilders smoothing), MACD, ATR, Bollinger Bands, EMA/SMA
- Sharpe ratio, Sortino ratio (annualization factors)
- Kelly criterion (multi-position, fractional)
- Win probability estimation, calibration
- Drawdown calculation (peak-to-trough)
- VaR, CVaR, risk of ruin
- Look-ahead labeling (no future leak)
- Position sizing math
- Correlation matrix calculation
- Gradient descent, Adam optimizer
- Softmax, temperature scaling
- Attention mechanism math (multi-head)
- Sentiment score aggregation
- Embedding distance metrics

Check: numerical stability (NaN, inf, /0), floating-point edge cases, statistical assumptions.

WORKING DIR: ${REPO}" &
fi

# ---- Launch Trading Strategy Agent ----
if [ "$STRATEGY_LOOPS" -gt 0 ]; then
  echo "📊 Launching Trading Strategy Agent ($STRATEGY_LOOPS loops)..."
  openclaw agent run \
    --name "trading-strategy-audit-$(date +%s)" \
    --cwd "$REPO" \
    --prompt "You are a professional quant trader auditing ${STRATEGY_LOOPS} loops of trading strategy.

Evaluate every strategy component:
- Signal generation (predictive or noise?)
- Entry/exit logic, TP/SL levels
- Position sizing (account-appropriate?)
- Cooldown logic (overtrading prevention?)
- Market regime detection (actually changing behavior?)
- Ensemble confidence (meaningful threshold?)
- Sentiment integration (signal or noise?)
- Kill switch conditions (false positive rate?)
- Paper trading fidelity
- Risk/reward ratios
- Correlation between positions
- Slippage and fee modeling
- Trailing stops
- Max drawdown limits
- Daily goal feasibility (esp. for small accounts)

PAST BUGS: death spiral (dyn_min raised when losing), get_equity() TypeError, micro-sizing floor.

WORKING DIR: ${REPO}" &
fi

# ---- Launch Holistic Agent ----
if [ "$HOLISTIC_LOOPS" -gt 0 ]; then
  echo "🔭 Launching Holistic End-to-End Agent ($HOLISTIC_LOOPS loops)..."
  openclaw agent run \
    --name "holistic-audit-$(date +%s)" \
    --cwd "$REPO" \
    --prompt "You are the final boss auditing ${HOLISTIC_LOOPS} holistic loops across ALL NexusTrader systems.

Cross-reference everything end-to-end:
- API routes → Dashboard JS calls
- NN weights → Strategy execution
- Sentiment → Signal → Trade pipeline
- LLaMA → Bridge → Decision flow
- Risk system → All safety nets
- Backtest → Live gap analysis
- Configuration → Actual behavior
- Test suite → All 226 tests pass?
- Deployment → deploy.sh works?
- Error recovery → What breaks when Kraken API fails?
- Paper trading fidelity → Realistic enough?

Read HANDOFF_NEXUSTRADER.md first for full context.

WORKING DIR: ${REPO}" &
fi

echo ""
echo "========================================="
echo "🍌 ALL AGENTS LAUNCHED!"
echo "========================================="
echo "Check status: openclaw ag list"
echo "View logs:    openclaw ag logs <name>"
echo ""
echo "Agents will auto-commit + push to GitHub."
echo "Give them 5-30 minutes depending on mode."
echo "UNDERSTOOD, BOSS!"
