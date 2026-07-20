# Handoff: OpenClaw → Antigravity — July 20-21, 2026

## What We Did Today

### Dashboard Fixes & New Endpoints
- **`/api/init` rebuilt from scratch** — was missing entirely from the repo. Now mirrors `/api/status` with positions, fiat breakdown, live holdings, 10 tickers.
- **`/api/trading/signals`** — live weighted signals per ticker. Returns `{ticker: {weighted_signal, direction, strategy_breakdown, price, ts}}`.
- **`/api/trading/reasoning`** — bot status panel (mode, capital, signals, performance, SUI risk warnings). Frontend was showing "Bot is operating normally" because this endpoint didn't exist.
- **`/api/trades/all`** — **enhanced** to merge DB `load_trades()` with Kraken `reconstruct_trades_from_exchange()`, deduplicating by (symbol, direction, entry_time, exit_time, quantity). Previously returned only 10 DB trades; Kraken has many more.
- **`/api/optimizations/apply/all`** — route ordering fixed (FastAPI matches routes in order; `/apply/all` must come BEFORE `/apply/{opt_id}`).

### WebSocket — Root Cause Found & Fixed
- **WS weights IndexError**: `ensembles.weights` had 7 entries, `ensembles.strategies` had 6 after the strategy purge. Dict comprehension used `range(len(weights))` — crashed on every WS connect. Fixed with `min(len(weights), len(strategies))`.
- nginx WS handshake returns 101. This crash was what caused the CONNECTED→DISCONNECTED loop.

### Dashboard JS — Critical Fix
- **`xhr()` helper was completely missing** from `enhancer.js`. Every Quant Team function (pollQuantTeam, loadQuantPrompt, saveQuantPrompt, trigger buttons) silently crashed with `ReferenceError: xhr is not defined`. This was the true cause of persona cards stuck at "Loading..." and empty prompt editors. Added proper xhr() with timeout/error logging.

### Coding Standards
- Replaced the Antigravity proxy routing section (AQ keys, port 8001) with **Commit & Deploy Discipline** — atomic commits, push-before-handoff, deploy via `deploy.sh`.

### Bugs Fixed (Cumulative — ~30 fixes this session)
- WS weights IndexError (above)
- `/api/trades/all` calling nonexistent `get_trades()` → `load_trades()`
- `/api/trading/reasoning` endpoint missing → now returns 5-item status panel
- `enhancer.js` missing `xhr()` helper → persona cards work
- `self.mode` used before assignment in `data_ingestion.py` → initialized in `__init__`
- SUI-USD delisted on yfinance (still in active tickers — needs removal)
- `pkill -f` matching SSH shell itself → use exact path patterns
- FastAPI route ordering: `/apply/all` before `/apply/{opt_id}`
- `bootQuantTeam` was named function expression → function declaration (hoisting)

## Current Bot State
- **Status**: OFF (process killed for clean handoff)
- **Machine**: `192.168.0.144:8000` (nginx 443 → `https://nexustrader.local/`)
- **Balance**: $90.83 USD + €9.70 EUR | Equity: ~$198.87 | Open positions: 0
- **Active tickers**: ADA, BTC, DOGE, DOT, ETH, LINK, LTC, SOL, SUI, XRP (10)
- **Trades in DB**: 10 (1W/9L) — Kraken has more to import
- **Mode**: LIVE, hyper_growth risk
- **DB path**: `~/.nexustrader/nexustrader.db`
- **Venv**: `/root/nexustrader/venv/bin/python3`
- **Log**: `/tmp/nx_live6.log`
- **GitHub**: `github.com:vimes1984/nexustrader.git` — last pushed `e24ac01`

## Quant Team (9 OpenClaw Cron Agents)
All 9 agents were created and force-run. Reports in `blog/daily_summaries/`. They run via OpenClaw cron (NOT system crontab) and talk through `openclaw_bridge.py` → `192.168.0.197:18789/v1/chat/completions` with model=`openclaw`. Dashboard tab-agents shows persona cards + prompt editors for all 9.

**Agent IDs**: `quant-optimizer`, `sentiment`, `risk-auditor`, `allocator`, `self-dev`, `asset-selector`, `self-improve`, `blogger`, `researcher`

## Antigravity Prompt — Start Here

Copy this into Antigravity to continue:

```
You're working on the NexusTrader repo at github.com:vimes1984/nexustrader.git (main branch, commit e24ac01). Read .agents/rules/coding_standards.md first — it's authoritative.

Current state: The bot is OFF. Start by running deploy.sh which will run unit tests, rsync to 192.168.0.144, and restart the nexustrader.service systemd unit. After deploy, verify these endpoints return 200:
- /api/health
- /api/trading/signals (should have 9-10 live signals after ~2 min of streaming)
- /api/trading/reasoning (status panel — 5 items)
- /api/trades/all (merged DB + Kraken — should be >10 trades if Kraken fetch works)

Immediate priorities:
1. Remove SUI-USD from active tickers (yfinance dead — "possibly delisted")
2. The enhanced /api/trades/all endpoint uses `reconstruct_trades_from_exchange()` which needs `ccxt` and Kraken API creds from `~/.nexustrader/config.json`. Verify Kraken trades are merging in.
3. Fix the "Stream stopped" / "All ticker streams stopped" pattern — bot occasionally shuts down its own uvicorn when ticker streams die. Build a self-healing watchdog.
4. User wants $1000/day profit target — bot is live with 1W/9L. Quant team needs to improve the signal pipeline.
5. Coding standards (Section 1): all new endpoints need unit tests added to tests/.

Key files:
- main.py (~3400 lines, FastAPI routes at bottom)
- dashboard/enhancer.js (v3.3, has xhr() helper now)
- database.py (load_trades, save_trade, load_setting, save_setting_directly)
- openclaw_bridge.py (LLM bridge)
- deploy.sh (tests → rsync → systemd restart)

The deploy.sh is the right workflow — use it. It enforces TDD.
```

## 2026-07-20 23:42 — NN Expansion Plan v2

### What's new

Full expansion plan written at `NN_EXPANSION_PLAN.md` (495 lines). Covers:

**Phase 4: Transformer Policy Network** (multi-head self-attention)
- Replaces/supplements LSTM with 4-head attention, 2 encoder layers
- Same interface as PolicyNetwork — drop-in compatible
- Attention weights visible for dashboard reasoning

**Phase 5: LLaMA Integration** (3-role LLM)
- llama.cpp server on Proxmox or 128GB machine
- Sentiment/macro analysis: analyze headlines → sentiment score
- Regime detection: classify market → risk mode recommendation
- Trade explanation: natural language "why did we enter this trade?"
- Single client module (`llm_client.py`), same bridge pattern

**Phase 6: Historical Training Pipeline**
- Kraken bulk data fetch (2 years, 1h candles)
- Simulated trades using real ensemble (not random actions)
- Epoch-based offline training with train/val/test split
- Weight hot-swap without bot restart
- New cron agent: Training Conductor (weekly)

### What Chris needs to do next
1. Check Proxmox host specs (192.168.0.166:8006 web UI)
2. Details on the 128GB machine (OS, GPU, LAN bridge feasibility)
3. Add OpenClaw's SSH key to Proxmox for deployment

### GitHub
Latest commit: `d00267f` — NN_EXPANSION_PLAN.md
