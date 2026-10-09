"""Heating boost setpoints must stay strictly below a device's max_temp (#396)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import UnitOfTemperature

from custom_components.roommind.const import TargetTemps
from custom_components.roommind.control.mpc_controller import (
    MODE_HEATING,
    MPCController,
    _last_commands,
)
from custom_components.roommind.control.thermal_model import RoomModelManager
from custom_components.roommind.managers.heat_source_orchestrator import DeviceCommand, HeatSourcePlan

from .conftest import build_hass, make_room


def _state(max_temp, *, min_temp=1.0, step=1.0, modes=("heat", "fan_only", "off")):
    state = MagicMock()
    state.state = "off"
    state.attributes = {
        "hvac_modes": list(modes),
        "min_temp": min_temp,
        "max_temp": max_temp,
        "target_temp_step": step,
        "temperature": 20.0,
    }
    return state


def _controller(hass, room):
    return MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=0.0,
        settings={},
        has_external_sensor=True,
    )


def _sent(hass, eid):
    return [
        c[0][2]["temperature"]
        for c in hass.services.async_call.call_args_list
        if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == eid
    ]


@pytest.mark.asyncio
async def test_trv_boost_stays_below_max_temp_by_one_step():
    """A device at max_temp=37 / step 1 gets 36, not the rejected 37.0 (#396)."""
    _last_commands.clear()
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_state(37.0))
    ctrl = _controller(hass, make_room(thermostats=["climate.purifier"]))

    await ctrl.async_apply(
        MODE_HEATING,
        TargetTemps(heat=21.0, cool=None),
        power_fraction=1.0,
        current_temp=15.0,
        heating_boost_target=37.0,
    )

    assert _sent(hass, "climate.purifier") == [36.0]


@pytest.mark.asyncio
async def test_boost_cap_uses_half_degree_without_step_attribute():
    _last_commands.clear()
    hass = build_hass()
    state = _state(37.0)
    del state.attributes["target_temp_step"]
    hass.states.get = MagicMock(return_value=state)
    ctrl = _controller(hass, make_room(thermostats=["climate.purifier"]))

    await ctrl.async_apply(
        MODE_HEATING,
        TargetTemps(heat=21.0, cool=None),
        power_fraction=1.0,
        current_temp=15.0,
        heating_boost_target=37.0,
    )

    assert _sent(hass, "climate.purifier") == [36.5]


@pytest.mark.asyncio
async def test_boost_cap_never_drops_below_target():
    """A target at the top of the device range is not pushed below itself."""
    _last_commands.clear()
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_state(30.0))
    ctrl = _controller(hass, make_room(thermostats=["climate.trv"]))

    await ctrl.async_apply(
        MODE_HEATING,
        TargetTemps(heat=30.0, cool=None),
        power_fraction=1.0,
        current_temp=25.0,
        heating_boost_target=30.0,
    )

    assert _sent(hass, "climate.trv") == [30.0]


@pytest.mark.asyncio
async def test_ac_boost_stays_below_max_temp():
    _last_commands.clear()
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_state(30.0, min_temp=16.0, modes=("heat", "cool", "off")))
    ctrl = _controller(hass, make_room(thermostats=[], acs=["climate.ac"]))

    await ctrl.async_apply(
        MODE_HEATING,
        TargetTemps(heat=21.0, cool=None),
        power_fraction=1.0,
        current_temp=15.0,
        ac_heating_boost_target=30.0,
    )

    assert _sent(hass, "climate.ac") == [29.0]


@pytest.mark.asyncio
async def test_orchestrated_secondary_thermostat_boost_stays_below_max_temp():
    """Dyson-like heater as secondary source behind an AC (#396)."""
    _last_commands.clear()
    hass = build_hass()
    states = {
        "climate.purifier": _state(37.0),
        "climate.ac": _state(30.0, min_temp=16.0, modes=("heat", "cool", "off")),
    }
    hass.states.get = MagicMock(side_effect=states.get)
    room = make_room(thermostats=["climate.purifier"], acs=["climate.ac"])
    ctrl = _controller(hass, room)
    plan = HeatSourcePlan(
        commands=[
            DeviceCommand("climate.ac", "primary", "ac", True, 1.0, "primary heating"),
            DeviceCommand("climate.purifier", "secondary", "thermostat", True, 1.0, "gap too large"),
        ],
        active_sources="both",
        reason="large gap",
    )

    await ctrl.async_apply(
        MODE_HEATING,
        TargetTemps(heat=21.0, cool=None),
        power_fraction=1.0,
        current_temp=15.0,
        heating_boost_target=37.0,
        ac_heating_boost_target=30.0,
        heat_source_plan=plan,
    )

    assert _sent(hass, "climate.purifier") == [36.0]
    assert _sent(hass, "climate.ac") == [29.0]


@pytest.mark.asyncio
async def test_direct_device_target_is_not_capped():
    """Direct mode sends the real room target; the boost cap does not apply."""
    _last_commands.clear()
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_state(30.0))
    room = make_room(thermostats=["climate.heater"])
    room["devices"][0]["setpoint_mode"] = "direct"
    ctrl = _controller(hass, room)

    await ctrl.async_apply(
        MODE_HEATING,
        TargetTemps(heat=30.0, cool=None),
        power_fraction=1.0,
        current_temp=25.0,
        heating_boost_target=30.0,
    )

    assert _sent(hass, "climate.heater") == [30.0]


@pytest.mark.asyncio
async def test_boost_cap_fahrenheit_uses_ha_units():
    """max_temp / step are in °F; the cap is applied in HA units."""
    _last_commands.clear()
    hass = build_hass()
    hass.config.units.temperature_unit = UnitOfTemperature.FAHRENHEIT
    hass.states.get = MagicMock(return_value=_state(98.6, min_temp=34.0, step=1.0))
    ctrl = _controller(hass, make_room(thermostats=["climate.purifier"]))

    await ctrl.async_apply(
        MODE_HEATING,
        TargetTemps(heat=21.0, cool=None),
        power_fraction=1.0,
        current_temp=15.0,
        heating_boost_target=37.0,
    )

    assert _sent(hass, "climate.purifier") == [98.0]
    assert all(t < 98.6 for t in _sent(hass, "climate.purifier"))


@pytest.mark.asyncio
async def test_boost_cap_zero_step_falls_back_to_half_degree():
    _last_commands.clear()
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_state(37.0, step=0))
    ctrl = _controller(hass, make_room(thermostats=["climate.purifier"]))

    await ctrl.async_apply(
        MODE_HEATING,
        TargetTemps(heat=21.0, cool=None),
        power_fraction=1.0,
        current_temp=15.0,
        heating_boost_target=37.0,
    )

    assert _sent(hass, "climate.purifier") == [36.5]


def test_boost_cap_ignores_unparsable_limits():
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_state("n/a"))
    ctrl = _controller(hass, make_room(thermostats=["climate.trv"]))

    assert ctrl._boost_setpoint_ha("climate.trv", 30.0, 21.0) == 30.0


@pytest.mark.asyncio
async def test_boost_cap_fahrenheit_without_step_survives_whole_degree_snap():
    """Without target_temp_step the cap is 0.5 °C (0.9 °F) and the whole-degree °F snap (#416) stays below max_temp."""
    _last_commands.clear()
    hass = build_hass()
    hass.config.units.temperature_unit = UnitOfTemperature.FAHRENHEIT
    state = _state(86.0, min_temp=34.0)
    del state.attributes["target_temp_step"]
    hass.states.get = MagicMock(return_value=state)
    ctrl = _controller(hass, make_room(thermostats=["climate.purifier"]))

    await ctrl.async_apply(
        MODE_HEATING,
        TargetTemps(heat=21.0, cool=None),
        power_fraction=1.0,
        current_temp=15.0,
        heating_boost_target=30.0,
    )

    sent = _sent(hass, "climate.purifier")
    assert sent
    assert sent[0] == 85.0
