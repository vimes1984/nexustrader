# Neural Network Architecture Audit & Tokenization Proposal

## Executive Summary

NexusTrader currently uses a **raw-feature policy gradient network** — a shallow MLP that maps 8 handcrafted market features directly to strategy weights. This is a valid starting point but is architecturally wrong for the problem we're actually solving. This document identifies what's wrong, proposes the correct architecture type, and specifies a **market tokenization algorithm** to bridge the gap.

---

## Part 1: What We Have Now

### Current Architecture: Shallow Policy Gradient MLP

**File**: `learning_engine.py` — `PolicyNetwork` class

```text
Input (8 features) → Hidden (12 neurons × N layers, ReLU) → Output (6 strategies, Softmax)
```

**8 Input Features** (from `get_state_vector()`):
1. Market Regime (binary: 1.0 if mean-reverting, 0.0 if trending)
2. Mean Reversion Speed (theta from OU process, clamped 0-1)
3. Normalized RSI (-1.0 to 1.0)
4. Normalized MACD Histogram
5. Bollinger Band Position (-0.5 to 0.5)
6. ATR Volatility Ratio
7. Recent 10-trade Win Trend
8. News Sentiment Weight Factor

**Training**: Online policy gradient with experience replay buffer (capacity 200). Each closed trade produces a (state, alignment, advantage) tuple. Advantage = reward - baseline. Adam/RMSprop/SGD optimizer.

**Output**: Softmax probability distribution over 6 active trading strategies, used as ensemble weights.

### What's Wrong With This

1. **The input representation throws away information.** Eight handpicked scalars cannot capture the rich temporal structure of market data. RSI, MACD, and ATR are already lossy compressions — feeding them as inputs means the NN sees second-order derivatives of the actual data.

2. **Time is collapsed.** The NN sees a single snapshot. It has no notion of what happened 5 minutes ago, an hour ago, or yesterday. Markets are sequential processes — this is like trying to read a sentence one letter at a time with no memory of previous letters.

3. **Cross-asset relationships are invisible.** BTC and ETH movements are correlated, but the NN sees each ticker in isolation. A spike in BTC should inform ETH predictions.

4. **The architecture is wrong for time-series prediction.** A simple feedforward MLP with ReLU activations is a universal function approximator, but it has no inductive bias for sequential data. Recurrent networks (LSTM/GRU) or attention-based architectures (Transformers) have structural advantages for this domain.

5. **No tokenization.** The NN processes raw floats. Professional quantitative systems convert market data into discrete tokens (like words in NLP) so the model can learn higher-order patterns, regime transitions, and market "grammar."

---

## Part 2: What Architecture We Should Use

### Recommendation: Temporal Fusion Transformer (TFT) — Lite

For a trading bot targeting $1,000/day on crypto markets with ~10 tickers, we need:

- **Memory of recent market context** (minutes to hours)
- **Attention across tickers** (cross-asset signals)
- **Interpretability** (so quant agents can audit decisions)
- **Training efficiency** (we have limited GPU — this runs on an LXC)

**TFT-Lite** configuration:
```text
Market Tokenizer → Embedding (d=64) → LSTM Encoder (64 units) → Multi-Head Self-Attention (4 heads) → Policy Head (6 strategies, Softmax)
```

**Why this, not the alternatives**:

| Architecture | Strengths | Weaknesses for us |
|---|---|---|
| **Current MLP** | Simple, fast | No memory, no time structure, 8 features is too few |
| **LSTM/GRU** | Temporal memory, proven in finance | Vanishing gradients on long sequences, single-asset |
| **Temporal CNN (TCN)** | Fast training, long receptive field | Dilated convolutions need tuning, no cross-asset attention |
| **Full Transformer** | Long-range dependencies, cross-attention | Needs lots of data, expensive inference |
| **TFT (Lite)** ✅ | Variable importance, temporal + cross-asset attention, interpretable | Slightly more complex than LSTM alone |

The TFT line gives us three things we need:
1. **Variable selection networks** — the model learns which features matter per regime (volatile vs calm markets use different signals)
2. **Static covariate encoders** — ticker metadata (market cap rank, sector, listing age) is encoded once
3. **Temporal self-attention** — the model attends to important points in the price history

### Minimum Viable Upgrade Path

If a full TFT is too heavy for the LXC, the pragmatic step is:

1. **Add the tokenizer** (Part 3 below) to convert raw market data into discrete tokens
2. **Replace PolicyNetwork with an LSTM** (1-2 layers, 32-64 units) that consumes token sequences
3. **Add cross-asset attention** as a second phase — only after LSTM is proven

---

## Part 3: Market Tokenization Algorithm

### The Problem

Neural networks work best on discrete tokens with learned embeddings — this is why NLP models represent words as integers, not raw character codes. Market data should be treated the same way.

Instead of feeding raw RSI=0.32 into the network, we should map continuous market states to discrete tokens like `[PRICE_RISING_FAST]`, `[VOL_SPIKE]`, `[MOMENTUM_DIVERGENCE]`, etc. The model then learns an embedding for each token and can compose them sequentially.

### Token Vocabulary Design

We need a vocabulary of market micro-states. I propose **4 token families**:

#### Family 1: Price Action Tokens (per candle)
Generated from OHLCV data per 1h candle.

| Token | Condition |
|---|---|
| `PR_STRONG_UP` | Close > Open by >1.5× ATR, closes near high |
| `PR_UP` | Close > Open by 0.5-1.5× ATR |
| `PR_FLAT` | abs(Close - Open) < 0.3× ATR |
| `PR_DOWN` | Open > Close by 0.5-1.5× ATR |
| `PR_STRONG_DOWN` | Open > Close by >1.5× ATR, closes near low |
| `PR_DOJI` | Small body, long wicks (indecision) |
| `PR_HAMMER` | Long lower wick, small body at top |
| `PR_SHOOTING_STAR` | Long upper wick, small body at bottom |
| `PR_ENGULFING_BULL` | Body engulfs previous candle, closes higher |
| `PR_ENGULFING_BEAR` | Body engulfs previous candle, closes lower |

#### Family 2: Volume/Volatility Tokens (per candle)
| Token | Condition |
|---|---|
| `VOL_SPIKE` | Volume > 2× 20-period average |
| `VOL_DRY` | Volume < 0.5× 20-period average |
| `VOL_NORMAL` | Volume within normal range |
| `ATR_EXPANDING` | ATR rising (last 5 candles) |
| `ATR_CONTRACTING` | ATR falling (last 5 candles) |
| `ATR_STEADY` | ATR flat |

#### Family 3: Technical Regime Tokens (per candle)
| Token | Condition |
|---|---|
| `REG_TRENDING_UP` | Price above 20 EMA and 50 EMA, EMAs diverging |
| `REG_TRENDING_DOWN` | Price below 20 EMA and 50 EMA, EMAs diverging |
| `REG_RANGING` | Price oscillating between Bollinger Bands, BB width stable |
| `REG_BREAKOUT` | Price breaking Bollinger Band with volume confirmation |
| `REG_MEAN_REVERTING` | OU theta > 0.05 on 24-candle window |
| `REG_MOMENTUM` | RSI > 70 or < 30, sustained |
| `REG_DIVERGENCE` | Price making higher high, RSI making lower high (or inverse) |
| `REG_SUPPORT_TEST` | Price approaching recent swing low ± 0.5% |
| `REG_RESISTANCE_TEST` | Price approaching recent swing high ± 0.5% |

#### Family 4: Cross-Asset Context Tokens (per evaluation cycle)
| Token | Condition |
|---|---|
| `CTX_BTC_LEADING` | BTC moved >1% before altcoins followed |
| `CTX_ALTS_OUTPERFORMING` | Major altcoins outperforming BTC this cycle |
| `CTX_RISK_ON` | Crypto market cap rising, funding rates positive |
| `CTX_RISK_OFF` | Crypto market cap falling, funding rates negative |
| `CTX_CORR_HIGH` | Cross-ticker correlation > 0.8 |
| `CTX_CORR_LOW` | Cross-ticker correlation < 0.3 |
| `CTX_NEWS_DRIVEN` | Sentiment score extreme (>0.7 or <-0.7) |

### Tokenization Algorithm

```python
def tokenize_candle(candle: dict, prev_candle: dict, atr_20: float,
                     volume_ma_20: float, ema_20: float, ema_50: float,
                     ou_theta: float, rsi_14: float, bb_upper: float,
                     bb_lower: float, swing_low: float, swing_high: float,
                     btc_1h_return: float) -> list[str]:
    """
    Convert a single 1h OHLCV candle into a list of market tokens.

    Each candle produces 3-5 tokens: one price action token,
    one volume token, 1-2 regime tokens, and 0-1 cross-asset tokens.

    The result is a sequence like:
    ['PR_UP', 'VOL_NORMAL', 'REG_TRENDING_UP', 'CTX_RISK_ON']

    These tokens are then embedded and fed to the LSTM/Transformer.
    """
    tokens = []

    open_p, high, low, close, volume = (
        candle['open'], candle['high'], candle['low'],
        candle['close'], candle['volume']
    )

    body = close - open_p
    upper_wick = high - max(open_p, close)
    lower_wick = min(open_p, close) - low
    total_range = high - low + 1e-9
    body_ratio = abs(body) / total_range

    # --- Price Action Token ---
    if body > 1.5 * atr_20 and close / high > 0.9:
        tokens.append('PR_STRONG_UP')
    elif body > 0.5 * atr_20:
        tokens.append('PR_UP' if body > 0 else 'PR_DOWN')
    elif abs(body) < 0.3 * atr_20:
        if body_ratio < 0.3 and upper_wick > lower_wick * 1.5:
            tokens.append('PR_SHOOTING_STAR')
        elif body_ratio < 0.3 and lower_wick > upper_wick * 1.5:
            tokens.append('PR_HAMMER')
        else:
            tokens.append('PR_DOJI' if body_ratio < 0.15 else 'PR_FLAT')
    else:
        tokens.append('PR_DOWN')

    # Engulfing check (requires prev_candle)
    if prev_candle:
        prev_body = prev_candle['close'] - prev_candle['open']
        prev_body_abs = abs(prev_body)
        if abs(body) > prev_body_abs * 1.2:
            if body > 0 and prev_body < 0 and close > prev_candle['open']:
                tokens[-1] = 'PR_ENGULFING_BULL'
            elif body < 0 and prev_body > 0 and close < prev_candle['open']:
                tokens[-1] = 'PR_ENGULFING_BEAR'

    # --- Volume Token ---
    if volume > 2.0 * volume_ma_20:
        tokens.append('VOL_SPIKE')
    elif volume < 0.5 * volume_ma_20:
        tokens.append('VOL_DRY')
    else:
        tokens.append('VOL_NORMAL')

    # --- Regime Token ---
    if ou_theta > 0.05:
        tokens.append('REG_MEAN_REVERTING')
    elif close > ema_20 and ema_20 > ema_50:
        tokens.append('REG_TRENDING_UP')
    elif close < ema_20 and ema_20 < ema_50:
        tokens.append('REG_TRENDING_DOWN')
    elif close > bb_upper and volume > 1.5 * volume_ma_20:
        tokens.append('REG_BREAKOUT')
    elif rsi_14 > 70:
        tokens.append('REG_MOMENTUM')
    elif rsi_14 < 30:
        tokens.append('REG_MOMENTUM')
    elif bb_upper - bb_lower < 0.02 * close:
        tokens.append('REG_RANGING')
    else:
        # Check support/resistance proximity
        dist_to_support = abs(close - swing_low) / close
        dist_to_resistance = abs(close - swing_high) / close
        if dist_to_support < 0.005:
            tokens.append('REG_SUPPORT_TEST')
        elif dist_to_resistance < 0.005:
            tokens.append('REG_RESISTANCE_TEST')

    # --- Cross-Asset Context ---
    if abs(btc_1h_return) > 0.01:
        tokens.append('CTX_BTC_LEADING')
    elif btc_1h_return > 0.003:
        tokens.append('CTX_RISK_ON')
    elif btc_1h_return < -0.003:
        tokens.append('CTX_RISK_OFF')

    return tokens


def tokenize_ticker_window(candles: list[dict], window_size: int = 24) -> list[list[str]]:
    """
    Tokenize a sliding window of recent candles for one ticker.
    Returns a sequence of token lists — one per candle.

    This is the input to the LSTM/Transformer: a sequence of
    discrete token lists, each embedded into a learned vector.
    """
    sequence = []
    # Precompute indicators that need rolling windows
    closes = [c['close'] for c in candles]
    volumes = [c['volume'] for c in candles]

    for i in range(max(0, len(candles) - window_size), len(candles)):
        candle = candles[i]
        prev = candles[i - 1] if i > 0 else None
        window = candles[max(0, i - 24):i + 1]
        window_closes = [w['close'] for w in window]
        window_volumes = [w['volume'] for w in window]

        atr_20 = compute_atr(window, 14)
        volume_ma_20 = np.mean(window_volumes[-20:]) if len(window) >= 20 else np.mean(window_volumes)
        ema_20 = compute_ema(window_closes, 20)
        ema_50 = compute_ema(window_closes, 50)
        ou_theta, _, _ = estimate_ou_process(window_closes[-24:])
        rsi = compute_rsi(window_closes, 14)
        bb_upper, bb_lower = compute_bollinger(window_closes, 20, 2)
        swing_low = min([w['low'] for w in window[-24:-1]] or [candle['low']])
        swing_high = max([w['high'] for w in window[-24:-1]] or [candle['high']])

        btc_return = 0.0  # Need cross-ticker data — fetched separately

        tokens = tokenize_candle(
            candle, prev, atr_20, volume_ma_20,
            ema_20, ema_50, ou_theta, rsi,
            bb_upper, bb_lower, swing_low, swing_high, btc_return
        )
        sequence.append(tokens)

    return sequence
```

### Vocabulary Size
Approximately **35-40 tokens** total across all four families. This is intentionally small — each token appears frequently enough for the embedding layer to learn meaningful representations. Can be expanded as the model proves profitable.

### How the Tokenizer Feeds the NN

```text
Raw OHLCV candles (24h window)
    │
    ▼
Tokenizer ──→ ['PR_UP', 'VOL_NORMAL', 'REG_TRENDING_UP', 'CTX_RISK_ON']   [t-24]
              ['PR_FLAT', 'VOL_DRY', 'REG_RANGING', 'CTX_CORR_HIGH']       [t-23]
              ...                                                           ...
              ['PR_STRONG_UP', 'VOL_SPIKE', 'REG_BREAKOUT', 'CTX_BTC_LEADING'] [t-1]
              ['PR_DOJI', 'VOL_NORMAL', 'REG_SUPPORT_TEST', 'CTX_RISK_OFF']    [t=0]
    │
    ▼
Multi-Hot Embedding (per candle)
    Each candle's tokens → binary vector of size vocab → learned dense embedding (d=64)
    │
    ▼
Positional Encoding
    Sinusoidal or learned position embeddings added to token embeddings
    │
    ▼
LSTM / Transformer Encoder
    Sequence of 24 embedded candle representations → contextualized hidden states
    │
    ▼
Policy Head (MLP)
    Final hidden state → 6-way Softmax → strategy allocation weights
```

---

## Part 4: Implementation Plan for Antigravity

### Phase 1: Tokenizer Module (1-2 hours)
- [ ] Create `tokenizer.py` with the token vocabulary and `tokenize_candle()` function
- [ ] Add unit tests in `tests/test_tokenizer.py`
- [ ] Verify tokenizer produces sensible sequences on historical BTC data
- [ ] Tokenizer should be a clean, standalone module — no database or network dependencies

### Phase 2: Tokenized State Representation (2-3 hours)
- [ ] Create `token_embedder.py` — maps token lists to dense vectors
- [ ] Embedding layer: each token gets a learned 64-dim vector
- [ ] Multi-hot pooling: if a candle has multiple tokens, average or sum their embeddings
- [ ] Add positional encoding for the 24-candle sequence
- [ ] Unit tests for embedder output shapes

### Phase 3: LSTM Policy Network (3-4 hours)
- [ ] Create `sequential_policy_net.py` — replaces or extends `PolicyNetwork`
- [ ] Architecture: TokenEmbed(64) → LSTM(64, 2 layers, dropout=0.1) → Linear(6) → Softmax
- [ ] Keep the existing experience replay buffer
- [ ] Same training interface: `forward(state_sequence)`, `backward(sequence, alignment, advantage)`
- [ ] Backward-compatible with `LearningEngine` — can swap in via config flag
- [ ] A/B test against current MLP on backtest data

### Phase 4: Cross-Asset Attention (4-5 hours)
- [ ] Add cross-ticker context tokens to the tokenizer
- [ ] Implement multi-ticker attention: each ticker's LSTM hidden state attends to every other ticker's hidden state
- [ ] This lets BTC movement influence ETH strategy weights without manual feature engineering
- [ ] Unit tests for attention weight correctness

### Phase 5: Full Integration & Backtest (3-4 hours)
- [ ] Wire new architecture into `main.py` orchestrator via config flag (`nn_architecture: "mlp" | "lstm" | "tft_lite"`)
- [ ] Backtest all three architectures on 60 days of historical data
- [ ] Compare: Sharpe ratio, max drawdown, win rate, PnL
- [ ] Deploy best-performing architecture via `deploy.sh`

### What NOT to Do
- ❌ Don't use the current 8-feature vector as input to the LSTM — you lose the whole point of tokenization
- ❌ Don't skip the positional encoding — LSTM has inherent order sensitivity, but explicit position info helps convergence
- ❌ Don't make the vocabulary too large (>50 tokens) — sparse tokens don't train well
- ❌ Don't use a full GPT-style Transformer — we have ~10 tickers × 24 candles = tiny context, not millions of tokens
- ❌ Don't remove the existing PolicyNetwork until the new one beats it on backtest

### Success Criteria
The tokenized LSTM/Transformer must outperform the current MLP on:
1. **Backtest Sharpe ratio** (target: >1.5, current: unknown — measure first)
2. **Live win rate** (target: >50%, current: 10%)
3. **Training stability** — no weight collapse, no NaN gradients
4. **Inference latency** — under 100ms per ticker (must keep up with 1h candles)

---

## Part 5: Why This Matters for $1,000/Day

The current MLP with 8 handcrafted features is a **linear model in a nonlinear world**. It can only learn surface-level patterns. The reason the bot is 1W/9L is not just bad parameters — it's that the model literally cannot see the patterns it needs to learn.

Tokenization + sequential architecture gives us:
- **Regime awareness**: The model sees the transition from `REG_RANGING` to `REG_BREAKOUT` as a discrete event
- **Memory**: The LSTM remembers that volume was drying up for 3 candles before the breakout — the MLP sees only the current candle
- **Transfer learning**: BTC regime tokens inform ETH predictions without manual feature engineering
- **Auditability**: Quant agents can inspect token sequences — "the model went bearish because it saw `PR_SHOOTING_STAR` + `VOL_SPIKE` + `CTX_RISK_OFF`" is much more interpretable than "the 3rd neuron in the hidden layer fired"

---

*Generated by OpenClaw (Keith 🍺) — handoff to Antigravity, July 20, 2026*
