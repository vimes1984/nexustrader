"""
mutation_guard.py — Live mutation freeze for NexusTrader.

LLM agents can generate recommendations but must NOT automatically write
live trading config when live_mutation_freeze is enabled (default: true).

Usage in any agent:
    from mutation_guard import should_apply_agent_mutation, log_blocked_mutation

    if should_apply_agent_mutation("risk_auditor", target_mode="live"):
        database.save_setting("max_daily_drawdown", new_val)
    else:
        log_blocked_mutation("risk_auditor", "max_daily_drawdown", new_val)
"""

import logging

PROTECTED_KEYS = {
    "policy_net_weights_",
    "active_policy_brain_",
    "max_daily_drawdown",
    "loss_cooldown_hours",
    "nn_weight_floor",
    "nn_learning_rate",
    "active_assets",
    "opt_tp_multiplier",
    "opt_sl_multiplier",
}


def _is_frozen() -> bool:
    """Returns True if live mutation freeze is enabled (default True = safe)."""
    try:
        import database
        val = database.load_setting("live_mutation_freeze", "true")
        return str(val).strip().lower() in ("true", "1", "yes")
    except Exception:
        return True  # Fail-safe: always freeze if we can't check


def _get_trading_mode() -> str:
    """Returns the current trading mode, defaulting to 'paper'."""
    try:
        import database
        return database.load_setting("trading_mode", "paper").strip().lower()
    except Exception:
        return "paper"


def is_live_mutation_allowed() -> bool:
    """
    Returns True if mutations to live config are currently permitted.
    Safe default: False (frozen) when in live mode.
    """
    mode = _get_trading_mode()
    if mode != "live":
        return True  # paper/research/simulation: mutations always allowed
    return not _is_frozen()


def should_apply_agent_mutation(agent_name: str, target_mode: str = None) -> bool:
    """
    Returns True if the agent is allowed to write config changes.

    Args:
        agent_name: Name of the calling agent (for logging).
        target_mode: Override mode check; if None uses current trading mode.

    Returns:
        True if mutation is permitted, False if it must be blocked.
    """
    mode = target_mode or _get_trading_mode()
    if mode == "live" and _is_frozen():
        logging.warning(
            f"[MUTATION GUARD] Agent '{agent_name}' attempted to mutate live config "
            f"but live_mutation_freeze=true. Recommendation logged only."
        )
        return False
    return True


def log_blocked_mutation(agent_name: str, key: str, value, reason: str = "live_mutation_freeze") -> None:
    """Logs a blocked mutation recommendation for audit purposes."""
    logging.info(
        f"[MUTATION GUARD] BLOCKED | agent={agent_name} | key={key} | "
        f"value={value} | reason={reason}"
    )
    try:
        import database
        import time
        rec_key = f"mutation_recommendation_{int(time.time())}_{agent_name}_{key}"
        database.save_setting(rec_key, str(value))
    except Exception:
        pass


def is_key_protected(key: str) -> bool:
    """Returns True if the given settings key is a protected live-trading key."""
    for prefix in PROTECTED_KEYS:
        if key.startswith(prefix) or key == prefix.rstrip("_"):
            return True
    return False
