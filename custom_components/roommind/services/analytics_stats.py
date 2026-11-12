"""Figures derived from the recorded history for the analytics page."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from math import ceil

from homeassistant.util import dt as dt_util

from ..const import CLIMATE_MODE_COOL_ONLY, CLIMATE_MODE_HEAT_ONLY, MODE_COOLING, MODE_HEATING

COMFORT_TOLERANCE_K = 0.5
# A sample stands for the time until the next one; a gap (HA down) must not count as running time
MAX_SAMPLE_GAP_S = 900
RHYTHM_DAYS = 14
RHYTHM_MAX_DAYS = 31
RHYTHM_MIN_DAYS = 2
RHYTHM_MEANS = {"temp": "room_temp", "humidity": "humidity", "outdoor": "outdoor_temp"}
# How long after a run the room may still carry it past the target (radiators keep giving heat)
OVERSHOOT_WINDOW_S = 3600
# A pre-heat starts at most this long before the block it heats for (PREHEAT_MAX_LEAD_HOURS)
PREHEAT_LOOKAHEAD_S = 12 * 3600


def _weighted(points: list[dict]) -> Iterator[tuple[dict, float]]:
    """Yield each sample with the seconds it stands for."""
    last_weight = 0.0
    for i, point in enumerate(points):
        if i + 1 < len(points):
            last_weight = min(points[i + 1]["ts"] - point["ts"], MAX_SAMPLE_GAP_S)
        yield point, last_weight


def _deviations(points: list[dict], climate_mode: str) -> list[float | None]:
    """Signed distance of each sample from the wanted band, None where it cannot be judged.

    Open windows and samples from before the targets were recorded are not judged. A room
    that only heats cannot be too warm and one that only cools cannot be too cold: nothing
    in it acts on that side, a sunny heat-only room would read as a failure all summer.
    """
    result: list[float | None] = []
    for point in points:
        temp = point.get("room_temp")
        # Judged against the schedule: a price shift is the user's trade, its cost shows here
        shift = point.get("price_shift") or 0.0
        low = None if climate_mode == CLIMATE_MODE_COOL_ONLY else point.get("heat_target")
        high = None if climate_mode == CLIMATE_MODE_HEAT_ONLY else point.get("cool_target")
        low = low - shift if low is not None else None
        high = high + shift if high is not None else None
        if temp is None or (low is None and high is None) or point.get("window_open"):
            result.append(None)
        elif low is not None and temp < low:
            result.append(round(temp - low, 3))
        elif high is not None and temp > high:
            result.append(round(temp - high, 3))
        else:
            result.append(0.0)
    return result


def _comfort_side(deviation: float) -> str:
    if deviation < -COMFORT_TOLERANCE_K:
        return "below"
    if deviation > COMFORT_TOLERANCE_K:
        return "above"
    return "within"


def _run_target(point: dict, target_key: str, sign: int) -> float | None:
    """The target a run may aim for at ``point``: the stricter of the target in force and the schedule.

    The price shift is taken out like in the comfort figures, so a run held under a target the
    price lowered (coasting) is judged against the schedule. Charging raises the target in force
    above the schedule; the stricter of both keeps that intended charge from counting as overshoot.
    History ``price_shift`` carries the heat-side sign (heat +shift, cool -shift).
    """
    target = point.get(target_key)
    if target is None:
        return None
    schedule = target - sign * (point.get("price_shift") or 0.0)
    return float(max(target, schedule) if sign > 0 else min(target, schedule))


def _reference_target(points: list[dict], run_start: int, end: int, target_key: str, sign: int) -> float | None:
    """The target a run of ``points[run_start..end]`` worked towards.

    The strictest target (``_run_target``) from the run's start to OVERSHOOT_WINDOW_S after its
    end (heating: the highest heat target, cooling: the lowest cool target), so a run ended by a
    lower target counts against the one it ran for. A run that started with the room already
    past that target can only be a pre-heat: then the next stricter target within
    PREHEAT_LOOKAHEAD_S is the reference (pre-heat starts up to hours before a block).
    """
    strictest = max if sign > 0 else min
    end_ts = points[end]["ts"]
    targets: list[float] = []
    for p in points[run_start:]:
        if p["ts"] - end_ts > OVERSHOOT_WINDOW_S:
            break
        if (t := _run_target(p, target_key, sign)) is not None:
            targets.append(t)
    if not targets:
        return None
    reference = strictest(targets)
    first = points[run_start].get("room_temp")
    if first is None or sign * (first - reference) < 0:
        return reference
    for p in points[end:]:
        if p["ts"] - end_ts > PREHEAT_LOOKAHEAD_S:
            break
        t = _run_target(p, target_key, sign)
        if t is not None and sign * (t - reference) > 0:
            return t
    return reference


def _run_overshoot(points: list[dict], mode: str, target_key: str, sign: int) -> dict | None:
    """How far the room went past the target after each run of ``mode``.

    The peak is taken from the run's end up to OVERSHOOT_WINDOW_S later or until the next run
    of the same mode; samples with an open window are left out. It is measured against the
    target the run worked towards (``_reference_target``), not the one in force at its end:
    pre-heat runs end under eco, runs end because the target dropped and the price lowers it.
    ``sign`` is +1 for heating (above the heat target), -1 for cooling (below the cool target).
    """
    strictest = max if sign > 0 else min
    overshoots: list[float] = []
    run_start = 0
    for i, point in enumerate(points[:-1]):
        if point.get("mode") != mode:
            continue
        if i == 0 or points[i - 1].get("mode") != mode:
            run_start = i
        if points[i + 1].get("mode") == mode:
            continue
        reference = _reference_target(points, run_start, i, target_key, sign)
        if reference is None:
            continue
        peak: float | None = None
        for later in points[i:]:
            if later["ts"] - point["ts"] > OVERSHOOT_WINDOW_S or (later is not point and later.get("mode") == mode):
                break
            temp = later.get("room_temp")
            if temp is None or later.get("window_open"):
                continue
            peak = temp if peak is None else strictest(peak, temp)
        if peak is not None:
            overshoots.append(max(0.0, sign * (peak - reference)))
    if not overshoots:
        return None
    return {
        "runs": len(overshoots),
        "mean": round(sum(overshoots) / len(overshoots), 2),
        "max": round(max(overshoots), 2),
    }


def compute_period_stats(points: list[dict], climate_mode: str) -> dict:
    """Sum up a time-sorted list of history points."""
    seconds = {"total": 0.0, "heating": 0.0, "cooling": 0.0, "window": 0.0}
    starts = {MODE_HEATING: 0, MODE_COOLING: 0}
    start_keys = {MODE_HEATING: "heat_starts", MODE_COOLING: "cool_starts"}
    comfort = {"below": 0.0, "within": 0.0, "above": 0.0}
    by_price: dict[str, dict[str, float]] = {MODE_HEATING: {}, MODE_COOLING: {}}
    priced = shifted = 0.0
    deviation_sum = 0.0
    miss_sum = 0.0
    previous_mode = None
    for (point, weight), deviation in zip(_weighted(points), _deviations(points, climate_mode), strict=True):
        mode = point.get("mode")
        seconds["total"] += weight
        if mode in starts:
            seconds[mode] += weight
        if any(point.get(key) is not None for key in start_keys.values()):
            # Counted when recorded: a compacted 5-min bucket keeps only its first mode
            for run, key in start_keys.items():
                starts[run] += point.get(key) or 0
        elif mode in starts and previous_mode is not None and previous_mode != mode:
            starts[mode] += 1
        previous_mode = mode
        if point.get("window_open"):
            seconds["window"] += weight
        level = point.get("price_level")
        if level:
            priced += weight
            if mode in by_price:
                by_price[mode][level] = by_price[mode].get(level, 0.0) + weight
            if point.get("price_shift"):
                shifted += weight
        if deviation is None:
            continue
        deviation_sum += abs(deviation) * weight
        side = _comfort_side(deviation)
        comfort[side] += weight
        if side != "within":
            miss_sum += abs(deviation) * weight

    judged = sum(comfort.values())
    missed = comfort["below"] + comfort["above"]
    return {
        "hours": round(seconds["total"] / 3600, 2),
        "heating_hours": round(seconds[MODE_HEATING] / 3600, 2),
        "cooling_hours": round(seconds[MODE_COOLING] / 3600, 2),
        "window_hours": round(seconds["window"] / 3600, 2),
        "heating_starts": starts[MODE_HEATING],
        "cooling_starts": starts[MODE_COOLING],
        # Run hours by price level and how long the price moved the target, None without a price
        "price": (
            {
                "heating_hours": {lv: round(v / 3600, 2) for lv, v in by_price[MODE_HEATING].items()},
                "cooling_hours": {lv: round(v / 3600, 2) for lv, v in by_price[MODE_COOLING].items()},
                "shifted_hours": round(shifted / 3600, 2),
            }
            if priced > 0
            else None
        ),
        "heat_overshoot": (
            _run_overshoot(points, MODE_HEATING, "heat_target", 1) if climate_mode != CLIMATE_MODE_COOL_ONLY else None
        ),
        "cool_overshoot": (
            _run_overshoot(points, MODE_COOLING, "cool_target", -1) if climate_mode != CLIMATE_MODE_HEAT_ONLY else None
        ),
        "comfort": (
            {
                "below_pct": round(100 * comfort["below"] / judged, 1),
                "within_pct": round(100 * comfort["within"] / judged, 1),
                "above_pct": round(100 * comfort["above"] / judged, 1),
                "mean_deviation": round(deviation_sum / judged, 2),
                # How far off the room was while it was off target, None when it never was
                "miss_deviation": round(miss_sum / missed, 2) if missed > 0 else None,
            }
            if judged > 0
            else None
        ),
    }


def _local_date(ts: float) -> date:
    local: date = dt_util.as_local(dt_util.utc_from_timestamp(ts)).date()
    return local


def rhythm_window(start_ts: float, end_ts: float, now: float) -> tuple[int, float]:
    """Days of the grid and the moment it ends for a selected range.

    The grid is an overview around the range: it stays on the days up to now while the
    range lies inside them, so picking a day does not move the rows under the pointer,
    grows with a longer range and only moves back for a range older than that.
    """
    days = min(max(ceil((end_ts - start_ts) / 86400), RHYTHM_DAYS), RHYTHM_MAX_DAYS)
    if _local_date(start_ts) >= _local_date(now) - timedelta(days=days - 1):
        return days, now
    return days, min(end_ts, now)


def _empty_day(date_str: str) -> dict:
    keys = ("heat", "cool", "window", "deviation", "below", "above", *RHYTHM_MEANS)
    return {"date": date_str, **{key: [None] * 24 for key in keys}, "within": None}


def compute_rhythm(points: list[dict], climate_mode: str, end_ts: float, days_shown: int = RHYTHM_DAYS) -> dict | None:
    """Hour-by-day grid of the local days up to end_ts, newest day first.

    heat, cool and window are shares of the hour (0-1), below and above the shares of the
    judged time too cold / too warm with the same tolerance as the period figures,
    deviation is the mean signed distance from the wanted band in K, temp, humidity and
    outdoor are hourly means; within is the day's judged share on target.
    An hour without samples is None. None overall while fewer than RHYTHM_MIN_DAYS days
    have data, a single row says nothing.
    """
    last_day = _local_date(end_ts)
    dates = [last_day - timedelta(days=i) for i in range(days_shown)]
    index = {day: i for i, day in enumerate(dates)}
    days = [_empty_day(day.isoformat()) for day in dates]

    cells: dict[tuple[int, int], dict[str, float]] = {}
    for (point, weight), deviation in zip(_weighted(points), _deviations(points, climate_mode), strict=True):
        local = dt_util.as_local(dt_util.utc_from_timestamp(point["ts"]))
        row = index.get(local.date())
        if row is None or weight <= 0:
            continue
        cell = cells.setdefault((row, local.hour), {})
        cell["seconds"] = cell.get("seconds", 0.0) + weight
        for key, on in (
            ("heat", point.get("mode") == MODE_HEATING),
            ("cool", point.get("mode") == MODE_COOLING),
            ("window", bool(point.get("window_open"))),
        ):
            cell[key] = cell.get(key, 0.0) + (weight if on else 0.0)
        if deviation is not None:
            side = _comfort_side(deviation)
            cell["judged"] = cell.get("judged", 0.0) + weight
            cell[side] = cell.get(side, 0.0) + weight
        values = {key: point.get(field) for key, field in RHYTHM_MEANS.items()}
        for key, value in {**values, "deviation": deviation}.items():
            if value is not None:
                cell[f"{key}_sum"] = cell.get(f"{key}_sum", 0.0) + value * weight
                cell[f"{key}_seconds"] = cell.get(f"{key}_seconds", 0.0) + weight

    for (row, hour), cell in cells.items():
        day = days[row]
        for key in ("heat", "cool", "window"):
            day[key][hour] = round(cell[key] / cell["seconds"], 2)
        for key in ("deviation", *RHYTHM_MEANS):
            if f"{key}_seconds" in cell:
                day[key][hour] = round(cell[f"{key}_sum"] / cell[f"{key}_seconds"], 2)
        if cell.get("judged"):
            for key in ("below", "above"):
                day[key][hour] = round(cell.get(key, 0.0) / cell["judged"], 2)

    for row, day in enumerate(days):
        judged = sum(cell.get("judged", 0.0) for (r, _), cell in cells.items() if r == row)
        if judged > 0:
            within = sum(cell.get("within", 0.0) for (r, _), cell in cells.items() if r == row)
            day["within"] = round(within / judged, 3)

    if len({row for row, _ in cells}) < RHYTHM_MIN_DAYS:
        return None
    while days and all(value is None for value in days[-1]["heat"]):
        days.pop()
    return {"days": days}
