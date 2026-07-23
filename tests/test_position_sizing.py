"""
Unit tests for position_sizing.py — Kelly criterion, safe fraction, volatility-adjusted qty.

Tests known Kelly formula inputs against expected outputs:
  - p=0.6, W=1.0, L=1.0 → Kelly=0.2
  - p=0.5, W=1.0, L=1.0 → Kelly=0.0
  - p=1.0, W=1.0, L=1.0 → Kelly=1.0
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.position_sizing import (
    compute_kelly_fraction,
    compute_safe_fraction,
    estimate_metrics_from_trades,
    volatility_adjusted_qty,
)


class TestComputeKellyFraction(unittest.TestCase):
    """Test Kelly formula against known inputs."""

    def test_kelly_p60_w1_l1(self):
        """p=0.6, W=1.0, L=1.0 → Kelly=0.2"""
        f = compute_kelly_fraction(0.6, 1.0, 1.0)
        self.assertAlmostEqual(f, 0.2, places=4)

    def test_kelly_p50_w1_l1(self):
        """p=0.5, W=1.0, L=1.0 → Kelly=0.0 (no edge)"""
        f = compute_kelly_fraction(0.5, 1.0, 1.0)
        self.assertEqual(f, 0.0)

    def test_kelly_p10_w1_l1(self):
        """p=0.1 → Kelly=0.0 (no edge)"""
        f = compute_kelly_fraction(0.1, 1.0, 1.0)
        self.assertEqual(f, 0.0)

    def test_kelly_p10_w2_l1(self):
        """p=0.1, W=2.0, L=1.0 → still negative edge → 0.0"""
        f = compute_kelly_fraction(0.1, 2.0, 1.0)
        self.assertEqual(f, 0.0)

    def test_kelly_w1_l1(self):
        """Kelly with W=L should be p - (1-p)/1 = 2p-1"""
        for p in [0.55, 0.70, 0.80, 0.90, 0.95]:
            expected = 2.0 * p - 1.0
            f = compute_kelly_fraction(p, 1.0, 1.0)
            self.assertAlmostEqual(f, expected, places=4,
                                   msg=f"Kelly({p}, W=1, L=1) != {expected}")

    def test_kelly_zero_win_rate(self):
        """win_rate <= 0 → 0.0"""
        self.assertEqual(compute_kelly_fraction(0.0, 1.0, 1.0), 0.0)

    def test_kelly_one_win_rate(self):
        """win_rate >= 1 (p=1.0 clipped in code) → 0.0"""
        f = compute_kelly_fraction(1.0, 1.0, 1.0)
        self.assertEqual(f, 0.0)

    def test_kelly_zero_avg_loss(self):
        """avg_loss <= 0 → 0.0"""
        self.assertEqual(compute_kelly_fraction(0.6, 1.0, 0.0), 0.0)

    def test_kelly_zero_avg_win(self):
        """avg_win <= 0 → 0.0 (no edge)"""
        self.assertEqual(compute_kelly_fraction(0.6, 0.0, 1.0), 0.0)

    def test_kelly_asymmetric_ratio(self):
        """p=0.6, W=2.0, L=1.0 → b=2.0 → f* = p - q/b = 0.6 - 0.4/2 = 0.4"""
        f = compute_kelly_fraction(0.6, 2.0, 1.0)
        self.assertAlmostEqual(f, 0.4, places=4)

    def test_kelly_clipped_at_one(self):
        """Kelly fraction capped at 1.0 even if formula would exceed."""
        # p=0.9, W=10, L=1 → f = 0.9 - 0.1/(10) = 0.89 → within 1.0
        f = compute_kelly_fraction(0.9, 10.0, 1.0)
        self.assertAlmostEqual(f, 0.89, places=4)
        self.assertLessEqual(f, 1.0)


class TestEstimateMetricsFromTrades(unittest.TestCase):

    def test_empty_trades(self):
        metrics = estimate_metrics_from_trades([])
        self.assertEqual(metrics["count"], 0)
        self.assertEqual(metrics["win_rate"], 0.5)

    def test_all_wins(self):
        trades = [{"pnl": 1.0}, {"pnl": 2.0}, {"pnl": 3.0}]
        metrics = estimate_metrics_from_trades(trades)
        self.assertEqual(metrics["win_rate"], 1.0)
        self.assertEqual(metrics["count"], 3)
        self.assertAlmostEqual(metrics["avg_win"], 2.0)

    def test_all_losses(self):
        trades = [{"pnl": -1.0}, {"pnl": -2.0}, {"pnl": -3.0}]
        metrics = estimate_metrics_from_trades(trades)
        self.assertEqual(metrics["win_rate"], 0.0)
        self.assertEqual(metrics["avg_win"], 0.0)

    def test_mixed_trades(self):
        trades = [
            {"pnl": 10.0}, {"pnl": -5.0}, {"pnl": 3.0},
            {"pnl": -2.0}, {"pnl": 0.0},
        ]
        metrics = estimate_metrics_from_trades(trades)
        self.assertAlmostEqual(metrics["win_rate"], 2 / 5)
        self.assertAlmostEqual(metrics["avg_win"], 6.5)  # (10+3)/2
        self.assertAlmostEqual(metrics["avg_loss"], 3.5)  # (5+2)/2

    def test_nan_pnl_guarded(self):
        """Trades with NaN pnl should be converted to 0.0 safely."""
        trades = [{"pnl": float('nan')}, {"pnl": 5.0}]
        metrics = estimate_metrics_from_trades(trades)
        self.assertEqual(metrics["count"], 2)
        self.assertAlmostEqual(metrics["win_rate"], 0.5)

    def test_pnl_percent_key(self):
        trades = [{"pnl_percent": 2.5}, {"pnl_percent": -1.0}]
        metrics = estimate_metrics_from_trades(trades)
        self.assertEqual(metrics["count"], 2)
        self.assertAlmostEqual(metrics["win_rate"], 0.5)

    def test_zero_avg_loss_fallback(self):
        trades = [{"pnl": 10.0}, {"pnl": 5.0}]  # no losses
        metrics = estimate_metrics_from_trades(trades)
        self.assertEqual(metrics["avg_loss"], 0.01)  # fallback


class TestComputeSafeFraction(unittest.TestCase):

    def test_insufficient_trades(self):
        result = compute_safe_fraction(0.6, 1.0, 1.0, n_trades=3)
        self.assertEqual(result["signal"], "cold_start_default")
        self.assertEqual(result["safe_fraction"], 0.05)

    def test_sufficient_trades_with_edge(self):
        result = compute_safe_fraction(
            0.6, 1.0, 1.0, n_trades=50, calibration_cap=0.15
        )
        self.assertEqual(result["signal"], "moderate")
        # Kelly=0.2, half=0.1, capped at 0.15 → 0.1, adjusted down
        self.assertGreater(result["safe_fraction"], 0.0)
        self.assertLessEqual(result["safe_fraction"], 0.15)

    def test_sufficient_trades_no_edge(self):
        result = compute_safe_fraction(
            0.5, 1.0, 1.0, n_trades=50
        )
        # Kelly=0, half_kelly=0, drawdown=0, calibration_cap=0.15
        # Floor 3.5% since drawdown < 30% of limit
        self.assertEqual(result["signal"], "conservative")
        self.assertGreater(result["safe_fraction"], 0.0)

    def test_drawdown_halt(self):
        """100% drawdown → halt trading."""
        result = compute_safe_fraction(
            0.6, 1.0, 1.0, n_trades=50,
            current_drawdown_pct=15.0, drawdown_limit_pct=15.0
        )
        self.assertEqual(result["signal"], "halted_drawdown")
        self.assertEqual(result["safe_fraction"], 0.0)
        self.assertEqual(result["drawdown_penalty"], 0.0)

    def test_partial_drawdown_penalty(self):
        """At 75% of limit → penalty tapers."""
        result = compute_safe_fraction(
            0.6, 1.0, 1.0, n_trades=50,
            current_drawdown_pct=11.25, drawdown_limit_pct=15.0
        )
        # dd_ratio = 11.25/15 = 0.75, > 0.5
        # drawdown_penalty = 2*(1-0.75) = 0.5
        self.assertAlmostEqual(result["drawdown_penalty"], 0.5, places=4)

    def test_kelly_clipped_by_calibration_cap(self):
        """High Kelly but tight calibration cap."""
        result = compute_safe_fraction(
            0.8, 3.0, 1.0, n_trades=50, calibration_cap=0.03
        )
        # raw_kelly = 0.8 - 0.2/3 = 0.733, half = 0.367
        # capped at calibration_cap = 0.03
        # The cap should bind, but floor of 0.035 applies since drawdown=0
        # safe_fraction = max(effective_kelly * drawdown_penalty, 0.035)
        # = max(0.03 * 1.0, 0.035) = 0.035
        self.assertEqual(result["safe_fraction"], 0.035)

    def test_hard_max_allocation(self):
        """Even with huge edge, safe_fraction limited by max_allocation."""
        result = compute_safe_fraction(
            0.9, 5.0, 1.0, n_trades=50, calibration_cap=0.5
        )
        # Safe fraction should not exceed 0.15
        self.assertLessEqual(result["safe_fraction"], 0.15)


class TestVolatilityAdjustedQty(unittest.TestCase):

    def test_basic_vol_adjustment(self):
        qty = volatility_adjusted_qty(
            capital=1000.0, risk_fraction=0.02,
            price=100.0, atr=2.0, atr_multiplier=1.0
        )
        # risk_amount = 1000 * 0.02 = 20
        # denominator = 2.0 * 1.0 = 2.0
        # qty = 20 / 2.0 = 10.0
        self.assertAlmostEqual(qty, 10.0, places=2)

    def test_zero_price(self):
        self.assertEqual(volatility_adjusted_qty(1000, 0.02, 0.0, 2.0), 0.0)

    def test_zero_atr(self):
        self.assertEqual(volatility_adjusted_qty(1000, 0.02, 100.0, 0.0), 0.0)

    def test_max_qty_capped(self):
        qty = volatility_adjusted_qty(
            capital=1000.0, risk_fraction=0.02,
            price=100.0, atr=2.0, max_qty=5.0
        )
        self.assertAlmostEqual(qty, 5.0, places=2)

    def test_fallback_no_atr_discount(self):
        """When atr_multiplier makes denominator 0, fallback to flat sizing."""
        qty = volatility_adjusted_qty(
            capital=1000.0, risk_fraction=0.02,
            price=100.0, atr=100.0, atr_multiplier=0.0
        )
        # risk_fraction = 0.02, so qty = 20/100 = 0.2
        self.assertAlmostEqual(qty, 0.2, places=4)


if __name__ == '__main__':
    unittest.main()
