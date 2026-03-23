"""Sensor reading utilities for RoomMind."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def _read_climate_attribute(state: Any, value_name: str) -> float | None:
    """Extract a numeric value from a climate entity's attributes.

    Climate entities use ``state.state`` for the HVAC mode (heat/cool/off),
    not for sensor readings.  Temperature and humidity live in attributes.
    """
    if "temperature" in value_name:
        raw = state.attributes.get("current_temperature")
    elif "humidity" in value_name:
        raw = state.attributes.get("current_humidity")
    else:
        return None
    if raw is None:
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def read_sensor_value(
    hass: HomeAssistant,
    entity_id: str | None,
    area_id: str,
    value_name: str,
) -> float | None:
    """Read a numeric sensor value, returning None on failure.

    Parameters
    ----------
    hass:
        Home Assistant instance.
    entity_id:
        The sensor entity to read (e.g. ``sensor.living_room_temp``).
        If *None* or empty, returns *None* immediately.
    area_id:
        Used only for log messages.
    value_name:
        Human-readable name of the value (e.g. "temperature", "humidity")
        used in warning messages.
    """
    if not entity_id:
        return None

    state = hass.states.get(entity_id)
    if state is None or state.state in ("unavailable", "unknown"):
        return None

    # Climate entities store values in attributes, not state
    if entity_id.startswith("climate."):
        return _read_climate_attribute(state, value_name)

    try:
        return float(state.state)
    except (ValueError, TypeError):
        _LOGGER.warning(
            "Room '%s': could not parse %s from '%s'",
            area_id,
            value_name,
            state.state,
        )
        return None
