"""Tests for the electricity price signal."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.roommind.const import TargetTemps
from custom_components.roommind.utils.price_utils import (
    LEVEL_CHEAP,
    LEVEL_EXPENSIVE,
    LEVEL_NORMAL,
    PRICE_LOOKAHEAD_H,
    PriceSlot,
    apply_price_shift,
    hourly,
    hourly_history,
    level_of,
    parse_price_forecast,
    price_thresholds,
    signal_from_state,
)

DAY = datetime(2026, 11, 9, tzinfo=UTC)
T0 = DAY.timestamp()
# Cheap night, expensive morning and evening
PATTERN = [20, 20, 20, 20, 20, 22, 30, 34, 30, 25, 24, 24, 24, 24, 24, 26, 30, 36, 38, 35, 28, 25, 22, 21]


def _nordpool(pattern=PATTERN, minutes=60):
    step = timedelta(minutes=minutes)
    out = []
    for i, price in enumerate(pattern):
        start = DAY + step * i
        out.append({"start": start.isoformat(), "end": (start + step).isoformat(), "value": price})
    return {"raw_today": out}


def test_parses_the_common_shapes():
    start = DAY.isoformat()
    shapes = [
        {"raw_today": [{"start": start, "end": (DAY + timedelta(hours=1)).isoformat(), "value": 10}]},
        {"data": [{"start_time": start, "end_time": (DAY + timedelta(hours=1)).isoformat(), "price_per_kwh": 10}]},
        {"prices": [{"time": start, "price": 10}, {"time": (DAY + timedelta(hours=1)).isoformat(), "price": 12}]},
        {"rates": [{"start": DAY, "end": DAY + timedelta(hours=1), "value_inc_vat": 10}]},
        {"forecast": [{"startsAt": int(T0 * 1000), "total": 10}]},
    ]
    for attrs in shapes:
        slots = parse_price_forecast(attrs)
        assert slots[0] == PriceSlot(T0, T0 + 3600, 10.0), attrs


def test_parse_merges_today_and_tomorrow_and_skips_junk():
    attrs = {
        "raw_today": [{"start": DAY.isoformat(), "value": 10}, {"start": "nonsense", "value": 3}, "x"],
        "raw_tomorrow": [{"start": (DAY + timedelta(hours=1)).isoformat(), "value": None}],
        "unrelated": [{"start": DAY.isoformat(), "value": 99}],
    }
    assert parse_price_forecast(attrs) == [PriceSlot(T0, T0 + 3600, 10.0)]


def test_quarter_hours_become_hourly_means():
    slots = parse_price_forecast(_nordpool([10, 20, 30, 40, 50, 50, 50, 50], minutes=15))
    assert hourly(slots) == [PriceSlot(T0, T0 + 3600, 25.0), PriceSlot(T0 + 3600, T0 + 7200, 50.0)]


def test_flat_tariff_has_no_levels():
    assert price_thresholds([25.0] * 24) is None
    assert price_thresholds([25.0, 25.5, 26.0] * 8) is None
    assert price_thresholds([1.0, 2.0]) is None


def test_negative_prices_rank_fine():
    thresholds = price_thresholds([-5.0, -1.0, 0.0, 2.0, 8.0, 12.0])
    assert level_of(-1.0, thresholds) == LEVEL_CHEAP
    assert level_of(12.0, thresholds) == LEVEL_EXPENSIVE


def test_signal_with_forecast_charges_only_before_an_expensive_stretch():
    signal = signal_from_state("sensor", "20", _nordpool(), T0 + 3 * 3600)
    assert signal.current_level == LEVEL_CHEAP
    assert signal.has_forecast
    # 03:00 cheap, expensive at 07:00 within the lookahead -> charge
    assert signal.direction_at(T0 + 3 * 3600) == 1
    # 00:00 cheap, the next expensive hour is 7 h away
    assert PRICE_LOOKAHEAD_H < 7
    assert signal.direction_at(T0) == 0
    # 18:00 expensive -> coast
    assert signal.level_at(T0 + 18 * 3600) == LEVEL_EXPENSIVE
    assert signal.direction_at(T0 + 18 * 3600) == -1
    # 12:00 normal
    assert signal.direction_at(T0 + 12 * 3600) == 0
    # Beyond the forecast nothing is known
    assert signal.level_at(T0 + 30 * 3600) is None


def test_signal_from_a_switch():
    assert signal_from_state("binary_sensor", "on", {}, T0).direction_at(T0) == 1
    assert signal_from_state("input_boolean", "off", {}, T0).direction_at(T0) == 0
    assert signal_from_state("binary_sensor", "unavailable", {}, T0) is None


def test_signal_without_forecast_ranks_against_history():
    history = [(T0 - (24 - h) * 3600, float(p)) for h, p in enumerate(PATTERN)]
    expensive = signal_from_state("sensor", "38", {}, T0, history)
    assert expensive.current_level == LEVEL_EXPENSIVE
    assert expensive.direction_at(T0) == -1
    assert expensive.direction_at(T0 + 7200) == 0
    assert signal_from_state("sensor", "26", {}, T0, history).current_level == LEVEL_NORMAL
    # Too little history: level unknown, nothing shifts
    short = signal_from_state("sensor", "38", {}, T0, history[:5])
    assert short.current_level is None
    assert short.direction_at(T0) == 0
    assert signal_from_state("sensor", "abc", {}, T0) is None


def test_hourly_history_means():
    assert hourly_history([(T0, 10.0), (T0 + 1800, 20.0), (T0 + 3600, 5.0)]) == [(T0, 15.0), (T0 + 3600, 5.0)]


@pytest.mark.parametrize(
    ("targets", "direction", "expected"),
    [
        (TargetTemps(21.0, 24.0), 1, TargetTemps(22.0, 23.0)),
        (TargetTemps(21.0, 24.0), -1, TargetTemps(20.0, 25.0)),
        (TargetTemps(21.0, 24.0), 0, TargetTemps(21.0, 24.0)),
        # Narrow band: charging meets in the middle, never crosses
        (TargetTemps(21.0, 22.0), 1, TargetTemps(21.5, 21.5)),
        (TargetTemps(21.0, None), 1, TargetTemps(22.0, None)),
        (TargetTemps(None, 24.0), -1, TargetTemps(None, 25.0)),
        (TargetTemps(None, None), 1, TargetTemps(None, None)),
        (TargetTemps(5.5, None), -1, TargetTemps(5.0, None)),
    ],
)
def test_apply_price_shift(targets, direction, expected):
    assert apply_price_shift(targets, direction, 1.0) == expected


def test_no_shift_without_amount():
    assert apply_price_shift(TargetTemps(21.0, 24.0), 1, 0.0) == TargetTemps(21.0, 24.0)
