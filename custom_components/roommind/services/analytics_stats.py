"""Figures derived from the recorded history for the analytics page."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

from homeassistant.util import dt as dt_util

from ..const import CLIMATE_MODE_COOL_ONLY, CLIMATE_MODE_HEAT_ONLY, MODE_COOLING, MODE_HEATING

COMFORT_TOLERANCE_K = 0.5
# A sample stands for the time until the next one; a gap (HA down) must not count as running time
MAX_SAMPLE_GAP_S = 900
RHYTHM_DAYS = 14
RHYTHM_MIN_DAYS = 2


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
        low = None if climate_mode == CLIMATE_MODE_COOL_ONLY else point.get("heat_target")
        high = None if climate_mode == CLIMATE_MODE_HEAT_ONLY else point.get("cool_target")
        if temp is None or (low is None and high is None) or point.get("window_open"):
            result.append(None)
        elif low is not None and temp < low:
            result.append(round(temp - low, 3))
        elif high is not None and temp > high:
            result.append(round(temp - high, 3))
        else:
            result.append(0.0)
    return result


def compute_period_stats(points: list[dict], climate_mode: str) -> dict:
    """Sum up a time-sorted list of history points."""
    seconds = {"total": 0.0, "heating": 0.0, "cooling": 0.0, "window": 0.0}
    starts = {MODE_HEATING: 0, MODE_COOLING: 0}
    comfort = {"below": 0.0, "within": 0.0, "above": 0.0}
    deviation_sum = 0.0
    previous_mode = None
    for (point, weight), deviation in zip(_weighted(points), _deviations(points, climate_mode), strict=True):
        mode = point.get("mode")
        seconds["total"] += weight
        if mode in starts:
            seconds[mode] += weight
            if previous_mode is not None and previous_mode != mode:
                starts[mode] += 1
        previous_mode = mode
        if point.get("window_open"):
            seconds["window"] += weight
        if deviation is None:
            continue
        deviation_sum += abs(deviation) * weight
        if deviation < -COMFORT_TOLERANCE_K:
            comfort["below"] += weight
        elif deviation > COMFORT_TOLERANCE_K:
            comfort["above"] += weight
        else:
            comfort["within"] += weight

    judged = sum(comfort.values())
    return {
        "hours": round(seconds["total"] / 3600, 2),
        "heating_hours": round(seconds[MODE_HEATING] / 3600, 2),
        "cooling_hours": round(seconds[MODE_COOLING] / 3600, 2),
        "window_hours": round(seconds["window"] / 3600, 2),
        "heating_starts": starts[MODE_HEATING],
        "cooling_starts": starts[MODE_COOLING],
        "comfort": (
            {
                "below_pct": round(100 * comfort["below"] / judged, 1),
                "within_pct": round(100 * comfort["within"] / judged, 1),
                "above_pct": round(100 * comfort["above"] / judged, 1),
                "mean_deviation": round(deviation_sum / judged, 2),
            }
            if judged > 0
            else None
        ),
    }


def _empty_day(date: str) -> dict:
    return {"date": date, "heat": [None] * 24, "cool": [None] * 24, "window": [None] * 24, "deviation": [None] * 24}


def compute_rhythm(points: list[dict], climate_mode: str, end_ts: float) -> dict | None:
    """Hour-by-day grid of the last RHYTHM_DAYS local days, newest day first.

    heat, cool and window are shares of the hour (0-1), deviation is the mean signed
    distance from the wanted band in K. An hour without samples is None. None overall
    while fewer than RHYTHM_MIN_DAYS days have data, a single row says nothing.
    """
    last_day = dt_util.as_local(dt_util.utc_from_timestamp(end_ts)).date()
    dates = [last_day - timedelta(days=i) for i in range(RHYTHM_DAYS)]
    index = {date: i for i, date in enumerate(dates)}
    days = [_empty_day(date.isoformat()) for date in dates]

    # [seconds, heat, cool, window, judged seconds, deviation seconds]
    cells: dict[tuple[int, int], list[float]] = {}
    for (point, weight), deviation in zip(_weighted(points), _deviations(points, climate_mode), strict=True):
        local = dt_util.as_local(dt_util.utc_from_timestamp(point["ts"]))
        row = index.get(local.date())
        if row is None or weight <= 0:
            continue
        cell = cells.setdefault((row, local.hour), [0.0] * 6)
        cell[0] += weight
        if point.get("mode") == MODE_HEATING:
            cell[1] += weight
        elif point.get("mode") == MODE_COOLING:
            cell[2] += weight
        if point.get("window_open"):
            cell[3] += weight
        if deviation is not None:
            cell[4] += weight
            cell[5] += deviation * weight

    for (row, hour), cell in cells.items():
        day = days[row]
        day["heat"][hour] = round(cell[1] / cell[0], 2)
        day["cool"][hour] = round(cell[2] / cell[0], 2)
        day["window"][hour] = round(cell[3] / cell[0], 2)
        if cell[4] > 0:
            day["deviation"][hour] = round(cell[5] / cell[4], 2)

    if len({row for row, _ in cells}) < RHYTHM_MIN_DAYS:
        return None
    while days and all(value is None for value in days[-1]["heat"]):
        days.pop()
    return {"days": days}
