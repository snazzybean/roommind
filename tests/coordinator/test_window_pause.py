"""Tests for window sensor delays, window open/close state transitions."""

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
    async def test_window_open_overrides_to_idle(self, hass, mock_config_entry):
        """Test that an open window sensor forces mode to idle and turns off devices."""
        room_with_window = {
            **SAMPLE_ROOM,
            "window_sensors": ["binary_sensor.living_room_window"],
        }
        store = _make_store_mock({"living_room_abc12345": room_with_window})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                window_sensors={"binary_sensor.living_room_window": "on"},
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["mode"] == "idle"
        assert room_state["window_open"] is True

        # MODE_IDLE turns off all devices via set_hvac_mode "off"
        calls = hass.services.async_call.call_args_list
        hvac_off_calls = [
            c
            for c in calls
            if c
            == call(
                "climate",
                "set_hvac_mode",
                {"entity_id": "climate.living_room", "hvac_mode": "off"},
                blocking=True,
                context=ANY,
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

        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                window_sensors={"binary_sensor.living_room_window": "off"},
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["mode"] == "heating"
        assert room_state["window_open"] is False

    @pytest.mark.asyncio
    async def test_window_sensor_unavailable_treated_as_closed(self, hass, mock_config_entry):
        """Test that an unavailable window sensor is treated as closed."""
        room_with_window = {
            **SAMPLE_ROOM,
            "window_sensors": ["binary_sensor.living_room_window"],
        }
        store = _make_store_mock({"living_room_abc12345": room_with_window})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                window_sensors={"binary_sensor.living_room_window": "unavailable"},
            )
        )
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

        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                window_sensors={
                    "binary_sensor.window1": "off",
                    "binary_sensor.window2": "on",
                },
            )
        )
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

        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                window_sensors={"binary_sensor.living_room_window": "on"},
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        # Mark room as already known (simulates prior cycle with window closed)
        coordinator._window_manager._seen.add("living_room_abc12345")
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

        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                window_sensors={"binary_sensor.living_room_window": "on"},
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        # Pre-set: window has been open for 130s (exceeds 120s delay)
        coordinator._window_manager._seen.add("living_room_abc12345")
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

        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                window_sensors={"binary_sensor.living_room_window": "off"},
            )
        )
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

        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                window_sensors={"binary_sensor.living_room_window": "off"},
            )
        )
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
    async def test_window_open_delay_tracks_temperature(self, hass, mock_config_entry):
        """During open_delay, EKF parameters must not be trained but temperature
        state (_x[0]) must be tracked via update_window_open().

        Without temperature tracking, when the window closes before open_delay
        elapses, the stale _x[0] causes a massive innovation on the first normal
        EKF update, corrupting alpha/tau.
        """
        room_with_delay = {
            **SAMPLE_ROOM,
            "window_sensors": ["binary_sensor.living_room_window"],
            "window_open_delay": 120,
        }
        store = _make_store_mock({"living_room_abc12345": room_with_delay})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                window_sensors={"binary_sensor.living_room_window": "on"},
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        # Mark room as already known (simulates prior cycle with window closed)
        coordinator._window_manager._seen.add("living_room_abc12345")

        with patch.object(
            coordinator._model_manager,
            "update_window_open",
            wraps=coordinator._model_manager.update_window_open,
        ) as mock_win_update:
            data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        # Still heating (delay not reached)
        assert room_state["mode"] == "heating"
        assert room_state["window_open"] is False

        # EKF accumulator must be cleared (not carried over into next cycle)
        assert "living_room_abc12345" not in coordinator._ekf_training._accumulated_dt
        assert "living_room_abc12345" not in coordinator._ekf_training._accumulated_mode
        assert "living_room_abc12345" not in coordinator._ekf_training._accumulated_pf

        # update_window_open must be called to track temperature state,
        # but k_window must NOT learn during delay (heating still active)
        mock_win_update.assert_called_once()
        _, kwargs = mock_win_update.call_args
        assert kwargs.get("learn_k_window") is False

    @pytest.mark.asyncio
    async def test_window_open_skips_k_window_with_residual_heat(self, hass, mock_config_entry):
        """k_window must not be learned when residual heat is still present.

        With underfloor heating the floor continues releasing heat after the
        system stops.  Learning k_window in this state would underestimate
        the window cooling rate because the residual heat masks it.
        """
        room_with_window = {
            **SAMPLE_ROOM,
            "window_sensors": ["binary_sensor.living_room_window"],
            "heating_system_type": "underfloor",
        }
        store = _make_store_mock({"living_room_abc12345": room_with_window})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                window_sensors={"binary_sensor.living_room_window": "on"},
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        # Simulate residual heat: heating was active, then stopped recently.
        # _on_since before _off_since gives a non-zero heat duration, and
        # a recent _off_since means the exponential decay hasn't elapsed.
        coordinator._residual_tracker._on_since["living_room_abc12345"] = time.time() - 120
        coordinator._residual_tracker._off_since["living_room_abc12345"] = time.time() - 5
        coordinator._residual_tracker._off_power["living_room_abc12345"] = 1.0
        # Also set previous_mode so get_q_residual returns > 0
        coordinator._previous_modes["living_room_abc12345"] = MODE_IDLE

        with patch.object(
            coordinator._model_manager,
            "update_window_open",
            wraps=coordinator._model_manager.update_window_open,
        ) as mock_win_update:
            await coordinator._async_update_data()

        # update_window_open must be called (temperature tracking) but
        # k_window must NOT be learned because q_residual > 0
        mock_win_update.assert_called_once()
        _, kwargs = mock_win_update.call_args
        assert kwargs.get("learn_k_window") is False

    @pytest.mark.asyncio
    async def test_window_open_learns_k_window_without_residual_heat(self, hass, mock_config_entry):
        """k_window IS learned when window is open and no residual heat remains."""
        room_with_window = {
            **SAMPLE_ROOM,
            "window_sensors": ["binary_sensor.living_room_window"],
        }
        store = _make_store_mock({"living_room_abc12345": room_with_window})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                window_sensors={"binary_sensor.living_room_window": "on"},
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)

        with patch.object(
            coordinator._model_manager,
            "update_window_open",
            wraps=coordinator._model_manager.update_window_open,
        ) as mock_win_update:
            await coordinator._async_update_data()

        # k_window should be learned (no residual heat, no delay)
        mock_win_update.assert_called_once()
        _, kwargs = mock_win_update.call_args
        assert kwargs.get("learn_k_window") is True

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

        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                window_sensors={"binary_sensor.living_room_window": "on"},
            )
        )
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

        # First call: window is open -- delay timer starts but not reached
        mock_states = {}
        base_mock = make_mock_states_get()

        def mock_states_get(entity_id):
            if entity_id in mock_states:
                return mock_states[entity_id]
            return base_mock(entity_id)

        hass.states.get = MagicMock(side_effect=mock_states_get)
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        # Mark room as already known (simulates prior cycle with window closed)
        coordinator._window_manager._seen.add("living_room_abc12345")

        # Window opens
        window_state = MagicMock()
        window_state.state = "on"
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
        assert area_id not in coordinator._window_manager._seen
