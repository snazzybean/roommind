"""Dehumidifiers and humidifiers as humidifier entities (device class from the model)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.humidifier import HumidifierAction, HumidifierDeviceClass, HumidifierEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from roommind_sim.appliances import SimAppliance

from .appliance import SimApplianceEntity
from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    rt = hass.data[DOMAIN]
    add([SimHumidifier(rt, a) for a in rt.world.appliances.values() if a.domain == "humidifier"])


class SimHumidifier(SimApplianceEntity, HumidifierEntity):
    def __init__(self, rt: Any, app: SimAppliance) -> None:
        super().__init__(rt, app)
        drying = app.model == "dehumidifier"
        self._attr_device_class = HumidifierDeviceClass.DEHUMIDIFIER if drying else HumidifierDeviceClass.HUMIDIFIER
        self._attr_min_humidity = app.min_humidity
        self._attr_max_humidity = app.max_humidity
        self._running_action = HumidifierAction.DRYING if drying else HumidifierAction.HUMIDIFYING

    @property
    def is_on(self) -> bool:
        return self.app.on

    @property
    def action(self) -> HumidifierAction | None:
        if not self.app.on:
            return HumidifierAction.OFF
        return self._running_action if self.app.running else HumidifierAction.IDLE

    @property
    def current_humidity(self) -> float | None:
        rh = self.app.current_rh
        return None if rh is None else round(rh)

    @property
    def target_humidity(self) -> float | None:
        return self.app.target_humidity

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._command("turn_on", {})

    async def async_set_humidity(self, humidity: int) -> None:
        self._command("set_humidity", {"humidity": humidity})
