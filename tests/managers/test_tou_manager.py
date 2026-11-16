"""Tests for the Time-of-Use tariff manager.

Ported from the reference fork (wBrhy2/roommind, tag tou-legacy-beta23).
Covers the tariff-awareness engine (period normalization, source resolution,
calendars, windows, the future view, the snapshot) and the tier dictionary
with its persisted price history. Store-layer shaping, tariff rules and
sensor-driven energy tiers are follow-up PRs on this engine. The store
layer (consent band, swing, gap, pre-charge) and the electricity-price
adapter are covered here as well since PR-04b.
"""

from __future__ import annotations

import math
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.util import dt as dt_util

from custom_components.roommind.const import (
    DOMAIN,
    TOU_SOURCE_PERIOD,
    TOU_TIER_MID,
    TOU_TIER_OFF,
    TOU_TIER_PEAK,
    TOU_TIER_ULTRA_LOW,
    TOU_TIER_UNKNOWN,
    TOU_WEEKDAYS,
    TargetTemps,
)
from custom_components.roommind.managers.tou_manager import (
    TouManager,
    TouSegment,
    TouTimeline,
    normalize_period_state,
)


def _make_hass(states: dict[str, str]) -> MagicMock:
    hass = MagicMock()
    entity_states = {}
    for eid, state in states.items():
        s = MagicMock()
        s.state = state
        s.attributes = {"unit_of_measurement": "CAD/kWh"}
        entity_states[eid] = s
    hass.states.get = MagicMock(side_effect=entity_states.get)
    hass.services.async_call = AsyncMock(return_value=None)
    # Manager code may await through hass.data (e.g. price-history persistence);
    # a bare MagicMock store attribute would blow up on await. Mirror the real
    # contract: an awaitable save, no recorded expectations unless a test wants them.
    store = MagicMock()
    store.async_save_settings = AsyncMock()
    hass.data = {DOMAIN: {"store": store}}
    return hass


def _state(value: str) -> MagicMock:
    s = MagicMock()
    s.state = value
    s.attributes = {}
    return s


def _timeline(*tiers_and_minutes: tuple[str, float]) -> TouTimeline:
    """Build a gap-free timeline from (tier, duration_minutes) pairs."""
    now = time.time()
    segments: list[TouSegment] = []
    cursor = now
    for tier, minutes in tiers_and_minutes:
        end = cursor + minutes * 60.0
        segments.append(TouSegment(start=cursor, end=end, tier=tier))
        cursor = end
    segments[-1].end = now + 16 * 3600.0
    return TouTimeline(segments, current_tier=tiers_and_minutes[0][0], current_rate=None)


# ---------------------------------------------------------------------------
# Period normalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "tier"),
    [
        ("ulo_on_peak", TOU_TIER_PEAK),
        ("ulo_mid_peak", TOU_TIER_MID),
        ("ulo_off_peak", TOU_TIER_OFF),
        ("ulo_overnight", TOU_TIER_ULTRA_LOW),
        ("on-peak", TOU_TIER_PEAK),
        ("mid-peak", TOU_TIER_MID),
        ("off-peak", TOU_TIER_OFF),
        ("super_off_peak", TOU_TIER_ULTRA_LOW),
        ("peak", TOU_TIER_PEAK),
        ("", TOU_TIER_UNKNOWN),
        ("unavailable", TOU_TIER_UNKNOWN),
        ("nonsense", TOU_TIER_UNKNOWN),
    ],
)
def test_normalize_period_state(raw: str, tier: str) -> None:
    assert normalize_period_state(raw) == tier


def test_period_aliases_override_word_recognition() -> None:
    """A user alias outranks the built-in vocabulary; unaliased strings (and
    aliases to a tier RoomMind does not know) keep the built-in answer."""
    settings = {"tou_period_aliases": {"partially_peak": "ultra_low", "bogus_target": "nope"}}
    assert TouManager._normalize_period("Partially_Peak", settings) == TOU_TIER_ULTRA_LOW
    assert TouManager._normalize_period("ulo_on_peak", settings) == TOU_TIER_PEAK
    # "bogus_target" is not a real string from any source; an alias whose
    # value is not a tier must be ignored: "peak" alone still maps normally.
    assert TouManager._normalize_period("peak", settings) == TOU_TIER_PEAK
    assert TouManager._normalize_period("partially_peak", {}) == TOU_TIER_PEAK


# ---------------------------------------------------------------------------
# Tier dictionary & price history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tier_info_observes_names_rates_and_unmapped() -> None:
    """The dictionary block reads live: mapped names with the rate seen in
    that tier, plus strings the normalizer could not place."""
    hass = _make_hass({"sensor.period": "ulo_on_peak", "sensor.rate": "0.337"})
    mgr = TouManager(hass)
    settings = {"tou_enabled": True, "tou_period_entity": "sensor.period", "tou_rate_entity": "sensor.rate"}
    assert await mgr.async_build_timeline(settings) is not None
    info = mgr.tier_info(settings)
    peak = info["tiers"][TOU_TIER_PEAK]
    assert peak["current"] is True
    assert peak["rate"] == 0.337 and peak["kind"] == "live"
    assert "ulo_on_peak" in peak["names"]
    assert info["tiers"][TOU_TIER_OFF]["rate"] is None
    assert info["unmapped"] == []

    # A provider wording the normalizer cannot read lands in unmapped.
    weird = _make_hass({"sensor.period": "tax block a"})
    mgr2 = TouManager(weird)
    settings2 = {"tou_enabled": True, "tou_period_entity": "sensor.period"}
    assert await mgr2.async_build_timeline(settings2) is not None
    info2 = mgr2.tier_info(settings2)
    assert {"state": "tax block a", "count": 1} in info2["unmapped"]


def test_tier_info_falls_back_to_windows_and_cutoffs() -> None:
    """No observations (fresh start): manual-window rates first, then cost
    thresholds marked as cutoffs so the UI can say "from"."""
    mgr = TouManager(_make_hass({}))
    settings = {
        "tou_peak_threshold": 0.3,
        "tou_mid_threshold": 0.15,
        "tou_ultra_threshold": 0.02,
        "tou_rate_windows": [{"id": "w", "rate": 0.42, "start": "17:00", "end": "21:00"}],
    }
    info = mgr.tier_info(settings)
    assert info["tiers"][TOU_TIER_PEAK]["rate"] == 0.42
    assert info["tiers"][TOU_TIER_PEAK]["kind"] == "window"
    assert info["tiers"][TOU_TIER_MID]["rate"] == 0.15
    assert info["tiers"][TOU_TIER_MID]["kind"] == "cutoff"
    assert info["tiers"][TOU_TIER_OFF]["rate"] is None  # between: no number to show


@pytest.mark.asyncio
async def test_cost_outage_keeps_running_on_the_last_known_value() -> None:
    """Rate source: a provider blip must not blind tariff shaping — the tier
    and the price fall back to the last valid cost while it is fresh."""
    hass = MagicMock()
    entity_states: dict = {}

    def _set(eid: str, value: str) -> None:
        s = MagicMock()
        s.state = value
        s.attributes = {"unit_of_measurement": "CAD/kWh"}
        entity_states[eid] = s

    hass.states.get = MagicMock(side_effect=entity_states.get)
    settings = {
        "tou_enabled": True,
        "tou_rate_entity": "sensor.rate",
        "tou_peak_threshold": 0.3,
        "tou_mid_threshold": 0.15,
        "tou_ultra_threshold": 0.02,
    }
    _set("sensor.rate", "0.42")
    mgr = TouManager(hass)
    timeline = await mgr.async_build_timeline(settings)
    assert timeline is not None and timeline.current_tier == TOU_TIER_PEAK

    _set("sensor.rate", "unavailable")
    timeline2 = await mgr.async_build_timeline(settings)
    assert timeline2 is not None
    assert timeline2.current_tier == TOU_TIER_PEAK  # shaped off the last valid price
    assert timeline2.current_rate == 0.42
    info = mgr.tier_info(settings)
    assert info["current"] == {"tier": TOU_TIER_PEAK, "rate": 0.42, "stale": True}


@pytest.mark.asyncio
async def test_price_history_persists_and_seeds_restart() -> None:
    """Observations write back (throttled) and a fresh manager reads them."""
    hass = _make_hass({"sensor.rate": "0.42"})
    store = MagicMock()
    store.async_save_settings = AsyncMock()
    hass.data = {"roommind": {"store": store}}
    settings = {
        "tou_enabled": True,
        "tou_rate_entity": "sensor.rate",
        "tou_peak_threshold": 0.3,
        "tou_mid_threshold": 0.15,
        "tou_ultra_threshold": 0.02,
    }
    mgr = TouManager(hass)
    await mgr.async_build_timeline(settings)
    store.async_save_settings.assert_called_once()
    persisted = store.async_save_settings.call_args[0][0]["tou_price_history"]
    assert persisted[TOU_TIER_PEAK]["rate"] == 0.42
    assert persisted[TOU_TIER_PEAK]["count"] == 1

    # Restart: no live rate anywhere, but the persisted history answers.
    mgr2 = TouManager(_make_hass({}))
    info2 = mgr2.tier_info({"tou_price_history": persisted})
    peak = info2["tiers"][TOU_TIER_PEAK]
    assert peak["rate"] == 0.42 and peak["kind"] == "last"


@pytest.mark.asyncio
async def test_tier_info_pulls_next_period_with_cost() -> None:
    """Next-change + next-rate sensors are read on view: the panel sees the
    upcoming period and its provider-published price before it starts."""
    next_ts = time.time() + 7200.0
    hass = _make_hass(
        {
            "sensor.period": "ulo_off_peak",
            "sensor.next_change": dt_util.utc_from_timestamp(next_ts).isoformat(),
            "sensor.next_rate": "0.45",
        }
    )
    settings = {
        "tou_enabled": True,
        "tou_period_entity": "sensor.period",
        "tou_next_change_entity": "sensor.next_change",
        "tou_next_rate_entity": "sensor.next_rate",
        "tou_lookahead": "next_change",
        "tou_next_change_tier": TOU_TIER_PEAK,
        "tou_peak_threshold": 0.3,
        "tou_mid_threshold": 0.15,
        "tou_ultra_threshold": 0.02,
    }
    mgr = TouManager(hass)
    assert await mgr.async_build_timeline(settings) is not None
    info = mgr.tier_info(settings)
    assert info["next"] is not None
    assert info["next"]["tier"] == TOU_TIER_PEAK
    assert info["next"]["rate"] == 0.45 and info["next"]["stale"] is False
    assert info["tiers"][TOU_TIER_PEAK]["kind"] == "next"
    assert info["tiers"][TOU_TIER_OFF]["current"] is True


# ---------------------------------------------------------------------------
# Timeline building from sources
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disabled_returns_none() -> None:
    mgr = TouManager(_make_hass({}))
    assert await mgr.async_build_timeline({}) is None
    assert mgr.timeline is None


@pytest.mark.asyncio
async def test_period_sensor_source() -> None:
    hass = _make_hass({"sensor.rate_period": "ulo_on_peak", "sensor.rate": "0.25"})
    mgr = TouManager(hass)
    timeline = await mgr.async_build_timeline(
        {"tou_enabled": True, "tou_period_entity": "sensor.rate_period", "tou_rate_entity": "sensor.rate"}
    )
    assert timeline is not None
    assert timeline.current_tier == TOU_TIER_PEAK
    assert timeline.current_rate == 0.25
    snap = mgr.snapshot()
    assert snap["enabled"] and snap["source"] == TOU_SOURCE_PERIOD


@pytest.mark.asyncio
async def test_flags_source() -> None:
    hass = _make_hass(
        {
            "input_boolean.tou_h": "off",
            "input_boolean.tou_m": "on",
            "input_boolean.tou_l": "off",
            "input_boolean.tou_ul": "off",
        }
    )
    mgr = TouManager(hass)
    timeline = await mgr.async_build_timeline(
        {
            "tou_enabled": True,
            "tou_flag_entities": {
                "peak": "input_boolean.tou_h",
                "mid": "input_boolean.tou_m",
                "off": "input_boolean.tou_l",
                "ultra_low": "input_boolean.tou_ul",
            },
        }
    )
    assert timeline is not None
    assert timeline.current_tier == TOU_TIER_MID


@pytest.mark.asyncio
async def test_rate_thresholds_source() -> None:
    hass = _make_hass({"sensor.rate": "0.20"})
    mgr = TouManager(hass)
    timeline = await mgr.async_build_timeline(
        {
            "tou_enabled": True,
            "tou_rate_entity": "sensor.rate",
            "tou_peak_threshold": 0.18,
            "tou_mid_threshold": 0.10,
        }
    )
    assert timeline is not None
    assert timeline.current_tier == TOU_TIER_PEAK


@pytest.mark.asyncio
async def test_unknown_source_shapes_nothing() -> None:
    mgr = TouManager(_make_hass({}))
    timeline = await mgr.async_build_timeline({"tou_enabled": True})
    assert timeline is not None
    assert timeline.current_tier == TOU_TIER_UNKNOWN


@pytest.mark.asyncio
async def test_calendar_events_build_segments() -> None:
    now = time.time()
    # Relative to now: absolute dates go stale the moment they fall behind the
    # clock, and past events are outside the horizon by design.
    start_iso = dt_util.utc_from_timestamp(now + 2 * 3600.0).isoformat()
    end_iso = dt_util.utc_from_timestamp(now + 7 * 3600.0).isoformat()
    hass = _make_hass({"sensor.rate_period": "ulo_off_peak", "calendar.tou_peak": "on"})
    hass.services.async_call = AsyncMock(
        return_value={
            "calendar.tou_peak": {"events": [{"start": {"date_time": start_iso}, "end": {"date_time": end_iso}}]}
        }
    )
    mgr = TouManager(hass)
    timeline = await mgr.async_build_timeline(
        {
            "tou_enabled": True,
            "tou_period_entity": "sensor.rate_period",
            "tou_calendar_entities": [{"entity_id": "calendar.tou_peak", "tier": "peak"}],
        }
    )
    assert timeline is not None
    parsed = dt_util.parse_datetime(start_iso).timestamp()
    # The event window paints its tier wherever it lands, and where it does not
    # cover a timestamp, the current tier still rules there.
    assert timeline.tier_at(parsed + 60) == TOU_TIER_PEAK
    assert timeline.tier_at(now + 1) == TOU_TIER_OFF


@pytest.mark.asyncio
async def test_next_change_sensor_step() -> None:
    future = time.time() + 2 * 3600.0
    iso = dt_util.utc_from_timestamp(future).isoformat()
    hass = _make_hass({"sensor.rate_period": "ulo_off_peak", "sensor.next_peak": iso})
    mgr = TouManager(hass)
    timeline = await mgr.async_build_timeline(
        {
            "tou_enabled": True,
            "tou_period_entity": "sensor.rate_period",
            "tou_next_change_entity": "sensor.next_peak",
            "tou_next_change_tier": "peak",
        }
    )
    assert timeline is not None
    assert timeline.tier_at(time.time() + 60) == TOU_TIER_OFF
    assert timeline.tier_at(future + 60) == TOU_TIER_PEAK


@pytest.mark.asyncio
async def test_tier_source_mode_pins_the_source() -> None:
    """An explicit tier source ignores the others, even while they stay bound."""
    hass = _make_hass(
        {
            "sensor.period": "on_peak",
            "input_boolean.flag_off": "on",
            "sensor.rate": "0.22",
        }
    )
    base: dict = {
        "tou_enabled": True,
        "tou_period_entity": "sensor.period",
        "tou_flag_entities": {"off": "input_boolean.flag_off"},
        "tou_rate_entity": "sensor.rate",
        "tou_peak_threshold": 0.20,
    }
    mgr = TouManager(hass)

    timeline = await mgr.async_build_timeline({**base, "tou_tier_source": "period"})
    assert timeline is not None and timeline.current_tier == TOU_TIER_PEAK
    assert timeline.current_rate == 0.22  # the rate still feeds the sensors

    timeline = await mgr.async_build_timeline({**base, "tou_tier_source": "flags"})
    assert timeline is not None and timeline.current_tier == TOU_TIER_OFF

    timeline = await mgr.async_build_timeline({**base, "tou_tier_source": "rate"})
    assert timeline is not None and timeline.current_tier == TOU_TIER_PEAK

    # auto (never touched): the legacy cascade — period wins.
    timeline = await mgr.async_build_timeline(base)
    assert timeline is not None and timeline.current_tier == TOU_TIER_PEAK


@pytest.mark.asyncio
async def test_tier_source_mode_has_no_fallback() -> None:
    """Explicit modes do not cascade: an unavailable period sensor stays unknown."""
    hass = _make_hass({"sensor.period": "unavailable", "sensor.rate": "0.22"})
    mgr = TouManager(hass)
    timeline = await mgr.async_build_timeline(
        {
            "tou_enabled": True,
            "tou_tier_source": "period",
            "tou_period_entity": "sensor.period",
            "tou_rate_entity": "sensor.rate",
            "tou_peak_threshold": 0.20,
        }
    )
    assert timeline is not None and timeline.current_tier == TOU_TIER_UNKNOWN
    assert timeline.current_rate == 0.22


@pytest.mark.asyncio
async def test_lookahead_mode_selects_the_future_source() -> None:
    """Calendar / next-change / none decide what RoomMind sees ahead."""
    now = time.time()
    cal_iso_start = dt_util.utc_from_timestamp(now + 1 * 3600.0).isoformat()
    cal_iso_end = dt_util.utc_from_timestamp(now + 4 * 3600.0).isoformat()
    nx_iso = dt_util.utc_from_timestamp(now + 2 * 3600.0).isoformat()
    hass = _make_hass({"sensor.period": "ulo_off_peak", "sensor.nx": nx_iso, "calendar.c": "on"})
    hass.services.async_call = AsyncMock(
        return_value={
            "calendar.c": {"events": [{"start": {"date_time": cal_iso_start}, "end": {"date_time": cal_iso_end}}]}
        }
    )
    mgr = TouManager(hass)
    base: dict = {
        "tou_enabled": True,
        "tou_period_entity": "sensor.period",
        "tou_calendar_entities": [{"entity_id": "calendar.c", "tier": "peak"}],
        "tou_next_change_entity": "sensor.nx",
        "tou_next_change_tier": "mid",
    }

    # auto: calendars cover the horizon window and win over next-change.
    timeline = await mgr.async_build_timeline(base)
    assert timeline is not None and timeline.tier_at(now + 2 * 3600.0) == TOU_TIER_PEAK

    # next_change: calendars ignored, the mid step lands at +2h.
    timeline = await mgr.async_build_timeline({**base, "tou_lookahead": "next_change"})
    assert timeline is not None
    assert timeline.tier_at(now + 1) == TOU_TIER_OFF
    assert timeline.tier_at(now + 2 * 3600.0 + 30) == TOU_TIER_MID

    # calendar: the next-change sensor is ignored.
    timeline = await mgr.async_build_timeline({**base, "tou_lookahead": "calendar"})
    assert timeline is not None and timeline.tier_at(now + 2 * 3600.0 + 30) == TOU_TIER_PEAK

    # none: flat current tier regardless of bindings.
    timeline = await mgr.async_build_timeline({**base, "tou_lookahead": "none"})
    assert timeline is not None
    assert len(timeline.segments) == 1
    assert timeline.tier_at(now + 2 * 3600.0) == TOU_TIER_OFF


@pytest.mark.asyncio
async def test_lookahead_next_change_rate() -> None:
    """The rate published for the period after the next change decides the tier."""
    now = time.time()
    future = now + 2 * 3600.0
    iso = dt_util.utc_from_timestamp(future).isoformat()
    hass = _make_hass(
        {
            "sensor.period": "ulo_off_peak",
            "sensor.nx": iso,
            "sensor.next_rate": "0.24",
        }
    )
    mgr = TouManager(hass)
    base: dict = {
        "tou_enabled": True,
        "tou_period_entity": "sensor.period",
        "tou_next_change_entity": "sensor.nx",
        "tou_next_rate_entity": "sensor.next_rate",
        "tou_next_change_tier": "off",  # fixed-tier choice must not win over the rate
        "tou_peak_threshold": 0.20,
    }

    timeline = await mgr.async_build_timeline({**base, "tou_lookahead": "next_change_rate"})
    assert timeline is not None
    assert timeline.tier_at(now + 60) == TOU_TIER_OFF
    assert timeline.tier_at(future + 30) == TOU_TIER_PEAK

    # explicit fixed-tier mode ignores the rate sensor entirely.
    timeline = await mgr.async_build_timeline({**base, "tou_lookahead": "next_change"})
    assert timeline is not None
    assert timeline.tier_at(future + 30) == TOU_TIER_OFF

    # legacy auto with no tier selected: a bound rate sensor is still used.
    timeline = await mgr.async_build_timeline({**base, "tou_next_change_tier": "", "tou_lookahead": "auto"})
    assert timeline is not None and timeline.tier_at(future + 30) == TOU_TIER_PEAK

    # unavailable next rate -> no guessing; the lookahead stays off.
    hass.states.get = MagicMock(
        side_effect={
            "sensor.period": _state("ulo_off_peak"),
            "sensor.nx": _state(iso),
            "sensor.next_rate": _state("unavailable"),
        }.get
    )
    timeline = await mgr.async_build_timeline({**base, "tou_lookahead": "next_change_rate"})
    assert timeline is not None and len(timeline.segments) == 1


def test_rate_window_events_and_guards() -> None:
    """Manual tariff rows paint tier events; inert input is ignored, never guessed.

    Horizon is 48 h, not the runtime's 16 h: the midnight-wrap case must find its
    next 23:00 occurrence at any wall-clock test time (16 h only covers it from
    ~07:00 onwards, making the assertion flaky outside that window).
    """
    now = time.time()
    horizon = now + 48 * 3600.0
    mgr = TouManager(_make_hass({}))

    # end == start wraps a full 24 h, so the window always covers "now".
    all_day = [{"id": "w1", "rate": 0.24, "start": "00:00", "end": "00:00", "days": []}]
    events = mgr._rate_window_events({"tou_peak_threshold": 0.20, "tou_rate_windows": all_day}, now, horizon)
    assert events and all(tier == TOU_TIER_PEAK for _, _, tier in events)
    assert any(start <= now < end for start, end, _ in events)

    # no thresholds configured -> rates cannot classify; rows stay inert.
    assert mgr._rate_window_events({"tou_rate_windows": all_day}, now, horizon) == []

    # a weekday that cannot occur inside the horizon matches nothing.
    today = dt_util.as_local(dt_util.utc_from_timestamp(now)).weekday()
    far = TOU_WEEKDAYS[(today + 3) % 7]
    inert = mgr._rate_window_events(
        {
            "tou_peak_threshold": 0.20,
            "tou_rate_windows": [{"id": "w2", "rate": 0.30, "start": "10:00", "end": "11:00", "days": [far]}],
        },
        now,
        horizon,
    )
    assert inert == []

    # end before start runs past midnight: two-hour events, never longer.
    wrapped = mgr._rate_window_events(
        {
            "tou_peak_threshold": 0.20,
            "tou_rate_windows": [{"id": "w3", "rate": 0.24, "start": "23:00", "end": "01:00", "days": []}],
        },
        now,
        horizon,
    )
    assert wrapped and all(0 < end - start <= 2 * 3600.0 for start, end, _ in wrapped)


@pytest.mark.asyncio
async def test_rate_window_paints_timeline_and_beats_next_change() -> None:
    """Windows are calendar-grade future: they paint over the tier and skip the fallback."""
    now = time.time()
    nx = dt_util.utc_from_timestamp(now + 2 * 3600.0).isoformat()
    hass = _make_hass({"sensor.period": "ulo_off_peak", "sensor.nx": nx})
    mgr = TouManager(hass)
    timeline = await mgr.async_build_timeline(
        {
            "tou_enabled": True,
            "tou_period_entity": "sensor.period",
            "tou_peak_threshold": 0.20,
            "tou_next_change_entity": "sensor.nx",
            "tou_next_change_tier": "mid",
            "tou_rate_windows": [{"id": "all", "rate": 0.24, "start": "00:00", "end": "00:00", "days": []}],
        }
    )
    assert timeline is not None
    assert timeline.tier_at(now + 60) == TOU_TIER_PEAK
    # windows count as events, so the next-change "mid" step never applies.
    assert timeline.tier_at(now + 2 * 3600.0 + 30) == TOU_TIER_PEAK


@pytest.mark.asyncio
async def test_calendar_service_failure_is_graceful() -> None:
    hass = _make_hass({"sensor.rate_period": "ulo_on_peak"})
    hass.services.async_call = AsyncMock(side_effect=RuntimeError("boom"))
    mgr = TouManager(hass)
    timeline = await mgr.async_build_timeline(
        {
            "tou_enabled": True,
            "tou_period_entity": "sensor.rate_period",
            "tou_calendar_entities": [{"entity_id": "calendar.x", "tier": "peak"}],
        }
    )
    assert timeline is not None
    assert timeline.current_tier == TOU_TIER_PEAK


# ---------------------------------------------------------------------------
# Future view
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_next_period_word_in_change_slot_still_shows_the_price() -> None:
    """A provider's period *name* in the next-change slot is understood.

    The Hydro One shape: "next peak" answers "ulo_mid_peak" where a timestamp
    is expected, "next_change_rate" is on, and no cost thresholds exist to
    classify the price. Old behavior: the future view died in silence and
    every other tier row read "no price". Now: the vocabulary recognition maps
    the name to the coming tier, the next-rate reading arrives with it, the
    missing clock is only hinted — never a blank — and the upcoming price
    lands in the persisted history. A stale fixed dropdown must not outrank
    the provider's own next-period answer.
    """
    hass = _make_hass(
        {
            "sensor.period": "ulo_overnight",
            "sensor.rate": "0.0638",
            "sensor.next_peak": "ulo_mid_peak",
            "sensor.next_rate": "0.1766",
        }
    )
    settings = {
        "tou_enabled": True,
        "tou_tier_source": "period",
        "tou_period_entity": "sensor.period",
        "tou_rate_entity": "sensor.rate",
        "tou_next_change_entity": "sensor.next_peak",
        "tou_next_rate_entity": "sensor.next_rate",
        "tou_next_change_tier": "off",  # stale user pick: must not win
        "tou_lookahead": "next_change_rate",
    }
    mgr = TouManager(hass)
    timeline = await mgr.async_build_timeline(settings)
    assert timeline is not None and len(timeline.segments) == 1  # no time -> no boundary

    info = mgr.tier_info(settings)
    assert info["next"] is not None
    assert info["next"]["ts"] is None and info["next"]["tier"] == TOU_TIER_MID
    assert info["next"]["rate"] == 0.1766 and info["next"]["stale"] is False
    assert info["next_hint"] == "no_time"
    assert info["tiers"][TOU_TIER_MID]["kind"] == "next"

    store = hass.data[DOMAIN]["store"]
    persisted = store.async_save_settings.call_args[0][0]["tou_price_history"]
    assert persisted[TOU_TIER_MID]["rate"] == 0.1766


@pytest.mark.asyncio
async def test_next_period_sensor_completes_the_future_view() -> None:
    """The dedicated next-period slot plus the timestamp gives the full view,
    and after the price source drops the persisted next-period value answers
    (marked stale, no nagging hint)."""
    future = time.time() + 2 * 3600.0
    hass = _make_hass(
        {
            "sensor.period": "ulo_overnight",
            "sensor.rate": "0.0638",
            "sensor.next_starts": dt_util.utc_from_timestamp(future).isoformat(),
            "sensor.next_peak": "ulo_mid_peak",
            "sensor.next_rate": "0.1766",
        }
    )
    settings = {
        "tou_enabled": True,
        "tou_tier_source": "period",
        "tou_period_entity": "sensor.period",
        "tou_rate_entity": "sensor.rate",
        "tou_next_change_entity": "sensor.next_starts",
        "tou_next_period_entity": "sensor.next_peak",
        "tou_next_rate_entity": "sensor.next_rate",
        "tou_lookahead": "next_change_rate",
    }
    mgr = TouManager(hass)
    timeline = await mgr.async_build_timeline(settings)
    assert timeline is not None and timeline.tier_at(future + 30) == TOU_TIER_MID

    info = mgr.tier_info(settings)
    assert info["next_hint"] == ""
    assert info["next"]["ts"] is not None and info["next"]["tier"] == TOU_TIER_MID
    assert info["next"]["rate"] == 0.1766

    # Provider blip: the observed next-period price keeps the view honest.
    good = {
        "sensor.period": _state("ulo_overnight"),
        "sensor.rate": _state("0.0638"),
        "sensor.next_starts": _state(dt_util.utc_from_timestamp(future).isoformat()),
        "sensor.next_peak": _state("ulo_mid_peak"),
        "sensor.next_rate": _state("unavailable"),
    }
    hass.states.get = MagicMock(side_effect=good.get)
    info2 = mgr.tier_info(settings)
    assert info2["next"]["tier"] == TOU_TIER_MID
    assert info2["next"]["rate"] == 0.1766 and info2["next"]["stale"] is True
    assert info2["next_hint"] == ""


@pytest.mark.asyncio
async def test_next_hint_reports_what_the_future_view_is_missing() -> None:
    """Future sensors bound but unable to answer leave an honest hint, not a
    silent "no price" row."""

    # Timestamp fine, but nothing says which tier follows: no_tier.
    future = time.time() + 2 * 3600.0
    hass = _make_hass({"sensor.period": "ulo_overnight", "sensor.nx": dt_util.utc_from_timestamp(future).isoformat()})
    mgr = TouManager(hass)
    settings = {
        "tou_enabled": True,
        "tou_period_entity": "sensor.period",
        "tou_next_change_entity": "sensor.nx",
    }
    await mgr.async_build_timeline(settings)
    assert mgr.tier_info(settings)["next_hint"] == "no_tier"

    # Tier and time known, next-rate bound but dead and no history: no_price.
    hass2 = _make_hass(
        {
            "sensor.period": "ulo_overnight",
            "sensor.nx": dt_util.utc_from_timestamp(future).isoformat(),
            "sensor.nx_rate": "unavailable",
        }
    )
    mgr2 = TouManager(hass2)
    settings2 = {
        "tou_enabled": True,
        "tou_period_entity": "sensor.period",
        "tou_next_change_entity": "sensor.nx",
        "tou_next_change_tier": TOU_TIER_MID,
        "tou_next_rate_entity": "sensor.nx_rate",
    }
    await mgr2.async_build_timeline(settings2)
    assert mgr2.tier_info(settings2)["next_hint"] == "no_price"


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


def test_snapshot_disabled() -> None:
    mgr = TouManager(_make_hass({}))
    snap = mgr.snapshot()
    assert snap["enabled"] is False
    assert snap["tier"] == TOU_TIER_UNKNOWN


def test_tier_at_empty_and_past_horizon() -> None:
    timeline = TouTimeline([], current_tier=TOU_TIER_UNKNOWN, current_rate=None)
    assert timeline.tier_at(time.time()) == TOU_TIER_UNKNOWN

    full = _timeline((TOU_TIER_OFF, 60))
    assert full.tier_at(full.segments[0].start - 5) == TOU_TIER_OFF
    assert full.tier_at(full.segments[-1].end + 999999) == TOU_TIER_OFF


# ---------------------------------------------------------------------------
# Source parser guards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unavailable_period_falls_back_through_chain() -> None:
    """Missing/unavailable sources degrade to tier unknown without raising."""
    hass = _make_hass({"sensor.period": "unavailable", "sensor.rate": "not_a_number"})
    mgr = TouManager(hass)
    timeline = await mgr.async_build_timeline(
        {
            "tou_enabled": True,
            "tou_period_entity": "sensor.period",
            "tou_rate_entity": "sensor.rate",
            "tou_flag_entities": "not-a-dict",
        }
    )
    assert timeline is not None
    assert timeline.current_tier == TOU_TIER_UNKNOWN
    assert timeline.current_rate is None


@pytest.mark.asyncio
async def test_flag_entity_missing_or_not_string() -> None:
    """Flags entries with empty ids or wrong types are skipped."""
    hass = _make_hass({"input_boolean.on_flag": "on"})
    mgr = TouManager(hass)
    timeline = await mgr.async_build_timeline(
        {
            "tou_enabled": True,
            "tou_flag_entities": {"mid": "", "peak": 42, "off": "input_boolean.on_flag"},
        }
    )
    assert timeline is not None
    assert timeline.current_tier == TOU_TIER_OFF


@pytest.mark.asyncio
async def test_calendar_entry_validation_skips_bad_rows() -> None:
    """Calendar rows without an entity or with an unknown tier are ignored."""
    hass = _make_hass({"sensor.period": "ulo_on_peak"})
    mgr = TouManager(hass)
    timeline = await mgr.async_build_timeline(
        {
            "tou_enabled": True,
            "tou_period_entity": "sensor.period",
            "tou_calendar_entities": [
                {"entity_id": "", "tier": "peak"},
                {"entity_id": "calendar.x", "tier": "bogus"},
            ],
        }
    )
    assert timeline is not None
    assert timeline.current_tier == TOU_TIER_PEAK
    assert len(timeline.segments) == 1


@pytest.mark.asyncio
async def test_calendar_payload_shapes_skipped() -> None:
    """Non-dict events and unparseable payloads never become segments."""
    hass = _make_hass({"sensor.period": "ulo_off_peak"})
    hass.services.async_call = AsyncMock(
        return_value={
            "calendar.x": {
                "events": [
                    "not-a-dict",
                    {"start": "garbage", "end": {"date_time": "2026-11-06T07:00:00-05:00"}},
                    {"start": {"date_time": "nope"}, "end": {"date_time": "nope"}},
                ]
            }
        }
    )
    mgr = TouManager(hass)
    timeline = await mgr.async_build_timeline(
        {
            "tou_enabled": True,
            "tou_period_entity": "sensor.period",
            "tou_calendar_entities": [{"entity_id": "calendar.x", "tier": "peak"}],
        }
    )
    assert timeline is not None
    assert len(timeline.segments) == 1


@pytest.mark.asyncio
async def test_next_change_guards() -> None:
    """Unavailable, unparseable or bogus next-change readings fall back safely."""
    hass = _make_hass(
        {
            "sensor.period": "ulo_off_peak",
            "sensor.nx1": "unavailable",
            "sensor.nx2": "not-a-date",
        }
    )
    mgr = TouManager(hass)
    timeline = await mgr.async_build_timeline(
        {
            "tou_enabled": True,
            "tou_period_entity": "sensor.period",
            "tou_next_change_entity": "sensor.nx1",
        }
    )
    assert timeline is not None and len(timeline.segments) == 1

    timeline = await mgr.async_build_timeline(
        {
            "tou_enabled": True,
            "tou_period_entity": "sensor.period",
            "tou_next_change_entity": "sensor.nx2",
        }
    )
    assert timeline is not None and len(timeline.segments) == 1

    # A valid timestamp with an unknown tier name: no guessing — the
    # lookahead stays off entirely (same as "Not set").
    future = time.time() + 3600.0
    hass.states.get = MagicMock(
        side_effect={
            "sensor.period": _state("ulo_off_peak"),
            "sensor.nx3": _state(dt_util.utc_from_timestamp(future).isoformat()),
        }.get
    )
    timeline = await mgr.async_build_timeline(
        {
            "tou_enabled": True,
            "tou_period_entity": "sensor.period",
            "tou_next_change_entity": "sensor.nx3",
            "tou_next_change_tier": "bogus",
        }
    )
    assert timeline is not None and len(timeline.segments) == 1
    assert timeline.tier_at(future + 30) == TOU_TIER_OFF

    timeline = await mgr.async_build_timeline(
        {
            "tou_enabled": True,
            "tou_period_entity": "sensor.period",
            "tou_next_change_entity": "sensor.nx3",
            "tou_next_change_tier": "",
        }
    )
    assert timeline is not None and len(timeline.segments) == 1
    assert timeline.tier_at(future + 30) == TOU_TIER_OFF


# ---------------------------------------------------------------------------
# Parity sources: forecast curve, relative ranking, switch/event
# ---------------------------------------------------------------------------


def _entity_hass(eid: str, state: str, attributes: dict) -> MagicMock:
    """A hass whose single entity reports *state* with *attributes*."""
    hass = _make_hass({})
    s = MagicMock()
    s.state = state
    s.attributes = {"unit_of_measurement": "EUR/kWh", **attributes}
    hass.states.get = MagicMock(side_effect=lambda wanted, _s=s: _s if wanted == eid else None)
    return hass


def _hourly_items(now: float, prices: list[float]) -> list[dict]:
    base = math.floor(now / 3600.0) * 3600.0
    return [
        {
            "start_time": dt_util.utc_from_timestamp(base + i * 3600.0).isoformat(),
            "end_time": dt_util.utc_from_timestamp(base + (i + 1) * 3600.0).isoformat(),
            "price": p,
        }
        for i, p in enumerate(prices)
    ]


@pytest.mark.asyncio
async def test_forecast_curve_with_thresholds_builds_segments() -> None:
    """A sensor publishing raw_today is a calendar the utility maintains: its
    hours land in the timeline, tiered by the configured thresholds."""
    now = time.time()
    base = math.floor(now / 3600.0) * 3600.0
    hass = _entity_hass("sensor.price", "0.10", {"raw_today": _hourly_items(now, [0.10, 0.05, 0.35, 0.05])})
    mgr = TouManager(hass)
    timeline = await mgr.async_build_timeline(
        {"tou_enabled": True, "tou_rate_entity": "sensor.price", "tou_peak_threshold": 0.30, "tou_mid_threshold": 0.09}
    )
    assert timeline is not None
    assert timeline.current_tier == TOU_TIER_MID  # 0.10 >= 0.09 mid
    assert timeline.tier_at(base + 2 * 3600.0 + 60) == TOU_TIER_PEAK  # the 0.35 hour
    assert timeline.tier_at(base + 3600.0 + 60) == TOU_TIER_OFF  # between: 0.05
    snap = mgr.snapshot()
    assert snap["next_tier"] == TOU_TIER_OFF  # first boundary: the cheap hour
    # The forecast is the future view: no next-change sensor was bound.


@pytest.mark.asyncio
async def test_forecast_without_thresholds_ranks_own_bands() -> None:
    """No thresholds: the curve classifies against its own spread (ported
    price-manager rule) — expensive hours peak, cheap hours off."""
    now = time.time()
    base = math.floor(now / 3600.0) * 3600.0
    prices = [0.30, 0.02, 0.30, 0.10, 0.35, 0.02, 0.20, 0.05]
    hass = _entity_hass("sensor.price", str(prices[0]), {"raw_today": _hourly_items(now, prices)})
    mgr = TouManager(hass)
    timeline = await mgr.async_build_timeline({"tou_enabled": True, "tou_rate_entity": "sensor.price"})
    assert timeline is not None
    assert timeline.tier_at(base + 2 * 3600.0 + 60) == TOU_TIER_PEAK  # 0.30 in the top band
    assert timeline.tier_at(base + 5 * 3600.0 + 60) == TOU_TIER_OFF  # 0.02 bottom band


@pytest.mark.asyncio
async def test_flat_forecast_stays_inert() -> None:
    """A flat curve has no bands to rank by: no segments are painted — the
    horizon stays exactly what the current tier is (never a guessed peak)."""
    now = time.time()
    hass = _entity_hass("sensor.price", "0.12", {"raw_today": _hourly_items(now, [0.12] * 6)})
    mgr = TouManager(hass)
    timeline = await mgr.async_build_timeline({"tou_enabled": True, "tou_rate_entity": "sensor.price"})
    assert timeline is not None and len(timeline.segments) == 1


@pytest.mark.asyncio
async def test_relative_ranking_from_seeded_history() -> None:
    """Threshold-free ranking, the base price manager's trick: rank today's
    price against the observed history — seeded from the recorded history so
    it works right after a restart, not after 12 h of uptime."""
    now = time.time()
    history = [(now - h * 3600.0, 0.05 + (h % 5) * 0.05) for h in range(2, 26)]
    loader = AsyncMock(return_value=history)

    high = TouManager(_make_hass({"sensor.price": "0.40"}))
    timeline = await high.async_build_timeline(
        {"tou_enabled": True, "tou_rate_entity": "sensor.price"}, history_loader=loader
    )
    assert timeline is not None and timeline.current_tier == TOU_TIER_PEAK

    low = TouManager(_make_hass({"sensor.price": "0.05"}))
    timeline2 = await low.async_build_timeline(
        {"tou_enabled": True, "tou_rate_entity": "sensor.price"}, history_loader=loader
    )
    assert timeline2 is not None and timeline2.current_tier == TOU_TIER_OFF

    # Without the seed (fresh process, thin history) ranking cannot answer
    # honestly, and the legacy no-threshold behaviour keeps the floor: off.
    bare = TouManager(_make_hass({"sensor.price": "0.40"}))
    timeline3 = await bare.async_build_timeline({"tou_enabled": True, "tou_rate_entity": "sensor.price"})
    assert timeline3 is not None and timeline3.current_tier == TOU_TIER_OFF


def test_relative_steady_gate_holds_flicker() -> None:
    """A relative tier change applies only once it held TOU_LEVEL_HOLD_S
    (ported hysteresis): the first reading is immediate."""
    mgr = TouManager(_make_hass({}))
    assert mgr._steady_tier(TOU_TIER_PEAK, 1000.0) == TOU_TIER_PEAK
    assert mgr._steady_tier(TOU_TIER_OFF, 1100.0) == TOU_TIER_PEAK  # 100 s: still held
    assert mgr._steady_tier(TOU_TIER_OFF, 2001.0) == TOU_TIER_OFF  # held 901 s ≥ 900


@pytest.mark.asyncio
async def test_switch_rate_source_maps_tiers() -> None:
    """The base feature accepted a switch that is on while energy is cheap;
    bound as the rate entity it reads as off-peak, and mid when not on."""
    on = TouManager(_entity_hass("input_boolean.pv_surplus", "on", {}))
    timeline = await on.async_build_timeline({"tou_enabled": True, "tou_rate_entity": "input_boolean.pv_surplus"})
    assert timeline is not None and timeline.current_tier == TOU_TIER_OFF

    off = TouManager(_entity_hass("input_boolean.pv_surplus", "off", {}))
    timeline2 = await off.async_build_timeline({"tou_enabled": True, "tou_rate_entity": "input_boolean.pv_surplus"})
    assert timeline2 is not None and timeline2.current_tier == TOU_TIER_MID


@pytest.mark.asyncio
async def test_event_domain_forecast_source() -> None:
    """Octopus publishes rates on an event entity: the state is a timestamp,
    the prices sit in the attributes — the current slot gives tier AND price,
    later slots give the timeline."""
    now = time.time()
    base = math.floor(now / 3600.0) * 3600.0
    items = [
        {
            "from": dt_util.utc_from_timestamp(base + i * 3600.0).isoformat(),
            "to": dt_util.utc_from_timestamp(base + (i + 1) * 3600.0).isoformat(),
            "value": p,
        }
        for i, p in enumerate([0.40, 0.03, 0.28, 0.05])
    ]
    hass = _entity_hass("event.octopus_rates", dt_util.utc_from_timestamp(base - 7200.0).isoformat(), {"rates": items})
    mgr = TouManager(hass)
    timeline = await mgr.async_build_timeline({"tou_enabled": True, "tou_rate_entity": "event.octopus_rates"})
    assert timeline is not None
    assert timeline.current_tier == TOU_TIER_PEAK  # 0.40 tops the curve's bands
    assert timeline.tier_at(base + 3600.0 + 30) == TOU_TIER_OFF
    snap = mgr.snapshot()
    assert snap["rate"] == 0.40  # the event's current slot is a real price
    assert snap["next_tier"] == TOU_TIER_OFF


@pytest.mark.asyncio
async def test_calendar_and_windows_beat_the_forecast() -> None:
    """The forecast is the fallback future: bound calendars (or manual
    windows) own the horizon and the curve is not consulted."""
    now = time.time()
    cal_start = dt_util.utc_from_timestamp(now + 1800.0).isoformat()
    cal_end = dt_util.utc_from_timestamp(now + 2 * 3600.0).isoformat()
    price_state = MagicMock()
    price_state.state = "0.10"
    price_state.attributes = {
        "unit_of_measurement": "EUR/kWh",
        "raw_today": _hourly_items(now, [0.10, 0.10, 0.35, 0.35]),
    }
    cal_state = MagicMock()
    cal_state.state = "on"
    lookup = {"sensor.price": price_state, "calendar.c": cal_state}
    hass = _make_hass({})
    hass.states.get = MagicMock(side_effect=lookup.get)
    hass.services.async_call = AsyncMock(
        return_value={"calendar.c": {"events": [{"start": {"date_time": cal_start}, "end": {"date_time": cal_end}}]}}
    )
    mgr = TouManager(hass)
    timeline = await mgr.async_build_timeline(
        {
            "tou_enabled": True,
            "tou_rate_entity": "sensor.price",
            "tou_calendar_entities": [{"entity_id": "calendar.c", "tier": "mid"}],
        }
    )
    assert timeline is not None
    # The calendar owns the horizon: its mid window paints the hours it
    # covers, and the forecast's 0.35 peak hours were never consulted —
    # after the window ends the tier falls back to the current, not to the
    # curve.
    assert timeline.tier_at(now + 3600.0) == TOU_TIER_MID  # inside the calendar window
    assert timeline.tier_at(now + 3 * 3600.0) == TOU_TIER_OFF


# ---------------------------------------------------------------------------
# Electricity-price adapter (D1 supersession)
# ---------------------------------------------------------------------------


def test_price_signal_maps_tiers_to_levels() -> None:
    """The surviving price consumers read the tariff through the old signal
    interface: levels from the tier ladder, charge direction from the coming
    expensive stretch, and per-tier last-known costs behind the live hour."""
    mgr = TouManager(_make_hass({}))
    now = time.time()
    mgr._timeline = TouTimeline(
        [TouSegment(now, now + 3600.0, TOU_TIER_OFF), TouSegment(now + 3600.0, now + 2 * 3600.0, TOU_TIER_PEAK)],
        current_tier=TOU_TIER_OFF,
        current_rate=0.05,
    )
    mgr._price_history = {
        TOU_TIER_PEAK: {"rate": 0.42, "unit": "EUR/kWh", "ts": now, "count": 3, "min": 0.4, "max": 0.44}
    }
    sig = mgr.price_signal()
    assert sig is not None
    assert sig.current_level == "cheap"
    assert sig.level_at(now + 1.5 * 3600.0) == "expensive"
    assert sig.direction_at(now) == 1  # cheap now, an expensive hour follows at once
    assert sig.direction_at(now + 1.5 * 3600.0) == -1
    assert sig.price_at(now) == 0.05  # the live reading covers the current hour
    assert sig.price_at(now + 1.5 * 3600.0) == 0.42  # the peak tier's known cost

    mgr._timeline = None
    assert mgr.price_signal() is None  # before the first cycle: no signal, shifts off


def test_price_signal_flat_horizon_behaves_like_the_base_without_forecast() -> None:
    """One segment is the base's no-forecast case: cheap charges ahead
    regardless, an unknown tariff says nothing and shifts nothing."""
    mgr = TouManager(_make_hass({}))
    now = time.time()
    mgr._timeline = TouTimeline(
        [TouSegment(now, now + 3600.0, TOU_TIER_OFF)], current_tier=TOU_TIER_OFF, current_rate=0.05
    )
    sig = mgr.price_signal()
    assert sig.direction_at(now) == 1
    assert sig.has_forecast is False

    mgr._timeline = TouTimeline(
        [TouSegment(now, now + 3600.0, TOU_TIER_UNKNOWN)], current_tier=TOU_TIER_UNKNOWN, current_rate=None
    )
    sig2 = mgr.price_signal()
    assert sig2.current_level is None
    assert sig2.direction_at(now) == 0


# ---------------------------------------------------------------------------
# Store layer
# ---------------------------------------------------------------------------


def _room(**overrides) -> dict:
    room = {
        "area_id": "living",
        "comfort_heat": 21.0,
        "comfort_cool": 24.0,
        "eco_heat": 17.0,
        "eco_cool": 27.0,
    }
    room.update(overrides)
    return room


def test_store_relaxes_expensive_run() -> None:
    mgr = TouManager(_make_hass({}))
    mgr._timeline = _timeline((TOU_TIER_OFF, 0), (TOU_TIER_PEAK, 120))
    adjust = mgr.make_adjuster(_room(tou_store_enabled=True), {"tou_enabled": True})
    assert adjust is not None
    ts = time.time() + 60.0
    result = adjust(ts, TargetTemps(heat=21.0, cool=24.0))
    assert result.heat == 18.0  # swung down from 21, floor above band & eco
    assert result.cool == 27.0  # drifts up toward the eco cooling target


def test_store_never_raises_a_colder_schedule() -> None:
    mgr = TouManager(_make_hass({}))
    mgr._timeline = _timeline((TOU_TIER_OFF, 0), (TOU_TIER_PEAK, 120))
    adjust = mgr.make_adjuster(_room(tou_store_enabled=True), {})
    assert adjust is not None
    result = adjust(time.time() + 60.0, TargetTemps(heat=16.0, cool=20.0))
    assert result.heat == 16.0  # relaxation only lowers, never raises heat
    assert result.cool == 23.0  # cooling relaxes upward by the swing


def test_store_run_merges_contiguous_expensive_tiers() -> None:
    """Mid + peak in a row are one coast: relaxation starts at the mid tier."""
    mgr = TouManager(_make_hass({}))
    mgr._timeline = _timeline((TOU_TIER_OFF, 0), (TOU_TIER_MID, 60), (TOU_TIER_PEAK, 60))
    adjust = mgr.make_adjuster(_room(tou_store_enabled=True), {})
    assert adjust is not None
    result = adjust(time.time() + 30 * 60, TargetTemps(heat=21.0, cool=24.0))
    assert result.heat == 18.0
    assert result.cool == 27.0


def test_store_is_quiet_without_a_run() -> None:
    """Cheap tier, nothing expensive ahead: no relaxation, no pre-charge —
    even with a learned decay model that could coast somewhere."""
    mgr = TouManager(_make_hass({}))
    mgr._timeline = _timeline((TOU_TIER_ULTRA_LOW, 120))
    adjust = mgr.make_adjuster(_room(tou_store_enabled=True), {}, decay=(0.2, 8.0))
    assert adjust is not None
    out = adjust(time.time() + 60.0, TargetTemps(heat=21.0, cool=24.0))
    assert out.heat == 21.0 and out.cool == 24.0

    off = mgr.make_adjuster(_room(), {}, decay=(0.2, 8.0))
    assert off is None  # no store: no participation
    forced_off = adjust(time.time() + 60.0, TargetTemps(heat=None, cool=None))
    assert forced_off == TargetTemps(heat=None, cool=None)  # off stays off


def test_store_precharge_bounds_and_gates() -> None:
    """Raise toward the coast floor before a run, bounded by the swing and the
    consent band; skipped for vacation and immature models; presence-blind."""
    mgr = TouManager(_make_hass({}))
    b = time.time()
    mgr._timeline = _timeline((TOU_TIER_ULTRA_LOW, 60), (TOU_TIER_PEAK, 300))
    ts = b + 30 * 60  # mid cheap window, the (long) peak still ahead
    decay = (0.2, 10.0)
    room = _room(tou_store_enabled=True)

    raised = mgr.make_adjuster(room, {}, decay=decay)
    assert raised is not None
    # floor_end 18, huge lead -> needed() explodes -> the swing cap rules: 21 + 3.
    assert raised(ts, TargetTemps(heat=21.0, cool=None)).heat == 24.0

    capped = mgr.make_adjuster({**room, "tou_heat_max": 22.5}, {}, decay=decay)
    assert capped is not None
    assert capped(ts, TargetTemps(heat=21.0, cool=None)).heat == 22.5  # the band wins

    vacant = mgr.make_adjuster(room, {}, room_vacant=True, presence_away=True, decay=decay)
    assert vacant is not None
    assert vacant(ts, TargetTemps(heat=21.0, cool=None)).heat == 24.0  # economics, not occupancy

    vacation = {"vacation_until": b + 3600.0, "vacation_temp": 15.0}
    vac = mgr.make_adjuster(room, vacation, decay=decay)
    assert vac is not None
    assert vac(ts, TargetTemps(heat=21.0, cool=None)).heat == 21.0  # no pre-charge in vacation

    inside = mgr.make_adjuster(room, {}, decay=decay)
    assert inside is not None
    assert inside(b + 90 * 60, TargetTemps(heat=21.0, cool=None)).heat == 18.0  # the run relaxes

    no_model = mgr.make_adjuster(room, {})
    assert no_model is not None
    assert no_model(ts, TargetTemps(heat=21.0, cool=None)).heat == 21.0  # nothing to derive from


def test_store_prechills_and_relaxes_cooling_run() -> None:
    """Cooling mirrors heating: drift up toward the eco ceiling during an
    expensive run, pre-chill within the swing before it, and degrade the
    same way (no chill without a model, none during vacation)."""
    mgr = TouManager(_make_hass({}))
    b = time.time()
    mgr._timeline = _timeline((TOU_TIER_OFF, 60), (TOU_TIER_PEAK, 600))
    ts = b + 30 * 60  # inside the off stretch, the (long) peak ahead
    room = _room(tou_store_enabled=True)

    chilled = mgr.make_adjuster(room, {}, decay=(0.2, 35.0))
    assert chilled is not None
    assert chilled(ts, TargetTemps(heat=None, cool=24.0)).cool == 21.0

    inside = mgr.make_adjuster(room, {}, decay=(0.2, 35.0))
    assert inside is not None
    assert inside(b + 90 * 60, TargetTemps(heat=None, cool=24.0)).cool == 27.0

    no_model = mgr.make_adjuster(room, {})
    assert no_model is not None
    assert no_model(ts, TargetTemps(heat=None, cool=24.0)).cool == 24.0

    vacation = {"vacation_until": b + 3600.0, "vacation_temp": 28.0}
    vac = mgr.make_adjuster(room, vacation, decay=(0.2, 35.0))
    assert vac is not None
    assert vac(ts, TargetTemps(heat=None, cool=24.0)).cool == 24.0

    mild = mgr.make_adjuster(room, {}, decay=(0.2, 20.0))
    assert mild is not None
    assert mild(ts, TargetTemps(heat=None, cool=24.0)).cool == 24.0


def test_override_never_shaved() -> None:
    mgr = TouManager(_make_hass({}))
    mgr._timeline = _timeline((TOU_TIER_PEAK, 120))
    room = _room(tou_store_enabled=True, override_heat=24.0, override_cool=None, override_until=None)
    adjust = mgr.make_adjuster(room, {})
    assert adjust is not None
    result = adjust(time.time() + 60.0, TargetTemps(heat=24.0, cool=27.0))
    assert result.heat == 24.0  # the override value passes through untouched


def test_mold_active_blocks_heat_relaxation() -> None:
    mgr = TouManager(_make_hass({}))
    mgr._timeline = _timeline((TOU_TIER_PEAK, 120))
    adjust = mgr.make_adjuster(_room(tou_store_enabled=True), {}, mold_active=True)
    assert adjust is not None
    result = adjust(time.time() + 60.0, TargetTemps(heat=21.0, cool=24.0))
    assert result.heat == 21.0  # prevention outranks tariff relaxation
    assert result.cool == 27.0  # cooling side is unaffected


def test_price_builder_gating() -> None:
    mgr = TouManager(_make_hass({}))
    mgr._timeline = _timeline((TOU_TIER_OFF, 60), (TOU_TIER_PEAK, 60))
    builder = mgr.make_price_series_builder(_room(tou_store_enabled=True), {"tou_enabled": True})
    assert builder is not None
    # One hour per block: block 0 sits in OFF, the rest land past the +60min boundary.
    series = builder(time.time(), 4, 60.0)
    assert series[0] == 1.0  # off
    assert series[-1] == 3.0  # peak
    assert mgr.make_price_series_builder(_room(), {}) is None
    assert mgr.make_price_series_builder(_room(), {"tou_price_weighting": False}) is None
    no_timeline = TouManager(_make_hass({}))
    assert no_timeline.make_price_series_builder(_room(), {}) is None


# ---------------------------------------------------------------------------
# Tariff rule library: rows -> records -> windows
# ---------------------------------------------------------------------------


def _room_schedule(*defs: dict, enabled: bool = True) -> tuple[dict, dict]:
    """(room, settings) pair wiring card-style references to a shared library.

    Each definition becomes a ``tou_rules`` entry (id ``rl{i}``) and one
    ``tou_overrides`` row referencing it; the room's schedule section is on
    unless ``enabled`` says otherwise.
    """
    rules = [{"id": f"rl{i}", "name": f"rule {i}", **d} for i, d in enumerate(defs)]
    rows = [{"id": f"row{i}", "rule_id": f"rl{i}", "enabled": True} for i in range(len(defs))]
    room = _room(tou_schedule_enabled=enabled, tou_overrides=rows)
    return room, {"tou_rules": rules}


def _two_tier_timeline(first_tier: str, boundary_offset: float = 30.0) -> TouTimeline:
    """One short segment now, then a tier that runs to the horizon's end."""
    boundary = time.time() + boundary_offset
    return TouTimeline(
        [
            TouSegment(start=time.time(), end=boundary, tier=first_tier),
            TouSegment(start=boundary, end=time.time() + 16 * 3600.0, tier=TOU_TIER_PEAK),
        ],
        current_tier=first_tier,
        current_rate=None,
    )


def test_row_window_duration_end() -> None:
    mgr = TouManager(_make_hass({}))
    boundary = time.time() + 30.0
    mgr._timeline = TouTimeline(
        [
            TouSegment(start=time.time(), end=boundary, tier=TOU_TIER_OFF),
            TouSegment(start=boundary, end=boundary + 3600, tier=TOU_TIER_PEAK),
            TouSegment(start=boundary + 3600, end=time.time() + 16 * 3600, tier=TOU_TIER_OFF),
        ],
        current_tier=TOU_TIER_OFF,
        current_rate=None,
    )
    room, settings = _room_schedule(
        {
            "tier": "peak",
            "edge": "start",
            "action": "set",
            "heat": 19.0,
            "cool": None,
            "until": "minutes",
            "minutes": 30,
        }
    )
    adjust = mgr.make_adjuster(room, settings)
    assert adjust is not None
    # Inside the row window: the rule's temperature replaces the schedule.
    inside = adjust(boundary + 120, TargetTemps(heat=21.0, cool=24.0))
    assert inside.heat == 19.0
    # Blank cool side: the rule skips cooling; the plain target stands.
    assert inside.cool == 24.0
    # After the 30-minute hold (still inside the peak segment): schedule resumes.
    assert adjust(boundary + 31 * 60, TargetTemps(heat=21.0, cool=24.0)).heat == 21.0


def test_record_tier_change_end_with_cap() -> None:
    mgr = TouManager(_make_hass({}))
    boundary = time.time() + 30.0
    # A peak that never ends within the horizon: the tier-change end falls back to the cap.
    mgr._timeline = TouTimeline(
        [
            TouSegment(start=time.time(), end=boundary, tier=TOU_TIER_ULTRA_LOW),
            TouSegment(start=boundary, end=time.time() + 16 * 3600, tier=TOU_TIER_PEAK),
        ],
        current_tier=TOU_TIER_ULTRA_LOW,
        current_rate=None,
    )
    settings = {
        "tou_coast_max_minutes": 90,
        "tou_schedules": [
            {
                "id": "r1-heat",
                "name": "hold to cheap",
                "enabled": True,
                "rooms": ["living"],
                "side": "heat",
                "tier": "peak",
                "edge": "start",
                "phase": "after",
                "until": "next_tier_change",
                "until_tier": "ultra_low",
                "value": {"mode": "set", "temp": 19.0},
            }
        ],
    }
    adjust = mgr.make_adjuster(_room(), settings)
    assert adjust is not None
    assert adjust(boundary + 120, TargetTemps(heat=21.0, cool=24.0)).heat == 19.0
    assert adjust(boundary + 91 * 60, TargetTemps(heat=21.0, cool=24.0)).heat == 21.0


def test_row_side_blanks_skip_per_mode() -> None:
    """A blank rule side skips that mode; plain shaping applies there."""
    mgr = TouManager(_make_hass({}))
    boundary = time.time() + 30.0
    mgr._timeline = _two_tier_timeline(TOU_TIER_ULTRA_LOW)

    def row(**extra: object) -> dict:
        base: dict = {
            "tier": "peak",
            "edge": "start",
            "action": "set",
            "until": "minutes",
            "minutes": 120,
        }
        base.update(extra)
        return base

    # Both sides set: each gets its own value within the same window.
    room, settings = _room_schedule(row(heat=18.5, cool=26.0))
    adjust = mgr.make_adjuster(room, settings)
    assert adjust is not None
    out = adjust(boundary + 60.0, TargetTemps(heat=21.0, cool=24.0))
    assert out.heat == 18.5
    assert out.cool == 26.0

    # Heating blank: the rule is skipped there (plain target stands), cooling holds.
    room, settings = _room_schedule(row(heat=None, cool=26.0))
    adjust = mgr.make_adjuster(room, settings)
    assert adjust is not None
    out = adjust(boundary + 60.0, TargetTemps(heat=21.0, cool=24.0))
    assert out.heat == 21.0
    assert out.cool == 26.0

    # Both blank: no window at all — with no store layer there is nothing
    # for the adjuster to do.
    room, settings = _room_schedule(row(heat=None, cool=None))
    assert mgr.make_adjuster(room, settings) is None


def test_row_window_ends_at_next_boundary() -> None:
    """A tier-window end closes the row window at the next tier change."""
    mgr = TouManager(_make_hass({}))
    now = time.time()
    b1 = now + 60.0
    b2 = now + 120.0
    mgr._timeline = TouTimeline(
        [
            TouSegment(start=now, end=b1, tier=TOU_TIER_OFF),
            TouSegment(start=b1, end=b2, tier=TOU_TIER_PEAK),
            TouSegment(start=b2, end=now + 16 * 3600.0, tier=TOU_TIER_OFF),
        ],
        current_tier=TOU_TIER_OFF,
        current_rate=None,
    )
    room, settings = _room_schedule(
        {"tier": "peak", "edge": "start", "action": "set", "heat": 19.0, "until": "tier_window"}
    )
    adjust = mgr.make_adjuster(room, settings)
    assert adjust is not None
    assert adjust(b1 + 5.0, TargetTemps(heat=21.0, cool=24.0)).heat == 19.0
    # After the peak->off boundary the schedule target returns untouched.
    assert adjust(b2 + 5.0, TargetTemps(heat=21.0, cool=24.0)).heat == 21.0


def test_row_records_expansion() -> None:
    """Referenced shared rules fan out into one engine record per set side."""
    rules = TouManager.rule_library(
        {
            "tou_rules": [
                {
                    "id": "d",
                    "name": "mid-peak relax",
                    "tier": "mid",
                    "edge": "start",
                    "action": "raise",
                    "heat": 2.0,
                    "cool": 3.0,
                    "until": "minutes",
                    "minutes": 90,
                    "days": ["monday"],
                    "between": {"from": "17:00", "to": "22:00"},
                },
                {
                    "id": "a2",
                    "name": "warm by nine",
                    "tier": "ultra_low",
                    "edge": "end",
                    "action": "arrive",
                    "heat": 20.0,
                    "cool": None,
                    "clock": "09:00",
                },
                {"id": "l", "name": "lower", "tier": "any", "edge": "start", "action": "lower", "heat": -2.0},
            ]
        }
    )
    room = _room(
        tou_schedule_enabled=True,
        tou_overrides=[
            {"id": "r1", "rule_id": "d", "enabled": True},
            {"id": "r2", "rule_id": "a2", "enabled": True},
            {"id": "r3", "rule_id": "l", "enabled": True},
        ],
    )
    recs = TouManager.row_records(room, rules)
    by_id = {r["id"]: r for r in recs}
    assert len(recs) == 4
    heat = by_id["d-heat"]
    assert heat["side"] == "heat" and heat["rooms"] == ["living"]
    assert heat["value"] == {"mode": "shift", "direction": "raise", "delta": 2.0}
    assert heat["until"] == "minutes" and heat["minutes"] == 90
    assert heat["days"] == ["monday"] and heat["between"] == {"from": "17:00", "to": "22:00"}
    assert by_id["d-cool"]["value"]["delta"] == 3.0
    arrive = by_id["a2-heat"]
    assert arrive["value"] == {"mode": "arrive", "temp": 20.0}
    assert arrive["until"] == "clock" and arrive["clock"] == "09:00"
    assert arrive["tier"] == "ultra_low" and arrive["edge"] == "end" and arrive["phase"] == "after"
    lower = by_id["l-heat"]
    assert lower["value"] == {"mode": "shift", "direction": "lower", "delta": 2.0}


def test_row_records_ignores_broken_references() -> None:
    """Dangling, disabled, non-dict and legacy inline rows compile to nothing."""
    rules = TouManager.rule_library(
        {
            "tou_rules": [
                {"id": "ok", "name": "n", "tier": "peak", "edge": "start", "action": "sundial", "heat": 19.0},
            ]
        }
    )
    room = _room(
        tou_schedule_enabled=True,
        tou_overrides=[
            "not-a-dict",
            {"id": "legacy", "tier": "peak", "action": "set", "heat": 19.0},  # inline format: no rule_id
            {"id": "dangling", "rule_id": "gone", "enabled": True},
            {"id": "off", "rule_id": "ok", "enabled": False},
        ],
    )
    assert TouManager.row_records(room, rules) == []
    # The rule with the unknown action compiles to nothing even when referenced.
    live = _room(tou_schedule_enabled=True, tou_overrides=[{"id": "r", "rule_id": "ok", "enabled": True}])
    assert TouManager.row_records(live, rules) == []


def test_row_named_target_tracks_room() -> None:
    """ "set to comfort" resolves against the room's own configured target."""
    mgr = TouManager(_make_hass({}))
    mgr._timeline = _two_tier_timeline(TOU_TIER_OFF)
    room, settings = _room_schedule(
        {"tier": "peak", "edge": "start", "action": "set", "heat": "comfort", "until": "tier_window"}
    )
    adjust = mgr.make_adjuster(room, settings)
    assert adjust is not None
    boundary = mgr._timeline.segments[1].start
    # _room()comfort_heat is 21.0: the rule tracks the room, not the schedule target.
    out = adjust(boundary + 60.0, TargetTemps(heat=22.5, cool=None))
    assert out.heat == 21.0


def test_rules_anchor_on_running_period_in_progress() -> None:
    """A rule on the period already holding fires now (in-progress anchor).

    The horizon opens inside peak — there is no future "peak starts"
    transition, yet "Peak · starts" describes being *in* peak. The opening
    segment seeds an in-progress boundary so the rule applies immediately;
    a rule anchored on the END of that same period must not fire (it has not
    ended), and the period's expiry still ends the window.
    """
    mgr = TouManager(_make_hass({}))
    now = time.time()
    mgr._timeline = TouTimeline(
        [
            TouSegment(start=now, end=now + 4 * 3600.0, tier=TOU_TIER_PEAK),
            TouSegment(start=now + 4 * 3600.0, end=now + 16 * 3600.0, tier=TOU_TIER_OFF),
        ],
        current_tier=TOU_TIER_PEAK,
        current_rate=None,
    )
    room, settings = _room_schedule(
        {"tier": "peak", "edge": "start", "action": "set", "heat": 18.0, "until": "tier_window"}
    )
    adjust = mgr.make_adjuster(room, settings)
    assert adjust is not None
    # Fires immediately inside the already-running period...
    assert adjust(now + 60.0, TargetTemps(heat=21.0, cool=None)).heat == 18.0
    # ...and ends with the period: off tier resumes the schedule.
    assert adjust(now + 5 * 3600.0, TargetTemps(heat=21.0, cool=None)).heat == 21.0

    # The same anchored at the period END does not fire while the period runs.
    room_end, settings_end = _room_schedule(
        {"tier": "peak", "edge": "end", "action": "set", "heat": 18.0, "until": "minutes", "minutes": 60}
    )
    adjust_end = mgr.make_adjuster(room_end, settings_end)
    assert adjust_end is not None
    assert adjust_end(now + 60.0, TargetTemps(heat=21.0, cool=None)).heat == 21.0


def test_row_arrive_curve_derives_boundary_temperature() -> None:
    """The contributor scenario: 20 °C at the arrival time, heating off since
    the ultra-low boundary — the floor slides down the model's decay curve."""
    mgr = TouManager(_make_hass({}))
    now = time.time()
    b = now + 3600.0
    mgr._timeline = TouTimeline(
        [
            TouSegment(start=now, end=b, tier=TOU_TIER_ULTRA_LOW),
            TouSegment(start=b, end=now + 16 * 3600, tier=TOU_TIER_OFF),
        ],
        current_tier=TOU_TIER_ULTRA_LOW,
        current_rate=None,
    )
    settings = {
        "tou_schedules": [
            {
                "id": "a",
                "name": "20 by nine",
                "enabled": True,
                "rooms": ["living"],
                "side": "heat",
                "tier": "ultra_low",
                "edge": "end",
                "phase": "after",
                "until": "minutes",
                "minutes": 120,
                "value": {"mode": "arrive", "temp": 20.0},
            }
        ]
    }
    room = _room()
    adjust = mgr.make_adjuster(room, settings, decay=(0.1, 10.0))
    assert adjust is not None

    def expected(ts: float) -> float:
        dt_hours = (b + 120 * 60.0 - ts) / 3600.0
        return 10.0 + (20.0 - 10.0) * math.exp(0.1 * dt_hours)

    # Before the boundary: plain schedule target, the MPC plans the pre-charge.
    assert adjust(b - 60.0, TargetTemps(heat=21.0, cool=None)).heat == 21.0
    # At the boundary the derived (indirect) target is above the arrival temp.
    at_boundary = adjust(b, TargetTemps(heat=21.0, cool=None)).heat
    assert at_boundary == pytest.approx(expected(b))
    assert at_boundary > 20.0
    # Mid-window the floor has slid partway down...
    mid = adjust(b + 3600.0, TargetTemps(heat=21.0, cool=None)).heat
    assert mid == pytest.approx(expected(b + 3600.0))
    assert mid < at_boundary
    # ...and it lands exactly on the arrival temperature at the window end.
    assert adjust(b + 120 * 60.0 - 1.0, TargetTemps(heat=21.0, cool=None)).heat == pytest.approx(20.0, abs=0.01)
    # After the window the schedule stands again.
    assert adjust(b + 121 * 60.0, TargetTemps(heat=21.0, cool=None)).heat == 21.0


def test_row_arrive_clock_infers_time_mode() -> None:
    """An arrive rule carrying a clock is time-mode regardless of ``edge``
    echo (the card hides that field): the anchor flips to the period's end."""
    room, settings = _room_schedule(
        {"tier": "ultra_low", "edge": "start", "action": "arrive", "heat": 20.0, "clock": "09:00"}
    )
    (rec,) = TouManager.row_records(room, TouManager.rule_library(settings))
    assert rec["until"] == "clock" and rec["clock"] == "09:00"
    assert rec["edge"] == "end" and rec["tier"] == "ultra_low"
    assert rec["value"] == {"mode": "arrive", "temp": 20.0}


def test_row_arrive_coast_through_lands_at_period_end() -> None:
    """A clock-less arrive rule coasts through the anchored period: the window
    is the period itself and the decay curve lands the target at its end."""
    mgr = TouManager(_make_hass({}))
    now = time.time()
    b = now + 3600.0  # peak starts in one hour, runs four
    mgr._timeline = TouTimeline(
        [
            TouSegment(start=now, end=b, tier=TOU_TIER_MID),
            TouSegment(start=b, end=b + 4 * 3600.0, tier=TOU_TIER_PEAK),
            TouSegment(start=b + 4 * 3600.0, end=now + 16 * 3600, tier=TOU_TIER_OFF),
        ],
        current_tier=TOU_TIER_MID,
        current_rate=None,
    )
    room, settings = _room_schedule(
        {"tier": "peak", "edge": "end", "action": "arrive", "heat": 19.0, "until": "tier_window", "clock": ""}
    )
    (rec,) = TouManager.row_records(room, TouManager.rule_library(settings))
    assert rec["until"] == "window"
    assert rec["edge"] == "start"  # forced: the coast begins when the period starts
    assert rec["value"] == {"mode": "arrive", "temp": 19.0}

    adjust = mgr.make_adjuster({**room, "tou_schedule_enabled": False}, settings)
    assert adjust is None  # store off and the section gated: nothing participates
    adjust = mgr.make_adjuster({**room, "tou_schedule_enabled": True}, settings, decay=(0.1, 10.0))
    assert adjust is not None

    def expected(ts: float) -> float:
        dt_hours = (b + 4 * 3600.0 - ts) / 3600.0
        return 10.0 + (19.0 - 10.0) * math.exp(0.1 * dt_hours)

    # Inside the coast: the derived floor slides down the decay curve...
    at_start = adjust(b, TargetTemps(heat=21.0, cool=None)).heat
    assert at_start == pytest.approx(expected(b))
    assert at_start > 19.0
    mid = adjust(b + 2 * 3600.0, TargetTemps(heat=21.0, cool=None)).heat
    assert mid == pytest.approx(expected(b + 2 * 3600.0)) and mid < at_start
    # ...landing exactly on the arrival temperature as the period ends.
    assert adjust(b + 4 * 3600.0 - 1.0, TargetTemps(heat=21.0, cool=None)).heat == pytest.approx(19.0, abs=0.02)
    # Before and after the period the row keeps its hands off; with the store
    # layer off, the plain schedule stands on both sides.
    assert adjust(b - 60.0, TargetTemps(heat=21.0, cool=None)).heat == 21.0
    assert adjust(b + 4 * 3600.0 + 60.0, TargetTemps(heat=21.0, cool=None)).heat == 21.0


def test_row_arrive_fallbacks_flat() -> None:
    """Immature model or wrong drift direction: hold the flat target (coast)."""
    mgr = TouManager(_make_hass({}))
    now = time.time()
    b = now + 3600.0
    mgr._timeline = TouTimeline(
        [
            TouSegment(start=now, end=b, tier=TOU_TIER_ULTRA_LOW),
            TouSegment(start=b, end=now + 16 * 3600, tier=TOU_TIER_OFF),
        ],
        current_tier=TOU_TIER_ULTRA_LOW,
        current_rate=None,
    )
    rec = {
        "id": "a",
        "name": "20 by nine",
        "enabled": True,
        "rooms": ["living"],
        "side": "heat",
        "tier": "ultra_low",
        "edge": "end",
        "phase": "after",
        "until": "minutes",
        "minutes": 120,
        "value": {"mode": "arrive", "temp": 20.0},
    }
    settings = {"tou_schedules": [rec]}
    room = _room()

    # No learned model yet: flat 20 across the window.
    adjust = mgr.make_adjuster(room, settings)
    assert adjust is not None
    assert adjust(b + 60.0, TargetTemps(heat=21.0, cool=None)).heat == 20.0
    assert adjust(b + 60 * 60.0, TargetTemps(heat=21.0, cool=None)).heat == 20.0

    # Outdoor warmer than the heating target: drift goes the wrong way, flat.
    adjust = mgr.make_adjuster(room, settings, decay=(0.1, 22.0))
    assert adjust is not None
    assert adjust(b + 60.0, TargetTemps(heat=21.0, cool=None)).heat == 20.0


def test_row_arrive_clamped_by_band() -> None:
    """An aggressive derived curve never demands more than the clamp band."""
    mgr = TouManager(_make_hass({}))
    now = time.time()
    b = now + 3600.0
    mgr._timeline = TouTimeline(
        [
            TouSegment(start=now, end=b, tier=TOU_TIER_ULTRA_LOW),
            TouSegment(start=b, end=now + 16 * 3600, tier=TOU_TIER_OFF),
        ],
        current_tier=TOU_TIER_ULTRA_LOW,
        current_rate=None,
    )
    settings = {
        "tou_schedules": [
            {
                "id": "a",
                "name": "x",
                "enabled": True,
                "rooms": ["living"],
                "side": "heat",
                "tier": "ultra_low",
                "edge": "end",
                "phase": "after",
                "until": "minutes",
                "minutes": 120,
                "value": {"mode": "arrive", "temp": 20.0},
            }
        ]
    }
    adjust = mgr.make_adjuster(_room(), settings, decay=(1.0, -20.0))
    assert adjust is not None
    assert adjust(b, TargetTemps(heat=21.0, cool=None)).heat == 28.0  # heat band ceiling


def test_rows_days_filter() -> None:
    """Days on a shared rule restrict which tier boundaries its rows fire on."""
    mgr = TouManager(_make_hass({}))
    now = time.time()
    b = now + 60.0
    mgr._timeline = TouTimeline(
        [
            TouSegment(start=now, end=b, tier=TOU_TIER_ULTRA_LOW),
            TouSegment(start=b, end=now + 16 * 3600, tier=TOU_TIER_OFF),
        ],
        current_tier=TOU_TIER_ULTRA_LOW,
        current_rate=None,
    )
    weekday = TOU_WEEKDAYS[dt_util.as_local(dt_util.utc_from_timestamp(b)).weekday()]
    other = next(d for d in TOU_WEEKDAYS if d != weekday)

    def adjust_for(days: list[str]):
        room, settings = _room_schedule(
            {
                "tier": "off",
                "edge": "start",
                "action": "set",
                "heat": 19.0,
                "until": "tier_window",
                "days": days,
            }
        )
        return mgr.make_adjuster(room, settings)

    assert adjust_for([weekday])(b + 5.0, TargetTemps(heat=21.0, cool=None)).heat == 19.0
    assert adjust_for([other])(b + 5.0, TargetTemps(heat=21.0, cool=None)).heat == 21.0
    assert adjust_for([])(b + 5.0, TargetTemps(heat=21.0, cool=None)).heat == 19.0


def test_preview_includes_room_rows() -> None:
    mgr = TouManager(_make_hass({}))
    now = time.time()
    b = now + 3600.0
    mgr._timeline = TouTimeline(
        [
            TouSegment(start=now, end=b, tier=TOU_TIER_OFF),
            TouSegment(start=b, end=now + 16 * 3600, tier=TOU_TIER_PEAK),
        ],
        current_tier=TOU_TIER_OFF,
        current_rate=None,
    )
    rooms = {
        "living": {
            "area_id": "living",
            "tou_schedule_enabled": True,
            "tou_overrides": [{"id": "r1", "rule_id": "shared1", "enabled": True}],
        }
    }
    settings = {
        "tou_enabled": True,
        "tou_rules": [
            {
                "id": "shared1",
                "name": "x",
                "tier": "peak",
                "edge": "start",
                "action": "set",
                "heat": 19.0,
                "until": "tier_window",
            }
        ],
    }
    out = mgr.preview(settings, None, rooms)
    assert out is not None
    assert out["areas"]["living"], "the room row window must show up in the preview"
    assert "shared1-heat" in out["records"]
    # Gated off: no preview at all.
    assert mgr.preview({"tou_enabled": False}, None, rooms) is None


def test_schedule_arrive_then_coast_chain() -> None:
    """The contributor scenario: reach 23 by the peak, then coast to an 18 floor."""
    mgr = TouManager(_make_hass({}))
    b = time.time() + 3600.0
    mgr._timeline = TouTimeline(
        [
            TouSegment(start=time.time(), end=b, tier=TOU_TIER_OFF),
            TouSegment(start=b, end=time.time() + 16 * 3600, tier=TOU_TIER_PEAK),
        ],
        current_tier=TOU_TIER_OFF,
        current_rate=None,
    )
    settings = {
        "tou_schedules": [
            {
                "id": "arrival",
                "name": "warm by peak",
                "enabled": True,
                "rooms": ["living"],
                "side": "heat",
                "tier": "peak",
                "edge": "start",
                "phase": "before",
                "minutes": 40,
                "until": "window",
                "value": {"mode": "set", "temp": 23.0},
            },
            {
                "id": "peakfloor",
                "name": "coast peak",
                "enabled": True,
                "rooms": ["living"],
                "side": "heat",
                "tier": "peak",
                "edge": "start",
                "phase": "after",
                "until": "window",
                "value": {"mode": "set", "temp": 18.0},
            },
        ]
    }
    adjust = mgr.make_adjuster(_room(), settings)
    assert adjust is not None
    # lead window [b-40m, b): floor raised to 23 so the MPC pre-heats,
    # despite the plain peak shaping wanting to cap heat at 18.
    assert adjust(b - 1800.0, TargetTemps(heat=21.0, cool=None)).heat == 23.0
    # at the boundary the arrival record ends and the coast floor applies.
    assert adjust(b + 60.0, TargetTemps(heat=21.0, cool=None)).heat == 18.0
    # before the lead, plain tier shaping (off -> no peak cap yet: schedule).
    assert adjust(b - 3600.0, TargetTemps(heat=21.0, cool=None)).heat == 21.0


def test_schedule_fires_every_occurrence_and_shift_is_plain_relative() -> None:
    """Two peaks in the horizon both get the window; shift bases on the schedule."""
    mgr = TouManager(_make_hass({}))
    b1 = time.time() + 1800.0
    b2 = b1 + 3600.0
    mgr._timeline = TouTimeline(
        [
            TouSegment(start=time.time(), end=b1, tier=TOU_TIER_OFF),
            TouSegment(start=b1, end=b2, tier=TOU_TIER_PEAK),
            TouSegment(start=b2, end=b2 + 1800.0, tier=TOU_TIER_OFF),
            TouSegment(start=b2 + 1800.0, end=time.time() + 16 * 3600, tier=TOU_TIER_PEAK),
        ],
        current_tier=TOU_TIER_OFF,
        current_rate=None,
    )
    settings = {
        "tou_schedules": [
            {
                "id": "relax",
                "name": "relax",
                "enabled": True,
                "rooms": ["living"],
                "side": "cool",
                "tier": "peak",
                "edge": "start",
                "phase": "after",
                "until": "window",
                "value": {"mode": "shift", "direction": "raise", "delta": 1.5},
            }
        ]
    }
    adjust = mgr.make_adjuster(_room(), settings)
    assert adjust is not None
    # every peak gets it: +1.5 on the plain schedule cool, not on the peak-shaped value
    assert adjust(b1 + 60.0, TargetTemps(heat=None, cool=24.0)).cool == 25.5
    assert adjust(b2 + 1860.0, TargetTemps(heat=None, cool=24.0)).cool == 25.5
    # off tier between peaks: schedule untouched
    assert adjust(b2 + 60.0, TargetTemps(heat=None, cool=24.0)).cool == 24.0


def test_record_requires_matching_room_and_enabled() -> None:
    mgr = TouManager(_make_hass({}))
    boundary = time.time() + 30.0
    mgr._timeline = TouTimeline(
        [
            TouSegment(start=time.time(), end=boundary, tier=TOU_TIER_OFF),
            TouSegment(start=boundary, end=time.time() + 16 * 3600, tier=TOU_TIER_PEAK),
        ],
        current_tier=TOU_TIER_OFF,
        current_rate=None,
    )
    rec = {
        "id": "r1-heat",
        "name": "x",
        "enabled": True,
        "rooms": ["other"],
        "side": "heat",
        "tier": "peak",
        "edge": "start",
        "phase": "after",
        "until": "minutes",
        "minutes": 60,
        "value": {"mode": "set", "temp": 19.0},
    }
    adjust = mgr.make_adjuster(_room(), {"tou_schedules": [rec]})
    assert adjust is not None
    assert adjust(boundary + 120, TargetTemps(heat=21.0, cool=24.0)).heat == 21.0

    disabled = {**rec, "rooms": ["living"], "enabled": False}
    adjust2 = mgr.make_adjuster(_room(), {"tou_schedules": [disabled]})
    assert adjust2 is not None
    assert adjust2(boundary + 120, TargetTemps(heat=21.0, cool=24.0)).heat == 21.0

    # A row is scoped to its own room by construction: it compiles for "living".
    row_room, row_settings = _room_schedule(
        {"tier": "peak", "edge": "start", "action": "set", "heat": 19.0, "until": "minutes", "minutes": 60}
    )
    row_adjust = mgr.make_adjuster(row_room, row_settings)
    assert row_adjust is not None
    assert row_adjust(boundary + 120, TargetTemps(heat=21.0, cool=24.0)).heat == 19.0


def test_record_clock_end_rolls_to_next_day() -> None:
    mgr = TouManager(_make_hass({}))
    now = time.time()
    boundary = now + 30.0
    mgr._timeline = TouTimeline(
        [
            TouSegment(start=now, end=boundary, tier=TOU_TIER_OFF),
            TouSegment(start=boundary, end=now + 16 * 3600, tier=TOU_TIER_PEAK),
        ],
        current_tier=TOU_TIER_OFF,
        current_rate=None,
    )
    # A clock twelve wall-clock hours behind "now": its next occurrence is
    # always ~12 h ahead (inside the horizon), and past midday it can only be
    # reached after midnight — the roll this guards.
    local = dt_util.as_local(dt_util.utc_from_timestamp(now))
    rolled = (local.hour * 60 + local.minute + 720) % 1440
    settings = {
        "tou_schedules": [
            {
                "id": "r1-heat",
                "name": "x",
                "enabled": True,
                "rooms": ["living"],
                "side": "heat",
                "tier": "peak",
                "edge": "start",
                "phase": "after",
                "until": "clock",
                "clock": f"{rolled // 60:02d}:{rolled % 60:02d}",
                "value": {"mode": "set", "temp": 19.0},
            }
        ]
    }
    adjust = mgr.make_adjuster(_room(), settings)
    assert adjust is not None
    assert adjust(boundary + 120, TargetTemps(heat=21.0, cool=24.0)).heat == 19.0


def test_record_next_change_holds_until_boundary() -> None:
    mgr = TouManager(_make_hass({}))
    now = time.time()
    b1 = now + 30.0
    b2 = now + 4 * 3600.0
    mgr._timeline = TouTimeline(
        [
            TouSegment(start=now, end=b1, tier=TOU_TIER_OFF),
            TouSegment(start=b1, end=b2, tier=TOU_TIER_PEAK),
            TouSegment(start=b2, end=now + 16 * 3600, tier=TOU_TIER_ULTRA_LOW),
        ],
        current_tier=TOU_TIER_OFF,
        current_rate=None,
    )
    settings = {
        "tou_schedules": [
            {
                "id": "r1-heat",
                "name": "x",
                "enabled": True,
                "rooms": ["living"],
                "side": "heat",
                "tier": "peak",
                "edge": "start",
                "phase": "after",
                "until": "next_change",
                "value": {"mode": "set", "temp": 19.0},
            }
        ]
    }
    adjust = mgr.make_adjuster(_room(), settings)
    assert adjust is not None
    # The hold runs until the next tier boundary...
    assert adjust(b1 + 1800, TargetTemps(heat=21.0, cool=24.0)).heat == 19.0
    # ...and the schedule stands after it.
    assert adjust(b2 + 60, TargetTemps(heat=21.0, cool=24.0)).heat == 21.0


def test_rules_ignore_malformed_entries() -> None:
    """Malformed library rules referenced by rows compile to nothing."""
    mgr = TouManager(_make_hass({}))
    room, settings = _room_schedule(
        {"action": "sundial", "heat": 19.0},  # unknown action
        {"action": "arrive", "heat": 20.0, "clock": "", "until": "clock"},  # by-time without a time
        {"action": "set", "heat": None, "cool": None},  # no side to apply
    )
    assert TouManager.row_records(room, TouManager.rule_library(settings)) == []
    # Nothing to compile and no store layer: the room does not participate.
    assert mgr.make_adjuster(room, settings) is None


def test_rows_gated_by_schedule_section() -> None:
    """The per-room toggle disables the rows but keeps them (no data loss)."""
    mgr = TouManager(_make_hass({}))
    mgr._timeline = _two_tier_timeline(TOU_TIER_OFF)
    room, settings = _room_schedule(
        {"tier": "peak", "edge": "start", "action": "set", "heat": 19.0, "until": "tier_window"},
        enabled=False,
    )
    assert TouManager.row_records(room, TouManager.rule_library(settings)) == []
    assert mgr.make_adjuster(room, settings) is None
    # Flipping the section back on brings the same rules with it.
    room["tou_schedule_enabled"] = True
    adjust = mgr.make_adjuster(room, settings)
    assert adjust is not None
    boundary = mgr._timeline.segments[1].start
    assert adjust(boundary + 60.0, TargetTemps(heat=21.0, cool=None)).heat == 19.0
