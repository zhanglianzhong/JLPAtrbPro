from typing import Dict, List

from core.types import ExecutionResult, Order


# 实盘适配器接口:定义策略与外部交易系统交互的抽象方法。
# 不同实现(Dummy、Drift 等)应遵循该接口,保证可替换性。
class ExchangeAdapter:
    async def get_prices(self) -> Dict[str, float]:
        # 返回最新价格(字典:资产 -> 价格)
        raise NotImplementedError

    async def get_liquidity(self) -> Dict[str, float]:
        # 返回当前可用流动性(字典:资产 -> 可成交名义)
        raise NotImplementedError

    async def place_orders(self, orders: List[Order]) -> Dict[str, ExecutionResult]:
        # 执行订单并返回执行结果(聚合)
        raise NotImplementedError

    async def get_positions(self) -> Dict[str, float]:
        # 查询当前持仓(用于监控与对账)
        raise NotImplementedError
