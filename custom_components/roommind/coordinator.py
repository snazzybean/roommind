"""DataUpdateCoordinator for RoomMind."""

from __future__ import annotations

import logging
import time
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import CLIMATE_MODE_COOL_ONLY, CLIMATE_MODE_HEAT_ONLY, COVER_DEFAULT_BETA_S, COVER_MIN_IDLE_FOR_LEARNED, COVER_SOLAR_LOOKAHEAD_H, DEFAULT_COMFORT_COOL, DEFAULT_COMFORT_HEAT, DEFAULT_ECO_COOL, DEFAULT_ECO_HEAT, DOMAIN, EKF_UPDATE_MIN_DT, HEATING_BOOST_TARGET, HISTORY_ROTATE_CYCLES, HISTORY_WRITE_CYCLES, MAX_PREDICTION_DELTA, MODE_COOLING, MODE_HEATING, MODE_IDLE, SCHEDULE_STATE_ON, THERMAL_SAVE_CYCLES, TargetTemps, UPDATE_INTERVAL, VALVE_PROTECTION_CHECK_CYCLES, build_override_live
from .utils.history_store import HistoryStore
from .control.mpc_controller import DEFAULT_OUTDOOR_TEMP_FALLBACK, MPCController, check_acs_can_heat, get_can_heat_cool, is_mpc_active
from .utils.sensor_utils import read_sensor_value
from .control.solar import compute_q_solar_norm, solar_elevation
from .utils.schedule_utils import resolve_schedule_index
from .utils.temp_utils import celsius_delta_to_ha, ha_temp_to_celsius, ha_temp_unit_str
from .control.thermal_model import RoomModelManager
from .managers.mold_manager import MoldManager
from .managers.weather_manager import WeatherManager
from .managers.residual_heat_tracker import ResidualHeatTracker
from .managers.valve_manager import ValveManager
from .managers.window_manager import WindowManager

_LOGGER = logging.getLogger(__name__)


def _get_area_name(hass: HomeAssistant, area_id: str) -> str:
    """Get human-readable area name from area registry."""
    try:
        area_reg = ar.async_get(hass)
        area = area_reg.async_get_area(area_id)
        return area.name if area else area_id
    except Exception:  # noqa: BLE001
        return area_id


class RoomMindCoordinator(DataUpdateCoordinator):
    """Central coordinator for RoomMind room data and state."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.entry = entry
        self.rooms: dict = {}
        self.outdoor_temp: float | None = None
        self.outdoor_humidity: float | None = None
        self._window_manager = WindowManager()
        self._previous_modes: dict[str, str] = {}
        self._model_manager: RoomModelManager = RoomModelManager()
        self._model_loaded = False
        self._thermal_save_count: int = 0
        self._last_temps: dict[str, float] = {}
        self._history_store: HistoryStore | None = None
        self._history_write_count: int = 0
        self._history_rotate_count: int = 0
        self._pending_predictions: dict[str, float] = {}
        self._prediction_forecasts: dict[str, list[dict]] = {}
        self._weather_manager = WeatherManager(hass)
        # EKF accumulator: batch updates for better signal-to-noise ratio
        self._ekf_accumulated_dt: dict[str, float] = {}
        self._ekf_accumulated_mode: dict[str, str] = {}
        self._ekf_accumulated_pf: dict[str, float] = {}
        self._current_q_solar: float = 0.0
        # Valve protection (anti-seize)
        self._valve_manager = ValveManager(hass)
        # Mold risk tracking
        self._mold_manager = MoldManager(hass)
        # Residual heat tracking (heating → idle transition)
        self._residual_tracker = ResidualHeatTracker()
        # Cover/blind automatic control
        from .managers.cover_manager import CoverManager
        self._cover_manager = CoverManager()
        # Track which rooms already have entity platform entities registered
        self._entity_areas: set[str] = set()
        self._switch_entity_areas: set[str] = set()
        self._binary_sensor_entity_areas: set[str] = set()

    async def _async_update_data(self) -> dict:
        """Fetch and compute state for all rooms.

        This is the central loop that:
        1. Reads current temperatures from sensor entities
        2. Evaluates active schedule for each room
        3. Determines heating/cooling action per room
        4. Applies climate control commands
        5. Returns state dict consumed by sensor entities
        """
        store = self.hass.data[DOMAIN]["store"]
        rooms = store.get_rooms()

        # Read outdoor sensors from global settings
        settings = store.get_settings()
        outdoor_sensor_id = settings.get("outdoor_temp_sensor")
        raw_outdoor = read_sensor_value(
            self.hass, outdoor_sensor_id, "global", "outdoor temperature"
        )
        self.outdoor_temp = ha_temp_to_celsius(self.hass, raw_outdoor, entity_id=outdoor_sensor_id) if raw_outdoor is not None else None
        self.outdoor_humidity = read_sensor_value(
            self.hass, settings.get("outdoor_humidity_sensor"), "global", "outdoor humidity"
        )

        # Load thermal model and valve actuation data from store (once)
        if not self._model_loaded:
            thermal_data = store.get_thermal_data()
            if thermal_data:
                self._model_manager = RoomModelManager.from_dict(thermal_data)
            self._valve_manager.load_actuation_data(settings.get("valve_last_actuation", {}))
            self._model_loaded = True

        # Initialize history store (once)
        if self._history_store is None:
            self._history_store = HistoryStore(
                self.hass.config.path(".storage/roommind_history")
            )

        room_states: dict[str, dict] = {}

        # Read weather forecast once for all rooms
        outdoor_forecast = await self._weather_manager.async_read_forecast(settings)

        # Compute solar irradiance once per cycle
        cloud_coverage = None
        weather_entity = settings.get("weather_entity")
        if weather_entity:
            ws = self.hass.states.get(weather_entity)
            if ws:
                cloud_coverage = ws.attributes.get("cloud_coverage")
        self._current_q_solar = compute_q_solar_norm(
            self.hass.config.latitude, self.hass.config.longitude,
            time.time(), cloud_coverage,
        )

        for area_id, room in rooms.items():
            try:
                room_state = await self._async_process_room(room, settings, outdoor_forecast)
                room_states[area_id] = room_state
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Room '%s': processing failed, skipping", area_id)

        # Record to history store (throttled)
        learning_disabled = set(settings.get("learning_disabled_rooms", []))
        self._history_write_count += 1
        if self._history_write_count >= HISTORY_WRITE_CYCLES and self._history_store:
            self._history_write_count = 0
            for area_id, rs in room_states.items():
                if area_id in learning_disabled:
                    continue
                current_temp = rs.get("current_temp")
                mode = rs.get("mode", MODE_IDLE)
                target_temp = rs.get("target_temp")
                # Use the prediction made *last* write cycle for the
                # current timestamp — this compares "what the model
                # predicted would happen" vs "what actually happened".
                predicted = self._pending_predictions.pop(area_id, None)
                try:
                    await self.hass.async_add_executor_job(
                        self._history_store.record, area_id, {
                            "room_temp": current_temp,
                            "outdoor_temp": self.outdoor_temp,
                            "target_temp": target_temp,
                            "mode": mode,
                            "predicted_temp": predicted,
                            "window_open": rs.get("window_open", False),
                            "heating_power": rs.get("heating_power", 0),
                            "solar_irradiance": round(self._current_q_solar, 3),
                            "blind_position": rs.get("blind_position"),
                        })
                except Exception:  # noqa: BLE001
                    _LOGGER.warning("History record failed for '%s'", area_id)
                # Compute prediction for the *next* write cycle (~3 min ahead)
                if current_temp is not None and self.outdoor_temp is not None:
                    try:
                        is_window_open = rs.get("window_open", False)
                        if is_window_open:
                            raw_pred = self._model_manager.predict_window_open(
                                area_id, current_temp, self.outdoor_temp, 3.0,
                            )
                        else:
                            model = self._model_manager.get_model(area_id)
                            hp = rs.get("heating_power", 100) / 100.0
                            Q = hp * model.Q_heat if mode == "heating" else (-hp * model.Q_cool if mode == "cooling" else 0.0)
                            raw_pred = model.predict(current_temp, self.outdoor_temp, Q, 3.0, q_solar=self._current_q_solar * rs.get("shading_factor", 1.0))
                        # Sanity clamp: prevent unrealistic jumps in one prediction step
                        clamped = max(current_temp - MAX_PREDICTION_DELTA, min(current_temp + MAX_PREDICTION_DELTA, raw_pred))
                        self._pending_predictions[area_id] = round(clamped, 2)
                    except Exception:  # noqa: BLE001
                        pass

        # Save thermal data periodically
        self._thermal_save_count += 1
        if self._thermal_save_count >= THERMAL_SAVE_CYCLES:
            self._thermal_save_count = 0
            await store.async_save_thermal_data(self._model_manager.to_dict())

        # Rotate history periodically
        self._history_rotate_count += 1
        if self._history_rotate_count >= HISTORY_ROTATE_CYCLES and self._history_store:
            self._history_rotate_count = 0
            for area_id in rooms:
                try:
                    await self.hass.async_add_executor_job(self._history_store.rotate, area_id)
                except Exception:  # noqa: BLE001
                    _LOGGER.warning("History rotation failed for '%s'", area_id)

        # Valve protection: finish active cycles (runs every tick, cheap)
        await self._valve_manager.async_finish_cycles()

        # Valve protection: check for stale valves (throttled)
        self._valve_manager._check_count += 1
        if self._valve_manager._check_count >= VALVE_PROTECTION_CHECK_CYCLES:
            self._valve_manager._check_count = 0
            await self._valve_manager.async_check_and_cycle(rooms, settings)

        # Persist valve actuation timestamps (piggyback on thermal save cycle)
        if self._valve_manager.actuation_dirty and self._thermal_save_count == 0:
            await store.async_save_settings({"valve_last_actuation": self._valve_manager._last_actuation})
            self._valve_manager.actuation_dirty = False

        self.rooms = room_states
        return {"rooms": room_states}

    def _estimate_solar_peak_temp(
        self, area_id: str, current_temp: float | None, target_temp: float, q_solar: float,
    ) -> float:
        """Estimate peak room temperature from solar gain (without MPC).

        Uses EKF-learned beta_s if available, otherwise a conservative default.
        Falls back to target_temp as base when no room temp sensor.
        """
        try:
            n_idle, _, _ = self._model_manager.get_mode_counts(area_id)
            if n_idle >= COVER_MIN_IDLE_FOR_LEARNED:
                beta_s = self._model_manager.get_model(area_id).Q_solar
            else:
                beta_s = COVER_DEFAULT_BETA_S
        except Exception:  # noqa: BLE001
            beta_s = COVER_DEFAULT_BETA_S

        base_temp = current_temp if current_temp is not None else target_temp
        return base_temp + beta_s * q_solar * COVER_SOLAR_LOOKAHEAD_H

    async def _async_process_room(self, room: dict, settings: dict, outdoor_forecast: list[dict]) -> dict:
        """Process a single room: read sensor, evaluate schedule, apply control."""
        area_id = room.get("area_id", "unknown")

        temp_sensor_id = room.get("temperature_sensor")
        has_external_sensor = bool(temp_sensor_id)

        raw_temp = read_sensor_value(
            self.hass, temp_sensor_id, area_id, "temperature"
        )
        current_temp = ha_temp_to_celsius(self.hass, raw_temp, entity_id=temp_sensor_id) if raw_temp is not None else None

        # Fallback: read current_temperature from first thermostat/AC if no external sensor
        if current_temp is None and not has_external_sensor:
            raw_dev = self._read_device_temp(room)
            current_temp = ha_temp_to_celsius(self.hass, raw_dev) if raw_dev is not None else None

        current_humidity = read_sensor_value(
            self.hass, room.get("humidity_sensor"), area_id, "humidity"
        )

        # --- Mold risk calculation ---
        mold = await self._mold_manager.evaluate(
            area_id, _get_area_name(self.hass, area_id), current_temp, current_humidity,
            self.outdoor_temp, settings,
            celsius_delta_to_ha_fn=lambda d: celsius_delta_to_ha(self.hass, d),
            ha_temp_unit_str_fn=lambda: ha_temp_unit_str(self.hass),
        )
        mold_risk_level = mold.risk_level
        mold_surface_rh = mold.surface_rh
        mold_prevention_active_room = mold.prevention_active
        mold_prevention_temp_delta = mold.prevention_delta

        # Determine dual heat/cool target temperatures
        # Returns TargetTemps(heat, cool). None values mean "force off".
        targets = self._resolve_target_temps(room, settings)

        # Apply mold prevention temperature delta (heating target only).
        # Safety: mold prevention overrides "off" to prevent structural damage.
        force_off = targets.heat is None and targets.cool is None
        if mold_prevention_active_room and mold_prevention_temp_delta > 0:
            if force_off:
                eco_heat = room.get("eco_heat", room.get("eco_temp", DEFAULT_ECO_HEAT))
                eco_cool = room.get("eco_cool", DEFAULT_ECO_COOL)
                targets = TargetTemps(
                    heat=eco_heat + mold_prevention_temp_delta,
                    cool=eco_cool,
                )
                force_off = False
            elif targets.heat is not None:
                targets = TargetTemps(
                    heat=targets.heat + mold_prevention_temp_delta,
                    cool=targets.cool,
                )

        # Read schedule blocks for MPC lookahead (pre-heating/pre-cooling)
        from .utils.schedule_utils import get_active_schedule_entity, make_target_resolver, read_schedule_blocks
        schedule_entity_id = get_active_schedule_entity(self.hass, room)
        schedule_blocks = await read_schedule_blocks(self.hass, schedule_entity_id) if schedule_entity_id else None
        presence_away = self._is_presence_away(room, settings)
        target_resolver = make_target_resolver(
            schedule_blocks, room, settings,
            hass=self.hass,
            presence_away=presence_away,
            mold_prevention_delta=mold_prevention_temp_delta,
        )

        # --- Compute residual heat from previous cycle state ---
        system_type = room.get("heating_system_type", "")
        q_residual = self._residual_tracker.get_q_residual(
            area_id, system_type, self._previous_modes.get(area_id, MODE_IDLE),
        )

        # Read current cover positions for shading factor
        from .managers.cover_manager import compute_shading_factor
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
                area_id, int(sum(cover_positions) / len(cover_positions)),
                override_minutes=room.get("covers_override_minutes", 60),
            )
        shading_factor = compute_shading_factor(cover_positions)

        # Determine and apply mode with MPC controller
        controller = MPCController(
            self.hass,
            room,
            model_manager=self._model_manager,
            outdoor_temp=self.outdoor_temp,
            outdoor_forecast=outdoor_forecast,
            settings=settings,
            previous_mode=self._previous_modes.get(area_id, MODE_IDLE),
            has_external_sensor=has_external_sensor,
            target_resolver=target_resolver,
            q_solar=self._current_q_solar,
            latitude=self.hass.config.latitude,
            longitude=self.hass.config.longitude,
            cloud_series=WeatherManager.extract_cloud_series(outdoor_forecast),
            q_residual=q_residual,
            heating_system_type=system_type,
            shading_factor=shading_factor,
        )
        mode, power_fraction = await controller.async_evaluate(current_temp, targets)

        # Compute effective single target_temp for display/history (mode + climate_mode aware)
        climate_mode = room.get("climate_mode", "auto")
        if climate_mode == CLIMATE_MODE_COOL_ONLY:
            target_temp = targets.cool
        elif climate_mode == CLIMATE_MODE_HEAT_ONLY:
            target_temp = targets.heat
        else:  # auto
            if mode == MODE_HEATING and targets.heat is not None:
                target_temp = targets.heat
            elif mode == MODE_COOLING and targets.cool is not None:
                target_temp = targets.cool
            else:
                target_temp = targets.heat if targets.heat is not None else targets.cool

        # Force idle when target resolved to "off" (presence away or schedule off)
        if force_off:
            mode = MODE_IDLE
            power_fraction = 0.0

        # Store MPC prediction forecast for analytics
        if controller.last_plan and len(controller.last_plan.temperatures) > 1:
            plan = controller.last_plan
            now_ts = time.time()
            dt_s = plan.dt_minutes * 60
            self._prediction_forecasts[area_id] = [
                {"ts": round(now_ts + i * dt_s, 1), "temp": round(t, 2)}
                for i, t in enumerate(plan.temperatures)
            ]
        else:
            self._prediction_forecasts.pop(area_id, None)

        # Pause climate control when any window/door is open (with configurable delays)
        raw_open = self._is_window_open(room)
        window_open = self._window_manager.update(
            area_id, raw_open,
            room.get("window_open_delay", 0),
            room.get("window_close_delay", 0),
        )
        if window_open:
            mode = MODE_IDLE
            power_fraction = 0.0

        # observed_mode/observed_pf: only populated when climate control is off
        observed_mode: str | None = None
        observed_pf = 0.0

        climate_active = settings.get("climate_control_active", True)

        # --- Residual heat transition tracking ---
        # Only track when climate control is active — RoomMind-initiated heating
        # transitions don't exist when control is disabled.
        if climate_active and system_type:
            self._residual_tracker.update(
                area_id, mode, power_fraction,
                self._previous_modes.get(area_id, MODE_IDLE),
                q_residual=q_residual,
            )

        # Exclude TRVs currently being valve-protection-cycled from normal control
        cycling_eids = {eid for eid in room.get("thermostats", []) if eid in self._valve_manager._cycling}
        if climate_active:
            try:
                await controller.async_apply(
                    mode, targets, power_fraction=power_fraction,
                    current_temp=current_temp, exclude_eids=cycling_eids,
                )
            except Exception:  # noqa: BLE001
                _LOGGER.warning(
                    "Room '%s': climate service call failed",
                    area_id,
                    exc_info=True,
                )
        else:
            # Climate control disabled (learn-only) — do NOT send commands,
            # do NOT touch mode/power_fraction (used for internal tracking).
            observed_mode, observed_pf = self._observe_device_action(room)
            if observed_mode is not None and observed_mode != MODE_IDLE:
                _LOGGER.debug(
                    "Room '%s': device self-regulating (%s), using for training",
                    area_id, observed_mode,
                )
            mode = MODE_IDLE
            power_fraction = 0.0

        # --- Cover/blind automatic control ---
        from .managers.cover_manager import CoverManager as _CM
        has_override = (
            room.get("override_temp") is not None
            and room.get("override_until") is not None
            and room.get("override_until", 0) > time.time()
        )
        # Use the appropriate target for cover decisions
        cover_target = (
            targets.cool if mode == MODE_COOLING and targets.cool is not None
            else targets.heat if targets.heat is not None
            else 22.0
        )
        # Compute MPC active status for cover decisions (also used later for room_state)
        _cover_mpc_active = False
        if has_external_sensor:
            try:
                _ch, _cc = get_can_heat_cool(room, self.outdoor_temp, acs_can_heat=check_acs_can_heat(self.hass, room))
                _T_out = self.outdoor_temp if self.outdoor_temp is not None else DEFAULT_OUTDOOR_TEMP_FALLBACK
                _cover_mpc_active = is_mpc_active(
                    self._model_manager, area_id, _ch, _cc,
                    current_temp or 20.0, _T_out,
                )
            except Exception:  # noqa: BLE001
                _cover_mpc_active = False
        # --- Cover forced position (schedule / night close) ---
        _forced_position: int | None = None
        _forced_reason = ""
        _active_cover_sched_idx = -1
        cover_schedules = room.get("cover_schedules", [])
        if cover_schedules:
            _active_cover_sched_idx = resolve_schedule_index(
                self.hass, room,
                schedules_key="cover_schedules",
                selector_key="cover_schedule_selector_entity",
            )
            if 0 <= _active_cover_sched_idx < len(cover_schedules):
                entry = cover_schedules[_active_cover_sched_idx]
                eid = entry.get("entity_id", "")
                if eid:
                    _sched_st = self.hass.states.get(eid)
                    if _sched_st is not None and _sched_st.state == "on":
                        # Read position from schedule block data (like temperature)
                        # Fallback: 0 = fully closed
                        _block_pos = _sched_st.attributes.get("position")
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

        # Tiered cover prediction: MPC if available, else simple solar estimate.
        # Note: simple estimate intentionally uses unshaded q_solar to prevent
        # oscillation (shaded → low prediction → retract → sun hits → deploy).
        # MPC (Tier 3) handles shading correctly via lookahead planning.
        _cover_predicted_peak = controller.predicted_peak_temp
        if _cover_predicted_peak is None:
            _cover_predicted_peak = self._estimate_solar_peak_temp(
                area_id, current_temp, cover_target, self._current_q_solar,
            )

        cover_decision = self._cover_manager.evaluate(
            area_id,
            covers_auto_enabled=room.get("covers_auto_enabled", False),
            cover_entity_ids=cover_eids,
            covers_deploy_threshold=room.get("covers_deploy_threshold", 1.5),
            covers_min_position=room.get("covers_min_position", 0),
            covers_outdoor_min_temp=room.get("covers_outdoor_min_temp"),
            predicted_peak_temp=_cover_predicted_peak,
            target_temp=cover_target,
            q_solar=self._current_q_solar,
            outdoor_temp=self.outdoor_temp,
            has_active_override=has_override,
            forced_position=_forced_position,
            forced_reason=_forced_reason,
        )
        if cover_decision.changed:
            _LOGGER.debug(
                "Cover control [%s]: %s → position %d%%",
                area_id, cover_decision.reason, cover_decision.target_position,
            )
            await _CM.async_apply(
                self.hass, cover_eids, cover_decision.target_position
            )

        # Track valve actuation during normal heating
        if mode == MODE_HEATING:
            self._valve_manager.record_heating(room.get("thermostats", []))

        # Determine mode for EKF training: when control is disabled, use
        # observed device state so self-regulating thermostats don't corrupt
        # the model (see #36).
        if climate_active:
            ekf_mode: str | None = mode
            ekf_pf = power_fraction
        else:
            ekf_mode = observed_mode   # may be None → skip training
            ekf_pf = observed_pf

        # Update thermal model with observation (EKF online learning)
        # Updates are accumulated over ~3 min for better signal-to-noise ratio.
        # On mode change, the accumulator is flushed immediately with the old mode.
        learning_disabled = settings.get("learning_disabled_rooms", [])
        learning_active = area_id not in learning_disabled
        if learning_active and current_temp is not None:
            dt_minutes = UPDATE_INTERVAL / 60.0
            T_outdoor = self.outdoor_temp if self.outdoor_temp is not None else current_temp
            if window_open:
                # Window open: flush pending EKF update, then learn k_window
                self._flush_ekf_accumulator(area_id, current_temp, T_outdoor, room, q_residual=q_residual, shading_factor=shading_factor)
                self._model_manager.update_window_open(
                    area_id, current_temp, T_outdoor, dt_minutes,
                )
            elif ekf_mode is None:
                # Unobservable device state (control disabled, no hvac_action)
                # — flush pending data and skip training to prevent corruption.
                self._flush_ekf_accumulator(area_id, current_temp, T_outdoor, room, q_residual=q_residual, shading_factor=shading_factor)
                self._ekf_accumulated_dt.pop(area_id, None)
                self._ekf_accumulated_mode.pop(area_id, None)
                self._ekf_accumulated_pf.pop(area_id, None)
            else:
                # Normal: accumulate and batch EKF updates
                prev_mode = self._ekf_accumulated_mode.get(area_id)
                if prev_mode is not None and prev_mode != ekf_mode:
                    # Mode changed — flush with the previous mode
                    self._flush_ekf_accumulator(area_id, current_temp, T_outdoor, room, q_residual=q_residual, shading_factor=shading_factor)

                old_dt = self._ekf_accumulated_dt.get(area_id, 0.0)
                new_dt = old_dt + dt_minutes
                if new_dt > 0:
                    old_pf = self._ekf_accumulated_pf.get(area_id, 1.0)
                    self._ekf_accumulated_pf[area_id] = (old_pf * old_dt + ekf_pf * dt_minutes) / new_dt
                self._ekf_accumulated_dt[area_id] = new_dt
                self._ekf_accumulated_mode[area_id] = ekf_mode

                if self._ekf_accumulated_dt[area_id] >= EKF_UPDATE_MIN_DT:
                    can_heat, can_cool = get_can_heat_cool(room, acs_can_heat=check_acs_can_heat(self.hass, room))
                    pf = self._ekf_accumulated_pf.pop(area_id, 1.0)
                    self._model_manager.update(
                        area_id, current_temp, T_outdoor, ekf_mode,
                        self._ekf_accumulated_dt[area_id],
                        can_heat=can_heat, can_cool=can_cool,
                        power_fraction=pf,
                        q_solar=self._current_q_solar * shading_factor,
                        q_residual=q_residual,
                    )
                    self._ekf_accumulated_dt[area_id] = 0.0
            self._last_temps[area_id] = current_temp
        else:
            # Learning disabled or no temp — clear accumulator
            self._ekf_accumulated_dt.pop(area_id, None)
            self._ekf_accumulated_mode.pop(area_id, None)
            self._ekf_accumulated_pf.pop(area_id, None)

        self._previous_modes[area_id] = mode

        # Reuse MPC active status computed earlier for cover control
        mpc_active = _cover_mpc_active

        # Minimum max_temp across thermostats (for UI display clamping)
        trv_max_temps = []
        for eid in room.get("thermostats", []):
            st = self.hass.states.get(eid)
            if st and st.attributes.get("max_temp") is not None:
                trv_max_temps.append(st.attributes["max_temp"])
        device_max_temp = min(trv_max_temps) if trv_max_temps else None

        # Compute display mode: when control is off, show actual device state
        # without affecting internal tracking (residual heat, valve actuation,
        # _previous_modes).  See #36.
        if climate_active:
            display_mode = mode
            display_pf = power_fraction
        else:
            if observed_mode is not None and observed_mode != MODE_IDLE:
                display_mode = observed_mode
                display_pf = observed_pf
            elif observed_mode is None:
                display_mode = self._infer_device_mode(room)
                display_pf = 1.0 if display_mode != MODE_IDLE else 0.0
            else:
                display_mode = MODE_IDLE
                display_pf = 0.0

        return {
            "area_id": area_id,
            "current_temp": current_temp,
            "current_humidity": current_humidity,
            "target_temp": target_temp,
            "heat_target": targets.heat,
            "cool_target": targets.cool,
            "mode": display_mode,
            "heating_power": round(display_pf * 100) if display_mode != MODE_IDLE else 0,
            "trv_setpoint": self._compute_trv_setpoint(mode, power_fraction, current_temp, target_temp, has_external_sensor, device_max_temp),
            "window_open": window_open,
            **build_override_live(room),
            "active_schedule_index": self._get_active_schedule_index(room),
            "confidence": self._model_manager.get_confidence(area_id),
            "mpc_active": mpc_active,
            "presence_away": presence_away,
            "force_off": force_off,
            "mold_risk_level": mold_risk_level,
            "mold_surface_rh": (
                round(mold_surface_rh, 1) if mold_surface_rh is not None else None
            ),
            "mold_prevention_active": mold_prevention_active_room,
            "mold_prevention_delta": mold_prevention_temp_delta,
            "shading_factor": shading_factor,
            "n_observations": self._model_manager.get_n_observations(area_id),
            "blind_position": (
                self._cover_manager.get_current_position(area_id)
                if cover_eids else None
            ),
            "cover_auto_paused": (
                self._cover_manager.is_user_override_active(area_id)
                if cover_eids else False
            ),
            "cover_forced_reason": (
                _forced_reason if cover_eids and _forced_position is not None else ""
            ),
            "active_cover_schedule_index": (
                _active_cover_sched_idx if cover_eids else -1
            ),
        }

    @staticmethod
    def _compute_trv_setpoint(
        mode: str, power_fraction: float, current_temp: float | None,
        target_temp: float | None, has_external_sensor: bool,
        device_max_temp: float | None = None,
    ) -> float | None:
        """Compute the TRV setpoint sent to thermostats (for UI display)."""
        if mode != MODE_HEATING or not has_external_sensor or current_temp is None or target_temp is None:
            return None
        trv = round(current_temp + power_fraction * (HEATING_BOOST_TARGET - current_temp), 1)
        trv = max(target_temp, trv)
        trv = min(HEATING_BOOST_TARGET, trv)
        if device_max_temp is not None:
            trv = min(trv, device_max_temp)
        return trv

    def _flush_ekf_accumulator(
        self, area_id: str, current_temp: float, T_outdoor: float, room: dict,
        q_residual: float = 0.0, shading_factor: float = 1.0,
    ) -> None:
        """Flush accumulated EKF update (on mode change or window open)."""
        accumulated = self._ekf_accumulated_dt.pop(area_id, 0.0)
        prev_mode = self._ekf_accumulated_mode.pop(area_id, None)
        pf = self._ekf_accumulated_pf.pop(area_id, 1.0)
        if accumulated > 0 and prev_mode is not None:
            can_heat, can_cool = get_can_heat_cool(room, acs_can_heat=check_acs_can_heat(self.hass, room))
            self._model_manager.update(
                area_id, current_temp, T_outdoor, prev_mode, accumulated,
                can_heat=can_heat, can_cool=can_cool, power_fraction=pf,
                q_solar=self._current_q_solar * shading_factor,
                q_residual=q_residual,
            )

    def _read_device_temp(self, room: dict) -> float | None:
        """Read current_temperature from the first thermostat or AC entity."""
        for entity_id in room.get("thermostats", []) + room.get("acs", []):
            state = self.hass.states.get(entity_id)
            if state and state.attributes.get("current_temperature") is not None:
                try:
                    return float(state.attributes["current_temperature"])
                except (ValueError, TypeError):
                    continue
        return None

    def _observe_device_action(self, room: dict) -> tuple[str | None, float]:
        """Observe actual hvac_action from climate devices for model training.

        When climate control is disabled, devices may still self-regulate.
        This method reads the actual device state so the EKF receives
        correct mode information instead of blindly assuming idle.

        Returns (observed_mode, power_fraction):
          - ("heating", 1.0) / ("cooling", 1.0) / ("idle", 0.0) when conclusive
          - (None, 0.0) when state is unobservable (caller should skip training)
        """
        dominated: str | None = None

        for eid in room.get("thermostats", []) + room.get("acs", []):
            state = self.hass.states.get(eid)
            if state is None or state.state in ("unavailable", "unknown"):
                continue

            # Device explicitly off → conclusively idle
            if state.state == "off":
                if dominated is None:
                    dominated = "idle"
                continue

            # Device in an active hvac_mode → need hvac_action to determine firing
            action = state.attributes.get("hvac_action")
            if action is None:
                # No hvac_action attribute → can't tell if firing → unobservable
                return (None, 0.0)

            if action in ("heating", "preheating"):
                if dominated == "cooling":
                    return (None, 0.0)  # conflicting → skip
                dominated = "heating"
            elif action == "cooling":
                if dominated == "heating":
                    return (None, 0.0)  # conflicting → skip
                dominated = "cooling"
            elif action in ("idle", "off"):
                if dominated is None:
                    dominated = "idle"
            else:
                # drying, fan, etc. — unknown thermal effect → skip
                return (None, 0.0)

        if dominated is None:
            return (None, 0.0)  # no devices or all unavailable

        pf = 1.0 if dominated in ("heating", "cooling") else 0.0
        return (dominated, pf)

    def _infer_device_mode(self, room: dict) -> str:
        """Infer heating/cooling from hvac_mode when hvac_action is unavailable.

        Compares current_temperature to the device setpoint to avoid showing
        'Heating' when the thermostat is in heat mode but already at target.
        Used only for dashboard display — EKF training uses _observe_device_action.
        """
        for eid in room.get("thermostats", []) + room.get("acs", []):
            state = self.hass.states.get(eid)
            if state is None or state.state in ("unavailable", "unknown", "off"):
                continue
            current = state.attributes.get("current_temperature")
            setpoint = state.attributes.get("temperature")
            if state.state == "heat":
                if current is not None and setpoint is not None and current >= setpoint:
                    continue  # at or above setpoint — not actively heating
                return MODE_HEATING
            if state.state == "cool":
                if current is not None and setpoint is not None and current <= setpoint:
                    continue  # at or below setpoint — not actively cooling
                return MODE_COOLING
        return MODE_IDLE

    def _is_window_open(self, room: dict) -> bool:
        """Return True if any configured window/door sensor reports 'on' (open)."""
        for entity_id in room.get("window_sensors", []):
            state = self.hass.states.get(entity_id)
            if state and state.state == "on":
                return True
        return False

    def _is_presence_away(self, room: dict, settings: dict) -> bool:
        """Return True if presence detection says all relevant persons are away."""
        from .utils.presence_utils import is_presence_away
        return is_presence_away(self.hass, room, settings)  # all tracked persons are away

    def _get_active_schedule_index(self, room: dict) -> int:
        """Return the index of the active schedule in room['schedules'].

        Returns -1 if there are no schedules.
        """
        from .utils.schedule_utils import resolve_schedule_index
        return resolve_schedule_index(self.hass, room)

    def _resolve_target_temps(self, room: dict, settings: dict) -> TargetTemps:
        """Resolve dual heat/cool target temperatures.

        Priority: override > vacation > presence away > schedule block temp > comfort/eco.
        Returns TargetTemps(heat, cool). None values mean "force off".
        """
        # 1. Override — single-point target
        override_until = room.get("override_until")
        if override_until is not None:
            if time.time() < override_until:
                override_temp = room.get("override_temp")
                if override_temp is not None:
                    t = float(override_temp)
                    return TargetTemps(heat=t, cool=t)
            else:
                area_id = room.get("area_id", "unknown")
                store = self.hass.data[DOMAIN]["store"]
                self.hass.async_create_task(
                    store.async_update_room(area_id, {
                        "override_temp": None,
                        "override_until": None,
                        "override_type": None,
                    })
                )

        # 2. Vacation — heat setback, cooling stays at eco_cool
        vacation_until = settings.get("vacation_until")
        if vacation_until is not None:
            if time.time() < vacation_until:
                vacation_temp = settings.get("vacation_temp")
                if vacation_temp is not None:
                    t = float(vacation_temp)
                    eco_cool = room.get("eco_cool", DEFAULT_ECO_COOL)
                    return TargetTemps(heat=t, cool=max(t, eco_cool))
            else:
                self.hass.async_create_task(
                    self.hass.data[DOMAIN]["store"].async_save_settings({
                        "vacation_until": None,
                    })
                )

        # 2.5 Presence-based eco or off
        if self._is_presence_away(room, settings):
            if settings.get("presence_away_action", "eco") == "off":
                return TargetTemps(heat=None, cool=None)
            return TargetTemps(
                heat=room.get("eco_heat", room.get("eco_temp", DEFAULT_ECO_HEAT)),
                cool=room.get("eco_cool", DEFAULT_ECO_COOL),
            )

        # 3. Schedule / comfort / eco
        comfort_heat = room.get("comfort_heat", room.get("comfort_temp", DEFAULT_COMFORT_HEAT))
        comfort_cool = room.get("comfort_cool", DEFAULT_COMFORT_COOL)
        eco_heat = room.get("eco_heat", room.get("eco_temp", DEFAULT_ECO_HEAT))
        eco_cool = room.get("eco_cool", DEFAULT_ECO_COOL)

        idx = self._get_active_schedule_index(room)
        if idx < 0:
            return TargetTemps(heat=comfort_heat, cool=comfort_cool)

        schedules = room.get("schedules", [])
        schedule_entity_id = schedules[idx].get("entity_id", "")

        if not schedule_entity_id:
            return TargetTemps(heat=comfort_heat, cool=comfort_cool)

        state = self.hass.states.get(schedule_entity_id)
        if state is None or state.state in ("unavailable", "unknown"):
            return TargetTemps(heat=comfort_heat, cool=comfort_cool)

        if state.state == SCHEDULE_STATE_ON:
            # Check for split heat/cool temps first
            heat_temp = state.attributes.get("heat_temperature")
            cool_temp = state.attributes.get("cool_temperature")
            if heat_temp is not None or cool_temp is not None:
                h = comfort_heat
                c = comfort_cool
                if heat_temp is not None:
                    try:
                        h = ha_temp_to_celsius(self.hass, float(heat_temp))
                    except (ValueError, TypeError):
                        pass
                if cool_temp is not None:
                    try:
                        c = ha_temp_to_celsius(self.hass, float(cool_temp))
                    except (ValueError, TypeError):
                        pass
                return TargetTemps(heat=h, cool=c)
            block_temp = state.attributes.get("temperature")
            if block_temp is not None:
                try:
                    t = ha_temp_to_celsius(self.hass, float(block_temp))
                    return TargetTemps(heat=t, cool=t)  # single-point
                except (ValueError, TypeError):
                    pass
            return TargetTemps(heat=comfort_heat, cool=comfort_cool)

        # Schedule is "off" -> eco or off
        if settings.get("schedule_off_action", "eco") == "off":
            return TargetTemps(heat=None, cool=None)
        return TargetTemps(heat=eco_heat, cool=eco_cool)

    async def async_room_added(self, room: dict) -> None:
        """Create entity platform entities for a newly added/updated room and refresh data."""
        area_id = room["area_id"]
        has_covers = bool(room.get("covers"))

        if area_id not in self._entity_areas and hasattr(self, "async_add_entities") and self.async_add_entities:
            from .sensor import _create_room_entities

            entities = _create_room_entities(self, area_id)
            self.async_add_entities(entities)
            self._entity_areas.add(area_id)

        # Cover entities: only create when covers are configured.
        # Not removed on save — cleanup_orphaned_entities() handles that at startup
        # so brief config changes don't break user automations.
        if has_covers:
            if area_id not in self._switch_entity_areas and hasattr(self, "async_add_switch_entities") and self.async_add_switch_entities:
                from .switch import _create_room_switches

                self.async_add_switch_entities(_create_room_switches(self, area_id))
                self._switch_entity_areas.add(area_id)
            if area_id not in self._binary_sensor_entity_areas and hasattr(self, "async_add_binary_sensor_entities") and self.async_add_binary_sensor_entities:
                from .binary_sensor import _create_room_binary_sensors

                self.async_add_binary_sensor_entities(_create_room_binary_sensors(self, area_id))
                self._binary_sensor_entity_areas.add(area_id)

        await self.async_request_refresh()

    async def async_room_removed(self, area_id: str) -> None:
        """Remove sensor entities for a deleted room and refresh data."""
        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(self.hass)

        # Find and remove all entities whose unique_id belongs to this area
        entries_to_remove = [
            entity_entry.entity_id
            for entity_entry in registry.entities.values()
            if entity_entry.unique_id
            and entity_entry.unique_id.startswith(f"{DOMAIN}_{area_id}_")
        ]

        for entity_id in entries_to_remove:
            registry.async_remove(entity_id)

        # Clean up in-memory state
        self._window_manager.remove_room(area_id)
        self._previous_modes.pop(area_id, None)
        self._last_temps.pop(area_id, None)
        self._pending_predictions.pop(area_id, None)
        self._residual_tracker.remove_room(area_id)
        self._cover_manager.remove_room(area_id)
        self._entity_areas.discard(area_id)
        self._switch_entity_areas.discard(area_id)
        self._binary_sensor_entity_areas.discard(area_id)
        self._model_manager.remove_room(area_id)
        if self._history_store:
            await self.hass.async_add_executor_job(self._history_store.remove_room, area_id)

        await self.async_request_refresh()

    def cleanup_orphaned_entities(self) -> None:
        """Remove entities that no longer match any registered entity type.

        Called at startup to clean up entities from removed features.
        """
        from homeassistant.helpers import entity_registry as er

        store = self.hass.data[DOMAIN]["store"]
        rooms = store.get_rooms()
        registry = er.async_get(self.hass)

        # Known valid suffixes for each condition
        always_valid = ("_target_temp", "_mode")
        cover_only = ("_cover_auto", "_cover_paused")

        to_remove: list[str] = []
        for entity_entry in registry.entities.values():
            uid = entity_entry.unique_id
            if not uid or not uid.startswith(f"{DOMAIN}_"):
                continue

            # Extract area_id: roommind_{area_id}_{suffix}
            parts = uid.removeprefix(f"{DOMAIN}_")
            # Find which room this belongs to
            matched_area = None
            for area_id in rooms:
                if parts.startswith(f"{area_id}_"):
                    matched_area = area_id
                    break

            if matched_area is None:
                # Room no longer exists — orphaned entity
                to_remove.append(entity_entry.entity_id)
                continue

            suffix = parts.removeprefix(f"{matched_area}")
            room = rooms[matched_area]

            if suffix in always_valid:
                continue
            if suffix in cover_only and room.get("covers"):
                continue

            # Entity doesn't match any valid type — orphaned
            to_remove.append(entity_entry.entity_id)

        for eid in to_remove:
            _LOGGER.info("Removing orphaned entity: %s", eid)
            registry.async_remove(eid)

