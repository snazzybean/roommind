"""What set a room's targets, recorded for the analytics chart."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.const import (
    TARGET_REASON_AWAY,
    TARGET_REASON_OVERRIDE,
    TARGET_REASON_VACANT,
    TARGET_REASON_VACATION,
)

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get

OVERRIDE = {"override_heat": 25.0, "override_cool": 25.0, "override_until": None, "override_type": "boost"}


def test_schedule_has_no_reason(hass, mock_config_entry):
    coordinator = _create_coordinator(hass, mock_config_entry)
    _, reason = coordinator._resolve_target_temps_and_reason(SAMPLE_ROOM, {})
    assert reason == ""


def test_override_is_named(hass, mock_config_entry):
    coordinator = _create_coordinator(hass, mock_config_entry)
    targets, reason = coordinator._resolve_target_temps_and_reason({**SAMPLE_ROOM, **OVERRIDE}, {})
    assert targets.heat == 25.0
    assert reason == TARGET_REASON_OVERRIDE


def test_override_cleared_by_presence_is_away(hass, mock_config_entry):
    coordinator = _create_coordinator(hass, mock_config_entry)
    coordinator._is_presence_away = lambda room, settings: True
    _, reason = coordinator._resolve_target_temps_and_reason(
        {**SAMPLE_ROOM, **OVERRIDE}, {"presence_clears_override": True}
    )
    assert reason == TARGET_REASON_AWAY


def test_vacation_is_named(hass, mock_config_entry):
    coordinator = _create_coordinator(hass, mock_config_entry)
    settings = {"vacation_until": time.time() + 3600, "vacation_temp": 15.0}
    targets, reason = coordinator._resolve_target_temps_and_reason(SAMPLE_ROOM, settings)
    assert targets.heat == 15.0
    assert reason == TARGET_REASON_VACATION


@pytest.mark.parametrize("action", ["eco", "off"])
def test_presence_away_is_named(hass, mock_config_entry, action):
    coordinator = _create_coordinator(hass, mock_config_entry)
    coordinator._is_presence_away = lambda room, settings: True
    _, reason = coordinator._resolve_target_temps_and_reason(SAMPLE_ROOM, {"presence_away_action": action})
    assert reason == TARGET_REASON_AWAY


def test_empty_room_is_named_only_when_it_lowered_the_target(hass, mock_config_entry):
    coordinator = _create_coordinator(hass, mock_config_entry)
    room = {**SAMPLE_ROOM, "eco_heat": 17.0, "eco_cool": 27.0}
    with patch.object(coordinator, "_resolve_schedule_targets", return_value=_targets(21.0, 24.0)):
        _, lowered = coordinator._resolve_target_temps_and_reason(room, {}, room_vacant=True)
    with patch.object(coordinator, "_resolve_schedule_targets", return_value=_targets(17.0, 27.0)):
        _, already_eco = coordinator._resolve_target_temps_and_reason(room, {}, room_vacant=True)
    assert lowered == TARGET_REASON_VACANT
    assert already_eco == ""


def _targets(heat, cool):
    from custom_components.roommind.utils.schedule_utils import TargetTemps

    return TargetTemps(heat=heat, cool=cool)


async def _run_cycle(hass, mock_config_entry, room, mold_delta=None):
    store = _make_store_mock({"living_room_abc12345": room})
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(side_effect=make_mock_states_get(schedule_state="off"))
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    if mold_delta is not None:
        coordinator._evaluate_mold_risk = AsyncMock(return_value=("critical", 85.0, 12.0, True, mold_delta))
    data = await coordinator._async_update_data()
    return data["rooms"]["living_room_abc12345"]


@pytest.mark.asyncio
async def test_room_state_carries_the_reason(hass, mock_config_entry):
    state = await _run_cycle(hass, mock_config_entry, {**SAMPLE_ROOM, **OVERRIDE})
    assert state["target_reason"] == TARGET_REASON_OVERRIDE
    assert state["mold_boost"] == 0.0


@pytest.mark.asyncio
async def test_room_state_carries_the_mold_boost_on_top_of_the_schedule(hass, mock_config_entry):
    state = await _run_cycle(hass, mock_config_entry, SAMPLE_ROOM, mold_delta=2.0)
    assert state["target_reason"] == ""
    assert state["mold_boost"] == 2.0


@pytest.mark.asyncio
async def test_room_state_without_reason_follows_the_schedule(hass, mock_config_entry):
    state = await _run_cycle(hass, mock_config_entry, SAMPLE_ROOM)
    assert state["target_reason"] == ""
