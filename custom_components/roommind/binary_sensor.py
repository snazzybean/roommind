"""Binary sensor platform for RoomMind."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RoomMindCoordinator


def _create_room_binary_sensors(
    coordinator: RoomMindCoordinator, area_id: str,
) -> list[BinarySensorEntity]:
    """Create binary sensor entities for a room."""
    return [RoomMindCoverPausedSensor(coordinator, area_id)]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RoomMind binary sensor entities from a config entry."""
    coordinator: RoomMindCoordinator = hass.data[DOMAIN][entry.entry_id]
    store = hass.data[DOMAIN]["store"]
    coordinator.async_add_binary_sensor_entities = async_add_entities
    rooms = store.get_rooms()
    entities: list[BinarySensorEntity] = []
    for area_id, room in rooms.items():
        if room.get("covers"):
            entities.extend(_create_room_binary_sensors(coordinator, area_id))
            coordinator._binary_sensor_entity_areas.add(area_id)
    if entities:
        async_add_entities(entities)


class RoomMindCoverPausedSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor indicating if cover auto-control is paused by user override."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator)
        self._area_id = area_id
        self._attr_unique_id = f"{DOMAIN}_{area_id}_cover_paused"
        self._attr_name = f"{area_id} Cover Paused"
        self._attr_icon = "mdi:hand-back-right"
        self.entity_id = f"binary_sensor.{DOMAIN}_{area_id}_cover_paused"

    @property
    def is_on(self) -> bool:
        """Return True if user override is active (auto-control paused)."""
        if self.coordinator.data is None:
            return False
        room = self.coordinator.data.get("rooms", {}).get(self._area_id)
        return bool(room.get("cover_auto_paused", False)) if room else False
