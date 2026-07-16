import numpy as np
import json
import logging

class PolicyNetwork:
    """NumPy-based Policy Gradient Neural Network for dynamic strategy weight allocation.
    
    Inputs (State Dim = 6):
    - Market Regime (1.0 if Mean Reverting, 0.0 if Trending)
    - Mean Reversion Speed (theta)
    - Normalized RSI (-1.0 to 1.0)
    - Normalized MACD Histogram
    - Bollinger Band Position (-0.5 to 0.5)
    - Current Portfolio PnL Trend
    
    Outputs (Action Dim = 6):
    - Softmax probability distribution over the 6 strategy weights.
    """
    def __init__(self, state_dim=6, hidden_dim=12, action_dim=6, learning_rate=0.05):
        self.state_dim = state_dim
        self.hidden_dim = hidden_dim
        self.action_dim = action_dim
        self.lr = learning_rate
        
        # Xavier Initialization
        self.W1 = np.random.randn(state_dim, hidden_dim) * np.sqrt(2.0 / state_dim)
        self.b1 = np.zeros((1, hidden_dim))
        self.W2 = np.random.randn(hidden_dim, action_dim) * np.sqrt(2.0 / hidden_dim)
        self.b2 = np.zeros((1, action_dim))

    def softmax(self, x):
        e_x = np.exp(x - np.max(x, axis=-1, keepdims=True))
        return e_x / np.sum(e_x, axis=-1, keepdims=True)

    def forward(self, state):
        """Runs forward pass to allocate strategy weights based on market state."""
        self.state = np.array(state).reshape(1, -1)
        self.z1 = np.dot(self.state, self.W1) + self.b1
        self.h1 = np.maximum(0, self.z1)  # ReLU activation
        self.z2 = np.dot(self.h1, self.W2) + self.b2
        self.probs = self.softmax(self.z2)
        return self.probs[0]

    def backward(self, state, strategy_signals, trade_direction, reward):
        """Policy Gradient backward pass.
        
        If reward > 0 (profit), we perform gradient ascent to increase the probability
        of the strategies that aligned with the entry direction.
        If reward < 0 (loss), we perform gradient descent to penalize them.
        """
        self.state = np.array(state).reshape(1, -1)
        dir_val = 1.0 if trade_direction == "BUY" else -1.0
        
        # Calculate strategy alignment: signals are in [-1, 0, 1]
        alignment = np.array(strategy_signals) * dir_val
        
        # Policy gradient target: d_z2 = -reward * alignment (scaled)
        # Cap reward scale to prevent extreme weights blowing up
        scaled_reward = np.clip(reward * 100.0, -5.0, 5.0)
        d_z2 = -scaled_reward * alignment.reshape(1, -1)
        
        # Gradients for layer 2
        dW2 = np.dot(self.h1.T, d_z2)
        db2 = d_z2
        
        # Backprop to layer 1
        dh1 = np.dot(d_z2, self.W2.T)
        dz1 = dh1 * (self.z1 > 0)  # ReLU gradient
        
        dW1 = np.dot(self.state.T, dz1)
        db1 = dz1
        
        # Parameter updates
        self.W1 -= self.lr * dW1
        self.b1 -= self.lr * db1
        self.W2 -= self.lr * dW2
        self.b2 -= self.lr * db2

    def to_json(self):
        return json.dumps({
            "W1": self.W1.tolist(),
            "b1": self.b1.tolist(),
            "W2": self.W2.tolist(),
            "b2": self.b2.tolist()
        })

    def from_json(self, json_str):
        data = json.loads(json_str)
        self.W1 = np.array(data["W1"])
        self.b1 = np.array(data["b1"])
        self.W2 = np.array(data["W2"])
        self.b2 = np.array(data["b2"])


class LearningEngine:
    def __init__(self, num_strategies=6, learning_rate=0.05, weight_floor=0.05):
        self.num_strategies = num_strategies
        self.weight_floor = weight_floor
        self.policy_net = PolicyNetwork(
            state_dim=7, 
            hidden_dim=12, 
            action_dim=num_strategies, 
            learning_rate=learning_rate
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

        return [is_mr, theta, rsi, macd_norm, bb_pos, atr_ratio, win_trend]

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
        """Performs backward propagation on the Policy Network using the trade PnL as reward."""
        # The reward is the actual trade percentage profit/loss (e.g. +0.024 for +2.4%)
        self.policy_net.backward(state, strategy_signals, trade_direction, pnl_percent)
        
        # Return updated weights for the current state after learning
        return self.select_weights(state)
