"""Tests for override/vacation/presence/schedule priority chain."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from .conftest import (
    SAMPLE_ROOM,
    _create_coordinator,
    _make_store_mock,
    make_mock_states_get,
)


class TestRoomMindCoordinator:
    """Tests for RoomMindCoordinator."""

    @pytest.mark.asyncio
    async def test_override_takes_priority_over_schedule(self, hass, mock_config_entry):
        """Test that an active override overrides the schedule target temp."""
        room_with_override = {
            **SAMPLE_ROOM,
            "override_heat": 25.0,
            "override_cool": 25.0,
            "override_until": time.time() + 3600,
            "override_type": "boost",
        }
        store = _make_store_mock({"living_room_abc12345": room_with_override})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(side_effect=make_mock_states_get(schedule_state="off"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["target_temp"] == 25.0
        assert room_state["override_active"] is True
        assert room_state["override_type"] == "boost"

    @pytest.mark.asyncio
    async def test_eco_override_in_auto_room_keeps_heat_cool_band(self, hass, mock_config_entry):
        """ECO override resolves to eco_heat/eco_cool, so a 21 C room does not cool toward eco_heat (#284)."""
        room = {
            **SAMPLE_ROOM,
            "climate_mode": "auto",
            "eco_heat": 17.0,
            "eco_cool": 27.0,
            "override_heat": 17.0,
            "override_cool": 27.0,
            "override_until": None,
            "override_type": "eco",
        }
        store = _make_store_mock({"living_room_abc12345": room})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp=21.0, schedule_state="off"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["heat_target"] == 17.0
        assert room_state["cool_target"] == 27.0
        assert room_state["mode"] == "idle"

    @pytest.mark.asyncio
    async def test_expired_override_falls_back_to_schedule(self, hass, mock_config_entry):
        """Test that an expired override reverts to normal schedule logic."""
        room_with_expired = {
            **SAMPLE_ROOM,
            "override_heat": 25.0,
            "override_cool": 25.0,
            "override_until": time.time() - 10,
            "override_type": "boost",
        }
        store = _make_store_mock({"living_room_abc12345": room_with_expired})
        store.async_update_room = AsyncMock()
        hass.data = {"roommind": {"store": store}}
        hass.async_create_task = MagicMock(side_effect=lambda coro: coro.close())

        hass.states.get = MagicMock(side_effect=make_mock_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["target_temp"] == 21.0
        assert room_state["override_active"] is False

    @pytest.mark.asyncio
    async def test_permanent_override_takes_priority(self, hass, mock_config_entry):
        """Permanent override (override_until=None) takes priority over schedule."""
        room_with_override = {
            **SAMPLE_ROOM,
            "override_heat": 23.0,
            "override_cool": 23.0,
            "override_until": None,
            "override_type": "custom",
        }
        store = _make_store_mock({"living_room_abc12345": room_with_override})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(side_effect=make_mock_states_get(schedule_state="off"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["target_temp"] == 23.0
        assert room_state["override_active"] is True
        assert room_state["override_type"] == "custom"


class TestVacationMode:
    """Tests for vacation mode target temperature override."""

    @pytest.mark.asyncio
    async def test_vacation_overrides_schedule(self, hass, mock_config_entry):
        """Active vacation mode uses vacation_temp instead of schedule."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "vacation_temp": 15.0,
            "vacation_until": time.time() + 86400,
        }
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(side_effect=make_mock_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["target_temp"] == 15.0

    @pytest.mark.asyncio
    async def test_override_beats_vacation(self, hass, mock_config_entry):
        """Manual override takes priority over vacation mode."""
        room_with_override = {
            **SAMPLE_ROOM,
            "override_heat": 25.0,
            "override_cool": 25.0,
            "override_until": time.time() + 3600,
            "override_type": "boost",
        }
        store = _make_store_mock({"living_room_abc12345": room_with_override})
        store.get_settings.return_value = {
            "vacation_temp": 15.0,
            "vacation_until": time.time() + 86400,
        }
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(side_effect=make_mock_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["target_temp"] == 25.0

    @pytest.mark.asyncio
    async def test_expired_vacation_falls_back_to_schedule(self, hass, mock_config_entry):
        """Expired vacation mode reverts to normal schedule logic."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "vacation_temp": 15.0,
            "vacation_until": time.time() - 10,
        }
        store.async_save_settings = AsyncMock()
        hass.data = {"roommind": {"store": store}}
        hass.async_create_task = MagicMock(side_effect=lambda coro: coro.close())

        hass.states.get = MagicMock(side_effect=make_mock_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["target_temp"] == 21.0  # comfort_temp from schedule

    @pytest.mark.asyncio
    async def test_vacation_cool_target_stays_at_eco_cool(self, hass, mock_config_entry):
        """Vacation should not collapse cool_target to vacation_temp."""
        room = {**SAMPLE_ROOM, "eco_cool": 27.0}
        store = _make_store_mock({"living_room_abc12345": room})
        store.get_settings.return_value = {
            "vacation_temp": 15.0,
            "vacation_until": time.time() + 86400,
        }
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(side_effect=make_mock_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["heat_target"] == 15.0
        assert room_state["cool_target"] == 27.0  # eco_cool, not 15


class TestSplitOverrideResolution:
    """Tests for split heat/cool override targets (#313)."""

    def test_resolve_override_auto_uses_split_dead_band(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        room = {
            **SAMPLE_ROOM,
            "climate_mode": "auto",
            "override_type": "custom",
            "override_heat": 19.5,
            "override_cool": 23.0,
            "override_until": None,
        }
        targets = coordinator._resolve_target_temps(room, {}, None, None)
        assert targets.heat == 19.5
        assert targets.cool == 23.0

    def test_resolve_override_cool_only_heat_none(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        room = {
            **SAMPLE_ROOM,
            "climate_mode": "cool_only",
            "override_type": "custom",
            "override_heat": None,
            "override_cool": 24.0,
            "override_until": None,
        }
        targets = coordinator._resolve_target_temps(room, {}, None, None)
        assert targets.heat is None
        assert targets.cool == 24.0
