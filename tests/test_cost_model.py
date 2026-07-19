import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.cost_model import (
    round_trip_cost, cost_as_fraction, would_trade_survive_costs,
    adjust_for_liquidity,
)


class TestCostModel(unittest.TestCase):

    def test_round_trip_cost_positive(self):
        cost = round_trip_cost(1000.0)
        self.assertGreater(cost, 0)
        self.assertLess(cost, 1000.0)

    def test_cost_as_fraction_range(self):
        frac = cost_as_fraction(1000.0)
        self.assertGreater(frac, 0)
        self.assertLess(frac, 0.1)

    def test_cost_as_fraction_low_fees(self):
        frac = cost_as_fraction(1000.0, maker_fee=0.0, taker_fee=0.0, spread=0.0, slippage=0.0)
        self.assertEqual(frac, 0.0)

    def test_would_trade_survive_costs_profitable(self):
        # 5% expected return easily clears ~0.35% costs
        safe, cost = would_trade_survive_costs(0.05)
        self.assertTrue(safe)
        self.assertGreater(cost, 0)

    def test_would_trade_survive_costs_tiny_edge(self):
        # 0.1% expected return — below costs
        safe, cost = would_trade_survive_costs(0.001)
        self.assertFalse(safe)

    def test_would_trade_survive_costs_low_edge_multiple(self):
        # 0.7% with maker fees and min_edge_multiple=1.0
        # maker costs: 0.001+0.001+0.0005+0.001 = 0.0035 = 0.35%
        # 0.007 >= 0.0035 * 1.0 → passes
        safe, cost = would_trade_survive_costs(0.007, is_maker=True, min_edge_multiple=1.0)
        self.assertTrue(safe)

    def test_adjust_for_liquidity_major(self):
        params = adjust_for_liquidity("BTC-USD")
        self.assertLess(params["spread"], 0.001)

    def test_adjust_for_liquidity_medium(self):
        params = adjust_for_liquidity("ATOM-USD")
        self.assertEqual(params["spread"], 0.001)

    def test_adjust_for_liquidity_unknown(self):
        params = adjust_for_liquidity("SHIB-USD")
        self.assertEqual(params["spread"], 0.003)


if __name__ == "__main__":
    unittest.main()
