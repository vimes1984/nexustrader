from dataclasses import dataclass
import re

# Kraken realistic spread bps by asset liquidity tier
# Source: Kraken order book data, typical for market orders
SPREAD_BPS_BY_PAIR = {
    # Tier 1: Ultra-liquid (1-3 bps spread)
    "BTC": 2.0,
    "ETH": 2.5,
    # Tier 2: High-liquidity (3-8 bps)
    "XRP": 5.0,
    "SOL": 5.0,
    "ADA": 6.0,
    "LINK": 6.0,
    "DOT": 7.0,
    "LTC": 5.0,
    "AVAX": 7.0,
    # Tier 3: Moderate liquidity (8-20 bps)
    "DOGE": 12.0,
    "MATIC": 10.0,
    "ATOM": 10.0,
    "UNI": 10.0,
    # Default for unknown pairs
    "DEFAULT": 10.0,
}


def get_spread_bps_for_symbol(symbol: str) -> float:
    """Return typical Kraken spread in bps for a given symbol (e.g. 'BTC-USD')."""
    base = re.split(r'[-/]', symbol)[0].upper() if symbol else ""
    return SPREAD_BPS_BY_PAIR.get(base, SPREAD_BPS_BY_PAIR["DEFAULT"])


@dataclass
class CostModel:
    maker_fee: float = 0.0016      # 0.16% (Kraken <$50K 30d volume, maker)
    taker_fee: float = 0.0026      # 0.26% (Kraken <$50K 30d volume, taker)
    slippage_bps: float = 10.0     # 10 bps estimated market impact
    spread_bps: float = 5.0        # 5 bps default (overridden by get_spread_bps_for_symbol)


def apply_entry_cost(price: float, side: str, cost_model: CostModel,
                    symbol: str = "") -> float:
    """Returns the effective entry price after fees and slippage.

    Args:
        symbol: Optional pair symbol (e.g. 'BTC-USD') for pair-specific spread.
    """
    fee = cost_model.taker_fee
    slip = cost_model.slippage_bps / 10_000.0
    spread_bps = get_spread_bps_for_symbol(symbol)
    spread = (spread_bps / 2) / 10_000.0
    if side.upper() == "BUY":
        return price * (1 + fee + slip + spread)
    else:  # SELL
        return price * (1 - fee - slip - spread)


def apply_exit_cost(price: float, side: str, cost_model: CostModel,
                    symbol: str = "") -> float:
    """Returns the effective exit price after fees and slippage.

    side = original entry side.
    symbol: Optional pair symbol for pair-specific spread.
    """
    fee = cost_model.taker_fee
    slip = cost_model.slippage_bps / 10_000.0
    spread_bps = get_spread_bps_for_symbol(symbol)
    spread = (spread_bps / 2) / 10_000.0
    if side.upper() == "BUY":
        return price * (1 - fee - slip - spread)
    else:
        return price * (1 + fee + slip + spread)


def estimate_round_trip_cost(position_value: float, cost_model: CostModel,
                             symbol: str = "") -> float:
    """Estimates total cost for a full round-trip trade on Kraken.

    Entry: pays taker fee + slippage + half-spread
    Exit: pays taker fee + slippage + half-spread
    Total: 2*taker_fee + 2*slippage + spread

    Spread varies by pair (see SPREAD_BPS_BY_PAIR):
    - BTC pairs: ~2 bps
    - ETH pairs: ~2.5 bps
    - DOGE pairs: ~12 bps
    """
    slip_bps = cost_model.slippage_bps / 10_000.0
    spread_bps = get_spread_bps_for_symbol(symbol) / 10_000.0
    fee_cost = position_value * cost_model.taker_fee * 2  # entry + exit
    slip_cost = position_value * slip_bps * 2
    spread_cost = position_value * spread_bps
    return fee_cost + slip_cost + spread_cost
