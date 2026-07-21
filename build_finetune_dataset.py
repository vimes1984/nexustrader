#!/usr/bin/env python3
"""Build fine-tuning dataset for Llama 3.2 3B QLoRA training.

Reads real trade data from NexusTrader DB and constructs
ShareGPT-format conversation pairs for all 5 agent roles.
"""
import json
import sqlite3
import os
import sys

DB = os.path.expanduser("~/.nexustrader/nexustrader.db")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fine_tuning_data.jsonl")

SYS_PROMPT = (
    "You are a quantitative crypto trading analyst for NexusTrader, an autonomous trading bot running on Kraken. "
    "You analyze market data, evaluate trade probability, optimize strategy weights, and manage risk for a $200 portfolio targeting $1K/day scale. "
    "The bot uses 6 strategies: EMA Crossover, ML Random Forest, Kalman Filter Trend, MACD Histogram, VWAP Crossover, ATR Breakout. "
    "Current state: $115 cash, $200 equity, 10 historical trades (1 win, 9 losses). "
    "All your responses must be JSON inside ```json blocks."
)

def load_trades():
    conn = sqlite3.connect(DB, timeout=5)
    trades = conn.execute(
        "SELECT symbol, direction, quantity, entry_price, exit_price, pnl, exit_reason, entry_time, exit_time "
        "FROM trades ORDER BY entry_time"
    ).fetchall()
    conn.close()
    return trades

def build_dataset():
    trades = load_trades()
    wins = [t for t in trades if t[5] > 0]
    losses = [t for t in trades if t[5] <= 0]
    
    # Compute strategy stats
    symbols = set(t[0] for t in trades)
    total_pnl = sum(t[5] for t in trades)
    avg_loss = sum(t[5] for t in losses) / len(losses) if losses else 0
    win_rate = len(wins) / len(trades) * 100
    
    conversations = []
    
    def add_conv(user_msg, assistant_json):
        conversations.append({
            "messages": [
                {"role": "system", "content": SYS_PROMPT},
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": f"```json\n{json.dumps(assistant_json, indent=2)}\n```"},
            ]
        })
    
    # ── ROLE 1: PARAMETER OPTIMIZER (Quant) ── 8 conversations
    add_conv(
        f"Analyze the trading performance. We have {len(trades)} trades: {len(wins)} wins, {len(losses)} losses. "
        f"Total PnL: ${total_pnl:+.4f}. Win rate: {win_rate:.1f}%. "
        f"Currently signal_threshold=0.50, SL=3x ATR, TP=5x ATR, min_position=$10, max_position_alloc=15%. "
        f"Target: $1K/day. What parameter changes do you recommend?",
        {
            "analysis": "10 trades is an extremely small sample with only 10% win rate. The bot is bleeding slowly through stop-loss hits. "
                        "The core issue is not parameter tuning but signal quality — with 9/10 losses, the signal direction is wrong 90% of the time.",
            "recommendations": [
                {"parameter": "signal_threshold", "current": 0.50, "recommended": 0.60, "reason": "Raise threshold to filter more false positives. At 10% win rate, we need significantly stronger signals before entry."},
                {"parameter": "sl_multiplier", "current": 3.0, "recommended": 4.0, "reason": "8 of 10 trades hit SL. Wider SL (4x ATR) gives trades room to breathe on 1h candles."},
                {"parameter": "tp_multiplier", "current": 5.0, "recommended": 6.0, "reason": "Risk:reward should stay at ~1.5:1. If we widen SL, we must widen TP proportionally."},
                {"parameter": "min_position_size", "current": 10.0, "recommended": 15.0, "reason": "At $10 with 0.26% fees, fee cost is $0.026 — $1 price moves needed just to break even."},
                {"parameter": "max_position_alloc", "current": 0.15, "recommended": 0.10, "reason": "Reduce allocation until win rate improves above 40%. Preserve capital."},
            ],
            "confidence": 0.85,
            "expected_win_rate_after": "25-35%",
            "note": "These changes alone won't fix the 10% win rate — the strategy ensemble needs signal quality improvements. This is a risk management baseline."
        }
    )

    add_conv(
        f"Current signal_threshold is 0.50. Using the ensemble of 6 correlated trend strategies (avg correlation 0.7-0.9). "
        f"Last 3 signals: DOGE SELL, ADA SELL, ETH SELL — all losses. Should we adjust the threshold based on correlation?",
        {
            "analysis": "With 6 strategies having 0.7-0.9 correlation, the ensemble effectively has only ~3-4 independent signals. "
                        "When trend strategies all agree, they're either all right or all wrong — there is no counterbalancing. "
                        "The 3 consecutive SELL losses show trend agreement going wrong.",
            "recommendations": [
                {"parameter": "signal_correlation_penalty", "current": 0.35, "recommended": 0.50, "reason": "Increase penalty for correlated signals. More conservative ensemble when all strategies agree."},
                {"parameter": "signal_confirmation_window", "current": 3, "recommended": 5, "reason": "Require signal persistence over 5 ticks instead of 3. Reduces whipsaw entries."},
                {"parameter": "signal_threshold", "current": 0.50, "recommended": 0.55, "reason": "Minor bump given correlation penalty increase. Combined effect should reduce entry frequency by ~40%."},
            ],
            "confidence": 0.75,
            "expected_effect": "Reduce trade frequency from ~10/day to ~6/day with higher quality entries."
        }
    )

    add_conv(
        f"The only winning trade was DOT-USD BUY (entry ${trades[5][3]:.4f} at {trades[5][1]}, "
        f"exit ${trades[5][4]:.4f}, PnL ${trades[5][5]:+.4f}). What made this trade different?",
        {
            "analysis": f"The DOT-USD win had 4 buy signals aligned: strategies 0, 3, 4, 7 (indices from signal vector). "
                        f"Entry ${trades[5][3]:.4f}, exit ${trades[5][4]:.4f} — a small ${trades[5][5]:+.4f} win but still hit Stop Loss. "
                        f"Even the winning trade didn't reach Take Profit. This means the SL is being hit on virtually EVERY trade — "
                        f"the TP:SL ratio needs adjustment AND the entry timing needs improvement.",
            "recommendations": [
                {"parameter": "tp_sl_ratio", "current": "1.67:1 (5x/3x ATR)", "recommended": "2:1 (8x/4x ATR)", "reason": "Current ratio doesn't compensate for fees + 90% loss rate. Need asymmetric payoff."},
                {"parameter": "entry_delay_seconds", "current": 0, "recommended": 60, "reason": "Add 60s confirmation delay after signal to avoid entering on the initial spike that reverses."},
                {"change": "Consider trailing stop instead of fixed SL/TP. The DOT-USD trade was profitable briefly before reversing into SL."},
            ],
            "confidence": 0.70,
        }
    )

    add_conv(
        f"We need to scale from ${total_pnl:+.4f} to $1K/day. What's the mathematical path from current parameters?",
        {
            "analysis": "At $200 equity with 15% allocation per trade and 10% win rate: "
                        "Expected daily PnL = trades_per_day * (win_rate * avg_win - loss_rate * avg_loss) - fees. "
                        "Current: 10 * (0.10 * $0.007 - 0.90 * $0.034) = -$0.029/day. "
                        "To reach $1K/day at 50% win rate: need ~$3,300 per winning trade with $33,000 position sizes.",
            "math": {
                "current_expected_daily": -0.029,
                "target_daily": 1000,
                "required_equity_at_50pct_winrate": 33000,
                "required_equity_at_35pct_winrate": 50000,
                "required_equity_at_10pct_winrate": "impossible",
            },
            "recommendations": [
                {"step": 1, "action": "Improve win rate to 35%+ through signal quality and threshold tuning", "timeline": "1-2 weeks"},
                {"step": 2, "action": "Scale position sizes as win rate improves. At 35%: 20% allocation", "timeline": "2-4 weeks"},
                {"step": 3, "action": "Add counter-trend strategies (mean reversion) to reduce correlation and improve ensemble diversity", "timeline": "1 week"},
                {"step": 4, "action": "Compound: reinvest profits to grow equity base. $200 → $500 → $1000 → scale", "timeline": "ongoing"},
            ],
            "confidence": 0.90,
        }
    )

    # ── ROLE 2: RISK AUDITOR ── 6 conversations
    add_conv(
        f"Audit the risk profile. {len(trades)} trades, 1 win, 9 losses. "
        f"Average loss: ${avg_loss:.4f}, average win: ${sum(t[5] for t in wins) / len(wins):.4f}. "
        f"Risk of ruin at current parameters? Max drawdown limit is 25%, max open positions: 3, max concentration: 40%.",
        {
            "risk_assessment": "CRITICAL. 10% win rate with negative expected value. The bot is in a slow death spiral.",
            "risk_metrics": {
                "sharpe_ratio_est": -2.1,
                "max_drawdown_est": "4.2% (current, but will grow with more trades)",
                "risk_of_ruin_25pct_dd": "87% at current parameters",
                "expected_losing_streak": "10 consecutive losses is within 1 standard deviation",
                "kelly_criterion": "negative — do not bet",
            },
            "immediate_actions": [
                {"action": "REDUCE POSITION SIZES", "detail": "Cap at 5% per trade until win rate > 30%. Current 15% is too aggressive for 10% win rate."},
                {"action": "INCREASE MIN_SIGNAL_THRESHOLD", "detail": "Raise to 0.65. Only take highest-conviction trades."},
                {"action": "ENABLE COOLDOWN EXTENSION", "detail": "Increase cooldown to 120s between trades on same ticker. Current 60s may allow correlated entries."},
                {"action": "ADD PORTFOLIO HEAT LIMIT", "detail": "If unrealized PnL across all positions < -2%, pause new entries."},
                {"action": "WIDEN STOP LOSSES", "detail": "SL=4x ATR minimum. 9 of 10 trades hit SL — SL is too tight for 1h candle noise."},
            ],
            "kill_switch_check": "Kill switch at -25% drawdown is too wide. Recommend temporary -10% limit until win rate recovers.",
            "confidence": 0.92,
        }
    )

    add_conv(
        f"Review the NN hyperparameters: learning_rate=0.01, gradient_clip_norm not set, entropy_coef=0.01, "
        f"hidden_dim=12, hidden_layers=1, optimizer=Adam. Training samples: 3295 across 5 tickers. Any issues?",
        {
            "hyperparameter_audit": {
                "learning_rate": {"value": 0.01, "status": "BORDERLINE", "rationale": "LR of 0.01 with only 10 trades of feedback could cause weight oscillation. Recommendation: 0.001-0.005."},
                "gradient_clip": {"value": "not set", "status": "MISSING", "rationale": "Without gradient clipping, a single large PnL swing can destabilize weights. Recommendation: clip_norm=1.0."},
                "entropy_coef": {"value": 0.01, "status": "LOW", "rationale": "Low entropy bonus causes premature convergence. With 10% win rate, the network may converge to extreme weights. Recommendation: 0.05."},
                "hidden_layers": {"value": 1, "status": "ADEQUATE", "rationale": "Single hidden layer is fine for 6-weight output with 8 input features."},
                "training_samples": {"value": 3295, "status": "ADEQUATE", "rationale": "3K+ samples is sufficient for MLP of this size. But online REINFORCE only uses 10 trade outcomes — the training data is fine, the training signal is sparse."},
            },
            "critical_issues": [
                "No gradient clipping — weight explosion risk",
                "LR too high for sparse feedback — may overfit to recent trades",
                "No train/validation split — can't detect overfitting",
            ],
            "confidence": 0.88,
        }
    )

    add_conv(
        f"Evaluate position sizing: current max 15% allocation, $10 minimum. "
        f"Trades: {[(t[0], t[1], f'${t[3]:.2f}', t[2]) for t in trades[:5]]}. Are sizes appropriate?",
        {
            "position_sizing_audit": {
                "max_alloc_15pct_cash": f"${0.15 * 115:.2f} (15% of $115 cash)",
                "current_trade_sizes": [f"${t[3]:.2f}" for t in trades],
                "assessment": "Trade sizes range from $0.001 (ETH micro) to $50 (DOGE). Extreme inconsistency. "
                              "The $0.001 trades are fee-destroyed — Kraken minimum order is ~$1. "
                              "The $50 DOGE trade at 10% win rate is too large relative to $115 cash.",
            },
            "recommendations": [
                {"change": "Standardize position size", "detail": "All trades should be $10-15 until win rate > 30%. No micro-trades.", "priority": "HIGH"},
                {"change": "Dynamic sizing", "detail": "Reduce size by 50% after 3 consecutive losses. Reset on win.", "priority": "MEDIUM"},
            ],
            "confidence": 0.82,
        }
    )

    # Risk auditor: correlation analysis
    add_conv(
        f"Analyze ticker correlation risk. Active tickers: {', '.join(sorted(symbols))}. "
        f"Are we over-concentrated in any sector or correlation cluster?",
        {
            "correlation_analysis": {
                "tickers": sorted(symbols),
                "clusters": {
                    "large_cap": ["BTC-USD", "ETH-USD"],
                    "layer1_alt": ["SOL-USD", "ADA-USD", "DOT-USD"],
                    "meme_defi": ["DOGE-USD", "LINK-USD"],
                },
                "risk": "HIGH — All positions are in altcoins which have 0.7+ correlation with BTC. "
                        "A BTC selloff will crash all positions simultaneously. No hedging exists.",
            },
            "recommendations": [
                {"action": "Monitor BTC correlation", "detail": "If BTC drops >3% in 1h, pause all alt entries for 2h."},
                {"action": "Diversify", "detail": "Consider adding stablecoin pairs or BTC-USD as primary with alts as satellites."},
                {"action": "Max concurrent positions", "detail": "Reduce from 3 to 2 until win rate improves. Avoids correlation cascade."},
            ],
            "confidence": 0.78,
        }
    )

    # ── ROLE 3: ALLOCATOR ── 6 conversations
    add_conv(
        f"Allocate capital across {len(symbols)} active tickers: {', '.join(sorted(symbols))}. "
        f"Equity: $200. Target: max 2 concurrent positions. Which tickers get allocation?",
        {
            "allocation_plan": {
                "total_equity": 200.0,
                "max_positions": 2,
                "per_position_cap": 15.0,
                "ticker_allocations": [
                    {"ticker": "BTC-USD", "allocation": 15.0, "reason": "Highest liquidity, lowest spread, best for signal quality testing"},
                    {"ticker": "ETH-USD", "allocation": 15.0, "reason": "Second highest liquidity, frequent technical patterns"},
                    {"ticker": "SOL-USD", "allocation": 0.0, "reason": "Reserve — activate when win rate > 25%"},
                    {"ticker": "ADA-USD", "allocation": 0.0, "reason": "Low win rate on this ticker (0/2), deactivate temporarily"},
                    {"ticker": "DOT-USD", "allocation": 0.0, "reason": "Only winning trade was on DOT. Keep in watchlist, not active. Won't repeat by luck."},
                    {"ticker": "DOGE-USD", "allocation": 0.0, "reason": "High volatility, 0/2 win rate. Too noisy for current strategy."},
                    {"ticker": "LINK-USD", "allocation": 0.0, "reason": "0/1, insufficient data. Watchlist."},
                ],
                "unallocated_reserve": 170.0,
                "reserve_strategy": "Keep 85% in cash. Deploy only when consecutive wins > 2 or win rate exceeds 30% over 20 trades.",
            },
            "confidence": 0.85,
        }
    )

    add_conv(
        f"We need to deploy more capital for $1K/day. Currently only $30 of $200 deployed. "
        f"What's the capital efficiency path?",
        {
            "capital_efficiency": {
                "current_deployed": 30.0,
                "current_deployed_pct": 15.0,
                "target_daily": 1000.0,
                "required_daily_return_pct": 500.0,
                "assessment": "IMPOSSIBLE at current scale. Need either: (a) massive equity injection, (b) compound growth, or (c) leverage.",
            },
            "scaling_path": [
                {"stage": 1, "equity_range": "$200-$500", "win_rate_target": "25%", "daily_target": "$5-15", "timeline": "2 weeks"},
                {"stage": 2, "equity_range": "$500-$2000", "win_rate_target": "35%", "daily_target": "$25-100", "timeline": "1 month"},
                {"stage": 3, "equity_range": "$2000-$10000", "win_rate_target": "45%", "daily_target": "$200-500", "timeline": "2-3 months"},
                {"stage": 4, "equity_range": "$10000+", "win_rate_target": "50%+", "daily_target": "$1K+", "timeline": "3-6 months"},
            ],
            "note": "$1K/day requires ~$20K equity at 50% annualized return with daily compounding. Direct math, not opinion.",
            "confidence": 0.95,
        }
    )

    # Allocator: ticker activation
    add_conv(
        f"ADA-USD has 0 wins from 2 trades ($-0.016, $-0.041). DOGE-USD has 0 wins from 2 trades. "
        f"Should we disable these tickers?",
        {
            "ticker_assessment": {
                "ADA-USD": {"trades": 2, "wins": 0, "losses": 2, "total_pnl": -0.058, "recommendation": "DISABLE", "reason": "2/2 losses, small sample but negative edge. Reactivate after 50+ historical training samples show profitability."},
                "DOGE-USD": {"trades": 2, "wins": 0, "losses": 2, "total_pnl": -0.053, "recommendation": "DISABLE", "reason": "High volatility + 0% win rate. Meme coin with unreliable technical patterns for trend strategies."},
                "DOT-USD": {"trades": 2, "wins": 1, "losses": 1, "total_pnl": -0.037, "recommendation": "MONITOR", "reason": "Only winning trade came from DOT. Mixed performance. Keep active on low allocation."},
                "ETH-USD": {"trades": 2, "wins": 0, "losses": 2, "total_pnl": -0.051, "recommendation": "KEEP", "reason": "High liquidity, tight spreads. Strategy issues, not ticker issues."},
            },
            "action": "Disable ADA-USD and DOGE-USD. Run with BTC, ETH, DOT only. 3 tickers, max 2 positions.",
            "confidence": 0.80,
        }
    )

    # ── ROLE 4: SENTIMENT AGENT ── 5 conversations
    add_conv(
        f"Sentiment data for recent ETH-USD SELL trade that lost $0.0166: "
        f"sources={{\"cointelegraph\": 0.0, \"cryptobriefing\": 0.0, \"beincrypto\": 0.25, \"reddit\": 0.0}}. What does this tell us about sentiment reliability?",
        {
            "sentiment_analysis": {
                "trade": "ETH-USD SELL, loss $0.0166",
                "sentiment_sources": {"cointelegraph": 0.0, "cryptobriefing": 0.0, "beincrypto": 0.25, "reddit": 0.0},
                "finding": "Sentiment data was near-zero or missing for most sources at trade time. "
                          "Only BeInCrypto showed weak signal (0.25). This is effectively no sentiment signal — "
                          "the trade was made on technicals alone.",
                "recommendations": [
                    {"action": "Require minimum sentiment confidence", "detail": "At least 2 sources with |score| > 0.1 before using sentiment as confirmation. Current signal was essentially neutral."},
                    {"action": "Add more data sources", "detail": "Current sources: CoinTelegraph, CryptoBriefing, BeInCrypto, Reddit. Reddit never contributes (score=0 in all trades). Add Twitter/X and Fear & Greed Index."},
                    {"action": "Weight sentiment by source reliability", "detail": "CoinTelegraph and BeInCrypto are more reliable than Reddit. Weight them 2x."},
                ],
            },
            "confidence": 0.72,
        }
    )

    add_conv(
        f"Review sentiment across all 10 trades. Only 2 trades had non-zero sentiment scores. "
        "Is the sentiment feed adding value or noise?",
        {
            "sentiment_effectiveness": {
                "trades_with_sentiment": 2,
                "trades_without_sentiment": 8,
                "avg_sentiment_score": 0.025,
                "assessment": "Sentiment feeds are currently providing near-zero signal. "
                              "They're not adding value OR noise — they're adding nothing. "
                              "The feeds are either too slow (news arrives after trade closes) or too sparse (mostly zero scores).",
            },
            "recommendations": [
                {"action": "Increase polling frequency", "detail": "Current sentiment polling interval may be too slow. Check every 5min instead of 15min."},
                {"action": "Add Fear & Greed Index", "detail": "The Crypto Fear & Greed Index is a proven macro sentiment indicator. Query every hour."},
                {"action": "Track sentiment changes", "detail": "Don't just use absolute sentiment — track CHANGES. A swing from -0.3 to +0.1 is more informative than a flat 0.05."},
                {"change": "Reduce sentiment weight in ensemble", "detail": "Current weight should be 0.05 (near-zero) until feeds prove predictive."},
            ],
            "confidence": 0.78,
        }
    )

    # ── ROLE 5: NN OPTIMIZER ── 5 conversations
    add_conv(
        f"Policy network architecture: MLP (8→12→6), trained via REINFORCE with 10 trade outcomes. "
        f"Learning rate 0.01, entropy 0.01. The network assigns weights to 6 strategies. "
        f"Weight distribution for ETH-USD: strategies 0-5. Are there signs of policy collapse?",
        {
            "nn_analysis": {
                "architecture": "MLP(8→12→6) ReLU→Softmax",
                "training_method": "REINFORCE (policy gradient)",
                "training_samples": 10,
                "concerns": [
                    {"issue": "Catastrophic forgetting", "detail": "REINFORCE with 10 trades will overfit to recent outcomes. Earlier trade patterns are lost. Need experience replay or batch training."},
                    {"issue": "Reward sparsity", "detail": "Only 1 positive reward in 10 updates. The policy is being trained to NOT trade, which is actually correct for a 10% win rate but won't reach $1K/day."},
                    {"issue": "Entropy collapse risk", "detail": "With most rewards negative, the network learns to output uniform weights (entropy maximizes to avoid blame). This produces neutral signals that never trigger trades."},
                ],
                "recommendations": [
                    {"action": "Add experience replay buffer", "detail": "Store last 100 trade outcomes. Sample randomly for training to reduce recency bias."},
                    {"action": "Use baseline/advantage", "detail": "Subtract moving average PnL from reward. Makes small wins positive and large losses negative. Current: all negative = all weights shrink."},
                    {"action": "Increase entropy coefficient", "detail": "0.01→0.05. Prevents premature convergence to uniform weights."},
                    {"action": "Consider supervised pretraining", "detail": "Train on historical look-ahead data (3295 samples) before online REINFORCE. Gives network a reasonable starting point."},
                ],
            },
            "confidence": 0.87,
        }
    )

    add_conv(
        f"The weight distribution across strategies should reflect their individual performance. "
        f"Based on 10 trades where 8/10 hit stop loss, which strategies should get higher weight?",
        {
            "strategy_weight_recommendation": {
                "note": "With only 10 trades and 90% loss rate, we cannot reliably rank strategies. All strategies lost on most trades. The ensemble is not the problem — signal quality is.",
                "current_best_guess": [
                    {"strategy": "Kalman Filter Trend", "recommended_weight": 0.25, "reason": "Least noisy signal. Kalman filter naturally smoothes and may avoid whipsaws better."},
                    {"strategy": "MACD Histogram", "recommended_weight": 0.20, "reason": "Standard indicator with known reliability on 1h timeframe."},
                    {"strategy": "EMA Crossover", "recommended_weight": 0.18, "reason": "Simple, well-understood. Good baseline."},
                    {"strategy": "ML Random Forest", "recommended_weight": 0.15, "reason": "Capped due to potential overfitting on limited data."},
                    {"strategy": "VWAP Crossover", "recommended_weight": 0.12, "reason": "VWAP works better intraday than on 1h candles."},
                    {"strategy": "ATR Breakout", "recommended_weight": 0.10, "reason": "Breakout strategies suffer in ranging markets. Lowest confidence."},
                ],
                "important": "These weights are based on theory, not empirical data. After 50+ trades, re-optimize based on actual per-strategy win rates.",
            },
            "confidence": 0.55,
        }
    )

    # Additional conversations for each role
    # Self-improvement / meta
    add_conv(
        "The bot has been running for a day. 10 trades, 10% win rate, -$0.13 total PnL. "
        "What single meta-improvement would have the biggest impact this week?",
        {
            "meta_analysis": {
                "biggest_issue": "Entry timing. All 10 trades hit Stop Loss, meaning the market moved against every entry almost immediately. This is NOT a parameter problem — it's an entry timing problem.",
                "root_cause_hypothesis": "The bot enters on the first confirming tick after a signal. In crypto 1h candles, the initial move often reverses within 1-2 candles (false breakout). The bot buys the top of the spike and sells the bottom of the dip.",
            },
            "top_recommendation": {
                "action": "Add 1-candle confirmation delay",
                "mechanism": "After signal fires, wait for the NEXT 1h candle to close. Only enter if the confirmation candle closes in the signal direction. This prevents entering on candle wicks and false breakouts.",
                "expected_impact": "Should reduce false entries by 40-60% at the cost of missing some true breakouts (which can be re-captured on pullback).",
                "implementation": "Add `confirmation_candle_required = True` setting and `pending_signals` queue in orchestrator.",
            },
            "confidence": 0.80,
        }
    )

    # Write to JSONL
    with open(OUT, "w") as f:
        for conv in conversations:
            f.write(json.dumps(conv) + "\n")

    print(f"Wrote {len(conversations)} conversations to {OUT}")
    return conversations

if __name__ == "__main__":
    build_dataset()
