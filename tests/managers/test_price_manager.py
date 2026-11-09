"""Tests for the price manager (one price source per cycle)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.roommind.managers import price_manager
from custom_components.roommind.managers.price_manager import PriceManager
from custom_components.roommind.utils.price_utils import LEVEL_CHEAP, LEVEL_EXPENSIVE, MIN_HISTORY_HOURS

NOW = datetime(2026, 11, 9, 3, tzinfo=UTC).timestamp()
PATTERN = [20, 20, 20, 20, 20, 22, 30, 34, 30, 25, 24, 24, 24, 24, 24, 26, 30, 36, 38, 35, 28, 25, 22, 21]


def _state(state, attributes=None):
    return SimpleNamespace(state=state, attributes=attributes or {})


def _nordpool():
    day = datetime(2026, 11, 9, tzinfo=UTC)
    return {
        "raw_today": [
            {
                "start": (day + timedelta(hours=h)).isoformat(),
                "end": (day + timedelta(hours=h + 1)).isoformat(),
                "value": p,
            }
            for h, p in enumerate(PATTERN)
        ]
    }


@pytest.fixture
def clock(monkeypatch):
    now = {"t": NOW}
    monkeypatch.setattr(price_manager, "time", SimpleNamespace(time=lambda: now["t"]))
    return now


def _manager(states: dict):
    hass = MagicMock()
    hass.states.get = states.get
    return PriceManager(hass)


@pytest.mark.asyncio
async def test_no_source_no_signal(clock):
    manager = _manager({})
    assert await manager.async_update({}) is None
    assert manager.status() is None


@pytest.mark.asyncio
async def test_forecast_sensor(clock):
    manager = _manager({"sensor.price": _state("20", _nordpool())})
    signal = await manager.async_update({"price_entity": "sensor.price"})
    assert signal.current_level == LEVEL_CHEAP
    status = manager.status()
    assert status["kind"] == "forecast"
    assert status["readable"] is True
    assert status["forecast_hours"] == 21


@pytest.mark.asyncio
async def test_unreadable_source_is_reported(clock):
    manager = _manager({"sensor.price": _state("unavailable")})
    assert await manager.async_update({"price_entity": "sensor.price"}) is None
    assert manager.status() == {
        "entity_id": "sensor.price",
        "readable": False,
        "kind": None,
        "price": None,
        "level": None,
        "forecast_hours": 0,
        "history_hours": 0,
        "history_needed": MIN_HISTORY_HOURS,
    }
    missing = _manager({})
    await missing.async_update({"price_entity": "sensor.gone"})
    assert missing.status()["readable"] is False


@pytest.mark.asyncio
async def test_switch_source(clock):
    manager = _manager({"binary_sensor.pv_surplus": _state("on")})
    signal = await manager.async_update({"price_entity": "binary_sensor.pv_surplus"})
    assert signal.direction_at(NOW) == 1
    assert manager.status()["kind"] == "switch"


@pytest.mark.asyncio
async def test_sensor_without_forecast_is_seeded_from_the_history_once(clock):
    states = {"sensor.price": _state("38")}
    manager = _manager(states)
    history = [(NOW - (24 - h) * 3600, float(p)) for h, p in enumerate(PATTERN)]
    load = AsyncMock(return_value=history)
    signal = await manager.async_update({"price_entity": "sensor.price"}, load)
    assert signal.current_level == LEVEL_EXPENSIVE
    assert manager.status()["kind"] == "history"
    clock["t"] += 600
    await manager.async_update({"price_entity": "sensor.price"}, load)
    load.assert_awaited_once()


@pytest.mark.asyncio
async def test_observed_prices_are_sampled_and_trimmed(clock):
    states = {"sensor.price": _state("20")}
    manager = _manager(states)
    for _ in range(3):
        await manager.async_update({"price_entity": "sensor.price"})
        clock["t"] += 60
    assert len(manager._observed) == 1
    clock["t"] += 8 * 86400
    states["sensor.price"] = _state("x")
    await manager.async_update({"price_entity": "sensor.price"})
    states["sensor.price"] = _state("25")
    await manager.async_update({"price_entity": "sensor.price"})
    assert manager._observed == [(clock["t"], 25.0)]


@pytest.mark.asyncio
async def test_changing_the_source_forgets_what_was_seen(clock):
    manager = _manager({"sensor.a": _state("20"), "sensor.b": _state("30")})
    await manager.async_update({"price_entity": "sensor.a"})
    await manager.async_update({"price_entity": "sensor.b"})
    assert [p for _, p in manager._observed] == [30.0]
    await manager.async_update({"price_entity": ""})
    assert manager.signal is None


@pytest.mark.asyncio
async def test_a_flapping_switch_does_not_move_the_level(clock):
    states = {"binary_sensor.pv": _state("off")}
    manager = _manager(states)
    settings = {"price_entity": "binary_sensor.pv"}
    assert (await manager.async_update(settings)).current_level == "normal"
    for i in range(6):
        clock["t"] += 300
        states["binary_sensor.pv"] = _state("on" if i % 2 == 0 else "off")
        assert (await manager.async_update(settings)).current_level == "normal"
    states["binary_sensor.pv"] = _state("on")
    clock["t"] += 300
    assert (await manager.async_update(settings)).current_level == "normal"
    clock["t"] += price_manager.LEVEL_HOLD_S
    assert (await manager.async_update(settings)).current_level == "cheap"
