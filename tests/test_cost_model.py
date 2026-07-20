import unittest
from cost_model import CostModel, apply_entry_cost, apply_exit_cost, estimate_round_trip_cost

class TestCostModel(unittest.TestCase):
    def test_apply_entry_cost_buy(self):
        cm = CostModel(taker_fee=0.002, slippage_bps=10, spread_bps=5)
        price = 100.0
        res = apply_entry_cost(price, "BUY", cm)
        self.assertGreater(res, price)

    def test_apply_entry_cost_sell(self):
        cm = CostModel(taker_fee=0.002, slippage_bps=10, spread_bps=5)
        price = 100.0
        res = apply_entry_cost(price, "SELL", cm)
        self.assertLess(res, price)

    def test_apply_exit_cost_buy(self):
        cm = CostModel(taker_fee=0.002, slippage_bps=10, spread_bps=5)
        price = 100.0
        res = apply_exit_cost(price, "BUY", cm)
        self.assertLess(res, price)

    def test_apply_exit_cost_sell(self):
        cm = CostModel(taker_fee=0.002, slippage_bps=10, spread_bps=5)
        price = 100.0
        res = apply_exit_cost(price, "SELL", cm)
        self.assertGreater(res, price)

    def test_estimate_round_trip_cost(self):
        cm = CostModel()
        res = estimate_round_trip_cost(100.0, cm)
        self.assertGreater(res, 0)
        self.assertLess(res, 10)

    def test_defaults_are_conservative(self):
        cm = CostModel()
        self.assertEqual(cm.maker_fee, 0.001)
        self.assertEqual(cm.taker_fee, 0.002)
        self.assertEqual(cm.slippage_bps, 10.0)
        self.assertEqual(cm.spread_bps, 5.0)

if __name__ == "__main__":
    unittest.main()
