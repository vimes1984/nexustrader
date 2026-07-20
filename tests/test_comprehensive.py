# tests/test_comprehensive.py
"""Comprehensive unit tests for NexusTrader: ExecutionEngine, StrategyEngine, ProbabilityEngine, API endpoints, and edge cases.

Run with: cd /root/nexustrader && python -m pytest tests/test_comprehensive.py -v
"""

import time
import json
import math
import os
import sys
import unittest
from unittest.mock import patch, MagicMock, PropertyMock
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ─── Global mocks for database and ccxt ───────────────────────────────────────
_mock_db = MagicMock()
_mock_ccxt = MagicMock()
sys.modules['database'] = _mock_db
sys.modules['ccxt'] = _mock_ccxt
sys.modules['evaluation'] = MagicMock()
sys.modules['evaluation.singletons'] = MagicMock()
sys.modules['evaluation.position_sizing'] = MagicMock()

import database
import ccxt


def _reset_db_mocks():
    database.load_setting.reset_mock()
    database.save_setting.reset_mock()
    database.init_db.reset_mock()
    database.get_db_connection.reset_mock()
    database.load_trades.reset_mock()
    database.save_trade.reset_mock()
    database.load_active_assets.reset_mock()
    database.save_active_asset.reset_mock()
    database.load_weights_history.reset_mock()
    database.save_weights_history.reset_mock()


def _setup_default_db_mocks():
    # Return the default value passed by the caller, so calls like
    # load_setting("cooldown_end_BTC-USD", "0.0") return "0.0".
    database.load_setting.side_effect = lambda key, default=None: default
    database.save_setting.return_value = None
    database.init_db.return_value = None
    database.load_trades.return_value = []
    database.save_trade.return_value = None
    database.get_db_connection.return_value = MagicMock()
    database.load_active_assets.return_value = []
    database.save_active_asset.return_value = True
    database.load_weights_history.return_value = []
    database.save_weights_history.return_value = None


# ==============================================================================
# TEST GROUP 1: ExecutionEngine
# ==============================================================================

class TestExecutionEngine(unittest.TestCase):
    """Tests for the ExecutionEngine class (mock ccxt, mock database)."""

    def setUp(self):
        _reset_db_mocks()
        _setup_default_db_mocks()
        # Mock os.path.expanduser + os.path.exists so config.json isn't read
        self._exists_patch = patch('os.path.exists', return_value=False)
        self._mock_exists = self._exists_patch.start()
        self._expand_patch = patch('os.path.expanduser', return_value='/tmp/.nexustrader_test')
        self._mock_expand = self._expand_patch.start()

    def tearDown(self):
        self._exists_patch.stop()
        self._expand_patch.stop()

    # ── 1.1 __init__ loads balance from DB ────────────────────────────────────

    def test_init_loads_balance_from_db(self):
        database.load_setting.side_effect = lambda key, default=None: {
            "portfolio_balance": "2500.00",
            "initial_portfolio_balance": "1000.00",
            "portfolio_live_equity": "2500.00",
            "portfolio_live_holdings": '{"USD": 2500.0}',
            "portfolio_last_known_prices": '{}',
        }.get(key, default)

        from execution_engine import ExecutionEngine
        engine = ExecutionEngine(initial_balance=100.0)

        self.assertAlmostEqual(engine.balance, 2500.00)
        self.assertAlmostEqual(engine.initial_balance, 1000.00)

    # ── 1.2 sync_live_balance() with mock exchange ────────────────────────────

    @patch('ccxt.kraken')
    def test_sync_live_balance_with_mock_exchange(self, mock_kraken_cls):
        from execution_engine import ExecutionEngine
        engine = ExecutionEngine(initial_balance=100.0)
        engine.trading_mode = "live"
        engine.config = {
            "trading_mode": "live",
            "broker": "kraken",
            "api_credentials": {"api_key": "test-key", "api_secret": "test-secret"},
        }

        mock_exchange = MagicMock()
        mock_kraken_cls.return_value = mock_exchange
        mock_exchange.fetch_balance.return_value = {
            'total': {'USD': 500.0, 'BTC': 0.2, 'ETH': 1.0}
        }
        mock_exchange.fetch_tickers.return_value = {
            'BTC/USD': {'last': 45000.0},
            'ETH/USD': {'last': 3000.0},
            'SOL/USD': {'last': 100.0},
            'DOGE/USD': {'last': 0.1},
            'XRP/USD': {'last': 0.5},
        }
        mock_exchange.symbols = [
            'BTC/USD', 'ETH/USD', 'SOL/USD', 'DOGE/USD', 'XRP/USD',
        ]
        mock_exchange.markets = {}

        engine.sync_live_balance()

        self.assertAlmostEqual(engine.balance, 500.0)
        # Equity = 500 + 0.2*45000 + 1.0*3000 = 500 + 9000 + 3000 = 12500
        self.assertAlmostEqual(engine.live_equity, 12500.0)

    # ── 1.3 sync_live_balance() converts EUR to USD ──────────────────────────

    @patch('ccxt.kraken')
    def test_sync_live_balance_converts_eur_to_usd(self, mock_kraken_cls):
        from execution_engine import ExecutionEngine
        engine = ExecutionEngine(initial_balance=100.0)
        engine.trading_mode = "live"
        engine.config = {
            "trading_mode": "live",
            "broker": "kraken",
            "api_credentials": {"api_key": "test-key", "api_secret": "test-secret"},
        }

        mock_exchange = MagicMock()
        mock_kraken_cls.return_value = mock_exchange
        mock_exchange.fetch_balance.return_value = {
            'total': {'ZEUR': 200.0, 'BTC': 0.1}
        }
        mock_exchange.fetch_tickers.return_value = {
            'EUR/USD': {'last': 1.12},
            'BTC/USD': {'last': 50000.0},
            'ETH/USD': {'last': 3000.0},
            'SOL/USD': {'last': 100.0},
            'DOGE/USD': {'last': 0.1},
            'XRP/USD': {'last': 0.5},
        }
        mock_exchange.symbols = [
            'BTC/USD', 'ETH/USD', 'SOL/USD', 'DOGE/USD', 'XRP/USD', 'EUR/USD',
        ]
        mock_exchange.markets = {}

        engine.sync_live_balance()

        # Cash: 200 EUR * 1.12 = 224 USD
        self.assertAlmostEqual(engine.balance, 224.0)
        # Equity: 224 + 0.1 * 50000 = 5224
        self.assertAlmostEqual(engine.live_equity, 5224.0)

    # ── 1.4 sync_live_balance() handles missing API keys ──────────────────────

    def test_sync_live_balance_missing_api_keys(self):
        from execution_engine import ExecutionEngine
        engine = ExecutionEngine(initial_balance=100.0)
        engine.trading_mode = "live"
        engine.config = {
            "trading_mode": "live",
            "broker": "kraken",
            "api_credentials": {"api_key": "", "api_secret": ""},
        }
        engine.sync_live_balance()
        self.assertEqual(engine.balance, 100.0)

    # ── 1.5 open_position() creates position correctly ───────────────────────

    def test_open_position_creates_position(self):
        from execution_engine import ExecutionEngine
        engine = ExecutionEngine(initial_balance=1000.0)
        engine.active_positions = {}
        engine.pending_limit_orders = {}

        database.load_setting.side_effect = lambda key, default=None: {
            "cooldown_end_BTC-USD": "0.0",
        }.get(key, default or "0.0")

        evaluation = {
            "direction": "BUY",
            "entry_price": 50000.0,
            "take_profit": 52000.0,
            "stop_loss": 49000.0,
            "kelly_fraction": 0.1,
        }
        signals = [1, 0, -1]

        result = engine.open_position("BTC-USD", evaluation, signals)

        self.assertTrue(result)
        self.assertIn("BTC-USD", engine.pending_limit_orders)
        order = engine.pending_limit_orders["BTC-USD"]
        self.assertEqual(order["direction"], "BUY")
        self.assertEqual(order["limit_price"], 50000.0)
        # kelly_fraction=0.1 -> position_value = 1000 * 0.1 = 100, qty = 100/50000 = 0.002
        self.assertAlmostEqual(order["quantity"], 0.002)

    # ── 1.6 open_position() rejects duplicate symbol ──────────────────────────

    def test_open_position_rejects_duplicate(self):
        from execution_engine import ExecutionEngine
        engine = ExecutionEngine(initial_balance=1000.0)
        engine.active_positions = {"BTC-USD": {"symbol": "BTC-USD"}}
        engine.pending_limit_orders = {}

        evaluation = {
            "direction": "BUY",
            "entry_price": 50000.0,
            "take_profit": 52000.0,
            "stop_loss": 49000.0,
            "kelly_fraction": 0.1,
        }

        result = engine.open_position("BTC-USD", evaluation, [1, 0])

        self.assertFalse(result)
        self.assertNotIn("BTC-USD", engine.pending_limit_orders)
        # Also test rejection when symbol is in pending_limit_orders
        engine.active_positions = {}
        engine.pending_limit_orders = {"ETH-USD": {}}
        result2 = engine.open_position("ETH-USD", evaluation, [1, 0])
        self.assertFalse(result2)

    # ── 1.7 open_position() respects loss cooldown ───────────────────────────

    def test_open_position_respects_loss_cooldown(self):
        from execution_engine import ExecutionEngine
        engine = ExecutionEngine(initial_balance=1000.0)
        engine.active_positions = {}
        engine.pending_limit_orders = {}

        future_time = time.time() + 7200
        database.load_setting.side_effect = lambda key, default=None: {
            "cooldown_end_BTC-USD": str(future_time),
        }.get(key, default or "0.0")

        evaluation = {
            "direction": "BUY",
            "entry_price": 50000.0,
            "take_profit": 52000.0,
            "stop_loss": 49000.0,
            "kelly_fraction": 0.1,
        }

        result = engine.open_position("BTC-USD", evaluation, [1, 0])

        self.assertFalse(result)
        self.assertNotIn("BTC-USD", engine.pending_limit_orders)

    # ── 1.8 update_positions() triggers TP/SL exit ───────────────────────────

    def test_update_positions_triggers_tp_exit(self):
        from execution_engine import ExecutionEngine
        engine = ExecutionEngine(initial_balance=1000.0)
        engine.active_positions = {}
        engine.pending_limit_orders = {}
        engine.closed_trades = []
        engine.learning_callback = None

        engine.active_positions["BTC-USD"] = {
            "symbol": "BTC-USD",
            "direction": "BUY",
            "entry_price": 50000.0,
            "quantity": 0.002,
            "take_profit": 52000.0,
            "stop_loss": 49000.0,
            "entry_time": time.time() - 100,
            "strategy_signals": [1, 0],
            "fee_paid": 0.1,
        }

        database.load_setting.side_effect = lambda key, default=None: {
            "trailing_stop_enabled": "false",
            "loss_cooldown_hours": "4.0",
        }.get(key, default)
        database.save_setting.return_value = None
        database.save_trade.return_value = None

        result = engine.update_positions("BTC-USD", 53000.0)

        self.assertIsNotNone(result)
        self.assertEqual(result["event"], "closed")
        self.assertEqual(result["data"]["exit_reason"], "Take Profit")
        self.assertNotIn("BTC-USD", engine.active_positions)

    def test_update_positions_triggers_sl_exit(self):
        from execution_engine import ExecutionEngine
        engine = ExecutionEngine(initial_balance=1000.0)
        engine.active_positions = {}
        engine.pending_limit_orders = {}
        engine.closed_trades = []
        engine.learning_callback = None

        engine.active_positions["BTC-USD"] = {
            "symbol": "BTC-USD",
            "direction": "BUY",
            "entry_price": 50000.0,
            "quantity": 0.002,
            "take_profit": 52000.0,
            "stop_loss": 49000.0,
            "entry_time": time.time() - 100,
            "strategy_signals": [1, 0],
            "fee_paid": 0.1,
        }

        database.load_setting.side_effect = lambda key, default=None: {
            "trailing_stop_enabled": "false",
            "loss_cooldown_hours": "4.0",
        }.get(key, default)

        result = engine.update_positions("BTC-USD", 48000.0)

        self.assertIsNotNone(result)
        self.assertEqual(result["event"], "closed")
        self.assertEqual(result["data"]["exit_reason"], "Stop Loss")
        self.assertNotIn("BTC-USD", engine.active_positions)

    # ── 1.9 update_positions() handles trailing stop-loss ────────────────────

    def test_update_positions_trailing_stop(self):
        from execution_engine import ExecutionEngine
        engine = ExecutionEngine(initial_balance=1000.0)
        engine.active_positions = {}
        engine.pending_limit_orders = {}
        engine.closed_trades = []
        engine.learning_callback = None

        database.load_setting.side_effect = lambda key, default=None: {
            "trailing_stop_enabled": "true",
            "loss_cooldown_hours": "4.0",
        }.get(key, default)
        database.save_setting.return_value = None
        database.save_trade.return_value = None

        entry_price = 50000.0
        initial_sl = 49000.0

        engine.active_positions["BTC-USD"] = {
            "symbol": "BTC-USD",
            "direction": "BUY",
            "entry_price": entry_price,
            "quantity": 0.002,
            "take_profit": 55000.0,
            "stop_loss": initial_sl,
            "entry_time": time.time() - 100,
            "strategy_signals": [1, 0],
            "fee_paid": 0.1,
        }

        result1 = engine.update_positions("BTC-USD", 51000.0)
        self.assertIsNone(result1)
        self.assertAlmostEqual(engine.active_positions["BTC-USD"]["stop_loss"], 50000.0)

    # ── 1.10 update_positions() fills pending limit orders ────────────────────

    def test_update_positions_fills_limit_order(self):
        from execution_engine import ExecutionEngine
        engine = ExecutionEngine(initial_balance=1000.0)
        engine.active_positions = {}
        engine.pending_limit_orders = {
            "BTC-USD": {
                "symbol": "BTC-USD",
                "direction": "BUY",
                "limit_price": 50000.0,
                "quantity": 0.002,
                "take_profit": 52000.0,
                "stop_loss": 49000.0,
                "entry_time": time.time() - 100,
                "strategy_signals": [1, 0],
                "fee": 0.1,
            }
        }
        engine.closed_trades = []
        database.load_setting.return_value = None
        database.save_setting.return_value = None

        result = engine.update_positions("BTC-USD", 49000.0)

        self.assertIsNotNone(result)
        self.assertEqual(result["event"], "filled")
        self.assertNotIn("BTC-USD", engine.pending_limit_orders)
        self.assertIn("BTC-USD", engine.active_positions)
        self.assertEqual(engine.active_positions["BTC-USD"]["entry_price"], 50000.0)

    # ── 1.11 get_equity() calculates correctly with positions ─────────────────

    def test_get_equity_calculates_with_positions(self):
        from execution_engine import ExecutionEngine
        engine = ExecutionEngine(initial_balance=1000.0)
        engine.trading_mode = "paper"
        engine.balance = 800.0
        engine.active_positions = {
            "BTC-USD": {
                "symbol": "BTC-USD",
                "direction": "BUY",
                "entry_price": 50000.0,
                "quantity": 0.01,
                "take_profit": 52000.0,
                "stop_loss": 49000.0,
                "entry_time": time.time(),
                "strategy_signals": [1, 0],
                "fee_paid": 0.5,
            }
        }
        equity = engine.get_equity({"BTC-USD": 51000.0})
        self.assertAlmostEqual(equity, 810.0)

    # ── 1.12 get_equity() converts EUR holdings to USD in live mode ──────────

    def test_get_equity_converts_eur_holdings_live(self):
        from execution_engine import ExecutionEngine
        engine = ExecutionEngine(initial_balance=100.0)
        engine.trading_mode = "live"
        engine.live_holdings = {"ZEUR": 200.0, "BTC": 0.1}
        engine.last_known_prices = {"EUR": 1.12, "BTC": 50000.0}

        equity = engine.get_equity(current_prices={})

        self.assertAlmostEqual(equity, 5224.0)

    # ── 1.13 execute_order_on_broker() in paper mode ──────────────────────────

    def test_execute_order_on_broker_paper_mode(self):
        from execution_engine import ExecutionEngine
        engine = ExecutionEngine(initial_balance=1000.0)
        engine.trading_mode = "paper"

        success, qty = engine.execute_order_on_broker("BTC-USD", "buy", 0.01, 50000.0)

        self.assertTrue(success)
        self.assertEqual(qty, 0.01)

    # ── 1.14 normalize_kraken_asset() for all known codes ────────────────────

    def test_normalize_kraken_asset_all_codes(self):
        from execution_engine import normalize_kraken_asset

        test_cases = [
            ("XXBT", "BTC"),
            ("XETH", "ETH"),
            ("XXRP", "XRP"),
            ("XLTC", "LTC"),
            ("XXLM", "XLM"),
            ("XDG", "DOGE"),
            ("ZEUR", "EUR"),
            ("ZUSD", "USD"),
            ("ZGBP", "GBP"),
            ("ZCAD", "CAD"),
            ("ZJPY", "JPY"),
            ("SOL", "SOL"),
            ("ADA", "ADA"),
        ]
        for kraken_code, expected in test_cases:
            self.assertEqual(normalize_kraken_asset(kraken_code), expected,
                             "Failed for {} -> {}".format(kraken_code, expected))

    def test_normalize_kraken_asset_strip_prefix(self):
        from execution_engine import normalize_kraken_asset
        self.assertEqual(normalize_kraken_asset("XFOO"), "FOO")
        self.assertEqual(normalize_kraken_asset("ZBAR"), "BAR")


# ==============================================================================
# TEST GROUP 2: StrategyEngine
# ==============================================================================

class TestStrategyEngine(unittest.TestCase):
    """Tests for all trading strategies."""

    def setUp(self):
        import importlib
        if 'strategy_engine' in sys.modules:
            del sys.modules['strategy_engine']
        self._db_patch = patch('database.load_setting')
        self._mock_db_load = self._db_patch.start()
        self._mock_db_load.side_effect = lambda key, default=None: {
            "opt_rsi_oversold": "35",
            "opt_rsi_overbought": "65",
            "opt_kalman_threshold": "0.001",
        }.get(key, default)

    def tearDown(self):
        self._db_patch.stop()
        if 'strategy_engine' in sys.modules:
            del sys.modules['strategy_engine']

    # ── 2.1 EMACrossoverStrategy ──────────────────────────────────────────────

    def test_ema_crossover_buy_signal(self):
        import strategy_engine
        strat = strategy_engine.EMACrossoverStrategy()
        signal = strat.generate_signal({'macd': 1.5, 'macd_signal': 1.0})
        self.assertEqual(signal, 1.0)

    def test_ema_crossover_sell_signal(self):
        import strategy_engine
        strat = strategy_engine.EMACrossoverStrategy()
        signal = strat.generate_signal({'macd': 0.5, 'macd_signal': 1.0})
        self.assertEqual(signal, -1.0)

    def test_ema_crossover_hold_signal(self):
        import strategy_engine
        strat = strategy_engine.EMACrossoverStrategy()
        signal = strat.generate_signal({'macd': 1.0, 'macd_signal': 1.0})
        self.assertEqual(signal, 0.0)

    # ── 2.2 RSIStrategy ───────────────────────────────────────────────────────

    def test_rsi_oversold_buy(self):
        import strategy_engine
        strat = strategy_engine.RSIStrategy()
        signal = strat.generate_signal({'rsi': 30.0})
        self.assertEqual(signal, 1.0)

    def test_rsi_overbought_sell(self):
        import strategy_engine
        strat = strategy_engine.RSIStrategy()
        signal = strat.generate_signal({'rsi': 70.0})
        self.assertEqual(signal, -1.0)

    def test_rsi_mid_hold(self):
        import strategy_engine
        strat = strategy_engine.RSIStrategy()
        signal = strat.generate_signal({'rsi': 50.0})
        self.assertEqual(signal, 0.0)

    # ── 2.3 BollingerBandsStrategy ────────────────────────────────────────────

    def test_bb_breakout_buy(self):
        import strategy_engine
        strat = strategy_engine.BollingerBandsStrategy()
        signal = strat.generate_signal({'close': 90.0, 'bb_lower': 95.0, 'bb_upper': 105.0})
        self.assertEqual(signal, 1.0)

    def test_bb_breakout_sell(self):
        import strategy_engine
        strat = strategy_engine.BollingerBandsStrategy()
        signal = strat.generate_signal({'close': 110.0, 'bb_lower': 95.0, 'bb_upper': 105.0})
        self.assertEqual(signal, -1.0)

    def test_bb_mid_hold(self):
        import strategy_engine
        strat = strategy_engine.BollingerBandsStrategy()
        signal = strat.generate_signal({'close': 100.0, 'bb_lower': 95.0, 'bb_upper': 105.0})
        self.assertEqual(signal, 0.0)

    # ── 2.4 KalmanTrendStrategy ───────────────────────────────────────────────

    def test_kalman_trend_buy_signal(self):
        import strategy_engine
        strat = strategy_engine.KalmanTrendStrategy()
        for p in [100.0, 100.1, 100.0, 100.05, 100.1]:
            strat.generate_signal({'close': p})
        signal = strat.generate_signal({'close': 105.0})
        self.assertEqual(signal, 1.0)

    def test_kalman_trend_sell_signal(self):
        import strategy_engine
        strat = strategy_engine.KalmanTrendStrategy()
        for p in [100.0, 99.9, 100.0, 99.95, 99.9]:
            strat.generate_signal({'close': p})
        signal = strat.generate_signal({'close': 95.0})
        self.assertEqual(signal, -1.0)

    # ── 2.5 MeanReversionZScoreStrategy ───────────────────────────────────────

    def test_mean_reversion_zscore_buy(self):
        import strategy_engine
        strat = strategy_engine.MeanReversionZScoreStrategy(entry_threshold=2.0)
        signal = strat.generate_signal({'close': 80.0, 'bb_mid': 100.0, 'bb_std': 5.0})
        self.assertEqual(signal, 1.0)

    def test_mean_reversion_zscore_sell(self):
        import strategy_engine
        strat = strategy_engine.MeanReversionZScoreStrategy(entry_threshold=2.0)
        signal = strat.generate_signal({'close': 120.0, 'bb_mid': 100.0, 'bb_std': 5.0})
        self.assertEqual(signal, -1.0)

    def test_mean_reversion_zscore_zero_std_hold(self):
        import strategy_engine
        strat = strategy_engine.MeanReversionZScoreStrategy()
        signal = strat.generate_signal({'close': 100.0, 'bb_mid': 100.0, 'bb_std': 0.0})
        self.assertEqual(signal, 0.0)

    # ── 2.6 VWAPCrossoverStrategy ─────────────────────────────────────────────

    def test_vwap_crossover_buy(self):
        import strategy_engine
        strat = strategy_engine.VWAPCrossoverStrategy()
        signal = strat.generate_signal({'close': 101.0, 'vwma_20': 100.0})
        self.assertEqual(signal, 1.0)

    def test_vwap_crossover_sell(self):
        import strategy_engine
        strat = strategy_engine.VWAPCrossoverStrategy()
        signal = strat.generate_signal({'close': 99.0, 'vwma_20': 100.0})
        self.assertEqual(signal, -1.0)

    def test_vwap_crossover_hold_near(self):
        import strategy_engine
        strat = strategy_engine.VWAPCrossoverStrategy()
        signal = strat.generate_signal({'close': 100.0, 'vwma_20': 100.0})
        self.assertEqual(signal, 0.0)

    # ── 2.7 ATRBreakoutStrategy ───────────────────────────────────────────────

    def test_atr_breakout_buy(self):
        import strategy_engine
        strat = strategy_engine.ATRBreakoutStrategy(multiplier=1.5)
        signal = strat.generate_signal({'close': 110.0, 'sma_20': 100.0, 'atr': 5.0})
        self.assertEqual(signal, 1.0)

    def test_atr_breakout_sell(self):
        import strategy_engine
        strat = strategy_engine.ATRBreakoutStrategy(multiplier=1.5)
        signal = strat.generate_signal({'close': 90.0, 'sma_20': 100.0, 'atr': 5.0})
        self.assertEqual(signal, -1.0)

    def test_atr_breakout_hold_zero_atr(self):
        import strategy_engine
        strat = strategy_engine.ATRBreakoutStrategy()
        signal = strat.generate_signal({'close': 110.0, 'sma_20': 100.0, 'atr': 0.0})
        self.assertEqual(signal, 0.0)

    # ── 2.8 StochasticOscillatorStrategy ──────────────────────────────────────

    def test_stochastic_oversold_buy(self):
        import strategy_engine
        strat = strategy_engine.StochasticOscillatorStrategy(overbought=80, oversold=20)
        signal = strat.generate_signal({'stoch_k': 15.0, 'stoch_d': 10.0})
        self.assertEqual(signal, 1.0)

    def test_stochastic_overbought_sell(self):
        import strategy_engine
        strat = strategy_engine.StochasticOscillatorStrategy(overbought=80, oversold=20)
        signal = strat.generate_signal({'stoch_k': 85.0, 'stoch_d': 90.0})
        self.assertEqual(signal, -1.0)

    def test_stochastic_mid_hold(self):
        import strategy_engine
        strat = strategy_engine.StochasticOscillatorStrategy()
        signal = strat.generate_signal({'stoch_k': 50.0, 'stoch_d': 50.0})
        self.assertEqual(signal, 0.0)

    def test_stochastic_non_cross_hold(self):
        import strategy_engine
        strat = strategy_engine.StochasticOscillatorStrategy()
        signal = strat.generate_signal({'stoch_k': 15.0, 'stoch_d': 20.0})
        self.assertEqual(signal, 0.0)

    # ── 2.9 StrategyEnsemble.get_weighted_signal() ────────────────────────────

    def test_ensemble_get_weighted_signal(self):
        import strategy_engine
        ensemble = strategy_engine.StrategyEnsemble()
        row = {
            'close': 100.0, 'rsi': 50, 'macd': 1.0, 'macd_signal': 0.5,
            'bb_lower': 90.0, 'bb_upper': 110.0, 'bb_mid': 100.0, 'bb_std': 5.0,
            'sma_20': 100.0, 'sma_50': 100.0, 'atr': 3.0,
            'stoch_k': 50, 'stoch_d': 50, 'vwma_20': 100.0,
        }
        weighted_signal, breakdown = ensemble.get_weighted_signal(row)
        self.assertIsInstance(weighted_signal, float)
        self.assertIsInstance(breakdown, dict)
        self.assertGreaterEqual(weighted_signal, -1.0)
        self.assertLessEqual(weighted_signal, 1.0)

    # ── 2.10 Ensemble weights sum to ~1.0 ─────────────────────────────────────

    def test_ensemble_weights_sum_to_one(self):
        import strategy_engine
        ensemble = strategy_engine.StrategyEnsemble()
        weight_sum = sum(ensemble.weights)
        self.assertAlmostEqual(weight_sum, 1.0, places=6)

    # ── 2.11 record_trade_outcome() ──────────────────────────────────────────

    def test_ensemble_record_trade_outcome_tracks_performance(self):
        import strategy_engine
        ensemble = strategy_engine.StrategyEnsemble()
        self.assertEqual(len(ensemble.strategy_performance), 0)

        strategy_signals = [1.0] * 12
        ensemble.record_trade_outcome(strategy_signals, "BUY", 0.05)

        for name, perf_list in ensemble.strategy_performance.items():
            self.assertEqual(len(perf_list), 1)
            self.assertTrue(perf_list[0]['correct'])
            self.assertEqual(perf_list[0]['direction'], "BUY")
            self.assertEqual(perf_list[0]['pnl_pct'], 0.05)

    def test_ensemble_record_trade_outcome_rolling_window(self):
        import strategy_engine
        ensemble = strategy_engine.StrategyEnsemble()
        for i in range(60):
            ensemble.record_trade_outcome([1.0] * 12, "BUY", 0.01 * i)
        for name, perf_list in ensemble.strategy_performance.items():
            self.assertLessEqual(len(perf_list), 50)


# ==============================================================================
# TEST GROUP 3: ProbabilityEngine
# ==============================================================================

class TestProbabilityEngine(unittest.TestCase):
    """Tests for ProbabilityEngine: ATR bounds, win probability, trade evaluation."""

    def setUp(self):
        self._db_load_patch = patch('database.load_setting')
        self._mock_db_load = self._db_load_patch.start()
        self._mock_db_load.side_effect = lambda key, default=None: {
            "opt_tp_multiplier": "2.5",
            "opt_sl_multiplier": "1.5",
        }.get(key, default)

        self._db_conn_patch = patch('database.get_db_connection')
        self._mock_db_conn = self._db_conn_patch.start()
        self._mock_db_conn.side_effect = Exception("Simulated DB error")

        self._db_trades_patch = patch('database.load_trades')
        self._mock_db_trades = self._db_trades_patch.start()
        self._mock_db_trades.return_value = []

        self._eval_singletons_patch = patch.dict('sys.modules', {
            'evaluation': MagicMock(),
            'evaluation.singletons': MagicMock(),
            'evaluation.position_sizing': MagicMock(),
        })
        self._eval_singletons_patch.start()

        from probability_engine import ProbabilityEngine
        self.engine = ProbabilityEngine(kelly_fraction=0.1, min_win_rate=0.45)

    def tearDown(self):
        self._db_load_patch.stop()
        self._db_conn_patch.stop()
        self._db_trades_patch.stop()
        self._eval_singletons_patch.stop()

    # ── 3.1 calculate_atr_bounds() with valid ATR ────────────────────────────

    def test_calculate_atr_bounds_buy_valid(self):
        tp, sl = self.engine.calculate_atr_bounds(price=100.0, atr=5.0, direction="BUY")
        self.assertAlmostEqual(tp, 112.5)
        self.assertAlmostEqual(sl, 92.5)

    def test_calculate_atr_bounds_sell_valid(self):
        tp, sl = self.engine.calculate_atr_bounds(price=100.0, atr=5.0, direction="SELL")
        self.assertAlmostEqual(tp, 87.5)
        self.assertAlmostEqual(sl, 107.5)

    # ── 3.2 calculate_atr_bounds() with zero ATR (fallback) ──────────────────

    def test_calculate_atr_bounds_zero_atr_fallback(self):
        tp, sl = self.engine.calculate_atr_bounds(price=100.0, atr=0.0, direction="BUY")
        self.assertAlmostEqual(tp, 102.5)
        self.assertAlmostEqual(sl, 98.5)

    def test_calculate_atr_bounds_nan_atr_fallback(self):
        tp, sl = self.engine.calculate_atr_bounds(price=100.0, atr=float('nan'), direction="BUY")
        self.assertAlmostEqual(tp, 102.5)
        self.assertAlmostEqual(sl, 98.5)

    # ── 3.3 estimate_win_probability() for buy signal ─────────────────────────

    def test_estimate_win_probability_buy(self):
        p_win = self.engine.estimate_win_probability(0.8, {'rsi': 50})
        self.assertGreater(p_win, 0.5)
        self.assertLessEqual(p_win, 0.75)

    def test_estimate_win_probability_buy_oversold_boost(self):
        p_normal = self.engine.estimate_win_probability(0.8, {'rsi': 50})
        p_oversold = self.engine.estimate_win_probability(0.8, {'rsi': 25})
        self.assertGreater(p_oversold, p_normal)

    # ── 3.4 estimate_win_probability() for sell signal ────────────────────────

    def test_estimate_win_probability_sell(self):
        p_win = self.engine.estimate_win_probability(-0.8, {'rsi': 50})
        self.assertGreater(p_win, 0.5)

    def test_estimate_win_probability_sell_overbought_boost(self):
        p_normal = self.engine.estimate_win_probability(-0.8, {'rsi': 50})
        p_overbought = self.engine.estimate_win_probability(-0.8, {'rsi': 80})
        self.assertGreater(p_overbought, p_normal)

    # ── 3.7 Kelly sizing doesn't exceed max_cap ───────────────────────────────

    def test_kelly_sizing_respects_max_cap(self):
        self.engine.set_risk_mode("conservative")
        result = self.engine.evaluate_trade(
            price=100.0, atr=5.0, direction="BUY",
            weighted_signal=0.9, row={'rsi': 30},
        )
        self.assertLessEqual(result["kelly_fraction"], 0.05)

    def test_kelly_sizing_aggressive_max_cap(self):
        self.engine.set_risk_mode("aggressive")
        result = self.engine.evaluate_trade(
            price=100.0, atr=5.0, direction="BUY",
            weighted_signal=0.9, row={'rsi': 30},
        )
        self.assertLessEqual(result["kelly_fraction"], 0.20)
        self.assertGreater(result["kelly_fraction"], 0.0)

    # ── 3.5 evaluate_trade() returns is_viable=True for strong signals ────────

    def test_evaluate_trade_viable_strong_signal(self):
        self.engine.min_win_rate = 0.45
        result = self.engine.evaluate_trade(
            price=100.0, atr=5.0, direction="BUY",
            weighted_signal=0.7, row={'rsi': 45},
        )
        self.assertTrue(result["is_viable"])
        self.assertGreater(result["kelly_fraction"], 0.0)
        self.assertGreater(result["expected_value"], 0.0)
        self.assertGreater(result["win_probability"], 0.45)

    # ── 3.6 evaluate_trade() returns is_viable=False for weak signals ─────────

    def test_evaluate_trade_not_viable_weak_signal(self):
        # Override the engine so that evaluate_trade cannot use DB trades for
        # safe-fraction capping (makes the test deterministic).
        self.engine.min_win_rate = 0.50  # Raise the bar
        result = self.engine.evaluate_trade(
            price=100.0, atr=5.0, direction="BUY",
            weighted_signal=0.01, row={'rsi': 80},
        )
        # weighted_signal 0.01 -> base_p = 0.5 + 0.01*0.15 = 0.5015
        # RSI 80 for BUY -> rsi_adjustment = -0.05
        # p_win = clip(0.5015 - 0.05, 0.35, 0.75) = 0.4515
        # min_win_rate = 0.50, so 0.4515 < 0.50 -> is_viable = False
        self.assertFalse(result["is_viable"])


# ==============================================================================
# TEST GROUP 4: API endpoints (mock)
# ==============================================================================

class TestApiEndpoints(unittest.TestCase):
    """Tests for FastAPI endpoints using mock orchestrator."""

    @classmethod
    def setUpClass(cls):
        _reset_db_mocks()
        _setup_default_db_mocks()

    def setUp(self):
        _reset_db_mocks()
        _setup_default_db_mocks()
        # long_term_strategy.LongTermStrategyLayer.__init__ calls
        # database.load_setting("shadow_balance", "10000.0") at module level.
        # Make sure every key returns its default via our side_effect.
        # Also kill_switch and drawdown_tracker singletons get loaded.
        # Patch before importing main.
        self._lt_patch = patch('long_term_strategy.database', database)
        self._lt_patch.start()

        # Ensure main's module-level singleton construction succeeds
        with patch('main.LongTermStrategyLayer') as mock_ltl_cls:
            mock_ltl_cls.return_value = MagicMock()
            with patch('main.ProbabilityEngine') as mock_pe_cls:
                mock_pe_cls.return_value = MagicMock()
                with patch('main.ExecutionEngine') as mock_ee_cls:
                    mock_ee = MagicMock()
                    mock_ee.balance = 5000.0
                    mock_ee.initial_balance = 1000.0
                    mock_ee.live_equity = 5000.0
                    mock_ee.get_equity.return_value = 5200.0
                    mock_ee.active_positions = {}
                    mock_ee.pending_limit_orders = {}
                    mock_ee.trading_mode = "paper"
                    mock_ee.closed_trades = []
                    mock_ee.live_holdings = {}
                    mock_ee.set_learning_callback = MagicMock()
                    mock_ee_cls.return_value = mock_ee

                    import importlib
                    if 'main' in sys.modules:
                        del sys.modules['main']
                    import main

        self._orch_patch = patch('main.orchestrator')
        self._mock_orch = self._orch_patch.start()
        self._mock_orch.tickers = ["BTC-USD", "ETH-USD"]
        self._mock_orch.data_ingestions = {}
        self._mock_orch.strategy_ensembles = {}
        self._mock_orch.execution_engine = MagicMock()
        self._mock_orch.execution_engine.balance = 5000.0
        self._mock_orch.execution_engine.initial_balance = 1000.0
        self._mock_orch.execution_engine.live_equity = 5000.0
        self._mock_orch.execution_engine.get_equity.return_value = 5200.0
        self._mock_orch.execution_engine.active_positions = {}
        self._mock_orch.execution_engine.pending_limit_orders = {}
        self._mock_orch.execution_engine.trading_mode = "paper"
        self._mock_orch.execution_engine.closed_trades = []
        self._mock_orch.execution_engine.live_holdings = {}
        self._mock_orch.execution_engine.config = {}
        self._mock_orch.probability_engine = MagicMock()
        self._mock_orch.long_term_layer = MagicMock()
        self._mock_orch.connected_websockets = []
        self._mock_orch.execution_engine.set_learning_callback = MagicMock()

    def tearDown(self):
        self._orch_patch.stop()
        self._lt_patch.stop()
        if 'main' in sys.modules:
            del sys.modules['main']
        # Clean up any import side effects
        for mod in list(sys.modules.keys()):
            if 'long_term_strategy' in mod:
                del sys.modules[mod]

    # ── 4.1 /api/status returns expected fields ──────────────────────────────

    def test_api_status_returns_expected_fields(self):
        import main
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.side_effect = [
            (5, 150.0),
            (3,),
        ]
        database.get_db_connection.return_value = mock_conn

        status = main.get_status()

        self.assertIn("balance", status)
        self.assertIn("equity", status)
        self.assertIn("total_pnl", status)
        self.assertIn("closed_trades", status)
        self.assertIn("winning_trades", status)
        self.assertIn("open_positions", status)
        self.assertIn("tickers", status)
        self.assertIn("trading_mode", status)
        self.assertEqual(status["balance"], 5000.0)
        self.assertEqual(status["total_pnl"], 150.0)
        self.assertEqual(status["closed_trades"], 5)
        self.assertEqual(status["winning_trades"], 3)

    # ── 4.2 /api/trading/reasoning returns items array ───────────────────────

    def test_api_trading_reasoning_returns_items(self):
        import main
        mock_ensemble = MagicMock()
        mock_ensemble.strategies = [MagicMock() for _ in range(5)]
        mock_ensemble.strategies[0].name = "EMA Crossover"
        # All tickers must have strategies for no "strat_issues"
        self._mock_orch.strategy_ensembles = {
            "BTC-USD": mock_ensemble,
            "ETH-USD": mock_ensemble,
        }
        self._mock_orch.execution_engine.closed_trades = []

        result = main.get_trading_reasoning()

        self.assertIn("items", result)
        self.assertIn("status", result)
        self.assertIn("trading_mode", result)
        self.assertIn("open_positions", result)
        self.assertIsInstance(result["items"], list)
        self.assertTrue(len(result["items"]) > 0)

    # ── 4.3 /api/trading/reasoning handles missing strategies ────────────────

    def test_api_trading_reasoning_handles_no_strategies(self):
        import main
        self._mock_orch.strategy_ensembles = {"BTC-USD": None}

        result = main.get_trading_reasoning()

        self.assertIn("items", result)
        items = result["items"]
        has_no_strategies = any(item["id"] == "no_strategies" for item in items)
        self.assertTrue(has_no_strategies)
        self.assertEqual(result["status"], "idle")

    # ── 4.4 /api/init returns strategies list ────────────────────────────────

    def test_api_init_returns_strategies_list(self):
        import main
        mock_ensemble = MagicMock()
        mock_strat_1 = MagicMock()
        mock_strat_1.name = "EMA Crossover"
        mock_strat_2 = MagicMock()
        mock_strat_2.name = "RSI Reversion"
        mock_ensemble.strategies = [mock_strat_1, mock_strat_2]
        mock_ensemble.weights = [0.5, 0.5]
        self._mock_orch.strategy_ensembles = {"BTC-USD": mock_ensemble}

        result = main.get_init_data()

        self.assertIn("strategies", result)
        self.assertEqual(len(result["strategies"]), 1)
        self.assertEqual(result["strategies"][0]["ticker"], "BTC-USD")
        self.assertEqual(result["strategies"][0]["count"], 2)
        self.assertIn("weights", result)


# ==============================================================================
# TEST GROUP 5: Edge Cases
# ==============================================================================

class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases: empty balances, zero positions, extreme values, missing config."""

    def setUp(self):
        _reset_db_mocks()
        _setup_default_db_mocks()
        self._exists_patch = patch('os.path.exists', return_value=False)
        self._mock_exists = self._exists_patch.start()
        self._expand_patch = patch('os.path.expanduser', return_value='/tmp/.nexustrader_test')
        self._mock_expand = self._expand_patch.start()

    def tearDown(self):
        self._exists_patch.stop()
        self._expand_patch.stop()

    # ── 5.1 Empty balance ────────────────────────────────────────────────────

    def test_empty_balance_initialization(self):
        database.load_setting.side_effect = lambda key, default=None: {
            "portfolio_balance": "0.00",
            "initial_portfolio_balance": "0.00",
            "portfolio_live_equity": "0.00",
            "portfolio_live_holdings": '{}',
            "portfolio_last_known_prices": '{}',
        }.get(key, default)

        from execution_engine import ExecutionEngine
        engine = ExecutionEngine(initial_balance=100.0)
        self.assertEqual(engine.balance, 0.0)

    def test_open_position_with_zero_balance(self):
        from execution_engine import ExecutionEngine
        engine = ExecutionEngine(initial_balance=0.0)
        engine.active_positions = {}
        engine.pending_limit_orders = {}

        database.load_setting.side_effect = lambda key, default=None: {
            "cooldown_end_BTC-USD": "0.0",
        }.get(key, default or "0.0")

        evaluation = {
            "direction": "BUY",
            "entry_price": 50000.0,
            "take_profit": 52000.0,
            "stop_loss": 49000.0,
            "kelly_fraction": 0.1,
        }

        result = engine.open_position("BTC-USD", evaluation, [1, 0])
        self.assertTrue(result)
        self.assertAlmostEqual(engine.pending_limit_orders["BTC-USD"]["quantity"], 0.0)

    # ── 5.2 Zero positions ───────────────────────────────────────────────────

    def test_update_positions_no_positions(self):
        from execution_engine import ExecutionEngine
        engine = ExecutionEngine(initial_balance=100.0)
        engine.active_positions = {}
        engine.pending_limit_orders = {}

        result = engine.update_positions("BTC-USD", 50000.0)
        self.assertIsNone(result)

    def test_get_equity_no_positions(self):
        from execution_engine import ExecutionEngine
        engine = ExecutionEngine(initial_balance=100.0)
        engine.trading_mode = "paper"
        engine.balance = 100.0
        engine.active_positions = {}

        equity = engine.get_equity({"BTC-USD": 50000.0})
        self.assertEqual(equity, 100.0)

    # ── 5.3 Extreme ATR values ───────────────────────────────────────────────

    def test_extreme_atr_values(self):
        from probability_engine import ProbabilityEngine
        engine = ProbabilityEngine(kelly_fraction=0.1)

        database.load_setting.side_effect = lambda key, default=None: {
            "opt_tp_multiplier": "2.5",
            "opt_sl_multiplier": "1.5",
        }.get(key, default)

        tp, sl = engine.calculate_atr_bounds(price=100.0, atr=500.0, direction="BUY")
        self.assertEqual(tp, 100.0 + 2.5 * 500.0)
        self.assertEqual(sl, 100.0 - 1.5 * 500.0)

        tp2, sl2 = engine.calculate_atr_bounds(price=100.0, atr=0.0001, direction="BUY")
        self.assertGreater(tp2, 100.0)
        self.assertLess(sl2, 100.0)

    # ── 5.4 NaN handling in signal generation ────────────────────────────────

    def test_nan_handling_ema_strategy(self):
        import strategy_engine
        strat = strategy_engine.EMACrossoverStrategy()
        signal = strat.generate_signal({'macd': float('nan'), 'macd_signal': 1.0})
        self.assertEqual(signal, 0.0)

    def test_nan_handling_rsi_strategy(self):
        import strategy_engine
        strat = strategy_engine.RSIStrategy()
        database.load_setting.side_effect = lambda key, default=None: default
        signal = strat.generate_signal({'rsi': float('nan')})
        self.assertEqual(signal, 0.0)

    def test_nan_handling_bb_strategy(self):
        import strategy_engine
        strat = strategy_engine.BollingerBandsStrategy()
        signal = strat.generate_signal({'close': float('nan'), 'bb_lower': 95.0, 'bb_upper': 105.0})
        self.assertEqual(signal, 0.0)

    # ── 5.5 Missing config file handling ─────────────────────────────────────

    def test_missing_config_uses_default_mode(self):
        from execution_engine import ExecutionEngine
        engine = ExecutionEngine(initial_balance=100.0)
        self.assertEqual(engine.trading_mode, "paper")

    def test_corrupted_config_falls_back_to_defaults(self):
        # Temporarily stop the setUp patches that would interfere
        self._exists_patch.stop()
        self._expand_patch.stop()

        # os.path.exists: first call (data_dir) -> True, second call (config_file) -> True
        mock_open = MagicMock()
        mock_file = MagicMock()
        mock_file.__enter__.return_value = mock_file
        mock_file.read.return_value = "this is not valid json {{"
        mock_open.return_value = mock_file

        with patch('os.path.exists') as mock_exists:
            # os.makedirs checks if parent dir exists, then two checks on config_path
            mock_exists.side_effect = [True, True, True]
            with patch('builtins.open', mock_open):
                from execution_engine import ExecutionEngine
                engine = ExecutionEngine(initial_balance=100.0)

        # Corrupted config leaves config empty, but trading_mode falls back to 'paper'
        self.assertEqual(engine.trading_mode, "paper")
        # The empty config should still be loadable as a dict
        self.assertEqual(engine.config, {})

        # Restore setUp patches for subsequent tests
        self._exists_patch = patch('os.path.exists', return_value=False)
        self._mock_exists = self._exists_patch.start()
        self._expand_patch = patch('os.path.expanduser', return_value='/tmp/.nexustrader_test')
        self._mock_expand = self._expand_patch.start()

    def test_sync_live_balance_not_live_mode(self):
        from execution_engine import ExecutionEngine
        engine = ExecutionEngine(initial_balance=100.0)
        engine.trading_mode = "paper"
        engine.sync_live_balance()
        self.assertEqual(engine.balance, 100.0)


if __name__ == "__main__":
    unittest.main()
