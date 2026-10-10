"""Timeline / CLI actions that need Home Assistant (world actions are delegated)."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from homeassistant.helpers import entity_registry as er

from roommind_sim import clock as clockmod
from roommind_sim.scenario import TimelineItem
from roommind_sim.world import World, WorldError

if TYPE_CHECKING:
    from .runtime import SimRuntime

_LOGGER = logging.getLogger(__name__)


async def run_timeline_item(rt: SimRuntime, item: TimelineItem) -> None:
    if item.index in rt.done:
        return
    rt.done.add(item.index)
    try:
        result = await run_action(rt, item.action, dict(item.args))
        rt.event(
            "action", {"index": item.index, "action": item.action, "args": item.args, "ok": True, "result": result}
        )
    except Exception as err:  # noqa: BLE001 - a failing action must not stop the run
        _LOGGER.error("timeline[%s] %s failed: %s", item.index, item.action, err)
        rt.event(
            "action", {"index": item.index, "action": item.action, "args": item.args, "ok": False, "error": str(err)}
        )


async def run_action(rt: SimRuntime, action: str, args: dict[str, Any]) -> Any:
    hass = rt.hass
    now = time.time()
    if action in World.WORLD_ACTIONS:
        try:
            touched = rt.world.apply_action(action, args, now)
        except WorldError as err:
            raise ValueError(str(err)) from err
        rt.write_states(touched)
        return sorted(touched)
    if action == "mark":
        rt.event("mark", {"label": args["label"]})
        return None
    if action == "roommind.ws":
        if rt.bridge is None:
            raise RuntimeError("WS bridge not ready (HA not started yet)")
        payload = {k: v for k, v in args.items() if k != "type"}
        return await rt.bridge.call(args["type"], payload)
    if action == "ha.service":
        domain, service = args["service"].split(".", 1)
        data = args.get("data") or {}
        response = args.get("response", False)
        return await hass.services.async_call(domain, service, data, blocking=True, return_response=response)
    if action == "roommind.reload":
        entries = hass.config_entries.async_entries("roommind")
        for entry in entries:
            await hass.config_entries.async_reload(entry.entry_id)
        return len(entries)
    if action == "ha.restart":
        rt.event("ha", {"what": "restart_requested"})
        await rt.async_persist()
        hass.async_create_task(hass.services.async_call("homeassistant", "restart", {}, blocking=False))
        return None
    if action == "entity.remove":
        eid = args["entity_id"]
        rt.removed.add(eid)
        reg = er.async_get(hass)
        if reg.async_get(eid) is not None:
            reg.async_remove(eid)
        hass.states.async_remove(eid)
        return eid
    if action in ("clock.speed", "clock.pause", "clock.realtime"):
        clk = clockmod.CLOCK
        if clk is None:
            raise RuntimeError("no virtual clock installed")
        if action == "clock.pause":
            clk.set_mode(clockmod.PAUSED)
        elif action == "clock.realtime":
            clk.set_mode(clockmod.SCALED, 1.0)
        else:
            clk.set_mode(clockmod.SCALED, float(args["factor"]))
        return clk.state()
    raise ValueError(f"unknown action {action!r}")
