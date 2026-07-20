import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import pandas as pd
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import strategy_engine

class TestStrategyEngine(unittest.TestCase):
    def test_ema_crossover_strategy(self):
        strat = strategy_engine.EMACrossoverStrategy()
        # Fast > Slow -> BUY
        self.assertEqual(strat.generate_signal({'macd': 1.5, 'macd_signal': 1.0}), 1.0)
        # Fast < Slow -> SELL
        self.assertEqual(strat.generate_signal({'macd': 0.5, 'macd_signal': 1.0}), -1.0)

    @patch('database.load_setting')
    def test_rsi_strategy(self, mock_load):
        mock_load.side_effect = lambda k, default: default
        strat = strategy_engine.RSIStrategy()
        # RSI < oversold -> BUY
        self.assertEqual(strat.generate_signal({'rsi': 25.0}), 1.0)
        # RSI > overbought -> SELL
        self.assertEqual(strat.generate_signal({'rsi': 75.0}), -1.0)

    def test_bb_breakout_strategy(self):
        strat = strategy_engine.BollingerBandsStrategy()
        # Close < Lower -> BUY
        self.assertEqual(strat.generate_signal({'close': 90.0, 'bb_lower': 95.0, 'bb_upper': 105.0}), 1.0)
        # Close > Upper -> SELL
        self.assertEqual(strat.generate_signal({'close': 110.0, 'bb_lower': 95.0, 'bb_upper': 105.0}), -1.0)

    @patch('database.load_setting')
    def test_kalman_trend_strategy(self, mock_load):
        mock_load.return_value = "0.001"
        strat = strategy_engine.KalmanTrendStrategy()
        # Initialize filter with a series of ticks
        for p in [100.0, 100.1, 100.2]:
            strat.generate_signal({'close': p})
            
        # Large upward price movement -> BUY
        self.assertEqual(strat.generate_signal({'close': 105.0}), 1.0)

    def test_ml_strategy_training_and_predict(self):
        strat = strategy_engine.MLPredictorStrategy()
        self.assertFalse(strat.is_trained)
        self.assertEqual(strat.generate_signal({'close': 100.0}), 0.0)

        # Train with a dummy dataframe
        dates = pd.date_range(start="2026-07-01", periods=100)
        df = pd.DataFrame({
            'close': [100.0 + i for i in range(100)],
            'rsi': [50.0]*100,
            'macd': [0.0]*100,
            'macd_signal': [0.0]*100,
            'sma_20': [100.0]*100,
            'sma_50': [100.0]*100,
            'bb_upper': [110.0]*100,
            'bb_lower': [90.0]*100
        }, index=dates)

        strat.train(df)
        self.assertTrue(strat.is_trained)

if __name__ == "__main__":
    unittest.main()
