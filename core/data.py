import math
import random
from typing import Dict

from .types import MarketSnapshot, JLPPool

# 本模块提供数据源与状态生成的简化实现:
# - GBMSimulator: 价格使用几何布朗运动(GBM)近似生成
# - LiquidityModel: 订单簿流动性折减的简化模型
# - JLPStateGenerator: 模拟 JLP 池内的持仓与费用演化(此处主要快照)


class GBMSimulator:
    def __init__(self, seed: int, initial_prices: Dict[str, float], mu: Dict[str, float], sigma: Dict[str, float]):
        self.rnd = random.Random(seed)  # 固定随机种子以获得可重复性
        self.prices = dict(initial_prices)
        self.mu = mu  # 日收益率期望(漂移)
        self.sigma = sigma  # 日波动率

    def step(self) -> Dict[str, float]:
        out = {}
        for a, p in self.prices.items():
            m = self.mu.get(a, 0.0)
            s = self.sigma.get(a, 0.0)
            z = self._gauss()
            # GBM 离散化: S_{t+1} = S_t * exp((μ - 0.5σ^2) + σ·Z)
            dp = p * math.exp((m - 0.5 * s * s) + s * z)
            out[a] = dp
        self.prices = out
        return out

    def _gauss(self) -> float:
        return self.rnd.gauss(0.0, 1.0)  # 标准正态


class LiquidityModel:
    def __init__(self, base: Dict[str, float], flat_haircut: float, crunch_haircut: float):
        self.base = base  # 基础可成交名义
        self.flat = flat_haircut  # 平坦折减比例
        self.crunch = crunch_haircut  # 紧缩折减比例(周期性模拟压力)
        self.counter = 0

    def snapshot(self) -> Dict[str, float]:
        self.counter += 1
        stress = 1.0
        # 每 300 步模拟一次流动性紧缩
        if self.counter % 300 == 0:
            stress = 1.0 - self.crunch
        adj = 1.0 - self.flat
        return {a: self.base[a] * adj * stress for a in self.base}


class JLPStateGenerator:
    def __init__(self, jlp_supply: float, undistributed_fees_usd: float, spot: Dict[str, float], long_perp: Dict[str, float], short_perp: Dict[str, float]):
        self.jlp_supply = jlp_supply
        self.fees = undistributed_fees_usd
        self.spot = dict(spot)
        self.long_perp = dict(long_perp)
        self.short_perp = dict(short_perp)

    def update_spot(self, spot_changes: Dict[str, float]):
        # 调整现货持仓(示例用; 回测中主要读取快照)
        for a, v in spot_changes.items():
            self.spot[a] = self.spot.get(a, 0.0) + v

    def accrue_fees(self, usd_amount: float):
        # 计入尚未分配的费用(美元)
        self.fees += usd_amount

    def snapshot(self) -> JLPPool:
        # 生成不可变的池状态快照
        return JLPPool(
            spot=dict(self.spot),
            long_perp=dict(self.long_perp),
            short_perp=dict(self.short_perp),
            undistributed_fees=self.fees,
            jlp_supply=self.jlp_supply,
        )


def build_market_snapshot(ts: int, prices: Dict[str, float], liquidity: Dict[str, float]) -> MarketSnapshot:
    # 构造市场快照的助手函数
    return MarketSnapshot(timestamp=ts, prices=prices, liquidity=liquidity)
