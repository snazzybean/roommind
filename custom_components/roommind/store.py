"""Room persistence layer for RoomMind."""

from __future__ import annotations

import copy

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    DEFAULT_COMFORT_COOL,
    DEFAULT_COMFORT_HEAT,
    DEFAULT_COMFORT_TEMP,
    DEFAULT_ECO_COOL,
    DEFAULT_ECO_HEAT,
    DEFAULT_ECO_TEMP,
    DOMAIN,
)

STORAGE_VERSION = 1
STORAGE_KEY = DOMAIN


def _migrate_room_temps(room: dict) -> dict:
    """Migrate legacy single comfort/eco temps to split heat/cool fields."""
    if "comfort_heat" not in room:
        room["comfort_heat"] = room.get("comfort_temp", DEFAULT_COMFORT_HEAT)
    if "comfort_cool" not in room:
        room["comfort_cool"] = DEFAULT_COMFORT_COOL
    if "eco_heat" not in room:
        room["eco_heat"] = room.get("eco_temp", DEFAULT_ECO_HEAT)
    if "eco_cool" not in room:
        room["eco_cool"] = DEFAULT_ECO_COOL
    return room


class RoomMindStore:
    """Manage room configuration storage for RoomMind."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise the store."""
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: dict[str, dict] = {}
        self._settings: dict = {}
        self._thermal_data: dict = {}

    async def async_load(self) -> None:
        """Load room data from the HA store."""
        stored = await self._store.async_load()
        if stored and "rooms" in stored:
            self._data = stored["rooms"]
        else:
            self._data = {}

        self._settings = stored.get("settings", {}) if stored else {}
        self._thermal_data = stored.get("thermal_data", {}) if stored else {}

    async def _async_save(self) -> None:
        """Persist current room data to the HA store."""
        await self._store.async_save({"rooms": self._data, "settings": self._settings, "thermal_data": self._thermal_data})

    def get_rooms(self) -> dict[str, dict]:
        """Return a deep copy of all rooms (with migration applied)."""
        rooms = copy.deepcopy(dict(self._data))
        for room in rooms.values():
            _migrate_room_temps(room)
        return rooms

    def get_room(self, area_id: str) -> dict | None:
        """Return a deep copy of a single room by area ID, or None if not found."""
        room = self._data.get(area_id)
        if room is None:
            return None
        result = copy.deepcopy(room)
        _migrate_room_temps(result)
        return result

    def get_settings(self) -> dict:
        """Return a deep copy of global settings."""
        return copy.deepcopy(dict(self._settings))

    async def async_save_settings(self, changes: dict) -> dict:
        """Merge changes into global settings and persist."""
        self._settings.update(changes)
        await self._async_save()
        return dict(self._settings)

    def get_thermal_data(self) -> dict:
        """Return a deep copy of thermal learning data."""
        return copy.deepcopy(dict(self._thermal_data))

    async def async_save_thermal_data(self, data: dict) -> None:
        """Replace thermal learning data and persist."""
        self._thermal_data = data
        await self._async_save()

    async def async_clear_thermal_data_room(self, area_id: str) -> None:
        """Clear thermal learning data for a single room."""
        self._thermal_data.pop(area_id, None)
        await self._async_save()

    async def async_clear_all_thermal_data(self) -> None:
        """Clear all thermal learning data."""
        self._thermal_data = {}
        await self._async_save()

    async def async_save_room(self, area_id: str, config: dict) -> dict:
        """Create or update room configuration for an area."""
        if area_id in self._data:
            # Update existing
            existing = self._data[area_id]
            for key, value in config.items():
                if key != "area_id":
                    existing[key] = value
            # Sync legacy fields from split fields for backward compat
            if "comfort_heat" in config:
                existing["comfort_temp"] = config["comfort_heat"]
            if "eco_heat" in config:
                existing["eco_temp"] = config["eco_heat"]
            # Reverse-sync: legacy callers sending only comfort_temp/eco_temp
            if "comfort_temp" in config and "comfort_heat" not in config:
                existing["comfort_heat"] = config["comfort_temp"]
            if "eco_temp" in config and "eco_heat" not in config:
                existing["eco_heat"] = config["eco_temp"]
            await self._async_save()
            return existing
        else:
            # Create new — derive split fields from legacy if needed
            comfort_heat = config.get("comfort_heat", config.get("comfort_temp", DEFAULT_COMFORT_HEAT))
            eco_heat = config.get("eco_heat", config.get("eco_temp", DEFAULT_ECO_HEAT))
            room = {
                "area_id": area_id,
                "thermostats": config.get("thermostats", []),
                "acs": config.get("acs", []),
                "temperature_sensor": config.get("temperature_sensor", ""),
                "humidity_sensor": config.get("humidity_sensor", ""),
                "climate_mode": config.get("climate_mode", "auto"),
                "schedules": config.get("schedules", []),
                "schedule_selector_entity": config.get("schedule_selector_entity", ""),
                "window_sensors": config.get("window_sensors", []),
                "window_open_delay": config.get("window_open_delay", 0),
                "window_close_delay": config.get("window_close_delay", 0),
                "comfort_temp": comfort_heat,
                "eco_temp": eco_heat,
                "comfort_heat": comfort_heat,
                "comfort_cool": config.get("comfort_cool", DEFAULT_COMFORT_COOL),
                "eco_heat": eco_heat,
                "eco_cool": config.get("eco_cool", DEFAULT_ECO_COOL),
                "presence_persons": config.get("presence_persons", []),
                "display_name": config.get("display_name", ""),
                "heating_system_type": config.get("heating_system_type", ""),
                "covers": config.get("covers", []),
                "covers_auto_enabled": config.get("covers_auto_enabled", False),
                "covers_deploy_threshold": config.get("covers_deploy_threshold", 1.5),
                "covers_min_position": config.get("covers_min_position", 0),
                "covers_outdoor_min_temp": config.get("covers_outdoor_min_temp", 10.0),
                "covers_override_minutes": config.get("covers_override_minutes", 60),
                "cover_schedules": config.get("cover_schedules", []),
                "cover_schedule_selector_entity": config.get("cover_schedule_selector_entity", ""),
                "covers_night_close": config.get("covers_night_close", False),
                "covers_night_position": config.get("covers_night_position", 0),
            }
            self._data[area_id] = room
            await self._async_save()
            return room

    async def async_update_room(self, area_id: str, changes: dict) -> dict:
        """Merge changes into an existing room. Raises KeyError if not found."""
        if area_id not in self._data:
            raise KeyError(f"Room '{area_id}' not found")

        # Prevent overriding the area_id
        changes.pop("area_id", None)

        self._data[area_id].update(changes)
        await self._async_save()
        return self._data[area_id]

    async def async_delete_room(self, area_id: str) -> None:
        """Delete a room. Raises KeyError if not found."""
        if area_id not in self._data:
            raise KeyError(f"Room '{area_id}' not found")

        del self._data[area_id]
        await self._async_save()
