"""Weather entity with hourly/daily forecasts from the deterministic weather model."""

from __future__ import annotations

from typing import Any

from homeassistant.components.weather import Forecast, WeatherEntity, WeatherEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfSpeed, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import SimEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    rt = hass.data[DOMAIN]
    ent = SimWeather(rt, rt.scn.weather.get("entity_id", "weather.simhome"), rt.scn.weather.get("name", "Sim Weather"))
    rt.extra_entities.append(ent)
    add([ent])


class SimWeather(SimEntity, WeatherEntity):
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_supported_features = WeatherEntityFeature.FORECAST_HOURLY | WeatherEntityFeature.FORECAST_DAILY

    @property
    def available(self) -> bool:
        delay = float(self.rt.scn.weather.get("unavailable_after_start_s", 0))
        return self.now - self.rt.world.boot_time >= delay

    @property
    def _out(self) -> Any:
        return self.rt.world.outdoor

    @property
    def native_temperature(self) -> float:
        return round(self._out.temp_c, 1)

    @property
    def humidity(self) -> float:
        return round(self._out.rh)

    @property
    def cloud_coverage(self) -> int:
        return round(self._out.cloud_pct)

    @property
    def native_wind_speed(self) -> float:
        return round(self._out.wind_kmh, 1)

    @property
    def condition(self) -> str:
        return self._out.condition

    def _forecast(self, kind: str) -> list[Forecast] | None:
        weather = self.rt.world.weather
        if not weather.forecast_available:
            return None
        out: list[Forecast] = []
        for f in weather.forecast(self.now, kind):
            item: dict[str, Any] = {
                "datetime": f["datetime"],
                "native_temperature": f["temperature"],
                "humidity": f["humidity"],
                "cloud_coverage": f["cloud_coverage"],
                "condition": f["condition"],
                "native_wind_speed": f["wind_speed"],
            }
            if "templow" in f:
                item["native_templow"] = f["templow"]
            out.append(Forecast(**item))  # type: ignore[typeddict-item]
        return out

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        return self._forecast("hourly")

    async def async_forecast_daily(self) -> list[Forecast] | None:
        return self._forecast("daily")
