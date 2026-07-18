#!/usr/bin/env python3
import os
import sys
import json
import sqlite3
import time
import datetime
import logging
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DB_PATH = os.path.expanduser("~/.nexustrader/nexustrader.db")
BLOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blog")

STRATEGY_NAMES = [
    "EMA Crossover",
    "RSI Reversion",
    "BB Breakout",
    "ML Random Forest",
    "Kalman Trend",
    "Psych Sweep",
    "News Sentiment"
]

def load_settings():
    """Loads current orchestrator settings from sqlite DB."""
    settings = {
        "portfolio_balance": 100.0,
        "risk_mode": "conservative",
        "policy_net_weights": None
    }
    if not os.path.exists(DB_PATH):
        return settings
        
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT key, value FROM settings")
        for row in c.fetchall():
            key, val = row
            if key == "portfolio_balance":
                settings[key] = float(val)
            elif key == "policy_net_weights":
                try:
                    settings[key] = json.loads(val)
                except Exception:
                    settings[key] = val
            else:
                settings[key] = val
        conn.close()
    except Exception as e:
        logging.error(f"Error loading settings: {e}")
    return settings

def load_trades(days_limit=None):
    """Loads trades from SQLite database."""
    trades = []
    if not os.path.exists(DB_PATH):
        return trades
        
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        if days_limit:
            cutoff = time.time() - (days_limit * 86400)
            c.execute("SELECT * FROM trades WHERE exit_time >= ? ORDER BY exit_time ASC", (cutoff,))
        else:
            c.execute("SELECT * FROM trades ORDER BY exit_time ASC")
            
        for row in c.fetchall():
            trade = dict(row)
            if trade.get("strategy_signals"):
                try:
                    trade["strategy_signals"] = json.loads(trade["strategy_signals"])
                except Exception:
                    trade["strategy_signals"] = []
            else:
                trade["strategy_signals"] = []
            trades.append(trade)
        conn.close()
    except Exception as e:
        logging.error(f"Error loading trades: {e}")
    return trades

def insert_mock_data():
    """Inserts realistic mock trades and settings into the database for demonstration purposes."""
    logging.info("Populating mock trading data...")
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    # Initialize DB schema if it doesn't exist
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        direction TEXT,
        quantity REAL,
        entry_price REAL,
        exit_price REAL,
        pnl REAL,
        pnl_percent REAL,
        exit_reason TEXT,
        entry_time REAL,
        exit_time REAL,
        strategy_signals TEXT
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    
    # Check current trades count
    c.execute("SELECT count(*) FROM trades")
    trades_count = c.fetchone()[0]
    
    if trades_count > 0:
        logging.info(f"Database already contains {trades_count} trades. Skipping mock data generation.")
        conn.close()
        return

    # Mock trades list
    # Let's generate 12 mock trades closed over the last 10 days
    now = time.time()
    mock_trades = [
        # (symbol, direction, quantity, entry_price, exit_price, pnl, pnl_percent, exit_reason, entry_offset_days, exit_offset_days, strategy_signals)
        ("ETH-EUR", "BUY", 0.05, 3120.0, 3198.0, 3.90, 0.025, "Take Profit", 9.5, 9.2, [1.0, 0.0, 0.0, 1.0, 1.0, 0.0]),
        ("SOL-EUR", "BUY", 1.2, 142.5, 149.6, 8.52, 0.0498, "Take Profit", 8.2, 8.0, [1.0, 1.0, 1.0, 0.0, 1.0, 1.0]),
        ("BTC-EUR", "SELL", 0.002, 58200.0, 58950.0, -1.50, -0.0128, "Stop Loss", 7.1, 6.9, [-1.0, 0.0, -1.0, -1.0, 0.0, -1.0]),
        ("ETH-EUR", "BUY", 0.05, 3180.0, 3132.3, -2.38, -0.015, "Stop Loss", 6.5, 6.3, [0.0, 1.0, 1.0, -1.0, 0.0, 1.0]),
        ("SOL-EUR", "SELL", 1.2, 151.2, 145.1, 7.32, 0.0403, "Take Profit", 5.4, 5.2, [-1.0, 1.0, 0.0, 1.0, -1.0, 1.0]),
        ("XRP-EUR", "BUY", 150.0, 0.542, 0.558, 2.40, 0.0295, "Take Profit", 4.8, 4.5, [1.0, 0.0, 1.0, 1.0, 0.0, 0.0]),
        ("BTC-EUR", "BUY", 0.002, 59100.0, 60873.0, 3.55, 0.030, "Take Profit", 3.9, 3.5, [1.0, 0.0, -1.0, 1.0, 1.0, 0.0]),
        ("ETH-EUR", "BUY", 0.06, 3210.0, 3290.2, 4.81, 0.0249, "Take Profit", 3.1, 2.9, [1.0, 1.0, 0.0, 0.0, 1.0, 0.0]),
        ("SOL-EUR", "BUY", 1.3, 148.4, 145.4, -3.90, -0.0202, "Stop Loss", 2.5, 2.3, [1.0, 1.0, 1.0, 1.0, 1.0, 1.0]),
        ("DOGE-EUR", "BUY", 800.0, 0.115, 0.122, 5.60, 0.0608, "Take Profit", 1.8, 1.5, [1.0, 0.0, 1.0, 1.0, 0.0, 1.5]),
        ("ETH-EUR", "SELL", 0.06, 3295.0, 3245.5, 2.97, 0.015, "Take Profit", 1.1, 0.8, [-1.0, 1.0, 1.0, 0.0, -1.0, 1.0]),
        ("BTC-EUR", "BUY", 0.002, 61200.0, 61506.0, 0.61, 0.005, "Take Profit", 0.4, 0.1, [1.0, 0.0, 0.0, 1.0, 1.0, 0.0])
    ]
    
    for t in mock_trades:
        sym, direction, qty, entry, exit, pnl, pnl_pct, reason, entry_off, exit_off, signals = t
        entry_time = now - (entry_off * 86400)
        exit_time = now - (exit_off * 86400)
        c.execute("""
        INSERT INTO trades (symbol, direction, quantity, entry_price, exit_price, pnl, pnl_percent, exit_reason, entry_time, exit_time, strategy_signals)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (sym, direction, qty, entry, exit, pnl, pnl_pct, reason, entry_time, exit_time, json.dumps(signals)))
        
    # Save settings
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('portfolio_balance', '129.90')")
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('risk_mode', 'aggressive')")
    
    # Mock Policy Network weights
    weights = [0.28, 0.08, 0.06, 0.22, 0.26, 0.10]
    weights_json = json.dumps({
        "W1": [[0.1]*12]*7,
        "b1": [[0.0]*12],
        "W2": [[0.1]*6]*12,
        "b2": [[0.0]*6]
    })
    # We save a format that matches weights query
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('policy_net_weights', ?)", (weights_json,))
    
    conn.commit()
    conn.close()
    logging.info("Mock database populated successfully!")

def analyze_weekly_performance(trades):
    """Calculates all key statistics from the weekly trade log."""
    if not trades:
        return {}
        
    pnl_list = [t["pnl"] for t in trades]
    pnl_pct_list = [t["pnl_percent"] for t in trades]
    
    total_trades = len(trades)
    winning_trades = [t for t in trades if t["pnl"] > 0]
    losing_trades = [t for t in trades if t["pnl"] <= 0]
    
    wins = len(winning_trades)
    losses = len(losing_trades)
    win_rate = (wins / total_trades) if total_trades > 0 else 0.0
    
    total_pnl = sum(pnl_list)
    avg_pnl = total_pnl / total_trades if total_trades > 0 else 0.0
    avg_pnl_pct = sum(pnl_pct_list) / total_trades if total_trades > 0 else 0.0
    
    best_trade = max(trades, key=lambda x: x["pnl"]) if trades else None
    worst_trade = min(trades, key=lambda x: x["pnl"]) if trades else None
    
    sum_win_pnl = sum([t["pnl"] for t in winning_trades])
    sum_loss_pnl = sum([t["pnl"] for t in losing_trades])
    profit_factor = abs(sum_win_pnl / sum_loss_pnl) if sum_loss_pnl != 0 else float('inf')
    
    # Ticker performance breakdown
    ticker_breakdown = {}
    for t in trades:
        sym = t.get("symbol", "UNKNOWN")
        if sym not in ticker_breakdown:
            ticker_breakdown[sym] = {"trades": 0, "wins": 0, "pnl": 0.0}
        ticker_breakdown[sym]["trades"] += 1
        ticker_breakdown[sym]["pnl"] += t["pnl"]
        if t["pnl"] > 0:
            ticker_breakdown[sym]["wins"] += 1
            
    for sym in ticker_breakdown:
        t_count = ticker_breakdown[sym]["trades"]
        w_count = ticker_breakdown[sym]["wins"]
        ticker_breakdown[sym]["win_rate"] = (w_count / t_count) if t_count > 0 else 0.0
        
    # Strategy attribution
    # Initialize counts and PnL for each of the 6 strategies
    strat_perf = {name: {"trades": 0, "wins": 0, "pnl": 0.0} for name in STRATEGY_NAMES}
    
    for t in trades:
        signals = t.get("strategy_signals", [])
        if len(signals) < len(STRATEGY_NAMES):
            continue
            
        direction_val = 1.0 if t["direction"] == "BUY" else -1.0
        for i, name in enumerate(STRATEGY_NAMES):
            sig = signals[i]
            # Alignment check: if signal aligns with direction, this strategy contributed to trade entry
            if sig * direction_val > 0:
                strat_perf[name]["trades"] += 1
                strat_perf[name]["pnl"] += t["pnl"]
                if t["pnl"] > 0:
                    strat_perf[name]["wins"] += 1
                    
    # Format strategy statistics
    for name in STRATEGY_NAMES:
        t_count = strat_perf[name]["trades"]
        w_count = strat_perf[name]["wins"]
        strat_perf[name]["win_rate"] = (w_count / t_count) if t_count > 0 else 0.0
        
    return {
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "avg_pnl": avg_pnl,
        "avg_pnl_pct": avg_pnl_pct,
        "profit_factor": profit_factor,
        "best_trade": best_trade,
        "worst_trade": worst_trade,
        "ticker_breakdown": ticker_breakdown,
        "strategy_performance": strat_perf
    }

def get_ascii_bar(val, max_val=1.0, width=15):
    """Generates an ASCII bar for visual weight comparison."""
    if max_val == 0:
        return "░" * width
    pct = val / max_val
    filled = int(round(pct * width))
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)

def generate_report_template(stats, settings, start_date, end_date, op_mode):
    """Generates a beautiful weekly blog report using stats and settings."""
    date_str = f"{start_date.strftime('%B %d, %Y')} to {end_date.strftime('%B %d, %Y')}"
    
    # Generate prominent Operational Status Badge based on mode
    if op_mode == "MOCK_DEMO":
        op_badge = """> [!NOTE]
> **Operational Status:** `SAMPLE DATA (MOCK TEST DATA)`  
> This report was generated using synthetic trade history for demonstration and testing purposes. No assets were traded. No real money or live connection was active.
"""
    elif op_mode == "LIVE_CAPITAL":
        op_badge = """> [!WARNING]
> **Operational Status:** `LIVE CAPITAL TRADING (REAL MONEY)`  
> **WARNING:** The system is currently executing live transactions with real capital via broker API credentials. Real financial assets are at risk.
"""
    else: # PAPER_TRADING
        op_badge = """> [!IMPORTANT]
> **Operational Status:** `PAPER TRADING (LIVE SIMULATION)`  
> The system is running simulations on live market feed ticks. Trades are executed using virtual balances (paper trading) with zero capital risk.
"""
    
    # Calculate balance changes
    current_bal = settings["portfolio_balance"]
    total_pnl = stats.get("total_pnl", 0.0)
    starting_bal = current_bal - total_pnl
    return_pct = (total_pnl / starting_bal) * 100 if starting_bal != 0 else 0.0
    
    # Risk Profile
    risk_mode = settings.get("risk_mode", "conservative").upper()
    
    # Policy weights representation
    weights_section = ""
    # Try to load weights from SQLite
    weights_list = [1.0/len(STRATEGY_NAMES)] * len(STRATEGY_NAMES)
    
    # Let's read weights from policy network if possible
    # W1, b1, etc are network weights, we need to run forward pass on a mock state
    # or just extract the weights if we can.
    # To keep it simple, we can load active weights from the dashboard api or compute them
    # Let's inspect database.py logic - policy network weights are saved to key 'policy_net_weights'
    # Actually, we can fetch active weights or use the last loaded weights from DB
    # Let's write code to query settings table for 'policy_net_weights'
    weights_dict = {}
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        # Let's see if we have weights saved directly or in network JSON
        c.execute("SELECT value FROM settings WHERE key LIKE 'policy_net_weights_%' LIMIT 1")
        row = c.fetchone()
        if row:
            # Check if it contains the neural network weights or raw array
            val = json.loads(row[0])
            if "W1" in val:
                # It's neural network weights. We can simulate a standard state to compute probabilities,
                # or just look at last weights. Wait, we can see if there are logs, or we can just run forward pass on average state.
                # Let's run a forward pass!
                from learning_engine import PolicyNetwork
                net = PolicyNetwork(state_dim=8, hidden_dim=12, action_dim=7)
                net.from_json(row[0])
                # standard/average state with 8 dimensions: regime, theta, rsi, macd, bb, atr, win_trend, sentiment
                probs = net.forward([0.5, 0.1, 0.0, 0.0, 0.0, 0.05, 0.5, 0.0])
                weights_list = probs.tolist()
            else:
                weights_list = val
        conn.close()
    except Exception as e:
        # Fallback: if we can't load, check if there are recent ticks to get weights or just use equal weights
        logging.warning(f"Could not compute neural weights: {e}. Using baseline weights.")
        
    max_w = max(weights_list) if weights_list else 1.0
    for i, name in enumerate(STRATEGY_NAMES):
        w = weights_list[i]
        bar = get_ascii_bar(w, max_w, width=15)
        weights_section += f"| **{name}** | {w*100:.1f}% | `{bar}` |\n"

    # Strategy Attribution Table
    attribution_rows = ""
    if stats:
        for name in STRATEGY_NAMES:
            perf = stats["strategy_performance"][name]
            pnl_val = perf["pnl"]
            pnl_str = f"€{pnl_val:+.2f}"
            wr_str = f"{perf['win_rate']*100:.1f}%" if perf["trades"] > 0 else "-"
            attribution_rows += f"| {name} | {perf['trades']} | {wr_str} | {pnl_str} |\n"
    else:
        attribution_rows = "| - | - | - | - |\n"

    # Ticker Breakdown Table
    ticker_breakdown_rows = ""
    ticker_breakdown = stats.get("ticker_breakdown", {})
    if ticker_breakdown:
        for sym in sorted(ticker_breakdown.keys()):
            data = ticker_breakdown[sym]
            pnl_val = data["pnl"]
            pnl_str = f"€{pnl_val:+.2f}"
            wr_str = f"{data['win_rate']*100:.1f}%" if data["trades"] > 0 else "-"
            ticker_breakdown_rows += f"| {sym} | {data['trades']} | {wr_str} | {pnl_str} |\n"
    else:
        ticker_breakdown_rows = "| - | - | - | - |\n"

    # Best / Worst Trades
    best_trade_str = "N/A"
    worst_trade_str = "N/A"
    if stats.get("best_trade"):
        bt = stats["best_trade"]
        best_trade_str = f"**{bt['symbol']}** ({bt['direction']}) - Exit PnL: **€{bt['pnl']:.2f}** ({bt['pnl_percent']*100:+.2f}%) via *{bt['exit_reason']}*"
    if stats.get("worst_trade"):
        wt = stats["worst_trade"]
        worst_trade_str = f"**{wt['symbol']}** ({wt['direction']}) - Exit PnL: **€{wt['pnl']:.2f}** ({wt['pnl_percent']*100:+.2f}%) via *{wt['exit_reason']}*"

    # Trade summary text
    trade_count = stats.get("total_trades", 0)
    win_rate = stats.get("win_rate", 0.0) * 100
    profit_factor = stats.get("profit_factor", 0.0)
    pf_str = f"{profit_factor:.2f}" if profit_factor != float('inf') else "∞"
    
    # ASCII sparkline or summary chart
    pnl_chart_str = ""
    if stats and trade_count > 0:
        # Show cumulative balance progression
        cum_bal = starting_bal
        pnl_chart_str = "\n### Cumulative Balance Progression\n"
        pnl_chart_str += "| Trade # | Ticker | Side | Net PnL | Portfolio Balance |\n"
        pnl_chart_str += "| --- | --- | --- | --- | --- |\n"
        pnl_chart_str += f"| Start | - | - | - | €{starting_bal:.2f} |\n"
        for idx, t in enumerate(trades):
            cum_bal += t["pnl"]
            pnl_chart_str += f"| {idx+1} | {t['symbol']} | {t['direction']} | €{t['pnl']:+.2f} | €{cum_bal:.2f} |\n"

    # Load weekly sentiment optimization report if it exists
    sentiment_opt_section = ""
    opt_report_path = os.path.join(BLOG_DIR, "daily_summaries", "weekly_sentiment_optimization.md")
    if os.path.exists(opt_report_path):
        try:
            with open(opt_report_path, "r") as f:
                sentiment_opt_section = "\n" + f.read() + "\n---\n"
        except Exception:
            pass

    # Load weekly self-improvement report if it exists
    self_improvement_section = ""
    imp_report_path = os.path.join(BLOG_DIR, "daily_summaries", "weekly_self_improvement.md")
    if os.path.exists(imp_report_path):
        try:
            with open(imp_report_path, "r") as f:
                self_improvement_section = "\n" + f.read() + "\n---\n"
        except Exception:
            pass

    template = f"""# Weekly Performance Log: NexusTrader Algorithmic Operations
**Reporting Period:** {date_str}  
**System Status:** ACTIVE 🟢  
{op_badge}

Welcome to the weekly performance report of **NexusTrader**, a self-learning quantitative trading bot driven by an ensemble of technical strategies and optimized in real-time by a Policy Gradient Neural Network.

Below is an extensive breakdown of the system's performance, resource allocations, neural network adaptations, and trading diagnostics.

---

## 📊 Executive Portfolio Summary

| Metric | Value |
| :--- | :--- |
| **Current Account Equity** | **€{current_bal:.2f}** |
| **Starting Balance (Week Start)** | €{starting_bal:.2f} |
| **Net PnL (Euros)** | **€{total_pnl:+.2f}** |
| **Weekly Return (%)** | **{return_pct:+.2f}%** |
| **Risk Profile Configuration** | `{risk_mode}` |
| **Active Trade Count** | {trade_count} |
| **Overall System Win Rate** | **{win_rate:.1f}%** |
| **Profit Factor** | **{pf_str}** |

---

## 💼 Portfolio Asset Performance Breakdown
Performance metrics segmented by individual portfolio asset ticker:

| Asset Ticker | Trades Executed | Win Rate | Net Asset PnL |
| :--- | :--- | :--- | :--- |
{ticker_breakdown_rows}

---

## 🧠 Neural Policy Network Allocations
The Policy Gradient Neural Network dynamically distributes weights among individual strategies on each tick. It monitors indicators (OU market regime parameters, RSI, Bollinger position, ATR volatility, and win rate trend) to shift allocations toward strategies that perform best in current conditions.

Current baseline weights computed by the neural network:

| Strategy | Allocation Weight | Visual Distribution |
| :--- | :--- | :--- |
{weights_section}

---
{sentiment_opt_section}
{self_improvement_section}
## 📈 Detailed Strategy Attribution
This table highlights how individual strategies contributed to the trades opened during this period. A strategy is considered "aligned" if its voting signal matches the entry direction of the executed trade.

| Strategy Component | Aligned Trades | Win Rate When Aligned | Net Strategy PnL |
| :--- | :--- | :--- | :--- |
{attribution_rows}

---

## 🔍 Trade Diagnostics & Extremes

* 🟢 **Best Execution:** {best_trade_str}
* 🔴 **Worst Drawdown:** {worst_trade_str}

{pnl_chart_str}

---

## 💡 System Insights & Quantitative Summary

1. **Regime Switching Adaptability:** The system uses Ornstein-Uhlenbeck process parameters to distinguish between trending and mean-reverting states. Under mean-reverting regimes, the neural network boosts weights for the **RSI Reversion**, **BB Breakout**, and **Psych Sweep** components, while suppressing trend-following metrics.
2. **Online Policy Gradient Optimization:** After each trade closes, the neural network runs a policy gradient backward pass using trade PnL as the reward. Successful trades strengthen the neural pathways of the voting strategies, while losing trades penalize their weights.
3. **Volatility-Adjusted Risk Sizing:** Take-profit and stop-loss boundaries are automatically computed using Average True Range (ATR) multiples. Sizing is governed by the Kelly Criterion (scaled by a fraction based on the risk profile), preventing catastrophic risk exposure.

---

## 🗺️ Quantitative Roadmap & Operational Plan
To optimize execution safety and target higher capital return frequencies, we are implementing a structured phased software roadmap:
1. **Diversified Multi-Asset Support (Active)**: We have transitioned the core loop to trade `ETH-EUR`, `SOL-EUR`, `BTC-EUR`, `DOGE-EUR`, and `XRP-EUR` concurrently under a single portfolio account.
2. **Limit Order Queue Simulation (Next Phase)**: To prevent execution slippage in live trading, we are implementing maker/taker transaction fee modelling and limit order fills based on tick high/low crossings.
3. **Daily Risk Safeguards & Circuit Breakers (Next Phase)**: Adding daily maximum drawdown boundaries (5% of daily start balance) that will automatically freeze the execution engines if breached, protecting the portfolio balance.

---
*Report generated automatically by the NexusTrader Blog Agent.*
"""
    return template

def query_gemini_api(api_key, context_prompt):
    """Queries Gemini 2.0 Flash API to write a witty, professional blog post."""
    try:
        logging.info("Sending request to Gemini API...")
        from quant_utils import query_gemini_robust
        return query_gemini_robust(api_key, context_prompt)
    except Exception as e:
        logging.error(f"Error querying Gemini API: {e}")
    return None

def write_blog_post(markdown_content, date_str):
    """Writes the markdown report to the blog directory and updates index."""
    os.makedirs(BLOG_DIR, exist_ok=True)
    
    filename = f"weekly_report_{date_str}.md"
    filepath = os.path.join(BLOG_DIR, filename)
    
    # Save the blog post
    with open(filepath, "w") as f:
        f.write(markdown_content)
    logging.info(f"Blog post written to: {filepath}")
    
    # Update README index (both README.md and index.md for GitHub Pages compatibility)
    index_path = os.path.join(BLOG_DIR, "README.md")
    existing_content = ""
    if os.path.exists(index_path):
        with open(index_path, "r") as f:
            existing_content = f.read()
            
    header = "# 📓 NexusTrader Operations Log\nWelcome to the operational blog for NexusTrader. Here you can track weekly system reports, neural network policy weight adaptations, and trade performance analytics.\n\n## 📋 Report Index\n"
    
    # Parse existing links
    links = []
    if existing_content:
        for line in existing_content.split("\n"):
            if "- [" in line and ".md)" in line:
                if filename not in line:  # Avoid duplicating the current file link
                    links.append(line)
                    
    # Insert new link at the top of the index (use relative path for GitHub Pages & repo viewer compatibility)
    new_link = f"- [{date_str} - Weekly Performance Log]({filename})"
    links.insert(0, new_link)
    
    new_index_content = header + "\n".join(links) + "\n"
    
    # Write to README.md
    with open(index_path, "w") as f:
        f.write(new_index_content)
        
    # Write to index.md for Jekyll/GitHub Pages
    index_md_path = os.path.join(BLOG_DIR, "index.md")
    with open(index_md_path, "w") as f:
        f.write(new_index_content)
        
    logging.info(f"Blog indices updated (README.md and index.md)")

def push_to_github():
    """Stages the generated blog posts and pushes to the GitHub remote repository."""
    import subprocess
    logging.info("Tying blog update back to the repository (git push)...")
    try:
        # Run git status/add first
        subprocess.run(["git", "add", "blog/"], check=True)
        # Check if there are staged changes to commit
        status = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True)
        if status.returncode != 0:
            # There are changes to commit
            date_str = datetime.datetime.now().strftime("%Y-%m-%d")
            subprocess.run(["git", "commit", "-m", f"Weekly bot progress report {date_str} [automated]"], check=True)
            subprocess.run(["git", "push", "origin", "main"], check=True)
            logging.info("Successfully pushed weekly blog updates to GitHub remote origin/main.")
        else:
            logging.info("No new blog changes to push.")
    except Exception as e:
        logging.error(f"Failed to push blog update to GitHub: {e}")

def load_config():
    """Loads trading configuration from config.json."""
    config_path = os.path.expanduser("~/.nexustrader/config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error loading config.json: {e}")
    return {}

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="NexusTrader Weekly Blog Agent")
    parser.add_argument("--mock", action="store_true", help="Insert mock trade data into SQLite database before running")
    parser.add_argument("--days", type=int, default=7, help="Number of days of history to include in the report")
    args = parser.parse_args()

    if args.mock:
        insert_mock_data()
        
    # 1. Run the news sentiment source optimizer before generating the weekly report
    try:
        from weekly_optimizer import optimize_sentiment_weights
        optimize_sentiment_weights()
    except Exception as e:
        logging.error(f"Error running weekly sentiment source optimization: {e}")
        
    # 2. Run the weekly self-improvement strategy parameter optimizer
    try:
        from self_improvement_agent import run_self_improvement
        run_self_improvement()
    except Exception as e:
        logging.error(f"Error running weekly self-improvement optimization: {e}")
        
    settings = load_settings()
    
    # Check if blog agent is disabled in config
    blog_enabled = settings.get("blog_enabled", "true")
    if blog_enabled == "false":
        logging.info("Weekly Blog Agent is currently DISABLED in configuration. Exiting.")
        sys.exit(0)
        
    # Determine the system operational mode
    config = load_config()
    trading_mode = config.get("trading_mode", "paper")
    
    if args.mock:
        op_mode = "MOCK_DEMO"
        op_mode_desc = "Synthetic Sample Data (Mock Test Data)"
    elif trading_mode == "live":
        op_mode = "LIVE_CAPITAL"
        op_mode_desc = "Live Capital Trading (Real Money at Risk)"
    else:
        op_mode = "PAPER_TRADING"
        op_mode_desc = "Paper Trading (Live Simulation on Real-time Market Data, No Risk)"
        
    trades = load_trades(days_limit=args.days)
    
    # Define reporting window
    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(days=args.days)
    date_str = end_date.strftime("%Y_%m_%d")
    
    stats = analyze_weekly_performance(trades)
    
    # Generate baseline template containing all data tables
    base_markdown = generate_report_template(stats, settings, start_date, end_date, op_mode)
    
    # Check if Gemini API key is available in DB or Environment
    api_key = settings.get("blog_gemini_api_key", "").strip()
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        
    ai_enabled = settings.get("blog_ai_enabled", "false") == "true"
    
    blog_created = False
    
    if ai_enabled and api_key:
        db_prompt = settings.get("prompt_blog_agent")
        if not db_prompt:
            db_prompt = """You are an expert quantitative researcher, financial blogger, and algorithmic trading editor. 
Our mission is to help the NexusTrader bot scale to a target of earning $1,000 USD a day.

Rewrite the raw report data into a highly detailed, witty, professional, and engaging market-commentary blog post.
Analyze metrics, explain profit factors, detail policy weights, and discuss the bot's mathematical evolution.
Keep all quantitative tables intact."""

        prompt = f"""{db_prompt}

Reporting Context:
- The operational mode for this reporting period is: {op_mode_desc}. (Make sure to clearly and explicitly mention this mode in your opening commentary and executive summary).
- Raw data and structured markdown for this week's report:
```markdown
{base_markdown}
```"""
        styled_markdown = query_gemini_api(api_key, prompt)
        if styled_markdown:
            write_blog_post(styled_markdown, date_str)
            print("Blog post created successfully with AI styling!")
            blog_created = True
            
            # Run meta-prompt optimization to evolve Blogger prompt
            optimize_own_prompt(settings, api_key)
            
    if not blog_created:
        # Fallback to base markdown if API fails, key is missing, or AI is disabled
        write_blog_post(base_markdown, date_str)
        print("Blog post created successfully with data template!")
        
    # Check if Git Push is enabled to publish public blog updates
    git_push_enabled = settings.get("blog_git_push_enabled", "true") == "true"
    if git_push_enabled:
        push_to_github()

def optimize_own_prompt(settings, api_key):
    try:
        db_prompt = settings.get("prompt_blog_agent", "")
        
        # Read PhD Quant and Developer logs from weekly_self_improvement.md
        quant_summary = ""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        report_path = os.path.join(base_dir, "blog", "daily_summaries", "weekly_self_improvement.md")
        if os.path.exists(report_path):
            with open(report_path, "r") as f:
                quant_summary = f.read()[-4000:]
                
        prompt = f"""
You are the Blogger agent for the NexusTrader self-learning trading bot system. 
Part of your meta-cognition routine is to evaluate your own prompt template and optimize it based on:
1. Your current prompt template.
2. The outputs of the PhD Quant Optimizer agent (which optimizes parameters).
3. The outputs of the AI Software Developer agent (which builds new features).

Our mission is to make the bot consistently earn $1,000 USD a day.

Current Prompt Template:
\"\"\"{db_prompt}\"\"\"

Recent Quant & Developer Logs:
\"\"\"{quant_summary}\"\"\"

Critically analyze this context. Redesign your own prompt template to focus it even more tightly on achieving $1,000 USD/day, ensuring it asks for engaging market commentary and keeps all tables intact.
Return ONLY a JSON block containing the key "revised_prompt_blog_agent" with your improved prompt template as the value (do not include markdown wrappers like ```json).
"""
        from quant_utils import query_gemini_robust
        raw_text = query_gemini_robust(api_key, prompt)
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            raw_text = raw_text.strip()
            
            res_data = json.loads(raw_text)
            revised = res_data.get("revised_prompt_blog_agent")
            if revised:
                # Save setting helper
                import sqlite3
                conn = sqlite3.connect(os.path.expanduser("~/.nexustrader/nexustrader.db"))
                c = conn.cursor()
                c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("prompt_blog_agent", str(revised)))
                conn.commit()
                conn.close()
                print("Meta-optimization: Successfully updated prompt_blog_agent in database settings.")
                return revised
    except Exception as e:
        print(f"Failed to meta-optimize prompt_blog_agent: {e}")
    return None

