"""Tests for general coordinator behavior, initialization, entity lifecycle, error handling, refresh logic, outdoor rooms."""

from __future__ import annotations

import time
from unittest.mock import ANY, AsyncMock, MagicMock, call, patch

import pytest

from custom_components.roommind.const import MODE_IDLE

from .conftest import (
    SAMPLE_ROOM,
    _create_coordinator,
    _make_store_mock,
    make_mock_states_get,
)


class TestRoomMindCoordinator:
    """Tests for RoomMindCoordinator."""

    @pytest.mark.asyncio
    async def test_coordinator_initializes(self, hass, mock_config_entry):
        """Test that the coordinator initializes without errors."""
        from datetime import timedelta

        from custom_components.roommind.const import UPDATE_INTERVAL
        from custom_components.roommind.control.thermal_model import RoomModelManager

        coordinator = _create_coordinator(hass, mock_config_entry)
        assert coordinator is not None
        assert coordinator.rooms == {}
        assert isinstance(coordinator._model_manager, RoomModelManager)
        assert coordinator.update_interval == timedelta(seconds=UPDATE_INTERVAL)
        assert coordinator._history_store is None
        assert coordinator._thermal_save_count == 0
        assert coordinator._history_write_count == 0
        assert coordinator._pending_predictions == {}
        assert coordinator.outdoor_temp is None

    @pytest.mark.asyncio
    async def test_update_with_comfort_temp_and_heating(self, hass, mock_config_entry):
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
        climate_calls = [c for c in hass.services.async_call.call_args_list if c[0][0] == "climate"]
        assert climate_calls[0] == call(
            "climate",
            "set_hvac_mode",
            {"entity_id": "climate.living_room", "hvac_mode": "heat"},
            blocking=True,
            context=ANY,
        )
        assert climate_calls[1] == call(
            "climate",
            "set_temperature",
            {"entity_id": "climate.living_room", "temperature": 30},
            blocking=True,
            context=ANY,
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
    async def test_update_sensor_unavailable_goes_idle(self, hass, mock_config_entry):
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
    async def test_update_sensor_state_none_skips_room(self, hass, mock_config_entry):
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
    async def test_update_climate_service_failure_does_not_crash(self, hass, mock_config_entry):
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
            RoomMindModeSensor,
            RoomMindTargetTemperatureSensor,
        )

        assert isinstance(entities[0], RoomMindTargetTemperatureSensor)
        assert isinstance(entities[1], RoomMindModeSensor)

        # Verify unique IDs
        assert entities[0]._attr_unique_id == "roommind_bedroom_abc12345_target_temp"
        assert entities[1]._attr_unique_id == "roommind_bedroom_abc12345_mode"

        coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_room_added_no_callback_does_not_crash(self, hass, mock_config_entry):
        """Test that async_room_added works even without async_add_entities set."""
        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator.async_request_refresh = AsyncMock()

        # No async_add_entities set on coordinator
        await coordinator.async_room_added({"area_id": "room_123"})

        # Should still refresh without error
        coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_room_added_twice_does_not_duplicate_entities(self, hass, mock_config_entry):
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
        mock_registry.entities.values.return_value = [entity1, entity2, other_entity]

        with patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=mock_registry,
        ):
            await coordinator.async_room_removed(room_id)

        # Verify only the 2 entities for the removed room were unregistered
        assert mock_registry.async_remove.call_count == 2
        removed_ids = [call.args[0] for call in mock_registry.async_remove.call_args_list]
        assert f"sensor.{room_id}_target_temp" in removed_ids
        assert f"sensor.{room_id}_mode" in removed_ids
        assert "sensor.other_room_target_temp" not in removed_ids

        coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_outdoor_room_skips_control(self, hass, mock_config_entry):
        """Outdoor room returns idle state and makes no climate service calls."""
        outdoor_room = {**SAMPLE_ROOM, "is_outdoor": True}
        store = _make_store_mock({"living_room_abc12345": outdoor_room})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["mode"] == MODE_IDLE
        assert room_state["target_temp"] is None
        assert room_state["mold_risk_level"] == "ok"
        assert room_state["mpc_active"] is False

        # No climate service calls should have been made
        climate_calls = [c for c in hass.services.async_call.call_args_list if c[0][0] == "climate"]
        assert climate_calls == []

    @pytest.mark.asyncio
    async def test_outdoor_room_still_records_history(self, hass, mock_config_entry):
        """Outdoor room data is still written to the history store."""
        from custom_components.roommind.const import HISTORY_WRITE_CYCLES

        outdoor_room = {**SAMPLE_ROOM, "is_outdoor": True}
        store = _make_store_mock({"living_room_abc12345": outdoor_room})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._history_write_count = HISTORY_WRITE_CYCLES - 1

        await coordinator._async_update_data()

        # history_store.record is called via hass.async_add_executor_job
        record_calls = [
            c
            for c in hass.async_add_executor_job.call_args_list
            if len(c[0]) >= 2 and hasattr(c[0][0], "__name__") and c[0][0].__name__ == "record"
        ]
        # The default _history_store is None, so we need to set one up
        # Re-run with a mock history store
        hass.async_add_executor_job.reset_mock()
        mock_history = MagicMock()
        mock_history.record = MagicMock()
        coordinator._history_store = mock_history
        coordinator._history_write_count = HISTORY_WRITE_CYCLES - 1

        await coordinator._async_update_data()

        # async_add_executor_job should have been called with history_store.record
        record_calls = [
            c for c in hass.async_add_executor_job.call_args_list if len(c[0]) >= 1 and c[0][0] is mock_history.record
        ]
        assert len(record_calls) == 1
        assert record_calls[0][0][1] == "living_room_abc12345"


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

        # Set up a mock history store so rotate is actually called
        mock_history = MagicMock()
        mock_history.rotate = MagicMock()
        coordinator._history_store = mock_history

        coordinator._history_rotate_count = HISTORY_ROTATE_CYCLES - 1
        await coordinator._async_update_data()

        # Rotation counter should have been reset
        assert coordinator._history_rotate_count == 0
        # rotate should have been called via async_add_executor_job
        rotate_calls = [
            c for c in hass.async_add_executor_job.call_args_list if len(c[0]) >= 1 and c[0][0] is mock_history.rotate
        ]
        assert len(rotate_calls) >= 1

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
    async def test_prediction_exception_silently_caught(self, hass, mock_config_entry):
        """Exception during prediction is caught and prediction is skipped."""
        from custom_components.roommind.const import HISTORY_WRITE_CYCLES

        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                temp="18.0",
                outdoor_temp="5.0",
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._history_write_count = HISTORY_WRITE_CYCLES - 1

        # Make model.predict raise an exception
        coordinator._model_manager.predict_window_open = MagicMock(side_effect=RuntimeError("boom"))
        mock_model = MagicMock()
        mock_model.predict.side_effect = RuntimeError("boom")
        mock_model.Q_heat = 1.0
        mock_model.Q_cool = 1.0
        coordinator._model_manager.get_model = MagicMock(return_value=mock_model)

        # Should not raise -- exception is silently caught
        result = await coordinator._async_update_data()
        assert result is not None

    @pytest.mark.asyncio
    async def test_mpc_active_check(self, hass, mock_config_entry):
        """MPC active flag is computed when control_mode is 'mpc'."""

        room = {**SAMPLE_ROOM, "area_id": "mpc_room"}
        store = _make_store_mock({"mpc_room": room})
        store.get_settings.return_value = {
            "control_mode": "mpc",
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                temp="18.0",
                outdoor_temp="5.0",
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        # Pre-train model with low std for MPC activation
        mgr = coordinator._model_manager
        mgr.update("mpc_room", 18.0, 5.0, "heating", 5.0)
        mgr.update("mpc_room", 18.5, 5.0, "heating", 5.0)

        data = await coordinator._async_update_data()

        room_state = data["rooms"]["mpc_room"]
        # Only 2 EKF updates, well below MIN_SAMPLES → MPC cannot activate
        assert room_state["mpc_active"] is False

    @pytest.mark.asyncio
    async def test_history_write_computes_prediction(self, hass, mock_config_entry):
        """History write cycle computes predictions for next cycle."""
        from custom_components.roommind.const import HISTORY_WRITE_CYCLES

        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                temp="18.0",
                outdoor_temp="5.0",
            )
        )
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
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                temp="18.0",
                outdoor_temp="5.0",
                window_sensors={"binary_sensor.window": "on"},
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._history_write_count = HISTORY_WRITE_CYCLES - 1
        await coordinator._async_update_data()

        # Prediction should still be computed (using window-open model)
        assert "living_room_abc12345" in coordinator._pending_predictions
