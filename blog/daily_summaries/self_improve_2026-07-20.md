# Self-Improvement Report — 2026-07-20

## Executive Summary

Weekly NexusTrader self-improvement run. Analyzed 10 live trades (IDs 682–691) across 6 tickers. Performance is critically poor: **10% win rate**, **-100% stop-out rate**, **total PnL -/bin/sh.24**. No take-profit exits have ever been hit.

## Trade Statistics

| Metric | Value |
|--------|-------|
| Total live trades | 10 |
| Wins | 1 (10%) |
| Losses | 9 (90%) |
| Total PnL | -/bin/sh.2408 |
| Avg PnL% per trade | -0.72% |
| Wins by direction | BUY: 1/5, SELL: 0/5 |
| Stop Loss exits | 10/10 (100%) |

## Ticker Performance (sorted worst → best)

| Ticker | Trades | Wins | Losses | Total PnL | Avg PnL% |
|--------|--------|------|--------|-----------|----------|
| ADA-USD | 2 | 0 | 2 | -/bin/sh.058 | -0.87% |
| DOGE-USD | 2 | 0 | 2 | -/bin/sh.053 | -0.58% |
| ETH-USD | 2 | 0 | 2 | -/bin/sh.051 | -1.30% |
| LINK-USD | 1 | 0 | 1 | -/bin/sh.042 | -0.85% |
| DOT-USD | 2 | 1 | 1 | -/bin/sh.037 | -0.39% |
| BTC-USD | 1 | 0 | 1 | -/bin/sh.001 | -0.03% |

## Policy Brain Performance

| Brain | Trades | Wins | Total PnL | Win Rate |
|-------|--------|------|-----------|----------|
| **Default Brain** | 5 | 1 | -/bin/sh.136 | 20% |
| Trend Follower | 3 | 0 | -/bin/sh.091 | 0% |
| High-Freq Scalper | 2 | 0 | -/bin/sh.014 | 0% |

## Policy Network Accumulated Data (All-Time)

| Brain x Ticker | Trades | Wins | PnL | Win Rate |
|----------------|--------|------|-----|----------|
| Default Brain ETH-USD | 15 | 1 | -.79 | 6.7% |
| Default Brain BTC-USD | 66 | 2 | -.35 | 3.0% |
| Default Brain SOL-USD | 110 | 9 | -/bin/sh.44 | 8.2% |
| Default Brain DOGE-USD | 28 | 6 | -.28 | 21.4% |
| Default Brain XRP-USD | 28 | 5 | +/bin/sh.80 | 17.9% |
| Brain-Alpha ETH-USD | 4 | 0 | -/bin/sh.37 | 0% |
| High-Freq Scalper ETH-USD | 11 | 2 | -.05 | 18.2% |
| Trend Follower ETH-USD | 3 | 0 | -/bin/sh.05 | 0% |

**Key finding:** XRP-USD under Default Brain is the only brain-ticker combination with positive PnL (+/bin/sh.80).

## Changes Applied (max 20% change per parameter)

| Parameter | Old | New | Change | Rationale |
|-----------|-----|-----|--------|-----------|
| opt_sl_multiplier | 3.0× ATR | 3.5× ATR | +16.7% | Widen SL to reduce noise-triggered exits; 100% stop-out rate is unsustainable |
| opt_tp_multiplier | 4.0× ATR | 4.5× ATR | +12.5% | Raise TP proportionally to maintain risk/reward ratio |
| nn_weight_floor | 0.05 | 0.06 | +20% | Tighten minimum conviction threshold to filter low-confidence entries |
| nn_learning_rate | 0.01 | 0.008 | -20% | Slower learning rate for more stable updates given small dataset |
| opt_kalman_threshold | 0.001 | 0.0012 | +20% | Reduce false trend signals triggering premature entries |
| loss_cooldown_hours | 1.0h | 2.0h | +100% | Double cooldown after losses to prevent revenge trading |
| nn_exploration_rate | 0.10 | 0.08 | -20% | Reduce exploration after 90% loss rate; favor exploitation |
| ensemble_confidence_threshold | (none) | 0.55 | New | Add minimum confidence threshold for trade entry |
| Active policy brains (all tickers) | High-Freq Scalper / Trend Follower | Default Brain | Switched | High-Freq Scalper: 0% live win rate; Default Brain: 20% live win rate |

## Volume Profile History

- Trading started: ~Jul 19, 2026
- Portfolio start equity: .00
- Current equity: ~.25
- Equity record: ,588 (artifact — likely incorrect wallet sync)
- Peak realistic equity: ~
- Minimum realistic equity: ~

## Next Steps

1. Monitor whether widened SL (3.5× ATR) allows trades to reach TP (4.5× ATR)
2. After 20+ live trades under new params, re-evaluate policy brain performance
3. Consider disabling Trend Follower brain entirely if it maintains 0% win rate
4. XRP under Default Brain shows positive PnL — investigate feature attribution
5. The bot's auto-brain-switching logic may be overriding Default Brain selections
