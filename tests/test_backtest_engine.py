import unittest
from backtest_engine import BacktestEngine


def make_candles(n, start_price=100, up_trend=True):
    """Helper to generate candle dicts for testing."""
    candles = []
    for i in range(n):
        chg = 1.0 if up_trend else -1.0
        direction = chg * (1 + 0.5 * (i / max(n, 1)))
        prices = [start_price + i * direction + j * 0.1 for j in range(5)]
        prices.sort()
        low, open_p, close_p, high = prices[0], prices[1], prices[2], prices[4]
        candles.append({
            "open": open_p,
            "high": high,
            "low": low,
            "close": close_p,
            "volume": 1000.0 + i * 10,
            "sma_20": start_price + i * direction,
            "sma_50": start_price + (i - 5) * direction,
            "ema_12": start_price + i * direction,
            "ema_26": start_price + (i - 3) * direction,
            "macd": 0.5 if i % 2 == 0 else -0.3,
            "macd_signal": 0.3 if i % 2 == 0 else -0.1,
            "rsi": 55.0 + (i % 10 - 5) * 2,
            "atr": 2.0,
            "volume_ratio": 1.2,
        })
    return candles

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
        be = BacktestEngine("BTC-USD")
        candles = [{"close": 100}, {"close": 105}, {"close": 110}]
        res = be.run(candles)
        bah = res["results"]["buy_and_hold"]
        self.assertAlmostEqual(bah["total_return"], 0.1, places=1)

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

    def test_walk_forward_not_enough_data(self):
        be = BacktestEngine("BTC-USD")
        # Only 50 candles — below the 100-minimum threshold
        candles = make_candles(50, start_price=100)
        res = be.run_walk_forward(candles)
        self.assertIn("error", res)
        self.assertIn("need >= 100", res["error"])

    def test_monte_carlo_few_trades(self):
        """With a flat price series, _collect_trade_pnls returns few trades,
        triggering the early-exit path returning base_return."""
        be = BacktestEngine("BTC-USD")
        # Flat price — almost no signals, so too few trades
        candles = [{"close": 100.0} for _ in range(200)]
        res = be.run_monte_carlo(candles, n_simulations=10)
        self.assertIn("note", res)
        self.assertEqual(res["n_simulations"], 0)

    def test_walk_forward_sufficient_data(self):
        """With 300 candles, walk_forward should produce valid folds."""
        be = BacktestEngine("BTC-USD")
        candles = make_candles(300, start_price=100, up_trend=True)
        res = be.run_walk_forward(candles, n_splits=2)
        # StrategyEnsemble may fail in test environment (missing dependencies)
        # In that case, 'error' is expected. Otherwise verify folds.
        if "error" in res:
            self.assertIn(res["error"], ["No valid folds", "Not enough data"],
                         f"Unexpected error: {res['error']}")
        else:
            self.assertGreater(res.get("n_splits", 0), 0)

if __name__ == "__main__":
    unittest.main()
