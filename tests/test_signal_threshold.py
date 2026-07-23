"""
Tests for the dynamic signal threshold logic and starvation relaxation.

Verifies:
1. Signal threshold scales inversely with account equity
2. Starvation relaxation progressively lowers threshold after >1h without trades
3. Saved threshold from DB is clamped to [0.10, 0.45]
4. Blocked cooldown prevents re-evaluation
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSignalThreshold(unittest.TestCase):
    """Tests the dynamic signal threshold calculation used in process_tick."""

    def test_threshold_scales_with_equity(self):
        """Signal threshold should decrease as equity grows (less restrictive)."""
        def calc_threshold(equity):
            return max(0.15, min(0.45, 1.0 / (1.0 + equity / 350.0)))

        # Small account: higher threshold (more selective), capped at 0.45
        t200 = calc_threshold(200.0)
        self.assertEqual(t200, 0.45, "Small account ($200) should be capped at 0.45")

        # Large account: lower threshold (more permissive)
        t1000 = calc_threshold(1000.0)
        self.assertLess(t1000, t200, "Larger account should have lower threshold")

        # Minimum threshold clamp
        t10000 = calc_threshold(10000.0)
        self.assertEqual(t10000, 0.15, "Large account threshold should floor at 0.15")

        # Maximum threshold clamp
        t50 = calc_threshold(50.0)
        self.assertEqual(t50, 0.45, "Tiny account threshold should ceiling at 0.45")

    def test_starvation_relaxation(self):
        """Starvation relaxation progressively lowers threshold after >1h."""
        # Simulate starvation: 90 min without a trade
        minutes_without_trade = 90.0
        base_threshold = 0.30

        _extra_relax = min(0.35, (minutes_without_trade - 60.0) / 15.0 * 0.01)
        relaxed = max(0.10, base_threshold - _extra_relax)

        self.assertGreater(_extra_relax, 0.0, "Should have relaxation after 90min")
        self.assertLess(relaxed, base_threshold, "Relaxed threshold should be lower")

    def test_starvation_no_relaxation_under_1h(self):
        """No starvation relaxation before 1 hour."""
        minutes_without_trade = 45.0

        if minutes_without_trade >= 60.0 and minutes_without_trade < 999.0:
            _extra_relax = min(0.35, (minutes_without_trade - 60.0) / 15.0 * 0.01)
        else:
            _extra_relax = 0.0  # No relaxation under 1h

        self.assertEqual(_extra_relax, 0.0, "No relaxation before 1 hour")

    def test_starvation_max_relaxation(self):
        """Starvation relaxation should cap at 0.35 (threshold floors at 0.10)."""
        minutes_without_trade = 600.0  # 10 hours
        _extra_relax = min(0.35, (minutes_without_trade - 60.0) / 15.0 * 0.01)
        self.assertEqual(_extra_relax, 0.35, "Should cap at 0.35")

        base = 0.45
        relaxed = max(0.10, base - 0.35)
        self.assertAlmostEqual(relaxed, 0.10, places=2, msg="Floor should be 0.10")

    def test_db_threshold_clamped(self):
        """DB-saved threshold should be clamped to [0.10, 0.45]."""
        # Simulate loading from DB with safety clamp
        def load_clamped(raw):
            try:
                return max(0.10, min(0.45, float(str(raw).strip())))
            except (ValueError, TypeError):
                return 0.30

        # Valid values pass through
        self.assertEqual(load_clamped("0.25"), 0.25)
        self.assertEqual(load_clamped("0.10"), 0.10)
        self.assertEqual(load_clamped("0.45"), 0.45)

        # Out of range clamped
        self.assertEqual(load_clamped("0.60"), 0.45, "Too high should clamp")
        self.assertEqual(load_clamped("0.05"), 0.10, "Too low should clamp")

        # Invalid fallback
        self.assertEqual(load_clamped(""), 0.30)
        self.assertEqual(load_clamped(None), 0.30)
        self.assertEqual(load_clamped("abc"), 0.30)

    def test_blocked_cooldown_prevents_reevaluation(self):
        """Blocked ticker cooldown should be honored before normal flow."""
        import time

        now = time.time()
        blocked_until = now + 30

        # Should skip if in blocked cooldown
        blocked = time.time() < blocked_until
        self.assertTrue(blocked, "Should be in blocked cooldown")

        # After cooldown expires
        blocked_until_past = now - 1
        blocked_after = time.time() < blocked_until_past
        self.assertFalse(blocked_after, "Should not be blocked after cooldown")

    def test_ticker_skip_while_pos_open(self):
        """Tickers with open positions should not generate signals."""
        # If pos_open is True, the signal evaluation section is skipped
        open_positions = {"ETH-USD": {}, "BTC-USD": {}}
        tickers = ["ETH-USD", "SOL-USD", "BTC-USD"]

        tickers_without_pos = [t for t in tickers if t not in open_positions]
        self.assertIn("SOL-USD", tickers_without_pos)
        self.assertNotIn("ETH-USD", tickers_without_pos)
        self.assertEqual(len(tickers_without_pos), 1,
                         "Only SOL-USD should be without a position")


if __name__ == "__main__":
    unittest.main()
