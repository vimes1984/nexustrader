import unittest
from performance_metrics import calculate_metrics, PerformanceMetrics

class TestPerformanceMetrics(unittest.TestCase):
    def test_empty_trades(self):
        m = calculate_metrics([], [])
        self.assertEqual(m.trade_count, 0)
        self.assertEqual(m.total_pnl, 0.0)

    def test_metrics_calculation(self):
        trades = [{"pnl": 100}, {"pnl": -50}, {"pnl": 200}, {"pnl": -50}]
        m = calculate_metrics([], trades)
        self.assertEqual(m.trade_count, 4)
        self.assertEqual(m.total_pnl, 200)
        self.assertEqual(m.win_rate, 0.5)
        self.assertEqual(m.profit_factor, 3.0) # 300 / 100
        self.assertEqual(m.avg_winner, 150)
        self.assertEqual(m.avg_loser, -50)
        self.assertEqual(m.expectancy, 50.0)

    def test_no_divide_by_zero(self):
        trades = [{"pnl": 100}, {"pnl": 200}]
        m = calculate_metrics([], trades)
        self.assertEqual(m.profit_factor, float('inf'))

    def test_max_drawdown(self):
        eq = [100.0, 110.0, 99.0, 105.0, 89.1, 120.0]
        m = calculate_metrics(eq, [])
        # Peak 110 -> 99 (10%)
        # Peak 110 -> 89.1 (19%)
        self.assertAlmostEqual(m.max_drawdown, 0.19)

    def test_sharpe_ratio(self):
        eq = [100.0, 101.0, 102.01, 103.0301]
        m = calculate_metrics(eq, [])
        self.assertTrue(m.sharpe > 0)

if __name__ == "__main__":
    unittest.main()
