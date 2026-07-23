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
    Computes the Kelly fraction: f* = p - (1-p) / (W/L)
    where p = win_rate, W = avg_win, L = avg_loss.

    Returns 0 if win_rate or avg_loss is invalid.
    """
    if win_rate <= 0 or win_rate >= 1 or avg_loss <= 0:
        return 0.0
    if avg_win <= 0:
        return 0.0  # No winning trades means no edge

    win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 1.0
    kelly = win_rate - (1.0 - win_rate) / win_loss_ratio
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

    The idea: risk a fixed fraction of capital, but convert that to
    position size based on ATR as a fraction of price.

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
    if price <= 0 or atr <= 0 or risk_fraction <= 0:
        return 0.0

    risk_amount = capital * risk_fraction

    # Scale position so that an ATR * atr_multiplier move represents the risk amount
    # qty = risk_amount / (atr * atr_multiplier)
    denominator = atr * atr_multiplier
    qty = risk_amount / denominator if denominator > 0 else 0.0

    # Alternative: flat qty based on risk fraction / price (if ATR not helpful)
    if qty <= 0:
        qty = (capital * risk_fraction) / price

    if max_qty is not None:
        qty = min(qty, max_qty)

    return round(qty, 4)
