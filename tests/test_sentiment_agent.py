import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import sqlite3
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sentiment_agent

class TestSentimentAgent(unittest.TestCase):
    def setUp(self):
        self.test_db = "test_nexustrader_sentiment.db"
        sentiment_agent.DB_PATH = self.test_db
        
        conn = sqlite3.connect(self.test_db)
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY, symbol TEXT, direction TEXT, pnl REAL, exit_reason TEXT)")
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('blog_gemini_api_key', 'test-key')")
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('blog_ai_enabled', 'true')")
        c.execute("INSERT INTO trades (symbol, direction, pnl, exit_reason) VALUES ('ETH-USD', 'BUY', 50.0, 'Take Profit')")
        conn.commit()
        conn.close()

    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    @patch('quant_utils.query_gemini_robust')
    def test_run_sentiment_self_improvement(self, mock_query):
        # Mock LLM design advice and meta revision
        llm_response = """
Sentiment feed analysis: stable performance.
```json
{
  "recommended_news_sentiment_weight": 0.45
}
```
"""
        meta_response = '{"revised_prompt_sentiment_agent": "new sentiment prompt"}'
        mock_query.side_effect = [llm_response, meta_response]
        
        res = sentiment_agent.run_sentiment_self_improvement(trigger_deploy=False)
        self.assertIn("News Sentiment Feeds Sentinel report", res)
        self.assertIn("News Sentiment Weight adjusted to `0.45`", res)
        
        # Verify db updates
        conn = sqlite3.connect(self.test_db)
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key='recommended_news_sentiment_weight'")
        self.assertEqual(c.fetchone()[0], "0.45")
        
        c.execute("SELECT value FROM settings WHERE key='prompt_sentiment_agent'")
        self.assertEqual(c.fetchone()[0], "new sentiment prompt")
        conn.close()

if __name__ == "__main__":
    unittest.main()
