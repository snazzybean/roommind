"""The compressor min-run hold passes on a deliberately changed target (#436)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import UnitOfTemperature

from custom_components.roommind.const import MODE_HEATING, MODE_IDLE, TargetTemps
from custom_components.roommind.control.mpc_controller import MPCController
from custom_components.roommind.control.thermal_model import RoomModelManager
from custom_components.roommind.managers.heat_source_orchestrator import DeviceCommand, HeatSourcePlan

from .conftest import build_hass, make_room

AC = "climate.ac"
HELD = {AC}
COMFORT = TargetTemps(heat=21.0, cool=27.0)


def _state(hvac="heat", **attrs):
    state = MagicMock()
    state.state = hvac
    state.attributes = {
        "hvac_modes": ["heat_cool", "heat", "cool", "off"],
        "min_temp": 16.0,
        "max_temp": 30.0,
        "temperature": 29.5,
        **attrs,
    }
    return state


def _setup(state, *, room=None, fahrenheit=False):
    hass = build_hass()
    if fahrenheit:
        hass.config.units.temperature_unit = UnitOfTemperature.FAHRENHEIT
    hass.states.get = MagicMock(return_value=state)
    ctrl = MPCController(
        hass,
        room or make_room(thermostats=[], acs=[AC]),
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    return hass, ctrl


def _sent(hass):
    return [c[0][2] for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]


async def _start_then_hold(hass, ctrl, held_targets, *, current_temp=22.5, started_with=COMFORT):
    """Heat with *started_with*, then hold for min-run with *held_targets*; returns what the hold sent."""
    await ctrl.async_apply(MODE_HEATING, started_with, power_fraction=1.0, current_temp=19.0)
    hass.services.async_call.reset_mock()
    await ctrl.async_apply(MODE_IDLE, held_targets, current_temp=current_temp, compressor_forced_on=HELD)
    return _sent(hass)


@pytest.mark.asyncio
async def test_unchanged_target_sends_nothing():
    hass, ctrl = _setup(_state())
    assert await _start_then_hold(hass, ctrl, COMFORT) == []


@pytest.mark.asyncio
async def test_without_an_active_command_on_record_sends_nothing():
    """After a reload the previous target is unknown: stay silent, as for a reached target."""
    hass, ctrl = _setup(_state())
    await ctrl.async_apply(MODE_IDLE, TargetTemps(heat=17.0, cool=27.0), current_temp=19.5, compressor_forced_on=HELD)
    assert _sent(hass) == []


@pytest.mark.asyncio
async def test_lowered_heat_target_is_sent_without_hvac_mode():
    hass, ctrl = _setup(_state())
    (call,) = await _start_then_hold(hass, ctrl, TargetTemps(heat=17.0, cool=27.0), current_temp=19.5)
    assert call["temperature"] == 17.0
    assert "hvac_mode" not in call
    assert [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_hvac_mode"] == []


@pytest.mark.asyncio
async def test_change_is_sent_once_while_the_hold_continues():
    hass, ctrl = _setup(_state())
    lowered = TargetTemps(heat=17.0, cool=27.0)
    assert len(await _start_then_hold(hass, ctrl, lowered, current_temp=19.5)) == 1
    hass.services.async_call.reset_mock()
    # the next cycle still holds and the device still reports its boost setpoint: nothing new to say
    await ctrl.async_apply(MODE_IDLE, lowered, current_temp=19.5, compressor_forced_on=HELD)
    assert _sent(hass) == []


@pytest.mark.asyncio
async def test_float_noise_is_not_a_change():
    hass, ctrl = _setup(_state())
    assert await _start_then_hold(hass, ctrl, TargetTemps(heat=21.01, cool=27.0)) == []


@pytest.mark.asyncio
async def test_other_side_changing_does_not_drop_a_heating_unit():
    """Editing the cooling target while the unit heats must not send the heating target (#436)."""
    hass, ctrl = _setup(_state("heat"))
    assert await _start_then_hold(hass, ctrl, TargetTemps(heat=21.0, cool=25.0)) == []


@pytest.mark.asyncio
async def test_cooling_unit_follows_the_cool_side_only():
    hass, ctrl = _setup(_state("cool", temperature=16.0))
    assert await _start_then_hold(hass, ctrl, TargetTemps(heat=17.0, cool=27.0)) == []
    hass.services.async_call.reset_mock()
    await ctrl.async_apply(MODE_IDLE, TargetTemps(heat=17.0, cool=29.0), current_temp=28.0, compressor_forced_on=HELD)
    assert [c["temperature"] for c in _sent(hass)] == [29.0]


@pytest.mark.asyncio
async def test_mold_prevention_raise_counts_as_a_change():
    """The delta is stepped and has hysteresis, so it is passed on like any other change."""
    hass, ctrl = _setup(_state())
    (call,) = await _start_then_hold(hass, ctrl, TargetTemps(heat=22.0, cool=27.0), current_temp=22.5)
    assert call["temperature"] == 22.0


@pytest.mark.asyncio
@pytest.mark.parametrize("hvac", ["off", "fan_only", "dry", "unknown"])
async def test_device_not_heating_or_cooling_is_left_alone(hvac):
    hass, ctrl = _setup(_state(hvac))
    assert await _start_then_hold(hass, ctrl, TargetTemps(heat=17.0, cool=27.0), current_temp=19.5) == []


@pytest.mark.asyncio
async def test_device_without_state_is_left_alone():
    hass, ctrl = _setup(None)
    assert await _start_then_hold(hass, ctrl, TargetTemps(heat=17.0, cool=27.0), current_temp=19.5) == []


@pytest.mark.asyncio
async def test_target_removed_on_the_regulated_side_sends_nothing():
    hass, ctrl = _setup(_state("heat"))
    assert await _start_then_hold(hass, ctrl, TargetTemps(heat=None, cool=27.0)) == []


@pytest.mark.asyncio
async def test_direct_device_gets_target_plus_offset():
    room = make_room(thermostats=[], acs=[AC])
    room["devices"][0].update(setpoint_mode="direct", setpoint_offset=1.0)
    hass, ctrl = _setup(_state(), room=room)
    (call,) = await _start_then_hold(hass, ctrl, TargetTemps(heat=17.0, cool=27.0), current_temp=19.5)
    assert call["temperature"] == 18.0


@pytest.mark.asyncio
async def test_value_is_clamped_to_the_device_limits():
    hass, ctrl = _setup(_state(min_temp=16.0))
    (call,) = await _start_then_hold(hass, ctrl, TargetTemps(heat=15.0, cool=27.0), current_temp=19.5)
    assert call["temperature"] == 16.0


@pytest.mark.asyncio
async def test_managed_mode_records_the_target_of_the_active_command():
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_state("heat"))
    ctrl = MPCController(
        hass,
        make_room(thermostats=[], acs=[AC], climate_mode="auto"),
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )
    (call,) = await _start_then_hold(hass, ctrl, TargetTemps(heat=17.0, cool=27.0), current_temp=19.5)
    assert call["temperature"] == 17.0


@pytest.mark.asyncio
async def test_cooling_records_the_target_of_the_active_command():
    hass, ctrl = _setup(_state("cool", temperature=16.0))
    await ctrl.async_apply("cooling", COMFORT, power_fraction=1.0, current_temp=29.0)
    hass.services.async_call.reset_mock()
    await ctrl.async_apply(MODE_IDLE, TargetTemps(heat=21.0, cool=29.0), current_temp=28.0, compressor_forced_on=HELD)
    assert [c["temperature"] for c in _sent(hass)] == [29.0]


# --- past the far side of the band: no boost into the other mode -------------------


@pytest.mark.asyncio
async def test_heating_hold_ends_once_the_room_reaches_the_cool_target():
    """Band 21/22.5, room at 22.6: the boost would flip the unit to cooling after the min-run."""
    hass, ctrl = _setup(_state("heat"))
    band = TargetTemps(heat=21.0, cool=22.5)
    (call,) = await _start_then_hold(hass, ctrl, band, current_temp=22.6, started_with=band)
    assert call["temperature"] == 21.0
    assert "hvac_mode" not in call


@pytest.mark.asyncio
async def test_heating_hold_keeps_the_boost_inside_the_band():
    hass, ctrl = _setup(_state("heat"))
    band = TargetTemps(heat=21.0, cool=22.5)
    assert await _start_then_hold(hass, ctrl, band, current_temp=22.4, started_with=band) == []


@pytest.mark.asyncio
async def test_heating_hold_overshoot_is_sent_once():
    hass, ctrl = _setup(_state("heat"))
    band = TargetTemps(heat=21.0, cool=22.5)
    assert len(await _start_then_hold(hass, ctrl, band, current_temp=22.6, started_with=band)) == 1
    hass.services.async_call.reset_mock()
    hass.states.get = MagicMock(return_value=_state("heat", temperature=21.0))
    await ctrl.async_apply(MODE_IDLE, band, current_temp=22.8, compressor_forced_on=HELD)
    assert _sent(hass) == []


@pytest.mark.asyncio
async def test_cooling_hold_ends_once_the_room_reaches_the_heat_target():
    hass, ctrl = _setup(_state("cool", temperature=16.0))
    band = TargetTemps(heat=21.0, cool=22.5)
    await ctrl.async_apply("cooling", band, power_fraction=1.0, current_temp=24.0)
    hass.services.async_call.reset_mock()
    await ctrl.async_apply(MODE_IDLE, band, current_temp=20.9, compressor_forced_on=HELD)
    assert [c["temperature"] for c in _sent(hass)] == [22.5]


@pytest.mark.asyncio
async def test_heat_only_room_never_cares_about_the_cool_target():
    room = make_room(thermostats=[], acs=[AC], climate_mode="heat_only")
    hass, ctrl = _setup(_state("heat"), room=room)
    band = TargetTemps(heat=21.0, cool=22.5)
    assert await _start_then_hold(hass, ctrl, band, current_temp=23.0, started_with=band) == []


@pytest.mark.asyncio
async def test_cool_only_room_never_cares_about_the_heat_target():
    room = make_room(thermostats=[], acs=[AC], climate_mode="cool_only")
    hass, ctrl = _setup(_state("cool", temperature=16.0), room=room)
    band = TargetTemps(heat=21.0, cool=24.0)
    await ctrl.async_apply("cooling", band, power_fraction=1.0, current_temp=26.0)
    hass.services.async_call.reset_mock()
    await ctrl.async_apply(MODE_IDLE, band, current_temp=20.0, compressor_forced_on=HELD)
    assert _sent(hass) == []


# --- heat_cool / auto: never a single value of the wrong side (#284) ---------------


@pytest.mark.asyncio
@pytest.mark.parametrize("hvac", ["heat_cool", "auto"])
async def test_single_setpoint_inside_the_new_band_sends_nothing(hvac):
    """Eco band 17-27, room at 21: a single 17 would cool the room."""
    hass, ctrl = _setup(_state(hvac))
    assert await _start_then_hold(hass, ctrl, TargetTemps(heat=17.0, cool=27.0), current_temp=21.0) == []


@pytest.mark.asyncio
async def test_single_setpoint_below_the_new_heat_target_sends_it():
    hass, ctrl = _setup(_state("heat_cool"))
    (call,) = await _start_then_hold(hass, ctrl, TargetTemps(heat=23.0, cool=27.0), current_temp=20.0)
    assert call["temperature"] == 23.0


@pytest.mark.asyncio
async def test_single_setpoint_above_the_new_cool_target_sends_it():
    hass, ctrl = _setup(_state("heat_cool", temperature=16.0))
    (call,) = await _start_then_hold(hass, ctrl, TargetTemps(heat=17.0, cool=25.0), current_temp=26.0)
    assert call["temperature"] == 25.0


@pytest.mark.asyncio
async def test_single_setpoint_without_room_temp_sends_nothing():
    hass, ctrl = _setup(_state("heat_cool"))
    assert await _start_then_hold(hass, ctrl, TargetTemps(heat=17.0, cool=27.0), current_temp=None) == []


@pytest.mark.asyncio
async def test_range_device_gets_the_band():
    hass, ctrl = _setup(_state("heat_cool", target_temp_low=20.0, target_temp_high=24.0))
    (call,) = await _start_then_hold(hass, ctrl, TargetTemps(heat=17.0, cool=26.0), current_temp=21.0)
    assert (call["target_temp_low"], call["target_temp_high"]) == (17.0, 26.0)
    assert "temperature" not in call


@pytest.mark.asyncio
async def test_range_device_parks_a_missing_side_on_its_limit():
    hass, ctrl = _setup(_state("heat_cool", target_temp_low=20.0, target_temp_high=24.0))
    (call,) = await _start_then_hold(hass, ctrl, TargetTemps(heat=17.0, cool=None), current_temp=21.0)
    assert (call["target_temp_low"], call["target_temp_high"]) == (17.0, 30.0)


@pytest.mark.asyncio
async def test_range_device_in_fahrenheit_mixes_no_units():
    """A °F device limit next to a °C target must be compared in °F (86 °F max, 17 °C = 62.6 °F)."""
    hass, ctrl = _setup(
        _state("heat_cool", target_temp_low=68.0, target_temp_high=75.0, min_temp=61.0, max_temp=86.0),
        fahrenheit=True,
    )
    (call,) = await _start_then_hold(hass, ctrl, TargetTemps(heat=17.0, cool=None), current_temp=21.0)
    assert call["target_temp_low"] == pytest.approx(62.6)
    assert call["target_temp_high"] == 86.0


@pytest.mark.asyncio
async def test_range_device_without_the_limit_it_needs_sends_nothing():
    state = _state("heat_cool", target_temp_low=20.0, target_temp_high=24.0)
    del state.attributes["min_temp"]
    hass, ctrl = _setup(state)
    assert await _start_then_hold(hass, ctrl, TargetTemps(heat=None, cool=26.0), current_temp=21.0) == []


# --- orchestrated branch: AC parked by the heat-source plan ---------------------------


def _parked_plan():
    return HeatSourcePlan(
        commands=[DeviceCommand(AC, "primary", "ac", False, 0.0, "test")], active_sources="none", reason="test"
    )


def _active_plan():
    return HeatSourcePlan(
        commands=[DeviceCommand(AC, "primary", "ac", True, 1.0, "test")], active_sources="primary", reason="test"
    )


async def _orchestrated(hass, ctrl, held_targets):
    await ctrl.async_apply(
        MODE_HEATING, COMFORT, power_fraction=1.0, current_temp=19.0, heat_source_plan=_active_plan()
    )
    hass.services.async_call.reset_mock()
    await ctrl.async_apply(
        MODE_HEATING,
        held_targets,
        power_fraction=1.0,
        current_temp=19.5,
        heat_source_plan=_parked_plan(),
        compressor_forced_on=HELD,
    )
    return hass.services.async_call.call_args_list


@pytest.mark.asyncio
async def test_orchestrated_parked_ac_follows_a_changed_target():
    hass, ctrl = _setup(_state("heat"))
    calls = await _orchestrated(hass, ctrl, TargetTemps(heat=17.0, cool=27.0))
    assert [(c[0][1], c[0][2].get("temperature"), c[0][2].get("hvac_mode")) for c in calls] == [
        ("set_temperature", 17.0, None)
    ]


@pytest.mark.asyncio
async def test_orchestrated_parked_ac_with_an_unchanged_target_gets_nothing():
    hass, ctrl = _setup(_state("heat"))
    assert await _orchestrated(hass, ctrl, COMFORT) == []


@pytest.mark.asyncio
async def test_orchestrated_parked_ac_reporting_off_is_not_switched_on_again():
    hass, ctrl = _setup(_state("off"))
    assert await _orchestrated(hass, ctrl, TargetTemps(heat=17.0, cool=27.0)) == []
