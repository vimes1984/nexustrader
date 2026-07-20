import os
import json
import sqlite3
import time
import logging
import database

DB_PATH = os.path.expanduser("~/.nexustrader/nexustrader.db")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def run_long_term_strategy_optimization():
    logging.info("Starting weekly Long-Term Strategy Quant Agent session...")
    
    if not os.path.exists(DB_PATH):
        logging.warning("Database not found. Skipping long-term strategy optimization.")
        return
        
    try:
        # Load settings
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        # Load settings dict
        c.execute("SELECT key, value FROM settings")
        settings = {r[0]: r[1] for r in c.fetchall()}
        
        # Load recent shadow trades
        c.execute(
            """
            SELECT id, symbol, direction, quantity, entry_price, exit_price, pnl, pnl_percent, exit_reason, entry_time, exit_time, status
            FROM shadow_trades 
            ORDER BY entry_time DESC 
            LIMIT 50
            """
        )
        shadow_trades = [{
            "id": r[0],
            "symbol": r[1],
            "direction": r[2],
            "quantity": r[3],
            "entry_price": r[4],
            "exit_price": r[5],
            "pnl": r[6],
            "pnl_percent": r[7],
            "exit_reason": r[8],
            "entry_time": r[9],
            "exit_time": r[10],
            "status": r[11]
        } for r in c.fetchall()]
        
        # Compile stats
        total_trades = len(shadow_trades)
        wins = [t for t in shadow_trades if (t.get("pnl") or 0.0) > 0.0]
        win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0
        total_pnl = sum([t.get("pnl") or 0.0 for t in shadow_trades])
        avg_pnl = (total_pnl / total_trades) if total_trades > 0 else 0.0
        
        # Current long-term config settings
        vol_target = float(settings.get("shadow_volatility_target_pct", "1.5"))
        tp_mult = float(settings.get("shadow_tp_atr_multiplier", "3.0"))
        sl_mult = float(settings.get("shadow_sl_atr_multiplier", "1.5"))
        nn_consensus = float(settings.get("shadow_nn_consensus_min_weight", "0.12"))
        max_hold_hours = float(settings.get("shadow_max_holding_hours", "48.0"))
        
        report_lines = []
        report_lines.append("## Weekly Long-Term Strategy Attribution & PhD Quant Optimization")
        report_lines.append(f"Session processed **{total_trades}** shadow walk-forward trades.")
        report_lines.append("\n### Shadow Mode Performance Metrics:")
        report_lines.append(f"* Win Rate: **{win_rate:.2f}%**")
        report_lines.append(f"* Total Net Profit: **${total_pnl:.2f}**")
        report_lines.append(f"* Average Trade PnL: **${avg_pnl:.2f}**")
        report_lines.append(f"* Volatility Target Scaling: `{vol_target}%` of price")
        report_lines.append(f"* ATR Stop Multipliers: TP = `{tp_mult}x ATR` | SL = `{sl_mult}x ATR`")
        report_lines.append(f"* Neural consensus gate filter: `{nn_consensus * 100:.1f}%` min weight")
        report_lines.append(f"* Max holding window limit: `{max_hold_hours} hours`")

        gemini_api_key = settings.get("blog_gemini_api_key", "").strip()
        ai_enabled = settings.get("blog_ai_enabled", "false") == "true"
        
        if ai_enabled and gemini_api_key:
            report_lines.append("\n### 💡 PhD Quantitative Risk Officer & Long-Term Architect Analysis:")
            
            db_prompt = settings.get("prompt_long_term_quant")
            if not db_prompt:
                db_prompt = """You are a world-class PhD Quantitative Risk Officer and Long-Term Strategy Architect.
Our core objective is to refine the Long-Term Strategy shadow model parameters to safely and consistently achieve our $1,000 USD/day profit target.

Evaluate the shadow trades, win rates, and holding periods. Analyze how volatility targeted sizing, Kalman filter trend gates, and neural gating can be optimized to improve expectancy. Compute required capital to hit $1,000/day.

At the very end of your response, output recommended setting adjustments strictly in a JSON block (wrapped in ```json):
```json
{
  "shadow_volatility_target_pct": float,
  "shadow_tp_atr_multiplier": float,
  "shadow_sl_atr_multiplier": float,
  "shadow_nn_consensus_min_weight": float,
  "shadow_max_holding_hours": float
}
```"""
                c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("prompt_long_term_quant", db_prompt))
                conn.commit()
                
            prompt = f"""{db_prompt}

Current Shadow Mode Parameters:
- shadow_volatility_target_pct: {vol_target}%
- shadow_tp_atr_multiplier: {tp_mult}x
- shadow_sl_atr_multiplier: {sl_mult}x
- shadow_nn_consensus_min_weight: {nn_consensus}
- shadow_max_holding_hours: {max_hold_hours}h

Walk-Forward Session Data:
- Recent shadow trades details: {json.dumps(shadow_trades, indent=2) if shadow_trades else '[]'}
- Win Rate: {win_rate:.2f}% | Total Net Profit: ${total_pnl:.2f} | Average Trade PnL: ${avg_pnl:.2f}
- Core Target: $1,000 USD average daily profit.
"""
            from quant_utils import query_gemini_robust
            
            # Audit trail logger wrapper
            try:
                raw_advice = query_gemini_robust(gemini_api_key, prompt)
                database.log_agent_run("LongTermQuant", "gemini", "gemini-1.5-flash", prompt, raw_advice, "success")
            except Exception as e_ai:
                database.log_agent_run("LongTermQuant", "gemini", "gemini-1.5-flash", prompt, str(e_ai), "failed")
                raise e_ai

            advice_clean = raw_advice
            json_block = ""
            if "```json" in raw_advice:
                parts = raw_advice.split("```json")
                advice_clean = parts[0]
                json_block = parts[1].split("```")[0].strip()
                
            report_lines.append(advice_clean)
            
            if json_block:
                adjustments = json.loads(json_block)
                new_vol = adjustments.get("shadow_volatility_target_pct")
                new_tp = adjustments.get("shadow_tp_atr_multiplier")
                new_sl = adjustments.get("shadow_sl_atr_multiplier")
                new_nn = adjustments.get("shadow_nn_consensus_min_weight")
                new_hold = adjustments.get("shadow_max_holding_hours")
                
                if new_vol is not None:
                    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('shadow_volatility_target_pct', ?)", (str(new_vol),))
                    report_lines.append(f"\n📈 **Auto-Applied setting (QRO)**: shadow_volatility_target_pct adjusted to `{new_vol}%`")
                if new_tp is not None:
                    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('shadow_tp_atr_multiplier', ?)", (str(new_tp),))
                    report_lines.append(f"\n📈 **Auto-Applied setting (QRO)**: shadow_tp_atr_multiplier adjusted to `{new_tp}x ATR`")
                if new_sl is not None:
                    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('shadow_sl_atr_multiplier', ?)", (str(new_sl),))
                    report_lines.append(f"\n📈 **Auto-Applied setting (QRO)**: shadow_sl_atr_multiplier adjusted to `{new_sl}x ATR`")
                if new_nn is not None:
                    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('shadow_nn_consensus_min_weight', ?)", (str(new_nn),))
                    report_lines.append(f"\n📈 **Auto-Applied setting (QRO)**: shadow_nn_consensus_min_weight adjusted to `{new_nn}`")
                if new_hold is not None:
                    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('shadow_max_holding_hours', ?)", (str(new_hold),))
                    report_lines.append(f"\n📈 **Auto-Applied setting (QRO)**: shadow_max_holding_hours adjusted to `{new_hold} hours`")
                    
                conn.commit()
            
            # Self-Improvement Meta-Prompt optimization
            meta_prompt = f"""
You are the Long-Term Quant Optimizer agent. Part of your meta-cognition routine is to evaluate your own prompt template and optimize it based on:
1. Your current prompt template.
2. Shadow mode trades history and current parameters.
3. The $1,000 USD/day target.

Current Prompt Template:
\"\"\"{db_prompt}\"\"\"

Walk-Forward Data:
- Recent shadow trades: {json.dumps(shadow_trades) if shadow_trades else '[]'}
- Win Rate: {win_rate:.2f}% | Total Profit: ${total_pnl:.2f}

Evolve your own prompt template to focus even more tightly on achieving $1,000 USD/day, ensuring it asks for correct statistical checks and keeps its final settings JSON format.
Return ONLY a JSON block containing the key "revised_prompt_long_term_quant" with your improved prompt template as the value (do not include markdown wrappers like ```json).
"""
            try:
                raw_meta = query_gemini_robust(gemini_api_key, meta_prompt)
                if raw_meta.startswith("```json"):
                    raw_meta = raw_meta[7:]
                if raw_meta.endswith("```"):
                    raw_meta = raw_meta[:-3]
                raw_meta = raw_meta.strip()
                
                meta_res = json.loads(raw_meta)
                revised = meta_res.get("revised_prompt_long_term_quant")
                if revised:
                    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('prompt_long_term_quant', ?)", (revised,))
                    conn.commit()
                    report_lines.append(f"\n🧠 **Prompt Meta-Optimization**: Successfully evolved long term strategy prompt template to optimize parameters closer to $1,000 USD/day.")
            except Exception as me_e:
                logging.error(f"Failed to meta-optimize prompt_long_term_quant: {me_e}")
                
        else:
            report_lines.append("\n### 💡 AI recommendations Status:")
            report_lines.append("*AI recommendations disabled or Gemini key not set.*")
            
        conn.close()
        
        # Save optimizer report page
        report_content = "\n".join(report_lines)
        logging.info("Long-term strategy parameters optimized:\n" + report_content)
        
        blog_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blog", "daily_summaries")
        if os.path.exists(blog_dir):
            report_path = os.path.join(blog_dir, "weekly_long_term_quant.md")
            with open(report_path, "w") as f:
                f.write(report_content)
            logging.info("Weekly long-term quant report page saved to blog.")
            
    except Exception as e:
        logging.error(f"Error in Long-Term Strategy Quant session: {e}")

if __name__ == "__main__":
    run_long_term_strategy_optimization()
