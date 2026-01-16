#!/usr/bin/env python3
"""
统一的Debug测试运行器
可以运行所有适配器的debug测试
"""

import asyncio
import os
import sys
import logging
import argparse
from typing import Dict, Any

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _load_env(path: str = ".env") -> None:
    """加载本地.env文件到环境变量(仅在未设置时注入)"""
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if not s or s.startswith("#"):
                        continue
                    if "=" not in s:
                        continue
                    k, v = s.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k and (k not in os.environ or not os.environ[k]):
                        os.environ[k] = v
    except Exception as e:
        logger.warning(f"加载.env失败: {e}")


class DebugTestRunner:
    """统一的Debug测试运行器"""
    
    def __init__(self):
        self.test_modules = {
            "utils": "tests.debug_utils",
            "drift": "tests.debug_drift_adapter", 
            "aster": "tests.debug_aster_adapter"
        }
        self.results = {}
    
    async def run_module_tests(self, module_name: str, test_name: str = None) -> Dict[str, Any]:
        """运行指定模块的测试"""
        if module_name not in self.test_modules:
            logger.error(f"未知模块: {module_name}")
            logger.info(f"可用模块: {list(self.test_modules.keys())}")
            return {}
        
        try:
            # 动态导入模块
            module_path = self.test_modules[module_name]
            module = __import__(module_path, fromlist=[''])
            
            if test_name:
                # 运行单个测试
                logger.info(f"运行 {module_name} 模块的测试: {test_name}")
                if hasattr(module, 'run_single_test'):
                    result = await module.run_single_test(test_name)
                    return {test_name: result}
                else:
                    logger.error(f"模块 {module_name} 不支持单测试运行")
                    return {}
            else:
                # 运行所有测试
                logger.info(f"运行 {module_name} 模块的所有测试")
                if hasattr(module, 'run_all_tests'):
                    return await module.run_all_tests()
                else:
                    logger.error(f"模块 {module_name} 不支持批量测试运行")
                    return {}
                    
        except ImportError as e:
            logger.error(f"导入模块 {module_name} 失败: {e}")
            return {}
        except Exception as e:
            logger.error(f"运行 {module_name} 模块测试失败: {e}")
            return {}
    
    async def run_all_modules(self) -> Dict[str, Dict[str, Any]]:
        """运行所有模块的测试"""
        all_results = {}
        
        for module_name in self.test_modules.keys():
            logger.info(f"\n{'='*60}")
            logger.info(f"开始运行 {module_name} 模块测试")
            logger.info(f"{'='*60}")
            
            results = await self.run_module_tests(module_name)
            all_results[module_name] = results
            
            # 添加延迟避免API限流
            await asyncio.sleep(1)
        
        return all_results
    
    def print_summary(self, all_results: Dict[str, Dict[str, Any]]):
        """打印测试总结"""
        logger.info(f"\n{'='*70}")
        logger.info("所有模块测试总结")
        logger.info(f"{'='*70}")
        
        total_tests = 0
        total_passed = 0
        total_failed = 0
        total_skipped = 0
        
        for module_name, results in all_results.items():
            if not results:
                logger.info(f"\n{module_name}: 无测试结果")
                continue
                
            passed = sum(1 for r in results.values() if r is True)
            failed = sum(1 for r in results.values() if r is False)
            skipped = sum(1 for r in results.values() if r is None)
            total = len(results)
            
            logger.info(f"\n{module_name}:")
            logger.info(f"  总测试数: {total}")
            logger.info(f"  通过: {passed}")
            logger.info(f"  失败: {failed}")
            logger.info(f"  跳过: {skipped}")
            logger.info(f"  成功率: {passed/(total-skipped)*100:.1f}%" if total > skipped else "N/A")
            
            total_tests += total
            total_passed += passed
            total_failed += failed
            total_skipped += skipped
        
        logger.info(f"\n总体统计:")
        logger.info(f"  总测试数: {total_tests}")
        logger.info(f"  通过: {total_passed}")
        logger.info(f"  失败: {total_failed}")
        logger.info(f"  跳过: {total_skipped}")
        logger.info(f"  总体成功率: {total_passed/(total_tests-total_skipped)*100:.1f}%" if total_tests > total_skipped else "N/A")


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="统一的Debug测试运行器")
    parser.add_argument("--module", "-m", help="指定要运行的模块 (utils/drift/aster)")
    parser.add_argument("--test", "-t", help="指定要运行的测试名称")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有可用模块")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    runner = DebugTestRunner()
    _load_env()
    
    if args.list:
        logger.info("可用模块:")
        for module in runner.test_modules.keys():
            logger.info(f"  - {module}")
        return 0
    
    if args.module:
        # 运行指定模块
        results = await runner.run_module_tests(args.module, args.test)
        if args.test:
            # 单个测试
            success = results.get(args.test, False) is True
            return 0 if success else 1
        else:
            # 所有测试
            passed = sum(1 for r in results.values() if r is True)
            failed = sum(1 for r in results.values() if r is False)
            return 0 if failed == 0 and passed > 0 else 1
    else:
        # 运行所有模块
        all_results = await runner.run_all_modules()
        runner.print_summary(all_results)
        
        # 计算总体结果
        total_passed = 0
        total_failed = 0
        for results in all_results.values():
            if results:
                total_passed += sum(1 for r in results.values() if r is True)
                total_failed += sum(1 for r in results.values() if r is False)
        
        return 0 if total_failed == 0 and total_passed > 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
