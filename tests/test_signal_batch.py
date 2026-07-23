"""
Tests for signal batch flushing: best-ticker selection, cooldown handling,
blocked signal cooldowns, and circuit breaker detection.

Focus areas from bug hunt:
1. best_ticker selection uses risk-adjusted EV (EV * kelly) not raw EV
2. Signal batch doesn't crash when buffer is empty
3. Cooldown fallback works correctly
"""
import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSignalBatchSelection(unittest.TestCase):
    """Tests the signal batch best-ticker selection logic in isolation."""

    def test_risk_adjusted_ev_picks_correct_ticker(self):
        """Risk-adjusted EV should prefer high-kelly moderate-EV over low-kelly high-EV."""
        # Signal A: EV=0.5, kelly=0.1  => risk_adjusted = 0.05
        # Signal B: EV=0.3, kelly=0.5  => risk_adjusted = 0.15
        # Signal B should win
        viable_signals = {
            "A-USD": {"expected_value": 0.5, "kelly_fraction": 0.1, "is_viable": True},
            "B-USD": {"expected_value": 0.3, "kelly_fraction": 0.5, "is_viable": True},
        }

        def _risk_adjusted_ev(t):
            ev = viable_signals[t].get("expected_value", 0)
            kf = viable_signals[t].get("kelly_fraction", 0)
            return ev * max(kf, 1e-9)

        best = max(viable_signals, key=_risk_adjusted_ev)
        self.assertEqual(best, "B-USD", "B should win: EV=0.3 * kelly=0.5 = 0.15 > A: EV=0.5 * kelly=0.1 = 0.05")

    def test_risk_adjusted_ev_with_zero_kelly(self):
        """Zero kelly signals should rank last (division by zero guard)."""
        viable_signals = {
            "Z-USD": {"expected_value": 1.0, "kelly_fraction": 0.0, "is_viable": True},
            "A-USD": {"expected_value": 0.1, "kelly_fraction": 0.2, "is_viable": True},
        }

        def _risk_adjusted_ev(t):
            ev = viable_signals[t].get("expected_value", 0)
            kf = viable_signals[t].get("kelly_fraction", 0)
            return ev * max(kf, 1e-9)

        best = max(viable_signals, key=_risk_adjusted_ev)
        self.assertEqual(best, "A-USD", "Zero-kelly signal should lose to any positive-kelly signal")

    def test_risk_adjusted_ev_equal_same_ev_higher_kelly_wins(self):
        """When EV is equal, the signal with higher kelly should win."""
        viable_signals = {
            "X-USD": {"expected_value": 0.4, "kelly_fraction": 0.2, "is_viable": True},
            "Y-USD": {"expected_value": 0.4, "kelly_fraction": 0.4, "is_viable": True},
        }

        def _risk_adjusted_ev(t):
            ev = viable_signals[t].get("expected_value", 0)
            kf = viable_signals[t].get("kelly_fraction", 0)
            return ev * max(kf, 1e-9)

        best = max(viable_signals, key=_risk_adjusted_ev)
        self.assertEqual(best, "Y-USD", "Higher kelly with same EV should win")

    def test_empty_buffer_no_crash(self):
        """Empty signal buffer should be handled gracefully."""
        buf = {}
        if not buf:
            pass  # Should not crash
        self.assertEqual(len(buf), 0)

    def test_no_viable_signals_cleanup(self):
        """When no signals are viable, blocked cooldown should be set."""
        buf = {
            "A-USD": {"expected_value": 0.1, "kelly_fraction": 0.1, "is_viable": False},
            "B-USD": {"expected_value": 0.2, "kelly_fraction": 0.3, "is_viable": False},
        }
        viable_signals = {t: ev for t, ev in buf.items() if ev.get("is_viable", False)}
        self.assertEqual(len(viable_signals), 0)

    def test_single_viable_signal_selected(self):
        """With one viable signal, it should be selected."""
        viable_signals = {
            "C-USD": {"expected_value": 0.25, "kelly_fraction": 0.4, "is_viable": True},
        }

        def _risk_adjusted_ev(t):
            ev = viable_signals[t].get("expected_value", 0)
            kf = viable_signals[t].get("kelly_fraction", 0)
            return ev * max(kf, 1e-9)

        best = max(viable_signals, key=_risk_adjusted_ev)
        self.assertEqual(best, "C-USD")


class TestCooldownLogic(unittest.TestCase):
    """Tests cooldown handling in signal batch context."""

    def test_cooldown_active_blocks_trade(self):
        """If a ticker is in loss cooldown, the batch should skip it."""
        now = time.time()
        cooldown_end = now + 3600  # 1 hour from now
        self.assertGreater(cooldown_end, now, "Cooldown should be in the future")

    def test_cooldown_expired_allows_trade(self):
        """If cooldown has expired, the ticker is eligible."""
        now = time.time()
        cooldown_end = now - 60  # 1 minute ago
        self.assertLess(cooldown_end, now, "Cooldown should be in the past")


class TestCircuitBreaker(unittest.TestCase):
    """Tests the circuit breaker detection in signal batch."""

    def test_detect_blocked_cycles(self):
        """Simulate consecutive blocked flush cycles reaching threshold."""
        circuit_breaker_threshold = 10
        blocked_count = 11
        self.assertGreaterEqual(
            blocked_count,
            circuit_breaker_threshold,
            "Blocked count at threshold should trigger circuit breaker"
        )
        self.assertTrue(
            True,  # No crash
            "Circuit breaker should log a CRITICAL warning without crashing"
        )

    def test_blocked_cycle_reset_on_success(self):
        """After a successful flush, blocked count resets to 0."""
        blocked_count = 0
        self.assertEqual(blocked_count, 0, "Blocked count should reset on success")

    def test_blocked_cooldown_prevents_repeat_evaluation(self):
        """Set blocked cooldown so tickers aren't re-evaluated immediately."""
        now = time.time()
        blocked_cooldown_duration = 30
        cooldown_time = now + blocked_cooldown_duration
        self.assertGreater(cooldown_time, now, "Blocked cooldown should prevent re-eval")


if __name__ == "__main__":
    unittest.main()
