"""Tests for RoomMind binary sensor platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.typing import UNDEFINED

from custom_components.roommind.binary_sensor import (
    RoomMindCoverPausedSensor,
    _create_room_binary_sensors,
    async_setup_entry,
)
from custom_components.roommind.const import DOMAIN


@pytest.fixture
def mock_coordinator():
    coordinator = MagicMock()
    coordinator.data = {"rooms": {"living_room": {"cover_auto_paused": False}}}
    return coordinator


def test_cover_paused_off(mock_coordinator):
    """Binary sensor OFF when no user override active."""
    mock_coordinator.data = {"rooms": {"living_room": {"cover_auto_paused": False}}}
    sensor = RoomMindCoverPausedSensor(mock_coordinator, "living_room")
    assert sensor.is_on is False


def test_cover_paused_on(mock_coordinator):
    """Binary sensor ON when user override is active."""
    mock_coordinator.data = {"rooms": {"living_room": {"cover_auto_paused": True}}}
    sensor = RoomMindCoverPausedSensor(mock_coordinator, "living_room")
    assert sensor.is_on is True


def test_cover_paused_missing_room(mock_coordinator):
    """Binary sensor returns False when room doesn't exist."""
    mock_coordinator.data = {"rooms": {}}
    sensor = RoomMindCoverPausedSensor(mock_coordinator, "nonexistent")
    assert sensor.is_on is False


def test_cover_paused_missing_key(mock_coordinator):
    """Binary sensor returns False when cover_auto_paused key is missing."""
    mock_coordinator.data = {"rooms": {"living_room": {}}}
    sensor = RoomMindCoverPausedSensor(mock_coordinator, "living_room")
    assert sensor.is_on is False


def test_binary_sensor_unique_id_and_entity_id(mock_coordinator):
    """Binary sensor has correct unique_id and entity_id."""
    sensor = RoomMindCoverPausedSensor(mock_coordinator, "living_room")
    assert sensor.unique_id == "roommind_living_room_cover_paused"
    assert sensor.entity_id == "binary_sensor.roommind_living_room_cover_paused"


def test_create_room_binary_sensors(mock_coordinator):
    """Factory creates exactly one binary sensor per room."""
    sensors = _create_room_binary_sensors(mock_coordinator, "living_room")
    assert len(sensors) == 1
    assert isinstance(sensors[0], RoomMindCoverPausedSensor)


def test_cover_paused_coordinator_data_none(mock_coordinator):
    """Binary sensor returns False when coordinator.data is None (before first update)."""
    mock_coordinator.data = None
    sensor = RoomMindCoverPausedSensor(mock_coordinator, "living_room")
    assert sensor.is_on is False


@pytest.mark.asyncio
async def test_async_setup_entry_creates_entities_for_rooms_with_covers():
    """async_setup_entry creates binary sensors for rooms with covers configured."""
    coordinator = MagicMock()
    coordinator._binary_sensor_entity_areas = set()

    store = MagicMock()
    store.get_rooms.return_value = {
        "living_room": {"covers": ["cover.blinds"]},
        "bedroom": {},  # no covers — should be skipped
    }

    entry = MagicMock()
    entry.entry_id = "test_entry"

    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: coordinator, "store": store}}

    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)

    # Callback stored on coordinator
    assert coordinator.async_add_binary_sensor_entities is async_add_entities
    # Only living_room has covers, so one entity created
    async_add_entities.assert_called_once()
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 1
    assert isinstance(entities[0], RoomMindCoverPausedSensor)
    # Area tracked
    assert "living_room" in coordinator._binary_sensor_entity_areas
    assert "bedroom" not in coordinator._binary_sensor_entity_areas


@pytest.mark.asyncio
async def test_async_setup_entry_no_covers_no_entities():
    """async_setup_entry does not call async_add_entities when no rooms have covers."""
    coordinator = MagicMock()
    coordinator._binary_sensor_entity_areas = set()

    store = MagicMock()
    store.get_rooms.return_value = {"bedroom": {}}

    entry = MagicMock()
    entry.entry_id = "test_entry"

    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: coordinator, "store": store}}

    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)

    async_add_entities.assert_not_called()


def _aq_coordinator(live, room=None):
    coordinator = MagicMock()
    coordinator.data = {"rooms": {"bed": live}}
    coordinator.hass.data = {DOMAIN: {"store": MagicMock(get_room=MagicMock(return_value=room or {}))}}
    return coordinator


def test_air_quality_sensor_reads_the_live_state():
    from custom_components.roommind.binary_sensor import RoomMindAirQualitySensor

    live = {
        "co2": 1250.0,
        "voc": None,
        "air_quality_bad": True,
        "air_quality_reason": "co2",
        "ventilation_active": True,
    }
    sensor = RoomMindAirQualitySensor(_aq_coordinator(live, {"display_name": "Schlafzimmer"}), "bed")
    assert sensor.unique_id == "roommind_bed_air_quality"
    assert sensor.entity_id == "binary_sensor.roommind_bed_air_quality"
    assert sensor.translation_placeholders == {"room": "Schlafzimmer"}
    assert sensor.is_on is True
    assert sensor.available is True
    assert sensor.extra_state_attributes == {"co2": 1250.0, "voc": None, "reason": "co2", "ventilation_active": True}


def test_air_quality_sensor_unavailable_without_a_reading():
    from custom_components.roommind.binary_sensor import RoomMindAirQualitySensor

    coordinator = _aq_coordinator({"co2": None, "voc": None, "air_quality_bad": False})
    sensor = RoomMindAirQualitySensor(coordinator, "bed")
    assert sensor.available is False
    assert sensor.is_on is False
    coordinator.data = None
    assert sensor.is_on is False


@pytest.mark.asyncio
async def test_async_setup_entry_creates_the_air_quality_sensor_next_to_the_cover_one():
    from custom_components.roommind.binary_sensor import RoomMindAirQualitySensor

    coordinator = MagicMock()
    coordinator._binary_sensor_entity_areas = set()
    coordinator._air_quality_entity_areas = set()
    store = MagicMock()
    store.get_rooms.return_value = {
        "living_room": {"covers": ["cover.blinds"], "co2_sensor": "sensor.co2"},
        "garden": {"co2_sensor": "sensor.garden_co2", "is_outdoor": True},
    }
    store.get_room.return_value = {"display_name": "Wohnzimmer"}
    entry = MagicMock()
    entry.entry_id = "test_entry"
    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: coordinator, "store": store}}
    coordinator.hass = hass
    add = MagicMock()
    await async_setup_entry(hass, entry, add)
    entities = add.call_args[0][0]
    assert [type(e) for e in entities] == [RoomMindCoverPausedSensor, RoomMindAirQualitySensor]
    assert coordinator._air_quality_entity_areas == {"living_room"}


def test_air_quality_sensor_name_follows_a_renamed_room():
    from custom_components.roommind.binary_sensor import RoomMindAirQualitySensor

    room = {"display_name": "Schlafzimmer"}
    coordinator = _aq_coordinator({}, room)
    sensor = RoomMindAirQualitySensor(coordinator, "bed")
    # CI's older HA reads the translation key through ``platform``, newer ones through ``platform_data``
    sensor.platform = sensor.platform_data = MagicMock(
        platform_name=DOMAIN,
        domain="binary_sensor",
        platform_translations={f"component.{DOMAIN}.entity.binary_sensor.air_quality.name": "{room} air quality poor"},
    )
    assert sensor.name == "Schlafzimmer air quality poor"
    room["display_name"] = "Kinderzimmer"
    assert sensor.name == "Kinderzimmer air quality poor"
    assert RoomMindAirQualitySensor(coordinator, "bed").name is UNDEFINED


def test_air_quality_sensor_falls_back_to_the_area_name():
    from custom_components.roommind.binary_sensor import RoomMindAirQualitySensor

    sensor = RoomMindAirQualitySensor(_aq_coordinator({}), "bed")
    with patch("custom_components.roommind.binary_sensor._get_area_name", return_value="Bedroom"):
        assert sensor.translation_placeholders == {"room": "Bedroom"}


@pytest.mark.asyncio
async def test_air_quality_sensor_lands_in_its_area_once():
    from custom_components.roommind.binary_sensor import RoomMindAirQualitySensor

    sensor = RoomMindAirQualitySensor(_aq_coordinator({}), "bed")
    sensor.hass = MagicMock()
    with (
        patch("homeassistant.helpers.update_coordinator.CoordinatorEntity.async_added_to_hass", new=AsyncMock()),
        patch("custom_components.roommind.binary_sensor.assign_area_once") as assign,
    ):
        await sensor.async_added_to_hass()
    assign.assert_called_once_with(sensor.hass, "binary_sensor.roommind_bed_air_quality", "bed", DOMAIN)
