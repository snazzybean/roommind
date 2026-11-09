"""Tests for the figures on the analytics page."""

from __future__ import annotations

from datetime import datetime

import pytest
from homeassistant.util import dt as dt_util

from custom_components.roommind.services.analytics_stats import (
    MAX_SAMPLE_GAP_S,
    RHYTHM_DAYS,
    RHYTHM_MAX_DAYS,
    compute_period_stats,
    compute_rhythm,
    rhythm_window,
)

T0 = 1_800_000_000.0
STEP = 180.0


def _point(i: int, **kw) -> dict:
    return {
        "ts": T0 + i * STEP,
        "room_temp": 21.0,
        "mode": "idle",
        "window_open": False,
        "heat_target": 21.0,
        "cool_target": 24.0,
        **kw,
    }


def _modes(*modes: str) -> list[dict]:
    return [_point(i, mode=m) for i, m in enumerate(modes)]


def test_empty_history_has_no_figures():
    stats = compute_period_stats([], "auto")
    assert stats["hours"] == 0
    assert stats["heating_starts"] == 0
    assert stats["comfort"] is None


def test_hours_follow_the_time_between_samples():
    points = _modes("heating", "heating", "idle", "cooling", "idle")
    stats = compute_period_stats(points, "auto")
    assert stats["heating_hours"] == pytest.approx(2 * STEP / 3600, abs=0.01)
    assert stats["cooling_hours"] == pytest.approx(STEP / 3600, abs=0.01)
    assert stats["hours"] == pytest.approx(5 * STEP / 3600, abs=0.01)


def test_a_gap_in_the_history_is_not_running_time():
    points = [{**_point(0, mode="heating")}, {**_point(0, mode="heating"), "ts": T0 + 10 * 3600}]
    stats = compute_period_stats(points, "auto")
    assert stats["heating_hours"] == pytest.approx(2 * MAX_SAMPLE_GAP_S / 3600, abs=0.01)


def test_a_run_already_going_at_the_start_of_the_range_is_no_start():
    stats = compute_period_stats(_modes("heating", "idle", "heating", "cooling", "idle", "heating"), "auto")
    assert stats["heating_starts"] == 2
    assert stats["cooling_starts"] == 1


def test_comfort_splits_into_cold_within_warm():
    points = [
        _point(0, room_temp=20.0),
        _point(1, room_temp=20.8),
        _point(2, room_temp=24.4),
        _point(3, room_temp=25.0),
    ]
    comfort = compute_period_stats(points, "auto")["comfort"]
    assert comfort["below_pct"] == 25
    assert comfort["within_pct"] == 50
    assert comfort["above_pct"] == 25
    assert comfort["mean_deviation"] == pytest.approx((1.0 + 0.2 + 0.4 + 1.0) / 4, abs=0.01)


def test_open_window_is_not_judged_but_counted():
    points = [_point(0, room_temp=15.0, window_open=True), _point(1)]
    stats = compute_period_stats(points, "auto")
    assert stats["window_hours"] == pytest.approx(STEP / 3600, abs=0.01)
    assert stats["comfort"]["within_pct"] == 100


def test_rows_from_before_the_targets_were_recorded_are_not_judged():
    stats = compute_period_stats([_point(0, heat_target=None, cool_target=None)] * 1, "auto")
    assert stats["comfort"] is None


def test_heat_only_room_is_never_too_warm():
    points = [_point(0, room_temp=26.0), _point(1, room_temp=20.0)]
    comfort = compute_period_stats(points, "heat_only")["comfort"]
    assert comfort["above_pct"] == 0
    assert comfort["below_pct"] == 50


def test_cool_only_room_is_never_too_cold():
    points = [_point(0, room_temp=19.0, cool_target=27.0), _point(1, room_temp=28.0, cool_target=27.0)]
    comfort = compute_period_stats(points, "cool_only")["comfort"]
    assert comfort["below_pct"] == 0
    assert comfort["above_pct"] == 50


def test_auto_room_with_schedule_off_on_one_side_keeps_the_other():
    points = [_point(0, room_temp=19.0, cool_target=None), _point(1, room_temp=30.0, cool_target=None)]
    comfort = compute_period_stats(points, "auto")["comfort"]
    assert comfort["below_pct"] == 50
    assert comfort["above_pct"] == 0


def _local_ts(day: int, hour: int, minute: int = 0) -> float:
    return datetime(2026, 11, day, hour, minute, tzinfo=dt_util.DEFAULT_TIME_ZONE).timestamp()


def _hour_of_samples(day: int, hour: int, **kw) -> list[dict]:
    return [{**_point(0, **kw), "ts": _local_ts(day, hour, m)} for m in range(0, 60, 3)]


def test_rhythm_fills_local_hours_newest_day_first():
    points = _hour_of_samples(4, 7, mode="heating") + _hour_of_samples(5, 18, mode="cooling", room_temp=25.0)
    rhythm = compute_rhythm(points, "auto", _local_ts(5, 20))
    assert rhythm is not None
    assert [d["date"] for d in rhythm["days"]] == ["2026-11-05", "2026-11-04"]
    newest, older = rhythm["days"]
    assert older["heat"][7] == 1
    assert older["heat"][8] is None
    assert newest["cool"][18] == 1
    assert newest["deviation"][18] == 1
    assert newest["heat"][18] == 0


def test_rhythm_needs_two_days():
    assert compute_rhythm(_hour_of_samples(5, 7), "auto", _local_ts(5, 20)) is None


def test_rhythm_ignores_samples_outside_the_window():
    points = _hour_of_samples(4, 7) + _hour_of_samples(5, 7) + [{**_point(0), "ts": _local_ts(5, 7) - 86400 * 30}]
    rhythm = compute_rhythm(sorted(points, key=lambda p: p["ts"]), "auto", _local_ts(5, 20))
    assert rhythm is not None
    assert len(rhythm["days"]) <= RHYTHM_DAYS


def test_rhythm_shares_are_parts_of_the_hour():
    samples = _hour_of_samples(5, 7)
    for s in samples[:5]:
        s["mode"] = "heating"
    for s in samples[:10]:
        s["window_open"] = True
    rhythm = compute_rhythm(_hour_of_samples(4, 7) + samples, "auto", _local_ts(5, 20))
    assert rhythm is not None
    assert rhythm["days"][0]["heat"][7] == 0.25
    assert rhythm["days"][0]["window"][7] == 0.5


def test_rhythm_hours_carry_the_means_for_the_popup():
    points = _hour_of_samples(4, 7) + _hour_of_samples(5, 7, room_temp=20.5, humidity=48.0, outdoor_temp=6.0)
    rhythm = compute_rhythm(points, "auto", _local_ts(5, 20))
    assert rhythm is not None
    newest = rhythm["days"][0]
    assert newest["temp"][7] == 20.5
    assert newest["humidity"][7] == 48
    assert newest["outdoor"][7] == 6
    assert rhythm["days"][1]["humidity"][7] is None


def test_rhythm_can_show_more_days():
    points = _hour_of_samples(1, 7) + _hour_of_samples(5, 7)
    earlier = [{**p, "ts": p["ts"] - 20 * 86400} for p in _hour_of_samples(5, 7)]
    rhythm = compute_rhythm(sorted(points + earlier, key=lambda p: p["ts"]), "auto", _local_ts(5, 20), 31)
    assert rhythm is not None
    assert len(rhythm["days"]) == 21


def test_window_stays_on_the_last_days_for_a_day_inside_them():
    now = _local_ts(20, 12)
    assert rhythm_window(_local_ts(10, 0), _local_ts(10, 23), now) == (RHYTHM_DAYS, now)


def test_window_includes_the_oldest_day_of_the_grid():
    now = _local_ts(20, 12)
    assert rhythm_window(_local_ts(7, 0), _local_ts(7, 23), now) == (RHYTHM_DAYS, now)
    assert rhythm_window(_local_ts(6, 0), _local_ts(6, 23), now)[1] != now


def test_window_moves_back_for_an_older_range():
    now = _local_ts(25, 12)
    end = _local_ts(3, 23)
    assert rhythm_window(_local_ts(1, 0), end, now) == (RHYTHM_DAYS, end)


def test_window_grows_with_the_range_up_to_the_limit():
    now = _local_ts(30, 12)
    assert rhythm_window(now - 29 * 86400, now, now) == (29, now)
    assert rhythm_window(now - 80 * 86400, now, now) == (RHYTHM_MAX_DAYS, now)


def test_window_never_ends_in_the_future():
    now = _local_ts(5, 12)
    days, end = rhythm_window(_local_ts(1, 0) - 86400 * 40, now + 86400, now)
    assert days == RHYTHM_MAX_DAYS
    assert end == now


def test_miss_deviation_is_the_mean_while_off_target():
    points = [
        _point(0, room_temp=20.0),
        _point(1, room_temp=21.0),
        _point(2, room_temp=21.0),
        _point(3, room_temp=25.0),
    ]
    comfort = compute_period_stats(points, "auto")["comfort"]
    assert comfort["miss_deviation"] == pytest.approx(1.0)


def test_miss_deviation_is_none_without_misses():
    points = [_point(0, room_temp=20.8), _point(1, room_temp=24.4)]
    assert compute_period_stats(points, "auto")["comfort"]["miss_deviation"] is None


def test_rhythm_hours_split_like_the_period_figures():
    # 10 minutes 1.5 K too cold inside an hour on target: the hourly mean (-0.25 K) hides it,
    # the share does not
    samples = _hour_of_samples(5, 7)
    for s in samples[:4]:
        s["room_temp"] = 19.5
    for s in samples[4:6]:
        s["room_temp"] = 24.4  # past the cool target, inside the tolerance
    rhythm = compute_rhythm(_hour_of_samples(4, 7) + samples, "auto", _local_ts(5, 20))
    assert rhythm is not None
    day = rhythm["days"][0]
    assert day["below"][7] == 0.2
    assert day["above"][7] == 0
    assert day["below"][8] is None
    assert day["within"] == 0.8
    assert rhythm["days"][1]["within"] == 1


def test_rhythm_day_without_judged_samples_has_no_share():
    samples = _hour_of_samples(5, 7, window_open=True)
    rhythm = compute_rhythm(_hour_of_samples(4, 7) + samples, "auto", _local_ts(5, 20))
    assert rhythm is not None
    assert rhythm["days"][0]["within"] is None
    assert rhythm["days"][0]["below"][7] is None


def _run(temps_and_modes: list[tuple[float, str]], **kw) -> list[dict]:
    return [_point(i, room_temp=t, mode=m, **kw) for i, (t, m) in enumerate(temps_and_modes)]


def test_overshoot_is_the_peak_after_each_heating_run():
    points = _run(
        [(20.5, "heating"), (21.0, "heating"), (21.4, "idle"), (21.8, "idle"), (21.5, "idle")]
        + [(20.6, "idle")] * 25
        + [(20.7, "heating"), (21.0, "idle"), (21.2, "idle")]
    )
    over = compute_period_stats(points, "auto")["heat_overshoot"]
    assert over == {"runs": 2, "mean": pytest.approx(0.5), "max": pytest.approx(0.8)}


def test_overshoot_window_ends_after_an_hour_and_at_the_next_run():
    late_rise = [(21.0, "heating")] + [(21.0, "idle")] * 25 + [(23.0, "idle")]
    assert compute_period_stats(_run(late_rise), "auto")["heat_overshoot"]["max"] == 0
    next_run = [(21.0, "heating"), (21.2, "idle"), (21.0, "heating"), (21.0, "idle")]
    assert compute_period_stats(_run(next_run), "auto")["heat_overshoot"]["max"] == pytest.approx(0.2)


def test_overshoot_ignores_open_windows_and_counts_cooling_downwards():
    points = _run([(21.0, "heating"), (21.0, "idle")]) + [_point(2, room_temp=25.0, mode="idle", window_open=True)]
    assert compute_period_stats(points, "auto")["heat_overshoot"]["max"] == 0
    cooling = _run([(24.5, "cooling"), (24.0, "idle"), (23.6, "idle")])
    assert compute_period_stats(cooling, "auto")["cool_overshoot"]["max"] == pytest.approx(0.4)


def test_overshoot_only_for_the_controlled_side():
    points = _run([(21.0, "heating"), (21.5, "idle")])
    assert compute_period_stats(points, "cool_only")["heat_overshoot"] is None
    assert compute_period_stats(points, "heat_only")["cool_overshoot"] is None
    assert compute_period_stats(_run([(21.0, "idle")]), "auto")["heat_overshoot"] is None


def test_run_hours_by_price_level():
    points = [
        _point(0, mode="heating", price_level="cheap", price_shift=1.0, heat_target=22.0, cool_target=23.0),
        _point(1, mode="heating", price_level="cheap", price_shift=1.0, heat_target=22.0, cool_target=23.0),
        _point(2, mode="heating", price_level="expensive"),
        _point(3, mode="idle", price_level="normal"),
        _point(4, mode="idle", price_level="normal"),
    ]
    price = compute_period_stats(points, "auto")["price"]
    assert price["heating_hours"] == {"cheap": 0.1, "expensive": 0.05}
    assert price["cooling_hours"] == {}
    assert price["shifted_hours"] == 0.1


def test_no_price_figures_without_price_data():
    assert compute_period_stats(_modes("heating", "idle"), "auto")["price"] is None


def test_comfort_is_judged_against_the_schedule_not_the_price_shift():
    # Coasting 1 K below a 21 °C schedule while expensive: the room at 19.9 °C is too cold
    coast = _point(0, room_temp=19.9, heat_target=20.0, cool_target=25.0, price_shift=-1.0)
    assert compute_period_stats([coast, _point(1)], "auto")["comfort"]["below_pct"] == 50
