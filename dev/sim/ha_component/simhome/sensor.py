"""Temperature and humidity sensors (rooms and outdoor)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from roommind_sim.sensors import SimSensor

from .const import DOMAIN
from .entity import SimEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    rt = hass.data[DOMAIN]
    add([SimSensorEntity(rt, s) for s in rt.world.sensors.values()])


class SimSensorEntity(SimEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, rt: Any, sensor: SimSensor) -> None:
        super().__init__(rt, sensor.entity_id, sensor.spec.name)
        self.sensor = sensor
        if sensor.spec.kind.endswith("humidity"):
            self._attr_device_class = SensorDeviceClass.HUMIDITY
            self._attr_native_unit_of_measurement = PERCENTAGE
        else:
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_suggested_display_precision = 1

    @property
    def available(self) -> bool:
        return self.rt.world.is_available(self.entity_id, self.now)

    @property
    def native_value(self) -> float | None:
        return self.sensor.value
