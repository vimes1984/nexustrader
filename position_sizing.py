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
    # Avoid division by zero
    avg_loss = abs(avg_loss) if avg_loss != 0 else 0.01

    return {
        "win_rate": win_rate,
        "avg_win": avg_win,
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
    if win_rate <= 0 or win_rate >= 1 or avg_loss <= 0:
        return 0.0
    if avg_win <= 0:
        return 0.0  # No winning trades means no edge

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
    return max(0.0, min(kelly, 1.0))


def compute_safe_fraction(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    n_trades: int,
    calibration_cap: float = 0.15,
    current_drawdown_pct: float = 0.0,
    drawdown_limit_pct: float = 15.0
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

    Returns:
        dict with keys: kelly_raw, half_kelly, drawdown_penalty,
                        calibration_cap, safe_fraction, signal
    """
    kelly_raw = compute_kelly_fraction(win_rate, avg_win, avg_loss)

    # If insufficient data, use conservative default
    if n_trades < MIN_TRADES_FOR_KELLY:
        return {
            "kelly_raw": 0.0,
            "half_kelly": 0.02,
            "drawdown_penalty": 1.0,
            "calibration_cap": calibration_cap,
            "safe_fraction": 0.05,  # 5% default when cold-starting
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
    if current_drawdown_pct > 0 and drawdown_limit_pct > 0:
        dd_ratio = current_drawdown_pct / drawdown_limit_pct
        if dd_ratio >= 1.0:
            drawdown_penalty = 0.0  # Halt trading
        elif dd_ratio > 0.5:
            drawdown_penalty = 2.0 * (1.0 - dd_ratio)  # Linear taper

    safe_fraction = effective_kelly * drawdown_penalty

    # Hard cap (upper bound)
    safe_fraction = min(safe_fraction, ABSOLUTE_MAX_FRACTION)
    # Minimum floor: only apply when outside drawdown taper zone
    # When drawdown_penalty < 1.0, the system is actively reducing risk —
    # don't override that reduction with an artificial floor.
    if drawdown_penalty >= 1.0 and current_drawdown_pct <= 0.0:
        min_safe_fraction = 0.02  # 2% minimum when no drawdown
        safe_fraction = max(safe_fraction, min_safe_fraction)

    # Determine signal
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

    ATR/price ratio sanity checks:
    - If ATR is near-zero (< 0.001% of price), use price-based fallback
      to avoid unrealistically large positions.
    - Position is capped at capital * 3 / price (3x leverage-like max).

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

    # Cap risk_amount to prevent degenerate positions
    risk_amount = min(risk_amount, capital * 0.5)  # Never risk > 50% of capital

    if atr > 0 and price > 0:
        atr_ratio = atr / price
        if atr_ratio >= 0.00001:
            # Sufficient ATR/price ratio: use volatility-based sizing
            denominator = atr * atr_multiplier
            qty = risk_amount / denominator if denominator > 0 else 0.0
        else:
            # Near-zero ATR (e.g., stablecoin): use flat capital fraction
            qty = risk_amount / price
    else:
        # No ATR data: use flat capital fraction
        qty = risk_amount / price

    # Hard cap to prevent excessive leverage: max 3x notional vs capital
    max_notional = capital * 3.0
    max_leverage_qty = max_notional / price if price > 0 else float('inf')
    qty = min(qty, max_leverage_qty)

    if max_qty is not None:
        qty = min(qty, max_qty)

    return round(qty, 4)
