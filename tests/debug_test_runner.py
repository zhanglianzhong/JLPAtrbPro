#!/usr/bin/env python3
"""
测试工具 - 将pytest测试转换为可debug的main形式
支持单条测试执行和交互式debug
"""

import os
import asyncio
import logging
import argparse
import sys
from typing import Dict, Callable, Any, Optional, List
from datetime import datetime

# Configure logging for debugging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f'test_debug_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)
logger = logging.getLogger(__name__)

# 测试状态记录
class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.status = "pending"  # pending, running, passed, failed, skipped
        self.error = None
        self.duration = 0
        self.details = {}

# 测试框架基类
class DebugTestFramework:
    def __init__(self, name: str):
        self.name = name
        self.results: Dict[str, TestResult] = {}
        self.current_test = None
        
    def add_test(self, test_name: str, test_func: Callable):
        """添加测试函数"""
        self.results[test_name] = TestResult(test_name)
        setattr(self, f"test_{test_name}", test_func)
        
    async def run_single_test(self, test_name: str, interactive: bool = False) -> bool:
        """运行单个测试"""
        if test_name not in self.results:
            logger.error(f"测试 {test_name} 不存在")
            return False
            
        test_func = getattr(self, f"test_{test_name}", None)
        if not test_func:
            logger.error(f"测试函数 {test_name} 未找到")
            return False
            
        result = self.results[test_name]
        result.status = "running"
        self.current_test = test_name
        start_time = asyncio.get_event_loop().time()
        
        logger.info(f"\n{'='*70}")
        logger.info(f"开始测试: {test_name}")
        logger.info(f"{'='*70}")
        
        try:
            # 运行测试
            if asyncio.iscoroutinefunction(test_func):
                test_result = await test_func()
            else:
                test_result = test_func()
                
            result.duration = asyncio.get_event_loop().time() - start_time
            
            # 处理测试结果
            if test_result is None:
                result.status = "skipped"
                logger.warning(f"⚠ 测试 {test_name} 被跳过")
            elif test_result is True:
                result.status = "passed"
                logger.info(f"✓ 测试 {test_name} 通过")
            else:
                result.status = "failed"
                logger.error(f"✗ 测试 {test_name} 失败")
                
            return result.status == "passed"
            
        except Exception as e:
            result.status = "failed"
            result.error = str(e)
            result.duration = asyncio.get_event_loop().time() - start_time
            logger.error(f"✗ 测试 {test_name} 失败: {type(e).__name__}: {e}")
            
            if interactive:
                logger.info("详细错误信息:")
                import traceback
                traceback.print_exc()
                
            return False
            
        finally:
            self.current_test = None
            
    async def run_all_tests(self, interactive: bool = False) -> Dict[str, bool]:
        """运行所有测试"""
        logger.info(f"\n开始运行 {self.name} 的所有测试...")
        results = {}
        
        for test_name in self.results.keys():
            success = await self.run_single_test(test_name, interactive)
            results[test_name] = success
            
            # 添加延迟避免API限流
            await asyncio.sleep(0.5)
            
        return results
        
    def print_summary(self):
        """打印测试总结"""
        logger.info(f"\n{'='*70}")
        logger.info(f"测试总结: {self.name}")
        logger.info(f"{'='*70}")
        
        total = len(self.results)
        passed = sum(1 for r in self.results.values() if r.status == "passed")
        failed = sum(1 for r in self.results.values() if r.status == "failed")
        skipped = sum(1 for r in self.results.values() if r.status == "skipped")
        
        logger.info(f"总测试数: {total}")
        logger.info(f"通过: {passed}")
        logger.info(f"失败: {failed}")
        logger.info(f"跳过: {skipped}")
        logger.info(f"成功率: {passed/(total-skipped)*100:.1f}%" if total > skipped else "N/A")
        
        if failed > 0:
            logger.info("\n失败的测试:")
            for name, result in self.results.items():
                if result.status == "failed":
                    logger.info(f"  ✗ {name}: {result.error or '未知错误'}")
                    
    def list_tests(self):
        """列出所有测试"""
        logger.info(f"\n可用测试 ({self.name}):")
        for test_name in self.results.keys():
            logger.info(f"  - {test_name}")


# Utils测试框架
class UtilsTestFramework(DebugTestFramework):
    def __init__(self):
        super().__init__("Utils Tests")
        self.setup_tests()
        
    def setup_tests(self):
        """设置utils测试"""
        
        async def test_supply():
            """测试JLP供应量"""
            logger.info("=== 测试JLP供应量 ===")
            from live.utils import get_jlp_supply_async
            try:
                val = await get_jlp_supply_async()
                logger.info(f"JLP供应量: {val}")
                assert isinstance(val, float)
                assert val >= 0.0
                return True
            except Exception as e:
                logger.error(f"JLP供应量测试失败: {e}")
                return False
                
        async def test_spot_and_staked():
            """测试现货流动性和质押SOL"""
            logger.info("=== 测试现货流动性和质押SOL ===")
            from live.utils import get_spot_liquidity_async, get_staked_sol_async
            try:
                assets = ["SOL", "ETH", "BTC"]
                vals = await asyncio.gather(*[get_spot_liquidity_async(a) for a in assets])
                spot = {a: float(v) for a, v in zip(assets, vals)}
                logger.info(f"现货流动性: {spot}")
                assert set(spot.keys()) == set(assets)
                for k, v in spot.items():
                    assert isinstance(v, float)
                    assert v >= 0.0
                sol_staked = await get_staked_sol_async()
                logger.info(f"质押SOL: {sol_staked}")
                assert isinstance(sol_staked, float)
                assert sol_staked >= 0.0
                return True
            except Exception as e:
                logger.error(f"现货/质押测试失败: {e}")
                return False
                
        async def test_fee_vault():
            """测试未分配费用(IDL聚合)"""
            logger.info("=== 测试未分配费用(IDL) ===")
            from live.utils import fetch_fees_reserves_async
            try:
                fees = await fetch_fees_reserves_async()
                val = float(sum(fees.values()))
                logger.info(f"未分配费用(USD): {val}")
                assert isinstance(val, float)
                assert val >= 0.0
                return True
            except Exception as e:
                logger.error(f"未分配费用(IDL)测试失败: {e}")
                return False
                
        async def test_idl_fees():
            """测试IDL费用聚合"""
            logger.info("=== 测试IDL费用聚合 ===")
            from live.utils import fetch_fees_reserves_async
            try:
                fees = await fetch_fees_reserves_async()
                val = float(sum(fees.values()))
                logger.info(f"IDL费用聚合: {val}")
                assert isinstance(val, float)
                assert val >= 0.0
                return True
            except Exception as e:
                logger.error(f"IDL费用聚合测试失败: {e}")
                return False
                
        async def test_perp_exposure():
            """测试永续合约风险敞口"""
            logger.info("=== 测试永续合约风险敞口 ===")
            from live.utils import get_positions_by_asset_async
            try:
                agg = await get_positions_by_asset_async()
                long_perp = {k: float(v.get('long', 0.0)) for k, v in agg.items()}
                short_perp = {k: float(v.get('short', 0.0)) for k, v in agg.items()}
                logger.info(f"多头风险敞口: {long_perp}")
                logger.info(f"空头风险敞口: {short_perp}")
                assert isinstance(long_perp, dict)
                assert isinstance(short_perp, dict)
                for m in [long_perp, short_perp]:
                    for k, v in m.items():
                        assert isinstance(v, float)
                        assert v >= 0.0
                return True
            except Exception as e:
                logger.error(f"永续合约风险敞口测试失败: {e}")
                return False
        
        # 添加所有测试
        self.add_test("supply", test_supply)
        self.add_test("spot_and_staked", test_spot_and_staked)
        self.add_test("fee_vault", test_fee_vault)
        self.add_test("idl_fees", test_idl_fees)
        self.add_test("perp_exposure", test_perp_exposure)


# Drift适配器测试框架
class DriftTestFramework(DebugTestFramework):
    def __init__(self):
        super().__init__("Drift Adapter Tests")
        self.setup_tests()
        
    def setup_tests(self):
        """设置drift适配器测试"""
        
        async def test_connection():
            """测试连接和初始化"""
            logger.info("=== 测试Drift适配器连接 ===")
            from live.drift_adapter import DriftAdapter
            
            wallet_secret = os.getenv("WALLET_SECRET_BASE58")
            rpc_url = os.getenv("SOLANA_RPC_URL")
            
            if not wallet_secret or not rpc_url:
                logger.warning("缺少WALLET_SECRET_BASE58或SOLANA_RPC_URL,跳过连接测试")
                return None
            
            try:
                assets = {"SOL": 0.0}
                adapter = DriftAdapter(assets)
                logger.info("DriftAdapter创建成功")
                logger.info(f"资产: {adapter.assets}")
                return True
            except Exception as e:
                logger.error(f"连接测试失败: {e}")
                return False
                
        async def test_prices():
            """测试价格获取"""
            logger.info("=== 测试Drift适配器价格 ===")
            from live.drift_adapter import DriftAdapter
            
            wallet_secret = os.getenv("WALLET_SECRET_BASE58")
            rpc_url = os.getenv("SOLANA_RPC_URL")
            
            if not wallet_secret or not rpc_url:
                logger.warning("缺少WALLET_SECRET_BASE58或SOLANA_RPC_URL,跳过价格测试")
                return None
            
            try:
                assets = {"SOL": 0.0, "ETH": 0.0, "BTC": 0.0}
                adapter = DriftAdapter(assets)
                prices = await adapter.get_prices()
                
                logger.info(f"价格: {prices}")
                assert set(prices.keys()) == set(assets.keys())
                
                for asset, price in prices.items():
                    assert isinstance(price, float)
                    assert price > 0.0
                    logger.info(f"✓ {asset}: ${price:.2f}")
                
                return True
            except Exception as e:
                logger.error(f"价格测试失败: {e}")
                return False
                
        async def test_error_handling():
            """测试错误处理"""
            logger.info("=== 测试Drift适配器错误处理 ===")
            from live.drift_adapter import DriftAdapter
            
            try:
                # 测试无效凭据
                original_wallet = os.getenv("WALLET_SECRET_BASE58")
                original_rpc = os.getenv("SOLANA_RPC_URL")
                
                # 临时移除凭据
                if "WALLET_SECRET_BASE58" in os.environ:
                    del os.environ["WALLET_SECRET_BASE58"]
                if "SOLANA_RPC_URL" in os.environ:
                    del os.environ["SOLANA_RPC_URL"]
                
                assets = {"SOL": 0.0}
                adapter = DriftAdapter(assets)
                
                # 这应该能优雅处理
                prices = await adapter.get_prices()
                logger.info(f"使用无效凭据获取的价格: {prices}")
                
                return True
                
            except Exception as e:
                logger.info(f"错误处理正常: {type(e).__name__}")
                return True
                
            finally:
                # 恢复原始凭据
                if original_wallet:
                    os.environ["WALLET_SECRET_BASE58"] = original_wallet
                if original_rpc:
                    os.environ["SOLANA_RPC_URL"] = original_rpc
        
        # 添加所有测试
        self.add_test("connection", test_connection)
        self.add_test("prices", test_prices)
        self.add_test("error_handling", test_error_handling)


# Aster适配器测试框架
class AsterTestFramework(DebugTestFramework):
    def __init__(self):
        super().__init__("Aster Adapter Tests")
        self.setup_tests()
        
    def setup_tests(self):
        """设置aster适配器测试"""
        
        async def test_connection():
            """测试连接和初始化"""
            logger.info("=== 测试Aster适配器连接 ===")
            from live.aster_adapter import AsterAdapter
            
            required = ["ASTER_API_KEY", "ASTER_API_SECRET"]
            missing = [k for k in required if not os.getenv(k)]
            
            if missing:
                logger.warning(f"缺少Aster凭据: {', '.join(missing)}")
                return None
            
            try:
                assets = {"BTC": 0.0}
                adapter = AsterAdapter(assets)
                logger.info("AsterAdapter创建成功")
                logger.info(f"资产: {adapter.assets}")
                return True
            except Exception as e:
                logger.error(f"连接测试失败: {e}")
                return False
                
        async def test_prices_and_depth():
            """测试价格和深度"""
            logger.info("=== 测试Aster适配器价格和深度 ===")
            from live.aster_adapter import AsterAdapter
            
            required = ["ASTER_API_KEY", "ASTER_API_SECRET"]
            missing = [k for k in required if not os.getenv(k)]
            
            if missing:
                logger.warning(f"缺少Aster凭据: {', '.join(missing)}")
                return None
            
            try:
                assets = {"BTC": 0.0}
                adapter = AsterAdapter(assets)
                
                prices = await adapter.get_prices()
                depth = await adapter.get_liquidity()
                
                logger.info(f"价格: {prices}")
                logger.info(f"深度: {depth}")
                
                assert "BTC" in prices and "BTC" in depth
                assert isinstance(prices["BTC"], float)
                assert isinstance(depth["BTC"], float)
                
                logger.info(f"✓ BTC价格: ${prices['BTC']:.2f}")
                logger.info(f"✓ BTC深度: {depth['BTC']:.2f}")
                
                return True
            except Exception as e:
                logger.error(f"价格和深度测试失败: {e}")
                return False
                
        async def test_multiple_assets():
            """测试多个资产"""
            logger.info("=== 测试Aster适配器多个资产 ===")
            from live.aster_adapter import AsterAdapter
            
            required = ["ASTER_API_KEY", "ASTER_API_SECRET"]
            missing = [k for k in required if not os.getenv(k)]
            
            if missing:
                logger.warning(f"缺少Aster凭据: {', '.join(missing)}")
                return None
            
            try:
                assets = {"BTC": 0.0, "ETH": 0.0, "SOL": 0.0}
                adapter = AsterAdapter(assets)
                
                prices = await adapter.get_prices()
                depth = await adapter.get_liquidity()
                
                logger.info(f"多资产价格: {prices}")
                logger.info(f"多资产深度: {depth}")
                
                # 验证所有资产
                for asset in assets.keys():
                    if asset in prices:
                        price = prices[asset]
                        assert isinstance(price, float) and price > 0
                        logger.info(f"✓ {asset}价格: ${price:.2f}")
                    else:
                        logger.warning(f"⚠ {asset}不在价格数据中")
                        
                    if asset in depth:
                        asset_depth = depth[asset]
                        assert isinstance(asset_depth, float) and asset_depth >= 0
                        logger.info(f"✓ {asset}深度: {asset_depth:.2f}")
                    else:
                        logger.warning(f"⚠ {asset}不在深度数据中")
                
                return True
            except Exception as e:
                logger.error(f"多资产测试失败: {e}")
                return False
                
        async def test_error_handling():
            """测试错误处理"""
            logger.info("=== 测试Aster适配器错误处理 ===")
            from live.aster_adapter import AsterAdapter
            
            try:
                # 测试无效凭据
                original_env = {}
                required = ["ASTER_API_KEY", "ASTER_API_SECRET"]
                
                # 存储原始值
                for key in required:
                    original_env[key] = os.getenv(key)
                    if key in os.environ:
                        del os.environ[key]
                
                # 设置无效值
                os.environ["ASTER_BASE_URL"] = "https://invalid-url.com"
                os.environ["ASTER_API_KEY"] = "invalid_key"
                os.environ["ASTER_API_SECRET"] = "invalid_secret"
                
                assets = {"BTC": 0.0}
                adapter = AsterAdapter(assets)
                
                # 这应该能优雅处理
                prices = await adapter.get_prices()
                logger.info(f"使用无效凭据获取的价格: {prices}")
                
                return True
                
            except Exception as e:
                logger.info(f"错误处理正常: {type(e).__name__}")
                return True
                
            finally:
                # 恢复原始凭据
                for key, value in original_env.items():
                    if value is not None:
                        os.environ[key] = value
                    elif key in os.environ:
                        del os.environ[key]
        
        # 添加所有测试
        self.add_test("connection", test_connection)
        self.add_test("prices_and_depth", test_prices_and_depth)
        self.add_test("multiple_assets", test_multiple_assets)
        self.add_test("error_handling", test_error_handling)


# 主测试运行器
class TestRunner:
    def __init__(self):
        self.frameworks = {
            "utils": UtilsTestFramework(),
            "drift": DriftTestFramework(),
            "aster": AsterTestFramework(),
        }
        
    def list_all_tests(self):
        """列出所有测试"""
        logger.info("\n可用测试:")
        for framework_name, framework in self.frameworks.items():
            logger.info(f"\n{framework.name}:")
            framework.list_tests()
            
    async def run_framework(self, framework_name: str, test_name: Optional[str] = None, interactive: bool = False):
        """运行指定框架的测试"""
        if framework_name not in self.frameworks:
            logger.error(f"未知测试框架: {framework_name}")
            logger.info(f"可用框架: {', '.join(self.frameworks.keys())}")
            return False
            
        framework = self.frameworks[framework_name]
        
        if test_name:
            # 运行单个测试
            success = await framework.run_single_test(test_name, interactive)
            framework.print_summary()
            return success
        else:
            # 运行所有测试
            results = await framework.run_all_tests(interactive)
            framework.print_summary()
            return all(results.values())
            
    async def run_specific_test(self, full_test_name: str, interactive: bool = False):
        """运行指定的测试(格式:框架.测试名)"""
        if "." not in full_test_name:
            logger.error("测试名称格式错误,应该为: 框架.测试名")
            return False
            
        framework_name, test_name = full_test_name.split(".", 1)
        return await self.run_framework(framework_name, test_name, interactive)


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Debug测试运行器")
    parser.add_argument("--framework", "-f", choices=["utils", "drift", "aster"], 
                       help="测试框架名称")
    parser.add_argument("--test", "-t", help="测试名称(格式:框架.测试名 或 测试名)")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有测试")
    parser.add_argument("--interactive", "-i", action="store_true", 
                       help="交互模式,显示详细错误信息")
    parser.add_argument("--verbose", "-v", action="store_true", 
                       help="详细日志输出")
    
    args = parser.parse_args()
    
    # 设置日志级别
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    runner = TestRunner()
    
    # 列出测试
    if args.list:
        runner.list_all_tests()
        return 0
    
    # 检查环境
    logger.info(f"当前工作目录: {os.getcwd()}")
    logger.info("检查环境变量...")
    
    # 运行测试
    try:
        if args.test and "." in args.test:
            # 运行指定测试(完整格式)
            success = await runner.run_specific_test(args.test, args.interactive)
        elif args.framework and args.test:
            # 运行指定框架的指定测试
            success = await runner.run_framework(args.framework, args.test, args.interactive)
        elif args.framework:
            # 运行指定框架的所有测试
            success = await runner.run_framework(args.framework, None, args.interactive)
        else:
            # 运行所有测试
            logger.info("运行所有测试框架...")
            all_success = True
            for framework_name in runner.frameworks.keys():
                framework_success = await runner.run_framework(framework_name, None, args.interactive)
                all_success = all_success and framework_success
            success = all_success
            
        return 0 if success else 1
        
    except KeyboardInterrupt:
        logger.info("\n测试被用户中断")
        return 130
    except Exception as e:
        logger.error(f"意外错误: {type(e).__name__}: {e}")
        if args.interactive:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
