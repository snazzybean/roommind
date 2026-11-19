"""Tests for WeatherManager."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import UnitOfTemperature

from custom_components.roommind.managers.weather_manager import WeatherManager


def _make_hass(fahrenheit: bool = False) -> MagicMock:
    hass = MagicMock()
    hass.config.units.temperature_unit = UnitOfTemperature.FAHRENHEIT if fahrenheit else UnitOfTemperature.CELSIUS
    hass.states.get = MagicMock(return_value=None)
    return hass


def _make_available_state() -> MagicMock:
    state = MagicMock()
    state.state = "cloudy"
    return state


def _make_sensor_state(value: Any, unit: str | None = None) -> MagicMock:
    state = MagicMock()
    state.state = str(value)
    state.attributes = {"unit_of_measurement": unit} if unit else {}
    return state


def _make_hass_with_states(states: dict[str, MagicMock], fahrenheit: bool = False) -> MagicMock:
    hass = _make_hass(fahrenheit)
    hass.states.get = MagicMock(side_effect=states.get)
    return hass


def _make_forecast_service(responses: dict[str, list[dict]]) -> AsyncMock:
    """get_forecasts mock returning per-entity hourly forecasts."""

    async def _call(_domain: str, _service: str, data: dict, **_kwargs: Any) -> dict:
        entity_id = data["entity_id"]
        forecast = responses.get(entity_id)
        return {entity_id: {"forecast": forecast}} if forecast is not None else {}

    return AsyncMock(side_effect=_call)


@pytest.mark.asyncio
async def test_no_weather_entity_returns_empty():
    """When no weather_entity is configured, forecast is empty."""
    mgr = WeatherManager(_make_hass())
    result = await mgr.async_read_forecast({})
    assert result == []
    assert mgr.forecast == []


@pytest.mark.asyncio
async def test_forecast_entry_without_temperature():
    """Forecast entry without 'temperature' key is passed through unchanged."""
    hass = _make_hass()
    hass.states.get = MagicMock(return_value=_make_available_state())
    hass.services.async_call = AsyncMock(
        return_value={
            "weather.home": {
                "forecast": [
                    {"temperature": 10.0, "cloud_coverage": 50},
                    {"cloud_coverage": 80},  # no temperature key
                ]
            }
        }
    )

    mgr = WeatherManager(hass)
    result = await mgr.async_read_forecast({"weather_entity": "weather.home"})

    assert len(result) == 2
    assert result[0]["temperature"] == 10.0
    # Second entry has no temperature, should be passed through as-is
    assert "temperature" not in result[1]
    assert result[1]["cloud_coverage"] == 80


# --- extract_cloud_series ---


def test_extract_cloud_series_with_valid_data():
    """Forecast entries with cloud_coverage return list of floats."""
    forecast = [
        {"cloud_coverage": 20},
        {"cloud_coverage": 80},
        {"cloud_coverage": 50},
    ]
    result = WeatherManager.extract_cloud_series(forecast)
    assert result == [20.0, 80.0, 50.0]


def test_extract_cloud_series_empty_forecast():
    """Empty forecast list returns None."""
    result = WeatherManager.extract_cloud_series([])
    assert result is None


def test_extract_cloud_series_missing_key():
    """Entries without cloud_coverage key produce None in the series."""
    forecast = [
        {"cloud_coverage": 30},
        {"temperature": 10},  # no cloud_coverage
        {"cloud_coverage": 70},
    ]
    result = WeatherManager.extract_cloud_series(forecast)
    assert result == [30.0, None, 70.0]


def test_extract_cloud_series_all_missing_returns_none():
    """If no entry has cloud_coverage, returns None (clear-sky fallback)."""
    forecast = [
        {"temperature": 10},
        {"temperature": 12},
    ]
    result = WeatherManager.extract_cloud_series(forecast)
    assert result is None


@pytest.mark.asyncio
async def test_service_response_parsed_and_stored():
    """Successful get_forecasts service call returns converted forecast."""
    hass = _make_hass()
    hass.states.get = MagicMock(return_value=_make_available_state())
    hass.services.async_call = AsyncMock(
        return_value={"weather.home": {"forecast": [{"temperature": 10.0}, {"temperature": 12.0}]}}
    )

    mgr = WeatherManager(hass)
    result = await mgr.async_read_forecast({"weather_entity": "weather.home"})

    assert len(result) == 2
    assert result[0]["temperature"] == 10.0
    assert mgr.forecast == result


@pytest.mark.asyncio
async def test_service_response_converts_fahrenheit():
    """Forecast temperatures are converted from °F to °C when HA uses Fahrenheit."""
    hass = _make_hass(fahrenheit=True)
    hass.states.get = MagicMock(return_value=_make_available_state())
    hass.services.async_call = AsyncMock(
        return_value={
            "weather.home": {"forecast": [{"temperature": 50.0}]}  # 50°F = 10°C
        }
    )

    mgr = WeatherManager(hass)
    result = await mgr.async_read_forecast({"weather_entity": "weather.home"})

    assert abs(result[0]["temperature"] - 10.0) < 0.01


@pytest.mark.asyncio
async def test_service_failure_falls_back_to_state_attributes():
    """If get_forecasts service fails, falls back to state attributes."""
    hass = _make_hass()
    hass.services.async_call = AsyncMock(side_effect=Exception("service unavailable"))

    state = MagicMock()
    state.attributes = {"forecast": [{"temperature": 8.0}]}
    hass.states.get = MagicMock(return_value=state)

    mgr = WeatherManager(hass)
    result = await mgr.async_read_forecast({"weather_entity": "weather.home"})

    assert len(result) == 1
    assert result[0]["temperature"] == 8.0


@pytest.mark.asyncio
async def test_service_failure_no_state_returns_empty():
    """If service fails and state is unavailable, returns empty list."""
    hass = _make_hass()
    hass.services.async_call = AsyncMock(side_effect=Exception("unavailable"))
    hass.states.get = MagicMock(side_effect=[_make_available_state(), None])

    mgr = WeatherManager(hass)
    result = await mgr.async_read_forecast({"weather_entity": "weather.home"})

    assert result == []


@pytest.mark.asyncio
async def test_entity_missing_skips_service_call():
    """No state for the weather entity yet (e.g. HA startup) skips the service call (#326)."""
    hass = _make_hass()
    hass.services.async_call = AsyncMock()

    mgr = WeatherManager(hass)
    result = await mgr.async_read_forecast({"weather_entity": "weather.home"})

    assert result == []
    assert mgr.forecast == []
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_entity_unavailable_skips_service_call():
    """Unavailable weather entity skips the service call (#326)."""
    hass = _make_hass()
    hass.services.async_call = AsyncMock()
    state = MagicMock()
    state.state = "unavailable"
    hass.states.get = MagicMock(return_value=state)

    mgr = WeatherManager(hass)
    result = await mgr.async_read_forecast({"weather_entity": "weather.home"})

    assert result == []
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_entity_unknown_skips_service_call():
    """Weather entity in unknown state skips the service call (#326)."""
    hass = _make_hass()
    hass.services.async_call = AsyncMock()
    state = MagicMock()
    state.state = "unknown"
    hass.states.get = MagicMock(return_value=state)

    mgr = WeatherManager(hass)
    result = await mgr.async_read_forecast({"weather_entity": "weather.home"})

    assert result == []
    hass.services.async_call.assert_not_called()


# --- split forecast sources (weather_split_enabled) ---


@pytest.mark.asyncio
async def test_split_disabled_ignores_split_entities():
    """With the toggle off, split settings are not consulted at all."""
    hass = _make_hass_with_states(
        {
            "weather.home": _make_available_state(),
            "weather.other": _make_available_state(),
        }
    )
    hass.services.async_call = _make_forecast_service(
        {
            "weather.home": [{"temperature": 10.0, "datetime": "A"}],
            "weather.other": [{"temperature": 3.0, "datetime": "A"}],
        }
    )

    mgr = WeatherManager(hass)
    result = await mgr.async_read_forecast({"weather_entity": "weather.home", "forecast_temp_entity": "weather.other"})

    assert result[0]["temperature"] == 10.0


@pytest.mark.asyncio
async def test_split_weather_entity_overrides_field_by_field():
    """A split weather entity replaces only its field; other fields keep the main forecast."""
    hass = _make_hass_with_states(
        {
            "weather.home": _make_available_state(),
            "weather.cold": _make_available_state(),
        }
    )
    hass.services.async_call = _make_forecast_service(
        {
            "weather.home": [
                {"temperature": 10.0, "cloud_coverage": 50, "datetime": "2026-11-19T10:00:00+00:00"},
                {"temperature": 12.0, "cloud_coverage": 60, "datetime": "2026-11-19T11:00:00+00:00"},
            ],
            "weather.cold": [
                {"temperature": 3.0, "datetime": "2026-11-19T10:00:00+00:00"},
                {"temperature": 4.0, "datetime": "2026-11-19T11:00:00+00:00"},
            ],
        }
    )

    mgr = WeatherManager(hass)
    result = await mgr.async_read_forecast(
        {
            "weather_entity": "weather.home",
            "weather_split_enabled": True,
            "forecast_temp_entity": "weather.cold",
        }
    )

    assert [f["temperature"] for f in result] == [3.0, 4.0]
    assert [f["cloud_coverage"] for f in result] == [50, 60]


@pytest.mark.asyncio
async def test_split_weather_entity_datetime_alignment():
    """Split values land on the matching hour, not on list position."""
    hass = _make_hass_with_states(
        {
            "weather.home": _make_available_state(),
            "weather.other": _make_available_state(),
        }
    )
    hass.services.async_call = _make_forecast_service(
        {
            "weather.home": [
                {"cloud_coverage": 10, "datetime": "2026-11-19T10:00:00+00:00"},
                {"cloud_coverage": 20, "datetime": "2026-11-19T11:00:00+00:00"},
            ],
            "weather.other": [
                # Shifted by one hour: 09:00 has no counterpart and is skipped.
                {"cloud_coverage": 99, "datetime": "2026-11-19T09:00:00+00:00"},
                {"cloud_coverage": 70, "datetime": "2026-11-19T10:00:00+00:00"},
            ],
        }
    )

    mgr = WeatherManager(hass)
    result = await mgr.async_read_forecast(
        {
            "weather_entity": "weather.home",
            "weather_split_enabled": True,
            "forecast_cloud_entity": "weather.other",
        }
    )

    assert result[0]["cloud_coverage"] == 70  # 10:00 ← split 10:00
    assert result[1]["cloud_coverage"] == 20  # 11:00 kept from main


@pytest.mark.asyncio
async def test_split_sensor_flatlines_cloud_onto_main_entries():
    """A plain sensor holds its current value across every forecast hour."""
    hass = _make_hass_with_states(
        {
            "weather.home": _make_available_state(),
            "sensor.cloud": _make_sensor_state(90),
        }
    )
    hass.services.async_call = _make_forecast_service({"weather.home": [{"temperature": 10.0}, {"temperature": 12.0}]})

    mgr = WeatherManager(hass)
    result = await mgr.async_read_forecast(
        {
            "weather_entity": "weather.home",
            "weather_split_enabled": True,
            "forecast_cloud_entity": "sensor.cloud",
        }
    )

    assert WeatherManager.extract_cloud_series(result) == [90.0, 90.0]
    assert [f["temperature"] for f in result] == [10.0, 12.0]


@pytest.mark.asyncio
async def test_split_sensor_only_without_main_forecast():
    """Without a main weather entity, a sensor still yields a usable (flat) forecast."""
    hass = _make_hass_with_states({"sensor.temp_out": _make_sensor_state(7.5)})

    mgr = WeatherManager(hass)
    result = await mgr.async_read_forecast({"weather_split_enabled": True, "forecast_temp_entity": "sensor.temp_out"})

    assert result == [{"temperature": 7.5}]


@pytest.mark.asyncio
async def test_split_sensor_temperature_converts_fahrenheit():
    """A °F split sensor is converted to Celsius like every other temperature source."""
    hass = _make_hass_with_states(
        {
            "weather.home": _make_available_state(),
            "sensor.temp_out": _make_sensor_state(50.0, "°F"),
        },
        fahrenheit=True,
    )
    hass.services.async_call = _make_forecast_service({"weather.home": [{"cloud_coverage": 10}]})

    mgr = WeatherManager(hass)
    result = await mgr.async_read_forecast(
        {
            "weather_entity": "weather.home",
            "weather_split_enabled": True,
            "forecast_temp_entity": "sensor.temp_out",
        }
    )

    assert abs(result[0]["temperature"] - 10.0) < 0.01


@pytest.mark.asyncio
async def test_split_wind_lands_in_forecast_entries():
    """Wind forecast entries carry wind_speed for the future MPC consumer."""
    hass = _make_hass_with_states(
        {
            "weather.home": _make_available_state(),
            "weather.windy": _make_available_state(),
        }
    )
    hass.services.async_call = _make_forecast_service(
        {
            "weather.home": [{"temperature": 8.0}],
            "weather.windy": [{"temperature": 99.0, "wind_speed": 14.0}],
        }
    )

    mgr = WeatherManager(hass)
    result = await mgr.async_read_forecast(
        {
            "weather_entity": "weather.home",
            "weather_split_enabled": True,
            "forecast_wind_entity": "weather.windy",
        }
    )

    assert result[0]["wind_speed"] == 14.0
    assert result[0]["temperature"] == 8.0  # wind source must not bleed its temperature in


@pytest.mark.asyncio
async def test_split_unavailable_source_falls_back_to_main():
    """An unavailable split entity keeps the main forecast untouched."""
    unavailable = MagicMock(state="unavailable", attributes={})
    hass = _make_hass_with_states(
        {
            "weather.home": _make_available_state(),
            "sensor.cloud": unavailable,
        }
    )
    hass.services.async_call = _make_forecast_service({"weather.home": [{"temperature": 10.0, "cloud_coverage": 40}]})

    mgr = WeatherManager(hass)
    result = await mgr.async_read_forecast(
        {
            "weather_entity": "weather.home",
            "weather_split_enabled": True,
            "forecast_cloud_entity": "sensor.cloud",
        }
    )

    assert result[0]["cloud_coverage"] == 40


# --- resolve_current_cloud / resolve_current_wind ---


def test_resolve_current_cloud_split_sensor_priority():
    hass = _make_hass_with_states(
        {
            "weather.home": MagicMock(state="cloudy", attributes={"cloud_coverage": 30}),
            "sensor.cloud": _make_sensor_state(85),
        }
    )
    mgr = WeatherManager(hass)
    value = mgr.resolve_current_cloud(
        {"weather_entity": "weather.home", "weather_split_enabled": True, "current_cloud_sensor": "sensor.cloud"}
    )
    assert value == 85.0


def test_resolve_current_cloud_falls_back_to_weather_attribute():
    hass = _make_hass_with_states(
        {
            "weather.home": MagicMock(state="cloudy", attributes={"cloud_coverage": 30}),
        }
    )
    mgr = WeatherManager(hass)
    value = mgr.resolve_current_cloud(
        {"weather_entity": "weather.home", "weather_split_enabled": True, "current_cloud_sensor": "sensor.gone"}
    )
    assert value == 30


def test_resolve_current_cloud_split_disabled_ignores_sensor():
    hass = _make_hass_with_states(
        {
            "weather.home": MagicMock(state="cloudy", attributes={"cloud_coverage": 30}),
            "sensor.cloud": _make_sensor_state(85),
        }
    )
    mgr = WeatherManager(hass)
    value = mgr.resolve_current_cloud({"weather_entity": "weather.home", "current_cloud_sensor": "sensor.cloud"})
    assert value == 30


def test_resolve_current_wind_requires_split_toggle():
    hass = _make_hass_with_states({"sensor.wind": _make_sensor_state(12)})
    mgr = WeatherManager(hass)
    assert mgr.resolve_current_wind({"current_wind_sensor": "sensor.wind"}) is None
    assert mgr.resolve_current_wind({"weather_split_enabled": True, "current_wind_sensor": "sensor.wind"}) == 12.0
