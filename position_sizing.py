"""
position_sizing.py — Fractional Kelly + volatility-targeted position sizing.

Computes the fraction of capital to risk per trade based on:
1. Historical win rate and average win/loss ratio (Kelly Criterion)
2. Brier score calibration cap
3. Current volatility (ATR/price ratio)
4. Current drawdown (reduce when underwater)

All functions are stateless and safe to call from any context.
"""

import math
import numpy as np
from typing import List, Optional

# Safety: never risk more than this fraction of capital on a single trade
ABSOLUTE_MAX_FRACTION = 0.25
# Kelly fraction multiplier for conservative sizing (half-kelly)
HALF_KELLY = 0.5
# Minimum historical trades needed for Kelly calculation
MIN_TRADES_FOR_KELLY = 10
# Minimum edge (expected return per trade) to allocate any risk budget.
# If the strategy's edge is below this threshold, treat as noise.
MIN_EDGE_FOR_RISK = 0.001  # 0.1% expected return per trade


def estimate_metrics_from_trades(trades: List[dict]) -> dict:
    """
    Computes win rate and avg win/loss ratio from a list of trade dicts.
    Each trade must have 'pnl' or 'pnl_percent' key.
    """
    if not trades:
        return {"win_rate": 0.5, "avg_win": 0.0, "avg_loss": 0.0, "count": 0}

    pnls = [t.get('pnl_percent', t.get('pnl', 0.0)) or 0.0 for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    n = len(pnls)
    win_rate = len(wins) / n if n > 0 else 0.5
    avg_win = np.mean(wins) if wins else 0.0
    avg_loss = np.mean(losses) if losses else 0.0
    # Avoid division by zero and extreme values
    avg_loss = abs(avg_loss)
    if avg_loss < 0.0005:
        avg_loss = 0.005  # Floor: at least 0.5% average loss for Kelly computation

    # Protection: if avg_win is also a floor, cap win_rate so Kelly doesn't
    # amplify noise. Trades with tiny PnLs relative to capital are unreliable.
    if avg_win < 0.001 and avg_loss <= 0.01 and n < 50:
        # Scale win_rate toward 0.5 (no edge) in proportion to tiny PnLs
        win_rate = 0.5 * win_rate + 0.25  # Shrink toward 50%

    return {
        "win_rate": win_rate,
        "avg_win": avg_win if avg_win >= 0.001 else 0.001,
        "avg_loss": avg_loss,
        "count": n
    }


def compute_kelly_fraction(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """
    Computes the Kelly fraction of portfolio to RISK (not allocate) per trade.

    Standard Kelly formula for trading outcomes:
        f* = (p * W - q * L) / (W * L)
    where:
        p = win_rate
        q = 1 - win_rate (loss rate)
        W = avg_win  (average winning PnL fraction, positive)
        L = avg_loss (average losing PnL fraction, positive)

    This gives the fraction of total capital to risk (the amount at stake).
    The position size is then: f* * capital / stop_loss_pct.

    Previous formula used f* = p - q / (W/L), which is INCORRECT for
    trading where win/loss amounts are not binary fixed-odds bets.
    The correct formula from Thorp (1969): f* = (p*W - q*L) / (W*L)

    Returns 0 if win_rate or avg_loss is invalid.
    """
    if avg_loss <= 0 and win_rate < 1.0:
        return 0.0  # No losing trades to calibrate risk
    if avg_win <= 0:
        return 0.0  # No winning trades means no edge

    # Handle edge cases at win_rate boundaries
    if win_rate <= 0:
        return 0.0  # Never bet on a guaranteed loss
    elif win_rate >= 1:
        # 100% win rate: Kelly is undefined since we have no loss examples.
        # Without knowing the true loss distribution, cap conservatively based
        # on avg_win magnitude. Very tiny avg_win → no meaningful edge.
        # Very large avg_win → unlikely to persist with 100% accuracy.
        return min(0.15, avg_win / (avg_win + 0.05))

    q = 1.0 - win_rate
    # Edge / odds formulation: f* = (p*W - q*L) / (W*L)
    # Edge = p*W - q*L, Odds = W*L (product of payoff magnitudes)
    edge = (win_rate * avg_win) - (q * avg_loss)
    if edge <= 0:
        return 0.0  # No positive edge

    odds = avg_win * avg_loss
    if odds <= 0:
        return 0.0

    kelly = edge / odds
    return max(0.0, min(kelly, 0.5))  # Cap raw Kelly at 0.5 — above this means 'bet it all' which breaks down in trading


def compute_safe_fraction(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    n_trades: int,
    calibration_cap: float = 0.15,
    current_drawdown_pct: float = 0.0,
    drawdown_limit_pct: float = 15.0,
    exchange_min_order_pct: float = 0.0  # Min order as % of capital (e.g., $5 on $100 = 5%)
) -> dict:
    """
    Computes the safe fraction of capital to risk on the next trade.

    Args:
        win_rate: Historical win rate [0, 1]
        avg_win: Average winning trade PnL percent
        avg_loss: Average losing trade PnL percent (positive)
        n_trades: Number of trades in history
        calibration_cap: Kelly cap from calibration (lower = more conservative)
        current_drawdown_pct: Current drawdown percent
        drawdown_limit_pct: Max drawdown before trading halts
        exchange_min_order_pct: Minimum order as pct of capital (if size falls below
                                this, signal = 'below_exchange_min')

    Returns:
        dict with keys: kelly_raw, half_kelly, drawdown_penalty,
                        calibration_cap, safe_fraction, signal
    """
    kelly_raw = compute_kelly_fraction(win_rate, avg_win, avg_loss)

    # If insufficient data, use conservative default
    if n_trades < MIN_TRADES_FOR_KELLY:
        # Cold-start: risk 5% of capital per trade maximum.
        # If 5% is below exchange minimum order, signal so caller can skip
        # rather than over-risk capital.
        if exchange_min_order_pct > 0.05:
            return {
                "kelly_raw": 0.0,
                "half_kelly": 0.025,
                "drawdown_penalty": 1.0,
                "calibration_cap": calibration_cap,
                "safe_fraction": 0.05,
                "signal": "below_exchange_min",
                "cold_start": True
            }
        safe_fraction = 0.05
        return {
            "kelly_raw": 0.0,
            "half_kelly": safe_fraction / 2.0,
            "drawdown_penalty": 1.0,
            "calibration_cap": calibration_cap,
            "safe_fraction": safe_fraction,
            "signal": "cold_start_default"
        }

    # Apply half-kelly for safety
    half_kelly = kelly_raw * HALF_KELLY

    # Compute net edge per trade (expectancy)
    q = 1.0 - win_rate
    expectancy = (win_rate * avg_win) - (q * avg_loss)
    if expectancy < MIN_EDGE_FOR_RISK:
        return {
            "kelly_raw": round(kelly_raw, 4),
            "half_kelly": round(half_kelly, 4),
            "drawdown_penalty": 1.0,
            "calibration_cap": calibration_cap,
            "safe_fraction": 0.0,
            "signal": "no_edge"
        }

    # Apply calibration cap (from Brier score)
    effective_kelly = min(half_kelly, calibration_cap)

    # Apply drawdown penalty: scale down linearly as drawdown approaches limit
    drawdown_penalty = 1.0
    if current_drawdown_pct > 0 and drawdown_limit_pct > 1e-6:
        dd_ratio = current_drawdown_pct / drawdown_limit_pct
        if dd_ratio >= 1.0:
            drawdown_penalty = 0.0  # Halt trading
        elif dd_ratio > 0.5:
            drawdown_penalty = 2.0 * (1.0 - dd_ratio)  # Linear taper from 0.5 to 1.0
    elif drawdown_limit_pct <= 1e-6:
        drawdown_penalty = 0.0  # Limit is zero: halt immediately

    safe_fraction = effective_kelly * drawdown_penalty

    # Hard cap (upper bound)
    safe_fraction = min(safe_fraction, ABSOLUTE_MAX_FRACTION)
    # Minimum floor: only apply when outside drawdown taper zone
    if drawdown_penalty >= 1.0 and current_drawdown_pct <= 0.0:
        min_safe_fraction = max(0.02, exchange_min_order_pct)  # At least 2% or exchange min
        safe_fraction = max(safe_fraction, min_safe_fraction)
    elif exchange_min_order_pct > 0 and safe_fraction > 0 and safe_fraction < exchange_min_order_pct:
        # Below exchange minimum — signal as minimal but keep the fraction
        signal = "below_exchange_min"

    # Determine signal (if not already set)
    if safe_fraction <= 0:
        signal = "halted_drawdown"
    elif safe_fraction < 0.01:
        signal = "minimal"
    elif safe_fraction < 0.05:
        signal = "conservative"
    elif safe_fraction < 0.10:
        signal = "moderate"
    else:
        signal = "aggressive"

    return {
        "kelly_raw": round(kelly_raw, 4),
        "half_kelly": round(half_kelly, 4),
        "drawdown_penalty": round(drawdown_penalty, 4),
        "calibration_cap": round(calibration_cap, 4),
        "safe_fraction": round(safe_fraction, 4),
        "signal": signal
    }


def volatility_adjusted_qty(
    capital: float,
    risk_fraction: float,
    price: float,
    atr: float,
    max_qty: Optional[float] = None,
    atr_multiplier: float = 1.0
) -> float:
    """
    Computes position quantity adjusted for volatility (ATR).

    Converts a risk budget (capital * risk_fraction) into a position size
    such that a move of atr_multiplier * ATR represents the full risk amount.

    Formula: qty = risk_amount / (ATR * atr_multiplier)

    Sanity checks:
    - ATR-based stop distance can't exceed 50% of price (avoids impossible
      position sizes from extremely wide stops).
    - Near-zero ATR (< 0.001% of price): fall back to flat capital fraction.
    - Position notional capped at 3x capital (3x leverage max).
    - Position notional also capped at `capital / (1 - atr_ratio * atr_multiplier)`
      to avoid total-loss-on-gap scenarios.

    Args:
        capital: Available capital
        risk_fraction: Fraction of capital to risk (e.g. 0.02 = 2%)
        price: Current asset price
        atr: Average True Range (volatility measure)
        max_qty: Optional maximum position size
        atr_multiplier: How many ATRs to use for position sizing

    Returns:
        Number of units to trade (float)
    """
    if price <= 0 or risk_fraction <= 0:
        return 0.0

    risk_amount = capital * risk_fraction
    risk_amount = min(risk_amount, capital * 0.5)  # Never risk > 50% of capital

    if atr > 0:
        atr_ratio = atr / price
        if 0.00001 <= atr_ratio <= 0.5:
            # Volatility-based sizing: stop = atr_multiplier * ATR in price units
            # qty = risk_amount / (atr * atr_multiplier)
            denominator = atr * atr_multiplier
            qty = risk_amount / denominator if denominator > 0 else 0.0

            # Also cap notional so that a gap of stop_distance won't exceed capital
            # stop_fraction = atr_ratio * atr_multiplier (as fraction of price)
            stop_fraction = atr_ratio * atr_multiplier
            if stop_fraction > 0 and stop_fraction < 1.0:
                max_notional_by_stop = capital / stop_fraction
                qty = min(qty, max_notional_by_stop / price)
        elif atr_ratio > 0.5:
            # Extremely wide ATR (ATR > 50% of price): extremely volatile
            # Use conservative flat fraction instead
            qty = (capital * min(risk_fraction, 0.05)) / price
        else:
            # Near-zero ATR (stablecoin): just use flat capital fraction
            qty = risk_amount / price
    else:
        qty = risk_amount / price

    # Hard cap: notional should not exceed 3x capital
    qty = min(qty, (capital * 3.0) / price)

    if max_qty is not None:
        qty = min(qty, max_qty)

    return round(qty, 4)
