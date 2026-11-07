"""Tests for tariff parsing and price-aware heating in the MPC path."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from custom_components.roommind.const import MODE_HEATING, MODE_IDLE, TargetTemps
from custom_components.roommind.control.electricity_tariff import (
    ElectricityTariff,
    PriceChange,
    PriceInterval,
    read_electricity_tariff,
)
from custom_components.roommind.control.mpc_controller import MPCController
from custom_components.roommind.control.thermal_model import RCModel, RoomModelManager

from .conftest import build_hass, make_room

NOW = datetime(2026, 11, 7, 16, 0, tzinfo=UTC).timestamp()


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat()


def _read_tariff(current: str, rows: object, forecast_state: str = "ready", forecast_unit: str = "EUR/kWh"):
    hass = build_hass()
    hass.states.get.side_effect = {
        "sensor.price": MagicMock(state=current, attributes={"unit_of_measurement": "EUR/kWh"}),
        "sensor.forecast": MagicMock(
            state=forecast_state, attributes={"prices": rows, "unit_of_measurement": forecast_unit}
        ),
    }.get
    return read_electricity_tariff(hass, "sensor.price", "sensor.forecast")


def test_read_accepts_current_plus_future_quarter_hours_and_negative_prices():
    tariff = _read_tariff(
        "-0.05",
        [
            {"start": _iso(NOW + 900), "end": _iso(NOW + 1800), "price": "0.28"},
            {"start": _iso(NOW), "end": _iso(NOW + 900), "price": -0.05},
            {"start": _iso(NOW + 1800), "end": _iso(NOW + 2700), "price": 0.3},
        ],
    )
    assert tariff is not None
    assert tariff.next_change(NOW, NOW + 7200) == PriceChange(NOW + 900, NOW + 2700, True)


@pytest.mark.parametrize(
    ("current", "rows", "forecast_state", "unit"),
    [
        ("nan", [], "ready", "EUR/kWh"),
        ("unknown", [], "ready", "EUR/kWh"),
        ("0.20", [], "unavailable", "EUR/kWh"),
        ("0.20", [], "ready", "cent/kWh"),
        ("0.20", None, "ready", "EUR/kWh"),
        (
            "0.20",
            [{"start": "2026-11-07T16:00:00", "end": _iso(NOW + 900), "price": 0.30}],
            "ready",
            "EUR/kWh",
        ),
        (
            "0.20",
            [
                {"start": _iso(NOW), "end": _iso(NOW + 900), "price": 0.20},
                {"start": _iso(NOW + 899), "end": _iso(NOW + 1800), "price": 0.30},
            ],
            "ready",
            "EUR/kWh",
        ),
    ],
)
def test_invalid_tariffs_fall_back(current, rows, forecast_state, unit):
    assert _read_tariff(current, rows, forecast_state, unit) is None


@pytest.mark.parametrize(
    "forecast",
    [
        (PriceInterval(NOW, NOW + 900, 0.3), PriceInterval(NOW + 900, NOW + 1800, 0.15)),
        (PriceInterval(NOW, NOW + 900, 0.2), PriceInterval(NOW + 901, NOW + 1800, 0.15)),
        (PriceInterval(NOW + 3601, NOW + 7200, 0.15),),
        (PriceInterval(NOW + 900, NOW + 1800, 0.21),),
    ],
)
def test_no_shift_for_mismatches_gaps_and_small_spreads(forecast):
    assert ElectricityTariff(0.2, forecast).next_change(NOW, NOW + 7200) is None


def test_next_hour_is_accepted_and_horizon_is_respected():
    tariff = ElectricityTariff(0.4, (PriceInterval(NOW + 3600, NOW + 7200, 0.2),))
    assert tariff.next_change(NOW, NOW + 1800) is None
    assert tariff.next_change(NOW, NOW + 5400) == PriceChange(NOW + 3600, NOW + 5400, False)


def _controller(hass, current, next_price, *, outdoor_temp=5.0, short_window=False, learned=True):
    model_manager = RoomModelManager()
    model_manager.get_prediction_std = MagicMock(return_value=0.1 if learned else 0.6)
    model_manager.get_mode_counts = MagicMock(return_value=(100, 40, 40))
    model_manager.get_model = MagicMock(return_value=RCModel(C=1.0, U=0.15, Q_heat=3.0, Q_cool=4.0))
    next_start = NOW + (300 if short_window else 900)
    targets = TargetTemps(heat=20.0, cool=None)
    return MPCController(
        hass,
        make_room(thermostats=[], acs=["climate.test"], climate_mode="heat_only"),
        model_manager=model_manager,
        outdoor_temp=outdoor_temp,
        target_resolver=lambda _: targets,
        electricity_tariff=ElectricityTariff(current, (PriceInterval(next_start, NOW + 3600, next_price),)),
    )


@pytest.mark.parametrize(
    ("current", "next_price", "temp", "expected_offset", "expected_mode"),
    [
        (0.15, 0.30, 20.0, 0.5, MODE_HEATING),
        (0.30, 0.15, 19.7, -0.5, MODE_IDLE),
        (0.30, 0.15, 19.4, 0.0, MODE_HEATING),
        (0.15, 0.30, 24.0, 0.0, MODE_IDLE),
    ],
)
@pytest.mark.asyncio
async def test_tariff_shifts_trained_mpc(monkeypatch, current, next_price, temp, expected_offset, expected_mode):
    monkeypatch.setattr("custom_components.roommind.control.mpc_controller.time.time", lambda: NOW)
    hass = build_hass()
    hass.states.get.return_value = MagicMock(
        state="heat", attributes={"hvac_modes": ["off", "heat"], "hvac_action": "idle"}
    )
    controller = _controller(hass, current, next_price)
    mode, _ = await controller.async_evaluate(temp, TargetTemps(heat=20.0, cool=None))

    assert controller.price_heat_offset == expected_offset
    assert mode == expected_mode
    if expected_offset > 0:
        assert controller.direct_target(mode, 20.0) == 20.5


@pytest.mark.parametrize("kwargs", [{"short_window": True}, {"learned": False}, {"outdoor_temp": None}])
@pytest.mark.asyncio
async def test_preheat_needs_a_long_enough_window_and_a_trained_model(monkeypatch, kwargs):
    monkeypatch.setattr("custom_components.roommind.control.mpc_controller.time.time", lambda: NOW)
    hass = build_hass()
    hass.states.get.return_value = MagicMock(state="heat", attributes={"hvac_modes": ["off", "heat"]})
    controller = _controller(hass, 0.15, 0.30, **kwargs)
    await controller.async_evaluate(20.0, TargetTemps(heat=20.0, cool=None))

    assert controller.price_heat_offset == 0.0
