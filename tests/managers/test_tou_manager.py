"""Tests for the Time-of-Use tariff manager.

Ported from the reference fork (wBrhy2/roommind, tag tou-legacy-beta23).
Covers the tariff-awareness engine (period normalization, source resolution,
calendars, windows, the future view, the snapshot) and the tier dictionary
with its persisted price history. Store-layer shaping, tariff rules and
sensor-driven energy tiers are follow-up PRs on this engine.
"""

from __future__ import annotations

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
