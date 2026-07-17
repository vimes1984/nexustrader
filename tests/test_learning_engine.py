import unittest
import numpy as np
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from learning_engine import PolicyNetwork, LearningEngine

class TestLearningEngine(unittest.TestCase):
    def setUp(self):
        self.state_dim = 6
        self.hidden_dim = 12
        self.action_dim = 6
        self.lr = 0.05
        self.net = PolicyNetwork(self.state_dim, self.hidden_dim, self.action_dim, self.lr)

    def test_network_dimensions(self):
        self.assertEqual(self.net.W1.shape, (self.state_dim, self.hidden_dim))
        self.assertEqual(self.net.b1.shape, (1, self.hidden_dim))
        self.assertEqual(self.net.W2.shape, (self.hidden_dim, self.action_dim))
        self.assertEqual(self.net.b2.shape, (1, self.action_dim))

    def test_forward_pass_probabilities(self):
        state = np.random.randn(self.state_dim)
        probs = self.net.forward(state)
        # Probabilities should sum to 1.0 (softmax)
        self.assertAlmostEqual(np.sum(probs), 1.0, places=5)
        # All probabilities should be strictly positive
        for p in probs:
            self.assertTrue(p > 0.0)

    def test_backward_pass_updates_weights(self):
        state = np.random.randn(self.state_dim)
        signals = [1, 0, -1, 1, 0, -1]
        direction = "BUY"
        reward = 0.15 # Profit reward

        # Save weights before backward pass
        W1_before = self.net.W1.copy()
        W2_before = self.net.W2.copy()

        # Run forward then backward
        self.net.forward(state)
        self.net.backward(state, signals, direction, reward)

        # Check that weights changed
        self.assertFalse(np.array_equal(self.net.W1, W1_before))
        self.assertFalse(np.array_equal(self.net.W2, W2_before))

    def test_learning_engine_decay(self):
        le = LearningEngine(num_strategies=6, learning_rate=0.1)
        self.assertEqual(le.policy_net.lr, 0.1)
        
        # Test learning and selecting strategy weights
        state = [0.0] * 8
        weights = le.learn_from_trade(state, strategy_signals=[1, -1, 0, 1, 1, -1], trade_direction="BUY", pnl_percent=0.05)
        self.assertEqual(len(weights), 6)
        self.assertAlmostEqual(sum(weights), 1.0, places=5)

if __name__ == "__main__":
    unittest.main()
