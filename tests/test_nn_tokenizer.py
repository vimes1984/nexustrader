"""Unit tests for market tokenizer, embedder, and sequential policy network."""
import unittest
import numpy as np
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tokenizer import (
    tokenize_candle, tokenize_ticker_window, tokenize_ticker_to_ids,
    tokens_to_ids, TOKEN_TO_ID, VOCAB_SIZE, FULL_VOCABULARY,
    _compute_atr, _compute_ema, _compute_rsi, _compute_bollinger,
    _estimate_ou_theta,
)
from token_embedder import TokenEmbedder
from sequential_policy_net import SequentialPolicyNetwork, LSTMCell


# ─── Sample Candles ─────────────────────────────────────────────────────────

def make_candle(open_p, high, low, close, volume):
    return {'open': open_p, 'high': high, 'low': low, 'close': close, 'volume': volume}


SAMPLE_CANDLES = [
    make_candle(100, 105, 99, 102, 1000),
    make_candle(102, 108, 101, 107, 1500),
    make_candle(107, 110, 106, 108, 800),
    make_candle(108, 109, 100, 101, 3000),
    make_candle(101, 103, 99, 103, 2000),
]

# Longer sequence for window tests
LONG_CANDLES = []
base = 100.0
for i in range(30):
    rng = np.random.RandomState(42 + i)
    close = base + rng.randn() * 2
    high = close + abs(rng.randn()) * 3
    low = close - abs(rng.randn()) * 3
    open_p = close - rng.randn() * 1
    volume = 500 + rng.rand() * 2000
    LONG_CANDLES.append(make_candle(open_p, high, low, close, volume))
    base = close


# ─── Tokenizer Tests ─────────────────────────────────────────────────────────

class TestHelperFunctions(unittest.TestCase):
    def test_compute_atr_basic(self):
        highs = np.array([105, 110, 111, 112, 113], dtype=float)
        lows = np.array([99, 101, 102, 103, 104], dtype=float)
        closes = np.array([102, 107, 108, 109, 110], dtype=float)
        atr = _compute_atr(highs, lows, closes, period=3)
        self.assertGreater(atr, 0)
        self.assertLess(atr, 20)

    def test_compute_atr_insufficient_data(self):
        atr = _compute_atr(np.array([100]), np.array([99]), np.array([100]))
        self.assertEqual(atr, 0.0)

    def test_compute_ema_basic(self):
        series = np.array([100 + i for i in range(30)], dtype=float)
        ema = _compute_ema(series, 20)
        self.assertGreater(ema, 115)
        self.assertLess(ema, 135)

    def test_compute_ema_short_series(self):
        ema = _compute_ema(np.array([100, 102, 104]), 20)
        self.assertEqual(ema, 102.0)

    def test_compute_rsi_basic(self):
        # All up closes -> RSI should be high
        closes = np.array([100 + i * 0.5 for i in range(20)], dtype=float)
        rsi = _compute_rsi(closes, 14)
        self.assertGreater(rsi, 70)  # Should be very high (all gains)

    def test_compute_rsi_all_losses(self):
        closes = np.array([100 - i * 0.5 for i in range(20)], dtype=float)
        rsi = _compute_rsi(closes, 14)
        self.assertLess(rsi, 30)

    def test_compute_bollinger_basic(self):
        closes = np.arange(100, 130, dtype=float)
        upper, lower = _compute_bollinger(closes, 20, 2.0)
        self.assertGreater(upper, lower)
        self.assertGreater(upper, closes[-1])

    def test_estimate_ou_theta_non_reverting(self):
        # Trending prices should not be mean-reverting
        prices = np.arange(100, 130, dtype=float)
        theta = _estimate_ou_theta(prices)
        self.assertEqual(theta, 0.0)  # a would be ~1.0, not mean reverting

    def test_estimate_ou_theta_short(self):
        theta = _estimate_ou_theta(np.array([100, 101]))
        self.assertEqual(theta, 0.0)


class TestTokenizeCandle(unittest.TestCase):
    def test_strong_up_candle(self):
        candle = make_candle(100, 115, 99, 114, 2000)
        tokens = tokenize_candle(
            candle, None, atr_20=5.0, volume_ma_20=800,
            ema_20=105, ema_50=100, ou_theta=0.0, rsi_14=65,
            bb_upper=118, bb_lower=95, swing_low=99, swing_high=115,
            btc_1h_return=0.005,
        )
        self.assertIn('PR_STRONG_UP', tokens)
        self.assertIn('VOL_SPIKE', tokens)
        self.assertIn('CTX_RISK_ON', tokens)

    def test_doji_candle(self):
        candle = make_candle(100, 108, 92, 100.5, 800)
        tokens = tokenize_candle(
            candle, None, atr_20=10.0, volume_ma_20=1000,
            ema_20=100, ema_50=100, ou_theta=0.0, rsi_14=50,
            bb_upper=120, bb_lower=80, swing_low=92, swing_high=108,
            btc_1h_return=0.0,
        )
        self.assertIn('PR_DOJI', tokens)

    def test_mean_reverting_detected(self):
        candle = make_candle(100, 102, 98, 101, 1000)
        tokens = tokenize_candle(
            candle, None, atr_20=3.0, volume_ma_20=1000,
            ema_20=100, ema_50=100, ou_theta=0.15, rsi_14=50,
            bb_upper=115, bb_lower=85, swing_low=98, swing_high=110,
            btc_1h_return=0.0,
        )
        self.assertIn('REG_MEAN_REVERTING', tokens)

    def test_btc_leading_detected(self):
        candle = make_candle(100, 102, 98, 101, 1000)
        tokens = tokenize_candle(
            candle, None, atr_20=3.0, volume_ma_20=1000,
            ema_20=100, ema_50=100, ou_theta=0.0, rsi_14=50,
            bb_upper=115, bb_lower=85, swing_low=98, swing_high=110,
            btc_1h_return=0.015,
        )
        self.assertIn('CTX_BTC_LEADING', tokens)

    def test_every_candle_gets_volume_token(self):
        for c in SAMPLE_CANDLES:
            tokens = tokenize_candle(
                c, None, atr_20=3.0, volume_ma_20=1000,
                ema_20=105, ema_50=100, ou_theta=0.0, rsi_14=50,
                bb_upper=120, bb_lower=80, swing_low=99, swing_high=115,
                btc_1h_return=0.0,
            )
            vol_tokens = [t for t in tokens if t.startswith('VOL_')]
            self.assertEqual(len(vol_tokens), 1, f"Missing volume token in {tokens}")

    def test_engulfing_bull(self):
        prev = make_candle(102, 103, 101, 101.5, 1000)  # small bearish
        curr = make_candle(101, 108, 100, 107, 2000)    # large bullish engulfing
        tokens = tokenize_candle(
            curr, prev, atr_20=3.0, volume_ma_20=1000,
            ema_20=105, ema_50=100, ou_theta=0.0, rsi_14=55,
            bb_upper=118, bb_lower=95, swing_low=100, swing_high=115,
            btc_1h_return=0.0,
        )
        self.assertIn('PR_ENGULFING_BULL', tokens)

    def test_support_test(self):
        candle = make_candle(100, 102, 98, 100.3, 1000)
        tokens = tokenize_candle(
            candle, None, atr_20=3.0, volume_ma_20=1000,
            ema_20=100, ema_50=100, ou_theta=0.0, rsi_14=50,
            bb_upper=115, bb_lower=85, swing_low=100.0, swing_high=110,
            btc_1h_return=0.0,
        )
        self.assertIn('REG_SUPPORT_TEST', tokens)

    def test_token_ids_in_vocab(self):
        """All token IDs should be valid."""
        for t in FULL_VOCABULARY:
            self.assertIn(t, TOKEN_TO_ID)
        self.assertEqual(len(FULL_VOCABULARY), VOCAB_SIZE)


class TestTokenizeWindow(unittest.TestCase):
    def test_returns_correct_length(self):
        seq = tokenize_ticker_window(LONG_CANDLES, window_size=10)
        self.assertEqual(len(seq), 10)

    def test_handles_short_input(self):
        short = LONG_CANDLES[:5]
        seq = tokenize_ticker_window(short, window_size=10)
        self.assertEqual(len(seq), 5)  # returns whatever's available

    def test_each_candle_has_tokens(self):
        seq = tokenize_ticker_window(LONG_CANDLES, window_size=12)
        for candle_tokens in seq:
            self.assertGreater(len(candle_tokens), 0)

    def test_all_tokens_valid(self):
        seq = tokenize_ticker_window(LONG_CANDLES, window_size=12)
        for candle_tokens in seq:
            for t in candle_tokens:
                self.assertIn(t, TOKEN_TO_ID)


class TestTokensToIDs(unittest.TestCase):
    def test_shape(self):
        seq = tokenize_ticker_window(LONG_CANDLES, window_size=10)
        ids = tokens_to_ids(seq, max_tokens_per_candle=5)
        self.assertEqual(ids.shape, (10, 5))

    def test_padding(self):
        seq = [['PR_UP']]  # single token candle
        ids = tokens_to_ids(seq, max_tokens_per_candle=5)
        self.assertEqual(ids.shape, (1, 5))
        self.assertEqual(ids[0, 0], TOKEN_TO_ID['PR_UP'])
        self.assertEqual(ids[0, 1], 0)  # padded

    def test_empty_input(self):
        ids = tokens_to_ids([], max_tokens_per_candle=5)
        self.assertEqual(ids.shape, (24, 5))  # default seq_len padding


class TestFullPipeline(unittest.TestCase):
    def test_full_pipeline_produces_ids(self):
        ids = tokenize_ticker_to_ids(LONG_CANDLES, window_size=12, max_tokens_per_candle=5)
        self.assertEqual(ids.shape, (12, 5))
        self.assertTrue(np.any(ids > 0))  # at least some non-padding tokens

    def test_insufficient_data_returns_zeros(self):
        ids = tokenize_ticker_to_ids(LONG_CANDLES[:3], window_size=24)
        self.assertEqual(ids.shape, (24, 5))
        self.assertTrue(np.all(ids == 0))


# ─── Token Embedder Tests ────────────────────────────────────────────────────

class TestTokenEmbedder(unittest.TestCase):
    def setUp(self):
        self.embedder = TokenEmbedder(embedding_dim=32, max_seq_len=24)
        # Generate sample token IDs: (seq_len=10, max_tokens=5)
        rng = np.random.RandomState(42)
        self.token_ids = np.array([
            [
                rng.randint(1, VOCAB_SIZE),
                rng.randint(0, VOCAB_SIZE),
                rng.randint(0, VOCAB_SIZE),
                rng.randint(0, VOCAB_SIZE),
                rng.randint(0, VOCAB_SIZE),
            ] for _ in range(10)
        ], dtype=int)
        self.token_ids[0][1:] = 0  # first candle has 1 token

    def test_forward_shape(self):
        out = self.embedder.forward(self.token_ids)
        self.assertEqual(out.shape, (1, 10, 32))

    def test_forward_batch_shape(self):
        batch = np.stack([self.token_ids, self.token_ids])  # (2, 10, 5)
        out = self.embedder.forward(batch)
        self.assertEqual(out.shape, (2, 10, 32))

    def test_forward_different_lengths(self):
        ids_8 = self.token_ids[:8]
        out = self.embedder.forward(ids_8)
        self.assertEqual(out.shape, (1, 8, 32))

    def test_backward_does_not_crash(self):
        out = self.embedder.forward(self.token_ids)
        d_out = np.random.randn(1, 10, 32).astype(float) * 0.01
        self.embedder.backward(d_out, self.token_ids, learning_rate=0.001)
        # Should not raise — weights should have changed
        self.assertGreater(np.sum(np.abs(self.embedder.token_embeddings)), 0)

    def test_serialization_roundtrip(self):
        out_before = self.embedder.forward(self.token_ids)
        json_str = self.embedder.to_json()
        restored = TokenEmbedder(embedding_dim=32, max_seq_len=24)
        restored.from_json(json_str)
        out_after = restored.forward(self.token_ids)
        np.testing.assert_array_almost_equal(out_before, out_after, decimal=4)

    def test_positional_encoding_differs_by_position(self):
        ids_small = self.token_ids[:2]
        out = self.embedder.forward(ids_small)  # (1, 2, 32)
        # Different positions should have different embeddings even with same tokens
        self.assertFalse(np.allclose(out[0, 0], out[0, 1]))


# ─── Sequential Policy Network Tests ─────────────────────────────────────────

class TestLSTMCell(unittest.TestCase):
    def setUp(self):
        self.cell = LSTMCell(input_dim=8, hidden_dim=4)

    def test_forward_shape(self):
        x = np.random.randn(2, 8)
        h = np.zeros((2, 4))
        c = np.zeros((2, 4))
        h_out, c_out = self.cell.forward(x, h, c)
        self.assertEqual(h_out.shape, (2, 4))
        self.assertEqual(c_out.shape, (2, 4))

    def test_backward_does_not_crash(self):
        x = np.random.randn(2, 8)
        h = np.random.randn(2, 4) * 0.1
        c = np.random.randn(2, 4) * 0.1
        h_out, c_out = self.cell.forward(x, h, c)
        dh = np.random.randn(2, 4) * 0.01
        dc = np.random.randn(2, 4) * 0.01
        dx, dh_prev, dc_prev = self.cell.backward(dh, dc, learning_rate=0.001)
        self.assertEqual(dx.shape, (2, 8))
        self.assertEqual(dh_prev.shape, (2, 4))
        self.assertEqual(dc_prev.shape, (2, 4))

    def test_serialization_roundtrip(self):
        x = np.random.randn(1, 8)
        h = np.zeros((1, 4))
        c = np.zeros((1, 4))
        h_out, c_out = self.cell.forward(x, h, c)
        json_str = self.cell.to_json()
        restored = LSTMCell(input_dim=8, hidden_dim=4)
        restored.from_json(json_str)
        h_out2, c_out2 = restored.forward(x, h, c)
        np.testing.assert_array_almost_equal(h_out, h_out2, decimal=4)
        np.testing.assert_array_almost_equal(c_out, c_out2, decimal=4)


class TestSequentialPolicyNetwork(unittest.TestCase):
    def setUp(self):
        self.net = SequentialPolicyNetwork(
            action_dim=6,
            embedding_dim=32,
            hidden_dim=32,
            num_layers=2,
            learning_rate=0.001,
            dropout=0.0,  # zero dropout for deterministic tests
            max_seq_len=24,
            seed=42,
        )
        # Generate token IDs for 10-candle sequence
        rng = np.random.RandomState(99)
        self.token_ids = np.array([
            [
                rng.randint(1, 20),  # use low IDs to hit trained embeddings
                rng.randint(0, 20),
                rng.randint(0, 20),
                rng.randint(0, 10),
                rng.randint(0, 10),
            ] for _ in range(12)
        ], dtype=int)

    def test_forward_shape(self):
        probs = self.net.forward(self.token_ids)
        self.assertEqual(len(probs), 6)
        self.assertAlmostEqual(sum(probs), 1.0, places=4)

    def test_forward_sum_to_one(self):
        for _ in range(5):
            probs = self.net.forward(self.token_ids)
            self.assertAlmostEqual(float(np.sum(probs)), 1.0, places=4)

    def test_forward_all_positive(self):
        probs = self.net.forward(self.token_ids)
        self.assertTrue(np.all(probs >= 0))

    def test_select_weights_with_floor(self):
        ids = tokenize_ticker_to_ids(LONG_CANDLES, window_size=12, max_tokens_per_candle=5)
        if np.any(ids > 0):
            weights = self.net.select_weights(ids, weight_floor=0.05)
            self.assertEqual(len(weights), 6)
            self.assertTrue(all(w >= 0.04 for w in weights))  # near-floor
        else:
            self.skipTest("No valid tokens in test data")

    def test_backward_does_not_crash(self):
        probs = self.net.forward(self.token_ids)
        strategy_signals = [0.5, 0.3, 0.1, 0.05, 0.03, 0.02]
        self.net.backward(
            state=np.zeros(8),  # ignored, kept for API compat
            strategy_signals=strategy_signals,
            trade_direction="BUY",
            reward=0.02,
        )
        self.assertGreater(self.net.t, 0)
        self.assertNotEqual(self.net.reward_baseline, 0.0)

    def test_serialization_roundtrip(self):
        probs_before = self.net.forward(self.token_ids)
        json_str = self.net.to_json()
        restored = SequentialPolicyNetwork(action_dim=6, embedding_dim=32, hidden_dim=32, num_layers=2, max_seq_len=24)
        restored.from_json(json_str)
        probs_after = restored.forward(self.token_ids)
        np.testing.assert_array_almost_equal(probs_before, probs_after, decimal=4)

    def test_empty_token_ids_fallback(self):
        zeros = np.zeros((12, 5), dtype=int)
        probs = self.net.forward(zeros)
        self.assertEqual(len(probs), 6)
        self.assertAlmostEqual(sum(probs), 1.0, places=4)
        self.assertFalse(np.any(np.isnan(probs)))

    def test_different_sequences_different_outputs(self):
        """Different token sequences should produce different weight distributions."""
        ids1 = tokenize_ticker_to_ids(LONG_CANDLES, window_size=12, max_tokens_per_candle=5)
        # Shifted candles
        shifted = LONG_CANDLES[5:] + LONG_CANDLES[:5]  # rearrange
        ids2 = tokenize_ticker_to_ids(shifted, window_size=12, max_tokens_per_candle=5)
        p1 = self.net.forward(ids1)
        p2 = self.net.forward(ids2)
        # Should be different (not exactly equal)
        self.assertFalse(np.allclose(p1, p2))

    def test_learning_rate_parameter(self):
        """Test that learning rate is properly stored."""
        net_high_lr = SequentialPolicyNetwork(action_dim=6, learning_rate=0.01)
        net_low_lr = SequentialPolicyNetwork(action_dim=6, learning_rate=0.0001)
        self.assertEqual(net_high_lr.lr, 0.01)
        self.assertEqual(net_low_lr.lr, 0.0001)


if __name__ == '__main__':
    unittest.main()
