"""Schedule utilities for resolving future target temperatures."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from ..const import DEFAULT_COMFORT_COOL, DEFAULT_COMFORT_HEAT, DEFAULT_ECO_COOL, DEFAULT_ECO_HEAT, SCHEDULE_STATE_ON, TargetTemps

_LOGGER = logging.getLogger(__name__)


def resolve_target_at_time(
    ts: float,
    schedule_blocks: dict | None,
    override_until: float | None,
    override_temp: float | None,
    vacation_until: float | None,
    vacation_temp: float | None,
    comfort_temp: float,
    eco_temp: float,
    presence_away: bool = False,
    block_temp_converter: "Callable[[float], float] | None" = None,
    presence_away_action: str = "eco",
    schedule_off_action: str = "eco",
) -> float | None:
    """Resolve what the target temp would be at a specific timestamp.

    Returns None when the action is "off" (devices should be turned off).
    """
    # 1. Override
    if override_until is not None and ts < override_until and override_temp is not None:
        return float(override_temp)
    # 2. Vacation
    if vacation_until is not None and ts < vacation_until and vacation_temp is not None:
        return float(vacation_temp)
    # 2.5 Presence
    if presence_away:
        if presence_away_action == "off":
            return None
        return eco_temp
    # 3. Schedule blocks
    if schedule_blocks is None:
        return comfort_temp
    dt = datetime.fromtimestamp(ts)
    day_name = dt.strftime("%A").lower()
    current_time = dt.time()
    day_blocks = schedule_blocks.get(day_name, [])
    for block in day_blocks:
        from_raw = block.get("from", "00:00:00")
        to_raw = block.get("to", "00:00:00")
        from_time = from_raw if hasattr(from_raw, "hour") else datetime.strptime(str(from_raw), "%H:%M:%S").time()
        to_time = to_raw if hasattr(to_raw, "hour") else datetime.strptime(str(to_raw), "%H:%M:%S").time()
        if from_time <= current_time < to_time:
            data = block.get("data", {})
            block_temp = data.get("temperature")
            if block_temp is not None:
                try:
                    val = float(block_temp)
                    return block_temp_converter(val) if block_temp_converter else val
                except (ValueError, TypeError):
                    pass
            return comfort_temp
    # Not in any block → eco or off
    if schedule_off_action == "off":
        return None
    return eco_temp



def resolve_targets_at_time(
    ts: float,
    schedule_blocks: dict | None,
    override_until: float | None,
    override_temp: float | None,
    vacation_until: float | None,
    vacation_temp: float | None,
    comfort_heat: float,
    comfort_cool: float,
    eco_heat: float,
    eco_cool: float,
    presence_away: bool = False,
    block_temp_converter: "Callable[[float], float] | None" = None,
    presence_away_action: str = "eco",
    schedule_off_action: str = "eco",
) -> TargetTemps:
    """Resolve dual heat/cool target temps at a specific timestamp.

    Returns TargetTemps(heat, cool). None values mean "force off".
    """
    # 1. Override — single-point target
    if override_until is not None and ts < override_until and override_temp is not None:
        t = float(override_temp)
        return TargetTemps(heat=t, cool=t)
    # 2. Vacation — heat setback, cooling stays at eco_cool
    if vacation_until is not None and ts < vacation_until and vacation_temp is not None:
        t = float(vacation_temp)
        return TargetTemps(heat=t, cool=max(t, eco_cool))
    # 2.5 Presence
    if presence_away:
        if presence_away_action == "off":
            return TargetTemps(heat=None, cool=None)
        return TargetTemps(heat=eco_heat, cool=eco_cool)
    # 3. Schedule blocks
    if schedule_blocks is None:
        return TargetTemps(heat=comfort_heat, cool=comfort_cool)
    dt = datetime.fromtimestamp(ts)
    day_name = dt.strftime("%A").lower()
    current_time = dt.time()
    day_blocks = schedule_blocks.get(day_name, [])
    for block in day_blocks:
        from_raw = block.get("from", "00:00:00")
        to_raw = block.get("to", "00:00:00")
        from_time = from_raw if hasattr(from_raw, "hour") else datetime.strptime(str(from_raw), "%H:%M:%S").time()
        to_time = to_raw if hasattr(to_raw, "hour") else datetime.strptime(str(to_raw), "%H:%M:%S").time()
        if from_time <= current_time < to_time:
            data = block.get("data", {})
            # Check for split heat/cool temps first
            heat_temp_raw = data.get("heat_temperature")
            cool_temp_raw = data.get("cool_temperature")
            if heat_temp_raw is not None or cool_temp_raw is not None:
                h = comfort_heat
                c = comfort_cool
                if heat_temp_raw is not None:
                    try:
                        val = float(heat_temp_raw)
                        h = block_temp_converter(val) if block_temp_converter else val
                    except (ValueError, TypeError):
                        pass
                if cool_temp_raw is not None:
                    try:
                        val = float(cool_temp_raw)
                        c = block_temp_converter(val) if block_temp_converter else val
                    except (ValueError, TypeError):
                        pass
                return TargetTemps(heat=h, cool=c)
            block_temp = data.get("temperature")
            if block_temp is not None:
                try:
                    val = float(block_temp)
                    t = block_temp_converter(val) if block_temp_converter else val
                    return TargetTemps(heat=t, cool=t)  # single-point
                except (ValueError, TypeError):
                    pass
            return TargetTemps(heat=comfort_heat, cool=comfort_cool)
    # Not in any block → eco or off
    if schedule_off_action == "off":
        return TargetTemps(heat=None, cool=None)
    return TargetTemps(heat=eco_heat, cool=eco_cool)


def resolve_schedule_index(
    hass: "HomeAssistant",
    room: dict,
    *,
    schedules_key: str = "schedules",
    selector_key: str = "schedule_selector_entity",
) -> int:
    """Return the 0-based index of the active schedule, or -1 if none.

    This is the single source of truth for schedule selector resolution,
    used by both the coordinator and schedule_utils helpers.

    Supports custom key names for reuse with different schedule types
    (e.g. cover schedules).
    """
    schedules = room.get(schedules_key, [])
    if not schedules:
        return -1

    selector_entity = room.get(selector_key, "")
    if not selector_entity:
        return 0

    state = hass.states.get(selector_entity)
    if state is None or state.state in ("unavailable", "unknown"):
        return 0

    if selector_entity.startswith("input_boolean."):
        return 1 if state.state == "on" else 0

    if selector_entity.startswith("input_number."):
        try:
            idx = int(float(state.state)) - 1  # 1-based → 0-based
        except (ValueError, TypeError):
            return 0
        if 0 <= idx < len(schedules):
            return idx
        return -1

    # Fallback for unknown entity domains
    return 0


def get_active_schedule_entity(
    hass: HomeAssistant,
    room: dict,
) -> str | None:
    """Return the entity_id of the currently active schedule, or None."""
    schedules = room.get("schedules", [])
    idx = resolve_schedule_index(hass, room)
    if 0 <= idx < len(schedules):
        return schedules[idx].get("entity_id", "") or None
    return None


async def read_schedule_blocks(
    hass: HomeAssistant,
    schedule_entity_id: str,
) -> dict | None:
    """Read weekly schedule blocks via schedule.get_schedule service."""
    if not schedule_entity_id or not schedule_entity_id.startswith("schedule."):
        return None
    try:
        response = await hass.services.async_call(
            "schedule", "get_schedule",
            {"entity_id": schedule_entity_id},
            blocking=True,
            return_response=True,
        )
        if response:
            return response.get(schedule_entity_id, {}) or None
    except Exception:  # noqa: BLE001
        _LOGGER.debug("schedule.get_schedule failed for %s", schedule_entity_id)
    return None


def make_target_resolver(
    schedule_blocks: dict | None,
    room: dict,
    settings: dict,
    hass: "HomeAssistant | None" = None,
    presence_away: bool = False,
    mold_prevention_delta: float = 0.0,
) -> Callable[[float], TargetTemps]:
    """Create a sync target resolver function (schedule blocks pre-fetched).

    Returns TargetTemps with None values for timestamps where devices should
    be turned off.
    """
    comfort_heat = room.get("comfort_heat", room.get("comfort_temp", DEFAULT_COMFORT_HEAT))
    comfort_cool = room.get("comfort_cool", DEFAULT_COMFORT_COOL)
    eco_heat = room.get("eco_heat", room.get("eco_temp", DEFAULT_ECO_HEAT))
    eco_cool = room.get("eco_cool", DEFAULT_ECO_COOL)
    override_until = room.get("override_until")
    override_temp = room.get("override_temp")
    vacation_until = settings.get("vacation_until")
    vacation_temp = settings.get("vacation_temp")
    presence_away_action = settings.get("presence_away_action", "eco")
    schedule_off_action = settings.get("schedule_off_action", "eco")

    converter: Callable[[float], float] | None = None
    if hass is not None:
        from .temp_utils import ha_temp_to_celsius
        _hass = hass
        converter = lambda v: ha_temp_to_celsius(_hass, v)  # noqa: E731

    def resolver(ts: float) -> TargetTemps:
        targets = resolve_targets_at_time(
            ts, schedule_blocks,
            override_until, override_temp,
            vacation_until, vacation_temp,
            comfort_heat, comfort_cool,
            eco_heat, eco_cool,
            presence_away=presence_away,
            block_temp_converter=converter,
            presence_away_action=presence_away_action,
            schedule_off_action=schedule_off_action,
        )
        if targets.heat is None and targets.cool is None:
            return targets
        return TargetTemps(
            heat=targets.heat + mold_prevention_delta if targets.heat is not None else None,
            cool=targets.cool if targets.cool is not None else None,
        )
    return resolver
