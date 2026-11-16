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
            "override_heat": 25.0,
            "override_cool": 25.0,
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
    async def test_presence_clears_override_when_enabled(self, hass, mock_config_entry):
        """presence_clears_override=True: presence-away suppresses active override (#306)."""
        room_with_override = {
            **SAMPLE_ROOM,
            "override_heat": 25.0,
            "override_cool": 25.0,
            "override_until": time.time() + 3600,
            "override_type": "boost",
        }
        store = _make_store_mock({"living_room_abc12345": room_with_override})
        store.get_settings.return_value = {
            "presence_enabled": True,
            "presence_persons": ["person.kevin"],
            "presence_clears_override": True,
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=_presence_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["target_temp"] == 17.0  # eco_temp, override suppressed
        assert room["override_active"] is True
        assert room["override_suppressed"] is True
        assert room["presence_away"] is True

    @pytest.mark.asyncio
    async def test_presence_clears_override_respects_ignore_presence(self, hass, mock_config_entry):
        """ignore_presence=True per room: override stays in effect even with setting on."""
        room_with_override = {
            **SAMPLE_ROOM,
            "override_heat": 25.0,
            "override_cool": 25.0,
            "override_until": time.time() + 3600,
            "override_type": "boost",
            "ignore_presence": True,
        }
        store = _make_store_mock({"living_room_abc12345": room_with_override})
        store.get_settings.return_value = {
            "presence_enabled": True,
            "presence_persons": ["person.kevin"],
            "presence_clears_override": True,
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=_presence_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["target_temp"] == 25.0  # override still wins
        assert room["override_active"] is True
        assert room["override_suppressed"] is False

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
    async def test_person_entity_missing_treated_as_home(self, hass, mock_config_entry, monkeypatch):
        """Missing person entity (None) treated as home (fail-safe)."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "presence_enabled": True,
            "presence_persons": ["person.nonexistent"],
        }
        hass.data = {"roommind": {"store": store}}
        hass.is_running = True
        # The entity is gone for good: not in the state machine, not registered.
        registry = MagicMock()
        registry.async_get = MagicMock(return_value=None)
        monkeypatch.setattr(
            "custom_components.roommind.utils.presence_utils.er.async_get",
            lambda _hass: registry,
        )

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
    async def test_presence_away_action_off_overrides_fan_only_idle(self, hass, mock_config_entry):
        """presence_away_action='off' turns a fan_only AC off instead of running the fan (#368)."""
        room_cfg = {
            **SAMPLE_ROOM,
            "thermostats": [],
            "acs": ["climate.living_room_ac"],
            "devices": [
                {
                    "entity_id": "climate.living_room_ac",
                    "type": "ac",
                    "role": "auto",
                    "heating_system_type": "",
                    "idle_action": "fan_only",
                    "idle_fan_mode": "low",
                }
            ],
        }
        store = _make_store_mock(
            {"living_room_abc12345": room_cfg},
            settings={
                "presence_enabled": True,
                "presence_persons": ["person.kevin"],
                "presence_away_action": "off",
            },
        )
        hass.data = {"roommind": {"store": store}}

        ac_state = MagicMock()
        ac_state.state = "cool"
        ac_state.attributes = {
            "hvac_modes": ["off", "cool", "fan_only"],
            "fan_modes": ["low", "high"],
            "current_temperature": 23.0,
            "temperature": 23.0,
        }
        base_mock = _presence_states_get()

        def custom_get(eid):
            if eid == "climate.living_room_ac":
                return ac_state
            return base_mock(eid)

        hass.states.get = MagicMock(side_effect=custom_get)
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        assert data["rooms"]["living_room_abc12345"]["force_off"] is True
        climate_calls = [c for c in hass.services.async_call.call_args_list if c[0][0] == "climate"]
        hvac_calls = [c for c in climate_calls if c[0][1] == "set_hvac_mode"]
        assert any(c[0][2].get("hvac_mode") == "off" for c in hvac_calls)
        assert not any(c[0][2].get("hvac_mode") == "fan_only" for c in hvac_calls)
        assert not any(c[0][1] == "set_fan_mode" for c in climate_calls)

    @pytest.mark.asyncio
    async def test_override_beats_force_off(self, hass, mock_config_entry):
        """Manual override takes priority even when presence_away_action is 'off'."""
        room_with_override = {
            **SAMPLE_ROOM,
            "override_heat": 25.0,
            "override_cool": 25.0,
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


class TestOverrideUntilNextChange:
    """An override held until the next change ends once presence switches (home <-> away)."""

    @staticmethod
    def _room(presence_away_at_set):
        return {
            **SAMPLE_ROOM,
            "override_heat": 25.0,
            "override_cool": 25.0,
            "override_until": time.time() + 3600,
            "override_type": "boost",
            "override_presence_away": presence_away_at_set,
        }

    async def _run(self, hass, mock_config_entry, room, *persons_home):
        store = _make_store_mock({"living_room_abc12345": room})
        store.get_settings.return_value = {"presence_enabled": True, "presence_persons": ["person.kevin"]}
        store.async_update_room = AsyncMock()
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=_presence_states_get(*persons_home))
        hass.services.async_call = AsyncMock()
        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()
        return data["rooms"]["living_room_abc12345"], store

    @pytest.mark.asyncio
    async def test_set_at_home_ends_when_everyone_leaves(self, hass, mock_config_entry):
        live, store = await self._run(hass, mock_config_entry, self._room(False))
        assert live["target_temp"] == 17.0  # eco: presence away, override gone
        assert live["override_active"] is False
        store.async_update_room.assert_any_call(
            "living_room_abc12345",
            {
                "override_heat": None,
                "override_cool": None,
                "override_until": None,
                "override_type": None,
                "override_presence_away": None,
            },
        )

    @pytest.mark.asyncio
    async def test_set_while_away_ends_when_someone_comes_home(self, hass, mock_config_entry):
        live, store = await self._run(hass, mock_config_entry, self._room(True), "person.kevin")
        assert live["target_temp"] == 21.0  # back to the schedule
        assert live["override_active"] is False
        store.async_update_room.assert_called()

    @pytest.mark.asyncio
    async def test_holds_while_presence_stays(self, hass, mock_config_entry):
        live, store = await self._run(hass, mock_config_entry, self._room(False), "person.kevin")
        assert live["target_temp"] == 25.0
        assert live["override_active"] is True
        assert live["override_ends_on_presence"] is True
        store.async_update_room.assert_not_called()

    @pytest.mark.asyncio
    async def test_timed_override_ignores_presence(self, hass, mock_config_entry):
        live, store = await self._run(hass, mock_config_entry, self._room(None))
        assert live["target_temp"] == 25.0  # override beats presence as before
        assert live["override_ends_on_presence"] is False
        store.async_update_room.assert_not_called()

    @pytest.mark.asyncio
    async def test_room_ignoring_presence_keeps_override(self, hass, mock_config_entry):
        room = {**self._room(False), "ignore_presence": True}
        live, store = await self._run(hass, mock_config_entry, room)
        assert live["target_temp"] == 25.0
        store.async_update_room.assert_not_called()
