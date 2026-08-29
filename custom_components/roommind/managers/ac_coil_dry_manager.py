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

from ..const import MODE_COOLING, MODE_HEATING
from ..utils.device_utils import COIL_DRY_STALE_SECONDS, get_ac_eids

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
