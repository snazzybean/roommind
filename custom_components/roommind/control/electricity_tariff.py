"""Provider-neutral electricity prices for heating."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from typing import TYPE_CHECKING

from homeassistant.util.dt import parse_datetime

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

# Require a material difference before accepting extra heat loss or cooler rooms.
MIN_RELATIVE_PRICE_SPREAD = 0.10


@dataclass(frozen=True)
class PriceInterval:
    start: float
    end: float
    price: float


@dataclass(frozen=True)
class PriceChange:
    starts_at: float
    ends_at: float
    more_expensive: bool


@dataclass(frozen=True)
class ElectricityTariff:
    current: float
    forecast: tuple[PriceInterval, ...]

    def next_change(self, now: float, horizon_end: float) -> PriceChange | None:
        """Find the first materially different price in the contiguous forecast."""
        cursor = now
        change = None
        for interval in self.forecast:
            if interval.end <= now:
                continue
            if interval.start >= horizon_end:
                break
            if interval.start > cursor:
                # A forecast may start with the next slot. The current sensor
                # supplies the price until that boundary, at most an hour away.
                if cursor != now or interval.start - now > 3600:
                    break
            diff = interval.price - self.current
            spread = MIN_RELATIVE_PRICE_SPREAD * max(abs(self.current), abs(interval.price))
            if interval.start <= now:
                # The current slot, when present, lets us reject stale or
                # mismatched current prices before shifting the heating target.
                if not math.isclose(interval.price, self.current, rel_tol=1e-4, abs_tol=1e-6):
                    return None
            elif diff and abs(diff) >= spread:
                if change is not None and change.more_expensive != (diff > 0):
                    break
                start = change.starts_at if change is not None else interval.start
                change = PriceChange(start, min(interval.end, horizon_end), diff > 0)
            elif change is not None:
                break
            cursor = interval.end
        return change


def read_electricity_tariff(hass: HomeAssistant, current_entity: str, forecast_entity: str) -> ElectricityTariff | None:
    """Read the selected sensors, requiring matching units when both declare one."""
    if not current_entity or not forecast_entity:
        return None
    current = hass.states.get(current_entity)
    forecast = hass.states.get(forecast_entity)
    if current is None or forecast is None or forecast.state in ("unknown", "unavailable"):
        return None
    current_unit = current.attributes.get("unit_of_measurement")
    forecast_unit = forecast.attributes.get("unit_of_measurement")
    if current_unit and forecast_unit and current_unit != forecast_unit:
        return None
    price = _number(current.state)
    rows = forecast.attributes.get("prices")
    if price is None or not isinstance(rows, list):
        return None

    intervals: list[PriceInterval] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        start, end = _timestamp(row.get("start")), _timestamp(row.get("end"))
        value = _number(row.get("price"))
        if start is not None and end is not None and end > start and value is not None:
            intervals.append(PriceInterval(start, end, value))
    intervals.sort(key=lambda interval: interval.start)
    if not intervals or any(a.end > b.start for a, b in pairwise(intervals)):
        return None
    return ElectricityTariff(price, tuple(intervals))


def _timestamp(value: object) -> float | None:
    if isinstance(value, str):
        try:
            value = parse_datetime(value)
        except ValueError:
            return None
    if isinstance(value, datetime) and value.utcoffset() is not None:
        return value.timestamp()
    return None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    return number if math.isfinite(number) else None
