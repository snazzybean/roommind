"""Per-device setpoint offset for direct mode (#369)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import UnitOfTemperature

from custom_components.roommind.const import TargetTemps
from custom_components.roommind.control.mpc_controller import (
    MODE_COOLING,
    MODE_HEATING,
    MPCController,
    _last_commands,
    async_idle_device,
)
from custom_components.roommind.control.thermal_model import RoomModelManager
from custom_components.roommind.managers.heat_source_orchestrator import DeviceCommand, HeatSourcePlan

from .conftest import build_hass, make_room


def _state(*, min_temp=16.0, max_temp=30.0, step=0.5, modes=("heat", "cool", "off"), hvac="heat", temperature=None):
    state = MagicMock()
    state.state = hvac
    state.attributes = {
        "hvac_modes": list(modes),
        "min_temp": min_temp,
        "max_temp": max_temp,
        "target_temp_step": step,
        "temperature": temperature,
    }
    return state


def _room(device_type="ac", *, mode="direct", offset=None, climate_mode="auto", **extra):
    thermostats = ["climate.dev"] if device_type == "trv" else []
    acs = ["climate.dev"] if device_type == "ac" else []
    room = make_room(thermostats=thermostats, acs=acs, climate_mode=climate_mode)
    device = room["devices"][0]
    device["setpoint_mode"] = mode
    if offset is not None:
        device["setpoint_offset"] = offset
    device.update(extra)
    return room


def _controller(hass, room, *, has_external_sensor=True):
    return MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=10.0,
        settings={},
        has_external_sensor=has_external_sensor,
    )


def _sent(hass, eid="climate.dev"):
    return [
        c[0][2]["temperature"]
        for c in hass.services.async_call.call_args_list
        if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == eid
    ]


@pytest.mark.asyncio
async def test_cooling_offset_added_to_target():
    """Device reads 1 K warmer than the room → send target + 1 (#369)."""
    _last_commands.clear()
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_state())
    ctrl = _controller(hass, _room(offset=1.0))

    await ctrl.async_apply(MODE_COOLING, TargetTemps(heat=None, cool=24.0), power_fraction=1.0, current_temp=27.0)

    assert _sent(hass) == [25.0]


@pytest.mark.asyncio
async def test_cooling_negative_offset():
    _last_commands.clear()
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_state())
    ctrl = _controller(hass, _room(offset=-2.0))

    await ctrl.async_apply(MODE_COOLING, TargetTemps(heat=None, cool=24.0), power_fraction=1.0, current_temp=27.0)

    assert _sent(hass) == [22.0]


@pytest.mark.asyncio
async def test_heating_ac_offset_added_to_target():
    _last_commands.clear()
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_state())
    ctrl = _controller(hass, _room(offset=2.0))

    await ctrl.async_apply(MODE_HEATING, TargetTemps(heat=21.0, cool=None), power_fraction=1.0, current_temp=18.0)

    assert _sent(hass) == [23.0]


@pytest.mark.asyncio
async def test_heating_trv_offset_added_to_target():
    _last_commands.clear()
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_state(min_temp=5.0, modes=("heat", "off")))
    ctrl = _controller(hass, _room("trv", offset=-1.5))

    await ctrl.async_apply(MODE_HEATING, TargetTemps(heat=21.0, cool=None), power_fraction=1.0, current_temp=18.0)

    assert _sent(hass) == [19.5]


@pytest.mark.asyncio
async def test_default_offset_keeps_old_behaviour():
    _last_commands.clear()
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_state())
    ctrl = _controller(hass, _room())

    await ctrl.async_apply(MODE_COOLING, TargetTemps(heat=None, cool=24.0), power_fraction=1.0, current_temp=27.0)

    assert _sent(hass) == [24.0]


@pytest.mark.asyncio
async def test_offset_ignored_in_proportional_mode():
    _last_commands.clear()
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_state())
    ctrl = _controller(hass, _room(mode="proportional", offset=3.0))

    await ctrl.async_apply(MODE_COOLING, TargetTemps(heat=None, cool=24.0), power_fraction=1.0, current_temp=27.0)

    # Full-power proportional cooling heads for the device minimum, no offset involved
    assert _sent(hass) == [16.0]


@pytest.mark.asyncio
async def test_offset_ignored_without_external_sensor():
    """Managed mode has no reference sensor to be offset against."""
    _last_commands.clear()
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_state())
    ctrl = _controller(hass, _room(offset=2.0, climate_mode="cool_only"), has_external_sensor=False)

    await ctrl.async_apply(MODE_COOLING, TargetTemps(heat=None, cool=24.0), power_fraction=1.0, current_temp=None)

    assert _sent(hass) == [24.0]


@pytest.mark.asyncio
async def test_offset_applied_before_clamp():
    """target + offset beyond the device limit is clamped, not sent raw."""
    _last_commands.clear()
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_state(min_temp=16.0))
    ctrl = _controller(hass, _room(offset=-5.0))

    await ctrl.async_apply(MODE_COOLING, TargetTemps(heat=None, cool=18.0), power_fraction=1.0, current_temp=27.0)

    assert _sent(hass) == [16.0]


@pytest.mark.asyncio
async def test_offset_snapped_to_device_step():
    _last_commands.clear()
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_state(step=1.0))
    ctrl = _controller(hass, _room(offset=0.5))

    await ctrl.async_apply(MODE_COOLING, TargetTemps(heat=None, cool=24.2), power_fraction=1.0, current_temp=27.0)

    assert _sent(hass) == [25.0]


@pytest.mark.asyncio
async def test_offset_fahrenheit_converted_from_celsius_delta():
    """Offset is stored in °C; target + offset is converted as one value."""
    _last_commands.clear()
    hass = build_hass()
    hass.config.units.temperature_unit = UnitOfTemperature.FAHRENHEIT
    hass.states.get = MagicMock(return_value=_state(min_temp=60.0, max_temp=86.0, step=0.5))
    ctrl = _controller(hass, _room(offset=1.0))

    await ctrl.async_apply(MODE_COOLING, TargetTemps(heat=None, cool=24.0), power_fraction=1.0, current_temp=27.0)

    # (24 + 1) °C = 77 °F
    assert _sent(hass) == [77.0]


@pytest.mark.asyncio
async def test_orchestrated_direct_devices_get_offset():
    _last_commands.clear()
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_state(min_temp=5.0, modes=("heat", "cool", "off")))
    room = make_room(thermostats=["climate.trv"], acs=["climate.ac"])
    for dev in room["devices"]:
        dev["setpoint_mode"] = "direct"
        dev["setpoint_offset"] = 1.0 if dev["entity_id"] == "climate.ac" else -1.0
    ctrl = _controller(hass, room)
    plan = HeatSourcePlan(
        commands=[
            DeviceCommand("climate.ac", "primary", "ac", True, 1.0, "primary heating"),
            DeviceCommand("climate.trv", "secondary", "thermostat", True, 1.0, "gap too large"),
        ],
        active_sources="both",
        reason="large gap",
    )

    await ctrl.async_apply(
        MODE_HEATING,
        TargetTemps(heat=21.0, cool=None),
        power_fraction=1.0,
        current_temp=15.0,
        heat_source_plan=plan,
    )

    assert _sent(hass, "climate.ac") == [22.0]
    assert _sent(hass, "climate.trv") == [20.0]


@pytest.mark.asyncio
async def test_setback_keeps_offset_for_direct_device():
    _last_commands.clear()
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_state(hvac="cool", step=0.5, temperature=24.0))
    devices = [
        {
            "entity_id": "climate.dev",
            "type": "ac",
            "setpoint_mode": "direct",
            "setpoint_offset": 1.0,
            "idle_action": "setback",
        }
    ]

    await async_idle_device(hass, "climate.dev", devices, targets=TargetTemps(heat=None, cool=24.0))

    # cool target 24 + offset 1 + setback 2 = 27
    assert _sent(hass) == [27.0]
