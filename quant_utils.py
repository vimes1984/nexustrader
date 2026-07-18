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

def query_gemini_robust(api_key: str, prompt, model: str = "gemini-2.0-flash", max_retries: int = 5, backoff_factor: float = 2.0) -> str:
    """Queries Google Gemini API with exponential backoff on HTTP 429 rate limit errors."""
    import urllib.request
    import urllib.error
    import json
    import time
    import logging
    
    # Check if the Antigravity local proxy is online on port 8001
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
        url = f"http://127.0.0.1:8001/v1beta/models/{model}:generateContent"
        logging.info("[PROXY ROUTE] Routing request through local Antigravity proxy on 127.0.0.1:8001")
    else:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    if isinstance(prompt, dict):
        payload = prompt
    else:
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
    encoded_data = json.dumps(payload).encode("utf-8")
    
    retries = 0
    delay = 2.0 # Start with 2 seconds delay
    
    while True:
        try:
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["x-goog-api-key"] = api_key
            req = urllib.request.Request(url, data=encoded_data, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))
                return res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
        except urllib.error.HTTPError as e:
            if e.code in [429, 500, 502, 503, 504] and retries < max_retries:
                logging.warning(f"[GEMINI API] Transient error ({e.code}) hit. Retrying in {delay:.1f}s... (Attempt {retries+1}/{max_retries})")
                time.sleep(delay)
                retries += 1
                delay *= backoff_factor
            else:
                logging.error(f"[GEMINI API] HTTP Error {e.code}: {e.reason}")
                raise e
        except Exception as e:
            logging.error(f"[GEMINI API] Unexpected error: {e}")
            raise e
