"""Minimal HA WebSocket client for the CLI (aiohttp ships with Home Assistant)."""

from __future__ import annotations

import asyncio
import itertools
from typing import Any

import aiohttp


class HaWsError(RuntimeError):
    pass


async def ws_call(url: str, token: str, calls: list[tuple[str, dict[str, Any]]], timeout: float = 120.0) -> list[Any]:
    """Run ``calls`` sequentially on one connection; returns their results."""
    ids = itertools.count(1)
    results: list[Any] = []
    async with aiohttp.ClientSession() as session, session.ws_connect(f"{url}/api/websocket", heartbeat=None) as ws:
        hello = await ws.receive_json(timeout=timeout)
        if hello.get("type") != "auth_required":
            raise HaWsError(f"unexpected greeting {hello}")
        await ws.send_json({"type": "auth", "access_token": token})
        auth = await ws.receive_json(timeout=timeout)
        if auth.get("type") != "auth_ok":
            raise HaWsError(f"auth failed: {auth}")
        for msg_type, payload in calls:
            msg_id = next(ids)
            await ws.send_json({"id": msg_id, "type": msg_type, **payload})
            while True:
                msg = await ws.receive_json(timeout=timeout)
                if msg.get("id") == msg_id and msg.get("type") == "result":
                    break
            if not msg.get("success"):
                err = msg.get("error") or {}
                raise HaWsError(f"{msg_type}: {err.get('code')}: {err.get('message')}")
            results.append(msg.get("result"))
    return results


def call(url: str, token: str, msg_type: str, payload: dict[str, Any] | None = None, timeout: float = 120.0) -> Any:
    return asyncio.run(ws_call(url, token, [(msg_type, payload or {})], timeout))[0]
