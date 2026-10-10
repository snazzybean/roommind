"""Diagnostics schema v2: enough detail to rebuild a reporter's setup in a simulation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.roommind.const import DOMAIN
from custom_components.roommind.diagnostics import (
    DIAGNOSTICS_SCHEMA_VERSION,
    _build_device_states,
    _build_entity_states,
    async_get_config_entry_diagnostics,
)
from tests.test_diagnostics import _make_coordinator, _make_estimator


def _state(state: str, **attrs):  # noqa: ANN003, ANN202
    obj = MagicMock()
    obj.state = state
    obj.attributes = attrs
    obj.last_changed.timestamp.return_value = 1000.0
    return obj


def _setup(hass, rooms, coordinator, states):  # noqa: ANN001, ANN202
    store = MagicMock()
    store.get_settings.return_value = {}
    store.get_rooms.return_value = rooms
    hass.data[DOMAIN] = {"store": store, "coordinator": coordinator}
    hass.states.get = MagicMock(side_effect=states.get)


@pytest.mark.asyncio
async def test_schema_version_and_location_rounded(hass, mock_config_entry):
    hass.config.latitude = 52.5163
    hass.config.longitude = 13.3777
    _setup(hass, {}, _make_coordinator(), {})
    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert result["schema_version"] == DIAGNOSTICS_SCHEMA_VERSION == 2
    integ = result["integration"]
    assert integ["latitude"] == 53
    assert integ["longitude"] == 13
    assert integ["time_zone"] == hass.config.time_zone
    assert integ["unit_system"] in ("metric", "us_customary")
    assert "ha_version" in integ


def test_device_states_include_capabilities_and_command_ages(hass):
    state = _state(
        "heat",
        hvac_mode="heat",
        hvac_modes=["off", "heat"],
        target_temp_step=0.5,
        supported_features=385,
        hvac_action="heating",
        preset_mode="comfort",
        preset_modes=["eco", "comfort"],
        assumed_state=True,
    )
    hass.states.get = MagicMock(return_value=state)
    with (
        patch("custom_components.roommind.diagnostics._last_commands", {}),
        patch("custom_components.roommind.diagnostics._sent_at", {("climate.trv", "set_temperature"): 90.0}),
        patch("custom_components.roommind.diagnostics._active_targets", {"climate.trv": (21.0, None)}),
        patch("custom_components.roommind.diagnostics._now", return_value=100.0),
    ):
        dev = _build_device_states(hass, [{"entity_id": "climate.trv", "type": "trv"}])[0]
    assert dev["target_temp_step"] == 0.5
    assert dev["supported_features"] == 385
    assert dev["hvac_action"] == "heating"
    assert dev["preset_mode"] == "comfort"
    assert dev["preset_modes"] == ["eco", "comfort"]
    assert dev["assumed_state"] is True
    assert dev["command_age_s"] == {"set_temperature": 10}
    assert dev["active_target"] == [21.0, None]


def test_entity_states_cover_every_referenced_entity(hass):
    states = {
        "sensor.t": _state("21.3", unit_of_measurement="°C", device_class="temperature"),
        "binary_sensor.win": _state("off", device_class="window"),
        "schedule.plan": _state("on"),
    }
    hass.states.get = MagicMock(side_effect=states.get)
    room = {
        "temperature_sensor": "sensor.t",
        "humidity_sensor": "",
        "window_sensors": ["binary_sensor.win"],
        "occupancy_sensors": ["binary_sensor.gone"],
        "schedules": [{"entity_id": "schedule.plan"}],
    }
    with patch("custom_components.roommind.diagnostics.time.time", return_value=1060.0):
        result = _build_entity_states(hass, room)
    assert result["sensor.t"] == {"state": "21.3", "unit": "°C", "device_class": "temperature", "age_s": 60}
    assert result["binary_sensor.win"]["device_class"] == "window"
    assert result["binary_sensor.gone"] == {"state": "not_found"}
    assert "schedule.plan" in result
    assert "" not in result


@pytest.mark.asyncio
async def test_room_has_full_model_schedule_blocks_and_entities(hass, mock_config_entry):
    est = _make_estimator()
    est.to_dict.return_value = {"x": [20.0, 0.5], "P": [[1.0]], "n_updates": 200}
    coordinator = _make_coordinator(estimators={"room_a": est})
    coordinator._schedule_blocks_cache = {"schedule.plan": {"monday": [{"from": "06:00:00", "to": "22:00:00"}]}}
    room = {"temperature_sensor": "sensor.t", "schedules": [{"entity_id": "schedule.plan"}]}
    _setup(hass, {"room_a": room}, coordinator, {"sensor.t": _state("20.5")})
    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    diag = result["rooms"]["room_a"]
    assert diag["model_state"] == {"x": [20.0, 0.5], "P": [[1.0]], "n_updates": 200}
    assert diag["schedule_blocks"]["schedule.plan"]["monday"][0]["from"] == "06:00:00"
    assert diag["entities"]["sensor.t"]["state"] == "20.5"


@pytest.mark.asyncio
async def test_history_48h_has_all_columns_and_is_capped(hass, mock_config_entry):
    rows = [{"timestamp": str(i), "room_temp": "20.0", "mode": "idle", "device_setpoint": "21"} for i in range(1500)]
    history = MagicMock()
    history.read_detail = MagicMock(return_value=rows)
    coordinator = _make_coordinator(history_store=history)
    _setup(hass, {"room_a": {}}, coordinator, {})
    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    hist = result["history_48h"]["room_a"]
    assert len(hist) == 1000
    assert hist[-1]["timestamp"] == "1499"
    assert hist[0]["device_setpoint"] == "21"
    assert len(result["recent_history"]["room_a"]) == 240  # v1 field unchanged


@pytest.mark.asyncio
async def test_history_48h_read_error_is_empty(hass, mock_config_entry):
    history = MagicMock()
    history.read_detail = MagicMock(side_effect=OSError("disk"))
    coordinator = _make_coordinator(history_store=history)
    _setup(hass, {"room_a": {}}, coordinator, {})
    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert result["history_48h"]["room_a"] == []
