"""
Unit tests for PPO Agent (PPOCritic + PPOAgent).

Pure NumPy — no external dependencies beyond numpy.
"""

import unittest
import json
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ppo_agent import PPOCritic, PPOAgent


# ---------------------------------------------------------------------------
# Minimal PolicyNetwork stub that mimics the interface we need.
# ---------------------------------------------------------------------------

class _MinimalPolicyNet:
    """Duck-typed stand-in for learning_engine.PolicyNetwork."""

    def __init__(self, state_dim=4, action_dim=3, hidden_dim=6,
                 hidden_layers=1, lr=0.05, optimizer="Adam"):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.hidden_dim = hidden_dim
        self.hidden_layers = hidden_layers
        self.lr = lr
        self.optimizer = optimizer

        # Simple 1-hidden-layer policy
        np.random.seed(42)
        self.W = [np.random.randn(state_dim, hidden_dim) * 0.1,
                  np.random.randn(hidden_dim, action_dim) * 0.1]
        self.b = [np.zeros((1, hidden_dim)), np.zeros((1, action_dim))]

        # Adam state
        self.m_W = [np.zeros_like(w) for w in self.W]
        self.m_b = [np.zeros_like(b) for b in self.b]
        self.v_W = [np.zeros_like(w) for w in self.W]
        self.v_b = [np.zeros_like(b) for b in self.b]
        self.t = 0
        self.a = []  # activations cache
        self.z = []  # pre-activations cache

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
        # Softmax output
        e_z = np.exp(z_out - np.max(z_out, axis=1, keepdims=True))
        probs = e_z / (np.sum(e_z, axis=1, keepdims=True) + 1e-12)
        self.a.append(probs)
        return probs[0]

    def _apply_gradients(self, dW, db):
        self.t += 1
        for i in range(len(self.W)):
            b1, b2, eps = 0.9, 0.999, 1e-8
            self.m_W[i] = b1 * self.m_W[i] + (1 - b1) * dW[i]
            self.m_b[i] = b1 * self.m_b[i] + (1 - b1) * db[i]
            self.v_W[i] = b2 * self.v_W[i] + (1 - b2) * (dW[i] ** 2)
            self.v_b[i] = b2 * self.v_b[i] + (1 - b2) * (db[i] ** 2)
            m_wh = self.m_W[i] / (1 - b1 ** self.t)
            m_bh = self.m_b[i] / (1 - b1 ** self.t)
            v_wh = self.v_W[i] / (1 - b2 ** self.t)
            v_bh = self.v_b[i] / (1 - b2 ** self.t)
            self.W[i] -= self.lr * m_wh / (np.sqrt(v_wh) + eps)
            self.b[i] -= self.lr * m_bh / (np.sqrt(v_bh) + eps)

    def to_json(self):
        return json.dumps({
            "W": [w.tolist() for w in self.W],
            "b": [b.tolist() for b in self.b],
            "m_W": [mw.tolist() for mw in self.m_W],
            "m_b": [mb.tolist() for mb in self.m_b],
            "v_W": [vw.tolist() for vw in self.v_W],
            "v_b": [vb.tolist() for vb in self.v_b],
            "t": self.t,
        })

    def from_json(self, s):
        data = json.loads(s)
        self.W = [np.array(w) for w in data["W"]]
        self.b = [np.array(b) for b in data["b"]]
        self.m_W = [np.array(mw) for mw in data.get("m_W",
                    [np.zeros_like(w) for w in self.W])]
        self.m_b = [np.array(mb) for mb in data.get("m_b",
                    [np.zeros_like(b) for b in self.b])]
        self.v_W = [np.array(vw) for vw in data.get("v_W",
                    [np.zeros_like(w) for w in self.W])]
        self.v_b = [np.array(vb) for vb in data.get("v_b",
                    [np.zeros_like(b) for b in self.b])]
        self.t = data.get("t", 0)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPPOCritic(unittest.TestCase):

    def setUp(self):
        np.random.seed(42)

    def test_forward_scalar_output(self):
        critic = PPOCritic(state_dim=4, hidden_dim=6, hidden_layers=1)
        state = np.array([0.1, -0.2, 0.3, 0.4])
        val = critic.forward(state)
        self.assertIsInstance(val, float)
        self.assertTrue(np.isfinite(val))

    def test_forward_batchable(self):
        critic = PPOCritic(state_dim=2, hidden_dim=4, hidden_layers=2)
        state = np.array([[0.5, -0.5]])
        val = critic.forward(state)
        self.assertIsInstance(val, float)

    def test_update_reduces_loss(self):
        critic = PPOCritic(state_dim=2, hidden_dim=4, hidden_layers=1,
                           learning_rate=0.1)
        state = np.array([1.0, 2.0])
        target = 1.5
        loss_before = (critic.forward(state) - target) ** 2
        for _ in range(50):
            critic.update(state, target)
        loss_after = (critic.forward(state) - target) ** 2
        self.assertLess(loss_after, loss_before)

    def test_update_batch_converges(self):
        critic = PPOCritic(state_dim=2, hidden_dim=6, hidden_layers=1,
                           learning_rate=0.05)
        states = [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]
        targets = [0.5, 1.0, 1.5]
        errors_before = sum((critic.forward(s) - t) ** 2
                            for s, t in zip(states, targets))
        for _ in range(100):
            critic.update_batch(states, targets)
        errors_after = sum((critic.forward(s) - t) ** 2
                           for s, t in zip(states, targets))
        self.assertLess(errors_after, errors_before)

    def test_serialization_round_trip(self):
        critic = PPOCritic(state_dim=4, hidden_dim=6, hidden_layers=1,
                           learning_rate=0.05, optimizer="Adam")
        state = np.array([1.0, 2.0, 3.0, 4.0])
        original_val = critic.forward(state)
        s = critic.to_json()
        data = json.loads(s)
        self.assertIn("W", data)
        self.assertEqual(len(data["W"]), 2)  # 1 hidden + 1 output

        # Restore into fresh critic
        critic2 = PPOCritic(state_dim=4, hidden_dim=6, hidden_layers=1,
                            learning_rate=0.05, optimizer="Adam")
        critic2.from_json(s)
        restored_val = critic2.forward(state)
        self.assertAlmostEqual(original_val, restored_val, places=10)

    def test_rmsprop_optimizer(self):
        critic = PPOCritic(state_dim=2, hidden_dim=4, hidden_layers=1,
                           learning_rate=0.01, optimizer="RMSprop")
        state = np.array([0.5, -0.5])
        target = 0.0
        loss_before = (critic.forward(state) - target) ** 2
        for _ in range(30):
            critic.update(state, target)
        loss_after = (critic.forward(state) - target) ** 2
        self.assertLess(loss_after, loss_before)

    def test_sgd_optimizer(self):
        critic = PPOCritic(state_dim=2, hidden_dim=4, hidden_layers=1,
                           learning_rate=0.01, optimizer="SGD")
        state = np.array([1.0, -1.0])
        target = 0.5
        for _ in range(30):
            critic.update(state, target)
        self.assertTrue(np.isfinite(critic.forward(state)))


class TestPPOAgent(unittest.TestCase):

    def setUp(self):
        np.random.seed(42)
        self.policy_net = _MinimalPolicyNet(
            state_dim=4, action_dim=3, hidden_dim=6
        )
        self.agent = PPOAgent(self.policy_net)

    def test_get_action_returns_distribution(self):
        state = np.array([0.1, -0.2, 0.3, 0.4])
        probs = self.agent.get_action(state)
        self.assertEqual(len(probs), 3)
        self.assertAlmostEqual(sum(probs), 1.0, places=5)
        self.assertTrue(all(p >= 0 for p in probs))

    def test_get_state_value_returns_scalar(self):
        state = np.array([0.1, -0.2, 0.3, 0.4])
        val = self.agent.get_state_value(state)
        self.assertIsInstance(val, float)
        self.assertTrue(np.isfinite(val))

    def test_compute_gae_shape(self):
        T = 5
        rewards = np.array([1.0, -0.5, 0.3, 0.0, 0.2])
        values = np.array([0.5, 0.6, 0.4, 0.5, 0.55, 0.5])  # T+1
        dones = np.array([False, False, False, False, False])
        adv, rets = self.agent.compute_gae(rewards, values, dones)
        self.assertEqual(adv.shape, (T,))
        self.assertEqual(rets.shape, (T,))
        self.assertTrue(np.all(np.isfinite(adv)))
        self.assertTrue(np.all(np.isfinite(rets)))

    def test_compute_gae_terminal_state(self):
        rewards = np.array([1.0, -0.5])
        values = np.array([0.5, 0.6, 0.0])
        dones = np.array([False, True])
        adv, rets = self.agent.compute_gae(rewards, values, dones)
        self.assertEqual(adv.shape, (2,))
        self.assertEqual(rets.shape, (2,))

    def test_update_returns_info_dict(self):
        B = 4
        states = np.random.randn(B, 4).astype(np.float64)
        actions = np.array([0, 1, 2, 0], dtype=np.float64)
        old_log_probs = np.full(B, np.log(1.0 / 3))  # uniform
        advantages = np.random.randn(B)
        returns = np.random.randn(B)

        info = self.agent.update(states, actions, old_log_probs,
                                 advantages, returns)
        self.assertIn('actor_loss', info)
        self.assertIn('entropy', info)
        self.assertIn('clip_frac', info)
        self.assertIn('approx_kl', info)
        self.assertTrue(np.isfinite(info['actor_loss']))

    def test_update_actor_weights_change(self):
        B = 8
        states = np.random.randn(B, 4).astype(np.float64)
        actions = np.array([0, 1, 2, 0, 1, 2, 0, 1], dtype=np.float64)
        old_log_probs = np.full(B, np.log(1.0 / 3))
        advantages = np.ones(B)
        returns = np.ones(B)

        w_before = [w.copy() for w in self.agent.policy_net.W]
        self.agent.update(states, actions, old_log_probs,
                          advantages, returns)
        for before, after in zip(w_before, self.agent.policy_net.W):
            self.assertFalse(np.allclose(before, after),
                             msg="Weights should change after update")

    def test_train_on_buffer_small(self):
        """Buffer too small should return None."""
        from replay_buffer import PrioritizedExperienceReplay
        buf = PrioritizedExperienceReplay(capacity=10)
        for _ in range(3):
            buf.add(np.random.randn(4), 1, 0.1, np.random.randn(4), False)
        result = self.agent.train_on_buffer(buf, batch_size=8)
        self.assertIsNone(result)

    def test_serialization_round_trip(self):
        state = np.array([0.1, -0.2, 0.3, 0.4])
        original_action = self.agent.get_action(state).copy()
        original_value = self.agent.get_state_value(state)

        s = self.agent.to_json()
        new_policy = _MinimalPolicyNet(
            state_dim=4, action_dim=3, hidden_dim=6
        )
        restored = PPOAgent.from_json(s, base_policy_net=new_policy)

        after_action = restored.get_action(state)
        after_value = restored.get_state_value(state)

        # Action distribution should differ if weights differ,
        # but the round-trip should be consistent
        self.assertEqual(len(after_action), 3)
        self.assertAlmostEqual(original_value, after_value, places=5)
        self.assertTrue(np.all(np.isfinite(after_action)))

    def test_lr_decay(self):
        lr_before = self.agent.policy_net.lr
        B = 4
        states = np.random.randn(B, 4).astype(np.float64)
        actions = np.array([0, 1, 2, 0], dtype=np.float64)
        old_log_probs = np.full(B, np.log(1.0 / 3))
        advantages = np.random.randn(B)
        returns = np.random.randn(B)

        self.agent.update(states, actions, old_log_probs,
                          advantages, returns)
        lr_after = self.agent.policy_net.lr
        self.assertLess(lr_after, lr_before)


if __name__ == "__main__":
    unittest.main()
