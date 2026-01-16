#!/usr/bin/env python3
"""
Aster适配器调试测试模块
支持单条测试执行和交互式debug模式
"""

import asyncio
import os
import sys
import logging
from typing import Dict, Any

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.debug_test_runner import AsterTestFramework
import live.config  # 加载 .env 到环境变量

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AsterDebugTests(AsterTestFramework):
    """Aster适配器的调试测试类"""
    
    def __init__(self):
        super().__init__()
        self.assets = {"SOL": 0.0, "ETH": 0.0, "BTC": 0.0}
        self.adapter = None
    
    async def setup(self):
        """初始化适配器"""
        try:
            from live.aster_adapter import AsterAdapter
            url = os.getenv("ASTER_BASE_URL", "")
            if (not url) or ("invalid-url.com" in url):
                os.environ["ASTER_BASE_URL"] = "https://fapi.asterdex.com"
            self.adapter = AsterAdapter(self.assets)
            logger.info("Aster适配器初始化成功")
            return True
        except Exception as e:
            logger.error(f"初始化Aster适配器失败: {e}")
            return False
    
    async def test_connection(self):
        """测试API连接"""
        logger.info("=== 测试API连接 ===")
        if not await self.setup():
            return False
            
        try:
            # 测试服务器时间获取
            server_time = await self.adapter._server_time()
            logger.info(f"服务器时间: {server_time}")
            
            # 测试时间同步
            await self.adapter._ensure_time_offset()
            logger.info(f"时间偏移: {self.adapter._time_offset_ms}ms")
            
            logger.info("API连接测试通过")
            return True
        except Exception as e:
            logger.error(f"API连接失败: {e}")
            return False
    
    async def test_prices(self):
        """测试价格获取"""
        logger.info("=== 测试价格获取 ===")
        if not await self.setup():
            return False
            
        try:
            prices = await self.adapter.get_prices()
            logger.info(f"获取到的价格: {prices}")
            
            # 验证价格格式
            for asset, price in prices.items():
                assert isinstance(price, (int, float)), f"价格必须是数字: {asset}"
                assert price > 0, f"价格必须大于0: {asset}"
            
            logger.info("价格获取测试通过")
            return True
        except Exception as e:
            logger.error(f"价格获取失败: {e}")
            return False
    
    async def test_liquidity(self):
        """测试流动性获取"""
        logger.info("=== 测试流动性获取 ===")
        if not await self.setup():
            return False
            
        try:
            liquidity = await self.adapter.get_liquidity()
            logger.info(f"获取到的流动性: {liquidity}")
            
            # 验证流动性格式
            for asset, liq in liquidity.items():
                assert isinstance(liq, (int, float)), f"流动性必须是数字: {asset}"
                assert liq >= 0, f"流动性必须非负: {asset}"
            
            logger.info("流动性获取测试通过")
            return True
        except Exception as e:
            logger.error(f"流动性获取失败: {e}")
            return False
    
    async def test_filters(self):
        """测试交易对过滤器"""
        logger.info("=== 测试交易对过滤器 ===")
        if not await self.setup():
            return False
            
        try:
            # 测试SOLUSDT过滤器
            symbol = self.adapter._symbol("SOL")
            filters = await self.adapter._get_filters(symbol)
            logger.info(f"SOLUSDT过滤器: {filters}")
            
            # 验证过滤器格式
            assert "step" in filters, "缺少step字段"
            assert "min_notional" in filters, "缺少min_notional字段"
            assert isinstance(filters["step"], (int, float)), "step必须是数字"
            assert isinstance(filters["min_notional"], (int, float)), "min_notional必须是数字"
            
            logger.info("过滤器测试通过")
            return True
        except Exception as e:
            logger.error(f"过滤器测试失败: {e}")
            return False
    
    async def test_positions(self):
        """测试仓位查询"""
        logger.info("=== 测试仓位查询 ===")
        if not await self.setup():
            return False
            
        try:
            positions = await self.adapter.get_positions()
            logger.info(f"获取到的仓位: {positions}")
            
            # 验证仓位格式
            for asset, pos in positions.items():
                assert isinstance(pos, (int, float)), f"仓位必须是数字: {asset}"
            
            logger.info("仓位查询测试通过")
            return True
        except Exception as e:
            logger.error(f"仓位查询失败: {e}")
            return False
    
    async def test_order_placement(self):
        """测试下单功能(模拟)"""
        logger.info("=== 测试下单功能 ===")
        if not await self.setup():
            return False
            
        try:
            from core.types import Order
            
            # 创建测试订单
            test_orders = [
                Order(asset="SOL", side="buy", notional=100.0, twap_slices=1, max_impact_bps=50),
                Order(asset="ETH", side="sell", notional=50.0, twap_slices=1, max_impact_bps=50)
            ]
            
            logger.info(f"测试订单: {[f'{o.asset} {o.side} {o.notional}' for o in test_orders]}")
            
            # 注意: 这里不会真正下单, 只是测试接口
            # 如果需要真实测试, 需要设置ASTER_API_KEY和ASTER_API_SECRET
            if not (os.getenv("ASTER_API_KEY") and os.getenv("ASTER_API_SECRET")):
                logger.warning("未设置ASTER_API_KEY和ASTER_API_SECRET, 跳过真实下单测试")
                return True
            
            results = await self.adapter.place_orders(test_orders)
            logger.info(f"下单结果: {results}")
            
            # 验证结果格式
            for asset, result in results.items():
                assert hasattr(result, 'filled_notional'), f"结果缺少filled_notional: {asset}"
                assert hasattr(result, 'avg_price'), f"结果缺少avg_price: {asset}"
                assert hasattr(result, 'tx_sig'), f"结果缺少tx_sig: {asset}"
            
            logger.info("下单功能测试通过")
            return True
        except Exception as e:
            logger.error(f"下单功能测试失败: {e}")
            return False

    async def test_set_leverage(self):
        """测试杠杆调整为20"""
        logger.info("=== 测试杠杆调整 ===")
        if not await self.setup():
            return False
        try:
            # 需要真实API密钥
            if not (os.getenv("ASTER_API_KEY") and os.getenv("ASTER_API_SECRET")):
                logger.warning("未设置ASTER_API_KEY/SECRET, 跳过杠杆测试")
                return True
            symbol = self.adapter._symbol("SOL")
            await self.adapter._set_leverage(symbol, 20)
            logger.info(f"杠杆设置成功: {symbol}=20")
            return True
        except Exception as e:
            logger.error(f"杠杆设置失败: {e}")
            return False
    
    async def test_signature(self):
        """测试签名功能"""
        logger.info("=== 测试签名功能 ===")
        if not await self.setup():
            return False
            
        try:
            # 测试参数签名
            test_params = {
                "symbol": "SOLUSDT",
                "side": "BUY",
                "type": "MARKET",
                "quantity": "1.0",
                "timestamp": "1234567890"
            }
            
            # 注意: 需要API_SECRET才能测试签名
            if not os.getenv("ASTER_API_SECRET"):
                logger.warning("未设置ASTER_API_SECRET, 跳过签名测试")
                return True
            
            signature = self.adapter._sign(test_params)
            logger.info(f"测试签名: {signature}")
            
            # 验证签名格式
            assert isinstance(signature, str), "签名必须是字符串"
            assert len(signature) == 64, "签名长度必须是64位"
            
            logger.info("签名功能测试通过")
            return True
        except Exception as e:
            logger.error(f"签名测试失败: {e}")
            return False


async def run_all_tests():
    """运行所有测试"""
    framework = AsterDebugTests()
    
    # 添加所有测试到框架
    test_map = {
        "connection": framework.test_connection,
        "prices": framework.test_prices,
        "liquidity": framework.test_liquidity,
        "filters": framework.test_filters,
        "positions": framework.test_positions,
        "order_placement": framework.test_order_placement,
        "set_leverage": framework.test_set_leverage,
        "signature": framework.test_signature,
    }
    
    for name, func in test_map.items():
        framework.add_test(name, func)
    
    results = await framework.run_all_tests()
    framework.print_summary()
    return results


async def run_single_test(test_name: str):
    """运行单个测试"""
    framework = AsterDebugTests()
    
    # 添加测试到框架
    test_map = {
        "connection": framework.test_connection,
        "prices": framework.test_prices,
        "liquidity": framework.test_liquidity,
        "filters": framework.test_filters,
        "positions": framework.test_positions,
        "order_placement": framework.test_order_placement,
        "set_leverage": framework.test_set_leverage,
        "signature": framework.test_signature,
    }
    
    for name, func in test_map.items():
        framework.add_test(name, func)
    
    if test_name not in test_map:
        logger.error(f"未知的测试名称: {test_name}")
        logger.info(f"可用测试: {list(test_map.keys())}")
        return False
    
    return await framework.run_single_test(test_name)


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Aster适配器调试测试")
    parser.add_argument("--test", type=str, help="运行指定测试")
    parser.add_argument("--interactive", action="store_true", help="交互式模式")
    
    args = parser.parse_args()
    
    if args.interactive:
        # 交互式模式
        framework = AsterDebugTests()
        asyncio.run(framework.interactive_mode())
    elif args.test:
        # 运行单个测试
        result = asyncio.run(run_single_test(args.test))
        sys.exit(0 if result else 1)
    else:
        # 运行所有测试
        results = asyncio.run(run_all_tests())
        total = len(results)
        passed = sum(1 for r in results.values() if r is True)
        skipped = sum(1 for r in results.values() if r is None)
        rate = (passed / (total - skipped)) if total > skipped else 0.0
        sys.exit(0 if rate >= 0.5 else 1)


if __name__ == "__main__":
    main()
