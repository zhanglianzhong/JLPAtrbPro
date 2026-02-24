import os
import asyncio
import logging
import sys
# 运行入口脚本:定时拉取链上/交易所数据,计算 Delta,生成并执行对冲订单

from core.types import StrategyConfig
from core.delta import asset_delta
from live.config import env_int as cfg_int, env_float as cfg_float, env_str as cfg_str, HJLP_ADAPTER
from core.strategy import decide_hedge
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
from live.alerts import push_dingding_error_msg
from core.execution import execute_orders
from live.utils import (
    get_jlp_supply_async,
    get_staked_sol_async,
    get_positions_by_asset_async,
    fetch_fees_reserves_async,
    get_spot_liquidity_async,
    cleanup_global_clients,
)


def build_adapter(assets):
    # 根据环境变量选择真实适配器(drift 或 aster)
    name = HJLP_ADAPTER
    if name == "drift":
        from live.drift_adapter import DriftAdapter
        return DriftAdapter(assets)
    if name == "aster":
        from live.aster_adapter import AsterAdapter
        return AsterAdapter(assets)
    raise RuntimeError("生产环境交易适配器配置错误,请将 HJLP_ADAPTER 设置为 drift 或 aster")


async def main_async():
    logger = logging.getLogger(__name__)
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", stream=sys.stdout)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    # 关注资产集合(作为键集合使用);价格与仓位数据在后续实时填充
    assets = {"SOL": 0.0, "ETH": 0.0, "BTC": 0.0}
    _validate_env()
    adapter = build_adapter(assets)
    ju = await adapter.get_jlp_units()
    
    # 构造策略参数(全部从环境变量读取),包含再平衡频率、Delta 边界与执行限制
    strategy = StrategyConfig(
        rebalance_minutes=cfg_int("HJLP_REBALANCE_MINUTES", 5),
        delta_bounds_pct={
            "SOL": cfg_float("HJLP_DELTA_BOUND_SOL", 0.08),
            "ETH": cfg_float("HJLP_DELTA_BOUND_ETH", 0.04),
            "BTC": cfg_float("HJLP_DELTA_BOUND_BTC", 0.03),
        },
        max_single_order_usd=cfg_float("HJLP_MAX_SINGLE_ORDER_USD", 500.0),
        twap_total_minutes=cfg_int("HJLP_TWAP_TOTAL_MINUTES", 30),
        max_market_impact_bps=cfg_float("HJLP_MAX_IMPACT_BPS", 10.0),
        base_perp_fee_bps=cfg_float("HJLP_BASE_PERP_FEE_BPS", 5.0),
        flat_orderbook_haircut_pct=0.0,
        crunch_orderbook_haircut_pct=0.0,
        rolling_delta_minutes=None,
        jlp_units=ju,
    )
    logger.info("live start | adapter=%s | jlp_units=%s | rebalance_minutes=%s", HJLP_ADAPTER, strategy.jlp_units, strategy.rebalance_minutes)

    # 链上数据与交易所数据定期刷新:基于资产边界触发纯资产级对冲
    scheduler = AsyncIOScheduler()
    # 定时作业:采集链上/交易所数据并根据资产级差异决定是否下单

    # 任务计数器
    job_counter = 0

    async def job():
        nonlocal job_counter
        job_counter += 1

        logger.info("" + ("-" * 100))
        logger.info("rebalance tick start")
        ju_tick = await adapter.get_jlp_units()
        strategy.jlp_units = ju_tick

        jlp_supply = await _resolve_jlp_supply()
        fees = await _resolve_undistributed_fees()
        spot = await _resolve_spot_liquidity(assets)
        long_perp, short_perp = await _resolve_perp_exposure()
        prices = await adapter.get_prices()
        liquid = await adapter.get_liquidity()
        hedge_pos = await adapter.get_positions()
        logger.info("onchain jlp_supply=%s jlp_units=%s fees=%s spot=%s long=%s short=%s", jlp_supply, strategy.jlp_units, fees, spot, long_perp, short_perp)
        logger.info("market prices=%s liquidity=%s", prices, liquid)
        logger.info("exchange positions=%s", hedge_pos)
        pool = build_pool(jlp_supply, fees, spot, long_perp, short_perp)
        dec = decide_hedge(pool, prices, strategy, hedge_positions=hedge_pos)
        orders = dec.orders
        by_asset = {o.asset: o for o in orders}
        for a in prices:
            d_cur = asset_delta(pool, a)
            denom = abs(d_cur) if abs(d_cur) > 1e-9 else 1e-9
            hedged_tokens = float(hedge_pos.get(a, 0.0))
            hedged_per_jlp = hedged_tokens / (strategy.jlp_units if strategy.jlp_units > 0 else 1.0)
            pct_diff = abs(hedged_per_jlp + d_cur) / denom
            bound = strategy.delta_bounds_pct.get(a, 0.0)
            fees_tokens = float((fees or {}).get(a, 0.0))
            spot_fee = float(spot.get(a, 0.0)) + fees_tokens
            logger.info("资产=%s | 当前delta=%.6f 已对冲=%.6f 差分%%=%.2f%% 边界=%.2f%%", a, d_cur, hedged_per_jlp, pct_diff * 100.0, bound * 100.0)
            logger.info("资产=%s | fees=%.6f spot+fees=%.6f long=%.6f short=%.6f jlp_supply=%.2f", a, fees_tokens, spot_fee, float(long_perp.get(a, 0.0)), float(short_perp.get(a, 0.0)), float(jlp_supply))
            if a in by_asset:
                o = by_asset[a]
                target_tokens = -d_cur * (strategy.jlp_units if strategy.jlp_units > 0 else 1.0)
                delta_tokens = target_tokens - hedged_tokens
                qty = abs(delta_tokens)
                notional = qty * prices.get(a, 0.0)
                logger.info("资产=%s | 决策=下单 side=%s qty≈%.6f notional≈%.2f", a, o.side, qty, notional)
            else:
                logger.info("资产=%s | 决策=无需调仓", a)
        if orders:
            fill = await adapter.place_orders(orders)
            for o in orders:
                r = fill.get(o.asset)
                px = prices.get(o.asset, 0.0)
                est_notional = o.quantity * px if o.quantity and o.quantity > 0 else o.notional
                logger.info(
                    "订单结果 | 资产=%s side=%s qty=%.6f notional=%.2f avg_price=%.6f filled=%.2f cost=%.2f slip_bps=%.2f tx=%s",
                    o.asset, o.side, (o.quantity if o.quantity else est_notional / max(1.0, px)), est_notional, (r.avg_price if r else px), (r.filled_notional if r else 0.0), (r.cost if r else 0.0), (r.slippage_bps if r else 0.0), (r.tx_sig if r else None),
                )
            txs = [fill[o.asset].tx_sig for o in orders if fill.get(o.asset)]
            logger.info("订单汇总 | 数量=%d tx=%s", len(orders), [t for t in txs if t])
            pos_after = await adapter.get_positions()
            logger.info("positions after=%s", pos_after)
        else:
            logger.info("no orders; within bounds")

    scheduler.add_job(
        push_dingding_error_msg(job, "HJLP rebalance error"),
        "interval",
        minutes=strategy.rebalance_minutes,
        next_run_time=datetime.now(),
        coalesce=True,
        max_instances=1,
        id="rebalance",
        misfire_grace_time=60,
    )
    scheduler.start()

    # 优雅退出处理
    try:
        await asyncio.Event().wait()
    finally:
        logger.info("正在清理全局 RPC 客户端...")
        await cleanup_global_clients()


def build_pool(jlp_supply, fees, spot, long_perp, short_perp):
    from core.types import JLPPool
    # 构造 JLP 池状态快照,作为 Delta 计算的输入
    return JLPPool(spot=spot, long_perp=long_perp, short_perp=short_perp, undistributed_fees=fees, jlp_supply=jlp_supply)


async def _resolve_undistributed_fees() -> dict:
    fees = await fetch_fees_reserves_async()
    return {k: float(v) for k, v in fees.items()}


async def _resolve_jlp_supply() -> float:
    return await get_jlp_supply_async()


async def _resolve_spot_liquidity(assets: dict) -> dict:
    assets_list = list(assets.keys())
    vals = await asyncio.gather(*[get_spot_liquidity_async(a) for a in assets_list])
    out = {a: float(v) for a, v in zip(assets_list, vals)}
    if "SOL" in out:
        out["SOL"] += await get_staked_sol_async()
    return out


async def _resolve_perp_exposure() -> tuple[dict, dict]:
    agg = await get_positions_by_asset_async()
    long_perp = {k: float(v.get('long',0.0)) for k,v in agg.items()}
    short_perp = {k: float(v.get('short',0.0)) for k,v in agg.items()}
    return long_perp, short_perp


def _validate_env():
    # 启动前校验必需环境变量,避免使用不完整配置导致运行期失败
    adapter = HJLP_ADAPTER
    if adapter == "drift":
        if not os.getenv("WALLET_SECRET_BASE58", "").strip():
            raise RuntimeError("WALLET_SECRET_BASE58 未配置")
    elif adapter == "aster":
        need = ["ASTER_API_KEY", "ASTER_API_SECRET"]
        for k in need:
            if not os.getenv(k, "").strip():
                raise RuntimeError(f"{k} 未配置")


if __name__ == "__main__":
    asyncio.run(main_async())
