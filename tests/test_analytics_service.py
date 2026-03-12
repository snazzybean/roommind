"""Tests for analytics_service.py."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.services.analytics_service import (
    _compute_target_forecast,
    build_analytics_data,
)

# ---------------------------------------------------------------------------
# _compute_target_forecast -- mold delta with heat_target=None
# ---------------------------------------------------------------------------


class TestComputeTargetForecast:
    """Tests for _compute_target_forecast edge cases."""

    @pytest.mark.asyncio
    async def test_mold_delta_applied_when_heat_target_none(self):
        """When heat_target is None and mold_prevention_delta > 0, eco_heat + delta used."""
        hass = MagicMock()
        hass.config.units.temperature_unit = "°C"
        room = {
            "comfort_heat": 21.0,
            "comfort_cool": 24.0,
            "eco_heat": 17.0,
            "eco_cool": 27.0,
            "climate_mode": "auto",
        }
        settings = {}

        from custom_components.roommind.const import TargetTemps

        with (
            patch(
                "custom_components.roommind.utils.presence_utils.is_presence_away",
                return_value=False,
            ),
            patch(
                "custom_components.roommind.utils.schedule_utils.get_active_schedule_entity",
                return_value=None,
            ),
            patch(
                "custom_components.roommind.utils.schedule_utils.resolve_targets_at_time",
                return_value=TargetTemps(heat=None, cool=24.0),
            ),
        ):
            result = await _compute_target_forecast(
                hass,
                room,
                settings,
                mold_prevention_delta=2.0,
                hours=0.0,
                interval_minutes=5,
            )
            assert len(result) == 1
            assert result[0]["heat_target"] == round(17.0 + 2.0, 1)

    @pytest.mark.asyncio
    async def test_cool_only_mode_returns_cool_target(self):
        """climate_mode=cool_only -> target = cool_target (line 127)."""
        hass = MagicMock()
        hass.config.units.temperature_unit = "°C"
        room = {
            "comfort_heat": 21.0,
            "comfort_cool": 24.0,
            "eco_heat": 17.0,
            "eco_cool": 27.0,
            "climate_mode": "cool_only",
        }
        settings = {}

        from custom_components.roommind.const import TargetTemps

        with (
            patch(
                "custom_components.roommind.utils.presence_utils.is_presence_away",
                return_value=False,
            ),
            patch(
                "custom_components.roommind.utils.schedule_utils.get_active_schedule_entity",
                return_value=None,
            ),
            patch(
                "custom_components.roommind.utils.schedule_utils.resolve_targets_at_time",
                return_value=TargetTemps(heat=21.0, cool=24.0),
            ),
        ):
            result = await _compute_target_forecast(
                hass,
                room,
                settings,
                hours=0.0,
                interval_minutes=5,
            )
            assert len(result) == 1
            assert result[0]["target_temp"] == 24.0

    @pytest.mark.asyncio
    async def test_heat_only_mode_returns_heat_target(self):
        """climate_mode=heat_only -> target = heat_target (line 129)."""
        hass = MagicMock()
        hass.config.units.temperature_unit = "°C"
        room = {
            "comfort_heat": 21.0,
            "comfort_cool": 24.0,
            "eco_heat": 17.0,
            "eco_cool": 27.0,
            "climate_mode": "heat_only",
        }
        settings = {}

        from custom_components.roommind.const import TargetTemps

        with (
            patch(
                "custom_components.roommind.utils.presence_utils.is_presence_away",
                return_value=False,
            ),
            patch(
                "custom_components.roommind.utils.schedule_utils.get_active_schedule_entity",
                return_value=None,
            ),
            patch(
                "custom_components.roommind.utils.schedule_utils.resolve_targets_at_time",
                return_value=TargetTemps(heat=21.0, cool=24.0),
            ),
        ):
            result = await _compute_target_forecast(
                hass,
                room,
                settings,
                hours=0.0,
                interval_minutes=5,
            )
            assert len(result) == 1
            assert result[0]["target_temp"] == 21.0


# ---------------------------------------------------------------------------
# build_analytics_data -- edge cases
# ---------------------------------------------------------------------------


class TestBuildAnalyticsData:
    """Tests for build_analytics_data edge cases."""

    @pytest.mark.asyncio
    async def test_target_forecast_exception_returns_empty(self):
        """Exception in _compute_target_forecast -> empty forecast (lines 237-239)."""
        hass = MagicMock()
        hass.async_add_executor_job = AsyncMock(return_value=[])
        store = MagicMock()
        store.get_settings.return_value = {}
        store.get_room.return_value = {}
        coordinator = None

        with patch(
            "custom_components.roommind.services.analytics_service._compute_target_forecast",
            side_effect=RuntimeError("boom"),
        ):
            result = await build_analytics_data(hass, "living_room", "12h", store, coordinator)
        assert result["forecast"] == []

    @pytest.mark.asyncio
    async def test_current_temp_from_reversed_points(self):
        """Last room_temp is found by iterating reversed all_points (lines 254-256)."""
        hass = MagicMock()
        hass.config.latitude = 48.0
        hass.config.longitude = 11.0

        store = MagicMock()
        store.get_settings.return_value = {"prediction_enabled": True}
        store.get_room.return_value = {"temperature_sensor": "sensor.temp"}

        from custom_components.roommind.control.thermal_model import ThermalEKF

        est = ThermalEKF()
        model = est.get_model()
        mgr = MagicMock()
        mgr._estimators = {"living_room": est}
        mgr.get_model.return_value = model

        coordinator = MagicMock()
        coordinator._model_manager = mgr
        coordinator.outdoor_temp = 10.0
        coordinator.rooms = {"living_room": {}}
        coordinator._weather_manager._outdoor_forecast = []
        coordinator._residual_tracker._off_since = {}
        coordinator._window_manager._paused = {}

        detail_rows = [
            {
                "timestamp": "1000",
                "room_temp": "",
                "outdoor_temp": "10",
                "target_temp": "21",
                "mode": "idle",
                "predicted_temp": "",
                "window_open": "",
                "heating_power": "",
            },
            {
                "timestamp": "2000",
                "room_temp": "20.5",
                "outdoor_temp": "10",
                "target_temp": "21",
                "mode": "idle",
                "predicted_temp": "",
                "window_open": "",
                "heating_power": "",
            },
        ]

        async def mock_executor(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        hass.async_add_executor_job = mock_executor

        history_store = MagicMock()
        history_store.read_detail.return_value = detail_rows
        history_store.read_history.return_value = []
        coordinator._history_store = history_store

        now = time.time()
        with (
            patch(
                "custom_components.roommind.services.analytics_service._compute_target_forecast",
                new_callable=AsyncMock,
                return_value=[{"ts": now, "target_temp": 21.0, "heat_target": 21.0, "cool_target": 24.0}],
            ),
            patch(
                "custom_components.roommind.services.analytics_service.get_can_heat_cool",
                return_value=(True, False),
            ),
            patch(
                "custom_components.roommind.services.analytics_service.is_mpc_active",
                return_value=False,
            ),
            patch(
                "custom_components.roommind.services.analytics_service.check_acs_can_heat",
                return_value=False,
            ),
            patch(
                "custom_components.roommind.control.analytics_simulator.simulate_prediction",
                return_value=[21.0],
            ) as mock_sim,
        ):
            await build_analytics_data(hass, "living_room", "12h", store, coordinator)
            mock_sim.assert_called_once()
            assert mock_sim.call_args.kwargs["current_temp"] == 20.5

    @pytest.mark.asyncio
    async def test_no_room_temp_skips_prediction(self):
        """If no room_temp in any point, prediction is skipped (current_t stays None)."""
        hass = MagicMock()
        hass.config.latitude = 48.0
        hass.config.longitude = 11.0

        store = MagicMock()
        store.get_settings.return_value = {"prediction_enabled": True}
        store.get_room.return_value = {"temperature_sensor": "sensor.temp"}

        est = MagicMock()
        est.get_model.return_value = MagicMock()
        est.prediction_std.return_value = 0.3
        est.confidence = 0.8
        est._P = [[0.01]]
        est._n_updates = 100
        est._n_heating = 50
        est._n_cooling = 10
        est._applicable_modes = {"heating", "idle"}

        mgr = MagicMock()
        mgr._estimators = {"room1": est}
        mgr.get_model.return_value = MagicMock()

        coordinator = MagicMock()
        coordinator._model_manager = mgr
        coordinator.outdoor_temp = 10.0
        coordinator.rooms = {"room1": {}}
        coordinator._weather_manager._outdoor_forecast = []
        coordinator._residual_tracker._off_since = {}
        coordinator._window_manager._paused = {}

        detail_rows = [
            {
                "timestamp": "1000",
                "room_temp": "",
                "outdoor_temp": "10",
                "target_temp": "21",
                "mode": "idle",
                "predicted_temp": "",
                "window_open": "",
                "heating_power": "",
            },
        ]

        async def mock_executor(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        hass.async_add_executor_job = mock_executor

        history_store = MagicMock()
        history_store.read_detail.return_value = detail_rows
        history_store.read_history.return_value = []
        coordinator._history_store = history_store

        now = time.time()
        with (
            patch(
                "custom_components.roommind.services.analytics_service._compute_target_forecast",
                new_callable=AsyncMock,
                return_value=[{"ts": now, "target_temp": 21.0, "heat_target": 21.0, "cool_target": 24.0}],
            ),
            patch(
                "custom_components.roommind.services.analytics_service.get_can_heat_cool",
                return_value=(True, False),
            ),
            patch(
                "custom_components.roommind.services.analytics_service.is_mpc_active",
                return_value=False,
            ),
            patch(
                "custom_components.roommind.services.analytics_service.check_acs_can_heat",
                return_value=False,
            ),
        ):
            result = await build_analytics_data(hass, "room1", "12h", store, coordinator)
            # No room_temp found -> simulate_prediction should NOT be called
            # Forecast should still have entries but predicted_temp = None
            assert len(result["forecast"]) == 1
            assert result["forecast"][0]["predicted_temp"] is None

    @pytest.mark.asyncio
    async def test_residual_heat_state_passed_to_simulation(self):
        """Residual heat state from coordinator passed to simulate_prediction (lines 258-280)."""
        hass = MagicMock()
        hass.config.latitude = 48.0
        hass.config.longitude = 11.0

        store = MagicMock()
        store.get_settings.return_value = {"prediction_enabled": True}
        store.get_room.return_value = {
            "temperature_sensor": "sensor.temp",
            "heating_system_type": "underfloor",
        }

        from custom_components.roommind.control.thermal_model import ThermalEKF

        est = ThermalEKF()
        model = est.get_model()
        mgr = MagicMock()
        mgr._estimators = {"room1": est}
        mgr.get_model.return_value = model

        coordinator = MagicMock()
        coordinator._model_manager = mgr
        coordinator.outdoor_temp = 10.0
        coordinator.rooms = {"room1": {}}
        coordinator._weather_manager._outdoor_forecast = []
        coordinator._window_manager._paused = {}

        now = time.time()
        coordinator._residual_tracker._off_since = {"room1": now - 300}
        coordinator._residual_tracker._on_since = {"room1": now - 900}
        coordinator._residual_tracker._off_power = {"room1": 0.8}

        detail_rows = [
            {
                "timestamp": str(now - 60),
                "room_temp": "20.0",
                "outdoor_temp": "10",
                "target_temp": "21",
                "mode": "idle",
                "predicted_temp": "",
                "window_open": "",
                "heating_power": "",
            },
        ]

        async def mock_executor(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        hass.async_add_executor_job = mock_executor

        history_store = MagicMock()
        history_store.read_detail.return_value = detail_rows
        history_store.read_history.return_value = []
        coordinator._history_store = history_store

        with (
            patch(
                "custom_components.roommind.services.analytics_service._compute_target_forecast",
                new_callable=AsyncMock,
                return_value=[{"ts": now, "target_temp": 21.0, "heat_target": 21.0, "cool_target": 24.0}],
            ),
            patch(
                "custom_components.roommind.services.analytics_service.get_can_heat_cool",
                return_value=(True, False),
            ),
            patch(
                "custom_components.roommind.services.analytics_service.is_mpc_active",
                return_value=False,
            ),
            patch(
                "custom_components.roommind.services.analytics_service.check_acs_can_heat",
                return_value=False,
            ),
            patch(
                "custom_components.roommind.control.analytics_simulator.simulate_prediction",
                return_value=[21.0],
            ) as mock_sim,
        ):
            await build_analytics_data(hass, "room1", "12h", store, coordinator)
            mock_sim.assert_called_once()
            kwargs = mock_sim.call_args.kwargs
            assert kwargs["heating_system_type"] == "underfloor"
            assert kwargs["q_residual"] > 0.0
            assert kwargs["last_power_fraction"] == 0.8
            assert kwargs["heating_duration_minutes"] > 0.0


# ---------------------------------------------------------------------------
# _csv_to_points -- device_setpoint field
# ---------------------------------------------------------------------------


class TestCsvToPointsDeviceSetpoint:
    """Tests for device_setpoint handling in _csv_to_points."""

    def test_device_setpoint_converted_to_float(self):
        """device_setpoint string is converted to float."""
        from custom_components.roommind.services.analytics_service import _csv_to_points

        rows = [
            {
                "timestamp": "1000",
                "room_temp": "20.0",
                "outdoor_temp": "5.0",
                "target_temp": "21.0",
                "mode": "heating",
                "predicted_temp": "20.5",
                "window_open": "",
                "heating_power": "80",
                "solar_irradiance": "",
                "blind_position": "",
                "device_setpoint": "24.5",
            }
        ]
        points = _csv_to_points(rows)
        assert len(points) == 1
        assert points[0]["device_setpoint"] == 24.5

    def test_missing_device_setpoint_returns_none(self):
        """Row without device_setpoint key returns None (backward compat)."""
        from custom_components.roommind.services.analytics_service import _csv_to_points

        rows = [
            {
                "timestamp": "1000",
                "room_temp": "20.0",
                "outdoor_temp": "5.0",
                "target_temp": "21.0",
                "mode": "idle",
                "predicted_temp": "20.0",
                "window_open": "",
                "heating_power": "",
                "solar_irradiance": "",
                "blind_position": "",
            }
        ]
        points = _csv_to_points(rows)
        assert len(points) == 1
        assert points[0]["device_setpoint"] is None
