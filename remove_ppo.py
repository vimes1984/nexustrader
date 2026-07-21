#!/usr/bin/env python3
"""
PPO REMOVAL: Delete broken discrete-action PPO layer.
PPO was bolted onto a continuous-action problem (12-dim weight vector).
int(action) always returns 0. Only strategy index 0 receives gradients.
Keep REINFORCE (learning_engine.py) — it's architecturally correct.
"""
import os, sys
os.chdir("/root/nexustrader")

changes = 0

# 1. Remove imports in main.py
with open("main.py") as f:
    m = f.read()

# Remove PPO import
old_import = "from ppo_agent import PPOAgent"
if old_import in m:
    m = m.replace(old_import + "\n", "")
    m = m.replace(old_import, "")
    changes += 1
    print("1. Removed PPO import from main.py")

# Remove replay buffer import  
old_rb = "from replay_buffer import PrioritizedReplayBuffer"
if old_rb in m:
    m = m.replace(old_rb + "\n", "")
    m = m.replace(old_rb, "")
    changes += 1
    print("2. Removed replay buffer import from main.py")

# Remove PPO agent creation in __init__
old_ppo_create = """        # Initialize PPO agents
        self.ppo_agents = {}
        for ticker in self.tickers:"""

if old_ppo_create in m:
    # Find end of block (next blank line or non-indented line)
    start = m.index(old_ppo_create)
    block_end = m.index("\n\n", start + 100)
    m = m[:start] + m[block_end:]
    changes += 1
    print("3. Removed PPO agent initialization block")
else:
    print("3. PPO creation block not found, searching...")
    for i, line in enumerate(m.split("\n"), 1):
        if "ppo_agent" in line.lower() and "import" not in line.lower():
            print(f"  Line {i}: {line.strip()}")
        if "replay_buffer" in line.lower() and "import" not in line.lower():
            print(f"  Line {i}: {line.strip()}")

# Remove PPO training calls
old_ppo_train = "ppo_agent.train_on_buffer"
if old_ppo_train in m:
    for i, line in enumerate(m.split("\n"), 1):
        if "ppo_agent" in line.lower() and "train" in line.lower():
            print(f"  PPO train line {i}: {line.strip()}")
    # Replace with pass
    m = m.replace(old_ppo_train, "pass  # PPO removed 2026-07-20; was " + old_ppo_train)
    changes += 1
    print("4. Disabled PPO training calls")

# Remove store_experience calls
old_store = "replay_buffers[ticker].add("
if old_store in m:
    m = m.replace(old_store, "pass  # PPO replay removed; was replay_buffers[ticker].add(")
    changes += 1
    print("5. Disabled replay buffer storage")

compile(m, "main.py", "exec")
with open("main.py", "w") as f:
    f.write(m)
print(f"main.py: {changes} changes, syntax OK")

# 2. Delete PPO files (keep as .bak for safety)
for f in ["ppo_agent.py", "replay_buffer.py"]:
    if os.path.exists(f):
        os.rename(f, f + ".bak")
        print(f"  Archived {f} → {f}.bak")
    else:
        print(f"  {f} not found — already removed?")

print("\nPPO REMOVAL COMPLETE")
print("REINFORCE (learning_engine.py) is untouched — it's the working RL system.")
