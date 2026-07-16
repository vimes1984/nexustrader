import urllib.request
import xml.etree.ElementTree as ET
import logging
import re
import os
import json

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

# Crypto news and social sentiment feeds
RSS_FEEDS = [
    "https://cointelegraph.com/rss",
    "https://cryptobriefing.com/feed/",
    "https://beincrypto.com/feed/",
    "https://www.reddit.com/r/CryptoCurrency/hot/.rss"
]

# Ticker keywords
TICKER_KEYWORDS = {
    "BTC": ["btc", "bitcoin"],
    "ETH": ["eth", "ethereum"],
    "SOL": ["sol", "solana"],
    "DOGE": ["doge", "dogecoin"],
    "XRP": ["xrp", "ripple"]
}

def analyze_text_sentiment(text):
    """Calculates a sentiment score between -1.0 and 1.0 based on lexical matching."""
    text = text.lower()
    score = 0.0
    words = re.findall(r'\b\w+\b', text)
    count = 0
    for w in words:
        if w in FINANCIAL_LEXICON:
            score += FINANCIAL_LEXICON[w]
            count += 1
    if count > 0:
        return max(-1.0, min(1.0, score / count))
    return 0.0

def fetch_ticker_sentiment(ticker):
    """Fetches the latest RSS news and social posts, filters for ticker keywords, and aggregates sentiment."""
    query_ticker = ticker.split("-")[0]
    keywords = TICKER_KEYWORDS.get(query_ticker, [query_ticker.lower()])
    
    scores = []
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'}
    
    for feed_url in RSS_FEEDS:
        try:
            req = urllib.request.Request(feed_url, headers=headers)
            with urllib.request.urlopen(req, timeout=4) as response:
                xml_data = response.read()
            
            root = ET.fromstring(xml_data)
            
            # Walk XML tree and find feed entries (handles both standard RSS <item> and Atom <entry>)
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
                        # Filter for ticker-specific news or posts
                        full_text_lower = full_text.lower()
                        if any(kw in full_text_lower for kw in keywords):
                            scores.append(analyze_text_sentiment(full_text))
        except Exception as e:
            # Silence specific feed errors to continue to next feeds
            logging.debug(f"Feed error on {feed_url}: {e}")
            continue
            
    if scores:
        avg_score = float(sum(scores) / len(scores))
        logging.info(f"[SENTIMENT] Ticker: {ticker} | Matches: {len(scores)} | Avg Score: {avg_score:+.4f}")
        return avg_score
        
    logging.info(f"[SENTIMENT] Ticker: {ticker} | No ticker-specific articles found. Defaulting to neutral (0.0000)")
    return 0.0
