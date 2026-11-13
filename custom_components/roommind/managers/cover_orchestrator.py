"""Cover orchestrator: coordinates cover position reading, schedule resolution, and control."""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.core import CoreState
from homeassistant.helpers import entity_registry as er

from ..const import (
    CLIMATE_MODE_HEAT_ONLY,
    COVER_CONFIDENCE_REFERENCE_SOLAR,
    COVER_COOLING_LINEAR_H,
    COVER_COOLING_LOOKAHEAD_H,
    COVER_DAILY_LOOKAHEAD_H,
    COVER_DEFAULT_BETA_S,
    COVER_DIRECT_SUN_ANGLE_DEG,
    COVER_LINEAR_LOOKAHEAD_H,
    COVER_MAX_PREDICTION_STD,
    COVER_MIN_IDLE_FOR_LEARNED,
    COVER_PREDICTION_DT_MINUTES,
    COVER_SMOOTHING_MINUTES,
    COVER_SMOOTHING_RISE_MINUTES,
    COVER_SOLAR_MIN,
    DEFAULT_COMFORT_COOL,
    DEFAULT_COVERS_OUTDOOR_MIN_TEMP,
    MAX_SENSOR_STALENESS,
    MODE_COOLING,
    TargetTemps,
)
from ..control.solar import (
    build_oriented_solar_series,
    build_solar_series,
    solar_azimuth,
    solar_elevation,
    surface_irradiance_factor,
)
from ..utils.device_utils import get_ac_eids
from ..utils.schedule_utils import resolve_schedule_index
from .cover_manager import _SUPPORT_SET_POSITION, CoverDecision, CoverManager, compute_shading_factor

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

    forced_reason: str
    active_cover_schedule_index: int
    decision: CoverDecision


def _unreadable(state: Any) -> bool:
    """True while an entity has no state yet or reports unavailable/unknown (e.g. right after a start)."""
    return state is None or state.state in ("unavailable", "unknown")


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
        # (value, timestamp) per room; see _smooth()
        self._smoothed_temp: dict[str, tuple[float, float]] = {}
        self._smoothed_excess: dict[str, tuple[float, float]] = {}
        self._running_since: float | None = None  # first cycle that saw HA fully running

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
            pos = self._reading(eid)
            if pos is not None:
                cover_positions.append(pos)

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
        window_open: bool = False,
    ) -> CoverResult:
        """Process cover control for a room: MPC check, schedule, prediction, evaluate, apply.

        *window_open* is the raw window state (no open/close delay, pending counts
        as open). With ``covers_window_hold`` it keeps the covers from going down.
        """
        # Early exit: when auto control is disabled, do nothing.
        # Schedule, night close and MPC are all suppressed — covers stay wherever they are.
        if not room.get("covers_auto_enabled", False):
            return CoverResult(
                forced_reason="",
                active_cover_schedule_index=-1,
                decision=CoverDecision(
                    target_position=self._cover_manager.get_current_position(area_id),
                    changed=False,
                    reason="disabled",
                ),
            )

        # Block B: Cover target
        # Shading attenuates solar gain, so it protects an upper bound. A room
        # that can cool aims at its cooling setpoint whether or not the AC runs
        # right now, otherwise the target would follow every compressor cycle.
        # Without cooling there is no cooling setpoint to aim at, and comparing
        # against targets.heat deployed ~3 C too early (#418) — in heat_only
        # rooms permanently, since MODE_COOLING is unreachable there.
        # targets.heat stays in the max() as a floor: a comfort_cool below the
        # heating setpoint must not shade harder than before.
        comfort_cool = room.get("comfort_cool", DEFAULT_COMFORT_COOL)
        can_cool = room.get("climate_mode", "auto") != CLIMATE_MODE_HEAT_ONLY and bool(
            get_ac_eids(room.get("devices", []))
        )
        if targets.cool is not None and (can_cool or mode == MODE_COOLING):
            cover_target = targets.cool
        else:
            cover_target = max([comfort_cool, *(t for t in (targets.cool, targets.heat) if t is not None)])

        # Block C: Forced position from schedule + night close
        _forced_position: int | None = None
        _forced_reason = ""
        _active_cover_sched_idx = -1
        _solar_gated = True  # True = solar protection allowed (default); False = gate schedule is off
        _forced_unknown = False  # a force schedule (or its selector) has no readable state yet

        cover_schedules = room.get("cover_schedules", [])
        if cover_schedules:
            _selector = room.get("cover_schedule_selector_entity", "")
            _any_force = any(e.get("mode", "force") != "gate" for e in cover_schedules)
            if _selector and _any_force and self._may_still_load(_selector):
                _forced_unknown = True
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
                    elif _unreadable(_sched_st):
                        _forced_unknown = _forced_unknown or self._may_still_load(eid)
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
            _offset = room.get("covers_night_close_offset_minutes", 0)
            _check_ts = time.time() - _offset * 60
            _elev = solar_elevation(
                self.hass.config.latitude,
                self.hass.config.longitude,
                _check_ts,
            )
            _night_elev_threshold = room.get("covers_night_close_elevation", 0)
            if _elev <= _night_elev_threshold:
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

        # Orientation gate: if covers have orientation configured and the sun is not
        # hitting that side, suppress solar deployment. Covers can't help against heat
        # coming through other windows. Uses the current oriented q_solar, not the
        # lookahead prediction — if the sun isn't on this side NOW, covers stay open.
        _oriented_q_solar = q_solar
        if _surface_azimuths and q_solar > 0:
            _now = time.time()
            _sun_az = solar_azimuth(self.hass.config.latitude, self.hass.config.longitude, _now)
            if can_cool:
                # GHI strength while the sun is on this facade, see _sunlit_weight()
                _oriented_q_solar = q_solar * self._sunlit_weight(_sun_az, _surface_azimuths)
            else:
                _sun_el = solar_elevation(self.hass.config.latitude, self.hass.config.longitude, _now)
                _factors = [surface_irradiance_factor(_sun_az, _sun_el, az) for az in _surface_azimuths]
                _oriented_q_solar = q_solar * (sum(_factors) / len(_factors))

        now = time.time()
        smoothed_temp = self._smooth_temp(area_id, current_temp, now)
        if can_cool:
            # Shade first, cool the rest: decide on the overshoot the sun alone
            # would cause, so a unit that could hold the room no longer keeps the
            # blind up. Same function in MPC and Simple mode; the MPC plan
            # (cooling included) adds the unit too weak to hold the room. Room
            # temperature, plan peak and learned solar gain all swing with the
            # compressor cycle, so base temperature and excess are smoothed.
            raw_peak = self._estimate_solar_load_peak(
                area_id, smoothed_temp, cover_target, q_solar, outdoor_temp, _surface_azimuths
            )
            if predicted_peak_temp is not None:
                raw_peak = max(raw_peak, predicted_peak_temp)
            excess = self._smooth(
                self._smoothed_excess,
                area_id,
                raw_peak - cover_target,
                now,
                rise_minutes=COVER_SMOOTHING_RISE_MINUTES,
            )
            _cover_predicted_peak = cover_target + excess
            _LOGGER.debug(
                "Cover input [%s]: target %.2f, smoothed temp %s, raw peak %.2f, plan peak %s, excess %.2f",
                area_id,
                cover_target,
                smoothed_temp,
                raw_peak,
                predicted_peak_temp,
                excess,
            )
        else:
            # Without cooling the question is whether the room overheats from
            # where it is now (#418): plan peak, or the free-running estimate.
            self._smoothed_excess.pop(area_id, None)
            if predicted_peak_temp is not None:
                _cover_predicted_peak = predicted_peak_temp
            else:
                _cover_predicted_peak = self._estimate_solar_peak_temp(
                    area_id, current_temp, cover_target, q_solar, outdoor_temp, _surface_azimuths
                )

        # Heating demand: solar gain is welcome, never shade against it. A cool_only
        # room has no heating demand, its heat side is only the band floor.
        if (
            room.get("climate_mode") != "cool_only"
            and targets.heat is not None
            and smoothed_temp is not None
            and smoothed_temp < targets.heat
        ):
            _cover_predicted_peak = cover_target

        if _oriented_q_solar < COVER_SOLAR_MIN and _surface_azimuths:
            _cover_predicted_peak = cover_target

        # None (store default up to 1.8.2) means the default the room page shows.
        _outdoor_min = room.get("covers_outdoor_min_temp")
        if _outdoor_min is None:
            _outdoor_min = DEFAULT_COVERS_OUTDOOR_MIN_TEMP
        if outdoor_temp is not None and outdoor_temp < _outdoor_min:
            _cover_predicted_peak = cover_target

        # Block E: Evaluate + apply
        cover_eids = room.get("covers", [])
        _cover_min_positions: dict[str, int] = room.get("cover_min_positions", {})
        window_hold = window_open and room.get("covers_window_hold", False)
        before = self._cover_manager.snapshot(area_id) if window_hold else None
        cover_decision = self._cover_manager.evaluate(
            area_id,
            covers_auto_enabled=room.get("covers_auto_enabled", False),
            cover_entity_ids=cover_eids,
            covers_deploy_threshold=room.get("covers_deploy_threshold", 1.5),
            covers_min_position=room.get("covers_min_position", 0),
            covers_snap_deploy=room.get("covers_snap_deploy", False),
            shade_by_need=can_cool,
            predicted_peak_temp=_cover_predicted_peak,
            target_temp=cover_target,
            q_solar=q_solar,
            has_active_override=has_override,
            forced_position=_forced_position,
            forced_expected=(
                self._expected_position(cover_eids, _forced_position, _cover_min_positions)
                if _forced_position is not None
                else None
            ),
            forced_reason=_forced_reason,
            forced_unknown=_forced_unknown,
            current_temp=current_temp,
            solar_gated=_solar_gated,
        )
        if (
            before is not None
            and cover_decision.changed
            and self._lowers_any(cover_eids, cover_decision.target_position, _cover_min_positions)
        ):
            cover_decision = self._cover_manager.hold(area_id, before, "window_hold")
            _forced_position = None

        if cover_decision.changed:
            _LOGGER.debug(
                "Cover control [%s]: %s → position %d%%",
                area_id,
                cover_decision.reason,
                cover_decision.target_position,
            )
            await CoverManager.async_apply(
                self.hass,
                cover_eids,
                cover_decision.target_position,
                cover_min_positions=_cover_min_positions or None,
            )
            expected = self._expected_position(cover_eids, cover_decision.target_position, _cover_min_positions)
            if expected is not None:
                self._cover_manager.set_commanded_position(area_id, expected)

        return CoverResult(
            forced_reason=_forced_reason if _forced_position is not None else "",
            active_cover_schedule_index=_active_cover_sched_idx,
            decision=cover_decision,
        )

    def _may_still_load(self, entity_id: str) -> bool:
        """True while an unreadable force source may still get its state (start), False once it is gone.

        A deleted helper or selector (no state, no registry entry while HA runs) and one still
        unreadable MAX_SENSOR_STALENESS after HA started running would otherwise keep a hand-closed
        cover counting as found inside a forced phase for good (#499).
        """
        state = self.hass.states.get(entity_id)
        if not _unreadable(state):
            return False
        if self.hass.state is not CoreState.running:
            return True
        now = time.monotonic()  # a wall clock jump (NTP on a Pi without RTC) must not end the window
        if self._running_since is None:
            self._running_since = now
        if now - self._running_since > MAX_SENSOR_STALENESS:
            return False
        return state is not None or er.async_get(self.hass).async_get(entity_id) is not None

    def _reading(self, eid: str) -> int | None:
        """Position a cover reports, None while it reports none (unavailable, moving binary cover)."""
        cstate = self.hass.states.get(eid)
        if cstate is None:
            return None
        pos = cstate.attributes.get("current_position")
        if pos is not None:
            return int(pos)
        return {"closed": 0, "open": 100}.get(cstate.state)

    def _expected_position(
        self, cover_eids: list[str], target_position: int, min_positions: dict[str, int]
    ) -> int | None:
        """Room average the covers report once *target_position* is applied (per-cover minimum, binary covers).

        Counts the same covers as read_positions(), else the two averages never meet.
        """
        expected: list[int] = []
        for eid in cover_eids:
            cstate = self.hass.states.get(eid)
            if cstate is None or self._reading(eid) is None:
                continue
            supported = cstate.attributes.get("supported_features", 0) or 0
            if supported & _SUPPORT_SET_POSITION:
                expected.append(max(min_positions.get(eid, 0), target_position))
            elif target_position < 100:
                expected.append(0)
            else:
                expected.append(100)
        return int(sum(expected) / len(expected)) if expected else None

    def _lowers_any(self, cover_eids: list[str], target_position: int, min_positions: dict[str, int]) -> bool:
        """Return True if sending *target_position* would move any cover down.

        Checked per cover against its own reading: the room average can rise
        while one cover still goes down. A cover without a known position counts
        as going down unless it is sent fully open.
        """
        for eid in cover_eids:
            cstate = self.hass.states.get(eid)
            if cstate is None:
                continue
            supported = cstate.attributes.get("supported_features", 0) or 0
            if supported & _SUPPORT_SET_POSITION:
                goal = max(min_positions.get(eid, 0), target_position)
            elif target_position < 100:
                goal = 0
            else:
                continue
            if goal >= 100:
                continue
            pos = cstate.attributes.get("current_position")
            if pos is None:
                pos = {"closed": 0, "open": 100}.get(cstate.state)
            if pos is None or goal < int(pos):
                return True
        return False

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

        try:
            n_idle, _, _ = self._model_manager.get_mode_counts(area_id)
            if (
                n_idle >= COVER_MIN_IDLE_FOR_LEARNED
                and outdoor_temp is not None
                and self._idle_solar_model_confident(area_id, base_temp, outdoor_temp)
            ):
                # Tier 1: RC model trajectory with proper physics
                model = self._model_manager.get_model(area_id)
                n_steps = int(COVER_DAILY_LOOKAHEAD_H * 60 / COVER_PREDICTION_DT_MINUTES)
                solar_series = self._solar_series(n_steps, surface_azimuths)
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
        daily_series = self._solar_series(n_daily, surface_azimuths)
        q_solar_peak = max(daily_series) if daily_series else q_solar
        return base_temp + COVER_DEFAULT_BETA_S * q_solar_peak * COVER_LINEAR_LOOKAHEAD_H

    def _estimate_solar_load_peak(
        self,
        area_id: str,
        current_temp: float | None,
        target_temp: float,
        q_solar: float,
        outdoor_temp: float | None,
        surface_azimuths: list[float] | None = None,
    ) -> float:
        """Peak temperature the sun alone would cause in a room that can cool.

        Looks only ``COVER_COOLING_LOOKAHEAD_H`` ahead, so the cover moves when
        the load arrives, not at sunrise for the midday sun. Starts at
        ``min(current_temp, target_temp)``: above the target the unit holds or
        should hold the room, and the question is only what the sun adds from
        there. Heat the room would gain without sun (a hot outdoor temperature)
        is not counted above the target, shading cannot stop it:
        peak = max_t [T_sun(t) - max(0, T_nosun(t) - target)].

        Linear estimate: default gain times the solar input over
        ``COVER_COOLING_LINEAR_H`` (no envelope loss, the unit removes all solar
        heat; shorter, as the default gain is about twice a learned one). A
        confident idle model may raise it with the RC trajectories with and
        without sun over ``COVER_COOLING_LOOKAHEAD_H``, but not lower it: the
        confidence check passes on day one while the learned solar gain is
        still ~0, and over the horizon its spread stays ~2 K for days. With cover
        orientations the series is GHI weighted by whether the sun is on the
        facade (see _sunlit_weight).
        """
        base_temp = min(current_temp, target_temp) if current_temp is not None else target_temp
        n_steps = max(1, int(COVER_COOLING_LOOKAHEAD_H * 60 / COVER_PREDICTION_DT_MINUTES))
        solar_series = self._sunlit_solar_series(n_steps, surface_azimuths)
        if not solar_series:
            solar_series = [q_solar] * n_steps
        n_linear = max(1, int(COVER_COOLING_LINEAR_H * 60 / COVER_PREDICTION_DT_MINUTES))
        solar_input_h = sum(solar_series[:n_linear]) * COVER_PREDICTION_DT_MINUTES / 60.0
        linear_peak = base_temp + COVER_DEFAULT_BETA_S * solar_input_h

        try:
            n_idle, _, _ = self._model_manager.get_mode_counts(area_id)
            if (
                n_idle >= COVER_MIN_IDLE_FOR_LEARNED
                and outdoor_temp is not None
                and self._idle_solar_model_confident(area_id, base_temp, outdoor_temp)
            ):
                model = self._model_manager.get_model(area_id)
                outdoor_series = [outdoor_temp] * len(solar_series)
                idle_series = [0.0] * len(solar_series)
                with_sun = model.predict_trajectory(
                    base_temp,
                    outdoor_series,
                    idle_series,
                    COVER_PREDICTION_DT_MINUTES,
                    q_solar_series=solar_series,
                )
                without_sun = model.predict_trajectory(
                    base_temp, outdoor_series, idle_series, COVER_PREDICTION_DT_MINUTES
                )
                model_peak = max(
                    t_sun - max(0.0, t_dark - target_temp) for t_sun, t_dark in zip(with_sun, without_sun, strict=False)
                )
                return max(model_peak, linear_peak)
        except Exception:  # noqa: BLE001
            pass
        return linear_peak

    def _sunlit_solar_series(self, n_steps: int, surface_azimuths: list[float] | None) -> list[float]:
        """GHI series, weighted per step by how directly the sun faces the covers.

        Orientation decides *when* the sun is on the window, GHI how strong it
        is: the learned and the default solar gain are both per unit GHI, and
        scaling by the vertical incidence factor halved the load at noon.
        """
        lat = self.hass.config.latitude
        lon = self.hass.config.longitude
        series = build_solar_series(
            lat, lon, n_steps, dt_minutes=COVER_PREDICTION_DT_MINUTES, cloud_series=self._cloud_series
        )
        if not surface_azimuths:
            return series
        now = time.time()
        dt_s = COVER_PREDICTION_DT_MINUTES * 60.0
        return [
            q * self._sunlit_weight(solar_azimuth(lat, lon, now + i * dt_s), surface_azimuths)
            for i, q in enumerate(series)
        ]

    @staticmethod
    def _sunlit_weight(sun_azimuth: float, surface_azimuths: list[float]) -> float:
        """Share of the covers the sun shines on directly, 0..1, averaged over the covers.

        Full weight within ``COVER_DIRECT_SUN_ANGLE_DEG`` of the facade normal,
        fading to 0 when the sun runs parallel to the facade or behind it.
        """
        full = math.cos(math.radians(COVER_DIRECT_SUN_ANGLE_DEG))
        weights = [max(0.0, min(1.0, math.cos(math.radians(sun_azimuth - az)) / full)) for az in surface_azimuths]
        return sum(weights) / len(weights)

    def _solar_series(self, n_steps: int, surface_azimuths: list[float] | None) -> list[float]:
        """Unshaded solar series for the cover lookahead, oriented when azimuths are known."""
        lat = self.hass.config.latitude
        lon = self.hass.config.longitude
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

    def _smooth_temp(self, area_id: str, current_temp: float | None, now: float) -> float | None:
        if current_temp is None:
            self._smoothed_temp.pop(area_id, None)
            return None
        return self._smooth(self._smoothed_temp, area_id, current_temp, now)

    @staticmethod
    def _smooth(
        store: dict[str, tuple[float, float]],
        area_id: str,
        value: float,
        now: float,
        rise_minutes: float = COVER_SMOOTHING_MINUTES,
    ) -> float:
        """Time-based EMA so a compressor cycle does not reach the cover decision.

        *rise_minutes* sets the time constant while the value climbs; a shorter
        one lets a growing excess deploy in one move instead of a staircase.
        """
        prev = store.get(area_id)
        if prev is None:
            store[area_id] = (value, now)
            return value
        if now <= prev[1]:
            return prev[0]
        tau = rise_minutes if value > prev[0] else COVER_SMOOTHING_MINUTES
        weight = 1.0 - math.exp(-(now - prev[1]) / (tau * 60.0))
        smoothed = prev[0] + (value - prev[0]) * weight
        store[area_id] = (smoothed, now)
        return smoothed

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

    def get_user_override_until(self, area_id: str) -> float | None:
        """Delegate to CoverManager.get_user_override_until."""
        return self._cover_manager.get_user_override_until(area_id)

    def clear_user_override(self, area_id: str) -> None:
        """Delegate to CoverManager.clear_user_override."""
        self._cover_manager.clear_user_override(area_id)

    def remove_room(self, area_id: str) -> None:
        """Drop per-room smoothing state and delegate to CoverManager.remove_room."""
        self._smoothed_temp.pop(area_id, None)
        self._smoothed_excess.pop(area_id, None)
        self._cover_manager.remove_room(area_id)
