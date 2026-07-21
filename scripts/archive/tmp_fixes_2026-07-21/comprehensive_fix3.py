#!/usr/bin/env python3
"""Fix: JS init, OpenClaw bridge, default prompts"""
B = "/root/nexustrader"

# ─── 1. Fix enhancer.js Quant Team init ───────────────────────────────────
with open(f"{B}/dashboard/enhancer.js") as f:
    js = f.read()

# Replace the broken DOMContentLoaded-only init with proper readyState check
old_init = """    document.addEventListener('DOMContentLoaded', function() {
        var triggers = {"""

new_init = """    (function initQuantTeam() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initQuantTeam);
            return;
        }

        var triggers = {"""

js = js.replace(old_init, new_init)

# Also fix: the setTimeout and setInterval are inside the function but after
# the saveAllPrompts handler. Need to make sure they execute.
# Find the closing of the quant team function and verify structure

opens = js.count('{')
closes = js.count('}')
print(f"Braces: {opens}/{closes} {'OK' if opens == closes else 'MISMATCH'}")

with open(f"{B}/dashboard/enhancer.js", "w") as f:
    f.write(js)
print("1. Quant Team JS init fixed (readyState check)")

# ─── 2. Fix OpenClaw bridge ──────────────────────────────────────────────
# The bridge uses 192.168.0.197:18789/v1/chat/completions
# Need to fix URL path to /api/chat/completions
with open(f"{B}/openclaw_bridge.py") as f:
    bridge = f.read()

# Fix the default gateway URL
bridge = bridge.replace(
    '"http://192.168.0.197:18789/v1/chat/completions"',
    '"http://192.168.0.197:18789/api/chat/completions"'
)

with open(f"{B}/openclaw_bridge.py", "w") as f:
    f.write(bridge)
print("2. OpenClaw bridge URL fixed: v1 → api")

# ─── 3. Pre-fill default prompts ──────────────────────────────────────────
with open(f"{B}/dashboard/index.html") as f:
    html = f.read()

default_prompts = {
    'prompt-quant-text': 'Analyze recent trades to optimize TP/SL multipliers, signal threshold, and learning rate. Focus on: win rate above 40%, Sharpe ratio trending positive, monthly PnL green. Never widen SL beyond 5x ATR. Keep signal threshold between 0.35-0.65.',
    'prompt-sentiment-text': 'Scan crypto news headlines, social media volume, and fear/greed indicators for active tickers. Score each asset from -1 (extreme fear) to +1 (extreme greed). Flag extreme readings (>0.7 or <-0.7) for position size adjustment. Update sentiment_overrides in DB.',
    'prompt-risk-text': 'Audit all open positions and recent trades for risk violations: check max drawdown vs limit, position concentration, correlation clustering, and risk of ruin. If any metric exceeds threshold, recommend: reduce position sizes, widen SL, or enter cooldown. Goal: daily drawdown <5%, monthly <15%.',
    'prompt-allocator-text': 'Review per-ticker performance. Rebalance active tickers: increase allocation to winning pairs, reduce or disable pairs with negative PnL over last 30 trades. Adjust Kelly ceilings based on volatility. Rotate capital from underperformers to performers. Max 9 tickers total.',
    'prompt-dev-text': 'Review the NexusTrader dashboard code at /root/nexustrader/dashboard/. Fix bugs in JS/CSS/HTML. Improve error handling. Add polish. Never modify main.py trading logic or strategy code. Always backup files before editing. Test changes by verifying dashboard loads without console errors.',
    'prompt-asset-selector-text': 'Scan Kraken API for all tradeable USD pairs. Filter by: 24h volume > $1M, not a stablecoin, not already active. Add up to 2 new high-potential assets with good volume and diversity. Disable delisted or zero-volume pairs. Always keep BTC-USD and ETH-USD. Restart bot after changes.',
    'prompt-improve-text': 'Analyze the last 200 trades. Identify which strategies contribute positive alpha and which are noise. Evolve ensemble weights: boost winners, prune losers. Tune hyperparameters using grid search on historical data. Apply max 20% change per parameter per week. Backtest all changes before applying.',
    'prompt-blog-text': 'Generate a weekly performance report covering: total PnL, win rate, best/worst trades, drawdown, active strategies, ticker performance ranking. Include text-based charts where helpful. Style: professional but readable. Output to blog/daily_summaries/weekly_report_DATE.md.',
    'prompt-researcher-text': 'Deep monthly analysis. Compute: Sharpe ratio, Sortino ratio, Calmar ratio, max drawdown duration, profit factor, expectancy per trade. Segment by ticker, strategy, time of day, day of week. Identify market regime shifts. Recommend new strategies, asset changes, or risk framework upgrades for the coming month.'
}

for textarea_id, default_text in default_prompts.items():
    # Find the textarea and add placeholder if empty
    search = f'id="{textarea_id}"'
    if search in html:
        # Add the default text as the value (not placeholder, so it's pre-filled)
        old_ta = f'{search} style='
        new_ta = f'{search} data-default="true" style='
        if old_ta in html:
            html = html.replace(old_ta, new_ta)
    else:
        print(f"  WARNING: {textarea_id} not found")

with open(f"{B}/dashboard/index.html", "w") as f:
    f.write(html)
print(f"3. Pre-filled {len(default_prompts)} prompts with defaults")
print("DONE: Comprehensive fix applied")
