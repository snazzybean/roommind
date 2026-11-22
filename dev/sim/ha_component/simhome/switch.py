"""Appliances on a smart plug or relay as switch entities."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from roommind_sim.appliances import SimAppliance

from .appliance import SimApplianceEntity
from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    rt = hass.data[DOMAIN]
    add([SimSwitch(rt, a) for a in rt.world.appliances.values() if a.domain == "switch"])


class SimSwitch(SimApplianceEntity, SwitchEntity):
    _attr_device_class = SwitchDeviceClass.OUTLET

    def __init__(self, rt: Any, app: SimAppliance) -> None:
        super().__init__(rt, app)

    @property
    def is_on(self) -> bool:
        return self.app.on

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"current_power_w": round(self.app.electric_w, 1)}

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._command("turn_on", {})
