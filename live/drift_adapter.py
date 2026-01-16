import os
import json
import asyncio
from typing import Dict, List
# Drift 适配器(主网):使用 DriftPy/AnchorPy 与 Solana 交互,真实下单/查询

from core.types import ExecutionResult, Order
from .interfaces import ExchangeAdapter

from solders.keypair import Keypair
from solana.rpc.async_api import AsyncClient
from anchorpy import Provider, Wallet
from driftpy.drift_client import DriftClient
from driftpy.drift_user import DriftUser
from driftpy.constants.config import configs
from driftpy.constants.numeric_constants import BASE_PRECISION
from driftpy.types import PositionDirection
import base58


class DriftAdapter(ExchangeAdapter):
    """Drift 实盘适配器:主网-only,读取价格与仓位,执行开仓。
    环境变量:
    - SOLANA_RPC_URL:主网 RPC
    - WALLET_SECRET_BASE58:私钥(Base58)
    方法:get_prices/get_liquidity/place_orders/get_positions
    """
    def __init__(self, assets: Dict[str, float]):
        self.assets = assets
        self.env = "mainnet"
        self.rpc_url = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
        self.wallet_secret_b58 = os.getenv("WALLET_SECRET_BASE58", "")
        self._ready = False
        self._lock = asyncio.Lock()
        self._client = None
        self._user = None

    async def _ensure(self):
        """初始化客户端与用户句柄(单例缓存)。"""
        async with self._lock:
            if self._ready:
                return
            cfg = configs[self.env]
            conn = AsyncClient(self.rpc_url)
            if not self.wallet_secret_b58:
                raise RuntimeError("Wallet not configured: set WALLET_SECRET_BASE58 to your base58-encoded secret key")
            secret_bytes = base58.b58decode(self.wallet_secret_b58)
            kp = Keypair.from_bytes(secret_bytes)
            wallet = Wallet(kp)
            provider = Provider(conn, wallet)
            self._client = DriftClient.from_config(cfg, provider)
            await self._client.subscribe()
            self._user = DriftUser(self._client)
            self._ready = True

    async def get_prices(self) -> Dict[str, float]:
        """读取 perp 市场的 TWAP 价格(单位:报价)"""
        await self._ensure()
        out: Dict[str, float] = {}
        for a in self.assets:
            idx = self._resolve_perp_index(a)
            market = await self._client.get_perp_market_account(idx)  # 读取市场账户
            px = market.amm.historical_oracle_data.last_oracle_price_twap
            out[a] = px / 1e6
        return out

    async def get_liquidity(self) -> Dict[str, float]:
        """简化的流动性估计(固定名义),生产可接网关或订单簿解析。"""
        await self._ensure()
        out: Dict[str, float] = {}
        for a in self.assets:
            out[a] = 1_000_000.0  # 简化:固定可成交名义,生产需读取订单簿或网关
        return out

    async def place_orders(self, orders: List[Order]) -> Dict[str, ExecutionResult]:
        """按名义近似换算基础量并下单,返回链上签名。"""
        await self._ensure()
        res: Dict[str, ExecutionResult] = {}
        prices = await self.get_prices()
        for o in orders:
            idx = self._resolve_perp_index(o.asset)
            direction = PositionDirection.SHORT() if o.side == "sell" else PositionDirection.LONG()
            qty_tokens = o.quantity if o.quantity and o.quantity > 0 else (o.notional / max(1.0, prices[o.asset]))
            qty = int(qty_tokens * BASE_PRECISION)
            sig = await self._client.open_position(direction, qty, idx)
            res[o.asset] = ExecutionResult(filled_notional=qty_tokens * prices[o.asset], avg_price=prices[o.asset], slippage_bps=o.max_impact_bps, cost=0.0, tx_sig=sig)
        return res

    async def get_positions(self) -> Dict[str, float]:
        """查询当前 perp 基础量仓位(base_asset_amount)。"""
        await self._ensure()
        await self._user.set_cache()
        out: Dict[str, float] = {}
        for a in self.assets:
            idx = self._resolve_perp_index(a)
            pos = await self._user.get_perp_position(idx)
            out[a] = float(pos.base_asset_amount) / float(BASE_PRECISION)
        return out

    def _resolve_perp_index(self, asset: str) -> int:
        m = {"SOL": 0, "ETH": 1, "BTC": 2}  # 市场索引映射(需与主网配置一致)
        return m.get(asset, 0)

    async def get_jlp_units(self) -> float:
        """返回配置的 JLP 数量(占位实现)。"""
        try:
            v = os.getenv("HJLP_JLP_HOLD_AMOUNT", "0").strip()
            return float(v) if v else 0.0
        except Exception:
            return 0.0
