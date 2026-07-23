import unittest
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from position_sizing import (
    estimate_metrics_from_trades,
    compute_kelly_fraction,
    compute_safe_fraction,
    volatility_adjusted_qty,
)
from evaluation.position_sizing import (
    compute_kelly_fraction as eval_compute_kelly_fraction,
    compute_safe_fraction as eval_compute_safe_fraction,
    estimate_metrics_from_trades as eval_estimate_metrics_from_trades,
    volatility_adjusted_qty as eval_volatility_adjusted_qty,
)


class TestPositionSizing(unittest.TestCase):
    """Tests for the root position_sizing module."""
    
    def test_compute_kelly_fraction_basic(self):
        """Test Kelly computation with reasonable values."""
        # 60% win rate, 2% avg win, 1% avg loss
        kelly = compute_kelly_fraction(0.6, 0.02, 0.01)
        # f* = (0.6*0.02 - 0.4*0.01) / (0.02*0.01) = (0.012 - 0.004) / 0.0002 = 40
        # Capped at 0.5
        self.assertAlmostEqual(kelly, 0.5, places=4)

    def test_compute_kelly_fraction_no_edge(self):
        """Test that negative edge returns 0."""
        # 50% win rate, 1% avg win, 2% avg loss (negative expectancy)
        kelly = compute_kelly_fraction(0.5, 0.01, 0.02)
        # f* = (0.5*0.01 - 0.5*0.02) / (0.01*0.02) = (0.005 - 0.01) / 0.0002 = -25
        self.assertAlmostEqual(kelly, 0.0, places=4)

    def test_compute_kelly_fraction_all_wins(self):
        """Test edge case: 100% win rate."""
        kelly = compute_kelly_fraction(1.0, 0.05, 0.01)
        self.assertGreater(kelly, 0)
        self.assertLessEqual(kelly, 0.5)

    def test_compute_kelly_fraction_all_losses(self):
        """Test edge case: 0% win rate."""
        kelly = compute_kelly_fraction(0.0, 0.01, 0.05)
        self.assertEqual(kelly, 0.0)

    def test_estimate_metrics_empty(self):
        """Test metrics estimation with no trades."""
        metrics = estimate_metrics_from_trades([])
        self.assertEqual(metrics["count"], 0)
        self.assertEqual(metrics["win_rate"], 0.5)

    def test_estimate_metrics_with_trades(self):
        """Test metrics estimation with sample trades."""
        trades = [
            {"pnl_percent": 0.05},
            {"pnl_percent": -0.02},
            {"pnl_percent": 0.03},
            {"pnl_percent": -0.01},
            {"pnl_percent": 0.02},
        ]
        metrics = estimate_metrics_from_trades(trades)
        self.assertEqual(metrics["count"], 5)
        self.assertAlmostEqual(metrics["win_rate"], 3/5)
        self.assertAlmostEqual(metrics["avg_win"], 0.03333, places=4)
        self.assertAlmostEqual(metrics["avg_loss"], 0.015, places=4)

    def test_compute_safe_fraction_cold_start(self):
        """Test cold-start default when insufficient trades."""
        result = compute_safe_fraction(0.5, 0.02, 0.01, n_trades=5)
        self.assertEqual(result["signal"], "cold_start_default")
        self.assertEqual(result["safe_fraction"], 0.05)

    def test_compute_safe_fraction_normal(self):
        """Test safe fraction with sufficient history."""
        result = compute_safe_fraction(0.6, 0.02, 0.01, n_trades=50)
        self.assertEqual(result["signal"], "aggressive")
        self.assertGreater(result["safe_fraction"], 0)

    def test_compute_safe_fraction_drawdown_halt(self):
        """Test that drawdown halts trading."""
        result = compute_safe_fraction(
            0.6, 0.02, 0.01, n_trades=50,
            current_drawdown_pct=20.0,  # Exceeds 15% limit
            drawdown_limit_pct=15.0,
        )
        self.assertEqual(result["signal"], "halted_drawdown")
        self.assertEqual(result["safe_fraction"], 0.0)

    def test_volatility_adjusted_qty_basic(self):
        """Test basic volatility-adjusted quantity calculation."""
        qty = volatility_adjusted_qty(
            capital=1000.0,
            risk_fraction=0.02,
            price=100.0,
            atr=5.0,
        )
        # risk_amount = 1000 * 0.02 = 20
        # qty = 20 / (5.0 * 1.0) = 4.0
        self.assertAlmostEqual(qty, 4.0, places=4)

    def test_volatility_adjusted_qty_no_atr(self):
        """Test fallback when ATR is zero — uses flat capital fraction."""
        qty = volatility_adjusted_qty(
            capital=1000.0,
            risk_fraction=0.02,
            price=100.0,
            atr=0.0,  # No volatility data
        )
        # Fallback: risk_amount / price = 20.0 / 100.0 = 0.2
        self.assertAlmostEqual(qty, 0.2, places=4)


class TestEvalPositionSizing(unittest.TestCase):
    """Tests for the evaluation/position_sizing module."""
    
    def test_eval_kelly_matches_root_kelly(self):
        """Test that both modules compute the same Kelly values."""
        test_cases = [
            (0.6, 0.02, 0.01),
            (0.5, 0.03, 0.015),
            (0.7, 0.01, 0.02),
            (0.55, 0.04, 0.025),
        ]
        for wr, aw, al in test_cases:
            root_kelly = compute_kelly_fraction(wr, aw, al)
            eval_kelly = eval_compute_kelly_fraction(wr, aw, al)
            self.assertAlmostEqual(root_kelly, eval_kelly, places=4,
                                   msg=f"Mismatch at wr={wr}, aw={aw}, al={al}")

    def test_eval_estimate_metrics_uses_pnl(self):
        """Test that eval module falls back to pnl when pnl_percent missing."""
        trades = [
            {"pnl": 50.0},
            {"pnl": -20.0},
        ]
        metrics = eval_estimate_metrics_from_trades(trades)
        self.assertEqual(metrics["count"], 2)
        self.assertAlmostEqual(metrics["win_rate"], 0.5)

    def test_eval_safe_fraction_max_allocation_in_output(self):
        """Test that eval safe_fraction includes max_allocation in output."""
        result = eval_compute_safe_fraction(0.6, 0.02, 0.01, n_trades=50)
        self.assertIn("max_allocation", result)
        self.assertEqual(result["max_allocation"], 0.15)

    def test_eval_volatility_adjusted_atr_zero(self):
        """Test eval module: ATR of zero returns 0."""
        qty = eval_volatility_adjusted_qty(1000.0, 0.02, 100.0, 0.0)
        self.assertEqual(qty, 0.0)


if __name__ == "__main__":
    unittest.main()
