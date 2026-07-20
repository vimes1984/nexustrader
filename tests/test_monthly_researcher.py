import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import sqlite3

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database

class TestMonthlyResearcher(unittest.TestCase):
    def setUp(self):
        # We need to reload database and monthly_researcher inside setup to ensure clean environment
        global database
        import importlib
        if 'database' in sys.modules and (isinstance(sys.modules['database'], MagicMock) or not hasattr(sys.modules['database'], 'get_db_connection')):
            sys.modules.pop('database', None)
        import database
        importlib.reload(database)
        
        import monthly_researcher
        importlib.reload(monthly_researcher)
        self.monthly_researcher = monthly_researcher

        self.original_db_path = database.DB_PATH
        self.test_dir = os.path.abspath("test_research_workspace")
        os.makedirs(self.test_dir, exist_ok=True)
        database.DB_PATH = os.path.join(self.test_dir, "nexustrader.db")
        self.monthly_researcher.DB_PATH = database.DB_PATH

        # Initialize DB
        conn = sqlite3.connect(database.DB_PATH)
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS trades (id TEXT PRIMARY KEY, symbol TEXT, direction TEXT, entry_price REAL, exit_price REAL, pnl REAL, pnl_percent REAL, exit_reason TEXT)")
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('blog_gemini_api_key', 'test_key')")
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('blog_ai_enabled', 'true')")
        conn.commit()
        conn.close()

        # Create dummy blog/daily_summaries folder
        self.blog_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "blog", "daily_summaries")
        os.makedirs(self.blog_dir, exist_ok=True)

    def tearDown(self):
        # Clean up database file
        database.DB_PATH = self.original_db_path
        if os.path.exists(self.test_dir):
            import shutil
            shutil.rmtree(self.test_dir)

    @patch('quant_utils.query_gemini_robust')
    def test_run_monthly_researcher_success(self, mock_query):
        # Setup mock advice and meta-prompt responses
        mock_query.side_effect = [
            # First call (Advice text containing json block)
            "Here is my PhD quantitative strategy research analysis.\n```json\n{\n  \"proposed_strategies\": [],\n  \"parameter_tuning\": {\n    \"target_asset_kelly_multiplier\": 0.15\n  }\n}\n```",
            # Second call (Meta-prompt JSON output)
            "{\n  \"revised_prompt_monthly_researcher\": \"Optimized Prompt template.\"\n}"
        ]

        res = self.monthly_researcher.run_monthly_researcher()
        self.assertTrue(res.startswith("Success!"))

        print(f"DEBUG: database.DB_PATH is {database.DB_PATH}")
        print(f"DEBUG: self.monthly_researcher.DB_PATH is {self.monthly_researcher.DB_PATH}")
        print(f"DEBUG: exists? {os.path.exists(database.DB_PATH)}")
        conn = sqlite3.connect(database.DB_PATH)
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key='quant_research_target_asset_kelly_multiplier'")
        row = c.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "0.15")

        c.execute("SELECT value FROM settings WHERE key='prompt_monthly_researcher'")
        row = c.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "Optimized Prompt template.")
        conn.close()

        # Verify report was written
        report_path = os.path.join(self.blog_dir, "monthly_quant_research.md")
        self.assertTrue(os.path.exists(report_path))

if __name__ == "__main__":
    unittest.main()
