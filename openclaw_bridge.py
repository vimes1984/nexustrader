"""Bridge: routes agent LLM queries through the OpenClaw Gateway API.

Replaces direct Gemini/OpenAI/Anthropic calls in quant agent files.
All agents call this instead of query_gemini_robust().
Handles auth, HTTP errors, backoff, and JSON parsing.
"""
import json
import time
import logging
import os
import sqlite3 as _sqlite3
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

# Default OpenClaw Gateway endpoint (LAN). Override via DB setting 'openclaw_gateway_url'.
DEFAULT_GATEWAY_URL = "http://192.168.0.197:18789/api/chat/completions"
DEFAULT_GATEWAY_TOKEN = "c49d2de941b0ec6a93e2fd89bf293ee8cd9f8e805cdda2d6"

# Agent name -> display string (mirrors agent_map in quant_utils.py)
AGENT_NAMES = {
    "quant": "Parameter Optimizer Agent",
    "nn": "Network Optimizer Agent",
    "sentiment": "Sentiment Feeds Agent",
    "risk": "Risk Check Agent",
    "allocator": "Allocation Check Agent",
    "dev": "Developer Agent",
    "reporter": "Reporter Agent",
    "default": "System Agent",
}

_DB_PATH = os.path.expanduser("~/.nexustrader/nexustrader.db")


def _load_db_setting(key, default=""):
    """Read a setting from the NexusTrader DB."""
    try:
        conn = _sqlite3.connect(_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else default
    except Exception:
        return default


def _save_db_setting(key, value):
    """Write a setting to the NexusTrader DB."""
    try:
        conn = _sqlite3.connect(_DB_PATH)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Could not save setting {key}: {e}")


def get_gateway_config():
    """Return (url, token) from DB or defaults."""
    url = _load_db_setting("openclaw_gateway_url", "")
    token = _load_db_setting("openclaw_gateway_token", "")
    if not url:
        url = DEFAULT_GATEWAY_URL
        _save_db_setting("openclaw_gateway_url", url)
    if not token:
        token = DEFAULT_GATEWAY_TOKEN
        _save_db_setting("openclaw_gateway_token", token)
    return url, token


def query_openclaw(
    prompt,
    agent_name="default",
    model="deepseek/deepseek-v4-flash",
    max_tokens=2048,
    max_retries=3,
    temperature=0.7,
    system_prompt=None,
):
    """Send a prompt to the OpenClaw Gateway API and return the response text.

    Args:
        prompt: The prompt string to send.
        agent_name: Logical agent name for logging (e.g. 'quant', 'nn').
        model: Model identifier (default: deepseek-flash).
        max_tokens: Max response tokens.
        max_retries: Number of retries on failure.
        temperature: Model temperature.
        system_prompt: Optional system-level instruction prepended as a system message.

    Returns:
        Response text string, or error message string on failure.
    """
    url, token = get_gateway_config()
    display = AGENT_NAMES.get(agent_name, agent_name)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    body = json.dumps(payload).encode("utf-8")

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            resp = urllib.request.urlopen(req, timeout=30)
            data = json.loads(resp.read().decode("utf-8"))
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not text:
                text = data.get("content", "")
            logger.info(f"[OpenClawBridge] {display} response OK ({len(text)} chars)")
            return text

        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")[:500]
            logger.warning(f"[OpenClawBridge] HTTP {e.code} for {display}: {err_body}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

        except urllib.error.URLError as e:
            logger.warning(f"[OpenClawBridge] Connection error for {display}: {e.reason}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

        except Exception as e:
            logger.error(f"[OpenClawBridge] Unexpected error for {display}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

    return f"[OpenClawBridge ERROR] Failed after {max_retries} retries for {display}"


def extract_json_block(text):
    """Extract first ```json ... ``` block from LLM response. Returns dict or None."""
    import re
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    return None
