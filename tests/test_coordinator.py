"""Tests for the RoomMind coordinator."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from custom_components.roommind.managers.weather_manager import WeatherManager


SAMPLE_ROOM = {
    "area_id": "living_room_abc12345",
    "thermostats": ["climate.living_room"],
    "acs": [],
    "temperature_sensor": "sensor.living_room_temp",
    "humidity_sensor": "sensor.living_room_humidity",
    "climate_mode": "auto",
    "schedules": [{"entity_id": "schedule.living_room_heating"}],
    "schedule_selector_entity": "",
    "comfort_temp": 21.0,
    "eco_temp": 17.0,
}


def _make_store_mock(rooms=None):
    """Create a store mock with proper get_settings and get_thermal_data returns."""
    store = MagicMock()
    store.get_rooms.return_value = rooms or {}
    store.get_settings.return_value = {}
    store.get_thermal_data.return_value = {}
    store.async_save_thermal_data = AsyncMock()
    return store


def make_mock_states_get(
    temp="18.0",
    humidity="55.0",
    schedule_state="on",
    schedule_attrs=None,
    outdoor_temp=None,
    outdoor_temp_entity="sensor.outdoor_temp",
    window_sensors=None,
    selector_state=None,
    selector_entity="input_boolean.schedule_toggle",
    person_states=None,
    extra=None,
    temp_unit=None,
):
    """Create a mock ``hass.states.get`` with configurable return values.

    Parameters
    ----------
    temp:
        Value for ``sensor.living_room_temp``.  Set to ``None`` to return
        ``None`` (entity missing).  ``"unavailable"`` is also supported.
    humidity:
        Value for ``sensor.living_room_humidity``.
    schedule_state:
        State for ``schedule.living_room_heating``.
    schedule_attrs:
        Attributes dict for the schedule entity (default ``{}``).
    outdoor_temp:
        If given, ``outdoor_temp_entity`` will return this value.
    outdoor_temp_entity:
        Entity id for the outdoor sensor (default ``sensor.outdoor_temp``).
    window_sensors:
        Dict mapping ``binary_sensor.*`` entity ids to state strings
        (e.g. ``{"binary_sensor.window1": "on"}``).
    selector_state:
        If given, ``selector_entity`` will return this state string.
    selector_entity:
        Entity id for the schedule selector (default ``input_boolean.schedule_toggle``).
    person_states:
        Dict mapping ``person.*`` entity ids to state strings
        (e.g. ``{"person.kevin": "home"}``).
    extra:
        Dict mapping arbitrary entity ids to ``(state_str, attrs_dict | None)``
        tuples for any entities not covered by the above parameters.
    temp_unit:
        If given (e.g. ``"°F"``), temperature sensor mocks will include
        ``unit_of_measurement`` in their attributes.
    """
    if schedule_attrs is None:
        schedule_attrs = {}
    if window_sensors is None:
        window_sensors = {}
    if person_states is None:
        person_states = {}
    if extra is None:
        extra = {}

    def _temp_attrs():
        return {"unit_of_measurement": temp_unit} if temp_unit else {}

    def _mock(entity_id):
        # Temperature sensor
        if entity_id == "sensor.living_room_temp":
            if temp is None:
                return None
            s = MagicMock()
            s.state = temp
            s.attributes = _temp_attrs()
            return s

        # Humidity sensor
        if entity_id == "sensor.living_room_humidity":
            if humidity is None:
                return None
            s = MagicMock()
            s.state = humidity
            s.attributes = {}
            return s

        # Schedule entity
        if entity_id == "schedule.living_room_heating":
            s = MagicMock()
            s.state = schedule_state
            s.attributes = schedule_attrs
            return s

        # Outdoor temperature
        if outdoor_temp is not None and entity_id == outdoor_temp_entity:
            s = MagicMock()
            s.state = outdoor_temp
            s.attributes = _temp_attrs()
            return s

        # Window / door sensors
        if entity_id in window_sensors:
            s = MagicMock()
            s.state = window_sensors[entity_id]
            return s

        # Schedule selector
        if selector_state is not None and entity_id == selector_entity:
            s = MagicMock()
            s.state = selector_state
            return s

        # Person entities
        if entity_id in person_states:
            s = MagicMock()
            s.state = person_states[entity_id]
            return s

        # Arbitrary extras
        if entity_id in extra:
            val = extra[entity_id]
            s = MagicMock()
            if isinstance(val, tuple):
                s.state = val[0]
                s.attributes = val[1] if val[1] is not None else {}
            else:
                s.state = val
            return s

        return None

    return _mock


def _create_coordinator(hass, mock_config_entry):
    """Create a RoomMindCoordinator with frame.report_usage patched out."""
    from custom_components.roommind.coordinator import RoomMindCoordinator

    with patch("homeassistant.helpers.frame.report_usage"):
        coordinator = RoomMindCoordinator(hass, mock_config_entry)
    return coordinator


class TestRoomMindCoordinator:
    """Tests for RoomMindCoordinator."""

    @pytest.mark.asyncio
    async def test_coordinator_initializes(self, hass, mock_config_entry):
        """Test that the coordinator initializes without errors."""
        coordinator = _create_coordinator(hass, mock_config_entry)
        assert coordinator is not None
        assert coordinator.rooms == {}

    @pytest.mark.asyncio
    async def test_update_with_comfort_temp_and_heating(
        self, hass, mock_config_entry
    ):
        """Test that update reads sensor, uses comfort_temp, and applies heating."""
        # Set up store mock
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(side_effect=make_mock_states_get())

        # Mock climate service calls
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        # Verify room state
        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["current_temp"] == 18.0
        assert room_state["current_humidity"] == 55.0
        assert room_state["target_temp"] == 21.0
        assert room_state["mode"] == "heating"

        # Verify service calls for heating: set_hvac_mode(heat) + set_temperature
        # Filter to climate calls only (schedule.get_schedule may also be called)
        climate_calls = [
            c for c in hass.services.async_call.call_args_list
            if c[0][0] == "climate"
        ]
        assert climate_calls[0] == call(
            "climate",
            "set_hvac_mode",
            {"entity_id": "climate.living_room", "hvac_mode": "heat"},
            blocking=True,
        )
        assert climate_calls[1] == call(
            "climate",
            "set_temperature",
            {"entity_id": "climate.living_room", "temperature": 30},
            blocking=True,
        )

    @pytest.mark.asyncio
    async def test_update_at_comfort_temp_goes_idle(self, hass, mock_config_entry):
        """Test that rooms at comfort_temp go idle (no heating/cooling needed)."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="21.0"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["target_temp"] == 21.0
        assert room_state["mode"] == "idle"

    @pytest.mark.asyncio
    async def test_update_sensor_unavailable_goes_idle(
        self, hass, mock_config_entry
    ):
        """Test that an unavailable sensor results in idle mode."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="unavailable"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["current_temp"] is None
        assert room_state["current_humidity"] == 55.0
        assert room_state["mode"] == "idle"

    @pytest.mark.asyncio
    async def test_update_sensor_state_none_skips_room(
        self, hass, mock_config_entry
    ):
        """Test that a missing sensor entity results in idle mode."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp=None))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["current_temp"] is None
        assert room_state["current_humidity"] == 55.0
        assert room_state["mode"] == "idle"

    @pytest.mark.asyncio
    async def test_update_empty_store_returns_empty(self, hass, mock_config_entry):
        """Test that an empty store returns an empty rooms dict."""
        store = _make_store_mock({})
        hass.data = {"roommind": {"store": store}}

        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        assert data == {"rooms": {}}

    @pytest.mark.asyncio
    async def test_update_climate_service_failure_does_not_crash(
        self, hass, mock_config_entry
    ):
        """Test that a climate service call failure is handled gracefully."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(side_effect=make_mock_states_get())

        # Service call raises an exception
        hass.services.async_call = AsyncMock(side_effect=Exception("Service down"))

        coordinator = _create_coordinator(hass, mock_config_entry)

        # Should not raise
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["mode"] == "heating"

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

        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(schedule_attrs={"temperature": 23.0})
        )
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
    async def test_async_room_added_triggers_refresh(self, hass, mock_config_entry):
        """Test that async_room_added calls async_request_refresh."""
        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator.async_request_refresh = AsyncMock()

        await coordinator.async_room_added({"area_id": "new_room_123"})

        coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_room_added_creates_entities(self, hass, mock_config_entry):
        """Test that async_room_added creates 3 sensor entities."""
        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator.async_request_refresh = AsyncMock()
        mock_add_entities = MagicMock()
        coordinator.async_add_entities = mock_add_entities

        room = {"area_id": "bedroom_abc12345"}
        await coordinator.async_room_added(room)

        # async_add_entities should be called with 3 entities
        mock_add_entities.assert_called_once()
        entities = mock_add_entities.call_args[0][0]
        assert len(entities) == 2

        # Verify entity types
        from custom_components.roommind.sensor import (
            RoomMindTargetTemperatureSensor,
            RoomMindModeSensor,
        )

        assert isinstance(entities[0], RoomMindTargetTemperatureSensor)
        assert isinstance(entities[1], RoomMindModeSensor)

        # Verify unique IDs
        assert entities[0]._attr_unique_id == "roommind_bedroom_abc12345_target_temp"
        assert entities[1]._attr_unique_id == "roommind_bedroom_abc12345_mode"

        coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_room_added_no_callback_does_not_crash(
        self, hass, mock_config_entry
    ):
        """Test that async_room_added works even without async_add_entities set."""
        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator.async_request_refresh = AsyncMock()

        # No async_add_entities set on coordinator
        await coordinator.async_room_added({"area_id": "room_123"})

        # Should still refresh without error
        coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_room_added_twice_does_not_duplicate_entities(
        self, hass, mock_config_entry
    ):
        """Calling async_room_added for an existing room must not register entities twice."""
        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator.async_request_refresh = AsyncMock()
        mock_add_entities = MagicMock()
        coordinator.async_add_entities = mock_add_entities

        room = {"area_id": "bedroom_abc12345"}
        await coordinator.async_room_added(room)
        await coordinator.async_room_added(room)  # simulates a room update

        # Entities should only be registered once
        mock_add_entities.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_room_update_still_refreshes(self, hass, mock_config_entry):
        """Updating an existing room must still trigger a coordinator refresh."""
        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator.async_request_refresh = AsyncMock()
        mock_add_entities = MagicMock()
        coordinator.async_add_entities = mock_add_entities

        room = {"area_id": "bedroom_abc12345"}
        await coordinator.async_room_added(room)
        await coordinator.async_room_added(room)  # simulates a room update

        assert coordinator.async_request_refresh.call_count == 2

    @pytest.mark.asyncio
    async def test_async_room_removed_triggers_refresh(self, hass, mock_config_entry):
        """Test that async_room_removed calls async_request_refresh."""
        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator.async_request_refresh = AsyncMock()

        # Mock entity registry with no matching entities
        mock_registry = MagicMock()
        mock_registry.entities = MagicMock()
        mock_registry.entities.values.return_value = []
        with patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=mock_registry,
        ):
            await coordinator.async_room_removed("some_room_id")

        coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_room_removed_removes_entities(self, hass, mock_config_entry):
        """Test that async_room_removed removes entities from the registry."""
        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator.async_request_refresh = AsyncMock()

        room_id = "living_room_abc12345"

        # Create mock entity registry entries for this room
        entity1 = MagicMock()
        entity1.unique_id = f"roommind_{room_id}_target_temp"
        entity1.entity_id = f"sensor.{room_id}_target_temp"

        entity2 = MagicMock()
        entity2.unique_id = f"roommind_{room_id}_mode"
        entity2.entity_id = f"sensor.{room_id}_mode"

        # Also include an entity for a different room (should NOT be removed)
        other_entity = MagicMock()
        other_entity.unique_id = "roommind_other_room_99999_target_temp"
        other_entity.entity_id = "sensor.other_room_target_temp"

        mock_registry = MagicMock()
        mock_registry.entities = MagicMock()
        mock_registry.entities.values.return_value = [
            entity1, entity2, other_entity
        ]

        with patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=mock_registry,
        ):
            await coordinator.async_room_removed(room_id)

        # Verify only the 2 entities for the removed room were unregistered
        assert mock_registry.async_remove.call_count == 2
        removed_ids = [
            call.args[0] for call in mock_registry.async_remove.call_args_list
        ]
        assert f"sensor.{room_id}_target_temp" in removed_ids
        assert f"sensor.{room_id}_mode" in removed_ids
        assert "sensor.other_room_target_temp" not in removed_ids

        coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_override_takes_priority_over_schedule(self, hass, mock_config_entry):
        """Test that an active override overrides the schedule target temp."""
        room_with_override = {
            **SAMPLE_ROOM,
            "override_temp": 25.0,
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
    async def test_expired_override_falls_back_to_schedule(self, hass, mock_config_entry):
        """Test that an expired override reverts to normal schedule logic."""
        room_with_expired = {
            **SAMPLE_ROOM,
            "override_temp": 25.0,
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
    async def test_get_active_schedule_index_input_boolean_on(
        self, hass, mock_config_entry
    ):
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
    async def test_get_active_schedule_index_input_boolean_off(
        self, hass, mock_config_entry
    ):
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
    async def test_get_active_schedule_index_input_number(
        self, hass, mock_config_entry
    ):
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
    async def test_get_active_schedule_index_input_number_out_of_range(
        self, hass, mock_config_entry
    ):
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
    async def test_get_active_schedule_index_no_schedules(
        self, hass, mock_config_entry
    ):
        """With empty schedules, returns -1."""
        room = {
            **SAMPLE_ROOM,
            "schedules": [],
            "schedule_selector_entity": "",
        }
        coordinator = _create_coordinator(hass, mock_config_entry)
        assert coordinator._get_active_schedule_index(room) == -1

    @pytest.mark.asyncio
    async def test_multi_schedule_selects_correct_entity(
        self, hass, mock_config_entry
    ):
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

        hass.states.get = MagicMock(side_effect=make_mock_states_get(
            selector_state="on",
            extra={
                "schedule.evening": ("on", {"temperature": 19.0}),
                "schedule.morning": ("on", {"temperature": 23.0}),
            },
        ))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        # Selector is "on" → index 1 → schedule.evening → block temp 19.0
        assert room_state["target_temp"] == 19.0

    @pytest.mark.asyncio
    async def test_process_room_returns_active_schedule_index(
        self, hass, mock_config_entry
    ):
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

    @pytest.mark.asyncio
    async def test_window_open_overrides_to_idle(self, hass, mock_config_entry):
        """Test that an open window sensor forces mode to idle and turns off devices."""
        room_with_window = {
            **SAMPLE_ROOM,
            "window_sensors": ["binary_sensor.living_room_window"],
        }
        store = _make_store_mock({"living_room_abc12345": room_with_window})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(side_effect=make_mock_states_get(
            window_sensors={"binary_sensor.living_room_window": "on"},
        ))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["mode"] == "idle"
        assert room_state["window_open"] is True

        # MODE_IDLE turns off all devices via set_hvac_mode "off"
        calls = hass.services.async_call.call_args_list
        hvac_off_calls = [
            c for c in calls
            if c == call(
                "climate",
                "set_hvac_mode",
                {"entity_id": "climate.living_room", "hvac_mode": "off"},
                blocking=True,
            )
        ]
        assert len(hvac_off_calls) >= 1

    @pytest.mark.asyncio
    async def test_window_closed_normal_operation(self, hass, mock_config_entry):
        """Test that a closed window sensor allows normal heating operation."""
        room_with_window = {
            **SAMPLE_ROOM,
            "window_sensors": ["binary_sensor.living_room_window"],
        }
        store = _make_store_mock({"living_room_abc12345": room_with_window})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(side_effect=make_mock_states_get(
            window_sensors={"binary_sensor.living_room_window": "off"},
        ))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["mode"] == "heating"
        assert room_state["window_open"] is False

    @pytest.mark.asyncio
    async def test_window_sensor_unavailable_treated_as_closed(
        self, hass, mock_config_entry
    ):
        """Test that an unavailable window sensor is treated as closed."""
        room_with_window = {
            **SAMPLE_ROOM,
            "window_sensors": ["binary_sensor.living_room_window"],
        }
        store = _make_store_mock({"living_room_abc12345": room_with_window})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(side_effect=make_mock_states_get(
            window_sensors={"binary_sensor.living_room_window": "unavailable"},
        ))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["window_open"] is False
        assert room_state["mode"] == "heating"

    @pytest.mark.asyncio
    async def test_no_window_sensors_normal_operation(self, hass, mock_config_entry):
        """Test that an empty window_sensors list results in normal heating."""
        room_with_no_windows = {
            **SAMPLE_ROOM,
            "window_sensors": [],
        }
        store = _make_store_mock({"living_room_abc12345": room_with_no_windows})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(side_effect=make_mock_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["window_open"] is False
        assert room_state["mode"] == "heating"

    @pytest.mark.asyncio
    async def test_multiple_windows_one_open_pauses(self, hass, mock_config_entry):
        """Test that if any one of multiple window sensors is open, mode is idle."""
        room_with_windows = {
            **SAMPLE_ROOM,
            "window_sensors": ["binary_sensor.window1", "binary_sensor.window2"],
        }
        store = _make_store_mock({"living_room_abc12345": room_with_windows})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(side_effect=make_mock_states_get(
            window_sensors={
                "binary_sensor.window1": "off",
                "binary_sensor.window2": "on",
            },
        ))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["window_open"] is True
        assert room_state["mode"] == "idle"

    @pytest.mark.asyncio
    async def test_window_open_delay_not_reached(self, hass, mock_config_entry):
        """Test that window open does NOT pause until open_delay is reached."""
        room_with_delay = {
            **SAMPLE_ROOM,
            "window_sensors": ["binary_sensor.living_room_window"],
            "window_open_delay": 120,
        }
        store = _make_store_mock({"living_room_abc12345": room_with_delay})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(side_effect=make_mock_states_get(
            window_sensors={"binary_sensor.living_room_window": "on"},
        ))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["mode"] == "heating"
        assert room_state["window_open"] is False

    @pytest.mark.asyncio
    async def test_window_open_delay_reached(self, hass, mock_config_entry):
        """Test that window open pauses climate once open_delay has elapsed."""
        room_with_delay = {
            **SAMPLE_ROOM,
            "window_sensors": ["binary_sensor.living_room_window"],
            "window_open_delay": 120,
        }
        store = _make_store_mock({"living_room_abc12345": room_with_delay})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(side_effect=make_mock_states_get(
            window_sensors={"binary_sensor.living_room_window": "on"},
        ))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        # Pre-set: window has been open for 130s (exceeds 120s delay)
        coordinator._window_manager._open_since["living_room_abc12345"] = time.time() - 130
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["mode"] == "idle"
        assert room_state["window_open"] is True

    @pytest.mark.asyncio
    async def test_window_close_delay_not_reached(self, hass, mock_config_entry):
        """Test that climate stays paused until close_delay has elapsed."""
        room_with_delay = {
            **SAMPLE_ROOM,
            "window_sensors": ["binary_sensor.living_room_window"],
            "window_close_delay": 300,
        }
        store = _make_store_mock({"living_room_abc12345": room_with_delay})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(side_effect=make_mock_states_get(
            window_sensors={"binary_sensor.living_room_window": "off"},
        ))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        # Pre-set: room was paused (window was open), now window is closed but delay not met
        coordinator._window_manager._paused["living_room_abc12345"] = True
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["mode"] == "idle"
        assert room_state["window_open"] is True

    @pytest.mark.asyncio
    async def test_window_close_delay_reached(self, hass, mock_config_entry):
        """Test that climate resumes once close_delay has elapsed after window closed."""
        room_with_delay = {
            **SAMPLE_ROOM,
            "window_sensors": ["binary_sensor.living_room_window"],
            "window_close_delay": 300,
        }
        store = _make_store_mock({"living_room_abc12345": room_with_delay})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(side_effect=make_mock_states_get(
            window_sensors={"binary_sensor.living_room_window": "off"},
        ))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        # Pre-set: room was paused and window has been closed for 310s (exceeds 300s delay)
        coordinator._window_manager._paused["living_room_abc12345"] = True
        coordinator._window_manager._closed_since["living_room_abc12345"] = time.time() - 310
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["mode"] == "heating"
        assert room_state["window_open"] is False

    @pytest.mark.asyncio
    async def test_zero_delays_instant_behavior(self, hass, mock_config_entry):
        """Test that zero delays cause instant pause (backward compatible)."""
        room_zero_delay = {
            **SAMPLE_ROOM,
            "window_sensors": ["binary_sensor.living_room_window"],
            "window_open_delay": 0,
            "window_close_delay": 0,
        }
        store = _make_store_mock({"living_room_abc12345": room_zero_delay})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(side_effect=make_mock_states_get(
            window_sensors={"binary_sensor.living_room_window": "on"},
        ))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["mode"] == "idle"
        assert room_state["window_open"] is True

    @pytest.mark.asyncio
    async def test_window_briefly_opened_then_closed(self, hass, mock_config_entry):
        """Test that a brief window open (under delay) never pauses climate."""
        room_with_delay = {
            **SAMPLE_ROOM,
            "window_sensors": ["binary_sensor.living_room_window"],
            "window_open_delay": 120,
        }
        store = _make_store_mock({"living_room_abc12345": room_with_delay})
        hass.data = {"roommind": {"store": store}}

        # First call: window is open — delay timer starts but not reached
        mock_states = {}
        base_mock = make_mock_states_get()

        def mock_states_get(entity_id):
            if entity_id in mock_states:
                return mock_states[entity_id]
            return base_mock(entity_id)

        hass.states.get = MagicMock(side_effect=mock_states_get)
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)

        # Window opens
        window_state = MagicMock(); window_state.state = "on"
        mock_states["binary_sensor.living_room_window"] = window_state
        data = await coordinator._async_update_data()
        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["mode"] == "heating"
        assert "living_room_abc12345" in coordinator._window_manager._open_since

        # Window closes before delay reached
        window_state.state = "off"
        data = await coordinator._async_update_data()
        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["mode"] == "heating"
        assert room_state["window_open"] is False
        assert "living_room_abc12345" not in coordinator._window_manager._open_since

    @pytest.mark.asyncio
    async def test_room_removed_cleans_up_window_state(self, hass, mock_config_entry):
        """Test that removing a room cleans up all window delay state dicts."""
        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator.async_request_refresh = AsyncMock()

        area_id = "living_room_abc12345"

        # Pre-populate window delay state
        coordinator._window_manager._open_since[area_id] = time.time() - 60
        coordinator._window_manager._closed_since[area_id] = time.time() - 30
        coordinator._window_manager._paused[area_id] = True

        mock_registry = MagicMock()
        mock_registry.entities = MagicMock()
        mock_registry.entities.values.return_value = []
        with patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=mock_registry,
        ):
            await coordinator.async_room_removed(area_id)

        assert area_id not in coordinator._window_manager._open_since
        assert area_id not in coordinator._window_manager._closed_since
        assert area_id not in coordinator._window_manager._paused


# ---------------------------------------------------------------------------
# T: Vacation Mode Tests
# ---------------------------------------------------------------------------


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
            "override_temp": 25.0,
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


# ---------------------------------------------------------------------------
# T2b: Presence Detection Tests
# ---------------------------------------------------------------------------


def _presence_states_get(*persons_home):
    """Create a mock states.get function with configurable presence.

    Any ``person.*`` entity in *persons_home* will report ``"home"``;
    all other ``person.*`` entities report ``"not_home"``.

    Non-person entities use the standard defaults from
    :func:`make_mock_states_get`.
    """
    home_set = set(persons_home)

    # Build the base mock with standard defaults
    base = make_mock_states_get()

    def _mock(entity_id):
        if entity_id.startswith("person."):
            s = MagicMock()
            s.state = "home" if entity_id in home_set else "not_home"
            return s
        return base(entity_id)

    return _mock


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
        hass.states.get = MagicMock(
            side_effect=_presence_states_get("person.kevin")
        )
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

        hass.states.get = MagicMock(side_effect=make_mock_states_get(
            person_states={"person.kevin": "unavailable"},
        ))
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
        hass.states.get = MagicMock(
            side_effect=_presence_states_get("person.kevin")
        )
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
        hass.states.get = MagicMock(
            side_effect=_presence_states_get("person.anna")
        )
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
        hass.states.get = MagicMock(
            side_effect=_presence_states_get("person.anna")
        )
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
    async def test_schedule_off_action_off_forces_idle(self, hass, mock_config_entry):
        """When schedule_off_action is 'off' and schedule is off, devices are turned off."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "schedule_off_action": "off",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(
            schedule_state="off",
        ))
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
        hass.states.get = MagicMock(side_effect=make_mock_states_get(
            schedule_state="off",
        ))
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


# ---------------------------------------------------------------------------
# T3: Coordinator + MPC Integration Tests
# ---------------------------------------------------------------------------

class TestCoordinatorMPCIntegration:
    """Integration tests for the coordinator → MPCController → optimizer chain."""

    @pytest.mark.asyncio
    async def test_trained_model_processes_through_mpc_path(
        self, hass, mock_config_entry
    ):
        """A room with a trained thermal model goes through the full MPC path.

        Verifies the coordinator → MPCController → MPCOptimizer chain by
        pre-training the model, mocking low prediction_std so MPC is selected,
        and confirming the coordinator produces the expected heating mode + state.
        """
        from custom_components.roommind.control.thermal_model import RoomModelManager

        room = {
            **SAMPLE_ROOM,
            "area_id": "mpc_room",
        }
        store = _make_store_mock({"mpc_room": room})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(temp="17.0", humidity="50.0")
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)

        # Pre-train the model so it has valid parameters
        mgr = coordinator._model_manager
        mgr.update("mpc_room", 17.5, 5.0, "heating", 5.0)
        mgr.update("mpc_room", 18.0, 5.0, "heating", 5.0)
        # Force low prediction std so the MPC path is taken (not bang-bang)
        mgr.get_prediction_std = MagicMock(return_value=0.1)

        data = await coordinator._async_update_data()

        room_state = data["rooms"]["mpc_room"]
        assert room_state["current_temp"] == 17.0
        assert room_state["target_temp"] == 21.0
        assert room_state["mode"] == "heating"
        assert room_state["confidence"] is not None
        # Verify climate service was called (MPC decided to heat)
        assert hass.services.async_call.called
        # Verify prediction_std was checked (MPC path selection)
        mgr.get_prediction_std.assert_called()

    @pytest.mark.asyncio
    async def test_untrained_model_uses_bangbang_fallback(
        self, hass, mock_config_entry
    ):
        """A room with an untrained model falls back to bang-bang control.

        Default model has high prediction uncertainty, so the coordinator
        should route through the bang-bang path instead of MPC optimizer.
        """
        room = {
            **SAMPLE_ROOM,
            "area_id": "bangbang_room",
        }
        store = _make_store_mock({"bangbang_room": room})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(temp="16.0", humidity="50.0")
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        # No pre-training — default model has high uncertainty → bang-bang
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["bangbang_room"]
        # 16°C is well below 21°C comfort → heating (via bang-bang)
        assert room_state["mode"] == "heating"
        assert room_state["current_temp"] == 16.0
        assert room_state["target_temp"] == 21.0

    @pytest.mark.asyncio
    async def test_mpc_with_weather_forecast(self, hass, mock_config_entry):
        """Coordinator passes weather forecast to MPCController for horizon planning."""
        room = {
            **SAMPLE_ROOM,
            "area_id": "forecast_room",
        }
        forecast_data = {
            "weather.home": {
                "forecast": [
                    {"temperature": 3.0},
                    {"temperature": 4.0},
                    {"temperature": 5.0},
                ]
            }
        }
        store = _make_store_mock({"forecast_room": room})
        store.get_settings.return_value = {"weather_entity": "weather.home"}
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(temp="17.0", humidity="50.0")
        )
        # services.async_call is used both for weather.get_forecasts and climate
        call_count = [0]
        original_results = [forecast_data]  # first call returns forecast

        async def mock_async_call(domain, service, data=None, **kwargs):
            if domain == "weather" and service == "get_forecasts":
                return forecast_data
            return None

        hass.services.async_call = AsyncMock(side_effect=mock_async_call)

        coordinator = _create_coordinator(hass, mock_config_entry)

        # Pre-train and force MPC path
        mgr = coordinator._model_manager
        mgr.update("forecast_room", 17.5, 3.0, "heating", 5.0)
        mgr.update("forecast_room", 18.0, 3.0, "heating", 5.0)
        mgr.get_prediction_std = MagicMock(return_value=0.1)

        data = await coordinator._async_update_data()

        room_state = data["rooms"]["forecast_room"]
        assert room_state["mode"] == "heating"
        # Weather service should have been called
        weather_calls = [
            c for c in hass.services.async_call.call_args_list
            if c.args[0] == "weather"
        ]
        assert len(weather_calls) >= 1

    @pytest.mark.asyncio
    async def test_mpc_updates_thermal_model_after_processing(
        self, hass, mock_config_entry
    ):
        """Coordinator updates the thermal model with observations after room processing."""
        room = {
            **SAMPLE_ROOM,
            "area_id": "learning_room",
        }
        store = _make_store_mock({"learning_room": room})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(temp="18.5", humidity="50.0")
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        # Set a previous temp so the model update has T_old available
        coordinator._last_temps["learning_room"] = 18.0

        data = await coordinator._async_update_data()

        room_state = data["rooms"]["learning_room"]
        assert room_state["current_temp"] == 18.5
        # Verify the model was updated (last_temps should now have the new value)
        assert coordinator._last_temps["learning_room"] == 18.5

    @pytest.mark.asyncio
    async def test_coordinator_mpc_idle_at_target(self, hass, mock_config_entry):
        """Full chain: MPC should produce idle when room is at target temperature.

        Uses T_outdoor=20 (close to target) so that the EKF model (C=1)
        predicts minimal cooling and the optimizer chooses idle.
        """
        room = {
            **SAMPLE_ROOM,
            "area_id": "idle_room",
        }
        store = _make_store_mock({"idle_room": room})
        store.get_settings = MagicMock(return_value={"outdoor_temp_sensor": "sensor.outdoor_temp"})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(side_effect=make_mock_states_get(
            temp="21.0", humidity="50.0", outdoor_temp="20.0",
        ))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)

        # Pre-train with mild outdoor temp so model sees low cooling
        mgr = coordinator._model_manager
        mgr.update("idle_room", 21.0, 20.0, "idle", 5.0)
        mgr.update("idle_room", 21.0, 20.0, "idle", 5.0)
        mgr.get_prediction_std = MagicMock(return_value=0.1)

        data = await coordinator._async_update_data()

        room_state = data["rooms"]["idle_room"]
        assert room_state["mode"] == "idle"
        assert room_state["target_temp"] == 21.0


# ---------------------------------------------------------------------------
# T4: Valve Protection Tests
# ---------------------------------------------------------------------------


class TestValveProtection:
    """Tests for valve protection (anti-seize) cycling."""

    @pytest.mark.asyncio
    async def test_valve_protection_disabled_by_default(self, hass, mock_config_entry):
        """No cycling occurs without explicit enable."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {}
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="21.0"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        # Force the check counter to trigger
        coordinator._valve_manager._check_count = 119
        await coordinator._async_update_data()

        # No valve cycling should have started
        assert len(coordinator._valve_manager._cycling) == 0

    @pytest.mark.asyncio
    async def test_valve_protection_cycles_stale_valve(self, hass, mock_config_entry):
        """TRV idle for 8 days gets cycled when protection is enabled."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "valve_protection_enabled": True,
            "valve_protection_interval_days": 7,
        }
        store.async_save_settings = AsyncMock()
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="21.0"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        # TRV was last used 8 days ago
        coordinator._valve_manager._last_actuation["climate.living_room"] = time.time() - 8 * 86400
        # Trigger check
        coordinator._valve_manager._check_count = 119
        await coordinator._async_update_data()

        # Valve should be cycling
        assert "climate.living_room" in coordinator._valve_manager._cycling

        # Verify heat + temperature service calls for the cycling valve
        climate_calls = [
            c for c in hass.services.async_call.call_args_list
            if c[0][0] == "climate" and c[0][2].get("entity_id") == "climate.living_room"
        ]
        hvac_heat_calls = [c for c in climate_calls if c[0][1] == "set_hvac_mode" and c[0][2]["hvac_mode"] == "heat"]
        set_temp_calls = [c for c in climate_calls if c[0][1] == "set_temperature"]
        assert len(hvac_heat_calls) >= 1
        assert len(set_temp_calls) >= 1

    @pytest.mark.asyncio
    async def test_valve_protection_finishes_after_duration(self, hass, mock_config_entry):
        """After 15s duration, valve gets turned off and timestamp updated."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {"valve_protection_enabled": True}
        store.async_save_settings = AsyncMock()
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="21.0"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        # Simulate: valve has been cycling for 20 seconds (exceeds 15s)
        coordinator._valve_manager._cycling["climate.living_room"] = time.time() - 20
        old_actuation = coordinator._valve_manager._last_actuation.get("climate.living_room", 0)

        await coordinator._async_update_data()

        # Valve should no longer be cycling
        assert "climate.living_room" not in coordinator._valve_manager._cycling
        # Actuation timestamp should be updated
        assert coordinator._valve_manager._last_actuation["climate.living_room"] > old_actuation
        assert coordinator._valve_manager._actuation_dirty is True

        # Verify off command was sent
        off_calls = [
            c for c in hass.services.async_call.call_args_list
            if c == call(
                "climate", "set_hvac_mode",
                {"entity_id": "climate.living_room", "hvac_mode": "off"},
                blocking=True,
            )
        ]
        assert len(off_calls) >= 1

    @pytest.mark.asyncio
    async def test_valve_protection_skips_recent_valve(self, hass, mock_config_entry):
        """TRV idle for only 2 days is not cycled (default interval = 7 days)."""
        recent_ts = time.time() - 2 * 86400
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "valve_protection_enabled": True,
            "valve_protection_interval_days": 7,
            "valve_last_actuation": {"climate.living_room": recent_ts},
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="21.0"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._valve_manager._check_count = 119
        await coordinator._async_update_data()

        assert "climate.living_room" not in coordinator._valve_manager._cycling

    @pytest.mark.asyncio
    async def test_valve_protection_excludes_cycling_from_apply(self, hass, mock_config_entry):
        """Cycling TRV is not turned off by normal idle control."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {"valve_protection_enabled": True}
        store.async_save_settings = AsyncMock()
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="21.0"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        # Valve is currently being cycled (started 5 seconds ago, still within 15s)
        coordinator._valve_manager._cycling["climate.living_room"] = time.time() - 5

        await coordinator._async_update_data()

        # The room is at target (21°C) so mode=idle, but the cycling valve
        # should NOT receive an "off" command from normal control.
        # Only the valve protection finish logic should close it (but not yet — only 5s elapsed).
        climate_off_calls = [
            c for c in hass.services.async_call.call_args_list
            if c == call(
                "climate", "set_hvac_mode",
                {"entity_id": "climate.living_room", "hvac_mode": "off"},
                blocking=True,
            )
        ]
        assert len(climate_off_calls) == 0
        # Valve should still be cycling
        assert "climate.living_room" in coordinator._valve_manager._cycling

    @pytest.mark.asyncio
    async def test_valve_protection_runs_when_climate_off(self, hass, mock_config_entry):
        """Valve protection works even when climate_control_active is False."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "climate_control_active": False,
            "valve_protection_enabled": True,
            "valve_protection_interval_days": 7,
        }
        store.async_save_settings = AsyncMock()
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="21.0"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._valve_manager._last_actuation["climate.living_room"] = time.time() - 8 * 86400
        coordinator._valve_manager._check_count = 119
        await coordinator._async_update_data()

        assert "climate.living_room" in coordinator._valve_manager._cycling

    @pytest.mark.asyncio
    async def test_valve_protection_only_trvs(self, hass, mock_config_entry):
        """Only thermostats are cycled, not ACs."""
        room_with_ac = {
            **SAMPLE_ROOM,
            "acs": ["climate.living_room_ac"],
        }
        store = _make_store_mock({"living_room_abc12345": room_with_ac})
        store.get_settings.return_value = {
            "valve_protection_enabled": True,
            "valve_protection_interval_days": 7,
        }
        store.async_save_settings = AsyncMock()
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="21.0"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        # Both TRV and AC idle for 8 days
        coordinator._valve_manager._last_actuation["climate.living_room"] = time.time() - 8 * 86400
        coordinator._valve_manager._last_actuation["climate.living_room_ac"] = time.time() - 8 * 86400
        coordinator._valve_manager._check_count = 119
        await coordinator._async_update_data()

        # Only TRV should be cycled, not AC
        assert "climate.living_room" in coordinator._valve_manager._cycling
        assert "climate.living_room_ac" not in coordinator._valve_manager._cycling

    @pytest.mark.asyncio
    async def test_valve_actuation_updated_on_heating(self, hass, mock_config_entry):
        """Normal heating updates valve actuation timestamps."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {}
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="18.0"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        assert "climate.living_room" not in coordinator._valve_manager._last_actuation

        await coordinator._async_update_data()

        # Room heats (18°C < 21°C target), so actuation should be tracked
        assert "climate.living_room" in coordinator._valve_manager._last_actuation
        assert coordinator._valve_manager._actuation_dirty is True

    @pytest.mark.asyncio
    async def test_valve_protection_custom_interval(self, hass, mock_config_entry):
        """Custom 3-day interval: TRV idle for 4 days gets cycled."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "valve_protection_enabled": True,
            "valve_protection_interval_days": 3,
        }
        store.async_save_settings = AsyncMock()
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="21.0"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._valve_manager._last_actuation["climate.living_room"] = time.time() - 4 * 86400
        coordinator._valve_manager._check_count = 119
        await coordinator._async_update_data()

        assert "climate.living_room" in coordinator._valve_manager._cycling

    @pytest.mark.asyncio
    async def test_valve_protection_cleanup_stale_entities(self, hass, mock_config_entry):
        """Entities no longer configured in any room are cleaned up."""
        now = time.time()
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "valve_protection_enabled": True,
            "valve_protection_interval_days": 7,
            "valve_last_actuation": {
                "climate.living_room": now,
                "climate.old_thermostat": now - 30 * 86400,
            },
        }
        store.async_save_settings = AsyncMock()
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="21.0"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._valve_manager._check_count = 119
        await coordinator._async_update_data()

        assert "climate.old_thermostat" not in coordinator._valve_manager._last_actuation
        assert "climate.living_room" in coordinator._valve_manager._last_actuation

    @pytest.mark.asyncio
    async def test_valve_protection_auto_only_thermostat(self, hass, mock_config_entry):
        """TRV with only 'off'+'auto' gets 'auto' mode during valve cycling."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "valve_protection_enabled": True,
            "valve_protection_interval_days": 7,
        }
        store.async_save_settings = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        trv_state = MagicMock()
        trv_state.state = "off"
        trv_state.attributes = {
            "hvac_modes": ["off", "auto"], "temperature": None,
            "min_temp": 5.0, "max_temp": 25.0, "current_temperature": 21.0,
        }
        base_get = make_mock_states_get(temp="21.0")

        def custom_get(eid):
            if eid == "climate.living_room":
                return trv_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=custom_get)
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._valve_manager._last_actuation["climate.living_room"] = time.time() - 8 * 86400
        coordinator._valve_manager._check_count = 119
        await coordinator._async_update_data()

        assert "climate.living_room" in coordinator._valve_manager._cycling
        climate_calls = [
            c for c in hass.services.async_call.call_args_list
            if c[0][0] == "climate" and c[0][2].get("entity_id") == "climate.living_room"
        ]
        hvac_calls = [c for c in climate_calls if c[0][1] == "set_hvac_mode"]
        assert any(c[0][2]["hvac_mode"] == "auto" for c in hvac_calls)
        assert not any(c[0][2]["hvac_mode"] == "heat" for c in hvac_calls)


class TestMoldRiskDetection:
    """Tests for mold risk detection and prevention in the coordinator."""

    @pytest.mark.asyncio
    async def test_mold_detection_disabled_by_default(self, hass, mock_config_entry):
        """When mold detection is not enabled, mold_risk_level should be 'ok'."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(humidity="80.0"),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_risk_level"] == "ok"
        assert room["mold_prevention_active"] is False

    @pytest.mark.asyncio
    async def test_mold_risk_computed_when_detection_enabled(
        self, hass, mock_config_entry,
    ):
        """When detection is enabled, mold risk should be calculated."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_detection_enabled": True,
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        # 18°C, 75% RH, 0°C outside → should be critical
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity="75.0", outdoor_temp="0.0",
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_risk_level"] == "critical"
        assert room["mold_surface_rh"] is not None
        assert room["mold_surface_rh"] > 80.0

    @pytest.mark.asyncio
    async def test_mold_prevention_raises_target_temp(
        self, hass, mock_config_entry,
    ):
        """When prevention is enabled and risk is high, target temp is raised."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_prevention_enabled": True,
            "mold_prevention_intensity": "medium",
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        # High mold risk conditions
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity="75.0", outdoor_temp="0.0",
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_prevention_active"] is True
        assert room["mold_prevention_delta"] == 2.0
        # Target temp should be comfort (21) + delta (2) = 23
        assert room["target_temp"] == 23.0

    @pytest.mark.asyncio
    async def test_mold_prevention_intensity_light(
        self, hass, mock_config_entry,
    ):
        """Light intensity raises target by 1°C."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_prevention_enabled": True,
            "mold_prevention_intensity": "light",
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity="75.0", outdoor_temp="0.0",
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_prevention_delta"] == 1.0
        assert room["target_temp"] == 22.0

    @pytest.mark.asyncio
    async def test_mold_no_humidity_sensor_skipped(
        self, hass, mock_config_entry,
    ):
        """Rooms without humidity data should not trigger mold logic."""
        room_no_humidity = {**SAMPLE_ROOM, "humidity_sensor": ""}
        store = _make_store_mock({"living_room_abc12345": room_no_humidity})
        store.get_settings.return_value = {
            "mold_detection_enabled": True,
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity=None, outdoor_temp="0.0",
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_risk_level"] == "ok"
        assert room["mold_surface_rh"] is None

    @pytest.mark.asyncio
    async def test_mold_risk_fields_in_room_state(
        self, hass, mock_config_entry,
    ):
        """Mold risk fields should always be present in room state."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert "mold_risk_level" in room
        assert "mold_surface_rh" in room
        assert "mold_prevention_active" in room
        assert "mold_prevention_delta" in room

    @pytest.mark.asyncio
    async def test_mold_prevention_intensity_strong(
        self, hass, mock_config_entry,
    ):
        """Strong intensity raises target by 3°C."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_prevention_enabled": True,
            "mold_prevention_intensity": "strong",
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity="75.0", outdoor_temp="0.0",
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_prevention_delta"] == 3.0
        assert room["target_temp"] == 24.0

    @pytest.mark.asyncio
    async def test_mold_sustained_timer_no_notification_before_threshold(
        self, hass, mock_config_entry,
    ):
        """Notification should NOT be sent before sustained_minutes elapsed."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_detection_enabled": True,
            "mold_notifications_enabled": True,
            "mold_sustained_minutes": 30,
            "mold_notification_targets": [
                {"entity_id": "notify.mobile", "person_entity": "", "notify_when": "always"},
            ],
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity="75.0", outdoor_temp="0.0",
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)

        # First cycle: risk starts, sustained timer begins
        await coordinator._async_update_data()

        # No notification service call should have been made for mold
        # (only climate control calls may have been made)
        mold_calls = [
            c for c in hass.services.async_call.call_args_list
            if c[0][0] == "notify"
        ]
        assert len(mold_calls) == 0

    @pytest.mark.asyncio
    async def test_mold_sustained_timer_notification_after_threshold(
        self, hass, mock_config_entry,
    ):
        """Notification should be sent after sustained_minutes have elapsed."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_detection_enabled": True,
            "mold_notifications_enabled": True,
            "mold_sustained_minutes": 0,  # immediate notification
            "mold_notification_cooldown": 60,
            "mold_notification_targets": [
                {"entity_id": "notify.mobile", "person_entity": "", "notify_when": "always"},
            ],
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity="75.0", outdoor_temp="0.0",
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        with patch(
            "custom_components.roommind.coordinator._get_area_name",
            return_value="Living Room",
        ):
            await coordinator._async_update_data()

        mold_calls = [
            c for c in hass.services.async_call.call_args_list
            if c[0][0] == "notify"
        ]
        assert len(mold_calls) >= 1

    @pytest.mark.asyncio
    async def test_mold_hysteresis_clearing(
        self, hass, mock_config_entry,
    ):
        """Prevention should deactivate only when surface RH drops below hysteresis threshold."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_prevention_enabled": True,
            "mold_prevention_intensity": "medium",
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)

        # Cycle 1: High risk → prevention activates
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity="75.0", outdoor_temp="0.0",
            ),
        )
        data = await coordinator._async_update_data()
        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_prevention_active"] is True

        # Cycle 2: Conditions improve (warm outside) → risk ok, surface RH well below threshold
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity="40.0", outdoor_temp="15.0",
            ),
        )
        data = await coordinator._async_update_data()
        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_prevention_active"] is False
        assert room["mold_prevention_delta"] == 0.0

    @pytest.mark.asyncio
    async def test_mold_warning_triggers_prevention(
        self, hass, mock_config_entry,
    ):
        """WARNING-level surface RH should trigger prevention (not just CRITICAL)."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_prevention_enabled": True,
            "mold_prevention_intensity": "medium",
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        # Conditions that produce WARNING (surface RH 70-80%) but room humidity below threshold
        # 20°C, 60% RH, 5°C outside → surface ~16°C, surface RH ~76% (WARNING)
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                temp="20.0", humidity="60.0", outdoor_temp="5.0",
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_risk_level"] == "warning"
        assert room["mold_prevention_active"] is True
        assert room["mold_prevention_delta"] == 2.0

    @pytest.mark.asyncio
    async def test_mold_no_outdoor_sensor_fallback(
        self, hass, mock_config_entry,
    ):
        """Without outdoor temp sensor, conservative fallback should be used."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_detection_enabled": True,
            # No outdoor_temp_sensor
        }
        hass.data = {"roommind": {"store": store}}
        # 70% room humidity → fallback = 80% surface RH → critical
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(humidity="70.0"),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_risk_level"] == "critical"
        assert room["mold_surface_rh"] == pytest.approx(80.0, abs=0.1)


class TestClimateControlDisabled:
    """Tests for learn-only mode (climate_control_active=False)."""

    @pytest.mark.asyncio
    async def test_no_service_calls_when_climate_control_disabled(
        self, hass, mock_config_entry
    ):
        """When climate_control_active is False, no climate service calls are made."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {"climate_control_active": False}
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(temp="18.0", humidity="55.0"),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        # No climate.* service calls at all
        climate_calls = [
            c for c in hass.services.async_call.call_args_list
            if c[0][0] == "climate"
        ]
        assert climate_calls == [], f"Expected no climate calls, got {climate_calls}"

    @pytest.mark.asyncio
    async def test_mode_is_idle_when_climate_control_disabled(
        self, hass, mock_config_entry
    ):
        """Room mode should be idle when climate control is disabled."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {"climate_control_active": False}
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(temp="18.0", humidity="55.0"),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mode"] == "idle"

    @pytest.mark.asyncio
    async def test_observed_heating_trains_ekf_as_heating(
        self, hass, mock_config_entry
    ):
        """When device is self-regulating (hvac_action=heating), EKF should train as heating."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {"climate_control_active": False}
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                temp="18.0", humidity="55.0",
                extra={
                    "climate.living_room": (
                        "heat",
                        {"hvac_action": "heating", "current_temperature": 18},
                    ),
                },
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        # Run 13 cycles: 6 to first EKF flush (init only), 6 more to second flush
        # (actual training), plus 1 extra for safety.
        for _ in range(13):
            data = await coordinator._async_update_data()

        # Display mode reflects observed device state (#36)
        room = data["rooms"]["living_room_abc12345"]
        assert room["mode"] == "heating"
        assert room["heating_power"] == 100

        # EKF should have trained with heating mode
        n_idle, n_heating, n_cooling = coordinator._model_manager.get_mode_counts(
            "living_room_abc12345",
        )
        assert n_heating > 0, "EKF should have trained with heating observations"

    @pytest.mark.asyncio
    async def test_missing_hvac_action_skips_training(
        self, hass, mock_config_entry
    ):
        """Device in heat mode without hvac_action → training should be skipped."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {"climate_control_active": False}
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                temp="18.0", humidity="55.0",
                extra={
                    "climate.living_room": (
                        "heat",
                        {"current_temperature": 18},
                    ),
                },
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        for _ in range(13):
            await coordinator._async_update_data()

        n_idle, n_heating, n_cooling = coordinator._model_manager.get_mode_counts(
            "living_room_abc12345",
        )
        assert n_idle == 0 and n_heating == 0 and n_cooling == 0, (
            "No training should occur when hvac_action is missing"
        )

    @pytest.mark.asyncio
    async def test_inferred_heating_does_not_affect_previous_modes(
        self, hass, mock_config_entry
    ):
        """Display mode (inferred heating) must not contaminate _previous_modes."""
        room = {**SAMPLE_ROOM, "heating_system_type": "radiator"}
        store = _make_store_mock({"living_room_abc12345": room})
        store.get_settings.return_value = {"climate_control_active": False}
        hass.data = {"roommind": {"store": store}}

        # Thermostat in heat mode, no hvac_action → inferred heating for display
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                temp="18.0", humidity="55.0",
                extra={
                    "climate.living_room": (
                        "heat",
                        {"current_temperature": 18, "temperature": 30},
                    ),
                },
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_data = data["rooms"]["living_room_abc12345"]
        # Display should show heating (inferred from hvac_mode + setpoint)
        assert room_data["mode"] == "heating"
        # Internal _previous_modes must stay idle (no side effects)
        assert coordinator._previous_modes.get("living_room_abc12345") == "idle"
        # Residual heat tracking must not be triggered
        assert "living_room_abc12345" not in coordinator._residual_tracker._on_since

    @pytest.mark.asyncio
    async def test_device_off_trains_as_idle(
        self, hass, mock_config_entry
    ):
        """Device explicitly off → EKF trains as idle."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {"climate_control_active": False}
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                temp="18.0", humidity="55.0",
                extra={
                    "climate.living_room": (
                        "off",
                        {"current_temperature": 18},
                    ),
                },
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        for _ in range(13):
            await coordinator._async_update_data()

        n_idle, n_heating, n_cooling = coordinator._model_manager.get_mode_counts(
            "living_room_abc12345",
        )
        assert n_idle > 0, "EKF should have trained with idle observations"
        assert n_heating == 0

    @pytest.mark.asyncio
    async def test_observed_cooling_trains_ekf_as_cooling(
        self, hass, mock_config_entry
    ):
        """AC with hvac_action=cooling → EKF trains as cooling."""
        room_with_ac = {
            **SAMPLE_ROOM,
            "thermostats": [],
            "acs": ["climate.living_room_ac"],
            "climate_mode": "cool_only",
        }
        store = _make_store_mock({"living_room_abc12345": room_with_ac})
        store.get_settings.return_value = {"climate_control_active": False}
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                temp="25.0", humidity="55.0",
                extra={
                    "climate.living_room_ac": (
                        "cool",
                        {"hvac_action": "cooling", "current_temperature": 25, "hvac_modes": ["cool", "off"]},
                    ),
                },
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        for _ in range(13):
            await coordinator._async_update_data()

        n_idle, n_heating, n_cooling = coordinator._model_manager.get_mode_counts(
            "living_room_abc12345",
        )
        assert n_cooling > 0, "EKF should have trained with cooling observations"

    @pytest.mark.asyncio
    async def test_conflicting_actions_skip_training(
        self, hass, mock_config_entry
    ):
        """Thermostat heating + AC cooling simultaneously → skip training."""
        room_both = {
            **SAMPLE_ROOM,
            "thermostats": ["climate.living_room"],
            "acs": ["climate.living_room_ac"],
        }
        store = _make_store_mock({"living_room_abc12345": room_both})
        store.get_settings.return_value = {"climate_control_active": False}
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                temp="20.0", humidity="55.0",
                extra={
                    "climate.living_room": (
                        "heat",
                        {"hvac_action": "heating", "current_temperature": 20},
                    ),
                    "climate.living_room_ac": (
                        "cool",
                        {"hvac_action": "cooling", "current_temperature": 20, "hvac_modes": ["cool", "off"]},
                    ),
                },
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        for _ in range(13):
            await coordinator._async_update_data()

        n_idle, n_heating, n_cooling = coordinator._model_manager.get_mode_counts(
            "living_room_abc12345",
        )
        assert n_idle == 0 and n_heating == 0 and n_cooling == 0, (
            "No training when actions conflict"
        )

    @pytest.mark.asyncio
    async def test_unavailable_device_skips_training(
        self, hass, mock_config_entry
    ):
        """Unavailable climate device → skip training."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {"climate_control_active": False}
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                temp="18.0", humidity="55.0",
                extra={
                    "climate.living_room": ("unavailable", {}),
                },
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        for _ in range(13):
            await coordinator._async_update_data()

        n_idle, n_heating, n_cooling = coordinator._model_manager.get_mode_counts(
            "living_room_abc12345",
        )
        assert n_idle == 0 and n_heating == 0 and n_cooling == 0

    @pytest.mark.asyncio
    async def test_observe_device_action_unit(self, hass, mock_config_entry):
        """Unit test for _observe_device_action with various device states."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        room = SAMPLE_ROOM

        # Device off → idle
        s = MagicMock()
        s.state = "off"
        s.attributes = {}
        hass.states.get = MagicMock(return_value=s)
        assert coordinator._observe_device_action(room) == ("idle", 0.0)

        # Device heating via hvac_action
        s = MagicMock()
        s.state = "heat"
        s.attributes = {"hvac_action": "heating"}
        hass.states.get = MagicMock(return_value=s)
        assert coordinator._observe_device_action(room) == ("heating", 1.0)

        # Device cooling via hvac_action
        s = MagicMock()
        s.state = "cool"
        s.attributes = {"hvac_action": "cooling"}
        hass.states.get = MagicMock(return_value=s)
        assert coordinator._observe_device_action(room) == ("cooling", 1.0)

        # Device in heat mode, hvac_action idle
        s = MagicMock()
        s.state = "heat"
        s.attributes = {"hvac_action": "idle"}
        hass.states.get = MagicMock(return_value=s)
        assert coordinator._observe_device_action(room) == ("idle", 0.0)

        # Device in heat mode, no hvac_action → unobservable
        s = MagicMock()
        s.state = "heat"
        s.attributes = {}
        hass.states.get = MagicMock(return_value=s)
        assert coordinator._observe_device_action(room) == (None, 0.0)

        # Device unavailable → unobservable
        s = MagicMock()
        s.state = "unavailable"
        s.attributes = {}
        hass.states.get = MagicMock(return_value=s)
        assert coordinator._observe_device_action(room) == (None, 0.0)

        # Device drying → unobservable (unknown thermal effect)
        s = MagicMock()
        s.state = "dry"
        s.attributes = {"hvac_action": "drying"}
        hass.states.get = MagicMock(return_value=s)
        assert coordinator._observe_device_action(room) == (None, 0.0)

        # Device not found → unobservable
        hass.states.get = MagicMock(return_value=None)
        assert coordinator._observe_device_action(room) == (None, 0.0)

        # Preheating → treated as heating
        s = MagicMock()
        s.state = "heat"
        s.attributes = {"hvac_action": "preheating"}
        hass.states.get = MagicMock(return_value=s)
        assert coordinator._observe_device_action(room) == ("heating", 1.0)


class TestFahrenheitConversion:
    """Tests for Fahrenheit temperature conversion at system boundaries."""

    @pytest.mark.asyncio
    async def test_fahrenheit_sensor_converted_to_celsius(
        self, hass, mock_config_entry
    ):
        """When HA is in Fahrenheit, sensor temps are converted to Celsius internally."""
        from homeassistant.const import UnitOfTemperature

        hass.config.units.temperature_unit = UnitOfTemperature.FAHRENHEIT

        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}

        # Sensor reports 64.4°F (= 18°C), outdoor 50°F (= 10°C)
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                temp="64.4",
                humidity="55.0",
                outdoor_temp="50",
                temp_unit="°F",
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        # Internal current_temp should be Celsius (~18°C)
        assert room["current_temp"] == pytest.approx(18.0, abs=0.1)
        # Target temp should remain in Celsius (comfort_temp=21°C stored in Celsius)
        assert room["target_temp"] == pytest.approx(21.0, abs=0.1)
        # Mode should be heating (18°C < 21°C target)
        assert room["mode"] == "heating"

    @pytest.mark.asyncio
    async def test_valve_protection_set_temperature_in_fahrenheit(
        self, hass, mock_config_entry
    ):
        """Valve protection set_temperature uses Fahrenheit when HA is in °F mode."""
        from homeassistant.const import UnitOfTemperature
        from custom_components.roommind.const import HEATING_BOOST_TARGET

        hass.config.units.temperature_unit = UnitOfTemperature.FAHRENHEIT

        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "valve_protection_enabled": True,
            "valve_protection_interval_days": 7,
        }
        store.async_save_settings = AsyncMock()
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(temp="69.8", temp_unit="°F"),  # 69.8°F ≈ 21°C
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._valve_manager._last_actuation["climate.living_room"] = (
            time.time() - 8 * 86400
        )
        coordinator._valve_manager._check_count = 119
        await coordinator._async_update_data()

        assert "climate.living_room" in coordinator._valve_manager._cycling

        # Find set_temperature calls for the cycling valve
        set_temp_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if c[0][0] == "climate"
            and c[0][1] == "set_temperature"
            and c[0][2].get("entity_id") == "climate.living_room"
        ]
        assert set_temp_calls
        # HEATING_BOOST_TARGET is 30°C → 86°F
        expected_f = HEATING_BOOST_TARGET * 9 / 5 + 32  # 86°F
        temp_arg = set_temp_calls[0][0][2]["temperature"]
        assert temp_arg == pytest.approx(expected_f)


# ---------------------------------------------------------------------------
# Static / helper method tests (outside the class to avoid large nesting)
# ---------------------------------------------------------------------------


class TestExtractCloudSeries:
    """Tests for _extract_cloud_series."""

    def test_empty_forecast(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        assert WeatherManager.extract_cloud_series([]) is None

    def test_all_none_cloud(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        forecast = [{"temperature": 5}, {"temperature": 6}]
        assert WeatherManager.extract_cloud_series(forecast) is None

    def test_some_valid_cloud(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        forecast = [
            {"temperature": 5, "cloud_coverage": 50},
            {"temperature": 6},
            {"temperature": 7, "cloud_coverage": 80},
        ]
        result = WeatherManager.extract_cloud_series(forecast)
        assert result == [50.0, None, 80.0]


class TestConvertForecastTemps:
    """Tests for _convert_forecast_temps."""

    def test_with_temperature(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        forecasts = [{"temperature": 5.0, "other": "val"}, {"temperature": 10.0}]
        result = coordinator._weather_manager._convert_forecast_temps(forecasts)
        assert result[0]["temperature"] == 5.0
        assert result[0]["other"] == "val"
        assert result[1]["temperature"] == 10.0

    def test_without_temperature(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        forecasts = [{"cloud_coverage": 50}]
        result = coordinator._weather_manager._convert_forecast_temps(forecasts)
        assert result == [{"cloud_coverage": 50}]


class TestReadDeviceTemp:
    """Tests for _read_device_temp."""

    def test_reads_from_thermostat(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        state = MagicMock()
        state.attributes = {"current_temperature": 21.5}
        hass.states.get = MagicMock(return_value=state)

        room = {"thermostats": ["climate.trv1"], "acs": []}
        assert coordinator._read_device_temp(room) == 21.5

    def test_reads_from_ac_when_no_thermostat(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        state = MagicMock()
        state.attributes = {"current_temperature": 25.0}
        hass.states.get = MagicMock(return_value=state)

        room = {"thermostats": [], "acs": ["climate.ac1"]}
        assert coordinator._read_device_temp(room) == 25.0

    def test_no_devices(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        room = {"thermostats": [], "acs": []}
        assert coordinator._read_device_temp(room) is None

    def test_state_is_none(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        hass.states.get = MagicMock(return_value=None)
        room = {"thermostats": ["climate.trv1"], "acs": []}
        assert coordinator._read_device_temp(room) is None

    def test_invalid_temperature_value(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        state = MagicMock()
        state.attributes = {"current_temperature": "unknown"}
        hass.states.get = MagicMock(return_value=state)

        room = {"thermostats": ["climate.trv1"], "acs": []}
        assert coordinator._read_device_temp(room) is None

    def test_no_current_temp_attribute(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        state = MagicMock()
        state.attributes = {"temperature": 21.0}  # different key
        hass.states.get = MagicMock(return_value=state)

        room = {"thermostats": ["climate.trv1"], "acs": []}
        assert coordinator._read_device_temp(room) is None


class TestFlushEkfAccumulator:
    """Tests for _flush_ekf_accumulator."""

    def test_no_accumulated_data(self, hass, mock_config_entry):
        """Flush with no accumulated data is a no-op."""
        coordinator = _create_coordinator(hass, mock_config_entry)
        # Should not raise
        coordinator._flush_ekf_accumulator("room_a", 20.0, 5.0, {"thermostats": [], "acs": []})

    def test_accumulated_without_mode(self, hass, mock_config_entry):
        """Flush with accumulated dt but no mode is a no-op."""
        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._ekf_accumulated_dt["room_a"] = 3.0
        # prev_mode not set -> should not call update
        coordinator._flush_ekf_accumulator("room_a", 20.0, 5.0, {"thermostats": [], "acs": []})

    def test_accumulated_with_mode_calls_update(self, hass, mock_config_entry):
        """Flush with accumulated data and mode calls model update."""
        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._ekf_accumulated_dt["room_a"] = 3.0
        coordinator._ekf_accumulated_mode["room_a"] = "heating"
        coordinator._ekf_accumulated_pf["room_a"] = 0.8

        with patch.object(coordinator._model_manager, "update") as mock_update:
            coordinator._flush_ekf_accumulator("room_a", 20.0, 5.0, {"thermostats": [], "acs": []})
            mock_update.assert_called_once()


class TestReadWeatherForecast:
    """Tests for _read_weather_forecast."""

    @pytest.mark.asyncio
    async def test_no_weather_entity(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        result = await coordinator._weather_manager.async_read_forecast({})
        assert result == []

    @pytest.mark.asyncio
    async def test_empty_weather_entity(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        result = await coordinator._weather_manager.async_read_forecast({"weather_entity": ""})
        assert result == []

    @pytest.mark.asyncio
    async def test_modern_service_success(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        hass.services.async_call = AsyncMock(return_value={
            "weather.home": {
                "forecast": [
                    {"temperature": 5.0, "cloud_coverage": 50},
                    {"temperature": 6.0, "cloud_coverage": 80},
                ]
            }
        })
        result = await coordinator._weather_manager.async_read_forecast({"weather_entity": "weather.home"})
        assert len(result) == 2
        assert result[0]["temperature"] == 5.0

    @pytest.mark.asyncio
    async def test_modern_service_fails_fallback_to_state(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        hass.services.async_call = AsyncMock(side_effect=RuntimeError("not supported"))
        state = MagicMock()
        state.attributes = {
            "forecast": [{"temperature": 7.0}]
        }
        hass.states.get = MagicMock(return_value=state)

        result = await coordinator._weather_manager.async_read_forecast({"weather_entity": "weather.home"})
        assert len(result) == 1
        assert result[0]["temperature"] == 7.0

    @pytest.mark.asyncio
    async def test_fallback_state_is_none(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        hass.services.async_call = AsyncMock(side_effect=RuntimeError("fail"))
        hass.states.get = MagicMock(return_value=None)

        result = await coordinator._weather_manager.async_read_forecast({"weather_entity": "weather.home"})
        assert result == []

    @pytest.mark.asyncio
    async def test_fallback_no_forecast_attribute(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        hass.services.async_call = AsyncMock(side_effect=RuntimeError("fail"))
        state = MagicMock()
        state.attributes = {}
        hass.states.get = MagicMock(return_value=state)

        result = await coordinator._weather_manager.async_read_forecast({"weather_entity": "weather.home"})
        assert result == []


class TestValveProtectionFinish:
    """Tests for _async_valve_protection_finish."""

    @pytest.mark.asyncio
    async def test_no_cycling_is_noop(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        # No cycling entries -> should return immediately
        await coordinator._valve_manager.async_finish_cycles()
        hass.services.async_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_finishes_expired_cycle(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        hass.services.async_call = AsyncMock()
        # Valve has been cycling for longer than VALVE_PROTECTION_CYCLE_DURATION
        coordinator._valve_manager._cycling["climate.trv1"] = time.time() - 120

        await coordinator._valve_manager.async_finish_cycles()

        assert "climate.trv1" not in coordinator._valve_manager._cycling
        assert "climate.trv1" in coordinator._valve_manager._last_actuation
        assert coordinator._valve_manager._actuation_dirty is True

    @pytest.mark.asyncio
    async def test_finish_exception_still_cleans_up(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        hass.services.async_call = AsyncMock(side_effect=RuntimeError("fail"))
        coordinator._valve_manager._cycling["climate.trv1"] = time.time() - 120

        await coordinator._valve_manager.async_finish_cycles()

        # Still cleaned up despite exception
        assert "climate.trv1" not in coordinator._valve_manager._cycling
        assert "climate.trv1" in coordinator._valve_manager._last_actuation


class TestValveProtectionCheck:
    """Tests for _async_valve_protection_check."""

    @pytest.mark.asyncio
    async def test_disabled_clears_active_cycles(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        hass.services.async_call = AsyncMock()
        coordinator._valve_manager._cycling["climate.trv1"] = time.time()

        settings = {"valve_protection_enabled": False}
        await coordinator._valve_manager.async_check_and_cycle({}, settings)

        assert len(coordinator._valve_manager._cycling) == 0

    @pytest.mark.asyncio
    async def test_starts_cycling_stale_valve(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        hass.services.async_call = AsyncMock()
        eid_state = MagicMock()
        eid_state.attributes = {"max_temp": 30}
        hass.states.get = MagicMock(return_value=eid_state)

        rooms = {"room_a": {"thermostats": ["climate.trv1"]}}
        settings = {"valve_protection_enabled": True, "valve_protection_interval_days": 7}

        # Valve was last actuated > 7 days ago
        coordinator._valve_manager._last_actuation["climate.trv1"] = time.time() - 8 * 86400

        await coordinator._valve_manager.async_check_and_cycle(rooms, settings)

        assert "climate.trv1" in coordinator._valve_manager._cycling
        assert hass.services.async_call.call_count >= 1

    @pytest.mark.asyncio
    async def test_skips_already_cycling(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        hass.services.async_call = AsyncMock()

        rooms = {"room_a": {"thermostats": ["climate.trv1"]}}
        settings = {"valve_protection_enabled": True, "valve_protection_interval_days": 7}

        # Already cycling
        coordinator._valve_manager._cycling["climate.trv1"] = time.time()
        coordinator._valve_manager._last_actuation["climate.trv1"] = time.time() - 8 * 86400

        await coordinator._valve_manager.async_check_and_cycle(rooms, settings)

        # Should not call any service (already cycling)
        hass.services.async_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleans_up_stale_entries(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        hass.services.async_call = AsyncMock()

        # Entity in actuation dict but not in any room
        coordinator._valve_manager._last_actuation["climate.old_trv"] = time.time()
        rooms = {"room_a": {"thermostats": ["climate.trv1"]}}
        settings = {"valve_protection_enabled": True, "valve_protection_interval_days": 7}

        await coordinator._valve_manager.async_check_and_cycle(rooms, settings)

        assert "climate.old_trv" not in coordinator._valve_manager._last_actuation
        assert coordinator._valve_manager._actuation_dirty is True


class TestComputeTrvSetpoint:
    """Tests for _compute_trv_setpoint static method."""

    def test_idle_returns_none(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        result = coordinator._compute_trv_setpoint("idle", 0.5, 20.0, 21.0, True)
        assert result is None

    def test_no_external_sensor_returns_none(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        result = coordinator._compute_trv_setpoint("heating", 0.5, 20.0, 21.0, False)
        assert result is None

    def test_none_current_temp_returns_none(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        result = coordinator._compute_trv_setpoint("heating", 0.5, None, 21.0, True)
        assert result is None

    def test_heating_computes_setpoint(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        # power_fraction=0.5, current=20, target=21, boost=30
        # trv = 20 + 0.5 * (30 - 20) = 25.0
        result = coordinator._compute_trv_setpoint("heating", 0.5, 20.0, 21.0, True)
        assert result == 25.0

    def test_heating_floor_at_target(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        # power_fraction=0.01, current=20, target=21
        # trv = 20 + 0.01 * (30 - 20) = 20.1 → clamped to target 21.0
        result = coordinator._compute_trv_setpoint("heating", 0.01, 20.0, 21.0, True)
        assert result == 21.0

    def test_clamped_to_device_max_temp(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        # power_fraction=0.5, current=20 → trv = 25.0, but device max is 25
        result = coordinator._compute_trv_setpoint("heating", 0.5, 20.0, 21.0, True, device_max_temp=25.0)
        assert result == 25.0
        # power_fraction=1.0, current=20 → trv = 30.0, but device max is 25
        result = coordinator._compute_trv_setpoint("heating", 1.0, 20.0, 21.0, True, device_max_temp=25.0)
        assert result == 25.0

    def test_device_max_temp_none_no_clamping(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        # Without device_max_temp, should reach 30 (HEATING_BOOST_TARGET)
        result = coordinator._compute_trv_setpoint("heating", 1.0, 20.0, 21.0, True, device_max_temp=None)
        assert result == 30.0


# ---------------------------------------------------------------------------
# Residual heat tracking tests
# ---------------------------------------------------------------------------


class TestResidualHeatTracking:
    """Tests for residual heat transition tracking in the coordinator."""

    @pytest.mark.asyncio
    async def test_no_tracking_without_system_type(self, hass, mock_config_entry):
        """Without heating_system_type, no residual tracking should occur."""
        room = {**SAMPLE_ROOM}
        # Default: no heating_system_type
        store = _make_store_mock(rooms={room["area_id"]: room})
        store.get_settings.return_value = {"climate_control_active": True}
        hass.data = {"roommind": {"store": store}}
        hass.states.get = make_mock_states_get(
            temp="18.0", schedule_state="on",
            schedule_attrs={"current_event": True, "friendly_name": "Living Room Heating"},
        )
        hass.services.async_call = AsyncMock()
        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        assert room["area_id"] not in coordinator._residual_tracker._off_since
        assert room["area_id"] not in coordinator._residual_tracker._on_since

    @pytest.mark.asyncio
    async def test_tracking_with_system_type(self, hass, mock_config_entry):
        """With heating_system_type, transition tracking should populate dicts."""
        room = {**SAMPLE_ROOM, "heating_system_type": "underfloor"}
        store = _make_store_mock(rooms={room["area_id"]: room})
        store.get_settings.return_value = {"climate_control_active": True}
        hass.data = {"roommind": {"store": store}}
        hass.states.get = make_mock_states_get(
            temp="18.0", schedule_state="on",
            schedule_attrs={"current_event": True, "friendly_name": "Living Room Heating"},
        )
        hass.services.async_call = AsyncMock()
        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        # After first cycle: room should be heating, so _heating_on_since tracked
        assert room["area_id"] in coordinator._residual_tracker._on_since

    @pytest.mark.asyncio
    async def test_heating_to_idle_transition_populates_off_since(self, hass, mock_config_entry):
        """When mode transitions from heating to idle, _heating_off_since should be set."""
        room = {**SAMPLE_ROOM, "heating_system_type": "underfloor"}
        store = _make_store_mock(rooms={room["area_id"]: room})
        store.get_settings.return_value = {"climate_control_active": True}
        hass.data = {"roommind": {"store": store}}
        hass.services.async_call = AsyncMock()
        aid = room["area_id"]

        # Cycle 1: heating (temp below target, schedule on)
        hass.states.get = make_mock_states_get(
            temp="18.0", schedule_state="on",
            schedule_attrs={"current_event": True, "friendly_name": "Heat"},
        )
        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()
        assert aid in coordinator._residual_tracker._on_since
        assert coordinator._previous_modes.get(aid) == "heating"

        # Backdate mode_on_since so the min-run window has already elapsed
        coordinator._mode_on_since[aid] = time.time() - 10000

        # Cycle 2: idle (schedule off -> eco 17, temp 18 above eco -> idle)
        hass.states.get = make_mock_states_get(
            temp="18.0", schedule_state="off",
            schedule_attrs={"current_event": False, "friendly_name": "Heat"},
        )
        await coordinator._async_update_data()

        # Transition to idle should populate _heating_off_since
        assert aid in coordinator._residual_tracker._off_since
        # Heating start should still be tracked (needed for charge fraction)
        assert aid in coordinator._residual_tracker._on_since

    @pytest.mark.asyncio
    async def test_reheat_clears_residual_tracking(self, hass, mock_config_entry):
        """When heating restarts, _heating_off_since should be cleared."""
        room = {**SAMPLE_ROOM, "heating_system_type": "radiator"}
        store = _make_store_mock(rooms={room["area_id"]: room})
        store.get_settings.return_value = {"climate_control_active": True}
        hass.data = {"roommind": {"store": store}}
        hass.services.async_call = AsyncMock()
        aid = room["area_id"]

        # Cycle 1: heating
        hass.states.get = make_mock_states_get(
            temp="18.0", schedule_state="on",
            schedule_attrs={"current_event": True, "friendly_name": "Heat"},
        )
        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()
        assert coordinator._previous_modes.get(aid) == "heating"

        # Backdate mode_on_since so the min-run window has already elapsed
        coordinator._mode_on_since[aid] = time.time() - 10000

        # Cycle 2: idle
        hass.states.get = make_mock_states_get(
            temp="18.0", schedule_state="off",
            schedule_attrs={"current_event": False, "friendly_name": "Heat"},
        )
        await coordinator._async_update_data()
        assert aid in coordinator._residual_tracker._off_since

        # Cycle 3: heating again
        hass.states.get = make_mock_states_get(
            temp="16.0", schedule_state="on",
            schedule_attrs={"current_event": True, "friendly_name": "Heat"},
        )
        await coordinator._async_update_data()
        # Reheating should clear off_since and reset on_since
        assert aid not in coordinator._residual_tracker._off_since
        assert aid in coordinator._residual_tracker._on_since

    @pytest.mark.asyncio
    async def test_room_removal_cleans_residual_dicts(self, hass, mock_config_entry):
        """Removing a room should clean up residual heat tracking dicts."""
        room = {**SAMPLE_ROOM, "heating_system_type": "underfloor"}
        store = _make_store_mock(rooms={room["area_id"]: room})
        store.get_settings.return_value = {"climate_control_active": True}
        hass.data = {"roommind": {"store": store}}
        hass.services.async_call = AsyncMock()
        aid = room["area_id"]

        coordinator = _create_coordinator(hass, mock_config_entry)
        # Manually populate tracking dicts (simulates active heating)
        coordinator._residual_tracker._on_since[aid] = time.time() - 600
        coordinator._residual_tracker._off_since[aid] = time.time() - 60
        coordinator._residual_tracker._off_power[aid] = 0.8

        # Now remove the room
        with patch("homeassistant.helpers.entity_registry.async_get") as mock_get, \
             patch.object(coordinator, "async_request_refresh", new_callable=AsyncMock):
            mock_registry = MagicMock()
            mock_registry.entities = MagicMock()
            mock_registry.entities.values.return_value = []
            mock_get.return_value = mock_registry
            await coordinator.async_room_removed(aid)

        assert aid not in coordinator._residual_tracker._off_since
        assert aid not in coordinator._residual_tracker._off_power
        assert aid not in coordinator._residual_tracker._on_since

    @pytest.mark.asyncio
    async def test_underfloor_window_delay_respects_user_config(self, hass, mock_config_entry):
        """Underfloor rooms respect the user-configured window open delay.

        With window_open_delay=0, underfloor rooms pause immediately just
        like standard rooms (no backend override).
        """
        room = {
            **SAMPLE_ROOM,
            "heating_system_type": "underfloor",
            "window_sensors": ["binary_sensor.window"],
            "window_open_delay": 0,
        }
        store = _make_store_mock(rooms={room["area_id"]: room})
        store.get_settings.return_value = {"climate_control_active": True}
        hass.data = {"roommind": {"store": store}}
        hass.states.get = make_mock_states_get(
            temp="20.0", schedule_state="on",
            schedule_attrs={"current_event": True, "friendly_name": "Living Room Heating"},
            window_sensors={"binary_sensor.window": "on"},
        )
        hass.services.async_call = AsyncMock()
        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        # With delay=0 and window open, underfloor room pauses immediately
        assert coordinator._window_manager._paused.get(room["area_id"], False)


# ---------------------------------------------------------------------------
# Coverage gap tests
# ---------------------------------------------------------------------------


class TestCoverageGaps:
    """Tests covering uncovered coordinator lines."""

    @pytest.mark.asyncio
    async def test_get_area_name_returns_area_id_when_area_none(self, hass, mock_config_entry):
        """_get_area_name returns area_id when area is not found."""
        from custom_components.roommind.coordinator import _get_area_name

        mock_reg = MagicMock()
        mock_reg.async_get_area.return_value = None
        with patch("custom_components.roommind.coordinator.ar.async_get", return_value=mock_reg):
            result = _get_area_name(hass, "nonexistent_area")
        assert result == "nonexistent_area"

    @pytest.mark.asyncio
    async def test_load_thermal_data_from_store(self, hass, mock_config_entry):
        """Thermal data is loaded from store on first run."""
        from custom_components.roommind.control.thermal_model import RoomModelManager, ThermalEKF

        ekf = ThermalEKF()
        ekf.update(20.0, 10.0, "idle", 5.0)
        ekf.update(19.5, 10.0, "idle", 5.0)
        mgr = RoomModelManager()
        mgr._estimators["living_room_abc12345"] = ekf
        thermal_data = mgr.to_dict()

        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_thermal_data.return_value = thermal_data
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        # Verify the model was loaded from store (estimator exists with prior data)
        est = coordinator._model_manager.get_estimator("living_room_abc12345")
        assert est._n_updates >= 1

    @pytest.mark.asyncio
    async def test_cloud_coverage_read_from_weather_entity(self, hass, mock_config_entry):
        """Cloud coverage is read from weather entity attributes."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {"weather_entity": "weather.home"}
        hass.data = {"roommind": {"store": store}}

        weather_state = MagicMock()
        weather_state.attributes = {"cloud_coverage": 75}

        hass.states.get = MagicMock(side_effect=make_mock_states_get(
            extra={"weather.home": ("sunny", {"cloud_coverage": 75})},
        ))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        # No assertion on exact value; just verify it ran without error
        assert coordinator._current_q_solar is not None

    @pytest.mark.asyncio
    async def test_process_room_exception_skips_room(self, hass, mock_config_entry):
        """Exception in _async_process_room is caught and room is skipped."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)

        with patch.object(coordinator, "_async_process_room", side_effect=RuntimeError("boom")):
            data = await coordinator._async_update_data()

        assert data["rooms"] == {}

    @pytest.mark.asyncio
    async def test_history_skip_learning_disabled_rooms(self, hass, mock_config_entry):
        """Learning-disabled rooms are skipped in history recording."""
        from custom_components.roommind.const import HISTORY_WRITE_CYCLES

        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "learning_disabled_rooms": ["living_room_abc12345"],
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._history_write_count = HISTORY_WRITE_CYCLES - 1
        data = await coordinator._async_update_data()

        # Room should still be processed
        assert "living_room_abc12345" in data["rooms"]
        # But no prediction should have been stored
        assert "living_room_abc12345" not in coordinator._pending_predictions

    @pytest.mark.asyncio
    async def test_thermal_save_periodically(self, hass, mock_config_entry):
        """Thermal data is saved when thermal save cycle reaches threshold."""
        from custom_components.roommind.const import THERMAL_SAVE_CYCLES

        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.async_save_settings = AsyncMock()
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._thermal_save_count = THERMAL_SAVE_CYCLES - 1
        await coordinator._async_update_data()

        store.async_save_thermal_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_history_rotation_periodically(self, hass, mock_config_entry):
        """History is rotated when rotation cycle reaches threshold."""
        from custom_components.roommind.const import HISTORY_ROTATE_CYCLES

        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._history_rotate_count = HISTORY_ROTATE_CYCLES - 1
        await coordinator._async_update_data()

        # Rotation should have been called (async_add_executor_job with rotate)
        assert coordinator._history_rotate_count == 0

    @pytest.mark.asyncio
    async def test_valve_actuation_persistence(self, hass, mock_config_entry):
        """Valve actuation timestamps are persisted on thermal save cycle."""
        from custom_components.roommind.const import THERMAL_SAVE_CYCLES

        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.async_save_settings = AsyncMock()
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="18.0"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._valve_manager.actuation_dirty = True
        coordinator._valve_manager._last_actuation["climate.living_room"] = time.time()
        coordinator._thermal_save_count = THERMAL_SAVE_CYCLES - 1
        await coordinator._async_update_data()

        store.async_save_settings.assert_called()
        assert coordinator._valve_manager.actuation_dirty is False

    @pytest.mark.asyncio
    async def test_device_temp_fallback_no_external_sensor(self, hass, mock_config_entry):
        """Without external temp sensor, current_temperature is read from device."""
        room_no_sensor = {
            **SAMPLE_ROOM,
            "temperature_sensor": "",
        }
        store = _make_store_mock({"living_room_abc12345": room_no_sensor})
        hass.data = {"roommind": {"store": store}}

        device_state = MagicMock()
        device_state.state = "heat"
        device_state.attributes = {
            "current_temperature": 19.5,
            "temperature": 21.0,
            "hvac_modes": ["off", "heat"],
        }
        base_mock = make_mock_states_get(temp=None)

        def custom_get(eid):
            if eid == "climate.living_room":
                return device_state
            return base_mock(eid)

        hass.states.get = MagicMock(side_effect=custom_get)
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["current_temp"] == 19.5

    @pytest.mark.asyncio
    async def test_heat_only_climate_mode_target(self, hass, mock_config_entry):
        """heat_only climate mode uses heat target for display."""
        room_heat_only = {**SAMPLE_ROOM, "climate_mode": "heat_only"}
        store = _make_store_mock({"living_room_abc12345": room_heat_only})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["target_temp"] == 21.0

    @pytest.mark.asyncio
    async def test_cool_only_climate_mode_target(self, hass, mock_config_entry):
        """cool_only climate mode uses cool target for display."""
        room_cool_only = {**SAMPLE_ROOM, "climate_mode": "cool_only"}
        store = _make_store_mock({"living_room_abc12345": room_cool_only})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        # cool_only uses cool target (DEFAULT_COMFORT_COOL = 24.0)
        assert room["target_temp"] == 24.0

    @pytest.mark.asyncio
    async def test_mold_prevention_force_off_override(self, hass, mock_config_entry):
        """Mold prevention overrides force_off to prevent structural damage."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_prevention_enabled": True,
            "mold_prevention_intensity": "medium",
            "outdoor_temp_sensor": "sensor.outdoor_temp",
            "presence_enabled": True,
            "presence_persons": ["person.kevin"],
            "presence_away_action": "off",
        }
        hass.data = {"roommind": {"store": store}}
        # Nobody home + mold risk conditions
        hass.states.get = MagicMock(side_effect=make_mock_states_get(
            humidity="75.0", outdoor_temp="0.0",
            person_states={"person.kevin": "not_home"},
        ))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        # Mold prevention should override force_off
        assert room["mold_prevention_active"] is True
        assert room["force_off"] is False

    @pytest.mark.asyncio
    async def test_schedule_split_heat_cool_temps(self, hass, mock_config_entry):
        """Schedule with split heat/cool temperatures."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(
            schedule_attrs={"heat_temperature": 20.0, "cool_temperature": 25.0},
        ))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["heat_target"] == 20.0
        assert room["cool_target"] == 25.0

    @pytest.mark.asyncio
    async def test_schedule_entity_unavailable_uses_comfort(self, hass, mock_config_entry):
        """Unavailable schedule entity falls back to comfort temp."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(
            schedule_state="unavailable",
        ))
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
        hass.states.get = MagicMock(side_effect=make_mock_states_get(
            schedule_attrs={"temperature": "not_a_number"},
        ))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["target_temp"] == 21.0

    @pytest.mark.asyncio
    async def test_climate_control_disabled_observe_device(self, hass, mock_config_entry):
        """When climate control is disabled, device state is observed for display."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {"climate_control_active": False}
        hass.data = {"roommind": {"store": store}}

        device_state = MagicMock()
        device_state.state = "heat"
        device_state.attributes = {
            "hvac_action": "heating",
            "current_temperature": 18.0,
            "temperature": 21.0,
            "hvac_modes": ["off", "heat"],
        }
        base_mock = make_mock_states_get()

        def custom_get(eid):
            if eid == "climate.living_room":
                return device_state
            return base_mock(eid)

        hass.states.get = MagicMock(side_effect=custom_get)
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        # Display should show observed heating
        assert room["mode"] == "heating"
        # But no climate service calls should have been made for this room's control
        climate_calls = [
            c for c in hass.services.async_call.call_args_list
            if c[0][0] == "climate"
        ]
        assert len(climate_calls) == 0

    @pytest.mark.asyncio
    async def test_climate_control_disabled_no_hvac_action_infers_mode(
        self, hass, mock_config_entry
    ):
        """When control disabled and no hvac_action, mode is inferred from hvac_mode."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {"climate_control_active": False}
        hass.data = {"roommind": {"store": store}}

        device_state = MagicMock()
        device_state.state = "heat"
        device_state.attributes = {
            "current_temperature": 18.0,
            "temperature": 21.0,
            "hvac_modes": ["off", "heat"],
        }
        base_mock = make_mock_states_get()

        def custom_get(eid):
            if eid == "climate.living_room":
                return device_state
            return base_mock(eid)

        hass.states.get = MagicMock(side_effect=custom_get)
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        # _infer_device_mode: heat mode, current < setpoint -> heating
        assert room["mode"] == "heating"

    @pytest.mark.asyncio
    async def test_infer_device_mode_at_setpoint_idle(self, hass, mock_config_entry):
        """_infer_device_mode returns idle when device is at setpoint."""
        coordinator = _create_coordinator(hass, mock_config_entry)

        device_state = MagicMock()
        device_state.state = "heat"
        device_state.attributes = {
            "current_temperature": 21.0,
            "temperature": 21.0,
        }
        hass.states.get = MagicMock(return_value=device_state)

        result = coordinator._infer_device_mode({"thermostats": ["climate.trv1"], "acs": []})
        assert result == "idle"

    @pytest.mark.asyncio
    async def test_infer_device_mode_cooling_at_setpoint(self, hass, mock_config_entry):
        """_infer_device_mode returns idle when AC is at/below setpoint."""
        coordinator = _create_coordinator(hass, mock_config_entry)

        device_state = MagicMock()
        device_state.state = "cool"
        device_state.attributes = {
            "current_temperature": 23.0,
            "temperature": 24.0,
        }
        hass.states.get = MagicMock(return_value=device_state)

        result = coordinator._infer_device_mode({"thermostats": [], "acs": ["climate.ac1"]})
        assert result == "idle"

    @pytest.mark.asyncio
    async def test_infer_device_mode_cooling_above_setpoint(self, hass, mock_config_entry):
        """_infer_device_mode returns cooling when AC is above setpoint."""
        coordinator = _create_coordinator(hass, mock_config_entry)

        device_state = MagicMock()
        device_state.state = "cool"
        device_state.attributes = {
            "current_temperature": 26.0,
            "temperature": 24.0,
        }
        hass.states.get = MagicMock(return_value=device_state)

        result = coordinator._infer_device_mode({"thermostats": [], "acs": ["climate.ac1"]})
        assert result == "cooling"

    @pytest.mark.asyncio
    async def test_observe_device_conflicting_actions(self, hass, mock_config_entry):
        """Conflicting device actions returns None (unobservable)."""
        coordinator = _create_coordinator(hass, mock_config_entry)

        def mock_get(eid):
            s = MagicMock()
            if eid == "climate.trv1":
                s.state = "heat"
                s.attributes = {"hvac_action": "heating"}
            elif eid == "climate.ac1":
                s.state = "cool"
                s.attributes = {"hvac_action": "cooling"}
            return s

        hass.states.get = MagicMock(side_effect=mock_get)

        result_mode, result_pf = coordinator._observe_device_action(
            {"thermostats": ["climate.trv1"], "acs": ["climate.ac1"]}
        )
        assert result_mode is None
        assert result_pf == 0.0

    @pytest.mark.asyncio
    async def test_mpc_active_check(self, hass, mock_config_entry):
        """MPC active flag is computed when control_mode is 'mpc'."""
        from custom_components.roommind.control.thermal_model import RCModel

        room = {**SAMPLE_ROOM, "area_id": "mpc_room"}
        store = _make_store_mock({"mpc_room": room})
        store.get_settings.return_value = {
            "control_mode": "mpc",
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(
            temp="18.0", outdoor_temp="5.0",
        ))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        # Pre-train model with low std for MPC activation
        mgr = coordinator._model_manager
        mgr.update("mpc_room", 18.0, 5.0, "heating", 5.0)
        mgr.update("mpc_room", 18.5, 5.0, "heating", 5.0)

        data = await coordinator._async_update_data()

        room_state = data["rooms"]["mpc_room"]
        # mpc_active should be a boolean (either True or False based on model state)
        assert isinstance(room_state["mpc_active"], bool)

    @pytest.mark.asyncio
    async def test_room_removed_cleans_history_store(self, hass, mock_config_entry):
        """async_room_removed calls history_store.remove_room."""
        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator.async_request_refresh = AsyncMock()

        mock_history_store = MagicMock()
        mock_history_store.remove_room = MagicMock()
        coordinator._history_store = mock_history_store

        mock_registry = MagicMock()
        mock_registry.entities = MagicMock()
        mock_registry.entities.values.return_value = []
        with patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=mock_registry,
        ):
            await coordinator.async_room_removed("test_room")

        mock_history_store.remove_room.assert_called_once_with("test_room")

    @pytest.mark.asyncio
    async def test_history_write_computes_prediction(self, hass, mock_config_entry):
        """History write cycle computes predictions for next cycle."""
        from custom_components.roommind.const import HISTORY_WRITE_CYCLES

        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(
            temp="18.0", outdoor_temp="5.0",
        ))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._history_write_count = HISTORY_WRITE_CYCLES - 1
        await coordinator._async_update_data()

        # Prediction should have been computed for next cycle
        assert "living_room_abc12345" in coordinator._pending_predictions

    @pytest.mark.asyncio
    async def test_history_write_window_open_prediction(self, hass, mock_config_entry):
        """History write with window open uses window-open prediction model."""
        from custom_components.roommind.const import HISTORY_WRITE_CYCLES

        room_with_window = {
            **SAMPLE_ROOM,
            "window_sensors": ["binary_sensor.window"],
        }
        store = _make_store_mock({"living_room_abc12345": room_with_window})
        store.get_settings.return_value = {
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(
            temp="18.0", outdoor_temp="5.0",
            window_sensors={"binary_sensor.window": "on"},
        ))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._history_write_count = HISTORY_WRITE_CYCLES - 1
        await coordinator._async_update_data()

        # Prediction should still be computed (using window-open model)
        assert "living_room_abc12345" in coordinator._pending_predictions
