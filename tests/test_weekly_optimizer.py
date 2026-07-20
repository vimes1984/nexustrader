import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import sqlite3
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import weekly_optimizer

class TestWeeklyOptimizer(unittest.TestCase):
    def setUp(self):
        self.test_db = "test_nexustrader_weekly_opt.db"
        weekly_optimizer.DB_PATH = self.test_db
        
        conn = sqlite3.connect(self.test_db)
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS trades (pnl REAL, pnl_percent REAL, sentiment_sources TEXT, direction TEXT)")
        
        # Seed trades
        c.execute("INSERT INTO trades (pnl, pnl_percent, sentiment_sources, direction) VALUES (10.0, 1.5, '{\"cointelegraph\": 0.5, \"reddit\": -0.2}', 'BUY')")
        c.execute("INSERT INTO trades (pnl, pnl_percent, sentiment_sources, direction) VALUES (-5.0, -0.8, '{\"cointelegraph\": -0.2, \"reddit\": 0.4}', 'BUY')")
        c.execute("INSERT INTO trades (pnl, pnl_percent, sentiment_sources, direction) VALUES (8.0, 1.2, '{\"cointelegraph\": 0.4, \"reddit\": -0.1}', 'BUY')")
        
        conn.commit()
        conn.close()

    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    def test_optimize_sentiment_weights(self):
        weekly_optimizer.optimize_sentiment_weights()
        
        conn = sqlite3.connect(self.test_db)
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key='feed_weight_cointelegraph'")
        val = c.fetchone()
        self.assertIsNotNone(val)
        
        c.execute("SELECT value FROM settings WHERE key='feed_weight_reddit'")
        val_reddit = c.fetchone()
        self.assertIsNotNone(val_reddit)
        
        conn.close()

if __name__ == "__main__":
    unittest.main()
