"""Rooms whose Home Assistant area was deleted rest in the coordinator cycle (#494)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.const import TargetTemps
from custom_components.roommind.utils.area_utils import REST_SWITCHED_OFF

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get

AREA_REGISTRY = "custom_components.roommind.utils.area_utils.ar.async_get"


def _registry(*area_ids: str) -> MagicMock:
    registry = MagicMock()
    registry.async_list_areas.return_value = [SimpleNamespace(id=a) for a in area_ids]
    return registry


def _resting_room(**extra) -> dict:
    return {
        **SAMPLE_ROOM,
        "area_id": "old_room",
        "devices": [
            {"entity_id": "climate.old_trv", "type": "trv", "role": "auto", "heating_system_type": ""},
            {"entity_id": "climate.living_room", "type": "trv", "role": "auto", "heating_system_type": ""},
        ],
        **extra,
    }


def _coordinator(hass, entry, rooms: dict):
    store = _make_store_mock(rooms)
    store.async_update_room = AsyncMock()
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(side_effect=make_mock_states_get())
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, entry)
    coordinator._async_switch_devices_off = AsyncMock()
    coordinator._async_release_valves = AsyncMock()
    return coordinator, store


@pytest.mark.asyncio
async def test_a_resting_room_is_not_controlled(hass, mock_config_entry):
    coordinator, _ = _coordinator(
        hass, mock_config_entry, {"living_room": SAMPLE_ROOM, "old_room": _resting_room(**{REST_SWITCHED_OFF: True})}
    )

    with patch(AREA_REGISTRY, return_value=_registry("living_room")):
        data = await coordinator._async_update_data()

    assert set(data["rooms"]) == {"living_room"}
    coordinator._async_switch_devices_off.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_room_starting_to_rest_switches_its_own_devices_off_once(hass, mock_config_entry):
    coordinator, store = _coordinator(
        hass, mock_config_entry, {"living_room": SAMPLE_ROOM, "old_room": _resting_room()}
    )
    coordinator.rooms = {"old_room": {"heat_target": 21.0, "cool_target": 24.0}}

    with patch(AREA_REGISTRY, return_value=_registry("living_room")):
        await coordinator._async_update_data()

    # The living room still drives its own thermostat, the resting room only lets go of its own
    coordinator._async_switch_devices_off.assert_awaited_once_with(
        "old_room",
        [{"entity_id": "climate.old_trv", "type": "trv", "role": "auto", "heating_system_type": ""}],
        TargetTemps(heat=21.0, cool=24.0),
    )
    store.async_update_room.assert_any_await("old_room", {REST_SWITCHED_OFF: True})


@pytest.mark.asyncio
async def test_climate_control_off_sends_nothing_to_a_resting_room(hass, mock_config_entry):
    coordinator, store = _coordinator(
        hass, mock_config_entry, {"old_room": _resting_room(climate_control_enabled=False)}
    )

    with patch(AREA_REGISTRY, return_value=_registry("living_room")):
        await coordinator._async_update_data()

    coordinator._async_switch_devices_off.assert_not_awaited()
    # Not marked: once control is on again, the next cycle switches the devices off
    store.async_update_room.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_area_deleted_during_the_cycle_is_skipped(hass, mock_config_entry):
    """The cycle's snapshot still has the room; the live check before processing it does not."""
    coordinator, _ = _coordinator(hass, mock_config_entry, {"living_room": SAMPLE_ROOM})
    coordinator._async_process_room = AsyncMock()
    snapshot_then_gone = MagicMock(side_effect=[{"living_room": SAMPLE_ROOM}, {}, {}, {}, {}, {}])

    with patch("custom_components.roommind.coordinator.rooms_with_area", snapshot_then_gone):
        await coordinator._async_update_data()

    coordinator._async_process_room.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_resting_room_keeps_its_learned_ac_offsets(hass, mock_config_entry):
    coordinator, _ = _coordinator(
        hass, mock_config_entry, {"living_room": SAMPLE_ROOM, "old_room": _resting_room(**{REST_SWITCHED_OFF: True})}
    )
    coordinator._head_offsets.prune = MagicMock()

    with patch(AREA_REGISTRY, return_value=_registry("living_room")):
        await coordinator._async_update_data()

    kept = coordinator._head_offsets.prune.call_args[0][0]
    assert "climate.old_trv" in kept


@pytest.mark.asyncio
async def test_a_room_running_again_loses_the_mark(hass, mock_config_entry):
    """Its area came back without an event (restored backup): resting later must switch off again."""
    coordinator, store = _coordinator(
        hass, mock_config_entry, {"living_room": {**SAMPLE_ROOM, REST_SWITCHED_OFF: True}}
    )

    with patch(AREA_REGISTRY, return_value=_registry("living_room")):
        await coordinator._async_update_data()

    store.async_update_room.assert_any_await("living_room", {REST_SWITCHED_OFF: False})


@pytest.mark.asyncio
async def test_a_room_deleted_while_switching_off_does_not_break_the_cycle(hass, mock_config_entry):
    coordinator, store = _coordinator(
        hass, mock_config_entry, {"living_room": SAMPLE_ROOM, "old_room": _resting_room()}
    )
    store.async_update_room = AsyncMock(side_effect=KeyError("old_room"))

    with patch(AREA_REGISTRY, return_value=_registry("living_room")):
        data = await coordinator._async_update_data()

    assert set(data["rooms"]) == {"living_room"}
