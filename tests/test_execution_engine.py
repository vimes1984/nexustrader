import unittest
from unittest.mock import patch, MagicMock
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock database module before importing execution_engine
sys.modules['database'] = MagicMock()
import database
database.load_setting = MagicMock(return_value=None)
database.save_setting = MagicMock()
database.init_db = MagicMock()

from execution_engine import ExecutionEngine

class TestExecutionEngine(unittest.TestCase):
    def setUp(self):
        # Clear mock histories
        database.load_setting.reset_mock()
        database.save_setting.reset_mock()
        
        # Instantiate engine
        self.engine = ExecutionEngine(initial_balance=100.0)
        self.engine.pending_limit_orders = {}
        self.engine.active_positions = {}

    def test_initialization(self):
        self.assertEqual(self.engine.initial_balance, 100.0)
        self.assertEqual(self.engine.transaction_fee_rate, 0.001)

    def test_open_position_paper_limit_order(self):
        symbol = "BTC-USD"
        evaluation = {
            "direction": "BUY",
            "entry_price": 50000.0,
            "take_profit": 52000.0,
            "stop_loss": 49000.0,
            "kelly_fraction": 0.1
        }
        signals = [1, 0, -1]

        # Ensure not in cooldown
        database.load_setting.return_value = "0.0"

        res = self.engine.open_position(symbol, evaluation, signals)
        self.assertTrue(res)
        
        # Check order was queued in pending limit orders
        self.assertIn(symbol, self.engine.pending_limit_orders)
        order = self.engine.pending_limit_orders[symbol]
        self.assertEqual(order["direction"], "BUY")
        self.assertEqual(order["limit_price"], 50000.0)
        self.assertEqual(order["quantity"], 10.0 / 50000.0) # 10% of 100 balance

    def test_limit_order_fill_simulation(self):
        symbol = "ETH-USD"
        self.engine.pending_limit_orders[symbol] = {
            "symbol": symbol,
            "direction": "BUY",
            "limit_price": 2000.0,
            "quantity": 0.05,
            "take_profit": 2100.0,
            "stop_loss": 1950.0,
            "strategy_signals": [1, 1],
            "fee": 0.1
        }

        # Price goes below limit (fill!)
        self.engine.update_positions(symbol, 1990.0)
        
        # Position should transition from pending to active
        self.assertNotIn(symbol, self.engine.pending_limit_orders)
        self.assertIn(symbol, self.engine.active_positions)
        
        pos = self.engine.active_positions[symbol]
        self.assertEqual(pos["entry_price"], 2000.0)
        self.assertEqual(pos["quantity"], 0.05)

    def test_active_position_take_profit_hit(self):
        import time
        symbol = "SOL-USD"
        self.engine.active_positions[symbol] = {
            "symbol": symbol,
            "direction": "BUY",
            "entry_price": 100.0,
            "quantity": 1.0,
            "take_profit": 110.0,
            "stop_loss": 95.0,
            "entry_time": time.time(),
            "strategy_signals": [1, 0, -1],
            "fee_paid": 0.1
        }
        
        self.engine.learning_callback = MagicMock()

        # Price hits take profit
        self.engine.update_positions(symbol, 112.0)
        
        # Position should be closed
        self.assertNotIn(symbol, self.engine.active_positions)
        self.engine.learning_callback.assert_called_once()

if __name__ == "__main__":
    unittest.main()
