"""
Unit tests for Prioritized Experience Replay buffer.

Pure NumPy + pickle — no external dependencies.
"""

import unittest
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from replay_buffer import PrioritizedExperienceReplay


class TestPrioritizedExperienceReplay(unittest.TestCase):

    def setUp(self):
        np.random.seed(42)

    # ----------------------------------------------------------------
    # Basic add / len
    # ----------------------------------------------------------------

    def test_empty_buffer_len(self):
        buf = PrioritizedExperienceReplay(capacity=100)
        self.assertEqual(len(buf), 0)

    def test_add_one(self):
        buf = PrioritizedExperienceReplay(capacity=100)
        buf.add(np.array([0.1, 0.2]), 1, 0.5, np.array([0.3, 0.4]), False)
        self.assertEqual(len(buf), 1)

    def test_add_until_capacity(self):
        buf = PrioritizedExperienceReplay(capacity=10)
        for i in range(10):
            buf.add(np.array([i]), 0, 0.0, np.array([i + 1]), False)
        self.assertEqual(len(buf), 10)

    def test_add_exceeds_capacity(self):
        buf = PrioritizedExperienceReplay(capacity=5)
        for i in range(10):
            buf.add(np.array([i]), 0, 0.0, np.array([i + 1]), False)
        self.assertEqual(len(buf), 5)

    # ----------------------------------------------------------------
    # Sampling
    # ----------------------------------------------------------------

    def test_sample_returns_correct_structure(self):
        buf = PrioritizedExperienceReplay(capacity=20, seed=42)
        for i in range(10):
            buf.add(np.array([i, i * 2]), float(i), float(i * 0.1),
                    np.array([i + 1, (i + 1) * 2]), False)
        states, actions, rewards, next_states, dones, indices, weights = \
            buf.sample(4)
        self.assertEqual(states.shape, (4, 2))
        self.assertEqual(actions.shape, (4,))
        self.assertEqual(rewards.shape, (4,))
        self.assertEqual(next_states.shape, (4, 2))
        self.assertEqual(dones.shape, (4,))
        self.assertEqual(indices.shape, (4,))
        self.assertEqual(weights.shape, (4,))
        self.assertTrue(np.all(np.isfinite(states)))
        self.assertTrue(np.all(np.isfinite(weights)))
        self.assertTrue(np.all(weights > 0))

    def test_all_dones_flag(self):
        buf = PrioritizedExperienceReplay(capacity=10, seed=42)
        for i in range(5):
            buf.add(np.array([i]), 0, 1.0, np.array([i + 1]), True)
        _, _, _, _, dones, _, _ = buf.sample(3)
        self.assertTrue(np.all(dones == 1.0))

    def test_sample_empty_raises(self):
        buf = PrioritizedExperienceReplay(capacity=10)
        with self.assertRaises(RuntimeError):
            buf.sample(1)

    # ----------------------------------------------------------------
    # Priorities
    # ----------------------------------------------------------------

    def test_higher_priority_samples_more_often(self):
        """Statistical test: high-error samples should be drawn more."""
        buf = PrioritizedExperienceReplay(capacity=10, alpha=2.0, seed=42)
        # 9 experiences with error=0.01 (very low priority)
        for i in range(9):
            buf.add(np.array([i]), 0, 0.0, np.array([i]), False, error=0.01)
        # 1 experience with error=100 (very high priority)
        buf.add(np.array([99]), 0, 0.0, np.array([99]), False, error=100.0)

        counts = np.zeros(10)
        trials = 500
        for _ in range(trials):
            _, _, _, _, _, indices, _ = buf.sample(1)
            counts[indices[0]] += 1

        # The high-error sample (index 9) should be drawn significantly more
        self.assertGreater(counts[9], counts[0],
                           "High-priority sample should be drawn more often")

    def test_update_priorities_changes_sampling(self):
        buf = PrioritizedExperienceReplay(capacity=5, alpha=1.0, seed=42)
        for i in range(3):
            buf.add(np.array([i]), 0, 0.0, np.array([i]), False, error=1.0)

        # Boost priority of index 0
        buf.update_priorities(np.array([0]), np.array([100.0]))
        probs = buf._compute_probs()
        self.assertGreater(probs[0], probs[1])

    # ----------------------------------------------------------------
    # Clear
    # ----------------------------------------------------------------

    def test_clear_empties(self):
        buf = PrioritizedExperienceReplay(capacity=10)
        for i in range(5):
            buf.add(np.array([i]), 0, 0.0, np.array([i]), False)
        self.assertEqual(len(buf), 5)
        buf.clear()
        self.assertEqual(len(buf), 0)

    # ----------------------------------------------------------------
    # Serialisation round-trip
    # ----------------------------------------------------------------

    def test_serialize_deserialize_round_trip(self):
        buf = PrioritizedExperienceReplay(
            capacity=20, alpha=0.7, beta=0.5, beta_increment=0.002, epsilon=1e-5
        )
        for i in range(8):
            buf.add(np.array([i, i * 2]), float(i), float(i * 0.1),
                    np.array([i + 1, (i + 1) * 2]), i % 2 == 0,
                    error=float(i + 1))

        # Sample once to advance beta
        buf.sample(3)

        blob = buf.serialize()
        self.assertIsInstance(blob, bytes)

        restored = PrioritizedExperienceReplay.deserialize(blob)
        self.assertEqual(len(restored), 8)
        self.assertEqual(restored.capacity, 20)
        self.assertAlmostEqual(restored.beta, buf.beta)
        self.assertEqual(restored.pos, buf.pos)

        # Verify state data
        r_s, r_a, r_r, r_ns, r_d, _, _ = restored.sample(4)
        o_s, o_a, o_r, o_ns, o_d, _, _ = buf.sample(4)
        # Same data (though sampling may differ if priorities shifted)
        self.assertEqual(r_s.shape, o_s.shape)

    def test_deserialize_empty_buffer(self):
        buf = PrioritizedExperienceReplay(capacity=5)
        blob = buf.serialize()
        restored = PrioritizedExperienceReplay.deserialize(blob)
        self.assertEqual(len(restored), 0)
        self.assertEqual(restored.capacity, 5)

    # ----------------------------------------------------------------
    # Edge cases
    # ----------------------------------------------------------------

    def test_custom_error_priority(self):
        buf = PrioritizedExperienceReplay(capacity=10, alpha=0.5)
        buf.add(np.array([0]), 0, 0.0, np.array([0]), False, error=42.0)
        # Priority = (|42| + 1e-6)^0.5 ≈ 6.48
        expected = (42.0 + 1e-6) ** 0.5
        self.assertAlmostEqual(buf.priorities[0], expected, places=3)

    def test_default_error_priority(self):
        buf = PrioritizedExperienceReplay(capacity=10, alpha=0.6)
        buf.add(np.array([0]), 0, 0.0, np.array([0]), False)
        # Default error = 1.0 → priority = (1 + 1e-6)^0.6
        expected = (1.0 + 1e-6) ** 0.6
        self.assertAlmostEqual(buf.priorities[0], expected, places=3)

    def test_beta_annealing(self):
        buf = PrioritizedExperienceReplay(capacity=10, beta=0.4,
                                           beta_increment=0.05)
        for i in range(6):
            buf.add(np.array([i]), 0, 0.0, np.array([i]), False)
        betas = []
        for _ in range(3):
            buf.sample(2)
            betas.append(buf.beta)
        self.assertEqual(betas[0], 0.45)
        self.assertEqual(betas[1], 0.50)
        self.assertEqual(betas[2], 0.55)

    def test_beta_caps_at_one(self):
        buf = PrioritizedExperienceReplay(capacity=10, beta=0.95,
                                           beta_increment=0.1)
        for i in range(5):
            buf.add(np.array([i]), 0, 0.0, np.array([i]), False)
        buf.sample(2)
        self.assertAlmostEqual(buf.beta, 1.0)
        buf.sample(2)
        self.assertAlmostEqual(buf.beta, 1.0)


if __name__ == "__main__":
    unittest.main()
