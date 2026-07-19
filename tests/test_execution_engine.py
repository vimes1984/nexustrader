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

    @patch('ccxt.kraken')
    def test_sync_live_balance(self, mock_kraken):
        # Setup mock exchange instance
        mock_exchange = MagicMock()
        mock_kraken.return_value = mock_exchange
        
        # Mock balance info
        mock_exchange.fetch_balance.return_value = {
            'total': {
                'USD': 50.0,
                'BTC': 0.1,
                'ETH': 0.5
            }
        }
        
        # Mock fetch_tickers
        mock_exchange.fetch_tickers.return_value = {
            'BTC/USD': {'last': 50000.0},
            'ETH/USD': {'last': 3000.0},
            'SOL/USD': {'last': 100.0},
            'DOGE/USD': {'last': 0.1},
            'XRP/USD': {'last': 0.5}
        }
        
        # Configure execution engine for live mode
        self.engine.trading_mode = "live"
        self.engine.config = {
            "broker": "kraken",
            "api_credentials": {
                "api_key": "test-key",
                "api_secret": "test-secret"
            }
        }
        
        # Run sync balance
        self.engine.sync_live_balance()
        
        # Assert cash balance updated correctly
        self.assertEqual(self.engine.balance, 50.0)
        
        # Assert live equity includes BTC & ETH value: 50.0 + (0.1 * 50000) + (0.5 * 3000) = 6550.0
        self.assertEqual(self.engine.live_equity, 6550.0)

if __name__ == "__main__":
    unittest.main()
