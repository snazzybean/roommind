"""Tests for the diagnostics module."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.roommind.diagnostics import (
    _build_model_info,
    async_get_config_entry_diagnostics,
)
from custom_components.roommind.const import DOMAIN


def _make_estimator():
    """Build a mock ThermalEKF estimator."""
    est = MagicMock()
    est._x = [20.0, 0.5, 100.0, 80.0, 10.0]
    est._n_updates = 200
    est._n_idle = 120
    est._n_heating = 60
    est._n_cooling = 20
    est._applicable_modes = {"idle", "heating"}
    est._P = [[0.01 * (i == j) for j in range(5)] for i in range(5)]
    est.prediction_std.return_value = 0.25
    est.confidence = 0.85
    rc = MagicMock()
    rc.Q_heat = 100.0
    rc.to_dict.return_value = {"alpha": 0.5, "beta_h": 100.0}
    est.get_model.return_value = rc
    return est


def test_build_model_info():
    """_build_model_info extracts correct fields from estimator."""
    est = _make_estimator()
    info = _build_model_info(est)

    assert info["alpha"] == 0.5
    assert info["beta_h"] == 100.0
    assert info["beta_c"] == 80.0
    assert info["n_updates"] == 200
    assert info["n_idle"] == 120
    assert info["n_heating"] == 60
    assert info["n_cooling"] == 20
    assert info["applicable_modes"] == ["heating", "idle"]  # sorted
    assert len(info["P_diagonal"]) == 5
    assert info["confidence"] == 0.85
    assert "model_params" in info


@pytest.mark.asyncio
async def test_diagnostics_no_store(hass, mock_config_entry):
    """Returns error when store is not loaded."""
    hass.data = {}
    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert result == {"error": "Integration not loaded"}


@pytest.mark.asyncio
async def test_diagnostics_no_store_in_domain(hass, mock_config_entry):
    """Returns error when domain data exists but no store."""
    hass.data[DOMAIN] = {}
    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert result == {"error": "Integration not loaded"}


@pytest.mark.asyncio
async def test_diagnostics_no_coordinator(hass, mock_config_entry):
    """Works without coordinator (live states empty)."""
    store = MagicMock()
    store.get_settings.return_value = {"presence_enabled": False}
    store.get_rooms.return_value = {"room_a": {"thermostats": ["climate.trv1"]}}
    hass.data[DOMAIN] = {"store": store}

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert result["rooms"]["room_a"]["live"]["mode"] == "idle"
    assert result["rooms"]["room_a"]["live"]["current_temp"] is None
    assert "model" not in result["rooms"]["room_a"]
    assert result["outdoor"]["temp"] is None
    assert result["recent_history"] == {}


@pytest.mark.asyncio
async def test_diagnostics_with_coordinator_and_model(hass, mock_config_entry):
    """Full path with coordinator, rooms, and EKF model."""
    store = MagicMock()
    store.get_settings.return_value = {"presence_enabled": True, "presence_persons": ["person.alice"]}
    store.get_rooms.return_value = {"room_a": {"thermostats": ["climate.trv1"]}}

    coordinator = MagicMock()
    coordinator.rooms = {
        "room_a": {
            "current_temp": 21.5,
            "current_humidity": 55,
            "target_temp": 21.0,
            "mode": "heating",
            "window_open": False,
            "mpc_active": True,
            "confidence": 0.9,
            "presence_away": False,
        }
    }
    coordinator.outdoor_temp = 5.0
    coordinator.outdoor_humidity = 60
    coordinator._weather_manager._outdoor_forecast = [{"temperature": 6.0}, {"temperature": 7.0}]
    coordinator._history_store = None

    est = _make_estimator()
    coordinator._model_manager._estimators = {"room_a": est}

    alice_state = MagicMock()
    alice_state.state = "home"
    hass.states.get = MagicMock(return_value=alice_state)

    hass.data[DOMAIN] = {"store": store, "coordinator": coordinator}

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert result["rooms"]["room_a"]["live"]["current_temp"] == 21.5
    assert result["rooms"]["room_a"]["live"]["mpc_active"] is True
    assert "model" in result["rooms"]["room_a"]
    assert result["outdoor"]["temp"] == 5.0
    assert result["outdoor"]["forecast_available"] is True
    assert result["outdoor"]["forecast_points"] == 2
    assert result["presence"]["enabled"] is True
    assert result["presence"]["person_states"]["person.alice"] == "home"


@pytest.mark.asyncio
async def test_diagnostics_room_without_estimator(hass, mock_config_entry):
    """Room without EKF estimator has no model key."""
    store = MagicMock()
    store.get_settings.return_value = {}
    store.get_rooms.return_value = {"room_a": {}}

    coordinator = MagicMock()
    coordinator.rooms = {}
    coordinator.outdoor_temp = None
    coordinator.outdoor_humidity = None
    coordinator._weather_manager._outdoor_forecast = []
    coordinator._history_store = None
    coordinator._model_manager._estimators = {}

    hass.data[DOMAIN] = {"store": store, "coordinator": coordinator}

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert "model" not in result["rooms"]["room_a"]


@pytest.mark.asyncio
async def test_diagnostics_history_store_with_rows(hass, mock_config_entry):
    """History data is included when history store is available."""
    store = MagicMock()
    store.get_settings.return_value = {}
    store.get_rooms.return_value = {"room_a": {}}

    history_store = MagicMock()
    history_store.read_detail.return_value = [
        {"timestamp": "1000", "room_temp": "21.0", "outdoor_temp": "5.0",
         "target_temp": "21.0", "mode": "idle", "predicted_temp": "21.1"},
    ]

    coordinator = MagicMock()
    coordinator.rooms = {}
    coordinator.outdoor_temp = 5.0
    coordinator.outdoor_humidity = 60
    coordinator._weather_manager._outdoor_forecast = []
    coordinator._history_store = history_store
    coordinator._model_manager._estimators = {}

    hass.data[DOMAIN] = {"store": store, "coordinator": coordinator}

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert len(result["recent_history"]["room_a"]) == 1
    assert result["recent_history"]["room_a"][0]["ts"] == "1000"


@pytest.mark.asyncio
async def test_diagnostics_history_store_exception(hass, mock_config_entry):
    """History read exception returns empty list for that room."""
    store = MagicMock()
    store.get_settings.return_value = {}
    store.get_rooms.return_value = {"room_a": {}}

    history_store = MagicMock()
    history_store.read_detail.side_effect = RuntimeError("disk error")

    coordinator = MagicMock()
    coordinator.rooms = {}
    coordinator.outdoor_temp = 5.0
    coordinator.outdoor_humidity = 60
    coordinator._weather_manager._outdoor_forecast = []
    coordinator._history_store = history_store
    coordinator._model_manager._estimators = {}

    hass.data[DOMAIN] = {"store": store, "coordinator": coordinator}

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert result["recent_history"]["room_a"] == []


@pytest.mark.asyncio
async def test_diagnostics_presence_person_unavailable(hass, mock_config_entry):
    """Person entity not found shows 'unavailable'."""
    store = MagicMock()
    store.get_settings.return_value = {
        "presence_enabled": True,
        "presence_persons": ["person.ghost"],
    }
    store.get_rooms.return_value = {}

    hass.states.get = MagicMock(return_value=None)
    hass.data[DOMAIN] = {"store": store}

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert result["presence"]["person_states"]["person.ghost"] == "unavailable"


@pytest.mark.asyncio
async def test_diagnostics_history_capped_at_240(hass, mock_config_entry):
    """History rows are capped at 240 per room."""
    store = MagicMock()
    store.get_settings.return_value = {}
    store.get_rooms.return_value = {"room_a": {}}

    rows = [
        {"timestamp": str(i), "room_temp": "21.0", "outdoor_temp": "5.0",
         "target_temp": "21.0", "mode": "idle", "predicted_temp": "21.0"}
        for i in range(300)
    ]
    history_store = MagicMock()
    history_store.read_detail.return_value = rows

    coordinator = MagicMock()
    coordinator.rooms = {}
    coordinator.outdoor_temp = 5.0
    coordinator.outdoor_humidity = 60
    coordinator._weather_manager._outdoor_forecast = []
    coordinator._history_store = history_store
    coordinator._model_manager._estimators = {}

    hass.data[DOMAIN] = {"store": store, "coordinator": coordinator}

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert len(result["recent_history"]["room_a"]) == 240
