"""
PPO (Proximal Policy Optimization) Agent for NexusTrader.

Uses the existing PolicyNetwork as the *actor* and adds a separate
critic (value) network.  Supports:
  - PPO-clip objective  (eps=0.2)
  - Generalized Advantage Estimation (GAE)
  - KL-divergence early stopping
  - Learning-rate scheduling (cosine annealing)
  - Full serialisation for brain storage
"""

import json
import logging
import math
import numpy as np

from learning_engine import PolicyNetwork

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Critic network  (value function V(s) – scalar output)
# ---------------------------------------------------------------------------

class PPOCritic:
    """NumPy-based value network for PPO.

    Architecture mirrors PolicyNetwork except the output is a single
    scalar (state-value estimate) with *no* activation function.
    """

    def __init__(self, state_dim=8, hidden_dim=12, hidden_layers=1,
                 learning_rate=0.05, optimizer="Adam"):
        self.state_dim = state_dim
        self.hidden_dim = hidden_dim
        self.hidden_layers = hidden_layers
        self.lr = learning_rate
        self.optimizer = optimizer

        # Layer parameters
        self.W = []
        self.b = []

        # Input → first hidden layer
        self.W.append(np.random.randn(state_dim, hidden_dim)
                      * np.sqrt(2.0 / state_dim))
        self.b.append(np.zeros((1, hidden_dim)))

        for _ in range(hidden_layers - 1):
            self.W.append(np.random.randn(hidden_dim, hidden_dim)
                          * np.sqrt(2.0 / hidden_dim))
            self.b.append(np.zeros((1, hidden_dim)))

        # Last hidden → scalar output  (linear, no activation)
        self.W.append(np.random.randn(hidden_dim, 1)
                      * np.sqrt(2.0 / hidden_dim))
        self.b.append(np.zeros((1, 1)))

        # Adam states
        self.m_W = [np.zeros_like(w) for w in self.W]
        self.m_b = [np.zeros_like(b) for b in self.b]
        self.v_W = [np.zeros_like(w) for w in self.W]
        self.v_b = [np.zeros_like(b) for b in self.b]
        self.t = 0

    # ----------------------------------------------------------------
    # Forward / backward
    # ----------------------------------------------------------------

    def forward(self, state):
        """Return scalar value estimate V(s)."""
        x = np.atleast_2d(np.asarray(state, dtype=np.float64))
        self._activations = [x]
        self._z = []

        for i in range(len(self.W) - 1):
            z = np.dot(self._activations[-1], self.W[i]) + self.b[i]
            self._z.append(z)
            a = np.maximum(0, z)                    # ReLU
            self._activations.append(a)

        z_out = np.dot(self._activations[-1], self.W[-1]) + self.b[-1]
        self._z.append(z_out)
        return z_out[0, 0]

    def _gradients(self, state, target):
        """Compute gradients of MSE loss:  L = (V(s) - target)^2."""
        value = self.forward(state)
        delta = value - target                       # scalar
        grad_scale = 2.0 * delta                     # dL/dV

        d_z = np.full((1, 1), grad_scale, dtype=np.float64)

        dW = [None] * len(self.W)
        db = [None] * len(self.b)

        for i in reversed(range(len(self.W))):
            dW[i] = np.dot(self._activations[i].T, d_z)
            db[i] = d_z
            if i > 0:
                da = np.dot(d_z, self.W[i].T)
                d_z = da * (self._z[i - 1] > 0).astype(np.float64)
        return dW, db

    def update(self, state, target):
        """Single gradient-descent step on (state, target)."""
        dW, db = self._gradients(state, target)
        self._apply_gradients(dW, db)

    def update_batch(self, states, targets):
        """Batch MSE update."""
        n = len(states)
        dW_acc = [np.zeros_like(w) for w in self.W]
        db_acc = [np.zeros_like(b) for b in self.b]

        for s, t in zip(states, targets):
            dW_s, db_s = self._gradients(s, t)
            for i in range(len(dW_acc)):
                dW_acc[i] += dW_s[i]
                db_acc[i] += db_s[i]

        for i in range(len(dW_acc)):
            dW_acc[i] /= n
            db_acc[i] /= n
        self._apply_gradients(dW_acc, db_acc)

    # ----------------------------------------------------------------
    # Optimizer  (Adam / RMSprop / SGD)
    # ----------------------------------------------------------------

    def _apply_gradients(self, dW, db):
        self.t += 1
        for i in range(len(self.W)):
            if self.optimizer == "Adam":
                b1, b2, eps = 0.9, 0.999, 1e-8
                self.m_W[i] = b1 * self.m_W[i] + (1 - b1) * dW[i]
                self.m_b[i] = b1 * self.m_b[i] + (1 - b1) * db[i]
                self.v_W[i] = b2 * self.v_W[i] + (1 - b2) * (dW[i] ** 2)
                self.v_b[i] = b2 * self.v_b[i] + (1 - b2) * (db[i] ** 2)
                m_wh = self.m_W[i] / (1 - b1 ** self.t)
                m_bh = self.m_b[i] / (1 - b1 ** self.t)
                v_wh = self.v_W[i] / (1 - b2 ** self.t)
                v_bh = self.v_b[i] / (1 - b2 ** self.t)
                self.W[i] -= self.lr * m_wh / (np.sqrt(v_wh) + eps)
                self.b[i] -= self.lr * m_bh / (np.sqrt(v_bh) + eps)
            elif self.optimizer == "RMSprop":
                decay, eps = 0.9, 1e-8
                self.v_W[i] = decay * self.v_W[i] + (1 - decay) * (dW[i] ** 2)
                self.v_b[i] = decay * self.v_b[i] + (1 - decay) * (db[i] ** 2)
                self.W[i] -= self.lr * dW[i] / (np.sqrt(self.v_W[i]) + eps)
                self.b[i] -= self.lr * db[i] / (np.sqrt(self.v_b[i]) + eps)
            else:   # SGD
                self.W[i] -= self.lr * dW[i]
                self.b[i] -= self.lr * db[i]

    # ----------------------------------------------------------------
    # Serialisation
    # ----------------------------------------------------------------

    def to_json(self):
        return json.dumps({
            "W": [w.tolist() for w in self.W],
            "b": [b.tolist() for b in self.b],
            "hidden_layers": self.hidden_layers,
            "optimizer": self.optimizer,
            "m_W": [mw.tolist() for mw in self.m_W],
            "m_b": [mb.tolist() for mb in self.m_b],
            "v_W": [vw.tolist() for vw in self.v_W],
            "v_b": [vb.tolist() for vb in self.v_b],
            "t": self.t,
        })

    def from_json(self, s):
        data = json.loads(s)
        self.W = [np.array(w) for w in data["W"]]
        self.b = [np.array(b) for b in data["b"]]
        self.hidden_layers = data.get("hidden_layers", 1)
        self.optimizer = data.get("optimizer", "Adam")
        self.m_W = [np.array(mw) for mw in data.get("m_W",
                    [np.zeros_like(w) for w in self.W])]
        self.m_b = [np.array(mb) for mb in data.get("m_b",
                    [np.zeros_like(b) for b in self.b])]
        self.v_W = [np.array(vw) for vw in data.get("v_W",
                    [np.zeros_like(w) for w in self.W])]
        self.v_b = [np.array(vb) for vb in data.get("v_b",
                    [np.zeros_like(b) for b in self.b])]
        self.t = data.get("t", 0)


# ---------------------------------------------------------------------------
# PPO Agent
# ---------------------------------------------------------------------------

class PPOAgent:
    """PPO agent that wraps a PolicyNetwork as actor + PPOCritic.

    Keeps ``self.policy_net`` to remain API-compatible with
    ``NexusTraderOrchestrator`` and ``LearningEngine``.
    """

    def __init__(self, policy_net, critic=None,
                 clip_epsilon=0.2, gamma=0.99, lam=0.95,
                 value_coef=0.5, entropy_coef=0.01,
                 kl_target=0.01, max_grad_norm=0.5,
                 lr_schedule_decay=0.9995):
        """
        Parameters
        ----------
        policy_net : PolicyNetwork  (or compatible)
            Actor network.  Stored as ``self.policy_net`` for compatibility.
        critic : PPOCritic or None
            Value network.  Auto-created with matching dimensions if None.
        clip_epsilon : float
            PPO clipping range (default 0.2).
        gamma : float
            Discount factor.
        lam : float
            GAE lambda.
        value_coef : float
            Weight of value loss in total loss.
        entropy_coef : float
            Weight of entropy bonus.
        kl_target : float
            KL-divergence threshold for early stopping.
        max_grad_norm : float
            Global gradient norm clipping.
        lr_schedule_decay : float
            Per-update multiplicative learning-rate decay.
        """
        self.policy_net = policy_net
        self.clip_epsilon = clip_epsilon
        self.gamma = gamma
        self.lam = lam
        self.value_coef = value_coef
        self.entropy_coef = entropy_coef
        self.kl_target = kl_target
        self.max_grad_norm = max_grad_norm
        self.lr_schedule_decay = lr_schedule_decay
        self._update_count = 0

        # Create critic if not provided
        if critic is None:
            self.critic = PPOCritic(
                state_dim=policy_net.state_dim,
                hidden_dim=policy_net.hidden_dim,
                hidden_layers=policy_net.hidden_layers,
                learning_rate=policy_net.lr,
                optimizer=policy_net.optimizer,
            )
        else:
            self.critic = critic

    # ----------------------------------------------------------------
    # Action selection  (compatible with LearningEngine API)
    # ----------------------------------------------------------------

    def get_action(self, state):
        """Return action logits (strategy weights) given *state*.

        Compatible with existing ``select_weights`` flow.
        """
        return self.policy_net.forward(state)

    def get_state_value(self, state):
        """Return scalar value estimate V(s)."""
        return self.critic.forward(state)

    # ----------------------------------------------------------------
    # GAE computation
    # ----------------------------------------------------------------

    def compute_gae(self, rewards, values, dones):
        """Compute Generalised Advantage Estimates.

        Parameters
        ----------
        rewards : 1-D ndarray, shape (T,)
        values : 1-D ndarray, shape (T+1,)
            values[:-1] are V(s_t); values[-1] is V(s_T) (bootstrapped).
        dones : 1-D ndarray, shape (T,), bool

        Returns
        -------
        advantages : ndarray, shape (T,)
        returns : ndarray, shape (T,)   (targets for value network)
        """
        T = len(rewards)
        advantages = np.zeros(T, dtype=np.float64)
        gae = 0.0
        for t in reversed(range(T)):
            delta = (rewards[t] + self.gamma * values[t + 1] * (1 - dones[t])
                     - values[t])
            gae = delta + self.gamma * self.lam * (1 - dones[t]) * gae
            advantages[t] = gae
        returns = advantages + values[:-1]
        return advantages, returns

    # ----------------------------------------------------------------
    # PPO update
    # ----------------------------------------------------------------

    def update(self, states, actions, old_log_probs, advantages, returns):
        """Perform a single PPO update on a batch of trajectory data.

        Parameters
        ----------
        states : ndarray, shape (B, D)
        actions : ndarray, shape (B,)
        old_log_probs : ndarray, shape (B,)
        advantages : ndarray, shape (B,)
        returns : ndarray, shape (B,)

        Returns
        -------
        info : dict
            Statistics for logging (approx_kl, entropy, clip_frac, losses).
        """
        # Normalise advantages  (stabilises training)
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

        # --- Actor (policy) gradients ---
        # Re-run forward pass to get new action probabilities
        dW_acc = [np.zeros_like(w) for w in self.policy_net.W]
        db_acc = [np.zeros_like(b) for b in self.policy_net.b]

        total_actor_loss = 0.0
        total_entropy = 0.0
        clip_frac = 0.0
        approx_kl = 0.0
        n = len(states)

        for i in range(n):
            state = states[i]
            action = actions[i]
            adv = advantages[i]
            old_lp = old_log_probs[i]

            # Forward pass to cache activations in policy_net
            probs = self.policy_net.forward(state)
            # Log-prob of the taken action
            new_lp = np.log(max(probs[int(action)], 1e-12))

            # Ratio r(theta)
            ratio = np.exp(new_lp - old_lp)

            # PPO-clipped surrogate objective
            surr1 = ratio * adv
            surr2 = np.clip(ratio, 1 - self.clip_epsilon,
                            1 + self.clip_epsilon) * adv
            actor_loss = -min(surr1, surr2)
            total_actor_loss += actor_loss

            # Entropy bonus
            entropy = -np.sum(probs * np.log(np.clip(probs, 1e-12, 1.0)))
            total_entropy += entropy

            # KL divergence (approximate)
            approx_kl += (old_lp - new_lp)

            # Clip fraction (diagnostic)
            if abs(ratio - 1) > self.clip_epsilon:
                clip_frac += 1.0 / n

            # PPO policy gradient: L^{CLIP}(theta) = -E[min(r_t * A_t, clip(r_t, ...) * A_t)]
            # dL/d(logits) = dL/d(probs) * d(probs)/d(logits)
            # 
            # For action probability p_a:
            # dL/d(logit_i) = sum_j dL/d(p_j) * p_j * (delta_{ij} - p_i)
            # where dL/d(p_a) = -adv * ratio * (1/p_a)  [if unclipped]
            #          or = 0                          [if clipped]
            #
            # This simplifies to:
            # dL/d(logit_i) = -adv * ratio * (delta_{i,action} - p_i)  [if unclipped]
            d_z_actor = np.zeros((1, self.policy_net.action_dim), dtype=np.float64)
            
            if surr1 < surr2:
                # Unclipped: use the proper softmax policy gradient
                # dL/d(logit_i) = -surrogate_gradient wrt log-prob * (delta_ia - p_i)
                # = -adv * ratio * (delta_i,action - p_i)
                d_z_actor[0] = -adv * ratio * (np.eye(self.policy_net.action_dim)[int(action)] - probs)
            else:
                # Clipped: gradient is zero (clipping stops gradient flow)
                pass

            # Entropy gradient: H = -sum(p * log(p))
            # dH/d(logit_i) = -p_i * (log(p_i) + 1 - sum_j p_j * (log(p_j) + 1))
            # We compute entropy_grad = -dH/d(logit_i) = p_i * (log(p_i) + 1 - sum_j p_j * (log(p_j) + 1))
            # Total loss L = L_CLIP - entropy_coef * H
            # dL/d(logit_i) = d(L_CLIP)/d(logit_i) - entropy_coef * dH/d(logit_i)
            #                = d(L_CLIP)/d(logit_i) + entropy_coef * entropy_grad
            log_p = np.log(np.clip(probs, 1e-12, 1.0))
            entropy_grad = probs * (log_p + 1.0 - np.sum(probs * (log_p + 1.0)))
            d_z_actor += self.entropy_coef * entropy_grad.reshape(1, -1)

            # Backprop through policy_net
            for j in reversed(range(len(self.policy_net.W))):
                if j == len(self.policy_net.W) - 1:
                    d_z = d_z_actor
                else:
                    d_z = np.dot(d_a, self.policy_net.W[j + 1].T)
                    d_z = d_z * (self.policy_net.z[j] > 0).astype(np.float64)

                dW_acc[j] += np.dot(self.policy_net.a[j].T, d_z)
                db_acc[j] += d_z
                d_a = d_z

        # Average gradients
        for j in range(len(dW_acc)):
            dW_acc[j] /= n
            db_acc[j] /= n

        # Gradient clipping
        total_norm = math.sqrt(sum(np.sum(w ** 2) for w in dW_acc)
                               + sum(np.sum(b ** 2) for b in db_acc))
        if total_norm > self.max_grad_norm:
            scale = self.max_grad_norm / (total_norm + 1e-8)
            for j in range(len(dW_acc)):
                dW_acc[j] *= scale
                db_acc[j] *= scale

        self.policy_net._apply_gradients(dW_acc, db_acc)

        # --- Critic (value) update ---
        self.critic.update_batch(states, returns)

        # --- LR scheduling ---
        self.policy_net.lr *= self.lr_schedule_decay
        self.critic.lr *= self.lr_schedule_decay

        self._update_count += 1

        approx_kl /= n
        total_actor_loss /= n
        total_entropy /= n

        return {
            'actor_loss': float(total_actor_loss),
            'entropy': float(total_entropy),
            'clip_frac': float(clip_frac),
            'approx_kl': float(approx_kl),
        }

    # ----------------------------------------------------------------
    # Full training step  (sample from replay buffer + PPO update)
    # ----------------------------------------------------------------

    def train_on_buffer(self, replay_buffer, batch_size=64,
                        ppo_epochs=4, minibatch_size=32):
        """Sample from *replay_buffer* and perform *ppo_epochs* PPO updates.

        Returns
        -------
        info : dict
            Averaged statistics across all minibatch updates.
        """
        if len(replay_buffer) < batch_size:
            logger.debug("Replay buffer too small for PPO training "
                         "(%d < %d)", len(replay_buffer), batch_size)
            return None

        states, actions, rewards, next_states, dones, indices, _ = \
            replay_buffer.sample(batch_size)

        # Bootstrap values for terminal states
        values = np.zeros(len(states) + 1, dtype=np.float64)
        for i in range(len(states)):
            values[i] = self.critic.forward(states[i])
        # Bootstrap value for last next_state
        if not dones[-1]:
            values[-1] = self.critic.forward(next_states[-1])
        else:
            values[-1] = 0.0

        advantages, returns = self.compute_gae(rewards, values, dones)

        # Old action log-probs (before update)
        old_log_probs = np.zeros(len(states), dtype=np.float64)
        for i in range(len(states)):
            probs = self.policy_net.forward(states[i])
            old_log_probs[i] = np.log(max(probs[int(actions[i])], 1e-12))

        avg_info = {}
        update_count = 0

        for epoch in range(ppo_epochs):
            # Shuffle
            perm = np.random.permutation(len(states))
            for start in range(0, len(states), minibatch_size):
                idxs = perm[start:start + minibatch_size]
                info = self.update(
                    states[idxs], actions[idxs],
                    old_log_probs[idxs],
                    advantages[idxs], returns[idxs],
                )

                # KL early stopping
                if info['approx_kl'] > 1.5 * self.kl_target:
                    logger.info("PPO early stopping at epoch %d (KL=%.5f)",
                                epoch, info['approx_kl'])
                    return avg_info

                # Accumulate stats
                for k, v in info.items():
                    if k not in avg_info:
                        avg_info[k] = 0.0
                    avg_info[k] += v
                update_count += 1

        if update_count > 0:
            for k in avg_info:
                avg_info[k] /= update_count

        # Update buffer priorities using |TD-error|
        td_errors = np.abs(returns - values[:-1])
        replay_buffer.update_priorities(indices, td_errors)

        return avg_info

    # ----------------------------------------------------------------
    # Serialisation  (actor + critic packed into one JSON)
    # ----------------------------------------------------------------

    def to_json(self):
        return json.dumps({
            'actor': self.policy_net.to_json(),
            'critic': self.critic.to_json(),
            'clip_epsilon': self.clip_epsilon,
            'gamma': self.gamma,
            'lam': self.lam,
            'value_coef': self.value_coef,
            'entropy_coef': self.entropy_coef,
            'kl_target': self.kl_target,
            'max_grad_norm': self.max_grad_norm,
            'lr_schedule_decay': self.lr_schedule_decay,
            '_update_count': self._update_count,
        })

    @classmethod
    def from_json(cls, s, base_policy_net=None):
        """Reconstruct a PPOAgent from a JSON string.

        Parameters
        ----------
        s : str
            JSON blob produced by :meth:`to_json`.
        base_policy_net : PolicyNetwork or None
            If given, its weights are overwritten with the stored actor
            weights.  If None a fresh PolicyNetwork is created (but
            requires state_dim / action_dim metadata).
        """
        data = json.loads(s)

        # Restore actor
        actor_json = data.get('actor', '{}')
        if base_policy_net is not None:
            base_policy_net.from_json(actor_json)
            policy_net = base_policy_net
        else:
            policy_net = PolicyNetwork()
            policy_net.from_json(actor_json)

        # Restore critic
        critic = PPOCritic(
            state_dim=policy_net.state_dim,
            hidden_dim=policy_net.hidden_dim,
            hidden_layers=policy_net.hidden_layers,
            learning_rate=policy_net.lr,
            optimizer=policy_net.optimizer,
        )
        critic_json = data.get('critic', '{}')
        if critic_json != '{}':
            critic.from_json(critic_json)

        agent = cls(policy_net, critic=critic)
        agent.clip_epsilon = data.get('clip_epsilon', 0.2)
        agent.gamma = data.get('gamma', 0.99)
        agent.lam = data.get('lam', 0.95)
        agent.value_coef = data.get('value_coef', 0.5)
        agent.entropy_coef = data.get('entropy_coef', 0.01)
        agent.kl_target = data.get('kl_target', 0.01)
        agent.max_grad_norm = data.get('max_grad_norm', 0.5)
        agent.lr_schedule_decay = data.get('lr_schedule_decay', 0.9995)
        agent._update_count = data.get('_update_count', 0)
        return agent
