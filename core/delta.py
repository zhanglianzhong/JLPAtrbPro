from typing import Dict

from .types import JLPPool

# Delta 计算:
# - asset_delta:单资产的方向性敏感度(每枚 JLP 的数量口径)
# - portfolio_delta:组合总敏感度(线性叠加)
# - normalized_delta:按权重加权后的敏感度(风险归一化/相关性调整;当前策略未使用)


def asset_delta(pool: JLPPool, asset: str) -> float:
    spot = pool.spot.get(asset, 0.0)
    lp = pool.long_perp.get(asset, 0.0)
    sp = pool.short_perp.get(asset, 0.0)
    fees_map = pool.undistributed_fees
    fees_tokens = fees_map.get(asset, 0.0) if isinstance(fees_map, dict) else 0.0
    supply = pool.jlp_supply if pool.jlp_supply > 0 else 1.0
    return (spot + fees_tokens - lp + sp) / supply


def portfolio_delta(pool: JLPPool, assets: Dict[str, float]) -> float:
    return sum(asset_delta(pool, a) for a in assets)


def normalized_delta(pool: JLPPool, weights: Dict[str, float]) -> float:
    return sum(weights.get(a, 0.0) * asset_delta(pool, a) for a in weights)

    
