from typing import Dict, List

"""简化回测引擎

该模块以分钟粒度推进市场与组合状态,依次执行:
1) 使用 GBM 近似生成价格路径;
2) 基于流动性模型给出可成交名义;
3) 计算池状态与 Delta,对冲产生订单;
4) 估算执行成本并累计权益曲线;
5) 汇总年化收益、波动、夏普、最大回撤等指标。

为便于快速实验,模型在执行与滑点上采用极简近似;真实接入请替换数据与执行层。
"""

from core.types import StrategyConfig, BacktestResult
from core.data import GBMSimulator, LiquidityModel, JLPStateGenerator
from core.strategy import decide_hedge
from core.execution import execute_orders
from core.metrics import cagr_from_total, volatility, sharpe, max_drawdown

# 回测主流程:分钟推进价格与流动性,计算 Delta 并生成订单,统计权益与指标。


def run_backtest(
    days: int,
    seed: int,
    initial_prices: Dict[str, float],
    mu_daily: Dict[str, float],
    sigma_daily: Dict[str, float],
    jlp_supply: float,
    undistributed_fees_usd: float,
    spot: Dict[str, float],
    long_perp: Dict[str, float],
    short_perp: Dict[str, float],
    strategy: StrategyConfig,
) -> BacktestResult:
    """按分钟推进的简化回测

    参数
    - days: 回测天数
    - seed: 随机种子(价格路径可重复)
    - initial_prices, mu_daily, sigma_daily: 初始价格与日频漂移/波动率
    - jlp_supply, undistributed_fees_usd: 初始 JLP 供给与未分配费用(美元)
    - spot, long_perp, short_perp: 初始现货与永续仓位名义
    - strategy: 策略参数(再平衡频率、阈值、执行限制等)

    流程
    - 生成价格与流动性;
    - 依据池快照与策略决策产生订单;
    - 估算执行成本并累计权益;
    - 计算年化与风险指标。
    """

    minutes = days * 24 * 60  # 总步数(分钟)
    per_year_minutes = 365 * 24 * 60  # 年化分钟数(用于波动/夏普)
    per_year_days = 365  # 年化天数(用于 CAGR)

    # 价格/流动性/池状态生成器
    gbm = GBMSimulator(seed, initial_prices, mu_daily, sigma_daily)
    liq = LiquidityModel(
        {a: 1_000_000.0 for a in initial_prices},
        strategy.flat_orderbook_haircut_pct,
        strategy.crunch_orderbook_haircut_pct,
    )
    jlp = JLPStateGenerator(jlp_supply, undistributed_fees_usd, spot, long_perp, short_perp)

    equity: List[float] = []  # 权益曲线
    returns: List[float] = []  # 分钟收益序列
    perps_costs = 0.0  # 永续执行成本累计
    spot_costs = 0.0  # 现货成本(当前示例未计)

    # 初始权益
    value_prev = _portfolio_value(jlp, initial_prices)
    equity.append(value_prev)

    # 主循环:分钟推进
    for t in range(1, minutes + 1):
        prices = gbm.step()  # 推进价格
        liquid = liq.snapshot()  # 当前可用流动性名义
        pool = jlp.snapshot()  # 池状态快照

        # 决策对冲(边界触发;外部频率由仿真步长决定)
        dec = decide_hedge(pool, prices, strategy)
        if dec.orders:
            res = execute_orders(dec.orders, prices, liquid, strategy.base_perp_fee_bps)
            perps_costs += sum(r.cost for r in res.values())

        # 更新权益与收益
        value = _portfolio_value(jlp, prices)
        equity.append(value)
        r = (value - value_prev) / value_prev if value_prev > 0 else 0.0
        returns.append(r)
        value_prev = value

    # 区间收益与年化指标
    total_ret = (equity[-1] - equity[0]) / equity[0] if equity[0] > 0 else 0.0
    c = cagr_from_total(total_ret, days, per_year_days)
    v = volatility(returns, per_year_minutes)
    s = sharpe(returns, per_year_minutes)
    mdd = max_drawdown(equity)

    # 相对风险指标(示例:以自身均值为“基准”近似)
    te = _tracking_error(returns)
    ir = _info_ratio(returns)

    # 成本归一化(占初始 AUM 比例)
    initial_aum = equity[0]
    perps_costs_pct = perps_costs / initial_aum if initial_aum > 0 else 0.0

    return BacktestResult(
        cagr=c,
        volatility=v,
        sharpe=s,
        total_return=total_ret,
        max_drawdown=mdd,
        perps_costs_pct=perps_costs_pct,
        spot_costs_pct=spot_costs / initial_aum if initial_aum > 0 else 0.0,
        tracking_error=te,
        info_ratio=ir,
    )


def _portfolio_value(jlp: JLPStateGenerator, prices: Dict[str, float]) -> float:
    """以当前价格计算池的简化总价值

    仅计入现货名义与未分配费用,不考虑永续的未实现盈亏;
    回测场景中用于近似权益曲线。
    """
    pool = jlp.snapshot()
    val = 0.0
    for a, qty in pool.spot.items():
        val += qty * prices[a]
    val += pool.undistributed_fees
    return val


def _tracking_error(returns: List[float]) -> float:
    """跟踪误差(标准差)

    以序列均值为“基准”近似,输出分布的标准差,
    仅用于演示 IR 的构成。
    """
    if not returns:
        return 0.0
    mu = sum(returns) / len(returns)
    var = sum((r - mu) ** 2 for r in returns) / max(1, len(returns) - 1)
    return var ** 0.5


def _info_ratio(returns: List[float]) -> float:
    """信息比率(均值 / 跟踪误差)"""
    te = _tracking_error(returns)
    if te == 0:
        return 0.0
    mu = sum(returns) / len(returns)
    return mu / te
