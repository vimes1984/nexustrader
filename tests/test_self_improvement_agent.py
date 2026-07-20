import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import sqlite3
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import self_improvement_agent

class TestSelfImprovementAgent(unittest.TestCase):
    def setUp(self):
        self.test_db = "test_nexustrader_param_opt.db"
        self_improvement_agent.DB_PATH = self.test_db
        
        conn = sqlite3.connect(self.test_db)
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY, pnl REAL, pnl_percent REAL, symbol TEXT, direction TEXT, strategy_signals TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS ticks (close REAL, rsi REAL, atr REAL, timestamp INTEGER)")
        
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('blog_gemini_api_key', 'test-key')")
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('blog_ai_enabled', 'true')")
        
        # Seed ticks
        for i in range(100):
            c.execute("INSERT INTO ticks (close, rsi, atr, timestamp) VALUES (?, ?, ?, ?)", (100.0 + i, 50.0, 1.0, 1234567 + i))
            
        c.execute("INSERT INTO trades (pnl, pnl_percent, symbol, direction, strategy_signals) VALUES (10.0, 2.0, 'SOL-USD', 'BUY', '{}')")
        conn.commit()
        conn.close()

    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    @patch('quant_utils.query_gemini_robust')
    def test_run_self_improvement(self, mock_query):
        # Mock LLM design advice and meta revision
        llm_response = """
PhD Quant advice: parameters look optimized.
```json
{
  "recommended_risk_mode": "conservative",
  "recommended_tp_multiplier": 2.8,
  "recommended_sl_multiplier": 1.6
}
```
"""
        meta_response = '{"revised_prompt_self_improvement": "new quant prompt"}'
        mock_query.side_effect = [llm_response, meta_response]
        
        self_improvement_agent.run_self_improvement()
        
        # Verify db updates
        conn = sqlite3.connect(self.test_db)
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key='risk_mode'")
        self.assertEqual(c.fetchone()[0], "conservative")
        
        c.execute("SELECT value FROM settings WHERE key='opt_tp_multiplier'")
        self.assertEqual(c.fetchone()[0], "2.8")
        
        c.execute("SELECT value FROM settings WHERE key='prompt_self_improvement'")
        self.assertEqual(c.fetchone()[0], "new quant prompt")
        conn.close()

if __name__ == "__main__":
    unittest.main()
