"""Predictive learned-occupancy schedule (consumer of Area Occupancy Detection).

Opt-in per room. Instead of a manual ``schedule.*`` window, the comfort/eco
window is driven by the occupancy prior learned by the Area Occupancy Detection
integration and exposed via its ``get_time_priors`` service. The prior is
evaluated at each (future) timestep so the MPC can pre-heat a room *before* its
habitual occupancy.

Kept in a dedicated module so the feature is fully additive and isolated: the
manual-schedule path in ``schedule_utils.py`` is untouched, and every fallback
(missing service, unmapped area, immature priors) reverts to the manual
schedule. The priority ladder mirrors ``schedule_utils.make_target_resolver``
exactly — override → vacation → presence-away → *window* → comfort/eco — and
only the window step is sourced from the learned prior.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from homeassistant.util import dt as dt_util

from ..const import (
    DEFAULT_COMFORT_COOL,
    DEFAULT_COMFORT_HEAT,
    DEFAULT_ECO_COOL,
    DEFAULT_ECO_HEAT,
    TargetTemps,
)

_LOGGER = logging.getLogger(__name__)


def build_prior_matrix(response: dict | None, area_id: str) -> tuple[dict[tuple[int, int], float] | None, int]:
    """Extract one area's learned priors from a ``get_time_priors`` response.

    Returns ``(matrix, slot_minutes)`` where ``matrix`` maps
    ``(day_of_week, time_slot)`` to the learned prior, or ``(None, 60)`` when the
    response is missing/empty or the area is not present — callers then fall back
    to the manual schedule. Slots the area has never observed are dropped, so an
    area-level fallback value can never be read as evidence.
    """
    if not isinstance(response, dict):
        return None, 60
    areas = response.get("areas") or {}
    default_slot_minutes = int(response.get("slot_minutes", 60) or 60)
    for area in areas.values():
        if not isinstance(area, dict) or area.get("area_id") != area_id:
            continue
        slot_minutes = int(area.get("slot_minutes", default_slot_minutes) or default_slot_minutes)
        # ``slots_raw`` is the learned per-slot prior on its own. ``slots`` blends it
        # with the area's global prior in logit space, which compresses the range so
        # far that an absolute threshold stops being meaningful for a room occupied
        # only a few hours a day. ``slots`` stays the fallback for an Area Occupancy
        # build that predates ``slots_raw``.
        slots = area.get("slots_raw") or area.get("slots") or {}
        # ``data_points`` counts the observations behind each slot; 0 means the slot
        # was never seen and its value is an area-level fallback, not evidence.
        # Dropping those stops a fallback from crossing the threshold on its own: in
        # a room whose global prior sits above the threshold, every unobserved slot
        # would otherwise read as comfort. If nothing survives, the matrix is empty
        # and the room reverts to its manual schedule.
        observations = area.get("data_points") or {}
        matrix: dict[tuple[int, int], float] = {}
        for key, value in slots.items():
            if observations and not observations.get(key):
                continue
            try:
                day_str, slot_str = str(key).split(",")
                matrix[(int(day_str), int(slot_str))] = float(value)
            except (ValueError, TypeError):
                continue
        return (matrix or None), slot_minutes
    return None, default_slot_minutes


def prior_at(ts: float, matrix: dict[tuple[int, int], float] | None, slot_minutes: int) -> float | None:
    """Return the learned prior for the slot containing ``ts``.

    ``ts`` is bucketed in Home Assistant local time to match how Area Occupancy
    learns its ``(day_of_week, time_slot)`` priors. Returns None if the slot has
    no learned value.
    """
    if not matrix:
        return None
    local = dt_util.as_local(datetime.fromtimestamp(ts, tz=UTC))
    slot = (local.hour * 60 + local.minute) // (slot_minutes or 60)
    return matrix.get((local.weekday(), slot))


def resolve_prior_window(
    ts: float,
    matrix: dict[tuple[int, int], float] | None,
    threshold: float,
    slot_minutes: int,
    comfort_heat: float,
    comfort_cool: float,
    eco_heat: float,
    eco_cool: float,
    schedule_off_action: str = "eco",
) -> TargetTemps:
    """Comfort/eco decision for one timestep from the learned prior.

    ``prior >= threshold`` → comfort; otherwise eco (or off when
    ``schedule_off_action == "off"``). Mirrors the schedule on/off → comfort/eco
    mapping, so an unlearned/below-threshold slot behaves exactly like a
    "schedule off" period.
    """
    prob = prior_at(ts, matrix, slot_minutes)
    if prob is not None and prob >= threshold:
        return TargetTemps(heat=comfort_heat, cool=comfort_cool)
    if schedule_off_action == "off":
        return TargetTemps(heat=None, cool=None)
    return TargetTemps(heat=eco_heat, cool=eco_cool)


def make_learned_target_resolver(
    matrix: dict[tuple[int, int], float] | None,
    threshold: float,
    slot_minutes: int,
    room: dict,
    settings: dict,
    presence_away: bool = False,
    mold_prevention_delta: float = 0.0,
) -> Callable[[float], TargetTemps]:
    """Sync target resolver over the learned prior (drop-in for the horizon).

    Structurally identical to ``schedule_utils.make_target_resolver`` — same
    override/vacation/presence ladder and the same mold-prevention tail — with
    the schedule-block window replaced by the learned-prior window. Returned as a
    closure so the MPC can evaluate any future timestep.
    """
    comfort_heat = room.get("comfort_heat", room.get("comfort_temp", DEFAULT_COMFORT_HEAT))
    comfort_cool = room.get("comfort_cool", DEFAULT_COMFORT_COOL)
    eco_heat = room.get("eco_heat", room.get("eco_temp", DEFAULT_ECO_HEAT))
    eco_cool = room.get("eco_cool", DEFAULT_ECO_COOL)
    override_until = room.get("override_until")
    override_heat = room.get("override_heat")
    override_cool = room.get("override_cool")
    vacation_until = settings.get("vacation_until")
    vacation_temp = settings.get("vacation_temp")
    presence_away_action = settings.get("presence_away_action", "eco")
    schedule_off_action = settings.get("schedule_off_action", "eco")
    presence_clears_override = bool(settings.get("presence_clears_override", False))

    def resolver(ts: float) -> TargetTemps:
        # 1. Override — split heat/cool dead-band
        if (override_heat is not None or override_cool is not None) and (override_until is None or ts < override_until):
            if not (presence_away and presence_clears_override):
                return TargetTemps(heat=override_heat, cool=override_cool)
        # 2. Vacation — heat setback, cooling stays at eco_cool
        if vacation_until is not None and ts < vacation_until and vacation_temp is not None:
            t = float(vacation_temp)
            return TargetTemps(heat=t, cool=max(t, eco_cool))
        # 2.5 Presence
        if presence_away:
            if presence_away_action == "off":
                return TargetTemps(heat=None, cool=None)
            return TargetTemps(heat=eco_heat, cool=eco_cool)
        # 3. Learned-prior window (replaces the schedule-block window)
        targets = resolve_prior_window(
            ts,
            matrix,
            threshold,
            slot_minutes,
            comfort_heat,
            comfort_cool,
            eco_heat,
            eco_cool,
            schedule_off_action,
        )
        if targets.heat is None and targets.cool is None:
            return targets
        return TargetTemps(
            heat=targets.heat + mold_prevention_delta if targets.heat is not None else None,
            cool=targets.cool if targets.cool is not None else None,
        )

    return resolver
