"""Rooms follow their Home Assistant area (#494).

A room whose area was deleted rests: no control, no entities, but its settings and learned
data stay until the user deletes it, so an area deleted by mistake and created again under the
same name (same id) brings the room back as it was.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers import area_registry as ar

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


# Room field: its devices were switched off when it started resting, not again after a restart
REST_SWITCHED_OFF = "rest_switched_off"


def _known_area_ids(hass: HomeAssistant) -> set[str] | None:
    """Area ids Home Assistant knows; None when no area registry is loaded."""
    try:
        areas = ar.async_get(hass).async_list_areas()
    except (KeyError, AttributeError, TypeError):
        return None
    return {area.id for area in areas}


def rooms_with_area(hass: HomeAssistant, rooms: dict[str, dict]) -> dict[str, dict]:
    """The rooms RoomMind runs: those whose area still exists."""
    known = _known_area_ids(hass)
    if known is None:
        return rooms
    return {area_id: room for area_id, room in rooms.items() if area_id in known}


def rooms_without_area(hass: HomeAssistant, rooms: dict[str, dict]) -> dict[str, dict]:
    """Stored rooms whose area was deleted; they rest until the area is back or the user deletes them."""
    running = rooms_with_area(hass, rooms)
    return {area_id: room for area_id, room in rooms.items() if area_id not in running}
