from typing import Dict, List

from .types import StrategyConfig, JLPPool, HedgeDecision, Order
from .delta import asset_delta


def decide_hedge(pool: JLPPool, prices: Dict[str, float], config: StrategyConfig, hedge_positions: Dict[str, float] | None = None) -> HedgeDecision:
    """
    根据当前 JLP 池状态与市场价格,基于资产级差异触发再平衡并生成对冲订单。
    当前逻辑:比较池内每枚 JLP 的资产 Delta 与自身已持仓对冲 Delta(hedged),
    当 |Δ_pool − Δ_hedged| 超过各资产边界时触发;对冲规模按 `config.jlp_units`
    将每枚 JLP 的 Delta 转为总名义,方向由需要的增量头寸决定。
    """
    target = {a: ((hedge_positions.get(a, 0.0) if hedge_positions else 0.0) / (config.jlp_units if config.jlp_units > 0 else 1.0)) for a in prices}
    orders: List[Order] = []

    # 用 jlp_units 将 delta 转换为名义规模;若配置为 0 或负,则退化为 1.0 避免乘 0
    scale = config.jlp_units if config.jlp_units > 0 else 1.0
    rebalance = False

    if config.delta_bounds_pct:
        for a in prices:
            d_cur = asset_delta(pool, a)
            # 已对冲 Delta(每枚 JLP 口径):账户该资产的对冲持仓数量除以 jlp_units;
            # 若 jlp_units<=0 则使用 1.0 以避免除 0,确保比较逻辑稳定
            hedged = (hedge_positions.get(a, 0.0) if hedge_positions else 0.0) / (scale if scale > 0 else 1.0)
            diff_target = hedged + d_cur
            bound = config.delta_bounds_pct.get(a, 0.0)
            # 百分比分母:使用 |Δ_pool| 归一化偏差;若 |Δ_pool|≈0 则退化为 1e-9 防止除零。
            # 当池 Delta 很小时,任意非零已对冲(hedged)都会产生很大的 pct_diff,促使回到贴近 0 的状态。
            denom = abs(d_cur) if abs(d_cur) > 1e-9 else 1e-9
            # 百分比差异:|hedged + Δ_pool| / |Δ_pool|,衡量账户已对冲与池暴露的相对偏离
            pct_diff = abs(diff_target) / denom
            hedge_tokens = (hedge_positions.get(a, 0.0) if hedge_positions else 0.0)
            # 目标头寸(基础量):按 -Δ_pool * jlp_units 取与池暴露相反的方向
            # 订单增量:目标 - 现有; >0 表示需要加多(买入), <0 表示需要加空(卖出)
            target_tokens = -d_cur * scale
            delta_tokens = target_tokens - hedge_tokens
            notional = abs(delta_tokens) * prices[a]
            if pct_diff > bound:
                rebalance = True

    # 若未触发任何边界,直接返回空订单
    if not rebalance:
        return HedgeDecision(orders=[], target_deltas=target)

    # 触发再平衡:根据池 Delta 与已对冲差值的增量生成订单
    for a in prices:
        d_cur = asset_delta(pool, a)
        hedge_tokens = (hedge_positions.get(a, 0.0) if hedge_positions else 0.0)
        target_tokens = -d_cur * scale
        delta_tokens = target_tokens - hedge_tokens
        if delta_tokens == 0.0:
            continue
        qty = abs(delta_tokens)
        notional = qty * prices[a]
        side = "buy" if delta_tokens > 0 else "sell"
        nslices = 1
        orders.append(
            Order(
                asset=a,
                notional=notional,
                quantity=qty,
                side=side,
                twap_slices=nslices,
                max_impact_bps=config.max_market_impact_bps,
            )
        )
        target[a] = (hedge_positions.get(a, 0.0) if hedge_positions else 0.0) / (scale if scale > 0 else 1.0)

    return HedgeDecision(orders=orders, target_deltas=target)
