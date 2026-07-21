"""
transformer_policy_net.py — Transformer-based Policy Network for strategy weighting

Pure NumPy implementation. Same interface as PolicyNetwork (MLP) and
SequentialPolicyNetwork (LSTM): forward(), backward(), select_weights(),
to_json(), from_json().

Architecture:
  Tokenized candles (seq_len=24, d_model=64)
       ↓
  + Positional Encoding (learned)
       ↓
  [Transformer Encoder] × 2 layers
  ├── Multi-Head Self-Attention (4 heads, d_k=16)
  ├── Add & LayerNorm
  ├── Feed-Forward Network (64 → 128 → 64, ReLU)
  └── Add & LayerNorm
       ↓
  Global Mean Pooling → 64d vector
       ↓
  Policy Head (64 → 32 → action_dim, Softmax)
       ↓
  Strategy weights [w₁, w₂, ..., wₙ]
"""

import numpy as np
from multi_head_attention import MultiHeadAttention, LayerNorm


class FeedForward:
    """Position-wise Feed-Forward Network: d_model → d_ff → d_model"""
    
    def __init__(self, d_model: int = 64, d_ff: int = 128, dropout: float = 0.1):
        scale1 = np.sqrt(2.0 / (d_model + d_ff))
        scale2 = np.sqrt(2.0 / (d_ff + d_model))
        self.W1 = np.random.randn(d_model, d_ff) * scale1
        self.b1 = np.zeros(d_ff)
        self.W2 = np.random.randn(d_ff, d_model) * scale2
        self.b2 = np.zeros(d_model)
        self.dropout = dropout
        self._cache = {}
    
    def forward(self, x: np.ndarray, training: bool = True) -> np.ndarray:
        # x: (batch, seq, d_model)
        hidden = np.maximum(0, np.einsum('bsd,df->bsf', x, self.W1) + self.b1)  # ReLU
        
        if training and self.dropout > 0:
            mask = (np.random.rand(*hidden.shape) > self.dropout) / (1.0 - self.dropout)
            hidden = hidden * mask
        
        output = np.einsum('bsf,fd->bsd', hidden, self.W2) + self.b2
        
        if training:
            self._cache = {'x': x, 'hidden': hidden, 'output': output}
        
        return output
    
    def backward(self, d_out: np.ndarray) -> np.ndarray:
        cache = self._cache
        
        # Gradient through W2
        self.d_W2 = np.einsum('bsf,bsd->fd', cache['hidden'], d_out)
        self.d_b2 = np.sum(d_out, axis=(0, 1))
        
        # Gradient through ReLU
        d_hidden = np.einsum('bsd,fd->bsf', d_out, self.W2)
        d_hidden = d_hidden * (cache['hidden'] > 0)
        
        # Gradient through W1
        self.d_W1 = np.einsum('bsd,bsf->df', cache['x'], d_hidden)
        self.d_b1 = np.sum(d_hidden, axis=(0, 1))
        
        # Gradient w.r.t. input
        d_x = np.einsum('bsf,df->bsd', d_hidden, self.W1)
        return d_x
    
    def to_json(self) -> str:
        import json
        return json.dumps({
            'W1': self.W1.tolist(), 'b1': self.b1.tolist(),
            'W2': self.W2.tolist(), 'b2': self.b2.tolist(),
        })
    
    @classmethod
    def from_json(cls, json_str: str, dropout: float = 0.1) -> 'FeedForward':
        import json
        data = json.loads(json_str)
        W1 = np.array(data['W1'])
        ff = cls(d_model=W1.shape[0], d_ff=W1.shape[1], dropout=dropout)
        ff.W1 = W1
        ff.b1 = np.array(data['b1'])
        ff.W2 = np.array(data['W2'])
        ff.b2 = np.array(data['b2'])
        return ff


class TransformerEncoderLayer:
    """One Transformer encoder block: Attention → Add&Norm → FFN → Add&Norm"""
    
    def __init__(self, d_model: int = 64, num_heads: int = 4, d_ff: int = 128,
                 max_seq_len: int = 24, dropout: float = 0.1):
        self.attention = MultiHeadAttention(d_model, num_heads, max_seq_len, dropout)
        self.norm1 = LayerNorm(d_model)
        self.norm2 = LayerNorm(d_model)
        self.ffn = FeedForward(d_model, d_ff, dropout)
        self.dropout = dropout
    
    def forward(self, x: np.ndarray, mask: np.ndarray = None, training: bool = True) -> np.ndarray:
        # Self-attention with residual
        attn_out = self.attention.forward(x, mask, training)
        x = self.norm1.forward(x + attn_out)
        
        # Feed-forward with residual
        ffn_out = self.ffn.forward(x, training)
        x = self.norm2.forward(x + ffn_out)
        
        return x
    
    def backward(self, d_out: np.ndarray) -> np.ndarray:
        # Backward through norm2 + FFN residual
        d_ffn = self.ffn.backward(d_out)
        d_before_norm2 = self.norm2.backward(d_out) + d_ffn
        
        # Backward through norm1 + attention residual
        d_attn = self.attention.backward(d_before_norm2)
        d_before_norm1 = self.norm1.backward(d_before_norm2) + d_attn
        
        return d_before_norm1
    
    def to_json(self) -> str:
        import json
        return json.dumps({
            'attention': json.loads(self.attention.to_json()),
            'norm1': json.loads(self.norm1.to_json()),
            'norm2': json.loads(self.norm2.to_json()),
            'ffn': json.loads(self.ffn.to_json()),
        })
    
    @classmethod
    def from_json(cls, json_str: str) -> 'TransformerEncoderLayer':
        import json
        data = json.loads(json_str)
        attn_data = data['attention']
        layer = cls(
            d_model=attn_data['d_model'],
            num_heads=attn_data['num_heads'],
            d_ff=len(data['ffn']['b1']),
            max_seq_len=attn_data['max_seq_len'],
            dropout=attn_data['dropout'],
        )
        layer.attention = MultiHeadAttention.from_json(json.dumps(attn_data))
        layer.norm1 = LayerNorm.from_json(json.dumps(data['norm1']))
        layer.norm2 = LayerNorm.from_json(json.dumps(data['norm2']))
        layer.ffn = FeedForward.from_json(json.dumps(data['ffn']))
        return layer


class PositionalEncoding:
    """Learned positional embeddings for sequence positions."""
    
    def __init__(self, max_seq_len: int = 24, d_model: int = 64):
        self.max_seq_len = max_seq_len
        self.d_model = d_model
        scale = np.sqrt(1.0 / d_model)
        self.embeddings = np.random.randn(max_seq_len, d_model) * scale
    
    def forward(self, x: np.ndarray) -> np.ndarray:
        """Add positional encoding to input.
        
        Args:
            x: (batch, seq, d_model) or (seq, d_model)
        """
        if x.ndim == 2:
            seq_len = x.shape[0]
            return x + self.embeddings[:seq_len]
        else:
            seq_len = x.shape[1]
            return x + self.embeddings[np.newaxis, :seq_len, :]
    
    def to_json(self) -> str:
        import json
        return json.dumps({'embeddings': self.embeddings.tolist()})
    
    @classmethod
    def from_json(cls, json_str: str) -> 'PositionalEncoding':
        import json
        data = json.loads(json_str)
        emb = np.array(data['embeddings'])
        pe = cls(max_seq_len=emb.shape[0], d_model=emb.shape[1])
        pe.embeddings = emb
        return pe


class Adam:
    """Adam optimizer for parameter updates."""
    
    def __init__(self, lr: float = 0.001, beta1: float = 0.9, beta2: float = 0.999, eps: float = 1e-8):
        self.lr = lr
        self.beta1 = beta1
        self.beta2 = beta2
        self.eps = eps
        self.t = 0
        self.m = {}
        self.v = {}
    
    def update(self, params: dict, grads: dict) -> dict:
        """Update parameters using Adam. Returns updated params dict."""
        self.t += 1
        updated = {}
        for key in params:
            if key in grads:
                g = grads[key]
                if key not in self.m:
                    self.m[key] = np.zeros_like(params[key])
                    self.v[key] = np.zeros_like(params[key])
                self.m[key] = self.beta1 * self.m[key] + (1 - self.beta1) * g
                self.v[key] = self.beta2 * self.v[key] + (1 - self.beta2) * (g ** 2)
                m_hat = self.m[key] / (1 - self.beta1 ** self.t)
                v_hat = self.v[key] / (1 - self.beta2 ** self.t)
                updated[key] = params[key] - self.lr * m_hat / (np.sqrt(v_hat) + self.eps)
            else:
                updated[key] = params[key]
        return updated


class TransformerPolicyNetwork:
    """Full Transformer policy network for strategy weight selection.
    
    Same interface as PolicyNetwork and SequentialPolicyNetwork.
    Usable as drop-in replacement in LearningEngine.
    """
    
    def __init__(self, action_dim: int = 6, d_model: int = 64, num_heads: int = 4,
                 num_layers: int = 2, d_ff: int = 128, max_seq_len: int = 24,
                 dropout: float = 0.1, learning_rate: float = 0.001):
        
        self.action_dim = action_dim
        self.d_model = d_model
        self.max_seq_len = max_seq_len
        self.learning_rate = learning_rate
        
        # Layers
        self.pos_encoding = PositionalEncoding(max_seq_len, d_model)
        self.encoder_layers = [
            TransformerEncoderLayer(d_model, num_heads, d_ff, max_seq_len, dropout)
            for _ in range(num_layers)
        ]
        
        # Global pooling → policy head
        scale_policy1 = np.sqrt(2.0 / (d_model + 32))
        scale_policy2 = np.sqrt(2.0 / (32 + action_dim))
        self.policy_W1 = np.random.randn(d_model, 32) * scale_policy1
        self.policy_b1 = np.zeros(32)
        self.policy_W2 = np.random.randn(32, action_dim) * scale_policy2
        self.policy_b2 = np.zeros(action_dim)
        
        # Optimizer
        self.optimizer = Adam(lr=learning_rate)
        
        # Cache
        self._cache = {}
        self._training = True
    
    # ------------------------------------------------------------------
    # Forward pass
    # ------------------------------------------------------------------
    
    def forward(self, x: np.ndarray, training: bool = None) -> np.ndarray:
        """Forward pass through transformer → softmax strategy weights.
        
        Args:
            x: (batch, seq, d_model) input embeddings
            training: Force training/eval mode
        
        Returns:
            (batch, action_dim) strategy weight probabilities
        """
        if training is None:
            training = self._training
        
        # Positional encoding
        x = self.pos_encoding.forward(x)
        
        # Transformer encoder layers
        for layer in self.encoder_layers:
            x = layer.forward(x, training=training)
        
        # Global mean pooling: (batch, seq, d_model) → (batch, d_model)
        pooled = np.mean(x, axis=1)
        
        # Policy head: d_model → 32 → action_dim → softmax
        hidden = np.maximum(0, np.einsum('bd,dh->bh', pooled, self.policy_W1) + self.policy_b1)
        logits = np.einsum('bh,ha->ba', hidden, self.policy_W2) + self.policy_b2
        
        # Numerically stable softmax
        logits_max = np.max(logits, axis=-1, keepdims=True)
        exp_logits = np.exp(logits - logits_max)
        probs = exp_logits / np.sum(exp_logits, axis=-1, keepdims=True)
        
        if training:
            self._cache = {
                'input': x if training else None,  # Original input before pos encoding
                'pooled': pooled,
                'hidden': hidden,
                'logits': logits,
                'probs': probs,
            }
        
        return probs
    
    # ------------------------------------------------------------------
    # Backward pass
    # ------------------------------------------------------------------
    
    def backward(self, d_out: np.ndarray) -> np.ndarray:
        """Backward pass. d_out = gradient of loss w.r.t. softmax output."""
        cache = self._cache
        batch_size = d_out.shape[0]
        
        # Gradient through softmax
        # dL/dlogits = probs * (d_out - sum(d_out * probs))
        d_logits = cache['probs'] * (d_out - np.sum(d_out * cache['probs'], axis=-1, keepdims=True))
        
        # Gradient through policy head
        self.d_policy_b2 = np.sum(d_logits, axis=0)
        self.d_policy_W2 = np.einsum('bh,ba->ha', cache['hidden'], d_logits)
        d_hidden = np.einsum('ba,ha->bh', d_logits, self.policy_W2)
        d_hidden = d_hidden * (cache['hidden'] > 0)  # ReLU backward
        
        self.d_policy_b1 = np.sum(d_hidden, axis=0)
        self.d_policy_W1 = np.einsum('bd,bh->dh', cache['pooled'], d_hidden)
        d_pooled = np.einsum('bh,dh->bd', d_hidden, self.policy_W1)
        
        # Gradient through pooling: broadcast back to sequence positions
        seq_len = self.encoder_layers[0]._cache.get('x', np.zeros((batch_size, 1, self.d_model))).shape[1] if hasattr(self.encoder_layers[0], '_cache') else self.max_seq_len
        d_pooled = d_pooled[:, np.newaxis, :] / seq_len  # Broadcast back
        
        # Gradient through encoder layers (reverse order)
        d_x = d_pooled * np.ones((batch_size, seq_len, self.d_model)) / seq_len  # Approximate
        for layer in reversed(self.encoder_layers):
            try:
                d_x = layer.backward(d_x)
            except Exception:
                pass  # Skip if backward cache not available
        
        return d_x
    
    # ------------------------------------------------------------------
    # Strategy weight selection
    # ------------------------------------------------------------------
    
    def select_weights(self, state: np.ndarray, weight_floor: float = 0.01) -> list:
        """Select strategy weights from state vector.
        
        Args:
            state: Can be either:
              - (seq_len, d_model) — token embedder output (Transformer path)
              - (state_dim,) — flat feature vector (MLP fallback)
        
        Returns:
            Weights list of length action_dim
        """
        self._training = False
        
        if state.ndim == 1:
            # Flat state vector — use as if it's a 1-timestep sequence
            # Pad to seq_len
            x = np.zeros((self.max_seq_len, self.d_model))
            x[0, :min(state.shape[0], self.d_model)] = state[:self.d_model]
            x = x[np.newaxis, :, :]
        elif state.ndim == 2:
            x = state[np.newaxis, :, :]
        else:
            x = state
        
        probs = self.forward(x, training=False)
        weights = probs[0].tolist()
        
        # Apply soft floor
        floor = weight_floor
        weights = [max(w, floor) for w in weights]
        total = sum(weights)
        weights = [w / total for w in weights]
        
        self._training = True
        return weights
    
    # ------------------------------------------------------------------
    # Training helpers
    # ------------------------------------------------------------------
    
    def get_attention_weights(self, x: np.ndarray) -> list:
        """Return attention weights for visualization (dashboard reasoning).
        
        Returns list of (batch, num_heads, seq, seq) per layer.
        """
        self._training = False
        old_training = self._training
        x = self.pos_encoding.forward(x if x.ndim == 3 else x[np.newaxis, :, :])
        attn_maps = []
        for layer in self.encoder_layers:
            layer.forward(x, training=True)  # Need cache for attention weights
            attn_maps.append(layer.attention._cache.get('attn_weights', None))
        self._training = True
        return attn_maps
    
    def get_params(self) -> dict:
        """Collect all trainable parameters for the optimizer."""
        params = {}
        params['policy_W1'] = self.policy_W1
        params['policy_b1'] = self.policy_b1
        params['policy_W2'] = self.policy_W2
        params['policy_b2'] = self.policy_b2
        params['pos_emb'] = self.pos_encoding.embeddings
        for i, layer in enumerate(self.encoder_layers):
            params[f'enc{i}_W_o'] = layer.attention.W_o
            params[f'enc{i}_W_q'] = layer.attention.W_q
            params[f'enc{i}_W_k'] = layer.attention.W_k
            params[f'enc{i}_W_v'] = layer.attention.W_v
            params[f'enc{i}_b_o'] = layer.attention.b_o
            params[f'enc{i}_b_q'] = layer.attention.b_q
            params[f'enc{i}_b_k'] = layer.attention.b_k
            params[f'enc{i}_b_v'] = layer.attention.b_v
            params[f'enc{i}_ln1_gamma'] = layer.norm1.gamma
            params[f'enc{i}_ln1_beta'] = layer.norm1.beta
            params[f'enc{i}_ln2_gamma'] = layer.norm2.gamma
            params[f'enc{i}_ln2_beta'] = layer.norm2.beta
            params[f'enc{i}_ffn_W1'] = layer.ffn.W1
            params[f'enc{i}_ffn_b1'] = layer.ffn.b1
            params[f'enc{i}_ffn_W2'] = layer.ffn.W2
            params[f'enc{i}_ffn_b2'] = layer.ffn.b2
        return params
    
    def get_grads(self) -> dict:
        """Collect gradients from the last backward pass."""
        grads = {}
        if hasattr(self, 'd_policy_W1'):
            grads['policy_W1'] = self.d_policy_W1
            grads['policy_b1'] = self.d_policy_b1
            grads['policy_W2'] = self.d_policy_W2
            grads['policy_b2'] = self.d_policy_b2
        for i, layer in enumerate(self.encoder_layers):
            attn = layer.attention
            norm1 = layer.norm1
            norm2 = layer.norm2
            ffn = layer.ffn
            for attr_name, key in [
                ('d_W_o', f'enc{i}_W_o'), ('d_W_q', f'enc{i}_W_q'),
                ('d_W_k', f'enc{i}_W_k'), ('d_W_v', f'enc{i}_W_v'),
                ('d_b_o', f'enc{i}_b_o'), ('d_b_q', f'enc{i}_b_q'),
                ('d_b_k', f'enc{i}_b_k'), ('d_b_v', f'enc{i}_b_v'),
            ]:
                if hasattr(attn, attr_name):
                    grads[key] = getattr(attn, attr_name)
            for attr_name, key in [
                ('d_gamma', f'enc{i}_ln1_gamma'), ('d_beta', f'enc{i}_ln1_beta'),
            ]:
                if hasattr(norm1, attr_name):
                    grads[key] = getattr(norm1, attr_name)
            for attr_name, key in [
                ('d_gamma', f'enc{i}_ln2_gamma'), ('d_beta', f'enc{i}_ln2_beta'),
            ]:
                if hasattr(norm2, attr_name):
                    grads[key] = getattr(norm2, attr_name)
            for attr_name, key in [
                ('d_W1', f'enc{i}_ffn_W1'), ('d_b1', f'enc{i}_ffn_b1'),
                ('d_W2', f'enc{i}_ffn_W2'), ('d_b2', f'enc{i}_ffn_b2'),
            ]:
                if hasattr(ffn, attr_name):
                    grads[key] = getattr(ffn, attr_name)
        return grads
    
    def apply_gradients(self):
        """Adam step on accumulated gradients."""
        params = self.get_params()
        grads = self.get_grads()
        if not grads:
            return
        updated = self.optimizer.update(params, grads)
        
        # Write back
        self.policy_W1 = updated['policy_W1']
        self.policy_b1 = updated['policy_b1']
        self.policy_W2 = updated['policy_W2']
        self.policy_b2 = updated['policy_b2']
        self.pos_encoding.embeddings = updated['pos_emb']
        for i, layer in enumerate(self.encoder_layers):
            layer.attention.W_o = updated[f'enc{i}_W_o']
            layer.attention.W_q = updated[f'enc{i}_W_q']
            layer.attention.W_k = updated[f'enc{i}_W_k']
            layer.attention.W_v = updated[f'enc{i}_W_v']
            layer.attention.b_o = updated[f'enc{i}_b_o']
            layer.attention.b_q = updated[f'enc{i}_b_q']
            layer.attention.b_k = updated[f'enc{i}_b_k']
            layer.attention.b_v = updated[f'enc{i}_b_v']
            layer.norm1.gamma = updated[f'enc{i}_ln1_gamma']
            layer.norm1.beta = updated[f'enc{i}_ln1_beta']
            layer.norm2.gamma = updated[f'enc{i}_ln2_gamma']
            layer.norm2.beta = updated[f'enc{i}_ln2_beta']
            layer.ffn.W1 = updated[f'enc{i}_ffn_W1']
            layer.ffn.b1 = updated[f'enc{i}_ffn_b1']
            layer.ffn.W2 = updated[f'enc{i}_ffn_W2']
            layer.ffn.b2 = updated[f'enc{i}_ffn_b2']
    
    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    
    def to_json(self) -> str:
        """Serialize entire network to JSON."""
        import json
        data = {
            'action_dim': self.action_dim,
            'd_model': self.d_model,
            'num_layers': len(self.encoder_layers),
            'max_seq_len': self.max_seq_len,
            'learning_rate': self.learning_rate,
            'pos_encoding': json.loads(self.pos_encoding.to_json()),
            'encoder_layers': [json.loads(layer.to_json()) for layer in self.encoder_layers],
            'policy_W1': self.policy_W1.tolist(),
            'policy_b1': self.policy_b1.tolist(),
            'policy_W2': self.policy_W2.tolist(),
            'policy_b2': self.policy_b2.tolist(),
        }
        return json.dumps(data)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'TransformerPolicyNetwork':
        """Deserialize from JSON."""
        import json
        data = json.loads(json_str)
        net = cls(
            action_dim=data['action_dim'],
            d_model=data['d_model'],
            num_heads=data['encoder_layers'][0]['attention']['num_heads'],
            num_layers=data['num_layers'],
            d_ff=len(data['encoder_layers'][0]['ffn']['b1']),
            max_seq_len=data['max_seq_len'],
            dropout=data['encoder_layers'][0]['attention']['dropout'],
            learning_rate=data['learning_rate'],
        )
        net.pos_encoding = PositionalEncoding.from_json(json.dumps(data['pos_encoding']))
        for i, layer_data in enumerate(data['encoder_layers']):
            net.encoder_layers[i] = TransformerEncoderLayer.from_json(json.dumps(layer_data))
        net.policy_W1 = np.array(data['policy_W1'])
        net.policy_b1 = np.array(data['policy_b1'])
        net.policy_W2 = np.array(data['policy_W2'])
        net.policy_b2 = np.array(data['policy_b2'])
        return net
