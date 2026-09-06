"""Tests for schedule resolution, multi-scheduler, schedule entity logic, off_action."""

from __future__ import annotations

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
    async def test_update_schedule_off_uses_eco_temp(self, hass, mock_config_entry):
        """Test that schedule 'off' uses eco_temp as target."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(side_effect=make_mock_states_get(schedule_state="off"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        # eco_temp is 17.0, current is 18.0 -> above target
        # With auto mode and no ACs, can't cool -> idle
        assert room_state["target_temp"] == 17.0
        assert room_state["mode"] == "idle"

    @pytest.mark.asyncio
    async def test_update_schedule_on_with_block_temp(self, hass, mock_config_entry):
        """Test that schedule 'on' with temperature attribute uses block temp."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(side_effect=make_mock_states_get(schedule_attrs={"temperature": 23.0}))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["target_temp"] == 23.0
        assert room_state["mode"] == "heating"

    @pytest.mark.asyncio
    async def test_update_no_schedule_entity_uses_comfort(self, hass, mock_config_entry):
        """Test that empty schedules uses comfort_temp as constant target."""
        room_no_schedule = {
            "area_id": "bedroom_abc12345",
            "thermostats": ["climate.bedroom"],
            "acs": [],
            "devices": [{"entity_id": "climate.bedroom", "type": "trv", "role": "auto", "heating_system_type": ""}],
            "temperature_sensor": "sensor.bedroom_temp",
            "climate_mode": "auto",
            "schedules": [],
            "schedule_selector_entity": "",
            "comfort_temp": 21.0,
            "eco_temp": 17.0,
        }
        store = _make_store_mock({"bedroom_abc12345": room_no_schedule})
        hass.data = {"roommind": {"store": store}}

        def mock_states_get(entity_id):
            if entity_id == "sensor.bedroom_temp":
                sensor_state = MagicMock()
                sensor_state.state = "18.0"
                return sensor_state
            if entity_id == "sensor.living_room_humidity":
                sensor_state = MagicMock()
                sensor_state.state = "55.0"
                return sensor_state
            return None

        hass.states.get = MagicMock(side_effect=mock_states_get)
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["bedroom_abc12345"]
        assert room_state["target_temp"] == 21.0
        assert room_state["mode"] == "heating"

    @pytest.mark.asyncio
    async def test_get_active_schedule_index_no_selector(self, hass, mock_config_entry):
        """With 2 schedules and no selector, returns 0."""
        room = {
            **SAMPLE_ROOM,
            "schedules": [
                {"entity_id": "schedule.morning"},
                {"entity_id": "schedule.evening"},
            ],
            "schedule_selector_entity": "",
        }
        coordinator = _create_coordinator(hass, mock_config_entry)
        assert coordinator._get_active_schedule_index(room) == 0

    @pytest.mark.asyncio
    async def test_get_active_schedule_index_input_boolean_on(self, hass, mock_config_entry):
        """With input_boolean 'on', returns 1."""
        room = {
            **SAMPLE_ROOM,
            "schedules": [
                {"entity_id": "schedule.morning"},
                {"entity_id": "schedule.evening"},
            ],
            "schedule_selector_entity": "input_boolean.schedule_toggle",
        }
        toggle_state = MagicMock()
        toggle_state.state = "on"
        hass.states.get = MagicMock(return_value=toggle_state)

        coordinator = _create_coordinator(hass, mock_config_entry)
        assert coordinator._get_active_schedule_index(room) == 1

    @pytest.mark.asyncio
    async def test_get_active_schedule_index_input_boolean_off(self, hass, mock_config_entry):
        """With input_boolean 'off', returns 0."""
        room = {
            **SAMPLE_ROOM,
            "schedules": [
                {"entity_id": "schedule.morning"},
                {"entity_id": "schedule.evening"},
            ],
            "schedule_selector_entity": "input_boolean.schedule_toggle",
        }
        toggle_state = MagicMock()
        toggle_state.state = "off"
        hass.states.get = MagicMock(return_value=toggle_state)

        coordinator = _create_coordinator(hass, mock_config_entry)
        assert coordinator._get_active_schedule_index(room) == 0

    @pytest.mark.asyncio
    async def test_get_active_schedule_index_input_number(self, hass, mock_config_entry):
        """With input_number '2' and 3 schedules, returns 1 (1-based to 0-based)."""
        room = {
            **SAMPLE_ROOM,
            "schedules": [
                {"entity_id": "schedule.a"},
                {"entity_id": "schedule.b"},
                {"entity_id": "schedule.c"},
            ],
            "schedule_selector_entity": "input_number.schedule_selector",
        }
        number_state = MagicMock()
        number_state.state = "2"
        hass.states.get = MagicMock(return_value=number_state)

        coordinator = _create_coordinator(hass, mock_config_entry)
        assert coordinator._get_active_schedule_index(room) == 1

    @pytest.mark.asyncio
    async def test_get_active_schedule_index_input_number_out_of_range(self, hass, mock_config_entry):
        """With input_number '5' and 3 schedules, returns -1 (out of range)."""
        room = {
            **SAMPLE_ROOM,
            "schedules": [
                {"entity_id": "schedule.a"},
                {"entity_id": "schedule.b"},
                {"entity_id": "schedule.c"},
            ],
            "schedule_selector_entity": "input_number.schedule_selector",
        }
        number_state = MagicMock()
        number_state.state = "5"
        hass.states.get = MagicMock(return_value=number_state)

        coordinator = _create_coordinator(hass, mock_config_entry)
        assert coordinator._get_active_schedule_index(room) == -1

    @pytest.mark.asyncio
    async def test_get_active_schedule_index_no_schedules(self, hass, mock_config_entry):
        """With empty schedules, returns -1."""
        room = {
            **SAMPLE_ROOM,
            "schedules": [],
            "schedule_selector_entity": "",
        }
        coordinator = _create_coordinator(hass, mock_config_entry)
        assert coordinator._get_active_schedule_index(room) == -1

    @pytest.mark.asyncio
    async def test_multi_schedule_selects_correct_entity(self, hass, mock_config_entry):
        """Full integration: 2 schedules, selector selects #2, uses second entity."""
        room = {
            **SAMPLE_ROOM,
            "schedules": [
                {"entity_id": "schedule.morning"},
                {"entity_id": "schedule.evening"},
            ],
            "schedule_selector_entity": "input_boolean.schedule_toggle",
        }
        store = _make_store_mock({"living_room_abc12345": room})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                selector_state="on",
                extra={
                    "schedule.evening": ("on", {"temperature": 19.0}),
                    "schedule.morning": ("on", {"temperature": 23.0}),
                },
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        # Selector is "on" -> index 1 -> schedule.evening -> block temp 19.0
        assert room_state["target_temp"] == 19.0

    @pytest.mark.asyncio
    async def test_process_room_returns_active_schedule_index(self, hass, mock_config_entry):
        """Verify active_schedule_index is in the room state result."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(side_effect=make_mock_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert "active_schedule_index" in room_state
        assert room_state["active_schedule_index"] == 0


class TestCoverageGaps:
    """Tests covering uncovered coordinator lines."""

    @pytest.mark.asyncio
    async def test_schedule_split_heat_cool_temps(self, hass, mock_config_entry):
        """Schedule with split heat/cool temperatures read from schedule.get_schedule.

        HA does not expose heat_temperature/cool_temperature as entity state attributes,
        so the fix reads them from block data via schedule.get_schedule instead.
        """
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                schedule_state="on",
                schedule_attrs={},  # No heat/cool attrs — HA does not expose these
            )
        )

        all_day_block = {
            "from": "00:00:00",
            "to": "23:59:59",
            "data": {"heat_temperature": 20.0, "cool_temperature": 25.0},
        }
        schedule_data = {
            day: [all_day_block]
            for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        }

        async def mock_service_call(domain, service, data=None, **kwargs):
            if domain == "schedule" and service == "get_schedule":
                eid = (data or {}).get("entity_id", "")
                return {eid: schedule_data}
            return None

        hass.services.async_call = AsyncMock(side_effect=mock_service_call)

        coordinator = _create_coordinator(hass, mock_config_entry)
        result = await coordinator._async_update_data()

        room = result["rooms"]["living_room_abc12345"]
        assert room["heat_target"] == 20.0
        assert room["cool_target"] == 25.0

    @pytest.mark.asyncio
    async def test_schedule_single_temperature_via_blocks(self, hass, mock_config_entry):
        """Single temperature field in block data also works via schedule.get_schedule."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(schedule_state="on", schedule_attrs={}))

        all_day_block = {"from": "00:00:00", "to": "23:59:59", "data": {"temperature": 22.5}}
        schedule_data = {
            day: [all_day_block]
            for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        }

        async def mock_service_call(domain, service, data=None, **kwargs):
            if domain == "schedule" and service == "get_schedule":
                eid = (data or {}).get("entity_id", "")
                return {eid: schedule_data}
            return None

        hass.services.async_call = AsyncMock(side_effect=mock_service_call)

        coordinator = _create_coordinator(hass, mock_config_entry)
        result = await coordinator._async_update_data()

        room = result["rooms"]["living_room_abc12345"]
        assert room["heat_target"] == 22.5
        assert room["cool_target"] == 22.5

    @pytest.mark.asyncio
    async def test_schedule_entity_unavailable_uses_comfort(self, hass, mock_config_entry):
        """Unavailable schedule entity falls back to comfort temp."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                schedule_state="unavailable",
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["target_temp"] == 21.0  # comfort_temp

    @pytest.mark.asyncio
    async def test_schedule_empty_entity_id_uses_comfort(self, hass, mock_config_entry):
        """Empty schedule entity_id uses comfort temp."""
        room_empty_schedule = {
            **SAMPLE_ROOM,
            "schedules": [{"entity_id": ""}],
        }
        store = _make_store_mock({"living_room_abc12345": room_empty_schedule})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["target_temp"] == 21.0

    @pytest.mark.asyncio
    async def test_schedule_invalid_block_temp_uses_comfort(self, hass, mock_config_entry):
        """Invalid (non-numeric) block temp falls back to comfort."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                schedule_attrs={"temperature": "not_a_number"},
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["target_temp"] == 21.0

    @pytest.mark.asyncio
    async def test_schedule_heat_cool_temp_parse_error(self, hass, mock_config_entry):
        """ValueError in heat_temperature/cool_temperature parsing falls back to comfort temps."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                schedule_state="on",
                schedule_attrs={
                    "heat_temperature": "bad_value",
                    "cool_temperature": "also_bad",
                },
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        result = await coordinator._async_update_data()
        assert result is not None
        # Room should still have a valid target -- comfort temps used as fallback
        room_state = result["rooms"]["living_room_abc12345"]
        assert room_state["target_temp"] == 21.0  # comfort_temp fallback


class TestPresenceDetection:
    """Tests for schedule off_action."""

    @pytest.mark.asyncio
    async def test_schedule_off_action_off_forces_idle(self, hass, mock_config_entry):
        """When schedule_off_action is 'off' and schedule is off, devices are turned off."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "schedule_off_action": "off",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                schedule_state="off",
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["target_temp"] is None
        assert room["mode"] == "idle"
        assert room["force_off"] is True

    @pytest.mark.asyncio
    async def test_schedule_off_action_eco_backward_compat(self, hass, mock_config_entry):
        """When schedule_off_action is 'eco' (default), eco_temp is used."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "schedule_off_action": "eco",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                schedule_state="off",
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["target_temp"] == 17.0  # eco_temp
        assert room["force_off"] is False

    @pytest.mark.asyncio
    async def test_schedule_off_action_off_overrides_fan_only_idle(self, hass, mock_config_entry):
        """schedule_off_action='off' turns a fan_only AC off instead of running the fan (#368)."""
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
            settings={"schedule_off_action": "off"},
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
        base_mock = make_mock_states_get(schedule_state="off")

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


class TestScheduleServiceFailureRecovery:
    """#308: a transient schedule.get_schedule failure must not silently jump
    the target back to comfort_heat when the schedule has data.temperature
    blocks. The coordinator caches the last good blocks per entity."""

    @pytest.mark.asyncio
    async def test_target_survives_transient_service_failure(self, hass, mock_config_entry):
        room = {
            **SAMPLE_ROOM,
            "climate_mode": "heat_only",
            "comfort_heat": 20.0,
            "comfort_temp": 20.0,
            "eco_heat": 15.0,
            "eco_temp": 15.0,
        }
        store = _make_store_mock({"living_room_abc12345": room})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(schedule_state="on", schedule_attrs={}))

        all_day_block = {
            "from": "00:00:00",
            "to": "23:59:59",
            "data": {"temperature": 17.5},
        }
        schedule_data = {
            day: [all_day_block]
            for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        }

        call_state = {"count": 0}

        async def flaky_service(domain, service, data=None, **kwargs):
            if domain == "schedule" and service == "get_schedule":
                call_state["count"] += 1
                if call_state["count"] == 1:
                    eid = (data or {}).get("entity_id", "")
                    return {eid: schedule_data}
                raise RuntimeError("simulated transient HA failure")
            return None

        hass.services.async_call = AsyncMock(side_effect=flaky_service)

        coordinator = _create_coordinator(hass, mock_config_entry)

        result1 = await coordinator._async_update_data()
        assert result1["rooms"]["living_room_abc12345"]["target_temp"] == 17.5

        result2 = await coordinator._async_update_data()
        room2 = result2["rooms"]["living_room_abc12345"]
        assert room2["target_temp"] == 17.5  # cached fallback kept us on the block temp
        assert room2["target_temp"] != 20.0  # would be comfort_heat without the cache (bug)


class TestScheduleEntityUnavailableFallback:
    """#308 follow-up: when the schedule entity state flickers to
    unavailable/unknown, target must not silently jump to comfort_heat.
    Prefer cached blocks if present; treat as schedule-off when outside
    any block; fall back to comfort_heat only when no cache is available."""

    @staticmethod
    def _all_day_schedule(temperature: float) -> dict:
        block = {
            "from": "00:00:00",
            "to": "23:59:59",
            "data": {"temperature": temperature},
        }
        return {day: [block] for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]}

    @pytest.mark.asyncio
    async def test_state_unavailable_uses_cached_block_temp(self, hass, mock_config_entry):
        """State briefly 'unavailable' but cached block active -> block temp wins."""
        room = {
            **SAMPLE_ROOM,
            "climate_mode": "heat_only",
            "comfort_heat": 20.0,
            "comfort_temp": 20.0,
            "eco_heat": 15.0,
            "eco_temp": 15.0,
        }
        store = _make_store_mock({"living_room_abc12345": room})
        hass.data = {"roommind": {"store": store}}

        schedule_data = self._all_day_schedule(17.5)
        call_state = {"count": 0}

        async def service_with_one_success(domain, service, data=None, **kwargs):
            if domain == "schedule" and service == "get_schedule":
                call_state["count"] += 1
                eid = (data or {}).get("entity_id", "")
                return {eid: schedule_data}
            return None

        hass.services.async_call = AsyncMock(side_effect=service_with_one_success)

        # First cycle: schedule "on" -> cache primed
        hass.states.get = MagicMock(side_effect=make_mock_states_get(schedule_state="on"))
        coordinator = _create_coordinator(hass, mock_config_entry)
        result1 = await coordinator._async_update_data()
        assert result1["rooms"]["living_room_abc12345"]["target_temp"] == 17.5

        # Second cycle: schedule entity flickers to "unavailable"
        # Without the fix: target would jump to comfort_heat (20.0).
        # With the fix: cached block keeps target at 17.5.
        hass.states.get = MagicMock(side_effect=make_mock_states_get(schedule_state="unavailable"))
        result2 = await coordinator._async_update_data()
        assert result2["rooms"]["living_room_abc12345"]["target_temp"] == 17.5

    @pytest.mark.asyncio
    async def test_state_unknown_uses_cached_block_temp(self, hass, mock_config_entry):
        """State 'unknown' behaves like 'unavailable' for fallback purposes."""
        room = {
            **SAMPLE_ROOM,
            "climate_mode": "heat_only",
            "comfort_heat": 20.0,
            "comfort_temp": 20.0,
            "eco_heat": 15.0,
            "eco_temp": 15.0,
        }
        store = _make_store_mock({"living_room_abc12345": room})
        hass.data = {"roommind": {"store": store}}

        schedule_data = self._all_day_schedule(16.0)

        async def get_schedule(domain, service, data=None, **kwargs):
            if domain == "schedule" and service == "get_schedule":
                eid = (data or {}).get("entity_id", "")
                return {eid: schedule_data}
            return None

        hass.services.async_call = AsyncMock(side_effect=get_schedule)

        hass.states.get = MagicMock(side_effect=make_mock_states_get(schedule_state="on"))
        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        hass.states.get = MagicMock(side_effect=make_mock_states_get(schedule_state="unknown"))
        result = await coordinator._async_update_data()
        assert result["rooms"]["living_room_abc12345"]["target_temp"] == 16.0

    @pytest.mark.asyncio
    async def test_state_unavailable_outside_block_falls_back_to_eco(self, hass, mock_config_entry):
        """State unavailable + cached blocks but no block at 'now' -> eco_heat (schedule_off_action='eco')."""
        room = {
            **SAMPLE_ROOM,
            "climate_mode": "heat_only",
            "comfort_heat": 20.0,
            "comfort_temp": 20.0,
            "eco_heat": 15.0,
            "eco_temp": 15.0,
        }
        store = _make_store_mock({"living_room_abc12345": room})
        hass.data = {"roommind": {"store": store}}

        # Empty schedule: no blocks for any day -> find_active_block always returns None
        empty_schedule = {
            day: [] for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        }

        async def get_schedule(domain, service, data=None, **kwargs):
            if domain == "schedule" and service == "get_schedule":
                eid = (data or {}).get("entity_id", "")
                return {eid: empty_schedule}
            return None

        hass.services.async_call = AsyncMock(side_effect=get_schedule)

        # Prime the cache via a normal "on" cycle
        hass.states.get = MagicMock(side_effect=make_mock_states_get(schedule_state="on"))
        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        # State flickers to unavailable, no block at now -> eco_heat
        hass.states.get = MagicMock(side_effect=make_mock_states_get(schedule_state="unavailable"))
        result = await coordinator._async_update_data()
        assert result["rooms"]["living_room_abc12345"]["target_temp"] == 15.0

    @pytest.mark.asyncio
    async def test_state_unavailable_no_cache_falls_back_to_comfort(self, hass, mock_config_entry):
        """State unavailable AND no cached blocks (first cycle after restart) -> comfort_heat.

        This preserves the original behavior as a last-resort fallback when there
        is genuinely no signal about the schedule.
        """
        room = {
            **SAMPLE_ROOM,
            "climate_mode": "heat_only",
            "comfort_heat": 22.0,
            "comfort_temp": 22.0,
            "eco_heat": 15.0,
            "eco_temp": 15.0,
        }
        store = _make_store_mock({"living_room_abc12345": room})
        hass.data = {"roommind": {"store": store}}

        # Service always fails: nothing ever lands in the cache
        hass.services.async_call = AsyncMock(side_effect=RuntimeError("schedule service down"))
        hass.states.get = MagicMock(side_effect=make_mock_states_get(schedule_state="unavailable"))

        coordinator = _create_coordinator(hass, mock_config_entry)
        result = await coordinator._async_update_data()
        assert result["rooms"]["living_room_abc12345"]["target_temp"] == 22.0

    @pytest.mark.asyncio
    async def test_state_unavailable_outside_block_off_action_force_off(self, hass, mock_config_entry):
        """State unavailable + cached blocks but no block + schedule_off_action='off' -> force_off."""
        room = {
            **SAMPLE_ROOM,
            "climate_mode": "heat_only",
            "comfort_heat": 20.0,
            "comfort_temp": 20.0,
            "eco_heat": 15.0,
            "eco_temp": 15.0,
        }
        store = _make_store_mock(
            {"living_room_abc12345": room},
            settings={"schedule_off_action": "off"},
        )
        hass.data = {"roommind": {"store": store}}

        empty_schedule = {
            day: [] for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        }

        async def get_schedule(domain, service, data=None, **kwargs):
            if domain == "schedule" and service == "get_schedule":
                eid = (data or {}).get("entity_id", "")
                return {eid: empty_schedule}
            return None

        hass.services.async_call = AsyncMock(side_effect=get_schedule)

        hass.states.get = MagicMock(side_effect=make_mock_states_get(schedule_state="on"))
        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        hass.states.get = MagicMock(side_effect=make_mock_states_get(schedule_state="unavailable"))
        result = await coordinator._async_update_data()
        room_state = result["rooms"]["living_room_abc12345"]
        assert room_state["force_off"] is True
        assert room_state["mode"] == "idle"


class TestOutOfRangeScheduleTemps:
    """Out-of-range schedule block temps are ignored in the live control path (#395)."""

    @staticmethod
    def _all_day_schedule(data: dict) -> dict:
        block = {"from": "00:00:00", "to": "23:59:59", "data": data}
        return {day: [block] for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]}

    @classmethod
    def _mock_get_schedule(cls, data: dict):
        schedule_data = cls._all_day_schedule(data)

        async def _call(domain, service, call_data=None, **kwargs):
            if domain == "schedule" and service == "get_schedule":
                eid = (call_data or {}).get("entity_id", "")
                return {eid: schedule_data}
            return None

        return AsyncMock(side_effect=_call)

    @pytest.mark.asyncio
    async def test_block_temp_typo_does_not_trigger_heating(self, hass, mock_config_entry):
        """#395: `temperature: 110` must not make a 22°C room heat towards 110°C."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}
        # Room is already warmer than comfort_temp (21), so heating only happens
        # if the bogus 110 target is accepted.
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(temp="22.0", schedule_state="on", schedule_attrs={})
        )
        hass.services.async_call = self._mock_get_schedule({"temperature": 110})

        coordinator = _create_coordinator(hass, mock_config_entry)
        result = await coordinator._async_update_data()

        room = result["rooms"]["living_room_abc12345"]
        assert room["target_temp"] == 21.0
        assert room["mode"] != "heating"

    @pytest.mark.asyncio
    async def test_block_temp_in_range_still_applies(self, hass, mock_config_entry):
        """A plausible block temp is still honoured (guard is not over-eager)."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(schedule_state="on", schedule_attrs={}))
        hass.services.async_call = self._mock_get_schedule({"temperature": 11})

        coordinator = _create_coordinator(hass, mock_config_entry)
        result = await coordinator._async_update_data()

        assert result["rooms"]["living_room_abc12345"]["target_temp"] == 11.0

    @pytest.mark.asyncio
    async def test_split_heat_out_of_range_falls_back(self, hass, mock_config_entry):
        """Out-of-range heat_temperature falls back to comfort_heat, cool is kept."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(schedule_state="on", schedule_attrs={}))
        hass.services.async_call = self._mock_get_schedule({"heat_temperature": 200.0, "cool_temperature": 25.0})

        coordinator = _create_coordinator(hass, mock_config_entry)
        result = await coordinator._async_update_data()

        room = result["rooms"]["living_room_abc12345"]
        assert room["heat_target"] == 21.0
        assert room["cool_target"] == 25.0

    @pytest.mark.asyncio
    async def test_split_cool_out_of_range_falls_back(self, hass, mock_config_entry):
        """Out-of-range cool_temperature falls back to comfort_cool, heat is kept."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(schedule_state="on", schedule_attrs={}))
        hass.services.async_call = self._mock_get_schedule({"heat_temperature": 20.0, "cool_temperature": -40.0})

        coordinator = _create_coordinator(hass, mock_config_entry)
        result = await coordinator._async_update_data()

        room = result["rooms"]["living_room_abc12345"]
        assert room["heat_target"] == 20.0
        assert room["cool_target"] == 24.0

    @pytest.mark.asyncio
    async def test_attribute_fallback_path_is_guarded(self, hass, mock_config_entry):
        """The state-attribute branch (no schedule.get_schedule) is guarded too."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(schedule_attrs={"temperature": 110}))
        hass.services.async_call = AsyncMock(return_value=None)

        coordinator = _create_coordinator(hass, mock_config_entry)
        result = await coordinator._async_update_data()

        assert result["rooms"]["living_room_abc12345"]["target_temp"] == 21.0

    @pytest.mark.asyncio
    async def test_warning_logged_once_per_value(self, hass, mock_config_entry, caplog):
        """The 30s cycle must not flood the log with the same typo."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(schedule_state="on", schedule_attrs={}))
        hass.services.async_call = self._mock_get_schedule({"temperature": 110})

        coordinator = _create_coordinator(hass, mock_config_entry)
        with caplog.at_level("WARNING", logger="custom_components.roommind.coordinator"):
            await coordinator._async_update_data()
            await coordinator._async_update_data()

        matching = [r for r in caplog.records if "outside the plausible range" in r.getMessage()]
        assert len(matching) == 1
        assert "living_room_abc12345" in matching[0].getMessage()
        assert "temperature" in matching[0].getMessage()

    @pytest.mark.asyncio
    async def test_warned_state_cleared_on_room_removal(self, hass, mock_config_entry):
        """Removing a room drops its warn keys so a re-added room warns again."""
        from unittest.mock import patch

        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator.async_request_refresh = AsyncMock()
        coordinator._block_temp_warned = {
            ("living_room_abc12345", "temperature", "110"),
            ("bedroom", "temperature", "110"),
        }

        registry = MagicMock()
        registry.entities = MagicMock()
        registry.entities.values.return_value = []
        with patch("homeassistant.helpers.entity_registry.async_get", return_value=registry):
            await coordinator.async_room_removed("living_room_abc12345")

        assert coordinator._block_temp_warned == {("bedroom", "temperature", "110")}

    @pytest.mark.asyncio
    async def test_inactive_block_typo_surfaces_in_room_state(self, hass, mock_config_entry):
        """#395: a typo in a block that is not running is reported to the panel."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(schedule_state="on", schedule_attrs={}))

        # Night block carries the typo; the all-day block that is running is fine.
        schedule_data = {
            "monday": [
                {"from": "00:00:00", "to": "06:00:00", "data": {"temperature": 110}},
                {"from": "06:00:00", "to": "23:59:59", "data": {"temperature": 21.0}},
            ]
        }

        async def _call(domain, service, call_data=None, **kwargs):
            if domain == "schedule" and service == "get_schedule":
                return {(call_data or {}).get("entity_id", ""): schedule_data}
            return None

        hass.services.async_call = AsyncMock(side_effect=_call)

        coordinator = _create_coordinator(hass, mock_config_entry)
        result = await coordinator._async_update_data()

        warnings = result["rooms"]["living_room_abc12345"]["schedule_temp_warnings"]
        assert warnings == [{"day": "monday", "from": "00:00:00", "field": "temperature", "value": "110"}]

    @pytest.mark.asyncio
    async def test_clean_schedule_reports_no_warnings(self, hass, mock_config_entry):
        """A schedule without typos produces an empty warning list."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(schedule_state="on", schedule_attrs={}))
        hass.services.async_call = self._mock_get_schedule({"temperature": 21.0})

        coordinator = _create_coordinator(hass, mock_config_entry)
        result = await coordinator._async_update_data()

        assert result["rooms"]["living_room_abc12345"]["schedule_temp_warnings"] == []
