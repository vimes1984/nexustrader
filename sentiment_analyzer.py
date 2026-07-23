import urllib.request
import xml.etree.ElementTree as ET
import logging
import re
import os
import json
import database
from typing import Optional, Tuple

# ── FinBERT integration (optional) ──
# When available, uses FinBERT (ProsusAI/finbert) for neural sentiment analysis.
# Falls back gracefully to lexical if transformers/torch are not installed.
_FINBERT_AVAILABLE = False
try:
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    _FINBERT_TOKENIZER = AutoTokenizer.from_pretrained("ProsusAI/finbert")
    _FINBERT_MODEL = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
    _FINBERT_AVAILABLE = True
    logging.info("[FinBERT] Neural sentiment model loaded successfully.")
except ImportError:
    logging.info("[FinBERT] transformers/torch not available — using lexical sentiment only.")
except Exception as e:
    logging.warning(f"[FinBERT] Failed to load model: {e} — using lexical sentiment only.")


def finbert_sentiment(text: str) -> Optional[Tuple[float, float]]:
    """Analyze text sentiment using FinBERT.
    
    Returns (score, confidence) where score ∈ [-1, 1], confidence ∈ [0, 1].
    Returns None if FinBERT is unavailable.
    """
    if not _FINBERT_AVAILABLE:
        return None
    try:
        inputs = _FINBERT_TOKENIZER(text, return_tensors="pt", truncation=True, max_length=512)
        with torch.no_grad():
            outputs = _FINBERT_MODEL(**inputs)
        probs = torch.nn.functional.softmax(outputs.logits, dim=-1).squeeze()
        # FinBERT model outputs: [negative, neutral, positive] logits
        # (ProsusAI/finbert uses the original FinBERT label order)
        neg, neu, pos = probs[0].item(), probs[1].item(), probs[2].item()
        # Map to [-1, 1] score: positive - negative, weighted by confidence
        score = pos - neg
        confidence = 1.0 - neu  # higher confidence = less neutral
        return (score, confidence)
    except Exception as e:
        logging.debug(f"[FinBERT] Inference error: {e}")
        return None


# Lexicon for financial sentiment analysis fallback
FINANCIAL_LEXICON = {
    "surge": 0.8, "rally": 0.7, "gain": 0.5, "bullish": 0.8, "growth": 0.6,
    "profit": 0.5, "rise": 0.4, "outperform": 0.7, "acquire": 0.4, "expand": 0.5,
    "breakout": 0.6, "support": 0.3, "high": 0.3, "success": 0.5, "upgrade": 0.6,
    "bull": 0.6, "green": 0.4, "boost": 0.5, "pump": 0.7,
    "plunge": -0.8, "crash": -0.9, "bearish": -0.8, "drop": -0.4, "loss": -0.5,
    "deficit": -0.6, "warning": -0.5, "hack": -0.9, "lawsuit": -0.7, "fine": -0.6,
    "slump": -0.7, "decline": -0.4, "collapse": -0.9, "bankrupt": -1.0, "panic": -0.8,
    "investigation": -0.5, "downgrade": -0.6, "resistance": -0.3, "low": -0.3,
    "bear": -0.6, "red": -0.4, "dump": -0.8, "liquidate": -0.7, "fear": -0.5, "fud": -0.6
}

# Crypto news and social sentiment feeds mapping
FEED_MAP = {
    "cointelegraph": "https://cointelegraph.com/rss",
    "cryptobriefing": "https://cryptobriefing.com/feed/",
    "beincrypto": "https://beincrypto.com/feed/",
    "reddit": "https://www.reddit.com/r/CryptoCurrency/hot/.rss"
}

# Ticker keywords
TICKER_KEYWORDS = {
    "BTC": ["btc", "bitcoin"],
    "ETH": ["eth", "ethereum"],
    "SOL": ["sol", "solana"],
    "DOGE": ["doge", "dogecoin"],
    "XRP": ["xrp", "ripple"]
}

def analyze_text_sentiment(text):
    """Calculates a sentiment score between -1.0 and 1.0.
    
    Uses FinBERT neural model when available, blending lexical fallback
    weighted by FinBERT's non-neutral confidence.
    """
    # Compute lexical baseline first (always available)
    text_lower = text.lower()
    words = re.findall(r'\b\w+\b', text_lower)
    lex_score = 0.0
    lex_count = 0
    for w in words:
        if w in FINANCIAL_LEXICON:
            lex_score += FINANCIAL_LEXICON[w]
            lex_count += 1
    lexical = max(-1.0, min(1.0, lex_score / lex_count)) if lex_count > 0 else 0.0
    
    # Try FinBERT and blend with lexical
    finbert_result = finbert_sentiment(text)
    if finbert_result is not None:
        nn_score, nn_confidence = finbert_result
        # Blend: high confidence → FinBERT dominates; low confidence → lexical dominates
        # confidence ∈ [0, 1] is 1 - P(neutral), so 0=all neutral, 1=no neutral
        blend_weight = nn_confidence  # 0..1
        # Blend weight threshold: only use FinBERT if it adds value (>10% non-neutral)
        if blend_weight > 0.10:
            return lexical * (1 - blend_weight) + nn_score * blend_weight
    
    # Fallback: lexical only
    return lexical

def fetch_ticker_sentiment(ticker):
    """Fetches the latest RSS news and social posts, filters by coin keywords, and computes weighted sentiment."""
    query_ticker = ticker.split("-")[0]
    keywords = TICKER_KEYWORDS.get(query_ticker, [query_ticker.lower()])
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'}
    
    # Store raw scores per feed source
    raw_feed_scores = {source: [] for source in FEED_MAP.keys()}
    
    for source, feed_url in FEED_MAP.items():
        try:
            req = urllib.request.Request(feed_url, headers=headers)
            with urllib.request.urlopen(req, timeout=4) as response:
                xml_data = response.read()
            
            root = ET.fromstring(xml_data)
            
            for element in root.iter():
                tag_local = element.tag.split("}")[-1]
                if tag_local in ["item", "entry"]:
                    title_text = ""
                    desc_text = ""
                    for child in element:
                        child_local = child.tag.split("}")[-1]
                        if child_local == "title" and child.text:
                            title_text = child.text
                        elif child_local in ["description", "content", "summary"] and child.text:
                            desc_text = child.text
                    
                    full_text = f"{title_text} {desc_text}"
                    if full_text.strip():
                        full_text_lower = full_text.lower()
                        if any(kw in full_text_lower for kw in keywords):
                            sentiment = analyze_text_sentiment(full_text)
                            raw_feed_scores[source].append(sentiment)
        except Exception as e:
            logging.debug(f"Error fetching/parsing {source}: {e}")
            continue

    # 1. Compute average score per feed source (if no matches, default to 0.0)
    source_averages = {}
    for source, scores in raw_feed_scores.items():
        if scores:
            source_averages[source] = float(sum(scores) / len(scores))
        else:
            source_averages[source] = 0.0
            
    # 2. Load feed weights from database and calculate weighted average
    weighted_sum = 0.0
    weight_total = 0.0
    
    # We only include feeds that had active matches to avoid diluting the score
    active_sources = {s: av for s, av in source_averages.items() if len(raw_feed_scores[s]) > 0}
    
    for source, avg_score in active_sources.items():
        # Load weights from SQLite setting
        weight_str = database.load_setting(f"feed_weight_{source}", "1.0")
        try:
            weight = float(weight_str)
        except ValueError:
            weight = 1.0
            
        weighted_sum += avg_score * weight
        weight_total += weight
        
    final_score = 0.0
    if weight_total > 0:
        final_score = weighted_sum / weight_total
        logging.info(f"[SENTIMENT] Ticker: {ticker} | Weighted Score: {final_score:+.4f} (Active feeds: {list(active_sources.keys())})")
    else:
        logging.info(f"[SENTIMENT] Ticker: {ticker} | No active feeds matched. Defaulting to neutral (0.0000)")
        
    return final_score, source_averages
