"""Tests for EKF training, device observation, MPC path in coordinator, residual heat tracking."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.control.mpc_controller import MPCController

from .conftest import (
    SAMPLE_ROOM,
    _create_coordinator,
    _make_store_mock,
    make_mock_states_get,
)


class TestCoordinatorMPCIntegration:
    """Integration tests for the coordinator -> MPCController -> optimizer chain."""

    @pytest.mark.asyncio
    async def test_trained_model_processes_through_mpc_path(self, hass, mock_config_entry):
        """A room with a trained thermal model goes through the full MPC path."""
        room = {
            **SAMPLE_ROOM,
            "area_id": "mpc_room",
        }
        store = _make_store_mock({"mpc_room": room})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="17.0", humidity="50.0"))
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
    async def test_untrained_model_uses_bangbang_fallback(self, hass, mock_config_entry):
        """A room with an untrained model falls back to bang-bang control."""
        room = {
            **SAMPLE_ROOM,
            "area_id": "bangbang_room",
        }
        store = _make_store_mock({"bangbang_room": room})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="16.0", humidity="50.0"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        # No pre-training -- default model has high uncertainty -> bang-bang
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["bangbang_room"]
        # 16degC is well below 21degC comfort -> heating (via bang-bang)
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
            side_effect=make_mock_states_get(temp="17.0", humidity="50.0", extra={"weather.home": ("cloudy", None)})
        )

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
        weather_calls = [c for c in hass.services.async_call.call_args_list if c.args[0] == "weather"]
        assert len(weather_calls) >= 1

    @pytest.mark.asyncio
    async def test_mpc_updates_thermal_model_after_processing(self, hass, mock_config_entry):
        """Coordinator updates the thermal model with observations after room processing."""
        room = {
            **SAMPLE_ROOM,
            "area_id": "learning_room",
        }
        store = _make_store_mock({"learning_room": room})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="18.5", humidity="50.0"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        # Set a previous temp so the model update has T_old available
        coordinator._ekf_training.last_temps["learning_room"] = 18.0

        data = await coordinator._async_update_data()

        room_state = data["rooms"]["learning_room"]
        assert room_state["current_temp"] == 18.5
        # Verify the model was updated (last_temps should now have the new value)
        assert coordinator._ekf_training.last_temps["learning_room"] == 18.5

    @pytest.mark.asyncio
    async def test_coordinator_mpc_idle_at_target(self, hass, mock_config_entry):
        """Full chain: MPC should produce idle when room is at target temperature."""
        room = {
            **SAMPLE_ROOM,
            "area_id": "idle_room",
        }
        store = _make_store_mock({"idle_room": room})
        store.get_settings = MagicMock(return_value={"outdoor_temp_sensor": "sensor.outdoor_temp"})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                temp="21.0",
                humidity="50.0",
                outdoor_temp="20.0",
            )
        )
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


class TestFlushEkfAccumulator:
    """Tests for EkfTrainingManager.flush."""

    def test_no_accumulated_data(self, hass, mock_config_entry):
        """Flush with no accumulated data is a no-op."""
        coordinator = _create_coordinator(hass, mock_config_entry)
        # Should not raise
        coordinator._ekf_training.flush("room_a", 20.0, 5.0, can_heat=True, can_cool=False, q_solar=0.0)

    def test_accumulated_without_mode(self, hass, mock_config_entry):
        """Flush with accumulated dt but no mode is a no-op."""
        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._ekf_training._accumulated_dt["room_a"] = 3.0
        # prev_mode not set -> should not call update
        coordinator._ekf_training.flush("room_a", 20.0, 5.0, can_heat=True, can_cool=False, q_solar=0.0)

    def test_accumulated_with_mode_calls_update(self, hass, mock_config_entry):
        """Flush with accumulated data and mode calls model update."""
        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._ekf_training._accumulated_dt["room_a"] = 3.0
        coordinator._ekf_training._accumulated_mode["room_a"] = "heating"
        coordinator._ekf_training._accumulated_pf["room_a"] = 0.8

        with patch.object(coordinator._model_manager, "update") as mock_update:
            coordinator._ekf_training.flush("room_a", 20.0, 5.0, can_heat=True, can_cool=False, q_solar=0.0)
            mock_update.assert_called_once()


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
            temp="18.0",
            schedule_state="on",
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
            temp="18.0",
            schedule_state="on",
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
            temp="18.0",
            schedule_state="on",
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
            temp="18.0",
            schedule_state="off",
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
            temp="18.0",
            schedule_state="on",
            schedule_attrs={"current_event": True, "friendly_name": "Heat"},
        )
        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()
        assert coordinator._previous_modes.get(aid) == "heating"

        # Backdate mode_on_since so the min-run window has already elapsed
        coordinator._mode_on_since[aid] = time.time() - 10000

        # Cycle 2: idle
        hass.states.get = make_mock_states_get(
            temp="18.0",
            schedule_state="off",
            schedule_attrs={"current_event": False, "friendly_name": "Heat"},
        )
        await coordinator._async_update_data()
        assert aid in coordinator._residual_tracker._off_since

        # Cycle 3: heating again
        hass.states.get = make_mock_states_get(
            temp="16.0",
            schedule_state="on",
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
        with (
            patch("homeassistant.helpers.entity_registry.async_get") as mock_get,
            patch.object(coordinator, "async_request_refresh", new_callable=AsyncMock),
        ):
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
        """Underfloor rooms respect the user-configured window open delay."""
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
            temp="20.0",
            schedule_state="on",
            schedule_attrs={"current_event": True, "friendly_name": "Living Room Heating"},
            window_sensors={"binary_sensor.window": "on"},
        )
        hass.services.async_call = AsyncMock()
        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        # With delay=0 and window open, underfloor room pauses immediately
        assert coordinator._window_manager._paused.get(room["area_id"], False)


class TestResidualHeatLearning:
    """The coordinator feeds the residual heat learner and the controller (radiator overshoot)."""

    @staticmethod
    def _radiator_coordinator(hass, mock_config_entry):
        room = {
            **SAMPLE_ROOM,
            "heating_system_type": "radiator",
            "devices": [
                {
                    "entity_id": "climate.living_room",
                    "type": "trv",
                    "role": "auto",
                    "heating_system_type": "radiator",
                }
            ],
        }
        store = _make_store_mock(rooms={room["area_id"]: room}, settings={"climate_control_active": True})
        hass.data = {"roommind": {"store": store}}
        hass.services.async_call = AsyncMock()
        hass.states.get = make_mock_states_get(
            temp="18.0",
            schedule_state="on",
            schedule_attrs={"current_event": True, "friendly_name": "Heat"},
        )
        return _create_coordinator(hass, mock_config_entry), room["area_id"]

    @pytest.mark.asyncio
    async def test_sample_is_folded_into_the_learned_scale(self, hass, mock_config_entry):
        coordinator, aid = self._radiator_coordinator(hass, mock_config_entry)
        with patch.object(coordinator._residual_learner, "step", return_value=2.5) as step:
            await coordinator._async_update_data()
        kwargs = step.call_args.kwargs
        assert kwargs["system_type"] == "radiator"
        assert kwargs["disturbed"] is False
        assert coordinator._model_manager.get_residual_scale(aid) == pytest.approx(2.5)

    @pytest.mark.asyncio
    async def test_heating_room_reports_the_heat_a_stop_would_leave(self, hass, mock_config_entry):
        coordinator, aid = self._radiator_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()
        assert coordinator._previous_modes.get(aid) == "heating"
        # A long run: the radiators are fully charged
        coordinator._residual_tracker._on_since[aid] = time.time() - 3600
        with patch("custom_components.roommind.coordinator.MPCController", wraps=MPCController) as ctrl:
            result = await coordinator._async_update_data()
        heat_run = ctrl.call_args.kwargs["heat_run"]
        assert heat_run is not None and heat_run[0] == pytest.approx(60.0, abs=0.5)
        assert result["rooms"][aid]["mode"] == "heating"
        assert result["rooms"][aid]["q_residual"] > 0.0

    @pytest.mark.asyncio
    async def test_underfloor_room_neither_learns_nor_stops_early(self, hass, mock_config_entry):
        coordinator, aid = self._radiator_coordinator(hass, mock_config_entry)
        room = coordinator.hass.data["roommind"]["store"].get_rooms.return_value[aid]
        room["heating_system_type"] = "underfloor"
        room["devices"][0]["heating_system_type"] = "underfloor"
        coordinator._model_manager.update_residual_scale(aid, 3.0)
        await coordinator._async_update_data()
        coordinator._residual_tracker._on_since[aid] = time.time() - 3600
        with (
            patch.object(coordinator._residual_learner, "step", return_value=None) as step,
            patch("custom_components.roommind.coordinator.MPCController", wraps=MPCController) as ctrl,
        ):
            result = await coordinator._async_update_data()
        assert step.call_args.kwargs["system_type"] == ""
        assert ctrl.call_args.kwargs["heat_run"] is None
        assert ctrl.call_args.kwargs["residual_scale"] == 1.0
        assert result["rooms"][aid]["q_residual"] == 0.0

    @pytest.mark.asyncio
    async def test_thermal_reset_drops_the_observation(self, hass, mock_config_entry):
        coordinator, aid = self._radiator_coordinator(hass, mock_config_entry)
        coordinator._residual_learner._obs[aid] = MagicMock()
        coordinator.reset_thermal_room(aid)
        assert aid not in coordinator._residual_learner._obs
        coordinator._residual_learner._obs[aid] = MagicMock()
        coordinator.reset_thermal_all()
        assert coordinator._residual_learner._obs == {}
