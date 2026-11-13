"""Binary sensor platform for RoomMind."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RoomMindCoordinator, _get_area_name, has_air_quality_sensor
from .utils.area_utils import rooms_with_area


def _create_room_binary_sensors(
    coordinator: RoomMindCoordinator,
    area_id: str,
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
    rooms = rooms_with_area(hass, store.get_rooms())
    entities: list[BinarySensorEntity] = []
    for area_id, room in rooms.items():
        if room.get("covers"):
            entities.extend(_create_room_binary_sensors(coordinator, area_id))
            coordinator._binary_sensor_entity_areas.add(area_id)
        if has_air_quality_sensor(room):
            entities.append(RoomMindAirQualitySensor(coordinator, area_id))
            coordinator._air_quality_entity_areas.add(area_id)
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


class RoomMindAirQualitySensor(CoordinatorEntity, BinarySensorEntity):
    """On while the room's air is bad (CO2 or VOC past its threshold, #267), for own automations."""

    _attr_has_entity_name = True
    _attr_translation_key = "air_quality"
    _attr_icon = "mdi:molecule-co2"

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator)
        self._area_id = area_id
        self._attr_unique_id = f"{DOMAIN}_{area_id}_air_quality"
        self.entity_id = f"binary_sensor.{DOMAIN}_{area_id}_air_quality"
        room = coordinator.hass.data[DOMAIN]["store"].get_room(area_id) or {}
        self._attr_translation_placeholders = {
            "room": room.get("display_name") or _get_area_name(coordinator.hass, area_id)
        }

    def _live(self) -> dict:
        live: dict = ((self.coordinator.data or {}).get("rooms") or {}).get(self._area_id) or {}
        return live

    @property
    def available(self) -> bool:
        """Unavailable while no air quality sensor delivers a reading."""
        live = self._live()
        return super().available and (live.get("co2") is not None or live.get("voc") is not None)

    @property
    def is_on(self) -> bool:
        return bool(self._live().get("air_quality_bad", False))

    @property
    def extra_state_attributes(self) -> dict:
        live = self._live()
        return {
            "co2": live.get("co2"),
            "voc": live.get("voc"),
            "reason": live.get("air_quality_reason"),
            "ventilation_active": live.get("ventilation_active", False),
        }
