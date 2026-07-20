# Neural Network Expansion Plan v2: Transformer + LLaMA + Historical Training

*Extension of NN_ARCHITECTURE_AUDIT.md Phase 1-3 (completed).*

## Executive Summary

The shallow MLP → LSTM upgrade (Phase 1-3) was step one. This document covers:

1. **Phase 4: Multi-Head Self-Attention (Transformer)** — replace/supplement LSTM with attention-based sequence modeling, per "Attention Is All You Need" (Vaswani et al., 2017)
2. **Phase 5: LLaMA Integration** — local large language model serving three roles: sentiment/macro analysis, regime detection, trade explanation
3. **Phase 6: Historical Training Pipeline** — years of 1h candle data from Kraken, offline epoch-based training, proper train/val/test splits

Timeframes assume Antigravity (Google's code LLM) doing the implementation. Total estimated: 20-30 hours.

---

## Hardware Realities

### Current
| Machine | Role | RAM | Cores | GPU | Disk |
|---------|------|-----|-------|-----|------|
| 192.168.0.144 | Bot VM (LXC) | 2GB | 2 | None | 20GB |
| 192.168.0.197 | OpenClaw Server (LXC) | 4GB | 2 | None | 14GB |
| 192.168.0.166 | Proxmox Host (HP ProDesk 600 G2) | Unknown | Unknown | Intel HD 530 | Unknown |

### Target (for this plan)
| Machine | Role | RAM needed | Notes |
|---------|------|------------|-------|
| 192.168.0.144 | Live trading only | 2GB ✓ | Inference only — no training, no LLaMA |
| 192.168.0.166 | Offline training + LLaMA | 16GB+ | Hosts training scripts + llama.cpp server |
| 128GB Machine | LLaMA heavy lifting | 8GB+ for 8B Q4 | If bridgeable from the other LAN |

**Decision tree:**
- If Proxmox has 32GB+ RAM: host LLaMA on Proxmox directly (single-box simpler)
- If Proxmox has 16GB: host TinyLlama 1.1B Q4 on Proxmox for fast inference, 128GB machine for larger models
- If Proxmox is too constrained: bridge the 128GB machine onto the LAN for LLaMA, keep Proxmox for training only

---

## Phase 4: Transformer Policy Network

### Architecture

```
Input: Tokenized candle sequence (seq_len=24, max_tokens=5 per candle)
       ↓
  Token Embedder (vocab → 64d, mean-pool per candle, positional encoding)
       ↓
  ［Transformer Encoder］
  ├── Multi-Head Self-Attention (4 heads, d_k=16)
  │   ├── Q = W_q · x    (learned query)
  │   ├── K = W_k · x    (learned key)
  │   ├── V = W_v · x    (learned value)
  │   └── Attention(Q,K,V) = softmax(QK^T / √d_k) · V
  ├── Add & Norm (residual + layer norm)
  ├── Feed-Forward (64 → 128 → 64, ReLU)
  ├── Add & Norm
  └── × 2 layers (stacked encoders)
       ↓
  Global Average Pooling → 64d vector
       ↓
  Policy Head (64 → 32 → num_strategies, Softmax)
       ↓
  Output: Strategy weights [w₁, w₂, ... wₙ]
```

### Why Transformer beats LSTM for trading

- **Parallel processing**: attention computes all time-steps simultaneously during training — 10-100x faster than LSTM sequential unrolling
- **Long-range dependencies**: LSTM forgets after ~20-30 steps due to vanishing gradients; attention has direct path from candle #1 to candle #24
- **Interpretability**: attention weights show exactly which historical candles the model considers important for each decision — gold for the dashboard reasoning panel
- **Multi-head**: different heads learn different patterns (one head for momentum, one for mean-reversion, one for volatility)

### Implementation (pure NumPy, no PyTorch)

**File: `transformer_policy_net.py`**

```python
class MultiHeadAttention:
    """Multi-head scaled dot-product attention.
    
    Q, K, V projections are learned linear transforms.
    Mask supports causal (autoregressive) and padding masks.
    """
    
class TransformerEncoderLayer:
    """One encoder block: Attention → Add&Norm → FFN → Add&Norm"""
    
class TransformerPolicyNetwork:
    """Full transformer for strategy weight selection.
    
    Same interface as PolicyNetwork and SequentialPolicyNetwork:
    - forward(state) → strategy_weights
    - backward(d_out) → parameter updates  
    - select_weights(state) → weights with floor enforcement
    - to_json() / from_json() → persistence
    """
```

### Integration into LearningEngine

Add `nn_architecture = "transformer"` option alongside `"mlp"` and `"lstm"`:
```python
if nn_architecture == "transformer":
    from transformer_policy_net import TransformerPolicyNetwork
    self.policy_net = TransformerPolicyNetwork(
        action_dim=num_strategies,
        embed_dim=hidden_dim,
        num_heads=4,
        num_layers=2,
        max_seq_len=24,
        learning_rate=learning_rate,
        dropout=dropout,
    )
```

### Unit tests (TDD, per coding standards)

- `test_transformer_policy_net.py`: attention math (QK^T shape, softmax rows sum to 1), encoder forward/backward, full pipeline with tokenizer → embedder → transformer → weights, serialization round-trip, gradient flow through attention heads

---

## Phase 5: LLaMA Integration

### System Architecture

```
┌─────────────────────┐     HTTP/JSON      ┌──────────────────────┐
│  NexusTrader Bot    │ ──────────────────→ │  llama.cpp Server    │
│  (192.168.0.144)    │ ←────────────────── │  (Proxmox or 128GB)  │
│                     │   OpenAI-compatible │                      │
│  openclaw_bridge.py │    /v1/completions  │  port 8080           │
│  (already exists)   │                     │                      │
└─────────────────────┘                     └──────────────────────┘
```

### LLaMA Server Setup (on Proxmox or 128GB machine)

```bash
# Build llama.cpp with server support
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp && make -j server

# Download model (choose based on available RAM):
# TinyLlama 1.1B Q4_K_M  — ~700MB RAM, runs on anything
# LLaMA 3 8B Q4_K_M     — ~5GB RAM, good quality
# LLaMA 3 70B Q4_K_M    — ~40GB RAM, 128GB machine only

# Run as systemd service:
./server -m models/llama-3-8b-q4_k_m.gguf \
  --host 0.0.0.0 --port 8080 \
  --ctx-size 4096 --threads 4
```

### LLM Client Module

**File: `nexustrader/llm_client.py`**

```python
class LLMClient:
    """Thin wrapper around llama.cpp server for trading-specific queries.
    
    Uses the same openclaw_bridge pattern Chris already has working:
    HTTP POST to llama.cpp's OpenAI-compatible /v1/completions endpoint.
    """
    
    def analyze_sentiment(self, headlines: list[str]) -> dict:
        """Sentiment/macro analysis of recent news/crypto headlines.
        
        Returns: {sentiment_score: float, direction: str, confidence: float,
                  key_themes: [str], risk_factors: [str]}
        """
    
    def classify_regime(self, market_summary: str) -> dict:
        """Regime detection from current market conditions.
        
        Returns: {regime: str, risk_level: str, recommended_allocation: float,
                  reasoning: str}
        """
    
    def explain_trade(self, trade_context: dict) -> str:
        """Explain WHY a trade was entered — for dashboard reasoning panel.
        
        Input: {symbol, direction, signal_strength, strategy_weights, 
                regime, market_data_summary, attention_weights}
        Returns: Natural language explanation
        """
```

### Three LLaMA Roles (as specified)

#### Role 1: Sentiment & Macro Analysis

Cron trigger: every 15 minutes or on significant news events.

```
Input to LLaMA:
"Analyze the following crypto market headlines for trading sentiment:
- [headline 1]
- [headline 2]
...

Current positions: {active_positions}
Current regime: {regime}
Recent PnL: ${pnl}

Output JSON with:
- overall_sentiment: -1.0 to 1.0
- conviction: 0.0 to 1.0
- key_themes: list of dominant narratives
- risk_factors: list of things to watch
- recommended_action: reduce/hold/increase exposure
"
```

Wired into `orchestrator` as an additional sentiment source — feeds into the ensemble signal alongside strategy signals, with configurable weight.

#### Role 2: Regime Detection

Cron trigger: every 30 minutes.

```
Input to LLaMA:
"Current market state for {ticker}:
Price: ${price}
24h change: {change_pct}%
ATR(14): {atr}
RSI(14): {rsi}
Volume vs 20-period MA: {volume_ratio}
BTC correlation: {btc_corr}
Recent signals: {signal_summary}

Classify into one of:
- TRENDING_UP (strong bullish trend)
- TRENDING_DOWN (strong bearish trend)  
- RANGING (sideways/consolidation)
- HIGH_VOL_BREAKOUT (potential breakout)
- HIGH_VOL_BREAKDOWN (potential crash)
- LOW_VOL_DRIFT (dead market, avoid)

Output JSON with regime, confidence, recommended position sizing multiplier."
```

This LLaMA regime classification replaces the broken OU process — it handles non-stationary data naturally by describing what it sees rather than assuming a stationary process.

#### Role 3: Trade Explanation

Trigger: every trade open event.

```
Input to LLaMA:
"Explain this trade entry to a trader:
Symbol: {symbol}
Direction: {direction}
Entry price: ${entry}
Strategy weights: {strategy_weights} (top 3: {top3})
Signal strength: {signal}
Market regime: {regime}
Attention focus: {top_attention_candles}
Confidence: {confidence}

Explain in 2-3 sentences why the bot entered this trade. 
Be specific about which indicators and patterns drove the decision.
Mention any risks."
```

Rendered in the dashboard reasoning panel (`/api/trading/reasoning`), replacing the current generic "Bot is operating normally."

### Overlap with OpenClaw Bridge

Chris already has `openclaw_bridge.py` working (192.168.0.197:18789/v1). The LLaMA client reuses the same pattern but points at the llama.cpp server instead. Two options:

1. **Separate client**: `llm_client.py` is standalone — direct HTTP to llama.cpp, no dependency on OpenClaw Gateway
2. **Through Gateway**: configure a "llama" model in OpenClaw that routes to the llama.cpp server — lets us use the same `openclaw_bridge.py` with `model="llama"`

**Recommendation: Option 2** — single code path, same auth, same retry logic. Just needs Gateway config update.

---

## Phase 6: Historical Training Pipeline

### Problem

Current training is **online-only policy gradient** from live trades:
- 10 trades total, 1 win / 9 losses
- Replay buffer capacity: 200 transitions (lost on restart)
- No offline training, no epochs, no train/val split
- Only trains when a trade closes — weeks between gradient steps at this rate
- MLP with 8 features has never seen a proper training loop

### Solution: Two-Path Training

```
Path A: Online (live, continuous) ← current path, preserved
  ↓
  On each trade close: store in replay, one REINFORCE step

Path B: Offline (periodic, bulk) ← NEW
  ↓
  Weekly cron: fetch historical data → tokenize → train epochs → save weights
  
Path B for initial bootstrap:
  1. Fetch 2 years of 1h candles from Kraken (not yfinance — rate limits)
  2. Simulate trades using same strategy ensemble + probability engine
  3. Tokenize all candles with tokenizer.py
  4. Train Transformer for 500 epochs on simulated outcomes
  5. Validate on held-out month, save best weights
  6. Load into live bot
```

### Kraken Historical Data Fetcher

**File: `nexustrader/historical_pipeline.py`**

```python
class HistoricalDataPipeline:
    """Bulk historical data fetch from Kraken (no rate limit issues like yfinance)."""
    
    KRAKEN_INTERVALS = {60: 720}  # 1h candles, max 720 per request
    
    def fetch_ticker_history(self, ticker: str, days: int = 730) -> pd.DataFrame:
        """Fetch up to 2 years of 1h OHLCV data from Kraken.
        
        Kraken allows 720 candles per request for 1h interval.
        For 2 years: 730 * 24 = 17,520 candles → ~25 requests.
        Rate limit: 1 request per 2 seconds → ~50 seconds per ticker.
        """
    
    def build_training_dataset(self, tickers: list[str]) -> dict:
        """Fetch + tokenize + store historical data for all active tickers.
        
        Returns: {
            'ticker_tokens': {ticker: [(seq_len, max_tokens)] arrays},
            'ticker_prices': {ticker: pd.DataFrame},
            'simulated_trades': {ticker: [Trade dicts]}
        }
        """
```

### Simulated Trade Generation

Rather than random actions (which teach nothing), simulate trades using the **existing strategy ensemble** on historical data:

```python
def simulate_historical_trades(price_df, strategies, signal_threshold):
    """Walk through price history, generate signals, simulate trades.
    
    For each candle:
    1. Run all strategies → get ensemble signal
    2. If signal > threshold: simulate entry
    3. Apply TP/SL logic with ATR-based levels
    4. Record outcome (win/loss, PnL%, strategy weights)
    
    This produces training labels that match how the bot actually trades,
    not random actions that teach a policy the bot can't execute.
    """
```

### Training Loop

**File: `nexustrader/trainer.py`**

```python
class OfflineTrainer:
    """Epoch-based training on historical data.
    
    Supports: MLP, LSTM, and Transformer architectures.
    """
    
    def train(self, dataset, architecture, epochs=500, 
              batch_size=32, val_split=0.2):
        """Full training loop with train/val/test split.
        
        Metrics tracked per epoch:
        - Policy loss (negative log likelihood + entropy bonus)
        - Win rate on validation set
        - Sharpe ratio on validation set
        - Gradient norm (stability check)
        
        Early stopping: patience=50 epochs on val win rate
        """
    
    def evaluate(self, test_dataset):
        """Final evaluation on held-out test month.
        
        Returns: {
            'win_rate': float,
            'sharpe': float,
            'max_drawdown': float,
            'total_return': float,
            'profit_factor': float
        }
        """
```

### Integration into Quant Team

New cron agent: **🧠 Training Conductor**

- **Schedule**: Every Sunday 2AM UTC (staggered from existing agents)
- **What it does**:
  1. SSH to Proxmox host (192.168.0.166)
  2. Run `trainer.py` with latest weights as initialization
  3. Fetch new historical data from Kraken (incremental update)
  4. Train for 500 epochs on all 10 tickers
  5. Evaluate on held-out validation period
  6. If val metrics improve: save new weights, report to blog, reload into bot
  7. If val metrics degrade: keep current weights, log warning

### Weight Reload (hot swap)

The bot needs to load new weights without restarting (restarting closes positions and resets state):

```python
# In orchestrator, add endpoint for weight hot-swap
@app.post("/api/nn/reload-weights")
async def reload_nn_weights():
    """Reload NN weights from disk without restarting the bot.
    
    Reads the latest trained weights JSON file,
    deserializes into the policy network, and swaps atomically.
    Does NOT affect open positions or active strategies.
    """
    orchestrator.learning_engine.policy_net.from_json(
        open("data/weights/best_transformer.json").read()
    )
    return {"status": "ok", "architecture": "transformer"}
```

---

## Implementation Plan

### Phase 4: Transformer (4-6 hours)
- [ ] `multi_head_attention.py` — MultiHeadAttention class, scaled dot-product, causal/padding masks
- [ ] `transformer_encoder.py` — EncoderLayer, stacked encoders, residual + layer norm
- [ ] `transformer_policy_net.py` — Full TransformerPolicyNetwork, same interface
- [ ] `tests/test_transformer.py` — attention math, encoder gradients, full pipeline
- [ ] Wire into LearningEngine: `nn_architecture = "transformer"`
- [ ] Verify with `python3 -m unittest`, commit, deploy

### Phase 5: LLaMA (6-8 hours)
- [ ] Set up llama.cpp server on target machine (Proxmox or 128GB)
- [ ] Download model (TinyLlama 1.1B for testing, 8B for production)
- [ ] `llm_client.py` — LLMClient with three query methods
- [ ] Wire sentiment analysis into orchestrator's signal pipeline
- [ ] Wire regime detection → risk mode override
- [ ] Wire trade explanation → `/api/trading/reasoning` dashboard panel
- [ ] Add `llama_enabled`, `llama_endpoint`, `llama_model` DB settings
- [ ] New Quant Team agent: **🧠 LLM Analyst** (cron: every 15 min)

### Phase 6: Historical Training (10-12 hours)
- [ ] `historical_pipeline.py` — Kraken bulk data fetch + tokenization
- [ ] `simulator.py` — Historical trade simulation using ensemble
- [ ] `trainer.py` — Epoch-based training loop with metrics
- [ ] `weight_manager.py` — Save/load/compare/swap model weights
- [ ] `/api/nn/reload-weights` — Hot-swap endpoint
- [ ] New Quant Team agent: **🧠 Training Conductor** (cron: weekly)
- [ ] Initial bootstrap: fetch 2 years data, train 500 epochs, validate

### Phase 7: Bridge 128GB Machine (2-4 hours, conditional)
- [ ] Network bridge: route/port-forward between LANs
- [ ] Deploy llama.cpp server with LLaMA 3 8B or 70B Q4
- [ ] Point `llm_client.py` at the 128GB machine
- [ ] Compare inference quality vs TinyLlama on Proxmox

---

## Success Criteria

| Metric | Current | Phase 4 (Transformer) | Phase 4+5 (+LLaMA) | Phase 4+5+6 (+Training) |
|--------|---------|----------------------|--------------------|------------------------|
| Win rate | 10% | 35-45% (offline sim) | 40-50% | 50-60% |
| Training samples | 10 trades | 10 trades | 10 trades | 2,000+ simulated + 10 live |
| Regime detection | Broken OU process | Broken OU process | LLaMA classification | LLaMA + backtested validity |
| Training speed | N/A (online only) | N/A | N/A | ~3 min/epoch (Transformer, batch=32) |
| Reasoning quality | "Bot operating normally" | Attention weights visible | Natural language explanation | Contextual + backtest-grounded |
| Daily PnL target | -$0.21 | Proving ground | $50-200/day | **$1,000/day** |

---

## Next Actions (Chris)

1. **Check Proxmox specs**: Open `https://192.168.0.166:8006/` in browser, log in, check Summary page for RAM/CPU/disk
2. **128GB machine**: What's the OS? Is it Linux? Any GPU? Can you bridge the two LANs?
3. **Proxmox SSH**: Add our public key so we can deploy training infrastructure
   ```bash
   # On Proxmox host (you'd run this):
   echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA..." >> /root/.ssh/authorized_keys
   ```
   Key is at `/root/.ssh/id_ed25519.pub` on the OpenClaw server (192.168.0.197)
4. **Pick LLaMA model size**: Based on Proxmox RAM, which model fits?
   - TinyLlama 1.1B Q4: ~700MB (bare minimum, fast but dumb)
   - LLaMA 3 8B Q4: ~5GB (sweet spot for trading analysis)
   - LLaMA 3 70B Q4: ~40GB (128GB machine only, overkill for this use case)
