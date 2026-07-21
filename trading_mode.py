"""
trading_mode.py — Legacy re-export wrapper.

All functionality migrated to trading_modes.py.
This file re-exports for backward compatibility.
"""
# flake8: noqa: F401
from trading_modes import (
    MODE_RESEARCH,
    MODE_PAPER,
    MODE_LIVE,
    MODE_SIMULATION,
    ALL_VALID_MODES,
    VALID_TRADING_MODES,
    validate_mode,
    normalize_trading_mode,
    ns,
    namespaced_key,
    isolate_key,
    load_trading_mode,
    get_namespaced_setting,
    save_namespaced_setting,
    migrate_existing_settings,
    list_keys_for_mode,
)
