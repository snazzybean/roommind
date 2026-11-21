"""Direct valve control: hold a TRV valve at a set opening through number entities (#413).

TRVs like the SONOFF TRVZB expose an opening degree (how far the valve opens when the TRV
wants heat) and a closing degree (how far it closes when it does not). Opening X with
closing 100 - X pins the valve at X % whatever the TRV's own controller decides. Both at
their maximum is the device default, a normal TRV.

The SONOFF TRV-ZBT names the second value the opening while idle (#482): X and X pin the
valve, 100 and 0 hand it back as a normal TRV.

TRVs like the Bosch BTH-RA have one entity, the valve position itself (``pi_heating_demand``,
#537), passed here with an empty closing entity. A written position holds only for a while
(BTH-RA: 15 minutes) before the TRV's own controller moves the valve again, so RoomMind
sends a held position again every ``VALVE_SINGLE_RESEND_SECONDS``. There is no device
default to hand back: a release closes the valve and the TRV takes over by itself.
"""

from __future__ import annotations

import logging
import math
import time
from typing import NamedTuple

from homeassistant.core import HomeAssistant

from ..const import VALVE_DEADBAND_PCT, VALVE_DWELL_SECONDS, VALVE_SINGLE_RESEND_SECONDS, make_roommind_context
from ..utils.device_utils import ValveEntities
from ..utils.temp_utils import celsius_to_ha_temp

_LOGGER = logging.getLogger(__name__)


class _Held(NamedTuple):
    at: float  # monotonic
    pct: int
    target: float | None
    opening_eid: str
    closing_eid: str
    idle_opening: bool = False

    @property
    def valve(self) -> ValveEntities:
        return ValveEntities(self.opening_eid, self.closing_eid, self.idle_opening)


# climate entity -> last position that reached the device
_valve_sent: dict[str, _Held] = {}
# climate entity -> closing mode its degrees were checked in since the start without RoomMind holding them
_checked: dict[str, bool] = {}
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
    idle_opening: bool = False,
) -> None:
    """Hold the valve at ``opening_pct`` (0-100).

    A position that reached the device stays for ``VALVE_DWELL_SECONDS`` unless the room
    target (``target``) moved or the caller marks the change ``urgent``, and changes below
    ``VALVE_DEADBAND_PCT`` never go out. Every move costs motor noise and battery, while
    the radiator takes minutes to follow anyway; a 0.2 K sensor step alone moves the
    demand by 20 %. ``idle_opening``: the second entity is the opening while idle (#482).

    Without ``closing_eid`` the TRV has a single valve position entity (#537). Its own
    controller takes the valve back some time after a write, so a held position goes out
    again after ``VALVE_SINGLE_RESEND_SECONDS``, also unchanged.
    """
    if _stopped:
        return
    single = not closing_eid
    pct = int(round(min(100.0, max(0.0, opening_pct))))
    held = _valve_sent.get(climate_eid)
    resend = False
    if held is not None and held.valve == (opening_eid, closing_eid, idle_opening):
        target_moved = target is not None and (held.target is None or abs(target - held.target) > 0.05)
        resend = single and _now() - held.at >= VALVE_SINGLE_RESEND_SECONDS
        if abs(pct - held.pct) < VALVE_DEADBAND_PCT:
            if not resend:
                if target_moved:
                    # The position stays, the target it is held for does not (hand_back sends it)
                    _valve_sent[climate_eid] = held._replace(target=target)
                return
            # Below the deadband the valve keeps its position: the resend must not move the motor
            pct = held.pct
        elif not urgent and not target_moved and _now() - held.at < VALVE_DWELL_SECONDS:
            return
    # Whatever reaches the device from here on has to be released again
    _checked.pop(climate_eid, None)
    if single:
        # ``resend`` forces: the state still shows the held value while the TRV is about to let go
        results = [await _async_set_number(hass, opening_eid, pct, area_id, force=resend)]
    else:
        results = [
            await _async_set_number(hass, opening_eid, pct, area_id),
            await _async_set_number(hass, closing_eid, pct if idle_opening else 100 - pct, area_id),
        ]
    if None in results:
        # Try again next cycle; a half-applied position is not remembered as held
        _valve_sent.pop(climate_eid, None)
        return
    _valve_sent[climate_eid] = _Held(_now(), pct, target, opening_eid, closing_eid, idle_opening)


async def async_release_valve(
    hass: HomeAssistant,
    climate_eid: str,
    opening_eid: str,
    closing_eid: str,
    *,
    area_id: str,
    hand_back: bool = False,
    idle_opening: bool = False,
) -> None:
    """Hand the valve back to the TRV: both degrees to their maximum, the device default.

    With ``idle_opening`` (#482) the second entity goes to 0 instead: closed while idle.
    A TRV with a single valve position entity (no ``closing_eid``, #537) has no default to
    go back to: its valve is closed, and its own controller moves it again by itself.

    A valve RoomMind holds is always sent (its state may still show the old degrees or
    lag behind the last send) and stays on record until the entities answered. One it
    does not hold is checked once after the start (a restart forgets what was held), so
    degrees set by hand while RoomMind does not control the TRV stay. ``hand_back``
    (RoomMind lets go for good: climate control off, room removed, unload) also sets the
    TRV to the room target it was pinned for; its proportional setpoint would otherwise
    heat the room flat out once the valve is free.
    """
    held = _valve_sent.get(climate_eid)
    # Checked in the other closing mode does not count: its hand-back would open a TRV-ZBT while idle
    if held is None and _checked.get(climate_eid) == idle_opening:
        return
    force = held is not None
    if not closing_eid and held is None:
        # Nothing to restore: a valve RoomMind does not hold is the TRV's own
        return
    if not closing_eid:
        results = [await _async_set_number(hass, opening_eid, 0, area_id, force=force)]
    else:
        results = [
            await _async_set_number(hass, opening_eid, 100, area_id, force=force),
            await _async_set_number(hass, closing_eid, 0 if idle_opening else 100, area_id, force=force),
        ]
    if None in results:
        return
    _valve_sent.pop(climate_eid, None)
    _checked[climate_eid] = idle_opening
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


async def async_release_orphaned_valves(hass: HomeAssistant, configured: dict[str, ValveEntities]) -> None:
    """Release valves RoomMind still holds but no longer has in its config.

    A cycle that started before a save or delete can pin a valve again after the save
    released it; from then on no config names its number entities. A changed closing
    mode alone is no orphan: the next cycle writes the valve in the new mode.
    """
    for climate_eid, held in list(_valve_sent.items()):
        valve = configured.get(climate_eid)
        if valve is None or valve[:2] != (held.opening_eid, held.closing_eid):
            await async_release_valve(
                hass,
                climate_eid,
                held.opening_eid,
                held.closing_eid,
                area_id="unconfigured",
                hand_back=True,
                idle_opening=held.idle_opening,
            )


async def async_release_all_valves(hass: HomeAssistant, configured: dict[str, ValveEntities]) -> None:
    """Unload: stop pinning and hand every configured or still held valve back."""
    global _stopped  # noqa: PLW0603
    _stopped = True
    valves = {eid: held.valve for eid, held in _valve_sent.items()} | configured
    for climate_eid, valve in valves.items():
        try:
            await async_release_valve(
                hass,
                climate_eid,
                valve.opening,
                valve.closing,
                area_id="unload",
                hand_back=True,
                idle_opening=valve.idle_opening,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Releasing the valve of '%s' on unload failed", climate_eid, exc_info=True)
