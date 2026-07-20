"""
Market Tokenization Module — Phase 1 of NN Architecture Upgrade.

Converts raw OHLCV candle data into discrete market-state tokens.
A 1h candle becomes 3-5 tokens from 4 families:
  - Price Action (10 tokens)
  - Volume/Volatility (6 tokens)
  - Technical Regime (9 tokens)
  - Cross-Asset Context (7 tokens)

Tokenized sequences feed into the LSTM policy network, giving the model
discrete market-state awareness instead of raw continuous scalars.
"""
import numpy as np
from typing import List, Optional

# ─── Token Vocabulary ──────────────────────────────────────────────────────

PRICE_ACTION_TOKENS = [
    'PR_STRONG_UP', 'PR_UP', 'PR_FLAT', 'PR_DOWN', 'PR_STRONG_DOWN',
    'PR_DOJI', 'PR_HAMMER', 'PR_SHOOTING_STAR',
    'PR_ENGULFING_BULL', 'PR_ENGULFING_BEAR',
]

VOLUME_TOKENS = [
    'VOL_SPIKE', 'VOL_DRY', 'VOL_NORMAL',
    'ATR_EXPANDING', 'ATR_CONTRACTING', 'ATR_STEADY',
]

REGIME_TOKENS = [
    'REG_TRENDING_UP', 'REG_TRENDING_DOWN', 'REG_RANGING',
    'REG_BREAKOUT', 'REG_MEAN_REVERTING', 'REG_MOMENTUM',
    'REG_DIVERGENCE', 'REG_SUPPORT_TEST', 'REG_RESISTANCE_TEST',
]

CONTEXT_TOKENS = [
    'CTX_BTC_LEADING', 'CTX_ALTS_OUTPERFORMING',
    'CTX_RISK_ON', 'CTX_RISK_OFF',
    'CTX_CORR_HIGH', 'CTX_CORR_LOW', 'CTX_NEWS_DRIVEN',
]

# Ordered full vocabulary; index used as token_id
FULL_VOCABULARY = (
    PRICE_ACTION_TOKENS +
    VOLUME_TOKENS +
    REGIME_TOKENS +
    CONTEXT_TOKENS
)

VOCAB_SIZE = len(FULL_VOCABULARY)
TOKEN_TO_ID = {tok: i for i, tok in enumerate(FULL_VOCABULARY)}


# ─── Helper Functions ───────────────────────────────────────────────────────

def _compute_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> float:
    """Compute ATR over a numpy array window."""
    if len(close) < 2:
        return 0.0
    tr = np.maximum(
        high[1:] - low[1:],
        np.maximum(
            np.abs(high[1:] - close[:-1]),
            np.abs(low[1:] - close[:-1]),
        ),
    )
    if len(tr) == 0:
        return 0.0
    return float(np.mean(tr[-period:]) if len(tr) >= period else np.mean(tr))


def _compute_ema(series: np.ndarray, period: int) -> float:
    """Compute EMA of a series at its last point."""
    if len(series) == 0:
        return 0.0
    if len(series) < period:
        return float(np.mean(series))
    alpha = 2.0 / (period + 1)
    ema = float(np.mean(series[:period]))
    for i in range(period, len(series)):
        ema = alpha * series[i] + (1 - alpha) * ema
    return ema


def _compute_rsi(closes: np.ndarray, period: int = 14) -> float:
    """Compute RSI-14."""
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = float(np.mean(gains[-period:]))
    avg_loss = float(np.mean(losses[-period:]))
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100.0 - 100.0 / (1.0 + rs))


def _compute_bollinger(closes: np.ndarray, period: int = 20, n_std: float = 2.0):
    """Return (upper, lower) Bollinger Bands."""
    if len(closes) < period:
        return closes[-1] + 1, closes[-1] - 1
    sma = float(np.mean(closes[-period:]))
    std = float(np.std(closes[-period:]))
    return sma + n_std * std, sma - n_std * std


def _estimate_ou_theta(prices: np.ndarray) -> float:
    """Estimate OU mean-reversion speed theta from a price window."""
    if len(prices) < 20:
        return 0.0
    x = prices[:-1]
    y = prices[1:]
    A = np.vstack([x, np.ones(len(x))]).T
    try:
        a, _ = np.linalg.lstsq(A, y, rcond=None)[0]
    except np.linalg.LinAlgError:
        return 0.0
    if a <= 0 or a >= 1:
        return 0.0
    return float(-np.log(a))


# ─── Tokenization ───────────────────────────────────────────────────────────

def tokenize_candle(
    candle: dict,
    prev_candle: Optional[dict],
    atr_20: float,
    volume_ma_20: float,
    ema_20: float,
    ema_50: float,
    ou_theta: float,
    rsi_14: float,
    bb_upper: float,
    bb_lower: float,
    swing_low: float,
    swing_high: float,
    btc_1h_return: float,
) -> List[str]:
    """Convert a single 1h candle into a list of market tokens.

    Args:
        candle: dict with open, high, low, close, volume
        prev_candle: previous candle dict (or None for first candle)
        atr_20: 20-period ATR computed from window
        volume_ma_20: 20-period volume moving average
        ema_20: 20-period EMA of close
        ema_50: 50-period EMA of close
        ou_theta: OU mean-reversion speed estimate
        rsi_14: 14-period RSI
        bb_upper: upper Bollinger Band (20, 2)
        bb_lower: lower Bollinger Band (20, 2)
        swing_low: recent 24-period swing low
        swing_high: recent 24-period swing high
        btc_1h_return: BTC 1-hour return (for cross-asset context)

    Returns:
        List of token strings, e.g. ['PR_UP', 'VOL_NORMAL', 'REG_TRENDING_UP']
    """
    tokens: List[str] = []

    open_p = float(candle['open'])
    high = float(candle['high'])
    low = float(candle['low'])
    close = float(candle['close'])
    volume = float(candle['volume'])

    body = close - open_p
    body_abs = abs(body)
    upper_wick = high - max(open_p, close)
    lower_wick = min(open_p, close) - low
    total_range = high - low + 1e-9
    body_ratio = body_abs / total_range if total_range > 0 else 0.0

    # ── Price Action Token ──
    if body > 1.5 * atr_20 and atr_20 > 0 and close > open_p:
        tokens.append('PR_STRONG_UP')
    elif body_abs > 1.5 * atr_20 and atr_20 > 0:
        tokens.append('PR_STRONG_DOWN')
    elif body_abs > 0.5 * atr_20 and atr_20 > 0:
        tokens.append('PR_UP' if body > 0 else 'PR_DOWN')
    elif body_abs < 0.3 * atr_20 or body_ratio < 0.2:
        if body_ratio < 0.1:
            tokens.append('PR_DOJI')
        elif upper_wick > lower_wick * 1.2 and upper_wick > body_abs * 2 and lower_wick < body_abs:
            tokens.append('PR_SHOOTING_STAR')
        elif lower_wick > upper_wick * 1.2 and lower_wick > body_abs * 2 and upper_wick < body_abs:
            tokens.append('PR_HAMMER')
        else:
            tokens.append('PR_FLAT')
    else:
        tokens.append('PR_UP' if body > 0 else 'PR_DOWN')

    # Engulfing check
    if prev_candle is not None:
        prev_body = float(prev_candle['close']) - float(prev_candle['open'])
        prev_body_abs = abs(prev_body)
        if prev_body_abs > 0 and body_abs > prev_body_abs * 1.1:
            if body > 0 and prev_body < 0 and close > float(prev_candle['open']):
                tokens[-1] = 'PR_ENGULFING_BULL'
            elif body < 0 and prev_body > 0 and close < float(prev_candle['open']):
                tokens[-1] = 'PR_ENGULFING_BEAR'

    # ── Volume Token ──
    if volume > 2.0 * volume_ma_20 and volume_ma_20 > 0:
        tokens.append('VOL_SPIKE')
    elif volume < 0.5 * volume_ma_20 and volume_ma_20 > 0:
        tokens.append('VOL_DRY')
    else:
        tokens.append('VOL_NORMAL')

    # ── Regime Token ──
    if ou_theta > 0.05:
        tokens.append('REG_MEAN_REVERTING')
    elif close > ema_20 and ema_20 > ema_50 and ema_50 > 0:
        tokens.append('REG_TRENDING_UP')
    elif close < ema_20 and ema_20 < ema_50 and ema_50 > 0:
        tokens.append('REG_TRENDING_DOWN')
    elif close > bb_upper and volume > 1.5 * volume_ma_20 and volume_ma_20 > 0:
        tokens.append('REG_BREAKOUT')
    elif rsi_14 > 70:
        tokens.append('REG_MOMENTUM')
    elif rsi_14 < 30:
        tokens.append('REG_MOMENTUM')
    elif bb_upper - bb_lower < 0.02 * close and close > 0 and bb_upper > bb_lower:
        tokens.append('REG_RANGING')
    else:
        # Support/resistance proximity
        dist_support = abs(close - swing_low) / close if close > 0 else 1.0
        dist_resistance = abs(close - swing_high) / close if close > 0 else 1.0
        if dist_support < 0.005:
            tokens.append('REG_SUPPORT_TEST')
        elif dist_resistance < 0.005:
            tokens.append('REG_RESISTANCE_TEST')
        else:
            tokens.append('REG_RANGING')  # fallback

    # ── Cross-Asset Context ──
    if abs(btc_1h_return) > 0.01:
        tokens.append('CTX_BTC_LEADING')
    elif btc_1h_return > 0.003:
        tokens.append('CTX_RISK_ON')
    elif btc_1h_return < -0.003:
        tokens.append('CTX_RISK_OFF')

    return tokens


def tokenize_ticker_window(
    candles: List[dict],
    window_size: int = 24,
    btc_hourly_returns: Optional[List[float]] = None,
) -> List[List[str]]:
    """Tokenize a sliding window of recent candles for one ticker.

    Args:
        candles: list of OHLCV candle dicts, ordered oldest→newest
        window_size: number of candles in the sliding window (default 24)
        btc_hourly_returns: parallel list of BTC 1h returns for each candle
                            index (used for cross-asset context tokens)

    Returns:
        List of token lists, one per candle in the window.
        E.g. [['PR_FLAT','VOL_NORMAL','REG_RANGING'], ['PR_UP','VOL_SPIKE','REG_BREAKOUT'], ...]
    """
    if len(candles) < window_size:
        window = candles
    else:
        window = candles[-window_size:]

    sequence: List[List[str]] = []
    for i in range(len(window)):
        candle = window[i]
        prev = window[i - 1] if i > 0 else candles[i - 1] if i > 0 and i - 1 < len(candles) else None

        # Build indicator window: from start of candles up to and including current
        idx_in_full = len(candles) - len(window) + i
        indicator_window = candles[max(0, idx_in_full - 24):idx_in_full + 1]

        closes = np.array([c['close'] for c in indicator_window], dtype=float)
        highs = np.array([c['high'] for c in indicator_window], dtype=float)
        lows = np.array([c['low'] for c in indicator_window], dtype=float)
        volumes = np.array([c['volume'] for c in indicator_window], dtype=float)

        atr_20 = _compute_atr(highs, lows, closes, 14)
        volume_ma_20 = float(np.mean(volumes[-20:])) if len(volumes) >= 20 else float(np.mean(volumes))
        ema_20 = _compute_ema(closes, 20)
        ema_50 = _compute_ema(closes, 50)
        ou_theta = _estimate_ou_theta(closes)
        rsi_14 = _compute_rsi(closes, 14)
        bb_upper, bb_lower = _compute_bollinger(closes, 20, 2.0)
        candle_low = float(candle['low'])
        candle_high = float(candle['high'])
        swing_low = float(np.min(lows[:-1])) if len(lows) > 1 else candle_low
        swing_high = float(np.max(highs[:-1])) if len(highs) > 1 else candle_high

        btc_ret = 0.0
        if btc_hourly_returns and idx_in_full < len(btc_hourly_returns):
            btc_ret = float(btc_hourly_returns[idx_in_full])

        tokens = tokenize_candle(
            candle=candle,
            prev_candle=prev,
            atr_20=atr_20,
            volume_ma_20=volume_ma_20,
            ema_20=ema_20,
            ema_50=ema_50,
            ou_theta=ou_theta,
            rsi_14=rsi_14,
            bb_upper=bb_upper,
            bb_lower=bb_lower,
            swing_low=swing_low,
            swing_high=swing_high,
            btc_1h_return=btc_ret,
        )
        sequence.append(tokens)

    return sequence


def tokens_to_ids(token_sequence: List[List[str]], max_tokens_per_candle: int = 5) -> np.ndarray:
    """Convert a token sequence into a fixed-size array of token IDs.

    Each candle's token list is padded/truncated to max_tokens_per_candle,
    with 0 used as a padding sentinel (no valid token has ID 0 in practice,
    but TOKEN_PAD = -1 is remapped to 0 below).

    Args:
        token_sequence: list of token lists per candle
        max_tokens_per_candle: pad/truncate each candle's tokens to this count

    Returns:
        numpy array of shape (window_size, max_tokens_per_candle)
    """
    if not token_sequence:
        return np.zeros((24, max_tokens_per_candle), dtype=int)

    result = np.zeros((len(token_sequence), max_tokens_per_candle), dtype=int)
    for i, tokens in enumerate(token_sequence):
        ids = [TOKEN_TO_ID.get(t, 0) for t in tokens[:max_tokens_per_candle]]
        for j, tid in enumerate(ids):
            result[i, j] = tid

    return result


def tokenize_ticker_to_ids(
    candles: List[dict],
    window_size: int = 24,
    btc_hourly_returns: Optional[List[float]] = None,
    max_tokens_per_candle: int = 5,
) -> np.ndarray:
    """Full pipeline: candles → token lists → padded ID matrix.

    Args:
        candles: OHLCV dicts oldest→newest
        window_size: candles in output sequence
        btc_hourly_returns: parallel BTC returns
        max_tokens_per_candle: padding limit per candle

    Returns:
        numpy array shape (window_size, max_tokens_per_candle) of int token IDs.
        Returns zeros if insufficient candle data.
    """
    if len(candles) < 10:
        return np.zeros((window_size, max_tokens_per_candle), dtype=int)
    seq = tokenize_ticker_window(candles, window_size, btc_hourly_returns)
    return tokens_to_ids(seq, max_tokens_per_candle)
