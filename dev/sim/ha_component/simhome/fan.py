"""Exhaust and room fans as fan entities."""

from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from roommind_sim.appliances import SimAppliance

from .appliance import SimApplianceEntity
from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    rt = hass.data[DOMAIN]
    add([SimFan(rt, a) for a in rt.world.appliances.values() if a.domain == "fan"])


class SimFan(SimApplianceEntity, FanEntity):
    def __init__(self, rt: Any, app: SimAppliance) -> None:
        super().__init__(rt, app)
        features = FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
        if app.speed_count:
            features |= FanEntityFeature.SET_SPEED
            self._attr_speed_count = app.speed_count
        self._attr_supported_features = features

    @property
    def is_on(self) -> bool:
        return self.app.on

    @property
    def percentage(self) -> int | None:
        if not self.app.speed_count:
            return None
        return self.app.percentage if self.app.on else 0

    async def async_turn_on(self, percentage: int | None = None, preset_mode: str | None = None, **kwargs: Any) -> None:
        self._command("turn_on", {} if percentage is None else {"percentage": percentage})

    async def async_set_percentage(self, percentage: int) -> None:
        self._command("set_percentage", {"percentage": percentage})
