from typing import Dict, List

from .types import Order, ExecutionResult

# 执行估算: 拆单、滑点与费用简化模型; 实际成交由适配器完成


def execute_orders(orders: List[Order], prices: Dict[str, float], liquidity: Dict[str, float], base_fee_bps: float) -> Dict[str, ExecutionResult]:
    results: Dict[str, ExecutionResult] = {}
    for o in orders:
        px = prices[o.asset]
        avail = liquidity.get(o.asset, 0.0)
        base_qty = o.quantity if o.quantity and o.quantity > 0 else (o.notional / max(1.0, px))
        slice_qty = base_qty / max(1, o.twap_slices)
        filled = 0.0
        cost = 0.0
        for _ in range(max(1, o.twap_slices)):
            notional_slice = min(slice_qty * px, avail)
            qty = notional_slice / max(1.0, px)
            impact = o.max_impact_bps / 10000.0
            fee = base_fee_bps / 10000.0
            slip_px = px * (1 + impact) if o.side == "buy" else px * (1 - impact)  # 价格冲击
            cost += (qty * slip_px) * fee
            filled += qty * slip_px
        avg_px = px if filled == 0 else slip_px  # 以最后一片滑点价近似均价
        results[o.asset] = ExecutionResult(
            filled_notional=filled,
            avg_price=avg_px,
            slippage_bps=o.max_impact_bps,
            cost=cost,
        )
    return results
