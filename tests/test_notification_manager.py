# tests/test_notification_manager.py
import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import shutil
import sqlite3
import importlib

# Clean mock database from sys.modules if it is a MagicMock
if 'database' in sys.modules:
    if not hasattr(sys.modules['database'], 'get_db_connection') or isinstance(sys.modules['database'], MagicMock):
        del sys.modules['database']

import database
importlib.reload(database)

import notification_manager
importlib.reload(notification_manager)

class TestNotificationManager(unittest.TestCase):
    def setUp(self):
        import importlib
        import sys
        from unittest.mock import MagicMock
        if 'database' in sys.modules and (isinstance(sys.modules['database'], MagicMock) or not hasattr(sys.modules['database'], 'get_db_connection')):
            sys.modules.pop('database', None)
        import database
        importlib.reload(database)
        
        import notification_manager
        importlib.reload(notification_manager)

        self.original_db_path = database.DB_PATH
        self.test_dir = os.path.abspath("test_notif_workspace")
        os.makedirs(self.test_dir, exist_ok=True)
        
        # Override paths in database and notification_manager
        database.DB_PATH = os.path.join(self.test_dir, "nexustrader.db")
        
        # Initialize DB
        conn = sqlite3.connect(database.DB_PATH)
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS trades (id TEXT PRIMARY KEY, status TEXT, pnl REAL)")
        
        # Insert initial data
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('portfolio_balance', '1500.00')")
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('portfolio_live_equity', '1650.00')")
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('initial_portfolio_balance', '1000.00')")
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('daily_income_goal', '500.00')")
        
        conn.execute("INSERT INTO trades (id, status, pnl) VALUES ('t1', 'closed', 150.0)")
        conn.execute("INSERT INTO trades (id, status, pnl) VALUES ('t2', 'open', 0.0)")
        conn.commit()
        conn.close()

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_get_and_save_settings(self):
        settings = notification_manager.get_notification_settings()
        self.assertEqual(settings["notif_email_recipient"], "churchill.c.j@gmail.com")
        self.assertEqual(settings["notif_email_enabled"], "false")
        
        # Save updates
        updates = {
            "notif_email_enabled": "true",
            "notif_email_recipient": "new@domain.com",
            "notif_whatsapp_enabled": "true",
            "notif_whatsapp_webhook": "http://webhook"
        }
        notification_manager.save_notification_settings(updates)
        
        # Reload
        reloaded = notification_manager.get_notification_settings()
        self.assertEqual(reloaded["notif_email_enabled"], "true")
        self.assertEqual(reloaded["notif_email_recipient"], "new@domain.com")
        self.assertEqual(reloaded["notif_whatsapp_enabled"], "true")
        self.assertEqual(reloaded["notif_whatsapp_webhook"], "http://webhook")

    def test_generate_summary_text(self):
        summary = notification_manager.generate_summary_text()
        self.assertIn("Current Balance (Cash): $1,500.00", summary)
        self.assertIn("Total Equity (Valuation): $1,650.00", summary)
        self.assertIn("Net PnL (Life-to-Date): $+650.00", summary)
        self.assertIn("Closed Trades Count: 1", summary)
        self.assertIn("Active Open Positions: 1", summary)

    @patch('smtplib.SMTP')
    def test_send_smtp_email_success(self, mock_smtp):
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        
        settings = {
            "notif_email_recipient": "dest@domain.com",
            "notif_smtp_host": "smtp.domain.com",
            "notif_smtp_port": "587",
            "notif_smtp_user": "user@domain.com",
            "notif_smtp_pass": "secret"
        }
        
        res = notification_manager.send_smtp_email(settings, "Subject", "Body")
        self.assertTrue(res)
        mock_smtp.assert_called_once_with("smtp.domain.com", 587, timeout=10)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user@domain.com", "secret")
        mock_server.sendmail.assert_called_once()

    @patch('urllib.request.urlopen')
    def test_send_whatsapp_webhook_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"status": "ok"}'
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        settings = {
            "notif_whatsapp_webhook": "http://openclaw:8002/api/whatsapp"
        }
        
        res = notification_manager.send_whatsapp_webhook(settings, "Body text")
        self.assertTrue(res)
        mock_urlopen.assert_called_once()

    @patch('notification_manager.send_smtp_email', return_value=True)
    @patch('notification_manager.send_whatsapp_webhook', return_value=True)
    def test_send_notification_summary(self, mock_wa, mock_email):
        # Setup settings with both enabled
        updates = {
            "notif_email_enabled": "true",
            "notif_whatsapp_enabled": "true"
        }
        notification_manager.save_notification_settings(updates)
        
        res = notification_manager.send_notification_summary()
        self.assertTrue(res)
        mock_email.assert_called_once()
        mock_wa.assert_called_once()
