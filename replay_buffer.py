"""
Prioritized Experience Replay (PER) Buffer for PPO/DQN training.

Stores (state, action, reward, next_state, done) tuples ranked by TD-error
magnitude so the agent learns more from surprising transitions.
"""

import numpy as np
import logging
import pickle
import random

logger = logging.getLogger(__name__)


class PrioritizedExperienceReplay:
    """Prioritized Experience Replay buffer with configurable alpha/beta.

    Sampling probability is proportional to |TD-error|^alpha.
    Importance-sampling weights are annealed via beta.
    """

    def __init__(self, capacity=5000, alpha=0.6, beta=0.4,
                 beta_increment=0.001, epsilon=1e-6, seed=None):
        self.capacity = int(capacity)
        self.alpha = float(alpha)
        self.beta = float(beta)
        self.beta_increment = float(beta_increment)
        self.epsilon = float(epsilon)

        # Storage
        self.buffer = [None] * self.capacity
        self.priorities = np.zeros(self.capacity, dtype=np.float64)
        self.pos = 0
        self.size = 0

        if seed is not None:
            np.random.seed(seed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, state, action, reward, next_state, done, error=1.0):
        """Insert a transition with an initial priority based on *error*.

        Parameters
        ----------
        state : array-like
        action : float or int
        reward : float
        next_state : array-like
        done : bool
        error : float
            Initial TD-error estimate.  Defaults to 1.0 so new samples
            are replayed at least once before being discarded.

        Returns
        -------
        bool
            True if insertion succeeded, False if buffer was full and
            oldest experience was overwritten (capacity overflow).
        """
        overflow = False
        if self.size >= self.capacity:
            overflow = True
        
        priority = (abs(error) + self.epsilon) ** self.alpha
        self.buffer[self.pos] = (np.asarray(state, dtype=np.float32),
                                 float(action),
                                 float(reward),
                                 np.asarray(next_state, dtype=np.float32),
                                 bool(done))
        self.priorities[self.pos] = priority
        self.pos = (self.pos + 1) % self.capacity
        self.size = min(self.size + 1, self.capacity)
        
        # Log capacity warning at most once per 10 overflows to avoid spam
        if overflow:
            if not hasattr(self, '_overflow_count'):
                self._overflow_count = 0
            self._overflow_count += 1
            if self._overflow_count % 10 == 1:
                logger.warning(
                    f"[REPLAY OVERFLOW] Buffer at capacity ({self.capacity}). "
                    f"Oldest experience evicted. Total overflows: {self._overflow_count}"
                )
        
        return not overflow

    def sample(self, batch_size):
        """Return a minibatch sampled according to stored priorities.

        Returns
        -------
        states : ndarray, shape (B, D)
        actions : ndarray, shape (B,)
        rewards : ndarray, shape (B,)
        next_states : ndarray, shape (B, D)
        dones : ndarray, shape (B,)
        indices : ndarray, shape (B,)
        weights : ndarray, shape (B,)   — importance-sampling weights
        """
        batch_size = min(batch_size, self.size)
        if batch_size == 0:
            raise RuntimeError("Cannot sample from an empty replay buffer.")

        probs = self._compute_probs()
        indices = np.random.choice(self.size, batch_size, p=probs, replace=False)

        # Importance-sampling weights (annealed)
        total = self.size
        weights = (total * probs[indices]) ** (-self.beta)
        weights /= np.max(weights) + 1e-12

        # Anneal beta
        self.beta = min(1.0, self.beta + self.beta_increment)

        # Unpack
        batch = [self.buffer[i] for i in indices]
        states = np.array([e[0] for e in batch], dtype=np.float32)
        actions = np.array([e[1] for e in batch], dtype=np.float32)
        rewards = np.array([e[2] for e in batch], dtype=np.float32)
        next_states = np.array([e[3] for e in batch], dtype=np.float32)
        dones = np.array([e[4] for e in batch], dtype=np.float32)

        return states, actions, rewards, next_states, dones, indices, weights

    def update_priorities(self, indices, errors):
        """Update priorities for a batch of transitions after computing
        fresh TD-errors."""
        for idx, err in zip(indices, errors):
            self.priorities[idx] = (abs(err) + self.epsilon) ** self.alpha

    def __len__(self):
        return self.size

    def clear(self):
        self.buffer = [None] * self.capacity
        self.priorities.fill(0.0)
        self.pos = 0
        self.size = 0

    # ------------------------------------------------------------------
    # Serialisation  (for DB storage via pickle / base64)
    # ------------------------------------------------------------------

    def serialize(self):
        """Return a bytes blob that can be stored in the database."""
        return pickle.dumps({
            'buffer': [(s.tolist(), a, r, ns.tolist(), d)
                       for s, a, r, ns, d in self.buffer[:self.size]],
            'priorities': self.priorities[:self.size].tolist(),
            'capacity': self.capacity,
            'pos': self.pos,
            'size': self.size,
            'alpha': self.alpha,
            'beta': self.beta,
            'beta_increment': self.beta_increment,
            'epsilon': self.epsilon,
        })

    @classmethod
    def deserialize(cls, blob):
        """Reconstruct a :class:`PrioritizedExperienceReplay` from a
        bytes blob previously returned by :meth:`serialize`."""
        data = pickle.loads(blob)
        buf = cls(
            capacity=data['capacity'],
            alpha=data.get('alpha', 0.6),
            beta=data.get('beta', 0.4),
            beta_increment=data.get('beta_increment', 0.001),
            epsilon=data.get('epsilon', 1e-6),
        )
        buf.buffer = [None] * buf.capacity
        for i, (s, a, r, ns, d) in enumerate(data['buffer']):
            buf.buffer[i] = (np.asarray(s, dtype=np.float32),
                             float(a), float(r),
                             np.asarray(ns, dtype=np.float32),
                             bool(d))
        buf.priorities[:len(data['priorities'])] = data['priorities']
        buf.pos = data['pos']
        buf.size = data['size']
        return buf

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_probs(self):
        priorities = self.priorities[:self.size]
        total = np.sum(priorities)
        if total <= 0:
            return np.ones(self.size, dtype=np.float64) / self.size
        return priorities / total

    def __repr__(self):
        return (f"<PrioritizedExperienceReplay size={self.size}/{self.capacity} "
                f"alpha={self.alpha:.2f} beta={self.beta:.3f}>")
