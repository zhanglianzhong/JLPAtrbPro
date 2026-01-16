import os
import time
import hmac
import hashlib
import base64
import asyncio
import traceback
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl
import httpx
import logging


def _append_query(url: str, params: dict) -> str:
    u = urlparse(url)
    q = dict(parse_qsl(u.query))
    q.update(params)
    return urlunparse((u.scheme, u.netloc, u.path, u.params, urlencode(q), u.fragment))


def _sign(secret: str) -> tuple[str, str]:
    ts = str(int(time.time() * 1000))
    s = f"{ts}\n{secret}".encode()
    sig = base64.b64encode(hmac.new(secret.encode(), s, hashlib.sha256).digest()).decode()
    return ts, sig


async def send_dingtalk_alert(content: str, title: str | None = None) -> None:
    token = os.getenv("DINGTALK_ACCESS_TOKEN", "")
    if not token:
        return
    secret = os.getenv("DINGTALK_SECRET", "")
    url = f"https://oapi.dingtalk.com/robot/send?access_token={token}"
    if secret:
        ts, sig = _sign(secret)
        url = _append_query(url, {"timestamp": ts, "sign": sig})
    payload = {"msgtype": "text", "text": {"content": content if not title else f"[{title}] {content}"}}
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(url, json=payload)


async def send_alarm_msg(text: str) -> None:
    await send_dingtalk_alert(text, "HJLP Alarm")


def push_dingding_error_msg(func, title: str):
    if asyncio.iscoroutinefunction(func):
        async def inner():
            try:
                await func()
            except Exception:
                logging.getLogger(__name__).exception("job failed: %s", title)
                await send_dingtalk_alert(title + "\n\n" + traceback.format_exc(), "HJLP Runtime")
        return inner
    else:
        def inner():
            try:
                func()
            except Exception:
                logging.getLogger(__name__).exception("job failed: %s", title)
                asyncio.create_task(send_dingtalk_alert(title + "\n\n" + traceback.format_exc(), "HJLP Runtime"))
        return inner
