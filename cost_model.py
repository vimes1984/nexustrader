from dataclasses import dataclass

@dataclass
class CostModel:
    maker_fee: float = 0.001      # 0.1%
    taker_fee: float = 0.002      # 0.2%
    slippage_bps: float = 10.0   # 10 bps
    spread_bps: float = 5.0      # 5 bps

def apply_entry_cost(price: float, side: str, cost_model: CostModel) -> float:
    """Returns the effective entry price after fees and slippage."""
    fee = cost_model.taker_fee
    slip = cost_model.slippage_bps / 10_000.0
    spread = (cost_model.spread_bps / 2) / 10_000.0
    if side.upper() == "BUY":
        return price * (1 + fee + slip + spread)
    else:  # SELL
        return price * (1 - fee - slip - spread)

def apply_exit_cost(price: float, side: str, cost_model: CostModel) -> float:
    """Returns the effective exit price after fees and slippage. side = original entry side."""
    fee = cost_model.taker_fee
    slip = cost_model.slippage_bps / 10_000.0
    spread = (cost_model.spread_bps / 2) / 10_000.0
    if side.upper() == "BUY":
        return price * (1 - fee - slip - spread)
    else:
        return price * (1 + fee + slip + spread)

def estimate_round_trip_cost(position_value: float, cost_model: CostModel) -> float:
    """Estimates total cost for a full round-trip trade.
    
    Entry: pays taker fee + slippage + half-spread
    Exit: pays taker fee + slippage + half-spread
    Total: 2*taker_fee + 2*slippage + spread
    """
    slip_bps = cost_model.slippage_bps / 10_000.0
    spread_bps = cost_model.spread_bps / 10_000.0
    fee_cost = position_value * cost_model.taker_fee * 2  # entry + exit
    slip_cost = position_value * slip_bps * 2
    spread_cost = position_value * spread_bps
    return fee_cost + slip_cost + spread_cost
