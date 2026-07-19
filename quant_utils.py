import numpy as np
import pandas as pd
import logging

class KalmanFilterPrice:
    """1D Kalman Filter to track true price trend by filtering market noise."""
    def __init__(self, process_variance=1e-4, measurement_variance=1e-2):
        self.Q = process_variance  # Process noise covariance
        self.R = measurement_variance  # Measurement noise covariance
        self.x = None  # Estimated price (state estimate)
        self.P = 1.0   # Estimation error covariance

    def update(self, measurement):
        if self.x is None:
            self.x = measurement
            return self.x

        # 1. Predict state and error covariance
        x_pred = self.x
        P_pred = self.P + self.Q

        # 2. Update (Correction)
        kalman_gain = P_pred / (P_pred + self.R)
        self.x = x_pred + kalman_gain * (measurement - x_pred)
        self.P = (1 - kalman_gain) * P_pred

        return float(self.x)

def estimate_ou_process(prices, dt=1.0):
    """Fits prices to the Ornstein-Uhlenbeck process:
    dx_t = theta * (mu - x_t) * dt + sigma * dW_t
    
    Using Ordinary Least Squares (OLS) discretization:
    x_t = a * x_{t-1} + b + e
    
    Returns:
    - theta: rate of mean reversion (speed)
    - mu: long-term mean price
    - is_mean_reverting: Boolean indicating if theta > 0
    """
    if len(prices) < 20:
        return 0.0, float(np.mean(prices)), False

    x = np.array(prices[:-1])
    y = np.array(prices[1:])

    # Perform OLS regression: y = a * x + b
    A = np.vstack([x, np.ones(len(x))]).T
    a, b = np.linalg.lstsq(A, y, rcond=None)[0]

    # Handle boundary conditions
    if a <= 0 or a >= 1:
        # Not mean-reverting (either trending or unstable)
        return 0.0, float(np.mean(prices)), False

    theta = -np.log(a) / dt
    mu = b / (1.0 - a)

    return float(theta), float(mu), True

def detect_psychological_sweep(df, lookback=24, round_number_base=5.0):
    """Detects retail liquidity sweeps (stop hunts) and round-number psychological traps.
    
    - Retail traders tend to place stops just below swing lows/highs or at round numbers.
    - A sweep occurs when price pierces a local support/resistance level, triggering stops,
      and then immediately closes back within the key level.
    """
    if len(df) < lookback + 1:
        return 0.0

    # Get local swing high and low (excluding the current bar)
    recent_highs = df['high'].iloc[-lookback:-1].values
    recent_lows = df['low'].iloc[-lookback:-1].values
    
    local_resistance = np.max(recent_highs)
    local_support = np.min(recent_lows)

    current_close = float(df['close'].iloc[-1])
    current_low = float(df['low'].iloc[-1])
    current_high = float(df['high'].iloc[-1])
    current_open = float(df['open'].iloc[-1])

    # Detect Support Sweep (Stop Hunt on Buyers)
    # Price dropped below support (triggering stop-loss selling), but closed back above
    is_support_sweep = (current_low < local_support) and (current_close > local_support)
    
    # Detect Resistance Sweep (Stop Hunt on Sellers)
    # Price rose above resistance (triggering stop-loss buying/short-covers), but closed back below
    is_resistance_sweep = (current_high > local_resistance) and (current_close < local_resistance)

    # Round number psychological alignment
    # Check if support/resistance is close to a psychological boundary (e.g. multiples of €5, €10, €100)
    round_support = round(local_support / round_number_base) * round_number_base
    is_near_round_support = abs(local_support - round_support) / local_support < 0.005 # within 0.5%

    if is_support_sweep:
        # Strong psychological reversal signal (Buy)
        # Score boosted if support lies on a round number
        return 1.5 if is_near_round_support else 1.0
    elif is_resistance_sweep:
        # Strong psychological reversal signal (Sell)
        return -1.5 if is_near_round_support else -1.0

    return 0.0

def query_gemini_robust(api_key: str, prompt, model: str = "gemini-flash-latest", max_retries: int = 5, backoff_factor: float = 2.0) -> str:
    """Queries configured LLM Provider (Gemini, OpenAI, Anthropic, OpenClaw) with backoff on transient errors."""
    import urllib.request
    import urllib.error
    import json
    import time
    import logging
    import os
    import sqlite3
    
    # 1. Identify which agent is executing by walking up the call stack
    agent = "default"
    try:
        import inspect
        for frame_info in inspect.stack():
            filename = os.path.basename(frame_info.filename)
            if filename in ["self_improvement_agent.py", "weekly_optimizer.py"]:
                agent = "quant"
                break
            elif filename == "agent_self_developer.py":
                agent = "dev"
                break
            elif filename in ["sentiment_agent.py", "sentiment_analyzer.py"]:
                agent = "sentiment"
                break
            elif filename == "nn_agent.py":
                agent = "nn"
                break
            elif filename == "risk_auditor.py":
                agent = "risk"
                break
            elif filename in ["blog_agent.py", "daily_reporter.py"]:
                agent = "reporter"
                break
    except Exception:
        pass

    # 2. Load config settings from database with per-agent overrides
    db_path = os.path.expanduser("~/.nexustrader/nexustrader.db")
    provider = "gemini"
    config_model = ""
    api_key_override = ""
    base_url = ""
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        c.execute("SELECT key, value FROM settings")
        rows = c.fetchall()
        conn.close()
        settings = {r[0]: r[1] for r in rows}
        
        # Check agent-specific settings first, then fallback to global defaults
        suffix = f"_{agent}" if agent != "default" else ""
        
        provider = settings.get(f"agent_llm_provider{suffix}", "")
        if not provider and agent != "default":
            provider = settings.get("agent_llm_provider", "gemini")
        elif not provider:
            provider = "gemini"
        provider = provider.lower()
            
        base_url = settings.get(f"agent_llm_base_url{suffix}", "")
        if not base_url and agent != "default":
            base_url = settings.get("agent_llm_base_url", "")
            
        config_model = settings.get(f"agent_llm_model{suffix}", "")
        if not config_model and agent != "default":
            config_model = settings.get("agent_llm_model", "")
            
        api_key_override = settings.get(f"agent_llm_api_key{suffix}", "")
        if not api_key_override and agent != "default":
            api_key_override = settings.get("agent_llm_api_key", "")
    except Exception:
        pass
        
    # Overwrite if database overrides exist
    if api_key_override:
        api_key = api_key_override
    use_model = config_model if config_model else model
    
    # 2. Convert Gemini structure dict prompt to flat string if needed
    flat_prompt = ""
    if isinstance(prompt, dict):
        if "contents" in prompt:
            parts = []
            for c in prompt["contents"]:
                if "parts" in c:
                    for p in c["parts"]:
                        if "text" in p:
                            parts.append(p["text"])
            flat_prompt = "\n".join(parts)
        else:
            flat_prompt = json.dumps(prompt)
    else:
        flat_prompt = str(prompt)
        
    # 3. Build target URL, payload, headers depending on provider
    if provider == "gemini":
        use_proxy = False
        try:
            req_health = urllib.request.Request("http://127.0.0.1:8001/health")
            with urllib.request.urlopen(req_health, timeout=1.0) as resp:
                data_health = json.loads(resp.read().decode("utf-8"))
                if data_health.get("status") == "ok":
                    use_proxy = True
        except Exception:
            pass

        if use_proxy:
            url = f"http://127.0.0.1:8001/v1beta/models/{use_model}:generateContent"
            logging.info("[PROXY ROUTE] Routing request through local Antigravity proxy on 127.0.0.1:8001")
        else:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{use_model}:generateContent?key={api_key}"
            
        payload = prompt if isinstance(prompt, dict) else {"contents": [{"parts": [{"text": flat_prompt}]}]}
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["x-goog-api-key"] = api_key
            
    elif provider in ["openai", "openclaw"]:
        url = base_url if base_url else "https://api.openai.com/v1/chat/completions"
        if url and not url.endswith("/chat/completions"):
            url = url.rstrip("/") + "/chat/completions"
            
        if not use_model or use_model in ["gemini-2.0-flash", "gemini-flash-latest"]:
            use_model = "gpt-4o"
        payload = {
            "model": use_model,
            "messages": [{"role": "user", "content": flat_prompt}],
            "temperature": 0.2
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
    elif provider == "anthropic":
        url = base_url if base_url else "https://api.anthropic.com/v1/messages"
        if url and not url.endswith("/messages"):
            url = url.rstrip("/") + "/messages"
            
        if not use_model or use_model in ["gemini-2.0-flash", "gemini-flash-latest"]:
            use_model = "claude-3-5-sonnet-20241022"
        payload = {
            "model": use_model,
            "messages": [{"role": "user", "content": flat_prompt}],
            "max_tokens": 4096,
            "temperature": 0.2
        }
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        }
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")
        
    encoded_data = json.dumps(payload).encode("utf-8")
    retries = 0
    delay = 2.0
    
    while True:
        try:
            req = urllib.request.Request(url, data=encoded_data, headers=headers)
            with urllib.request.urlopen(req, timeout=45) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))
                if provider == "gemini":
                    return res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
                elif provider in ["openai", "openclaw"]:
                    return res_json["choices"][0]["message"]["content"].strip()
                elif provider == "anthropic":
                    return res_json["content"][0]["text"].strip()
        except urllib.error.HTTPError as e:
            if e.code in [429, 500, 502, 503, 504] and retries < max_retries:
                logging.warning(f"[{provider.upper()} API] Transient HTTP error ({e.code}) hit. Retrying in {delay:.1f}s... (Attempt {retries+1}/{max_retries})")
                time.sleep(delay)
                retries += 1
                delay *= backoff_factor
            else:
                try:
                    err_body = e.read().decode("utf-8")
                    logging.error(f"[{provider.upper()} API] HTTP Error {e.code}: {e.reason} - Body: {err_body}")
                    e.reason = f"{e.reason} - {err_body}"
                except Exception:
                    logging.error(f"[{provider.upper()} API] HTTP Error {e.code}: {e.reason}")
                raise e
        except (urllib.error.URLError, ConnectionResetError, BrokenPipeError, TimeoutError) as e:
            if retries < max_retries:
                logging.warning(f"[{provider.upper()} API] Transient Network error ({e}) hit. Retrying in {delay:.1f}s... (Attempt {retries+1}/{max_retries})")
                time.sleep(delay)
                retries += 1
                delay *= backoff_factor
            else:
                logging.error(f"[{provider.upper()} API] Network Error: {e}")
                raise e
        except Exception as e:
            logging.error(f"[{provider.upper()} API] Unexpected error: {e}")
            raise e
