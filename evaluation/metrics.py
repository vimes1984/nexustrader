"""
Performance and calibration metrics for NexusTrader.

All pure functions. No DB or broker dependencies.
"""
import math
from typing import Sequence, Optional


def sharpe_ratio(returns: Sequence[float], risk_free_rate: float = 0.0) -> float:
    """Annualized Sharpe ratio from a sequence of per-trade returns.
    
    NOTE: This function receives per-trade returns, not daily returns.
    Annualization by sqrt(252) is only valid for daily returns.
    For per-trade returns, proper annualization requires sqrt(avg_trades_per_year).
    Without that info, we compute the non-annualized version or let the caller
    pass appropriate scaling. Here we return the non-annualized Sharpe.
    """
    if len(returns) < 2:
        return 0.0
    mean_r = sum(returns) / len(returns)
    variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
    if variance <= 0:
        return 0.0
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    # Non-annualized Sharpe (per-trade basis). For annualized, multiply by sqrt(trades_per_year).
    return (mean_r - risk_free_rate) / std


def sortino_ratio(returns: Sequence[float], risk_free_rate: float = 0.0) -> float:
    """Sortino ratio — uses downside deviation only.
    
    Standard formula: (mean_return - risk_free) / downside_deviation
    where downside_deviation = sqrt( sum(min(r - rf, 0)^2) / N )
    
    Returns non-annualized Sortino. For annualized, multiply by sqrt(periods_per_year).
    """
    if len(returns) < 2:
        return 0.0
    mean_r = sum(returns) / len(returns)
    # Downside deviation: semi-variance of returns below risk-free rate
    n = len(returns)
    downside_var = sum(min(r - risk_free_rate, 0) ** 2 for r in returns) / n
    if downside_var <= 0:
        return float('inf') if mean_r > risk_free_rate else 0.0
    return (mean_r - risk_free_rate) / math.sqrt(downside_var)


def calmar_ratio(returns: Sequence[float], max_drawdown: float) -> float:
    """Calmar ratio — CAGR / max drawdown. Returns 0 if drawdown is 0.
    
    CAGR = (1 + cumulative_return)^(1/years) - 1
    For simplicity when period info is unavailable, uses the mean return as approximation.
    
    NOTE: Proper Calmar requires knowing the time span. The sum-of-returns approximation
    is only valid when returns are small (ln(1+r) ~ r).
    """
    if len(returns) < 1 or max_drawdown <= 0:
        return 0.0
    # Cumulative return as sum of log returns approximation
    total_return = sum(returns)
    # Annualized mean return *as an approximation of CAGR*
    cagr = total_return / len(returns) * 252  # rough annualization
    return cagr / max_drawdown


def profit_factor(trades: Sequence[dict]) -> float:
    """Gross profit / gross loss. Returns 0 if no losing trades (safe div)."""
    gross_profit = sum(t.get('pnl', 0) for t in trades if t.get('pnl', 0) > 0)
    gross_loss = sum(abs(t.get('pnl', 0)) for t in trades if t.get('pnl', 0) < 0)
    if gross_loss == 0:
        return float('inf') if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


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
    """Expected calibration error (ECE). Lower is better."""
    if len(probabilities) == 0:
        return 0.0
    pairs = sorted(zip(probabilities, outcomes), key=lambda x: x[0])
    n = len(pairs)
    bin_size = max(1, n // bins)
    total_error = 0.0
    for i in range(0, n, bin_size):
        bin_pairs = pairs[i:i + bin_size]
        if not bin_pairs:
            continue
        avg_prob = sum(p for p, _ in bin_pairs) / len(bin_pairs)
        actual_freq = sum(o for _, o in bin_pairs) / len(bin_pairs)
        total_error += abs(avg_prob - actual_freq) * (len(bin_pairs) / n)
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
