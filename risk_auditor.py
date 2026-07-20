import os
import sqlite3
import json
import urllib.request
import logging
import subprocess

DB_PATH = os.path.expanduser("~/.nexustrader/nexustrader.db")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def load_settings():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    c.execute("SELECT key, value FROM settings")
    rows = c.fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}

def save_setting(key, value):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def run_risk_audit(trigger_deploy: bool = False):
    logging.info("Starting Quantitative Portfolio Risk Audit...")
    settings = load_settings()
    gemini_api_key = settings.get("blog_gemini_api_key", "").strip()
    ai_enabled = settings.get("blog_ai_enabled", "false") == "true"
    
    if not gemini_api_key or not ai_enabled:
        logging.warning("Gemini API key is not configured or AI is disabled. Cannot run Risk Audit.")
        return "Gemini API key is not configured or AI is disabled."
        
    db_prompt = settings.get("prompt_risk_auditor")
    if not db_prompt:
        db_prompt = """You are a highly conservative Quantitative Portfolio Risk Auditor.
Our goal is to verify that risk exposures, asset correlations, and tail drawdowns strictly protect capital while targeting $1,000 USD/day.
Critique leverage levels, daily drawdown limits, and portfolio correlation matrices.
At the very end of your response, output a strict JSON block with risk parameter recommendations:
```json
{
  "recommended_max_daily_loss": float,
  "recommended_loss_cooldown_hours": float
}
```"""

    # Read trades from DB for risk auditing
    recent_trades = []
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT id, symbol, direction, pnl, exit_reason FROM trades ORDER BY id DESC LIMIT 20")
        recent_trades = [dict(r) for r in c.fetchall()]
        conn.close()
    except Exception as e:
        logging.error(f"Error querying trades for risk audit: {e}")

    prompt = f"""{db_prompt}

Current Risk Settings:
- Max Daily Loss Drawdown Limit: {settings.get("max_daily_drawdown", "5.0")}%
- Loss Cooldown Hold Period: {settings.get("loss_cooldown_hours", "4.0")} hours

Recent trades telemetry:
{json.dumps(recent_trades, indent=2) if recent_trades else '[]'}
"""
    
    report_lines = ["\n## 🛡️ Portfolio Risk Audit Report"]
    
    try:
        logging.info("Requesting Risk Audit evaluation from Gemini...")
        from openclaw_bridge import query_openclaw, extract_json_block
        advice_text = query_openclaw(prompt, agent_name="risk")
        
        advice_clean = advice_text
        json_block = ""
        if "```json" in advice_text:
            parts = advice_text.split("```json")
            advice_clean = parts[0]
            json_block = parts[1].split("```")[0].strip()
            
        report_lines.append(advice_clean)
        
        if json_block:
            adjustments = json.loads(json_block)
            r_drawdown = adjustments.get("recommended_max_daily_loss")
            r_cooldown = adjustments.get("recommended_loss_cooldown_hours")
            
            if r_drawdown is not None:
                save_setting("max_daily_drawdown", str(r_drawdown))
                report_lines.append(f"\n📊 **Auto-Applied Setting**: Max Daily Drawdown adjusted to `{r_drawdown}%`")
            if r_cooldown is not None:
                save_setting("loss_cooldown_hours", str(r_cooldown))
                report_lines.append(f"\n📊 **Auto-Applied Setting**: Loss Cooldown adjusted to `{r_cooldown} hours`")
    except Exception as e:
        logging.error(f"API call failed: {e}")
        return f"API call failed: {e}"
        
    # Perform Meta-Prompt Optimization for Risk Auditor Prompt
    try:
        dev_summary = ""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        report_path = os.path.join(base_dir, "blog", "daily_summaries", "weekly_self_improvement.md")
        if os.path.exists(report_path):
            with open(report_path, "r") as f:
                dev_summary = f.read()[-3000:]
                
        meta_prompt = f"""
You are the Portfolio Risk Auditor agent. Part of your meta-cognition routine is to evaluate your own prompt template and optimize it based on:
1. Your current prompt template.
2. The outputs of the PhD Quant Optimizer agent.
3. The outputs of the AI Software Developer agent.

Our mission is to scale the bot to earn $1,000 USD a day safely.

Current Prompt Template:
\"\"\"{db_prompt}\"\"\"

Recent Developer/Quant logs:
\"\"\"{dev_summary}\"\"\"

Critically analyze this context. Redesign your own prompt template to focus it even more tightly on achieving $1,000 USD/day, ensuring it asks for correct hedging checks and keeps its final settings JSON format.
Return ONLY a JSON block containing the key "revised_prompt_risk_auditor" with your improved prompt template as the value (do not include markdown wrappers like ```json).
"""
        from openclaw_bridge import query_openclaw, extract_json_block
        raw_text = query_openclaw(meta_prompt, agent_name="risk", max_tokens=2048)
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()
        
        res_data = json.loads(raw_text)
        revised = res_data.get("revised_prompt_risk_auditor")
        if revised:
            save_setting("prompt_risk_auditor", revised)
            report_lines.append(f"\n🛡️ **AI Prompt Meta-Optimization**: Evolved Risk Auditor prompt template closer to target.")
    except Exception as e:
        logging.error(f"Failed to meta-optimize prompt_risk_auditor: {e}")
        
    report_content = "\n".join(report_lines)
    
    # Save/Append report to blog/daily_summaries/weekly_self_improvement.md
    if os.path.exists(os.path.join(base_dir, "blog", "daily_summaries")):
        report_path = os.path.join(base_dir, "blog", "daily_summaries", "weekly_self_improvement.md")
        try:
            with open(report_path, "a") as f:
                f.write("\n\n" + report_content)
            logging.info("Saved Risk Audit logs to blog summaries.")
        except Exception as e:
            logging.error(f"Failed to append Risk logs to blog summaries: {e}")
            
    # Trigger reload on Proxmox if requested
    if trigger_deploy:
        try:
            subprocess.run(["./deploy.sh"], timeout=30)
            logging.info("Deploy completed after Risk Audit.")
        except Exception as e:
            logging.error(f"Deploy execution failed: {e}")
        
    return f"Success! Risk Audit completed.\n\n" + report_content

if __name__ == "__main__":
    print(run_risk_audit(trigger_deploy=True))
