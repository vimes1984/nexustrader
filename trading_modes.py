"""
Trading mode namespace separation.

Ensures paper and live trading use separate database state,
preventing research artifacts from leaking into live execution.
"""

from typing import Optional, Tuple

# Mode constants
MODE_RESEARCH = "research"
MODE_PAPER = "paper"
MODE_LIVE = "live"

_VALID_MODES = {MODE_RESEARCH, MODE_PAPER, MODE_LIVE}


def validate_mode(mode: str) -> str:
    """Validate and normalize trading mode string."""
    m = mode.strip().lower()
    if m not in _VALID_MODES:
        raise ValueError(f"Invalid trading mode: {mode}. Must be one of {_VALID_MODES}")
    return m


def ns(setting_key: str, mode: str = MODE_PAPER) -> str:
    """Namespace a setting key by trading mode.

    Example:
        ns("policy_net_weights_BTC-USD", "live") -> "live:policy_net_weights_BTC-USD"
        ns("loss_cooldown_hours", "research") -> "research:loss_cooldown_hours"

    Research and paper share the same namespace group.
    Live is fully isolated.
    """
    if mode == MODE_LIVE:
        return f"live:{setting_key}"
    return f"{MODE_RESEARCH}:{setting_key}"


def isolate_key(key: str) -> Tuple[str, str]:
    """Reverse a namespaced key. Returns (mode, original_key)."""
    if key.startswith("live:"):
        return MODE_LIVE, key[5:]
    if key.startswith("research:"):
        return MODE_RESEARCH, key[9:]
    return MODE_RESEARCH, key


def migrate_existing_settings(database_module) -> int:
    """Idempotent migration: copy existing unnamespaced settings to research: namespace.

    Returns count of keys migrated.
    """
    count = 0
    # Get all settings from DB — this assumes database has a list-like capability
    # Falls back to trying known keys
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
    # This is a best-effort scan — depends on DB schema
    # For SQLite we'd need a settings table with LIKE query
    try:
        conn = database_module.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM settings WHERE key LIKE ?", (prefix + "%",))
        for row in cursor.fetchall():
            result[row[0]] = row[1]
        conn.close()
    except Exception:
        pass
    return result
