import os
import json
import logging
import database as _db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def run_monthly_researcher():
    logging.info("Starting monthly Quantitative Strategy Researcher Agent session...")
    
    try:
        # Load settings
        conn = _db.get_db_connection()
        conn.row_factory = __import__('sqlite3').Row
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
            
        report_lines.append("\n### Monthly Strategy Researcher Evaluation (via OpenClaw Gateway):")

        db_prompt = settings.get("prompt_monthly_researcher")
        if not db_prompt:
            db_prompt = "You are a quantitative strategy researcher. Propose 2-3 new alpha-generating strategies or improvements for NexusTrader. Use advanced mathematical tools (OU processes, Kalman filters, fractional Kelly, cointegration). Output valid JSON with keys 'proposed_strategies' and 'parameter_tuning'."
            c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("prompt_monthly_researcher", db_prompt))
            conn.commit()

        prompt = db_prompt + "\n\nCurrent Strategy Roster:\n" + json.dumps(strategies_info, indent=2) + "\n\nRecent Trades:\n" + json.dumps(recent_trades, indent=2) + "\n\nTarget: $1,000/day profit."

        from openclaw_bridge import query_openclaw, extract_json_block

        try:
            raw_advice = query_openclaw(prompt, agent_name="quant", max_tokens=4096)
        except Exception as e_ai:
            logging.error(f"OpenClaw call failed for MonthlyResearcher: {e_ai}")
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
                tuning = adjustments.get("parameter_tuning", {})
                for key, val in tuning.items():
                    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (f"quant_research_{key}", str(val)))
                    report_lines.append(f"\nAuto-Applied: quant_research_{key} = {val}")
            except Exception as e_json:
                logging.error(f"Failed to parse JSON: {e_json}")

        # Meta-prompt optimization via OpenClaw
        try:
            meta_prompt = f"Evaluate and rewrite your promoter prompt. Current: {db_prompt}. Return ONLY JSON with key 'revised_prompt_monthly_researcher' (no markdown)."
            raw_text = query_openclaw(meta_prompt, agent_name="quant", max_tokens=2048)
            res_data = extract_json_block(raw_text)
            if res_data and isinstance(res_data, dict):
                revised = res_data.get("revised_prompt_monthly_researcher")
                if revised:
                    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('prompt_monthly_researcher', ?)", (revised,))
                    report_lines.append("\nMeta-Optimization: updated monthly researcher prompt.")
        except Exception as e_meta:
            logging.error(f"Failed to meta-optimize: {e_meta}")

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
