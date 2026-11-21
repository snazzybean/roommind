"""Mocked Area Occupancy Detection: the learned priors a scenario declares.

RoomMind can take a room's comfort window from Area Occupancy Detection's
``area_occupancy.get_time_priors`` service. The sim does not run that integration;
simhome registers the service under its domain and answers with the response built
here from the scenario's ``area_occupancy:`` section:

```yaml
area_occupancy:
  slot_minutes: 60                 # optional, default 60
  areas:
    bad:                           # area id reported by the service
      global_prior: 0.05           # share of the week the area is occupied
      default: 0.02                # prior of every slot not covered by a window
      windows:                     # habitual use: prior per weekday and time range
        - {days: [mon, tue, wed, thu, fri], from: "06:00", to: "08:00", prior: 0.4}
      unobserved: [sat, sun]       # optional: weekdays whose slots have no observations
```
"""

from __future__ import annotations

from typing import Any

from .scenario.errors import ScenarioError

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _minutes(hhmm: str, where: str) -> int:
    """Minutes after midnight of an "HH:MM" string ("24:00" allowed as the end of a day).

    Args:
        hhmm: Time of day.
        where: Scenario path for the error message.
    """
    try:
        hours, minutes = (int(part) for part in str(hhmm).split(":"))
    except ValueError as err:
        raise ScenarioError(f"time {hhmm!r} is not HH:MM", where) from err
    total = hours * 60 + minutes
    if not 0 <= total <= 1440:
        raise ScenarioError(f"time {hhmm!r} is outside the day", where)
    return total


def _days(raw: Any, where: str) -> list[int]:
    """Weekday indexes (0 = Monday) of a list of day names.

    Args:
        raw: List of names from ``DAYS``.
        where: Scenario path for the error message.
    """
    names = list(raw or [])
    unknown = [d for d in names if d not in DAYS]
    if unknown:
        raise ScenarioError(f"unknown days {unknown} (use {', '.join(DAYS)})", where)
    return [DAYS.index(d) for d in names]


def _fraction(raw: Any, where: str) -> float:
    """A share between 0 and 1.

    Args:
        raw: Value from the scenario.
        where: Scenario path for the error message.
    """
    try:
        value = float(raw)
    except (TypeError, ValueError) as err:
        raise ScenarioError(f"{raw!r} is not a number", where) from err
    if not 0.0 <= value <= 1.0:
        raise ScenarioError(f"{value} is outside 0..1", where)
    return value


def build_time_priors(spec: dict[str, Any]) -> dict[str, Any]:
    """The ``get_time_priors`` response for an ``area_occupancy:`` section; raises ScenarioError when invalid.

    Each area gets ``slots_raw`` for every slot of the week (``default`` overlaid with its
    windows) and ``data_points`` with 0 for the ``unobserved`` days, so RoomMind sees the
    same fields as from the real integration. ``slots`` and ``slots_baseline`` repeat the
    default only: RoomMind must not read them, and a scenario shows it if it did.

    Args:
        spec: The scenario's ``area_occupancy:`` section.
    """
    if not isinstance(spec, dict):
        raise ScenarioError("area_occupancy must be a mapping", "area_occupancy")
    slot_minutes = int(spec.get("slot_minutes", 60))
    if slot_minutes <= 0 or 1440 % slot_minutes:
        raise ScenarioError(f"slot_minutes {slot_minutes} must divide a day", "area_occupancy.slot_minutes")
    slots_per_day = 1440 // slot_minutes
    areas: dict[str, Any] = {}
    for area_id, area_spec in (spec.get("areas") or {}).items():
        where = f"area_occupancy.areas.{area_id}"
        area = area_spec or {}
        default = _fraction(area.get("default", 0.0), f"{where}.default")
        raw = {(day, slot): default for day in range(7) for slot in range(slots_per_day)}
        for i, window in enumerate(area.get("windows") or []):
            wwhere = f"{where}.windows[{i}]"
            start = _minutes(window.get("from", "00:00"), wwhere)
            end = _minutes(window.get("to", "24:00"), wwhere)
            prior = _fraction(window.get("prior"), f"{wwhere}.prior")
            for day in _days(window.get("days", DAYS), wwhere):
                for slot in range(slots_per_day):
                    if start <= slot * slot_minutes < end:
                        raw[(day, slot)] = prior
        unobserved = set(_days(area.get("unobserved"), f"{where}.unobserved"))
        areas[f"sim_{area_id}"] = {
            "area_id": area_id,
            "global_prior": _fraction(area.get("global_prior", default), f"{where}.global_prior"),
            "slot_minutes": slot_minutes,
            "slots_raw": {f"{day},{slot}": prior for (day, slot), prior in raw.items()},
            "data_points": {f"{day},{slot}": 0 if day in unobserved else 50 for (day, slot) in raw},
            "slots": {f"{day},{slot}": default for (day, slot) in raw},
            "slots_baseline": {f"{day},{slot}": default for (day, slot) in raw},
        }
    return {"slot_minutes": slot_minutes, "areas": areas}
