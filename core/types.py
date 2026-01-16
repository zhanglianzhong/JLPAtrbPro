from dataclasses import dataclass
from typing import Dict, List, Optional

# 本模块定义策略系统的核心类型(数据结构与配置项),供各模块统一引用。
# 尽量保持轻量、无业务逻辑,仅承载数据表达。


Asset = str  # 资产符号类型,例如 "SOL"、"ETH"、"BTC"


@dataclass
class MarketSnapshot:
    # 市场快照:记录某一时刻的价格与流动性信息
    timestamp: int  # 时间戳(分钟粒度)
    prices: Dict[Asset, float]  # 各资产最新价格(报价货币计价)
    liquidity: Dict[Asset, float]  # 各资产可用流动性(简化模型下的可成交名义)


@dataclass
class JLPPool:
    # JLP 池状态:用于计算 Delta 与对冲目标
    spot: Dict[Asset, float]  # 现货持仓数量
    long_perp: Dict[Asset, float]  # 永续合约多头名义
    short_perp: Dict[Asset, float]  # 永续合约空头名义
    undistributed_fees: float  # 尚未分配的费用(美元计价)
    jlp_supply: float  # JLP 代币总供给(用于 Delta 归一化)


@dataclass
class Order:
    # 策略生成的对冲订单(抽象层),后由执行模块撮合/下单
    asset: Asset  # 资产符号
    side: str  # "buy" 或 "sell"
    twap_slices: int  # 拆单份数(用于 TWAP)
    max_impact_bps: float  # 允许的最大价格冲击(基点)
    notional: float = 0.0  # 名义金额(美元计)
    quantity: float = 0.0


@dataclass
class ExecutionResult:
    # 执行结果(聚合层):用于统计成本与成交信息
    filled_notional: float  # 实际成交名义
    avg_price: float  # 均价(简化模型)
    slippage_bps: float  # 估算滑点(基点)
    cost: float  # 手续费成本等(美元计)
    tx_sig: Optional[str] = None  # 交易签名(链上下单时返回),仿真/失败为 None


@dataclass
class HedgeDecision:
    # 对冲决策产物:订单列表与目标 Delta(每枚 JLP 的目标值;当前为已持仓对冲口径)
    orders: List[Order]
    target_deltas: Dict[Asset, float]


@dataclass
class StrategyConfig:
    # 策略配置项:控制再平衡频率、阈值与执行相关参数
    rebalance_minutes: Optional[int]  # 定时再平衡频率(分钟);None 表示关闭
    delta_bounds_pct: Optional[Dict[Asset, float]]  # 各资产 Delta 阈值(超过则触发对冲)
    max_single_order_usd: float  # 单笔最大订单名义(用于拆单)
    twap_total_minutes: int  # TWAP 总时长(简化用作切片个数参考)
    max_market_impact_bps: float  # 允许最大市场冲击(滑点)
    base_perp_fee_bps: float  # 永续交易基础费用(基点)
    flat_orderbook_haircut_pct: float  # 平坦订单簿折减比例
    crunch_orderbook_haircut_pct: float  # 流动性紧缩折减比例
    rolling_delta_minutes: Optional[int]  # 滚动 Delta 时间窗(None 表示不使用)
    jlp_units: float  # 当前持有的 JLP 数量(用于将每枚 JLP 的 Delta 转换为总对冲名义)


@dataclass
class BacktestResult:
    # 回测指标输出:用于评估策略风险收益特征
    cagr: float  # 年化复合增长率
    volatility: float  # 年化波动率
    sharpe: float  # 夏普比率(无风险利率近似为 0)
    total_return: float  # 总收益率(区间)
    max_drawdown: float  # 最大回撤
    perps_costs_pct: float  # 永续交易成本占初始 AUM 的比例
    spot_costs_pct: float  # 现货交易成本占初始 AUM 的比例
    tracking_error: float  # 跟踪误差(相对基准)
    info_ratio: float  # 信息比率(超额收益/跟踪误差)
