"""Tests for the diagnostics module."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from custom_components.roommind.const import DOMAIN
from custom_components.roommind.diagnostics import (
    _build_device_states,
    _build_model_info,
    async_get_config_entry_diagnostics,
)


def _make_estimator():
    """Build a mock ThermalEKF estimator."""
    est = MagicMock()
    est._x = [20.0, 0.5, 100.0, 80.0, 10.0, 0.3]
    est._n_updates = 200
    est._n_idle = 120
    est._n_heating = 60
    est._n_cooling = 20
    est._applicable_modes = {"idle", "heating"}
    est._P = [[0.01 * (i == j) for j in range(6)] for i in range(6)]
    est.prediction_std.return_value = 0.25
    est.confidence = 0.85
    rc = MagicMock()
    rc.Q_heat = 100.0
    rc.to_dict.return_value = {"alpha": 0.5, "beta_h": 100.0}
    est.get_model.return_value = rc
    return est


def _make_coordinator(
    rooms=None,
    outdoor_temp=5.0,
    outdoor_humidity=60,
    forecast=None,
    history_store=None,
    estimators=None,
    window_paused=None,
    window_open_since=None,
    window_closed_since=None,
    cover_states=None,
    heat_source_states=None,
    compressor_groups=None,
    compressor_states=None,
    valve_cycling=None,
    valve_last_actuation=None,
):
    """Build a mock coordinator with all manager attributes."""
    coordinator = MagicMock()
    coordinator.rooms = rooms or {}
    coordinator.outdoor_temp = outdoor_temp
    coordinator.outdoor_humidity = outdoor_humidity
    coordinator._weather_manager._outdoor_forecast = forecast or []
    coordinator._history_store = history_store
    coordinator._model_manager._estimators = estimators or {}

    # Window manager
    coordinator._window_manager._paused = window_paused or {}
    coordinator._window_manager._open_since = window_open_since or {}
    coordinator._window_manager._closed_since = window_closed_since or {}

    # Cover manager
    coordinator._cover_manager._states = cover_states or {}

    # Heat source states
    coordinator._heat_source_states = heat_source_states or {}

    # Compressor manager
    coordinator._compressor_manager._groups = compressor_groups or {}
    coordinator._compressor_manager._states = compressor_states or {}

    # Valve manager
    coordinator._valve_manager._cycling = valve_cycling or {}
    coordinator._valve_manager._last_actuation = valve_last_actuation or {}

    return coordinator


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
    assert len(info["P_diagonal"]) == 6
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

    est = _make_estimator()
    coordinator = _make_coordinator(
        rooms={
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
        },
        estimators={"room_a": est},
    )

    alice_state = MagicMock()
    alice_state.state = "home"
    hass.states.get = MagicMock(return_value=alice_state)

    hass.data[DOMAIN] = {"store": store, "coordinator": coordinator}

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert result["rooms"]["room_a"]["live"]["current_temp"] == 21.5
    assert result["rooms"]["room_a"]["live"]["mpc_active"] is True
    assert "model" in result["rooms"]["room_a"]
    assert result["outdoor"]["temp"] == 5.0
    assert result["outdoor"]["forecast_available"] is False
    assert result["presence"]["enabled"] is True
    assert result["presence"]["person_states"]["person.alice"] == "home"


@pytest.mark.asyncio
async def test_diagnostics_room_without_estimator(hass, mock_config_entry):
    """Room without EKF estimator has no model key."""
    store = MagicMock()
    store.get_settings.return_value = {}
    store.get_rooms.return_value = {"room_a": {}}

    coordinator = _make_coordinator(rooms={})

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
        {
            "timestamp": "1000",
            "room_temp": "21.0",
            "outdoor_temp": "5.0",
            "target_temp": "21.0",
            "mode": "idle",
            "predicted_temp": "21.1",
        },
    ]

    coordinator = _make_coordinator(history_store=history_store)

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

    coordinator = _make_coordinator(history_store=history_store)

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
        {
            "timestamp": str(i),
            "room_temp": "21.0",
            "outdoor_temp": "5.0",
            "target_temp": "21.0",
            "mode": "idle",
            "predicted_temp": "21.0",
        }
        for i in range(300)
    ]
    history_store = MagicMock()
    history_store.read_detail.return_value = rows

    coordinator = _make_coordinator(history_store=history_store)

    hass.data[DOMAIN] = {"store": store, "coordinator": coordinator}

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert len(result["recent_history"]["room_a"]) == 240


# --- New tests for enhanced diagnostics ---


def test_build_device_states_with_ha_state(hass):
    """Device states include HA entity attributes."""
    state = MagicMock()
    state.state = "heat"
    state.attributes = {
        "hvac_mode": "heat",
        "hvac_modes": ["off", "heat", "cool", "fan_only"],
        "current_temperature": 21.5,
        "temperature": 22.0,
        "target_temp_low": None,
        "target_temp_high": None,
        "fan_mode": "low",
        "fan_modes": ["low", "medium", "high"],
    }
    hass.states.get = MagicMock(return_value=state)

    devices = [
        {"entity_id": "climate.ac1", "type": "ac", "role": "auto", "idle_action": "fan_only", "idle_fan_mode": "low"},
    ]

    with patch(
        "custom_components.roommind.diagnostics._last_commands",
        {"climate.ac1": {"service": "set_hvac_mode", "hvac_mode": "heat"}},
    ):
        result = _build_device_states(hass, devices)

    assert len(result) == 1
    dev = result[0]
    assert dev["entity_id"] == "climate.ac1"
    assert dev["type"] == "ac"
    assert dev["idle_action"] == "fan_only"
    assert dev["idle_fan_mode"] == "low"
    assert dev["ha_state"] == "heat"
    assert dev["hvac_modes"] == ["off", "heat", "cool", "fan_only"]
    assert dev["current_temperature"] == 21.5
    assert dev["fan_mode"] == "low"
    assert dev["last_command"] == {"service": "set_hvac_mode", "hvac_mode": "heat"}


def test_build_device_states_entity_not_found(hass):
    """Device with missing HA entity shows not_found."""
    hass.states.get = MagicMock(return_value=None)
    devices = [{"entity_id": "climate.gone", "type": "trv", "role": "auto"}]

    with patch("custom_components.roommind.diagnostics._last_commands", {}):
        result = _build_device_states(hass, devices)

    assert result[0]["ha_state"] == "not_found"
    assert "last_command" not in result[0]


@pytest.mark.asyncio
async def test_diagnostics_device_states_included(hass, mock_config_entry):
    """Device states are included in room diagnostics when devices exist."""
    store = MagicMock()
    store.get_settings.return_value = {}
    store.get_rooms.return_value = {
        "room_a": {
            "devices": [
                {"entity_id": "climate.trv1", "type": "trv", "role": "auto"},
            ],
        }
    }

    state = MagicMock()
    state.state = "heat"
    state.attributes = {
        "hvac_mode": "heat",
        "hvac_modes": ["off", "heat"],
        "current_temperature": 20.0,
        "temperature": 21.0,
        "target_temp_low": None,
        "target_temp_high": None,
        "fan_mode": None,
        "fan_modes": [],
    }
    hass.states.get = MagicMock(return_value=state)

    coordinator = _make_coordinator()
    hass.data[DOMAIN] = {"store": store, "coordinator": coordinator}

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert "device_states" in result["rooms"]["room_a"]
    assert len(result["rooms"]["room_a"]["device_states"]) == 1
    assert result["rooms"]["room_a"]["device_states"][0]["ha_state"] == "heat"


@pytest.mark.asyncio
async def test_diagnostics_window_state(hass, mock_config_entry):
    """Window manager state is included per room."""
    store = MagicMock()
    store.get_settings.return_value = {}
    store.get_rooms.return_value = {"room_a": {}}

    now = time.time()
    coordinator = _make_coordinator(
        window_paused={"room_a": True},
        window_open_since={"room_a": now - 120},
    )
    hass.data[DOMAIN] = {"store": store, "coordinator": coordinator}

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    window = result["rooms"]["room_a"]["window"]
    assert window["paused"] is True
    assert 118 <= window["open_since"] <= 122


@pytest.mark.asyncio
async def test_diagnostics_cover_state(hass, mock_config_entry):
    """Cover manager state is included when cover exists."""
    store = MagicMock()
    store.get_settings.return_value = {}
    store.get_rooms.return_value = {"room_a": {}}

    now = time.time()
    cover_state = MagicMock()
    cover_state.current_position = 80
    cover_state.last_commanded_position = 80
    cover_state.last_was_forced = False
    cover_state.last_change_ts = now - 300
    cover_state.user_override_until = now + 600

    coordinator = _make_coordinator(cover_states={"room_a": cover_state})
    hass.data[DOMAIN] = {"store": store, "coordinator": coordinator}

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    cover = result["rooms"]["room_a"]["cover"]
    assert cover["current_position"] == 80
    assert cover["last_commanded_position"] == 80
    assert cover["last_was_forced"] is False
    assert 298 <= cover["last_change_ago_s"] <= 302
    assert 598 <= cover["user_override_remaining_s"] <= 602


@pytest.mark.asyncio
async def test_diagnostics_cover_state_no_override(hass, mock_config_entry):
    """Cover state without active override omits remaining_s."""
    store = MagicMock()
    store.get_settings.return_value = {}
    store.get_rooms.return_value = {"room_a": {}}

    cover_state = MagicMock()
    cover_state.current_position = 100
    cover_state.last_commanded_position = None
    cover_state.last_was_forced = False
    cover_state.last_change_ts = 0
    cover_state.user_override_until = 0

    coordinator = _make_coordinator(cover_states={"room_a": cover_state})
    hass.data[DOMAIN] = {"store": store, "coordinator": coordinator}

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    cover = result["rooms"]["room_a"]["cover"]
    assert "user_override_remaining_s" not in cover
    assert "last_change_ago_s" not in cover


@pytest.mark.asyncio
async def test_diagnostics_heat_source_routing(hass, mock_config_entry):
    """Heat source routing state is included when present."""
    store = MagicMock()
    store.get_settings.return_value = {}
    store.get_rooms.return_value = {"room_a": {}}

    coordinator = _make_coordinator(heat_source_states={"room_a": "ac_only"})
    hass.data[DOMAIN] = {"store": store, "coordinator": coordinator}

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert result["rooms"]["room_a"]["heat_source_routing"] == "ac_only"


@pytest.mark.asyncio
async def test_diagnostics_compressor_groups(hass, mock_config_entry):
    """Compressor group state is included."""
    store = MagicMock()
    store.get_settings.return_value = {}
    store.get_rooms.return_value = {}

    now = time.time()
    group_cfg = MagicMock()
    group_cfg.min_run_seconds = 180
    group_cfg.min_off_seconds = 300

    group_state = MagicMock()
    group_state.active_members = {"climate.ac1"}
    group_state.compressor_on_since = now - 60
    group_state.compressor_off_since = None

    coordinator = _make_coordinator(
        compressor_groups={"g1": group_cfg},
        compressor_states={"g1": group_state},
    )
    hass.data[DOMAIN] = {"store": store, "coordinator": coordinator}

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    cg = result["compressor_groups"]["g1"]
    assert cg["active_members"] == ["climate.ac1"]
    assert cg["min_run_s"] == 180
    assert cg["min_off_s"] == 300
    assert 58 <= cg["on_for_s"] <= 62
    assert "off_for_s" not in cg


@pytest.mark.asyncio
async def test_diagnostics_compressor_master_device(hass, mock_config_entry):
    """Compressor group with master device includes master fields in diagnostics."""
    store = MagicMock()
    store.get_settings.return_value = {}
    store.get_rooms.return_value = {}

    now = time.time()
    group_cfg = MagicMock()
    group_cfg.min_run_seconds = 180
    group_cfg.min_off_seconds = 300
    group_cfg.master_entity = "climate.boiler"
    group_cfg.conflict_resolution = "cooling_priority"
    group_cfg.action_script = "script.boiler_control"

    group_state = MagicMock()
    group_state.active_members = {"climate.ac1"}
    group_state.compressor_on_since = now - 60
    group_state.compressor_off_since = None
    group_state.master_action = "heating"
    group_state.master_on_since = now - 45

    coordinator = _make_coordinator(
        compressor_groups={"g1": group_cfg},
        compressor_states={"g1": group_state},
    )
    hass.data[DOMAIN] = {"store": store, "coordinator": coordinator}

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    cg = result["compressor_groups"]["g1"]
    assert cg["master_entity"] == "climate.boiler"
    assert cg["master_action"] == "heating"
    assert cg["conflict_resolution"] == "cooling_priority"
    assert cg["action_script"] == "script.boiler_control"
    assert 43 <= cg["master_on_for_s"] <= 47


@pytest.mark.asyncio
async def test_diagnostics_valve_protection(hass, mock_config_entry):
    """Valve protection state is included."""
    store = MagicMock()
    store.get_settings.return_value = {}
    store.get_rooms.return_value = {}

    now = time.time()
    coordinator = _make_coordinator(
        valve_cycling={"climate.trv1": now - 30},
        valve_last_actuation={"climate.trv1": now - 3600},
    )
    hass.data[DOMAIN] = {"store": store, "coordinator": coordinator}

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    valve = result["valve_protection"]
    assert 28 <= valve["currently_cycling"]["climate.trv1"] <= 32
    assert 3598 <= valve["last_actuation"]["climate.trv1"] <= 3602


@pytest.mark.asyncio
async def test_diagnostics_window_closed_since(hass, mock_config_entry):
    store = MagicMock()
    store.get_settings.return_value = {}
    store.get_rooms.return_value = {"room_a": {}}

    now = time.time()
    coordinator = _make_coordinator(
        window_closed_since={"room_a": now - 60},
    )
    hass.data[DOMAIN] = {"store": store, "coordinator": coordinator}

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    window = result["rooms"]["room_a"]["window"]
    assert 58 <= window["closed_since"] <= 62


@pytest.mark.asyncio
async def test_diagnostics_compressor_off_since(hass, mock_config_entry):
    store = MagicMock()
    store.get_settings.return_value = {}
    store.get_rooms.return_value = {}

    now = time.time()
    group_cfg = MagicMock()
    group_cfg.min_run_seconds = 180
    group_cfg.min_off_seconds = 300
    group_cfg.master_entity = ""
    group_cfg.enforce_uniform_mode = False

    group_state = MagicMock()
    group_state.active_members = set()
    group_state.compressor_on_since = None
    group_state.compressor_off_since = now - 90

    coordinator = _make_coordinator(
        compressor_groups={"g1": group_cfg},
        compressor_states={"g1": group_state},
    )
    hass.data[DOMAIN] = {"store": store, "coordinator": coordinator}

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    cg = result["compressor_groups"]["g1"]
    assert 88 <= cg["off_for_s"] <= 92
    assert "on_for_s" not in cg


@pytest.mark.asyncio
async def test_diagnostics_room_with_temperature_sensor(hass, mock_config_entry):
    store = MagicMock()
    store.get_settings.return_value = {}
    store.get_rooms.return_value = {
        "room_a": {"temperature_sensor": "sensor.temp_living"},
    }

    sensor_state = MagicMock()
    sensor_state.state = "21.3"
    hass.states.get = MagicMock(return_value=sensor_state)

    coordinator = _make_coordinator()
    hass.data[DOMAIN] = {"store": store, "coordinator": coordinator}

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert result["rooms"]["room_a"]["live"]["sensor_state"] == "21.3"


@pytest.mark.asyncio
async def test_diagnostics_room_with_temperature_sensor_not_found(hass, mock_config_entry):
    store = MagicMock()
    store.get_settings.return_value = {}
    store.get_rooms.return_value = {
        "room_a": {"temperature_sensor": "sensor.missing"},
    }

    hass.states.get = MagicMock(return_value=None)

    coordinator = _make_coordinator()
    hass.data[DOMAIN] = {"store": store, "coordinator": coordinator}

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert result["rooms"]["room_a"]["live"]["sensor_state"] == "not_found"


@pytest.mark.asyncio
async def test_diagnostics_room_with_active_schedule(hass, mock_config_entry):
    store = MagicMock()
    store.get_settings.return_value = {}
    store.get_rooms.return_value = {
        "room_a": {
            "schedules": [{"entity_id": "schedule.weekday"}],
        },
    }

    schedule_state = MagicMock()
    schedule_state.state = "on"
    hass.states.get = MagicMock(return_value=schedule_state)

    coordinator = _make_coordinator(
        rooms={"room_a": {"active_schedule_index": 0}},
    )
    hass.data[DOMAIN] = {"store": store, "coordinator": coordinator}

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    live = result["rooms"]["room_a"]["live"]
    assert live["schedule_entity"] == "schedule.weekday"
    assert live["schedule_state"] == "on"


@pytest.mark.asyncio
async def test_diagnostics_room_schedule_entity_not_found(hass, mock_config_entry):
    store = MagicMock()
    store.get_settings.return_value = {}
    store.get_rooms.return_value = {
        "room_a": {
            "schedules": [{"entity_id": "schedule.missing"}],
        },
    }

    hass.states.get = MagicMock(return_value=None)

    coordinator = _make_coordinator(
        rooms={"room_a": {"active_schedule_index": 0}},
    )
    hass.data[DOMAIN] = {"store": store, "coordinator": coordinator}

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    live = result["rooms"]["room_a"]["live"]
    assert live["schedule_entity"] == "schedule.missing"
    assert live["schedule_state"] == "not_found"


@pytest.mark.asyncio
async def test_diagnostics_cover_with_last_command_ts(hass, mock_config_entry):
    store = MagicMock()
    store.get_settings.return_value = {}
    store.get_rooms.return_value = {"room_a": {}}

    now = time.time()
    cover_state = MagicMock()
    cover_state.current_position = 50
    cover_state.last_commanded_position = 50
    cover_state.last_was_forced = True
    cover_state.last_change_ts = None
    cover_state.last_command_ts = now - 200
    cover_state.user_override_until = 0

    coordinator = _make_coordinator(cover_states={"room_a": cover_state})
    hass.data[DOMAIN] = {"store": store, "coordinator": coordinator}

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    cover = result["rooms"]["room_a"]["cover"]
    assert 198 <= cover["last_command_ago_s"] <= 202
    assert "last_change_ago_s" not in cover
