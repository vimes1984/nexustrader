"""
llm_client.py — LLaMA integration for NexusTrader

Queries a local llama.cpp server (OpenAI-compatible API) for three roles:
  1. Sentiment & Macro Analysis — market headlines → sentiment score
  2. Regime Detection — current conditions → regime classification
  3. Trade Explanation — entry context → natural language reasoning

Architecture:
  Bot VM (192.168.0.144) → HTTP → llama-server (192.168.0.77:8080)

Reuses the same HTTP patterns as openclaw_bridge.py — single retry,
5s timeout, structured JSON responses.
"""

import json
import urllib.request
import urllib.error
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_ENDPOINT = "http://192.168.0.77:8080"
DEFAULT_TIMEOUT = 15  # seconds — Llama 3B on CPU needs ~10-15s per query
DEFAULT_MAX_TOKENS = 120
SYSTEM_PROMPT = (
    "You are a professional crypto trading analyst embedded in an automated "
    "trading system. Provide concise, data-driven analysis. Always respond "
    "with valid JSON unless instructed otherwise. No markdown, no fluff."
)


class LLMClient:
    """Thin HTTP client for llama.cpp server (OpenAI-compatible /v1/completions)."""

    def __init__(
        self,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = 1,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    # ------------------------------------------------------------------
    # Low-level completion call
    # ------------------------------------------------------------------

    def _complete(
        self,
        prompt: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = 0.7,
        stop: Optional[list[str]] = None,
    ) -> str:
        """Send a prompt to the llama server, return the generated text."""
        if stop is None:
            stop = ["<|user|>", "<|system|>", "\n\n\n"]

        payload = json.dumps({
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stop": stop,
        }).encode("utf-8")

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                req = urllib.request.Request(
                    f"{self.endpoint}/v1/completions",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    return body["choices"][0]["text"].strip()
            except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
                    KeyError, OSError) as e:
                last_error = e
                if attempt < self.max_retries:
                    logger.warning(f"LLM call failed (attempt {attempt+1}): {e}")
                    time.sleep(2)

        raise RuntimeError(f"LLM call failed after {self.max_retries+1} attempts: {last_error}")

    def _complete_json(self, prompt: str, max_tokens: int = 150) -> dict:
        """Complete and parse as JSON, with fallback stripping."""
        raw = self._complete(prompt, max_tokens=max_tokens, temperature=0.5)
        # Try to extract JSON from the response (model may add commentary)
        for attempt in [raw, raw[raw.find("{"):raw.rfind("}")+1] if "{" in raw else ""]:
            try:
                return json.loads(attempt)
            except json.JSONDecodeError:
                continue
        # Fallback: return raw text as a key
        logger.warning(f"Could not parse JSON from LLM response: {raw[:200]}")
        return {"raw_response": raw, "parse_error": True}

    # ------------------------------------------------------------------
    # Role 1: Sentiment & Macro Analysis
    # ------------------------------------------------------------------

    def analyze_sentiment(self, headlines: list[str], market_summary: str = "") -> dict:
        """Analyze crypto market sentiment from news headlines.

        Args:
            headlines: List of recent crypto news headlines
            market_summary: Optional — BTC price, ETH price, 24h change, volume info

        Returns:
            {
                "sentiment_score": float,   # -1.0 (bearish) to +1.0 (bullish)
                "conviction": float,         # 0.0 to 1.0
                "direction": str,            # "bullish" | "bearish" | "neutral"
                "key_themes": [str],         # Top 2-3 themes driving sentiment
                "risk_factors": [str],       # Things to watch
                "recommended_action": str,   # "increase" | "hold" | "reduce"
            }
        """
        headlines_text = "\n".join(f"- {h}" for h in headlines[:10])
        market_text = market_summary or "No current market data provided."

        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"<|user|>\n"
            f"Analyze crypto market sentiment from these headlines:\n\n"
            f"{headlines_text}\n\n"
            f"Market context: {market_text}\n\n"
            f"Return ONLY valid JSON (no markdown, no explanation outside the JSON):\n"
            f'{{"sentiment_score": <float -1.0 to 1.0>, '
            f'"conviction": <float 0.0 to 1.0>, '
            f'"direction": "<bullish|bearish|neutral>", '
            f'"key_themes": ["<theme1>", "<theme2>", ...], '
            f'"risk_factors": ["<risk1>", ...], '
            f'"recommended_action": "<increase|hold|reduce>"}}\n'
            f"<|assistant|>\n"
        )

        return self._complete_json(prompt, max_tokens=200)

    # ------------------------------------------------------------------
    # Role 2: Regime Detection
    # ------------------------------------------------------------------

    def classify_regime(self, ticker_data: dict) -> dict:
        """Detect the current market regime for a ticker.

        Args:
            ticker_data: {
                "symbol": str,
                "price": float,
                "change_24h_pct": float,
                "atr_14": float,
                "rsi_14": float,
                "volume_vs_ma": float,        # ratio vs 20-period volume MA
                "btc_correlation": float,      # -1 to 1
                "signal_summary": str,         # recent signal direction/strength
            }

        Returns:
            {
                "regime": str,       # "TRENDING_UP" | "TRENDING_DOWN" | "RANGING" |
                                     #  "HIGH_VOL_BREAKOUT" | "HIGH_VOL_BREAKDOWN" |
                                     #  "LOW_VOL_DRIFT"
                "confidence": float,  # 0.0 to 1.0
                "risk_level": str,    # "low" | "medium" | "high" | "extreme"
                "position_multiplier": float,  # 0.0 to 1.0 (suggested sizing)
                "reasoning": str,     # One sentence
            }
        """
        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"<|user|>\n"
            f"Classify the current market regime for {ticker_data.get('symbol', 'unknown')}:\n\n"
            f"Price: \${ticker_data.get('price', 'N/A')}\n"
            f"24h Change: {ticker_data.get('change_24h_pct', 'N/A')}%\n"
            f"ATR(14): {ticker_data.get('atr_14', 'N/A')}\n"
            f"RSI(14): {ticker_data.get('rsi_14', 'N/A')}\n"
            f"Volume vs 20-MA: {ticker_data.get('volume_vs_ma', 'N/A')}x\n"
            f"BTC Correlation: {ticker_data.get('btc_correlation', 'N/A')}\n"
            f"Recent Signals: {ticker_data.get('signal_summary', 'N/A')}\n\n"
            f"Return ONLY valid JSON:\n"
            f'{{"regime": "<TRENDING_UP|TRENDING_DOWN|RANGING|'
            f'HIGH_VOL_BREAKOUT|HIGH_VOL_BREAKDOWN|LOW_VOL_DRIFT>", '
            f'"confidence": <float 0.0-1.0>, '
            f'"risk_level": "<low|medium|high|extreme>", '
            f'"position_multiplier": <float 0.0-1.0>, '
            f'"reasoning": "<one sentence>"}}\n'
            f"<|assistant|>\n"
        )

        return self._complete_json(prompt, max_tokens=150)

    # ------------------------------------------------------------------
    # Role 3: Trade Explanation
    # ------------------------------------------------------------------

    def explain_trade(self, trade_context: dict) -> str:
        """Generate a natural-language explanation for a trade entry.

        Args:
            trade_context: {
                "symbol": str,
                "direction": str,           # "LONG" | "SHORT"
                "entry_price": float,
                "signal_strength": float,   # -1 to 1
                "top_strategies": [str],    # Top 3 strategies that fired
                "regime": str,              # Current regime classification
                "attention_focus": str,     # Which candles/patterns mattered
                "market_overview": str,     # Brief market context
            }

        Returns:
            Natural language explanation string (2-3 sentences)
        """
        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"<|user|>\n"
            f"Explain this trade entry to a trader in 2-3 concise sentences:\n\n"
            f"Symbol: {trade_context.get('symbol', 'unknown')}\n"
            f"Direction: {trade_context.get('direction', 'unknown')}\n"
            f"Entry Price: \${trade_context.get('entry_price', 'N/A')}\n"
            f"Signal Strength: {trade_context.get('signal_strength', 'N/A')}\n"
            f"Top Strategies: {', '.join(trade_context.get('top_strategies', ['N/A']))}\n"
            f"Market Regime: {trade_context.get('regime', 'unknown')}\n"
            f"Key Patterns: {trade_context.get('attention_focus', 'N/A')}\n"
            f"Market Context: {trade_context.get('market_overview', 'N/A')}\n\n"
            f"Be specific about what drove this decision. Mention risks if any.\n"
            f"<|assistant|>\n"
        )

        return self._complete(prompt, max_tokens=120, temperature=0.5)

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self) -> dict:
        """Check if the llama server is reachable and responding."""
        try:
            req = urllib.request.Request(f"{self.endpoint}/health")
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                return {"ok": True, "status": body.get("status", "unknown"), "endpoint": self.endpoint}
        except Exception as e:
            return {"ok": False, "error": str(e), "endpoint": self.endpoint}


# ---------------------------------------------------------------------------
# Convenience: same interface as openclaw_bridge
# ---------------------------------------------------------------------------

_llm_client: Optional[LLMClient] = None


def get_llm_client(endpoint: str = DEFAULT_ENDPOINT) -> LLMClient:
    """Get or create the singleton LLM client."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient(endpoint=endpoint)
    return _llm_client


def query_llm(prompt: str, max_tokens: int = 120) -> str:
    """Simple raw query — same call signature as query_openclaw()."""
    return get_llm_client()._complete(prompt, max_tokens=max_tokens)
