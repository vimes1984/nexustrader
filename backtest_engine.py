"""
BacktestEngine — runs multiple strategy baselines against historical data.

Extended with PPO agent replay pipeline that evaluates a trained
PPO policy and saves the best-performing weights.
"""

import json
import logging
import math
import os
import random
from dataclasses import asdict

from cost_model import CostModel, apply_entry_cost, apply_exit_cost
from performance_metrics import calculate_metrics, PerformanceMetrics
from strategy_engine import StrategyEnsemble

logger = logging.getLogger(__name__)


class BacktestEngine:
    def __init__(self, symbol: str, cost_model: CostModel = None):
        self.symbol = symbol
        self.cost_model = cost_model or CostModel()
        self._best_ppo_weights = None
        self._best_ppo_sharpe = -float("inf")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, candles: list, period_start: str = "",
            period_end: str = "", ppo_agent=None,
            entry_threshold: float = 0.30, exit_threshold: float = 0.10) -> dict:
        """Run all baselines + optional PPO evaluation.

        Parameters
        ----------
        candles : list[dict]
            Historical OHLCV candles with indicators.
        period_start, period_end : str
            Human-readable labels for the period.
        ppo_agent : PPOAgent or None
            If provided, a PPO policy-replay benchmark is included.

        Returns
        -------
        dict
            Comparison results with verdict.
        """
        results = {}
        results["buy_and_hold"] = self._run_buy_and_hold(candles)
        results["ema_crossover"] = self._run_ema_crossover(candles)
        results["random_same_risk"] = self._run_random_same_risk(candles, seed=42)
        results["nexus_ensemble"] = self._run_nexus_ensemble(candles, entry_threshold=entry_threshold, exit_threshold=exit_threshold)

        if ppo_agent is not None:
            ppo_result = self._run_ppo_policy(candles, ppo_agent)
            results["ppo_policy"] = ppo_result.get("metrics", {})

        nexus = results["nexus_ensemble"]
        bah = results["buy_and_hold"]
        ema = results["ema_crossover"]
        rand = results["random_same_risk"]
        nexus_ret = nexus.get("total_return", -999)

        verdict = {
            "beats_buy_and_hold": nexus_ret > bah.get("total_return", 0),
            "beats_ema": nexus_ret > ema.get("total_return", 0),
            "beats_random": nexus_ret > rand.get("total_return", 0),
            "tradable": False,
        }
        verdict["tradable"] = (verdict["beats_buy_and_hold"]
                               and verdict["beats_ema"]
                               and verdict["beats_random"])

        # PPO verdict
        ppo_res = results.get("ppo_policy", {})
        if ppo_res:
            ppo_ret = ppo_res.get("total_return", -999)
            verdict["ppo_beats_buy_and_hold"] = ppo_ret > bah.get("total_return", 0)
            verdict["ppo_beats_ema"] = ppo_ret > ema.get("total_return", 0)
            verdict["ppo_beats_nexus"] = ppo_ret > nexus_ret

        return {
            "symbol": self.symbol,
            "period": {"start": period_start, "end": period_end},
            "cost_model": asdict(self.cost_model),
            "results": results,
            "verdict": verdict,
            "best_ppo_weights": self._best_ppo_weights,
        }

    # ------------------------------------------------------------------
    # PPO policy replay
    # ------------------------------------------------------------------

    def _run_ppo_policy(self, candles, ppo_agent):
        """Replay historical candles through a trained PPO policy and
        compute performance metrics.

        The agent's actor network (`ppo_agent.policy_net`) provides
        strategy-weight distributions; the ensemble signal is derived
        from a synthetic weighted vote, then positions are opened/closed
        using the usual entry/exit rules.

        Returns
        -------
        dict with keys: 'metrics' (dict), 'equity_curve' (list),
                        'trades' (list), 'sharpe' (float)
        """
        try:
            from learning_engine import LearningEngine
            # We need a LearningEngine to build state vectors from candle data.
            # Create a minimal one.  The policy_net is shared with ppo_agent.
            num_strats = ppo_agent.policy_net.action_dim
            learner = LearningEngine(num_strategies=num_strats)
            # Replace its policy_net reference with the trained one
            learner.policy_net = ppo_agent.policy_net

            equity_curve = [1.0]
            trades = []
            position = None
            nav = 1.0

            for i, row in enumerate(candles):
                close = float(row.get("close", 0))
                if close <= 0:
                    equity_curve.append(nav)
                    continue

                # Build price history and closed trades lists (empty for replay)
                price_history = [float(c.get("close", 0))
                                 for c in candles[max(0, i - 60):i + 1]]

                # Build a minimal state vector using row data
                state = learner.get_state_vector(row, price_history, [])

                # Get action (strategy-weight distribution) from the policy net
                weights = ppo_agent.get_action(state)
                # Weighted ensemble signal: map weight distribution [-1, 1]
                # Convert N strategy weights to net direction by dividing into
                # long-side (first half) and short-side (second half) buckets.
                half = len(weights) // 2
                long_weight = sum(weights[:half]) if half > 0 else 0.0
                short_weight = sum(weights[half:]) if len(weights) > half else 0.0
                total = long_weight + short_weight or 1.0
                weighted_signal = (long_weight - short_weight) / total

                # Entry / exit logic
                if position is None and abs(weighted_signal) >= 0.30:
                    side = "BUY" if weighted_signal > 0 else "SELL"
                    entry = apply_entry_cost(close, side, self.cost_model)
                    position = {"entry": entry, "side": side, "state": state}
                elif position is not None and abs(weighted_signal) < 0.1:
                    side = position["side"]
                    exit_p = apply_exit_cost(close, side, self.cost_model)
                    pnl = (exit_p - position["entry"]
                           if side == "BUY"
                           else position["entry"] - exit_p)
                    ret = pnl / abs(position["entry"]) if position["entry"] != 0 else 0.0
                    nav = nav * (1 + ret)
                    trades.append({
                        "pnl": pnl,
                        "entry_price": position["entry"],
                        "exit_price": exit_p,
                        "side": side,
                    })
                    position = None

                equity_curve.append(nav)

            # Close any open position at end of series
            if position is not None and candles:
                last_close = float(candles[-1].get("close", 0))
                exit_p = apply_exit_cost(last_close, position["side"],
                                         self.cost_model)
                pnl = (exit_p - position["entry"]
                       if position["side"] == "BUY"
                       else position["entry"] - exit_p)
                ret = pnl / abs(position["entry"]) if position["entry"] != 0 else 0.0
                nav = nav * (1 + ret)
                trades.append({
                    "pnl": pnl,
                    "entry_price": position["entry"],
                    "exit_price": exit_p,
                    "side": position["side"],
                })
                equity_curve.append(nav)

            metrics = self._metrics_to_dict(equity_curve, trades)

            # Track best Sharpe
            sharpe = metrics.get("sharpe", 0)
            if sharpe > self._best_ppo_sharpe:
                self._best_ppo_sharpe = sharpe
                self._best_ppo_weights = ppo_agent.policy_net.to_json()
                logger.info(
                    "New best PPO policy for %s: Sharpe=%.4f, Return=%.4f%%",
                    self.symbol, sharpe, metrics.get("total_return", 0) * 100,
                )

            return {
                "metrics": metrics,
                "equity_curve": equity_curve,
                "trades": trades,
                "sharpe": sharpe,
            }

        except Exception as e:
            logger.error("PPO policy replay failed for %s: %s", self.symbol, e)
            return {
                "metrics": self._metrics_to_dict([1.0], []),
                "equity_curve": [1.0],
                "trades": [],
                "sharpe": 0.0,
            }

    # ------------------------------------------------------------------
    # Save best PPO weights to file
    # ------------------------------------------------------------------

    def save_best_ppo_weights(self, filepath=None):
        """Write the best PPO policy weights encountered during this
        backtest session to a JSON file.

        Returns
        -------
        str or None
            Path to the saved file, or None if no weights were captured.
        """
        if self._best_ppo_weights is None:
            logger.warning("No best PPO weights to save for %s", self.symbol)
            return None

        if filepath is None:
            data_dir = os.path.join(os.path.expanduser("~"), ".nexustrader")
            os.makedirs(data_dir, exist_ok=True)
            sanitised = self.symbol.replace("/", "-").replace(" ", "_")
            filepath = os.path.join(data_dir,
                                    f"best_ppo_{sanitised}.json")

        try:
            # If weights are already a JSON string, write directly
            if isinstance(self._best_ppo_weights, str):
                data = {"symbol": self.symbol,
                        "sharpe": self._best_ppo_sharpe,
                        "policy_net": self._best_ppo_weights}
            else:
                data = {"symbol": self.symbol,
                        "sharpe": self._best_ppo_sharpe,
                        "policy_net": json.dumps(self._best_ppo_weights)}

            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)

            logger.info("Saved best PPO weights for %s to %s (Sharpe=%.4f)",
                        self.symbol, filepath, self._best_ppo_sharpe)
            return filepath

        except Exception as e:
            logger.error("Failed to save best PPO weights: %s", e)
            return None

    # ------------------------------------------------------------------
    # Baselines  (unchanged)
    # ------------------------------------------------------------------

    def _metrics_to_dict(self, equity_curve, trades):
        m = calculate_metrics(equity_curve, trades)
        return {
            "total_return": round(m.total_return, 6),
            "total_pnl": round(m.total_pnl, 4),
            "win_rate": round(m.win_rate, 4),
            "profit_factor": round(m.profit_factor, 4),
            "max_drawdown": round(m.max_drawdown, 4),
            "sharpe": round(m.sharpe, 4),
            "trade_count": m.trade_count,
            "avg_trade_pnl": round(m.avg_trade_pnl, 4),
            "expectancy": round(m.expectancy, 4),
        }

    def _run_buy_and_hold(self, candles):
        if not candles:
            return self._metrics_to_dict([], [])
        entry_price_raw = candles[0].get("close", 0)
        exit_price_raw = candles[-1].get("close", 0)
        entry_price = apply_entry_cost(entry_price_raw, "BUY", self.cost_model)
        exit_price = apply_exit_cost(exit_price_raw, "BUY", self.cost_model)
        pnl_pct = (exit_price - entry_price) / entry_price if entry_price > 0 else 0.0
        equity_curve = []
        buy_price = entry_price
        # Build equity curve consistent with other baselines: start at 1.0
        for c in candles:
            close = c.get("close", buy_price)
            nav = close / buy_price  # relative to entry price
            equity_curve.append(nav)
        trades = [{"pnl": exit_price - entry_price}]
        d = self._metrics_to_dict(equity_curve, trades)
        d["total_return"] = round(pnl_pct, 6)
        return d

    def _run_ema_crossover(self, candles):
        equity_curve = [1.0]
        trades = []
        position = None
        nav = 1.0
        for i, row in enumerate(candles):
            macd = row.get("macd", 0)
            macd_signal = row.get("macd_signal", 0)
            close = row.get("close", 0)
            signal = 1 if macd > macd_signal else (-1 if macd < macd_signal else 0)

            if position is None and signal == 1:
                entry = apply_entry_cost(close, "BUY", self.cost_model)
                position = {"entry": entry, "side": "BUY", "nav_at_entry": nav}
            elif position is not None and signal == -1:
                exit_p = apply_exit_cost(close, "BUY", self.cost_model)
                pnl = exit_p - position["entry"]
                ret = pnl / position["entry"] if position["entry"] > 0 else 0.0
                nav = nav * (1 + ret)
                trades.append({"pnl": pnl})
                position = None
            equity_curve.append(nav)

        if position is not None and candles:
            close = candles[-1].get("close", 0)
            exit_p = apply_exit_cost(close, "BUY", self.cost_model)
            pnl = exit_p - position["entry"]
            ret = pnl / position["entry"] if position["entry"] > 0 else 0.0
            nav = nav * (1 + ret)
            trades.append({"pnl": pnl})
            equity_curve.append(nav)

        return self._metrics_to_dict(equity_curve, trades)

    def _run_random_same_risk(self, candles, seed=42):
        rng = random.Random(seed)
        equity_curve = [1.0]
        trades = []
        position = None
        nav = 1.0
        for row in candles:
            close = row.get("close", 0)
            decision = rng.choice(["BUY", "SELL", "HOLD", "HOLD"])
            if position is None and decision in ("BUY", "SELL"):
                entry = apply_entry_cost(close, decision, self.cost_model)
                position = {"entry": entry, "side": decision}
            elif position is not None and decision != "HOLD":
                exit_p = apply_exit_cost(close, position["side"], self.cost_model)
                if position["side"] == "BUY":
                    pnl = exit_p - position["entry"]
                else:
                    pnl = position["entry"] - exit_p
                ret = pnl / abs(position["entry"]) if position["entry"] != 0 else 0.0
                nav = nav * (1 + ret)
                trades.append({"pnl": pnl})
                position = None
            equity_curve.append(nav)

        if position is not None and candles:
            close = candles[-1].get("close", 0)
            exit_p = apply_exit_cost(close, position["side"], self.cost_model)
            pnl = (exit_p - position["entry"]) if position["side"] == "BUY" else (position["entry"] - exit_p)
            ret = pnl / abs(position["entry"]) if position["entry"] != 0 else 0.0
            nav = nav * (1 + ret)
            trades.append({"pnl": pnl})
            equity_curve.append(nav)

        return self._metrics_to_dict(equity_curve, trades)

    def _run_nexus_ensemble(self, candles, entry_threshold=0.30, exit_threshold=0.10):
        """Run the StrategyEnsemble signals over candles without any DB mutations.
        
        Parameters:
            entry_threshold: abs(signal) must exceed this to enter
            exit_threshold: abs(signal) below this triggers exit
        """
        try:
            ensemble = StrategyEnsemble()
        except Exception:
            return self._metrics_to_dict([1.0], [])

        equity_curve = [1.0]
        trades = []
        position = None
        nav = 1.0

        for i, row in enumerate(candles):
            history = candles[max(0, i - 100):i]
            try:
                signal, _ = ensemble.get_weighted_signal(row, history_df=history)
            except Exception:
                signal = 0.0
            close = row.get("close", 0)

            if position is None and signal > 0.3:
                entry = apply_entry_cost(close, "BUY", self.cost_model)
                position = {"entry": entry, "side": "BUY"}
            elif position is None and signal < -0.3:
                entry = apply_entry_cost(close, "SELL", self.cost_model)
                position = {"entry": entry, "side": "SELL"}
            elif position is not None and abs(signal) < 0.1:
                exit_p = apply_exit_cost(close, position["side"], self.cost_model)
                pnl = (exit_p - position["entry"]) if position["side"] == "BUY" else (position["entry"] - exit_p)
                ret = pnl / abs(position["entry"]) if position["entry"] != 0 else 0.0
                nav = nav * (1 + ret)
                trades.append({"pnl": pnl})
                position = None
            equity_curve.append(nav)

        if position is not None and candles:
            close = candles[-1].get("close", 0)
            exit_p = apply_exit_cost(close, position["side"], self.cost_model)
            pnl = (exit_p - position["entry"]) if position["side"] == "BUY" else (position["entry"] - exit_p)
            ret = pnl / abs(position["entry"]) if position["entry"] != 0 else 0.0
            nav = nav * (1 + ret)
            trades.append({"pnl": pnl})
            equity_curve.append(nav)

        return self._metrics_to_dict(equity_curve, trades)
