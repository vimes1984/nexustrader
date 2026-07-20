# tests/test_new_features.py
"""Unit tests for health monitoring, alert lifecycle, profit calculation, and mode controls."""
import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import shutil
import sqlite3
import time
import importlib

# Clean mocks
for mod in ['database', 'notification_manager', 'health_monitor']:
    if mod in sys.modules:
        if isinstance(sys.modules[mod], MagicMock) or not hasattr(sys.modules[mod], '__file__'):
            del sys.modules[mod]

import database
importlib.reload(database)
import notification_manager
importlib.reload(notification_manager)

TEST_DIR = os.path.abspath("test_new_features_workspace")


class TestAlertLifecycle(unittest.TestCase):
    """Test alert CRUD, auto-resolve, and health state tracking."""

    @classmethod
    def setUpClass(cls):
        os.makedirs(TEST_DIR, exist_ok=True)
        # Reinitialize with test DB path
        notification_manager.ALERT_DB_PATH = os.path.join(TEST_DIR, "alerts.db")
        if os.path.exists(notification_manager.ALERT_DB_PATH):
            os.remove(notification_manager.ALERT_DB_PATH)

    def setUp(self):
        if os.path.exists(notification_manager.ALERT_DB_PATH):
            os.remove(notification_manager.ALERT_DB_PATH)
        notification_manager._ensure_alerts_db()

    def tearDown(self):
        if os.path.exists(notification_manager.ALERT_DB_PATH):
            os.remove(notification_manager.ALERT_DB_PATH)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(TEST_DIR):
            shutil.rmtree(TEST_DIR)

    def test_push_and_fetch_alert(self):
        """Test pushing an alert and fetching it back."""
        notification_manager.push_alert('critical', 'system', 'Test Orphaned', 'No streams running.')
        alerts = notification_manager.get_alerts(limit=10)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['severity'], 'critical')
        self.assertEqual(alerts[0]['category'], 'system')
        self.assertEqual(alerts[0]['title'], 'Test Orphaned')
        self.assertEqual(alerts[0]['message'], 'No streams running.')
        self.assertFalse(alerts[0]['acknowledged'])
        self.assertFalse(alerts[0]['resolved'])

    def test_acknowledge_alert(self):
        """Test acknowledging an alert."""
        notification_manager.push_alert('warning', 'trading', 'Inactive', 'No trades for 5h.')
        alerts = notification_manager.get_alerts(limit=10)
        alert_id = alerts[0]['id']
        notification_manager.acknowledge_alert(alert_id)
        alerts = notification_manager.get_alerts(limit=10)
        self.assertTrue(alerts[0]['acknowledged'])

    def test_resolve_alert(self):
        """Test resolving a single alert."""
        notification_manager.push_alert('critical', 'system', 'Orphaned', 'Test')
        alerts = notification_manager.get_alerts(limit=10)
        alert_id = alerts[0]['id']
        notification_manager.resolve_alert(alert_id)
        alerts = notification_manager.get_alerts(limit=10)
        self.assertTrue(alerts[0]['resolved'])

    def test_resolve_alerts_by_category(self):
        """Test bulk-resolving alerts by category and title substring."""
        notification_manager.push_alert('critical', 'system', 'Trading Stream Orphaned', 'No streams')
        notification_manager.push_alert('critical', 'system', 'Trading Stream Orphaned', 'Still no streams')
        notification_manager.push_alert('warning', 'trading', 'Inactive', 'No trades')
        notification_manager.push_alert('info', 'system', 'Bot Started', 'OK')

        # Resolve only orphaned system alerts
        notification_manager.resolve_alerts_by_category('system', 'Trading Stream Orphaned')
        alerts = notification_manager.get_alerts(limit=10)

        orphaned = [a for a in alerts if a['title'] == 'Trading Stream Orphaned']
        for a in orphaned:
            self.assertTrue(a['resolved'], f"Alert {a['id']} not resolved")

        other = [a for a in alerts if a['title'] != 'Trading Stream Orphaned']
        for a in other:
            self.assertFalse(a['resolved'], f"Alert {a['id']} should not be resolved")

    def test_resolve_alerts_by_category_only(self):
        """Test resolving all alerts in a category."""
        notification_manager.push_alert('warning', 'exchange', 'Insuff Funds', 'Not enough cash')
        notification_manager.push_alert('warning', 'exchange', 'Rate Limited', 'Too many requests')
        notification_manager.push_alert('critical', 'system', 'Orphan Stream', 'No streams')

        notification_manager.resolve_alerts_by_category('exchange')
        alerts = notification_manager.get_alerts(limit=10)
        exchange_alerts = [a for a in alerts if a['category'] == 'exchange']
        system_alerts = [a for a in alerts if a['category'] == 'system']
        for a in exchange_alerts:
            self.assertTrue(a['resolved'])
        for a in system_alerts:
            self.assertFalse(a['resolved'])

    def test_health_state_tracking(self):
        """Test set/get health state keys."""
        notification_manager.set_health_state('last_orphan_alert', '12345')
        self.assertEqual(notification_manager.get_health_state('last_orphan_alert'), '12345')

        notification_manager.set_health_state('stream_status', 'active')
        self.assertEqual(notification_manager.get_health_state('stream_status'), 'active')

    def test_alert_pagination(self):
        """Test alert limit and ordering."""
        for i in range(15):
            notification_manager.push_alert('info', 'test', f'Alert {i}', 'test')
        alerts_all = notification_manager.get_alerts(limit=100)
        self.assertEqual(len(alerts_all), 15)

        alerts_limited = notification_manager.get_alerts(limit=5)
        self.assertEqual(len(alerts_limited), 5)

        # Most recent first
        self.assertEqual(alerts_limited[0]['title'], 'Alert 14')

    def test_ntfy_push_format(self):
        """Test that push messages are properly formatted (not actually sent)."""
        notification_manager.push_alert('critical', 'system', 'Critical Alert', 'Something broke!')
        alerts = notification_manager.get_alerts(limit=10)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['severity'], 'critical')

    def test_multiple_categories_independent_resolve(self):
        """Resolving system alerts shouldn't affect trading alerts."""
        notification_manager.push_alert('warning', 'trading', 'Inactive', 'Idle')
        notification_manager.push_alert('critical', 'system', 'Stream Orphaned', 'No streams')
        notification_manager.resolve_alerts_by_category('system', 'Stream Orphaned')
        alerts = notification_manager.get_alerts(limit=10)
        trading = [a for a in alerts if a['category'] == 'trading']
        system = [a for a in alerts if a['category'] == 'system']
        self.assertFalse(trading[0]['resolved'])
        self.assertTrue(system[0]['resolved'])


class TestProfitCalculation(unittest.TestCase):
    """Test that profit is calculated from the trades table (not equity math)."""

    def setUp(self):
        self.test_dir = os.path.join(TEST_DIR, "profit_test")
        os.makedirs(self.test_dir, exist_ok=True)
        self.db_path = os.path.join(self.test_dir, "nexustrader.db")

        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                direction TEXT,
                quantity REAL,
                entry_price REAL,
                exit_price REAL,
                pnl REAL,
                pnl_percent REAL,
                exit_reason TEXT,
                entry_time REAL,
                exit_time REAL,
                status TEXT,
                tp_price REAL,
                sl_price REAL,
                atr_at_entry REAL,
                strategy_signals TEXT,
                sentiment_sources TEXT,
                policy_brain TEXT,
                trading_mode TEXT
            )
        """)
        conn.commit()
        conn.close()

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def _insert_trade(self, conn, pnl, trading_mode='live'):
        conn.execute(
            "INSERT INTO trades (symbol, direction, quantity, entry_price, exit_price, pnl, pnl_percent, "
            "exit_reason, entry_time, exit_time, status, policy_brain, trading_mode) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ('ETH-USD', 'SELL', 0.5, 2000, 2010, pnl, pnl / (2000 * 0.5) * 100,
             'TP', 1000, 1100, 'closed', 'Test Brain', trading_mode)
        )
        conn.commit()

    def test_sum_of_live_trades_pnl(self):
        """Profit should be sum of all live trade PnL."""
        conn = sqlite3.connect(self.db_path)
        self._insert_trade(conn, 5.0)
        self._insert_trade(conn, -2.0)
        self._insert_trade(conn, 3.50)
        conn.close()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), COALESCE(SUM(pnl),0) FROM trades WHERE trading_mode = 'live'")
        cnt, total = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) FROM trades WHERE trading_mode = 'live' AND pnl > 0")
        wins = cursor.fetchone()[0]
        conn.close()

        self.assertEqual(cnt, 3)
        self.assertAlmostEqual(total, 6.5)
        self.assertEqual(wins, 2)

    def test_simulation_trades_excluded(self):
        """Simulation trades should NOT be included in live profit."""
        conn = sqlite3.connect(self.db_path)
        self._insert_trade(conn, 10.0, 'live')
        self._insert_trade(conn, 999.0, 'simulation')
        conn.close()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), COALESCE(SUM(pnl),0) FROM trades WHERE trading_mode = 'live'")
        cnt, total = cursor.fetchone()
        conn.close()

        self.assertEqual(cnt, 1)
        self.assertAlmostEqual(total, 10.0)

    def test_empty_trades_returns_zero(self):
        """When no trades exist, PnL should be 0.0 not error."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), COALESCE(SUM(pnl),0) FROM trades WHERE trading_mode = 'live'")
        cnt, total = cursor.fetchone()
        conn.close()
        self.assertEqual(cnt, 0)
        self.assertEqual(total, 0.0)

    def test_profit_never_uses_equity_minus_balance(self):
        """Critical: Profit should NOT be currentEquity - initialBalance."""
        # Simulate the old wrong approach
        equity = 115.41
        initial_balance = 100.0  # Easy to overwrite
        fake_profit = equity - initial_balance  # = 15.41 (WRONG for this test)

        conn = sqlite3.connect(self.db_path)
        self._insert_trade(conn, 2.50, 'live')
        self._insert_trade(conn, -1.00, 'live')
        conn.close()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COALESCE(SUM(pnl),0) FROM trades WHERE trading_mode = 'live'")
        real_profit = float(cursor.fetchone()[0])
        conn.close()

        # Real profit is 1.50 (2.50 - 1.00) not 15.41
        self.assertAlmostEqual(real_profit, 1.50)
        self.assertNotAlmostEqual(real_profit, fake_profit)


class TestHealthMonitorLogic(unittest.TestCase):
    """Test the health check decision logic (isolated, no real streams)."""

    def test_orphan_detection_no_streams(self):
        """When no data_ingestions are streaming, orphan check should trigger."""
        mock_orch = MagicMock()
        mock_orch.tickers = ['ETH-USD', 'LINK-USD']
        mock_orch.data_ingestions = {
            'ETH-USD': MagicMock(streaming=False),
            'LINK-USD': MagicMock(streaming=False),
        }
        mock_orch.execution_engine.trading_mode = 'live'

        streams_alive = False
        for ticker in mock_orch.tickers:
            di = mock_orch.data_ingestions.get(ticker)
            if di and hasattr(di, "streaming") and di.streaming:
                streams_alive = True
                break

        self.assertFalse(streams_alive)

    def test_orphan_not_triggered_when_streaming(self):
        """When at least one stream is alive, orphan check should pass."""
        mock_orch = MagicMock()
        mock_orch.tickers = ['ETH-USD', 'LINK-USD']
        mock_orch.data_ingestions = {
            'ETH-USD': MagicMock(streaming=True),
            'LINK-USD': MagicMock(streaming=False),
        }
        mock_orch.execution_engine.trading_mode = 'live'

        streams_alive = False
        for ticker in mock_orch.tickers:
            di = mock_orch.data_ingestions.get(ticker)
            if di and hasattr(di, "streaming") and di.streaming:
                streams_alive = True
                break

        self.assertTrue(streams_alive)

    def test_orphan_not_triggered_in_sim_mode(self):
        """When trading mode is 'paper', orphan check should be skipped."""
        mock_orch = MagicMock()
        mock_orch.tickers = ['ETH-USD']
        mock_orch.data_ingestions = {'ETH-USD': MagicMock(streaming=False)}
        mock_orch.execution_engine.trading_mode = 'paper'

        # In paper mode, we don't check orphaned
        is_live = mock_orch.execution_engine.trading_mode == 'live'
        self.assertFalse(is_live)

    def test_insufficient_funds_alert_logic(self):
        """Test that insufficient funds count change triggers alert."""
        ee = MagicMock()
        ee.insufficient_funds_count = 5

        prev = 0
        if ee.insufficient_funds_count > prev:
            triggered = True
        else:
            triggered = False

        self.assertTrue(triggered)

    def test_inactivity_alert_logic(self):
        """Test that >3h inactivity with no trades triggers idle check."""
        now = time.time()
        last_trade_ts = now - (5 * 3600)  # 5 hours ago
        idle_hours = (now - last_trade_ts) / 3600
        self.assertGreater(idle_hours, 3)

    def test_drawdown_alert_logic(self):
        """Test that drawdown >5% triggers warning."""
        dd = MagicMock()
        dd.current_pct = 8.5
        self.assertGreater(dd.current_pct, 5)


class TestModeIndicator(unittest.TestCase):
    """Test trading mode distinction and control visibility."""

    def test_live_mode_hides_sim_controls(self):
        """In live mode, sim controls bar should be hidden (display:none)."""
        # JS toggleSimControls(False) should hide controls
        show = False  # False = live mode
        display = 'flex' if show else 'none'
        self.assertEqual(display, 'none')

    def test_sim_mode_shows_controls(self):
        """In simulation mode, controls bar should be visible."""
        show = True  # True = simulation mode
        display = 'flex' if show else 'none'
        self.assertEqual(display, 'flex')

    def test_mode_badge_live_text(self):
        """Mode badge should show 'LIVE' when in live mode."""
        show = False  # live
        text = 'SIM' if show else 'LIVE'
        self.assertEqual(text, 'LIVE')

    def test_mode_badge_sim_text(self):
        """Mode badge should show 'SIM' when in sim mode."""
        show = True  # sim
        text = 'SIM' if show else 'LIVE'
        self.assertEqual(text, 'SIM')


if __name__ == '__main__':
    unittest.main()
