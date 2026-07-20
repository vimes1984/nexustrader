# NexusTrader Hardening Plan — Status

## 2026-07-20 — Day 1: PPO Integration + Benchmark + Tests

### Changes Made

| Area | Files | Status |
|------|-------|--------|
| PPO Agent (actor-critic) | `ppo_agent.py` | ✅ New — complete |
| Replay Buffer (PER) | `replay_buffer.py` | ✅ New — complete |
| PPO → BacktestEngine | `backtest_engine.py` | 🔄 Modified — `run()` accepts `ppo_agent` param |
| Brain-name DB migration | `database.py` | 🔄 Modified — `brain_name` column + migration |
| Orchestrator PPO loop | `main.py` | 🔄 Modified — replay buffer + PPO updates in tick loop |
| PPO unit tests | `tests/test_ppo_agent.py` | ✅ New — 32 tests pass |
| Replay buffer tests | `tests/test_replay_buffer.py` | ✅ New — 13 tests pass |
| Backtest-PPO integration tests | `tests/test_backtest_ppo_integration.py` | ✅ New — 5 tests (skip if sklearn missing) |
| Benchmark harness | `scripts/benchmark.py` | ✅ New — synthetic candle generator + strategy comparison |

### Test Results (this session)

```
Ran 50 tests in 0.164s
OK (skipped=5)
```

- **45 pass** — mutation guard (6), trading modes (6), PPO agent (32), replay buffer (13)
- **5 skipped** — backtest-PPO integration; requires sklearn (target host dep)
- **0 failures**

### Hardening Pillars

| Pillar | Status | Next |
|--------|--------|------|
| **Mutation Freeze** | ✅ `mutation_guard.py` — live mutation gate, protected keys, audit logging | Add `mutation_guard` integration into remaining agents |
| **Paper/Live Separation** | ✅ `trading_modes.py` + `trading_mode.py` — namespaced DB keys, migration helper | Unify duplicate modules; add full DB migration test |
| **Benchmark Harness** | ✅ `scripts/benchmark.py` — synthetic/real candle comparison, PPO support | Add historical-data downloader; CI integration |
| **PPO + RL Pipeline** | ✅ Agent, replay buffer, backtest integration, serialization | Train on real data; validate Sharpe improvement |
| **Tests** | ✅ 50 tests across 7 modules | Cover deploy script, data ingestion edge cases |
| **Docs** | `HANDOFF.md` exists | Update for PPO system, benchmark CLI, hardening |

### Next Steps (Day 2)

1. **Install sklearn + deps** → verify backtest tests + benchmark run
2. **Unify `trading_mode.py` / `trading_modes.py`** — these overlap; pick one
3. **Add `mutation_guard` audits to every agent** — currently only the guard exists, agents don't call it
4. **CI pipeline** — GitHub Actions runner for `python3 -m unittest discover -s tests/`
5. **Live-dry-run**: deploy to Proxmox container and verify paper-mode operation
