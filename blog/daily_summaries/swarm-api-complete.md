# DevSwarm API Batch — Completion Summary

## Overview
400-iteration batch for NexusTrader API endpoint fixes. Completed **50+ iterations** addressing:
- Data serialization consistency
- Security vulnerabilities
- Error handling gaps
- Missing API endpoints
- Field name normalization
- None/NaN guards

## Key Fixes By Area

### API Endpoint Fixes

| Iter | Issue | Fix |
|------|-------|-----|
| 1 | `/api/init` total_pnl unrounded | Round to 2 decimal places |
| 2 | `/api/init` missing total_pnl_pct | Added percentage field |
| 3 | `/api/status` missing winrate | Added winrate field |
| 4 | `/api/status` missing unrealized_pnl | Computes from active positions + current prices |
| 5 | `/api/trades` returns empty [] on exchange error | Merges exchange+DB, falls back to DB |
| 6 | `/api/trades` field normalization | All required fields with float types ensured |
| 7 | `/api/positions` stale current_price | Computes unrealized PnL from live prices |
| 8 | `/api/weights` sum normalization | Normalizes to ~1.0 |
| 9 | `/api/history` candle timestamps | Unix epoch seconds, OHLCV + BB fields |
| 10 | `/api/status` probability data | Added probability, EV, risk_reward, kelly, viable |
| 11 | CORS missing preflight handler | OPTIONS handler, headers on all endpoints |
| 12-16 | Public API list incomplete | Added missng read-only endpoints |
| 13 | `/api/system/broker_config` credential leak | Masked api_key/api_secret in GET |
| 14 | Silent exception swallows | Log errors instead of bare `pass` |
| 15 | `/api/system/risk_mode` always error | Fixed missing return in success branch |
| 17 | `/api/health` uptime always 0 | Set `orchestrator.start_time` in startup event |
| 18 | `/api/history` timestamp fallback to `time.time()` | Use pandas `Timestamp.timestamp()` |
| 19 | Bare `except Exception: pass` in `/api/init` | Log error messages |
| 20 | Missing `/api/probability` endpoint | Added with all probability engine fields |
| 21 | `/api/status` positions as raw dict | Converted to array format matching `/api/positions` |
| 22-23 | Path traversal in backup download | Basename sanitize, extension check, path prefix |
| 27 | `/api/positions` unrealized_pnl_pct *100 vs decimal | Standardized to decimal fraction (0.05=5%) |
| 28 | WS init winrate 0-1 vs HTTP 0-100 | Standardized to percentage (0-100) |
| 29 | `/api/init` missing today_pnl | Added today_pnl field |
| 30 | DB string->float type coercion | SQLite pnl/price/quantity as float |
| 31 | `last_evaluation` None guard | `hasattr` + truthy check |
| 32 | SMTP password leak via settings GET | Masked password in response |
| 33 | pnl_percent/pnl_pct field inconsistency | Populate both in trades response |
| 35 | Division by zero in PnL% calculation | Entry value guard |
| 36 | Position serialization robustness | Guard empty positions, abs quantity |
| 37 | get_equity() exception crash | Fallback to balance |
| 38 | WS init missing unrealized_pnl | Added aggregated UPL field |
| 39 | Weights history JSON decode failure | try/except guard |
| 40 | **CRITICAL: `last_evaluation` never stored** | Save evaluate_trade() result to engine |
| 41 | Missing DB table in portfolio history | Guard SQLite OperationalError |
| 52 | Exchange trades missing entry_time | Added timestamp to completed trades |

## Commits Made
```
1a087cd swarm-api iter 40: CRITICAL — store evaluate_trade() result as probability_engine.last_evaluation
88e70bd swarm-api iter 41: guard portfolio_history missing tables
be37a3e swarm-api iter 39: guard weights history JSON decode
88f9a16 swarm-api iter 38: add unrealized_pnl to WS init_state
1104b47 swarm-api iter 37: guard get_equity() exceptions
952aadd swarm-api iter 36: position serialization robustness
3d035aa swarm-api iter 35: division-by-zero guard
0fc71b3 swarm-api iter 33: normalize pnl_percent/pnl_pct
911c36f swarm-api iter 32: mask SMTP password
a89f4c5 swarm-api iter 31: last_evaluation None guard
6d0d9b1 swarm-api iter 30: DB numeric type coercion
546d8e0 swarm-api iter 29: add today_pnl to /api/init
ef435c5 swarm-api iter 28: standardize winrate to percentage
3716e64 swarm-api iter 27: fix unrealized_pnl_pct consistency
2bae0c7 swarm-api iter 26: test_broker GET->POST
f35c82a swarm-api iter 20: add /api/probability
55db744 swarm-api iter 18: fix timestamp parsing
1ab7912 swarm-api iter 17: fix uptime always 0
```

## Remaining Known Issues
- All major API endpoint issues resolved
- Risk: concurrent agent commits may overwrite some fixes
- Remainder of 400 iterations can focus on edge case hardening
