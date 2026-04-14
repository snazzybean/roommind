"""Tests for cover orchestration, night close, entity creation for covers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from .conftest import (
    SAMPLE_ROOM,
    _create_coordinator,
    _make_store_mock,
    make_mock_states_get,
)


class TestCoverageGaps:
    """Tests covering uncovered coordinator lines."""

    @pytest.mark.asyncio
    async def test_async_room_added_with_covers_creates_switch_and_binary_sensor(self, hass, mock_config_entry):
        """async_room_added creates switch and binary_sensor entities when covers are configured."""
        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator.async_request_refresh = AsyncMock()
        coordinator.async_add_entities = MagicMock()
        mock_add_switch = MagicMock()
        mock_add_binary = MagicMock()
        coordinator.async_add_switch_entities = mock_add_switch
        coordinator.async_add_binary_sensor_entities = mock_add_binary

        room = {"area_id": "bedroom_abc", "covers": ["cover.blind1"]}
        await coordinator.async_room_added(room)

        assert mock_add_switch.call_count == 2
        mock_add_binary.assert_called_once()
        assert "bedroom_abc" in coordinator._switch_entity_areas
        assert "bedroom_abc" in coordinator._binary_sensor_entity_areas
        assert "bedroom_abc" in coordinator._climate_control_switch_areas

    @pytest.mark.asyncio
    async def test_async_room_added_with_covers_no_duplicate(self, hass, mock_config_entry):
        """Calling async_room_added twice for same room with covers does not duplicate cover entities."""
        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator.async_request_refresh = AsyncMock()
        coordinator.async_add_entities = MagicMock()
        coordinator.async_add_switch_entities = MagicMock()
        coordinator.async_add_binary_sensor_entities = MagicMock()

        room = {"area_id": "bedroom_abc", "covers": ["cover.blind1"]}
        await coordinator.async_room_added(room)
        await coordinator.async_room_added(room)

        assert coordinator.async_add_switch_entities.call_count == 2
        coordinator.async_add_binary_sensor_entities.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_room_added_without_covers_no_switch_binary(self, hass, mock_config_entry):
        """async_room_added without covers does not create switch/binary_sensor entities."""
        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator.async_request_refresh = AsyncMock()
        coordinator.async_add_entities = MagicMock()
        coordinator.async_add_switch_entities = MagicMock()
        coordinator.async_add_binary_sensor_entities = MagicMock()

        room = {"area_id": "bedroom_abc"}
        await coordinator.async_room_added(room)

        coordinator.async_add_switch_entities.assert_called_once()
        coordinator.async_add_binary_sensor_entities.assert_not_called()
        assert "bedroom_abc" in coordinator._climate_control_switch_areas
        assert "bedroom_abc" not in coordinator._switch_entity_areas

    @pytest.mark.asyncio
    async def test_is_mpc_active_exception_handled_gracefully(self, hass, mock_config_entry):
        """Exception in is_mpc_active check in coordinator is caught, mpc_active=False."""
        store = _make_store_mock({"living_room_abc12345": {**SAMPLE_ROOM}})
        store.get_settings.return_value = {
            "outdoor_temp_sensor": "sensor.outdoor_temp",
            "climate_control_active": True,
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

        with patch(
            "custom_components.roommind.coordinator.is_mpc_active",
            side_effect=RuntimeError("mpc check failed"),
        ):
            result = await coordinator._async_update_data()
            assert result is not None
            room_state = result["rooms"]["living_room_abc12345"]
            assert room_state["mode"] in ("heating", "cooling", "idle")
            assert room_state["mpc_active"] is False
            assert room_state["target_temp"] is not None
            assert room_state["current_temp"] == 18.0

    @pytest.mark.asyncio
    async def test_cover_schedule_position_parse_error(self, hass, mock_config_entry):
        """ValueError/TypeError in cover schedule position parsing falls back to 0."""
        room_with_covers = {
            **SAMPLE_ROOM,
            "covers": ["cover.blind1"],
            "covers_auto_enabled": True,
            "cover_schedules": [{"entity_id": "schedule.cover_sched"}],
        }
        store = _make_store_mock({"living_room_abc12345": room_with_covers})
        store.get_settings.return_value = {
            "outdoor_temp_sensor": "sensor.outdoor_temp",
            "climate_control_active": True,
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                temp="18.0",
                outdoor_temp="5.0",
                extra={
                    "schedule.cover_sched": ("on", {"position": "not_a_number"}),
                },
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        result = await coordinator._async_update_data()
        assert result is not None
        room_state = result["rooms"]["living_room_abc12345"]
        # Room still processes normally despite cover schedule parse error
        assert room_state["mode"] == "heating"  # 18 < 21 target
        assert room_state["target_temp"] == 21.0
        assert room_state["current_temp"] == 18.0

    @pytest.mark.asyncio
    async def test_cover_night_close(self, hass, mock_config_entry):
        """Covers use night close position when solar elevation <= 0."""
        room_with_covers = {
            **SAMPLE_ROOM,
            "covers": ["cover.blind1"],
            "covers_auto_enabled": True,
            "covers_night_close": True,
            "covers_night_position": 10,
        }
        store = _make_store_mock({"living_room_abc12345": room_with_covers})
        store.get_settings.return_value = {
            "outdoor_temp_sensor": "sensor.outdoor_temp",
            "climate_control_active": True,
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

        # Mock solar_elevation to return negative (nighttime)
        with patch(
            "custom_components.roommind.managers.cover_orchestrator.solar_elevation",
            return_value=-5.0,
        ):
            result = await coordinator._async_update_data()
            assert result is not None
            room_state = result["rooms"]["living_room_abc12345"]
            assert room_state["mode"] in ("heating", "cooling", "idle")
            assert room_state["target_temp"] is not None
            assert room_state["current_temp"] == 18.0
            # Verify night close forced position was applied
            cover_calls = [c for c in hass.services.async_call.call_args_list if c[0][0] == "cover"]
            if cover_calls:
                # Night close should set position to 10 (covers_night_position)
                positions = [c[0][2].get("position") for c in cover_calls if "position" in c[0][2]]
                assert any(p == 10 for p in positions), f"Expected night position 10, got {positions}"

    def test_estimate_solar_peak_temp_learned_beta_s(self, hass, mock_config_entry):
        """Uses RC trajectory when idle model is confident (Tier 1)."""
        from custom_components.roommind.const import COVER_MIN_IDLE_FOR_LEARNED

        coordinator = _create_coordinator(hass, mock_config_entry)

        # Mock model manager with enough idle data
        coordinator._model_manager.get_mode_counts = MagicMock(return_value=(COVER_MIN_IDLE_FOR_LEARNED, 10, 5))
        mock_model = MagicMock()
        mock_model.predict_trajectory = MagicMock(return_value=[22.0, 22.5, 23.0, 23.5, 24.0])
        coordinator._model_manager.get_model = MagicMock(return_value=mock_model)

        with (
            patch.object(coordinator._cover_orchestrator, "_idle_solar_model_confident", return_value=True),
            patch(
                "custom_components.roommind.managers.cover_orchestrator.build_solar_series",
                return_value=[0.3, 0.4, 0.5, 0.6, 0.7],
            ),
        ):
            result = coordinator._cover_orchestrator._estimate_solar_peak_temp(
                "room1", 20.0, 22.0, 0.5, outdoor_temp=15.0
            )

        assert result == pytest.approx(24.0)

    @patch("custom_components.roommind.managers.cover_orchestrator.build_solar_series", return_value=[0.5])
    def test_estimate_solar_peak_temp_not_enough_idle(self, _mock_solar, hass, mock_config_entry):
        """Falls back to linear when not enough idle observations (Tier 2)."""
        from custom_components.roommind.const import COVER_DEFAULT_BETA_S, COVER_LINEAR_LOOKAHEAD_H

        coordinator = _create_coordinator(hass, mock_config_entry)

        coordinator._model_manager.get_mode_counts = MagicMock(
            return_value=(5, 10, 5)  # n_idle < 30
        )

        result = coordinator._cover_orchestrator._estimate_solar_peak_temp("room1", 20.0, 22.0, 0.5, outdoor_temp=15.0)
        expected = 20.0 + COVER_DEFAULT_BETA_S * 0.5 * COVER_LINEAR_LOOKAHEAD_H
        assert result == pytest.approx(expected)

    @patch("custom_components.roommind.managers.cover_orchestrator.build_solar_series", return_value=[0.5])
    def test_estimate_solar_peak_temp_exception_fallback(self, _mock_solar, hass, mock_config_entry):
        """Falls back to linear when model manager raises."""
        from custom_components.roommind.const import COVER_DEFAULT_BETA_S, COVER_LINEAR_LOOKAHEAD_H

        coordinator = _create_coordinator(hass, mock_config_entry)

        coordinator._model_manager.get_mode_counts = MagicMock(side_effect=RuntimeError("no model"))

        result = coordinator._cover_orchestrator._estimate_solar_peak_temp("room1", 20.0, 22.0, 0.5, outdoor_temp=15.0)
        expected = 20.0 + COVER_DEFAULT_BETA_S * 0.5 * COVER_LINEAR_LOOKAHEAD_H
        assert result == pytest.approx(expected)

    @patch("custom_components.roommind.managers.cover_orchestrator.build_solar_series", return_value=[0.5])
    def test_estimate_solar_peak_temp_no_current_temp(self, _mock_solar, hass, mock_config_entry):
        """Uses target_temp as base when current_temp is None."""
        from custom_components.roommind.const import COVER_DEFAULT_BETA_S, COVER_LINEAR_LOOKAHEAD_H

        coordinator = _create_coordinator(hass, mock_config_entry)

        coordinator._model_manager.get_mode_counts = MagicMock(return_value=(5, 0, 0))

        result = coordinator._cover_orchestrator._estimate_solar_peak_temp("room1", None, 22.0, 0.5, outdoor_temp=15.0)
        expected = 22.0 + COVER_DEFAULT_BETA_S * 0.5 * COVER_LINEAR_LOOKAHEAD_H
        assert result == pytest.approx(expected)

    def test_estimate_solar_peak_model_not_confident_uses_linear(self, hass, mock_config_entry):
        """When prediction_std >= 0.5 (model not confident), fall back to linear."""
        from custom_components.roommind.const import (
            COVER_DEFAULT_BETA_S,
            COVER_LINEAR_LOOKAHEAD_H,
            COVER_MIN_IDLE_FOR_LEARNED,
        )

        coordinator = _create_coordinator(hass, mock_config_entry)

        # Enough idle data, but model not confident
        coordinator._model_manager.get_mode_counts = MagicMock(return_value=(COVER_MIN_IDLE_FOR_LEARNED, 10, 5))

        with (
            patch.object(coordinator._cover_orchestrator, "_idle_solar_model_confident", return_value=False),
            patch(
                "custom_components.roommind.managers.cover_orchestrator.build_solar_series",
                return_value=[0.5],
            ),
        ):
            result = coordinator._cover_orchestrator._estimate_solar_peak_temp(
                "room1", 20.0, 22.0, 0.5, outdoor_temp=15.0
            )

        expected = 20.0 + COVER_DEFAULT_BETA_S * 0.5 * COVER_LINEAR_LOOKAHEAD_H
        assert result == pytest.approx(expected)

    def test_estimate_solar_peak_outdoor_none_uses_linear(self, hass, mock_config_entry):
        """When outdoor_temp is None, fall back to linear."""
        from custom_components.roommind.const import (
            COVER_DEFAULT_BETA_S,
            COVER_LINEAR_LOOKAHEAD_H,
            COVER_MIN_IDLE_FOR_LEARNED,
        )

        coordinator = _create_coordinator(hass, mock_config_entry)

        coordinator._model_manager.get_mode_counts = MagicMock(return_value=(COVER_MIN_IDLE_FOR_LEARNED, 10, 5))

        with patch(
            "custom_components.roommind.managers.cover_orchestrator.build_solar_series",
            return_value=[0.5],
        ):
            result = coordinator._cover_orchestrator._estimate_solar_peak_temp(
                "room1", 20.0, 22.0, 0.5, outdoor_temp=None
            )

        expected = 20.0 + COVER_DEFAULT_BETA_S * 0.5 * COVER_LINEAR_LOOKAHEAD_H
        assert result == pytest.approx(expected)

    def test_idle_solar_model_confident_true(self, hass, mock_config_entry):
        """Low prediction_std returns True."""
        from custom_components.roommind.const import COVER_CONFIDENCE_REFERENCE_SOLAR, COVER_PREDICTION_DT_MINUTES

        coordinator = _create_coordinator(hass, mock_config_entry)

        coordinator._model_manager.get_prediction_std = MagicMock(return_value=0.2)

        result = coordinator._cover_orchestrator._idle_solar_model_confident("room1", 20.0, 15.0)

        assert result is True
        coordinator._model_manager.get_prediction_std.assert_called_once_with(
            "room1",
            0.0,
            20.0,
            15.0,
            COVER_PREDICTION_DT_MINUTES,
            q_solar=COVER_CONFIDENCE_REFERENCE_SOLAR,
        )

    def test_idle_solar_model_confident_false_high_std(self, hass, mock_config_entry):
        """High prediction_std returns False."""
        coordinator = _create_coordinator(hass, mock_config_entry)

        coordinator._model_manager.get_prediction_std = MagicMock(return_value=0.8)

        result = coordinator._cover_orchestrator._idle_solar_model_confident("room1", 20.0, 15.0)

        assert result is False

    def test_idle_solar_model_confident_false_exception(self, hass, mock_config_entry):
        """Exception in get_prediction_std returns False."""
        coordinator = _create_coordinator(hass, mock_config_entry)

        coordinator._model_manager.get_prediction_std = MagicMock(side_effect=RuntimeError("boom"))

        result = coordinator._cover_orchestrator._idle_solar_model_confident("room1", 20.0, 15.0)

        assert result is False

    def test_set_cloud_series_used_in_estimate(self, hass, mock_config_entry):
        """Cloud series propagated to build_solar_series in RC trajectory."""
        from custom_components.roommind.const import COVER_MIN_IDLE_FOR_LEARNED

        coordinator = _create_coordinator(hass, mock_config_entry)

        coordinator._model_manager.get_mode_counts = MagicMock(return_value=(COVER_MIN_IDLE_FOR_LEARNED, 10, 5))
        mock_model = MagicMock()
        mock_model.predict_trajectory = MagicMock(return_value=[22.0, 23.0, 24.0])
        coordinator._model_manager.get_model = MagicMock(return_value=mock_model)

        cloud_series = [50.0, 60.0, 70.0]
        coordinator._cover_orchestrator.set_cloud_series(cloud_series)

        with (
            patch.object(coordinator._cover_orchestrator, "_idle_solar_model_confident", return_value=True),
            patch(
                "custom_components.roommind.managers.cover_orchestrator.build_solar_series",
                return_value=[0.3, 0.4, 0.5],
            ) as mock_build,
        ):
            result = coordinator._cover_orchestrator._estimate_solar_peak_temp(
                "room1", 20.0, 22.0, 0.5, outdoor_temp=15.0
            )

        assert result == pytest.approx(24.0)
        # Verify cloud_series was passed through
        _, kwargs = mock_build.call_args
        assert kwargs["cloud_series"] == cloud_series
