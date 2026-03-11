"""Tests for RoomMind switch platform."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.roommind.const import DOMAIN, VACATION_SENTINEL_UNTIL
from custom_components.roommind.switch import (
    RoomMindCoverAutoSwitch,
    RoomMindVacationSwitch,
    _create_room_switches,
    async_setup_entry,
)


@pytest.fixture
def mock_coordinator():
    coordinator = MagicMock()
    coordinator.data = {"rooms": {"living_room": {"covers_auto_enabled": True, "cover_auto_paused": False}}}
    coordinator.hass = MagicMock()
    coordinator.async_request_refresh = AsyncMock()
    store = MagicMock()
    coordinator.hass.data = {"roommind": {"store": store}}
    return coordinator, store


def test_cover_auto_switch_is_on_reads_store(mock_coordinator):
    """Switch reads is_on from store, not coordinator data."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"covers_auto_enabled": True}
    switch = RoomMindCoverAutoSwitch(coordinator, "living_room")
    assert switch.is_on is True

    store.get_room.return_value = {"covers_auto_enabled": False}
    assert switch.is_on is False


def test_cover_auto_switch_is_on_missing_room(mock_coordinator):
    """Switch returns False when room doesn't exist."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = None
    switch = RoomMindCoverAutoSwitch(coordinator, "nonexistent")
    assert switch.is_on is False


@pytest.mark.asyncio
async def test_cover_auto_switch_turn_on(mock_coordinator):
    """Turn on persists to store and refreshes coordinator."""
    coordinator, store = mock_coordinator
    store.async_update_room = AsyncMock()
    switch = RoomMindCoverAutoSwitch(coordinator, "living_room")
    await switch.async_turn_on()
    store.async_update_room.assert_awaited_once_with("living_room", {"covers_auto_enabled": True})
    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_cover_auto_switch_turn_off(mock_coordinator):
    """Turn off persists to store and refreshes coordinator."""
    coordinator, store = mock_coordinator
    store.async_update_room = AsyncMock()
    switch = RoomMindCoverAutoSwitch(coordinator, "living_room")
    await switch.async_turn_off()
    store.async_update_room.assert_awaited_once_with("living_room", {"covers_auto_enabled": False})
    coordinator.async_request_refresh.assert_awaited_once()


def test_switch_unique_id_and_entity_id(mock_coordinator):
    """Switch has correct unique_id and entity_id."""
    coordinator, _ = mock_coordinator
    switch = RoomMindCoverAutoSwitch(coordinator, "living_room")
    assert switch.unique_id == "roommind_living_room_cover_auto"
    assert switch.entity_id == "switch.roommind_living_room_cover_auto"


def test_create_room_switches(mock_coordinator):
    """Factory creates exactly one switch per room."""
    coordinator, _ = mock_coordinator
    switches = _create_room_switches(coordinator, "living_room")
    assert len(switches) == 1
    assert isinstance(switches[0], RoomMindCoverAutoSwitch)


@pytest.mark.asyncio
async def test_cover_auto_switch_turn_on_store_raises_keyerror(mock_coordinator):
    """Exception propagates when store raises KeyError for deleted room."""
    coordinator, store = mock_coordinator
    store.async_update_room = AsyncMock(side_effect=KeyError("nonexistent"))
    switch = RoomMindCoverAutoSwitch(coordinator, "nonexistent")
    with pytest.raises(KeyError):
        await switch.async_turn_on()


@pytest.mark.asyncio
async def test_async_setup_entry_creates_entities_for_rooms_with_covers():
    """async_setup_entry creates vacation switch + cover switches for rooms with covers."""
    coordinator = MagicMock()
    coordinator._switch_entity_areas = set()
    coordinator.hass = MagicMock()
    coordinator.hass.data = {DOMAIN: {"store": MagicMock()}}

    store = MagicMock()
    store.get_rooms.return_value = {
        "living_room": {"covers": ["cover.blinds"]},
        "bedroom": {},  # no covers
    }

    entry = MagicMock()
    entry.entry_id = "test_entry"

    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: coordinator, "store": store}}

    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)

    assert coordinator.async_add_switch_entities is async_add_entities
    async_add_entities.assert_called_once()
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 2
    assert isinstance(entities[0], RoomMindVacationSwitch)
    assert isinstance(entities[1], RoomMindCoverAutoSwitch)
    assert "living_room" in coordinator._switch_entity_areas
    assert "bedroom" not in coordinator._switch_entity_areas


@pytest.mark.asyncio
async def test_async_setup_entry_no_covers_still_creates_vacation_switch():
    """async_setup_entry always creates the global vacation switch even without covers."""
    coordinator = MagicMock()
    coordinator._switch_entity_areas = set()

    store = MagicMock()
    store.get_rooms.return_value = {"bedroom": {}}

    entry = MagicMock()
    entry.entry_id = "test_entry"

    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: coordinator, "store": store}}

    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)

    async_add_entities.assert_called_once()
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 1
    assert isinstance(entities[0], RoomMindVacationSwitch)


@pytest.fixture
def mock_vacation_coordinator():
    coordinator = MagicMock()
    coordinator.async_request_refresh = AsyncMock()
    store = MagicMock()
    coordinator.hass = MagicMock()
    coordinator.hass.data = {DOMAIN: {"store": store}}
    return coordinator, store


def test_vacation_switch_unique_id_and_entity_id(mock_vacation_coordinator):
    """Vacation switch has correct unique_id and entity_id."""
    coordinator, _ = mock_vacation_coordinator
    switch = RoomMindVacationSwitch(coordinator)
    assert switch.unique_id == "roommind_vacation"
    assert switch.entity_id == "switch.roommind_vacation"
    assert switch.icon == "mdi:beach"
    assert switch.name == "Vacation Mode"


def test_vacation_switch_is_on_active(mock_vacation_coordinator):
    """Vacation switch returns True when vacation_until is in the future."""
    coordinator, store = mock_vacation_coordinator
    store.get_settings.return_value = {"vacation_until": time.time() + 3600}
    switch = RoomMindVacationSwitch(coordinator)
    assert switch.is_on is True


def test_vacation_switch_is_on_expired(mock_vacation_coordinator):
    """Vacation switch returns False when vacation_until is in the past."""
    coordinator, store = mock_vacation_coordinator
    store.get_settings.return_value = {"vacation_until": time.time() - 3600}
    switch = RoomMindVacationSwitch(coordinator)
    assert switch.is_on is False


def test_vacation_switch_is_on_none(mock_vacation_coordinator):
    """Vacation switch returns False when vacation_until is None."""
    coordinator, store = mock_vacation_coordinator
    store.get_settings.return_value = {"vacation_until": None}
    switch = RoomMindVacationSwitch(coordinator)
    assert switch.is_on is False


def test_vacation_switch_is_on_missing_key(mock_vacation_coordinator):
    """Vacation switch returns False when vacation_until key is absent."""
    coordinator, store = mock_vacation_coordinator
    store.get_settings.return_value = {}
    switch = RoomMindVacationSwitch(coordinator)
    assert switch.is_on is False


@pytest.mark.asyncio
async def test_vacation_switch_turn_on(mock_vacation_coordinator):
    """Turn on sets vacation_until to sentinel and preserves stored temp."""
    coordinator, store = mock_vacation_coordinator
    store.get_settings.return_value = {"vacation_temp": 16.0}
    store.async_save_settings = AsyncMock()
    switch = RoomMindVacationSwitch(coordinator)
    await switch.async_turn_on()
    store.async_save_settings.assert_awaited_once_with(
        {
            "vacation_temp": 16.0,
            "vacation_until": VACATION_SENTINEL_UNTIL,
        }
    )
    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_vacation_switch_turn_on_default_temp(mock_vacation_coordinator):
    """Turn on uses 15.0 as default when no vacation_temp is stored."""
    coordinator, store = mock_vacation_coordinator
    store.get_settings.return_value = {}
    store.async_save_settings = AsyncMock()
    switch = RoomMindVacationSwitch(coordinator)
    await switch.async_turn_on()
    store.async_save_settings.assert_awaited_once_with(
        {
            "vacation_temp": 15.0,
            "vacation_until": VACATION_SENTINEL_UNTIL,
        }
    )


@pytest.mark.asyncio
async def test_vacation_switch_turn_off(mock_vacation_coordinator):
    """Turn off clears vacation_until."""
    coordinator, store = mock_vacation_coordinator
    store.async_save_settings = AsyncMock()
    switch = RoomMindVacationSwitch(coordinator)
    await switch.async_turn_off()
    store.async_save_settings.assert_awaited_once_with({"vacation_until": None})
    coordinator.async_request_refresh.assert_awaited_once()
