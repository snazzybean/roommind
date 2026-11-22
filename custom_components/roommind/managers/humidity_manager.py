"""Room humidity limits and the devices RoomMind runs for them (#518, #526).

A room with an upper limit (``humidity_max``) is too humid from it on and fine again
``HUMIDITY_HYSTERESIS`` % RH below it; the lower limit (``humidity_min``) mirrors that for too
dry. Too humid runs the room's dehumidifier and its ventilation entity (the one CO2/VOC use,
only while the outdoor air dries the room), too dry its humidifier. Switching, minimum run and
a hand on the switch are the ``VentilationController`` of #267, one instance for the
ventilation (shared with CO2/VOC, so one trigger never switches off what the other needs) and
one for the dehumidifiers and humidifiers.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from ..const import (
    HUMIDITY_HYSTERESIS,
    HUMIDITY_VENT_KEEP_MARGIN,
    HUMIDITY_VENT_START_MARGIN,
    MAX_SENSOR_STALENESS,
)
from ..utils.mold_utils import absolute_humidity

HUMIDITY_HIGH = "high"
HUMIDITY_LOW = "low"


def _limit(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def humidity_limits(room: dict) -> tuple[float | None, float | None]:
    """The room's (lower, upper) humidity limit in % RH; None where not set."""
    return _limit(room.get("humidity_min")), _limit(room.get("humidity_max"))


def humidity_regulated(room: dict) -> bool:
    """Whether RoomMind judges the room's humidity: a limit and a humidity sensor, not outdoor."""
    return (
        bool(room.get("humidity_sensor"))
        and not room.get("is_outdoor", False)
        and any(limit is not None for limit in humidity_limits(room))
    )


def next_humidity_level(previous: str | None, value: float | None, low: float | None, high: float | None) -> str | None:
    """Too humid from the upper limit on, too dry from the lower one; fine again past the hysteresis."""
    if value is None:
        if (previous == HUMIDITY_HIGH and high is None) or (previous == HUMIDITY_LOW and low is None):
            return None
        return previous
    if high is not None and value >= high:
        return HUMIDITY_HIGH
    if low is not None and value <= low:
        return HUMIDITY_LOW
    if previous == HUMIDITY_HIGH and high is not None and value > high - HUMIDITY_HYSTERESIS:
        return HUMIDITY_HIGH
    if previous == HUMIDITY_LOW and low is not None and value < low + HUMIDITY_HYSTERESIS:
        return HUMIDITY_LOW
    return None


def outdoor_air_dries(
    indoor_temp: float | None,
    indoor_rh: float | None,
    outdoor_temp: float | None,
    outdoor_rh: float | None,
    *,
    running: bool,
) -> bool:
    """Whether outdoor air carries less water than the room's, so ventilating dries it.

    Without a reading (no outdoor humidity sensor) it does not block: the shower case needs the
    fan, and RoomMind cannot tell. Starting asks for a wider margin than going on, so a fan
    near the point where airing stops helping does not flap.
    """
    if indoor_temp is None or indoor_rh is None or outdoor_temp is None or outdoor_rh is None:
        return True
    margin = HUMIDITY_VENT_KEEP_MARGIN if running else HUMIDITY_VENT_START_MARGIN
    return absolute_humidity(outdoor_temp, outdoor_rh) <= absolute_humidity(indoor_temp, indoor_rh) - margin


class HumidityTracker:
    """Per room: too humid, too dry or fine, with hysteresis across cycles.

    A sensor without a reading keeps its last judgement for MAX_SENSOR_STALENESS, then counts
    as fine. ``assume`` seeds a room not judged since the start (a device RoomMind runs after a
    restart), so the hysteresis goes on instead of ending the run inside the band.
    """

    def __init__(self) -> None:
        self._level: dict[str, str | None] = {}
        self._seen: dict[str, float] = {}
        self._venting: dict[str, bool] = {}
        # Rooms that wanted their ventilation for humidity before a restart (persisted)
        self._vented_before: set[str] = set()

    def evaluate(
        self,
        area_id: str,
        value: float | None,
        low: float | None,
        high: float | None,
        now: float,
        *,
        assume: str | None = None,
    ) -> str | None:
        if assume is not None and area_id not in self._seen:
            self._level[area_id] = assume
            self._seen[area_id] = now
        if value is not None:
            self._seen[area_id] = now
        elif now - self._seen.get(area_id, -math.inf) > MAX_SENSOR_STALENESS:
            self._level.pop(area_id, None)
            return None
        level = next_humidity_level(self._level.get(area_id), value, low, high)
        self._level[area_id] = level
        return level

    def level(self, area_id: str) -> str | None:
        return self._level.get(area_id)

    def is_too_humid(self, area_id: str) -> bool:
        """The room is above its upper limit (and not yet back below the hysteresis)."""
        return self._level.get(area_id) == HUMIDITY_HIGH

    def ventilation_dries(
        self,
        area_id: str,
        indoor_temp: float | None,
        indoor_rh: float | None,
        outdoor_temp: float | None,
        outdoor_rh: float | None,
    ) -> bool:
        """``outdoor_air_dries`` with the room's own hysteresis; call while the room is too humid."""
        dries = outdoor_air_dries(
            indoor_temp, indoor_rh, outdoor_temp, outdoor_rh, running=self._venting.get(area_id, False)
        )
        self._venting[area_id] = dries
        return dries

    def stop_venting(self, area_id: str) -> None:
        self._venting.pop(area_id, None)

    def venting_rooms(self) -> list[str]:
        """Rooms that want their ventilation for humidity now; persisted for ``vented_before``."""
        return sorted(a for a, v in self._venting.items() if v)

    def load_venting_rooms(self, area_ids: Any) -> None:
        self._vented_before = {str(a) for a in area_ids} if isinstance(area_ids, list) else set()

    def vented_rooms(self) -> list[str]:
        """The rooms loaded by ``load_venting_rooms``, as they are stored."""
        return sorted(self._vented_before)

    def vented_before(self, area_id: str) -> bool:
        """The room wanted its ventilation for humidity before the restart (not for CO2/VOC)."""
        return area_id in self._vented_before

    def remove_room(self, area_id: str) -> None:
        for store in (self._level, self._seen, self._venting):
            store.pop(area_id, None)
        self._vented_before.discard(area_id)


def humidity_device_claims(
    rooms: dict[str, dict],
    room_states: dict[str, dict],
    get_state: Callable[[str], Any],
) -> tuple[dict[str, bool], set[str]]:
    """What the rooms under control want from their dehumidifiers and humidifiers.

    Returns ``(wanted, blocked)`` for ``VentilationController.async_reconcile``. A device is
    claimed by a room with the matching limit; it is wanted while the room is past that limit
    and the device of the other direction does not read on. A room past the other limit drops
    the device from its claim (off at once, not after the min run). An open window blocks it.
    One device in several rooms runs while any of them wants it; a window open in one blocks it.
    """
    wanted: dict[str, bool] = {}
    blocked: set[str] = set()
    for area_id, room in rooms.items():
        if not humidity_regulated(room):
            continue
        low, high = humidity_limits(room)
        rs = room_states.get(area_id) or {}
        dehum = room.get("dehumidifier_entity") or ""
        hum = room.get("humidifier_entity") or ""
        sides = (
            (dehum, high, bool(rs.get("humidity_high")), bool(rs.get("humidity_low")), hum),
            (hum, low, bool(rs.get("humidity_low")), bool(rs.get("humidity_high")), dehum),
        )
        for entity_id, limit, past, opposite, other in sides:
            if not entity_id or limit is None:
                continue
            if rs.get("window_open"):
                blocked.add(entity_id)
                continue
            if opposite:
                continue
            other_on = bool(other) and getattr(get_state(other), "state", None) == "on"
            wanted[entity_id] = wanted.get(entity_id, False) or (past and not other_on)
    for entity_id in blocked:
        wanted.pop(entity_id, None)
    return wanted, blocked
