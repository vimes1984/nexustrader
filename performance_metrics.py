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

def _infer_periods_per_year(curve_len: int) -> int:
    """Infer the number of bars per year from the length of the equity curve.
    
    This is a heuristic based on typical trading data granularity:
    - < 50 bars: assume weekly (52 periods/year)
    - 50-200: assume daily (252)
    - 200-1000: assume 4-hour (252*6 = 1512)
    - 1000-5000: assume hourly (252*24 = 6048)
    - 5000+: assume 5-min bars (252*78 = 19656)
    
    A value of at least 1 is always returned to prevent div-by-zero.
    """
    if curve_len < 50:
        return max(1, 52)  # weekly-ish
    elif curve_len < 200:
        return 252  # daily-ish
    elif curve_len < 1000:
        return 252 * 6  # ~4-hour bars
    elif curve_len < 5000:
        return 252 * 24  # hourly
    else:
        return 252 * 78  # 5-min bars


def calculate_metrics(equity_curve: List[float], trades: List[dict], periods_per_year: int = 0, risk_free_rate: float = 0.0) -> PerformanceMetrics:
    """
    Calculate performance metrics from an equity curve and list of trades.
    
    Parameters
    ----------
    equity_curve : list[float]
        Portfolio values over time.
    trades : list[dict]
        List of dicts with keys: pnl (float).
    periods_per_year : int
        Number of bars per year for Sharpe annualization.
        If 0 (default), inferred from equity_curve length.
    risk_free_rate : float
        Annual risk-free rate (e.g., 0.05 for 5%).
    """
    if periods_per_year == 0:
        periods_per_year = _infer_periods_per_year(len(equity_curve))
    m = PerformanceMetrics()
    # Sanitize inputs: filter NaN, None, negative values from equity curve
    cleaned_curve = [float(v) for v in equity_curve if v is not None and isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v))]
    if not cleaned_curve:
        return m

    # Process equity curve FIRST (before early return for empty trades)
    if len(cleaned_curve) > 1:
        peak = cleaned_curve[0]
        max_dd = 0.0
        for val in cleaned_curve:
            if val > peak:
                peak = val
            dd = (peak - val) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        m.max_drawdown = max_dd
        start_equity = cleaned_curve[0]
        end_equity = cleaned_curve[-1]
        if start_equity > 0:
            m.total_return = (end_equity - start_equity) / start_equity
        elif end_equity > 0:
            # Started from zero (deposit mid-track): use end as baseline
            m.total_return = 0.0
        else:
            m.total_return = 0.0

    if len(cleaned_curve) > 2:
        returns = []
        for i in range(1, len(cleaned_curve)):
            prev = cleaned_curve[i - 1]
            curr = cleaned_curve[i]
            # Guard against zero or negative equity causing division issues
            r = (curr - prev) / prev if prev > 1e-10 else 0.0
            returns.append(r)
        n = len(returns)
        if n >= 5:  # Minimum 5 observations for meaningful Sharpe
            mean_r = sum(returns) / n
            # Use population variance (MLE) with Bessel correction for small samples
            if n > 1:
                variance = sum((r - mean_r) ** 2 for r in returns) / (n - 1)
            else:
                variance = 0.0
            std_r = math.sqrt(variance) if variance > 1e-20 else 0.0
            # Annualized Sharpe (with risk-free rate)
            # Convert annual risk-free rate to per-period
            rf_period = risk_free_rate / periods_per_year
            excess_mean = mean_r - rf_period
            # Annualize: multiply per-period Sharpe by sqrt(periods)
            if std_r > 1e-10:
                m.sharpe = excess_mean / std_r * math.sqrt(periods_per_year)
            elif excess_mean > 0:
                m.sharpe = 3.0  # No volatility, pure profit — capped at 3.0 
            else:
                m.sharpe = 0.0  # No volatility, no profit

    if not trades:
        return m

    pnls = [t.get("pnl", 0.0) for t in trades]
    # Neutral trades (exactly 0.0 PnL) are NOT counted as wins or losses
    # They only contribute to total_pnl and trade_count.
    winners = [p for p in pnls if p > 0]
    neutral = [p for p in pnls if p == 0.0]
    losers = [p for p in pnls if p < 0]

    m.total_pnl = sum(pnls)
    m.trade_count = len(pnls)
    decision_count = len(winners) + len(losers)  # Exclude neutrals from win rate
    m.win_rate = len(winners) / decision_count if decision_count > 0 else 0.0
    m.avg_trade_pnl = m.total_pnl / len(pnls) if pnls else 0.0
    m.avg_winner = sum(winners) / len(winners) if winners else 0.0
    m.avg_loser = sum(losers) / len(losers) if losers else 0.0

    gross_profit = sum(winners)
    gross_loss = abs(sum(losers))
    # Cap profit factor at 100 for JSON-safety (inf breaks serialization)
    if gross_loss > 0:
        m.profit_factor = min(gross_profit / gross_loss, 100.0)
    elif gross_profit > 0:
        m.profit_factor = 100.0
    else:
        m.profit_factor = 0.0

    # Expectancy: expected PnL per trade (including neutrals at 0)
    # Using decision_count isolates predictive power from non-trading days
    m.expectancy = (m.win_rate * m.avg_winner) + ((1.0 - m.win_rate) * m.avg_loser)
    if decision_count == 0:
        m.expectancy = 0.0

    return m
