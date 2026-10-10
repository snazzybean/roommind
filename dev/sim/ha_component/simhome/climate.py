"""Climate entities backed by simulated devices."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACAction, HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from roommind_sim.devices import SimDevice

from .const import DOMAIN
from .entity import SimEntity

_ACTIONS = {
    "heating": HVACAction.HEATING,
    "cooling": HVACAction.COOLING,
    "drying": HVACAction.DRYING,
    "fan": HVACAction.FAN,
    "idle": HVACAction.IDLE,
    "off": HVACAction.OFF,
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    rt = hass.data[DOMAIN]
    add([SimClimate(rt, dev) for dev in rt.world.devices.values()])


class SimClimate(SimEntity, ClimateEntity):
    def __init__(self, rt: Any, dev: SimDevice) -> None:
        super().__init__(rt, dev.entity_id, dev.spec.name)
        self.dev = dev
        self._attr_temperature_unit = UnitOfTemperature.FAHRENHEIT if dev.unit == "F" else UnitOfTemperature.CELSIUS
        self._attr_hvac_modes = [HVACMode(m) for m in dev.hvac_modes]
        self._attr_min_temp = dev.min_temp
        self._attr_max_temp = dev.max_temp
        self._attr_target_temperature_step = dev.step_size
        features = ClimateEntityFeature.TARGET_TEMPERATURE
        if dev.range_setpoint:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        if dev.fan_modes:
            features |= ClimateEntityFeature.FAN_MODE
            self._attr_fan_modes = dev.fan_modes
        if "off" in dev.hvac_modes:
            features |= ClimateEntityFeature.TURN_OFF | ClimateEntityFeature.TURN_ON
        self._attr_supported_features = features

    @property
    def available(self) -> bool:
        return self.dev.state(self.now) != "unavailable"

    @property
    def _attrs(self) -> dict[str, Any]:
        return self.dev.attributes(self.now)

    @property
    def hvac_mode(self) -> HVACMode | None:
        state = self.dev.state(self.now)
        if state == "unknown":
            return None
        return HVACMode(state) if state in self.dev.hvac_modes else None

    @property
    def hvac_action(self) -> HVACAction | None:
        action = self._attrs.get("hvac_action")
        return _ACTIONS.get(action) if action else None

    @property
    def current_temperature(self) -> float | None:
        return self._attrs.get("current_temperature")

    @property
    def target_temperature(self) -> float | None:
        return self._attrs.get("temperature")

    @property
    def target_temperature_low(self) -> float | None:
        return self._attrs.get("target_temp_low")

    @property
    def target_temperature_high(self) -> float | None:
        return self._attrs.get("target_temp_high")

    @property
    def fan_mode(self) -> str | None:
        return self._attrs.get("fan_mode")

    def _command(self, service: str, data: dict[str, Any]) -> None:
        result = self.rt.world.device_call(self.entity_id, service, data, self.now)
        self.rt.log_command(self.entity_id, service, data, result.status)
        self.async_write_ha_state()
        if not result.ok:
            raise HomeAssistantError(f"{self.entity_id}: {result.reason}")

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self._command("set_hvac_mode", {"hvac_mode": str(hvac_mode)})

    async def async_set_temperature(self, **kwargs: Any) -> None:
        data: dict[str, Any] = {}
        for key in (ATTR_TEMPERATURE, "target_temp_low", "target_temp_high", "hvac_mode"):
            if kwargs.get(key) is not None:
                data[key] = str(kwargs[key]) if key == "hvac_mode" else float(kwargs[key])
        self._command("set_temperature", data)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        self._command("set_fan_mode", {"fan_mode": fan_mode})

    async def async_turn_on(self) -> None:
        self._command("turn_on", {})

    async def async_turn_off(self) -> None:
        self._command("turn_off", {})
