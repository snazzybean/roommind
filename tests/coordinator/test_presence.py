"""Tests for presence detection, per-room persons, presence_away_action."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from .conftest import (
    SAMPLE_ROOM,
    _create_coordinator,
    _make_store_mock,
    _presence_states_get,
    make_mock_states_get,
)


class TestPresenceDetection:
    """Tests for presence-based eco temperature."""

    @pytest.mark.asyncio
    async def test_nobody_home_uses_eco(self, hass, mock_config_entry):
        """When all configured persons are away, rooms use eco_temp."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "presence_enabled": True,
            "presence_persons": ["person.kevin", "person.anna"],
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=_presence_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["target_temp"] == 17.0  # eco_temp
        assert room["presence_away"] is True

    @pytest.mark.asyncio
    async def test_someone_home_uses_schedule(self, hass, mock_config_entry):
        """When at least one person is home, schedule determines temp."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "presence_enabled": True,
            "presence_persons": ["person.kevin", "person.anna"],
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=_presence_states_get("person.kevin"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["target_temp"] == 21.0  # comfort_temp
        assert room["presence_away"] is False

    @pytest.mark.asyncio
    async def test_override_beats_presence(self, hass, mock_config_entry):
        """Manual override takes priority over presence."""
        room_with_override = {
            **SAMPLE_ROOM,
            "override_temp": 25.0,
            "override_until": time.time() + 3600,
            "override_type": "boost",
        }
        store = _make_store_mock({"living_room_abc12345": room_with_override})
        store.get_settings.return_value = {
            "presence_enabled": True,
            "presence_persons": ["person.kevin"],
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=_presence_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["target_temp"] == 25.0  # override wins

    @pytest.mark.asyncio
    async def test_vacation_beats_presence(self, hass, mock_config_entry):
        """Vacation takes priority over presence."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "presence_enabled": True,
            "presence_persons": ["person.kevin"],
            "vacation_temp": 15.0,
            "vacation_until": time.time() + 86400,
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=_presence_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["target_temp"] == 15.0  # vacation wins

    @pytest.mark.asyncio
    async def test_person_unavailable_treated_as_home(self, hass, mock_config_entry):
        """Unavailable person entity treated as home (fail-safe)."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "presence_enabled": True,
            "presence_persons": ["person.kevin"],
        }
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                person_states={"person.kevin": "unavailable"},
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["target_temp"] == 21.0  # comfort (fail-safe: home)
        assert room["presence_away"] is False

    @pytest.mark.asyncio
    async def test_person_entity_missing_treated_as_home(self, hass, mock_config_entry):
        """Missing person entity (None) treated as home (fail-safe)."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "presence_enabled": True,
            "presence_persons": ["person.nonexistent"],
        }
        hass.data = {"roommind": {"store": store}}

        # person.nonexistent not in any dict -> returns None (fail-safe: treated as home)
        hass.states.get = MagicMock(side_effect=make_mock_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["target_temp"] == 21.0  # comfort (fail-safe)

    @pytest.mark.asyncio
    async def test_per_room_persons_away(self, hass, mock_config_entry):
        """Room with assigned persons uses eco when all assigned are away."""
        room_with_presence = {
            **SAMPLE_ROOM,
            "presence_persons": ["person.anna"],
        }
        store = _make_store_mock({"living_room_abc12345": room_with_presence})
        store.get_settings.return_value = {
            "presence_enabled": True,
            "presence_persons": ["person.kevin", "person.anna"],
        }
        hass.data = {"roommind": {"store": store}}
        # kevin is home, anna is away
        hass.states.get = MagicMock(side_effect=_presence_states_get("person.kevin"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["target_temp"] == 17.0  # eco (anna is away)
        assert room["presence_away"] is True

    @pytest.mark.asyncio
    async def test_per_room_person_home_others_away(self, hass, mock_config_entry):
        """Room with assigned person uses schedule when that person is home."""
        room_with_presence = {
            **SAMPLE_ROOM,
            "presence_persons": ["person.anna"],
        }
        store = _make_store_mock({"living_room_abc12345": room_with_presence})
        store.get_settings.return_value = {
            "presence_enabled": True,
            "presence_persons": ["person.kevin", "person.anna"],
        }
        hass.data = {"roommind": {"store": store}}
        # anna is home, kevin is away
        hass.states.get = MagicMock(side_effect=_presence_states_get("person.anna"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["target_temp"] == 21.0  # comfort (anna is home)
        assert room["presence_away"] is False

    @pytest.mark.asyncio
    async def test_per_room_multi_person_one_home(self, hass, mock_config_entry):
        """Room with 2 assigned persons heats if at least one is home."""
        room_with_presence = {
            **SAMPLE_ROOM,
            "presence_persons": ["person.kevin", "person.anna"],
        }
        store = _make_store_mock({"living_room_abc12345": room_with_presence})
        store.get_settings.return_value = {
            "presence_enabled": True,
            "presence_persons": ["person.kevin", "person.anna"],
        }
        hass.data = {"roommind": {"store": store}}
        # only anna is home
        hass.states.get = MagicMock(side_effect=_presence_states_get("person.anna"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["target_temp"] == 21.0  # comfort (anna is home)
        assert room["presence_away"] is False

    @pytest.mark.asyncio
    async def test_presence_disabled_no_effect(self, hass, mock_config_entry):
        """When presence_enabled is False, presence has no effect."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "presence_enabled": False,
            "presence_persons": ["person.kevin"],
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=_presence_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["target_temp"] == 21.0  # comfort (presence disabled)
        assert room["presence_away"] is False

    @pytest.mark.asyncio
    async def test_ignore_presence_uses_comfort(self, hass, mock_config_entry):
        """Room with ignore_presence=True stays at comfort even when all persons are away."""
        room_ignore = {**SAMPLE_ROOM, "ignore_presence": True}
        store = _make_store_mock({"living_room_abc12345": room_ignore})
        store.get_settings.return_value = {
            "presence_enabled": True,
            "presence_persons": ["person.kevin", "person.anna"],
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=_presence_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["target_temp"] == 21.0  # comfort, not eco
        assert room["presence_away"] is False

    @pytest.mark.asyncio
    async def test_ignore_presence_prevents_force_off(self, hass, mock_config_entry):
        """Room with ignore_presence=True is not forced off even with presence_away_action=off."""
        room_ignore = {**SAMPLE_ROOM, "ignore_presence": True}
        store = _make_store_mock({"living_room_abc12345": room_ignore})
        store.get_settings.return_value = {
            "presence_enabled": True,
            "presence_persons": ["person.kevin"],
            "presence_away_action": "off",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=_presence_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["target_temp"] == 21.0  # comfort, not None
        assert room["force_off"] is False
        assert room["presence_away"] is False

    @pytest.mark.asyncio
    async def test_ignore_presence_false_still_uses_eco(self, hass, mock_config_entry):
        """Room with ignore_presence=False behaves normally (eco when away)."""
        room_no_ignore = {**SAMPLE_ROOM, "ignore_presence": False}
        store = _make_store_mock({"living_room_abc12345": room_no_ignore})
        store.get_settings.return_value = {
            "presence_enabled": True,
            "presence_persons": ["person.kevin"],
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=_presence_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["target_temp"] == 17.0  # eco_temp
        assert room["presence_away"] is True

    @pytest.mark.asyncio
    async def test_presence_away_action_off_forces_idle(self, hass, mock_config_entry):
        """When presence_away_action is 'off', devices are turned off (target=None, force_off=True)."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "presence_enabled": True,
            "presence_persons": ["person.kevin"],
            "presence_away_action": "off",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=_presence_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["target_temp"] is None
        assert room["mode"] == "idle"
        assert room["force_off"] is True
        assert room["presence_away"] is True

    @pytest.mark.asyncio
    async def test_presence_away_action_eco_backward_compat(self, hass, mock_config_entry):
        """When presence_away_action is 'eco' (default), eco_temp is used."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "presence_enabled": True,
            "presence_persons": ["person.kevin"],
            "presence_away_action": "eco",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=_presence_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["target_temp"] == 17.0  # eco_temp
        assert room["force_off"] is False

    @pytest.mark.asyncio
    async def test_override_beats_force_off(self, hass, mock_config_entry):
        """Manual override takes priority even when presence_away_action is 'off'."""
        room_with_override = {
            **SAMPLE_ROOM,
            "override_temp": 25.0,
            "override_until": time.time() + 3600,
            "override_type": "boost",
        }
        store = _make_store_mock({"living_room_abc12345": room_with_override})
        store.get_settings.return_value = {
            "presence_enabled": True,
            "presence_persons": ["person.kevin"],
            "presence_away_action": "off",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=_presence_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["target_temp"] == 25.0  # override wins
        assert room["force_off"] is False
