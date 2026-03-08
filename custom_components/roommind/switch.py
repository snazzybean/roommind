"""Switch platform for RoomMind."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RoomMindCoordinator


def _create_room_switches(
    coordinator: RoomMindCoordinator, area_id: str,
) -> list[SwitchEntity]:
    """Create switch entities for a room."""
    return [RoomMindCoverAutoSwitch(coordinator, area_id)]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RoomMind switch entities from a config entry."""
    coordinator: RoomMindCoordinator = hass.data[DOMAIN][entry.entry_id]
    store = hass.data[DOMAIN]["store"]
    coordinator.async_add_switch_entities = async_add_entities
    rooms = store.get_rooms()
    entities: list[SwitchEntity] = []
    for area_id, room in rooms.items():
        if room.get("covers"):
            entities.extend(_create_room_switches(coordinator, area_id))
            coordinator._switch_entity_areas.add(area_id)
    if entities:
        async_add_entities(entities)


class RoomMindCoverAutoSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to toggle automatic cover control per room."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator)
        self._area_id = area_id
        self._attr_unique_id = f"{DOMAIN}_{area_id}_cover_auto"
        self._attr_name = f"{area_id} Cover Auto"
        self._attr_icon = "mdi:blinds-horizontal"
        self.entity_id = f"switch.{DOMAIN}_{area_id}_cover_auto"

    @property
    def is_on(self) -> bool:
        """Return True if automatic cover control is enabled."""
        store = self.coordinator.hass.data[DOMAIN]["store"]
        room = store.get_room(self._area_id)
        return bool(room.get("covers_auto_enabled", False)) if room else False

    async def async_turn_on(self, **kwargs) -> None:
        """Enable automatic cover control."""
        store = self.coordinator.hass.data[DOMAIN]["store"]
        await store.async_update_room(self._area_id, {"covers_auto_enabled": True})
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Disable automatic cover control."""
        store = self.coordinator.hass.data[DOMAIN]["store"]
        await store.async_update_room(self._area_id, {"covers_auto_enabled": False})
        await self.coordinator.async_request_refresh()
