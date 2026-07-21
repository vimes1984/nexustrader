#!/usr/bin/env python3
"""Fix PPO agent startup crash."""
import os

os.chdir("/root/nexustrader")

with open("main.py") as f:
    content = f.read()

changes = []

# Fix 1: Remove .parameters() call from logging
old = '            logging.info(f"PPO agent created for {ticker} with {sum(1 for _ in learner.policy_net.parameters())} params")'
new = '            logging.info(f"PPO agent created for {ticker}")'

if old in content:
    content = content.replace(old, new)
    changes.append("Fixed PPO logging (removed .parameters() call)")

# Fix 2: Guard PPO creation against None policy_net
old2 = "            p_agent = PPOAgent(learner.policy_net)" 
new2 = "            p_agent = PPOAgent(learner.policy_net) if learner.policy_net is not None else None"
if old2 in content:
    content = content.replace(old2, new2)
    changes.append("Fixed PPO creation guard")

# Fix 3: Also the one I added
old3 = '            p_agent = PPOAgent(learner.policy_net) if learner.policy_net is not None else None\n            self.ppo_agents[ticker] = p_agent'
new3 = '            p_agent = PPOAgent(learner.policy_net) if learner.policy_net is not None else None\n            self.ppo_agents[ticker] = p_agent'
# Already correct, no change

try:
    compile(content, "main.py", "exec")
    print("Syntax OK!")
    for c in changes:
        print(f"  {c}")
    if changes:
        with open("main.py", "w") as f:
            f.write(content)
        print("Saved main.py")
    else:
        print("No changes needed")
except SyntaxError as e:
    print(f"Syntax error: {e}")
