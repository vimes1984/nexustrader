import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import json

# Setup sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock ccxt, database, and background tasks before importing main
sys.modules['ccxt'] = MagicMock()
sys.modules['database'] = MagicMock()
import database

# Mock settings load/save
def load_setting_mock(key, default=None):
    if key == "loss_cooldown_hours":
        return "4.0"
    if key == "opt_tp_multiplier":
        return "2.5"
    if key == "opt_sl_multiplier":
        return "1.5"
    if key == "max_daily_drawdown":
        return "5.0"
    if key == "nn_learning_rate":
        return "0.15"
    if key == "nn_weight_floor":
        return "0.05"
    if key == "trailing_stop_enabled":
        return "false"
    if key == "risk_mode":
        return "conservative"
    return default or f"mocked_{key}"

database.load_setting = MagicMock(side_effect=load_setting_mock)
database.save_setting = MagicMock()

# Import main router endpoints
with patch('main.update_crontab_schedule') as mock_cron:
    import main

class TestMainApi(unittest.TestCase):
    def setUp(self):
        database.load_setting.reset_mock()
        database.save_setting.reset_mock()
        database.load_setting.side_effect = load_setting_mock

    @patch('os.path.exists', return_value=True)
    @patch('builtins.open', new_callable=MagicMock)
    def test_get_system_config_reads_config_file(self, mock_open, mock_exists):
        config_data = {
            "trading_mode": "paper",
            "broker": "kraken",
            "api_credentials": {
                "api_key": "test_key",
                "api_secret": "test_secret"
            }
        }
        
        # Mock file read
        mock_file = MagicMock()
        mock_file.read.return_value = json.dumps(config_data)
        mock_open.return_value.__enter__.return_value = mock_file

        # Call get_system_config route
        res = main.get_system_config()
        
        self.assertEqual(res["trading_mode"], "paper")
        self.assertEqual(res["broker"], "kraken")
        self.assertEqual(res["api_key"], "test_key")
        self.assertEqual(res["api_secret"], "test_secret")

    def test_get_prompts(self):
        # Setup load_setting behavior
        database.load_setting.side_effect = lambda key, default=None: f"mocked_{key}"
        
        res = main.get_prompts()
        
        self.assertEqual(res["prompt_quant"], "mocked_prompt_self_improvement")
        self.assertEqual(res["prompt_dev"], "mocked_prompt_self_developer")
        self.assertEqual(res["prompt_blog"], "mocked_prompt_blog_agent")
        self.assertEqual(res["prompt_nn"], "mocked_prompt_nn_agent")
        self.assertEqual(res["prompt_sentiment"], "mocked_prompt_sentiment_agent")
        self.assertEqual(res["prompt_risk"], "mocked_prompt_risk_auditor")
        self.assertEqual(res["prompt_allocator"], "mocked_prompt_allocator_agent")

    def test_update_prompts_saves_to_db(self):
        req = main.PromptsUpdateRequest(
            prompt_quant="new_q",
            prompt_dev="new_d",
            prompt_blog="new_b",
            prompt_nn="new_n",
            prompt_sentiment="new_s",
            prompt_risk="new_r",
            prompt_allocator="new_a"
        )
        res = main.update_prompts(req)
        
        self.assertEqual(res["status"], "success")
        # Verify database save calls
        database.save_setting.assert_any_call("prompt_self_improvement", "new_q")
        database.save_setting.assert_any_call("prompt_self_developer", "new_d")
        database.save_setting.assert_any_call("prompt_blog_agent", "new_b")
        database.save_setting.assert_any_call("prompt_nn_agent", "new_n")
        database.save_setting.assert_any_call("prompt_sentiment_agent", "new_s")
        database.save_setting.assert_any_call("prompt_risk_auditor", "new_r")
        database.save_setting.assert_any_call("prompt_allocator_agent", "new_a")

    def test_get_system_schedule(self):
        database.load_setting.side_effect = lambda key, default=None: int(default)
        
        res = main.get_system_schedule()
        
        self.assertEqual(res["daily_agent_hour"], 0)
        self.assertEqual(res["weekly_agent_day"], 0)
        self.assertEqual(res["weekly_agent_hour"], 23)
        self.assertEqual(res["nn_agent_hour"], 1)
        self.assertEqual(res["sentiment_agent_hour"], 2)
        self.assertEqual(res["risk_auditor_hour"], 3)

    def test_get_assets_endpoint(self):
        database.load_active_assets.return_value = [
            {"ticker": "BTC-USD", "is_active": 1, "tp_multiplier": 2.5, "sl_multiplier": 1.5, "kelly_ceiling": 0.2}
        ]
        database.list_policy_brains.return_value = [{"name": "Brain-A"}]
        
        res = main.get_assets()
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["ticker"], "BTC-USD")
        self.assertIn("Brain-A", res[0]["brains"])
        self.assertIn("Default Brain", res[0]["brains"])
        
    def test_save_asset_endpoint(self):
        database.save_active_asset.reset_mock()
        database.save_active_asset.return_value = True
        res = main.save_asset(ticker="BTC-USD", is_active=True, tp_multiplier=2.5, sl_multiplier=1.5, kelly_ceiling=0.2)
        self.assertEqual(res["status"], "success")
        database.save_active_asset.assert_called_once_with("BTC-USD", True, 2.5, 1.5, 0.2)
        
    def test_get_agent_llm_config_endpoint(self):
        database.load_setting.side_effect = lambda key, default="": "gemini" if key == "agent_llm_provider" else "sk-123456789" if key == "agent_llm_api_key" else "test-val"
        res = main.get_agent_llm_config()
        self.assertEqual(res["provider"], "gemini")
        self.assertEqual(res["api_key"], "sk-1****6789")
        
    def test_save_agent_llm_config_endpoint(self):
        res = main.save_agent_llm_config(provider="openai", base_url="https://test.com", model="gpt-4", api_key="sk-newkey")
        self.assertEqual(res["status"], "success")
        database.save_setting.assert_any_call("agent_llm_provider", "openai")
        database.save_setting.assert_any_call("agent_llm_base_url", "https://test.com")
        database.save_setting.assert_any_call("agent_llm_model", "gpt-4")
        database.save_setting.assert_any_call("agent_llm_api_key", "sk-newkey")

    @patch('allocator_agent.run_allocator_self_improvement', return_value="Success! Designed rebalance.")
    def test_trigger_allocator_endpoint(self, mock_run):
        res = main.trigger_allocator()
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["log"], "Success! Designed rebalance.")

    def test_get_agent_optimizations_endpoint(self):
        database.load_optimizations.return_value = [
            {"id": 1, "timestamp": 1234567, "agent": "PhD Quant Agent", "parameter": "risk_mode", "old_value": "conservative", "new_value": "aggressive", "rationale": "Testing"}
        ]
        res = main.get_agent_optimizations()
        self.assertEqual(res["status"], "success")
        self.assertEqual(len(res["optimizations"]), 1)
        self.assertEqual(res["optimizations"][0]["agent"], "PhD Quant Agent")

if __name__ == "__main__":
    unittest.main()
