import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import sqlite3
import json

# Setup sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import risk_auditor

class TestRiskAuditor(unittest.TestCase):
    def setUp(self):
        # Ensure temporary test DB path
        self.test_db = "test_nexustrader_risk.db"
        risk_auditor.DB_PATH = self.test_db
        
        # Initialize test DB tables
        conn = sqlite3.connect(self.test_db)
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY, symbol TEXT, direction TEXT, pnl REAL, exit_reason TEXT)")
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('blog_gemini_api_key', 'test-key')")
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('blog_ai_enabled', 'true')")
        
        # Seed trades
        c.execute("INSERT INTO trades (symbol, direction, pnl, exit_reason) VALUES ('SOL-USD', 'BUY', -5.0, 'Stop Loss')")
        conn.commit()
        conn.close()

    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    @patch('quant_utils.query_gemini_robust')
    def test_run_risk_audit_success(self, mock_query):
        # Mock LLM design advice and meta revision
        llm_response = """
Risk Audit Analysis: Sol looks highly volatile.
```json
{
  "recommended_max_daily_loss": 3.5,
  "recommended_loss_cooldown_hours": 6.0
}
```
"""
        meta_response = """
{
  "revised_prompt_risk_auditor": "new risk prompt"
}
"""
        mock_query.side_effect = [llm_response, meta_response]
        
        res = risk_auditor.run_risk_audit(trigger_deploy=False)
        self.assertIn("Portfolio Risk Audit Report", res)
        self.assertIn("Max Daily Drawdown adjusted to `3.5%`", res)
        self.assertIn("Loss Cooldown adjusted to `6.0 hours`", res)
        
        # Verify db updates
        conn = sqlite3.connect(self.test_db)
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key='max_daily_drawdown'")
        self.assertEqual(c.fetchone()[0], "3.5")
        
        c.execute("SELECT value FROM settings WHERE key='loss_cooldown_hours'")
        self.assertEqual(c.fetchone()[0], "6.0")
        
        c.execute("SELECT value FROM settings WHERE key='prompt_risk_auditor'")
        self.assertEqual(c.fetchone()[0], "new risk prompt")
        conn.close()

if __name__ == "__main__":
    unittest.main()
