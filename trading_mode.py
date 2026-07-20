"""
trading_mode.py — Central mode/namespace helpers for NexusTrader.

Prevents research/paper state from contaminating live execution by
namespacing all state keys per trading mode.
"""

import logging

VALID_TRADING_MODES = {"research", "paper", "live", "simulation"}

def normalize_trading_mode(mode: str) -> str:
    """Normalizes and validates a trading mode string."""
    if not mode:
        return "paper"
    mode = mode.strip().lower()
    if mode not in VALID_TRADING_MODES:
        logging.warning(f"Unknown trading mode '{mode}', defaulting to 'paper'")
        return "paper"
    return mode

def mode_namespace(mode: str) -> str:
    """Returns the namespace prefix for the given mode."""
    return normalize_trading_mode(mode)

def namespaced_key(mode: str, key: str) -> str:
    """Returns a mode-namespaced database key."""
    ns = mode_namespace(mode)
    return f"{ns}.{key}"

def load_trading_mode() -> str:
    """Loads the current trading mode from database settings."""
    try:
        import database
        mode = database.load_setting("trading_mode", "paper")
        return normalize_trading_mode(mode)
    except Exception:
        return "paper"

def get_namespaced_setting(mode: str, key: str, default="") -> str:
    """
    Loads a setting with mode namespace, falling back to legacy key for backward compatibility.
    E.g. get_namespaced_setting("live", "policy_net_weights_BTC-USD")
    Tries "live.policy_net_weights_BTC-USD" first, then "policy_net_weights_BTC-USD".
    """
    import database
    ns_key = namespaced_key(mode, key)
    val = database.load_setting(ns_key, None)
    if val is None:
        val = database.load_setting(key, default)
    return val

def save_namespaced_setting(mode: str, key: str, value: str) -> None:
    """Saves a setting under the mode namespace. New writes always go to namespaced key."""
    import database
    ns_key = namespaced_key(mode, key)
    database.save_setting(ns_key, value)
