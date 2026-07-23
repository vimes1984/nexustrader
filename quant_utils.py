import numpy as np
import pandas as pd
import logging

class KalmanFilterPrice:
    """1D Kalman Filter to track true price trend by filtering market noise.
    
    Includes outlier rejection: measurements deviating > 5 * sqrt(P+R) from the
    prediction are treated as outliers and rejected outright.
    """
    def __init__(self, process_variance=1e-4, measurement_variance=1e-2,
                 outlier_threshold_sigma=5.0):
        self.Q = process_variance  # Process noise covariance
        self.R = measurement_variance  # Measurement noise covariance
        self.x = None  # Estimated price (state estimate)
        self.P = 1.0   # Estimation error covariance
        self.outlier_threshold = outlier_threshold_sigma  # Std-dev threshold for outlier rejection
        self._n_updates = 0  # Track for auto-reset after long outlier streak

    def _reset(self, measurement):
        """Reinitialize filter state with a measurement."""
        self.x = measurement
        self.P = 1.0
        self._n_updates = 0

    def update(self, measurement):
        # Guard against NaN or inf measurements
        if measurement is None or not np.isfinite(measurement):
            return float(self.x) if self.x is not None else 0.0
            
        if self.x is None:
            self._reset(measurement)
            return float(self.x)

        # 1. Predict state and error covariance
        x_pred = self.x
        P_pred = self.P + self.Q

        # 2. Outlier rejection: check prediction residual
        residual = abs(measurement - x_pred)
        expected_noise = self.outlier_threshold * np.sqrt(P_pred + self.R)
        if residual > expected_noise:
            # Reject this measurement — keep state unchanged but increase uncertainty
            self.P = P_pred  # Let uncertainty grow to track through noise
            self._n_updates += 1
            # If more than 5 consecutive outliers, reinitialize (data feed may have reset)
            if self._n_updates > 5:
                self._reset(measurement)
            return float(self.x)

        # 3. Update (Correction)
        kalman_gain = P_pred / (P_pred + self.R)
        # Guard against numerical instability in Kalman gain
        kalman_gain = np.clip(kalman_gain, 0.0, 1.0)
        self.x = x_pred + kalman_gain * (measurement - x_pred)
        self.P = (1.0 - kalman_gain) * P_pred
        # Prevent P from going negative due to floating point
        self.P = max(self.P, 1e-12)
        self._n_updates = 0  # Reset outlier counter on valid update

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

    # Check that prices have meaningful variance — flat/constant prices
    # always appear to be "mean-reverting" (a≈1 with tiny noise)
    x_var = np.var(x)
    if x_var < 1e-10:
        return 0.0, float(np.mean(prices)), False

    # Perform OLS regression: y = a * x + b
    A = np.vstack([x, np.ones(len(x))]).T
    a, b = np.linalg.lstsq(A, y, rcond=None)[0]

    # Handle boundary conditions
    if a <= 0 or a >= 1:
        # Not mean-reverting (either trending or unstable)
        return 0.0, float(np.mean(prices)), False

    # Guard against near-unit-root producing absurdly large mu
    # If 1-a < 1e-6, the mean reversion is too weak to trust the mu estimate
    one_minus_a = max(1.0 - a, 1e-8)
    mu = b / one_minus_a

    theta = -np.log(a) / dt

    # Sanity-check mu: it should be within reasonable bounds of observed prices
    price_min, price_max = float(np.min(prices)), float(np.max(prices))
    price_range = price_max - price_min
    if price_range > 0:
        # mu should be within 3x the observed range (guard against blowup)
        if mu < price_min - 3 * price_range or mu > price_max + 3 * price_range:
            return 0.0, float(np.mean(prices)), False

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
    round_support = round(local_support / round_number_base) * round_number_base if local_support != 0 else 0.0
    # Guard against division by zero when local_support = 0
    if local_support != 0:
        is_near_round_support = abs(local_support - round_support) / local_support < 0.005
    else:
        is_near_round_support = (round_support == 0.0)

    if is_support_sweep:
        # Strong psychological reversal signal (Buy)
        # Score boosted if support lies on a round number
        return 1.5 if is_near_round_support else 1.0
    elif is_resistance_sweep:
        # Strong psychological reversal signal (Sell)
        return -1.5 if is_near_round_support else -1.0

    return 0.0

def query_gemini_robust(api_key: str, prompt, model: str = "gemini-flash-latest", max_retries: int = 5, backoff_factor: float = 2.0) -> str:
    """Queries configured LLM Provider (Gemini, OpenAI, Anthropic) with backoff on transient errors."""
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
            elif filename == "allocator_agent.py":
                agent = "allocator"
                break
    except Exception:
        pass

    agent_map = {
        "quant": "PhD Quant Agent",
        "dev": "AI Software Developer",
        "sentiment": "Sentiment Sentinel",
        "nn": "NeuralCore Optimizer",
        "risk": "Risk Auditor",
        "reporter": "Blogger Agent",
        "allocator": "Ensemble Asset Allocator",
        "default": "System Agent"
    }
    hr_agent = agent_map.get(agent, "System Agent")

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
        
    goal_val = 10.0  # Realistic: ~5% of $200 account. Old $1000/day = 500% daily — unrealistic.
    try:
        if 'settings' in locals() and "daily_income_goal" in settings:
            goal_val = float(settings["daily_income_goal"])
    except Exception:
        pass

    # Overwrite if database overrides exist
    if api_key_override:
        api_key = api_key_override
    use_model = config_model if config_model else model
    
    # Dynamic daily goal replacement helper
    def replace_goal_references(text: str, goal_val: float) -> str:
        if not isinstance(text, str):
            return text
        goal_str = f"{int(goal_val):,}"
        replacements = [
            ("$1,000 USD/day", f"${goal_str} USD/day"),
            ("$1,000 USD a day", f"${goal_str} USD a day"),
            ("$1,000/day", f"${goal_str}/day"),
            ("$1,000 USD average daily profit", f"${goal_str} USD average daily profit"),
            ("earn $1,000 USD a day", f"earn ${goal_str} USD a day"),
            ("target of $1,000 USD a day", f"target of ${goal_str} USD a day"),
            ("earn $1,000 USD a day safely", f"earn ${goal_str} USD a day safely"),
            ("targeting $1,000 USD/day", f"targeting ${goal_str} USD/day"),
            ("average $1,000/day", f"average ${goal_str}/day"),
            ("scale bot earnings to $1,000 USD/day", f"scale bot earnings to ${goal_str} USD/day"),
            ("scale NexusTrader earnings to $1,000 USD/day", f"scale NexusTrader earnings to ${goal_str} USD/day"),
            ("achieve $1,000 USD/day", f"achieve ${goal_str} USD/day"),
            ("scale earnings to $1,000 USD a day", f"scale earnings to ${goal_str} USD a day"),
            ("achieve our $1,000 USD/day profit target", f"achieve our ${goal_str} USD/day profit target"),
            ("hit $1,000/day", f"hit ${goal_str}/day"),
            ("target of $1,000/day", f"target of ${goal_str}/day"),
            ("closer to $1,000/day", f"closer to ${goal_str}/day"),
            ("closer to $1,000 USD/day", f"closer to ${goal_str} USD/day")
        ]
        for old, new in replacements:
            text = text.replace(old, new)
            old_no_comma = old.replace(",000", "000")
            if old_no_comma != old:
                text = text.replace(old_no_comma, new)
        return text

    def walk_and_replace_goal(data, goal_val: float):
        if isinstance(data, dict):
            return {k: walk_and_replace_goal(v, goal_val) for k, v in data.items()}
        elif isinstance(data, list):
            return [walk_and_replace_goal(x, goal_val) for x in data]
        elif isinstance(data, str):
            return replace_goal_references(data, goal_val)
        return data

    prompt = walk_and_replace_goal(prompt, goal_val)

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
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{use_model}:generateContent?key={api_key}"
            
        payload = prompt if isinstance(prompt, dict) else {"contents": [{"parts": [{"text": flat_prompt}]}]}
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["x-goog-api-key"] = api_key
            
    elif provider == "openai":
        url = base_url if base_url else "https://api.openai.com/v1/chat/completions"
        if url and not url.endswith("/chat/completions"):
            url = url.rstrip("/") + "/chat/completions"

        # gpt-4o-mini has a much higher TPM limit (200K vs 30K) and is cheaper
        if not use_model or use_model in ["gemini-2.0-flash", "gemini-flash-latest", "gpt-4o"]:
            use_model = "gpt-4o-mini"

        # Truncate prompt to stay well under token limits (~20K chars ≈ 5K tokens)
        MAX_PROMPT_CHARS = 20_000
        if len(flat_prompt) > MAX_PROMPT_CHARS:
            logging.warning(
                f"[OPENAI] Prompt too large ({len(flat_prompt):,} chars). "
                f"Truncating to {MAX_PROMPT_CHARS:,} chars to avoid TPM limit."
            )
            flat_prompt = flat_prompt[:MAX_PROMPT_CHARS] + "\n\n[...context truncated to fit token limits...]"

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
                res_text = ""
                if provider == "gemini":
                    res_text = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
                elif provider == "openai":
                    res_text = res_json["choices"][0]["message"]["content"].strip()
                elif provider == "anthropic":
                    res_text = res_json["content"][0]["text"].strip()
                
                try:
                    import database
                    database.log_agent_run(hr_agent, provider, use_model, flat_prompt, res_text, "Success")
                except Exception:
                    pass
                return res_text
        except urllib.error.HTTPError as e:
            if e.code in [429, 500, 502, 503, 504] and retries < max_retries:
                logging.warning(f"[{provider.upper()} API] Transient HTTP error ({e.code}) hit. Retrying in {delay:.1f}s... (Attempt {retries+1}/{max_retries})")
                time.sleep(delay)
                retries += 1
                delay *= backoff_factor
            else:
                msg = ""
                try:
                    err_body = e.read().decode("utf-8")
                    logging.error(f"[{provider.upper()} API] HTTP Error {e.code}: {e.reason} - Body: {err_body}")
                    try:
                        err_json = json.loads(err_body)
                        if "error" in err_json:
                            if isinstance(err_json["error"], dict):
                                msg = err_json["error"].get("message", err_body)
                            else:
                                msg = str(err_json["error"])
                        elif "message" in err_json:
                            msg = err_json["message"]
                        else:
                            msg = err_body
                    except Exception:
                        msg = err_body
                except Exception:
                    logging.error(f"[{provider.upper()} API] HTTP Error {e.code}: {e.reason}")
                    msg = e.reason
                
                err_msg = f"[{provider.upper()} API Error] HTTP {e.code} {e.reason}: {msg}"
                try:
                    import database
                    database.log_agent_run(hr_agent, provider, use_model, flat_prompt, f"Error: {err_msg}", "Failed")
                except Exception:
                    pass
                raise RuntimeError(err_msg)
        except (urllib.error.URLError, ConnectionResetError, BrokenPipeError, TimeoutError) as e:
            if retries < max_retries:
                logging.warning(f"[{provider.upper()} API] Transient Network error ({e}) hit. Retrying in {delay:.1f}s... (Attempt {retries+1}/{max_retries})")
                time.sleep(delay)
                retries += 1
                delay *= backoff_factor
            else:
                logging.error(f"[{provider.upper()} API] Network Error: {e}")
                err_msg = f"[{provider.upper()} API Network Error]: {e}"
                try:
                    import database
                    database.log_agent_run(hr_agent, provider, use_model, flat_prompt, f"Error: {err_msg}", "Failed")
                except Exception:
                    pass
                raise e
        except Exception as e:
            logging.error(f"[{provider.upper()} API] Unexpected error: {e}")
            err_msg = f"[{provider.upper()} API Unexpected Error]: {e}"
            try:
                import database
                database.log_agent_run(hr_agent, provider, use_model, flat_prompt, f"Error: {err_msg}", "Failed")
            except Exception:
                pass
            raise e
