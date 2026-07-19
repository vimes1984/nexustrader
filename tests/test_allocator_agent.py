import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import json
import sqlite3

# Setup sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import allocator_agent

class TestAllocatorAgent(unittest.TestCase):
    def setUp(self):
        # Ensure temporary test DB path
        self.test_db = "test_nexustrader.db"
        allocator_agent.DB_PATH = self.test_db
        
        # Initialize test DB tables
        conn = sqlite3.connect(self.test_db)
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS active_assets (ticker TEXT PRIMARY KEY, is_active INTEGER, tp_multiplier REAL, sl_multiplier REAL, kelly_ceiling REAL)")
        c.execute("CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY, timestamp REAL, ticker TEXT, result TEXT, pnl_pct REAL, pnl REAL)")
        
        # Seed settings
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('blog_gemini_api_key', 'test-key')")
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('blog_ai_enabled', 'true')")
        
        # Seed active assets
        c.execute("INSERT OR REPLACE INTO active_assets (ticker, is_active, tp_multiplier, sl_multiplier, kelly_ceiling) VALUES ('BTC-USD', 1, 2.5, 1.5, 0.2)")
        
        # Seed trades
        c.execute("INSERT INTO trades (timestamp, ticker, result, pnl_pct, pnl) VALUES (1784400000, 'BTC-USD', 'WIN', 2.5, 15.0)")
        
        conn.commit()
        conn.close()

    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    @patch('quant_utils.query_gemini_robust')
    def test_run_allocator_self_improvement_updates_settings(self, mock_query):
        # Mock LLM response containing adjustments and meta-prompt revision
        llm_response = """
Proposed adjustments for BTC-USD: Kelly ceiling and stops look fine.
```json
{
  "asset_adjustments": {
    "BTC-USD": {
      "is_active": true,
      "tp_multiplier": 3.0,
      "sl_multiplier": 1.2,
      "kelly_ceiling": 0.25
    }
  }
}
```
"""
        meta_response = """
```json
{
  "revised_prompt_allocator_agent": "revised allocator prompt"
}
```
"""
        mock_query.side_effect = [llm_response, meta_response]
        
        res = allocator_agent.run_allocator_self_improvement(trigger_deploy=False)
        self.assertTrue(res.startswith("Success"))
        
        # Check active_assets was updated in database
        conn = sqlite3.connect(self.test_db)
        c = conn.cursor()
        c.execute("SELECT is_active, tp_multiplier, sl_multiplier, kelly_ceiling FROM active_assets WHERE ticker='BTC-USD'")
        row = c.fetchone()
        
        self.assertEqual(row[0], 1)
        self.assertEqual(row[1], 3.0)
        self.assertEqual(row[2], 1.2)
        self.assertEqual(row[3], 0.25)
        
        # Check prompt_allocator_agent was saved
        c.execute("SELECT value FROM settings WHERE key='prompt_allocator_agent'")
        prompt_val = c.fetchone()[0]
        self.assertEqual(prompt_val, "revised allocator prompt")
        
        conn.close()

if __name__ == "__main__":
    unittest.main()
