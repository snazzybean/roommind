"""Overrides held until the next change also end when presence switches between home and away."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .presence_utils import is_presence_away

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def presence_applies(room: dict, settings: dict) -> bool:
    """Return True when presence detection is on with persons to watch and the room does not ignore it."""
    return (
        bool(settings.get("presence_enabled", False))
        and bool(settings.get("presence_persons"))
        and not room.get("ignore_presence", False)
    )


def room_presence_away(hass: HomeAssistant, room: dict, settings: dict) -> bool:
    """Return True when presence counts as away for this room (False for rooms that ignore presence)."""
    return not room.get("ignore_presence", False) and is_presence_away(hass, room, settings)


def override_presence_binding(hass: HomeAssistant, room: dict, settings: dict) -> bool | None:
    """Return the presence an override held until the next change is bound to (``override_presence_away``).

    The presence at the time it is set; the coordinator ends the override once presence
    differs. None where presence does not apply to the room: only the schedule ends it then.
    """
    return room_presence_away(hass, room, settings) if presence_applies(room, settings) else None


def override_ended_by_presence(room: dict, presence_away: bool) -> bool:
    """Return True when an override bound to presence saw presence switch."""
    held_at = room.get("override_presence_away")
    return held_at is not None and bool(held_at) != presence_away
