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
    slippage_bps: float = 10.0     # 10 bps estimated total market impact per side
    # spread_bps is per-asset via get_spread_bps_for_symbol()


def apply_entry_cost(price: float, side: str, cost_model: CostModel,
                    symbol: str = "", is_maker: bool = False) -> float:
    """Returns the effective entry price after fees and slippage.

    slippage_bps already includes the half-spread + market impact, so we do NOT
    add spread separately — that would double-count. The function uses:
    - fee (maker or taker)
    - slippage_bps (includes spread + market impact)

    Args:
        symbol: Optional pair symbol (e.g. 'BTC-USD') for pair-specific spread.
        is_maker: If True, use maker fee instead of taker (limit orders).
    """
    fee = cost_model.maker_fee if is_maker else cost_model.taker_fee
    slip = get_slippage_bps_for_symbol(cost_model, symbol, is_maker=is_maker) / 10_000.0
    if side.upper() == "BUY":
        return price * (1 + fee + slip)
    else:  # SELL
        return price * (1 - fee - slip)


def apply_exit_cost(price: float, side: str, cost_model: CostModel,
                    symbol: str = "", is_maker: bool = False) -> float:
    """Returns the effective exit price after fees and slippage.

    slippage_bps already includes the half-spread + market impact.

    side = original entry side.
    symbol: Optional pair symbol (e.g. 'BTC-USD') for pair-specific spread.
    is_maker: If True, use maker fee instead of taker (limit orders on exit).
    """
    fee = cost_model.maker_fee if is_maker else cost_model.taker_fee
    slip = get_slippage_bps_for_symbol(cost_model, symbol, is_maker=is_maker) / 10_000.0
    if side.upper() == "BUY":
        return price * (1 - fee - slip)
    else:
        return price * (1 + fee + slip)


def get_slippage_bps_for_symbol(cost_model: CostModel, symbol: str = "", is_maker: bool = False) -> float:
    """Returns total slippage estimate in bps for a symbol.

    Combines the baseline slippage_bps from the cost model with the
    asset-specific spread from SPREAD_BPS_BY_PAIR.

    For maker orders (limit), slippage is approximately the half-spread since
    the order provides liquidity rather than taking it. Market impact is minimal.
    """
    pair_spread = get_spread_bps_for_symbol(symbol)
    if is_maker:
        # Maker: only pay half-spread (liquidity provider), no market impact
        return pair_spread / 2.0
    # Taker: slippage = max(baseline impact, full spread)
    return max(cost_model.slippage_bps, pair_spread)


def get_volume_adjusted_slippage(position_value: float, cost_model: CostModel,
                                  symbol: str = "", daily_volume_usd: float = 0.0,
                                  is_maker: bool = False) -> float:
    """Returns slippage multiplier adjusted for order type and size vs daily volume.

    Market impact grows with order size relative to daily volume:
    - < 0.01% of daily vol: 1x baseline (no additional impact)
    - 0.01-0.1% of daily vol: 2x baseline (moderate impact)
    - 0.1-1% of daily vol: 5x baseline (significant impact)
    - > 1% of daily vol: 50x baseline (whale-sized, unlikely to fill cleanly)

    For maker orders: impact is always minimal (0.5x half-spread) since
    the order provides liquidity and waits for a match.

    Returns:
        Price multiplier (e.g., 0.005 = 0.5% price adjustment).
    """
    total_slip_bps = get_slippage_bps_for_symbol(cost_model, symbol, is_maker=is_maker)

    if is_maker:
        # Maker orders have no market impact (they are resting limit orders)
        return total_slip_bps / 10_000.0

    impact_mult = 1.0
    if daily_volume_usd > 0 and position_value > 0:
        vol_fraction = position_value / daily_volume_usd
        # Sub-linear scaling: impact grows with sqrt of volume fraction
        # 0.01% of daily vol → 1x, 0.1% → ~3x, 1% → ~10x, 10% → ~32x
        # Using min(10 * sqrt(vol_fraction * 10000), 50) gives smooth curve
        scaled_fraction = vol_fraction * 10000  # Convert to basis points of daily vol
        impact_mult = min(10.0 * (scaled_fraction ** 0.5), 50.0)
        impact_mult = max(1.0, impact_mult)  # Never go below 1x

    return total_slip_bps * impact_mult / 10_000.0


def estimate_round_trip_cost(position_value: float, cost_model: CostModel,
                             symbol: str = "", maker_entry: bool = False,
                             maker_exit: bool = False,
                             daily_volume_usd: float = 0.0) -> float:
    """Estimates total cost for a full round-trip trade on Kraken.

    Total cost = fee_entry + fee_exit + slippage_entry + slippage_exit
    where slippage (from get_volume_adjusted_slippage) varies by:
    - Asset liquidity (BTC: 2bps, DOGE: 12bps)
    - Order size relative to daily volume
    - Order type (maker vs taker)

    Optional maker routing:
    - maker_entry: use maker fee + maker slippage on entry (post-only limit order)
    - maker_exit: use maker fee + maker slippage on exit

    Returns:
        Total round-trip cost in the same unit as position_value.
    """
    slip_entry = get_volume_adjusted_slippage(position_value, cost_model, symbol, daily_volume_usd, is_maker=maker_entry)
    slip_exit = get_volume_adjusted_slippage(position_value, cost_model, symbol, daily_volume_usd, is_maker=maker_exit)
    fee_entry = cost_model.maker_fee if maker_entry else cost_model.taker_fee
    fee_exit = cost_model.maker_fee if maker_exit else cost_model.taker_fee
    fee_cost = position_value * (fee_entry + fee_exit)
    slip_cost = position_value * (slip_entry + slip_exit)
    return fee_cost + slip_cost
