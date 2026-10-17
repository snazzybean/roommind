"""Idle action "hold": an AC near its target stays in its mode at the target in its own frame."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.roommind.const import MODE_IDLE, TargetTemps
from custom_components.roommind.control.mpc_controller import MPCController, clear_command_cache
from custom_components.roommind.control.thermal_model import RoomModelManager
from custom_components.roommind.managers.head_offset_tracker import HeadOffsetTracker

from .conftest import build_hass, make_room

AC = "climate.ac"
TARGETS = TargetTemps(heat=21.0, cool=24.0)


def _tracker(**offsets: float) -> HeadOffsetTracker:
    tracker = HeadOffsetTracker()
    tracker.load_state({AC: {state: [value, 50] for state, value in offsets.items()}})
    return tracker


def _state(hvac: str, temperature: float = 20.0):
    state = MagicMock()
    state.state = hvac
    state.attributes = {
        "hvac_modes": ["heat", "cool", "off"],
        "min_temp": 16.0,
        "max_temp": 30.0,
        "target_temp_step": 0.5,
        "temperature": temperature,
    }
    return state


async def _idle(hvac: str, current_temp: float, *, tracker=None, idle_action="hold", release=frozenset(), **kwargs):
    clear_command_cache()
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_state(hvac))
    room = make_room(thermostats=[], acs=[AC])
    room["devices"][0]["idle_action"] = idle_action
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=28.0,
        settings={},
        has_external_sensor=True,
        head_offsets=tracker,
    )
    ctrl._setback_release = release
    await ctrl.async_apply(MODE_IDLE, TARGETS, current_temp=current_temp, **kwargs)
    calls = [(c[0][1], c[0][2]) for c in hass.services.async_call.call_args_list]
    return ctrl, calls


def _temps(calls):
    return [data["temperature"] for service, data in calls if service == "set_temperature"]


@pytest.mark.asyncio
async def test_cooling_unit_near_target_holds_at_the_target_in_its_frame():
    ctrl, calls = await _idle("cool", 23.8, tracker=_tracker(cool=1.0, idle=2.0))
    assert _temps(calls) == [25.0]  # target + running offset, not the idle offset
    assert ("set_hvac_mode", {"entity_id": AC, "hvac_mode": "off"}) not in calls
    assert ctrl.held_at_target == {AC}


@pytest.mark.asyncio
async def test_heating_unit_near_target_holds_at_the_target_in_its_frame():
    ctrl, calls = await _idle("heat", 21.3, tracker=_tracker(heat=1.5))
    assert _temps(calls) == [22.5]
    assert ctrl.held_at_target == {AC}


@pytest.mark.asyncio
async def test_room_past_the_hold_band_gets_the_setback():
    ctrl, calls = await _idle("cool", 23.4)
    assert _temps(calls) == [26.0]  # cool target + 2 K, as idle_action "setback"
    assert ctrl.held_at_target == set()


@pytest.mark.asyncio
async def test_hold_does_not_switch_a_unit_on():
    ctrl, calls = await _idle("off", 24.0)
    assert _temps(calls) == []
    assert ctrl.held_at_target == set()


@pytest.mark.asyncio
async def test_no_run_ahead_ends_the_hold_in_off():
    ctrl, calls = await _idle("cool", 24.0, release=frozenset({"cool"}))
    assert ("set_hvac_mode", {"entity_id": AC, "hvac_mode": "off"}) in calls
    assert ctrl.held_at_target == set()


@pytest.mark.asyncio
async def test_force_off_is_not_held():
    ctrl, calls = await _idle("cool", 24.0, force_off=True)
    assert ("set_hvac_mode", {"entity_id": AC, "hvac_mode": "off"}) in calls
    assert ctrl.held_at_target == set()


@pytest.mark.asyncio
async def test_other_idle_actions_are_unchanged():
    ctrl, calls = await _idle("cool", 24.0, idle_action="off")
    assert ("set_hvac_mode", {"entity_id": AC, "hvac_mode": "off"}) in calls
    assert ctrl.held_at_target == set()


@pytest.mark.asyncio
async def test_unit_that_stopped_on_its_own_is_held_in_its_idle_frame():
    """Its sensor reads the warm layer once stopped: the idle offset keeps it from restarting early."""
    clear_command_cache()
    hass = build_hass()
    state = _state("cool")
    state.attributes["hvac_action"] = "idle"
    hass.states.get = MagicMock(return_value=state)
    room = make_room(thermostats=[], acs=[AC])
    room["devices"][0]["idle_action"] = "hold"
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=28.0,
        settings={},
        has_external_sensor=True,
        head_offsets=_tracker(cool=1.0, idle=2.0),
    )
    await ctrl.async_apply(MODE_IDLE, TARGETS, current_temp=23.8)
    sent = [c[0][2]["temperature"] for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert sent == [26.0]
    assert ctrl.held_at_target == {AC}
