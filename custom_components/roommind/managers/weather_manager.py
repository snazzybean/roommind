"""Weather forecast manager for RoomMind."""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

from ..utils.sensor_utils import read_sensor_value
from ..utils.temp_utils import ha_temp_to_celsius

_LOGGER = logging.getLogger(__name__)

# Split sources for "My weather forecast doesn't include everything":
# forecast entry key -> global setting naming the entity that supplies it.
# The entity is either a weather.* entity (its hourly forecast carries the
# field) or a plain sensor (its current reading holds for the coming hours).
_SPLIT_FORECAST_FIELDS = {
    "temperature": "forecast_temp_entity",
    "cloud_coverage": "forecast_cloud_entity",
    "wind_speed": "forecast_wind_entity",
}


class WeatherManager:
    """Manages weather forecast retrieval and conversion."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._outdoor_forecast: list[dict] = []

    @property
    def forecast(self) -> list[dict]:
        """Return the current outdoor forecast."""
        return self._outdoor_forecast

    async def async_read_forecast(self, settings: dict) -> list[dict]:
        """Read weather forecast from configured weather entity.

        With ``weather_split_enabled``, each field first checks its own
        source (temperature, cloud coverage, wind); whatever it delivers
        overrides the main ``weather_entity`` field by field. Sources that
        are unset or carry nothing fall back to the main forecast, and the
        downstream fallback logic stays untouched.
        """
        base = await self._fetch_weather_forecast(settings.get("weather_entity", ""))
        if not settings.get("weather_split_enabled"):
            self._outdoor_forecast = base
            return base
        merged = list(base)
        for field, setting in _SPLIT_FORECAST_FIELDS.items():
            entity_id = settings.get(setting, "")
            if not entity_id:
                continue
            series = await self._read_field_series(entity_id, field)
            if series is None:
                continue
            merged = self._overlay(merged, series, field)
        self._outdoor_forecast = merged
        return merged

    async def _fetch_weather_forecast(self, weather_entity: str) -> list[dict]:
        """Hourly forecast entries of a weather entity, temperatures in Celsius.

        Returns an empty list when the entity is not configured or not
        available, and on total retrieval failure.
        """
        if not weather_entity:
            return []

        # Calling get_forecasts on a missing/unavailable entity makes HA core
        # log a warning (e.g. during startup before the weather integration
        # has loaded, see #326) — skip until the entity is available.
        entity_state = self.hass.states.get(weather_entity)
        if entity_state is None or entity_state.state in ("unavailable", "unknown"):
            _LOGGER.debug(
                "Weather entity %s not available, skipping forecast read",
                weather_entity,
            )
            return []

        # Modern approach: use weather.get_forecasts service (HA 2024.6+)
        try:
            response = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": weather_entity, "type": "hourly"},
                blocking=True,
                return_response=True,
            )
            entity_data = response.get(weather_entity, {}) if isinstance(response, dict) else {}  # type: ignore[union-attr]
            forecasts = entity_data.get("forecast", []) if isinstance(entity_data, dict) else []
            if isinstance(forecasts, list) and forecasts:
                return self._convert_forecast_temps(forecasts)  # type: ignore[arg-type]
        except Exception:  # noqa: BLE001
            _LOGGER.debug(
                "weather.get_forecasts service call failed for %s, falling back to state attributes",
                weather_entity,
            )

        # Fallback: read deprecated state attribute (older HA versions)
        state = self.hass.states.get(weather_entity)
        if state is None:
            return []
        forecast = state.attributes.get("forecast")
        if isinstance(forecast, list):
            return self._convert_forecast_temps(forecast)
        return []

    async def _read_field_series(self, entity_id: str, field: str) -> list[dict] | float | None:
        """Split-source values for one forecast field.

        A weather entity yields its forecast entries (aligned by their
        ``datetime`` downstream); any other entity yields a single scalar
        that holds flat across the horizon. ``None`` when the source
        carries nothing usable this cycle, which keeps the main forecast.
        """
        if entity_id.startswith("weather."):
            series = await self._fetch_weather_forecast(entity_id)
            return series or None
        raw = read_sensor_value(self.hass, entity_id, "global", field.replace("_", " "))
        if raw is None:
            return None
        if field == "temperature":
            converted = ha_temp_to_celsius(self.hass, raw, entity_id=entity_id)
            return converted if converted is not None else None
        return raw

    @staticmethod
    def _overlay(merged: list[dict], series: list[dict] | float, field: str) -> list[dict]:
        """Apply one split source's values onto the merged forecast list."""
        out = [dict(f) for f in merged]
        if isinstance(series, (int, float)):
            value = float(series)
            if not out:
                # No main forecast: a single flat entry, which consumers
                # expand and pad across the horizon.
                return [{field: value}]
            for entry in out:
                entry[field] = value
            return out
        if not series:
            return out
        if not out:
            # Main forecast unavailable: the split source carries the horizon.
            return [dict(f) for f in series]
        base_by_dt = {f.get("datetime"): f for f in out if f.get("datetime") is not None}
        aligns = bool(base_by_dt) and any(f.get("datetime") is not None for f in series)
        for i, entry in enumerate(series):
            entry_value = entry.get(field)
            if entry_value is None:
                continue
            if aligns:
                target = base_by_dt.get(entry.get("datetime"))
            elif i < len(out):
                target = out[i]
            else:
                continue
            if target is not None:
                target[field] = entry_value
        return out

    def resolve_current_cloud(self, settings: dict) -> float | None:
        """Current cloud coverage: split sensor → weather entity → None."""
        if settings.get("weather_split_enabled"):
            value = read_sensor_value(self.hass, settings.get("current_cloud_sensor"), "global", "cloud coverage")
            if value is not None:
                return value
        return self._current_weather_attribute(settings, "cloud_coverage")

    def resolve_current_wind(self, settings: dict) -> float | None:
        """Current wind speed from the split sensor.

        Placeholder until a control feature consumes wind: without
        ``weather_split_enabled`` nothing reads wind at all, so this stays
        the only wind source and is reported through diagnostics.
        """
        if not settings.get("weather_split_enabled"):
            return None
        return read_sensor_value(self.hass, settings.get("current_wind_sensor"), "global", "wind speed")

    def _current_weather_attribute(self, settings: dict, key: str) -> float | None:
        weather_entity = settings.get("weather_entity")
        if not weather_entity:
            return None
        state = self.hass.states.get(weather_entity)
        if state is None:
            return None
        value = state.attributes.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        return None

    def _convert_forecast_temps(self, forecasts: list[dict]) -> list[dict]:
        """Convert forecast temperatures from HA units to Celsius."""
        result = []
        for f in forecasts:
            if "temperature" in f:
                result.append({**f, "temperature": ha_temp_to_celsius(self.hass, f["temperature"])})
            else:
                result.append(f)
        return result

    @staticmethod
    def extract_cloud_series(forecast: list[dict]) -> list[float | None] | None:
        """Extract cloud_coverage values from forecast entries.

        Returns None if no cloud data is available (clear-sky fallback).
        """
        if not forecast:
            return None
        series: list[float | None] = []
        for entry in forecast:
            cc = entry.get("cloud_coverage")
            series.append(float(cc) if cc is not None else None)
        return series if any(v is not None for v in series) else None
