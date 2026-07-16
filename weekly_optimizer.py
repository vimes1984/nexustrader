import os
import json
import sqlite3
import numpy as np
import logging

DB_PATH = os.path.expanduser("~/.nexustrader/nexustrader.db")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def optimize_sentiment_weights():
    logging.info("Starting weekly sentiment source optimization...")
    if not os.path.exists(DB_PATH):
        logging.warning("Database file not found. Skipping optimization.")
        return
        
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        # Load completed trades
        c.execute("SELECT pnl, pnl_percent, sentiment_sources, direction FROM trades")
        rows = c.fetchall()
        
        if len(rows) < 3:
            logging.info(f"Insufficient trade history ({len(rows)} trades). Need at least 3 trades to compute correlations. Keeping default weights.")
            conn.close()
            return
            
        # Parse data
        sources = ["cointelegraph", "cryptobriefing", "beincrypto", "reddit"]
        source_pnl_correlations = {s: [] for s in sources}
        
        for row in rows:
            pnl_pct = float(row["pnl_percent"])
            direction = row["direction"]
            
            # Extract sentiment sources
            sent_str = row["sentiment_sources"]
            if not sent_str:
                continue
                
            try:
                sources_dict = json.loads(sent_str)
            except Exception:
                continue
                
            for src in sources:
                score = sources_dict.get(src, 0.0)
                if score is not None and score != 0.0:
                    # Direction alignment: if direction is SELL, a negative sentiment score is "correct"
                    # So we align sentiment direction with position direction:
                    aligned_score = score if direction == "BUY" else -score
                    source_pnl_correlations[src].append((aligned_score, pnl_pct))
                    
        # Compute correlations
        new_weights = {}
        report_lines = []
        report_lines.append("## Weekly Sentiment Source Attribution & Optimization\n")
        report_lines.append("| News/Social Source | Sample Count | Correlation (PnL) | Active Weight |")
        report_lines.append("| --- | --- | --- | --- |")
        
        for src in sources:
            pairs = source_pnl_correlations[src]
            if len(pairs) >= 3:
                scores_arr = np.array([p[0] for p in pairs])
                pnls_arr = np.array([p[1] for p in pairs])
                
                # Pearson Correlation coefficient
                std_scores = np.std(scores_arr)
                std_pnls = np.std(pnls_arr)
                if std_scores > 1e-6 and std_pnls > 1e-6:
                    correlation = float(np.corrcoef(scores_arr, pnls_arr)[0, 1])
                else:
                    correlation = 0.0
            else:
                correlation = 0.0  # default
                
            # Map correlation to weight (sigmoid-like scaling: weight bounds [0.1, 2.0])
            # A correlation of 0.0 maps to 1.0. Perfect positive correlation (1.0) maps to 2.0. Negative correlation maps towards 0.1.
            weight = float(1.0 + correlation)
            weight = max(0.1, min(2.0, weight))
            new_weights[src] = weight
            
            # Save new weights in database settings
            c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (f"feed_weight_{src}", f"{weight:.4f}"))
            
            report_lines.append(f"| **{src}** | {len(pairs)} | {correlation:+.4f} | **{weight:.4f}** |")
            
        conn.commit()
        conn.close()
        
        # Add report to blog daily summary or a dedicated optimizer summary
        report_content = "\n".join(report_lines)
        logging.info("Sentiment weights optimized and saved to SQLite settings:\n" + report_content)
        
        # Save optimizer report to blog
        blog_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blog", "daily_summaries")
        if os.path.exists(blog_dir):
            report_path = os.path.join(blog_dir, "weekly_sentiment_optimization.md")
            with open(report_path, "w") as f:
                f.write(report_content)
            logging.info("Weekly sentiment optimizer page saved to blog.")
                
    except Exception as e:
        logging.error(f"Error optimizing sentiment weights: {e}")

if __name__ == "__main__":
    optimize_sentiment_weights()
