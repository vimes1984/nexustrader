import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading_modes import (
    validate_mode, ns, isolate_key,
    MODE_RESEARCH, MODE_PAPER, MODE_LIVE,
)


class TestTradingModes(unittest.TestCase):

    def test_validate_mode_valid(self):
        self.assertEqual(validate_mode("paper"), MODE_PAPER)
        self.assertEqual(validate_mode("Live"), MODE_LIVE)
        self.assertEqual(validate_mode("  research  "), MODE_RESEARCH)

    def test_validate_mode_invalid(self):
        with self.assertRaises(ValueError):
            validate_mode("production")

    def test_ns_paper(self):
        result = ns("policy_net_weights_BTC-USD", MODE_PAPER)
        self.assertEqual(result, f"{MODE_RESEARCH}:policy_net_weights_BTC-USD")

    def test_ns_live(self):
        result = ns("loss_cooldown_hours", MODE_LIVE)
        self.assertEqual(result, f"{MODE_LIVE}:loss_cooldown_hours")

    def test_isolate_live_key(self):
        mode, key = isolate_key("live:policy_net_weights_BTC")
        self.assertEqual(mode, MODE_LIVE)
        self.assertEqual(key, "policy_net_weights_BTC")

    def test_isolate_research_key(self):
        mode, key = isolate_key("research:loss_cooldown_hours")
        self.assertEqual(mode, MODE_RESEARCH)
        self.assertEqual(key, "loss_cooldown_hours")

    def test_isolate_unnamespaced(self):
        mode, key = isolate_key("trading_mode")
        self.assertEqual(mode, MODE_RESEARCH)
        self.assertEqual(key, "trading_mode")


if __name__ == "__main__":
    unittest.main()
