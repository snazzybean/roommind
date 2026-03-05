"""Presence detection utilities for RoomMind."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def is_presence_away(hass: HomeAssistant, room: dict, settings: dict) -> bool:
    """Return True if presence detection says all relevant persons are away.

    Per-room persons take precedence over global persons.
    Fail-safe: unavailable/unknown entities are treated as "home".
    """
    if not settings.get("presence_enabled", False):
        return False
    global_persons = settings.get("presence_persons", [])
    if not global_persons:
        return False

    room_persons = room.get("presence_persons", [])
    persons = room_persons if room_persons else global_persons

    for pid in persons:
        state = hass.states.get(pid)
        if state is None or state.state in ("unavailable", "unknown"):
            return False  # fail-safe: treat as home
        if _is_entity_home(state):
            return False
    return True


def _is_entity_home(state) -> bool:
    """Check if a presence entity indicates someone is home.

    person.*/device_tracker.* use "home"/"not_home"; binary_sensor/input_boolean use "on"/"off".
    """
    if state.entity_id.startswith(("person.", "device_tracker.")):
        return state.state == "home"
    return state.state == "on"
