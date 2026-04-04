"""Fixtures for RoomMind tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.roommind.control.mpc_controller import clear_command_cache
from custom_components.roommind.store import RoomMindStore


def make_mock_states_get(
    temp="18.0",
    humidity="55.0",
    schedule_state="on",
    schedule_attrs=None,
    outdoor_temp=None,
    outdoor_temp_entity="sensor.outdoor_temp",
    window_sensors=None,
    selector_state=None,
    selector_entity="input_boolean.schedule_toggle",
    person_states=None,
    extra=None,
    temp_unit=None,
):
    """Create a mock ``hass.states.get`` with configurable return values.

    Parameters
    ----------
    temp:
        Value for ``sensor.living_room_temp``.  Set to ``None`` to return
        ``None`` (entity missing).  ``"unavailable"`` is also supported.
    humidity:
        Value for ``sensor.living_room_humidity``.
    schedule_state:
        State for ``schedule.living_room_heating``.
    schedule_attrs:
        Attributes dict for the schedule entity (default ``{}``).
    outdoor_temp:
        If given, ``outdoor_temp_entity`` will return this value.
    outdoor_temp_entity:
        Entity id for the outdoor sensor (default ``sensor.outdoor_temp``).
    window_sensors:
        Dict mapping ``binary_sensor.*`` entity ids to state strings
        (e.g. ``{"binary_sensor.window1": "on"}``).
    selector_state:
        If given, ``selector_entity`` will return this state string.
    selector_entity:
        Entity id for the schedule selector (default ``input_boolean.schedule_toggle``).
    person_states:
        Dict mapping ``person.*`` entity ids to state strings
        (e.g. ``{"person.kevin": "home"}``).
    extra:
        Dict mapping arbitrary entity ids to ``(state_str, attrs_dict | None)``
        tuples for any entities not covered by the above parameters.
    temp_unit:
        If given (e.g. ``"°F"``), temperature sensor mocks will include
        ``unit_of_measurement`` in their attributes.
    """
    if schedule_attrs is None:
        schedule_attrs = {}
    if window_sensors is None:
        window_sensors = {}
    if person_states is None:
        person_states = {}
    if extra is None:
        extra = {}

    def _temp_attrs():
        return {"unit_of_measurement": temp_unit} if temp_unit else {}

    def _mock(entity_id):
        # Temperature sensor
        if entity_id == "sensor.living_room_temp":
            if temp is None:
                return None
            s = MagicMock()
            s.state = temp
            s.attributes = _temp_attrs()
            return s

        # Humidity sensor
        if entity_id == "sensor.living_room_humidity":
            if humidity is None:
                return None
            s = MagicMock()
            s.state = humidity
            s.attributes = {}
            return s

        # Schedule entity
        if entity_id == "schedule.living_room_heating":
            s = MagicMock()
            s.state = schedule_state
            s.attributes = schedule_attrs
            return s

        # Outdoor temperature
        if outdoor_temp is not None and entity_id == outdoor_temp_entity:
            s = MagicMock()
            s.state = outdoor_temp
            s.attributes = _temp_attrs()
            return s

        # Window / door sensors
        if entity_id in window_sensors:
            s = MagicMock()
            s.state = window_sensors[entity_id]
            return s

        # Schedule selector
        if selector_state is not None and entity_id == selector_entity:
            s = MagicMock()
            s.state = selector_state
            return s

        # Person entities
        if entity_id in person_states:
            s = MagicMock()
            s.state = person_states[entity_id]
            return s

        # Arbitrary extras
        if entity_id in extra:
            val = extra[entity_id]
            s = MagicMock()
            if isinstance(val, tuple):
                s.state = val[0]
                s.attributes = val[1] if val[1] is not None else {}
            else:
                s.state = val
            return s

        return None

    return _mock


@pytest.fixture(autouse=True)
def _clear_command_cache():
    """Clear the module-level command cache between tests."""
    clear_command_cache()
    yield
    clear_command_cache()


@pytest.fixture
def hass():
    """Return a mocked Home Assistant instance."""
    hass = MagicMock()
    hass.data = {}
    hass.config.path = MagicMock(side_effect=lambda *p: "/".join(("/config",) + p))
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *args: fn(*args))
    return hass


@pytest.fixture
def mock_config_entry():
    """Return a mocked config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {}
    entry.options = {}
    return entry


@pytest.fixture
def store(hass):
    """Return a RoomMindStore with mocked HA storage backend."""
    s = RoomMindStore(hass)
    s._store = AsyncMock()
    s._store.async_load = AsyncMock(return_value=None)
    s._store.async_save = AsyncMock()
    return s
