"""
Tests for PPO integration in BacktestEngine.

Verifies that the ppo_agent parameter flows through correctly
and adds ppo_policy results to the output dict.

Skips gracefully when sklearn is not available (standard dev dependency).
"""

import unittest
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cost_model import CostModel

# BacktestEngine imports strategy_engine → sklearn → may not be installed
_BACKTEST_REASON = ""
try:
    from backtest_engine import BacktestEngine
    _BACKTEST_OK = True
except ImportError as e:
    _BACKTEST_OK = False
    _BACKTEST_REASON = str(e)


class _MinimalPolicyNet:
    """Stand-in for PolicyNetwork."""

    def __init__(self, state_dim=4, action_dim=3, hidden_dim=6):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.hidden_dim = hidden_dim
        self.hidden_layers = 1
        self.lr = 0.05
        self.optimizer = "Adam"
        np.random.seed(42)
        self.W = [np.random.randn(state_dim, hidden_dim) * 0.1,
                  np.random.randn(hidden_dim, action_dim) * 0.1]
        self.b = [np.zeros((1, hidden_dim)), np.zeros((1, action_dim))]
        self.m_W = [np.zeros_like(w) for w in self.W]
        self.m_b = [np.zeros_like(b) for b in self.b]
        self.v_W = [np.zeros_like(w) for w in self.W]
        self.v_b = [np.zeros_like(b) for b in self.b]
        self.t = 0
        self.a = []
        self.z = []

    def forward(self, state):
        x = np.atleast_2d(np.asarray(state, dtype=np.float64))
        self.a = [x]
        self.z = []
        for i in range(len(self.W) - 1):
            z = np.dot(self.a[-1], self.W[i]) + self.b[i]
            self.z.append(z)
            a = np.maximum(0, z)
            self.a.append(a)
        z_out = np.dot(self.a[-1], self.W[-1]) + self.b[-1]
        self.z.append(z_out)
        e_z = np.exp(z_out - np.max(z_out, axis=1, keepdims=True))
        probs = e_z / (np.sum(e_z, axis=1, keepdims=True) + 1e-12)
        self.a.append(probs)
        return probs[0]

    def to_json(self):
        import json
        return json.dumps({
            "W": [w.tolist() for w in self.W],
            "b": [b.tolist() for b in self.b],
        })


class _StubPPOAgent:
    """Minimal PPO agent that works with BacktestEngine._run_ppo_policy."""

    def __init__(self):
        self.policy_net = _MinimalPolicyNet(state_dim=4, action_dim=3)

    def get_action(self, state):
        return self.policy_net.forward(state)


@unittest.skipIf(not _BACKTEST_OK, f"BacktestEngine not importable: {_BACKTEST_REASON}")
class TestBacktestPPOIntegration(unittest.TestCase):

    def setUp(self):
        np.random.seed(42)
        cm = CostModel()
        cm.maker_fee = 0.0
        cm.taker_fee = 0.0
        cm.slippage_bps = 0.0
        self.engine = BacktestEngine("PPO-TEST", cm)

    def _candles(self, n=50):
        candles = []
        price = 100.0
        for i in range(n):
            price *= (1 + np.random.randn() * 0.02)
            candles.append({
                "close": round(price, 2),
                "open": round(price * 0.99, 2) if i > 0 else round(price, 2),
                "high": round(price * 1.01, 2),
                "low": round(price * 0.99, 2),
                "volume": round(np.random.uniform(100, 5000), 2),
            })
        return candles

    def test_run_without_ppo(self):
        """Baseline: no ppo_agent → no ppo_policy key in results."""
        candles = self._candles(20)
        res = self.engine.run(candles)
        self.assertNotIn("ppo_policy", res["results"])

    def test_run_with_ppo(self):
        """PPO agent provided → ppo_policy appears in results."""
        candles = self._candles(50)
        ppo = _StubPPOAgent()
        res = self.engine.run(candles, ppo_agent=ppo)
        self.assertIn("ppo_policy", res["results"])
        self.assertIn("total_return", res["results"]["ppo_policy"])
        self.assertIsInstance(res["results"]["ppo_policy"]["total_return"], float)

    def test_ppo_verdict_keys(self):
        """PPO verdict keys present when PPO agent is used."""
        candles = self._candles(60)
        ppo = _StubPPOAgent()
        res = self.engine.run(candles, ppo_agent=ppo)
        v = res["verdict"]
        for key in ("ppo_beats_buy_and_hold", "ppo_beats_ema", "ppo_beats_nexus"):
            self.assertIn(key, v)

    def test_best_ppo_weights(self):
        """best_ppo_weights populated after run with PPO."""
        candles = self._candles(40)
        ppo = _StubPPOAgent()
        res = self.engine.run(candles, ppo_agent=ppo)
        self.assertIn("best_ppo_weights", res)

    def test_paper_live_mode_consistency(self):
        """Trading mode isolation doesn't break PPO data flow."""
        candles = self._candles(30)
        ppo = _StubPPOAgent()
        res_paper = self.engine.run(candles, ppo_agent=ppo)
        cm2 = CostModel()
        cm2.maker_fee = 0.001
        cm2.taker_fee = 0.002
        cm2.slippage_bps = 2.0
        engine_live = BacktestEngine("PPO-TEST", cm2)
        res_live = engine_live.run(candles, ppo_agent=ppo)
        self.assertIn("ppo_policy", res_paper["results"])
        self.assertIn("ppo_policy", res_live["results"])
        self.assertIsInstance(res_paper["results"]["ppo_policy"]["total_return"], float)
        self.assertIsInstance(res_live["results"]["ppo_policy"]["total_return"], float)


if __name__ == "__main__":
    unittest.main()
