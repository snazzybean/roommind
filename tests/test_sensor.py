"""Tests for the sensor platform."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.roommind.const import DOMAIN
from custom_components.roommind.sensor import (
    RoomMindModeSensor,
    RoomMindTargetTemperatureSensor,
    _create_room_entities,
    async_setup_entry,
)


def _make_coordinator(rooms_data=None):
    """Build a mock coordinator with data dict."""
    coordinator = MagicMock()
    coordinator.data = {"rooms": rooms_data or {}}
    return coordinator


@pytest.mark.asyncio
async def test_setup_entry_creates_entities(hass, mock_config_entry, store):
    """Entities are created for each existing room."""
    await store.async_load()
    await store.async_save_room("room_a", {"thermostats": ["climate.trv1"]})

    coordinator = _make_coordinator()
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: coordinator,
        "store": store,
    }
    add_entities = MagicMock()

    await async_setup_entry(hass, mock_config_entry, add_entities)

    # Callback stored on coordinator
    assert coordinator.async_add_entities is add_entities
    # 2 entities per room (target_temp + mode)
    add_entities.assert_called_once()
    entities = add_entities.call_args[0][0]
    assert len(entities) == 2


@pytest.mark.asyncio
async def test_setup_entry_no_rooms(hass, mock_config_entry, store):
    """No entities created when store has no rooms."""
    await store.async_load()

    coordinator = _make_coordinator()
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: coordinator,
        "store": store,
    }
    add_entities = MagicMock()

    await async_setup_entry(hass, mock_config_entry, add_entities)

    assert coordinator.async_add_entities is add_entities
    add_entities.assert_not_called()


@pytest.mark.asyncio
async def test_setup_entry_multiple_rooms(hass, mock_config_entry, store):
    """Entities created for each room."""
    await store.async_load()
    await store.async_save_room("room_a", {"thermostats": ["climate.trv1"]})
    await store.async_save_room("room_b", {"thermostats": ["climate.trv2"]})

    coordinator = _make_coordinator()
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: coordinator,
        "store": store,
    }
    add_entities = MagicMock()

    await async_setup_entry(hass, mock_config_entry, add_entities)

    entities = add_entities.call_args[0][0]
    assert len(entities) == 4  # 2 per room


def test_create_room_entities():
    """_create_room_entities returns target temp and mode sensors."""
    coordinator = _make_coordinator()
    entities = _create_room_entities(coordinator, "room_a")
    assert len(entities) == 2
    assert isinstance(entities[0], RoomMindTargetTemperatureSensor)
    assert isinstance(entities[1], RoomMindModeSensor)


def test_target_temp_sensor_value():
    """Target temperature sensor returns value from room data."""
    coordinator = _make_coordinator({"room_a": {"target_temp": 21.5}})
    sensor = RoomMindTargetTemperatureSensor(coordinator, "room_a")
    assert sensor.native_value == 21.5


def test_target_temp_sensor_missing_room():
    """Target temperature sensor returns None when room is missing."""
    coordinator = _make_coordinator({})
    sensor = RoomMindTargetTemperatureSensor(coordinator, "room_a")
    assert sensor.native_value is None


def test_target_temp_sensor_missing_key():
    """Target temperature sensor returns None when key is missing."""
    coordinator = _make_coordinator({"room_a": {"mode": "idle"}})
    sensor = RoomMindTargetTemperatureSensor(coordinator, "room_a")
    assert sensor.native_value is None


def test_mode_sensor_value():
    """Mode sensor returns value from room data."""
    coordinator = _make_coordinator({"room_a": {"mode": "heating"}})
    sensor = RoomMindModeSensor(coordinator, "room_a")
    assert sensor.native_value == "heating"


def test_mode_sensor_defaults_to_idle():
    """Mode sensor defaults to 'idle' when key is missing."""
    coordinator = _make_coordinator({"room_a": {"target_temp": 21.0}})
    sensor = RoomMindModeSensor(coordinator, "room_a")
    assert sensor.native_value == "idle"


def test_mode_sensor_missing_room():
    """Mode sensor returns 'idle' when room is missing."""
    coordinator = _make_coordinator({})
    sensor = RoomMindModeSensor(coordinator, "room_a")
    assert sensor.native_value == "idle"


def test_sensor_unique_id():
    """Sensors have correct unique_id format."""
    coordinator = _make_coordinator()
    temp_sensor = RoomMindTargetTemperatureSensor(coordinator, "room_a")
    mode_sensor = RoomMindModeSensor(coordinator, "room_a")
    assert temp_sensor.unique_id == f"{DOMAIN}_room_a_target_temp"
    assert mode_sensor.unique_id == f"{DOMAIN}_room_a_mode"


def test_sensor_entity_id():
    """Sensors have correct entity_id format."""
    coordinator = _make_coordinator()
    temp_sensor = RoomMindTargetTemperatureSensor(coordinator, "room_a")
    mode_sensor = RoomMindModeSensor(coordinator, "room_a")
    assert temp_sensor.entity_id == f"sensor.{DOMAIN}_room_a_target_temp"
    assert mode_sensor.entity_id == f"sensor.{DOMAIN}_room_a_mode"


# ---------------------------------------------------------------------------
# Global Time-of-Use sensors
# ---------------------------------------------------------------------------


def _tou_coordinator(tou=None):
    coordinator = _make_coordinator()
    coordinator.data = {"rooms": {}, "tou": tou} if tou is not None else {"rooms": {}}
    return coordinator


def test_create_global_entities():
    """_create_global_entities returns the three tariff sensors."""
    from custom_components.roommind.sensor import _create_global_entities

    entities = _create_global_entities(_tou_coordinator())
    assert len(entities) == 3


@pytest.mark.asyncio
async def test_setup_entry_adds_globals_when_tou_enabled(hass, mock_config_entry, store):
    """Enabling Time-of-Use at setup registers the tariff sensors."""
    await store.async_load()
    await store.async_save_settings({"tou_enabled": True})

    coordinator = _make_coordinator()
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: coordinator,
        "store": store,
    }
    add_entities = MagicMock()

    await async_setup_entry(hass, mock_config_entry, add_entities)

    entities = add_entities.call_args[0][0]
    assert len(entities) == 3
    assert coordinator._tou_entities_added is True


def test_energy_rate_sensor_value():
    coordinator = _tou_coordinator({"enabled": True, "tier": "peak", "rate": 0.146, "rate_unit": "CAD/kWh"})
    from custom_components.roommind.sensor import RoomMindEnergyRateSensor

    sensor = RoomMindEnergyRateSensor(coordinator)
    assert sensor.native_value == 0.146
    assert sensor.native_unit_of_measurement == "CAD/kWh"
    assert sensor.entity_id == f"sensor.{DOMAIN}_energy_rate"


def test_energy_rate_sensor_disabled():
    from custom_components.roommind.sensor import RoomMindEnergyRateSensor

    sensor = RoomMindEnergyRateSensor(_tou_coordinator())
    assert sensor.native_value is None
    assert sensor.native_unit_of_measurement is None


def test_energy_period_sensor_value_and_unknown():
    from custom_components.roommind.sensor import RoomMindEnergyPeriodSensor

    coordinator = _tou_coordinator({"enabled": True, "tier": "ultra_low", "rate": None})
    assert RoomMindEnergyPeriodSensor(coordinator).native_value == "ultra_low"

    unknown = _tou_coordinator({"enabled": True, "tier": "unknown", "rate": None})
    assert RoomMindEnergyPeriodSensor(unknown).native_value is None


def test_energy_next_change_sensor_value():
    from custom_components.roommind.sensor import RoomMindEnergyNextChangeSensor

    ts = 1_794_000_000.0
    coordinator = _tou_coordinator(
        {"enabled": True, "tier": "mid", "rate": None, "next_change": ts, "next_tier": "peak"}
    )
    sensor = RoomMindEnergyNextChangeSensor(coordinator)
    value = sensor.native_value
    assert value is not None
    assert abs(value.timestamp() - ts) < 2
    assert sensor.extra_state_attributes == {"next_tier": "peak"}


def test_energy_next_change_sensor_none():
    from custom_components.roommind.sensor import RoomMindEnergyNextChangeSensor

    sensor = RoomMindEnergyNextChangeSensor(_tou_coordinator())
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}
