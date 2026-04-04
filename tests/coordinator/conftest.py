"""Shared helpers and constants for coordinator tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import make_mock_states_get  # noqa: F401

SAMPLE_ROOM = {
    "area_id": "living_room_abc12345",
    "thermostats": ["climate.living_room"],
    "acs": [],
    "devices": [{"entity_id": "climate.living_room", "type": "trv", "role": "auto", "heating_system_type": ""}],
    "temperature_sensor": "sensor.living_room_temp",
    "humidity_sensor": "sensor.living_room_humidity",
    "climate_mode": "auto",
    "schedules": [{"entity_id": "schedule.living_room_heating"}],
    "schedule_selector_entity": "",
    "comfort_temp": 21.0,
    "eco_temp": 17.0,
    "occupancy_sensors": [],
}

MANAGED_ROOM = {
    **SAMPLE_ROOM,
    "temperature_sensor": "",  # No external sensor -> Managed Mode
}


def _make_store_mock(rooms=None):
    """Create a store mock with proper get_settings and get_thermal_data returns."""
    store = MagicMock()
    store.get_rooms.return_value = rooms or {}
    store.get_settings.return_value = {}
    store.get_thermal_data.return_value = {}
    store.async_save_thermal_data = AsyncMock()
    return store


def _create_coordinator(hass, mock_config_entry):
    """Create a RoomMindCoordinator with frame.report_usage patched out."""
    from custom_components.roommind.coordinator import RoomMindCoordinator

    with patch("homeassistant.helpers.frame.report_usage"):
        coordinator = RoomMindCoordinator(hass, mock_config_entry)
    return coordinator


def _presence_states_get(*persons_home):
    """Create a mock states.get function with configurable presence.

    Any ``person.*`` entity in *persons_home* will report ``"home"``;
    all other ``person.*`` entities report ``"not_home"``.

    Non-person entities use the standard defaults from
    :func:`make_mock_states_get`.
    """
    home_set = set(persons_home)

    # Build the base mock with standard defaults
    base = make_mock_states_get()

    def _mock(entity_id):
        if entity_id.startswith("person."):
            s = MagicMock()
            s.state = "home" if entity_id in home_set else "not_home"
            return s
        return base(entity_id)

    return _mock
