"""Tests for the startup guard: no device commands until first valid temperature reading."""

from __future__ import annotations

import logging
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.roommind.const import MAX_SENSOR_STALENESS, MODE_IDLE

from .conftest import (
    MANAGED_ROOM,
    SAMPLE_ROOM,
    _create_coordinator,
    _make_store_mock,
    make_mock_states_get,
)

AC_ROOM = {
    **SAMPLE_ROOM,
    "thermostats": [],
    "acs": ["climate.ac_living"],
    "devices": [{"entity_id": "climate.ac_living", "type": "ac", "role": "auto", "heating_system_type": ""}],
}

AC_ATTRS = {
    "hvac_modes": ["off", "cool", "heat", "fan_only"],
    "current_temperature": None,
    "temperature": 24.0,
    "min_temp": 16,
    "max_temp": 30,
}


def _climate_calls(hass, entity_id=None):
    calls = []
    for c in hass.services.async_call.call_args_list:
        if not c.args or c.args[0] != "climate":
            continue
        if entity_id is not None and c.args[2].get("entity_id") != entity_id:
            continue
        calls.append(c)
    return calls


@pytest.mark.asyncio
async def test_startup_no_temp_sends_no_climate_commands(hass, mock_config_entry):
    """First cycle after restart with unavailable sensor must not touch devices."""
    store = _make_store_mock({"living_room_abc12345": AC_ROOM})
    hass.data = {"roommind": {"store": store}}

    hass.states.get = MagicMock(
        side_effect=make_mock_states_get(
            temp=None,
            extra={"climate.ac_living": ("cool", AC_ATTRS)},
        )
    )
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    result = await coordinator._async_update_data()

    assert result["rooms"]["living_room_abc12345"]["mode"] == MODE_IDLE
    assert _climate_calls(hass) == [], "no climate commands until first temperature reading"


@pytest.mark.asyncio
async def test_startup_commands_resume_after_first_reading(hass, mock_config_entry):
    """Control resumes normally once the sensor delivers its first value."""
    store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
    hass.data = {"roommind": {"store": store}}

    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp=None))
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    await coordinator._async_update_data()
    assert _climate_calls(hass) == []

    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="18.0"))
    result = await coordinator._async_update_data()
    assert result["rooms"]["living_room_abc12345"]["mode"] == "heating"
    assert len(_climate_calls(hass, "climate.living_room")) >= 1


@pytest.mark.asyncio
async def test_dropout_after_valid_reading_still_turns_off(hass, mock_config_entry):
    """Prolonged sensor dropout mid-operation keeps the safety shutdown."""
    store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
    hass.data = {"roommind": {"store": store}}

    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="18.0"))
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    await coordinator._async_update_data()

    area_id = "living_room_abc12345"
    cached_temp, _ = coordinator._last_valid_temps[area_id]
    coordinator._last_valid_temps[area_id] = (cached_temp, time.monotonic() - MAX_SENSOR_STALENESS - 1)

    hass.services.async_call.reset_mock()
    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp=None))
    result = await coordinator._async_update_data()

    assert result["rooms"][area_id]["mode"] == MODE_IDLE
    off_calls = [
        c
        for c in _climate_calls(hass, "climate.living_room")
        if c.args[1] == "set_hvac_mode" and c.args[2].get("hvac_mode") == "off"
    ]
    assert len(off_calls) == 1, "safety shutdown on stale sensor must still command off"


@pytest.mark.asyncio
async def test_managed_mode_not_gated(hass, mock_config_entry):
    """Managed Mode rooms need no external sensor and are controlled immediately."""
    managed_room = {**MANAGED_ROOM, "area_id": "living_room_abc12345"}
    store = _make_store_mock({"living_room_abc12345": managed_room})
    hass.data = {"roommind": {"store": store}}

    climate_attrs = {
        "hvac_modes": ["off", "heat"],
        "current_temperature": 19.0,
        "temperature": 18.0,
        "min_temp": 5,
        "max_temp": 30,
    }
    hass.states.get = MagicMock(
        side_effect=make_mock_states_get(
            temp=None,
            extra={"climate.living_room": ("heat", climate_attrs)},
        )
    )
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    await coordinator._async_update_data()

    assert len(_climate_calls(hass, "climate.living_room")) >= 1


@pytest.mark.asyncio
async def test_master_not_commanded_while_member_waiting(hass, mock_config_entry):
    """Master device must not be idled while a member room waits for first data."""
    store = _make_store_mock({"living_room_abc12345": AC_ROOM})
    store.get_settings.return_value = {
        "climate_control_active": True,
        "outdoor_temp_sensor": "sensor.outdoor_temp",
        "compressor_groups": [
            {
                "id": "g1",
                "name": "G1",
                "members": ["climate.ac_living"],
                "master_entity": "climate.outdoor_unit",
            }
        ],
    }
    hass.data = {"roommind": {"store": store}}

    master_attrs = {"hvac_modes": ["off", "cool", "heat"]}
    hass.states.get = MagicMock(
        side_effect=make_mock_states_get(
            temp=None,
            extra={
                "climate.ac_living": ("cool", AC_ATTRS),
                "climate.outdoor_unit": ("cool", master_attrs),
            },
        )
    )
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    await coordinator._async_update_data()

    assert _climate_calls(hass, "climate.outdoor_unit") == []


def test_any_member_room_waiting_skips_outdoor_and_disabled(hass, mock_config_entry):
    """Outdoor and climate-disabled rooms never count as waiting for data."""
    coordinator = _create_coordinator(hass, mock_config_entry)
    rooms = {
        "balcony": {**AC_ROOM, "area_id": "balcony", "is_outdoor": True},
        "cellar": {**AC_ROOM, "area_id": "cellar", "climate_control_enabled": False},
    }
    assert coordinator._any_member_room_waiting(["climate.ac_living"], rooms) is False


@pytest.mark.asyncio
async def test_startup_guard_expires_after_staleness_window(hass, mock_config_entry):
    """A sensor that never reports after restart must not hold the guard forever."""
    store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
    hass.data = {"roommind": {"store": store}}

    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp=None))
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    await coordinator._async_update_data()
    assert _climate_calls(hass) == []

    coordinator._startup_ts = time.monotonic() - MAX_SENSOR_STALENESS - 1
    result = await coordinator._async_update_data()

    assert result["rooms"]["living_room_abc12345"]["mode"] == MODE_IDLE
    off_calls = [
        c
        for c in _climate_calls(hass, "climate.living_room")
        if c.args[1] == "set_hvac_mode" and c.args[2].get("hvac_mode") == "off"
    ]
    assert len(off_calls) == 1, "expired guard must apply the same safety shutdown as a dropout"


@pytest.mark.asyncio
async def test_startup_guard_expiry_warns_once(hass, mock_config_entry, caplog):
    """Guard expiry logs a single warning per room, not one per cycle."""
    store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
    hass.data = {"roommind": {"store": store}}

    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp=None))
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    coordinator._startup_ts = time.monotonic() - MAX_SENSOR_STALENESS - 1

    with caplog.at_level(logging.WARNING):
        await coordinator._async_update_data()
        await coordinator._async_update_data()

    warnings = [
        r for r in caplog.records if r.levelno == logging.WARNING and "no temperature reading" in r.getMessage()
    ]
    assert len(warnings) == 1


def test_any_member_room_waiting_expires_with_grace_period(hass, mock_config_entry):
    """Compressor master guard uses the same startup grace period."""
    coordinator = _create_coordinator(hass, mock_config_entry)
    rooms = {"living": {**AC_ROOM, "area_id": "living"}}
    assert coordinator._any_member_room_waiting(["climate.ac_living"], rooms) is True

    coordinator._startup_ts = time.monotonic() - MAX_SENSOR_STALENESS - 1
    assert coordinator._any_member_room_waiting(["climate.ac_living"], rooms) is False


def test_any_member_room_waiting_counts_pending_window(hass, mock_config_entry):
    """A room whose window state is unresolved keeps the master guard up, even without a temp sensor."""
    coordinator = _create_coordinator(hass, mock_config_entry)
    rooms = {"living": {**AC_ROOM, "area_id": "living", "temperature_sensor": ""}}
    assert coordinator._any_member_room_waiting(["climate.ac_living"], rooms) is False

    coordinator._window_manager.resolve_raw("living", {"binary_sensor.window": "unavailable"})
    assert coordinator._any_member_room_waiting(["climate.ac_living"], rooms) is True

    coordinator._window_manager.resolve_raw("living", {"binary_sensor.window": "off"})
    assert coordinator._any_member_room_waiting(["climate.ac_living"], rooms) is False
