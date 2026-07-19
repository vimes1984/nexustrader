import unittest
from unittest.mock import patch, MagicMock, mock_open
import os
import sys
import sqlite3
import json

# Setup sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import modules first to avoid mock interference with system library imports
import quant_utils
import agent_self_developer

class TestAgentSelfDeveloper(unittest.TestCase):
    def setUp(self):
        # Ensure temporary test DB path
        self.test_db = "test_nexustrader.db"
        agent_self_developer.DB_PATH = self.test_db
        
        # Initialize test DB tables
        conn = sqlite3.connect(self.test_db)
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('blog_gemini_api_key', 'test-key')")
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('blog_ai_enabled', 'true')")
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('prompt_self_developer', 'You are developer')")
        conn.commit()
        conn.close()

    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    @patch('quant_utils.query_gemini_robust')
    @patch('subprocess.run')
    def test_run_self_developer_success(self, mock_subproc, mock_query):
        # Mock LLM design response
        llm_response = """
{
  "explanation": "Adding alert element",
  "modifications": [
    {
      "file_path": "main.py",
      "replacements": [
        {
          "find": "mock code content",
          "replace": "mock code content updated"
        }
      ]
    }
  ]
}
"""
        meta_response = """
{
  "revised_prompt_self_developer": "new dev prompt"
}
"""
        mock_query.side_effect = [llm_response, meta_response]
        
        # Mock subprocess check_compile and deploy success
        mock_subproc.return_value = MagicMock(returncode=0, stdout="success", stderr="")
        
        # Run self developer inside builtins.open patch context to avoid breaking imports
        with patch('builtins.open', mock_open(read_data="mock code content")) as mock_file:
            res = agent_self_developer.run_self_developer(trigger_deploy=False)
            self.assertTrue(res.startswith("Success"))
        
        # Verify db prompt settings update
        conn = sqlite3.connect(self.test_db)
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key='prompt_self_developer'")
        prompt_val = c.fetchone()[0]
        self.assertEqual(prompt_val, "new dev prompt")
        conn.close()

    def test_run_self_developer_disabled(self):
        # Disable AI
        conn = sqlite3.connect(self.test_db)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('blog_ai_enabled', 'false')")
        conn.commit()
        conn.close()
        
        res = agent_self_developer.run_self_developer(trigger_deploy=False)
        self.assertIn("AI is disabled", res)

if __name__ == "__main__":
    unittest.main()
