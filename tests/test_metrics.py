import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.metrics import (
    sharpe_ratio, sortino_ratio, calmar_ratio,
    profit_factor, win_rate, avg_trade, max_drawdown_from_equity,
    brier_score, calibration_error, expected_value, kelly_fraction,
)


class TestMetrics(unittest.TestCase):

    def test_sharpe_ratio_all_positive(self):
        r = [0.01, 0.02, 0.015, 0.01, 0.005]
        sr = sharpe_ratio(r)
        self.assertGreater(sr, 0)

    def test_sharpe_ratio_empty(self):
        self.assertEqual(sharpe_ratio([]), 0.0)

    def test_sharpe_ratio_single(self):
        self.assertEqual(sharpe_ratio([0.01]), 0.0)

    def test_sortino_ratio(self):
        r = [0.02, -0.01, 0.01, -0.005, 0.015]
        sr = sortino_ratio(r)
        self.assertGreater(sr, 0)

    def test_calmar_ratio(self):
        r = [0.01, 0.02, -0.03, 0.01, 0.005]
        dd = 0.05
        cr = calmar_ratio(r, dd)
        self.assertGreater(cr, 0)

    def test_calmar_zero_drawdown(self):
        self.assertEqual(calmar_ratio([0.01], 0), 0.0)

    def test_profit_factor_all_profitable(self):
        trades = [{"pnl": 10}, {"pnl": 5}, {"pnl": 3}]
        self.assertEqual(profit_factor(trades), float('inf'))

    def test_profit_factor_mixed(self):
        trades = [{"pnl": 10}, {"pnl": -5}, {"pnl": 3}, {"pnl": -2}]
        pf = profit_factor(trades)
        self.assertAlmostEqual(pf, 13 / 7)

    def test_win_rate(self):
        trades = [{"pnl": 10}, {"pnl": -5}, {"pnl": 3}, {"pnl": -2}, {"pnl": 0}]
        wr = win_rate(trades)
        self.assertAlmostEqual(wr, 2 / 5)

    def test_win_rate_empty(self):
        self.assertEqual(win_rate([]), 0.0)

    def test_avg_trade(self):
        trades = [{"pnl": 10}, {"pnl": -5}, {"pnl": 3}]
        self.assertAlmostEqual(avg_trade(trades), 8 / 3)

    def test_max_drawdown_from_equity(self):
        equity = [100, 110, 105, 95, 100, 120]
        dd = max_drawdown_from_equity(equity)
        self.assertAlmostEqual(dd, (110 - 95) / 110, places=4)

    def test_max_drawdown_flat(self):
        self.assertEqual(max_drawdown_from_equity([100, 100, 100]), 0.0)

    def test_brier_score(self):
        probs = [0.9, 0.1, 0.8, 0.2]
        outcomes = [1, 0, 1, 0]
        bs = brier_score(probs, outcomes)
        self.assertAlmostEqual(bs, 0.025)

    def test_brier_score_mismatch_length(self):
        self.assertEqual(brier_score([0.5], [1, 0]), 0.0)

    def test_calibration_error(self):
        # 8 samples: 4 at 90% prob (all wins), 4 at 10% (all losses)
        # With 2 bins, bin 1 avg_prob=0.1 actual=0 → error=0.1
        # bin 2 avg_prob=0.9 actual=1 → error=0.1
        # ECE = 0.1*0.5 + 0.1*0.5 = 0.1
        probs = [0.9, 0.9, 0.9, 0.9, 0.1, 0.1, 0.1, 0.1]
        outcomes = [1, 1, 1, 1, 0, 0, 0, 0]
        ce = calibration_error(probs, outcomes, bins=2)
        self.assertAlmostEqual(ce, 0.1)

    def test_kelly_fraction(self):
        # (0.55 * 1.2 - 0.45) / 1.2 = 0.175 — well under the 0.25 cap
        f = kelly_fraction(0.55, 1.2)
        expected = (0.55 * 1.2 - 0.45) / 1.2
        self.assertAlmostEqual(f, expected)

    def test_kelly_fraction_capped(self):
        f = kelly_fraction(0.9, 3.0)
        self.assertLessEqual(f, 0.25)

    def test_kelly_fraction_no_edge(self):
        self.assertEqual(kelly_fraction(0.3, 1.0), 0.0)

    def test_expected_value(self):
        ev = expected_value(0.6, 100, -50)
        self.assertAlmostEqual(ev, 40.0)


if __name__ == "__main__":
    unittest.main()
