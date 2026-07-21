"""Bridge: routes agent LLM queries through OpenClaw Gateway API or local LLaMA.

Replaces direct Gemini/OpenAI/Anthropic calls in quant agent files.
All agents call query_auto() (or query_openclaw() / query_llama() directly).
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

# OpenClaw Gateway defaults (LAN).
DEFAULT_GATEWAY_URL = "http://192.168.0.197:18789/v1/chat/completions"
DEFAULT_GATEWAY_TOKEN = "c49d2de941b0ec6a93e2fd89bf293ee8cd9f8e805cdda2d6"

# Local LLaMA server defaults (llama.cpp OpenAI-compatible API on LAN)
DEFAULT_LLAMA_URL = "http://192.168.0.77:8080/v1/chat/completions"
DEFAULT_LLAMA_TOKEN = ""  # no auth needed on LAN

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


def _do_http_request(url, headers, body, timeout_sec, display, attempt, max_retries):
    """Core HTTP request with retry logic. Returns (text, ok)."""
    for retry in range(max_retries):
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            resp = urllib.request.urlopen(req, timeout=timeout_sec)
            data = json.loads(resp.read().decode("utf-8"))
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not text:
                text = data.get("content", "")
            if not text and isinstance(data, list) and data:
                text = data[0].get("message", {}).get("content", "")
            if text:
                return text, True
            raise ValueError("Empty response")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")[:500]
            logger.warning(f"[LLMBridge] HTTP {e.code} for {display}: {err_body}")
            if retry < max_retries - 1:
                time.sleep(2 ** retry)
        except urllib.error.URLError as e:
            logger.warning(f"[LLMBridge] Connection error for {display}: {e.reason}")
            if retry < max_retries - 1:
                time.sleep(2 ** retry)
        except Exception as e:
            logger.warning(f"[LLMBridge] Error for {display}: {e}")
            if retry < max_retries - 1:
                time.sleep(2 ** retry)
    return None, False


# ═══════════════════════════════════════════════════════════════
#  QUERY FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def query_openclaw(
    prompt,
    agent_name="default",
    model="openclaw",
    max_tokens=2048,
    max_retries=3,
    temperature=0.7,
    system_prompt=None,
):
    """Send a prompt to the OpenClaw Gateway API and return the response text."""
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

    text, ok = _do_http_request(url, headers, body, 30, display, 0, max_retries)
    if ok:
        logger.info(f"[OpenClawBridge] {display} response OK ({len(text)} chars)")
        return text
    return f"[OpenClawBridge ERROR] Failed after {max_retries} retries for {display}"


def query_llama(
    prompt,
    agent_name="default",
    max_tokens=2048,
    max_retries=3,
    temperature=0.7,
    system_prompt=None,
):
    """Send a prompt to the LOCAL LLaMA server on chris-System (192.168.0.77:8080).

    Uses llama.cpp's OpenAI-compatible /v1/chat/completions endpoint.
    Falls back to OpenClaw Gateway if local LLaMA is unreachable and fallback enabled.
    """
    url = _load_db_setting("llama_server_url", "") or DEFAULT_LLAMA_URL
    token = _load_db_setting("llama_server_token", "") or DEFAULT_LLAMA_TOKEN
    fallback = _load_db_setting("llama_fallback_to_openclaw", "true").lower() == "true"
    display = AGENT_NAMES.get(agent_name, agent_name)

    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    body = json.dumps(payload).encode("utf-8")

    text, ok = _do_http_request(url, headers, body, 60, display, 0, max_retries)
    if ok:
        logger.info(f"[LlamaBridge] {display} response OK ({len(text)} chars)")
        return text

    # Fallback to OpenClaw Gateway
    if fallback:
        logger.info(f"[LlamaBridge] Falling back to OpenClaw Gateway for {display}")
        return query_openclaw(
            prompt, agent_name=agent_name, max_tokens=max_tokens,
            temperature=temperature, system_prompt=system_prompt,
        )

    return f"[LlamaBridge ERROR] Failed after {max_retries} retries for {display}"


def query_auto(
    prompt,
    agent_name="default",
    max_tokens=2048,
    max_retries=3,
    temperature=0.7,
    system_prompt=None,
):
    """Auto-route: uses local LLaMA if DB setting enable_local_llama=true, else OpenClaw Gateway.

    This is the recommended entry point for all Quant Team agents.
    Set DB setting 'enable_local_llama' to 'true' to use your LAN LLaMA server.

    If RAG is enabled (DB setting 'enable_rag' = 'true'), relevant trading context
    is automatically injected from the vector store into the prompt.
    """
    use_local = _load_db_setting("enable_local_llama", "false").lower() == "true"

    # Inject RAG context if enabled
    use_rag = _load_db_setting("enable_rag", "true").lower() == "true"
    if use_rag:
        try:
            from rag_pipeline import rag_query
            rag_ctx = rag_query(prompt, top_k=5)
            if rag_ctx:
                prompt = rag_ctx + "\n\n---\n\n" + prompt
        except Exception as e:
            logger.debug(f"RAG injection skipped: {e}")

    if use_local:
        return query_llama(prompt, agent_name=agent_name, max_tokens=max_tokens,
                           max_retries=max_retries, temperature=temperature,
                           system_prompt=system_prompt)
    else:
        return query_openclaw(prompt, agent_name=agent_name, max_tokens=max_tokens,
                              max_retries=max_retries, temperature=temperature,
                              system_prompt=system_prompt)


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
