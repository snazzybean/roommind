"""Sent-command cache for devices without a usable state (IR blasters) (#416)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.roommind.const import (
    COMMAND_CACHE_REASSERT_SECONDS,
    MODE_COOLING,
    MODE_HEATING,
    MODE_IDLE,
    TargetTemps,
)
from custom_components.roommind.control.mpc_controller import MPCController
from custom_components.roommind.control.thermal_model import RoomModelManager

from .conftest import build_hass, make_room

AC = "climate.ir_ac"


def _state(state, temperature=None):
    s = MagicMock()
    s.state = state
    s.attributes = {
        "hvac_modes": ["off", "cool", "heat"],
        "min_temp": 16.0,
        "max_temp": 30.0,
        "temperature": temperature,
    }
    return s


def _ctrl(hass):
    return MPCController(
        hass,
        make_room(thermostats=[], acs=[AC]),
        model_manager=RoomModelManager(),
        outdoor_temp=10.0,
        settings={},
        has_external_sensor=True,
    )


def _sent(hass):
    return [
        (c[0][1], c[0][2].get("hvac_mode"), c[0][2].get("temperature")) for c in hass.services.async_call.call_args_list
    ]


async def _tick(hass, ctrl, mode=MODE_HEATING):
    hass.services.async_call.reset_mock()
    await ctrl.async_apply(mode, TargetTemps(heat=21.0, cool=24.0), power_fraction=1.0, current_temp=18.0)
    return _sent(hass)


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["unknown", "unavailable"])
async def test_identical_target_is_sent_once_while_state_is_unusable(state):
    """Mode and setpoint evicted each other in the single-entry cache, so every tick resent both."""
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_state(state))
    ctrl = _ctrl(hass)

    first = await _tick(hass, ctrl)
    second = await _tick(hass, ctrl)
    third = await _tick(hass, ctrl)

    assert {s for s, _, _ in first} == {"set_hvac_mode", "set_temperature"}
    assert second == []
    assert third == []


@pytest.mark.asyncio
async def test_setpoint_is_resent_after_a_mode_change():
    """A mode change can reset the device's setpoint, so the cached setpoint must not suppress it."""
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_state("unknown"))
    ctrl = _ctrl(hass)

    await _tick(hass, ctrl)
    off = await _tick(hass, ctrl, MODE_IDLE)
    again = await _tick(hass, ctrl)

    assert ("set_hvac_mode", "off", None) in off
    assert {s for s, _, _ in again} == {"set_hvac_mode", "set_temperature"}


@pytest.mark.asyncio
async def test_changed_setpoint_is_sent_again():
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_state("unknown"))
    ctrl = _ctrl(hass)

    await _tick(hass, ctrl)
    hass.services.async_call.reset_mock()
    await ctrl.async_apply(MODE_HEATING, TargetTemps(heat=22.0, cool=24.0), power_fraction=0.0, current_temp=18.0)

    assert [s for s, _, _ in _sent(hass)] == ["set_temperature"]


@pytest.mark.asyncio
async def test_state_confirmed_value_replaces_a_stale_cache_entry():
    """While the state is usable, what the device reports wins over what we sent earlier."""
    hass = build_hass()
    ctrl = _ctrl(hass)

    hass.states.get = MagicMock(return_value=_state("off"))
    await _tick(hass, ctrl, MODE_COOLING)  # cache: cool

    hass.states.get = MagicMock(return_value=_state("heat", 30.0))  # user switched to heat by hand
    await _tick(hass, ctrl)  # mode heat is confirmed by the state, nothing to send for the mode

    hass.states.get = MagicMock(return_value=_state("unknown"))
    sent = await _tick(hass, ctrl, MODE_COOLING)  # must not be swallowed by the stale "cool"

    assert ("set_hvac_mode", "cool", None) in sent


@pytest.mark.asyncio
async def test_cached_command_is_reasserted_once_after_the_ttl():
    """No state feedback: a lost frame or a change on the remote heals after the TTL, without beeping every cycle."""
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_state("unknown"))
    ctrl = _ctrl(hass)
    module = "custom_components.roommind.control.mpc_controller._now"
    clock = {"t": 1000.0}

    with patch(module, side_effect=lambda: clock["t"]):
        first = await _tick(hass, ctrl)
        clock["t"] += COMMAND_CACHE_REASSERT_SECONDS - 1
        before = await _tick(hass, ctrl)
        clock["t"] += 1
        expired = await _tick(hass, ctrl)
        clock["t"] += 30
        after = await _tick(hass, ctrl)
        clock["t"] += COMMAND_CACHE_REASSERT_SECONDS
        next_round = await _tick(hass, ctrl)

    assert {s for s, _, _ in first} == {"set_hvac_mode", "set_temperature"}
    assert before == []
    assert {s for s, _, _ in expired} == {"set_hvac_mode", "set_temperature"}
    assert after == []
    assert {s for s, _, _ in next_round} == {"set_hvac_mode", "set_temperature"}


@pytest.mark.asyncio
async def test_off_is_reasserted_after_the_ttl_for_a_device_without_state():
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_state("unknown"))
    ctrl = _ctrl(hass)
    clock = {"t": 1000.0}

    with patch("custom_components.roommind.control.mpc_controller._now", side_effect=lambda: clock["t"]):
        first = await _tick(hass, ctrl, MODE_IDLE)
        before = await _tick(hass, ctrl, MODE_IDLE)
        clock["t"] += COMMAND_CACHE_REASSERT_SECONDS
        expired = await _tick(hass, ctrl, MODE_IDLE)
        after = await _tick(hass, ctrl, MODE_IDLE)

    assert ("set_hvac_mode", "off", None) in first
    assert before == []
    assert ("set_hvac_mode", "off", None) in expired
    assert after == []


@pytest.mark.asyncio
async def test_valid_state_devices_ignore_the_ttl():
    """The TTL only concerns the cache path; a device with a real state is compared against that state."""
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_state("heat", 29.5))
    ctrl = _ctrl(hass)
    clock = {"t": 1000.0}

    with patch("custom_components.roommind.control.mpc_controller._now", side_effect=lambda: clock["t"]):
        first = await _tick(hass, ctrl)
        clock["t"] += 10 * COMMAND_CACHE_REASSERT_SECONDS
        later = await _tick(hass, ctrl)

    assert first == later == []
