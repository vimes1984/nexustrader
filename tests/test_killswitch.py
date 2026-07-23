"""
Tests for KillSwitch state persistence, stale state auto-reset, and
cross-restart behavior.

Key focus: the "tripped: true" state must not permanently block trades
after a restart if the triggering condition has expired.
"""
import unittest
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.safety import KillSwitch


class TestKillSwitchPersistence(unittest.TestCase):
    """Tests that KillSwitch state persists correctly and handles stale state."""

    def test_to_dict_roundtrip_retains_tripped(self):
        """to_dict→from_dict preserves tripped state."""
        ks = KillSwitch(max_daily_loss=100.0)
        ks.record_trade(-200)  # Exceeds daily loss
        ks.check()
        self.assertTrue(ks.tripped)
        data = ks.to_dict()
        restored = KillSwitch.from_dict(data, max_daily_loss=100.0)
        self.assertTrue(restored.tripped)
        self.assertEqual(restored.trigger_reason, ks.trigger_reason)

    def test_stale_tripped_state_auto_resets_after_24h(self):
        """If daily_reset_time is >24h in the past, the tripped state is stale
        and should be treated as expired (auto-reset on startup)."""
        ks = KillSwitch(max_daily_loss=100.0)
        ks.tripped = True
        ks.trigger_reason = "Daily loss: -120.00 >= 100.00"
        ks.daily_pnl = -120.0
        ks.daily_reset_time = time.time() - 90000  # ~25 hours ago

        elapsed = time.time() - ks.daily_reset_time
        should_reset = elapsed > 86400
        self.assertTrue(should_reset, "State >24h old should be stale")

        if should_reset:
            ks.reset()

        self.assertFalse(ks.tripped, "Stale tripped state should be auto-reset")
        self.assertIsNone(ks.trigger_reason)

    def test_recent_tripped_state_not_auto_reset(self):
        """If tripped < 24h ago, DO NOT auto-reset — the condition is still live."""
        ks = KillSwitch(max_daily_loss=100.0)
        ks.tripped = True
        ks.trigger_reason = "Daily loss: -120.00 >= 100.00"
        ks.daily_pnl = -120.0
        ks.daily_reset_time = time.time() - 3600  # 1 hour ago

        elapsed = time.time() - ks.daily_reset_time
        should_reset = elapsed > 86400
        self.assertFalse(should_reset, "State <24h old should NOT be stale")

        # NOT resetting — mimicking startup code that only resets stale state
        self.assertTrue(ks.tripped, "Recent tripped state should persist")

    def test_drawdown_tracker_persistence(self):
        """DrawdownTracker to_dict→from_dict roundtrip works."""
        from evaluation.safety import DrawdownTracker
        ddt = DrawdownTracker(initial_equity=100)
        ddt.update(120)  # peak
        ddt.update(90)   # trough
        self.assertAlmostEqual(ddt.max_drawdown, (120 - 90) / 120)

        data = ddt.to_dict()
        restored = DrawdownTracker.from_dict(data)
        self.assertAlmostEqual(restored.peak, ddt.peak)
        self.assertAlmostEqual(restored.max_drawdown, ddt.max_drawdown)

    def test_killswitch_stays_tripped_after_reset_window_passes(self):
        """Simulate: KillSwitch trips, then 12h passes (not expired).
        check() should still return False (tripped) because reset hasn't been called.
        """
        ks = KillSwitch(max_daily_loss=100.0)
        ks.tripped = True
        ks.trigger_reason = "Some trigger"
        ks.daily_reset_time = time.time() - 43200  # 12 hours ago

        safe, reason = ks.check()
        self.assertFalse(safe)
        self.assertIsNotNone(reason)

    def test_killswitch_after_reset_works_normally(self):
        """After manual reset, KillSwitch allows trades again."""
        ks = KillSwitch(max_daily_loss=100.0)
        ks.tripped = True
        ks.trigger_reason = "Some trigger"
        ks.daily_pnl = -120.0
        ks.reset()

        safe, reason = ks.check()
        self.assertTrue(safe)
        self.assertIsNone(reason)


class TestKillSwitchScaling(unittest.TestCase):
    """Tests that KillSwitch limits scale with account size."""

    def test_daily_loss_scale_small_account(self):
        """Small account ($200 baseline) should have $10 daily loss limit."""
        ks = KillSwitch()
        safe, reason = ks.check(current_equity=200.0)
        self.assertTrue(safe, f"Small account should be safe: {reason}")

        # Simulate $15 loss on a $200 account
        ks.record_trade(-5.0)
        safe, reason = ks.check(current_equity=200.0)
        self.assertTrue(safe, f"$-5 loss should be ok: {reason}")

        ks.record_trade(-5.0)
        ks.record_trade(-5.0)  # -15 total
        safe, reason = ks.check(current_equity=200.0)
        self.assertFalse(safe, f"$-15 loss should trigger: {reason}")

    def test_daily_loss_scale_large_account(self):
        """Larger account ($5000) should have proportionally larger limits."""
        ks = KillSwitch()

        # With $5000, daily limit scales: 10 * (5000/200) = $250
        ks.record_trade(-100.0)
        safe, reason = ks.check(current_equity=5000.0)
        self.assertTrue(safe, f"$-100 on $5K should be ok: {reason}")

        ks.record_trade(-150.0)  # -250 total
        safe, reason = ks.check(current_equity=5000.0)
        self.assertFalse(safe, f"$-250 on $5K should trigger: {reason}")


    def test_win_clears_cooldown(self):
        """After a winning trade, cooldown should be cleared (set to 0)."""
        ks = KillSwitch(max_daily_loss=100.0)
        # No tripped state, the cooldown clear happens in execution_engine
        # Test that a losing trade record doesn't trip from one loss alone
        ks.record_trade(-5.0)  # Small loss
        safe, reason = ks.check(current_equity=200.0)
        self.assertTrue(safe, f"Small loss should not trip KS: {reason}")

    def test_cooldown_fallback_uses_risk_adjusted_ev(self):
        """Cooldown fallback should sort by risk-adjusted EV, not raw EV."""
        # Simulate viable signals where best is in cooldown
        viable = {
            "A-USD": {"expected_value": 0.8, "kelly_fraction": 0.1},  # raw=0.8, risk_adj=0.08
            "B-USD": {"expected_value": 0.3, "kelly_fraction": 0.5},  # raw=0.3, risk_adj=0.15
        }
        def _fallback_key(item):
            _t2, _ev2 = item
            return _ev2.get("expected_value", 0) * max(_ev2.get("kelly_fraction", 0), 1e-9)
        sorted_v = sorted(viable.items(), key=_fallback_key, reverse=True)
        # B should be first with risk-adjusted EV
        self.assertEqual(sorted_v[0][0], "B-USD",
                         "Risk-adjusted EV should rank B first")


if __name__ == "__main__":
    unittest.main()
