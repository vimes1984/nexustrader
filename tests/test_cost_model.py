import unittest
from cost_model import CostModel, apply_entry_cost, apply_exit_cost, estimate_round_trip_cost


class TestCostModel(unittest.TestCase):
    def test_apply_entry_cost_buy(self):
        cm = CostModel(taker_fee=0.002, slippage_bps=10)
        price = 100.0
        res = apply_entry_cost(price, "BUY", cm)
        self.assertGreater(res, price)

    def test_apply_entry_cost_sell(self):
        cm = CostModel(taker_fee=0.002, slippage_bps=10)
        price = 100.0
        res = apply_entry_cost(price, "SELL", cm)
        self.assertLess(res, price)

    def test_apply_exit_cost_buy(self):
        cm = CostModel(taker_fee=0.002, slippage_bps=10)
        price = 100.0
        res = apply_exit_cost(price, "BUY", cm)
        self.assertLess(res, price)

    def test_apply_exit_cost_sell(self):
        cm = CostModel(taker_fee=0.002, slippage_bps=10)
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
        self.assertEqual(cm.maker_fee, 0.0016)
        self.assertEqual(cm.taker_fee, 0.0026)
        self.assertEqual(cm.slippage_bps, 10.0)

    def test_apply_entry_cost_with_symbol(self):
        """Entry cost uses symbol-specific spread via get_slippage_bps_for_symbol."""
        cm = CostModel(taker_fee=0.002, slippage_bps=10)
        price = 100.0
        res = apply_entry_cost(price, "BUY", cm, symbol="BTC-USD")
        self.assertGreater(res, price)

    def test_apply_exit_cost_with_symbol(self):
        """Exit cost with symbol uses appropriate slippage."""
        cm = CostModel(maker_fee=0.001, taker_fee=0.002, slippage_bps=10)
        price = 100.0
        res = apply_exit_cost(price, "SELL", cm, symbol="ETH-USD", is_maker=True)
        self.assertGreater(res, price)

    def test_round_trip_with_symbol(self):
        """Round-trip cost should be positive and finite."""
        cm = CostModel()
        res = estimate_round_trip_cost(100.0, cm, symbol="SOL-USD")
        self.assertGreater(res, 0)
        self.assertLess(res, 10)

    def test_cost_round_trip_cost_default(self):
        """Test the evaluate cost model's round_trip_cost function."""
        from evaluation.cost_model import round_trip_cost, cost_as_fraction, would_trade_survive_costs
        cost = round_trip_cost(1000.0)
        self.assertGreater(cost, 0)
        frac = cost_as_fraction(1000.0)
        self.assertGreater(frac, 0)
        self.assertLess(frac, 0.05)
        should_trade, cost_frac = would_trade_survive_costs(0.05)
        self.assertIsInstance(should_trade, bool)
        self.assertGreater(cost_frac, 0)

if __name__ == "__main__":
    unittest.main()
