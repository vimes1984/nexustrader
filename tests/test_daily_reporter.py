import unittest
from unittest.mock import patch, MagicMock, mock_open
import os
import sys
import sqlite3

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import daily_reporter

class TestDailyReporter(unittest.TestCase):
    def setUp(self):
        self.test_db = "test_nexustrader_daily_reporter.db"
        daily_reporter.DB_PATH = self.test_db
        
        # Setup temporary directories
        self.test_blog_dir = "test_blog"
        self.test_daily_dir = os.path.join(self.test_blog_dir, "daily_summaries")
        daily_reporter.BLOG_DIR = self.test_blog_dir
        daily_reporter.DAILY_DIR = self.test_daily_dir
        
        if not os.path.exists(self.test_daily_dir):
            os.makedirs(self.test_daily_dir)
            
        conn = sqlite3.connect(self.test_db)
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY, symbol TEXT, direction TEXT, entry_price REAL, exit_price REAL, pnl REAL, exit_reason TEXT, exit_time REAL, strategy_signals TEXT)")
        # Seed trade
        c.execute("INSERT INTO trades (symbol, direction, entry_price, exit_price, pnl, exit_reason, exit_time, strategy_signals) VALUES ('BTC-USD', 'BUY', 50000.0, 51000.0, 1000.0, 'Take Profit', ?, '{}')", (sqlite3.Timestamp.now().timestamp(),))
        conn.commit()
        conn.close()

    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        # Clean up files
        if os.path.exists(self.test_blog_dir):
            import shutil
            shutil.rmtree(self.test_blog_dir)

    @patch('subprocess.run')
    def test_get_git_commits(self, mock_sub):
        # Mock successful git execution
        mock_sub.return_value = MagicMock(returncode=0, stdout="a1b2c3d commit msg\n")
        commits = daily_reporter.get_git_commits()
        self.assertEqual(commits, ["a1b2c3d commit msg"])

    @patch('daily_reporter.push_to_github')
    @patch('subprocess.run')
    def test_generate_daily_report(self, mock_sub, mock_push):
        mock_sub.return_value = MagicMock(returncode=0, stdout="commit1\n")
        
        # Setup index files
        with open(os.path.join(self.test_blog_dir, "index.md"), "w") as f:
            f.write("## 📅 Daily Summaries\n")
            
        daily_reporter.generate_daily_report()
        
        # Verify daily summary file was written
        files = os.listdir(self.test_daily_dir)
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].startswith("daily_summary_"))
        
        # Check that index was updated
        with open(os.path.join(self.test_blog_dir, "index.md"), "r") as f:
            index_content = f.read()
            self.assertIn("Daily Summary", index_content)

if __name__ == "__main__":
    unittest.main()
