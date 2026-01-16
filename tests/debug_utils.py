#!/usr/bin/env python3
"""
Utils测试模块 - 独立运行的debug测试
可以单独运行或作为模块导入
"""

import os
import sys
import asyncio
import logging
from datetime import datetime
from typing import Dict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 测试函数定义
async def test_supply():
    """测试JLP供应量"""
    logger.info("=== 测试JLP供应量 ===")
    try:
        from live.utils import get_jlp_supply_async
        val = await get_jlp_supply_async()
        logger.info(f"JLP供应量: {val}")
        assert isinstance(val, float), f"期望float类型,得到{type(val)}"
        assert val >= 0.0, f"期望非负值,得到{val}"
        logger.info("✓ JLP供应量测试通过")
        return True
    except Exception as e:
        logger.error(f"✗ JLP供应量测试失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_spot_and_staked():
    logger.info("=== 测试现货流动性和质押SOL ===")
    try:
        from live.utils import get_spot_liquidity_async, get_staked_sol_async
        sol_staked = await get_staked_sol_async()
        logger.info(f"质押SOL: {sol_staked}")
        assert isinstance(sol_staked, float)
        assets = ["SOL","ETH","BTC"]
        spot_vals = await asyncio.gather(*[get_spot_liquidity_async(a) for a in assets])
        spot = {a: float(v) for a, v in zip(assets, spot_vals)}
        logger.info(f"现货流动性: {spot}")
        assert set(spot.keys()) == set(assets)
        for k, v in spot.items():
            assert isinstance(v, float)
            assert v >= 0.0
        logger.info("✓ 现货流动性测试通过")
        logger.info("✓ 质押SOL测试通过")
        return True
    except Exception as e:
        logger.error(f"✗ 现货/质押测试失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_fee_vault():
    """测试未分配费用(IDL聚合)"""
    logger.info("=== 测试未分配费用(IDL) ===")
    try:
        from live.utils import fetch_fees_reserves_async
        fees = await fetch_fees_reserves_async()
        val = float(sum(fees.values()))
        logger.info(f"未分配费用(USD): {val}")
        assert isinstance(val, float)
        assert val >= 0.0
        logger.info("✓ 未分配费用(IDL)测试通过")
        return True
    except Exception as e:
        logger.error(f"✗ 未分配费用(IDL)测试失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_idl_fees():
    """测试IDL费用聚合"""
    logger.info("=== 测试IDL费用聚合 ===")
    try:
        from live.utils import fetch_fees_reserves_async
        fees = await fetch_fees_reserves_async()
        val = float(sum(fees.values()))
        logger.info(f"IDL费用聚合: {val}")
        assert isinstance(val, float)
        assert val >= 0.0
        logger.info("✓ IDL费用聚合测试通过")
        return True
    except Exception as e:
        logger.error(f"✗ IDL费用聚合测试失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_perp_exposure():
    """测试永续合约风险敞口"""
    logger.info("=== 测试永续合约风险敞口 ===")
    try:
        from live.utils import get_positions_by_asset_async
        agg = await get_positions_by_asset_async()
        long_perp = {k: float(v.get('long',0.0)) for k,v in agg.items()}
        short_perp = {k: float(v.get('short',0.0)) for k,v in agg.items()}
        logger.info(f"多头风险敞口: {long_perp}")
        logger.info(f"空头风险敞口: {short_perp}")
        
        assert isinstance(long_perp, dict)
        assert isinstance(short_perp, dict)
        
        for m in [long_perp, short_perp]:
            for k, v in m.items():
                assert isinstance(v, float)
                assert v >= 0.0
        
        logger.info("✓ 永续合约风险敞口测试通过")
        return True
    except Exception as e:
        logger.error(f"✗ 永续合约风险敞口测试失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

# 测试执行器
class UtilsTestRunner:
    def __init__(self):
        self.tests = {
            "supply": test_supply,
            "spot_and_staked": test_spot_and_staked,
            "fee_vault": test_fee_vault,
            "idl_fees": test_idl_fees,
            "perp_exposure": test_perp_exposure,
        }
        
    def list_tests(self):
        """列出所有测试"""
        logger.info("可用的utils测试:")
        for name in self.tests.keys():
            logger.info(f"  - {name}")
            
    async def run_test(self, test_name: str) -> bool:
        """运行单个测试"""
        if test_name not in self.tests:
            logger.error(f"未知测试: {test_name}")
            return False
            
        logger.info(f"\n{'='*60}")
        logger.info(f"运行测试: {test_name}")
        logger.info(f"{'='*60}")
        
        test_func = self.tests[test_name]
        try:
            result = await test_func()
            if result is True:
                logger.info(f"✓ 测试 {test_name} 通过")
                return True
            elif result is None:
                logger.warning(f"⚠ 测试 {test_name} 被跳过")
                return None
            else:
                logger.error(f"✗ 测试 {test_name} 失败")
                return False
        except Exception as e:
            logger.error(f"✗ 测试 {test_name} 异常失败: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return False
            
    async def run_all_tests(self) -> Dict[str, bool]:
        """运行所有测试"""
        logger.info("开始运行所有utils测试...")
        results = {}
        
        for test_name in self.tests.keys():
            result = await self.run_test(test_name)
            results[test_name] = result
            
            # 添加延迟避免API限流
            await asyncio.sleep(0.5)
            
        return results
        
    def print_summary(self, results: Dict[str, bool]):
        """打印测试总结"""
        logger.info(f"\n{'='*60}")
        logger.info("Utils测试总结")
        logger.info(f"{'='*60}")
        
        total = len(results)
        passed = sum(1 for r in results.values() if r is True)
        skipped = sum(1 for r in results.values() if r is None)
        failed = sum(1 for r in results.values() if r is False)
        
        logger.info(f"总测试数: {total}")
        logger.info(f"通过: {passed}")
        logger.info(f"跳过: {skipped}")
        logger.info(f"失败: {failed}")
        logger.info(f"成功率: {passed/(total-skipped)*100:.1f}%" if total > skipped else "N/A")
        
        if failed > 0:
            logger.info("\n失败的测试:")
            for name, result in results.items():
                if result is False:
                    logger.info(f"  ✗ {name}")


# 主函数
async def interactive_mode():
    """交互式模式"""
    runner = UtilsTestRunner()
    
    logger.info("\n进入交互式测试模式")
    logger.info("可用命令:")
    logger.info("  list - 列出所有测试")
    logger.info("  run <test_name> - 运行指定测试")
    logger.info("  run_all - 运行所有测试")
    logger.info("  quit - 退出")
    
    while True:
        try:
            command = input("\n测试命令 > ").strip().lower()
            
            if command == "quit":
                logger.info("退出交互式模式")
                break
            elif command == "list":
                runner.list_tests()
            elif command.startswith("run "):
                test_name = command[4:].strip()
                await runner.run_test(test_name)
            elif command == "run_all":
                results = await runner.run_all_tests()
                runner.print_summary(results)
            else:
                logger.info("未知命令,请重试")
                
        except KeyboardInterrupt:
            logger.info("\n退出交互式模式")
            break
        except Exception as e:
            logger.error(f"交互式模式错误: {e}")


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Utils测试运行器")
    parser.add_argument("--test", "-t", help="指定要运行的测试名称")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有可用测试")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互式模式")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    runner = UtilsTestRunner()
    
    if args.interactive:
        # 交互式模式
        await interactive_mode()
        return 0
        
    if args.list:
        runner.list_tests()
        return 0
        
    if args.test:
        # 运行单个测试
        result = await runner.run_test(args.test)
        return 0 if result is True else 1
    else:
        # 运行所有测试
        results = await runner.run_all_tests()
        runner.print_summary(results)
        failed_count = sum(1 for r in results.values() if r is False)
        return 1 if failed_count > 0 else 0


# 导出函数供其他模块调用
async def run_single_test(test_name: str) -> bool:
    """运行单个测试(供外部调用)"""
    runner = UtilsTestRunner()
    result = await runner.run_test(test_name)
    return result is True


async def run_all_tests() -> Dict[str, bool]:
    """运行所有测试(供外部调用)"""
    runner = UtilsTestRunner()
    results = await runner.run_all_tests()
    return results


if __name__ == "__main__":
    # 检查环境
    logger.info(f"当前工作目录: {os.getcwd()}")
    logger.info(f"Python路径: {sys.path}")
    
    exit_code = asyncio.run(main())
    exit(exit_code)
