"""Direct valve control: hold a TRV valve at a set opening through number entities (#413).

TRVs like the SONOFF TRVZB expose an opening degree (how far the valve opens when the TRV
wants heat) and a closing degree (how far it closes when it does not). Opening X with
closing 100 - X pins the valve at X % whatever the TRV's own controller decides. Both at
their maximum is the device default, a normal TRV.
"""

from __future__ import annotations

import logging
import math
import time
from typing import NamedTuple

from homeassistant.core import HomeAssistant

from ..const import VALVE_DEADBAND_PCT, VALVE_DWELL_SECONDS, make_roommind_context
from ..utils.temp_utils import celsius_to_ha_temp

_LOGGER = logging.getLogger(__name__)


class _Held(NamedTuple):
    at: float  # monotonic
    pct: int
    target: float | None
    opening_eid: str
    closing_eid: str


# climate entity -> last position that reached the device
_valve_sent: dict[str, _Held] = {}
# climate entities whose degrees were checked since the start without RoomMind holding them
_checked: set[str] = set()
# set on unload: a cycle still running must not pin a valve again
_stopped = False


def _now() -> float:
    return time.monotonic()


def held_opening(climate_eid: str) -> float | None:
    """Opening (0-1) RoomMind holds the valve at, None when it does not hold it."""
    held = _valve_sent.get(climate_eid)
    return held.pct / 100.0 if held is not None else None


def clear_valve_cache() -> None:
    """Forget sent positions (tests, integration setup)."""
    global _stopped  # noqa: PLW0603
    _valve_sent.clear()
    _checked.clear()
    _stopped = False


def _number_range(hass: HomeAssistant, entity_id: str) -> tuple[float, float, float] | None:
    """(min, max, step) of a number entity, None while it has no usable state."""
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unavailable", "unknown"):
        return None
    attrs = state.attributes
    try:
        lo = float(attrs.get("min", 0))
        hi = float(attrs.get("max", 100))
        step = float(attrs.get("step", 1) or 1)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lo) and math.isfinite(hi)) or hi <= lo:
        return None
    return lo, hi, step


def _scaled(pct: int, lo: float, hi: float, step: float) -> float:
    """Percent of the entity's range, on its step (an entity may run 0-99)."""
    value = lo + (hi - lo) * pct / 100.0
    value = lo + round((value - lo) / step) * step
    return round(min(hi, max(lo, value)), 3)


def _current(hass: HomeAssistant, entity_id: str) -> float | None:
    state = hass.states.get(entity_id)
    try:
        return float(state.state) if state is not None else None
    except (TypeError, ValueError):
        return None


async def _async_set_number(
    hass: HomeAssistant, entity_id: str, pct: int, area_id: str, *, force: bool = False
) -> bool | None:
    """Set a number entity to ``pct`` % of its range.

    True when sent, False when it already holds the value, None when it has no usable
    state or the call failed. ``force`` sends even if the state shows the value: right
    after a send the state may not have caught up with the device yet.
    """
    limits = _number_range(hass, entity_id)
    if limits is None:
        return None
    value = _scaled(pct, *limits)
    current = _current(hass, entity_id)
    if not force and current is not None and abs(current - value) < limits[2] / 2:
        return False
    try:
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": entity_id, "value": value},
            blocking=True,
            context=make_roommind_context(),
        )
    except Exception:  # noqa: BLE001
        _LOGGER.warning("Area '%s': number.set_value(%s) failed on '%s'", area_id, value, entity_id, exc_info=True)
        return None
    return True


async def async_set_valve(
    hass: HomeAssistant,
    climate_eid: str,
    opening_eid: str,
    closing_eid: str,
    opening_pct: float,
    *,
    area_id: str,
    target: float | None = None,
    urgent: bool = False,
) -> None:
    """Hold the valve at ``opening_pct`` (0-100).

    A position that reached the device stays for ``VALVE_DWELL_SECONDS`` unless the room
    target (``target``) moved or the caller marks the change ``urgent``, and changes below
    ``VALVE_DEADBAND_PCT`` never go out. Every move costs motor noise and battery, while
    the radiator takes minutes to follow anyway; a 0.2 K sensor step alone moves the
    demand by 20 %.
    """
    if _stopped:
        return
    pct = int(round(min(100.0, max(0.0, opening_pct))))
    held = _valve_sent.get(climate_eid)
    if held is not None and (held.opening_eid, held.closing_eid) == (opening_eid, closing_eid):
        target_moved = target is not None and (held.target is None or abs(target - held.target) > 0.05)
        if abs(pct - held.pct) < VALVE_DEADBAND_PCT or (
            not urgent and not target_moved and _now() - held.at < VALVE_DWELL_SECONDS
        ):
            if target_moved:
                # The position stays, the target it is held for does not (hand_back sends it)
                _valve_sent[climate_eid] = held._replace(target=target)
            return
    # Whatever reaches the device from here on has to be released again
    _checked.discard(climate_eid)
    results = [
        await _async_set_number(hass, opening_eid, pct, area_id),
        await _async_set_number(hass, closing_eid, 100 - pct, area_id),
    ]
    if None in results:
        # Try again next cycle; a half-applied position is not remembered as held
        _valve_sent.pop(climate_eid, None)
        return
    _valve_sent[climate_eid] = _Held(_now(), pct, target, opening_eid, closing_eid)


async def async_release_valve(
    hass: HomeAssistant,
    climate_eid: str,
    opening_eid: str,
    closing_eid: str,
    *,
    area_id: str,
    hand_back: bool = False,
) -> None:
    """Hand the valve back to the TRV: both degrees to their maximum, the device default.

    A valve RoomMind holds is always sent (its state may still show the old degrees or
    lag behind the last send) and stays on record until the entities answered. One it
    does not hold is checked once after the start (a restart forgets what was held), so
    degrees set by hand while RoomMind does not control the TRV stay. ``hand_back``
    (RoomMind lets go for good: climate control off, room removed, unload) also sets the
    TRV to the room target it was pinned for; its proportional setpoint would otherwise
    heat the room flat out once the valve is free.
    """
    held = _valve_sent.get(climate_eid)
    if held is None and climate_eid in _checked:
        return
    force = held is not None
    results = [await _async_set_number(hass, eid, 100, area_id, force=force) for eid in (opening_eid, closing_eid)]
    if None in results:
        return
    _valve_sent.pop(climate_eid, None)
    _checked.add(climate_eid)
    if hand_back and held is not None and held.target is not None:
        try:
            await hass.services.async_call(
                "climate",
                "set_temperature",
                {"entity_id": climate_eid, "temperature": celsius_to_ha_temp(hass, held.target)},
                blocking=True,
                context=make_roommind_context(),
            )
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Area '%s': handing the setpoint back to '%s' failed", area_id, climate_eid, exc_info=True)


async def async_release_orphaned_valves(hass: HomeAssistant, configured: dict[str, tuple[str, str]]) -> None:
    """Release valves RoomMind still holds but no longer has in its config.

    A cycle that started before a save or delete can pin a valve again after the save
    released it; from then on no config names its number entities.
    """
    for climate_eid, held in list(_valve_sent.items()):
        if configured.get(climate_eid) != (held.opening_eid, held.closing_eid):
            await async_release_valve(
                hass, climate_eid, held.opening_eid, held.closing_eid, area_id="unconfigured", hand_back=True
            )


async def async_release_all_valves(hass: HomeAssistant, configured: dict[str, tuple[str, str]]) -> None:
    """Unload: stop pinning and hand every configured or still held valve back."""
    global _stopped  # noqa: PLW0603
    _stopped = True
    valves = {eid: (held.opening_eid, held.closing_eid) for eid, held in _valve_sent.items()} | configured
    for climate_eid, (opening, closing) in valves.items():
        try:
            await async_release_valve(hass, climate_eid, opening, closing, area_id="unload", hand_back=True)
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Releasing the valve of '%s' on unload failed", climate_eid, exc_info=True)
