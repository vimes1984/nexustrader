"""
Realistic cost modeling for trade decisions.

Models spread, exchange fees, and slippage to determine
whether a trade has enough edge to survive costs.
"""

from typing import Optional, Tuple


DEFAULT_MAKER_FEE = 0.001    # 0.1%
DEFAULT_TAKER_FEE = 0.0026   # 0.26% (Kraken taker)
DEFAULT_SPREAD = 0.0005      # 0.05% for liquid pairs
DEFAULT_SLIPPAGE = 0.001     # 0.1% estimated market impact


def round_trip_cost(
    notional: float,
    maker_fee: float = DEFAULT_MAKER_FEE,
    taker_fee: float = DEFAULT_TAKER_FEE,
    spread: float = DEFAULT_SPREAD,
    slippage: float = DEFAULT_SLIPPAGE,
    is_maker: bool = False,
) -> float:
    """Total cost in quote currency to open AND close a position.

    Breakdown (round trip):
      - Entry fee:   notional * fee_rate
      - Exit fee:    notional * fee_rate
      - Spread cost: notional * spread  (half paid on entry, half on exit)
      - Slippage:    notional * slippage * 2  (once on entry, once on exit)
    """
    fee_rate = maker_fee if is_maker else taker_fee
    entry_fee = notional * fee_rate
    exit_fee = notional * fee_rate  # assume same fee rate to close
    spread_cost = notional * spread
    slippage_cost = notional * slippage * 2  # slippage on entry AND exit
    return entry_fee + exit_fee + spread_cost + slippage_cost


def cost_as_fraction(
    notional: float,
    maker_fee: float = DEFAULT_MAKER_FEE,
    taker_fee: float = DEFAULT_TAKER_FEE,
    spread: float = DEFAULT_SPREAD,
    slippage: float = DEFAULT_SLIPPAGE,
    is_maker: bool = False,
) -> float:
    """Round-trip cost as a fraction of notional."""
    return round_trip_cost(notional, maker_fee, taker_fee, spread, slippage, is_maker) / notional


def would_trade_survive_costs(
    expected_return_pct: float,
    notional: float = 1.0,
    maker_fee: float = DEFAULT_MAKER_FEE,
    taker_fee: float = DEFAULT_TAKER_FEE,
    spread: float = DEFAULT_SPREAD,
    slippage: float = DEFAULT_SLIPPAGE,
    is_maker: bool = False,
    min_edge_multiple: float = 2.0,
) -> Tuple[bool, float]:
    """Check whether expected return is large enough to survive costs.

    Returns (should_trade, cost_fraction).
    """
    cost_frac = cost_as_fraction(notional, maker_fee, taker_fee, spread, slippage, is_maker)
    return (expected_return_pct >= cost_frac * min_edge_multiple), cost_frac


def adjust_for_liquidity(symbol: str) -> dict:
    """Return estimated cost parameters for a symbol based on liquidity tier.
    In production this would look up order book depth.
    """
    # Tier 1: major pairs (BTC, ETH, etc.)
    high_liquidity = {"spread": 0.0003, "slippage": 0.0005}
    # Tier 2: medium
    medium_liquidity = {"spread": 0.001, "slippage": 0.002}
    # Tier 3: low
    low_liquidity = {"spread": 0.003, "slippage": 0.005}

    major_prefixes = ("BTC", "ETH", "XRP", "SOL", "ADA", "DOT", "LINK", "AVAX", "MATIC")
    medium_prefixes = ("ATOM", "UNI", "AAVE", "SNX", "CRV", "ALGO", "FIL", "APT", "SUI")

    base = symbol.split("-")[0].upper() if "-" in symbol else symbol.upper()
    if base.startswith(major_prefixes):
        return high_liquidity
    if base.startswith(medium_prefixes):
        return medium_liquidity
    return low_liquidity
