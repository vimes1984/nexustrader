# PPO/RL Deep-Dive Audit
**Date:** 2026-07-20  
**Auditor:** OpenClaw Subagent  
**Target:** NexusTrader on 192.168.0.144 (`/root/nexustrader/`)

---

## Executive Summary

There are **6 bugs** in the PPO implementation, **2 of which are fatal** (the agent can never learn). The PPO layer is fundamentally misaligned with the problem it's trying to solve. It was bolted on top of an existing REINFORCE-based system without adapting the action-space representation.

**Bottom line:** The PPO layer is non-functional as-is. `int(action)` always returns 0, so the agent's policy gradient only updates strategy index 0. The entire PPO plumbing should be either removed (reverting to the original REINFORCE) or replaced with a correctly designed discrete-action PPO.

---

## Bug 1: `int(action)` Always Returns 0 — FATAL [CRITICAL]

### Location
- **`main.py` line 368** — action stored in replay buffer
- **`ppo_agent.py` lines 342, 368, 374, 465** — action consumed

### Root Cause

In `main.py`, the "action" stored in the replay buffer is computed as:

```python
# main.py:367-368
action_vec = strategy_signals if strategy_signals else [0.0] * len(ensemble.strategies)
action_scalar = sum(action_vec) / (len(action_vec) + 1e-9)
```

`action_scalar` is the **mean of 12 strategy signals**, each in roughly [-1, 1]. So `action_scalar` is a continuous float in **approximately [-1, 1]**.

When the PPO update reads it back:

```python
# ppo_agent.py:342  (during update)
new_lp = np.log(max(probs[int(action)], 1e-12))

# ppo_agent.py:368  (gradient computation)
grad_scale = -adv * ratio / (probs[int(action)] + 1e-12)

# ppo_agent.py:374  (gradient placement)
d_z_actor[0, int(action)] = grad_scale
```

`int(action_scalar)` for any value in [-1, 1] always truncates to **0**:
- `int(0.34)` → `0`
- `int(-0.12)` → `0`
- `int(0.99)` → `0`

### Consequences
1. **Only strategy index 0** (EMACrossoverStrategy) ever receives gradient updates.
2. The log-prob `new_lp` is always `log(probs[0])`, so the PPO ratio is computed against strategy 0's probability regardless of which strategies actually contributed to the trade.
3. The entire remaining 11 strategies drift randomly due to weight decay and entropy noise but never receive meaningful learning signals.
4. This is equivalent to a policy network producing 12 outputs but only the first being trained — the agent learns nothing about the other 11 strategies.

### Fix — The PPO approach is fundamentally misaligned

The PPO code treats the action as a **discrete index** into the strategy probability distribution. But the actual problem is **continuous**: the agent must output a probability distribution over 12 strategies (a 12-dimensional simplex), and the "action" is the entire weight vector, not a single index.

PPO (discrete) → expects scalar action index `a ∈ {0, 1, ..., 11}`, `π(a|s)` is a categorical.  
This problem → needs continuous action `w ∈ Δ¹¹` (11-simplex), or needs reformulation as discrete choice.

Two possible fixes:

**Option A: Reformulate as discrete-action PPO (recommended)**
- When a trade opens, the "action" is the index of the strategy that contributed the most to the signal:
  ```python
  action_idx = int(np.argmax(strategy_signals))
  replay.add(state, action_idx, pnl_percent, next_state, done=True, error=abs(pnl_percent))
  ```
- Then PPO learns which strategy to "trust" the most in each market state.
- Loss: discards the nuanced weight distribution information.

**Option B: Continuous PPO / remove PPO entirely (cleanest)**
- The existing REINFORCE (`PolicyNetwork.backward` + replay buffer in `learning_engine.py`) already handles the continuous weight distribution correctly.
- The PPO layer was an incomplete second attempt. **Remove it** and fix the original REINFORCE's replay-buffer training interval.
- The original `PolicyNetwork` with `_compute_gradients` already computes proper policy gradients for the full action distribution.

---

## Bug 2: GAE on Randomly-Ordered Mini-Batch — CRITICAL (partially masked)

### Location
- **`ppo_agent.py` lines 273-289** — `compute_gae`  
- **`ppo_agent.py` lines 432-470** — `train_on_buffer`  

### Root Cause

`train_on_buffer` samples a batch from the **Prioritized Experience Replay** buffer:

```python
# ppo_agent.py:445-446
states, actions, rewards, next_states, dones, indices, _ = \
    replay_buffer.sample(batch_size)
```

`replay_buffer.sample()` (in `replay_buffer.py:68`) uses `np.random.choice` with probability weights — transitions are **randomly ordered**, not chronologically sequential.

Then `compute_gae` processes them **as if they were a sequential trajectory**:

```python
# ppo_agent.py:279-287
T = len(rewards)
advantages = np.zeros(T, dtype=np.float64)
gae = 0.0
for t in reversed(range(T)):
    delta = (rewards[t] + self.gamma * values[t + 1] * (1 - dones[t]) - values[t])
    gae = delta + self.gamma * self.lam * (1 - dones[t]) * gae
    advantages[t] = gae
```

`rewards[t]` and `rewards[t+1]` have **no temporal relationship** — they're from completely different trades. The GAE lambda-weighted bootstrapping is computing nonsense.

### Why It's "Partially Masked"

All experiences in the buffer are stored with `done=True` (see Bug 3). This means `(1 - dones[t]) = 0` for every transition, collapsing the GAE formula to:

```
delta = reward[t] - values[t]
gae = delta
advantages = reward[t] - values[t]
```

This is just **TD-0 per sample**, independent of ordering. So the ordering bug is 100% masked and GAE provides zero benefit over simple TD-0 advantage estimation. The `gamma` and `lam` hyperparameters are effectively ignored.

### Fix

GAE requires sequential trajectory data. Either:
1. Store full episode trajectories and compute GAE on them, not on randomly-sampled transitions.
2. Remove GAE entirely and use simple per-sample TD-error as advantage.
3. Since all experiences are `done=True`, direct `reward[t] - values[t]` is the only valid advantage (which is what collapses to anyway).

---

## Bug 3: All Experiences Marked as Terminal (`done=True`) — MAJOR

### Location
- **`main.py` line 371**

```python
replay.add(state, action_scalar, pnl_percent, next_state, done=True, error=abs(pnl_percent))
```

### Problem

Every experience is stored as a terminal transition. This has several consequences:

1. **No temporal bootstrapping:** `return = advantage + value = (reward - value) + value = reward`. The return for every sample is just the raw PnL — no discounted future reward is incorporated.
2. **`gamma` is useless:** `gamma * (1 - done) = 0` for all transitions.
3. **`lam` (GAE lambda) is useless:** Same reason — the GAE bootstrap chain is always cut immediately.
4. **Multi-step credit assignment impossible:** The agent can never learn that an action leading to a small immediate loss might create a valuable future opportunity.

### Fix

Change `done=True` to reflect whether the trade was the *last* in a logical sequence, or remove the PPO layer entirely since this level of simplification provides no benefit over the original REINFORCE.

---

## Bug 4: Missing Softmax Jacobian in PPO Actor Backprop — CRITICAL

### Location
- **`ppo_agent.py` lines 365-393** — actor gradient computation

### Root Cause

The PPO `update` method computes:

```python
# ppo_agent.py:374
d_z_actor[0, int(action)] = grad_scale
```

Where `grad_scale = dL/d(probs[action])` — the gradient of the PPO-clip loss w.r.t. the **post-softmax probability** of the action.

Then the backprop loop treats this as the gradient w.r.t. the **pre-softmax logits**:

```python
# ppo_agent.py:381-385
for j in reversed(range(len(self.policy_net.W))):
    if j == len(self.policy_net.W) - 1:
        d_z = d_z_actor            # ← TREATED AS dL/dz_out (logits)
    else:
        ...
    dW_acc[j] += np.dot(self.policy_net.a[j].T, d_z)
```

The softmax function connects logits (z) to probabilities (p) via the Jacobian:

```
∂p_k / ∂z_j = p_k * (δ_{kj} - p_j)
```

The code **skips this entirely** and treats `dL/dp` as if it were `dL/dz`. For a single-element dependency (loss only depends on `p_a`), the correct gradient is:

```
dL/dz_j = dL/dp_a * p_a * (δ_{ja} - p_j)
```

This is non-zero for ALL j, not just j=a. By only setting the `[0, action]` entry, the code misses the `-p_j` component that distributes gradient to all other logits.

### Same Bug in Original REINFORCE

The `PolicyNetwork._compute_gradients` (`learning_engine.py:159-180`) has the identical issue:

```python
# learning_engine.py:173
d_z = -scaled_reward * alignment.reshape(1, -1) - entropy_beta * entropy_grad
```

This is also treated as `dL/dz` (logits) but computed as `dL/dp` (probabilities). The original REINFORCE got "lucky" because the alignment vector is dense (all strategies get some gradient), and the entropy gradient already includes the softmax-dependent structure.

### Impact on PPO

The missing softmax Jacobian means:
- The gradient at logit `action` is approximately correct in sign/magnitude
- But the gradient at **all other logits** (j ≠ action) is **zero** — they receive no gradient from the PPO-clip term
- Only the entropy term provides gradient to other logits
- This slows learning dramatically and biases the network toward outputting degenerate distributions

### Fix

Replace the manual backprop with the correct softmax-aware gradient:

```python
# Correct gradient through softmax for PPO-clip loss
probs = self.policy_net.probs[0]  # cached from forward pass
a = int(action)

# dL/dz_j = sum_k dL/dp_k * p_k * (delta_{kj} - p_j)
# Since only dL/dp_a is non-zero:
# dL/dz_j = dL/dp_a * p_a * (delta_{ja} - p_j)

dl_dp_a = -adv * ratio / (probs[a] + 1e-12) if surr1 < surr2 else 0.0
d_z_actor = np.zeros((1, self.policy_net.action_dim), dtype=np.float64)
for j in range(self.policy_net.action_dim):
    d_z_actor[0, j] = dl_dp_a * probs[a] * ((1.0 if j == a else 0.0) - probs[j])
# + entropy gradient (which IS computed correctly w.r.t. logits already)
d_z_actor -= self.entropy_coef * (probs - entropy_grad)  # simplified entropy-logit gradient
```

---

## Bug 5: `value_coef` Never Applied — MINOR

### Location
- **`ppo_agent.py` line 405**

```python
# --- Critic (value) update ---
self.critic.update_batch(states, returns)
```

### Problem

The `self.value_coef = 0.5` parameter is stored but never used. In standard PPO, the total loss is:

```
L_total = L_actor + value_coef * L_value + entropy_coef * L_entropy
```

The critic is trained on full MSE (gradient `2 * (V - R)`), not scaled by `value_coef`. The `value_coef` only makes sense if the actor and critic share layers, which they don't here (separate `PolicyNetwork` and `PPOCritic`).

### Impact

None — since actor and critic are separate networks, the `value_coef` is irrelevant. The critic learning rate absorbs the MSE gradient scale. Remove the unused field.

---

## Bug 6: Original REINFORCE Entropy Gradient Error — MINOR

### Location
- **`learning_engine.py` lines 162, 173-174**

```python
entropy = -np.sum(probs * np.log(probs + 1e-9))
entropy_grad = -probs * (entropy + np.log(probs + 1e-9))
```

### Problem

The entropy gradient is incorrect. Mathematically:

```
H(p) = -Σ p_j * log(p_j)
∂H/∂p_k = -(log(p_k) + 1)
```

But the code computes:
```python
entropy_grad = -probs * (entropy + np.log(probs + 1e-9))
```

This computes `-p_k * (H + log(p_k))` instead of `-(log(p_k) + 1)`. The `entropy` term is wrong — it multiplies the entropy value into every element.

### Fix

```python
entropy_grad = -(np.log(np.clip(probs, 1e-12, 1.0)) + 1.0)
```

Note: The PPO agent's entropy gradient in `ppo_agent.py:377` uses a different expression:

```python
entropy_grad = -probs * (np.log(np.clip(probs, 1e-12, 1.0)) + 1.0)
```

This is also wrong (same mathematical error). Should be:

```python
entropy_grad = -(np.log(np.clip(probs, 1e-12, 1.0)) + 1.0)
```

---

## Summary Table

| # | Bug | File:Line | Severity | Status |
|---|---|---|---|---|
| 1 | `int(action)` always 0 — action is continuous float | `main.py:368`, `ppo_agent.py:342,368,374,465` | **FATAL** | Unfixable without redesign |
| 2 | GAE on random-order mini-batch | `ppo_agent.py:273-289` vs `445` | **CRITICAL** | Masked by Bug 3 |
| 3 | All experiences `done=True` | `main.py:371` | **MAJOR** | Fixable |
| 4 | Missing softmax Jacobian in PPO backprop | `ppo_agent.py:374-385` | **CRITICAL** | Fixable |
| 5 | `value_coef` unused | `ppo_agent.py:405` | MINOR | Cosmetic |
| 6 | REINFORCE entropy gradient wrong | `learning_engine.py:173-174` | MINOR | Fixable |

---

## Verdict: Can PPO Work After Fixes?

**No.** Bug 1 is a fundamental design misalignment:

- **The problem is continuous:** The agent must output a **12-dimensional softmax weight vector** over strategies.
- **The PPO code assumes discrete:** It expects a single discrete action index `a ∈ {0,...,11}`.

Fixing Bug 1 by converting the action to an index (`argmax` of strategy signals) would work, but it discards the rich weight-distribution information that the original REINFORCE system preserves. You'd be learning "which single strategy to bet on" instead of "how to blend all 12 strategies."

## Recommendation

**Remove the PPO layer entirely and fix the original REINFORCE implementation.**

The original `LearningEngine` + `PolicyNetwork` in `learning_engine.py` is:
- Architecturally correct for this problem (outputs a full strategy distribution)
- Already includes experience replay, baseline subtraction, and entropy regularization
- Integrated cleanly into `on_trade_closed` and `select_weights`

### What to remove

1. **`ppo_agent.py`** — delete the entire file
2. **`main.py` lines 355-410** — the PPO/replay buffer section inside `on_trade_closed`
3. **`main.py` lines 82-93** — `self.replay_buffers`, `self.ppo_agents`, and related config
4. **`main.py` lines 161-185** — PPO agent creation and replay buffer restoration in `init_ticker`
5. **`from ppo_agent import PPOAgent`** at `main.py:33`
6. **`from replay_buffer import PrioritizedExperienceReplay`** at `main.py:32` (if unused elsewhere)

### What to keep/improve

The existing REINFORCE in `learning_engine.py` has a working `backward()` method that:
- Stores experiences in its own `ReplayBuffer`
- Periodically trains from mini-batch replay
- Computes policy gradients with baseline subtraction
- Applies entropy regularization

**Two improvements for the original REINFORCE:**

1. **Fix the entropy gradient** (Bug 6 above — `learning_engine.py:173-174`)
2. **Increase the replay buffer capacity** from hardcoded 200 to match the DB-configured `replay_capacity` (e.g., 5000)

---

## Fixed Code Snippets

### Fix for PPO Action (if keeping PPO with discrete actions)

In `main.py:367-368`, replace:

```python
action_vec = strategy_signals if strategy_signals else [0.0] * len(ensemble.strategies)
action_scalar = sum(action_vec) / (len(action_vec) + 1e-9)
```

With:

```python
# The "action" is the index of the most confident strategy signal
action_vec = strategy_signals if strategy_signals else [0.0] * len(ensemble.strategies)
action_idx = int(np.argmax(action_vec) if np.any(action_vec) else 0)
```

And in `ppo_agent.py:342,368,374,465`, keep `int(action)` — it now correctly indexes into strategies.

### Fix for Softmax Jacobian in PPO

In `ppo_agent.py`, replace lines 360-393 with:

```python
# Correct gradient through softmax for PPO-clip + entropy
probs_flat = self.policy_net.probs[0]  # (action_dim,) post-softmax
a = int(action)

# Gradient of PPO-clip loss w.r.t. logits
dl_dpa = 0.0
if surr1 < surr2:
    dl_dpa = -adv * ratio / (probs_flat[a] + 1e-12)

d_z_actor = np.zeros((1, self.policy_net.action_dim), dtype=np.float64)
for j in range(self.policy_net.action_dim):
    # dL/dz_j = dL/dp_a * p_a * (delta_{ja} - p_j)
    d_z_actor[0, j] = dl_dpa * probs_flat[a] * ((1.0 if j == a else 0.0) - probs_flat[j])

# Entropy gradient w.r.t. logits (correct)
# H = -Σ p_j * log(p_j)
# dH/dz_j = -p_j * (log(p_j) + 1) + p_j * (Σ p_k * (log(p_k) + 1))
log_probs = np.log(np.clip(probs_flat, 1e-12, 1.0))
entropy_grad_logits = -probs_flat * (log_probs + 1.0)
entropy_grad_logits += probs_flat * np.sum(probs_flat * (log_probs + 1.0))
d_z_actor -= self.entropy_coef * entropy_grad_logits.reshape(1, -1)

# Backprop through policy_net (unchanged below)
for j in reversed(range(len(self.policy_net.W))):
    ...
```

### Fix for Entropy Gradient in REINFORCE

In `learning_engine.py:173-174`, replace:

```python
entropy = -np.sum(probs * np.log(probs + 1e-9))
entropy_grad = -probs * (entropy + np.log(probs + 1e-9))
```

With:

```python
entropy_grad = -(np.log(np.clip(probs, 1e-12, 1.0)) + 1.0)
```

### Fix for GAE (if keeping PPO)

Since all experiences are terminal (`done=True`), simplify `compute_gae` and `train_on_buffer` to use plain TD-0 advantage:

In `ppo_agent.py`, replace `compute_gae` call with:

```python
# Simple TD-0 advantage (all transitions are terminal)
advantages = rewards - values[:-1]
returns = rewards  # = advantages + values[:-1]
```

---

## Appendix: Key Line Numbers

| File | Lines | Purpose |
|---|---|---|
| `main.py` | 367-371 | Action storage in replay buffer |
| `main.py` | 383-419 | PPO training trigger logic |
| `ppo_agent.py` | 150-172 | PPOAgent constructor |
| `ppo_agent.py` | 273-289 | GAE computation |
| `ppo_agent.py` | 298-425 | PPO `update` method |
| `ppo_agent.py` | 340-345 | `int(action)` in log-prob computation |
| `ppo_agent.py` | 365-374 | `int(action)` in gradient computation |
| `ppo_agent.py` | 432-500 | `train_on_buffer` |
| `ppo_agent.py` | 442-447 | Random batch sample |
| `ppo_agent.py` | 452-459 | GAE call on random batch |
| `ppo_agent.py` | 461-465 | `int(actions[i])` in log-prob |
| `learning_engine.py` | 159-180 | `_compute_gradients` with entropy bug |
| `learning_engine.py` | 185-215 | `backward` method |
| `replay_buffer.py` | 44-58 | `add` method |
| `replay_buffer.py` | 68-100 | `sample` method |
