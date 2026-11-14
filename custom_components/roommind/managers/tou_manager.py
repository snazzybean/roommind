"""Time-of-Use (TOU) tariff manager for RoomMind.

Reads the configured tariff source (rate/period/next-change sensors, tariff
calendars, manual rate windows, or plain tier flags) and builds a per-cycle
tier timeline: a gap-free ``[start, end, tier]`` model of the next 16 hours.

``snapshot`` exposes the current tariff state (tier, price, provenance, the
upcoming change and the raw segments) for entities and diagnostics. Later TOU
layers — the target-shaping store layer, the price-weighted MPC series, and
the tariff-rule library — build on this timeline; the timeline is the single
source of tariff truth they all read.

Degrade rules (behavioural invariants, kept by the tests):

* ``tou_enabled`` off (or no usable source) yields a timeline whose
  ``current_tier`` is ``unknown``, which shapes nothing — behaviour is
  identical to TOU being off;
* a tier is never guessed past a source's evidence: no cost thresholds means
  manual rate windows cannot classify and stay inert; a future view missing
  its time or tier simply leaves the horizon flat.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..const import (
    TOU_SOURCE_FLAGS,
    TOU_SOURCE_NONE,
    TOU_SOURCE_PERIOD,
    TOU_SOURCE_RATE,
    TOU_TIER_MID,
    TOU_TIER_OFF,
    TOU_TIER_PEAK,
    TOU_TIER_ULTRA_LOW,
    TOU_TIER_UNKNOWN,
    TOU_TIMELINE_HORIZON_MINUTES,
    TOU_WEEKDAYS,
)

_LOGGER = logging.getLogger(__name__)


def normalize_period_state(state: str) -> str:
    """Map a period sensor state (any tariff wording) onto a RoomMind tier.

    Order matters: ``ulo_off_peak`` contains both "off" and "peak" and must
    resolve to off, while ``ulo_on_peak`` resolves to peak and ``ulo_overnight``
    (the Ontario ultra-low overnight window) resolves to ultra_low.
    """
    s = (state or "").strip().lower().replace("-", "_")
    if s in ("", "unknown", "unavailable"):
        return TOU_TIER_UNKNOWN
    if "overnight" in s or "ultra" in s or "super_off" in s or "deep_off" in s:
        return TOU_TIER_ULTRA_LOW
    if "mid" in s:
        return TOU_TIER_MID
    if "off" in s:
        return TOU_TIER_OFF
    if "peak" in s or "high" in s or s in ("on", "expensive"):
        return TOU_TIER_PEAK
    return TOU_TIER_UNKNOWN


@dataclass
class TouSegment:
    """A contiguous stretch of one tariff tier inside the horizon."""

    start: float
    end: float
    tier: str


class TouTimeline:
    """Tier timeline covering [now, now + horizon] with no gaps."""

    def __init__(self, segments: list[TouSegment], *, current_tier: str, current_rate: float | None) -> None:
        self.segments = segments
        self.current_tier = current_tier
        self.current_rate = current_rate

    def tier_at(self, ts: float) -> str:
        """Return the tier covering *ts* (clamped to the timeline edges)."""
        if not self.segments:
            return TOU_TIER_UNKNOWN
        if ts <= self.segments[0].start:
            return self.segments[0].tier
        for seg in self.segments:
            if seg.start <= ts < seg.end:
                return seg.tier
        return self.segments[-1].tier

    def boundaries(self) -> list[tuple[float, str, str]]:
        """Return (ts, tier_before, tier_after) for every change in the horizon."""
        out: list[tuple[float, str, str]] = []
        for prev, nxt in zip(self.segments, self.segments[1:], strict=False):
            if nxt.tier != prev.tier:
                out.append((nxt.start, prev.tier, nxt.tier))
        return out

    def next_boundary_after(self, ts: float, to_tier: str | None = None) -> float | None:
        """First change after *ts* (optionally into *to_tier*), or None."""
        for b_ts, _, tier_after in self.boundaries():
            if b_ts > ts and (to_tier is None or tier_after == to_tier):
                return b_ts
        return None


class TouManager:
    """Owns the tariff source reading and the timeline the TOU layers share."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._timeline: TouTimeline | None = None
        self._source_kind: str = TOU_SOURCE_NONE
        self._rate_unit: str = ""

    @property
    def timeline(self) -> TouTimeline | None:
        """Return the timeline computed by the last cycle."""
        return self._timeline

    # ------------------------------------------------------------------
    # Timeline construction
    # ------------------------------------------------------------------

    async def async_build_timeline(self, settings: dict[str, Any]) -> TouTimeline | None:
        """Read the configured sources and build the horizon timeline.

        Returns None when the feature is disabled. A missing or unavailable
        source yields a timeline with ``current_tier`` unknown, which shapes
        nothing — behavior is identical to TOU being off. ``tou_lookahead``
        picks which future source counts (calendars, next-change, or none);
        "auto" keeps the legacy order: calendars, with next-change as the
        fallback when no calendar window covers the horizon.
        """
        if not settings.get("tou_enabled", False):
            self._timeline = None
            self._source_kind = TOU_SOURCE_NONE
            return None

        now = time.time()
        horizon = now + TOU_TIMELINE_HORIZON_MINUTES * 60.0

        current, rate, unit, source = self._resolve_current_tier(settings)
        self._source_kind = source
        self._rate_unit = unit

        lookahead = str(settings.get("tou_lookahead") or "auto")
        events: list[tuple[float, float, str]] = []
        if lookahead in ("auto", "calendar"):
            for entry in settings.get("tou_calendar_entities") or []:
                entity_id = str(entry.get("entity_id", ""))
                tier = str(entry.get("tier", ""))
                if not entity_id or tier not in (TOU_TIER_PEAK, TOU_TIER_MID, TOU_TIER_OFF, TOU_TIER_ULTRA_LOW):
                    continue
                for ev_start, ev_end in await self._async_calendar_windows(entity_id, now, horizon):
                    events.append((ev_start, ev_end, tier))
            for win_start, win_end, win_tier in self._rate_window_events(settings, now, horizon):
                events.append((win_start, win_end, win_tier))

        if not events and lookahead in ("auto", "next_change", "next_change_rate"):
            next_ts, next_tier, _next_rate, _next_unit = self._resolve_next_view(settings, lookahead)
            if next_ts is not None and next_tier is not None and now < next_ts < horizon:
                events.append((next_ts, horizon, next_tier))

        segments = self._paint_segments(now, horizon, current, events)
        timeline = TouTimeline(segments, current_tier=current, current_rate=rate)
        self._timeline = timeline
        return timeline

    def _resolve_current_tier(self, settings: dict[str, Any]) -> tuple[str, float | None, str, str]:
        """Return (tier, rate, rate_unit, source_kind) for *now*.

        ``tou_tier_source`` selects which source may answer; "auto" keeps the
        legacy cascade (period -> flags -> rate). The numeric rate is always
        read when a cost sensor is bound — it feeds the rate sensors and the
        price display even when another source classifies the tier.
        """
        mode = str(settings.get("tou_tier_source") or "auto")
        period_entity = str(settings.get("tou_period_entity") or "")
        if period_entity and mode in ("auto", "period"):
            state = self.hass.states.get(period_entity)
            if state is not None and state.state not in ("unavailable", "unknown"):
                tier = self._normalize_period(state.state, settings)
                if tier != TOU_TIER_UNKNOWN:
                    rate, unit = self._read_rate(settings)
                    return tier, rate, unit, TOU_SOURCE_PERIOD

        flags = settings.get("tou_flag_entities") or {}
        if isinstance(flags, dict) and mode in ("auto", "flags"):
            for tier, entity_id in flags.items():
                if not entity_id or not isinstance(entity_id, str):
                    continue
                state = self.hass.states.get(entity_id)
                if state is not None and state.state == "on":
                    rate, unit = self._read_rate(settings)
                    return str(tier), rate, unit, TOU_SOURCE_FLAGS

        rate, unit = self._read_rate(settings)
        if mode not in ("auto", "rate"):
            return TOU_TIER_UNKNOWN, rate, unit, TOU_SOURCE_NONE
        tier = self._tier_from_rate(rate, settings)
        if tier != TOU_TIER_UNKNOWN:
            return tier, rate, unit, TOU_SOURCE_RATE
        return TOU_TIER_UNKNOWN, rate, unit, TOU_SOURCE_NONE

    @staticmethod
    def _normalize_period(state: str, settings: dict[str, Any]) -> str:
        """``normalize_period_state`` with the user's vocabulary consulted first.

        ``tou_period_aliases`` maps a lower-cased raw period state onto a tier
        and overrides the built-in word recognition — the fix lever for
        provider wording the normalizer cannot read. The settings panel
        surfaces those unreads as unmapped strings the user can assign.
        """
        key = (state or "").strip().lower()
        aliases = settings.get("tou_period_aliases")
        if isinstance(aliases, dict):
            mapped = aliases.get(key)
            if mapped in (TOU_TIER_PEAK, TOU_TIER_MID, TOU_TIER_OFF, TOU_TIER_ULTRA_LOW):
                return str(mapped)
        return normalize_period_state(state)

    def _read_rate(self, settings: dict[str, Any]) -> tuple[float | None, str]:
        return self._read_rate_entity(str(settings.get("tou_rate_entity") or ""))

    def _read_rate_entity(self, entity_id: str) -> tuple[float | None, str]:
        """Numeric state and unit of any bound rate-like entity, or (None, "")."""
        if not entity_id:
            return None, ""
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unavailable", "unknown"):
            return None, ""
        try:
            rate = float(state.state)
        except (TypeError, ValueError):
            return None, ""
        unit = str(state.attributes.get("unit_of_measurement", ""))
        return rate, unit

    @staticmethod
    def _tier_from_rate(rate: float | None, settings: dict[str, Any]) -> str:
        """Classify *rate* against the configured tier thresholds."""
        if rate is None:
            return TOU_TIER_UNKNOWN
        peak = settings.get("tou_peak_threshold")
        mid = settings.get("tou_mid_threshold")
        ultra = settings.get("tou_ultra_threshold")
        if isinstance(peak, (int, float)) and rate >= float(peak):
            return TOU_TIER_PEAK
        if isinstance(mid, (int, float)) and rate >= float(mid):
            return TOU_TIER_MID
        if isinstance(ultra, (int, float)) and rate <= float(ultra):
            return TOU_TIER_ULTRA_LOW
        return TOU_TIER_OFF

    def _resolve_next_view(
        self, settings: dict[str, Any], lookahead: str
    ) -> tuple[float | None, str | None, float | None, str]:
        """The upcoming period pulled from the bound future sensors.

        Returns ``(ts, tier, rate, unit)``: the change time from
        ``tou_next_change_entity``, the price from ``tou_next_rate_entity``,
        and the tier from whichever future source can answer — the
        next-period sensor's vocabulary (provider names like ``ulo_mid_peak``
        mapped by the same recognition as the current period), the cost
        thresholds applied to the next rate, or the fixed tier dropdown, in
        the order ``tou_lookahead`` trusts them. A next-change slot fed a
        period *name* instead of a timestamp is understood as vocabulary
        rather than discarded: the tier and price still arrive, minus the
        time. No source is ever guessed past its evidence.
        """
        ts: float | None = None
        slot_tier: str | None = None
        change_id = str(settings.get("tou_next_change_entity") or "")
        if change_id:
            state = self.hass.states.get(change_id)
            if state is not None and state.state not in ("unavailable", "unknown"):
                raw: datetime | None
                if isinstance(state.state, datetime):
                    raw = state.state
                else:
                    raw = dt_util.parse_datetime(str(state.state))
                if raw is not None:
                    ts = raw.timestamp()
                else:
                    guessed = self._normalize_period(str(state.state), settings)
                    slot_tier = guessed if guessed != TOU_TIER_UNKNOWN else None

        period_tier: str | None = None
        period_id = str(settings.get("tou_next_period_entity") or "")
        if period_id:
            state = self.hass.states.get(period_id)
            if state is not None and state.state not in ("unavailable", "unknown"):
                guessed = self._normalize_period(state.state, settings)
                period_tier = guessed if guessed != TOU_TIER_UNKNOWN else None

        next_rate, next_unit = self._read_rate_entity(str(settings.get("tou_next_rate_entity") or ""))
        rate_tier: str | None = None
        if next_rate is not None and self._thresholds_present(settings):
            rate_tier = self._tier_from_rate(next_rate, settings)

        dropdown = str(settings.get("tou_next_change_tier") or "")
        if dropdown not in (TOU_TIER_PEAK, TOU_TIER_MID, TOU_TIER_OFF, TOU_TIER_ULTRA_LOW):
            dropdown = ""

        if lookahead == "next_change_rate":
            # The rate decides in this mode; a fixed dropdown must not outrank it.
            order: list[str] = [p for p in (period_tier, rate_tier, slot_tier) if p]
        else:
            order = [p for p in (period_tier, dropdown, rate_tier, slot_tier) if p]
        tier = order[0] if order else None
        return ts, tier, next_rate, next_unit

    @staticmethod
    def _thresholds_present(settings: dict[str, Any]) -> bool:
        return any(
            isinstance(settings.get(key), (int, float))
            for key in ("tou_peak_threshold", "tou_mid_threshold", "tou_ultra_threshold")
        )

    @staticmethod
    def _hhmm_minutes(hhmm: str) -> int | None:
        parts = hhmm.split(":")
        if len(parts) < 2:
            return None
        try:
            hour, minute = int(parts[0]), int(parts[1])
        except ValueError:
            return None
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        return hour * 60 + minute

    def _rate_window_events(
        self, settings: dict[str, Any], now: float, horizon: float
    ) -> list[tuple[float, float, str]]:
        """Materialize manual tariff-window rows into [start, end, tier] events.

        Each row applies its rate between two wall-clock times on the chosen
        weekdays (no day ticked = every day; an end not after the start wraps
        past midnight). Rates map to tiers through the cost thresholds —
        without any threshold configured the rows cannot classify and are
        ignored rather than guessed.
        """
        rows = settings.get("tou_rate_windows")
        if not isinstance(rows, list) or not rows or not self._thresholds_present(settings):
            return []
        out: list[tuple[float, float, str]] = []
        base = dt_util.as_local(dt_util.utc_from_timestamp(now)).replace(hour=0, minute=0, second=0, microsecond=0)
        for row in rows:
            if not isinstance(row, dict):
                continue
            rate = row.get("rate")
            if not isinstance(rate, (int, float)):
                continue
            tier = self._tier_from_rate(float(rate), settings)
            if tier == TOU_TIER_UNKNOWN:
                continue
            start_min = self._hhmm_minutes(str(row.get("start") or ""))
            end_min = self._hhmm_minutes(str(row.get("end") or ""))
            if start_min is None or end_min is None:
                continue
            days = {str(d) for d in row.get("days") or [] if isinstance(d, str)}
            for offset in range(-1, 3):
                day = base + timedelta(days=offset)
                if days and TOU_WEEKDAYS[day.weekday()] not in days:
                    continue
                start_dt = day.replace(hour=start_min // 60, minute=start_min % 60)
                end_dt = day.replace(hour=end_min // 60, minute=end_min % 60)
                if end_dt <= start_dt:
                    end_dt += timedelta(days=1)
                start = max(start_dt.timestamp(), now)
                end = min(end_dt.timestamp(), horizon)
                if start < end:
                    out.append((start, end, tier))
        return out

    async def _async_calendar_windows(self, entity_id: str, now: float, horizon: float) -> list[tuple[float, float]]:
        """Return [start, end] epoch windows of running/upcoming events, clamped to the horizon."""
        state = self.hass.states.get(entity_id)
        if state is None or state.state == "unavailable":
            return []
        try:
            response = await self.hass.services.async_call(
                "calendar",
                "get_events",
                {
                    "entity_id": entity_id,
                    "start_date_time": dt_util.utc_from_timestamp(now).isoformat(),
                    "duration": {"minutes": TOU_TIMELINE_HORIZON_MINUTES},
                },
                blocking=True,
                return_response=True,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("calendar.get_events failed for %s: %r", entity_id, err)
            return []
        events: list[Any] = []
        if isinstance(response, dict):
            data = response.get(entity_id)
            if isinstance(data, dict):
                events = data.get("events") or []
        windows: list[tuple[float, float]] = []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            start = self._event_ts(ev.get("start"))
            end = self._event_ts(ev.get("end"))
            if start is None or end is None or end <= now or start >= horizon:
                continue
            windows.append((max(start, now), min(end, horizon)))
        return windows

    @staticmethod
    def _event_ts(payload: Any) -> float | None:
        """Extract an epoch from a calendar event start/end payload."""
        if not isinstance(payload, dict):
            return None
        raw = payload.get("date_time") or payload.get("date")
        if not isinstance(raw, str):
            return None
        parsed = dt_util.parse_datetime(raw) or dt_util.parse_date(raw)
        if parsed is None:
            return None
        if isinstance(parsed, datetime):
            return float(parsed.timestamp())
        # All-day date: local midnight of that day.
        local = dt_util.start_of_local_day(parsed)
        return float(local.timestamp())

    @staticmethod
    def _paint_segments(
        now: float,
        horizon: float,
        current_tier: str,
        events: list[tuple[float, float, str]],
    ) -> list[TouSegment]:
        """Paint event windows over the flat current tier and merge equal neighbors."""
        points = {now, horizon}
        for start, end, _ in events:
            points.add(max(start, now))
            points.add(min(end, horizon))
        ordered = sorted(p for p in points if now <= p <= horizon)
        segments: list[TouSegment] = []
        for lo, hi in zip(ordered, ordered[1:], strict=False):
            if hi <= lo:
                continue
            mid = (lo + hi) / 2.0
            tier = current_tier
            # Events sorted by start: the most recently started covering event wins.
            for start, end, ev_tier in sorted(events, key=lambda e: e[0]):
                if start <= mid < end:
                    tier = ev_tier
            if segments and segments[-1].tier == tier and segments[-1].end == lo:
                segments[-1].end = hi
            else:
                segments.append(TouSegment(start=lo, end=hi, tier=tier))
        if not segments:
            segments = [TouSegment(start=now, end=horizon, tier=current_tier)]
        return segments

    # ------------------------------------------------------------------
    # Snapshot for entities / diagnostics
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Return the current tariff state for the panel, sensors and diagnostics."""
        timeline = self._timeline
        if timeline is None:
            return {"enabled": False, "tier": TOU_TIER_UNKNOWN, "rate": None, "rate_unit": self._rate_unit}
        next_ts, next_tier = self._next_change_from_timeline(timeline)
        return {
            "enabled": True,
            "tier": timeline.current_tier,
            "rate": timeline.current_rate,
            "rate_unit": self._rate_unit,
            "source": self._source_kind,
            "next_change": next_ts,
            "next_tier": next_tier,
            "segments": [[round(s.start, 1), round(s.end, 1), s.tier] for s in timeline.segments],
        }

    @staticmethod
    def _next_change_from_timeline(timeline: TouTimeline) -> tuple[float | None, str | None]:
        now = time.time()
        for b_ts, _, tier_after in timeline.boundaries():
            if b_ts > now:
                return b_ts, tier_after
        return None, None
