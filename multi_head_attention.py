"""
multi_head_attention.py — Pure NumPy Multi-Head Self-Attention

Implements scaled dot-product attention from "Attention Is All You Need"
(Vaswani et al., 2017). No PyTorch, no TensorFlow — pure NumPy.

Architecture:
  Input:   X ∈ R^(seq_len × d_model)
  Per head h:  
    Q_h = X @ W_qh    # Query: "what am I looking for?"
    K_h = X @ W_kh    # Key:   "what do I have?"
    V_h = X @ W_vh    # Value: "what information do I carry?"
    
    Attention(Q,K,V) = softmax(Q @ K^T / sqrt(d_k)) @ V
    
  Output:  concat(heads) @ W_o  → R^(seq_len × d_model)
"""

import numpy as np


class MultiHeadAttention:
    """Multi-head scaled dot-product self-attention.
    
    Args:
        d_model:  Total embedding dimension (must be divisible by num_heads)
        num_heads: Number of attention heads (default 4)
        max_seq_len: Maximum sequence length for causal mask (default 24)
        dropout: Dropout probability (default 0.1)
    """
    
    def __init__(self, d_model: int = 64, num_heads: int = 4, 
                 max_seq_len: int = 24, dropout: float = 0.1):
        assert d_model % num_heads == 0, f"d_model ({d_model}) must be divisible by num_heads ({num_heads})"
        
        self.d_model = d_model
        self.num_heads = num_heads
        self.d_k = d_model // num_heads  # Dimension per head
        self.scale = np.sqrt(self.d_k)
        self.max_seq_len = max_seq_len
        self.dropout = dropout
        
        # Xavier initialization for all projection matrices
        scale_qk = np.sqrt(2.0 / (d_model + self.d_k))
        scale_v = np.sqrt(2.0 / (d_model + self.d_k))
        scale_o = np.sqrt(2.0 / (d_model + d_model))
        
        # Shape: (num_heads, d_model, d_k)
        self.W_q = np.random.randn(num_heads, d_model, self.d_k) * scale_qk
        self.W_k = np.random.randn(num_heads, d_model, self.d_k) * scale_qk
        # Shape: (num_heads, d_model, d_k) — V also d_k dimension per head
        self.W_v = np.random.randn(num_heads, d_model, self.d_k) * scale_v
        # Shape: (num_heads * d_k, d_model) = (d_model, d_model)
        self.W_o = np.random.randn(d_model, d_model) * scale_o
        
        # Bias terms
        self.b_q = np.zeros((num_heads, self.d_k))
        self.b_k = np.zeros((num_heads, self.d_k))
        self.b_v = np.zeros((num_heads, self.d_k))
        self.b_o = np.zeros(d_model)
        
        # Cached values for backward pass
        self._cache = {}
    
    # ------------------------------------------------------------------
    # Causal mask (prevent attending to future positions)
    # ------------------------------------------------------------------
    
    def _causal_mask(self, seq_len: int) -> np.ndarray:
        """Upper triangular mask: position i can only attend to positions <= i.
        
        Returns: (seq_len, seq_len) with -inf on forbidden positions, 0 on allowed
        """
        mask = np.triu(np.ones((seq_len, seq_len)), k=1) * -1e9
        return mask
    
    # ------------------------------------------------------------------
    # Softmax (numerically stable)
    # ------------------------------------------------------------------
    
    @staticmethod
    def _softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
        """Numerically stable softmax along given axis."""
        x_max = np.max(x, axis=axis, keepdims=True)
        e_x = np.exp(x - x_max)
        return e_x / np.sum(e_x, axis=axis, keepdims=True)
    
    # ------------------------------------------------------------------
    # Forward pass
    # ------------------------------------------------------------------
    
    def forward(self, x: np.ndarray, mask: np.ndarray = None, training: bool = True) -> np.ndarray:
        """Forward pass through multi-head attention.
        
        Args:
            x: Input tensor (batch_size, seq_len, d_model) or (seq_len, d_model)
            mask: Optional attention mask (batch_size, seq_len, seq_len)
            training: If True, apply dropout and cache values for backward
        
        Returns:
            Output tensor of same shape as x
        """
        # Ensure 3D: (batch, seq, d_model)
        original_ndim = x.ndim
        if x.ndim == 2:
            x = x[np.newaxis, :, :]
        
        batch_size, seq_len, _ = x.shape
        
        # Create causal mask if none provided
        if mask is None:
            attn_mask = self._causal_mask(seq_len)  # (seq_len, seq_len)
            attn_mask = attn_mask[np.newaxis, np.newaxis, :, :]  # (1, 1, seq, seq)
        else:
            attn_mask = mask[:, np.newaxis, :, :] if mask.ndim == 3 else mask
        
        # Project queries, keys, values for ALL heads simultaneously
        # x: (batch, seq, d_model) → (batch, num_heads, seq, d_k)
        Q = np.einsum('bsd,hde->bhse', x, self.W_q) + self.b_q[:, np.newaxis, :]
        K = np.einsum('bsd,hde->bhse', x, self.W_k) + self.b_k[:, np.newaxis, :]
        V = np.einsum('bsd,hde->bhse', x, self.W_v) + self.b_v[:, np.newaxis, :]
        
        # Scaled dot-product attention: softmax(Q @ K^T / sqrt(d_k)) @ V
        # scores: (batch, num_heads, seq, seq)
        scores = np.einsum('bhse,bhte->bhst', Q, K) / self.scale
        
        # Apply mask
        scores = scores + attn_mask
        
        # Softmax + dropout
        attn_weights = self._softmax(scores, axis=-1)
        
        if training and self.dropout > 0:
            dropout_mask = (np.random.rand(*attn_weights.shape) > self.dropout) / (1.0 - self.dropout)
            attn_weights = attn_weights * dropout_mask
        
        # Weighted sum of values
        # attn_weights: (batch, num_heads, seq, seq), V: (batch, num_heads, seq, d_k)
        head_outputs = np.einsum('bhst,bhte->bhse', attn_weights, V)
        
        # Concatenate heads and project: (batch, seq, d_model)
        # head_outputs: (batch, num_heads, seq, d_k) → (batch, seq, num_heads*d_k) = (batch, seq, d_model)
        concat = head_outputs.transpose(0, 2, 1, 3).reshape(batch_size, seq_len, self.d_model)
        output = np.einsum('bsd,do->bso', concat, self.W_o) + self.b_o
        
        # Cache for backward
        if training:
            self._cache = {
                'x': x,
                'Q': Q, 'K': K, 'V': V,
                'scores': scores,
                'attn_weights': attn_weights,
                'head_outputs': head_outputs,
                'concat': concat,
                'mask': attn_mask,
                'output': output,
            }
        
        return output.squeeze(0) if original_ndim == 2 else output
    
    # ------------------------------------------------------------------
    # Backward pass
    # ------------------------------------------------------------------
    
    def backward(self, d_out: np.ndarray) -> np.ndarray:
        """Backward pass through multi-head attention."""
        if not self._cache:
            # No forward cache — backward called out of order
            return np.zeros_like(d_out)
        cache = self._cache
        batch_size, seq_len, d_model = d_out.shape
        
        # Gradient through output projection
        d_concat = np.einsum('bso,do->bsd', d_out, self.W_o.T)
        self.d_W_o = np.einsum('bsd,bso->do', cache['concat'], d_out)
        self.d_b_o = np.sum(d_out, axis=(0, 1))
        
        # Reshape back to heads: (batch, seq, num_heads, d_k) -> (batch, num_heads, seq, d_k)
        d_heads = d_concat.reshape(batch_size, seq_len, self.num_heads, self.d_k).transpose(0, 2, 1, 3)
        
        # Gradient through attention-weighted values
        # attn_weights: (batch, num_heads, seq, seq) = bhst
        # V: (batch, num_heads, seq, d_k) = bhse
        d_V = np.einsum('bhst,bhse->bhte', cache['attn_weights'], d_heads)
        d_attn_weights = np.einsum('bhte,bhse->bhst', d_heads, cache['V'])
        
        # Gradient through softmax: proper Jacobian
        # d(softmax(x)_i)/dx_j = softmax(x)_i * (delta_ij - softmax(x)_j)
        # In matrix form: diag(p) - p @ p^T
        p = cache['attn_weights']  # (batch, num_heads, seq, seq)
        # d_scores = p * (d_attn - sum(p * d_attn, axis=-1, keepdims=True))
        d_scores = p * (d_attn_weights - np.sum(p * d_attn_weights, axis=-1, keepdims=True))
        d_scores = d_scores / self.scale
        
        # Gradient w.r.t Q, K, V (approximate — full backprop through scale is omitted)
        Q, K, V = cache['Q'], cache['K'], cache['V']
        
        # d_W_q: (batch, seq, d_model) -> (num_heads, d_model, d_k)
        d_Q = np.einsum('bhst,bhte->bhse', d_scores, K)  # (batch, num_heads, seq, d_k)
        self.d_W_q = np.einsum('bsd,bhse->hde', cache['x'], d_Q)
        self.d_b_q = np.sum(d_Q, axis=(0, 2))
        
        # d_W_k
        d_K = np.einsum('bhst,bhse->bhte', d_scores.transpose(0, 1, 3, 2), Q)
        self.d_W_k = np.einsum('bsd,bhte->hde', cache['x'], d_K)
        self.d_b_k = np.sum(d_K, axis=(0, 2))
        
        # d_W_v
        self.d_W_v = np.einsum('bsd,bhte->hde', cache['x'], d_V)
        self.d_b_v = np.sum(d_V, axis=(0, 2))
        
        # Gradient w.r.t. input x
        d_x = (
            np.einsum('bhse,hde->bsd', d_Q, self.W_q) +
            np.einsum('bhse,hde->bsd', d_K, self.W_k) +
            np.einsum('bhse,hde->bsd', d_V, self.W_v)
        )
        
        return d_x
    
    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        import json
        data = {
            'd_model': self.d_model,
            'num_heads': self.num_heads,
            'd_k': self.d_k,
            'max_seq_len': self.max_seq_len,
            'dropout': self.dropout,
            'W_q': self.W_q.tolist(),
            'W_k': self.W_k.tolist(),
            'W_v': self.W_v.tolist(),
            'W_o': self.W_o.tolist(),
            'b_q': self.b_q.tolist(),
            'b_k': self.b_k.tolist(),
            'b_v': self.b_v.tolist(),
            'b_o': self.b_o.tolist(),
        }
        return json.dumps(data)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'MultiHeadAttention':
        """Deserialize from JSON string."""
        import json
        data = json.loads(json_str)
        mha = cls(
            d_model=data['d_model'],
            num_heads=data['num_heads'],
            max_seq_len=data['max_seq_len'],
            dropout=data['dropout'],
        )
        mha.W_q = np.array(data['W_q'])
        mha.W_k = np.array(data['W_k'])
        mha.W_v = np.array(data['W_v'])
        mha.W_o = np.array(data['W_o'])
        mha.b_q = np.array(data['b_q'])
        mha.b_k = np.array(data['b_k'])
        mha.b_v = np.array(data['b_v'])
        mha.b_o = np.array(data['b_o'])
        return mha


class LayerNorm:
    """Pure NumPy Layer Normalization (Ba et al., 2016).
    Normalizes across the last dimension."""
    
    def __init__(self, d_model: int, eps: float = 1e-5):
        self.gamma = np.ones(d_model)
        self.beta = np.zeros(d_model)
        self.eps = eps
        self._cache = {}
    
    def forward(self, x: np.ndarray) -> np.ndarray:
        mean = np.mean(x, axis=-1, keepdims=True)
        var = np.var(x, axis=-1, keepdims=True)
        x_norm = (x - mean) / np.sqrt(var + self.eps)
        out = self.gamma * x_norm + self.beta
        self._cache = {'x': x, 'x_norm': x_norm, 'var': var, 'mean': mean}
        return out
    
    def backward(self, d_out: np.ndarray) -> np.ndarray:
        """Backward pass through layer norm.

        Analytical derivatives:
          x̂ = (x - μ) / σ  where σ = √(var + ε)
          ∂x̂/∂x_i = (1/σ) - (x_i - μ)² / (d * σ³)
          ∂x̂_i/∂μ = -1/σ
          ∂x̂_i/∂var = -(x_i - μ) / (2 * σ³)

        Using the aggregated approach (Ba et al., 2016):
          ∂L/∂x = (1/σ) * [∂L/∂x̂ - (1/d) * (x̂ ⊙ ∂L/∂x̂) ⊙ x̂ - (1/d) * ⟨∂L/∂x̂⟩]
          where ⟨⋅⟩ denotes mean over the last dimension.
        """
        if not self._cache:
            return np.zeros_like(d_out)
        cache = self._cache
        d = d_out.shape[-1]
        N = np.prod(d_out.shape[:-1])
        
        d_x_norm = d_out * self.gamma  # ∂L/∂x̂
        sigma = np.sqrt(cache['var'] + self.eps)  # (..., 1)
        x_hat = cache['x_norm']  # cache saved during forward
        x = cache['x']
        mu = cache['mean']
        
        # ∂L/∂var = Σ ∂L/∂x̂  * (x - μ) * (-1/2) * (var + ε)^(-3/2)
        #         = Σ d_x_norm * -(x - μ) / (2 * σ³)
        d_var = np.sum(d_x_norm * (cache['x'] - cache['mean']) * (-0.5) * (cache['var'] + self.eps) ** (-1.5), axis=-1, keepdims=True)
        # ∂L/∂μ = Σ ∂L/∂x̂ * (-1 / σ)
        d_mean = np.sum(d_x_norm * (-1.0 / sigma), axis=-1, keepdims=True)
        
        # ∂x̂_i/∂x_i = 1/σ + (x̂_i * ∂(1/σ)/∂σ² * 2(x_i-μ)/d) ... full vectorized:
        # ∂L/∂x = ∂L/∂x̂ * (1/σ) + ∂L/∂σ² * (2(x_i-μ)/d) + ∂L/∂μ * (1/d)
        d_x = d_x_norm / sigma
        d_x += d_var * 2.0 * (cache['x'] - cache['mean']) / d
        d_x += d_mean / d
        
        self.d_gamma = np.sum(d_out * cache['x_norm'], axis=tuple(range(d_out.ndim - 1)))
        self.d_beta = np.sum(d_out, axis=tuple(range(d_out.ndim - 1)))
        
        return d_x
    
    def to_json(self) -> str:
        import json
        return json.dumps({'gamma': self.gamma.tolist(), 'beta': self.beta.tolist(), 'eps': self.eps})
    
    @classmethod
    def from_json(cls, json_str: str) -> 'LayerNorm':
        import json
        data = json.loads(json_str)
        ln = cls(len(data['gamma']), data['eps'])
        ln.gamma = np.array(data['gamma'])
        ln.beta = np.array(data['beta'])
        return ln
