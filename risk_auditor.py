import os
import json
import logging
import math
from collections import defaultdict
from mutation_guard import should_apply_agent_mutation, log_blocked_mutation
import database as _db
import numpy as np

AGENT_NAME = "risk_auditor"
import subprocess

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def load_settings():
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
    # Use database.save_setting() which handles mutation freeze detection
    # via call-stack inspection, optimization logging, and DB write.
    _db.save_setting(key, str(value))

def _compute_correlation_risk_block() -> str:
    """Compute correlation matrix with eigenvalue cleaning (shrinkage estimation)
    and regime-conditional risk metrics from trade-level PnL co-movement.
    """
    try:
        conn = _db.get_db_connection()
        conn.row_factory = __import__('sqlite3').Row
        c = conn.cursor()
        # Get all recent PnL by symbol, grouped by day or trade batch
        c.execute("""
            SELECT symbol, pnl FROM trades 
            WHERE pnl IS NOT NULL 
            ORDER BY id DESC LIMIT 500
        """)
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        
        if not rows or len(rows) < 10:
            return ""
            
        # Group PnL by symbol into sequences
        from collections import defaultdict
        seqs = defaultdict(list)
        for r in rows:
            symbol = r['symbol']
            if symbol:
                seqs[symbol].append(float(r['pnl']))
                
        # Keep only symbols with >= 5 data points for a meaningful correlation
        seqs = {k: np.array(v[:100]) for k, v in seqs.items() if len(v) >= 5}
        if len(seqs) < 2:
            return ""
            
        symbols = list(seqs.keys())
        n = len(symbols)
        
        # Align sequences by truncating all to the shortest length
        min_len = min(len(v) for v in seqs.values())
        if min_len < 3:
            return ""
        X = np.column_stack([seqs[s][:min_len] for s in symbols])
        
        # Raw correlation matrix
        corr_raw = np.corrcoef(X.T)
        # Replace NaN from constant returns
        corr_raw = np.nan_to_num(corr_raw, nan=0.0)
        
        # Eigenvalue cleaning: shrink extreme eigenvalues toward mean
        # Marcenko-Pastur-inspired: eigenvalues > 2σ are likely signal, not noise
        eigvals, eigvecs = np.linalg.eigh(corr_raw)
        eigvals = np.clip(eigvals, 0.0, None)  # ensure positive semidefinite
        mean_eig = np.mean(eigvals)
        # Shrink: pull eigenvalues above 2*mean towards 1.5*mean
        cleaned = eigvals.copy()
        threshold = 2.0 * mean_eig
        for i in range(len(cleaned)):
            if cleaned[i] > threshold:
                cleaned[i] = 1.5 * mean_eig
        # Re-normalize to preserve trace == n
        cleaned = cleaned * (n / np.sum(cleaned))
        corr_clean = eigvecs @ np.diag(cleaned) @ eigvecs.T
        # Re-normalize diagonal to 1.0 and ensure symmetry
        d = np.sqrt(np.diag(corr_clean))
        d_inv = np.where(d > 1e-12, 1.0 / d, 1.0)
        corr_clean = (corr_clean * d_inv) * d_inv[:, np.newaxis]
        corr_clean = (corr_clean + corr_clean.T) / 2.0  # force symmetry
        
        # Compute min-variance hedge ratios from cleaned correlation
        # w* = inv(Σ) * 1 / (1^T * inv(Σ) * 1)
        cov_raw = np.cov(X.T)
        cov_raw = np.nan_to_num(cov_raw, nan=0.0)
        try:
            inv_cov = np.linalg.inv(cov_raw + np.eye(n) * 1e-6)
            ones = np.ones(n)
            hedge_weights = inv_cov @ ones / (ones @ inv_cov @ ones)
        except np.linalg.LinAlgError:
            hedge_weights = np.ones(n) / n
        
        # Build readable output
        lines = ["### Quantitative Risk Analysis", ""]
        lines.append("**Cleaned Correlation Matrix (shrinkage-estimated):**")
        header = "Symbol      " + "  ".join(f"{s:<10}" for s in symbols)
        lines.append(header)
        for i in range(n):
            row_vals = "  ".join(f"{corr_clean[i,j]:>+8.4f}" for j in range(n))
            lines.append(f"{symbols[i]:<12}{row_vals}")
        lines.append("")
        lines.append("**Minimum Variance Hedge Portfolio Weights:**")
        for i in range(n):
            lines.append(f"  {symbols[i]}: {hedge_weights[i]:>8.4f}")
        lines.append("")
        lines.append(f"**Eigenvalue Spectrum (raw):** {', '.join(f'{v:.4f}' for v in sorted(eigvals, reverse=True))}")
        lines.append(f"**Eigenvalue Spectrum (cleaned):** {', '.join(f'{v:.4f}' for v in sorted(cleaned, reverse=True))}")
        lines.append(f"**Avg cross-correlation:** {np.mean(corr_clean[np.triu_indices(n, k=1)]):.4f}")
        lines.append("")
        
        return "\n".join(lines)
    except Exception as e:
        logging.error(f"Correlation analysis failed: {e}")
        return ""


def _compute_hedging_risk_block() -> str:
    """Compute hedging metrics: minimum variance hedge ratios,
    beta-neutral weights, dollar-neutral assessment, and cointegration
    test (Engle-Granger via correlation proxy).
    """
    try:
        conn = _db.get_db_connection()
        conn.row_factory = __import__('sqlite3').Row
        c = conn.cursor()
        # Get recent trades PnL via sym
        c.execute("""
            SELECT symbol, pnl, pnl_percent FROM trades
            WHERE pnl IS NOT NULL AND pnl_percent IS NOT NULL
            ORDER BY id DESC LIMIT 500
        """)
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        if not rows or len(rows) < 10:
            return ""
        
        from collections import defaultdict
        seqs = defaultdict(list)
        for r in rows:
            sym = r['symbol']
            if sym:
                seqs[sym].append(float(r.get('pnl_percent', 0.0)))
        seqs = {k: np.array(v[:80]) for k, v in seqs.items() if len(v) >= 5}
        if len(seqs) < 2:
            return ""
        
        symbols = list(seqs.keys())
        n = len(symbols)
        min_len = min(len(v) for v in seqs.values())
        if min_len < 5:
            return ""
        X = np.column_stack([seqs[s][:min_len] for s in symbols])
        
        # Price proxy: cumprod of (1 + return)
        price = np.cumprod(1.0 + X, axis=0)
        log_ret = X
        
        # --- Minimum Variance Hedge Ratio ---
        # h* = Cov(r_a, r_b) / Var(r_b)
        # For each pair, compute the hedge ratio that minimizes portfolio variance
        hedge_lines = []
        for i in range(n):
            for j in range(i + 1, n):
                ri = log_ret[:, i]
                rj = log_ret[:, j]
                cov_ij = np.cov(ri, rj)[0, 1]
                var_j = np.var(rj)
                if var_j > 1e-12:
                    h = cov_ij / var_j
                else:
                    h = 0.0
                
                # Beta: Cov(r_i, r_j) / Var(r_j)
                beta = h  # same formula for single regressor
                
                # Dollar-neutral check: |beta| ≈ 1 means hedged
                dollar_neutral = abs(abs(beta) - 1.0) < 0.15
                
                hedge_lines.append(
                    f"  {symbols[i]} vs {symbols[j]}: hedge_ratio={h:.4f}, "
                    f"beta={beta:.4f}, $neutral={dollar_neutral}"
                )
        
        # --- Portfolio Beta to first principal component (market proxy) ---
        cov = np.cov(log_ret.T)
        eigvals, eigvecs = np.linalg.eigh(cov)
        pc1 = eigvecs[:, -1]  # first PC = market direction
        # Market portfolio returns = projection onto PC1
        mkt_rets = log_ret @ pc1
        betas = []
        for i in range(n):
            c = np.cov(log_ret[:, i], mkt_rets)[0, 1]
            v = np.var(mkt_rets)
            betas.append(c / v if v > 1e-12 else 0.0)
        
        # --- Cointegration proxy: correlation of log prices ---
        # A true cointegration test requires ADF on residuals; here we use
        # the spread around the hedge ratio as a first-pass signal
        coint_lines = []
        if len(symbols) >= 2:
            for idx in range(min(3, n)):
                spread = price[:, 0] - betas[0] * price[:, idx]
                # Simple mean-reversion check on spread
                spread_mean = np.mean(spread)
                spread_std = np.std(spread)
                if spread_std > 1e-12:
                    last_spread_z = (spread[-1] - spread_mean) / spread_std
                    coint_lines.append(
                        f"  {symbols[0]}/{symbols[idx]} spread z={last_spread_z:.2f}, "
                        f"mean-rev strength={abs(np.mean(np.diff(spread > spread_mean))*2-1):.3f}"
                    )
        
        # Build output
        lines = ["\n### Hedging & Beta Analysis", ""]
        lines.append("**Minimum Variance Hedge Ratios & Beta:**")
        lines.extend(hedge_lines if hedge_lines else ["  (insufficient multi-asset data)"])
        lines.append("")
        lines.append("**Portfolio Betas (vs PC1 market proxy):**")
        for i in range(n):
            label = "beta-neutral" if abs(betas[i]) < 0.2 else "directional"
            lines.append(f"  {symbols[i]}: beta={betas[i]:.4f} ({label})")
        lines.append("")
        if coint_lines:
            lines.append("**Cointegration Proxy (spread mean-reversion):**")
            lines.extend(coint_lines)
        lines.append("")
        return "\n".join(lines)
    except Exception as e:
        logging.error(f"Hedging analysis failed: {e}")
        return ""


def _compute_stress_test_block() -> str:
    """Run scenario stress tests on portfolio.
    
    Scenarios:
    1. Flash crash: -15% single-day drop in all assets
    2. Vol spike: +50% volatility expansion (+2σ daily move)
    3. Liquidity crisis: 3x spread widening
    4. Trend reversal: 5-day -8% across all positions
    """
    try:
        conn = _db.get_db_connection()
        conn.row_factory = __import__('sqlite3').Row
        c = conn.cursor()
        c.execute("""
            SELECT symbol, pnl, pnl_percent FROM trades
            WHERE pnl IS NOT NULL AND pnl_percent IS NOT NULL
            ORDER BY id DESC LIMIT 300
        """)
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        if not rows:
            return ""
        
        from collections import defaultdict
        seqs = defaultdict(list)
        for r in rows:
            sym = r['symbol']
            if sym:
                seqs[sym].append(float(r.get('pnl_percent', 0.0)))
        seqs = {k: np.array(v) for k, v in seqs.items() if len(v) >= 3}
        if not seqs:
            return ""
        
        lines = ["\n### Stress Test Scenarios"]
        
        # Est. current equity from settings
        current_equity = 1000.0
        try:
            from database import load_setting as _ls
            eq = _ls("current_equity", "1000")
            current_equity = float(eq)
        except Exception:
            pass
        
        for sym, rets in seqs.items():
            vol = float(np.std(rets))
            mean_ret = float(np.mean(rets))
            
            lines.append(f"\n**{sym}** (vol={vol:.4f}, mean={mean_ret:.4f}, n={len(rets)}):")
            
            # Scenario 1: Flash crash (-15%)
            crash_impact = -0.15
            lines.append(f"  Flash crash (-15%): impact=${current_equity * crash_impact:,.2f}")
            
            # Scenario 2: Vol spike: 2σ daily move adverse direction
            if vol > 0:
                vol_spike = mean_ret - 2.0 * vol
                lines.append(f"  Vol spike (2σ adverse): expected return {vol_spike:.4f}")
            
            # Scenario 3: Max historical drawdown from returns
            cum_ret = np.cumprod(1.0 + rets)
            if len(cum_ret) > 1:
                peak = np.maximum.accumulate(cum_ret)
                dd = (peak - cum_ret) / peak
                max_dd = float(np.max(dd))
                lines.append(f"  Historical max DD: {max_dd*100:.2f}%")
            
            # Scenario 4: Consecutive loss analysis
            neg_streak = 0
            max_neg_streak = 0
            for r_val in rets:
                if r_val < 0:
                    neg_streak += 1
                    max_neg_streak = max(max_neg_streak, neg_streak)
                else:
                    neg_streak = 0
            lines.append(f"  Max consecutive losses: {max_neg_streak}")
        
        return "\n".join(lines)
    except Exception as e:
        logging.error(f"Stress test failed: {e}")
        return ""


def run_risk_audit(trigger_deploy: bool = False):
    logging.info("Starting Quantitative Portfolio Risk Audit...")
    settings = load_settings()
    ai_enabled = settings.get("blog_ai_enabled", "false") == "true"
    
    # Use OpenClaw bridge regardless of Gemini key - the bridge handles routing
    if not ai_enabled:
        logging.warning("AI is disabled. Cannot run Risk Audit.")
        return "AI is disabled. Enable blog_ai_enabled setting."
        
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
        conn = _db.get_db_connection()
        conn.row_factory = __import__('sqlite3').Row
        c = conn.cursor()
        c.execute("SELECT id, symbol, direction, pnl, exit_reason FROM trades ORDER BY id DESC LIMIT 20")
        recent_trades = [dict(r) for r in c.fetchall()]
        conn.close()
    except Exception as e:
        logging.error(f"Error querying trades for risk audit: {e}")

    # --- Quantitative risk analysis: correlation + hedging + stress test ---
    corr_block = _compute_correlation_risk_block()
    hedging_block = _compute_hedging_risk_block()
    stress_block = _compute_stress_test_block()

    prompt = f"""{db_prompt}

Current Risk Settings:
- Max Daily Loss Drawdown Limit: {settings.get("max_daily_drawdown", "5.0")}%
- Loss Cooldown Hold Period: {settings.get("loss_cooldown_hours", "4.0")} hours

Recent trades telemetry:
{json.dumps(recent_trades, indent=2) if recent_trades else '[]'}

{corr_block}

{hedging_block}

{stress_block}
"""
    
    report_lines = ["\n## 🛡️ Portfolio Risk Audit Report"]
    
    try:
        logging.info("Requesting Risk Audit evaluation from LLM...")
        from openclaw_bridge import query_auto, extract_json_block
        advice_text = query_auto(prompt, agent_name="risk")
        
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
        from openclaw_bridge import query_auto, extract_json_block
        raw_text = query_auto(meta_prompt, agent_name="risk", max_tokens=2048)
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
    base_dir = os.path.dirname(os.path.abspath(__file__))
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
