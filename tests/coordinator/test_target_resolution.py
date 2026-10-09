"""Tests for override/vacation/presence/schedule priority chain."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.climate import HVACMode

from custom_components.roommind.climate import OVERRIDE_TURN_ON_REFRESH_DELAY_S, RoomMindOverrideClimate

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


AC_ROOM_KEY = "living_room_abc12345"
AC_ROOM = {
    **SAMPLE_ROOM,
    "thermostats": [],
    "acs": ["climate.living_room"],
    "devices": [{"entity_id": "climate.living_room", "type": "ac", "role": "auto", "heating_system_type": ""}],
    "schedules": [],
}


class TestPendingOverrideSeed:
    """A just-seeded override (entity turned on) is not evaluated until the real values arrive (#447)."""

    @staticmethod
    async def _tick(hass, mock_config_entry, room, seeded_age=None):
        store = _make_store_mock({AC_ROOM_KEY: room}, settings={"outdoor_cooling_min": 10})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp=24.6, outdoor_temp=8.0, schedule_state="off"))
        hass.services.async_call = AsyncMock()
        coordinator = _create_coordinator(hass, mock_config_entry)
        if seeded_age is not None:
            coordinator._override_seeded_at[AC_ROOM_KEY] = time.monotonic() - seeded_age
        data = await coordinator._async_update_data()
        return coordinator, data["rooms"][AC_ROOM_KEY]

    SEED = {
        "override_heat": 22.5,
        "override_cool": 24.0,
        "override_until": None,
        "override_type": "custom",
    }

    @pytest.mark.asyncio
    async def test_tick_before_real_values_ignores_seed_and_keeps_gate(self, hass, mock_config_entry):
        _, state = await self._tick(hass, mock_config_entry, {**AC_ROOM, **self.SEED}, seeded_age=0.5)
        assert state["override_active"] is False
        assert state["mode"] == "idle"
        assert state["commanded_mode"] == "idle"

    @pytest.mark.asyncio
    async def test_after_real_values_override_is_evaluated(self, hass, mock_config_entry):
        room = {**AC_ROOM, **self.SEED, "override_heat": 24.0, "override_cool": 28.5}
        coordinator, state = await self._tick(hass, mock_config_entry, room, seeded_age=0.5)
        coordinator.clear_override_seed(AC_ROOM_KEY)
        data = await coordinator._async_update_data()
        state = data["rooms"][AC_ROOM_KEY]
        assert state["override_active"] is True
        assert (state["heat_target"], state["cool_target"]) == (24.0, 28.5)
        assert state["mode"] == "idle"

    @pytest.mark.asyncio
    async def test_bare_turn_on_evaluates_seed_after_grace_period(self, hass, mock_config_entry):
        coordinator, state = await self._tick(hass, mock_config_entry, {**AC_ROOM, **self.SEED}, seeded_age=10.0)
        assert state["override_active"] is True
        assert (state["heat_target"], state["cool_target"]) == (22.5, 24.0)
        assert AC_ROOM_KEY not in coordinator._override_seeded_at

    def test_is_override_seed_pending_is_read_only_and_time_bound(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        assert coordinator.is_override_seed_pending(AC_ROOM_KEY) is False
        coordinator.note_override_seed(AC_ROOM_KEY)
        assert coordinator.is_override_seed_pending(AC_ROOM_KEY) is True
        coordinator._override_seeded_at[AC_ROOM_KEY] = time.monotonic() - OVERRIDE_TURN_ON_REFRESH_DELAY_S - 0.1
        assert coordinator.is_override_seed_pending(AC_ROOM_KEY) is False
        assert AC_ROOM_KEY in coordinator._override_seeded_at

    @staticmethod
    def _entity_with_real_coordinator(hass, mock_config_entry):
        room = {**AC_ROOM}
        store = _make_store_mock({AC_ROOM_KEY: room})

        async def update_room(_area, changes):
            room.update(changes)
            return room

        store.async_update_room = AsyncMock(side_effect=update_room)
        store.get_room = MagicMock(side_effect=lambda _a: room)
        hass.data = {"roommind": {"store": store}}
        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator.async_request_refresh = AsyncMock()
        coordinator.data = {"rooms": {AC_ROOM_KEY: {"heat_target": 19.0, "cool_target": 26.0}}}
        entity = RoomMindOverrideClimate(coordinator, AC_ROOM_KEY)
        entity.async_write_ha_state = MagicMock()
        return coordinator, entity, room

    @pytest.mark.asyncio
    async def test_second_turn_on_within_grace_keeps_seed_masked(self, hass, mock_config_entry):
        coordinator, entity, room = self._entity_with_real_coordinator(hass, mock_config_entry)
        with patch("custom_components.roommind.climate.async_call_later", return_value=MagicMock()) as later:
            await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)
            await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)

        assert later.call_count == 1
        assert AC_ROOM_KEY in coordinator._override_seeded_at
        assert coordinator._without_pending_override_seed(room)["override_heat"] is None
        coordinator.async_request_refresh.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_turn_on_on_older_override_unmasks_and_refreshes(self, hass, mock_config_entry):
        coordinator, entity, room = self._entity_with_real_coordinator(hass, mock_config_entry)
        room.update(override_heat=21.0, override_cool=24.0, override_until=None, override_type="custom")
        coordinator._override_seeded_at[AC_ROOM_KEY] = time.monotonic() - 60
        await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)

        assert AC_ROOM_KEY not in coordinator._override_seeded_at
        coordinator.async_request_refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_note_and_removal(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator.note_override_seed(AC_ROOM_KEY)
        assert AC_ROOM_KEY in coordinator._override_seeded_at
        coordinator.clear_override_seed(AC_ROOM_KEY)
        assert AC_ROOM_KEY not in coordinator._override_seeded_at
        coordinator.note_override_seed(AC_ROOM_KEY)
        coordinator.async_request_refresh = AsyncMock()
        hass.data = {"roommind": {"store": _make_store_mock()}}
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("homeassistant.helpers.entity_registry.async_get", lambda _h: MagicMock(entities={}))
            await coordinator.async_room_removed(AC_ROOM_KEY)
        assert AC_ROOM_KEY not in coordinator._override_seeded_at
