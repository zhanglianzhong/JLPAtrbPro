import math
from typing import List

# 指标模块:提供常见的回测评价指标


def cagr_from_total(total_return: float, periods: int, per_year: int) -> float:
    if periods <= 0:
        return 0.0
    # 年化处理:将区间总收益折算为每年复合增长率
    return (1.0 + total_return) ** (per_year / periods) - 1.0


def volatility(returns: List[float], per_year: int) -> float:
    if not returns:
        return 0.0
    mu = sum(returns) / len(returns)
    var = sum((r - mu) ** 2 for r in returns) / max(1, len(returns) - 1)
    # 年化波动率:样本标准差乘以年化因子
    return math.sqrt(var) * math.sqrt(per_year)


def sharpe(returns: List[float], per_year: int, rf: float = 0.0) -> float:
    vol = volatility(returns, per_year)
    if vol == 0:
        return 0.0
    mu = sum(returns) / len(returns)
    excess = mu - rf / per_year
    # 夏普比率:超额收益除以波动率(等效于按期的标准差)
    return excess / (vol / math.sqrt(per_year))


def max_drawdown(equity: List[float]) -> float:
    max_peak = -1e9
    mdd = 0.0
    for v in equity:
        if v > max_peak:
            max_peak = v
        dd = (v - max_peak) / max_peak if max_peak > 0 else 0
        mdd = min(mdd, dd)
    return abs(mdd)
