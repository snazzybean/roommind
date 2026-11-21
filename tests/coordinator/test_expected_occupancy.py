"""Tests for the expected occupancy input in the coordinator's target resolution."""

from __future__ import annotations

import time
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import State
from homeassistant.util import dt as dt_util

from custom_components.roommind.utils import schedule_utils
from custom_components.roommind.utils.expected_occupancy import ExpectedOccupancy

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get

AREA = "living_room_abc12345"


def _expected(probability: float | None) -> ExpectedOccupancy:
    """An expected occupancy with the same probability at every instant."""
    return ExpectedOccupancy(probability=lambda _ts: probability, threshold=0.5)


async def _run(hass, mock_config_entry, expected, room=None, settings=None, **states):
    """One update cycle of SAMPLE_ROOM (schedule on) with the given expected occupancy."""
    store = _make_store_mock({AREA: room or SAMPLE_ROOM}, settings)
    hass.data = {"roommind": {"store": store}}
    hass.states.get = make_mock_states_get(**states)
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    with patch.object(coordinator, "_async_expected_occupancy", AsyncMock(return_value=expected)):
        data = await coordinator._async_update_data()
    return coordinator, data["rooms"][AREA]


@pytest.mark.asyncio
async def test_without_source_the_schedule_decides(hass, mock_config_entry):
    coordinator, room = await _run(hass, mock_config_entry, None)
    assert room["target_temp"] == 21.0
    assert coordinator.expected_occupancy(AREA) is None


@pytest.mark.asyncio
async def test_expected_window_replaces_the_schedule_window(hass, mock_config_entry):
    coordinator, room = await _run(hass, mock_config_entry, _expected(0.1))
    assert room["target_temp"] == 17.0
    assert room["target_reason"] == ""
    assert coordinator.expected_occupancy(AREA) is not None


@pytest.mark.asyncio
async def test_expected_use_gives_comfort_while_the_schedule_is_off(hass, mock_config_entry):
    _, room = await _run(hass, mock_config_entry, _expected(0.9), schedule_state="off")
    assert room["target_temp"] == 21.0


@pytest.mark.asyncio
async def test_unknown_instant_falls_back_to_the_schedule(hass, mock_config_entry):
    _, room = await _run(hass, mock_config_entry, _expected(None), schedule_state="off")
    assert room["target_temp"] == 17.0


@pytest.mark.asyncio
async def test_override_keeps_priority(hass, mock_config_entry):
    room_cfg = {
        **SAMPLE_ROOM,
        "override_heat": 23.0,
        "override_cool": 23.0,
        "override_until": time.time() + 3600,
        "override_type": "custom",
    }
    _, room = await _run(hass, mock_config_entry, _expected(0.1), room=room_cfg)
    assert room["target_temp"] == 23.0
    assert room["target_reason"] == "override"


@pytest.mark.asyncio
async def test_horizon_gets_the_expected_occupancy(hass, mock_config_entry):
    """The MPC horizon resolves with the same input, so it pre-heats for the expected window."""
    expected = _expected(0.9)
    with patch.object(schedule_utils, "make_target_resolver", wraps=schedule_utils.make_target_resolver) as resolver:
        await _run(hass, mock_config_entry, expected)
    assert resolver.call_args.kwargs["expected_occupancy"] is expected


MOTION = "binary_sensor.living_room_motion"
SENSOR_ROOM = {**SAMPLE_ROOM, "occupancy_sensors": [MOTION], "occupancy_eco_enabled": True, "occupancy_eco_delay": 5}


def _in_window_until(end: float) -> ExpectedOccupancy:
    """Expected in use from an hour ago until ``end``, not expected afterwards."""
    start = time.time() - 3600
    return ExpectedOccupancy(probability=lambda ts: 0.9 if start <= ts < end else 0.0, threshold=0.5, slot_minutes=1)


async def _cycle(hass, coordinator, expected, motion_state, changed_ago_s):
    """One more update cycle with the motion sensor in the given state."""
    base = make_mock_states_get()
    motion = State(MOTION, motion_state, last_changed=dt_util.utcnow() - timedelta(seconds=changed_ago_s))
    hass.states.get = lambda eid: motion if eid == MOTION else base(eid)
    with patch.object(coordinator, "_async_expected_occupancy", AsyncMock(return_value=expected)):
        data = await coordinator._async_update_data()
    return data["rooms"][AREA]


def _coordinator(hass, mock_config_entry, room):
    store = _make_store_mock({AREA: room})
    hass.data = {"roommind": {"store": store}}
    hass.services.async_call = AsyncMock()
    return _create_coordinator(hass, mock_config_entry)


@pytest.mark.asyncio
async def test_empty_in_the_window_is_eco_but_the_next_window_is_pre_heated(hass, mock_config_entry):
    coordinator = _coordinator(hass, mock_config_entry, SENSOR_ROOM)
    window_end = time.time() + 1800
    with patch.object(schedule_utils, "make_target_resolver", wraps=schedule_utils.make_target_resolver) as resolver:
        room = await _cycle(hass, coordinator, _in_window_until(window_end), "off", 3 * 3600)
    assert room["target_temp"] == 17.0
    assert room["occupancy_vacant"] is True
    assert room["target_reason"] == "vacant"
    kwargs = resolver.call_args.kwargs
    assert kwargs["room_vacant"] is False
    assert kwargs["expected_occupancy"].vacant_until == pytest.approx(window_end, abs=60)


@pytest.mark.asyncio
async def test_use_outside_the_window_lifts_to_comfort_and_holds(hass, mock_config_entry):
    coordinator = _coordinator(hass, mock_config_entry, SENSOR_ROOM)
    never = ExpectedOccupancy(probability=lambda _ts: 0.0, threshold=0.5)
    room = await _cycle(hass, coordinator, never, "on", 60)
    assert room["target_temp"] == 17.0  # not confirmed yet
    room = await _cycle(hass, coordinator, never, "on", 6 * 60)
    assert room["target_temp"] == 21.0
    room = await _cycle(hass, coordinator, never, "off", 2 * 60)
    assert room["target_temp"] == 21.0  # stepped out for a moment
    room = await _cycle(hass, coordinator, never, "off", 6 * 60)
    assert room["target_temp"] == 17.0


def _priors_now(prior: float) -> dict:
    """A get_time_priors response whose 'living' area has ``prior`` in the current hour and 0.0 elsewhere."""
    local = dt_util.now()
    slots = {f"{day},{hour}": 0.0 for day in range(7) for hour in range(24)}
    slots[f"{local.weekday()},{local.hour}"] = prior
    return {"areas": {"entry": {"area_id": "living", "global_prior": 0.05, "slot_minutes": 60, "slots_raw": slots}}}


async def _run_with_area_occupancy(hass, mock_config_entry, room, response, schedule_state="on"):
    """One update cycle with Area Occupancy's service answering ``response``."""
    store = _make_store_mock({AREA: room})
    hass.data = {"roommind": {"store": store}}
    hass.states.get = make_mock_states_get(schedule_state=schedule_state)
    hass.services.has_service = lambda domain, service: domain == "area_occupancy"

    async def _call(domain, service, data=None, **kwargs):
        return response if domain == "area_occupancy" else None

    hass.services.async_call = AsyncMock(side_effect=_call)
    coordinator = _create_coordinator(hass, mock_config_entry)
    data = await coordinator._async_update_data()
    return data["rooms"][AREA]


LEARNED_ROOM = {**SAMPLE_ROOM, "use_learned_schedule": True, "learned_occupancy_area_id": "living"}


@pytest.mark.asyncio
async def test_area_occupancy_replaces_the_schedule_window(hass, mock_config_entry):
    room = await _run_with_area_occupancy(hass, mock_config_entry, LEARNED_ROOM, _priors_now(0.0))
    assert room["target_temp"] == 17.0
    # automatic threshold: 3 x 0.05 = 0.15
    assert room["expected_occupancy_threshold"] == 0.15
    assert room["expected_comfort_hours"] == 0.0


@pytest.mark.asyncio
async def test_area_occupancy_gives_comfort_in_a_habitual_hour(hass, mock_config_entry):
    room = await _run_with_area_occupancy(hass, mock_config_entry, LEARNED_ROOM, _priors_now(0.3), schedule_state="off")
    assert room["target_temp"] == 21.0
    assert room["expected_comfort_hours"] == 1.0


@pytest.mark.asyncio
async def test_area_occupancy_is_opt_in(hass, mock_config_entry):
    room = await _run_with_area_occupancy(hass, mock_config_entry, SAMPLE_ROOM, _priors_now(0.0))
    assert room["target_temp"] == 21.0
    assert room["expected_occupancy_threshold"] is None


@pytest.mark.asyncio
async def test_missing_area_falls_back_to_the_schedule(hass, mock_config_entry):
    room = await _run_with_area_occupancy(hass, mock_config_entry, LEARNED_ROOM, {"areas": {}})
    assert room["target_temp"] == 21.0
    assert room["expected_occupancy_threshold"] is None
