import datetime
import os
import json
import logging
import subprocess
import database as _db

# Paths
BLOG_DIR = os.path.expanduser("~/nexustrader/blog")
DAILY_DIR = os.path.join(BLOG_DIR, "daily_summaries")

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def get_db_connection():
    return _db.get_db_connection()

def load_daily_trades():
    """Loads trades closed in the last 24 hours."""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # 24 hours ago
    cutoff = datetime.datetime.now() - datetime.timedelta(days=1)
    cutoff_ts = cutoff.timestamp()
    
    c.execute("SELECT * FROM trades WHERE exit_time >= ? ORDER BY exit_time DESC", (cutoff_ts,))
    rows = c.fetchall()
    conn.close()
    
    trades = []
    for r in rows:
        t = dict(r)
        # Parse strategy signals
        if t.get("strategy_signals"):
            try:
                t["strategy_signals"] = json.loads(t["strategy_signals"])
            except Exception:
                t["strategy_signals"] = []
        else:
            t["strategy_signals"] = []
        trades.append(t)
    return trades

def get_git_commits():
    """Gets commits made in the last 24 hours to summarize developer work."""
    try:
        res = subprocess.run(
            ["git", "log", "--since=24.hours", "--oneline"],
            capture_output=True,
            text=True,
            cwd=os.path.expanduser("~/nexustrader")
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip().split("\n")
    except Exception as e:
        logging.error(f"Error fetching git commits: {e}")
    return []

def generate_daily_report():
    """Generates the daily summary report and saves it to the blog directory."""
    if not os.path.exists(DAILY_DIR):
        os.makedirs(DAILY_DIR)
        
    trades = load_daily_trades()
    commits = get_git_commits()
    
    now = datetime.datetime.now()
    date_title = now.strftime("%B %d, %Y")
    filename_date = now.strftime("%Y_%m_%d")
    
    # Calculate stats
    total_trades = len(trades)
    wins = len([t for t in trades if t["pnl"] > 0])
    total_pnl = sum([t["pnl"] for t in trades])
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
    
    # Build markdown
    md = f"""# Daily Algorithmic Summary: {date_title}
**System Status:** ACTIVE 🟢  
**Report Time:** {now.strftime('%H:%M:%S')}  

---

## 📈 Daily Performance Metrics
* **Trades Closed (Last 24h):** {total_trades}
* **Daily Win Rate:** {win_rate:.1f}%
* **Net Daily PnL:** €{total_pnl:+.2f}

### Closed Trades List
"""
    if total_trades > 0:
        md += "| Asset | Side | Entry Price | Exit Price | Net PnL | Exit Reason |\n"
        md += "| --- | --- | --- | --- | --- | --- |\n"
        for t in trades:
            md += f"| {t['symbol']} | {t['direction']} | €{t['entry_price']:.2f} | €{t['exit_price']:.2f} | €{t['pnl']:+.2f} | {t['exit_reason']} |\n"
    else:
        md += "_No trades were closed in the last 24 hours._\n"
        
    md += "\n---\n\n## 🛠️ Software Updates & Code Contributions (Last 24h)\n"
    if commits:
        for c in commits:
            md += f"* `{c}`\n"
    else:
        md += "_No codebase modifications recorded today._\n"
        
    md += """
---
*Daily summary generated automatically by the NexusTrader Daily Reporter.*
"""
    
    # Write summary file
    summary_path = os.path.join(DAILY_DIR, f"daily_summary_{filename_date}.md")
    with open(summary_path, "w") as f:
        f.write(md)
        
    logging.info(f"Daily report generated: {summary_path}")
    
    # Update index file
    update_blog_indexes(filename_date, date_title)
    
    # Push updates to GitHub
    push_to_github(filename_date)

def update_blog_indexes(filename_date, date_title):
    """Updates the blog index pages to link to the new daily summary."""
    index_md_path = os.path.join(BLOG_DIR, "index.md")
    readme_md_path = os.path.join(BLOG_DIR, "README.md")
    
    # We want to insert the daily link at the top of the 'Daily Summaries' section
    for filepath in [index_md_path, readme_md_path]:
        if not os.path.exists(filepath):
            continue
            
        with open(filepath, "r") as f:
            content = f.read()
            
        new_link = f"* [Daily Summary — {date_title}](daily_summaries/daily_summary_{filename_date}.md)\n"
        
        # Check if already exists to prevent duplicate links
        if f"daily_summary_{filename_date}.md" in content:
            continue
            
        if "## 📅 Daily Summaries" in content:
            parts = content.split("## 📅 Daily Summaries")
            header = parts[0] + "## 📅 Daily Summaries\n"
            rest = parts[1].strip()
            
            # If the rest starts with a list, we place it right after the header
            updated_content = header + new_link + rest
        else:
            # Append to the bottom
            updated_content = content.strip() + "\n\n## 📅 Daily Summaries\n" + new_link
            
        with open(filepath, "w") as f:
            f.write(updated_content)

def push_to_github(filename_date):
    """Pushes daily summary files back to the public repository."""
    try:
        subprocess.run(["git", "add", "blog/"], check=True)
        # Check if there are staged changes
        status = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True)
        if status.returncode != 0:
            subprocess.run(["git", "commit", "-m", f"Daily operations summary {filename_date} [automated]"], check=True)
            subprocess.run(["git", "push", "origin", "main"], check=True)
            logging.info("Successfully pushed daily summary to GitHub.")
        else:
            logging.info("No daily report changes to push.")
    except Exception as e:
        logging.error(f"Failed to push daily summary: {e}")

if __name__ == "__main__":
    generate_daily_report()
