"""Phones of simulated people (home / not_home) for person entities."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import ScannerEntity, SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import SimEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    rt = hass.data[DOMAIN]
    add([SimTracker(rt, p) for p in rt.world.people.values()])


class SimTracker(SimEntity, ScannerEntity):
    _attr_source_type = SourceType.ROUTER

    def __init__(self, rt: Any, person: Any) -> None:
        super().__init__(rt, person.spec.tracker, f"{person.spec.name} Phone")
        self.person = person

    @property
    def is_connected(self) -> bool:
        return self.person.home
