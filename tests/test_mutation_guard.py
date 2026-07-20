import unittest
from unittest.mock import patch
import mutation_guard

class TestMutationGuard(unittest.TestCase):

    @patch('mutation_guard._get_trading_mode')
    def test_is_live_mutation_allowed_paper(self, mock_get_mode):
        mock_get_mode.return_value = 'paper'
        self.assertTrue(mutation_guard.is_live_mutation_allowed())

    @patch('mutation_guard._is_frozen')
    @patch('mutation_guard._get_trading_mode')
    def test_is_live_mutation_allowed_live_frozen(self, mock_get_mode, mock_is_frozen):
        mock_get_mode.return_value = 'live'
        mock_is_frozen.return_value = True
        self.assertFalse(mutation_guard.is_live_mutation_allowed())

    @patch('mutation_guard._is_frozen')
    @patch('mutation_guard._get_trading_mode')
    def test_is_live_mutation_allowed_live_not_frozen(self, mock_get_mode, mock_is_frozen):
        mock_get_mode.return_value = 'live'
        mock_is_frozen.return_value = False
        self.assertTrue(mutation_guard.is_live_mutation_allowed())

    @patch('mutation_guard._is_frozen')
    @patch('mutation_guard._get_trading_mode')
    def test_should_apply_agent_mutation(self, mock_get_mode, mock_is_frozen):
        # target_mode = None, mode = live, frozen = True -> False
        mock_get_mode.return_value = 'live'
        mock_is_frozen.return_value = True
        self.assertFalse(mutation_guard.should_apply_agent_mutation("test_agent"))
        
        # target_mode = 'live', mode doesn't matter, frozen = False -> True
        mock_is_frozen.return_value = False
        self.assertTrue(mutation_guard.should_apply_agent_mutation("test_agent", target_mode='live'))
        
        # target_mode = 'paper', frozen = True -> True
        mock_is_frozen.return_value = True
        self.assertTrue(mutation_guard.should_apply_agent_mutation("test_agent", target_mode='paper'))

    def test_log_blocked_mutation(self):
        # Just ensure it doesn't raise an exception
        try:
            mutation_guard.log_blocked_mutation("agent1", "key1", "val1")
        except Exception as e:
            self.fail(f"log_blocked_mutation raised exception: {e}")

    def test_is_key_protected(self):
        self.assertTrue(mutation_guard.is_key_protected("policy_net_weights_BTC"))
        self.assertTrue(mutation_guard.is_key_protected("max_daily_drawdown"))
        self.assertTrue(mutation_guard.is_key_protected("active_policy_brain"))
        self.assertFalse(mutation_guard.is_key_protected("unprotected_key"))

if __name__ == '__main__':
    unittest.main()
