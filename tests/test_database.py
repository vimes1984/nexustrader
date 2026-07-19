import unittest
import os
import sys
import sqlite3
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database

class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.test_db = "test_database_module.db"
        database.DB_PATH = self.test_db
        database.init_db()

    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

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

if __name__ == "__main__":
    unittest.main()
