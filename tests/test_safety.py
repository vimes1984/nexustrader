import unittest
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.safety import DrawdownTracker, KillSwitch, MutationFreeze


class TestDrawdownTracker(unittest.TestCase):

    def test_no_drawdown(self):
        ddt = DrawdownTracker(initial_equity=100)
        ddt.update(110)
        ddt.update(120)
        self.assertAlmostEqual(ddt.current_drawdown, 0.0)
        self.assertAlmostEqual(ddt.max_drawdown, 0.0)

    def test_drawdown_calculated(self):
        ddt = DrawdownTracker(initial_equity=100)
        ddt.update(120)  # peak
        ddt.update(100)  # drop
        ddt.update(90)   # trough
        self.assertAlmostEqual(ddt.current_drawdown, (120 - 90) / 120)
        self.assertAlmostEqual(ddt.max_drawdown, (120 - 90) / 120)

    def test_drawdown_recovers(self):
        ddt = DrawdownTracker(initial_equity=100)
        ddt.update(120)
        ddt.update(100)
        ddt.update(130)  # new peak
        self.assertAlmostEqual(ddt.current_drawdown, 0.0)
        self.assertAlmostEqual(ddt.max_drawdown, (120 - 100) / 120)

    def test_serialize_roundtrip(self):
        ddt = DrawdownTracker(initial_equity=100)
        ddt.update(120)
        ddt.update(90)
        data = ddt.to_dict()
        restored = DrawdownTracker.from_dict(data)
        self.assertAlmostEqual(restored.peak, ddt.peak)
        self.assertAlmostEqual(restored.max_drawdown, ddt.max_drawdown)


class TestKillSwitch(unittest.TestCase):

    def test_safe_by_default(self):
        ks = KillSwitch()
        safe, reason = ks.check()
        self.assertTrue(safe)
        self.assertIsNone(reason)

    def test_daily_loss_triggers(self):
        ks = KillSwitch(max_daily_loss=100.0)
        for _ in range(5):
            ks.record_trade(-30)
        safe, reason = ks.check()
        self.assertFalse(safe)
        self.assertIn("Daily loss", reason)

    def test_drawdown_triggers(self):
        ks = KillSwitch(max_drawdown_pct=0.1)
        safe, reason = ks.check(current_drawdown=0.15)
        self.assertFalse(safe)
        self.assertIn("drawdown", reason.lower())

    def test_position_limit_triggers(self):
        ks = KillSwitch(max_position_per_symbol=1000.0)
        safe, reason = ks.check(open_positions={"BTC-USD": 1500.0})
        self.assertFalse(safe)
        self.assertIn("BTC-USD", reason)

    def test_exposure_triggers(self):
        ks = KillSwitch(max_total_exposure=10000.0)
        safe, reason = ks.check(total_exposure=15000.0)
        self.assertFalse(safe)
        self.assertIn("exposure", reason.lower())

    def test_stays_tripped(self):
        ks = KillSwitch(max_daily_loss=100.0)
        ks.record_trade(-200)
        ks.check()  # trips
        # Even with clean params, still tripped
        safe, reason = ks.check()
        self.assertFalse(safe)

    def test_reset(self):
        ks = KillSwitch(max_daily_loss=100.0)
        ks.record_trade(-200)
        ks.check()
        ks.reset()
        safe, reason = ks.check()
        self.assertTrue(safe)

    def test_serialize_roundtrip(self):
        ks = KillSwitch(max_daily_loss=100.0)
        ks.record_trade(-50)
        data = ks.to_dict()
        restored = KillSwitch.from_dict(data, max_daily_loss=100.0)
        self.assertEqual(restored.daily_pnl, ks.daily_pnl)
        self.assertEqual(restored.tripped, ks.tripped)


class TestMutationFreeze(unittest.TestCase):

    def test_frozen_by_default(self):
        mf = MutationFreeze()
        self.assertTrue(mf.frozen)

    def test_suggest_does_not_mutate(self):
        mf = MutationFreeze()
        mf.suggest("QuantAgent", "risk_mode", "conservative", "aggressive")
        self.assertEqual(len(mf.pending_suggestions), 1)
        self.assertTrue(mf.frozen)

    def test_thaw_and_refreeze(self):
        mf = MutationFreeze()
        mf.thaw()
        self.assertFalse(mf.frozen)
        mf.refreeze()
        self.assertTrue(mf.frozen)


if __name__ == "__main__":
    unittest.main()
