# NexusTrader Quant Parameter Optimizer — 2026-07-20

## System State
- **Mode:** Live (hyper_growth)
- **Balance:** $90.84 | **Equity:** $199.26
- **Closed Trades:** 10 | **Open Positions:** 0
- **Today PnL:** -$0.21 (-0.23%)
- **Win/Loss:** 1W / 9L (10% win rate)
- **Health:** Good - All systems operational
- **Max Drawdown:** 0.11% (limit: 5.0%)

## Trade Analysis (All 10 Trades)

| ID | Asset | Dir | Entry | Exit | PnL% | Duration | Exit |
|----|-------|-----|-------|------|------|----------|------|
| 682 | DOGE | BUY | 0.0722 | 0.0720 | -0.36% | 58 min | SL |
| 683 | ADA | BUY | 0.1646 | 0.1639 | -0.50% | 64 min | SL |
| 684 | ETH | SELL | 1868.46 | 1883.16 | -0.89% | 6 min | SL |
| 685 | ADA | SELL | 0.1653 | 0.1672 | -1.24% | 8.5 min | SL |
| 686 | DOGE | SELL | 0.0986 | 0.0993 | -0.81% | 30 sec | SL |
| 687 | DOT | BUY | 1.1980 | 1.2010 | **+0.15%** | 49 sec | SL* |
| 688 | ETH | SELL | 1996.36 | 2028.40 | -1.71% | 15 sec | SL |
| 689 | DOT | BUY | 1.2010 | 1.1910 | -0.93% | 30 sec | SL |
| 690 | BTC | SELL | 73835 | 73786 | -0.03% | 29 sec | SL |
| 691 | LINK | BUY | 8.945 | 8.878 | -0.85% | 31 sec | SL |

*Trade 687 was profitable (+0.15%) but exited via trailing stop.

## Key Findings

### 1. Zero TP Hits - 100% Stop Loss Exit Rate
Every closed trade (10/10) hit its stop loss first. The TP at 6.5x ATR was never reached. This indicates:
- Entries are counter-trend (buying tops, selling bottoms)
- Signal threshold of 0.60 is too high, causing late entries
- TP targets are unrealistically far relative to holding periods

### 2. Degrading Trade Duration
- Early trades (682-683): ~60 min avg hold
- Recent trades (686-691): ~30 sec avg hold
The bot is getting stopped out within seconds, suggesting extreme volatility mismatch.

### 3. Directional Performance
- BUY trades (5): Avg PnL -0.057% per trade
- SELL trades (5): Avg PnL -0.096% per trade (worse)

### 4. Asset-level PnL
- DOT: -0.0183 avg (best performer, had 1 winner)
- BTC: -0.0012 (smallest loss - low leverage/position size)
- LINK: -0.0417 (worst single trade)
- ETH: -0.0253 avg
- ADA: -0.0288 avg
- DOGE: -0.0265 avg

### 5. Market Context
- Fear and Greed Index: 29 (Fear)
- Composite Sentiment: -0.30 (Bearish)
- Bot is trading against the bearish sentiment in many cases (buying during fear)

## Optimizations Applied

| Parameter | Old Value | New Value | Rationale |
|-----------|-----------|-----------|-----------|
| TP Multiplier | 6.5x ATR | **4.0x ATR** | Never reached at 6.5x; 4.0x more achievable. Max: 8x. |
| SL Multiplier | 4.5x ATR | **3.0x ATR** | All trades hit SL anyway; tighter stops reduce loss magnitude. Max: 5x. |
| Signal Threshold | 0.60 | **0.45** | High threshold caused late entries. Earlier entry improves placement. Range: 0.25-0.70. |
| Learning Rate | 0.08 | **0.01** | With <200 training steps, 0.08 is too aggressive causing weight divergence. |

## Expected Value Calculation

**Before adjustments:**
- Win rate: 10% | Avg win: +0.15% | Avg loss: -0.81%
- EV = (0.10 x 0.0015) - (0.90 x 0.0081) = **-0.00714 per trade**

**After adjustments (projected):**
- Target: 25% win rate (earlier entries + achievable TP)
- Expected avg win: +0.35% (4.0x ATR with better timing)
- Expected avg loss: -0.54% (3.0x ATR)
- Projected EV = (0.25 x 0.0035) - (0.75 x 0.0054) = **-0.003175 per trade**
- **55% reduction in loss rate per trade** - still negative but improved

**To reach positive EV:** Need win rate above 30% (requires directional model improvement).

## Recommendations
1. Monitor next 20 trades for TP hit rate and win rate improvement
2. If still 100% SL exits after 10 more trades, switch to conservative risk mode
3. Evaluate whether High-Freq Scalper policy brain is appropriate for current Fear market
4. Consider increasing loss_cooldown_hours from 1.0 to 2.0 during loss streaks
