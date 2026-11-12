"""A room rests while its Home Assistant area is deleted and comes back with it (#494)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers import area_registry as ar

from custom_components.roommind import async_track_area_changes
from custom_components.roommind.const import DOMAIN
from custom_components.roommind.utils.area_utils import REST_SWITCHED_OFF, rooms_with_area, rooms_without_area
from custom_components.roommind.websocket_api import async_remove_room

ROOMS = {"kitchen": {"area_id": "kitchen"}, "old_room": {"area_id": "old_room", "display_name": "Old"}}


def _registry(area_ids: set[str]) -> MagicMock:
    registry = MagicMock()
    registry.async_list_areas.return_value = [SimpleNamespace(id=a) for a in area_ids]
    return registry


@pytest.fixture
def coordinator():
    coord = MagicMock()
    coord.async_room_paused = AsyncMock()
    coord.async_room_added = AsyncMock()
    coord.async_room_removed = AsyncMock()
    return coord


@pytest.fixture
def rm_hass(hass, store, coordinator):
    hass.data[DOMAIN] = {"store": store, "coordinator": coordinator}
    return hass


def test_rooms_without_their_area_rest(hass):
    with patch("custom_components.roommind.utils.area_utils.ar.async_get", return_value=_registry({"kitchen"})):
        assert set(rooms_with_area(hass, ROOMS)) == {"kitchen"}
        assert set(rooms_without_area(hass, ROOMS)) == {"old_room"}


def test_without_any_area_every_room_rests(hass):
    """Resting keeps everything stored, so a registry that came up empty costs nothing."""
    with patch("custom_components.roommind.utils.area_utils.ar.async_get", return_value=_registry(set())):
        assert rooms_with_area(hass, ROOMS) == {}
        assert rooms_without_area(hass, ROOMS) == ROOMS


def test_no_area_registry_loaded_pauses_nothing(hass):
    with patch("custom_components.roommind.utils.area_utils.ar.async_get", side_effect=KeyError("area_registry")):
        assert rooms_with_area(hass, ROOMS) == ROOMS


def _area_event(action: str, area_id: str) -> SimpleNamespace:
    return SimpleNamespace(data={"action": action, "area_id": area_id})


def _listen(hass):
    unsub = async_track_area_changes(hass)
    event_type, handler = hass.bus.async_listen.call_args[0]
    assert event_type == ar.EVENT_AREA_REGISTRY_UPDATED
    assert unsub is hass.bus.async_listen.return_value
    return handler


@pytest.mark.asyncio
async def test_deleting_an_area_rests_its_room_and_keeps_it_stored(rm_hass, store, coordinator):
    await store.async_load()
    await store.async_save_room("guest_room", {})
    await store.async_save_thermal_data({"guest_room": {"x": 1}})
    handler = _listen(rm_hass)

    await handler(_area_event("remove", "guest_room"))

    assert set(store.get_rooms()) == {"guest_room"}
    assert set(store.get_thermal_data()) == {"guest_room"}
    coordinator.async_room_paused.assert_awaited_once_with("guest_room")
    coordinator.async_room_removed.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_room_runs_again_when_its_area_is_back(rm_hass, store, coordinator):
    await store.async_load()
    await store.async_save_room("guest_room", {"comfort_temp": 22.5})
    await store.async_update_room("guest_room", {REST_SWITCHED_OFF: True})
    handler = _listen(rm_hass)

    await handler(_area_event("create", "guest_room"))

    room = coordinator.async_room_added.await_args[0][0]
    assert room["area_id"] == "guest_room"
    assert room["comfort_temp"] == 22.5
    # Resting again later switches its devices off again
    assert room[REST_SWITCHED_OFF] is False


@pytest.mark.asyncio
async def test_area_changes_without_a_room_or_other_actions_do_nothing(rm_hass, store, coordinator):
    await store.async_load()
    await store.async_save_room("office", {})
    handler = _listen(rm_hass)

    await handler(_area_event("update", "office"))
    await handler(_area_event("remove", "garage"))
    await handler(_area_event("create", "garage"))

    coordinator.async_room_paused.assert_not_awaited()
    coordinator.async_room_added.assert_not_awaited()


@pytest.mark.asyncio
async def test_deleting_a_resting_room_drops_its_learned_model(rm_hass, store, coordinator):
    await store.async_load()
    await store.async_save_room("old_room", {})
    await store.async_save_thermal_data({"old_room": {"x": 1}, "kitchen": {"x": 2}})

    assert await async_remove_room(rm_hass, "old_room")

    assert store.get_rooms() == {}
    assert set(store.get_thermal_data()) == {"kitchen"}
    coordinator.async_room_removed.assert_awaited_once_with("old_room")


@pytest.mark.asyncio
async def test_deleting_a_room_queues_its_devices_and_forgets_it_in_the_room_lists(rm_hass, store, coordinator):
    await store.async_load()
    await store.async_save_room("old_room", {"devices": [{"entity_id": "climate.old_trv", "type": "trv"}]})
    await store.async_save_settings(
        {
            "hidden_rooms": ["old_room", "kitchen"],
            "room_order": ["kitchen", "old_room"],
            "learning_disabled_rooms": ["old_room"],
        }
    )
    coordinator.note_room_deleted = MagicMock(return_value=True)

    assert await async_remove_room(rm_hass, "old_room")

    area_id, room = coordinator.note_room_deleted.call_args[0]
    assert area_id == "old_room"
    assert [d["entity_id"] for d in room["devices"]] == ["climate.old_trv"]
    settings = store.get_settings()
    assert settings["hidden_rooms"] == ["kitchen"]
    assert settings["room_order"] == ["kitchen"]
    assert settings["learning_disabled_rooms"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("queued", [True, False])
async def test_a_deleted_room_hands_its_valves_back_only_when_its_devices_stay_on(rm_hass, store, coordinator, queued):
    """Switched off next cycle: the room target as setpoint would let the TRV heat on by itself."""
    await store.async_load()
    await store.async_save_room(
        "old_room",
        {
            "devices": [
                {
                    "entity_id": "climate.old_trv",
                    "type": "trv",
                    "valve_opening_entity": "number.old_trv_opening",
                    "valve_closing_entity": "number.old_trv_closing",
                }
            ]
        },
    )
    coordinator.note_room_deleted = MagicMock(return_value=queued)

    with patch("custom_components.roommind.websocket_api.async_release_valve", AsyncMock()) as release:
        assert await async_remove_room(rm_hass, "old_room")

    assert release.await_args.kwargs["hand_back"] is not queued
