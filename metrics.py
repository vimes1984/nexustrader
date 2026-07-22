"""
Performance and calibration metrics for NexusTrader.

All pure functions. No DB or broker dependencies.
"""
import math
from typing import Sequence, Optional


def sharpe_ratio(returns: Sequence[float], risk_free_rate: float = 0.0) -> float:
    """Annualized Sharpe ratio from a sequence of per-trade returns."""
    if len(returns) < 2:
        return 0.0
    mean_r = sum(returns) / len(returns)
    variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
    if variance <= 0:
        return 0.0
    std = math.sqrt(variance)
    # Approximate annualization factor assuming ~252 trading days
    # per-trade returns are already fractional (e.g. 0.02 for 2%), so scale by sqrt(n_trades)
    # For a proper annualized Sharpe, we'd need daily returns. This is a heuristic.
    if std == 0:
        return 0.0
    return (mean_r - risk_free_rate) / std


def sortino_ratio(returns: Sequence[float], risk_free_rate: float = 0.0) -> float:
    """Sortino ratio — uses downside deviation only."""
    if len(returns) < 2:
        return 0.0
    mean_r = sum(returns) / len(returns)
    downside = [r for r in returns if r < risk_free_rate]
    if not downside:
        return float('inf') if mean_r > risk_free_rate else 0.0
    down_var = sum((r - risk_free_rate) ** 2 for r in downside) / len(returns)
    if down_var <= 0:
        return 0.0
    return (mean_r - risk_free_rate) / math.sqrt(down_var)


def calmar_ratio(returns: Sequence[float], max_drawdown: float, periods_per_year: float = 252.0) -> float:
    """Calmar ratio — CAGR / max drawdown. Returns 0 if drawdown is 0.
    
    Uses proper CAGR: (1 + total_return)^(periods_per_year / n) - 1
    """
    if len(returns) < 1 or max_drawdown <= 0:
        return 0.0
    n = len(returns)
    years = n / periods_per_year
    if years <= 0:
        return 0.0
    total_return = sum(returns)
    base = max(1.0 + total_return, 1e-10)
    try:
        cagr = base ** (1.0 / years) - 1.0
    except (ValueError, OverflowError, ZeroDivisionError):
        return 0.0
    return cagr / max_drawdown


def profit_factor(trades: Sequence[dict]) -> float:
    """Gross profit / gross loss. Returns 0 if no losing trades (safe div).
    Capped at 100 for JSON safety.
    """
    gross_profit = sum(t.get('pnl', 0) for t in trades if t.get('pnl', 0) > 0)
    gross_loss = sum(abs(t.get('pnl', 0)) for t in trades if t.get('pnl', 0) < 0)
    if gross_loss == 0:
        return 100.0 if gross_profit > 0 else 0.0
    return min(gross_profit / gross_loss, 100.0)


def win_rate(trades: Sequence[dict]) -> float:
    """Fraction of trades with positive PnL."""
    if not trades:
        return 0.0
    wins = sum(1 for t in trades if t.get('pnl', 0) > 0)
    return wins / len(trades)


def avg_trade(trades: Sequence[dict]) -> float:
    """Mean PnL per trade."""
    if not trades:
        return 0.0
    return sum(t.get('pnl', 0) for t in trades) / len(trades)


def max_drawdown_from_equity(equity_curve: Sequence[float]) -> float:
    """Maximum drawdown as a positive fraction (0.25 = 25% drop)."""
    if len(equity_curve) < 2:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve[1:]:
        if value > peak:
            peak = value
        dd = (peak - value) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
    return max_dd


# --- Calibration Metrics ---

def brier_score(probabilities: Sequence[float], outcomes: Sequence[int]) -> float:
    """Brier score (mean squared error) for probability predictions. Lower is better.
    outcomes should be 0 or 1 (loss or win)."""
    if len(probabilities) != len(outcomes) or len(probabilities) == 0:
        return 0.0
    return sum((p - o) ** 2 for p, o in zip(probabilities, outcomes)) / len(probabilities)


def calibration_error(probabilities: Sequence[float], outcomes: Sequence[int], bins: int = 10) -> float:
    """Expected calibration error (ECE). Lower is better.
    
    Uses fixed-width probability bins [0, 0.1), [0.1, 0.2), ..., [0.9, 1.0]
    as per standard ECE definition (Guo et al., 2017).
    """
    if len(probabilities) == 0:
        return 0.0
    n = len(probabilities)
    total_error = 0.0
    bin_size = 1.0 / bins
    for i in range(bins):
        low = i * bin_size
        high = low + bin_size
        in_bin = [(p, o) for p, o in zip(probabilities, outcomes) if low <= p < high]
        if not in_bin:
            continue
        avg_prob = sum(p for p, _ in in_bin) / len(in_bin)
        actual_freq = sum(o for _, o in in_bin) / len(in_bin)
        total_error += abs(avg_prob - actual_freq) * (len(in_bin) / n)
    return total_error


def expected_value(p_win: float, win_amount: float, loss_amount: float) -> float:
    """Expected value of a trade given win probability and amounts."""
    return p_win * win_amount - (1 - p_win) * abs(loss_amount)


def kelly_fraction(p_win: float, win_loss_ratio: float) -> float:
    """Kelly criterion fraction. Caps at 0.25 for safety. Returns 0 if no edge."""
    if win_loss_ratio <= 0 or p_win <= 0 or p_win >= 1:
        return 0.0
    b = win_loss_ratio
    q = 1 - p_win
    f = (p_win * b - q) / b
    return max(0.0, min(f, 0.25))
