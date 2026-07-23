import os
import json
import logging
import math
from mutation_guard import should_apply_agent_mutation, log_blocked_mutation
import database as _db
import numpy as np

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

def compute_multi_asset_kelly() -> dict:
    """Compute multi-asset Kelly-optimal allocation fractions using covariance.
    
    Uses the multi-asset Kelly criterion:
      f* = inv(Σ) * μ
    where Σ is the covariance matrix of trade returns and μ is the
    vector of excess returns over risk-free.
    
    Falls back to single-asset Kelly if covariance is singular.
    """
    try:
        conn = _db.get_db_connection()
        conn.row_factory = __import__('sqlite3').Row
        c = conn.cursor()
        c.execute("""
            SELECT symbol, pnl_percent, pnl FROM trades 
            WHERE pnl_percent IS NOT NULL AND pnl_percent != ''
            ORDER BY id DESC LIMIT 1000
        """)
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        
        if not rows:
            return {}
            
        # Group pnl_percent by symbol
        from collections import defaultdict
        ret_seqs = defaultdict(list)
        for r in rows:
            sym = r['symbol']
            pct = r.get('pnl_percent')
            if sym and pct is not None:
                try:
                    ret_seqs[sym].append(float(pct))
                except (ValueError, TypeError):
                    pass
        
        # Keep only symbols with >= 5 trades
        ret_seqs = {k: np.array(v) for k, v in ret_seqs.items() if len(v) >= 5}
        if len(ret_seqs) < 1:
            return {}
            
        symbols = list(ret_seqs.keys())
        n = len(symbols)
        
        # Truncate to shortest length for covariance
        min_len = min(len(v) for v in ret_seqs.values())
        X = np.column_stack([ret_seqs[s][:min_len] for s in symbols])
        
        # Mean returns and covariance
        mu = X.mean(axis=0)
        Sigma = np.cov(X.T)
        Sigma_reg = Sigma + np.eye(n) * 1e-6  # regularize for numerical stability
        
        # Multi-asset Kelly: f* = inv(Σ) * μ
        try:
            inv_sigma = np.linalg.inv(Sigma_reg)
            kelly_fractions = inv_sigma @ mu
        except np.linalg.LinAlgError:
            # Fallback: single-asset Kelly per symbol
            kelly_fractions = np.array([
                mu[i] / (Sigma[i, i] + 1e-12) for i in range(n)
            ])
        
        # Apply ceiling constraint (keep fractions between 0.0 and 0.5)
        kelly_fractions = np.clip(kelly_fractions, 0.0, 0.5)
        # Scale back so sum doesn't exceed 1.0 (fractional Kelly)
        total_kelly = kelly_fractions.sum()
        if total_kelly > 1.0:
            kelly_fractions = kelly_fractions / total_kelly
        
        # Also compute simple single-asset Kelly for comparison
        simple_kelly = {}
        for i, s in enumerate(symbols):
            returns = ret_seqs[s]
            w = (returns > 0).mean()
            if w <= 0 or w >= 1:
                simple_kelly[s] = 0.0
            else:
                avg_w = returns[returns > 0].mean() if returns[returns > 0].size > 0 else 0.0
                avg_l = abs(returns[returns <= 0].mean()) if returns[returns <= 0].size > 0 else 1.0
                b = avg_w / avg_l if avg_l > 1e-12 else 1.0
                simple_kelly[s] = (w * b - (1 - w)) / b if b > 0 else 0.0
                simple_kelly[s] = max(0.0, min(simple_kelly[s], 0.5))
        
        # Build return map
        result = {}
        for i, s in enumerate(symbols):
            result[s] = {
                "multi_asset_kelly": float(round(kelly_fractions[i], 4)),
                "simple_kelly": float(round(simple_kelly.get(s, 0.0), 4)),
                "mean_return_pct": float(round(mu[i], 4)),
                "trade_count": int(len(ret_seqs[s])),
            }
        return result
    except Exception as e:
        logging.error(f"Multi-asset Kelly computation failed: {e}")
        return {}


def compute_turnover_penalty() -> dict:
    """Compute turnover penalty and cost-aware rebalancing metrics.

    Estimates the drag from portfolio turnover by:
    1. Comparing current Kelly ceilings vs previous settings
    2. Estimating round-trip transaction cost per asset
    3. Computing turnover ratio = (trades / total_capital) as a cost drag
    """
    try:
        conn = _db.get_db_connection()
        conn.row_factory = __import__('sqlite3').Row
        c = conn.cursor()
        # Get trade history for turnover estimation
        c.execute("""
            SELECT symbol, pnl, side, fee FROM trades
            WHERE fee IS NOT NULL
            ORDER BY id DESC LIMIT 200
        """)
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
    except Exception:
        rows = []

    try:
        # Fallback: estimate from trade count if fees not stored
        conn2 = _db.get_db_connection()
        c2 = conn2.cursor()
        c2.execute("SELECT COUNT(*) as cnt, COALESCE(SUM(ABS(pnl)), 0) as vol FROM trades")
        r = c2.fetchone()
        conn2.close()
        trade_count = r[0] if r else 0
        trade_volume = float(r[1]) if r and r[1] else 0.0
    except Exception:
        trade_count = 0
        trade_volume = 0.0

    # Load previous Kelly settings for turnover delta
    current_assets = load_active_assets()
    prev_settings = {}
    try:
        conn3 = _db.get_db_connection()
        c3 = conn3.cursor()
        c3.execute("SELECT key, value FROM settings WHERE key LIKE 'kelly_ceiling_%'")
        prev = c3.fetchall()
        conn3.close()
        prev_settings = {r[0]: float(r[1]) for r in prev} if prev else {}
    except Exception:
        pass

    # Compute sum of absolute delta in Kelly ceilings
    kelly_delta = 0.0
    asset_count = 0
    for ticker, info in current_assets.items():
        current_k = info.get("kelly_ceiling", 0.2) if isinstance(info, dict) else 0.2
        prev_k = prev_settings.get(f"kelly_ceiling_{ticker}", current_k)
        kelly_delta += abs(current_k - prev_k)
        asset_count += 1

    avg_kelly_delta = kelly_delta / max(asset_count, 1)
    # Estimate annualized turnover from trade volume / assets
    estimated_turnover = trade_volume / max(trade_count, 1) if trade_count > 0 else 0.0

    # Transaction cost drag: estimate from Kraken taker fees (0.26%) per side
    est_cost_per_trade = 0.0026 * 2  # entry + exit
    total_cost_drag = trade_count * est_cost_per_trade * estimated_turnover if estimated_turnover > 0 else 0.0

    return {
        "trade_count": trade_count,
        "trade_volume": round(trade_volume, 2),
        "avg_kelly_delta": round(avg_kelly_delta, 4),
        "estimated_turnover": round(estimated_turnover, 4),
        "total_cost_drag": round(total_cost_drag, 4),
        "turnover_label": "low" if avg_kelly_delta < 0.05 else ("medium" if avg_kelly_delta < 0.15 else "high"),
    }


def compute_optimal_rebalance(assets: dict, perf: dict) -> dict:
    """Determine whether rebalancing is needed based on drift and volatility.
    
    Uses a drift-based threshold approach:
    - Computes performance-weighted drift from target (Kelly) allocations
    - Recommends rebalance only if drift exceeds cost-aware threshold
    - Threshold = 2 * (est_turnover_cost / benefit_of_rebalance)
    
    Returns:
        dict with rebalance_decision, drift_pct, thresholds
    """
    if not assets:
        return {"should_rebalance": False, "reason": "No assets to evaluate"}
    
    # Compute current allocation drift from target Kelly
    total_drift = 0.0
    asset_count = 0
    drift_details = {}
    
    for ticker, info in assets.items():
        if not isinstance(info, dict):
            continue
        target_kelly = info.get("kelly_ceiling", 0.2)
        perf_data = perf.get(ticker, {})
        trade_count = perf_data.get("trades", 0)
        win_rate = perf_data.get("wins", 0) / max(trade_count, 1)
        
        # Estimate current allocation from performance
        # If win_rate > 0.5 and positive PnL, actual allocation > target
        total_pnl = perf_data.get("total_pnl", 0.0)
        if trade_count > 0 and win_rate > 0.55 and total_pnl > 0:
            # Outperformance suggests drift above target
            current_alloc = target_kelly * (1.0 + min(win_rate - 0.55, 0.3))
        elif trade_count > 0 and win_rate < 0.45 and total_pnl < 0:
            # Underperformance suggests drift below target
            current_alloc = target_kelly * max(0.0, 1.0 - min(0.45 - win_rate, 0.3))
        else:
            current_alloc = target_kelly
        
        drift = abs(current_alloc - target_kelly)
        total_drift += drift
        asset_count += 1
        drift_details[ticker] = {
            "target_kelly": round(target_kelly, 4),
            "estimated_current": round(current_alloc, 4),
            "drift": round(drift, 4),
        }
    
    avg_drift = total_drift / max(asset_count, 1)
    
    # Cost-aware threshold: rebalance only if expected benefit > cost
    # Benefit estimate: drift > 5% of allocation ~ 0.5% expected improvement
    # Cost estimate: round-trip = 2 * taker fee (0.26%) + slippage (0.1%) ≈ 0.72%
    cost_est = 0.0072  # 0.72% round-trip cost
    benefit_est = avg_drift * 0.5  # assume 50% of drift is exploitable
    
    # Dynamic threshold: rebalance only when drift > 2 * cost/benefit ratio
    rebalance_threshold = 2.0 * (cost_est / max(benefit_est, 0.0001))
    should_rebalance = avg_drift > rebalance_threshold and avg_drift > 0.02
    
    return {
        "should_rebalance": bool(should_rebalance),
        "avg_drift_pct": round(avg_drift * 100, 2),
        "threshold_pct": round(rebalance_threshold * 100, 2),
        "est_cost_pct": round(cost_est * 100, 2),
        "est_benefit_pct": round(benefit_est * 100, 2),
        "asset_count": asset_count,
        "reason": (
            "Drift exceeds cost-aware threshold" if should_rebalance
            else f"Drift ({avg_drift*100:.2f}%) below threshold ({rebalance_threshold*100:.2f}%)"
        ),
        "details": drift_details,
    }


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
        
    # Compute multi-asset Kelly fractions from covariance
    multi_kelly = compute_multi_asset_kelly()
    kelly_block = ""
    if multi_kelly:
        kelly_lines = ["\n### Multi-Asset Kelly Allocation (Covariance-Aware):", "Symbol    | Multi-Kelly | Simple-Kelly | Mean Ret | Trades", "-" * 60]
        for sym, vals in multi_kelly.items():
            kelly_lines.append(f"{sym:<10} | {vals['multi_asset_kelly']:<12.4f} | {vals['simple_kelly']:<13.4f} | {vals['mean_return_pct']:<9.4f} | {vals['trade_count']}")
        kelly_block = "\n".join(kelly_lines)
    
    # Turnover penalty / cost-aware rebalancing
    turnover = compute_turnover_penalty()
    turnover_block = (
        f"\n### Turnover & Cost Drag Analysis:\n"
        f"  Trade count: {turnover['trade_count']}\n"
        f"  Est. trade volume: {turnover['trade_volume']}\n"
        f"  Kelly delta (rebalancing churn): {turnover['avg_kelly_delta']}\n"
        f"  Est. total cost drag: {turnover['total_cost_drag']}\n"
        f"  Turnover regime: {turnover['turnover_label']}\n"
    )
    
    # Drift-based rebalance decision
    rebalance = compute_optimal_rebalance(active_assets, perf_summary)
    rebalance_block = (
        f"\n### Rebalance Decision (Drift-Based, Cost-Aware):\n"
        f"  Should rebalance: {rebalance['should_rebalance']}\n"
        f"  Reason: {rebalance['reason']}\n"
        f"  Avg drift: {rebalance['avg_drift_pct']}% (threshold: {rebalance['threshold_pct']}%)\n"
        f"  Est. cost: {rebalance['est_cost_pct']}% vs benefit: {rebalance['est_benefit_pct']}%\n"
    )
    if rebalance.get("details"):
        for ticker, det in rebalance["details"].items():
            rebalance_block += (
                f"  {ticker}: target={det['target_kelly']:.4f}, "
                f"current={det['estimated_current']:.4f}, drift={det['drift']:.4f}\n"
            )
    
    prompt = f"""{db_prompt}

Current Asset Configs:
{json.dumps(active_assets, indent=2)}

Recent Performance Summary (Last 100 Trades Grouped By Ticker):
{json.dumps(perf_summary, indent=2)}

{kelly_block}

{turnover_block}

{rebalance_block}
"""
    
    report_lines = ["\n## ⚖️ Ensemble Asset Allocator Report"]
    if kelly_block:
        report_lines.append(kelly_block)
    if rebalance_block:
        report_lines.append(rebalance_block)
    
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
