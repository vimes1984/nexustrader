import numpy as np
import json
import logging

class PolicyNetwork:
    """NumPy-based Policy Gradient Neural Network for dynamic strategy weight allocation.
    
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

    def softmax(self, x):
        e_x = np.exp(x - np.max(x, axis=-1, keepdims=True))
        return e_x / np.sum(e_x, axis=-1, keepdims=True)

    def forward(self, state):
        """Runs forward pass to allocate strategy weights based on market state."""
        self.state = np.array(state).reshape(1, -1)
        self.a = [self.state]
        self.z = []
        
        # Forward pass through hidden layers
        for i in range(len(self.W) - 1):
            z_curr = np.dot(self.a[-1], self.W[i]) + self.b[i]
            self.z.append(z_curr)
            a_curr = np.maximum(0, z_curr)  # ReLU
            # Apply dropout in training if active
            if self.dropout > 0:
                mask = (np.random.rand(*a_curr.shape) >= self.dropout) / (1.0 - self.dropout)
                a_curr = a_curr * mask
            self.a.append(a_curr)
            
        # Final output layer (Softmax)
        z_out = np.dot(self.a[-1], self.W[-1]) + self.b[-1]
        self.z.append(z_out)
        self.probs = self.softmax(z_out)
        return self.probs[0]

    def backward(self, state, strategy_signals, trade_direction, reward):
        """Policy Gradient backward pass with advantage baseline and entropy regularization."""
        dir_val = 1.0 if trade_direction == "BUY" else -1.0
        
        # Calculate strategy alignment: signals are in [-1, 0, 1]
        alignment = np.array(strategy_signals) * dir_val
        
        # Calculate policy gradient advantage baseline
        advantage = reward - self.reward_baseline
        self.reward_baseline = (1.0 - self.baseline_alpha) * self.reward_baseline + self.baseline_alpha * reward
        
        # Scale advantage
        scaled_reward = np.clip(advantage * 100.0, -5.0, 5.0)
        
        # Calculate Entropy Regularization Gradient to prevent weight collapse
        probs = self.probs
        entropy = -np.sum(probs * np.log(probs + 1e-9))
        entropy_grad = -probs * (entropy + np.log(probs + 1e-9))
        entropy_beta = 0.01
        
        d_z = -scaled_reward * alignment.reshape(1, -1) - entropy_beta * entropy_grad
        
        dW = [None] * len(self.W)
        db = [None] * len(self.b)
        
        # Backpropagate gradients
        for i in reversed(range(len(self.W))):
            dW[i] = np.dot(self.a[i].T, d_z)
            db[i] = d_z
            
            if i > 0:
                d_a = np.dot(d_z, self.W[i].T)
                d_z = d_a * (self.z[i-1] > 0)  # ReLU gradient
                
        # Parameter updates
        self.t += 1
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

    def to_json(self):
        return json.dumps({
            "W": [w.tolist() for w in self.W],
            "b": [b.tolist() for b in self.b],
            "hidden_layers": self.hidden_layers,
            "dropout": self.dropout,
            "optimizer": self.optimizer
        })

    def from_json(self, json_str):
        data = json.loads(json_str)
        if "W" in data:
            self.W = [np.array(w) for w in data["W"]]
            self.b = [np.array(b) for b in data["b"]]
            self.hidden_layers = data.get("hidden_layers", 1)
            self.dropout = data.get("dropout", 0.0)
            self.optimizer = data.get("optimizer", "Adam")
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

        # Migrate old action_dim=7 weights to new action_dim=12
        if self.W[-1].shape[1] == 7:
            logging.info("[WEIGHT MIGRATION] Expanding action_dim 7→12 (adding 5 new strategies)")
            hidden_dim = self.W[-1].shape[0]
            new_w_out = np.random.randn(hidden_dim, 12) * np.sqrt(2.0 / hidden_dim)
            new_w_out[:, :7] = self.W[-1]
            self.W[-1] = new_w_out
            new_b_out = np.zeros((1, 12))
            new_b_out[:, :7] = self.b[-1]
            self.b[-1] = new_b_out
            
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
    def __init__(self, num_strategies=12, learning_rate=0.05, weight_floor=0.05, hidden_dim=12, hidden_layers=1, dropout=0.0, optimizer="Adam"):
        self.num_strategies = num_strategies
        self.weight_floor = weight_floor
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
        """Queries the Policy Network for optimal strategy weights given current state."""
        raw_weights = self.policy_net.forward(state)
        
        # Apply weight floor to ensure all strategies keep active search-space exploration
        n = len(raw_weights)
        if any(raw_weights < self.weight_floor):
            raw_weights = np.maximum(raw_weights, self.weight_floor)
            raw_weights = raw_weights / np.sum(raw_weights)
            
        return raw_weights.tolist()

    def learn_from_trade(self, state, strategy_signals, trade_direction, pnl_percent):
        # Ensure strategy_signals matches action_dim; pad/trim if needed
        target_len = self.policy_net.action_dim
        if len(strategy_signals) > target_len:
            strategy_signals = strategy_signals[:target_len]
        elif len(strategy_signals) < target_len:
            strategy_signals = list(strategy_signals) + [0.0] * (target_len - len(strategy_signals))
        """Performs backward propagation on the Policy Network using the trade PnL as reward."""
        # Ensure forward activations are cached for this state before backpropagation
        self.policy_net.forward(state)
        # The reward is the actual trade percentage profit/loss (e.g. +0.024 for +2.4%)
        self.policy_net.backward(state, strategy_signals, trade_direction, pnl_percent)
        
        # Return updated weights for the current state after learning
        return self.select_weights(state)
