# NexusTrader Architecture & Strategy — July 2026

## The Trading Architecture

NexusTrader is a **multi-strategy crypto trading bot** running an ensemble of 36 strategies across 10 Kraken spot tickers. It trades live, autonomously, with a target of **$1,000/day**.

---

## Strategy Ensemble

### Active Strategies (36 total)
Strategies span four families, weighted by a learned policy network:

**Trend Following** — EMA crossover, MACD, Parabolic SAR, ADX directional, SuperTrend, Ichimoku, Donchian breakout, Hull MA, TRIX, KST, Rainbow MA, PMax

**Mean Reversion** — RSI extremes, Bollinger Bands, Stochastic, Williams %R, CCI, Keltner Channels

**Momentum/Breakout** — Volume surge, volatility expansion, ATR squeeze, Opening Range Breakout, Darvas Box, Squeeze Momentum

**ML/Statistical** — Bayesian signal, Kalman filter, Hurst exponent regime, Fractional differentiation, Market Microstructure imbalance, Order flow delta

### Signal Pipeline
```
Raw OHLCV data → 36 strategy calculations → Ensemble weighted sum → Signal score [-1, +1]
                                                                            ↓
                                                                  Signal > threshold?
                                                                   ↓ yes       ↓ no
                                                                  Enter Trade   Skip
```

---

## Neural Network Architecture

### Two Modes (togglable via `nn_architecture` config)

#### Mode 1: MLP Policy Network (original, default)
```
8 handcrafted features → 12 hidden (ReLU) → 6 strategy weights (Softmax)
```
- Online policy gradient training (REINFORCE)
- Replay buffer capacity: 200 transitions
- Simple but no memory, no time structure, no cross-asset awareness

#### Mode 2: LSTM Sequential Policy Network (NEW, Phase 1-3)
```
OHLCV candles → Tokenizer (32 tokens) → Embedder (64d) → 2-layer LSTM → Softmax
```
- **Tokenizer**: Converts raw price/volume/volatility into 32 discrete tokens across 4 vocabularies:
  - Price Action: `PR_STRONG_UP`, `PR_WEAK_UP`, `PR_DOJI`, `PR_ENGULFING_BULL`, etc.
  - Volume/Volatility: `VOL_SPIKE`, `VOL_DRY`, `VOL_CLIMAX`
  - Technical Regime: `REG_TRENDING_UP`, `REG_BREAKOUT`, `REG_MEAN_REVERTING`, etc.
  - Cross-Asset Context: `CTX_BTC_LEADING`, `CTX_RISK_ON`, `CTX_CORRELATION_SPIKE`
- **Embedder**: 32-token vocabulary → 64-dimensional learned embeddings with Adam optimizer and LayerNorm
- **LSTM**: 2-layer stacked LSTM (64→64 hidden), forget/input/output/cell gates, dropout regularization
- **Output**: Softmax over strategy weights, same interface as MLP mode

### Tokenization Pipeline
```python
candles[24] → tokenize_candle() → [(24, max_tokens=5) token_ids]
                                    ↓
                            TokenEmbedder.forward()
                                    ↓
                            (batch, seq, 64) embeddings
                                    ↓
                            SequentialPolicyNetwork.forward()
                                    ↓
                            (batch, 6) strategy_weights
```

---

## Quant Team — 9 Autonomous Agents

Each agent is an OpenClaw cron job with dedicated prompts, running independently:

| Agent | Role | Schedule |
|-------|------|----------|
| 📊 **Quant Optimizer** | Tunes TP/SL, signal threshold, learning rate from trade outcomes | Daily |
| 🧠 **Sentiment** | Market sentiment from news/headlines/on-chain data | Daily |
| 🛡️ **Risk Auditor** | Monitors drawdown, correlation, position sizing, NN hyperparameters | Daily |
| ⚖️ **Allocator** | Rebalances ticker activation, Kelly ceilings, capital rotation | Daily |
| 🔧 **Self-Dev** | Code improvements, bug fixes, refactoring | Daily |
| 🔍 **Asset Selector** | Scans Kraken for new assets, disables delisted pairs | 14 days |
| 🔄 **Self-Improve** | Meta-learning: improves prompts of other agents | Weekly |
| 📝 **Blogger** | Generates daily summaries and trade reports | Daily |
| 🔬 **Researcher** | Explores new strategies, papers, and market patterns | Daily |

### Agent Autonomy
- Each agent SSH's to the bot VM, reads/writes the database, and can restart the bot
- Agents communicate via DB settings and blog entries
- Per-agent prompts are editable from the dashboard and stored in the DB
- Dashboard shows live status badges per agent

---

## Training Architecture

### Current: Online Policy Gradient
- REINFORCE algorithm on each closed trade
- Only trains when trades happen (sample-inefficient)
- 10 trades total in DB (1W/9L)

### Planned: Dual-Path Training

**Path A — Online (continuous)**
- Live policy gradient from each closed trade
- Always running, always learning

**Path B — Offline (weekly)**
- Fetch 2 years of 1h Kraken candles
- Simulate trades using the same strategy ensemble
- Epoch-based training (500 epochs) on simulated data
- Train/val/test splits with early stopping
- Hot-swap best weights into live bot without restart

### Planned: Transformer Policy Network (Phase 4)
```
Token Embedder → Multi-Head Self-Attention (4 heads) → FFN → Policy Head
```
- Scaled dot-product attention: softmax(QK^T / √d_k) · V
- 2 stacked encoder layers with residual connections + LayerNorm
- Interpretable attention weights (see which candles drove each decision)
- Parallel training — 10-100x faster than LSTM sequential unrolling

---

## LLaMA Integration (Phase 5)

Three specialized roles for a local LLM:

### Role 1: Sentiment & Macro Analysis
- Processes crypto news headlines, market data
- Outputs sentiment score [-1, +1] with conviction
- Feeds into ensemble signal pipeline as additional weight

### Role 2: Regime Detection
- Classifies market conditions: TRENDING, RANGING, HIGH_VOL_BREAKOUT, LOW_VOL_DRIFT
- Replaces broken Ornstein-Uhlenbeck process
- Adjusts position sizing and risk parameters per regime

### Role 3: Trade Explanation
- Generates natural language reasoning for every trade entry
- Rendered in dashboard reasoning panel
- Uses attention weights + signal breakdown + market context

---

## Dashboard

### Live Views
- **Overview**: Equity curve, PnL, balance, active positions, win rate
- **Trading**: Live signals per ticker, probability panel, reasoning panel
- **Performance**: Trade history, strategy performance breakdown
- **Quant Team**: 9 persona cards, prompt editors, status badges, system prompt
- **Optimizations**: Pending parameter changes with Apply All

### Tech Stack
- LightweightCharts v4 (candlestick + indicator overlays)
- WebSocket live streaming (fixed reconnection logic)
- 75 REST API endpoints
- enhancer.js v3.3 with xhr() helper, Quant Team bootstrapper

---

## Data Flow

```
Kraken Exchange
     ↓
Data Ingestion (10 tickers, async)
     ↓
Strategy Engine (36 strategies × 10 tickers)
     ↓
Ensemble (NN-weighted strategy combination)
     ↓
Signal Router (threshold gate + risk check)
     ↓
Trade Executor (Kraken API, TP/SL management)
     ↓
Trade Logger → Database (SQLite)
     ↓
Learning Engine (policy gradient update)
     ↓
Dashboard (WebSocket push to browser)
```

---

## Roadmap

| Phase | What | Status |
|-------|------|--------|
| 1-3 | Tokenizer + Embedder + LSTM | ✅ Deployed |
| 4 | Transformer Policy Network | 📋 Planned |
| 5 | LLaMA Integration (3 roles) | 🛠️ In Progress |
| 6 | Historical Training Pipeline | 📋 Planned |
| - | Win rate: 10% → 50-60% | 🎯 Target |
| - | Daily PnL: $1,000/day | 🎯 Target |

---

*Authored by Kevin the Minion 🍌*
*BANANAAA!*
