"""
Token Embedder & Positional Encoding — Phase 2 of NN Architecture Upgrade.

Converts token ID matrices from the tokenizer into dense embedding vectors
suitable for LSTM/Transformer consumption. Each candle's multi-token
representation is pooled into a single embedding vector, then positional
encoding is added to preserve temporal order.
"""
import numpy as np
from typing import Optional
from tokenizer import VOCAB_SIZE


class TokenEmbedder:
    """Embeds multi-token candle representations into dense vectors.

    A candle produces 1-5 token IDs. This embedder:
    1. Looks up each token ID in a learned embedding table
    2. Averages (mean-pools) the embeddings for each candle
    3. Applies Layer Normalization for stable gradients
    4. Optionally adds learnable positional embeddings

    Args:
        vocab_size: total number of tokens in the vocabulary
        embedding_dim: dimensionality of the output embedding (default 64)
        max_seq_len: maximum sequence length for positional embeddings
        seed: random seed for reproducibility
    """

    def __init__(
        self,
        vocab_size: int = VOCAB_SIZE,
        embedding_dim: int = 64,
        max_seq_len: int = 24,
        seed: int = 42,
    ):
        rng = np.random.RandomState(seed)
        self.embedding_dim = embedding_dim
        self.max_seq_len = max_seq_len
        self.vocab_size = vocab_size

        # Token embedding table: (vocab_size, embedding_dim)
        self.token_embeddings = rng.randn(vocab_size, embedding_dim) * np.sqrt(
            2.0 / max(vocab_size, 1)
        )

        # Positional embeddings: (max_seq_len, embedding_dim)
        self.pos_embeddings = rng.randn(max_seq_len, embedding_dim) * 0.02

        # LayerNorm parameters
        self.gamma = np.ones((1, 1, embedding_dim), dtype=float)
        self.beta = np.zeros((1, 1, embedding_dim), dtype=float)

        # Optimizer state (Adam)
        self.m_te = np.zeros_like(self.token_embeddings)
        self.v_te = np.zeros_like(self.token_embeddings)
        self.m_pe = np.zeros_like(self.pos_embeddings)
        self.v_pe = np.zeros_like(self.pos_embeddings)
        self.m_g = np.zeros_like(self.gamma)
        self.v_g = np.zeros_like(self.gamma)
        self.m_b = np.zeros_like(self.beta)
        self.v_b = np.zeros_like(self.beta)
        self.t = 0

    def forward(
        self,
        token_ids: np.ndarray,
        positions: Optional[np.ndarray] = None,
        training: bool = False,
        mask: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """Embed a batch of token ID sequences.

        Args:
            token_ids: (batch_size, seq_len, max_tokens) int array from tokenizer
            positions: optional (batch_size, seq_len) position indices
            training: if True, apply dropout-like noise
            mask: optional (batch_size, seq_len) boolean mask (True = keep)

        Returns:
            (batch_size, seq_len, embedding_dim) float array
        """
        if token_ids.ndim == 2:
            token_ids = token_ids[np.newaxis, :, :]  # (1, seq_len, max_tokens)

        batch_size, seq_len, max_tokens = token_ids.shape
        assert seq_len <= self.max_seq_len, (
            f"Sequence length {seq_len} exceeds max_seq_len {self.max_seq_len}"
        )

        # Lookup token embeddings: (batch, seq, tokens, embed_dim)
        tok_embeds = self.token_embeddings[token_ids]

        if mask is not None:
            mask_expanded = mask[:, :, np.newaxis, np.newaxis]
            tok_embeds = tok_embeds * mask_expanded

        # Count valid token positions (non-zero token IDs)
        valid_mask = (token_ids > 0).astype(float)  # (batch, seq, tokens)
        valid_count = np.sum(valid_mask, axis=2, keepdims=True)  # (batch, seq, 1)
        valid_count = np.maximum(valid_count, 1.0)
        pooled = np.sum(tok_embeds, axis=2) / valid_count  # (batch, seq, embed_dim)

        # Add positional embeddings
        if positions is None:
            pos_ids = np.arange(seq_len)[np.newaxis, :, np.newaxis]  # (1, seq_len, 1)
        else:
            pos_ids = positions[:, :, np.newaxis]
        pos_embeds = self.pos_embeddings[pos_ids]  # (batch, seq_len, 1, embed_dim)
        pooled = pooled + np.squeeze(pos_embeds, axis=2)

        # Layer Normalization
        mean = np.mean(pooled, axis=-1, keepdims=True)
        var = np.var(pooled, axis=-1, keepdims=True)
        pooled = (pooled - mean) / np.sqrt(var + 1e-8)
        pooled = self.gamma * pooled + self.beta

        return pooled

    def backward(
        self,
        d_out: np.ndarray,
        token_ids: np.ndarray,
        learning_rate: float = 0.001,
    ):
        """Backprop gradients through the embedder and update embeddings.

        Args:
            d_out: gradient w.r.t. output of shape (batch, seq, embed_dim)
            token_ids: original token ID input used in forward()
            learning_rate: Adam learning rate for embedding updates
        """
        self.t += 1

        # Ensure token_ids is 3D to match d_out
        if token_ids.ndim == 2:
            token_ids = token_ids[np.newaxis, :, :]
        if d_out.ndim == 2:
            d_out = d_out[np.newaxis, :, :]

        batch_size, seq_len, embed_dim = d_out.shape

        # LayerNorm backward
        d_norm = self.gamma * d_out

        # Gamma/beta update: broadcast-compatible shapes
        d_gamma = np.sum(d_out, axis=(0, 1), keepdims=True)  # (1, 1, embed_dim)
        d_beta = np.sum(d_out, axis=(0, 1), keepdims=True)
        self._adam_step(self.gamma, d_gamma, self.m_g, self.v_g, learning_rate)
        self._adam_step(self.beta, d_beta, self.m_b, self.v_b, learning_rate)

        # d_pooled receives gradient from layer norm
        d_pooled = d_norm  # simplified: norm gradient passes through

        # Positional embedding gradients
        d_pos_full = np.zeros_like(self.pos_embeddings)
        d_pos_full[:seq_len, :] = np.sum(d_pooled, axis=0)  # (seq_len, embed_dim)
        self._adam_step(self.pos_embeddings, d_pos_full, self.m_pe, self.v_pe, learning_rate)

        # Token embedding gradients — distribute to active token IDs
        d_pooled_expanded = d_pooled[:, :, np.newaxis, :]  # (batch, seq, 1, embed_dim)
        max_tokens = token_ids.shape[-1]
        valid_mask = (token_ids > 0).astype(float)
        valid_count = np.maximum(np.sum(valid_mask, axis=2, keepdims=True), 1.0)
        d_tok = d_pooled_expanded / valid_count[:, :, np.newaxis, :]  # (batch, seq, 1, embed_dim)
        d_tok = np.broadcast_to(d_tok, (batch_size, seq_len, max_tokens, embed_dim))

        # Accumulate into token embedding table
        d_te = np.zeros_like(self.token_embeddings)
        for b in range(batch_size):
            for s in range(seq_len):
                for tk in range(max_tokens):
                    tid = token_ids[b, s, tk]
                    if tid > 0:
                        d_te[tid] += d_tok[b, s, tk]

        self._adam_step(self.token_embeddings, d_te, self.m_te, self.v_te, learning_rate)

    def _adam_step(self, params, grads, m, v, lr, beta1=0.9, beta2=0.999, eps=1e-8):
        """In-place Adam update for a parameter group."""
        m[:] = beta1 * m + (1.0 - beta1) * grads
        v[:] = beta2 * v + (1.0 - beta2) * (grads ** 2)
        m_hat = m / (1.0 - beta1 ** self.t)
        v_hat = v / (1.0 - beta2 ** self.t)
        params -= lr * m_hat / (np.sqrt(v_hat) + eps)

    def to_json(self) -> str:
        """Serialize embedder state to JSON."""
        import json
        return json.dumps({
            'token_embeddings': self.token_embeddings.tolist(),
            'pos_embeddings': self.pos_embeddings.tolist(),
            'gamma': self.gamma.squeeze().tolist(),
            'beta': self.beta.squeeze().tolist(),
            'embedding_dim': self.embedding_dim,
            'max_seq_len': self.max_seq_len,
        })

    def from_json(self, json_str: str):
        """Load embedder state from JSON."""
        import json
        data = json.loads(json_str)
        self.embedding_dim = data['embedding_dim']
        self.max_seq_len = data['max_seq_len']
        self.token_embeddings = np.array(data['token_embeddings'])
        self.pos_embeddings = np.array(data['pos_embeddings'])
        if self.pos_embeddings.shape[0] != self.max_seq_len:
            old_pos = self.pos_embeddings
            new_pos = np.random.randn(self.max_seq_len, self.embedding_dim) * 0.02
            new_pos[:min(len(old_pos), self.max_seq_len)] = old_pos[:self.max_seq_len]
            self.pos_embeddings = new_pos
        self.gamma = np.array(data['gamma']).reshape(1, 1, self.embedding_dim)
        self.beta = np.array(data['beta']).reshape(1, 1, self.embedding_dim)
