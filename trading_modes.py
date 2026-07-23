"""
Trading mode namespace separation — canonical module.

Ensures paper and live trading use separate database state,
preventing research artifacts from leaking into live execution.

Unified from trading_mode.py + trading_modes.py.
"""

import logging
from typing import Optional, Tuple

# Mode constants
MODE_RESEARCH = "research"
MODE_PAPER = "paper"
MODE_LIVE = "live"
MODE_SIMULATION = "simulation"

ALL_VALID_MODES = {MODE_RESEARCH, MODE_PAPER, MODE_LIVE, MODE_SIMULATION}
VALID_TRADING_MODES = ALL_VALID_MODES  # backward compat alias
_STRICT_VALID_MODES = {MODE_RESEARCH, MODE_PAPER, MODE_LIVE}


def validate_mode(mode: str) -> str:
    """Validate and normalize trading mode string (strict — raises on invalid)."""
    m = mode.strip().lower()
    if m not in _STRICT_VALID_MODES:
        raise ValueError(
            f"Invalid trading mode: {mode}. Must be one of {_STRICT_VALID_MODES}"
        )
    return m


def normalize_trading_mode(mode: str) -> str:
    """Normalizes and validates a trading mode string (permissive — defaults on invalid)."""
    if not mode:
        return MODE_PAPER
    mode = mode.strip().lower()
    if mode not in ALL_VALID_MODES:
        logging.warning(
            f"Unknown trading mode '{mode}', defaulting to '{MODE_PAPER}'"
        )
        return MODE_PAPER
    return mode


def ns(setting_key: str, mode: str = MODE_PAPER) -> str:
    """Namespace a setting key by trading mode (colon separator).

    Example:
        ns("policy_net_weights_BTC-USD", "live") -> "live:policy_net_weights_BTC-USD"
        ns("loss_cooldown_hours", "research") -> "research:loss_cooldown_hours"

    Research and paper share the same namespace group.
    Live is fully isolated.
    """
    normalized = normalize_trading_mode(mode)
    if normalized == MODE_LIVE:
        return f"live:{setting_key}"
    return f"{MODE_RESEARCH}:{setting_key}"


def namespaced_key(mode: str, key: str) -> str:
    """Alias for ns() — returns a mode-namespaced database key."""
    return ns(key, mode)


def isolate_key(key: str) -> Tuple[str, str]:
    """Reverse a namespaced key. Returns (mode, original_key)."""
    if key.startswith("live:"):
        return MODE_LIVE, key[5:]
    if key.startswith("research:"):
        return MODE_RESEARCH, key[9:]
    return MODE_RESEARCH, key


def load_trading_mode() -> str:
    """Loads the current trading mode from database settings."""
    try:
        import database
        mode = database.load_setting("trading_mode", MODE_PAPER)
        return normalize_trading_mode(mode)
    except Exception:
        return MODE_PAPER


def get_namespaced_setting(mode: str, key: str, default="") -> str:
    """Loads a setting with mode namespace, falling back to legacy key.

    E.g. get_namespaced_setting("live", "policy_net_weights_BTC-USD")
    Tries "live:policy_net_weights_BTC-USD" first, then "policy_net_weights_BTC-USD".
    """
    import database
    ns_key = ns(key, mode)
    val = database.load_setting(ns_key, None)
    if val is None:
        val = database.load_setting(key, default)
    return val


def save_namespaced_setting(mode: str, key: str, value: str) -> None:
    """Saves a setting under the mode namespace."""
    import database
    ns_key = ns(key, mode)
    database.save_setting(ns_key, value)


def migrate_existing_settings(database_module) -> int:
    """Idempotent migration: copy existing unnamespaced settings to research: namespace.

    Returns count of keys migrated.
    """
    count = 0
    known_keys = [
        "trading_mode", "broker", "trailing_stop_enabled",
        "loss_cooldown_hours", "opt_tp_multiplier", "opt_sl_multiplier",
        "risk_mode", "max_daily_drawdown",
        "nn_learning_rate", "nn_weight_floor", "nn_discount_factor",
        "nn_exploration_rate", "initial_portfolio_balance",
        "nn_hidden_layers", "nn_hidden_dim",
    ]
    for key in known_keys:
        existing = database_module.load_setting(key)
        if existing is not None and existing != "":
            ns_key = ns(key, MODE_RESEARCH)
            existing_ns = database_module.load_setting(ns_key)
            if existing_ns is None or existing_ns == "":
                database_module.save_setting(ns_key, str(existing))
                count += 1
    return count


def list_keys_for_mode(database_module, mode: str) -> dict:
    """List all settings keys that belong to a given trading mode."""
    prefix = f"{mode}:"
    result = {}
    conn = None
    try:
        conn = database_module.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM settings WHERE key LIKE ?", (prefix + "%",))
        for row in cursor.fetchall():
            result[row[0]] = row[1]
    except Exception:
        pass
    finally:
        if conn:
            conn.close()
    return result
