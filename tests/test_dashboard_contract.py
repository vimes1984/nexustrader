import unittest
import os
import sys
import json
import re

# Setup sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class TestDashboardContract(unittest.TestCase):
    def test_static_dom_integrity(self):
        """Verifies that all critical DOM elements queried by app_v2.js exist in index.html."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        js_path = os.path.join(base_dir, "dashboard", "app_v2.js")
        html_path = os.path.join(base_dir, "dashboard", "index.html")
        
        self.assertTrue(os.path.exists(js_path), "app_v2.js is missing!")
        self.assertTrue(os.path.exists(html_path), "index.html is missing!")
        
        with open(js_path, "r", encoding="utf-8") as f:
            js_content = f.read()
            
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
            
        # Statically extract document.getElementById matches
        matches = re.findall(r'document\.getElementById\([\'"]([a-zA-Z0-9_-]+)[\'"]\)', js_content)
        queried_ids = set(matches)
        
        # Statically extract all id attribute values in index.html
        html_ids = set(re.findall(r'\bid=[\'"]([a-zA-Z0-9_-]+)[\'"]', html_content))
        
        # Define critical IDs that are mandatory for dashboard function
        critical_ids = [
            "val-equity", "val-balance", "val-winrate", "val-trade-count",
            "val-total-pnl", "val-total-pnl-percent", "val-max-drawdown",
            "main-chart", "ticker-switcher-bar", "recent-trades-list",
            "weights-container", "bot-status", "status-text"
        ]
        
        for cid in critical_ids:
            self.assertIn(cid, html_ids, f"Critical DOM element with ID '{cid}' is referenced in JS but missing from index.html!")

    def test_endpoint_responses(self):
        """Verifies that key REST endpoints return correct structures under FastAPI."""
        # Mock database settings load/save
        from unittest.mock import patch, MagicMock
        sys.modules['ccxt'] = MagicMock()
        database = sys.modules.get('database')
        if not database:
            sys.modules['database'] = MagicMock()
            database = sys.modules['database']
        
        database.load_setting.side_effect = lambda key, default="": "gemini" if "provider" in key else ""
        database.save_setting = MagicMock()
        database.load_active_assets.return_value = []
        database.list_policy_brains.return_value = []
        
        with patch('main.update_crontab_schedule'):
            import main
            
        # Test API assets response
        assets_res = main.get_assets()
        self.assertIsInstance(assets_res, list)
        
        # Test API system prompts response
        prompts_res = main.get_prompts()
        self.assertIn("prompt_quant", prompts_res)
        self.assertIn("prompt_dev", prompts_res)
        
        # Test LLM provider config endpoint
        llm_res = main.get_agent_llm_config()
        self.assertEqual(llm_res["provider"], "gemini")

if __name__ == "__main__":
    unittest.main()
