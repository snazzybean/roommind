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


# Power sensor units to kW; a sensor without a unit is read as W (HA's default for power)
_POWER_UNIT_TO_KW = {"W": 0.001, "kW": 1.0, "MW": 1000.0, None: 0.001}
_power_warned: set[str] = set()


def usable_power_sensors(
    hass: HomeAssistant,
    entity_ids: list[str],
    area_id: str,
    *,
    exclude_device_ids: set[str] | frozenset[str] = frozenset(),
) -> list[str]:
    """The room's power sensors without those on its own climate devices.

    A sensor on a device in *exclude_device_ids* is left out with a warning once: the
    heat of the room's own heaters is already learned as heating power.
    """
    if not exclude_device_ids:
        return list(entity_ids)
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    usable: list[str] = []
    for entity_id in entity_ids:
        entry = registry.async_get(entity_id)
        if entry is not None and entry.device_id in exclude_device_ids:
            if entity_id not in _power_warned:
                _power_warned.add(entity_id)
                _LOGGER.warning(
                    "Room '%s': power sensor '%s' belongs to one of the room's climate devices, "
                    "its heat is already learned as heating power; ignored",
                    area_id,
                    entity_id,
                )
            continue
        usable.append(entity_id)
    return usable


def read_power_readings(hass: HomeAssistant, entity_ids: list[str], area_id: str) -> dict[str, float]:
    """Reading of each power sensor in kW; sensors without a usable reading are left out.

    Negative readings (a meter that also counts feed-in) count as 0.
    """
    readings: dict[str, float] = {}
    for entity_id in entity_ids:
        value = read_sensor_value(hass, entity_id, area_id, "power")
        if value is None:
            continue
        state = hass.states.get(entity_id)
        unit = state.attributes.get("unit_of_measurement") if state is not None else None
        factor = _POWER_UNIT_TO_KW.get(unit)
        if factor is None:
            if entity_id not in _power_warned:
                _power_warned.add(entity_id)
                _LOGGER.warning(
                    "Room '%s': power sensor '%s' has unit '%s', expected W or kW", area_id, entity_id, unit
                )
            continue
        readings[entity_id] = max(0.0, value) * factor
    return readings


def read_power_kw(
    hass: HomeAssistant,
    entity_ids: list[str],
    area_id: str,
    *,
    exclude_device_ids: set[str] | frozenset[str] = frozenset(),
) -> float | None:
    """Sum of the room's usable power sensors in kW (for display), None when none has a reading."""
    usable = usable_power_sensors(hass, entity_ids, area_id, exclude_device_ids=exclude_device_ids)
    readings = read_power_readings(hass, usable, area_id)
    return sum(readings.values()) if readings else None


def room_device_ids(hass: HomeAssistant, devices: list[dict]) -> set[str]:
    """HA device ids of the room's climate devices."""
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    ids: set[str] = set()
    for device in devices:
        entry = registry.async_get(device.get("entity_id", ""))
        if entry is not None and entry.device_id:
            ids.add(entry.device_id)
    return ids
