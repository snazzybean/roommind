"""Reads the configured electricity price source once per cycle (see utils/price_utils)."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.core import HomeAssistant

from ..utils.price_utils import (
    HISTORY_WINDOW_S,
    MIN_HISTORY_HOURS,
    SWITCH_DOMAINS,
    PriceSignal,
    hourly_history,
    signal_from_state,
)

# One observed price per this many seconds is enough to rank hours without a forecast
_SAMPLE_EVERY_S = 300
# Without a forecast (switch, raw price) a new level counts once it held this long: a PV
# surplus switch flips with every cloud, each flip would move the target and send commands
LEVEL_HOLD_S = 900


class PriceManager:
    """Builds the PriceSignal for the cycle and keeps the observed prices of a sensor without
    forecast, seeded from the recorded history after a restart so ranking resumes at once."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.signal: PriceSignal | None = None
        self._entity = ""
        self._observed: list[tuple[float, float]] = []
        self._seeded = False
        self._readable = False
        self._held_level: str | None = None
        self._pending: tuple[str | None, float] | None = None

    async def async_update(
        self,
        settings: dict,
        load_history: Callable[[], Awaitable[list[tuple[float, float]]]] | None = None,
    ) -> PriceSignal | None:
        entity = settings.get("price_entity", "") or ""
        if entity != self._entity:
            self._entity = entity
            self._observed = []
            self._seeded = False
            self._held_level = None
            self._pending = None
        if not entity:
            self.signal = None
            self._readable = False
            return None

        now = time.time()
        state = self.hass.states.get(entity)
        domain = entity.split(".", 1)[0]
        raw = state.state if state is not None else None
        attributes: dict[str, Any] = dict(state.attributes) if state is not None else {}
        if domain not in SWITCH_DOMAINS:
            self._observe(raw, now)
        signal = signal_from_state(domain, raw, attributes, now, hourly_history(self._observed))
        if (
            signal is not None
            and not signal.has_forecast
            and signal.current_level is None
            and not self._seeded
            and load_history is not None
        ):
            self._seeded = True
            self._seed(await load_history(), now)
            signal = signal_from_state(domain, raw, attributes, now, hourly_history(self._observed))
        if signal is not None and not signal.has_forecast:
            signal.current_level = self._steady_level(signal.current_level, now)
        self._readable = signal is not None
        self.signal = signal
        return signal

    def _steady_level(self, level: str | None, now: float) -> str | None:
        """The level in force: the first reading at once, a change once it held LEVEL_HOLD_S."""
        if self._held_level is None or level == self._held_level:
            self._held_level = level
            self._pending = None
            return level
        if self._pending is None or self._pending[0] != level:
            self._pending = (level, now)
        if now - self._pending[1] >= LEVEL_HOLD_S:
            self._held_level = level
            self._pending = None
        return self._held_level

    def _observe(self, raw: str | None, now: float) -> None:
        try:
            price = float(raw) if raw is not None else None
        except ValueError:
            price = None
        if price is None:
            return
        if not self._observed or now - self._observed[-1][0] >= _SAMPLE_EVERY_S:
            self._observed.append((now, price))
        cutoff = now - HISTORY_WINDOW_S
        if self._observed and self._observed[0][0] < cutoff:
            self._observed = [o for o in self._observed if o[0] >= cutoff]

    def _seed(self, rows: list[tuple[float, float]], now: float) -> None:
        known = {round(ts) for ts, _ in self._observed}
        older = [(ts, p) for ts, p in rows if now - ts <= HISTORY_WINDOW_S and round(ts) not in known]
        self._observed = sorted(older + self._observed)

    def status(self) -> dict | None:
        """What the settings page shows: is the source read, and what does it say now."""
        if not self._entity:
            return None
        signal = self.signal
        hours = len(hourly_history(self._observed))
        if signal is None:
            kind = None
        elif signal.has_forecast:
            kind = "forecast"
        elif signal.current_price is None:
            kind = "switch"
        else:
            kind = "history"
        return {
            "entity_id": self._entity,
            "readable": self._readable,
            "kind": kind,
            "price": signal.price_at(signal.now) if signal else None,
            "level": signal.current_level if signal else None,
            "forecast_hours": round(signal.forecast_hours(), 1) if signal and signal.has_forecast else 0,
            "history_hours": hours,
            "history_needed": MIN_HISTORY_HOURS,
        }
