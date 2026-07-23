"""
Safety infrastructure: kill switch, drawdown tracker, mutation freeze.

Designed to be integrated into live trading without changing existing behavior.
"""
import math
import time
import logging
from typing import Optional, Tuple


class DrawdownTracker:
    """Tracks peak-to-trough drawdown from an equity feed.

    Survives restarts if you periodically save/load state.
    """

    def __init__(self, initial_equity: float = 0.0):
        self.peak = initial_equity
        self.current_drawdown = 0.0  # fraction, e.g. 0.05 = 5%
        self.max_drawdown = 0.0

    def update(self, equity: float) -> float:
        """Call with current portfolio value. Returns current drawdown as fraction.

        Drawdown is peak-to-trough, capped at 1.0 (100% loss).
        Negative equity (account in debt) is treated as 100% drawdown.
        """
        if equity > self.peak:
            self.peak = equity
        if self.peak > 0:
            if equity >= 0:
                self.current_drawdown = (self.peak - equity) / self.peak
            else:
                self.current_drawdown = 1.0  # Total loss if equity is negative
        else:
            self.current_drawdown = 0.0
        self.current_drawdown = min(self.current_drawdown, 1.0)  # Hard cap at 100%
        if self.current_drawdown > self.max_drawdown:
            self.max_drawdown = self.current_drawdown
        return self.current_drawdown

    def to_dict(self) -> dict:
        return {
            "peak": self.peak,
            "max_drawdown": self.max_drawdown,
            "current_drawdown": self.current_drawdown,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DrawdownTracker":
        t = cls()
        t.peak = data.get("peak", 0.0)
        t.max_drawdown = data.get("max_drawdown", 0.0)
        t.current_drawdown = data.get("current_drawdown", 0.0)
        return t


class KillSwitch:
    """Multi-layered circuit breaker for trading.

    Stop conditions (any one triggers):
    - Daily loss exceeds max_daily_loss
    - Open position on a symbol exceeds max_position_per_symbol
    - Total exposure exceeds max_total_exposure
    - Drawdown exceeds max_drawdown_pct
    """

    def __init__(
        self,
        max_daily_loss: float = 500.0,
        max_position_per_symbol: float = 5000.0,
        max_total_exposure: float = 25000.0,
        max_drawdown_pct: float = 0.15,  # 15% max drawdown
    ):
        self.max_daily_loss = max_daily_loss
        self.max_position_per_symbol = max_position_per_symbol
        self.max_total_exposure = max_total_exposure
        self.max_drawdown_pct = max_drawdown_pct
        self._base_equity = 0.0  # tracked so limits scale if account grows

        # Runtime state
        self.daily_pnl = 0.0
        self.daily_reset_time = time.time()
        self.tripped = False
        self.trigger_reason: Optional[str] = None
        # Drawdown hysteresis: once tripped on drawdown, recovery must be
        # to hysteresis_recover_pct below the limit before re-arming.
        # Prevents flip-flopping at the boundary when price oscillates.
        self._drawdown_hysteresis_active = False
        self.hysteresis_recover_pct = 0.02  # 2% below max_drawdown_pct to re-arm

    def check(
        self,
        current_drawdown: float = 0.0,
        open_positions: Optional[dict] = None,
        total_exposure: float = 0.0,
        current_equity: Optional[float] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Returns (is_safe, reason_if_tripped).

        If already tripped, stays tripped until reset.
        current_equity: if provided, enables dynamic scaling of limits to account size.
        """
        if self.tripped:
            return False, self.trigger_reason

        # Set base equity on first check with real value
        if self._base_equity == 0.0 and current_equity is not None and current_equity > 0:
            self._base_equity = current_equity

        # Dynamic limits scaled to account size
        # Base limits from percentage of equity with dollar ceilings from config.
        # For a $200 account: 10% daily loss ($20), 25% per-position ($50), 75% total ($150)
        # The config max values are the ABSOLUTE ceiling — never exceed them.
        # The percentage-based floor ensures tiny accounts have appropriately tight limits.
        if current_equity is not None and current_equity > 0:
            # Percentage-based floor (lines scale with account, never exceed config)
            max_daily = min(self.max_daily_loss, max(current_equity * 0.10, 5.0))
            max_per_pos = min(self.max_position_per_symbol, max(current_equity * 0.25, 10.0))
            max_exposure = min(self.max_total_exposure, max(current_equity * 0.75, 30.0))
        else:
            max_daily = self.max_daily_loss
            max_per_pos = self.max_position_per_symbol
            max_exposure = self.max_total_exposure

        # Daily reset every 24h
        if time.time() - self.daily_reset_time > 86400:
            self.daily_pnl = 0.0
            self.daily_reset_time = time.time()

        if self.daily_pnl <= -max_daily:
            self.tripped = True
            self.trigger_reason = "Daily loss limit: {:.2f} >= {:.2f} (account: ${:.0f})".format(-self.daily_pnl, max_daily, current_equity or 0)
            return False, self.trigger_reason

        # Drawdown check with hysteresis to prevent flip-flopping
        effective_dd_threshold = self.max_drawdown_pct
        if self._drawdown_hysteresis_active:
            # Already in hysteresis zone: require recovery below threshold - margin
            recovery_threshold = effective_dd_threshold - self.hysteresis_recover_pct
            if current_drawdown < recovery_threshold:
                self._drawdown_hysteresis_active = False  # Re-armed
            else:
                # Stay tripped until recovery
                self.tripped = True
                self.trigger_reason = "Drawdown hysteresis: {:.2%} still above {:.2%} recovery threshold".format(current_drawdown, recovery_threshold)
                return False, self.trigger_reason

        # Normal drawdown check (not in hysteresis)
        if current_drawdown >= effective_dd_threshold:
            self.tripped = True
            self._drawdown_hysteresis_active = True
            self.trigger_reason = "Max drawdown: {:.2%} >= {:.2%} (hysteresis margin: {:.2%})".format(current_drawdown, effective_dd_threshold, self.hysteresis_recover_pct)
            return False, self.trigger_reason

        if open_positions:
            for sym, size in open_positions.items():
                if abs(size) > max_per_pos:
                    self.tripped = True
                    self.trigger_reason = "Position limit {}: {} > {:.0f} (account: ${:.0f})".format(sym, size, max_per_pos, current_equity or 0)
                    return False, self.trigger_reason

        if total_exposure > max_exposure:
            self.tripped = True
            self.trigger_reason = "Total exposure: {:.0f} > {:.0f} (account: ${:.0f})".format(total_exposure, max_exposure, current_equity or 0)
            return False, self.trigger_reason

        return True, None

    def record_trade(self, pnl: float):
        """Record a completed trade PnL against the daily limit."""
        if pnl is None:
            return
        try:
            pnl_float = float(pnl)
        except (ValueError, TypeError):
            return
        if math.isnan(pnl_float) or math.isinf(pnl_float):
            return
        self.daily_pnl += pnl_float

    def reset(self, current_equity: Optional[float] = None):
        """Manual reset after investigation.

        Clears hysteresis state and optionally resets base_equity
        to the current account value (for recovery after drawdown).
        """
        self.tripped = False
        self.trigger_reason = None
        self.daily_pnl = 0.0
        self.daily_reset_time = time.time()
        self._drawdown_hysteresis_active = False
        if current_equity is not None and current_equity > 0:
            self._base_equity = current_equity

    def to_dict(self) -> dict:
        return {
            "tripped": self.tripped,
            "trigger_reason": self.trigger_reason,
            "daily_pnl": self.daily_pnl,
            "daily_reset_time": self.daily_reset_time,
            "base_equity": self._base_equity,
            "drawdown_hysteresis_active": self._drawdown_hysteresis_active,
        }

    @classmethod
    def from_dict(cls, data: dict, **kwargs) -> "KillSwitch":
        ks = cls(**kwargs)
        ks.tripped = data.get("tripped", False)
        ks.trigger_reason = data.get("trigger_reason")
        ks.daily_pnl = data.get("daily_pnl", 0.0)
        ks.daily_reset_time = data.get("daily_reset_time", time.time())
        ks._base_equity = data.get("base_equity", 0.0)
        ks._drawdown_hysteresis_active = data.get("drawdown_hysteresis_active", False)
        return ks


class MutationFreeze:
    """Gate that prevents automatic config/strategy mutations.

    When frozen, LLM agents and auto-optimizers can log suggestions
    but cannot change live parameters, prompts, or brains.
    """

    def __init__(self, frozen_by_default: bool = True):
        self.frozen = frozen_by_default
        self.pending_suggestions: list[dict] = []

    def suggest(self, agent_name: str, parameter: str, old_value, new_value, reason: str = ""):
        """Log a mutation suggestion without applying it."""
        suggestion = {
            "timestamp": time.time(),
            "agent": agent_name,
            "parameter": parameter,
            "old_value": str(old_value),
            "new_value": str(new_value),
            "reason": reason,
        }
        self.pending_suggestions.append(suggestion)
        logging.info(
            f"[MutationFreeze] SUGGESTION from {agent_name}: "
            f"{parameter} = {new_value} (was {old_value}) — {reason}"
        )
        return suggestion

    def apply(self, suggestion_index: int) -> bool:
        """Apply a specific pending suggestion (human approval gate)."""
        if suggestion_index < 0 or suggestion_index >= len(self.pending_suggestions):
            return False
        self.pending_suggestions.pop(suggestion_index)
        return True  # caller implements the actual mutation

    def thaw(self):
        self.frozen = False

    def refreeze(self):
        self.frozen = True
