"""
probability_calibration.py — Calibration metrics for the ProbabilityEngine.

Tracks whether predicted win probabilities match actual outcomes.
Poor calibration → Kelly fraction is capped aggressively.

Usage:
    from probability_calibration import brier_score, calibration_bins, kelly_cap_from_calibration

    score = brier_score(predictions, outcomes)
    cap = kelly_cap_from_calibration(score)
"""

import math
import logging
from typing import List

POOR_CALIBRATION_THRESHOLD = 0.25
POOR_CALIBRATION_KELLY_CAP = 0.02  # 2% max position when calibration is poor
MINIMUM_CALIBRATION_SAMPLES = 30   # Minimum trades needed before trusting calibration


def brier_score(predictions: List[float], outcomes: List[int]) -> float:
    """
    Calculates the Brier score for probability predictions.

    Args:
        predictions: List of predicted win probabilities [0.0, 1.0]
        outcomes: List of actual outcomes (1 = win, 0 = loss)

    Returns:
        Brier score in [0.0, 1.0]. Lower is better. 0.25 = random.
        Returns 0.25 (random baseline) if insufficient data.
    """
    if not predictions or not outcomes or len(predictions) != len(outcomes):
        return 0.25  # Return random baseline — not enough data

    if len(predictions) < MINIMUM_CALIBRATION_SAMPLES:
        logging.debug(
            f"[CALIBRATION] Only {len(predictions)} samples; need {MINIMUM_CALIBRATION_SAMPLES}. "
            f"Returning random baseline score."
        )
        return 0.25

    # Filter out any NaN/None pairs that would corrupt the score
    clean_pairs = [(p, o) for p, o in zip(predictions, outcomes)
                   if p is not None and o is not None
                   and not (isinstance(p, float) and p != p)  # NaN check
                   and not (isinstance(o, float) and o != o)]  # NaN check
    if len(clean_pairs) < MINIMUM_CALIBRATION_SAMPLES:
        logging.debug(
            f"[CALIBRATION] Only {len(clean_pairs)} clean samples after NaN filtering; "
            f"need {MINIMUM_CALIBRATION_SAMPLES}. Returning random baseline."
        )
        return 0.25

    score = sum((p - o) ** 2 for p, o in clean_pairs) / len(clean_pairs)
    return round(score, 6)


def calibration_bins(predictions: List[float], outcomes: List[int], bins: int = 10) -> List[dict]:
    """
    Groups predictions into bins and computes mean predicted vs actual win rate per bin.

    Returns:
        List of dicts: [{bin_low, bin_high, predicted_mean, actual_mean, count}]
    """
    if not predictions or not outcomes or len(predictions) != len(outcomes):
        return []

    # Clamp predictions to [0, 1] to avoid dropping out-of-range values
    clamped_preds = [max(0.0, min(1.0, p)) for p in predictions]

    bin_size = 1.0 / bins
    result = []

    for i in range(bins):
        low = i * bin_size
        high = low + bin_size
        # Last bin is inclusive of upper bound (handles predictions exactly 1.0)
        if i == bins - 1:
            in_bin = [(p, o) for p, o in zip(clamped_preds, outcomes) if low <= p <= high]
        else:
            in_bin = [(p, o) for p, o in zip(clamped_preds, outcomes) if low <= p < high]
        if not in_bin:
            continue
        preds_in_bin = [x[0] for x in in_bin]
        outs_in_bin = [x[1] for x in in_bin]
        result.append({
            "bin_low": round(low, 2),
            "bin_high": round(high, 2),
            "predicted_mean": round(sum(preds_in_bin) / len(preds_in_bin), 4),
            "actual_mean": round(sum(outs_in_bin) / len(outs_in_bin), 4),
            "count": len(in_bin),
        })

    return result


def kelly_cap_from_calibration(brier: float, n_samples: int = 0) -> float:
    """
    Returns the Kelly cap to apply based on calibration quality.

    Args:
        brier: Current Brier score (0.0 = perfect, 0.25 = random)
        n_samples: Number of samples used to compute the score

    Returns:
        Max Kelly fraction allowed. Conservative default if data is sparse.
    """
    if n_samples < MINIMUM_CALIBRATION_SAMPLES:
        return 0.05

    # Guard against None, NaN, or out-of-range Brier scores
    if brier is None:
        logging.warning(f"[CALIBRATION] Brier score is None. Using random baseline cap.")
        return POOR_CALIBRATION_KELLY_CAP
    if isinstance(brier, float) and brier != brier:  # NaN check
        logging.warning(f"[CALIBRATION] Brier score is NaN. Using random baseline cap.")
        return POOR_CALIBRATION_KELLY_CAP
    if brier < 0.0:
        logging.warning(
            f"[CALIBRATION] Brier score {brier:.4f} is negative (impossible value). "
            f"Clamping to 0.0."
        )
        brier = 0.0
    if brier > 1.0:
        logging.warning(
            f"[CALIBRATION] Brier score {brier:.4f} exceeds maximum possible (1.0). "
            f"Clamping to 1.0."
        )
        brier = 1.0

    if brier >= POOR_CALIBRATION_THRESHOLD:
        logging.warning(
            f"[CALIBRATION] Brier score {brier:.4f} >= {POOR_CALIBRATION_THRESHOLD} threshold. "
            f"Capping Kelly to {POOR_CALIBRATION_KELLY_CAP:.0%}."
        )
        return POOR_CALIBRATION_KELLY_CAP

    # Linear interpolation: Brier=0 -> cap=0.15 (good calibration), Brier=threshold -> cap=0.02
    # Score better than random = better cap
    ratio = brier / POOR_CALIBRATION_THRESHOLD  # 0.0 (perfect) to 1.0 (random)
    max_kelly = 0.15  # Max Kelly fraction even with perfect calibration
    cap = max_kelly * (1.0 - ratio) + POOR_CALIBRATION_KELLY_CAP * ratio
    return round(float(cap), 4)


def load_calibration_from_trades(db_path: str = None) -> dict:
    """
    Loads predicted_win_probability and outcomes from the trades table.

    Returns:
        dict with keys: predictions, outcomes, brier_score, n_samples, kelly_cap
    """
    import sqlite3
    import os

    if db_path is None:
        home = os.path.expanduser("~")
        db_path = os.path.join(home, ".nexustrader", "nexustrader.db")

    predictions = []
    outcomes = []

    try:
        conn = sqlite3.connect(db_path, timeout=10)
        conn.row_factory = sqlite3.Row

        try:
            conn.execute("ALTER TABLE trades ADD COLUMN predicted_win_probability REAL")
            conn.commit()
        except Exception:
            pass  # Column already exists

        try:
            conn.execute("ALTER TABLE trades ADD COLUMN expected_value REAL")
            conn.commit()
        except Exception:
            pass

        try:
            conn.execute("ALTER TABLE trades ADD COLUMN risk_reward_ratio REAL")
            conn.commit()
        except Exception:
            pass

        try:
            conn.execute("ALTER TABLE trades ADD COLUMN kelly_fraction REAL")
            conn.commit()
        except Exception:
            pass

        cursor = conn.execute(
            "SELECT predicted_win_probability, pnl FROM trades "
            "WHERE predicted_win_probability IS NOT NULL"
        )
        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            p = row["predicted_win_probability"]
            pnl = row["pnl"]
            if p is not None and pnl is not None:
                predictions.append(float(p))
                outcomes.append(1 if float(pnl) > 0 else 0)

    except Exception as e:
        logging.warning(f"[CALIBRATION] Could not load trade calibration data: {e}")

    n = len(predictions)
    score = brier_score(predictions, outcomes)
    cap = kelly_cap_from_calibration(score, n_samples=n)

    return {
        "predictions": predictions,
        "outcomes": outcomes,
        "brier_score": score,
        "n_samples": n,
        "kelly_cap": cap,
    }
