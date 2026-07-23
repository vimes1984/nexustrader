"""
FinBERT-style crypto sentiment analysis via local LLaMA server.
Uses the fine-tuned nexustrader-3B model (192.168.0.193:8080) for neural
sentiment scoring of crypto headlines. Zero additional dependencies required.
"""

import logging
import urllib.request
import json
from typing import Optional, Tuple

LLAMA_URL = "http://192.168.0.193:8080/completion"

# Structured prompt engineered for the fine-tuned nexustrader model
SENTIMENT_PROMPT_TEMPLATE = """[INST] Analyze the sentiment of this crypto market headline.

Headline: "{headline}"

Respond with ONLY a JSON object with these fields:
- score: float between -1.0 (extremely bearish) and 1.0 (extremely bullish)
- confidence: float between 0.0 and 1.0
- reasoning: brief 5-10 word explanation

Example: {{"score": 0.7, "confidence": 0.85, "reasoning": "Strong bullish momentum on ETF approval"}}
[/INST]"""


def finbert_sentiment_llama(headline: str, timeout: float = 8.0) -> Optional[Tuple[float, float]]:
    """Analyze a single headline via LLaMA for neural sentiment.

    Returns (score, confidence) where score ∈ [-1, 1], confidence ∈ [0, 1].
    Returns None on any failure (network, parse, etc.) so caller falls back gracefully.
    """
    try:
        prompt = SENTIMENT_PROMPT_TEMPLATE.format(headline=headline[:300])
        payload = json.dumps({
            "prompt": prompt,
            "temperature": 0.1,  # deterministic for scoring
            "max_tokens": 80,
            "stop": ["\n\n", "</s>"]
        }).encode("utf-8")

        req = urllib.request.Request(
            LLAMA_URL,
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body)
            content = data.get("content", "").strip()

        # Parse structured JSON from model output
        # The model may wrap in ```json blocks; extract the JSON
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()

        result = json.loads(content)
        score = float(result.get("score", 0))
        confidence = float(result.get("confidence", 0))
        reasoning = result.get("reasoning", "")

        # Clamp and validate
        score = max(-1.0, min(1.0, score))
        confidence = max(0.0, min(1.0, confidence))

        logging.debug(f"[FinBERT-LLaMA] \"{headline[:50]}...\" → score={score:.2f} conf={confidence:.2f} ({reasoning})")
        return (score, confidence)

    except urllib.error.URLError:
        logging.debug("[FinBERT-LLaMA] LLaMA server unreachable — falling back to lexical")
        return None
    except json.JSONDecodeError:
        logging.debug(f"[FinBERT-LLaMA] Failed to parse model output")
        return None
    except Exception as e:
        logging.warning(f"[FinBERT-LLaMA] Error: {e}")
        return None


def batch_sentiment_llama(headlines, max_headlines: int = 5, timeout: float = 30.0) -> dict:
    """Batch sentiment analysis of multiple headlines via LLaMA.

    Returns dict with:
      - aggregated_score: weighted mean score
      - individual: list of {headline, score, confidence}
      - sources_used: number of headlines analyzed
    """
    results = []
    total_score = 0.0
    total_weight = 0.0

    for headline in headlines[:max_headlines]:
        result = finbert_sentiment_llama(headline, timeout=min(timeout / max_headlines, 8.0))
        if result is not None:
            score, confidence = result
            results.append({
                "headline": headline[:100],
                "score": score,
                "confidence": confidence
            })
            total_score += score * confidence
            total_weight += confidence

    if total_weight > 0:
        aggregated = total_score / total_weight
    else:
        aggregated = 0.0

    return {
        "aggregated_score": round(aggregated, 4),
        "individual": results,
        "sources_used": len(results)
    }


def is_llama_available(timeout: float = 3.0) -> bool:
    """Quick health check — is the LLaMA server reachable?"""
    try:
        req = urllib.request.Request(
            "http://192.168.0.193:8080/health",
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


# ── Oxford Microstructure Studies Integration ──
# Key findings from Oxford-Man Institute's Realized Library and microstructure research:

OXFORD_MICROSTRUCTURE_RULES = {
    "volatility_clustering": {
        "description": "Volatility clusters in time (Mandelbrot 1963, Cont 2001). "
                       "High-vol periods tend to persist for 5-15 days in crypto.",
        "rule": "After a 2-std volatility spike, widen SL by 50% for next 24h.",
        "reference": "Cont, R. (2001). Empirical properties of asset returns. Quantitative Finance."
    },
    "volume_price_trend": {
        "description": "Volume precedes price. Large volume moves predict "
                       "subsequent price direction (Karpoff 1987, Oxford-Man VPT indicator).",
        "rule": "If volume > 1.5x 20-period average AND price moves +2%, confirm BUY signal confidence +25%.",
        "reference": "Karpoff, J. (1987). The relation between price changes and trading volume."
    },
    "bid_ask_bounce": {
        "description": "Transaction prices bounce between bid and ask, creating "
                       "negative first-order autocorrelation in returns (Roll 1984).",
        "rule": "For low-liquidity assets (<$10K daily vol), require signal > 1.5x threshold to filter bounce noise.",
        "reference": "Roll, R. (1984). A simple implicit measure of the effective bid-ask spread."
    },
    "momentum_reversal": {
        "description": "Short-term reversal (<1 day) + medium-term momentum (1-12 months) "
                       "is well-documented (Jegadeesh & Titman 1993, Oxford-Man RVaR).",
        "rule": "For hourly signals: if 1h return > 3 std, expect reversal (fade the move). "
               "For daily signals: follow the 20-day trend.",
        "reference": "Jegadeesh & Titman (1993). Returns to buying winners and selling losers."
    },
    "realized_variance_scaling": {
        "description": "Position sizing should scale inversely with realized variance "
                       "(Oxford-Man Realized Library methodology).",
        "rule": "position_size = base_size * (target_vol / realized_vol_20d). "
               "Cap at 2x. Floor at 0.5x.",
        "reference": "Shephard & Sheppard (2010). Realising the future: forecasting with high-frequency-based volatility."
    },
    "overnight_gap_risk": {
        "description": "Crypto trades 24/7 but weekend/overnight gaps in traditional "
                       "markets create Monday effects. For crypto, large weekend moves "
                       "often reverse by Tuesday UTC.",
        "rule": "Reduce position size by 25% entering weekends (Fri 20:00 UTC). "
               "Monday 06:00 UTC: restore normal sizing.",
        "reference": "French, K. (1980). Stock returns and the weekend effect."
    }
}


def apply_oxford_rules(ticker: str, signal_score: float, volume_ratio: float,
                       realized_vol: float, target_vol: float = 0.02,
                       is_weekend: bool = False) -> dict:
    """Apply Oxford microstructure rules to adjust a raw signal.

    Returns dict with adjusted_signal and per-rule adjustments for transparency.
    """
    adjustments = {}
    adjusted = signal_score

    # Rule 1: Volume confirmation (VPT)
    if volume_ratio > 1.5:
        boost = min(0.25, volume_ratio * 0.1)
        adjustments["volume_confirm"] = f"+{boost:.2f}"
        adjusted += boost * abs(signal_score)

    # Rule 2: Realized variance position scaling hint
    if realized_vol > 0:
        vol_ratio = target_vol / max(realized_vol, 0.005)
        vol_scale = max(0.5, min(2.0, vol_ratio))
        adjustments["vol_scaling"] = f"{vol_scale:.2f}x position"

    # Rule 3: Weekend gap risk
    if is_weekend:
        adjustments["weekend_trim"] = "-25% position"

    # Rule 4: Bid-ask bounce filter (low liquidity)
    # Applied in execution engine; flag here for consumer

    return {
        "adjusted_signal": round(adjusted, 4),
        "original_signal": signal_score,
        "adjustments": adjustments
    }
