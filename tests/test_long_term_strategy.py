import unittest
from unittest.mock import MagicMock, patch
import os
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock database module before importing long_term_strategy
sys.modules['database'] = MagicMock()
import database
database.load_setting = MagicMock(return_value="10000.0")
database.save_setting = MagicMock()

from long_term_strategy import LongTermStrategyLayer

class TestLongTermStrategy(unittest.TestCase):
    def setUp(self):
        database.load_setting.reset_mock()
        database.save_setting.reset_mock()
        database.load_setting.side_effect = lambda key, default=None: default
        
        self.layer = LongTermStrategyLayer(initial_shadow_balance=1000.0, transaction_fee_rate=0.001, slippage_rate=0.0)
        self.layer.active_positions = {}

    def test_shadow_position_take_profit_buy(self):
        # Setup active buy position
        self.layer.active_positions["BTC-USD"] = {
            "id": 1,
            "symbol": "BTC-USD",
            "direction": "BUY",
            "quantity": 0.1,
            "entry_price": 50000.0,
            "tp_price": 52000.0,
            "sl_price": 49000.0,
            "atr_at_entry": 500.0,
            "entry_time": time.time()
        }
        
        # Price hits TP
        res = self.layer.update_shadow_positions("BTC-USD", 52100.0)
        
        self.assertIsNotNone(res)
        self.assertEqual(res["event"], "closed")
        self.assertEqual(res["exit_reason"], "Take Profit Hit")
        
        # Profit: (52000 - 50000) * 0.1 = 200.0
        # Transaction Fee: 52000 * 0.1 * 0.001 = 5.2
        # Net Profit: 194.80
        self.assertAlmostEqual(res["pnl"], 194.80)
        self.assertNotIn("BTC-USD", self.layer.active_positions)

    def test_shadow_position_stop_loss_buy(self):
        # Setup active buy position
        self.layer.active_positions["ETH-USD"] = {
            "id": 2,
            "symbol": "ETH-USD",
            "direction": "BUY",
            "quantity": 1.0,
            "entry_price": 3000.0,
            "tp_price": 3200.0,
            "sl_price": 2900.0,
            "atr_at_entry": 100.0,
            "entry_time": time.time()
        }
        
        # Price hits SL
        res = self.layer.update_shadow_positions("ETH-USD", 2850.0)
        
        self.assertIsNotNone(res)
        self.assertEqual(res["event"], "closed")
        self.assertEqual(res["exit_reason"], "Stop Loss Hit")
        
        # Loss: (2900 - 3000) * 1.0 = -100.0
        # Transaction Fee: 2900 * 1.0 * 0.001 = 2.9
        # Net Profit: -102.90
        self.assertAlmostEqual(res["pnl"], -102.90)

    def test_drawdown_circuit_breaker(self):
        # Trigger drawdown by setting balance low
        self.layer.peak_balance = 1000.0
        self.layer.balance = 850.0 # 15% drawdown
        
        # Mock inputs
        row = {"close": 100.0, "atr": 2.0}
        ensemble = MagicMock()
        learner = MagicMock()
        
        res = self.layer.evaluate_long_term_rules("SOL-USD", 100.0, row, None, ensemble, learner)
        self.assertIsNone(res) # Blocked by circuit breaker!

if __name__ == "__main__":
    unittest.main()
