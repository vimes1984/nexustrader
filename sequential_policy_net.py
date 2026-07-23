"""
Sequential Policy Network — Phase 3 of NN Architecture Upgrade.

LSTM-based policy gradient network that consumes tokenized candle sequences
instead of raw 8-dimensional feature vectors. This gives the model:
  - Temporal memory (remembers market context across candles)
  - Discrete state awareness (token vocabulary captures market grammar)
  - Cross-ticker readiness (architecture supports multi-head attention later)

Maintains the same interface as PolicyNetwork so it can be dropped into
LearningEngine via a config flag (nn_architecture: "mlp" | "lstm").
"""
import numpy as np
import json
from typing import Optional, List, Tuple
from token_embedder import TokenEmbedder
from tokenizer import (
    VOCAB_SIZE,
    tokenize_ticker_to_ids,
)


# ─── LSTM Cell (Pure NumPy) ────────────────────────────────────────────────

class LSTMCell:
    """Single LSTM cell with forget/input/output gates.

    Handles one time-step of the recurrence: h_t, c_t = LSTM(x_t, h_{t-1}, c_{t-1})
    """

    def __init__(self, input_dim: int, hidden_dim: int, seed: int = 42):
        rng = np.random.RandomState(seed)
        self.hidden_dim = hidden_dim
        self.input_dim = input_dim

        # Weight matrices: stacked [W_f, W_i, W_c, W_o] for input and hidden
        limit = np.sqrt(2.0 / input_dim)
        self.W = rng.randn(input_dim, hidden_dim * 4) * limit  # input weights
        self.U = rng.randn(hidden_dim, hidden_dim * 4) * limit  # hidden weights
        self.b = np.zeros((1, hidden_dim * 4))  # biases

        # Adam optimizer state
        self.m_W = np.zeros_like(self.W)
        self.v_W = np.zeros_like(self.W)
        self.m_U = np.zeros_like(self.U)
        self.v_U = np.zeros_like(self.U)
        self.m_b = np.zeros_like(self.b)
        self.v_b = np.zeros_like(self.b)
        self.t = 0

        # Cache for backward pass
        self.cache: dict = {}

    def forward(
        self, x: np.ndarray, h_prev: np.ndarray, c_prev: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Forward pass for one timestep.

        Args:
            x: (batch, input_dim) input at this timestep
            h_prev: (batch, hidden_dim) previous hidden state
            c_prev: (batch, hidden_dim) previous cell state

        Returns:
            (h, c) — new hidden and cell states
        """
        # Compute gates
        gates = np.dot(x, self.W) + np.dot(h_prev, self.U) + self.b  # (batch, 4*hidden)
        dim = self.hidden_dim
        f = 1.0 / (1.0 + np.exp(-gates[:, :dim]))  # forget gate (sigmoid)
        i = 1.0 / (1.0 + np.exp(-gates[:, dim:2*dim]))  # input gate (sigmoid)
        c_tilde = np.tanh(gates[:, 2*dim:3*dim])  # candidate cell
        o = 1.0 / (1.0 + np.exp(-gates[:, 3*dim:]))  # output gate (sigmoid)

        c = f * c_prev + i * c_tilde
        h = o * np.tanh(c)

        # Cache for backward
        self.cache = {
            'x': x, 'h_prev': h_prev, 'c_prev': c_prev,
            'f': f, 'i': i, 'c_tilde': c_tilde, 'o': o,
            'c': c, 'h': h, 'gates': gates,
        }
        return h, c

    def backward(
        self, dh: np.ndarray, dc: np.ndarray, learning_rate: float = 0.001
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Backprop through one timestep.

        Args:
            dh: gradient w.r.t. hidden state output
            dc: gradient w.r.t. cell state output
            learning_rate: Adam learning rate

        Returns:
            (dx, dh_prev, dc_prev) gradients
        """
        self.t += 1
        cache = self.cache
        dim = self.hidden_dim

        h, c = cache['h'], cache['c']
        o, i, f, c_tilde = cache['o'], cache['i'], cache['f'], cache['c_tilde']
        x, h_prev, c_prev = cache['x'], cache['h_prev'], cache['c_prev']

        # Output gate gradients
        do = dh * np.tanh(c)
        dc = dc + dh * o * (1.0 - np.tanh(c) ** 2)

        # Cell gradients
        dc_tilde = dc * i * (1.0 - c_tilde ** 2)
        di = dc * c_tilde * i * (1.0 - i)
        df = dc * c_prev * f * (1.0 - f)
        dc_prev = dc * f

        # Gate gradients stacked
        dgates = np.hstack([df, di, dc_tilde, do])  # (batch, 4*dim)

        # Weight gradients
        dW = np.dot(x.T, dgates) / x.shape[0]
        dU = np.dot(h_prev.T, dgates) / h_prev.shape[0]
        db = np.mean(dgates, axis=0, keepdims=True)
        dx = np.dot(dgates, self.W.T)
        dh_prev = np.dot(dgates, self.U.T)

        # Update weights
        self._adam_step(self.W, dW, self.m_W, self.v_W, learning_rate)
        self._adam_step(self.U, dU, self.m_U, self.v_U, learning_rate)
        self._adam_step(self.b, db, self.m_b, self.v_b, learning_rate)

        return dx, dh_prev, dc_prev

    def _adam_step(self, params, grads, m, v, lr, beta1=0.9, beta2=0.999, eps=1e-8):
        m[:] = beta1 * m + (1.0 - beta1) * grads
        v[:] = beta2 * v + (1.0 - beta2) * (grads ** 2)
        m_hat = m / (1.0 - beta1 ** self.t)
        v_hat = v / (1.0 - beta2 ** self.t)
        params -= lr * m_hat / (np.sqrt(v_hat) + eps)

    def to_json(self) -> str:
        return json.dumps({
            'W': self.W.tolist(), 'U': self.U.tolist(), 'b': self.b.tolist(),
            't': self.t, 'hidden_dim': self.hidden_dim, 'input_dim': self.input_dim,
        })

    def from_json(self, json_str: str):
        data = json.loads(json_str)
        self.W = np.array(data['W'])
        self.U = np.array(data['U'])
        self.b = np.array(data['b'])
        self.t = data.get('t', 0)
        self.hidden_dim = data['hidden_dim']
        self.input_dim = data['input_dim']


# ─── Sequential Policy Network ──────────────────────────────────────────────

class SequentialPolicyNetwork:
    """LSTM-based policy gradient network for trading strategy allocation.

    Architecture:
      TokenEmbedder (vocab→64d) → 2×LSTM (64→64, dropout=0.1)
      → Linear(64→action_dim) → Softmax

    Args:
        action_dim: number of trading strategies (output size)
        embedding_dim: token embedding dimension (default 64)
        hidden_dim: LSTM hidden state dimension (default 64)
        num_layers: number of stacked LSTM layers (default 2)
        learning_rate: Adam learning rate for RL training
        dropout: dropout rate between LSTM layers
        max_seq_len: maximum candle sequence length
        seed: random seed
    """

    def __init__(
        self,
        action_dim: int = 6,
        embedding_dim: int = 64,
        hidden_dim: int = 64,
        num_layers: int = 2,
        learning_rate: float = 0.001,
        dropout: float = 0.1,
        max_seq_len: int = 24,
        seed: int = 42,
    ):
        rng = np.random.RandomState(seed)

        self.action_dim = action_dim
        self.embedding_dim = embedding_dim
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.lr = learning_rate
        self.dropout = dropout
        self.max_seq_len = max_seq_len

        # Embedder
        self.embedder = TokenEmbedder(
            vocab_size=VOCAB_SIZE,
            embedding_dim=embedding_dim,
            max_seq_len=max_seq_len,
            seed=seed,
        )

        # LSTM layers
        self.lstm_layers: List[LSTMCell] = []
        input_dim = embedding_dim
        for i in range(num_layers):
            self.lstm_layers.append(
                LSTMCell(input_dim, hidden_dim, seed=seed + i)
            )
            input_dim = hidden_dim

        # Output projection: hidden → action logits
        self.W_out = rng.randn(hidden_dim, action_dim) * np.sqrt(2.0 / hidden_dim)
        self.b_out = np.zeros((1, action_dim))

        # Adam state for output layer
        self.m_Wo = np.zeros_like(self.W_out)
        self.v_Wo = np.zeros_like(self.W_out)
        self.m_bo = np.zeros_like(self.b_out)
        self.v_bo = np.zeros_like(self.b_out)
        self.t = 0

        # Policy gradient baseline
        self.reward_baseline = 0.0
        self.baseline_alpha = 0.05

        # Forward caches
        self.cache_h: List[List[np.ndarray]] = []  # hidden states per layer per timestep
        self.cache_c: List[List[np.ndarray]] = []  # cell states per layer per timestep
        self.cache_emb = None  # embedded input
        self.cache_logits = None
        self.cache_probs = None

    def forward(
        self,
        token_ids: np.ndarray,
        training: bool = False,
    ) -> np.ndarray:
        """Forward pass: token IDs → strategy weights.

        Args:
            token_ids: (seq_len, max_tokens_per_candle) int array
            training: if True, apply dropout

        Returns:
            (action_dim,) numpy array — Softmax probability distribution
        """
        batch_size = 1
        seq_len = token_ids.shape[0]

        # Embed
        emb = self.embedder.forward(
            token_ids, training=training
        )  # (1, seq_len, embedding_dim)
        self.cache_emb = emb

        # Initialize hidden/cell states
        self.cache_h = [[] for _ in range(self.num_layers)]
        self.cache_c = [[] for _ in range(self.num_layers)]

        h_states = [np.zeros((batch_size, self.hidden_dim)) for _ in range(self.num_layers)]
        c_states = [np.zeros((batch_size, self.hidden_dim)) for _ in range(self.num_layers)]

        # Process sequence
        for t in range(seq_len):
            x_t = emb[:, t, :]  # (1, embedding_dim)

            for layer_idx in range(self.num_layers):
                h, c = self.lstm_layers[layer_idx].forward(
                    x_t, h_states[layer_idx], c_states[layer_idx]
                )
                self.cache_h[layer_idx].append(h)
                self.cache_c[layer_idx].append(c)
                h_states[layer_idx] = h
                c_states[layer_idx] = c

                # Dropout between layers
                if training and self.dropout > 0 and layer_idx < self.num_layers - 1:
                    mask = (np.random.random(h.shape) >= self.dropout) / (1.0 - self.dropout)
                    x_t = h * mask
                else:
                    x_t = h

        # Final hidden state → logits
        final_h = h_states[-1]  # (1, hidden_dim)
        logits = np.dot(final_h, self.W_out) + self.b_out
        self.cache_logits = logits

        # Softmax
        e_x = np.exp(logits - np.max(logits, axis=-1, keepdims=True))
        probs = e_x / np.sum(e_x, axis=-1, keepdims=True)
        self.cache_probs = probs

        return probs[0]  # (action_dim,)

    def backward(self, state, strategy_signals, trade_direction, reward, weight_floor=0.0):
        """Policy gradient backward pass using trade outcome as reward.

        Args:
            state: unused (kept for API compat); the forward() cache is used
            strategy_signals: list of strategy signal strengths
            trade_direction: "BUY" or "SELL"
            reward: trade PnL percentage (e.g. 0.024 for +2.4%)
            weight_floor: minimum strategy weight (for exploration)
        """
        # Guard: must call forward() before backward()
        if self.cache_probs is None:
            logging.warning("[LSTM] backward() called without prior forward() — skipping gradient update")
            return

        self.t += 1

        dir_val = 1.0 if trade_direction == "BUY" else -1.0
        alignment = np.array(strategy_signals) * dir_val

        # Ensure alignment matches action_dim
        if len(alignment) != self.action_dim:
            alignment = np.resize(alignment, self.action_dim)

        # Advantage
        advantage = reward - self.reward_baseline
        self.reward_baseline = (
            1.0 - self.baseline_alpha
        ) * self.reward_baseline + self.baseline_alpha * reward

        scaled_reward = np.clip(advantage * 100.0, -5.0, 5.0)

        # Entropy bonus (prevent premature convergence)
        probs = self.cache_probs  # (1, action_dim)
        log_p = np.log(probs + 1e-9)
        entropy = -np.sum(probs * log_p)
        entropy_beta = 0.005

        # Gradient at output: dL/d(logit) for policy gradient + entropy
        # dL/d(logit_i) = -S * (alignment_i - sum_j(alignment_j) * p_i) - beta * p_i * (entropy - log(p_i))
        # Standard PG: dL/dz = S * (probs - alignment)  [with S = scaled_reward]
        d_logits = scaled_reward * (probs - alignment.reshape(1, -1))
        # Entropy gradient: dH/dz = p * (entropy - log(p))
        entropy_grad = probs * (entropy - log_p)
        d_logits -= entropy_beta * entropy_grad

        # Backprop through output layer
        dW_out = np.dot(self.cache_h[-1][-1].T, d_logits)
        db_out = d_logits
        self._adam_step_out(dW_out, db_out)

        # Gradient to LSTM: dL/dh for final layer at last timestep
        dh = np.dot(d_logits, self.W_out.T)  # (1, hidden_dim)
        dc = np.zeros_like(dh)

        seq_len = len(self.cache_h[0])

        # BPTT through time for stacked LSTM layers
        # Track dh/dc per layer as we go backwards through time
        dh_per_layer = [np.zeros((1, self.hidden_dim)) for _ in range(self.num_layers)]
        dc_per_layer = [np.zeros((1, self.hidden_dim)) for _ in range(self.num_layers)]
        # The last layer at the last timestep receives gradient from output
        dh_per_layer[-1] = dh

        for t in reversed(range(seq_len)):
            for layer_idx in reversed(range(self.num_layers)):
                # Combine gradient from output + gradient from next timestep
                dh_combined = dh_per_layer[layer_idx]
                dc_combined = dc_per_layer[layer_idx]
                
                dx, dh_in, dc_in = self.lstm_layers[layer_idx].backward(
                    dh_combined, dc_combined, self.lr
                )
                
                # Gradient flows to previous layer (lower index) at THIS timestep
                if layer_idx > 0:
                    dh_per_layer[layer_idx - 1] += dh_in
                    dc_per_layer[layer_idx - 1] += dc_in
                # Gradient also flows to next timestep of same layer
                # (handled by the reversed loop — we track in separate accumulators)
                
                # Save gradient to propagate to earlier timestep
                dh_per_layer[layer_idx] = dh_in
                dc_per_layer[layer_idx] = dc_in

        # Backprop through embedder
        if self.cache_emb is not None:
            # For the embedder: use the gradient from the first layer at the first timestep
            # In practice, we have dx from the bottom LSTM layer's backward call at timestep 0
            pass

    def _adam_step_out(self, dW, db, beta1=0.9, beta2=0.999, eps=1e-8):
        """Adam update for output projection layer."""
        self.m_Wo = beta1 * self.m_Wo + (1.0 - beta1) * dW
        self.v_Wo = beta2 * self.v_Wo + (1.0 - beta2) * (dW ** 2)
        self.m_bo = beta1 * self.m_bo + (1.0 - beta1) * db
        self.v_bo = beta2 * self.v_bo + (1.0 - beta2) * (db ** 2)

        m_hat_w = self.m_Wo / (1.0 - beta1 ** self.t)
        v_hat_w = self.v_Wo / (1.0 - beta2 ** self.t)
        m_hat_b = self.m_bo / (1.0 - beta1 ** self.t)
        v_hat_b = self.v_bo / (1.0 - beta2 ** self.t)

        self.W_out -= self.lr * m_hat_w / (np.sqrt(v_hat_w) + eps)
        self.b_out -= self.lr * m_hat_b / (np.sqrt(v_hat_b) + eps)

    def to_json(self) -> str:
        """Serialize entire network state."""
        return json.dumps({
            'action_dim': self.action_dim,
            'embedding_dim': self.embedding_dim,
            'hidden_dim': self.hidden_dim,
            'num_layers': self.num_layers,
            'lr': self.lr,
            'dropout': self.dropout,
            'max_seq_len': self.max_seq_len,
            'embedder': json.loads(self.embedder.to_json()),
            'lstm_layers': [json.loads(cell.to_json()) for cell in self.lstm_layers],
            'W_out': self.W_out.tolist(),
            'b_out': self.b_out.tolist(),
            't': self.t,
            'reward_baseline': self.reward_baseline,
        })

    def from_json(self, json_str: str):
        """Load network state from JSON."""
        data = json.loads(json_str)

        self.action_dim = data['action_dim']
        self.embedding_dim = data['embedding_dim']
        self.hidden_dim = data['hidden_dim']
        self.num_layers = data.get('num_layers', 2)
        self.lr = data.get('lr', 0.001)
        self.dropout = data.get('dropout', 0.1)
        self.max_seq_len = data.get('max_seq_len', 24)

        # Rebuild embedder
        embedder_data = data['embedder']
        self.embedder = TokenEmbedder(
            vocab_size=VOCAB_SIZE,
            embedding_dim=self.embedding_dim,
            max_seq_len=self.max_seq_len,
        )
        self.embedder.token_embeddings = np.array(embedder_data['token_embeddings'])
        self.embedder.pos_embeddings = np.array(embedder_data['pos_embeddings'])
        self.embedder.gamma = np.array(embedder_data['gamma'])
        self.embedder.beta = np.array(embedder_data['beta'])

        # Rebuild LSTM layers
        self.lstm_layers = []
        for layer_data in data['lstm_layers']:
            cell = LSTMCell(layer_data['input_dim'], layer_data['hidden_dim'])
            cell.W = np.array(layer_data['W'])
            cell.U = np.array(layer_data['U'])
            cell.b = np.array(layer_data['b'])
            cell.t = layer_data.get('t', 0)
            self.lstm_layers.append(cell)

        self.W_out = np.array(data['W_out'])
        self.b_out = np.array(data['b_out'])
        self.t = data.get('t', 0)
        self.reward_baseline = data.get('reward_baseline', 0.0)

        # Reinit Adam state
        self.m_Wo = np.zeros_like(self.W_out)
        self.v_Wo = np.zeros_like(self.W_out)
        self.m_bo = np.zeros_like(self.b_out)
        self.v_bo = np.zeros_like(self.b_out)

    def select_weights(self, token_ids: np.ndarray, weight_floor: float = 0.0) -> List[float]:
        """Convenience: forward pass with weight floor applied.

        Args:
            token_ids: (seq_len, max_tokens) token ID array
            weight_floor: minimum weight per strategy

        Returns:
            list of strategy weight floats
        """
        raw = self.forward(token_ids, training=False)
        if weight_floor > 0 and any(raw < weight_floor):
            raw = np.maximum(raw, weight_floor)
            raw = raw / np.sum(raw)
        return raw.tolist()
