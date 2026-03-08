"""Cover/blind manager for RoomMind smart home control."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from homeassistant.core import HomeAssistant

from ..const import (
    COVER_HYSTERESIS,
    COVER_MAX_EFFECTIVENESS,
    COVER_MIN_HOLD_SECONDS,
    COVER_POS_SCALE,
    COVER_SOLAR_MIN,
    COVER_USER_CONFLICT_THRESHOLD,
    COVER_USER_OVERRIDE_MINUTES,
)

_LOGGER = logging.getLogger(__name__)

# HA cover supported_features bit for SET_POSITION
_SUPPORT_SET_POSITION = 4


def compute_shading_factor(
    positions: list[int],
    max_effectiveness: float = COVER_MAX_EFFECTIVENESS,
) -> float:
    """Compute solar shading factor [0..1] from cover positions.

    HA convention: position 0 = fully closed, 100 = fully open.
    Returns 1.0 when fully open (no shading), (1-max_effectiveness) when fully closed.
    """
    if not positions:
        return 1.0
    avg = sum(positions) / len(positions)
    return 1.0 - max_effectiveness * (1.0 - avg / 100.0)


@dataclass
class CoverDecision:
    """Result of CoverManager.evaluate() for a single room."""

    target_position: int   # 0-100 (HA: 0=closed, 100=open)
    changed: bool          # True if caller should call HA service
    reason: str            # For debug logging


@dataclass
class _RoomCoverState:
    """Per-room mutable state."""

    current_position: int = 100
    last_change_ts: float = 0.0  # 0 = never changed, allows first action immediately
    last_commanded_position: int | None = None  # None = never commanded yet
    user_override_until: float = 0.0  # Unix timestamp; 0 = no override
    last_was_forced: bool = False  # True after forced position (schedule/night close)


class CoverManager:
    """Manages automatic blind/cover control per room."""

    def __init__(self) -> None:
        self._states: dict[str, _RoomCoverState] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_position(self, area_id: str, position: int, override_minutes: int = COVER_USER_OVERRIDE_MINUTES) -> None:
        """Update the tracked position from HA state. Call before evaluate().

        Detects user manual override: if the cover position differs significantly
        from the last position RoomMind commanded (in either direction), the user
        moved it manually. In that case, auto control pauses for
        COVER_USER_OVERRIDE_MINUTES.
        """
        state = self._get_state(area_id)
        # Drift detection: only if we previously commanded a position
        if (
            state.last_commanded_position is not None
            and abs(position - state.last_commanded_position) > COVER_USER_CONFLICT_THRESHOLD
        ):
            state.user_override_until = time.time() + override_minutes * 60
            _LOGGER.info(
                "Cover user override detected [%s]: position %d vs commanded %d"
                " → pausing %d min",
                area_id, position, state.last_commanded_position,
                override_minutes,
            )
        state.current_position = position

    def get_current_position(self, area_id: str) -> int:
        """Return the last-known cover position for a room (100 if unknown)."""
        return self._get_state(area_id).current_position

    def is_user_override_active(self, area_id: str) -> bool:
        """Return True if user manual override is currently active."""
        return self._get_state(area_id).user_override_until > time.time()

    def evaluate(
        self,
        area_id: str,
        *,
        covers_auto_enabled: bool,
        cover_entity_ids: list[str],
        covers_deploy_threshold: float,
        covers_min_position: int,
        covers_outdoor_min_temp: float | None,
        predicted_peak_temp: float | None,
        target_temp: float,
        q_solar: float,
        outdoor_temp: float | None,
        has_active_override: bool,
        forced_position: int | None = None,
        forced_reason: str = "",
    ) -> CoverDecision:
        """Evaluate whether to change cover positions this cycle.

        Does NOT call HA services — caller handles that.
        Returns CoverDecision(changed=False) to hold current state.
        """
        state = self._get_state(area_id)
        current = state.current_position

        # Gate 1: Feature disabled or no covers configured
        if not covers_auto_enabled or not cover_entity_ids:
            return CoverDecision(target_position=current, changed=False, reason="disabled")

        # Gate 2: Manual override — never fight the user
        if has_active_override:
            return CoverDecision(target_position=current, changed=False,
                                 reason="manual_override_active")

        # Gate 2b: User manually moved cover (e.g. opened for balcony)
        if state.user_override_until > time.time():
            return CoverDecision(target_position=current, changed=False,
                                 reason="user_override_active")

        # Gate 2c: Forced position (schedule or night close) — immediate, no rate limit
        # User-defined schedules and night close should always apply instantly.
        # Rate limiting only applies to thermal/solar MPC-based decisions below.
        if forced_position is not None:
            state.last_was_forced = True
            if forced_position == current:
                return CoverDecision(target_position=current, changed=False,
                                     reason=f"forced_at_target({forced_reason})")
            return self._apply_change(state, forced_position, f"forced({forced_reason})")

        # Gate 3: Safety check — predicted_peak_temp must be available
        if predicted_peak_temp is None:
            return CoverDecision(target_position=current, changed=False, reason="no_prediction")

        # After forced section: allow immediate transition back to normal control
        was_forced = state.last_was_forced
        state.last_was_forced = False

        # Gate 4: Cold weather — we want solar gain, not shading (skip if gate disabled)
        if covers_outdoor_min_temp is not None and outdoor_temp is not None and outdoor_temp < covers_outdoor_min_temp:
            if current < 100:
                if not was_forced and (time.time() - state.last_change_ts) < COVER_MIN_HOLD_SECONDS:
                    return CoverDecision(target_position=current, changed=False, reason="min_hold_time")
                return self._apply_change(state, 100, "cold_weather_retract")
            return CoverDecision(target_position=100, changed=False, reason="cold_weather")

        # Gate 5: Not actually sunny
        if q_solar < COVER_SOLAR_MIN:
            if current < 100:
                if not was_forced and (time.time() - state.last_change_ts) < COVER_MIN_HOLD_SECONDS:
                    return CoverDecision(target_position=current, changed=False, reason="min_hold_time")
                return self._apply_change(state, 100, "low_solar_retract")
            return CoverDecision(target_position=100, changed=False, reason="low_solar")

        # Compute desired position
        excess = predicted_peak_temp - target_temp
        retract_threshold = covers_deploy_threshold - COVER_HYSTERESIS

        if excess > covers_deploy_threshold:
            raw_close_pct = min(100, int((excess - covers_deploy_threshold) * COVER_POS_SCALE))
            desired_pos = max(covers_min_position, 100 - raw_close_pct)
        elif excess < retract_threshold:
            desired_pos = 100
        else:
            # Hysteresis band — hold
            return CoverDecision(target_position=current, changed=False, reason="hysteresis_hold")

        # Rate-limit: minimum hold time between changes (skip after forced)
        now = time.time()
        if not was_forced and (now - state.last_change_ts) < COVER_MIN_HOLD_SECONDS:
            return CoverDecision(target_position=current, changed=False, reason="min_hold_time")

        # No change needed
        if desired_pos == current:
            return CoverDecision(target_position=desired_pos, changed=False, reason="at_target")

        reason = (
            f"deploy(excess={excess:.2f}°C→pos={desired_pos}%)"
            if desired_pos < 100
            else "retract"
        )
        return self._apply_change(state, desired_pos, reason)

    def remove_room(self, area_id: str) -> None:
        """Clean up state when a room is deleted."""
        self._states.pop(area_id, None)

    @staticmethod
    async def async_apply(
        hass: HomeAssistant,
        cover_entity_ids: list[str],
        target_position: int,
    ) -> None:
        """Call HA cover service to set position on all configured cover entities."""
        position_eids: list[str] = []
        binary_open_eids: list[str] = []
        binary_close_eids: list[str] = []

        for eid in cover_entity_ids:
            state = hass.states.get(eid)
            if state is None:
                continue
            supported = state.attributes.get("supported_features", 0) or 0
            if supported & _SUPPORT_SET_POSITION:
                position_eids.append(eid)
            elif target_position >= 100:
                binary_open_eids.append(eid)
            else:
                binary_close_eids.append(eid)

        if position_eids:
            await hass.services.async_call(
                "cover", "set_cover_position",
                {"entity_id": position_eids, "position": target_position},
                blocking=False,
            )
        if binary_open_eids:
            await hass.services.async_call(
                "cover", "open_cover",
                {"entity_id": binary_open_eids},
                blocking=False,
            )
        if binary_close_eids:
            await hass.services.async_call(
                "cover", "close_cover",
                {"entity_id": binary_close_eids},
                blocking=False,
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_state(self, area_id: str) -> _RoomCoverState:
        if area_id not in self._states:
            self._states[area_id] = _RoomCoverState()
        return self._states[area_id]

    def _apply_change(
        self, state: _RoomCoverState, position: int, reason: str
    ) -> CoverDecision:
        state.current_position = position
        state.last_commanded_position = position
        state.last_change_ts = time.time()
        return CoverDecision(target_position=position, changed=True, reason=reason)
