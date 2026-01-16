HJLP 策略设计概述

目标

基于 hJLP 白皮书实现可运行的 Python 策略系统,支持数据管线、Delta 计算、对冲决策、执行模拟、监控指标与回测。

系统结构

 - 目录结构:
   - `core/`:`types.py`、`data.py`、`delta.py`、`strategy.py`、`execution.py`、`metrics.py`
   - `backtest/`:`backtest.py`、`__main__.py`(入口)
   - `live/`:`run.py`(实盘主循环)、`interfaces.py`、`drift_adapter.py`、`aster_adapter.py`、`utils.py`
   - `tests/`:统一调试运行器与各模块调试脚本
   - `docs/`:文档与说明

核心数据模型

- `JLPPool`:`spot`、`long_perp`、`short_perp`、`undistributed_fees`、`jlp_supply`。
- `MarketSnapshot`:`timestamp`、`prices`、`liquidity`。
 - `StrategyConfig`:`rebalance_minutes`、`delta_bounds_pct`、`max_single_order_usd`、`twap_total_minutes`、`max_market_impact_bps`、`base_perp_fee_bps`、`flat_orderbook_haircut_pct`、`crunch_orderbook_haircut_pct`、`rolling_delta_minutes`、`jlp_units`(持有的 JLP 数量,来源环境变量 `HJLP_JLP_HOLD_AMOUNT`,读取于 `live/run.py:48`)。

策略机制

- 定时对冲:`rebalance_minutes` 到期触发再平衡。
- 阈值对冲:`delta_bounds_pct` 超界触发再平衡。
- 目标 Delta:各资产目标为 0(中性),生成相应买卖订单以靠近目标。

执行机制

- 拆单:`max_single_order_usd` 控制每片订单规模。
- TWAP:`twap_total_minutes` 与片数形成时间分散执行。
- 滑点:使用 `max_market_impact_bps` 作为简化的价格冲击模型。
- 费用:`base_perp_fee_bps` 计入执行成本。
 - 流动性:可按 `flat_orderbook_haircut_pct` 与 `crunch_orderbook_haircut_pct` 施加折减(当前实盘入口默认不启用折减)。

指标与回测

- 回测粒度:分钟级推进,年化基于分钟频率(波动、夏普)与天粒度(CAGR)。
- 输出:`BacktestResult` 包含 CAGR、波动率、夏普、总回报、最大回撤、成本、跟踪误差与信息比率。

运行示例

- 回测:`python backtest/main.py`(入口于 `backtest/main.py`)。
- 实盘:`python live/run.py`(主循环每轮对冲前刷新链上与交易所数据)。
- 默认资产:SOL、ETH、BTC;价格/流动性由适配器返回。

生产落地注意事项

 - 真实数据接入:使用链上与交易所数据源;实现可靠数据校验与容错。
 - 真仓执行:将 `execution.py` 的估算与适配器结合,支持订单生命周期管理与失败重试(Drift/Aster)。
 - 风险控制:增加限价、止损、熔断与参数动态调整;强化监控与告警。
 - 参数管理:通过环境变量管理秘钥与参数;严禁在代码中暴露秘钥;本地 `.env` 已在 `.gitignore` 忽略(规则见 `.gitignore:10–12`),使用 `.env.example` 作为模板。
 - 运行期容错:数据获取异常统一告警并跳过本次再平衡(逻辑位于 `live/run.py:59–69`)。
 - 关键链上读取:JLP 总供应量由 `get_jlp_supply_async` 获取(`live/utils.py:103–106`),与官网存在分钟级时点或口径差异属正常现象。
