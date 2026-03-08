"""Tests for RoomMind switch platform."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.roommind.switch import RoomMindCoverAutoSwitch, _create_room_switches


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
