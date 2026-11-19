"""Air conditioners in dry while a room is too humid and needs neither heating nor cooling (#440).

Rooms with an upper humidity limit and no dehumidifier of their own (or one unreadable for
``AC_DRY_DEHUMIDIFIER_GONE_MINUTES``) let an AC that offers ``dry`` run in it while the room is
too humid and the controller idles. Heating and cooling always come first: the room's mode is
decided before, and a room that heats or cools ends dry in the same cycle, ``async_apply`` then
switches the unit. Dry cools as well, so it keeps to the room's band: it ends
``AC_DRY_STOP_MARGIN_K`` above the heat target and starts again only ``AC_DRY_START_MARGIN_K``
above it, and not within ``AC_DRY_AFTER_HEATING_MINUTES`` of the room heating. Like coil dry, a
running unit is left out of ``async_apply`` and counts as a running member of its compressor
group.

The unit gets the stop point as its setpoint: most units dry like they cool, down to the
setpoint, so one left at its setback (cool 27 °C) would not dry at all, and the unit stops by
itself if RoomMind's room sensor lags. A unit idling in setback goes back to its mode and
setpoint afterwards; off and fan_only units get their idle action from ``async_apply``.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from homeassistant.core import HomeAssistant

from ..const import (
    AC_DRY_AFTER_HEATING_MINUTES,
    AC_DRY_DEHUMIDIFIER_GONE_MINUTES,
    AC_DRY_MAX_BELOW_COOL_K,
    AC_DRY_MIN_OFF_MINUTES,
    AC_DRY_MIN_RUN_MINUTES,
    AC_DRY_REPORT_SECONDS,
    AC_DRY_SETTLE_MINUTES,
    AC_DRY_START_MARGIN_K,
    AC_DRY_STOP_MARGIN_K,
    CLIMATE_MODE_COOL_ONLY,
    MODE_HEATING,
    MODE_IDLE,
)
from ..control.mpc_controller import async_climate_command, async_turn_off_climate, device_setpoint_ha
from ..utils.device_utils import IDLE_ACTION_SETBACK, get_ac_eids, get_idle_action, get_setpoint_offset

_LOGGER = logging.getLogger(__name__)

DRY = "dry"
_NO_READING = ("unavailable", "unknown")
_END_CONTROL_OFF = "climate control off"
_END_DRY_ENOUGH = "humidity back in range"
_END_COLD = "room at its lower limit"
_END_NOT_ALLOWED = "room may not dry"
_END_WINDOW = "window open"
_END_DEHUMIDIFIER_BACK = "the room's dehumidifier is back"


def dry_stop_temp(heat: float | None, cool: float | None, climate_mode: str) -> float | None:
    """Room temperature (°C) at which dry ends: above the heat target, at most 3 K under the cool one.

    None without a target (the room is switched off).
    """
    bounds: list[float] = []
    if heat is not None and climate_mode != CLIMATE_MODE_COOL_ONLY:
        bounds.append(heat)
    if cool is not None:
        bounds.append(cool - AC_DRY_MAX_BELOW_COOL_K)
    return max(bounds) + AC_DRY_STOP_MARGIN_K if bounds else None


@dataclass
class _Dry:
    """A unit RoomMind runs in dry. Persisted (see get_state)."""

    area_id: str
    since: float
    setpoint: float | None = None
    # Shown dry since the switch: from then on another mode is a hand on the device
    confirmed: bool = False
    # A setback unit's mode and setpoint before dry, given back afterwards
    prev_mode: str | None = None
    prev_temperature: float | None = None


@dataclass
class AcDryRoomResult:
    """What the coordinator needs after one room.

    ``drying_eids`` run in dry (compressor on, no EKF training); ``excluded_eids`` stay out of
    async_apply this cycle: those and a setback unit just given back its mode.
    """

    drying_eids: set[str] = field(default_factory=set)
    restored_eids: set[str] = field(default_factory=set)

    # Dry ran this cycle or ended less than AC_DRY_SETTLE_MINUTES ago: the air still sits below the walls
    settling: bool = False

    @property
    def active(self) -> bool:
        return bool(self.drying_eids)

    @property
    def excluded_eids(self) -> set[str]:
        return self.drying_eids | self.restored_eids


class AcDryManager:
    """Start, hold and end dry per AC of a too humid room."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._running: dict[str, _Dry] = {}
        self._heated_at: dict[str, float] = {}
        # Per room: last cycle a unit dried
        self._dried_at: dict[str, float] = {}
        # Per room: dry reached the stop point, no new start before this time
        self._rest_until: dict[str, float] = {}
        # Units that did not take dry or were changed by hand, until the room is no longer too humid
        self._declined: dict[str, set[str]] = {}
        # Per room: since when its own dehumidifier does not read (in memory)
        self._dehumidifier_gone_since: dict[str, float] = {}
        self._dirty = False

    def is_running(self, entity_id: str) -> bool:
        return entity_id in self._running

    def running_eids(self, area_id: str) -> set[str]:
        return {eid for eid, st in self._running.items() if st.area_id == area_id}

    async def async_process_room(
        self,
        *,
        area_id: str,
        room: dict,
        mode: str,
        too_humid: bool,
        allowed: bool,
        may_cool: bool,
        control_active: bool,
        window_open: bool = False,
        dehumidifier_reads: bool | None = None,
        waiting: bool,
        room_temp: float | None,
        stop_temp: float | None,
        compressor_forced_on: set[str],
        blocked_eids: set[str],
        group_conflicts: dict[str, frozenset[str]],
        can_start: Callable[[str], bool],
        coil_dry_follows: Callable[[str], bool] = lambda _eid: False,
        switched_off: bool = False,
    ) -> AcDryRoomResult:
        """Advance dry for every AC of the room.

        ``allowed``: the room may dry at all (Full Control, upper limit, switch on, not switched
        off, not heat only). ``window_open`` ends a run at once and gives no setback back: the
        window pause in async_apply takes the unit over in the same cycle.
        ``dehumidifier_reads``: None without a dehumidifier of the room's own; it is the tool the
        user picked, so an AC only starts once it was unreadable for
        ``AC_DRY_DEHUMIDIFIER_GONE_MINUTES``, and a run ends after its min run once it is back.
        ``may_cool``: the outdoor limit lets the room cool now; asked only for a start, a reading going back and forth over the cooling
        minimum must not end a run. ``coil_dry_follows``: units whose coil dry takes over after
        dry, they get no setback back. ``switched_off``: the room's schedule or presence switches
        it off, async_apply sends the off. ``control_active``: climate control on for the
        room; when off, a unit RoomMind runs in dry goes off once and nothing else is sent (#36).
        ``waiting``: no reading yet, nothing is sent and nothing changes. ``group_conflicts``: the
        modes each unit's uniform-mode group rules out for a running room. ``can_start`` asks the
        compressor group (min off, uniform mode) last, it may claim the group's way for the cycle.
        """
        result = AcDryRoomResult()
        now = time.time()
        devices = room.get("devices", [])
        if mode == MODE_HEATING:
            self._heated_at[area_id] = now
        if not too_humid:
            self._declined.pop(area_id, None)
        if dehumidifier_reads is not False:
            self._dehumidifier_gone_since.pop(area_id, None)
        may_replace_dehumidifier = dehumidifier_reads is None or (
            dehumidifier_reads is False
            and now - self._dehumidifier_gone_since.setdefault(area_id, now) >= AC_DRY_DEHUMIDIFIER_GONE_MINUTES * 60
        )
        cold = room_temp is None or stop_temp is None or room_temp <= stop_temp
        warm_enough = (
            room_temp is not None
            and stop_temp is not None
            and room_temp >= stop_temp - AC_DRY_STOP_MARGIN_K + AC_DRY_START_MARGIN_K
        )
        heated_recently = now - self._heated_at.get(area_id, -math.inf) < AC_DRY_AFTER_HEATING_MINUTES * 60

        for eid in get_ac_eids(devices):
            st = self._running.get(eid)
            if waiting:
                if st is not None:
                    result.drying_eids.add(eid)
                continue
            state = self.hass.states.get(eid)
            if st is not None:
                st.area_id = area_id  # a unit moved to another room goes on there
                reason = self._end_reason(
                    eid,
                    st,
                    state,
                    now,
                    mode=mode,
                    too_humid=too_humid,
                    allowed=allowed,
                    window_open=window_open,
                    control_active=control_active,
                    cold=cold,
                    dehumidifier_back=dehumidifier_reads is True,
                    held=eid in compressor_forced_on,
                    conflicts=group_conflicts.get(eid, frozenset()),
                )
                if reason is None:
                    result.drying_eids.add(eid)
                    await self._keep_setpoint(eid, st, state, area_id, stop_temp, devices)
                    continue
                _LOGGER.debug("Area '%s': dry on '%s' ends (%s)", area_id, eid, reason)
                self._dried_at[area_id] = now
                if reason == _END_COLD:
                    self._rest_until[area_id] = now + AC_DRY_MIN_OFF_MINUTES * 60
                restore = (
                    not switched_off
                    and not coil_dry_follows(eid)
                    and st.prev_mode not in group_conflicts.get(eid, frozenset())
                )
                if await self._async_end(eid, st, state, area_id, reason=reason, restore=restore):
                    result.restored_eids.add(eid)
                continue
            if (
                too_humid
                and allowed
                and not window_open
                and may_replace_dehumidifier
                and may_cool
                and control_active
                and mode == MODE_IDLE
                and warm_enough
                and not heated_recently
                and now >= self._rest_until.get(area_id, -math.inf)
                and eid not in self._declined.get(area_id, set())
                and eid not in blocked_eids
                and eid not in compressor_forced_on
                and DRY not in group_conflicts.get(eid, frozenset())
                and self._offers_dry(state)
                and can_start(eid)
            ):
                await self._async_start(eid, state, area_id, now, stop_temp, devices)
                result.drying_eids.add(eid)
        if result.drying_eids:
            self._dried_at[area_id] = now
        result.settling = now - self._dried_at.get(area_id, -math.inf) < AC_DRY_SETTLE_MINUTES * 60
        return result

    @staticmethod
    def _offers_dry(state: Any) -> bool:
        if state is None or state.state in _NO_READING:
            return False
        return DRY in (state.attributes.get("hvac_modes") or [])

    def _end_reason(
        self,
        eid: str,
        st: _Dry,
        state: Any,
        now: float,
        *,
        mode: str,
        too_humid: bool,
        allowed: bool,
        window_open: bool,
        control_active: bool,
        cold: bool,
        dehumidifier_back: bool,
        held: bool,
        conflicts: frozenset[str],
    ) -> str | None:
        """Why a running dry ends now, None while it goes on."""
        if not control_active:
            return _END_CONTROL_OFF
        if mode != MODE_IDLE:
            return f"room {mode}"
        if window_open:
            return _END_WINDOW
        if not allowed:
            return _END_NOT_ALLOWED
        if DRY in conflicts:
            return "compressor group runs the other way"
        current = state.state if state is not None else None
        if current == DRY:
            st.confirmed = True
        elif current is not None and current not in _NO_READING:
            # Another mode: changed by hand, or the unit never took dry
            if st.confirmed or now - st.since >= AC_DRY_REPORT_SECONDS:
                self._declined.setdefault(st.area_id, set()).add(eid)
                return "changed on the device" if st.confirmed else "device does not take dry"
            return None
        if held or now - st.since < AC_DRY_MIN_RUN_MINUTES * 60:
            return None
        if not too_humid:
            return _END_DRY_ENOUGH
        if cold:
            return _END_COLD
        if dehumidifier_back:
            return _END_DEHUMIDIFIER_BACK
        return None

    async def _async_start(
        self, eid: str, state: Any, area_id: str, now: float, stop_temp: float | None, devices: list[dict]
    ) -> None:
        idle_action, _ = get_idle_action(devices, eid)
        st = _Dry(area_id=area_id, since=now)
        if idle_action == IDLE_ACTION_SETBACK and state.state in ("heat", "cool"):
            temperature = state.attributes.get("temperature")
            if isinstance(temperature, int | float):
                st.prev_mode = state.state
                st.prev_temperature = float(temperature)
        self._running[eid] = st
        self._dirty = True
        _LOGGER.debug("Area '%s': '%s' dries (room too humid, no heating or cooling needed)", area_id, eid)
        if state.state != DRY:
            await async_climate_command(self.hass, eid, "set_hvac_mode", {"hvac_mode": DRY}, area_id=area_id)
        await self._keep_setpoint(eid, st, self.hass.states.get(eid), area_id, stop_temp, devices)

    async def _keep_setpoint(
        self, eid: str, st: _Dry, state: Any, area_id: str, stop_temp: float | None, devices: list[dict]
    ) -> None:
        """The stop point as setpoint, sent again only when it moves (target change)."""
        if stop_temp is None or state is None or not isinstance(state.attributes.get("temperature"), int | float):
            return
        value = device_setpoint_ha(self.hass, state, stop_temp + get_setpoint_offset(devices, eid))
        if st.setpoint is not None and abs(value - st.setpoint) < 0.05:
            return
        st.setpoint = value
        self._dirty = True
        if abs(float(state.attributes["temperature"]) - value) < 0.05:
            return
        await async_climate_command(self.hass, eid, "set_temperature", {"temperature": value}, area_id=area_id)

    async def _async_end(self, eid: str, st: _Dry, state: Any, area_id: str, *, reason: str, restore: bool) -> bool:
        """Leave dry. True when the unit got its setback back here and stays out of async_apply this cycle.

        Not when the room heats or cools (async_apply switches the unit) nor after a hand on it.
        """
        del self._running[eid]
        self._dirty = True
        in_dry = state is not None and state.state == DRY
        if reason == _END_CONTROL_OFF:
            # #36: nothing is sent while control is off, only the dry RoomMind started goes off once
            if in_dry:
                await async_turn_off_climate(self.hass, eid, area_id=area_id)
            return False
        if (
            restore
            and in_dry
            and reason in (_END_DRY_ENOUGH, _END_COLD, _END_NOT_ALLOWED, _END_DEHUMIDIFIER_BACK)
            and st.prev_mode is not None
            and st.prev_temperature is not None
        ):
            return await async_climate_command(
                self.hass,
                eid,
                "set_temperature",
                {"hvac_mode": st.prev_mode, "temperature": st.prev_temperature},
                area_id=area_id,
            )
        return False

    # --- persistence -------------------------------------------------------

    @property
    def state_dirty(self) -> bool:
        return self._dirty

    @state_dirty.setter
    def state_dirty(self, value: bool) -> None:
        self._dirty = value

    def get_state(self) -> dict[str, dict]:
        return {
            eid: {
                "area_id": st.area_id,
                "since": st.since,
                "setpoint": st.setpoint,
                "prev_mode": st.prev_mode,
                "prev_temperature": st.prev_temperature,
            }
            for eid, st in self._running.items()
        }

    def load_state(self, data: Any) -> None:
        """Units RoomMind ran in dry before a restart; they count as shown in dry (a hand since then ends it)."""
        self._running = {}
        if not isinstance(data, dict):
            return
        for eid, raw in data.items():
            if not isinstance(raw, dict) or not isinstance(raw.get("area_id"), str):
                continue
            since = raw.get("since")
            if not isinstance(since, int | float):
                continue
            setpoint, prev_temperature = raw.get("setpoint"), raw.get("prev_temperature")
            prev_mode = raw.get("prev_mode")
            self._running[eid] = _Dry(
                area_id=raw["area_id"],
                since=float(since),
                setpoint=float(setpoint) if isinstance(setpoint, int | float) else None,
                confirmed=True,
                prev_mode=prev_mode if prev_mode in ("heat", "cool") else None,
                prev_temperature=float(prev_temperature) if isinstance(prev_temperature, int | float) else None,
            )

    def prune(self, known_eids: set[str]) -> None:
        """Forget units no longer configured in any room."""
        for eid in [e for e in self._running if e not in known_eids]:
            del self._running[eid]
            self._dirty = True

    def remove_room(self, area_id: str) -> None:
        for eid in [e for e, st in self._running.items() if st.area_id == area_id]:
            del self._running[eid]
            self._dirty = True
        self._heated_at.pop(area_id, None)
        self._rest_until.pop(area_id, None)
        self._dried_at.pop(area_id, None)
        self._declined.pop(area_id, None)
        self._dehumidifier_gone_since.pop(area_id, None)
