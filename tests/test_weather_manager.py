"""Tests for WeatherManager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from homeassistant.const import UnitOfTemperature

from custom_components.roommind.managers.weather_manager import WeatherManager


def _make_hass(fahrenheit: bool = False) -> MagicMock:
    hass = MagicMock()
    hass.config.units.temperature_unit = (
        UnitOfTemperature.FAHRENHEIT if fahrenheit else UnitOfTemperature.CELSIUS
    )
    hass.states.get = MagicMock(return_value=None)
    return hass


@pytest.mark.asyncio
async def test_no_weather_entity_returns_empty():
    """When no weather_entity is configured, forecast is empty."""
    mgr = WeatherManager(_make_hass())
    result = await mgr.async_read_forecast({})
    assert result == []
    assert mgr.forecast == []


@pytest.mark.asyncio
async def test_service_response_parsed_and_stored():
    """Successful get_forecasts service call returns converted forecast."""
    hass = _make_hass()
    hass.services.async_call = AsyncMock(return_value={
        "weather.home": {"forecast": [{"temperature": 10.0}, {"temperature": 12.0}]}
    })

    mgr = WeatherManager(hass)
    result = await mgr.async_read_forecast({"weather_entity": "weather.home"})

    assert len(result) == 2
    assert result[0]["temperature"] == 10.0
    assert mgr.forecast == result


@pytest.mark.asyncio
async def test_service_response_converts_fahrenheit():
    """Forecast temperatures are converted from °F to °C when HA uses Fahrenheit."""
    hass = _make_hass(fahrenheit=True)
    hass.services.async_call = AsyncMock(return_value={
        "weather.home": {"forecast": [{"temperature": 50.0}]}  # 50°F = 10°C
    })

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
    hass.states.get = MagicMock(return_value=None)

    mgr = WeatherManager(hass)
    result = await mgr.async_read_forecast({"weather_entity": "weather.home"})

    assert result == []
