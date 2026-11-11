"""Electricity price signal: read a price source, rank prices, shift targets.

RoomMind takes one price source (a price sensor with or without a forecast attribute, or a
switch that is on while energy is cheap) and turns it into a level per hour: cheap, normal or
expensive. Rooms that opted in shift their schedule targets by a small amount: charge the
house while it is cheap and an expensive stretch is coming, coast while it is expensive. All
of it is relative, so the unit (EUR/MWh, ct/kWh, p/kWh) does not matter and negative prices
work. The shift is a pure function used by the coordinator, the MPC horizon and the analytics
forecast alike.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util

from ..const import MAX_TARGET_TEMP, MIN_TARGET_TEMP, TargetTemps

LEVEL_CHEAP = "cheap"
LEVEL_NORMAL = "normal"
LEVEL_EXPENSIVE = "expensive"

# Attributes integrations put their price list in (Nordpool, Energi Data Service: raw_today/
# raw_tomorrow; EPEX Spot: data; ENTSO-e: prices, prices_today/tomorrow; Octopus: rates)
FORECAST_ATTRIBUTES = (
    "raw_today",
    "raw_tomorrow",
    "data",
    "prices",
    "prices_today",
    "prices_tomorrow",
    "forecast",
    "rates",
)
START_KEYS = ("start", "start_time", "startsAt", "from", "time", "hour", "valid_from")
END_KEYS = ("end", "end_time", "till", "to", "valid_to")
PRICE_KEYS = ("value", "price", "price_per_kwh", "value_inc_vat", "total", "marketprice")
SWITCH_DOMAINS = ("binary_sensor", "input_boolean", "switch")
# Octopus Energy publishes its rates on event entities
EVENT_DOMAIN = "event"

SLOT_S = 3600
# Bottom / top third of the known prices are cheap / expensive
CHEAP_QUANTILE = 1 / 3
EXPENSIVE_QUANTILE = 2 / 3
# A flat tariff must not shift anything: the gap between the thirds has to be this share of
# the typical price (median magnitude)
MIN_RELATIVE_SPREAD = 0.1
# Charging the house only pays off when an expensive stretch follows within this time
PRICE_LOOKAHEAD_H = 6
# Without a forecast: rank the current price against what was seen in this window
HISTORY_WINDOW_S = 7 * 86400
MIN_HISTORY_HOURS = 12


@dataclass(frozen=True)
class PriceSlot:
    """One price interval, timestamps in seconds."""

    start: float
    end: float
    price: float


def _timestamp(value: Any) -> float | None:
    if isinstance(value, datetime):
        return (
            value.timestamp()
            if value.tzinfo
            else dt_util.as_utc(value.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)).timestamp()
        )
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # Epoch seconds or milliseconds
        return float(value) / 1000 if value > 1e11 else float(value)
    if isinstance(value, str):
        parsed = dt_util.parse_datetime(value)
        if parsed is None:
            return None
        return _timestamp(parsed)
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _first(item: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in item and item[key] is not None:
            return item[key]
    return None


def parse_price_forecast(attributes: Mapping[str, Any]) -> list[PriceSlot]:
    """Price intervals from an entity's attributes, sorted, in any of the common shapes."""
    raw: list[tuple[float, float | None, float]] = []
    for name in FORECAST_ATTRIBUTES:
        items = attributes.get(name)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, Mapping):
                continue
            start = _timestamp(_first(item, START_KEYS))
            price = _number(_first(item, PRICE_KEYS))
            if start is None or price is None:
                continue
            raw.append((start, _timestamp(_first(item, END_KEYS)), price))
    by_start: dict[float, tuple[float | None, float]] = {}
    for start, end, price in raw:
        by_start[start] = (end, price)
    starts = sorted(by_start)
    slots: list[PriceSlot] = []
    for i, start in enumerate(starts):
        end, price = by_start[start]
        if end is None or end <= start:
            end = starts[i + 1] if i + 1 < len(starts) else start + _typical_length(starts)
        slots.append(PriceSlot(start, end, price))
    return slots


def _typical_length(starts: list[float]) -> float:
    gaps = sorted(b - a for a, b in zip(starts, starts[1:], strict=False) if b > a)
    return gaps[len(gaps) // 2] if gaps else SLOT_S


def hourly(slots: list[PriceSlot]) -> list[PriceSlot]:
    """Time-weighted means per clock hour: 15-min day-ahead prices flicker, a target must not."""
    sums: dict[float, list[float]] = {}
    for slot in slots:
        t = slot.start
        while t < slot.end:
            hour = math.floor(t / SLOT_S) * SLOT_S
            part_end = min(slot.end, hour + SLOT_S)
            acc = sums.setdefault(hour, [0.0, 0.0])
            acc[0] += slot.price * (part_end - t)
            acc[1] += part_end - t
            t = part_end
    return [PriceSlot(h, h + SLOT_S, acc[0] / acc[1]) for h, acc in sorted(sums.items()) if acc[1] > 0]


def _quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    pos = q * (len(ordered) - 1)
    low = math.floor(pos)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def price_thresholds(prices: list[float]) -> tuple[float, float] | None:
    """(cheap at or below, expensive at or above), None for a flat or too short price list."""
    if len(prices) < 3:
        return None
    low = _quantile(prices, CHEAP_QUANTILE)
    high = _quantile(prices, EXPENSIVE_QUANTILE)
    typical = abs(_quantile(prices, 0.5))
    spread = high - low
    if spread <= 0 or (typical > 0 and spread < MIN_RELATIVE_SPREAD * typical):
        return None
    return low, high


def level_of(price: float, thresholds: tuple[float, float] | None) -> str:
    if thresholds is None:
        return LEVEL_NORMAL
    low, high = thresholds
    if price <= low:
        return LEVEL_CHEAP
    if price >= high:
        return LEVEL_EXPENSIVE
    return LEVEL_NORMAL


@dataclass
class PriceSignal:
    """Price levels over time for one cycle.

    ``slots`` holds hourly prices when the source has a forecast; without one only
    ``current_level`` is known (switch or a sensor ranked against its own history).
    """

    current_price: float | None = None
    current_level: str | None = None
    slots: list[PriceSlot] = field(default_factory=list)
    thresholds: tuple[float, float] | None = None
    now: float = 0.0

    @property
    def has_forecast(self) -> bool:
        return bool(self.slots)

    def forecast_hours(self) -> float:
        return sum(s.end - max(s.start, self.now) for s in self.slots if s.end > self.now) / 3600

    def _slot_at(self, ts: float) -> PriceSlot | None:
        for slot in self.slots:
            if slot.start <= ts < slot.end:
                return slot
        return None

    def price_at(self, ts: float) -> float | None:
        slot = self._slot_at(ts)
        if slot is not None:
            return slot.price
        return self.current_price if self._is_current(ts) else None

    def level_at(self, ts: float) -> str | None:
        slot = self._slot_at(ts)
        if slot is not None:
            return level_of(slot.price, self.thresholds)
        return self.current_level if self._is_current(ts) else None

    def _is_current(self, ts: float) -> bool:
        return math.floor(ts / SLOT_S) == math.floor(self.now / SLOT_S)

    def direction_at(self, ts: float) -> int:
        """+1 charge (cheap, and an expensive stretch follows if the future is known),
        -1 coast (expensive), 0 leave the target alone."""
        level = self.level_at(ts)
        if level == LEVEL_EXPENSIVE:
            return -1
        if level != LEVEL_CHEAP:
            return 0
        if not self.has_forecast:
            return 1
        horizon = ts + PRICE_LOOKAHEAD_H * 3600
        for slot in self.slots:
            if slot.start > ts and slot.start < horizon and level_of(slot.price, self.thresholds) == LEVEL_EXPENSIVE:
                return 1
        return 0


def signal_from_state(
    domain: str,
    state: str | None,
    attributes: Mapping[str, Any],
    now: float,
    history: list[tuple[float, float]] | None = None,
) -> PriceSignal | None:
    """Build the signal from the price entity's state; None when the entity says nothing usable."""
    if domain == EVENT_DOMAIN:
        # An event's state is when it last fired (unknown until then); its prices sit in the attributes
        current = None
    elif state is None or state in ("unknown", "unavailable", ""):
        return None
    elif domain in SWITCH_DOMAINS:
        return PriceSignal(current_level=LEVEL_CHEAP if state == "on" else LEVEL_NORMAL, now=now)
    else:
        current = _number(state)
    slots = hourly(parse_price_forecast(attributes))
    if slots:
        thresholds = price_thresholds([s.price for s in slots])
        signal = PriceSignal(current_price=current, slots=slots, thresholds=thresholds, now=now)
        signal.current_level = signal.level_at(now)
        return signal
    if current is None:
        return None
    recent = [p for ts, p in (history or []) if now - ts <= HISTORY_WINDOW_S]
    thresholds = price_thresholds(recent) if len(recent) >= MIN_HISTORY_HOURS else None
    level = level_of(current, thresholds) if thresholds is not None else None
    return PriceSignal(current_price=current, current_level=level, thresholds=thresholds, now=now)


def apply_price_shift(targets: TargetTemps, direction: int, shift: float) -> TargetTemps:
    """Shift heat and cool target by ``shift`` K: up/down to charge, down/up to coast.

    Charging never lifts the heat target past the cool target (nor the other way round), so
    a narrow auto band cannot turn into heating against cooling.
    """
    if direction == 0 or shift <= 0:
        return targets
    heat, cool = targets.heat, targets.cool
    new_heat = heat + direction * shift if heat is not None else None
    new_cool = cool - direction * shift if cool is not None else None
    if direction > 0 and new_heat is not None and new_cool is not None and new_heat > new_cool:
        assert heat is not None and cool is not None
        middle = (heat + cool) / 2
        new_heat, new_cool = max(heat, min(new_heat, middle)), min(cool, max(new_cool, middle))

    def clamp(value: float | None) -> float | None:
        return None if value is None else min(max(value, MIN_TARGET_TEMP), MAX_TARGET_TEMP)

    return TargetTemps(clamp(new_heat), clamp(new_cool))


def hourly_history(points: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    """Hourly means of observed (timestamp, price) pairs, for ranking without a forecast."""
    sums: dict[float, list[float]] = {}
    for ts, price in points:
        hour = math.floor(ts / SLOT_S) * SLOT_S
        acc = sums.setdefault(hour, [0.0, 0])
        acc[0] += price
        acc[1] += 1
    return [(h, acc[0] / acc[1]) for h, acc in sorted(sums.items())]
