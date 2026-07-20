# NexusTrader Asset Allocator — Daily Summary
**Date:** 2026-07-20 21:13 UTC  
**Period:** Last 100 trades (all-time: 10 trades total)  
**Exchange:** Kraken (Live)

---

## Market Context
Crypto markets remain volatile. All 10 recorded trades exited via Stop Loss with no Take Profit hits, suggesting current market conditions favor tighter TP targets.

## Performance Summary

| Metric | Value |
|---|---|
| Total Trades | 10 |
| Wins | 1 |
| Losses | 9 |
| Win Rate | 10% |
| Total PnL | -$0.2428 |
| Best Performer | DOT-USD (+$0.0070, +0.15%) |
| Worst Performer | ADA-USD (-$0.0576, -0.87% avg) |
| TP Hits | 0 / 10 |
| SL Hits | 10 / 10 |

## Per-Asset Breakdown

| Ticker | Trades | Wins | Losses | Win Rate | Total PnL | Avg PnL% | Status |
|---|---|---|---|---|---|---|---|
| ADA-USD | 2 | 0 | 2 | 0% | -$0.0576 | -0.87% | ⚠️ Poor |
| BTC-USD | 1 | 0 | 1 | 0% | -$0.0012 | -0.03% | ✅ Neutral |
| DOGE-USD | 2 | 0 | 2 | 0% | -$0.0549 | -0.59% | ⚠️ Poor |
| DOT-USD | 2 | 1 | 1 | 50% | -$0.0366 | -0.39% | ✅ Best WR |
| ETH-USD | 2 | 0 | 2 | 0% | -$0.0507 | -1.30% | 🔴 Worst |
| LINK-USD | 1 | 0 | 1 | 0% | -$0.0417 | -0.85% | ⚠️ Poor |
| LTC-USD | 0 | 0 | 0 | N/A | $0.00 | N/A | 📡 No data |
| SOL-USD | 0 | 0 | 0 | N/A | $0.00 | N/A | 📡 No data |
| XRP-USD | 0 | 0 | 0 | N/A | $0.00 | N/A | 📡 No data |
| SUI-USD | 0 | 0 | 0 | N/A | $0.00 | N/A | 📡 No data |

## Analysis

**Key finding:** Only 1 of 10 trades was profitable. All exits triggered Stop Loss — TP never got hit. This pattern indicates either:
- TP multipliers (2.5:1) were too ambitious for current market conditions
- Entry signals were being placed in choppy/sideways conditions

DOT-USD was the sole asset with a positive trade (50% WR) and has been **inactive**. It should be reactivated.

## Adjustments Applied

### Activation Changes
| Ticker | Before | After | Rationale |
|---|---|---|---|
| DOT-USD | Inactive | **Active** | Only asset with winning trade (50% WR) |

### TP/SL Multipliers (all active assets)
| Parameter | Before | After | Rationale |
|---|---|---|---|
| TP Multiplier | 2.5 | **2.0** | 0 TP hits in 10 trades — target too far |
| SL Multiplier | 1.5 | **1.5** | No change — functioning as designed |

### Kelly Ceiling Adjustments
| Ticker | Before | After | Rationale |
|---|---|---|---|
| ADA-USD | 0.10 | **0.05** | 0% WR, -0.87% avg loss |
| BTC-USD | 0.20 | **0.15** | Only 1 trade, negligible loss |
| DOGE-USD | 0.10 | **0.05** | 0% WR, -0.59% avg loss |
| DOT-USD | 0.10 | **0.10** | Reactivated, keep moderate sizing |
| ETH-USD | 0.15 | **0.05** | Worst performer (-1.30% avg) |
| LINK-USD | 0.15 | **0.08** | 0% WR, -0.85% avg loss |
| LTC-USD | 0.10 | **0.08** | No trades yet — conservative start |
| SOL-USD | 0.10 | **0.10** | No data — no change |
| XRP-USD | 0.10 | **0.10** | No data — no change |
| SUI-USD | 0.10 | **0.10** | No data — no change |

## Result JSON

```json
{
  "asset_adjustments": {
    "ADA-USD": {"is_active": true, "tp_multiplier": 2.0, "sl_multiplier": 1.5, "kelly_ceiling": 0.05},
    "AVAX-USD": {"is_active": false, "tp_multiplier": 2.5, "sl_multiplier": 1.5, "kelly_ceiling": 0.10},
    "BTC-USD": {"is_active": true, "tp_multiplier": 2.0, "sl_multiplier": 1.5, "kelly_ceiling": 0.15},
    "DOGE-USD": {"is_active": true, "tp_multiplier": 2.0, "sl_multiplier": 1.5, "kelly_ceiling": 0.05},
    "DOT-USD": {"is_active": true, "tp_multiplier": 2.0, "sl_multiplier": 1.5, "kelly_ceiling": 0.10},
    "ETH-USD": {"is_active": true, "tp_multiplier": 2.0, "sl_multiplier": 1.5, "kelly_ceiling": 0.05},
    "LINK-USD": {"is_active": true, "tp_multiplier": 2.0, "sl_multiplier": 1.5, "kelly_ceiling": 0.08},
    "LTC-USD": {"is_active": true, "tp_multiplier": 2.0, "sl_multiplier": 1.5, "kelly_ceiling": 0.08},
    "SOL-USD": {"is_active": true, "tp_multiplier": 2.0, "sl_multiplier": 1.5, "kelly_ceiling": 0.10},
    "SUI-USD": {"is_active": true, "tp_multiplier": 2.0, "sl_multiplier": 1.5, "kelly_ceiling": 0.10},
    "XRP-USD": {"is_active": true, "tp_multiplier": 2.0, "sl_multiplier": 1.5, "kelly_ceiling": 0.10}
  }
}
```

## Next Review
Scheduled: 2026-07-21 — monitor whether reduced TP multipliers improve hit rate.
