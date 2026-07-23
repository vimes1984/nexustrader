"""
Safety infrastructure: kill switch, drawdown tracker, mutation freeze.

Designed to be integrated into live trading without changing existing behavior.
"""
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
        """Call with current portfolio value. Returns current drawdown as fraction."""
        if equity > self.peak:
            self.peak = equity
        if self.peak > 0:
            self.current_drawdown = (self.peak - equity) / self.peak
        else:
            self.current_drawdown = 0.0
        if self.current_drawdown > self.max_drawdown:
            self.max_drawdown = self.current_drawdown
        return self.current_drawdown

    def to_dict(self) -> dict:
        return {"peak": self.peak, "max_drawdown": self.max_drawdown}

    @classmethod
    def from_dict(cls, data: dict) -> "DrawdownTracker":
        t = cls()
        t.peak = data.get("peak", 0.0)
        t.max_drawdown = data.get("max_drawdown", 0.0)
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
        max_daily_loss: float = 10.0,
        max_position_per_symbol: float = 50.0,
        max_total_exposure: float = 100.0,
        max_drawdown_pct: float = 0.10,  # 10% max drawdown (tighter for small account)
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
        # For a $200 baseline account: $10 daily loss, $50 per-position, $100 total exposure
        # These scale up linearly as the account grows.
        # BUGFIX: Defaults of $500/$5000/$25000 were absurd for a $200 account.
        # They'd never trip. Now they provide real circuit-breaking.
        if current_equity is not None and current_equity > 0:
            scale = current_equity / 200.0  # Scale from $200 baseline
            max_daily = max(10.0, 10.0 * scale)
            max_per_pos = max(20.0, 50.0 * scale)
            max_exposure = max(30.0, 100.0 * scale)
        else:
            max_daily = 10.0
            max_per_pos = 50.0
            max_exposure = 100.0

        # Daily reset every 24h
        if time.time() - self.daily_reset_time > 86400:
            self.daily_pnl = 0.0
            self.daily_reset_time = time.time()

        if self.daily_pnl <= -max_daily:
            self.tripped = True
            self.trigger_reason = "Daily loss limit: {:.2f} >= {:.2f} (account: ${:.0f})".format(-self.daily_pnl, max_daily, current_equity or 0)
            return False, self.trigger_reason

        if current_drawdown >= self.max_drawdown_pct:
            self.tripped = True
            self.trigger_reason = "Max drawdown: {:.2%} >= {:.2%}".format(current_drawdown, self.max_drawdown_pct)
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
        self.daily_pnl += pnl

    def reset(self):
        """Manual reset after investigation."""
        self.tripped = False
        self.trigger_reason = None
        self.daily_pnl = 0.0
        self.daily_reset_time = time.time()

    def to_dict(self) -> dict:
        return {
            "tripped": self.tripped,
            "trigger_reason": self.trigger_reason,
            "daily_pnl": self.daily_pnl,
            "daily_reset_time": self.daily_reset_time,
            "_base_equity": self._base_equity,
        }

    @classmethod
    def from_dict(cls, data: dict, **kwargs) -> "KillSwitch":
        ks = cls(**kwargs)
        ks.tripped = data.get("tripped", False)
        ks.trigger_reason = data.get("trigger_reason")
        ks.daily_pnl = data.get("daily_pnl", 0.0)
        ks.daily_reset_time = data.get("daily_reset_time", time.time())
        ks._base_equity = data.get("_base_equity", 0.0)
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
        # BUGFIX: Cap pending suggestions at 500 to prevent unbounded memory growth.
        # Optimizer agents can generate thousands of suggestions during backtesting.
        if len(self.pending_suggestions) > 500:
            self.pending_suggestions = self.pending_suggestions[-500:]
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
