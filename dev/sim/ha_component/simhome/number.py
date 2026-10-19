"""Valve opening/closing degree of TRVs with direct valve control (Sonoff TRVZB via Zigbee2MQTT)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from roommind_sim.devices import SimDevice

from .const import DOMAIN
from .entity import SimEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    rt = hass.data[DOMAIN]
    add(
        [
            SimValveNumber(rt, dev, kind, eid)
            for dev in rt.world.devices.values()
            for kind, eid in dev.spec.valve_numbers().items()
        ]
    )


class SimValveNumber(SimEntity, NumberEntity):
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, rt: Any, dev: SimDevice, kind: str, entity_id: str) -> None:
        super().__init__(rt, entity_id, f"{dev.spec.name} valve {kind} degree")
        self.dev = dev
        self.kind = kind

    @property
    def available(self) -> bool:
        return self.dev.state(self.now) != "unavailable"

    @property
    def native_value(self) -> float | None:
        return getattr(self.dev, f"valve_{self.kind}_deg")

    async def async_set_native_value(self, value: float) -> None:
        result = self.rt.world.valve_call(self.entity_id, value, self.now)
        self.rt.log_command(self.entity_id, "set_value", {"value": value}, result.status)
        self.async_write_ha_state()
        if not result.ok:
            raise HomeAssistantError(f"{self.entity_id}: {result.reason}")
