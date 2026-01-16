HJLP

目录结构

- `core/` 基础模块(`types`、`data`、`delta`、`strategy`、`execution`、`metrics`)
- `backtest/` 回测模块(`backtest.py`、`__main__.py`)
- `live/` 实盘入口与适配器(`run.py`、`interfaces.py`、`drift_adapter.py`、`aster_adapter.py`、`utils.py`)
- `.env.example` 示例环境变量文件(仓库追踪);`.env` 被忽略(不提交)
- `docs/` 文档

运行

- 回测:`python backtest/main.py`
- 实盘:`python live/run.py`
- 适配器:设置 `HJLP_ADAPTER=drift|aster`

策略原理

- 目标:在持有 JLP 的前提下,通过永续对冲降低底层资产(SOL/ETH/BTC)价格波动带来的收益波动,保住来自交易活动的费用分成。
- Delta 定义:单资产 `Δ_a = (spot_a - longPerp_a + shortPerp_a + fees)/jlpSupply`;组合归一化 `Δ_norm = Σ w_a · Δ_a`(权重动态计算,默认逆波动率+流动性修正+平滑)。
- 触发机制:
  - 资产级:当 `|Δ_cur - Δ_sma| > bound` 时触发对冲(边界 `HJLP_DELTA_BOUND_*`)。
  - 组合级:当 `|Δ_norm_cur - Δ_norm_sma| > portfolio_bound` 时触发,组合边界默认取资产边界的最大值。
- 滚动目标:默认使用 1 小时的滚动均值(SMA)作为目标以降噪;窗口越短跟随越快、偏差越小;窗口越长在趋势阶段偏差更大、触发更敏感。
- 下单与增量:增量需求 `needTokens = (Δ_cur - Δ_sma) · jlpUnits - hedgePositions`,方向 `needTokens>0` 卖(做空对冲),`<0` 买(做多对冲),名义 `notional = |needTokens| · price`;执行受 `HJLP_MAX_SINGLE_ORDER_USD` 拆片与 `HJLP_MAX_IMPACT_BPS` 冲击限制。
- 行为与权衡:区间内不交易以减少滑点与费用,仅在超界时做增量调整;边界越小、窗口越短触发更频繁、波动更低但成本更高。
- 收益与成本:
  - 收益:来自 JLP 的交易活动费用分成;资金费率在正向时可能提供附加收益。
  - 成本:永续交易费、滑点与冲击、负资金费率等。
- 参数建议:
  - 稳健:统一 1% 边界 + 1 小时窗口,触发更积极、波动更低。
  - 折中:BTC/ETH 2%、SOL 5%;窗口 30 分钟;5 分钟调度;10bps 冲击;较小单笔,在趋势中更快介入、成本可控。
  - 回报优先:3%/4%/8% 边界 + 1 小时窗口,绝对收益高、波动更高、可扩展性优。
  

测试

- 统一调试运行器:`python tests/run_debug_tests.py --module utils|drift|aster`
- 运行全部:`python tests/run_debug_tests.py`
- 单模块示例:`python tests/run_debug_tests.py --module utils`
- 单测试示例(各模块自带):`python tests/debug_utils.py`、`python tests/debug_drift_adapter.py`

环境变量

- 基础
  - `HJLP_ADAPTER` 选择适配器(`drift|aster`)
  - `SOLANA_RPC_URL` 主网 RPC 地址
  - `WALLET_SECRET_BASE58` Base58 私钥(Drift 实盘)
- 策略参数(`live/run.py`)
  - `HJLP_REBALANCE_MINUTES`
  - `HJLP_DELTA_BOUND_SOL|ETH|BTC`
  - `HJLP_MAX_SINGLE_ORDER_USD`
  - `HJLP_TWAP_TOTAL_MINUTES`
  - `HJLP_MAX_IMPACT_BPS`
  - `HJLP_BASE_PERP_FEE_BPS`
  - `HJLP_JLP_HOLD_AMOUNT` 当前持有的 JLP 数量
- Aster(可选)
  - `ASTER_BASE_URL`、`ASTER_API_KEY`、`ASTER_API_SECRET`、`ASTER_RECV_WINDOW`

依赖与环境

- 创建环境(Python 3.10):
  - `conda create -y -n hjlp python=3.10`
  - `conda activate hjlp`
  - `pip install -r requirements-hjlp-live.txt`

生产行为

- 数据获取异常(链上/交易所)统一告警并跳过本次再平衡(`live/run.py` 主循环)
- `.env` 为本地敏感配置,已在 `.gitignore` 忽略;统一通过 `.env.example` 分享模板
