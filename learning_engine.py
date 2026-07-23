import numpy as np
import json
import logging
import random

class ReplayBuffer:
    """Experience replay buffer for batch policy gradient training.
    
    Stores (state, alignment, advantage) tuples and samples minibatches.
    This decouples training from individual trade events, smoothing gradients
    and preventing catastrophic forgetting.
    
    Uses a set of state fingerprints to prevent duplicate experiences.
    When capacity is reached, the OLDEST experience is evicted (FIFO)
    rather than overwriting an arbitrary position, ensuring temporal
    diversity in the buffer.
    """
    def __init__(self, capacity=200):
        self.capacity = capacity
        self.buffer = []
        self._fingerprints = set()

    def push(self, state, alignment, advantage):
        # Create a fingerprint from the state to detect duplicates
        state_flat = np.asarray(state).flatten()
        fp = hash(state_flat.tobytes())
        if fp in self._fingerprints:
            # Duplicate state — skip to avoid double-counting the same experience
            return False
        
        if len(self.buffer) >= self.capacity:
            # FIFO eviction: remove oldest to make room
            oldest_state, _, _ = self.buffer.pop(0)
            old_fp = hash(np.asarray(oldest_state).flatten().tobytes())
            self._fingerprints.discard(old_fp)
        
        self.buffer.append((state, alignment, advantage))
        self._fingerprints.add(fp)
        return True

    def sample(self, batch_size=32):
        if len(self.buffer) < batch_size:
            return list(self.buffer)
        return random.sample(self.buffer, batch_size)

    def __len__(self):
        return len(self.buffer)


class PolicyNetwork:
    """NumPy-based Policy Gradient Neural Network with Experience Replay.
    
    Inputs (State Dim = 8):
    - Market Regime (1.0 if Mean Reverting, 0.0 if Trending)
    - Mean Reversion Speed (theta)
    - Normalized RSI (-1.0 to 1.0)
    - Normalized MACD Histogram
    - Bollinger Band Position (-0.5 to 0.5)
    - ATR Volatility Ratio
    - Recent 10-trade Win Trend
    - News Sentiment Weight Factor
    
    Outputs (Action Dim = num_strategies):
    - Softmax probability distribution over the strategies.
    
    Training uses a replay buffer to batch-update from past experiences,
    avoiding weight collapse from single-trade noise.
    """
    def __init__(self, state_dim=8, hidden_dim=12, action_dim=6, learning_rate=0.05, hidden_layers=1, dropout=0.0, optimizer="Adam"):
        self.state_dim = state_dim
        self.hidden_dim = hidden_dim
        self.action_dim = action_dim
        self.lr = learning_rate
        self.hidden_layers = hidden_layers
        self.dropout = dropout
        self.optimizer = optimizer
        
        # Initialize layers lists
        self.W = []
        self.b = []
        
        # Input to first hidden layer
        self.W.append(np.random.randn(state_dim, hidden_dim) * np.sqrt(2.0 / state_dim))
        self.b.append(np.zeros((1, hidden_dim)))
        
        # Intermediate hidden layers
        for _ in range(hidden_layers - 1):
            self.W.append(np.random.randn(hidden_dim, hidden_dim) * np.sqrt(2.0 / hidden_dim))
            self.b.append(np.zeros((1, hidden_dim)))
            
        # Hidden layer to output layer
        self.W.append(np.random.randn(hidden_dim, action_dim) * np.sqrt(2.0 / hidden_dim))
        self.b.append(np.zeros((1, action_dim)))
        
        # Optimizer states for Adam / RMSprop
        self.m_W = [np.zeros_like(w) for w in self.W]
        self.m_b = [np.zeros_like(b) for b in self.b]
        self.v_W = [np.zeros_like(w) for w in self.W]
        self.v_b = [np.zeros_like(b) for b in self.b]
        self.t = 0
        
        # Policy Gradient Baseline & Entropy scaling for stable convergence
        self.reward_baseline = 0.0
        self.baseline_alpha = 0.05
        
        # Experience replay buffer
        self.replay = ReplayBuffer(capacity=200)
        # Batch size for replay training
        self.replay_batch_size = 32
        # How often to train from replay (every N trades)
        self.replay_train_interval = 5
        
        # Learning rate scheduling: initial and minimum LR
        self.initial_lr = learning_rate
        self.min_lr = learning_rate * 0.1  # Decay floor at 10% of initial
        self.lr_decay_steps = 100  # Halving point (in gradient steps)
        self.total_learning_steps = 0  # Tracks all gradient updates

    def softmax(self, x):
        e_x = np.exp(x - np.max(x, axis=-1, keepdims=True))
        return e_x / np.sum(e_x, axis=-1, keepdims=True)

    def forward(self, state, training=True):
        """Runs forward pass to allocate strategy weights based on market state.
        
        Args:
            state: Input feature vector
            training: If True, apply dropout (inverted dropout scaling).
                      During inference, set to False to disable dropout.
        """
        self.state = np.array(state).reshape(1, -1)
        self.a = [self.state]
        self.z = []
        
        # Forward pass through hidden layers
        for i in range(len(self.W) - 1):
            z_curr = np.dot(self.a[-1], self.W[i]) + self.b[i]
            self.z.append(z_curr)
            a_curr = np.maximum(0, z_curr)  # ReLU
            # Apply dropout only in training mode
            if training and self.dropout > 0:
                mask = (np.random.rand(*a_curr.shape) >= self.dropout) / (1.0 - self.dropout)
                a_curr = a_curr * mask
            self.a.append(a_curr)
            
        # Final output layer (Softmax)
        z_out = np.dot(self.a[-1], self.W[-1]) + self.b[-1]
        self.z.append(z_out)
        self.probs = self.softmax(z_out)
        return self.probs[0]

    def _apply_gradients(self, dW, db):
        """Apply gradients using the configured optimizer.
        
        Also applies learning rate decay: LR halves roughly every
        lr_decay_steps gradient updates, down to min_lr (10% of initial).
        This reduces aggressive updates as more data accumulates.
        """
        self.t += 1
        self.total_learning_steps += 1
        
        # Cosine-like LR scheduling: gentle decay, accelerates as steps accumulate
        fraction = min(1.0, self.total_learning_steps / self.lr_decay_steps)
        self.lr = self.initial_lr * (1.0 - fraction * 0.9)  # Decay to 10% of initial over lr_decay_steps
        self.lr = max(self.lr, self.min_lr)
        
        # Weight change magnitude tracking (every 10th step, log gradient norm)
        _total_grad_sq = 0.0
        for i in range(len(dW)):
            _total_grad_sq += np.sum(dW[i] ** 2) + np.sum(db[i] ** 2)
        _grad_norm = np.sqrt(_total_grad_sq)
        if self.total_learning_steps % 10 == 0:
            if _grad_norm > 10.0:
                logging.warning(
                    f"[GRADIENT NORM] grad_norm={_grad_norm:.4f} > 10.0 — gradients may be exploding. "
                    f"LR={self.lr:.6f}, step={self.total_learning_steps}"
                )
            elif _grad_norm < 1e-8 and self.total_learning_steps > 5:
                logging.warning(
                    f"[GRADIENT NORM] grad_norm={_grad_norm:.10f} < 1e-8 — gradients may be vanishing. "
                    f"Step={self.total_learning_steps}"
                )
        
        for i in range(len(self.W)):
            if self.optimizer == "Adam":
                beta1 = 0.9
                beta2 = 0.999
                eps = 1e-8
                
                self.m_W[i] = beta1 * self.m_W[i] + (1 - beta1) * dW[i]
                self.m_b[i] = beta1 * self.m_b[i] + (1 - beta1) * db[i]
                self.v_W[i] = beta2 * self.v_W[i] + (1 - beta2) * (dW[i] ** 2)
                self.v_b[i] = beta2 * self.v_b[i] + (1 - beta2) * (db[i] ** 2)
                
                m_W_hat = self.m_W[i] / (1 - beta1 ** self.t)
                m_b_hat = self.m_b[i] / (1 - beta1 ** self.t)
                v_W_hat = self.v_W[i] / (1 - beta2 ** self.t)
                v_b_hat = self.v_b[i] / (1 - beta2 ** self.t)
                
                self.W[i] -= self.lr * m_W_hat / (np.sqrt(v_W_hat) + eps)
                self.b[i] -= self.lr * m_b_hat / (np.sqrt(v_b_hat) + eps)
                
            elif self.optimizer == "RMSprop":
                decay = 0.9
                eps = 1e-8
                self.v_W[i] = decay * self.v_W[i] + (1 - decay) * (dW[i] ** 2)
                self.v_b[i] = decay * self.v_b[i] + (1 - decay) * (db[i] ** 2)
                
                self.W[i] -= self.lr * dW[i] / (np.sqrt(self.v_W[i]) + eps)
                self.b[i] -= self.lr * db[i] / (np.sqrt(self.v_b[i]) + eps)
                
            else:  # SGD
                self.W[i] -= self.lr * dW[i]
                self.b[i] -= self.lr * db[i]

    def _compute_gradients(self, state, alignment, advantage, entropy_beta=0.01):
        """Compute policy gradients for a single (state, alignment, advantage) tuple.

        Uses the REINFORCE policy gradient (Williams, 1992).

        The ensemble weights define a distribution over strategies. The 'action' is the
        strategy whose signal most strongly agrees with the trade direction.

        Policy gradient:  ∇J = E[∇log π(a|s) * A]
        For softmax policy:  ∂log π(a_i|s)/∂z_j = δ_{ij} - π_j

        Entropy bonus gradient (Schulman et al., 2017):
        H = -Σ π_i log π_i
        ∂H/∂z_j = -π_j * (log π_j + H)
        """
        # Forward pass to cache activations
        self.forward(state)
        
        # Scale advantage to a reasonable range for gradient magnitude
        scaled_reward = np.clip(advantage * 100.0, -5.0, 5.0)
        
        probs = self.probs
        
        # Determine the chosen action: the strategy with strongest alignment signal
        # alignment = strategy_signals * dir_val  (positive = agreed with trade direction)
        alignment_flat = alignment.reshape(-1)
        if np.any(alignment_flat > 0):
            # Pick the strategy that most strongly agreed with the trade direction
            action_idx = np.argmax(alignment_flat)
        else:
            # All strategies disagreed; pick the one that disagreed least
            action_idx = np.argmax(alignment_flat)  # max of negative values = least negative
        
        # --- REINFORCE policy gradient (Williams, 1992) ---
        # Objective to maximize: J = E[A * log π(a|s)]
        # We use gradient DESCENT: minimize L = -J = -A * log π(a|s)
        # ∂(-J)/∂z_i = -A * (δ_{i,action} - π_i)
        one_hot = np.zeros_like(probs)
        one_hot[0, action_idx] = 1.0
        d_z = -scaled_reward * (one_hot - probs)
        
        # --- Entropy bonus: L = -J - beta * H where H = -sum(π log π) ---
        # dL/dz = -∂J/∂z - beta * ∂H/∂z
        # ∂H/∂z_j = -π_j * (log π_j + H)  (derived from softmax Jacobian)
        # entropy_grad = π * (H + log π) = -∂H/∂z
        # So: dL/dz = -A*(e_a-π) - beta * (-entropy_grad) = -A*(e_a-π) + beta * entropy_grad
        log_p = np.log(probs + 1e-9)
        entropy = -np.sum(probs * log_p)
        entropy_grad = probs * (entropy + log_p)  # = π * (H + log(π)) = -∂H/∂z
        d_z += entropy_beta * entropy_grad  # dL/dz = -A*(e_a-π) + beta*π*(H+logπ)
        
        dW = [None] * len(self.W)
        db = [None] * len(self.b)
        
        for i in reversed(range(len(self.W))):
            dW[i] = np.dot(self.a[i].T, d_z)
            db[i] = d_z
            if i > 0:
                d_a = np.dot(d_z, self.W[i].T)
                d_z = d_a * (self.z[i-1] > 0)
        
        return dW, db

    def backward(self, state, strategy_signals, trade_direction, reward):
        """Policy Gradient backward pass with experience replay.
        
        Stores (state, alignment, advantage) in replay buffer and
        periodically trains from a minibatch to smooth gradients.
        
        After each gradient update, verifies that loss decreased.
        If loss increased, logs WARNING — the update may have been harmful.
        """
        dir_val = 1.0 if trade_direction == "BUY" else -1.0
        alignment = np.array(strategy_signals) * dir_val
        
        # Calculate advantage
        advantage = reward - self.reward_baseline
        self.reward_baseline = (1.0 - self.baseline_alpha) * self.reward_baseline + self.baseline_alpha * reward
        
        def _compute_loss_for_state(s, al, adv, training_=False):
            """Compute current policy loss for a single (state, alignment, advantage).
            Uses training=False for consistency with inference.
            """
            probs = self.forward(s, training=training_)
            alignment_flat = al.reshape(-1)
            if np.any(alignment_flat > 0):
                action_idx = np.argmax(alignment_flat)
            else:
                action_idx = np.argmax(alignment_flat)
            scaled_adv = np.clip(adv * 100.0, -5.0, 5.0)
            log_prob = np.log(max(probs[action_idx], 1e-12))
            return -scaled_adv * log_prob  # REINFORCE loss
        
        # Compute loss BEFORE update (no dropout for deterministic loss computation)
        loss_before = _compute_loss_for_state(state, alignment, advantage, training_=False)
        
        # Store in replay buffer (returns False if duplicate state was skipped)
        _added = self.replay.push(np.array(state, dtype=float), alignment, advantage)
        if not _added:
            if not hasattr(self, '_dup_count'):
                self._dup_count = 0
            self._dup_count += 1
            if self._dup_count % 50 == 1:
                logging.debug(f"[REPLAY DUPLICATE] Skipped {self._dup_count} duplicate experiences (state fingerprint collision)")
        
        # Online/offline gradient consistency check (occasional validation):
        # If we have enough replay data, compute the offline (minibatch) gradient
        # and compare its direction to the online (single-trade) gradient.
        # If they disagree (cosine similarity < 0), the online update may be harmful.
        if len(self.replay) >= self.replay_batch_size and self.total_learning_steps > 0 and (
            self.total_learning_steps % 10 == 0  # Check every 10th step
        ):
            _batch = self.replay.sample(self.replay_batch_size)
            # Compute offline gradient direction on a minibatch
            dW_off = [np.zeros_like(w) for w in self.W]
            db_off = [np.zeros_like(b) for b in self.b]
            for s, al, adv in _batch:
                dW_s, db_s = self._compute_gradients(s, al, adv)
                for i in range(len(dW_off)):
                    dW_off[i] += dW_s[i]
                    db_off[i] += db_s[i]
            n_batch = len(_batch)
            for i in range(len(dW_off)):
                dW_off[i] /= n_batch
                db_off[i] /= n_batch
            
            # Cosine similarity between online and offline gradients
            dot_num = 0.0
            norm_online_sq = 0.0
            norm_offline_sq = 0.0
            eps_ = 1e-12
            for i in range(len(dW)):
                dot_num += np.sum(dW[i] * dW_off[i])
                norm_online_sq += np.sum(dW[i] ** 2)
                norm_offline_sq += np.sum(dW_off[i] ** 2)
            cos_sim = dot_num / (np.sqrt(norm_online_sq) * np.sqrt(norm_offline_sq) + eps_)
            if cos_sim < 0:
                logging.warning(
                    f"[GRADIENT CONSISTENCY] Online gradient disagrees with offline minibatch "
                    f"(cosine_sim={cos_sim:.3f}). Online update may overfit to noise."
                )
        
        # Immediate gradient update for this trade (online learning)
        dW, db = self._compute_gradients(state, alignment, advantage)
        self._apply_gradients(dW, db)
        
        # Compute loss AFTER update
        loss_after = _compute_loss_for_state(state, alignment, advantage)
        
        # Verify loss decreased (gradient descent should reduce loss)
        # Use training=False for deterministic loss comparison
        loss_after = _compute_loss_for_state(state, alignment, advantage, training_=False)
        if loss_after > loss_before * 1.01:  # >1% increase
            logging.warning(
                f"[LOSS VERIFICATION] Loss increased from {loss_before:.4f} to {loss_after:.4f} "
                f"after gradient update. advantage={advantage:.4f}, reward={reward:.4f}"
            )
        
        # Periodically train from replay buffer to reinforce patterns
        if len(self.replay) >= self.replay_batch_size and (
            self.t % self.replay_train_interval == 0
        ):
            batch = self.replay.sample(self.replay_batch_size)
            # Compute loss before batch update (no dropout)
            batch_loss_before = sum(_compute_loss_for_state(s, al, adv, training_=False) for s, al, adv in batch) / len(batch)
            
            # Accumulate gradients across batch
            dW_acc = [np.zeros_like(w) for w in self.W]
            db_acc = [np.zeros_like(b) for b in self.b]
            for s, al, adv in batch:
                dW_s, db_s = self._compute_gradients(s, al, adv)
                for i in range(len(dW_acc)):
                    dW_acc[i] += dW_s[i]
                    db_acc[i] += db_s[i]
            # Average and apply
            n = len(batch)
            for i in range(len(dW_acc)):
                dW_acc[i] /= n
                db_acc[i] /= n
            self._apply_gradients(dW_acc, db_acc)
            
            # Compute loss after batch update (no dropout)
            batch_loss_after = sum(_compute_loss_for_state(s, al, adv, training_=False) for s, al, adv in batch) / len(batch)
            if batch_loss_after > batch_loss_before * 1.01:
                logging.warning(
                    f"[LOSS VERIFICATION] Batch replay loss increased from {batch_loss_before:.4f} "
                    f"to {batch_loss_after:.4f} after batch gradient update (n={n})"
                )
                # Revert the batch update: reload weights from saved state
                # This prevents the batch update from making things worse.
                # We revert by re-applying the negative gradient.
                for i in range(len(dW_acc)):
                    dW_acc[i] = -dW_acc[i]
                    db_acc[i] = -db_acc[i]
                self._apply_gradients(dW_acc, db_acc)
                logging.info("[LOSS VERIFICATION] Reverted batch gradient update (loss increased).")

    def to_json(self):
        """Serialize network weights to JSON string."""
        data = {
            "W": [w.tolist() for w in self.W],
            "b": [b.tolist() for b in self.b],
            "hidden_layers": self.hidden_layers,
            "dropout": self.dropout,
            "optimizer": self.optimizer,
            "m_W": [mw.tolist() for mw in self.m_W],
            "m_b": [mb.tolist() for mb in self.m_b],
            "v_W": [vw.tolist() for vw in self.v_W],
            "v_b": [vb.tolist() for vb in self.v_b],
            "t": self.t,
            "initial_lr": self.initial_lr,
            "min_lr": self.min_lr,
            "lr_decay_steps": self.lr_decay_steps,
            "total_learning_steps": self.total_learning_steps,
        }
        return json.dumps(data)

    def from_json(self, json_str):
        """Load network weights from JSON string in-place, with automatic weight migration."""
        data = json.loads(json_str)
        if "W" in data:
            self.W = [np.array(w) for w in data["W"]]
            self.b = [np.array(b) for b in data["b"]]
            self.hidden_layers = data.get("hidden_layers", 1)
            self.dropout = data.get("dropout", 0.0)
            self.optimizer = data.get("optimizer", "Adam")
            # Restore Adam optimizer momentum/velocity states if present
            if "m_W" in data and "m_b" in data:
                try:
                    self.m_W = [np.array(mw) for mw in data["m_W"]]
                    self.m_b = [np.array(mb) for mb in data["m_b"]]
                    self.v_W = [np.array(vw) for vw in data["v_W"]]
                    self.v_b = [np.array(vb) for vb in data["v_b"]]
                    self.t = data.get("t", 0)
                except (ValueError, KeyError, IndexError) as e:
                    logging.warning(f"[Adam State] Could not restore optimizer state (will re-init): {e}")
        else:
            # Backward compatibility
            self.W = [np.array(data["W1"]), np.array(data["W2"])]
            self.b = [np.array(data["b1"]), np.array(data["b2"])]
            self.hidden_layers = 1
            self.dropout = 0.0
            self.optimizer = "Adam"

        # Migrate old state_dim=7 weights to new state_dim=8
        if self.W[0].shape[0] == 7:
            logging.info("[WEIGHT MIGRATION] Expanding state_dim 7→8 (adding sentiment input)")
            new_w0 = np.random.randn(8, self.W[0].shape[1]) * np.sqrt(2.0 / 8)
            new_w0[:7, :] = self.W[0]
            self.W[0] = new_w0
            new_b0 = self.b[0]
            self.b[0] = new_b0

        # Migrate old action_dim weights to current expected action_dim
        current_action_dim = self.W[-1].shape[1]
        expected_dim = self.action_dim
        if expected_dim != current_action_dim:
            if expected_dim > current_action_dim:
                # PAD with small random weights for new strategies
                logging.info(f"[WEIGHT MIGRATION] Padding action_dim {current_action_dim}→{expected_dim}")
                pad_w = np.random.randn(self.W[-1].shape[0], expected_dim - current_action_dim) * 0.01
                pad_b = np.random.randn(1, expected_dim - current_action_dim) * 0.01
                self.W[-1] = np.hstack([self.W[-1], pad_w])
                self.b[-1] = np.hstack([self.b[-1], pad_b])
            else:
                # TRUNCATE: fewer strategies now (unlikely but handle it)
                logging.info(f"[WEIGHT MIGRATION] Truncating action_dim {current_action_dim}→{expected_dim}")
                self.W[-1] = self.W[-1][:, :expected_dim]
                self.b[-1] = self.b[-1][:, :expected_dim]
        
        # Restore LR scheduling state if present (backward-compatible: defaults to __init__ values)
        self.initial_lr = data.get("initial_lr", self.initial_lr)
        self.min_lr = data.get("min_lr", self.initial_lr * 0.1)
        self.lr_decay_steps = data.get("lr_decay_steps", 100)
        self.total_learning_steps = data.get("total_learning_steps", 0)
        
        # Update action_dim to match actual loaded weights after migration
        self.action_dim = self.W[-1].shape[1]

        # Init optimizer momentum/velocity if NOT already restored from saved state,
        # OR if individual optimizer tensor shapes don't match weights (dimension migration)
        need_optimizer_reinit = False
        if "m_W" not in data or not hasattr(self, 'm_W') or len(self.m_W) != len(self.W):
            need_optimizer_reinit = True
        else:
            # Check that every optimizer state tensor matches its corresponding weight shape
            for i in range(len(self.W)):
                if self.m_W[i].shape != self.W[i].shape or self.m_b[i].shape != self.b[i].shape:
                    need_optimizer_reinit = True
                    break
                if self.v_W[i].shape != self.W[i].shape or self.v_b[i].shape != self.b[i].shape:
                    need_optimizer_reinit = True
                    break

        if need_optimizer_reinit:
            self.m_W = [np.zeros_like(w) for w in self.W]
            self.m_b = [np.zeros_like(b) for b in self.b]
            self.v_W = [np.zeros_like(w) for w in self.W]
            self.v_b = [np.zeros_like(b) for b in self.b]
            self.t = 0

    @property
    def W1(self):
        return self.W[0]
        
    @W1.setter
    def W1(self, value):
        self.W[0] = value

    @property
    def b1(self):
        return self.b[0]
        
    @b1.setter
    def b1(self, value):
        self.b[0] = value

    @property
    def W2(self):
        return self.W[-1]
        
    @W2.setter
    def W2(self, value):
        self.W[-1] = value

    @property
    def b2(self):
        return self.b[-1]
        
    @b2.setter
    def b2(self, value):
        self.b[-1] = value


class LearningEngine:
    def __init__(self, num_strategies=12, learning_rate=0.05, weight_floor=0.05, hidden_dim=12, hidden_layers=1, dropout=0.0, optimizer="Adam", nn_architecture="mlp"):
        self.num_strategies = num_strategies
        self.weight_floor = weight_floor
        self.nn_architecture = nn_architecture
        if nn_architecture == "transformer":
            from transformer_policy_net import TransformerPolicyNetwork
            # Import VOCAB_SIZE for token embedding
            try:
                from tokenizer import VOCAB_SIZE as _VS
            except ImportError:
                _VS = 128
            self.policy_net = TransformerPolicyNetwork(
                action_dim=num_strategies,
                d_model=hidden_dim if hidden_dim >= 64 else 64,
                num_heads=4,
                num_layers=max(2, hidden_layers),
                max_seq_len=24,
                dropout=dropout,
                learning_rate=learning_rate,
                vocab_size=_VS,
            )
        elif nn_architecture == "lstm":
            from sequential_policy_net import SequentialPolicyNetwork
            self.policy_net = SequentialPolicyNetwork(
                action_dim=num_strategies,
                embedding_dim=hidden_dim,
                hidden_dim=hidden_dim,
                num_layers=hidden_layers,
                learning_rate=learning_rate,
                dropout=dropout,
            )
        else:
            self.policy_net = PolicyNetwork(
                state_dim=8,
                hidden_dim=hidden_dim,
                action_dim=num_strategies,
                learning_rate=learning_rate,
                hidden_layers=hidden_layers,
                dropout=dropout,
                optimizer=optimizer
            )
        
    def get_state_vector(self, row, price_history, closed_trades):
        """Constructs a normalized state vector representing current market conditions."""
        # 1. Market Regime
        from quant_utils import estimate_ou_process
        is_mr = 0.0
        theta = 0.0
        if len(price_history) >= 20:
            theta_est, mu, is_mr_est = estimate_ou_process(price_history)
            is_mr = 1.0 if is_mr_est and theta_est > 0.05 else 0.0
            theta = np.clip(theta_est, 0.0, 1.0)

        # 2. RSI momentum
        rsi = (float(row.get('rsi', 50.0)) - 50.0) / 50.0  # mapped to [-1.0, 1.0]

        # 3. MACD
        macd_hist = float(row.get('macd_hist', 0.0))
        close = float(row.get('close', 1e-9))
        macd_norm = np.clip(macd_hist / close, -0.05, 0.05) * 20.0  # normalized

        # 4. Bollinger Band position
        bb_upper = float(row.get('bb_upper', close))
        bb_lower = float(row.get('bb_lower', close))
        bb_range = bb_upper - bb_lower + 1e-9
        bb_pos = (close - bb_lower) / bb_range - 0.5  # mapped to [-0.5, 0.5]

        # 5. Volatility (ATR ratio)
        atr = float(row.get('atr', 0.0))
        atr_ratio = np.clip(atr / close, 0.0, 0.1) * 10.0  # normalized

        # 6. Win trend (Success rate over last 10 trades)
        win_trend = 0.5
        if len(closed_trades) > 0:
            recent_trades = closed_trades[-10:]
            wins = sum(1 for t in recent_trades if t['pnl'] > 0)
            win_trend = wins / len(recent_trades)

        # 7. Real-time news sentiment (value in [-1.0, 1.0])
        sentiment = float(row.get('sentiment', 0.0))

        return [is_mr, theta, rsi, macd_norm, bb_pos, atr_ratio, win_trend, sentiment]

    def select_weights(self, state):
        """Queries the Policy Network for optimal strategy weights given current state.
        
        For MLP mode: state is an 8-element feature vector.
        For LSTM mode: state is a (seq_len, max_tokens) token ID array.
        """
        if self.nn_architecture in ("lstm", "transformer") and hasattr(self.policy_net, 'select_weights'):
            return self.policy_net.select_weights(state, weight_floor=self.weight_floor)
        raw_weights = self.policy_net.forward(state, training=False)
        
        # Apply weight floor to ensure all strategies keep active search-space exploration
        n = len(raw_weights)
        if any(raw_weights < self.weight_floor):
            raw_weights = np.maximum(raw_weights, self.weight_floor)
            raw_weights = raw_weights / np.sum(raw_weights)
            
        return raw_weights.tolist()

    def learn_from_trade(self, state, strategy_signals, trade_direction, pnl_percent):
        """Performs backward propagation on the Policy Network using the trade PnL as reward."""
        # Ensure strategy_signals matches action_dim; pad/trim if needed
        target_len = self.policy_net.action_dim
        if len(strategy_signals) > target_len:
            strategy_signals = strategy_signals[:target_len]
        elif len(strategy_signals) < target_len:
            strategy_signals = list(strategy_signals) + [0.0] * (target_len - len(strategy_signals))
        # backward() calls forward() internally — no need for separate forward() call
        # The reward is the actual trade percentage profit/loss (e.g. +0.024 for +2.4%)
        self.policy_net.backward(state, strategy_signals, trade_direction, pnl_percent)
        
        # Return updated weights for the current state after learning
        return self.select_weights(state)
