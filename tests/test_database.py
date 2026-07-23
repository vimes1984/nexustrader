import unittest
import os
import sys
import sqlite3
import time
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database

class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.test_db = os.path.abspath("test_database_module.db")
        database.DB_PATH = self.test_db
        database.init_db()

    def tearDown(self):
        # Close any active SQLite connections to release locks before deleting
        try:
            conn = sqlite3.connect(self.test_db)
            conn.close()
        except Exception:
            pass
        if os.path.exists(self.test_db):
            try:
                os.remove(self.test_db)
            except Exception:
                pass

    def test_settings_save_and_load(self):
        database.save_setting("test_key", "test_val")
        val = database.load_setting("test_key")
        self.assertEqual(val, "test_val")
        
        # Test default fallback
        fallback = database.load_setting("non_existent", "default_val")
        self.assertEqual(fallback, "default_val")

    def test_active_assets(self):
        # Save asset
        success = database.save_active_asset("BTC-USD", True, 3.0, 1.2, 0.25)
        self.assertTrue(success)
        
        # Load assets
        assets = database.load_active_assets()
        btc_asset = next((a for a in assets if a["ticker"] == "BTC-USD"), None)
        self.assertIsNotNone(btc_asset)
        self.assertTrue(btc_asset["is_active"])
        self.assertEqual(btc_asset["tp_multiplier"], 3.0)
        self.assertEqual(btc_asset["sl_multiplier"], 1.2)
        self.assertEqual(btc_asset["kelly_ceiling"], 0.25)
        
        # Delete asset
        del_success = database.delete_active_asset("BTC-USD")
        self.assertTrue(del_success)
        assets_post_del = database.load_active_assets()
        btc_asset_post = next((a for a in assets_post_del if a["ticker"] == "BTC-USD"), None)
        self.assertIsNone(btc_asset_post)

    def test_agent_optimizations(self):
        database.log_optimization("Test Agent", "test_param", "1.0", "2.0", "For testing")
        opts = database.load_optimizations()
        self.assertEqual(len(opts), 1)
        self.assertEqual(opts[0]["agent"], "Test Agent")
        self.assertEqual(opts[0]["parameter"], "test_param")
        self.assertEqual(opts[0]["old_value"], "1.0")
        self.assertEqual(opts[0]["new_value"], "2.0")
        self.assertEqual(opts[0]["rationale"], "For testing")

    def test_settings_edge_cases(self):
        """Test settings save/load with edge cases: JSON, empty, special chars, Unicode."""
        # JSON serialized data
        json_data = json.dumps({"key": "value", "nested": {"a": 1}})
        database.save_setting("json_setting", json_data)
        loaded = database.load_setting("json_setting", "")
        self.assertEqual(json.loads(loaded), {"key": "value", "nested": {"a": 1}})
        
        # Empty string
        database.save_setting("empty_setting", "")
        loaded_empty = database.load_setting("empty_setting", "fallback")
        self.assertEqual(loaded_empty, "")
        
        # Special characters
        database.save_setting("special_chars", "val=123&test=true#hash")
        loaded_special = database.load_setting("special_chars", "")
        self.assertEqual(loaded_special, "val=123&test=true#hash")
        
        # Unicode
        database.save_setting("unicode", "café — ✓ ✅")
        loaded_unicode = database.load_setting("unicode", "")
        self.assertEqual(loaded_unicode, "café — ✓ ✅")
        
        # Long string (10KB)
        long_val = "x" * 10000
        database.save_setting("long_val", long_val)
        loaded_long = database.load_setting("long_val", "")
        self.assertEqual(loaded_long, long_val)
        self.assertEqual(len(loaded_long), 10000)
        
        # Setting with equals sign in value
        database.save_setting("eq_val", "key=value")
        loaded_eq = database.load_setting("eq_val", "")
        self.assertEqual(loaded_eq, "key=value")
        
        # Numeric value saved as string, verify round-trip
        database.save_setting("numeric", "123.456")
        loaded_num = database.load_setting("numeric", "0")
        self.assertEqual(float(loaded_num), 123.456)

    def test_active_positions_cleanup(self):
        """Test that active_positions are properly cleaned up on close/delete.
        
        This catches the regression where active_positions were being written
        but never cleaned up when positions closed, causing stale positions
        to be reloaded on restart.
        """
        # Save a position
        pos = {
            'direction': 'long',
            'entry_price': 50000.0,
            'entry_price_raw': 50000.0,
            'quantity': 0.5,
            'take_profit': 55000.0,
            'stop_loss': 48000.0,
            'entry_time': time.time(),
            'cost_basis': 25000.0,
            'fee_paid': 12.5,
            'trading_mode': 'paper',
            'strategy_signals': [0.5, -0.2],
            'sentiment_sources': {'cointelegraph': 0.3},
            'predicted_win_probability': 0.65,
            'expected_value': 0.02,
            'risk_reward_ratio': 2.5,
            'kelly_fraction': 0.15,
        }
        database.save_active_position('ETH-USD', pos)
        
        # Verify it was saved
        loaded = database.load_active_positions()
        self.assertIn('ETH-USD', loaded)
        self.assertEqual(loaded['ETH-USD']['direction'], 'long')
        self.assertAlmostEqual(loaded['ETH-USD']['entry_price'], 50000.0)
        
        # Delete the position (simulates closing the trade)
        database.delete_active_position('ETH-USD')
        
        # Verify it's gone
        loaded_after = database.load_active_positions()
        self.assertNotIn('ETH-USD', loaded_after)

    def test_agent_runs(self):
        database.log_agent_run("Test Quant Agent", "gemini", "gemini-flash", "What is 1+1?", "It is 2", "Success")
        runs = database.load_agent_runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["agent"], "Test Quant Agent")
        self.assertEqual(runs[0]["provider"], "gemini")
        self.assertEqual(runs[0]["model"], "gemini-flash")
        self.assertEqual(runs[0]["prompt"], "What is 1+1?")
        self.assertEqual(runs[0]["response"], "It is 2")
        self.assertEqual(runs[0]["status"], "Success")

if __name__ == "__main__":
    unittest.main()
