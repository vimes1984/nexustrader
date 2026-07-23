"""
test_transformer.py — Unit tests for Transformer Policy Network

Tests cover:
  1. MultiHeadAttention — shapes, causal mask, softmax, forward/backward
  2. LayerNorm — normalization math, backward
  3. FeedForward — shapes, forward/backward
  4. TransformerEncoderLayer — full block forward/backward
  5. TransformerPolicyNetwork — end-to-end, select_weights, serialization
"""

import unittest
import numpy as np
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from multi_head_attention import MultiHeadAttention, LayerNorm
from transformer_policy_net import (
    FeedForward, TransformerEncoderLayer, PositionalEncoding,
    TransformerPolicyNetwork, Adam
)


class TestMultiHeadAttention(unittest.TestCase):
    
    def setUp(self):
        self.d_model = 64
        self.num_heads = 4
        self.seq_len = 24
        self.mha = MultiHeadAttention(self.d_model, self.num_heads, self.seq_len)
    
    def test_forward_shape(self):
        x = np.random.randn(2, self.seq_len, self.d_model)
        out = self.mha.forward(x, training=False)
        self.assertEqual(out.shape, (2, self.seq_len, self.d_model))
    
    def test_forward_shape_2d(self):
        x = np.random.randn(self.seq_len, self.d_model)
        out = self.mha.forward(x, training=False)
        self.assertEqual(out.shape, (self.seq_len, self.d_model))
    
    def test_causal_mask(self):
        mask = self.mha._causal_mask(4)
        # Upper triangular = -1e9 (can't attend to future)
        # Diagonal and below = 0 (can attend to past and present)
        # Position 0 can attend to position 0
        self.assertEqual(mask[0, 0], 0.0)
        # Position 0 cannot attend to position 1 (future)
        self.assertLess(mask[0, 1], -1e6)
        # Position 3 can attend to position 0 (past)
        self.assertEqual(mask[3, 0], 0.0)
        # Position 3 can attend to position 3 (present)
        self.assertEqual(mask[3, 3], 0.0)
    
    def test_softmax_rows_sum_to_one(self):
        x = np.random.randn(5, 10)
        probs = MultiHeadAttention._softmax(x, axis=-1)
        row_sums = np.sum(probs, axis=-1)
        np.testing.assert_array_almost_equal(row_sums, np.ones(5), decimal=5)
    
    def test_forward_yields_different_values(self):
        np.random.seed(42)
        x = np.random.randn(2, self.seq_len, self.d_model)
        out = self.mha.forward(x, training=False)
        self.assertFalse(np.allclose(out, x))
    
    def test_backward_shape(self):
        x = np.random.randn(2, self.seq_len, self.d_model)
        out = self.mha.forward(x, training=True)
        d_out = np.ones_like(out)
        d_x = self.mha.backward(d_out)
        self.assertEqual(d_x.shape, x.shape)
    
    def test_backward_produces_gradients(self):
        x = np.random.randn(1, self.seq_len, self.d_model)
        self.mha.forward(x, training=True)
        d_out = np.ones((1, self.seq_len, self.d_model))
        self.mha.backward(d_out)
        self.assertIsNotNone(self.mha.d_W_q)
        self.assertIsNotNone(self.mha.d_W_k)
        self.assertIsNotNone(self.mha.d_W_v)
        self.assertIsNotNone(self.mha.d_W_o)
    
    def test_serialization_round_trip(self):
        np.random.seed(42)
        x = np.random.randn(2, self.seq_len, self.d_model)
        original_out = self.mha.forward(x, training=False)
        
        json_str = self.mha.to_json()
        restored = MultiHeadAttention.from_json(json_str)
        restored_out = restored.forward(x, training=False)
        
        np.testing.assert_array_almost_equal(original_out, restored_out, decimal=5)


class TestLayerNorm(unittest.TestCase):
    
    def test_normalizes_to_zero_mean(self):
        ln = LayerNorm(64)
        x = np.random.randn(10, 24, 64) * 5 + 10
        out = ln.forward(x)
        means = np.mean(out, axis=-1)
        np.testing.assert_array_almost_equal(means, np.zeros((10, 24)), decimal=5)
    
    def test_normalizes_to_unit_variance(self):
        ln = LayerNorm(64)
        x = np.random.randn(10, 24, 64) * 5 + 10
        out = ln.forward(x)
        vars_ = np.var(out, axis=-1)
        np.testing.assert_array_almost_equal(vars_, np.ones((10, 24)), decimal=1)
    
    def test_backward_shape(self):
        ln = LayerNorm(64)
        x = np.random.randn(5, 12, 64)
        ln.forward(x)
        d_out = np.ones_like(x)
        d_x = ln.backward(d_out)
        self.assertEqual(d_x.shape, x.shape)
    
    def test_serialization_round_trip(self):
        ln = LayerNorm(64)
        x = np.random.randn(3, 8, 64)
        out1 = ln.forward(x)
        
        restored = LayerNorm.from_json(ln.to_json())
        out2 = restored.forward(x)
        
        np.testing.assert_array_almost_equal(out1, out2, decimal=5)


class TestFeedForward(unittest.TestCase):
    
    def test_forward_shape(self):
        ff = FeedForward(64, 128)
        x = np.random.randn(2, 24, 64)
        out = ff.forward(x, training=False)
        self.assertEqual(out.shape, (2, 24, 64))
    
    def test_backward_shape(self):
        ff = FeedForward(64, 128)
        x = np.random.randn(2, 24, 64)
        ff.forward(x, training=True)
        d_out = np.ones_like(x)
        d_x = ff.backward(d_out)
        self.assertEqual(d_x.shape, x.shape)
    
    def test_serialization_round_trip(self):
        ff = FeedForward(64, 128)
        x = np.random.randn(2, 24, 64)
        out1 = ff.forward(x, training=False)
        
        restored = FeedForward.from_json(ff.to_json())
        out2 = restored.forward(x, training=False)
        
        np.testing.assert_array_almost_equal(out1, out2, decimal=5)


class TestTransformerEncoderLayer(unittest.TestCase):
    
    def test_forward_shape(self):
        layer = TransformerEncoderLayer(64, 4, 128, 24)
        x = np.random.randn(2, 24, 64)
        out = layer.forward(x, training=False)
        self.assertEqual(out.shape, (2, 24, 64))
    
    def test_forward_different_from_input(self):
        layer = TransformerEncoderLayer(64, 4, 128, 24)
        x = np.random.randn(1, 24, 64)
        out = layer.forward(x, training=False)
        self.assertFalse(np.allclose(out, x))
    
    def test_backward_shape(self):
        layer = TransformerEncoderLayer(64, 4, 128, 24)
        x = np.random.randn(1, 24, 64)
        layer.forward(x, training=True)
        d_out = np.ones((1, 24, 64))
        d_x = layer.backward(d_out)
        self.assertEqual(d_x.shape, x.shape)
    
    def test_serialization_round_trip(self):
        layer = TransformerEncoderLayer(64, 4, 128, 24)
        x = np.random.randn(1, 24, 64)
        out1 = layer.forward(x, training=False)
        
        restored = TransformerEncoderLayer.from_json(layer.to_json())
        out2 = restored.forward(x, training=False)
        
        np.testing.assert_array_almost_equal(out1, out2, decimal=5)


class TestPositionalEncoding(unittest.TestCase):
    
    def test_adds_different_values(self):
        pe = PositionalEncoding(24, 64)
        x = np.random.randn(2, 24, 64)
        out = pe.forward(x)
        # Different positions should have different encodings added
        pos0 = out[:, 0, :]
        pos1 = out[:, 1, :]
        self.assertFalse(np.allclose(pos0, pos1))


class TestTransformerPolicyNetwork(unittest.TestCase):
    
    def setUp(self):
        self.action_dim = 6
        self.net = TransformerPolicyNetwork(
            action_dim=self.action_dim,
            d_model=64,
            num_heads=4,
            num_layers=2,
            max_seq_len=24,
            learning_rate=0.001,
        )
    
    def test_forward_shape(self):
        x = np.random.randn(2, 24, 64)
        probs = self.net.forward(x, training=False)
        self.assertEqual(probs.shape, (2, self.action_dim))
        # Probabilities sum to 1
        np.testing.assert_array_almost_equal(np.sum(probs, axis=-1), np.ones(2), decimal=5)
    
    def test_select_weights_2d(self):
        x = np.random.randn(24, 64)
        weights = self.net.select_weights(x)
        self.assertEqual(len(weights), self.action_dim)
        np.testing.assert_almost_equal(sum(weights), 1.0, decimal=4)
        # All weights above floor
        self.assertTrue(all(w >= 0.01 for w in weights))
    
    def test_select_weights_1d_fallback(self):
        state = np.random.randn(8)
        weights = self.net.select_weights(state)
        self.assertEqual(len(weights), self.action_dim)
        np.testing.assert_almost_equal(sum(weights), 1.0, decimal=4)
    
    def test_backward_shape(self):
        x = np.random.randn(1, 24, 64)
        self.net.forward(x, training=True)
        d_out = np.ones((1, self.action_dim))
        # backward is aliased to reinforce_backward; use _backward_pass directly for gradient testing
        d_x = self.net._backward_pass(d_out)
        self.assertEqual(d_x.shape, (1, 24, 64))
    
    def test_serialization_round_trip(self):
        np.random.seed(42)
        x = np.random.randn(1, 24, 64)
        out1 = self.net.forward(x, training=False)
        
        json_str = self.net.to_json()
        restored = TransformerPolicyNetwork.from_json(json_str)
        out2 = restored.forward(x, training=False)
        
        np.testing.assert_array_almost_equal(out1, out2, decimal=4)
    
    def test_serialization_preserves_action_dim(self):
        json_str = self.net.to_json()
        restored = TransformerPolicyNetwork.from_json(json_str)
        self.assertEqual(restored.action_dim, self.action_dim)
    
    def test_get_attention_weights(self):
        x = np.random.randn(1, 24, 64)
        attn_maps = self.net.get_attention_weights(x)
        self.assertEqual(len(attn_maps), 2)  # 2 layers
        # First non-None attention map should have batch and heads dims
        self.assertEqual(attn_maps[0].ndim, 4)


class TestAdam(unittest.TestCase):
    
    def test_updates_parameters(self):
        adam = Adam(lr=0.1)
        params = {'w': np.array([1.0, 2.0, 3.0])}
        grads = {'w': np.array([0.1, 0.2, 0.3])}
        
        updated = adam.update(params, grads)
        
        # Parameters should decrease (gradient is positive, so params -= lr * grad)
        self.assertTrue(np.all(updated['w'] < params['w']))


class TestEndToEndWithTokenizer(unittest.TestCase):
    """Full pipeline: tokenize → embed → transformer → weights"""
    
    def test_transformer_in_learning_engine(self):
        from learning_engine import LearningEngine
        
        engine = LearningEngine(
            num_strategies=6,
            nn_architecture="transformer",
            hidden_dim=64,
            hidden_layers=2,
        )
        
        # Should have a TransformerPolicyNetwork
        self.assertEqual(engine.nn_architecture, "transformer")
        
        # select_weights should work with a dummy state
        state = np.random.randn(24, 64)
        weights = engine.select_weights(state)
        self.assertEqual(len(weights), 6)
        np.testing.assert_almost_equal(sum(weights), 1.0, decimal=3)


if __name__ == '__main__':
    unittest.main()
