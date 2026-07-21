#!/usr/bin/env python3
"""Complete PPO removal from main.py: creation blocks, training calls, storage."""
import os, sys, re
os.chdir("/root/nexustrader")

with open("main.py") as f:
    m = f.read()
lines = m.split("\n")
changes = 0

# Remove all PPO/replay buffer related lines in __init__
remove_blocks = [
    ("        # Persistent PPO replay buffer storage\n", ""),
    ("        self.ppo_agents = {}", ""),
    ("        self.replay_buffers = {}", ""),
    ("        self.replay_capacity = 5000", ""),
]

for old, new in remove_blocks:
    if old in m:
        m = m.replace(old, new)
        changes += 1

# Remove the PPO agent creation + replay buffer restoration block
# Pattern: starts with "ppo_agent = PPOAgent" and ends before next section
ppo_start = None
ppo_end = None
for i, line in enumerate(m.split("\n")):
    if "ppo_agent = PPOAgent" in line:
        ppo_start = i
    if ppo_start and "replay_buffers[ticker] = PrioritizedExperienceReplay" in line:
        ppo_end = i + 1

if ppo_start and ppo_end:
    old_lines = m.split("\n")
    removed = old_lines[ppo_start:ppo_end]
    new_lines = old_lines[:ppo_start] + old_lines[ppo_end:]
    m = "\n".join(new_lines)
    changes += 1
    print(f"Removed PPO creation block ({ppo_end - ppo_start} lines)")
else:
    print("PPO creation block already removed or not found")

# Remove store_experience in on_trade_closed
old_store = "        replay = self.replay_buffers.get(ticker)"
if old_store in m:
    # Find the full store block
    start = m.index(old_store)
    end = m.index("\n\n", start + 100)
    m = m[:start] + m[end:]
    changes += 1
    print("Removed replay buffer storage from on_trade_closed")

# Remove PPO serialization
old_ser = "ppo_json = ppo.policy_net.to_json()"
if old_ser in m:
    for pattern in ["ppo_json = ppo.policy_net.to_json()", "database.save_setting(f\"ppo_agent_", "database.save_setting(f\"replay_buffer_"]:
        if pattern in m:
            line = [l for l in m.split("\n") if pattern in l]
            if line:
                m = m.replace(line[0], "")
            changes += 1
    print("Removed PPO serialization")

# Clean up empty lines
while "\n\n\n" in m:
    m = m.replace("\n\n\n", "\n\n")

compile(m, "main.py", "exec")
with open("main.py", "w") as f:
    f.write(m)
print(f"\nmain.py: {changes} additional PPO removals, syntax OK")
