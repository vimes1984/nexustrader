import os
import json
import logging
import database as _db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from openclaw_bridge import query_openclaw, extract_json_block


def run_long_term_strategy_optimization():
    logging.info("Starting weekly Long-Term Strategy Quant Agent session...")

    try:
        conn = _db.get_db_connection()
        conn.row_factory = __import__('sqlite3').Row
        c = conn.cursor()

        c.execute("SELECT key, value FROM settings")
        settings = {r[0]: r[1] for r in c.fetchall()}

        c.execute(
            """
            SELECT id, symbol, direction, quantity, entry_price, exit_price,
                   pnl, pnl_percent, exit_reason, entry_time, exit_time, status
            FROM shadow_trades
            ORDER BY entry_time DESC
            LIMIT 50
            """
        )
        shadow_trades = [
            {
                "id": r[0], "symbol": r[1], "direction": r[2],
                "quantity": r[3], "entry_price": r[4], "exit_price": r[5],
                "pnl": r[6], "pnl_percent": r[7], "exit_reason": r[8],
                "entry_time": r[9], "exit_time": r[10], "status": r[11],
            }
            for r in c.fetchall()
        ]

        total_trades = len(shadow_trades)
        wins = [t for t in shadow_trades if (t.get("pnl") or 0.0) > 0.0]
        losses = [t for t in shadow_trades if (t.get("pnl") or 0.0) < 0.0]
        ties = total_trades - len(wins) - len(losses)  # zero-PnL trades
        resolved = len(wins) + len(losses)
        win_rate = (len(wins) / resolved * 100.0) if resolved > 0 else 0.0
        total_pnl = sum(t.get("pnl") or 0.0 for t in shadow_trades)
        avg_pnl = (total_pnl / total_trades) if total_trades > 0 else 0.0

        def _safe_float(key, default):
            val = settings.get(key, default)
            if val is None or val == "":
                return float(default)
            try:
                return float(val)
            except (ValueError, TypeError):
                return float(default)

        vol_target = _safe_float("shadow_volatility_target_pct", "1.5")
        tp_mult = _safe_float("shadow_tp_atr_multiplier", "3.0")
        sl_mult = _safe_float("shadow_sl_atr_multiplier", "1.5")
        nn_consensus = _safe_float("shadow_nn_consensus_min_weight", "0.12")
        max_hold_hours = _safe_float("shadow_max_holding_hours", "48.0")

        report_lines = [
            "## Weekly Long-Term Strategy Attribution & Quant Optimization",
            f"Session processed **{total_trades}** shadow walk-forward trades.",
            "\n### Shadow Mode Performance Metrics:",
            f"* Win Rate: **{win_rate:.2f}%**",
            f"* Total Net Profit: **${total_pnl:.2f}**",
            f"* Average Trade PnL: **${avg_pnl:.2f}**",
            f"* Volatility Target Scaling: `{vol_target}%` of price",
            f"* ATR Stop Multipliers: TP = `{tp_mult}x ATR` | SL = `{sl_mult}x ATR`",
            f"* Neural consensus gate filter: `{nn_consensus * 100:.1f}%` min weight",
            f"* Max holding window limit: `{max_hold_hours} hours`",
        ]

        report_lines.append("\n### AI Long-Term Strategy Analysis (via OpenClaw Gateway):")

        db_prompt = settings.get("prompt_long_term_quant")
        if not db_prompt:
            db_prompt = (
                "You are a quantitative risk officer. "
                "Evaluate shadow trades and propose parameter tuning for $1,000/day target. "
                "Output JSON with keys shadow_volatility_target_pct, shadow_tp_atr_multiplier, "
                "shadow_sl_atr_multiplier, shadow_nn_consensus_min_weight, shadow_max_holding_hours."
            )
            c.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                ("prompt_long_term_quant", db_prompt),
            )
            conn.commit()

        # Summarize trades for the prompt (don't dump 50 raw trade dicts into LLM context)
        trade_summary = {
            "total": total_trades,
            "wins": len(wins),
            "losses": len(losses),
            "ties": ties,
            "win_rate_pct": round(win_rate, 1),
            "total_pnl": round(total_pnl, 2),
            "avg_pnl": round(avg_pnl, 2),
            "best_pnl": round(max((t.get("pnl") or 0.0) for t in shadow_trades), 2) if shadow_trades else 0,
            "worst_pnl": round(min((t.get("pnl") or 0.0) for t in shadow_trades), 2) if shadow_trades else 0,
        }
        # Include last 5 trades for sample detail
        recent_5 = [
            {"s": t.get("symbol", ""), "d": t.get("direction", ""),
             "pnl": round(t.get("pnl") or 0.0, 2),
             "r": t.get("exit_reason", "")[:20]}
            for t in shadow_trades[:5]
        ]
        prompt = (
            f"{db_prompt}\n\n"
            f"Current Parameters:\n"
            f"- shadow_volatility_target_pct: {vol_target}%\n"
            f"- shadow_tp_atr_multiplier: {tp_mult}x\n"
            f"- shadow_sl_atr_multiplier: {sl_mult}x\n"
            f"- shadow_nn_consensus_min_weight: {nn_consensus}\n"
            f"- shadow_max_holding_hours: {max_hold_hours}h\n\n"
            f"Walk-Forward Data Summary:\n"
            f"{json.dumps(trade_summary, indent=2)}\n"
            f"Recent Trades (last 5):\n"
            f"{json.dumps(recent_5, indent=2)}\n\n"
            f"Win Rate: {win_rate:.2f}% | Total PnL: ${total_pnl:.2f} | Avg PnL: ${avg_pnl:.2f}\n"
            f"Target: $1,000/day.\n"
            f"Output your recommended setting adjustments in a ```json block."
        )

        try:
            raw_advice = query_openclaw(prompt, agent_name="quant", max_tokens=4096)
        except Exception as e_ai:
            logging.error(f"OpenClaw call failed for LongTermQuant: {e_ai}")
            raise

        advice_clean = raw_advice
        json_block = ""
        if "```json" in raw_advice:
            parts = raw_advice.split("```json")
            advice_clean = parts[0]
            json_block = parts[1].split("```")[0].strip()

        report_lines.append(advice_clean)

        if json_block and json_block.strip():
            adjustments = json.loads(json_block)
            for key in (
                "shadow_volatility_target_pct", "shadow_tp_atr_multiplier",
                "shadow_sl_atr_multiplier", "shadow_nn_consensus_min_weight",
                "shadow_max_holding_hours",
            ):
                val = adjustments.get(key)
                if val is not None:
                    c.execute(
                        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                        (key, str(val)),
                    )
                    report_lines.append(f"\nAuto-Applied: {key} = {val}")
            conn.commit()

        # Meta-prompt optimization
        try:
            meta_prompt = (
                f"Evaluate and rewrite your prompt template. Current: {db_prompt}. "
                f"Return ONLY JSON with key 'revised_prompt_long_term_quant' (no markdown)."
            )
            raw_text = query_openclaw(meta_prompt, agent_name="quant", max_tokens=2048)
            res_data = extract_json_block(raw_text)
            if res_data and isinstance(res_data, dict):
                revised = res_data.get("revised_prompt_long_term_quant")
                if revised:
                    c.execute(
                        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                        ("prompt_long_term_quant", revised),
                    )
                    conn.commit()
                    report_lines.append("\nMeta-Optimization: updated long-term quant prompt.")
        except Exception as me_e:
            logging.error(f"Failed to meta-optimize prompt: {me_e}")

        conn.close()

        report_content = "\n".join(report_lines)
        logging.info("Long-term strategy parameters optimized:\n" + report_content)

        blog_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blog", "daily_summaries")
        if os.path.exists(blog_dir):
            report_path = os.path.join(blog_dir, "weekly_long_term_quant.md")
            with open(report_path, "w") as f:
                f.write(report_content)
            logging.info("Weekly long-term quant report saved to blog.")

    except Exception as e:
        logging.error(f"Error in Long-Term Strategy Quant session: {e}")


if __name__ == "__main__":
    run_long_term_strategy_optimization()
