"""Tests for sensor dropout fallback (cached temperature on sensor unavailability)."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.const import MAX_SENSOR_STALENESS, MODE_IDLE

from .conftest import (
    MANAGED_ROOM,
    SAMPLE_ROOM,
    _create_coordinator,
    _make_store_mock,
    make_mock_states_get,
)


@pytest.mark.asyncio
async def test_sensor_dropout_keeps_previous_mode(hass, mock_config_entry):
    """When sensor drops out, cached temp keeps mode=heating instead of idle."""
    store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
    hass.data = {"roommind": {"store": store}}

    # Cycle 1: valid temp → heating (18°C < 21°C comfort)
    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="18.0"))
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    result1 = await coordinator._async_update_data()
    assert result1["rooms"]["living_room_abc12345"]["mode"] == "heating"

    # Cycle 2: sensor dropout (temp=None) → should still be heating via cache
    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp=None))
    result2 = await coordinator._async_update_data()
    room2 = result2["rooms"]["living_room_abc12345"]
    assert room2["mode"] == "heating", "sensor dropout should use cached temp, not idle"
    assert room2["current_temp"] == 18.0, "current_temp should show cached value"
    assert room2["current_temp_raw"] is None, "current_temp_raw should be None (real reading)"


@pytest.mark.asyncio
async def test_sensor_dropout_staleness_timeout(hass, mock_config_entry):
    """Cached temp older than MAX_SENSOR_STALENESS → fall back to idle."""
    store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
    hass.data = {"roommind": {"store": store}}

    # Cycle 1: populate cache
    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="18.0"))
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    await coordinator._async_update_data()

    # Manually expire the cache
    area_id = "living_room_abc12345"
    cached_temp, _ = coordinator._last_valid_temps[area_id]
    coordinator._last_valid_temps[area_id] = (cached_temp, time.monotonic() - MAX_SENSOR_STALENESS - 1)

    # Cycle 2: sensor dropout with expired cache → idle
    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp=None))
    result = await coordinator._async_update_data()
    assert result["rooms"]["living_room_abc12345"]["mode"] == MODE_IDLE


@pytest.mark.asyncio
async def test_sensor_dropout_ekf_skipped(hass, mock_config_entry):
    """EKF training is skipped during sensor dropout, even with cached temp."""
    store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
    hass.data = {"roommind": {"store": store}}

    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="18.0"))
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    await coordinator._async_update_data()

    # Patch EKF training to track calls
    with (
        patch.object(coordinator._ekf_training, "process") as mock_process,
        patch.object(coordinator._ekf_training, "clear") as mock_clear,
    ):
        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp=None))
        await coordinator._async_update_data()

        mock_process.assert_not_called()
        mock_clear.assert_called_once_with("living_room_abc12345")


@pytest.mark.asyncio
async def test_sensor_dropout_history_records_none(hass, mock_config_entry):
    """History CSV should record None for room_temp during dropout, not cached value."""
    store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
    hass.data = {"roommind": {"store": store}}

    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="18.0"))
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    await coordinator._async_update_data()

    # Sensor dropout
    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp=None))
    result = await coordinator._async_update_data()
    room = result["rooms"]["living_room_abc12345"]
    assert room["current_temp_raw"] is None
    assert room["current_temp"] == 18.0  # cached for display


@pytest.mark.asyncio
async def test_sensor_dropout_min_run_preserved(hass, mock_config_entry):
    """Min-run timer (_mode_on_since) survives sensor dropout."""
    store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
    hass.data = {"roommind": {"store": store}}

    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="18.0"))
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    await coordinator._async_update_data()

    area_id = "living_room_abc12345"
    assert area_id in coordinator._mode_on_since, "_mode_on_since should be set after heating starts"
    ts_before = coordinator._mode_on_since[area_id]

    # Sensor dropout
    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp=None))
    await coordinator._async_update_data()

    assert area_id in coordinator._mode_on_since, "_mode_on_since should survive sensor dropout"
    assert coordinator._mode_on_since[area_id] == ts_before, "timestamp should not change"


@pytest.mark.asyncio
async def test_no_cache_first_cycle_stays_idle(hass, mock_config_entry):
    """First cycle with no prior cache and sensor=None → idle (no fallback available)."""
    store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
    hass.data = {"roommind": {"store": store}}

    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp=None))
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    result = await coordinator._async_update_data()

    assert result["rooms"]["living_room_abc12345"]["mode"] == MODE_IDLE


@pytest.mark.asyncio
async def test_room_removal_clears_cache(hass, mock_config_entry):
    """async_room_removed clears the temperature cache for that room."""
    store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
    hass.data = {"roommind": {"store": store}}

    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="18.0"))
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    await coordinator._async_update_data()

    area_id = "living_room_abc12345"
    assert area_id in coordinator._last_valid_temps

    coordinator.async_request_refresh = AsyncMock()
    with patch("homeassistant.helpers.entity_registry.async_get") as mock_er:
        mock_er.return_value = MagicMock(entities=MagicMock(values=MagicMock(return_value=[])))
        await coordinator.async_room_removed(area_id)

    assert area_id not in coordinator._last_valid_temps


@pytest.mark.asyncio
async def test_managed_mode_dropout_uses_cache(hass, mock_config_entry):
    """Managed Mode room with device temp dropout also uses cached temperature."""
    managed_room = {**MANAGED_ROOM, "area_id": "living_room_abc12345"}
    store = _make_store_mock({"living_room_abc12345": managed_room})
    hass.data = {"roommind": {"store": store}}

    # Cycle 1: device reports temperature via climate entity
    climate_attrs = {
        "hvac_modes": ["off", "heat"],
        "current_temperature": 19.0,
        "temperature": 21.0,
        "min_temp": 5,
        "max_temp": 30,
    }
    hass.states.get = MagicMock(
        side_effect=make_mock_states_get(
            temp=None,  # no external sensor
            extra={"climate.living_room": ("heat", climate_attrs)},
        )
    )
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    await coordinator._async_update_data()

    area_id = "living_room_abc12345"
    assert area_id in coordinator._last_valid_temps
    cached_val, _ = coordinator._last_valid_temps[area_id]
    assert cached_val == 19.0

    # Cycle 2: device also unavailable → cache kicks in
    climate_attrs_none = {
        "hvac_modes": ["off", "heat"],
        "current_temperature": None,
        "temperature": 21.0,
        "min_temp": 5,
        "max_temp": 30,
    }
    hass.states.get = MagicMock(
        side_effect=make_mock_states_get(
            temp=None,
            extra={"climate.living_room": ("heat", climate_attrs_none)},
        )
    )
    result = await coordinator._async_update_data()
    room = result["rooms"]["living_room_abc12345"]
    assert room["current_temp"] == 19.0, "should use cached device temp"
    assert room["current_temp_raw"] is None
