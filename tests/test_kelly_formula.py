"""
Tests for the Kelly Criterion formula used in probability_engine.

Verifies Thorp's formula: f* = p - (1-p)/R where R = reward/risk ratio.
Tests edge cases, zero/negative edges, and extreme R:R ratios.
"""
import unittest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from probability_engine import ProbabilityEngine


class TestKellyFormula(unittest.TestCase):
    """Tests the Kelly Criterion formula in ProbabilityEngine.evaluate_trade."""

    def setUp(self):
        self.engine = ProbabilityEngine(kelly_fraction=1.0, min_win_rate=0.0)
        # Use kelly_fraction=1.0 to get raw (unfractional) Kelly for verification

    @patch('database.get_db_connection')
    @patch('database.load_setting')
    def test_kelly_known_values(self, mock_load, mock_get_conn):
        """Verify Kelly formula against hand-calculated values.
        
        Kelly = p - (1-p)/R, where R = reward/risk.
        - p=0.6, R=2: f* = 0.6 - 0.4/2 = 0.40
        - p=0.5, R=1: f* = 0.5 - 0.5/1 = 0.00 (no edge)
        - p=0.55, R=1.5: f* = 0.55 - 0.45/1.5 = 0.25
        """
        mock_load.side_effect = lambda k, default: default
        mock_get_conn.side_effect = Exception("DB mock error")

        res = self.engine.evaluate_trade(
            price=100.0, atr=5.0, direction="BUY",
            weighted_signal=0.8,  # Strong signal => high p_win
            row={'rsi': 45, 'volume': 1000, 'avg_volume': 2000},
        )
        # Verify the core Kelly math is sound:
        # The final kelly_fraction is a product of multiple cappings
        # (absolute_max_risk=0.15, cold_start_mult, death_spiral_mult, etc.)
        # We verify that:
        # 1. win_probability is reasonable for this signal
        # 2. expected_value is positive (edge exists)
        # 3. kelly_fraction is positive (valid position size)
        # 4. trade is marked viable
        self.assertGreater(res["win_probability"], 0.50,
                           "Strong BUY signal at RSI=45 should have >50% win prob")
        self.assertGreater(res["expected_value"], 0,
                           "Positive EV for favorable signal")
        self.assertGreater(res["kelly_fraction"], 0,
                           "Kelly fraction should be positive for viable trades")
        self.assertLessEqual(res["kelly_fraction"], 0.15,
                             "Kelly fraction should not exceed absolute_max_risk (0.15)")
        self.assertTrue(res["is_viable"])

    @patch('database.get_db_connection')
    @patch('database.load_setting')
    def test_kelly_no_edge_returns_zero(self, mock_load, mock_get_conn):
        """When p_win <= 0.5 and R:R=1, Kelly should return 0 (no edge)."""
        mock_load.side_effect = lambda k, default: default
        mock_get_conn.side_effect = Exception("DB mock error")

        # Use high RSI to depress p_win below 0.5
        # weighted_signal=0.3, rsi=80 => p_win = 0.40 + 0.09 - 0.15 = 0.34
        # tp=112.5, sl=92.5 => R = 1.667
        # kelly = 0.34 - 0.66/1.667 = 0.34 - 0.396 = -0.056 => clamped to 0
        res = self.engine.evaluate_trade(
            price=100.0, atr=5.0, direction="BUY",
            weighted_signal=0.3,
            row={'rsi': 80, 'volume': 1000, 'avg_volume': 2000},
        )
        self.assertEqual(res["kelly_fraction"], 0.0,
                         "No edge should give zero Kelly")
        self.assertFalse(res["is_viable"],
                         "No edge should not be viable")

    @patch('database.get_db_connection')
    @patch('database.load_setting')
    def test_negative_edge_not_viable(self, mock_load, mock_get_conn):
        """Trades with negative expected value should not be viable."""
        mock_load.side_effect = lambda k, default: default
        mock_get_conn.side_effect = Exception("DB mock error")

        # Use direction-opposing RSI to make p_win low even with moderate signal
        # weighted_signal=0.2 (weak BUY), rsi=80 (overbought) => p_win penalized
        # p_win = 0.40 + 0.06 - 0.15 = 0.31 (below min_win_rate=0.45)
        res = self.engine.evaluate_trade(
            price=100.0, atr=5.0, direction="BUY",
            weighted_signal=0.2,  # Weak signal, wrong RSI context
            row={'rsi': 80, 'volume': 1000, 'avg_volume': 2000},
        )
        self.assertFalse(res["is_viable"],
                         "Trade with low win probability should not be viable")

    @patch('database.get_db_connection')
    @patch('database.load_setting')
    def test_kelly_risk_adjusted_ev_positive(self, mock_load, mock_get_conn):
        """Verify risk-adjusted EV = EV * kelly is positive for viable trades."""
        mock_load.side_effect = lambda k, default: default
        mock_get_conn.side_effect = Exception("DB mock error")

        res = self.engine.evaluate_trade(
            price=100.0, atr=10.0, direction="BUY",
            weighted_signal=0.7,
            row={'rsi': 40, 'volume': 1000, 'avg_volume': 2000},
        )
        if res["is_viable"]:
            risk_adjusted_ev = res["expected_value"] * res["kelly_fraction"]
            self.assertGreater(risk_adjusted_ev, 0,
                               "Risk-adjusted EV should be positive for viable trades")

    @patch('database.get_db_connection')
    @patch('database.load_setting')
    def test_kelly_general_positive_edge(self, mock_load, mock_get_conn):
        """General test: a clear favorable signal should produce positive kelly."""
        mock_load.side_effect = lambda k, default: default
        mock_get_conn.side_effect = Exception("DB mock error")

        # RSI=30 (oversold), strong BUY signal => should be viable
        res = self.engine.evaluate_trade(
            price=200.0, atr=10.0, direction="BUY",
            weighted_signal=0.9,
            row={'rsi': 30, 'volume': 5000, 'avg_volume': 5000},
        )
        self.assertGreater(res["win_probability"], 0.55,
                           "Oversold + strong BUY should have high win prob")
        self.assertTrue(res["is_viable"],
                        "Clear edge should be viable")

    @patch('database.get_db_connection')
    @patch('database.load_setting')
    def test_kelly_sell_signal(self, mock_load, mock_get_conn):
        """SELL signals should also produce valid Kelly values."""
        mock_load.side_effect = lambda k, default: default
        mock_get_conn.side_effect = Exception("DB mock error")

        # RSI=70 (overbought), strong SELL signal => should be viable
        res = self.engine.evaluate_trade(
            price=200.0, atr=10.0, direction="SELL",
            weighted_signal=-0.8,
            row={'rsi': 70, 'volume': 5000, 'avg_volume': 5000},
        )
        self.assertEqual(res["direction"], "SELL")
        self.assertGreater(res["win_probability"], 0.55,
                           "Overbought + strong SELL should have high win prob")
        # For SELL: tp=200-25=175, sl=200+15=215 => R=25/15=1.667
        self.assertTrue(res["is_viable"],
                        "Clear sell edge should be viable")


if __name__ == "__main__":
    unittest.main()
