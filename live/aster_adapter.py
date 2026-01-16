import os
from typing import Dict, List, Optional
# Aster 实盘适配器:REST v1/v2,签名下单/价格/深度/仓位查询
# 参考接口文档:https://github.com/asterdex/api-docs/blob/master/aster-finance-futures-api_CN.md

import asyncio
import time
import hmac
import hashlib
from urllib.parse import urlencode
import httpx
import logging

from core.types import ExecutionResult, Order
from live.interfaces import ExchangeAdapter


class AsterAdapter(ExchangeAdapter):
    """
    Aster 永续实盘适配器(REST),基于 v1/v2 路由:
    - 基础地址: `https://fapi.asterdex.com`
    - 价格: `GET /fapi/v1/ticker/price?symbol=...`
    - 深度: `GET /fapi/v1/depth?symbol=...&limit=...`
    - 下单: `POST /fapi/v1/order` (TRADE),下单前自动设置杠杆为 20(同交易对缓存)
    - 持仓风险: `GET /fapi/v2/positionRisk` (USER_DATA)
    - 余额查询: `GET /fapi/v2/balance`,读取资产 `JLP` 作为当前 JLP 数量

    鉴权与签名:
    - 需要签名的接口 (TRADE/USER_DATA) 使用参数 `timestamp`、可选 `recvWindow`,并附加 HMAC-SHA256 `signature`
    - 请求头包含 `X-MBX-APIKEY`
    """

    def __init__(self, assets: Dict[str, float]):
        self.assets = assets
        self.base_url = os.getenv("ASTER_BASE_URL", "https://fapi.asterdex.com")
        self.api_key = os.getenv("ASTER_API_KEY", "")
        self.api_secret = os.getenv("ASTER_API_SECRET", "")
        self.recv_window = int(os.getenv("ASTER_RECV_WINDOW", "5000"))
        self.client = httpx.AsyncClient(timeout=15.0)
        self._lock = asyncio.Lock()
        self.positions: Dict[str, float] = {a: 0.0 for a in assets}
        self._time_offset_ms: Optional[int] = None
        self._filters_cache: Dict[str, Dict[str, float]] = {}
        self._leverage_cache: Dict[str, int] = {}
        self._logger = logging.getLogger(__name__)

    async def _headers(self) -> Dict[str, str]:
        return {"X-MBX-APIKEY": self.api_key, "Content-Type": "application/x-www-form-urlencoded"}

    async def _server_time(self) -> int:
        try:
            r = await self.client.get(f"{self.base_url}/fapi/v1/time")
            if r.status_code == 200:
                return int(r.json().get("serverTime"))
        except Exception:
            pass
        return int(time.time() * 1000)

    async def _ensure_time_offset(self):
        if self._time_offset_ms is not None:
            return
        t_server = await self._server_time()
        t_local = int(time.time() * 1000)
        self._time_offset_ms = t_server - t_local

    def _timestamp(self) -> int:
        base = int(time.time() * 1000)
        return base + (self._time_offset_ms or 0)

    def _sign(self, params: Dict[str, str]) -> str:
        qs = urlencode(params)
        return hmac.new(self.api_secret.encode(), qs.encode(), hashlib.sha256).hexdigest()

    def _symbol(self, asset: str) -> str:
        return os.getenv(f"ASTER_SYMBOL_{asset}", f"{asset}USDT")

    def _url(self, route: str) -> str:
        return f"{self.base_url}/fapi/v1/{route}"

    async def _get_filters(self, symbol: str) -> Dict[str, float]:
        """获取交易对过滤器(步长与最小名义),用于下单前校验;来源 `GET /fapi/v1/exchangeInfo`。"""
        if symbol in self._filters_cache:
            return self._filters_cache[symbol]
        try:
            r = await self.client.get(self._url("exchangeInfo"))
            if r.status_code == 200:
                ex = r.json()
                for s in ex.get("symbols", []):
                    if s.get("symbol") == symbol:
                        lot = next((f for f in s.get("filters", []) if f.get("filterType") in ("LOT_SIZE", "MARKET_LOT_SIZE")), None)
                        min_notional = next((f for f in s.get("filters", []) if f.get("filterType") == "MIN_NOTIONAL"), None)
                        step = float(lot.get("stepSize", 0.001)) if lot else 0.001
                        min_not = float(min_notional.get("notional", 0.0)) if min_notional else 0.0
                        out = {"step": step, "min_notional": min_not}
                        self._filters_cache[symbol] = out
                        return out
        except Exception:
            pass
        out = {"step": 0.001, "min_notional": 0.0}
        self._filters_cache[symbol] = out
        return out

    def _round_step(self, qty: float, step: float) -> float:
        """按步长取整数量，并处理浮点精度问题"""
        if step <= 0:
            return qty
        return round((int(qty / step)) * step, 8)  # 最多保留8位小数

    def _get_precision(self, step: float) -> int:
        """根据步长计算精度（小数位数）"""
        if step >= 1:
            return 0
        step_str = f"{step:.10f}".rstrip('0')
        if '.' in step_str:
            return len(step_str.split('.')[1])
        return 0

    async def get_prices(self) -> Dict[str, float]:
        """读取最新价格;使用 `GET /fapi/v1/ticker/price`。"""
        await self._ensure_time_offset()
        out: Dict[str, float] = {}
        for a in self.assets:
            sym = self._symbol(a)
            r = await self.client.get(self._url("ticker/price"), params={"symbol": sym})
            if r.status_code == 200:
                out[a] = float(r.json().get("price", self.assets[a]))
            else:
                raise RuntimeError(f"Aster get_prices失败: {sym} -> {r.text}")
        return out

    async def get_liquidity(self) -> Dict[str, float]:
        """聚合前几档深度估算可成交名义;使用 `GET /fapi/v1/depth`。"""
        await self._ensure_time_offset()
        out: Dict[str, float] = {}
        for a in self.assets:
            sym = self._symbol(a)
            r = await self.client.get(self._url("depth"), params={"symbol": sym, "limit": 5})
            if r.status_code == 200:
                data = r.json()
                # 聚合前5档名义(估算)
                bids = data.get("bids", [])
                asks = data.get("asks", [])
                top = bids[:3] + asks[:3]
                avail = 0.0
                for px, sz, *_ in top:
                    avail += float(px) * float(sz)
                out[a] = max(avail, 0.0)
            else:
                raise RuntimeError(f"Aster get_liquidity失败: {sym} -> {r.text}")
        return out

    async def place_orders(self, orders: List[Order]) -> Dict[str, ExecutionResult]:
        """签名市价下单,自动设置杠杆(20),按步长与最小名义校验;返回订单ID或空成交。"""
        prices = await self.get_prices()
        res: Dict[str, ExecutionResult] = {}
        await self._ensure_time_offset()
        for o in orders:
            sym = self._symbol(o.asset)
            try:
                target_leverage = 20
                if self._leverage_cache.get(sym) != target_leverage:
                    await self._set_leverage(sym, target_leverage)
                    self._leverage_cache[sym] = target_leverage
            except Exception as e:
                self._logger.warning(f"set_leverage failed for {sym}: {e}")
            filters = await self._get_filters(sym)
            px = prices[o.asset]
            qty_in = o.quantity if o.quantity and o.quantity > 0 else (o.notional / max(1.0, px))
            step = filters.get("step", 0.001)
            qty = self._round_step(qty_in, step)
            min_not = filters.get("min_notional", 0.0)
            notional = qty * px
            if notional < min_not:
                self._logger.info(
                    "skip min_notional | sym=%s asset=%s notional=%.2f min_notional=%.2f price=%.6f qty_raw=%.6f qty_rounded=%.6f",
                    sym, o.asset, notional, min_not, px, qty_in, qty,
                )
                res[o.asset] = ExecutionResult(filled_notional=0.0, avg_price=px, slippage_bps=o.max_impact_bps, cost=0.0, tx_sig=None)
                continue
            if qty <= 0.0:
                self._logger.info(
                    "skip zero_qty | sym=%s asset=%s notional=%.2f price=%.6f qty_raw=%.6f step=%.6f",
                    sym, o.asset, notional, px, qty_in, step,
                )
                res[o.asset] = ExecutionResult(filled_notional=0.0, avg_price=px, slippage_bps=o.max_impact_bps, cost=0.0, tx_sig=None)
                continue

            # 根据步长计算精度并格式化数量字符串
            precision = self._get_precision(step)
            qty_str = f"{qty:.{precision}f}"

            side = "BUY" if o.side == "buy" else "SELL"
            params = {
                "symbol": sym,
                "side": side,
                "type": "MARKET",
                "quantity": qty_str,
                "timestamp": str(self._timestamp()),
                "recvWindow": str(self.recv_window),
            }
            sig = self._sign(params)
            params["signature"] = sig
            headers = await self._headers()
            r = await self.client.post(self._url("order"), data=params, headers=headers)
            if r.status_code == 200:
                j = r.json()
                txid = j.get("orderId") or j.get("clientOrderId")
                self.positions[o.asset] = self.positions.get(o.asset, 0.0) + (qty if side == "BUY" else -qty)
                res[o.asset] = ExecutionResult(filled_notional=notional, avg_price=px, slippage_bps=o.max_impact_bps, cost=0.0, tx_sig=str(txid) if txid else None)
            else:
                try:
                    msg = r.text
                except Exception:
                    msg = "<no text>"
                self._logger.warning("place order failed | sym=%s asset=%s status=%s body=%s", sym, o.asset, r.status_code, msg)
                res[o.asset] = ExecutionResult(filled_notional=0.0, avg_price=px, slippage_bps=o.max_impact_bps, cost=0.0, tx_sig=None)
        return res

    async def _set_leverage(self, symbol: str, leverage: int) -> None:
        await self._ensure_time_offset()
        params = {
            "symbol": symbol,
            "leverage": str(leverage),
            "timestamp": str(self._timestamp()),
            "recvWindow": str(self.recv_window),
        }
        params["signature"] = self._sign(params)
        headers = await self._headers()
        r = await self.client.post(self._url("leverage"), data=params, headers=headers)
        if r.status_code != 200:
            raise RuntimeError(f"set_leverage failed: {symbol} -> {r.text}")

    async def get_jlp_units(self) -> float:
        await self._ensure_time_offset()
        ts = str(self._timestamp())
        params = {"timestamp": ts, "recvWindow": str(self.recv_window)}
        params["signature"] = self._sign(params)
        headers = await self._headers()
        r = await self.client.get(f"{self.base_url}/fapi/v2/balance", params=params, headers=headers)
        if r.status_code != 200:
            raise RuntimeError(f"balance query failed: {r.text}")
        data = r.json()
        if not isinstance(data, list):
            raise RuntimeError("balance response format invalid")
        for b in data:
            asset = str(b.get("asset", ""))
            if asset == "JLP":
                val = b.get("balance")
                if val is None:
                    raise RuntimeError("JLP balance missing")
                try:
                    return round(float(val), 2)
                except Exception:
                    raise RuntimeError("JLP balance parse error")
        raise RuntimeError("JLP asset not found in balance list")

    async def get_positions(self) -> Dict[str, float]:
        """查询账户风险(positionRisk),映射到资产符号;使用 `GET /fapi/v2/positionRisk`。"""
        await self._ensure_time_offset()
        ts = str(self._timestamp())
        params = {"timestamp": ts, "recvWindow": str(self.recv_window)}
        params["signature"] = self._sign(params)
        headers = await self._headers()
        r = await self.client.get(f"{self.base_url}/fapi/v2/positionRisk", params=params, headers=headers)
        out: Dict[str, float] = {}
        if r.status_code == 200:
            for p in r.json():
                sym = p.get("symbol")
                qty = float(p.get("positionAmt", 0.0))
                for a in self.assets:
                    if self._symbol(a) == sym:
                        out[a] = qty
        else:
            raise RuntimeError(f"Aster get_positions失败: {r.text}")
        return out
