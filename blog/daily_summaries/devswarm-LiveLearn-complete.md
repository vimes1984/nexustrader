# DevSwarm LiveLearn — Complete Summary

## Overview

32 iterations improving the online learning pipeline for NexusTrader's neural network-based trading system. Focused on ensuring the model actually learns from its 694+ closed trades, with robust monitoring, verification, and safety guards.

## Files Modified

### `learning_engine.py` (15 iterations)
- **Iter 1**: ReplayBuffer deduplication via state fingerprints + FIFO eviction
- **Iter 3**: Learning rate scheduling — linear decay from initial_lr to min_lr
- **Iter 9**: Online/offline gradient consistency check (cosine similarity)
- **Iter 10**: Loss verification uses `training=False` (deterministic)
- **Iter 11**: Batch update revert if loss increases
- **Iter 12**: Persist LR scheduler state (total_learning_steps) across restarts
- **Iter 16**: Sync `action_dim` after weight migration
- **Iter 18**: Gradient norm monitoring (exploding/vanishing detection)
- **Iter 19**: Duplicate experience logging
- **Iter 21**: Fix weight floor redistribution (preserve policy ordering)
- **Iter 22**: Degenerate state vector detection (NaN/Inf/all-zero)
- **Iter 26**: Learning rate warmup (20-step linear ramp)
- **Iter 27**: Early gradient diagnostics (first 5 updates)
- **Iter 28**: Forward pass NaN/Inf guard (uniform fallback)
- **Iter 30**: Network config validation (hidden_dim, hidden_layers, lr)
- **Iter 31**: Fix signal padding mutation bug
- **Iter 32**: Advantage clipping detection

### `main.py` (11 iterations)
- **Iter 2**: Rolling 50-trade win rate tracking per ticker
- **Iter 4**: Catastrophic forgetting guard — revert weights on >20% WR drop
- **Iter 6**: Minimum data for learning (10 trades, both wins and losses)
- **Iter 8**: Trade replay on restart — catch-up learning pass
- **Iter 13**: Fix PPO action — use argmax instead of scalar mean
- **Iter 14**: Replay buffer capacity logging at 80%+
- **Iter 15**: PPO gradient norm logging
- **Iter 17**: Cumulative PnL tracking per ticker
- **Iter 20**: Stale brain detection (0 training steps despite 10+ trades)
- **Iter 23**: Learning frequency tracking (steps-to-trades ratio)
- **Iter 24**: Weight divergence monitoring (max/min ratio)
- **Iter 25**: Seed new brains from active brain weights

### `probability_engine.py` (1 iteration)
- **Iter 5**: Cold start curriculum — 25%→100% position size over first 100 trades

### `execution_engine.py` (1 iteration)
- **Iter 7**: Learning disabled detection — CRITICAL log if callback is None

### `ppo_agent.py` (2 iterations)
- **Iter 15**: KL/entropy running window + gradient norm tracking
- **Iter 29**: Critic MSE divergence monitoring

### `replay_buffer.py` (1 iteration)
- **Iter 14**: Overflow detection and warning logging

## Key Bug Fixes

1. **PPO action was always 0**: `sum(action_vec) / len(action_vec)` cast to `int(0.01) = 0`, so PPO trained on action 0 every time. Fixed to use `argmax(abs(signals))` for discrete action index.

2. **Weight floor destroyed policy**: When all weights were below `weight_floor`, clamping them to floor and renormalizing produced a uniform distribution regardless of the policy's signal. Fixed by proportionally subtracting excess from above-floor weights.

3. **Learn rate never decayed**: No scheduling existed. Added linear decay from `initial_lr` to `min_lr` over `lr_decay_steps` gradient updates.

4. **No catastrophic forgetting protection**: Added pre-update weight snapshot + rolling WR monitoring. If WR drops >20%, weights are reverted.

5. **Cold start overbetting**: First 100 trades now use a linear ramp from 25% to 100% position size.

6. **Gradient direction validation**: Added cosine similarity check between online (single-trade) and offline (minibatch) gradients. Warns when they disagree.

7. **Replay buffer overflow**: Added capacity monitoring at 80%+ and 100%.

## Monitoring Added

| Metric | Location | Trigger |
|--------|----------|---------|
| Loss increase | `backward()` | >1% after update |
| WR decline | `on_trade_closed` | >15% rolling |
| Gradient norm | `_apply_gradients` | >10 (exploding), <1e-8 (vanishing) |
| KL divergence | PPO update | Running avg > 0.05 |
| Entropy collapse | PPO update | Running avg < 0.01 |
| Critic divergence | `update_batch` | MSE >50% increase |
| Weight divergence | `on_trade_closed` | max/min ratio >10 |
| Learning disabled | ExecutionEngine | callback is None |
| Stale brain | `on_trade_closed` | 0 steps with 10+ trades |
| Degenerate state | `get_state_vector` | NaN/Inf/all-zero |

## Summary

The bot has 694+ closed trades but was not effectively learning from them because:
1. PPO action was always index 0 (bug in action encoding)
2. No loss verification after gradient updates
3. No LR scheduling — updates remained aggressive regardless of experience count
4. No rolling performance tracking to detect if learning helps or hurts
5. No cold-start safety for early trades

All 10 task requirements were addressed across 32 focused iterations.
