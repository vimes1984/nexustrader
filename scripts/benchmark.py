#!/usr/bin/env python3
"""
Benchmark Harness for NexusTrader.

Runs the BacktestEngine against sample candle data, comparing all
baselines (buy-and-hold, EMA crossover, random, ensemble) with
optional PPO policy replay.  Reports performance metrics.

Safe to run in any environment — uses synthetic data when real
market data is unavailable.

Usage:
    python3 scripts/benchmark.py                       # synthetic data
    python3 scripts/benchmark.py --symbol BTC-USD      # real data mode (stub)
    python3 scripts/benchmark.py --json                # JSON output
"""

import argparse
import json
import math
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _generate_synthetic_candles(n: int = 252, seed: int = 42) -> list:
    """Generate synthetic OHLCV candles with a slight upward drift."""
    rng = random.Random(seed)
    candles = []
    price = 100.0
    for _ in range(n):
        change = rng.gauss(0.001, 0.02)  # +0.1% mean, 2% std
        price *= (1 + change)
        candles.append({
            "close": round(price, 2),
            "open": round(price / (1 + rng.uniform(-0.01, 0.01)), 2),
            "high": round(price * (1 + abs(rng.gauss(0, 0.005))), 2),
            "low": round(price * (1 - abs(rng.gauss(0, 0.005))), 2),
            "volume": round(rng.uniform(100, 10000), 2),
        })
    return candles


def run_benchmark(symbol: str = "SYNTH-USD", candles: list = None,
                  ppo_agent=None, json_output: bool = False) -> dict:
    """Run the benchmark and print / return results."""
    try:
        from backtest_engine import BacktestEngine
        from cost_model import CostModel
    except ImportError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Benchmark requires sklearn and other dependencies.", file=sys.stderr)
        print("Install with: pip install -r requirements.txt", file=sys.stderr)
        sys.exit(1)

    if candles is None:
        candles = _generate_synthetic_candles(252)

    cost_model = CostModel(maker_fee=0.001, taker_fee=0.002,
                           slippage_bps=2, spread_bps=1)
    engine = BacktestEngine(symbol, cost_model=cost_model)
    result = engine.run(candles, period_start="benchmark_start",
                        period_end="benchmark_end", ppo_agent=ppo_agent)

    verdict = result["verdict"]
    results = result["results"]

    summary = {
        "symbol": symbol,
        "candles": len(candles),
        "tradable": verdict.get("tradable", False),
        "nexus_return": results["nexus_ensemble"].get("total_return", 0),
        "nexus_sharpe": results["nexus_ensemble"].get("sharpe", 0),
        "buy_and_hold_return": results["buy_and_hold"].get("total_return", 0),
        "ema_return": results["ema_crossover"].get("total_return", 0),
        "random_return": results["random_same_risk"].get("total_return", 0),
        "beats_buy_and_hold": verdict.get("beats_buy_and_hold", False),
        "beats_ema": verdict.get("beats_ema", False),
        "beats_random": verdict.get("beats_random", False),
    }

    if "ppo_policy" in results and results["ppo_policy"]:
        ppo = results["ppo_policy"]
        summary["ppo_return"] = ppo.get("total_return", 0)
        summary["ppo_sharpe"] = ppo.get("sharpe", 0)
        summary["ppo_beats_buy_and_hold"] = verdict.get("ppo_beats_buy_and_hold", False)
        summary["ppo_beats_ema"] = verdict.get("ppo_beats_ema", False)
        summary["ppo_beats_nexus"] = verdict.get("ppo_beats_nexus", False)

    if json_output:
        print(json.dumps(summary, indent=2))
    else:
        _print_summary(summary)

    return summary


def _print_summary(s: dict):
    """Pretty-print benchmark results."""
    print(f"\n{'=' * 56}")
    print(f"  Benchmark: {s['symbol']}  |  {s['candles']} candles")
    print(f"{'=' * 56}")
    print(f"  Tradable:          {'✅ YES' if s['tradable'] else '❌ NO'}")
    print(f"  Nexus Ensemble:")
    print(f"    Total Return:    {s['nexus_return']:+.4%}")
    print(f"    Sharpe:          {s['nexus_sharpe']:.4f}")
    print(f"  Buy & Hold:        {s['buy_and_hold_return']:+.4%}")
    print(f"  EMA Crossover:     {s['ema_return']:+.4%}")
    print(f"  Random (same risk):{s['random_return']:+.4%}")
    stat = lambda v: '✅' if v else '❌'
    print(f"  Beats B&H:         {stat(s['beats_buy_and_hold'])}")
    print(f"  Beats EMA:         {stat(s['beats_ema'])}")
    print(f"  Beats Random:      {stat(s['beats_random'])}")
    if s.get("ppo_return") is not None:
        print(f"  PPO Policy:")
        print(f"    Total Return:    {s['ppo_return']:+.4%}")
        print(f"    Sharpe:          {s['ppo_sharpe']:.4f}")
        print(f"    PPO beats B&H:   {stat(s.get('ppo_beats_buy_and_hold', False))}")
        print(f"    PPO beats EMA:   {stat(s.get('ppo_beats_ema', False))}")
        print(f"    PPO beats Nexus: {stat(s.get('ppo_beats_nexus', False))}")
    print(f"{'=' * 56}\n")


def main():
    parser = argparse.ArgumentParser(description="NexusTrader Benchmark Harness")
    parser.add_argument("--symbol", default="SYNTH-USD", help="Ticker symbol")
    parser.add_argument("--candles", type=int, default=252,
                        help="Number of synthetic candles to generate")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON")
    parser.add_argument("--ppo", action="store_true",
                        help="Include PPO policy replay benchmark")
    args = parser.parse_args()

    candles = _generate_synthetic_candles(args.candles, args.seed)

    ppo_agent = None
    if args.ppo:
        # Create a minimal PPO agent with random weights for benchmark
        try:
            from ppo_agent import PPOAgent
            from learning_engine import PolicyNetwork
            pn = PolicyNetwork()
            ppo_agent = PPOAgent(pn)
        except Exception as e:
            print(f"Warning: Could not create PPO agent: {e}", file=sys.stderr)

    run_benchmark(args.symbol, candles, ppo_agent, args.json)


if __name__ == "__main__":
    main()
