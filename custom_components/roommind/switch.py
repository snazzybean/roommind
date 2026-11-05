"""Switch platform for RoomMind."""

from __future__ import annotations

import time
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, HEATING_SYSTEM_RADIATOR, VACATION_SENTINEL_UNTIL
from .coordinator import RoomMindCoordinator
from .utils.area_utils import rooms_with_area


def _create_room_switches(
    coordinator: RoomMindCoordinator,
    area_id: str,
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

    # Global vacation switch (always created)
    entities: list[SwitchEntity] = [RoomMindVacationSwitch(coordinator)]

    rooms = rooms_with_area(hass, store.get_rooms())
    for area_id, room in rooms.items():
        entities.append(RoomMindClimateControlSwitch(coordinator, area_id))
        coordinator._climate_control_switch_areas.add(area_id)
        if room.get("heating_system_type", "") == HEATING_SYSTEM_RADIATOR:
            entities.append(RoomMindResidualHeatSwitch(coordinator, area_id))
            coordinator._residual_switch_areas.add(area_id)
        if room.get("covers"):
            entities.extend(_create_room_switches(coordinator, area_id))
            coordinator._switch_entity_areas.add(area_id)

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

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable automatic cover control."""
        store = self.coordinator.hass.data[DOMAIN]["store"]
        await store.async_update_room(self._area_id, {"covers_auto_enabled": True})
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable automatic cover control."""
        store = self.coordinator.hass.data[DOMAIN]["store"]
        await store.async_update_room(self._area_id, {"covers_auto_enabled": False})
        await self.coordinator.async_request_refresh()


class RoomMindClimateControlSwitch(CoordinatorEntity, SwitchEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator)
        self._area_id = area_id
        self._attr_unique_id = f"{DOMAIN}_{area_id}_climate_control"
        self._attr_name = f"{area_id} Climate Control"
        self._attr_icon = "mdi:thermostat"
        self.entity_id = f"switch.{DOMAIN}_{area_id}_climate_control"

    @property
    def is_on(self) -> bool:
        store = self.coordinator.hass.data[DOMAIN]["store"]
        room = store.get_room(self._area_id)
        return bool(room.get("climate_control_enabled", True)) if room else True

    async def async_turn_on(self, **kwargs: Any) -> None:
        store = self.coordinator.hass.data[DOMAIN]["store"]
        await store.async_update_room(self._area_id, {"climate_control_enabled": True})
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        store = self.coordinator.hass.data[DOMAIN]["store"]
        await store.async_update_room(self._area_id, {"climate_control_enabled": False})
        await self.coordinator.async_request_refresh()


class RoomMindResidualHeatSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to have control consider the radiators' residual heat (radiator rooms only).

    Off: the controller and the analytics prediction ignore the afterglow, so a run
    is no longer stopped early on it. The thermal model keeps learning with it.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator)
        self._area_id = area_id
        self._attr_unique_id = f"{DOMAIN}_{area_id}_residual_heat"
        self._attr_name = f"{area_id} Residual Heat"
        self._attr_icon = "mdi:radiator"
        self.entity_id = f"switch.{DOMAIN}_{area_id}_residual_heat"

    @property
    def is_on(self) -> bool:
        """Return True if control considers the residual heat."""
        store = self.coordinator.hass.data[DOMAIN]["store"]
        room = store.get_room(self._area_id)
        return bool(room.get("residual_heat_enabled", True)) if room else True

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Consider the residual heat in control."""
        store = self.coordinator.hass.data[DOMAIN]["store"]
        await store.async_update_room(self._area_id, {"residual_heat_enabled": True})
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Ignore the residual heat in control."""
        store = self.coordinator.hass.data[DOMAIN]["store"]
        await store.async_update_room(self._area_id, {"residual_heat_enabled": False})
        await self.coordinator.async_request_refresh()


class RoomMindVacationSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to toggle vacation mode globally."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: RoomMindCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_vacation"
        self._attr_name = "Vacation Mode"
        self._attr_icon = "mdi:beach"
        self.entity_id = f"switch.{DOMAIN}_vacation"

    @property
    def is_on(self) -> bool:
        """Return True if vacation mode is active."""
        store = self.coordinator.hass.data[DOMAIN]["store"]
        settings = store.get_settings()
        vacation_until = settings.get("vacation_until")
        return bool(vacation_until is not None and time.time() < vacation_until)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Activate vacation mode with stored temp, no end date."""
        store = self.coordinator.hass.data[DOMAIN]["store"]
        settings = store.get_settings()
        temp = settings.get("vacation_temp", 15.0)
        await store.async_save_settings(
            {
                "vacation_temp": temp,
                "vacation_until": VACATION_SENTINEL_UNTIL,
            }
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Deactivate vacation mode."""
        store = self.coordinator.hass.data[DOMAIN]["store"]
        await store.async_save_settings({"vacation_until": None})
        await self.coordinator.async_request_refresh()
