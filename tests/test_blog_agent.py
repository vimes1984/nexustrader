import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import sqlite3

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import blog_agent

class TestBlogAgent(unittest.TestCase):
    def setUp(self):
        self.test_db = "test_nexustrader_blog_agent.db"
        blog_agent.DB_PATH = self.test_db
        
        # Setup temporary directories
        self.test_blog_dir = "test_blog_agent_dir"
        blog_agent.BLOG_DIR = self.test_blog_dir
        
        if not os.path.exists(self.test_blog_dir):
            os.makedirs(self.test_blog_dir)
            
        conn = sqlite3.connect(self.test_db)
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY, symbol TEXT, direction TEXT, entry_price REAL, exit_price REAL, pnl REAL, pnl_percent REAL, exit_reason TEXT, exit_time REAL, strategy_signals TEXT)")
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('blog_gemini_api_key', 'test-key')")
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('blog_ai_enabled', 'true')")
        
        # Seed trades
        c.execute("INSERT INTO trades (symbol, direction, entry_price, exit_price, pnl, pnl_percent, exit_reason, exit_time, strategy_signals) VALUES ('SOL-USD', 'BUY', 100.0, 105.0, 5.0, 5.0, 'Take Profit', ?, '{}')", (sqlite3.Timestamp.now().timestamp(),))
        c.execute("INSERT INTO trades (symbol, direction, entry_price, exit_price, pnl, pnl_percent, exit_reason, exit_time, strategy_signals) VALUES ('BTC-USD', 'BUY', 50000.0, 48000.0, -2000.0, -4.0, 'Stop Loss', ?, '{}')", (sqlite3.Timestamp.now().timestamp(),))
        
        conn.commit()
        conn.close()

    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        if os.path.exists(self.test_blog_dir):
            import shutil
            shutil.rmtree(self.test_blog_dir)

    def test_analyze_weekly_performance(self):
        trades = blog_agent.load_trades()
        stats = blog_agent.analyze_weekly_performance(trades)
        self.assertEqual(stats["total_trades"], 2)
        self.assertEqual(stats["wins"], 1)
        self.assertEqual(stats["losses"], 1)
        self.assertEqual(stats["win_rate"], 0.5)

    def test_get_ascii_bar(self):
        bar = blog_agent.get_ascii_bar(0.5, max_val=1.0, width=10)
        self.assertEqual(len(bar), 10)
        self.assertIn("█", bar)

    @patch('quant_utils.query_gemini_robust')
    def test_query_gemini_api(self, mock_query):
        mock_query.return_value = "Mock Blog Post Content"
        res = blog_agent.query_gemini_api("key", "prompt")
        self.assertEqual(res, "Mock Blog Post Content")

if __name__ == "__main__":
    unittest.main()
