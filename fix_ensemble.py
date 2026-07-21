#!/usr/bin/env python3
"""Fix correlation blindness and OU process in StrategyEnsemble."""
import os, sys
os.chdir("/root/nexustrader")

with open("strategy_engine.py") as f:
    content = f.read()

changes = 0

# FIX 1: Add signal history for correlation tracking
old_init = "        # Performance tracker: each strategy's recent directional accuracy\n        self.strategy_performance = defaultdict(list)"
new_init = """        # Performance tracker: each strategy's recent directional accuracy
        self.strategy_performance = defaultdict(list)
        
        # Signal history for correlation tracking (last 50 signals per strategy)
        self.signal_history = [[] for _ in range(len(self.strategies))]
        
        # Correlation penalty scale (0.0 = off, 1.0 = full penalty)
        self.correlation_penalty = 0.35"""
if old_init in content:
    content = content.replace(old_init, new_init)
    changes += 1
    print("FIX 1: Added signal_history + correlation_penalty")

# FIX 2: Store signal history
old_track = "        signals = np.array(signals)\n        \n        # Compute active weights starting from policy network weights\n        active_weights = np.array(self.weights)"
new_track = """        signals = np.array(signals)
        
        # Track signal history for correlation analysis
        for i, sig in enumerate(signals):
            self.signal_history[i].append(float(sig))
            if len(self.signal_history[i]) > 50:
                self.signal_history[i].pop(0)
        
        # Compute active weights starting from policy network weights
        active_weights = np.array(self.weights)"""
if old_track in content:
    content = content.replace(old_track, new_track)
    changes += 1
    print("FIX 2: Signal history tracking wired in")

# FIX 3: Correlation penalty
old_norm = "        # Layer 2: Recent Performance Biasing"
new_norm = """        # Layer 2: Signal Correlation Penalty
        # Reduces weight on correlated strategies to prevent false consensus
        if self.correlation_penalty > 0 and min(len(h) for h in self.signal_history) >= 10:
            hist_matrix = np.array([h[-20:] for h in self.signal_history])
            try:
                corr_matrix = np.corrcoef(hist_matrix)
                for i in range(len(self.strategies)):
                    correlated_count = 0
                    for j in range(len(self.strategies)):
                        if i != j and not np.isnan(corr_matrix[i][j]) and corr_matrix[i][j] > 0.6:
                            correlated_count += 1
                    if correlated_count > 0:
                        penalty = 1.0 - self.correlation_penalty * min(correlated_count, 5) / 5.0
                        active_weights[i] *= max(penalty, 0.3)
            except Exception:
                pass
        
        # Layer 3: Recent Performance Biasing"""
if old_norm in content:
    content = content.replace(old_norm, new_norm)
    changes += 1
    print("FIX 3: Correlation penalty added between OU and performance layers")

# FIX 4: OU process on log returns
old_ou = """        if len(self.price_history) >= 20:
            theta, mu, is_mr = estimate_ou_process(self.price_history)"""
new_ou = """        if len(self.price_history) >= 20:
            import math
            log_prices = [math.log(p) for p in self.price_history if p > 0]
            if len(log_prices) >= 20:
                theta, mu, is_mr = estimate_ou_process(log_prices)
            else:
                theta, mu, is_mr = 0.0, 0.0, False"""
if old_ou in content:
    content = content.replace(old_ou, new_ou)
    changes += 1
    print("FIX 4: OU process now uses log prices (stationary)")

try:
    compile(content, "strategy_engine.py", "exec")
    with open("strategy_engine.py", "w") as f:
        f.write(content)
    print(f"\nApplied {changes} fixes to strategy_engine.py - syntax OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}")
    sys.exit(1)
