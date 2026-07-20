import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import sqlite3
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import nn_agent

class TestNNAgent(unittest.TestCase):
    def setUp(self):
        self.test_db = "test_nexustrader_nn.db"
        nn_agent.DB_PATH = self.test_db
        
        conn = sqlite3.connect(self.test_db)
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY, symbol TEXT, direction TEXT, entry_price REAL, exit_price REAL, pnl REAL, exit_reason TEXT)")
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('blog_gemini_api_key', 'test-key')")
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('blog_ai_enabled', 'true')")
        c.execute("INSERT INTO trades (symbol, direction, entry_price, exit_price, pnl, exit_reason) VALUES ('BTC-USD', 'BUY', 50000.0, 51000.0, 1000.0, 'Take Profit')")
        conn.commit()
        conn.close()

    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    @patch('quant_utils.query_gemini_robust')
    def test_run_nn_self_improvement(self, mock_query):
        # Mock LLM design advice and meta revision
        llm_response = """
Neural Network Analysis: stable updates.
```json
{
  "recommended_nn_learning_rate": 0.12,
  "recommended_nn_weight_floor": 0.08
}
```
"""
        meta_response = '{"revised_prompt_nn_agent": "new nn prompt"}'
        mock_query.side_effect = [llm_response, meta_response]
        
        res = nn_agent.run_nn_self_improvement(trigger_deploy=False)
        self.assertIn("Neural Network Policy Self-Improvement Report", res)
        self.assertIn("NN Learning Rate adjusted to `0.12`", res)
        self.assertIn("NN Weight Floor adjusted to `0.08`", res)
        
        # Verify db updates
        conn = sqlite3.connect(self.test_db)
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key='nn_learning_rate'")
        self.assertEqual(c.fetchone()[0], "0.12")
        
        c.execute("SELECT value FROM settings WHERE key='nn_weight_floor'")
        self.assertEqual(c.fetchone()[0], "0.08")
        
        c.execute("SELECT value FROM settings WHERE key='prompt_nn_agent'")
        self.assertEqual(c.fetchone()[0], "new nn prompt")
        conn.close()

if __name__ == "__main__":
    unittest.main()
