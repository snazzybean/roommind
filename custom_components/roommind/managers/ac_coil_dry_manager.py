"""AC evaporator coil drying (anti-odour) manager for RoomMind.

An AC that is cut hard out of cooling leaves a wet evaporator behind: biofilm
grows on it and the next cooling start smells musty.  This manager runs the
indoor fan for a bounded time before the device really goes off.

Unlike ``idle_action`` (a *state* the device holds while there is no demand)
this is a *transition ritual*: time-limited, triggered by "cooling just ended",
and it ends in a real shutdown.  Therefore it carries its own state instead of
living inside the stateless ``async_idle_device``.

Times are wall-clock (``time.time()``), not ``monotonic()``, because the state
has to survive a Home Assistant restart.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from homeassistant.core import HomeAssistant

from ..const import MODE_COOLING, MODE_HEATING, TargetTemps, make_roommind_context
from ..control.mpc_controller import async_idle_device
from ..utils.device_utils import (
    COIL_DRY_MODE_DRY,
    COIL_DRY_PHASE_BLOW,
    COIL_DRY_PHASE_DRAIN,
    COIL_DRY_STALE_SECONDS,
    IDLE_ACTION_FAN_ONLY,
    IDLE_ACTION_SETBACK,
    CoilDryConfig,
    get_ac_eids,
    get_coil_dry_config,
    get_idle_action,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class CoilDryState:
    """Per-device runtime state.  Persisted verbatim (see get_state)."""

    wet_seconds: float = 0.0
    cooling_since: float | None = None
    expires_at: float | None = None
    phase: str | None = None
    phase_until: float | None = None
    mode: str = ""
    fan_mode: str = ""
    prev_fan_mode: str | None = None


@dataclass
class CoilDryRoomResult:
    """What the coordinator needs to know after processing one room."""

    controlled_eids: set[str] = field(default_factory=set)
    compressor_active_eids: set[str] = field(default_factory=set)
    skip_ekf_training: bool = False
    active: bool = False
    phase: str | None = None
    until: float | None = None


class AcCoilDryManager:
    """Accumulate cooling runtime per AC and run a bounded drying phase."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._states: dict[str, CoilDryState] = {}
        self._eid_to_area: dict[str, str] = {}
        self._unsupported_warned: set[str] = set()
        self._dirty = False

    def state_for(self, entity_id: str) -> CoilDryState | None:
        """Return the state for one device, or None. For tests and diagnostics."""
        return self._states.get(entity_id)

    async def async_process_room(
        self,
        *,
        area_id: str,
        room: dict,
        settings: dict,
        mode: str,
        commandable: bool,
        compressor_forced_on: set[str],
        compressor_forced_off: set[str],
        exclude_eids: set[str],
        force_off: bool,
        can_activate: Callable[[str], bool],
    ) -> CoilDryRoomResult:
        """Advance the state machine for every AC in this room.

        ``commandable`` is ``climate_active and not waiting_for_data`` — when
        False, RoomMind must send no commands at all (see #36).
        """
        result = CoilDryRoomResult()
        now = time.time()
        devices = room.get("devices", [])

        for eid in get_ac_eids(devices):
            self._eid_to_area[eid] = area_id
            st = self._states.setdefault(eid, CoilDryState())

            is_cooling = (
                mode == MODE_COOLING and commandable and eid not in compressor_forced_off and eid not in exclude_eids
            )

            self._update_wetness(st, now, mode=mode, commandable=commandable, is_cooling=is_cooling)

            cfg = get_coil_dry_config(devices, eid, settings)

            if st.phase is not None:
                await self._advance_phase(
                    eid,
                    st,
                    cfg,
                    area_id,
                    now,
                    devices,
                    mode=mode,
                    commandable=commandable,
                    force_off=force_off,
                )
            elif self._should_start(
                eid,
                st,
                cfg,
                devices,
                mode=mode,
                commandable=commandable,
                force_off=force_off,
                compressor_forced_on=compressor_forced_on,
                exclude_eids=exclude_eids,
                can_activate=can_activate,
            ):
                await self._start_run(eid, st, cfg, area_id, now, devices, force_off=force_off)

            await self._restore_fan_mode(eid, st, area_id, commandable)

            if st.phase is not None:
                result.controlled_eids.add(eid)
                result.active = True
                if result.until is None or (st.phase_until or 0) > result.until:
                    result.until = st.phase_until
                    result.phase = st.phase
                if st.mode == COIL_DRY_MODE_DRY and st.phase == COIL_DRY_PHASE_BLOW:
                    result.compressor_active_eids.add(eid)
                    result.skip_ekf_training = True

        return result

    # --- wetness accumulator -------------------------------------------------

    def _update_wetness(self, st: CoilDryState, now: float, *, mode: str, commandable: bool, is_cooling: bool) -> None:
        """Track how long this device has been making condensate.

        Level-based, not edge-based: the start condition later only looks at
        ``wet_seconds``, so a run that could not fire earlier (control disabled,
        min-run active) still fires once the blocker is gone.
        """
        if mode == MODE_HEATING and commandable:
            # Heating turns the indoor heat exchanger into a warm condenser.
            self._reset_wetness(st)
        elif is_cooling:
            if st.cooling_since is None:
                st.cooling_since = now
                self._dirty = True
            st.expires_at = None
        elif st.cooling_since is not None:
            st.wet_seconds += now - st.cooling_since
            st.cooling_since = None
            st.expires_at = now + COIL_DRY_STALE_SECONDS
            self._dirty = True
        elif st.expires_at is not None and now >= st.expires_at:
            # Passive drying: a run this late would be pointless.
            self._reset_wetness(st)

    def _reset_wetness(self, st: CoilDryState) -> None:
        if st.wet_seconds or st.cooling_since is not None or st.expires_at is not None:
            self._dirty = True
        st.wet_seconds = 0.0
        st.cooling_since = None
        st.expires_at = None

    # --- start condition -------------------------------------------------

    def _should_start(
        self,
        eid: str,
        st: CoilDryState,
        cfg: CoilDryConfig,
        devices: list[dict],
        *,
        mode: str,
        commandable: bool,
        force_off: bool,
        compressor_forced_on: set[str],
        exclude_eids: set[str],
        can_activate: Callable[[str], bool],
    ) -> bool:
        """All start conditions from spec 5.1, in cheapest-first order."""
        if st.prev_fan_mode is not None:
            # A restore is still pending (e.g. the previous run ended while not
            # commandable, see §5.5/§9.5). Starting a new run here would let
            # _start_run overwrite prev_fan_mode with the device's *current*
            # fan mode — which is still the drying value, since the restore
            # never happened — losing the user's real original setting.
            return False
        if not cfg.enabled or not commandable:
            return False
        if mode in (MODE_COOLING, MODE_HEATING):
            return False
        if st.wet_seconds < cfg.min_cooling_minutes * 60:
            return False
        if eid in compressor_forced_on or eid in exclude_eids:
            return False

        idle_action, _ = get_idle_action(devices, eid)
        if idle_action == IDLE_ACTION_FAN_ONLY and not force_off:
            # async_idle_device parks it in fan_only indefinitely anyway.
            return False

        state = self.hass.states.get(eid)
        hvac_modes: list[str] = (state.attributes.get("hvac_modes") or []) if state else []
        if cfg.mode not in hvac_modes:
            if eid not in self._unsupported_warned:
                self._unsupported_warned.add(eid)
                _LOGGER.warning(
                    "Coil dry: device '%s' does not support hvac_mode '%s' (available: %s), skipping",
                    eid,
                    cfg.mode,
                    hvac_modes,
                )
            return False

        if cfg.mode == COIL_DRY_MODE_DRY and not can_activate(eid):
            _LOGGER.debug("Coil dry: '%s' blocked by compressor min-off (dry mode)", eid)
            return False

        return True

    # --- phase start / advance --------------------------------------------

    async def _start_run(
        self,
        eid: str,
        st: CoilDryState,
        cfg: CoilDryConfig,
        area_id: str,
        now: float,
        devices: list[dict],
        *,
        force_off: bool,
    ) -> None:
        """Remember the fan speed, then enter drain or blow."""
        state = self.hass.states.get(eid)
        st.mode = cfg.mode
        st.fan_mode = cfg.fan_mode
        st.prev_fan_mode = (state.attributes.get("fan_mode") if state else None) if cfg.fan_mode else None
        self._dirty = True

        idle_action, _ = get_idle_action(devices, eid)
        # The drain phase only means anything if the device is really off during
        # it.  With idle_action="setback" (and no force_off) it stays in cool
        # mode, so skip straight to blowing.
        drain_effective = cfg.drain_minutes > 0 and (force_off or idle_action != IDLE_ACTION_SETBACK)

        if drain_effective:
            st.phase = COIL_DRY_PHASE_DRAIN
            st.phase_until = now + cfg.drain_minutes * 60
            _LOGGER.debug("Area '%s': coil dry on '%s' — draining for %d min", area_id, eid, cfg.drain_minutes)
            await self._assert_drain(eid, area_id, devices)
        else:
            await self._start_blow(eid, st, cfg, area_id, now)

    async def _assert_drain(self, eid: str, area_id: str, devices: list[dict]) -> None:
        """Hold the device off during the drain phase.

        force_off=True normalises any idle_action to "off"; async_idle_device is
        cheap to re-send because it returns early when the device is already off.
        """
        try:
            await async_idle_device(
                self.hass,
                eid,
                devices,
                area_id=area_id,
                targets=TargetTemps(heat=None, cool=None),
                force_off=True,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Area '%s': coil dry drain failed on '%s'", area_id, eid, exc_info=True)

    async def _start_blow(self, eid: str, st: CoilDryState, cfg: CoilDryConfig, area_id: str, now: float) -> None:
        st.phase = COIL_DRY_PHASE_BLOW
        st.phase_until = now + cfg.minutes * 60
        st.mode = cfg.mode
        self._dirty = True
        _LOGGER.debug(
            "Area '%s': coil dry on '%s' — %s for %d min (fan=%s)",
            area_id,
            eid,
            cfg.mode,
            cfg.minutes,
            st.fan_mode or "keep",
        )
        await self._call(eid, "set_hvac_mode", {"hvac_mode": st.mode}, area_id)

        if not st.fan_mode:
            return
        state = self.hass.states.get(eid)
        fan_modes: list[str] = (state.attributes.get("fan_modes") or []) if state else []
        if st.fan_mode in fan_modes:
            await self._call(eid, "set_fan_mode", {"fan_mode": st.fan_mode}, area_id)
        else:
            _LOGGER.debug(
                "Area '%s': device '%s' does not support fan_mode '%s' (available: %s), keeping current",
                area_id,
                eid,
                st.fan_mode,
                fan_modes,
            )
            # Nothing was set, so there is nothing to restore later.
            st.fan_mode = ""
            st.prev_fan_mode = None

    async def _advance_phase(
        self,
        eid: str,
        st: CoilDryState,
        cfg: CoilDryConfig,
        area_id: str,
        now: float,
        devices: list[dict],
        *,
        mode: str,
        commandable: bool,
        force_off: bool,
    ) -> None:
        """Move a running phase forward, or end it (time up / aborted).

        Aborting only ends the phase and releases the device — the hvac_mode is
        re-commanded by async_apply in the very same coordinator cycle, so there
        is no second command path and no race.
        """
        abort_reason: str | None = None
        if mode == MODE_COOLING:
            abort_reason = "cooling demand returned"
        elif mode == MODE_HEATING:
            abort_reason = "heating demand returned"
        elif not commandable:
            abort_reason = "climate control disabled"
        elif not cfg.enabled:
            abort_reason = "coil dry disabled in config"

        if abort_reason is not None:
            _LOGGER.debug("Area '%s': coil dry on '%s' aborted (%s)", area_id, eid, abort_reason)
            self._end_phase(st, completed=False)
            return

        if st.phase_until is not None and now >= st.phase_until:
            if st.phase == COIL_DRY_PHASE_DRAIN:
                await self._start_blow(eid, st, cfg, area_id, now)
            else:
                _LOGGER.debug("Area '%s': coil dry on '%s' complete", area_id, eid)
                self._end_phase(st, completed=True)
            return

        if st.phase == COIL_DRY_PHASE_DRAIN:
            await self._assert_drain(eid, area_id, devices)

    async def _restore_fan_mode(self, eid: str, st: CoilDryState, area_id: str, commandable: bool) -> None:
        """Give back the fan speed the device had before the run.

        One idempotent step instead of a copy in every abort path — that is the
        only way this does not get forgotten in one of them. Runs after the
        phase logic and before the device is released, so async_apply sees the
        correct speed in the same cycle.
        """
        if st.prev_fan_mode is None or st.phase is not None or not commandable:
            return

        state = self.hass.states.get(eid)
        current = state.attributes.get("fan_mode") if state else None
        if current == st.fan_mode:
            await self._call(eid, "set_fan_mode", {"fan_mode": st.prev_fan_mode}, area_id)
        else:
            _LOGGER.debug(
                "Area '%s': fan mode on '%s' is '%s', not the coil dry value '%s' — changed externally, not restoring",
                area_id,
                eid,
                current,
                st.fan_mode,
            )
        st.prev_fan_mode = None
        self._dirty = True

    def _end_phase(self, st: CoilDryState, *, completed: bool) -> None:
        """Leave the run.  On completion the coil counts as dry."""
        st.phase = None
        st.phase_until = None
        if completed:
            st.wet_seconds = 0.0
            st.expires_at = None
        self._dirty = True

    async def _call(self, eid: str, service: str, data: dict, area_id: str) -> None:
        try:
            await self.hass.services.async_call(
                "climate",
                service,
                {"entity_id": eid, **data},
                blocking=True,
                context=make_roommind_context(),
            )
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Area '%s': coil dry climate.%s failed on '%s'", area_id, service, eid, exc_info=True)

    # --- persistence -------------------------------------------------------

    @property
    def state_dirty(self) -> bool:
        """True when the state changed since it was last persisted."""
        return self._dirty

    @state_dirty.setter
    def state_dirty(self, value: bool) -> None:
        self._dirty = value

    def load_state(self, data: dict | None) -> None:
        """Restore persisted state.  Tolerates corrupt entries.

        ``cooling_since`` is deliberately never restored — a restart ends the
        cooling command, and get_state() has already folded the elapsed time
        into ``wet_seconds``.  A phase whose end has passed is dropped;
        ``prev_fan_mode`` survives as a pending restore (see spec 5.5).
        """
        now = time.time()
        self._states = {}
        for eid, raw in (data or {}).items():
            if not isinstance(raw, dict):
                _LOGGER.debug("Coil dry: ignoring malformed persisted state for '%s'", eid)
                continue
            try:
                wet = float(raw.get("wet_seconds", 0.0))
            except (TypeError, ValueError):
                wet = 0.0
            phase_until = raw.get("phase_until")
            if phase_until is not None:
                try:
                    phase_until = float(phase_until)
                except (TypeError, ValueError):
                    phase_until = None
            expires_at = raw.get("expires_at")
            if expires_at is not None:
                try:
                    expires_at = float(expires_at)
                except (TypeError, ValueError):
                    expires_at = None
            st = CoilDryState(
                wet_seconds=wet,
                expires_at=expires_at,
                phase=raw.get("phase"),
                phase_until=phase_until,
                mode=raw.get("mode", ""),
                fan_mode=raw.get("fan_mode", ""),
                prev_fan_mode=raw.get("prev_fan_mode"),
            )
            if st.phase is not None and not (st.phase_until and st.phase_until > now):
                st.phase = None
                st.phase_until = None
            self._states[eid] = st

    def get_state(self) -> dict:
        """Serialise state for the store.  Empty entries are omitted."""
        now = time.time()
        out: dict[str, dict] = {}
        for eid, st in self._states.items():
            wet = st.wet_seconds + (now - st.cooling_since if st.cooling_since is not None else 0.0)
            if wet <= 0 and st.phase is None and st.prev_fan_mode is None:
                continue
            out[eid] = {
                "wet_seconds": round(wet, 1),
                "expires_at": st.expires_at,
                "phase": st.phase,
                "phase_until": st.phase_until,
                "mode": st.mode,
                "fan_mode": st.fan_mode,
                "prev_fan_mode": st.prev_fan_mode,
            }
        return out

    # --- cleanup ----------------------------------------------------------

    def prune(self, known_eids: set[str]) -> None:
        """Drop state for devices that are no longer configured anywhere.

        Mirrors the stale-entry cleanup in ValveManager.async_check_and_cycle.
        """
        stale = [eid for eid in self._states if eid not in known_eids]
        for eid in stale:
            del self._states[eid]
            self._eid_to_area.pop(eid, None)
            self._unsupported_warned.discard(eid)
        if stale:
            self._dirty = True

    def remove_room(self, area_id: str) -> None:
        """Drop state for every device of a deleted room."""
        eids = [eid for eid, area in self._eid_to_area.items() if area == area_id]
        for eid in eids:
            self._states.pop(eid, None)
            self._eid_to_area.pop(eid, None)
            self._unsupported_warned.discard(eid)
        if eids:
            self._dirty = True
