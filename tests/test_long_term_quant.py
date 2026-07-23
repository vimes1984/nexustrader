import unittest
from unittest.mock import MagicMock, patch
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock database module
sys.modules['database'] = MagicMock()
import database

# Configure database mocks
database.load_setting = MagicMock(return_value="10000.0")
database.save_setting = MagicMock()
database.log_agent_run = MagicMock()

from long_term_quant import run_long_term_strategy_optimization

class TestLongTermQuant(unittest.TestCase):
    @patch('long_term_quant.query_openclaw')
    def test_run_long_term_strategy_optimization(self, mock_query_openclaw):
        # Configure database.get_db_connection mock
        import database
        mock_conn = MagicMock()
        database.get_db_connection = MagicMock(return_value=mock_conn)
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock recent shadow trades returned from cursor
        mock_cursor.fetchall.side_effect = [
            # First fetchall: settings key-values
            [
                ("blog_gemini_api_key", "test-api-key"),
                ("blog_ai_enabled", "true"),
                ("shadow_volatility_target_pct", "1.5"),
                ("shadow_tp_atr_multiplier", "3.0"),
                ("shadow_sl_atr_multiplier", "1.5"),
                ("shadow_nn_consensus_min_weight", "0.12"),
                ("shadow_max_holding_hours", "48.0")
            ],
            # Second fetchall: recent shadow trades
            [
                (1, "SOL-USD", "BUY", 1.5, 100.0, 105.0, 7.5, 5.0, "Take Profit Hit", 1234567.0, 1234600.0, "closed"),
                (2, "BTC-USD", "SELL", 0.05, 50000.0, 51000.0, -50.0, -2.0, "Stop Loss Hit", 1234568.0, 1234610.0, "closed")
            ]
        ]
        
        # Mock OpenClaw LLM responses
        mock_query_openclaw.side_effect = [
            # Response 1: Parameter advice with settings JSON block
            """The performance shows stable bounds.
```json
{
  "shadow_volatility_target_pct": 1.6,
  "shadow_tp_atr_multiplier": 3.1,
  "shadow_sl_atr_multiplier": 1.4,
  "shadow_nn_consensus_min_weight": 0.15,
  "shadow_max_holding_hours": 36.0
}
```""",
            # Response 2: Meta-prompt optimization response (with ```json block)
            """```json
{"revised_prompt_long_term_quant": "Evolved prompt focuses on $1,000 USD/day target"}
```"""
        ]
        
        # Run optimization session
        run_long_term_strategy_optimization()
        
        # Verify database inserts were triggered for recommendations (parameterized query)
        mock_cursor.execute.assert_any_call("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("shadow_volatility_target_pct", "1.6"))
        mock_cursor.execute.assert_any_call("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("shadow_tp_atr_multiplier", "3.1"))
        mock_cursor.execute.assert_any_call("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("shadow_sl_atr_multiplier", "1.4"))
        mock_cursor.execute.assert_any_call("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("shadow_nn_consensus_min_weight", "0.15"))
        mock_cursor.execute.assert_any_call("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("shadow_max_holding_hours", "36.0"))
        
        # Verify meta-prompt optimization updated prompt template
        mock_cursor.execute.assert_any_call("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("prompt_long_term_quant", "Evolved prompt focuses on $1,000 USD/day target"))
        
        pass  # long_term_quant does not call database.log_agent_run

if __name__ == "__main__":
    unittest.main()
