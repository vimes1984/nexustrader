import unittest
from trading_modes import normalize_trading_mode, namespaced_key, load_trading_mode

class TestTradingMode(unittest.TestCase):
    def test_normalize_trading_mode(self):
        self.assertEqual(normalize_trading_mode(""), "paper")
        self.assertEqual(normalize_trading_mode(None), "paper")
        self.assertEqual(normalize_trading_mode("LiVe"), "live")
        self.assertEqual(normalize_trading_mode("invalid"), "paper")
        self.assertEqual(normalize_trading_mode("research"), "research")

    def test_namespaced_key(self):
        self.assertEqual(namespaced_key("live", "weights"), "live:weights")
        self.assertEqual(namespaced_key("paper", "key"), "research:key")
        self.assertEqual(namespaced_key("research", "key"), "research:key")

    def test_load_trading_mode(self):
        self.assertEqual(load_trading_mode(), "paper")

if __name__ == "__main__":
    unittest.main()
