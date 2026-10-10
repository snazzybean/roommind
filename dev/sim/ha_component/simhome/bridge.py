"""In-process WebSocket bridge: run any WS command through HA's real connection handling.

Same validation, normalisation and error paths as the frontend, without a socket, so
it works at an exact virtual time inside turbo runs.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
from typing import Any

from homeassistant.auth.models import User
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class WsError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class WsBridge:
    def __init__(self, hass: HomeAssistant, user: User) -> None:
        self.hass = hass
        self._ids = itertools.count(1)
        self._waiting: dict[int, asyncio.Future] = {}
        adapter = logging.LoggerAdapter(_LOGGER, {"connid": "simhome"})
        self.conn = ActiveConnection(adapter, hass, self._receive, user, None, "simhome")  # type: ignore[arg-type]

    def _receive(self, message: bytes | str | dict[str, Any]) -> None:
        data = json.loads(message) if isinstance(message, bytes | str) else message
        for msg in data if isinstance(data, list) else [data]:
            fut = self._waiting.pop(msg.get("id"), None)
            if fut is not None and not fut.done():
                fut.set_result(msg)

    async def call(self, msg_type: str, payload: dict[str, Any] | None = None, timeout: float = 120.0) -> Any:
        msg_id = next(self._ids)
        fut: asyncio.Future = self.hass.loop.create_future()
        self._waiting[msg_id] = fut
        self.conn.async_handle({"id": msg_id, "type": msg_type, **(payload or {})})
        msg = await asyncio.wait_for(fut, timeout)
        if msg.get("success") is False:
            err = msg.get("error") or {}
            raise WsError(err.get("code", "error"), err.get("message", ""))
        return msg.get("result")
