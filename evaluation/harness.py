"""
Strategy benchmark harness.

Compares any strategy against:
- Buy-and-hold
- Simple EMA crossover
- Random entry with same risk profile

Reports: Sharpe, max drawdown, win rate, profit factor, Calmar ratio.
"""

import random
import math
from typing import Callable, Optional, Sequence
from .metrics import (
    sharpe_ratio, sortino_ratio, calmar_ratio,
    profit_factor, win_rate, avg_trade, max_drawdown_from_equity,
)
from .cost_model import DEFAULT_MAKER_FEE, DEFAULT_TAKER_FEE, DEFAULT_SPREAD, DEFAULT_SLIPPAGE


def simulate_ema_crossover(
    closes: Sequence[float],
    fast_period: int = 12,
    slow_period: int = 26,
    initial_capital: float = 1000.0,
    fee_rate: float = DEFAULT_TAKER_FEE,
) -> dict:
    """Simulate a simple EMA crossover strategy.

    Returns performance metrics.
    """
    if len(closes) < slow_period + 1:
        return _empty_result(initial_capital)

    def ema(data, period):
        multiplier = 2 / (period + 1)
        result = [data[0]]
        for i in range(1, len(data)):
            result.append((data[i] - result[-1]) * multiplier + result[-1])
        return result

    fast_ema = ema(closes, fast_period)
    slow_ema = ema(closes, slow_period)

    equity = [initial_capital]
    position = 0  # shares held
    cash = initial_capital

    for i in range(1, len(closes)):
        if fast_ema[i] > slow_ema[i] and fast_ema[i - 1] <= slow_ema[i - 1]:
            # Buy signal
            if position == 0 and cash > 0:
                position = (cash * (1 - fee_rate)) / closes[i]
                cash = 0
        elif fast_ema[i] < slow_ema[i] and fast_ema[i - 1] >= slow_ema[i - 1]:
            # Sell signal
            if position > 0:
                cash = position * closes[i] * (1 - fee_rate)
                position = 0
        equity.append(cash + position * closes[i])

    # Final value
    final_value = cash + position * closes[-1] if position > 0 else cash
    returns = _returns_from_equity(equity)
    dd = max_drawdown_from_equity(equity)
    return {
        "final_value": final_value,
        "total_return_pct": (final_value - initial_capital) / initial_capital * 100,
        "sharpe": sharpe_ratio(returns),
        "sortino": sortino_ratio(returns),
        "max_drawdown_pct": dd * 100,
        "win_rate": 0.0,  # not trade-level
        "profit_factor": 0.0,
        "calmar": calmar_ratio(returns, dd),
    }


def simulate_buy_and_hold(
    closes: Sequence[float],
    initial_capital: float = 1000.0,
    fee_rate: float = DEFAULT_TAKER_FEE,
) -> dict:
    """Simple buy-and-hold benchmark."""
    if not closes:
        return _empty_result(initial_capital)
    shares = (initial_capital * (1 - fee_rate)) / closes[0]
    final_value = shares * closes[-1]
    equity = [initial_capital]
    for price in closes[1:]:
        equity.append(shares * price)
    returns = _returns_from_equity(equity)
    dd = max_drawdown_from_equity(equity)
    return {
        "final_value": final_value,
        "total_return_pct": (final_value - initial_capital) / initial_capital * 100,
        "sharpe": sharpe_ratio(returns),
        "sortino": sortino_ratio(returns),
        "max_drawdown_pct": dd * 100,
        "win_rate": 1.0 if final_value > initial_capital else 0.0,
        "profit_factor": float('inf') if final_value > initial_capital else 0.0,
        "calmar": calmar_ratio(returns, dd),
    }


def simulate_random_entry(
    closes: Sequence[float],
    trade_frequency: float = 0.2,
    initial_capital: float = 1000.0,
    fee_rate: float = DEFAULT_TAKER_FEE,
) -> dict:
    """Random entry benchmark — same number of trades, random direction."""
    if len(closes) < 2:
        return _empty_result(initial_capital)

    equity = [initial_capital]
    position = 0
    cash = initial_capital
    in_trade = False

    for i in range(1, len(closes)):
        if not in_trade and random.random() < trade_frequency:
            # Random entry
            direction = 1 if random.random() < 0.5 else -1
            position = direction * (cash * (1 - fee_rate)) / closes[i]
            cash = 0
            in_trade = True
        elif in_trade:
            # Close next bar
            pnl_pct = (closes[i] - closes[i - 1]) / closes[i - 1] * (1 if position > 0 else -1)
            cash = abs(position) * closes[i] * (1 - fee_rate)
            position = 0
            in_trade = False

        equity.append(cash + abs(position) * closes[i] if position else cash)

    final_value = equity[-1]
    returns = _returns_from_equity(equity)
    dd = max_drawdown_from_equity(equity)
    return {
        "final_value": final_value,
        "total_return_pct": (final_value - initial_capital) / initial_capital * 100,
        "sharpe": sharpe_ratio(returns),
        "sortino": sortino_ratio(returns),
        "max_drawdown_pct": dd * 100,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "calmar": calmar_ratio(returns, dd),
    }


def benchmark_strategy(
    closes: Sequence[float],
    strategy_fn: Callable,
    initial_capital: float = 1000.0,
    name: str = "strategy",
    fee_rate: float = DEFAULT_TAKER_FEE,
) -> dict:
    """Run a custom strategy function and compare with baselines.

    strategy_fn(closes, initial_capital, fee_rate) should return a dict with at least:
        final_value, total_return_pct, sharpe, max_drawdown_pct

    Returns comparison dict with strategy result and benchmarks.
    """
    # Force deterministic random seed for reproducible benchmarks
    random.seed(42)

    strategy_result = strategy_fn(closes, initial_capital, fee_rate)
    bh_result = simulate_buy_and_hold(closes, initial_capital, fee_rate)
    ema_result = simulate_ema_crossover(closes, initial_capital=initial_capital, fee_rate=fee_rate)

    strategy_sharpe = strategy_result.get("sharpe", 0)
    bh_sharpe = bh_result.get("sharpe", 0)
    ema_sharpe = ema_result.get("sharpe", 0)

    beats_bh = strategy_sharpe > bh_sharpe if bh_sharpe != 0 else strategy_sharpe > 0
    beats_ema = strategy_sharpe > ema_sharpe if ema_sharpe != 0 else strategy_sharpe > 0

    return {
        "name": name,
        "initial_capital": initial_capital,
        "strategy": strategy_result,
        "benchmarks": {
            "buy_and_hold": bh_result,
            "ema_crossover": ema_result,
        },
        "has_edge": {
            "beats_buy_and_hold": beats_bh,
            "beats_ema_crossover": beats_ema,
        },
    }


def _empty_result(initial_capital: float) -> dict:
    return {
        "final_value": initial_capital,
        "total_return_pct": 0.0,
        "sharpe": 0.0,
        "sortino": 0.0,
        "max_drawdown_pct": 0.0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "calmar": 0.0,
    }


def _returns_from_equity(equity: Sequence[float]):
    """Convert equity curve to per-step returns."""
    returns = []
    for i in range(1, len(equity)):
        if equity[i - 1] > 0:
            returns.append((equity[i] - equity[i - 1]) / equity[i - 1])
    return returns
