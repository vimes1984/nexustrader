from dataclasses import dataclass, field
from typing import List, Optional
import math

@dataclass
class PerformanceMetrics:
    total_return: float = 0.0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    sharpe: float = 0.0
    trade_count: int = 0
    avg_trade_pnl: float = 0.0
    avg_winner: float = 0.0
    avg_loser: float = 0.0
    expectancy: float = 0.0

def calculate_metrics(equity_curve: List[float], trades: List[dict], periods_per_year: int = 252, risk_free_rate: float = 0.0) -> PerformanceMetrics:
    """
    Calculate performance metrics from an equity curve and list of trades.
    trades: list of dicts with keys: pnl (float)
    equity_curve: list of portfolio values over time
    """
    m = PerformanceMetrics()
    m.trade_count = len(trades)

    # Process equity curve FIRST (before early return for empty trades)
    if equity_curve and len(equity_curve) > 1:
        peak = equity_curve[0]
        max_dd = 0.0
        for val in equity_curve:
            if val > peak:
                peak = val
            dd = (peak - val) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        m.max_drawdown = max_dd
        start = equity_curve[0]
        end = equity_curve[-1]
        m.total_return = ((end - start) / start) if start > 0 else 0.0

    if len(equity_curve) > 2:
        returns = []
        for i in range(1, len(equity_curve)):
            prev = equity_curve[i - 1]
            curr = equity_curve[i]
            r = (curr - prev) / prev if prev > 0 else 0.0
            returns.append(r)
        n = len(returns)
        if n > 1:
            mean_r = sum(returns) / n
            variance = sum((r - mean_r) ** 2 for r in returns) / (n - 1)
            std_r = math.sqrt(variance) if variance > 0 else 0.0
            # Annualized Sharpe (with risk-free rate)
            excess_mean = mean_r - (risk_free_rate / periods_per_year)  # convert yearly rf to per-period
            m.sharpe = (excess_mean / std_r * math.sqrt(periods_per_year)) if std_r > 1e-10 else 0.0

    if not trades:
        return m

    pnls = [t.get("pnl", 0.0) for t in trades]
    winners = [p for p in pnls if p > 0]
    losers = [p for p in pnls if p <= 0]

    m.total_pnl = sum(pnls)
    m.win_rate = len(winners) / len(pnls) if pnls else 0.0
    m.avg_trade_pnl = m.total_pnl / len(pnls) if pnls else 0.0
    m.avg_winner = sum(winners) / len(winners) if winners else 0.0
    m.avg_loser = sum(losers) / len(losers) if losers else 0.0

    gross_profit = sum(winners)
    gross_loss = abs(sum(losers))
    # Cap profit factor at 100 for JSON-safety (inf breaks serialization)
    if gross_loss > 0:
        m.profit_factor = min(gross_profit / gross_loss, 100.0)
    else:
        m.profit_factor = 100.0 if gross_profit > 0 else 0.0

    m.expectancy = (m.win_rate * m.avg_winner) + ((1 - m.win_rate) * m.avg_loser)

    return m
