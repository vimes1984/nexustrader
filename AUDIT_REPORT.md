# NexusTrader — Full Codebase Audit Report

**Date:** 2026-07-20  
**Auditor:** Subagent — deep dive with `main.py` (2981 lines), `execution_engine.py` (649 lines), `strategy_engine.py` (409 lines), `database.py` (916 lines), `health_monitor.py` (115 lines), `notification_manager.py` (186 lines), `probability_engine.py` (209 lines), `learning_engine.py` (399 lines), `quant_utils.py` (407 lines), `data_ingestion.py` (351 lines), `evaluation/safety.py` (174 lines), `evaluation/position_sizing.py` (170 lines)  
**Total analyzed:** ~6,060 lines of Python across 12+ files

---

## Executive Summary

NexusTrader is an ambitious quantitative trading bot with 12 trading strategies, a Policy Gradient neural network for weight allocation, multi-asset support (ETH, BTC, SOL, DOGE, XRP), and a FastAPI dashboard. The architecture is sophisticated on paper — but it has **critical structural flaws** that explain why **it isn't generating trades despite having 84 strategies loaded** (12 strategies × up to 7 tickers = 84 `TradingStrategy` instances).

The root cause of zero trades is **not strategy logic** — it's the **signal strength threshold of 0.25** combined with **weight normalization that dilutes consensus signals below that threshold**.

---

## 1. `main.py` (2981 lines) — Orchestrator & API Server

### Key Components
- **`NexusTraderOrchestrator`** — Central state manager holding tickers, data ingestions, strategy ensembles, learning engines, and WebSocket connections.
- **FastAPI app** with ~45 API endpoints for control, status, brains, assets, logs, backup, and gateway bridging.
- **Windows `if __name__ == "__main__"`** — Desktop pywebview mode; runs `uvicorn` in headless mode on server.

### Critical Issue: Why No Trades Are Generated

**The signal threshold / weight normalization death spiral:**

1. **`process_tick()` → line ~550:**
   ```python
   if abs(weighted_signal) >= 0.25:
   ```
   This is the **only gate** to `evaluate_trade()`. No trade evaluation happens below 0.25.

2. **`get_weighted_signal()` in `strategy_engine.py`**:
   - Generates signals from 12 strategies (each returns -1.0, 0.0, or 1.0).
   - Multiplies by `active_weights` (from Policy Network).
   - Applies **OU Regime boosting** (can suppress strategies by up to 40-60%).
   - Applies **Performance Biasing** (can further suppress underperformers).
   - Then **normalizes weights** to sum 1.0.

3. **The net effect**: With 12 strategies, even if *all* agree on a signal, the raw sum before normalization represents the count of agreeing strategies minus disagreeing ones. But the **weighted signal is the dot product of normalized weights with signals**. If the Policy Network outputs near-uniform weights (as it does when not trained), each strategy gets ~1/12 = ~0.083 weight. Even if all 12 agree BUY (signal = 1.0), the weighted signal = 1.0 × 1.0 / 1.0 = 1.0… Wait.

Let me trace this more carefully:

```python
weighted_signal = np.dot(active_weights, signals)
```
If weights sum to 1.0 and all signals = 1.0, result = 1.0. So what's the actual problem?

**The actual problems are:**
1. **Most strategies return 0.0 (Hold)** most of the time. With 12 strategies, you might get 2 BUY, 1 SELL, 9 HOLD. Net signal after dot product with normalized weights ≈ 0.08 (BUY) - 0.08 (SELL) ≈ 0.0.
2. **RSI Strategy fetches optimizable parameters from DB** — but defaults are oversold=35, overbought=65, meaning it only fires on extreme moves.
3. **Bollinger Bands** — price must cross outside ±2σ bands to fire. In normal markets this is rare.
4. **MLPredictorStrategy** — only fires after training (which requires a `history_df` and ≥50 rows). The model may be untrained or poorly calibrated.
5. **KalmanTrendStrategy** — threshold of 0.001 (0.1%) is very tight; may fire frequently but then get suppressed by OU regime detection.

**Result**: The weighted signal rarely exceeds |0.25|, so `evaluate_trade()` is almost never called.

### Additional Issues in `main.py`

| Issue | Location | Severity |
|-------|----------|----------|
| **Hardcoded $1,000/day goal** in ALL default prompts | DEFAULT_PROMPT_* constants | Medium — inhibits realistic goal-setting |
| **`broadcast_message` exceptions swallowed silently** | line ~680 | Medium — WebSocket failures invisible |
| **`_run_async` ignores scheduled coroutine failures** | ~55 lines | Low — fire-and-forget async |
| **Live exchange trades exposed via API with API key** | `/api/trades` endpoint reconstructs trades from live exchange using API key from config | **HIGH** — API key is read from disk but not leaked to client (trades returned). However, config.json is a plaintext file. |
| **`orchestrator.start_stream(mode="live")` called unconditionally on startup** | startup_event | **HIGH** — Starts live polling to exchanges even during development/testing |
| **`update_crontab_schedule()` called on every startup** | startup_event | Medium — overwrites crontab |
| **Path traversal possible in `/api/system/backup/download`** | `download_backup` sanitizes with `basename()` | Low — mitigated by `basename` |
| **config.json API credentials in plaintext on disk** | `~/.nexustrader/config.json` | Medium — should be encrypted |

---

## 2. `execution_engine.py` (649 lines) — Order Execution & Balance

### Key Components
- **`ExecutionEngine.__init__()`** — Loads config, balance from DB, trades, and sets trading mode.
- **`sync_live_balance()`** — Fetches real balances from Kraken/CCXT, converts to USD, updates DB.
- **`execute_order_on_broker()`** — Routes orders to live exchange via CCXT.
- **`open_position()`** — Either places market order (live) or queued limit order (paper).
- **`update_positions()`** — Checks TP/SL hits, trailing stops, handles cooldowns.
- **`get_equity()`** — Computes portfolio value including unrealized PnL.

### Silent Error Swallowing & Bugs

| Issue | Location | Impact |
|-------|----------|--------|
| **`sync_live_balance()` — silent return when no API key** | line ~107 | Balance never syncs; user thinks live mode works but balance never updates |
| **`sync_live_balance()` — catches ALL exceptions** | line ~225 | Any failure silently falls back to stale balance |
| **EUR/USD rate hardcoded to 1.09 fallback** | multiple places | Off by ~3% vs market (EURUSD ≈ 1.12) |
| **`open_position()` — live mode always executes market orders** | line ~327 | **No limit orders in live mode** even though paper mode queues them. Live mode immediate market execution with no price improvement |
| **`update_positions()` — TP/SL check never fires for live positions** | line ~450 | Because live positions have `take_profit` and `stop_loss` set, but **no market-level monitoring** — the code checks on each tick, but in live mode ticks come from yfinance polling (every 10s) not from exchange order books |
| **Loss cooldown database key has typo risk** — `cooldown_end_{symbol}` used everywhere | consistent | Low — at least it's consistent |
| **`balance -= fee`** on paper trade open | open_position | Fee deducted from balance at entry, NOT refunded if trade doesn't fill (pending limit order cancelled) — balance leak |
| **`close_trade` calls `execute_order_on_broker` but exits order may fail silently** | line ~430 | If live exit fails, position remains open but code returns `None` — no retry mechanism |
| **`sync_live_balance` queries ALL tickers every call** | lines 160-180 | Expensive API call for every balance sync (30 ticks = ~5 minutes in practice) |

### Position Sizing Analysis

```python
position_value = self.balance * kelly_fraction
quantity = position_value / entry_price
```

For a $100 balance with kelly_fraction = 0.1 (conservative): position = $10. On ETH at $3,400: quantity = 0.00294 ETH. Most exchanges require minimum order amounts that would **fail** at this size. The code does adjust for min_amount in `execute_order_on_broker()`:

```python
adjusted_qty = max(qty, min_amount)
```

So the **real position size could be much larger than intended** — if min_amount is 0.01 ETH, it would trade 0.01 ETH ($34), which is 34% of the portfolio instead of the intended 10%. This is a **3.4x oversizing bug**.

---

## 3. `strategy_engine.py` (409 lines) — Strategy Ensemble & Signal Generation

### Key Components
- **12 Trading Strategies**: EMACrossover, RSIReversion, BB Breakout, ML Random Forest, KalmanTrend, Psych Liquidity Sweep, NewsSentiment, MACDHistCrossover, MeanReversionZScore, VWAPCrossover, ATRBreakout, StochasticReversion
- **`StrategyEnsemble`** — Combines signals with OU process regime detection and performance biasing.

### Critical Signal Flow Issue

The **`get_weighted_signal()`** method applies three layers of weight modification:

1. **OU Regime Detection** — Up to ±40% weight shift
2. **Performance Biasing** — Up to 1.5x boost for >60% win-rate strategies; up to 2x penalty for <35% win-rate
3. **Normalization** — Forces sum to 1.0

**Problem**: OU regime detection uses `price_history` (close prices only from the last 60 processed ticks). But `price_history` is populated in `get_weighted_signal()` every tick. The first ~20 ticks have insufficient data, so `theta=0, is_mr=False`. This means **early ticks get no regime adjustment**, then suddenly at tick 20 the adjustment kicks in, causing a **discontinuity in weights**.

### MLPredictorStrategy Not Trained

The RandomForest model is trained once in `__init__` if `history_df` is provided, and during `train_ml_strategy()`. But:
- Training uses `shift(-self.lookahead)` to create labels — this creates **forward-looking bias** in backtests.
- If `history_df` has < 50 rows, training is skipped silently.
- The `_extract_features` method can fail on NaN/Inf values from poorly calculated indicators (no sanitization).

### Bugs

| Issue | Location | Impact |
|-------|----------|--------|
| **`KalmanTrendStrategy` creates a NEW Kalman filter per ticker on instantiation** | constructor | Each `StrategyEnsemble` creates a new KalmanFilter, so **state is lost** across ticker re-initialization |
| **`PsychologicalSweepStrategy` receives `history` parameter but it's `history_df` not raw history** | call signature confusion | The history passed from `ensemble` is the full `DataFrame`, but `detect_psychological_sweep()` expects a DataFrame with 'high'/'low' columns — this actually works, but the method signature `row, history=None` is misleading |
| **`record_trade_outcome` stores the signal but `generate_signal` can be called on every tick** | performance_tracker | Performance tracking only works when trades actually close, which is circular with the trade-generation problem |

---

## 4. `database.py` (916 lines) — SQLite Persistence Layer

### Key Components
- **`init_db()`** — Creates 8+ tables with extensive migration logic.
- **`save_tick()`, `save_trade()`** — Insert/update operations.
- **`save_setting()` / `load_setting()`** — Global key-value store (384+ keys visible via "Research" namespace).
- **`load_trades()`** — Trade retrieval with optional `trading_mode` filter.
- **Policy Brains CRUD** — `save_policy_brain`, `load_policy_brain`, `list_policy_brains`, `delete_policy_brain`.

### Critical Issues

| Issue | Location | Impact |
|-------|----------|--------|
| **`save_setting()` uses `inspect.stack()` on EVERY call** | line ~406-432 | **Massive performance overhead.** Stack inspection walks the entire call stack to detect agent callers. Called **hundreds of times per minute** (every tick saves multiple settings). This alone could cause significant latency. |
| **MutationFreeze check also uses `inspect.stack()`** | line ~370-395 | Same issue — duplicate stack walking |
| **`save_active_asset()` also uses `inspect.stack()`** | line ~733-753 | Third location with stack inspection |
| **No connection pooling** | All methods | Every DB operation opens/closes a connection. SQLite can handle this, but with 5 tickers × 12 strategies per tick, this is ~60 DB ops per tick cycle. |
| **`load_setting("initial_portfolio_balance")` type confusion** | multiple locations | Sometimes loaded as `str`, sometimes `float`. Comparison `float(db_init_balance) == 100.0` can fail if user set $100.01. |
| **Backfill logic runs on every startup** | init_db() → standalone check | Queries ALL trades to backfill brain stats every time the app restarts; O(n) per restart |
| **No database cleanup / TTL** | entire file | Ticks table grows unbounded. No index on `symbol` column for ticks queries. |

### MutationFreeze Interaction

The `save_setting()` double-checks `mutation_freeze.frozen` AND walks the stack. When frozen:
- Agent changes are **blocked but not applied**.
- The `save_setting_directly()` bypass function exists for dashboard-initiated changes.
- **Critical gap**: If MutationFreeze is frozen (default `True`), then **the startup code that seeds default brains and prompts also runs through `save_setting()`** which checks MutationFreeze. However, the startup code runs in `main.py` frame, so the stack inspection won't find an agent filename and will proceed normally… **But**: if any agent code tries to save during initialization, it'll be silently blocked.

---

## 5. `health_monitor.py` (115 lines) — Background Health Checks

### Key Components
- **`health_monitor_loop()`** — Runs every 60s checking: stream aliveness, insufficient funds, inactivity, KillSwitch, drawdown.

### Issues

| Issue | Description | Severity |
|-------|-------------|----------|
| **`last_orphan_alert` initialization** | Local variable `last_orphan_alert = 0` resets every bot restart, so first orphan alert may fire immediately after startup | Low |
| **`stream_active` check is unreliable** | Checks `hasattr(di, 'stream_active')` and `di.stream_active`. If stream is stopped but `streaming=False`, the bot checks again in 60s | Low — just delayed detection |
| **Idle time tracking uses `exit_time` of last closed trade** | If no trades ever closed, `last_trade_ts = 0`, so idle_hours = ∞ always. First idle alert fires after 3 hours without any trades | Medium — constant false alarms on fresh starts |
| **No health check for DB size or connectivity** | No disk space, DB integrity, or memory checks | Medium — can silently fail when disk fills |
| **No self-healing** | Only alerts; never attempts to restart streams or heal | Low — by design |

---

## 6. `notification_manager.py` (186 lines) — Alert Routing

### Key Components
- **`push_alert()`** — Inserts alert into SQLite + routes to ntfy/email/WhatsApp.
- **`get_alerts()`, `acknowledge_alert()`, `resolve_alert()`** — CRUD.
- **`send_smtp_email()`** — SMTP via STARTTLS.
- **`send_whatsapp_webhook()`** — POST to webhook URL.
- **`generate_summary_text()`** — Portfolio summary Markdown.

### Issues

| Issue | Description | Severity |
|-------|-------------|----------|
| **SMTP password stored in plaintext** in settings DB | `notif_smtp_pass` setting key | Medium — any SQLite access reveals SMTP credentials |
| **WhatsApp webhook URL stored in plaintext** | `notif_whatsapp_webhook` | Low — webhook URLs can be revoked |
| **`push_alert` calls `get_notification_settings()` every time** | Opens a DB connection + queries all settings on every alert | Medium — alert-heavy scenarios create DB churn |
| **`send_smtp_email` exceptions caught broadly** | All SMTP Errors → silent failure with log | Low — acceptable for email |
| **`ALERT_DB_PATH` is separate from main DB** | `/root/nexustrader/data/alerts.db` vs DB at `~/.nexustrader/nexustrader.db` | Low — but backup scripts may miss it |

---

## 7. `probability_engine.py` (209 lines) — Trade Evaluation & Position Sizing

### Key Components
- **`ProbabilityEngine`** — Evaluates trade viability by computing TP/SL, win probability, EV, Kelly fraction.
- **`calculate_atr_bounds()`** — Volatility-adjusted TP/SL from ATR.
- **`estimate_win_probability()`** — Blends signal strength, RSI, and historical similarity.

### Issues

| Issue | Description | Severity |
|-------|-------------|----------|
| **`estimate_win_probability()` uses `shift(-5)` on `history_df`** | Forward-looking bias: looks 5 periods ahead to determine if "this signal would have been correct" | **CRITICAL** — This leaks future information into the probability estimate, making the system think it's more accurate than it is |
| **`min_win_rate = 0.45` hardcoded** | If win probability < 45%, trade is not viable. But the estimate is systematically wrong (see above) | High — combines with signal threshold to block trades |
| **No minimum EV check** | EV > 0 is the only gate, but EV uses the biased win probability | Medium |
| **ATR fallback hardcoded to 1% of price** | `atr = price * 0.01` when ATR is NaN | Low — reasonable fallback |
| **`evaluate_trade` double-queries DB per call** | Opens connection twice (once for asset multipliers, once for kelly ceiling) | Medium — called potentially every tick per ticker |

---

## 8. `learning_engine.py` (399 lines) — Policy Gradient Neural Network

### Key Components
- **`PolicyNetwork`** — NumPy-based 2-layer neural net (expandable to multi-layer) with Adam/RMSprop/SGD.
- **`ReplayBuffer`** — Experience replay for batch training.
- **`LearningEngine`** — Wraps PolicyNetwork with state vector construction and weight selection.

### Issues

| Issue | Description | Severity |
|-------|-------------|----------|
| **`select_weights()` applies weight floor with re-normalization** | If any weight < `weight_floor` (default 0.05), all weights are floored and renormalized. This means the network can never output a weight below 0.05, preventing strategy extinction | Medium — prevents focus on best strategies |
| **`learn_from_trade()` pads/trims strategy_signals to match action_dim** | But `strategy_signals` comes from `signals_at_entry` which is aligned with `ensemble.strategies` (12). If action_dim differs, signals misalign | High — silent data corruption |
| **Weight migration (7→8 state dim, 7→12 action dim) resets optimizer state** | `from_json()` overwrites `m_W`, `m_b`, `v_W`, `v_b` to zeros | Low — acceptable for migration |
| **No gradient clipping** | Policy gradients use raw `advantage * 100` with `clip(-5.0, 5.0)`. The `* 100` is arbitrary and can interact badly with optimization | Medium |
| **`backward()` applies BOTH online gradient AND replay buffer training** | On every trade, it does an immediate update + periodic batch update. This can cause **double-counting** of experiences | High — trade contributes twice to weight updates |
| **Replay buffer training accumulates then averages gradients from all batch samples** | But averages include the current trade's contribution (since it was just pushed) | Medium |

---

## 9. `quant_utils.py` (407 lines) — Utility Functions

### Key Components
- **`KalmanFilterPrice`** — 1D Kalman filter for trend estimation.
- **`estimate_ou_process()`** — OLS-based Ornstein-Uhlenbeck fitting.
- **`detect_psychological_sweep()`** — Stop-hunt detection.
- **`query_gemini_robust()`** — Multi-LLM routing (Gemini, OpenAI, Anthropic) with retries.

### Issues

| Issue | Description | Severity |
|-------|-------------|----------|
| **`estimate_ou_process()` uses `np.linalg.lstsq` without regularization** | If `x` is constant or near-constant, OLS can produce nonsense results | Medium |
| **`detect_psychological_sweep()` accesses `df['open'].iloc[-1]` but `open` may not exist** | Pandas KeyError if `open` column missing | Low |
| **`query_gemini_robust()` opens raw SQLite connection** (not via `database.get_db_connection()`) | Bypasses centralized DB config; direct path `~/.nexustrader/nexustrader.db` | Medium — if DB_PATH changes, this breaks silently |
| **API keys loaded into `settings` dict but never cleared** | All settings including API keys remain in local memory until GC | Low |
| **Goal replacement runs up to 21 `str.replace()` per prompt** | O(n) per prompt character — negligible but wasteful | Cosmetic |

---

## 10. `data_ingestion.py` (351 lines) — Market Data Feeds

### Key Components
- **`DataIngestion`** — yfinance historical fetching, live polling via CCXT + yfinance fallback.
- **10 technical indicators** computed on every data batch.
- **Simulation mode** — Replays historical data row-by-row.

### Issues

| Issue | Description | Severity |
|-------|-------------|----------|
| **`compute_technical_indicators()` called on EVERY tick** | After each live price update, all 10 indicators are recomputed on the entire DataFrame | **High** — O(n) per tick, where n grows without bound |
| **Live polling uses `threading.Thread` with no lock** | `self.data` is mutated from the polling thread while `process_tick()` (main thread) reads it | **High** — race condition on DataFrame access |
| **`self.data` grows unbounded** | New rows appended forever; no maximum history limit | High — memory leak over days/weeks |
| **yfinance fetches entire history on every live poll** (fallback path) | `ticker_obj.history(period="1d")` downloads >300 1m candles each poll | High — API rate abuse, unnecessary data transfer |
| **`_run_live_polling()` has CCXT reconnection logic but starts yfinance fallback concurrently** | Both exchange and yfinance paths may execute in the same loop iteration | Medium — duplicate data |
| **Simulation index starts at 150** (`start_index=150` in `start_stream`) | Skips first 150 rows of indicators (which may still be NaN). First 20+ ticks have no OU process data | Low |

---

## 11. `evaluation/safety.py` (174 lines) — KillSwitch, DrawdownTracker, MutationFreeze

### Key Components
- **`KillSwitch`** — Checks: daily loss limit ($500 default), position size limit ($5K/symbol), total exposure ($25K), max drawdown (15%).
- **`DrawdownTracker`** — Peak-to-trough tracking.
- **`MutationFreeze`** — Gates automatic config mutations from LLM agents.

### Issues

| Issue | Description | Severity |
|-------|-------------|----------|
| **KillSwitch default `max_daily_loss = 500.0`** | With $100 initial balance, this limit will never trip in paper mode. In live mode with larger balance, it could trip too late | Medium — misaligned with small balance |
| **`KillSwitch.check()` `daily_pnl` accumulates absolute PnL, not directional** | `abs(self.daily_pnl) >= self.max_daily_loss` — tripped by profits OR losses | **High** — profitable trading day can kill the bot |
| **`max_position_per_symbol = 5000.0`** | With $100 balance, can never be triggered | Medium |
| **`max_total_exposure = 25000.0`** | With $100 balance, can never be triggered | Medium — killswitch is effectively inert at small balances |
| **`MutationFreeze` defaults to `frozen=True`** | All LLM agent suggestions are silently blocked on startup | High — "optimizations" run but never take effect |
| **`from_dict()` on KillSwitch doesn't restore `max_*` config values** | Only tripped state and PnL; limits stay at defaults | Low |

---

## 12. `evaluation/position_sizing.py` (170 lines) — Fractional Kelly

### Issues

| Issue | Description | Severity |
|-------|-------------|----------|
| **`estimate_metrics_from_trades()` uses `abs(t.get('pnl_percent', ...))`** | `avg_loss = 0.01` fallback if no losses exist. But `abs()` means all PnLs are treated as positive | **CRITICAL** — `pnl_percent` for losses is negative (e.g., -0.02). `abs()` of negative is positive, so ALL trades appear as wins. Win rate = 100%. Kelly says "bet the farm." |
| **`compute_kelly_fraction()` receives `avg_loss = 0.01` when no losses** | Win rate = 1.0, avg_win > 0, avg_loss = 0.01 → Kelly = 1.0 - 0/0.01 = 1.0 (bet everything) | **CRITICAL** — Combined with the above, fresh bots with only winning paper trades will bet 100% of capital |
| **`compute_safe_fraction()` returns 2% cold_start default** | This masks the bug above for the first 10 trades, but after 10 trades with all wins, `n_trades >= MIN_TRADES_FOR_KELLY` fires and the full 25% cap can apply | High |

---

## Root Cause Analysis: Why Zero Trades

The bot has **84 strategy instances** (12 strategies × 7 tickers), but the pipeline has multiple gating layers that compound to block trades:

### Gate 1: Signal Strength (`main.py` ~550)
```python
if abs(weighted_signal) >= 0.25:
```
### Gate 2: Win Probability (`probability_engine.py`)
```python
is_viable = (p_win >= self.min_win_rate) and (ev > 0) and (final_fraction > 0)
```
### Gate 3: KillSwitch (`main.py` ~570)
```python
safe, reason = kill_switch.check(...)
```
### Gate 4: Loss Cooldown (`execution_engine.py` ~270)
```python
if time.time() < cooldown_end: return False
```

**Flow analysis:**

1. Most strategies return `0.0` (Hold) in normal market conditions.
2. The weighted average of 11 "Hold" + 1 "Buy" = ~0.08 after normalization.
3. OU regime detection may further suppress the lone active strategy.
4. The 0.25 threshold is rarely crossed.
5. Even if crossed, the forward-looking win probability estimate overestimates `p_win`, but the `min_win_rate = 0.45` gate still blocks.
6. KillSwitch defaults won't trip at $100 balance (limits are $500, $5K, $25K).
7. Cooldown states persist across restarts (stored in DB).

**The most effective fix**: Lower the signal threshold from 0.25 to 0.15 (or make it configurable based on market volatility). Or implement a "conviction scoring" system where the threshold adapts.

---

## Data Flow Diagram (Tick → Signal → Order)

```
yfinance/CCXT tick
    ↓
DataIngestion._run_live_polling()
    ↓ callback
NexusTraderOrchestrator.process_tick(row, ticker)
    ├── Sentiment refresh (every 300s)
    ├── Balance sync (every 30 ticks)
    ├── Latest tick cache update
    ├── Database tick save
    ├── [AUTO-BRAIN-SWITCH check] — queries DB
    ├── Neural state vector construction
    ├── Policy Network forward → base_weights → ensemble.weights
    ├── update_positions() — TP/SL/stop check
    ├── Long-term shadow strategy evaluation
    ├── if no position open:
    │     ├── Weighted signal from ensemble
    │     ├── Signal ≥ 0.25?
    │     │     ├── NO → broadcast (no trade)
    │     │     └── YES → ProbabilityEngine.evaluate_trade()
    │     │             ├── ATR-based TP/SL
    │     │             ├── (Biased) win probability
    │     │             ├── Kelly fraction
    │     │             └── is_viable?
    │     │                   ├── NO → broadcast
    │     │                   └── YES → KillSwitch.check()
    │     │                             ├── BLOCKED → log warning
    │     │                             └── SAFE → ExecutionEngine.open_position()
    │     │                                       ├── live: market order via CCXT
    │     │                                       └── paper: pending limit order
    └── WebSocket broadcast
```

---

## All Bugs & Issues — Prioritized

### 🔴 Critical (Will prevent profitable trading)

| # | File | Bug |
|---|------|-----|
| 1 | `execution_engine.py` | `open_position()` — min_order adjustment can cause **3.4x position oversizing** on small accounts |
| 2 | `position_sizing.py` | `estimate_metrics_from_trades()` uses `abs()` on PnL — **all trades treated as wins** |
| 3 | `position_sizing.py` | `compute_kelly_fraction()` with 100% win rate returns 1.0 (bet everything) |
| 4 | `probability_engine.py` | `estimate_win_probability()` uses `shift(-5)` — **forward-looking bias** |
| 5 | `main.py` | Signal threshold `≥ 0.25` blocks most ensemble signals |
| 6 | `main.py` | Auto-starts live stream on every startup — **can generate real orders accidentally** |
| 7 | `data_ingestion.py` | **Race condition** — DataFrame mutated in thread while read in main thread |
| 8 | `data_ingestion.py` | Indicators recomputed on **entire DataFrame** every tick (O(n) growth) |

### 🟠 High (Will degrade or confuse)

| # | File | Bug |
|---|------|-----|
| 9 | `database.py` | `save_setting()` calls `inspect.stack()` **on every call** — massive overhead |
| 10 | `learning_engine.py` | `backward()` applies **both online + replay gradient** — double-counting trades |
| 11 | `main.py` | `update_crontab_schedule()` runs on every startup, overwriting existing crontab |
| 12 | `main.py` | `KillSwitch.check()` uses `abs(self.daily_pnl)` — kills bot on profits too |
| 13 | `execution_engine.py` | `EUR/USD rate hardcoded 1.09` — systematic mis-valuation |
| 14 | `evaluation/safety.py` | KillSwitch limits ($500 loss, $5K position, $25K exposure) don't apply to $100 portfolio |
| 15 | `evaluation/safety.py` | `MutationFreeze.frozen = True` by default — all agent optimizations blocked |

### 🟡 Medium (Reliability, performance, correctness)

| # | File | Bug |
|---|------|-----|
| 16 | `execution_engine.py` | Live mode uses **market orders only** — no limit order price improvement |
| 17 | `execution_engine.py` | Balance deducted for fee at limit order placement, **not refunded if unfilled** |
| 18 | `main.py` | `broadcast_message` silently drops disconnected websockets |
| 19 | `health_monitor.py` | No trades = infinite idle time alert every 3 hours |
| 20 | `notification_manager.py` | Separate `alerts.db` not in backup scope |
| 21 | `data_ingestion.py` | yfinance `history(period="1d")` called every 10s — rate limit risk |
| 22 | `strategy_engine.py` | `KalmanTrendStrategy` re-initializes Kalman filter per ensemble — state loss |
| 23 | `main.py` | `config.json` stores API keys in **plaintext** |
| 24 | `quant_utils.py` | Direct SQLite path bypasses centralized DB config |
| 25 | `database.py` | No TTL/cleanup on ticks table — memory leak over time |

### 🟢 Low (Cosmetic, edge cases)

| # | File | Bug |
|---|------|-----|
| 26 | `notification_manager.py` | SMTP password in plaintext DB setting |
| 27 | `strategy_engine.py` | `PsychologicalSweepStrategy` checks for `df['open']` may KeyError |
| 28 | `main.py` | `initial_balance = 100.0` compared as `== 100.0` — float equality |
| 29 | `quant_utils.py` | OU process `lstsq` unregularized for constant inputs |
| 30 | `health_monitor.py` | `last_orphan_alert` resets to 0 on restart, fires premature alert |

---

## Architectural Recommendations

1. **Fix position_sizing.py first** — the `abs()` bug means the system thinks all trades are wins
2. **Reduce signal threshold** from 0.25 → 0.10 or implement adaptive threshold based on ATR
3. **Remove forward-looking bias** in probability estimation (shift(-5))
4. **Add connection pooling** or singleton DB cursor to eliminate stack-inspection overhead
5. **Set KILLSWITCH limits proportional to balance** (e.g., 10% daily loss, 50% position, 200% exposure)
6. **Add threading locks** to `DataIngestion.data` DataFrame access
7. **Cap data history** (e.g., keep last 500 rows) to prevent O(n) growth
8. **Remove auto-start of live stream** on startup_event; require explicit API call
9. **Thaw MutationFreeze** or expose its state clearly in the dashboard
10. **Add integration tests** for the complete tick→signal→order pipeline (currently 0 tests exercise the full flow)
