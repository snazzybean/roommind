"""The room fan RoomMind runs while it heats or cools the room (#266).

A ceiling or standing fan (``room_fan_entity``) spreads the heat of a radiator or the cold of an
AC through the room. It runs while the room actually heats or cools (the shown mode: in Managed
Mode what the device reports, a unit held for its min run counts), per room for heating,
cooling or both. After heating it goes on while the heater still gives off heat. On/off only:
the speed stays as the user set it. Switching, minimum run and a hand on the switch are the
``VentilationController`` of #267 on its own instance.
"""

from __future__ import annotations

from collections.abc import Callable

from ..const import (
    DEFAULT_ROOM_FAN_MODE,
    HEATING_SYSTEM_RADIATOR,
    MODE_COOLING,
    MODE_HEATING,
    ROOM_FAN_COOL,
    ROOM_FAN_HEAT,
    ROOM_FAN_MODES,
    ROOM_FAN_POST_HEAT_MAX_MINUTES,
    ROOM_FAN_POST_HEAT_MINUTES,
)

_UNDERFLOOR = "underfloor"


def room_fan_mode(room: dict) -> str:
    """When the room's fan runs: ``heat``, ``cool`` or ``both`` (default)."""
    mode = room.get("room_fan_mode")
    return mode if mode in ROOM_FAN_MODES else DEFAULT_ROOM_FAN_MODE


class RoomFanTracker:
    """Per room: when it last heated, the start of the fan's post-run (in memory)."""

    def __init__(self) -> None:
        self._heated_at: dict[str, float] = {}

    def wants(self, area_id: str, room: dict, rs: dict, now: float) -> bool:
        fan_mode = room_fan_mode(room)
        heats = fan_mode != ROOM_FAN_COOL
        mode = rs.get("mode")
        if mode == MODE_HEATING and heats:
            self._heated_at[area_id] = now
            return True
        if mode == MODE_COOLING:
            self._heated_at.pop(area_id, None)
            return fan_mode != ROOM_FAN_HEAT
        if mode == MODE_HEATING:
            self._heated_at.pop(area_id, None)
            return False
        since = self._heated_at.get(area_id)
        if since is None:
            return False
        elapsed = now - since
        system = room.get("heating_system_type", "")
        # The stop cycle shows no afterglow yet (computed from the previous mode), hence the fixed
        # minutes first. A screed glows for hours: no post-run, the fan ran through the long run
        if system != _UNDERFLOOR and (
            elapsed < ROOM_FAN_POST_HEAT_MINUTES * 60
            or (
                system == HEATING_SYSTEM_RADIATOR
                and elapsed < ROOM_FAN_POST_HEAT_MAX_MINUTES * 60
                and rs.get("q_residual", 0.0) > 0.0
            )
        ):
            return True
        del self._heated_at[area_id]
        return False

    def forget(self, area_id: str) -> None:
        self._heated_at.pop(area_id, None)

    def retain(self, area_ids: set[str]) -> None:
        self._heated_at = {a: t for a, t in self._heated_at.items() if a in area_ids}

    def remove_room(self, area_id: str) -> None:
        self.forget(area_id)


def room_fan_claims(
    rooms: dict[str, dict],
    room_states: dict[str, dict],
    tracker: RoomFanTracker,
    now: float,
    is_running: Callable[[str], bool],
) -> tuple[dict[str, bool], set[str]]:
    """What the rooms under control want from their fans.

    Returns ``(wanted, blocked)`` for ``VentilationController.async_reconcile``. Every fan of a
    room passed in gets an entry, wanted or not, so one RoomMind runs goes off after its min run
    and not at once. An open window blocks it (off at once, the post-run dropped: the heat left).
    A room waiting for its first readings keeps the fan as it is. One fan in several rooms runs
    while any of them wants it; a window open in one blocks it.
    """
    wanted: dict[str, bool] = {}
    blocked: set[str] = set()
    tracker.retain(set(rooms))
    for area_id, room in rooms.items():
        entity_id = room.get("room_fan_entity") or ""
        if not entity_id or room.get("is_outdoor", False):
            continue
        rs = room_states.get(area_id) or {}
        if rs.get("window_open"):
            blocked.add(entity_id)
            tracker.forget(area_id)
            continue
        if rs.get("waiting_for_data"):
            want = is_running(entity_id)
        else:
            want = tracker.wants(area_id, room, rs, now)
        wanted[entity_id] = wanted.get(entity_id, False) or want
    for entity_id in blocked:
        wanted.pop(entity_id, None)
    return wanted, blocked
