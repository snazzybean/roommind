"""Rooms follow their Home Assistant area (#494).

A room whose area was deleted rests: no control, no entities, but its settings and learned
data stay until the user deletes it, so an area deleted by mistake and created again under the
same name (same id) brings the room back as it was.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import floor_registry as fr

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


def ha_floor_order(hass: HomeAssistant) -> list[str]:
    """Floor ids in Home Assistant's own order (its areas page, reorderable there); [] without registry."""
    try:
        return [floor.floor_id for floor in fr.async_get(hass).async_list_floors()]
    except (KeyError, AttributeError, TypeError):
        return []


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


def assign_area_once(hass: HomeAssistant, entity_id: str, area_id: str, domain: str) -> None:
    """Put an entity into its room's area the first time it appears (area cards, Assist).

    Marked in the entity's registry options, so an area the user removes or changes stays that way.
    """
    registry = er.async_get(hass)
    entry = registry.async_get(entity_id)
    if entry is None:
        return
    options = dict(entry.options.get(domain, {}))
    if options.get("area_assigned"):
        return
    if entry.area_id is None and ar.async_get(hass).async_get_area(area_id) is not None:
        registry.async_update_entity(entity_id, area_id=area_id)
    registry.async_update_entity_options(entity_id, domain, {**options, "area_assigned": True})
