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

def run_nn_self_improvement(trigger_deploy: bool = False):
    logging.info("Starting Neural Network self-improvement session...")
    settings = load_settings()
    gemini_api_key = settings.get("blog_gemini_api_key", "").strip()
    ai_enabled = settings.get("blog_ai_enabled", "false") == "true"
    
    if not gemini_api_key or not ai_enabled:
        logging.warning("Gemini API key is not configured or AI is disabled. Cannot run NN self-improvement.")
        return "Gemini API key is not configured or AI is disabled."
        
    nn_lr = settings.get("nn_learning_rate", "0.15")
    nn_floor = settings.get("nn_weight_floor", "0.05")
    
    # Read recent trades from DB
    recent_trades = []
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT id, symbol, direction, entry_price, exit_price, pnl, exit_reason FROM trades ORDER BY id DESC LIMIT 15")
        recent_trades = [dict(r) for r in c.fetchall()]
        conn.close()
    except Exception as e:
        logging.error(f"Error querying trades: {e}")
        
    db_prompt = settings.get("prompt_nn_agent")
    if not db_prompt:
        db_prompt = """You are a world-class Deep Learning Engineer and Neuro-Symbolic Quantitative Researcher.
Our goal is to optimize the policy gradient neural network of the NexusTrader bot to enable it to safely scale earnings to $1,000 USD a day.
Critique the learning rate, weight floor, and policy network convergence based on the latest training steps.
At the very end of your response, output recommended setting adjustments strictly in a JSON block:
```json
{
  "recommended_nn_learning_rate": float,
  "recommended_nn_weight_floor": float
}
```"""

    prompt = f"""{db_prompt}

Current Neural Network Parameters:
- Hidden Dimension: 12
- Learning Rate: {nn_lr}
- Weight Floor: {nn_floor}

Recent closed trades for analysis:
{json.dumps(recent_trades, indent=2) if recent_trades else '[]'}
"""
    
    report_lines = ["\n## 🧠 Neural Network Policy Self-Improvement Report"]
    
    try:
        logging.info("Requesting Neural Network evaluation from Gemini...")
        from quant_utils import query_gemini_robust
        advice_text = query_gemini_robust(gemini_api_key, prompt)
        
        advice_clean = advice_text
        json_block = ""
        if "```json" in advice_text:
            parts = advice_text.split("```json")
            advice_clean = parts[0]
            json_block = parts[1].split("```")[0].strip()
            
        report_lines.append(advice_clean)
        
        if json_block:
            adjustments = json.loads(json_block)
            r_lr = adjustments.get("recommended_nn_learning_rate")
            r_floor = adjustments.get("recommended_nn_weight_floor")
            
            if r_lr:
                save_setting("nn_learning_rate", str(r_lr))
                report_lines.append(f"\n📊 **Auto-Applied Setting**: NN Learning Rate adjusted to `{r_lr}`")
            if r_floor:
                save_setting("nn_weight_floor", str(r_floor))
                report_lines.append(f"\n📊 **Auto-Applied Setting**: NN Weight Floor adjusted to `{r_floor}`")
    except Exception as e:
        logging.error(f"API call failed: {e}")
        return f"API call failed: {e}"
        
    # Perform Meta-Prompt Optimization for NN Prompt
    try:
        dev_summary = ""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        report_path = os.path.join(base_dir, "blog", "daily_summaries", "weekly_self_improvement.md")
        if os.path.exists(report_path):
            with open(report_path, "r") as f:
                dev_summary = f.read()[-3000:]
                
        meta_prompt = f"""
You are the Neural Network Optimizer agent. Part of your meta-cognition routine is to evaluate your own prompt template and optimize it based on:
1. Your current prompt template.
2. The outputs of the PhD Quant Optimizer agent.
3. The outputs of the AI Software Developer agent.

Our mission is to scale the bot to earn $1,000 USD a day.

Current Prompt Template:
\"\"\"{db_prompt}\"\"\"

Recent Developer/Quant logs:
\"\"\"{dev_summary}\"\"\"

Critically analyze this context. Redesign your own prompt template to focus it even more tightly on achieving $1,000 USD/day, ensuring it asks for correct neural checks and keeps its final settings JSON format.
Return ONLY a JSON block containing the key "revised_prompt_nn_agent" with your improved prompt template as the value (do not include markdown wrappers like ```json).
"""
        from quant_utils import query_gemini_robust
        raw_text = query_gemini_robust(gemini_api_key, meta_prompt)
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()
        
        res_data = json.loads(raw_text)
        revised = res_data.get("revised_prompt_nn_agent")
        if revised:
            save_setting("prompt_nn_agent", revised)
            report_lines.append(f"\n🧠 **AI Prompt Meta-Optimization**: Successfully evolved NN Optimizer prompt template closer to $1,000/day target.")
    except Exception as e:
        logging.error(f"Failed to meta-optimize prompt_nn_agent: {e}")
        
    report_content = "\n".join(report_lines)
    
    # Save/Append report to blog/daily_summaries/weekly_self_improvement.md
    if os.path.exists(os.path.join(base_dir, "blog", "daily_summaries")):
        report_path = os.path.join(base_dir, "blog", "daily_summaries", "weekly_self_improvement.md")
        try:
            with open(report_path, "a") as f:
                f.write("\n\n" + report_content)
            logging.info("Saved NN self-improvement logs to blog summaries.")
        except Exception as e:
            logging.error(f"Failed to append NN logs to blog summaries: {e}")
            
    # Trigger reload on Proxmox if requested
    if trigger_deploy:
        try:
            subprocess.run(["./deploy.sh"], timeout=30)
            logging.info("Deploy completed after NN optimization.")
        except Exception as e:
            logging.error(f"Deploy execution failed: {e}")
        
    return f"Success! Neural Network self-improvement completed.\n\n" + report_content

if __name__ == "__main__":
    print(run_nn_self_improvement(trigger_deploy=True))
