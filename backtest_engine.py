import json, math, random
from dataclasses import asdict
from cost_model import CostModel, apply_entry_cost, apply_exit_cost
from performance_metrics import calculate_metrics, PerformanceMetrics
from strategy_engine import StrategyEnsemble

class BacktestEngine:
    def __init__(self, symbol: str, cost_model: CostModel = None):
        self.symbol = symbol
        self.cost_model = cost_model or CostModel()

    def run(self, candles: list, period_start: str = "", period_end: str = "") -> dict:
        """Run all baselines and return comparison JSON."""
        results = {}
        results["buy_and_hold"] = self._run_buy_and_hold(candles)
        results["ema_crossover"] = self._run_ema_crossover(candles)
        results["random_same_risk"] = self._run_random_same_risk(candles, seed=42)
        results["nexus_ensemble"] = self._run_nexus_ensemble(candles)

        nexus = results["nexus_ensemble"]
        bah = results["buy_and_hold"]
        ema = results["ema_crossover"]
        rand = results["random_same_risk"]

        nexus_ret = nexus.get("total_return", -999)
        verdict = {
            "beats_buy_and_hold": nexus_ret > bah.get("total_return", 0),
            "beats_ema": nexus_ret > ema.get("total_return", 0),
            "beats_random": nexus_ret > rand.get("total_return", 0),
            "tradable": False,  # only True if beats ALL baselines
        }
        verdict["tradable"] = verdict["beats_buy_and_hold"] and verdict["beats_ema"] and verdict["beats_random"]

        return {
            "symbol": self.symbol,
            "period": {"start": period_start, "end": period_end},
            "cost_model": asdict(self.cost_model),
            "results": results,
            "verdict": verdict,
        }

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
        nav = 1.0
        buy_price = entry_price
        for c in candles:
            close = c.get("close", buy_price)
            nav = close / buy_price
            equity_curve.append(nav)
        trades = [{"pnl": exit_price - entry_price}]
        m = calculate_metrics(equity_curve, trades)
        d = self._metrics_to_dict(equity_curve, trades)
        d["total_return"] = round(pnl_pct, 6)
        return d

    def _run_ema_crossover(self, candles):
        equity_curve = [1.0]
        trades = []
        position = None  # None or {"entry": price, "side": "BUY"}
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
            decision = rng.choice(["BUY", "SELL", "HOLD", "HOLD"])  # 50% hold
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

    def _run_nexus_ensemble(self, candles):
        """Run the StrategyEnsemble signals over candles without any DB mutations."""
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
                signal, _ = ensemble.generate_ensemble_signal(row, history_df=history)
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
