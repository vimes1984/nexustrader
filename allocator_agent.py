import os
import json
import logging
from mutation_guard import should_apply_agent_mutation, log_blocked_mutation
import database as _db

AGENT_NAME = "allocator_agent"
import subprocess

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def load_settings():
    settings = {}
    try:
        conn = _db.get_db_connection()
        c = conn.cursor()
        c.execute("SELECT key, value FROM settings")
        rows = c.fetchall()
        conn.close()
        return {r[0]: r[1] for r in rows} if rows else {}
    except Exception:
        return {}

def save_setting(key, value):
    if not should_apply_agent_mutation(AGENT_NAME):
        log_blocked_mutation(AGENT_NAME, key, value)
        return
    _db.save_setting_directly(key, value)

def load_active_assets():
    return _db.load_active_assets()

def save_active_asset(ticker, is_active, tp_multiplier, sl_multiplier, kelly_ceiling):
    _db.save_active_asset(ticker, is_active, tp_multiplier, sl_multiplier, kelly_ceiling)

def load_performance_summary():
    summary = {}
    try:
        conn = _db.get_db_connection()
        c = conn.cursor()
        c.execute("SELECT symbol, pnl_percent, pnl FROM trades ORDER BY id DESC LIMIT 100")
        rows = c.fetchall()
        conn.close()
        for symbol, pnl_pct, pnl in rows:
            if symbol not in summary:
                summary[symbol] = {"trades": 0, "wins": 0, "total_pnl": 0.0}
            summary[symbol]["trades"] += 1
            if pnl and float(pnl) > 0:
                summary[symbol]["wins"] += 1
            summary[symbol]["total_pnl"] += float(pnl or 0.0)
    except Exception:
        pass
    return summary

def run_allocator_self_improvement(trigger_deploy: bool = False):
    logging.info("Starting Allocation Check self-improvement session...")
    settings = load_settings()
        
    active_assets = load_active_assets()
    perf_summary = load_performance_summary()
    
    db_prompt = settings.get("prompt_allocator_agent")
    if not db_prompt:
        db_prompt = """You are a world-class Portfolio Allocation Specialist and Risk Management Engineer.
Our goal is to dynamically optimize the active asset roster, Kelly allocation ceilings, and risk parameters to safely scale NexusTrader earnings to $1,000 USD/day.

Analyze the recent trading performance, win/loss stats, and PnL distributions per asset.
Propose adjustments to:
1. Asset Status: Activate trending/profitable tickers; temporarily deactivate/cooldown underperforming assets with consecutive losses or deep drawdowns.
2. Kelly Ceiling caps: Limit capital exposure on high-volatility assets while optimizing allocation on stable performers.
3. Volatility multipliers: Custom ATR TP/SL multipliers tailored to the specific asset's risk regime.

At the very end of your response, output a strict JSON block with your recommended adjustments:
```json
{
  "asset_adjustments": {
    "TICKER": {
      "is_active": boolean,
      "tp_multiplier": float,
      "sl_multiplier": float,
      "kelly_ceiling": float
    }
  }
}
```"""
        save_setting("prompt_allocator_agent", db_prompt)
        
    prompt = f"""{db_prompt}

Current Asset Configs:
{json.dumps(active_assets, indent=2)}

Recent Performance Summary (Last 100 Trades Grouped By Ticker):
{json.dumps(perf_summary, indent=2)}
"""
    
    report_lines = ["\n## ⚖️ Ensemble Asset Allocator Report"]
    
    try:
        logging.info("Requesting Allocation evaluation from LLM...")
        from openclaw_bridge import query_auto, extract_json_block
        advice_text = query_auto(prompt, agent_name="allocator")
        
        advice_clean = advice_text
        json_block = ""
        if "```json" in advice_text:
            parts = advice_text.split("```json")
            advice_clean = parts[0]
            json_block = parts[1].split("```")[0].strip()
            
        report_lines.append(advice_clean)
        
        if json_block:
            adjustments = json.loads(json_block)
            asset_adjusts = adjustments.get("asset_adjustments", {})
            for ticker, params in asset_adjusts.items():
                is_active = params.get("is_active", True)
                tp_mult = params.get("tp_multiplier", 2.5)
                sl_mult = params.get("sl_multiplier", 1.5)
                kelly = params.get("kelly_ceiling", 0.2)
                save_active_asset(ticker, is_active, tp_mult, sl_mult, kelly)
                report_lines.append(f"\n📊 **Auto-Applied Asset Setting**: `{ticker}` -> Active: `{is_active}`, TP: `{tp_mult}x`, SL: `{sl_mult}x`, Kelly Cap: `{kelly}`")
    except Exception as e:
        logging.error(f"API call failed: {e}")
        return f"API call failed: {e}"
        
    # Perform Meta-Prompt Optimization for Allocator Prompt
    try:
        dev_summary = ""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        report_path = os.path.join(base_dir, "blog", "daily_summaries", "weekly_self_improvement.md")
        if os.path.exists(report_path):
            with open(report_path, "r") as f:
                dev_summary = f.read()[-3000:]
                
        meta_prompt = f"""
You are the Ensemble Asset Allocator agent. Part of your meta-cognition routine is to evaluate your own prompt template and optimize it based on:
1. Your current prompt template.
2. The outputs of the PhD Quant Optimizer agent.
3. The outputs of the AI Software Developer agent.

Our mission is to scale the bot to earn $1,000 USD a day.

Current Prompt Template:
\"\"\"{db_prompt}\"\"\"

Recent Developer/Quant logs:
\"\"\"{dev_summary}\"\"\"

Critically analyze this context. Redesign your own prompt template to focus it even more tightly on achieving $1,000 USD/day, ensuring it asks for correct asset allocation checks and keeps its final settings JSON format.
Return ONLY a JSON block containing the key "revised_prompt_allocator_agent" with your improved prompt template as the value (do not include markdown wrappers like ```json).
"""
        from openclaw_bridge import query_auto, extract_json_block
        raw_text = query_auto(meta_prompt, agent_name="allocator", max_tokens=2048)
        raw_text = raw_text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()
        
        res_data = json.loads(raw_text)
        revised = res_data.get("revised_prompt_allocator_agent")
        if revised:
            save_setting("prompt_allocator_agent", revised)
            report_lines.append(f"\n📡 **AI Prompt Meta-Optimization**: Evolved Ensemble Allocator prompt template closer to target.")
    except Exception as e:
        logging.error(f"Failed to meta-optimize prompt_allocator_agent: {e}")
        
    report_content = "\n".join(report_lines)
    
    # Save/Append report to blog/daily_summaries/weekly_self_improvement.md
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.exists(os.path.join(base_dir, "blog", "daily_summaries")):
        report_path = os.path.join(base_dir, "blog", "daily_summaries", "weekly_self_improvement.md")
        try:
            with open(report_path, "a") as f:
                f.write("\n\n" + report_content)
            logging.info("Saved Allocator self-improvement logs to blog summaries.")
        except Exception as e:
            logging.error(f"Failed to append Allocator logs to blog summaries: {e}")
            
    # Trigger reload on Proxmox if requested
    if trigger_deploy:
        try:
            subprocess.run(["./deploy.sh"], timeout=30)
            logging.info("Deploy completed after Allocator optimization.")
        except Exception as e:
            logging.error(f"Deploy execution failed: {e}")
            
    return f"Success! Allocator self-improvement completed.\n\n" + report_content

if __name__ == "__main__":
    print(run_allocator_self_improvement(trigger_deploy=True))
