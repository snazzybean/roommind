"""simhome: a simulated house for testing RoomMind (see dev/sim/README.md)."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType

from roommind_sim import clock as clockmod

from .actions import run_action
from .const import DOMAIN, PLATFORMS
from .runtime import SimRuntime

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    inst = os.environ.get("ROOMMIND_SIM_INSTANCE_DIR")
    if not inst:
        _LOGGER.error("simhome needs ROOMMIND_SIM_INSTANCE_DIR (start HA through roommind_sim.boot)")
        return False
    runtime = await hass.async_add_executor_job(SimRuntime.load, hass, Path(inst))
    hass.data[DOMAIN] = runtime
    for cmd in (ws_status, ws_clock, ws_action, ws_world):
        websocket_api.async_register_command(hass, cmd)

    async def _started(_event: Any) -> None:
        await runtime.async_ensure_user()
        await runtime.async_provision()
        runtime.schedule_timeline()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _started)
    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, runtime.async_stop)
    if not hass.config_entries.async_entries(DOMAIN):
        hass.async_create_task(hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_IMPORT}, data={}))
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    runtime: SimRuntime = hass.data[DOMAIN]
    runtime.setup_registries()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    runtime.assign_areas()
    runtime.start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _rt(hass: HomeAssistant) -> SimRuntime:
    return hass.data[DOMAIN]


@websocket_api.websocket_command({vol.Required("type"): "simhome/status"})
@callback
def ws_status(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    rt = _rt(hass)
    clk = clockmod.CLOCK
    now = time.time()
    connection.send_result(
        msg["id"],
        {
            "scenario": rt.scn.name,
            "now": now,
            "start": rt.scn.start,
            "elapsed": now - rt.scn.start,
            "duration": rt.scn.duration,
            "clock": clk.state() if clk else None,
            "provisioned": rt.provisioned,
            "timeline_done": sorted(rt.done),
            "timeline_total": len(rt.scn.timeline),
            "real_time": clockmod._real_time(),
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "simhome/clock",
        vol.Optional("mode"): vol.In(list(clockmod.MODES)),
        vol.Optional("factor"): vol.Coerce(float),
        vol.Optional("ff"): vol.Coerce(float),
        vol.Optional("until"): vol.Coerce(float),
        vol.Optional("then"): vol.In(["realtime", "pause", "keep"]),
    }
)
@callback
def ws_clock(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    clk = clockmod.CLOCK
    if clk is None:
        connection.send_error(msg["id"], "no_clock", "virtual clock not installed")
        return
    then_choice = msg.get("then", "keep")
    if then_choice == "keep":
        then = (clk.mode, clk.factor) if clk.mode != clockmod.TURBO else (clockmod.SCALED, 1.0)
    else:
        then = (clockmod.PAUSED, 1.0) if then_choice == "pause" else (clockmod.SCALED, 1.0)
    if "ff" in msg:
        clk.run_until(clk.mono() + msg["ff"], then)
    elif "until" in msg:
        clk.run_until(msg["until"] - clk.epoch_start, then)
    elif "mode" in msg:
        clk.set_mode(msg["mode"], msg.get("factor", 1.0))
    connection.send_result(msg["id"], clk.state())


@websocket_api.websocket_command(
    {vol.Required("type"): "simhome/action", vol.Required("action"): str, vol.Optional("args", default={}): dict}
)
@websocket_api.async_response
async def ws_action(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    rt = _rt(hass)
    try:
        result = await run_action(rt, msg["action"], msg["args"])
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "action_failed", str(err))
        return
    rt.event("action", {"index": None, "action": msg["action"], "args": msg["args"], "ok": True, "source": "cli"})
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): "simhome/world"})
@callback
def ws_world(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    rt = _rt(hass)
    data = rt.world.sample()
    data["counters"] = {e: d.counters.__dict__ for e, d in rt.world.devices.items()}
    data["ground_truth"] = rt.world.ground_truth()
    connection.send_result(msg["id"], data)
