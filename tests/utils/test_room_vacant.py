"""Tests for is_room_vacant: occupancy eco reads last_changed, not the poll (#180)."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

from homeassistant.core import State
from homeassistant.util import dt as dt_util

from custom_components.roommind.utils.presence_utils import (
    is_occupancy_held,
    is_room_occupied,
    is_room_vacant,
    occupancy_quiet_since,
)

ROOM = {
    "occupancy_sensors": ["binary_sensor.motion", "binary_sensor.desk"],
    "occupancy_eco_enabled": True,
    "occupancy_eco_delay": 15,
}


def _hass(states: dict[str, tuple[str, float] | None]):
    """entity_id -> (state, minutes since last change), None for a missing entity."""
    now = dt_util.utcnow()
    objs = {
        eid: State(eid, val[0], last_changed=now - timedelta(minutes=val[1]))
        for eid, val in states.items()
        if val is not None
    }
    hass = MagicMock()
    hass.states.get = objs.get
    return hass, now.timestamp()


def test_vacant_once_every_sensor_is_off_for_the_delay():
    hass, now = _hass({"binary_sensor.motion": ("off", 20), "binary_sensor.desk": ("off", 15)})
    assert is_room_vacant(hass, ROOM, now) is True


def test_latest_change_restarts_the_delay():
    """A motion pulse between two polls still shows up as a fresh last_changed."""
    hass, now = _hass({"binary_sensor.motion": ("off", 2), "binary_sensor.desk": ("off", 60)})
    assert is_room_vacant(hass, ROOM, now) is False


def test_any_sensor_on_means_occupied():
    hass, now = _hass({"binary_sensor.motion": ("off", 60), "binary_sensor.desk": ("on", 60)})
    assert is_room_vacant(hass, ROOM, now) is False


def test_unreadable_or_missing_sensor_counts_as_occupied():
    for state in ("unavailable", "unknown"):
        hass, now = _hass({"binary_sensor.motion": ("off", 60), "binary_sensor.desk": (state, 60)})
        assert is_room_vacant(hass, ROOM, now) is False
    hass, now = _hass({"binary_sensor.motion": ("off", 60), "binary_sensor.desk": None})
    assert is_room_vacant(hass, ROOM, now) is False


def test_disabled_or_without_sensors_is_never_vacant():
    hass, now = _hass({"binary_sensor.motion": ("off", 60), "binary_sensor.desk": ("off", 60)})
    assert is_room_vacant(hass, {**ROOM, "occupancy_eco_enabled": False}, now) is False
    assert is_room_vacant(hass, {**ROOM, "occupancy_sensors": []}, now) is False
    assert is_room_vacant(hass, {"occupancy_sensors": ROOM["occupancy_sensors"]}, now) is False


def test_missing_delay_uses_the_default():
    room = {"occupancy_sensors": ["binary_sensor.motion"], "occupancy_eco_enabled": True}
    hass, now = _hass({"binary_sensor.motion": ("off", 14)})
    assert is_room_vacant(hass, room, now) is False
    hass, now = _hass({"binary_sensor.motion": ("off", 16)})
    assert is_room_vacant(hass, room, now) is True


def test_quiet_since_is_the_latest_change_while_all_are_off():
    hass, now = _hass({"binary_sensor.motion": ("off", 20), "binary_sensor.desk": ("off", 5)})
    assert occupancy_quiet_since(hass, ROOM) == now - 5 * 60


def test_not_quiet_while_a_sensor_is_on_or_unavailable():
    hass, _ = _hass({"binary_sensor.motion": ("on", 20), "binary_sensor.desk": ("off", 5)})
    assert occupancy_quiet_since(hass, ROOM) is None
    hass, _ = _hass({"binary_sensor.motion": ("unavailable", 20), "binary_sensor.desk": ("off", 5)})
    assert occupancy_quiet_since(hass, ROOM) is None


def test_occupied_after_the_confirmation_time():
    hass, now = _hass({"binary_sensor.motion": ("on", 5), "binary_sensor.desk": ("off", 60)})
    assert is_room_occupied(hass, ROOM, now, 5) is True
    assert is_room_occupied(hass, ROOM, now, 6) is False


def test_unavailable_sensor_is_not_occupied():
    hass, now = _hass({"binary_sensor.motion": ("unavailable", 60), "binary_sensor.desk": None})
    assert is_room_occupied(hass, ROOM, now, 0) is False


def test_held_while_a_sensor_is_on_or_off_for_less_than_the_release_time():
    hass, now = _hass({"binary_sensor.motion": ("on", 0), "binary_sensor.desk": ("off", 60)})
    assert is_occupancy_held(hass, ROOM, now, 5) is True
    hass, now = _hass({"binary_sensor.motion": ("off", 4), "binary_sensor.desk": ("off", 60)})
    assert is_occupancy_held(hass, ROOM, now, 5) is True
    hass, now = _hass({"binary_sensor.motion": ("off", 5), "binary_sensor.desk": ("off", 60)})
    assert is_occupancy_held(hass, ROOM, now, 5) is False


def test_unavailable_or_missing_sensor_releases_the_hold():
    hass, now = _hass({"binary_sensor.motion": ("unavailable", 0), "binary_sensor.desk": ("off", 1)})
    assert is_occupancy_held(hass, ROOM, now, 5) is False
    hass, now = _hass({"binary_sensor.motion": None, "binary_sensor.desk": ("off", 1)})
    assert is_occupancy_held(hass, ROOM, now, 5) is False
