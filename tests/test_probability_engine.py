import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import sqlite3
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from probability_engine import ProbabilityEngine

class TestProbabilityEngine(unittest.TestCase):
    def setUp(self):
        self.engine = ProbabilityEngine(kelly_fraction=0.1, min_win_rate=0.45)

    def test_risk_modes(self):
        self.engine.set_risk_mode("conservative")
        self.assertEqual(self.engine.kelly_fraction, 0.1)
        self.assertEqual(self.engine.max_cap, 0.05)
        
        self.engine.set_risk_mode("aggressive")
        self.assertEqual(self.engine.kelly_fraction, 0.3)
        self.assertEqual(self.engine.max_cap, 0.20)
        
        self.engine.set_risk_mode("hyper_growth")
        self.assertEqual(self.engine.kelly_fraction, 0.5)
        self.assertEqual(self.engine.max_cap, 0.50)
        
        with self.assertRaises(ValueError):
            self.engine.set_risk_mode("invalid_mode")

    @patch('database.load_setting')
    def test_calculate_atr_bounds(self, mock_load):
        mock_load.side_effect = lambda k, default: default
        # Buy bounds
        tp, sl = self.engine.calculate_atr_bounds(100.0, 5.0, "BUY")
        self.assertAlmostEqual(tp, 112.5)
        self.assertAlmostEqual(sl, 92.5)
        
        # Sell bounds
        tp, sl = self.engine.calculate_atr_bounds(100.0, 5.0, "SELL")
        self.assertAlmostEqual(tp, 87.5)
        self.assertAlmostEqual(sl, 107.5)

    def test_estimate_win_probability(self):
        # High signal strength should increase win probability
        p_win = self.engine.estimate_win_probability(0.8, {'rsi': 50})
        self.assertGreater(p_win, 0.5)
        
        # High RSI on BUY should reduce probability
        p_win_rsi_high = self.engine.estimate_win_probability(0.8, {'rsi': 75})
        self.assertLess(p_win_rsi_high, p_win)

        # Historical returns empirical odds blending
        history_data = {
            'rsi': [72]*60,
            'close': [10.0 + i * 0.1 for i in range(60)]
        }
        df = pd.DataFrame(history_data)
        p_win_empirical = self.engine.estimate_win_probability(0.8, {'rsi': 72}, history_df=df)
        self.assertTrue(0.0 <= p_win_empirical <= 1.0)

    @patch('database.get_db_connection')
    @patch('database.load_setting')
    def test_evaluate_trade(self, mock_load, mock_get_conn):
        mock_load.side_effect = lambda k, default: default
        mock_get_conn.side_effect = Exception("DB mock error")
        
        res = self.engine.evaluate_trade(
            price=100.0,
            atr=5.0,
            direction="BUY",
            weighted_signal=0.5,
            row={'rsi': 50}
        )
        self.assertEqual(res["direction"], "BUY")
        self.assertEqual(res["entry_price"], 100.0)
        self.assertGreater(res["take_profit"], 100.0)
        self.assertLess(res["stop_loss"], 100.0)
        self.assertTrue("is_viable" in res)

if __name__ == "__main__":
    unittest.main()
