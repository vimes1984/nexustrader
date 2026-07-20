import unittest
from backtest_engine import BacktestEngine
from cost_model import CostModel

class TestBacktestEngine(unittest.TestCase):
    def test_engine_run_dict_structure(self):
        be = BacktestEngine("BTC-USD")
        candles = [{"close": 100}, {"close": 110}]
        res = be.run(candles)
        self.assertIn("symbol", res)
        self.assertIn("period", res)
        self.assertIn("cost_model", res)
        self.assertIn("results", res)
        self.assertIn("verdict", res)

    def test_verdict_tradable(self):
        be = BacktestEngine("BTC-USD")
        res = be.run([])
        self.assertFalse(res["verdict"]["tradable"])

    def test_buy_and_hold_rising(self):
        be = BacktestEngine("BTC-USD", CostModel(maker_fee=0, taker_fee=0, slippage_bps=0, spread_bps=0))
        candles = [{"close": 100}, {"close": 105}, {"close": 110}]
        res = be.run(candles)
        bah = res["results"]["buy_and_hold"]
        self.assertAlmostEqual(bah["total_return"], 0.1)

    def test_random_same_risk_deterministic(self):
        be = BacktestEngine("BTC-USD")
        candles = [{"close": 100}, {"close": 105}, {"close": 110}, {"close": 100}, {"close": 90}]
        res1 = be.run(candles)
        res2 = be.run(candles)
        self.assertEqual(res1["results"]["random_same_risk"]["total_return"], 
                         res2["results"]["random_same_risk"]["total_return"])

    def test_empty_candles(self):
        be = BacktestEngine("BTC-USD")
        res = be.run([])
        self.assertEqual(res["results"]["buy_and_hold"]["total_return"], 0.0)

if __name__ == "__main__":
    unittest.main()
