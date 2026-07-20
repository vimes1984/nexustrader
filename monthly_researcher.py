import os
import json
import sqlite3
import logging
import database

DB_PATH = os.path.expanduser("~/.nexustrader/nexustrader.db")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def run_monthly_researcher():
    logging.info("Starting monthly Quantitative Strategy Researcher Agent session...")
    
    if not os.path.exists(DB_PATH):
        logging.warning("Database not found. Skipping research optimization.")
        return "Database not found."
        
    try:
        # Load settings
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        # Load settings dict
        c.execute("SELECT key, value FROM settings")
        settings = {r[0]: r[1] for r in c.fetchall()}
        
        # Load recent trades to analyze what worked and what didn't
        c.execute("SELECT id, symbol, direction, entry_price, exit_price, pnl, pnl_percent, exit_reason FROM trades ORDER BY id DESC LIMIT 50")
        recent_trades = [dict(r) for r in c.fetchall()]
        
        # Load active strategy list from strategy_engine
        try:
            import strategy_engine
            ensemble = strategy_engine.StrategyEnsemble()
            strategies_info = [{"name": s.name, "regime": getattr(s, "regime", "general")} for s in ensemble.strategies]
        except Exception as e:
            logging.error(f"Error loading strategy info: {e}")
            strategies_info = []

        report_lines = []
        report_lines.append("## 📈 Monthly Quantitative Strategy Research & Alpha Generation Report")
        report_lines.append(f"Processed performance metrics across **{len(recent_trades)}** recent trades.")
        report_lines.append("\n### Active Strategy Roster:")
        for s in strategies_info:
            report_lines.append(f"* **{s['name']}** (Regime: `{s['regime']}`)")
            
        gemini_api_key = settings.get("blog_gemini_api_key", "").strip()
        ai_enabled = settings.get("blog_ai_enabled", "false") == "true"
        
        if ai_enabled and gemini_api_key:
            report_lines.append("\n### 🧠 Senior Quant Strategy Researcher Evaluation & Mathematical Recommendations:")
            
            db_prompt = settings.get("prompt_monthly_researcher")
            if not db_prompt:
                db_prompt = """You are a senior Quantitative Strategy Researcher and PhD Mathematician.
Our core objective is to research, propose, and refine algorithmic trading strategies to safely and consistently scale NexusTrader earnings to achieve our $1,000 USD/day target.

Evaluate the current strategy roster and recent trade metrics. Propose 2-3 new alpha-generating strategies or improvements utilizing advanced mathematical tools (e.g. Ornstein-Uhlenbeck processes, Kalman filters, stochastic calculus, machine learning, fractional Kelly adjustments, cointegration).

At the very end of your response, output recommended strategy parameters and new strategy proposals strictly in a JSON block (wrapped in ```json):
```json
{
  "proposed_strategies": [
    {
      "name": "string",
      "regime": "trend" | "mean_reversion",
      "mathematical_basis": "string"
    }
  ],
  "parameter_tuning": {
    "target_asset_kelly_multiplier": float,
    "volatility_breakout_threshold": float
  }
}
```"""
                c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("prompt_monthly_researcher", db_prompt))
                conn.commit()
                
            prompt = f"""{db_prompt}

Current Strategy Roster:
{json.dumps(strategies_info, indent=2)}

Recent Live Trade Performance Analysis:
{json.dumps(recent_trades, indent=2) if recent_trades else '[]'}

Core Target: $1,000 USD average daily profit.
"""
            from quant_utils import query_gemini_robust
            
            # Audit trail logger wrapper
            try:
                raw_advice = query_gemini_robust(gemini_api_key, prompt)
                database.log_agent_run("MonthlyResearcher", "gemini", "gemini-1.5-flash", prompt, raw_advice, "success")
            except Exception as e_ai:
                database.log_agent_run("MonthlyResearcher", "gemini", "gemini-1.5-flash", prompt, str(e_ai), "failed")
                raise e_ai

            advice_clean = raw_advice
            json_block = ""
            if "```json" in raw_advice:
                parts = raw_advice.split("```json")
                advice_clean = parts[0]
                json_block = parts[1].split("```")[0].strip()
                
            report_lines.append(advice_clean)
            
            if json_block:
                try:
                    adjustments = json.loads(json_block)
                    # Auto-apply parameters or proposed strategy log updates
                    tuning = adjustments.get("parameter_tuning", {})
                    for key, val in tuning.items():
                        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (f"quant_research_{key}", str(val)))
                        report_lines.append(f"\n📊 **Auto-Applied Parameter**: quant_research_{key} adjusted to `{val}`")
                except Exception as e_json:
                    logging.error(f"Failed to parse JSON adjustments: {e_json}")
                    
            # 6. Perform Meta-Prompt Optimization for Monthly Researcher
            try:
                meta_prompt = f"""You are the Monthly Strategy Researcher agent. Part of your meta-cognition routine is to evaluate your own prompt template and optimize it based on:
1. Your current prompt template.
2. The recent live trade performance.

Our mission is to scale the bot to earn $1,000 USD a day.

Current Prompt Template:
\"\"\"{db_prompt}\"\"\"

Critically analyze this context. Redesign your own prompt template to focus it even more tightly on achieving $1,000 USD/day and discovering new alpha models.
Return ONLY a JSON block containing the key "revised_prompt_monthly_researcher" with your improved prompt template as the value (do not include markdown wrappers like ```json).
"""
                raw_text = query_gemini_robust(gemini_api_key, meta_prompt)
                if raw_text.startswith("```json"):
                    raw_text = raw_text[7:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
                raw_text = raw_text.strip()
                
                res_data = json.loads(raw_text)
                revised = res_data.get("revised_prompt_monthly_researcher")
                if revised:
                    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('prompt_monthly_researcher', ?)", (revised,))
                    report_lines.append(f"\n🧠 **AI Prompt Meta-Optimization**: Successfully evolved Monthly Strategy Researcher prompt template.")
            except Exception as e_meta:
                logging.error(f"Failed to meta-optimize prompt_monthly_researcher: {e_meta}")
                
        conn.commit()
        conn.close()
        
        # Save/Append report to blog/daily_summaries/monthly_quant_research.md
        report_content = "\n".join(report_lines)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        blog_dir = os.path.join(base_dir, "blog", "daily_summaries")
        if os.path.exists(blog_dir):
            report_path = os.path.join(blog_dir, "monthly_quant_research.md")
            with open(report_path, "w") as f:
                f.write(report_content)
            logging.info("Monthly quant researcher report saved to blog.")
            
        return "Success! " + report_content
    except Exception as e:
        logging.error(f"Error running monthly researcher: {e}")
        return f"Error: {e}"

if __name__ == "__main__":
    print(run_monthly_researcher())
