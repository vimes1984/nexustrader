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

    def test_entropy_increases_with_uniform_distribution(self):
        """When the policy is near-uniform, entropy term should push it toward
        higher entropy (more uniform), keeping strategies alive."""
        net = PolicyNetwork(state_dim=8, hidden_dim=12, action_dim=6, learning_rate=0.01)
        state = np.random.randn(8)
        signals = [0.5, 0.3, 0.1, 0.05, 0.03, 0.02]
        
        # Store probs before training
        probs_before = net.forward(state, training=False)
        entropy_before = -np.sum(probs_before * np.log(probs_before + 1e-9))
        
        # Run several low-reward backward passes to see entropy effect dominate
        for _ in range(5):
            net.backward(state, signals, "BUY", reward=0.0)
        
        probs_after = net.forward(state, training=False)
        entropy_after = -np.sum(probs_after * np.log(probs_after + 1e-9))
        
        # With zero reward, entropy bonus should increase entropy (more uniform)
        self.assertGreaterEqual(entropy_after, entropy_before - 0.01)

    def test_entropy_gradient_sign(self):
        """Entropy gradient should push toward increasing entropy (more uniform).
        Verify that dL/dz has the correct sign: for entropy bonus H = -sum(pi*log(pi)),
        gradient descent on -β*H increases H (entropy grows).
        """
        net = PolicyNetwork(state_dim=8, hidden_dim=12, action_dim=4, learning_rate=0.01)
        state = np.random.randn(8)
        signals = [0.4, 0.3, 0.2, 0.1]
        
        probs_before = net.forward(state, training=False)
        entropy_before = -np.sum(probs_before * np.log(probs_before + 1e-9))
        
        # Maximum entropy for 4 actions = log(4) ≈ 1.386
        max_entropy = np.log(4)
        
        # Run many zero-reward backward passes — entropy should increase toward max
        for _ in range(50):
            net.backward(state, signals, "BUY", reward=0.0)
        
        probs_after = net.forward(state, training=False)
        entropy_after = -np.sum(probs_after * np.log(probs_after + 1e-9))
        
        # Entropy should have increased (moved toward uniform/max)
        self.assertGreater(entropy_after, entropy_before)
        # Should be closer to max entropy
        delta_before = max_entropy - entropy_before
        delta_after = max_entropy - entropy_after
        self.assertLess(delta_after, delta_before)

    def test_weight_floor_preserves_total_mass(self):
        """select_weights with weight floor should produce weights summing to 1."""
        le = LearningEngine(num_strategies=6, learning_rate=0.01, weight_floor=0.05)
        state = np.random.randn(8)
        weights = le.select_weights(state)
        self.assertAlmostEqual(sum(weights), 1.0, places=5)
        # No weight should be below floor (accounting for redistribution precision)
        for w in weights:
            self.assertGreaterEqual(w, 0.04, msg=f"Weight {w} below floor (tolerance)")

    def test_weight_floor_prevents_zero_strategies(self):
        """With weight_floor, every strategy should have non-negligible weight."""
        le = LearningEngine(num_strategies=12, learning_rate=0.01, weight_floor=0.02)
        state = np.random.randn(8)
        weights = le.select_weights(state)
        nonzero = sum(1 for w in weights if w > 0.001)
        self.assertEqual(nonzero, 12, msg=f"Only {nonzero}/12 strategies have weight > 0.001")

if __name__ == "__main__":
    unittest.main()
