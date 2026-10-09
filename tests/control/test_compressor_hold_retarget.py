"""The compressor min-run hold passes on a deliberately changed target (#436)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import UnitOfTemperature

from custom_components.roommind.const import MODE_HEATING, MODE_IDLE, TargetTemps
from custom_components.roommind.control.mpc_controller import MPCController, _active_targets
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


async def _run_active(hass, ctrl, mode, targets, **kwargs):
    """An active cycle whose command really goes out: the device does not report the setpoint yet."""
    state = hass.states.get(AC)
    shown = None if state is None else state.attributes.get("temperature")
    if state is not None:
        state.attributes["temperature"] = None
    try:
        await ctrl.async_apply(mode, targets, power_fraction=1.0, **kwargs)
    finally:
        if state is not None:
            state.attributes["temperature"] = shown


async def _start_then_hold(hass, ctrl, held_targets, *, current_temp=22.5, started_with=COMFORT):
    """Heat with *started_with*, then hold for min-run with *held_targets*; returns what the hold sent."""
    await _run_active(hass, ctrl, MODE_HEATING, started_with, current_temp=19.0)
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
async def test_mold_prevention_drop_counts_as_a_change():
    """The delta is stepped and has hysteresis, so its removal is passed on like any other lowered target."""
    hass, ctrl = _setup(_state())
    raised = TargetTemps(heat=22.0, cool=27.0)
    (call,) = await _start_then_hold(hass, ctrl, COMFORT, current_temp=22.5, started_with=raised)
    assert call["temperature"] == 21.0


@pytest.mark.asyncio
async def test_raised_heating_target_is_not_sent_when_the_room_arrives():
    """Target 21 -> 22 while the unit heats on a saturated boost: sending 22.0 at 22.2 would stop it at once (#436)."""
    hass, ctrl = _setup(_state())
    assert await _start_then_hold(hass, ctrl, TargetTemps(heat=22.0, cool=27.0), current_temp=22.2) == []


@pytest.mark.asyncio
async def test_raised_cooling_target_counts_for_a_cooling_unit_and_a_lowered_one_does_not():
    hass, ctrl = _setup(_state("cool", temperature=16.0))
    await _run_active(hass, ctrl, "cooling", COMFORT, current_temp=29.0)
    hass.services.async_call.reset_mock()
    await ctrl.async_apply(MODE_IDLE, TargetTemps(heat=21.0, cool=26.0), current_temp=25.0, compressor_forced_on=HELD)
    assert _sent(hass) == []
    await ctrl.async_apply(MODE_IDLE, TargetTemps(heat=21.0, cool=29.0), current_temp=25.0, compressor_forced_on=HELD)
    assert [c["temperature"] for c in _sent(hass)] == [29.0]


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
    await _run_active(hass, ctrl, "cooling", COMFORT, current_temp=29.0)
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
@pytest.mark.parametrize(
    ("room_temp", "sends"), [(21.0, False), (21.2, False), (21.4, False), (21.5, True), (22.0, True)]
)
async def test_single_point_target_needs_the_margin_before_the_heating_hold_ends(room_temp, sends):
    """heat == cool (schedule block with one temperature): reaching the target is not an overshoot (#436)."""
    hass, ctrl = _setup(_state("heat"))
    point = TargetTemps(heat=21.0, cool=21.0)
    calls = await _start_then_hold(hass, ctrl, point, current_temp=room_temp, started_with=point)
    assert [c["temperature"] for c in calls] == ([21.0] if sends else [])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("room_temp", "sends"), [(21.0, False), (20.8, False), (20.6, False), (20.5, True), (20.0, True)]
)
async def test_single_point_target_needs_the_margin_before_the_cooling_hold_ends(room_temp, sends):
    hass, ctrl = _setup(_state("cool", temperature=16.0))
    point = TargetTemps(heat=21.0, cool=21.0)
    await _run_active(hass, ctrl, "cooling", point, current_temp=24.0)
    hass.services.async_call.reset_mock()
    await ctrl.async_apply(MODE_IDLE, point, current_temp=room_temp, compressor_forced_on=HELD)
    assert [c["temperature"] for c in _sent(hass)] == ([21.0] if sends else [])


@pytest.mark.asyncio
async def test_band_wider_than_the_margin_still_ends_at_the_cool_target():
    hass, ctrl = _setup(_state("heat"))
    band = TargetTemps(heat=21.0, cool=22.5)
    assert await _start_then_hold(hass, ctrl, band, current_temp=22.4, started_with=band) == []
    hass.services.async_call.reset_mock()
    await ctrl.async_apply(MODE_IDLE, band, current_temp=22.5, compressor_forced_on=HELD)
    assert [c["temperature"] for c in _sent(hass)] == [21.0]


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
    await _run_active(hass, ctrl, "cooling", band, current_temp=24.0)
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
    await _run_active(hass, ctrl, "cooling", band, current_temp=26.0)
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
@pytest.mark.parametrize("hvac", ["heat_cool", "auto"])
@pytest.mark.parametrize(("later_temp", "expected"), [(16.5, 17.0), (27.5, 27.0)])
async def test_unsent_change_stays_pending_for_a_single_setpoint_device(hvac, later_temp, expected):
    """Eco 17/27 with the room inside: nothing can be sent yet, but the change must not count as delivered (#436)."""
    hass, ctrl = _setup(_state(hvac))
    eco = TargetTemps(heat=17.0, cool=27.0)
    assert await _start_then_hold(hass, ctrl, eco, current_temp=21.5) == []
    hass.services.async_call.reset_mock()
    await ctrl.async_apply(MODE_IDLE, eco, current_temp=later_temp, compressor_forced_on=HELD)
    assert [c["temperature"] for c in _sent(hass)] == [expected]


@pytest.mark.asyncio
async def test_delivered_single_setpoint_change_is_not_sent_twice():
    hass, ctrl = _setup(_state("heat_cool"))
    eco = TargetTemps(heat=17.0, cool=27.0)
    assert len(await _start_then_hold(hass, ctrl, eco, current_temp=16.5)) == 1
    hass.services.async_call.reset_mock()
    hass.states.get = MagicMock(return_value=_state("heat_cool", temperature=17.0))
    await ctrl.async_apply(MODE_IDLE, eco, current_temp=16.4, compressor_forced_on=HELD)
    assert _sent(hass) == []


@pytest.mark.asyncio
async def test_single_setpoint_below_the_lowered_heat_target_sends_it():
    hass, ctrl = _setup(_state("heat_cool"))
    (call,) = await _start_then_hold(hass, ctrl, TargetTemps(heat=19.0, cool=27.0), current_temp=18.5)
    assert call["temperature"] == 19.0


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
    await _run_active(hass, ctrl, MODE_HEATING, COMFORT, current_temp=19.0, heat_source_plan=_active_plan())
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


# --- the reference moves only with a command that really went out (R2b) -----------------


@pytest.mark.asyncio
async def test_target_change_during_active_cycles_still_reaches_the_hold():
    """Eco arrives while the unit still heats on its boost: no command goes out, so the hold must still send it."""
    hass, ctrl = _setup(_state("heat"))
    eco = TargetTemps(heat=17.0, cool=27.0)
    await _run_active(hass, ctrl, MODE_HEATING, COMFORT, current_temp=19.0)
    hass.services.async_call.reset_mock()
    # unit already shows its boost setpoint, so the active cycle with the new target sends nothing
    await ctrl.async_apply(MODE_HEATING, eco, power_fraction=1.0, current_temp=19.0)
    assert _sent(hass) == []

    await ctrl.async_apply(MODE_IDLE, eco, current_temp=19.5, compressor_forced_on=HELD)
    assert [c["temperature"] for c in _sent(hass)] == [17.0]
    hass.services.async_call.reset_mock()
    hass.states.get = MagicMock(return_value=_state("heat", temperature=17.0))
    await ctrl.async_apply(MODE_IDLE, eco, current_temp=19.4, compressor_forced_on=HELD)
    assert _sent(hass) == []


@pytest.mark.asyncio
async def test_cool_side_change_during_active_cycles_still_reaches_the_hold():
    hass, ctrl = _setup(_state("cool", temperature=16.0))
    eco = TargetTemps(heat=17.0, cool=29.0)
    await _run_active(hass, ctrl, "cooling", COMFORT, current_temp=28.0)
    hass.services.async_call.reset_mock()
    await ctrl.async_apply("cooling", eco, power_fraction=1.0, current_temp=28.0)
    await ctrl.async_apply(MODE_IDLE, eco, current_temp=28.0, compressor_forced_on=HELD)
    assert [c["temperature"] for c in _sent(hass)] == [29.0]


@pytest.mark.asyncio
async def test_failed_send_does_not_move_the_reference():
    hass, ctrl = _setup(_state("heat"))
    hass.services.async_call.side_effect = RuntimeError("device offline")
    await _run_active(hass, ctrl, MODE_HEATING, COMFORT, current_temp=19.0)
    assert AC not in _active_targets


@pytest.mark.asyncio
async def test_failed_hold_send_is_retried_once_per_cycle():
    """Like before the hold: one attempt per cycle while it fails, a single send once it works."""
    hass, ctrl = _setup(_state("heat"))
    eco = TargetTemps(heat=17.0, cool=27.0)
    await _run_active(hass, ctrl, MODE_HEATING, COMFORT, current_temp=19.0)
    hass.services.async_call.reset_mock()
    hass.services.async_call.side_effect = RuntimeError("device offline")
    attempts = []
    for _ in range(3):
        hass.services.async_call.reset_mock()
        await ctrl.async_apply(MODE_IDLE, eco, current_temp=19.5, compressor_forced_on=HELD)
        attempts.append(len(_sent(hass)))
    assert attempts == [1, 1, 1]

    hass.services.async_call.side_effect = None
    hass.services.async_call.reset_mock()
    await ctrl.async_apply(MODE_IDLE, eco, current_temp=19.5, compressor_forced_on=HELD)
    assert len(_sent(hass)) == 1
    hass.services.async_call.reset_mock()
    await ctrl.async_apply(MODE_IDLE, eco, current_temp=19.5, compressor_forced_on=HELD)
    assert _sent(hass) == []


@pytest.mark.asyncio
async def test_reference_starts_from_a_running_unit_after_a_reload():
    """The unit already shows its boost when the module state is fresh: confirmed ticks must still seed the reference."""
    hass, ctrl = _setup(_state("heat"))
    eco = TargetTemps(heat=17.0, cool=27.0)
    await ctrl.async_apply(MODE_HEATING, COMFORT, power_fraction=1.0, current_temp=19.0)
    assert _sent(hass) == []
    await ctrl.async_apply(MODE_IDLE, COMFORT, current_temp=22.0, compressor_forced_on=HELD)
    assert _sent(hass) == []
    await ctrl.async_apply(MODE_IDLE, eco, current_temp=19.5, compressor_forced_on=HELD)
    assert [c["temperature"] for c in _sent(hass)] == [17.0]


@pytest.mark.asyncio
async def test_seeding_never_replaces_a_remembered_reference():
    hass, ctrl = _setup(_state("heat"))
    eco = TargetTemps(heat=17.0, cool=27.0)
    await _run_active(hass, ctrl, MODE_HEATING, COMFORT, current_temp=19.0)
    await ctrl.async_apply(MODE_HEATING, eco, power_fraction=1.0, current_temp=19.0)  # confirmed, not sent
    assert _active_targets[AC] == (21.0, 27.0)


# --- reload in the middle of the hold (K5) and the once-per-hold overshoot send (K7) ----


@pytest.mark.asyncio
async def test_reload_in_the_middle_of_the_hold_seeds_the_reference_then_follows_eco():
    hass, ctrl = _setup(_state("heat"))
    eco = TargetTemps(heat=17.0, cool=27.0)
    await ctrl.async_apply(MODE_IDLE, COMFORT, current_temp=22.0, compressor_forced_on=HELD)  # nothing remembered
    assert _sent(hass) == []
    await ctrl.async_apply(MODE_IDLE, eco, current_temp=19.5, compressor_forced_on=HELD)
    assert [c["temperature"] for c in _sent(hass)] == [17.0]
    hass.services.async_call.reset_mock()
    await ctrl.async_apply(MODE_IDLE, eco, current_temp=19.5, compressor_forced_on=HELD)
    assert _sent(hass) == []


@pytest.mark.asyncio
async def test_overshoot_is_sent_once_per_hold_for_a_device_that_does_not_take_it():
    hass, ctrl = _setup(_state("heat"))  # the state never changes: the unit does not confirm
    band = TargetTemps(heat=21.0, cool=22.5)
    await _run_active(hass, ctrl, MODE_HEATING, band, current_temp=19.0)
    counts = []
    for _ in range(4):
        hass.services.async_call.reset_mock()
        await ctrl.async_apply(MODE_IDLE, band, current_temp=22.8, compressor_forced_on=HELD)
        counts.append(len(_sent(hass)))
    assert counts == [1, 0, 0, 0]


@pytest.mark.asyncio
async def test_overshoot_may_be_sent_again_in_the_next_hold():
    hass, ctrl = _setup(_state("heat"))
    band = TargetTemps(heat=21.0, cool=22.5)
    await _run_active(hass, ctrl, MODE_HEATING, band, current_temp=19.0)
    await ctrl.async_apply(MODE_IDLE, band, current_temp=22.8, compressor_forced_on=HELD)
    # the unit is driven again, then held again
    await _run_active(hass, ctrl, MODE_HEATING, band, current_temp=19.0)
    hass.services.async_call.reset_mock()
    await ctrl.async_apply(MODE_IDLE, band, current_temp=22.8, compressor_forced_on=HELD)
    assert len(_sent(hass)) == 1


@pytest.mark.asyncio
async def test_failed_overshoot_send_is_retried_once_per_cycle():
    hass, ctrl = _setup(_state("heat"))
    band = TargetTemps(heat=21.0, cool=22.5)
    await _run_active(hass, ctrl, MODE_HEATING, band, current_temp=19.0)
    hass.services.async_call.side_effect = RuntimeError("device offline")
    for _ in range(3):
        hass.services.async_call.reset_mock()
        await ctrl.async_apply(MODE_IDLE, band, current_temp=22.8, compressor_forced_on=HELD)
        assert len(_sent(hass)) == 1
    hass.services.async_call.side_effect = None
    hass.services.async_call.reset_mock()
    await ctrl.async_apply(MODE_IDLE, band, current_temp=22.8, compressor_forced_on=HELD)
    assert len(_sent(hass)) == 1
    hass.services.async_call.reset_mock()
    await ctrl.async_apply(MODE_IDLE, band, current_temp=22.8, compressor_forced_on=HELD)
    assert _sent(hass) == []
