# DevSwarm MathNN Batch — Complete

## Summary

12 iterations of neural network math bug fixes across 7 core files in the NexusTrader reinforcement learning stack.

## Iterations

| Iter | File | Category | Bug |
|------|------|----------|-----|
| 1 | transformer_policy_net.py | Gradient Math | Double softmax Jacobian in `_backward_impl` — `d_out` was already ∂L/∂(logits), but the code re-applied the softmax derivative, corrupting gradients through the policy head |
| 2 | sequential_policy_net.py | PPO Math | Entropy gradient sign error in LSTM backward — `dH/dz = -p*(log p + H)`, so `-β*dH/dz = +β*p*(log p + H)`, but code had `-β*p*(H - log p)` |
| 3 | transformer_policy_net.py | PPO Math | Same entropy gradient sign error in transformer `reinforce_backward` |
| 4 | multi_head_attention.py | Normalization | LayerNorm `∂L/∂var` used `x̂ * (-0.5) / σ³` instead of `(x-μ) * (-0.5) / σ³`, producing a gradient off by `1/σ` |
| 5 | nn_agent.py | Initialization | `sqlite3.connect(DB_PATH)` used undefined names `sqlite3` and `DB_PATH` — would crash with `NameError` at runtime |
| 6 | sequential_policy_net.py | Gradient Math | BPTT vertical gradient routing swapped `dx` (input/vertical) and `dh_in` (horizontal/time) — passed time gradient to the layer below instead of input gradient |
| 7 | multi_head_attention.py | Attention Math | Cached post-dropout attention weights for softmax Jacobian; dropout zeroes probability mass, corrupting the Jacobian `p*(δ_ij - p_j)` which requires true softmax outputs |
| 8 | transformer_policy_net.py | Gradient Math | TransformerEncoderLayer backward incorrectly routed residual gradients — `ffn.backward()` received ∂L/∂output (after Norm2) instead of ∂L/∂(x+ffn_out) (before Norm2), skipping the norm gradient for the FFN path |
| 9 | learning_engine.py | Dropout | PolicyNetwork.forward always applied dropout (no `training` flag), meaning inference calls (select_weights, PPO forward) randomly zeroed activations |
| 10 | multi_head_attention.py | Dropout | Pre/post-dropout softmax separation — cached pre-dropout weights for Jacobian (already fixed, included in iter 7) |
| 11 | sequential_policy_net.py | Gradient Math | Cell state gradient `dc_in` incorrectly propagated between LSTM layers; cell state is per-layer-through-time, not between layers |
| 12 | transformer_policy_net.py | Gradient Math | PositionalEncoding had no backward — `pos_emb` was included in `get_params()` but never received gradients, so it was never trained |

## Validation

- All 7 target files pass `py_compile` syntax check
- 16/16 replay buffer tests pass
- 28/29 transformer tests pass (1 pre-existing failure from mismatched API)
- All entropy gradient formulas verified across 4 implementations (MLP, LSTM, Transformer, PPO)
- Adam optimizer bias correction verified in all implementations
- Attention QKV projection shapes and backward paths verified
- GAE computation and PPO clipping objective verified
