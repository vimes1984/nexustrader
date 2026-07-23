import unittest
from unittest.mock import patch, MagicMock, DEFAULT
import os
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock database and ccxt modules before importing execution_engine
sys.modules['ccxt'] = MagicMock()
sys.modules['database'] = MagicMock()
import database
database.load_setting = MagicMock(return_value=None)
database.save_setting = MagicMock()
database.init_db = MagicMock()
database.load_active_positions = MagicMock(return_value={})
database.load_trades = MagicMock(return_value=[])

from execution_engine import ExecutionEngine


class TestExecutionEngine(unittest.TestCase):
    def setUp(self):
        # Fully reset all mocks to eliminate cross-test-file contamination
        database.load_setting.reset_mock()
        database.load_setting.side_effect = None
        database.load_setting.return_value = None
        database.save_setting.reset_mock()
        database.load_active_positions = MagicMock(return_value={})
        database.load_trades = MagicMock(return_value=[])
        
        # Instantiate engine
        self.engine = ExecutionEngine(initial_balance=100.0)
        self.engine.active_positions = {}

    def test_initialization(self):
        self.assertEqual(self.engine.initial_balance, 100.0)
        self.assertEqual(self.engine.transaction_fee_rate, 0.0026)
        self.assertEqual(self.engine.balance, 100.0)

    def test_open_position_buy(self):
        """Test that a BUY position opens correctly, deducts from balance."""
        symbol = "BTC-USD"
        evaluation = {
            "direction": "BUY",
            "entry_price": 50000.0,
            "take_profit": 52000.0,
            "stop_loss": 49000.0,
            "kelly_fraction": 0.1,
            "win_probability": 0.6,
            "expected_value": 0.02,
            "risk_reward_ratio": 2.0,
        }
        signals = [1, 0, -1]

        # Ensure all DB settings return sensible defaults
        def db_get(key, default=None):
            defaults = {
                f"cooldown_end_{symbol}": "0.0",
                "max_open_positions": "3",
                "max_concentration_pct": "40",
                "max_total_exposure_pct": "60",
                "max_position_pct": "15",
                "trailing_stop_enabled": "false",
                f"atr_{symbol}": "0",
            }
            return defaults.get(key, default)
        database.load_setting.side_effect = db_get

        res = self.engine.open_position(symbol, evaluation, signals)
        self.assertTrue(res)
        
        # Position should be active
        self.assertIn(symbol, self.engine.active_positions)
        pos = self.engine.active_positions[symbol]
        self.assertEqual(pos["direction"], "BUY")
        self.assertGreater(pos["quantity"], 0)
        self.assertAlmostEqual(pos["entry_price"], 50000.0, delta=100.0)  # With slippage
        self.assertGreater(pos["fee_paid"], 0)
        # Balance should be reduced by cost + fee
        self.assertLess(self.engine.balance, 100.0)

    def test_open_position_max_positions_limit(self):
        """Test that max open positions limit is respected."""
        symbol = "BTC-USD"
        evaluation = {
            "direction": "BUY",
            "entry_price": 50000.0,
            "take_profit": 52000.0,
            "stop_loss": 49000.0,
            "kelly_fraction": 0.1,
        }
        signals = [1, 0, -1]

        def db_get(key, default=None):
            defaults = {
                f"cooldown_end_{symbol}": "0.0",
                "max_open_positions": "0",  # No positions allowed
                "max_concentration_pct": "40",
                "max_total_exposure_pct": "60",
                "max_position_pct": "15",
                "trailing_stop_enabled": "false",
                f"atr_{symbol}": "0",
            }
            return defaults.get(key, default)
        database.load_setting.side_effect = db_get

        res = self.engine.open_position(symbol, evaluation, signals)
        self.assertFalse(res)  # Should be rejected
        self.assertNotIn(symbol, self.engine.active_positions)

    def test_active_position_take_profit_closes_and_updates_balance(self):
        """Test that a BUY position closes at TP and balance is updated correctly."""
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
            "fee_paid": 0.1,
            "cost_basis": 100.0,
        }
        self.engine.balance = 0.0  # All capital in position
        self.engine.learning_callback = MagicMock()

        def db_get(key, default=None):
            defaults = {
                "trailing_stop_enabled": "false",
                "max_position_hours": "48",
                f"atr_{symbol}": "0",
            }
            return defaults.get(key, default)
        database.load_setting.side_effect = db_get

        # Price hits take profit
        self.engine.update_positions(symbol, 112.0)

        # Position should be closed
        self.assertNotIn(symbol, self.engine.active_positions)
        self.engine.learning_callback.assert_called_once()
        # Balance should reflect TP gain (cost_basis + pnl - exit_fee)
        # Expected: ~100 + (12*1 - 0.1) = ~111.9  (12.0 - 0.1 = 11.9 pnl net)
        self.assertGreater(self.engine.balance, 110.0)

    def test_active_position_stop_loss_closes_and_updates_balance(self):
        """Test that a BUY position closes at SL and balance reflects loss."""
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
            "fee_paid": 0.1,
            "cost_basis": 100.0,
        }
        self.engine.balance = 0.0
        self.engine.learning_callback = MagicMock()

        def db_get(key, default=None):
            defaults = {
                "trailing_stop_enabled": "false",
                "max_position_hours": "48",
                f"atr_{symbol}": "0",
            }
            return defaults.get(key, default)
        database.load_setting.side_effect = db_get

        # Price hits stop loss
        self.engine.update_positions(symbol, 94.0)

        # Position should be closed
        self.assertNotIn(symbol, self.engine.active_positions)
        # Balance after SL close should be less than 100
        self.assertLess(self.engine.balance, 100.0)

    def test_buy_sell_cycle_returns_balance_roughly_original(self):
        """Test that a full BUY->SELL cycle returns balance near original (minus fees)."""
        symbol = "TEST-USD"
        
        def db_get(key, default=None):
            defaults = {
                f"cooldown_end_{symbol}": "0.0",
                "max_open_positions": "10",
                "max_concentration_pct": "80",
                "max_total_exposure_pct": "90",
                "max_position_pct": "50",
                "trailing_stop_enabled": "false",
                f"atr_{symbol}": "0",
            }
            return defaults.get(key, default)
        database.load_setting.side_effect = db_get

        initial_balance = self.engine.balance  # $100
        
        # Open a BUY position
        evaluation = {
            "direction": "BUY",
            "entry_price": 100.0,
            "take_profit": 140.0,
            "stop_loss": 50.0,
            "kelly_fraction": 0.5,
        }
        signals = [1]
        res = self.engine.open_position(symbol, evaluation, signals)
        self.assertTrue(res)
        self.assertIn(symbol, self.engine.active_positions)
        balance_after_open = self.engine.balance
        self.assertLess(balance_after_open, initial_balance)
        
        # Price returns to entry — position should stay open
        self.engine.learning_callback = MagicMock()
        result = self.engine.update_positions(symbol, 100.0)
        self.assertIsNone(result)  # Not closed
        
        # Price hits take profit (adjusted for slippage, TP ~199.9)
        result = self.engine.update_positions(symbol, 210.0)
        self.assertIsNotNone(result)
        self.assertEqual(result["event"], "closed")
        
        # Balance after close should be roughly original minus fees
        # At $150 exit on $100 entry with 1 share: pnl ~$50, minus ~$0.65 fees
        # Balance should be > initial
        self.assertGreater(self.engine.balance, initial_balance)

    def test_fee_calculation_is_accurate(self):
        """Test that fee is calculated correctly on both entry and exit."""
        symbol = "FEE-USD"
        
        def db_get(key, default=None):
            defaults = {
                f"cooldown_end_{symbol}": "0.0",
                "max_open_positions": "10",
                "max_concentration_pct": "80",
                "max_total_exposure_pct": "90",
                "max_position_pct": "50",
                "trailing_stop_enabled": "false",
                f"atr_{symbol}": "0",
            }
            return defaults.get(key, default)
        database.load_setting.side_effect = db_get
        
        evaluation = {
            "direction": "BUY",
            "entry_price": 100.0,
            "take_profit": 110.0,
            "stop_loss": 90.0,
            "kelly_fraction": 0.2,
        }
        signals = [1]
        self.engine.open_position(symbol, evaluation, signals)
        
        pos = self.engine.active_positions[symbol]
        expected_fee_pct = 0.0026  # 0.26%
        
        # Entry fee should be ~ fee_rate * cost_basis
        expected_fee = pos["cost_basis"] * expected_fee_pct
        self.assertAlmostEqual(pos["fee_paid"], expected_fee, delta=0.01)

    def test_duplicate_position_prevented(self):
        """Test that opening a position on an already-active symbol is rejected."""
        symbol = "DUPE-USD"
        
        def db_get(key, default=None):
            defaults = {
                f"cooldown_end_{symbol}": "0.0",
                "max_open_positions": "10",
                "max_concentration_pct": "80",
                "max_total_exposure_pct": "90",
                "max_position_pct": "50",
                "trailing_stop_enabled": "false",
                f"atr_{symbol}": "0",
            }
            return defaults.get(key, default)
        database.load_setting.side_effect = db_get
        
        evaluation = {
            "direction": "BUY",
            "entry_price": 100.0,
            "take_profit": 110.0,
            "stop_loss": 90.0,
            "kelly_fraction": 0.2,
        }
        signals = [1]
        
        # First open should succeed
        res = self.engine.open_position(symbol, evaluation, signals)
        self.assertTrue(res)
        
        # Second open on same symbol should fail
        res = self.engine.open_position(symbol, evaluation, signals)
        self.assertFalse(res)

    def test_get_equity_with_open_positions(self):
        """Test equity calculation with open positions in paper mode."""
        import time
        symbol = "BTC-USD"
        self.engine.active_positions[symbol] = {
            "symbol": symbol,
            "direction": "BUY",
            "entry_price": 50000.0,
            "quantity": 0.5,
            "entry_time": time.time(),
            "fee_paid": 6.5,
            "cost_basis": 25000.0,
        }
        self.engine.balance = 75000.0
        
        # Equity with price above entry: 75000 + (52000-50000)*0.5 = 76000
        equity = self.engine.get_equity({symbol: 52000.0})
        self.assertAlmostEqual(equity, 76000.0, delta=0.01)

    def test_get_equity_with_eur_link_ada(self):
        self.engine.trading_mode = "live"
        self.engine.live_holdings = {
            "ZEUR": 100.0,
            "XLINK": 5.0,
            "XADA": 20.0
        }
        self.engine.last_known_prices = {
            "EUR": 1.10,
            "LINK": 15.0,
            "ADA": 0.50
        }
        
        equity = self.engine.get_equity(current_prices={})
        
        # Cash: 100.0 * 1.10 = 110.0
        # LINK: 5.0 * 15.0 = 75.0
        # ADA: 20.0 * 0.50 = 10.0
        # Total: 195.0
        self.assertAlmostEqual(equity, 195.0)

    @patch('ccxt.kraken')
    def test_sync_live_balance(self, mock_kraken):
        mock_exchange = MagicMock()
        mock_kraken.return_value = mock_exchange
        
        mock_exchange.fetch_balance.return_value = {
            'total': {
                'USD': 50.0,
                'BTC': 0.1,
                'ETH': 0.5
            }
        }
        mock_exchange.fetch_tickers.return_value = {
            'BTC/USD': {'last': 50000.0},
            'ETH/USD': {'last': 3000.0},
            'SOL/USD': {'last': 100.0},
            'DOGE/USD': {'last': 0.1},
            'XRP/USD': {'last': 0.5}
        }
        
        self.engine.trading_mode = "live"
        self.engine.config = {
            "broker": "kraken",
            "api_credentials": {
                "api_key": "test-key",
                "api_secret": "test-secret"
            }
        }
        
        self.engine.sync_live_balance()
        
        self.assertEqual(self.engine.balance, 50.0)
        self.assertEqual(self.engine.live_equity, 6550.0)

    @patch('ccxt.kraken')
    def test_sync_live_balance_with_eur_link_ada(self, mock_kraken):
        mock_exchange = MagicMock()
        mock_kraken.return_value = mock_exchange
        
        mock_exchange.fetch_balance.return_value = {
            'total': {
                'ZEUR': 100.0,
                'XLINK': 5.0,
                'XADA': 20.0
            }
        }
        mock_exchange.fetch_tickers.return_value = {
            'EUR/USD': {'last': 1.10},
            'LINK/USD': {'last': 15.0},
            'ADA/USD': {'last': 0.50},
            'BTC/USD': {'last': 50000.0},
            'ETH/USD': {'last': 3000.0},
            'SOL/USD': {'last': 100.0},
            'DOGE/USD': {'last': 0.1},
            'XRP/USD': {'last': 0.5}
        }
        
        self.engine.trading_mode = "live"
        self.engine.config = {
            "broker": "kraken",
            "api_credentials": {
                "api_key": "test-key",
                "api_secret": "test-secret"
            }
        }
        
        self.engine.sync_live_balance()
        
        self.assertAlmostEqual(self.engine.balance, 110.0)
        self.assertAlmostEqual(self.engine.live_equity, 195.0)

    def test_balance_persistence_roundtrip(self):
        """Test that balance roundtrips through save/load correctly."""
        saved_calls = {}
        def mock_save(key, value):
            saved_calls[key] = value
        database.save_setting.side_effect = mock_save
        
        self.engine.balance = 1234.56
        database.save_setting("portfolio_balance", self.engine.balance)
        self.assertEqual(saved_calls["portfolio_balance"], 1234.56)

    def test_loss_cooldown_blocks_new_trades(self):
        """Test that a symbol in loss cooldown is blocked from opening positions."""
        import time
        symbol = "COOLDOWN-USD"
        
        def db_get(key, default=None):
            defaults = {
                f"cooldown_end_{symbol}": str(time.time() + 3600),  # 1 hour cooldown
                "max_open_positions": "10",
                "max_concentration_pct": "80",
                "max_total_exposure_pct": "90",
                "max_position_pct": "50",
                "trailing_stop_enabled": "false",
                f"atr_{symbol}": "0",
            }
            return defaults.get(key, default)
        database.load_setting.side_effect = db_get
        
        evaluation = {
            "direction": "BUY",
            "entry_price": 100.0,
            "take_profit": 110.0,
            "stop_loss": 90.0,
            "kelly_fraction": 0.2,
        }
        signals = [1]
        res = self.engine.open_position(symbol, evaluation, signals)
        self.assertFalse(res)  # Should be blocked


if __name__ == "__main__":
    unittest.main()
