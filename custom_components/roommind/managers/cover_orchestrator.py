"""Cover orchestrator: coordinates cover position reading, schedule resolution, and control."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..const import (
    COVER_CONFIDENCE_REFERENCE_SOLAR,
    COVER_DAILY_LOOKAHEAD_H,
    COVER_DEFAULT_BETA_S,
    COVER_LINEAR_LOOKAHEAD_H,
    COVER_MAX_PREDICTION_STD,
    COVER_MIN_IDLE_FOR_LEARNED,
    COVER_PREDICTION_DT_MINUTES,
    COVER_RC_LOOKAHEAD_H,
    MODE_COOLING,
    TargetTemps,
)
from ..control.mpc_controller import (
    DEFAULT_OUTDOOR_TEMP_FALLBACK,
    check_acs_can_heat,
    get_can_heat_cool,
    is_mpc_active,
)
from ..control.solar import build_oriented_solar_series, build_solar_series, solar_elevation
from ..utils.schedule_utils import resolve_schedule_index
from .cover_manager import CoverDecision, CoverManager, compute_shading_factor

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from ..control.thermal_model import RoomModelManager

_LOGGER = logging.getLogger(__name__)


@dataclass
class CoverPositionResult:
    """Result of reading current cover positions."""

    shading_factor: float
    positions: list[int]


@dataclass
class CoverResult:
    """Result of cover processing for a room."""

    mpc_active: bool
    forced_reason: str
    active_cover_schedule_index: int
    decision: CoverDecision


class CoverOrchestrator:
    """Coordinates cover position reading, schedule resolution, and control decisions."""

    def __init__(
        self,
        hass: HomeAssistant,
        cover_manager: CoverManager,
        model_manager: RoomModelManager,
    ) -> None:
        self.hass = hass
        self._cover_manager = cover_manager
        self._model_manager = model_manager
        self._cloud_series: list[float | None] | None = None

    def set_model_manager(self, model_manager: RoomModelManager) -> None:
        """Update the model manager reference (used after full thermal reset)."""
        self._model_manager = model_manager

    def set_cloud_series(self, cloud_series: list[float | None] | None) -> None:
        """Update cloud forecast for solar trajectory prediction."""
        self._cloud_series = cloud_series

    def read_positions(self, area_id: str, room: dict[str, Any]) -> CoverPositionResult:
        """Read current cover positions from HA state and update cover manager."""
        cover_eids: list[str] = room.get("covers", [])
        cover_positions: list[int] = []
        for eid in cover_eids:
            cstate = self.hass.states.get(eid)
            if cstate is None:
                continue
            pos = cstate.attributes.get("current_position")
            if pos is not None:
                cover_positions.append(int(pos))
            elif cstate.state == "closed":
                cover_positions.append(0)
            elif cstate.state == "open":
                cover_positions.append(100)

        if cover_positions:
            self._cover_manager.update_position(
                area_id,
                int(sum(cover_positions) / len(cover_positions)),
                override_minutes=room.get("covers_override_minutes", 60),
            )

        shading_factor = compute_shading_factor(cover_positions)
        return CoverPositionResult(shading_factor=shading_factor, positions=cover_positions)

    async def async_process(
        self,
        area_id: str,
        room: dict[str, Any],
        targets: TargetTemps,
        mode: str,
        current_temp: float | None,
        outdoor_temp: float | None,
        q_solar: float,
        predicted_peak_temp: float | None,
        has_override: bool,
    ) -> CoverResult:
        """Process cover control for a room: MPC check, schedule, prediction, evaluate, apply."""
        # Early exit: when auto control is disabled, do nothing.
        # Schedule, night close and MPC are all suppressed — covers stay wherever they are.
        if not room.get("covers_auto_enabled", False):
            return CoverResult(
                mpc_active=False,
                forced_reason="",
                active_cover_schedule_index=-1,
                decision=CoverDecision(
                    target_position=self._cover_manager.get_current_position(area_id),
                    changed=False,
                    reason="disabled",
                ),
            )

        has_external_sensor = bool(room.get("temperature_sensor"))

        # Block A: MPC active check
        _cover_mpc_active = False
        if has_external_sensor:
            try:
                _ch, _cc = get_can_heat_cool(
                    room,
                    outdoor_temp,
                    acs_can_heat=check_acs_can_heat(self.hass, room),
                )
                _T_out = outdoor_temp if outdoor_temp is not None else DEFAULT_OUTDOOR_TEMP_FALLBACK
                _cover_mpc_active = is_mpc_active(
                    self._model_manager,
                    area_id,
                    _ch,
                    _cc,
                    current_temp or 20.0,
                    _T_out,
                )
            except Exception:  # noqa: BLE001
                _cover_mpc_active = False

        # Block B: Cover target
        cover_target = (
            targets.cool
            if mode == MODE_COOLING and targets.cool is not None
            else targets.heat
            if targets.heat is not None
            else 22.0
        )

        # Block C: Forced position from schedule + night close
        _forced_position: int | None = None
        _forced_reason = ""
        _active_cover_sched_idx = -1
        _solar_gated = True  # True = solar protection allowed (default); False = gate schedule is off

        cover_schedules = room.get("cover_schedules", [])
        if cover_schedules:
            _active_cover_sched_idx = resolve_schedule_index(
                self.hass,
                room,
                schedules_key="cover_schedules",
                selector_key="cover_schedule_selector_entity",
            )
            if 0 <= _active_cover_sched_idx < len(cover_schedules):
                entry = cover_schedules[_active_cover_sched_idx]
                eid = entry.get("entity_id", "")
                sched_mode = entry.get("mode", "force")
                if eid:
                    _sched_st = self.hass.states.get(eid)
                    if sched_mode == "gate":
                        # Gate mode: schedule controls when solar protection is allowed.
                        # No forced position — RoomMind's thermal logic decides the actual position.
                        # Fail-safe: if entity is unavailable, keep solar protection active
                        # to prevent thermal overshoot during temporary HA restarts.
                        if _sched_st is None:
                            _LOGGER.warning(
                                "Cover gate schedule entity %s unavailable; keeping solar protection active",
                                eid,
                            )
                        else:
                            _solar_gated = _sched_st.state == "on"
                    elif _sched_st is not None and _sched_st.state == "on":
                        # Force mode (default): read position attribute and force covers.
                        _block_pos = _sched_st.attributes.get("position")
                        if _block_pos is None:
                            _LOGGER.warning(
                                "Cover schedule entity %s has no 'position' attribute; defaulting to 0%% (closed)",
                                eid,
                            )
                        try:
                            _forced_position = max(0, min(100, int(_block_pos))) if _block_pos is not None else 0
                        except (ValueError, TypeError):
                            _forced_position = 0
                        _forced_reason = "schedule_active"

        if _forced_position is None and room.get("covers_night_close", False):
            _elev = solar_elevation(
                self.hass.config.latitude,
                self.hass.config.longitude,
                time.time(),
            )
            if _elev <= 0:
                _forced_position = room.get("covers_night_position", 0)
                _forced_reason = "night_close"

        # Block D: Tiered prediction
        # Build per-cover orientation list for solar series scaling
        _cover_eids: list[str] = room.get("covers", [])
        _cover_orientations: dict[str, int] = room.get("cover_orientations", {})
        _surface_azimuths: list[float] | None = None
        if _cover_eids and _cover_orientations:
            _az_list = [float(_cover_orientations[eid]) for eid in _cover_eids if eid in _cover_orientations]
            if _az_list:
                _surface_azimuths = _az_list

        _cover_predicted_peak = predicted_peak_temp
        if _cover_predicted_peak is None:
            _cover_predicted_peak = self._estimate_solar_peak_temp(
                area_id, current_temp, cover_target, q_solar, outdoor_temp, _surface_azimuths
            )

        # Block E: Evaluate + apply
        cover_eids = room.get("covers", [])
        cover_decision = self._cover_manager.evaluate(
            area_id,
            covers_auto_enabled=room.get("covers_auto_enabled", False),
            cover_entity_ids=cover_eids,
            covers_deploy_threshold=room.get("covers_deploy_threshold", 1.5),
            covers_min_position=room.get("covers_min_position", 0),
            covers_snap_deploy=room.get("covers_snap_deploy", False),
            predicted_peak_temp=_cover_predicted_peak,
            target_temp=cover_target,
            q_solar=q_solar,
            has_active_override=has_override,
            forced_position=_forced_position,
            forced_reason=_forced_reason,
            current_temp=current_temp,
            solar_gated=_solar_gated,
        )

        if cover_decision.changed:
            _LOGGER.debug(
                "Cover control [%s]: %s → position %d%%",
                area_id,
                cover_decision.reason,
                cover_decision.target_position,
            )
            await CoverManager.async_apply(self.hass, cover_eids, cover_decision.target_position)

        return CoverResult(
            mpc_active=_cover_mpc_active,
            forced_reason=_forced_reason if _forced_position is not None else "",
            active_cover_schedule_index=_active_cover_sched_idx,
            decision=cover_decision,
        )

    def _estimate_solar_peak_temp(
        self,
        area_id: str,
        current_temp: float | None,
        target_temp: float,
        q_solar: float,
        outdoor_temp: float | None,
        surface_azimuths: list[float] | None = None,
    ) -> float:
        """Estimate peak temperature from solar gain.

        Tier 1: RC model trajectory (idle model confident, incl. heat loss physics)
        Tier 2: Conservative linear fallback with default beta_s

        *surface_azimuths*: list of cover surface azimuths (degrees, 0=N).
            When provided, solar series are scaled by the per-step averaged
            orientation factor so that north-facing covers don't trigger
            deployment for southern sunlight.
        """
        base_temp = current_temp if current_temp is not None else target_temp
        lat = self.hass.config.latitude
        lon = self.hass.config.longitude

        def _solar_series(n_steps: int) -> list[float]:
            if surface_azimuths:
                return build_oriented_solar_series(
                    lat,
                    lon,
                    n_steps,
                    surface_azimuths,
                    dt_minutes=COVER_PREDICTION_DT_MINUTES,
                    cloud_series=self._cloud_series,
                )
            return build_solar_series(
                lat, lon, n_steps, dt_minutes=COVER_PREDICTION_DT_MINUTES, cloud_series=self._cloud_series
            )

        try:
            n_idle, _, _ = self._model_manager.get_mode_counts(area_id)
            if (
                n_idle >= COVER_MIN_IDLE_FOR_LEARNED
                and outdoor_temp is not None
                and self._idle_solar_model_confident(area_id, base_temp, outdoor_temp)
            ):
                # Tier 1: RC model trajectory with proper physics
                model = self._model_manager.get_model(area_id)
                n_steps = int(COVER_RC_LOOKAHEAD_H * 60 / COVER_PREDICTION_DT_MINUTES)
                solar_series = _solar_series(n_steps)
                trajectory = model.predict_trajectory(
                    base_temp,
                    [outdoor_temp] * n_steps,
                    [0.0] * n_steps,
                    COVER_PREDICTION_DT_MINUTES,
                    q_solar_series=solar_series,
                )
                return max(trajectory)
        except Exception:  # noqa: BLE001
            pass

        # Tier 2: Linear fallback using daily solar peak + cloud forecast.
        # Using the daily peak (instead of current q_solar) means the initial position is computed
        # from the afternoon maximum — one decisive deployment rather than incremental steps as q_solar rises.
        n_daily = int(COVER_DAILY_LOOKAHEAD_H * 60 / COVER_PREDICTION_DT_MINUTES)
        daily_series = _solar_series(n_daily)
        q_solar_peak = max(daily_series) if daily_series else q_solar
        return base_temp + COVER_DEFAULT_BETA_S * q_solar_peak * COVER_LINEAR_LOOKAHEAD_H

    def _idle_solar_model_confident(self, area_id: str, T_room: float, T_outdoor: float) -> bool:
        """Check if idle model with solar is confident enough for trajectory prediction.

        Uses a reference q_solar to include beta_s uncertainty (P[4][4]) in the check.
        When beta_s hasn't learned from solar data yet, P[4][4] remains high,
        making prediction_std exceed the threshold -> falls back to linear.
        """
        try:
            pred_std = self._model_manager.get_prediction_std(
                area_id,
                0.0,
                T_room,
                T_outdoor,
                COVER_PREDICTION_DT_MINUTES,
                q_solar=COVER_CONFIDENCE_REFERENCE_SOLAR,
            )
            return pred_std < COVER_MAX_PREDICTION_STD
        except Exception:  # noqa: BLE001
            return False

    def get_current_position(self, area_id: str) -> int:
        """Delegate to CoverManager.get_current_position."""
        return self._cover_manager.get_current_position(area_id)

    def is_user_override_active(self, area_id: str) -> bool:
        """Delegate to CoverManager.is_user_override_active."""
        return self._cover_manager.is_user_override_active(area_id)

    def remove_room(self, area_id: str) -> None:
        """Delegate to CoverManager.remove_room."""
        self._cover_manager.remove_room(area_id)
