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

    def test_eval_safe_fraction_without_drawdown_min_floor(self):
        """Safe fraction should apply min floor when drawdown=0."""
        result = eval_compute_safe_fraction(0.6, 0.02, 0.01, n_trades=50)
        # kelly = (0.6*0.02 - 0.4*0.01)/(0.02*0.01) = (0.012-0.004)/0.0002 = 40
        # capped at 0.5, half = 0.25, calibration_cap=0.15 -> 0.15
        # drawdown_penalty=1.0, min floor 0.02
        self.assertGreaterEqual(result["safe_fraction"], 0.02)
        self.assertLessEqual(result["safe_fraction"], 0.25)


class TestPositionSizingWith1000Balance(unittest.TestCase):
    """Position sizing scenarios with a $1000 account balance."""

    def test_safe_fraction_gives_reasonable_dollars(self):
        """With $1000 and 60% win rate, the safe fraction should translate
        to a reasonable dollar amount to risk (within bounds)."""
        result = compute_safe_fraction(
            win_rate=0.6, avg_win=0.02, avg_loss=0.01, n_trades=50
        )
        risk_dollars = 1000.0 * result["safe_fraction"]
        self.assertGreaterEqual(risk_dollars, 10.0,
                                msg=f"${risk_dollars:.2f} risk too small for $1000")
        self.assertLessEqual(risk_dollars, 250.0,
                             msg=f"${risk_dollars:.2f} exceeds 25% cap")

    def test_vol_adjusted_position_with_1000(self):
        """With $1000, 2% risk_fraction, $50 price, $2 ATR.
        risk_amount = $20, qty = 20/(2*1) = 10 units."""
        qty = volatility_adjusted_qty(
            capital=1000.0, risk_fraction=0.02,
            price=50.0, atr=2.0, atr_multiplier=1.0
        )
        position_value = qty * 50.0
        self.assertAlmostEqual(qty, 10.0, places=2)
        self.assertAlmostEqual(position_value, 500.0, places=2)

    def test_cold_start_minimum_dollars(self):
        """Cold-start with $1000 should give $50 minimum risk (5%)."""
        result = compute_safe_fraction(
            win_rate=0.5, avg_win=0.02, avg_loss=0.01, n_trades=5
        )
        self.assertEqual(result["signal"], "cold_start_default")
        risk_dollars = 1000.0 * result["safe_fraction"]
        self.assertAlmostEqual(risk_dollars, 50.0, places=2)


if __name__ == "__main__":
    unittest.main()
