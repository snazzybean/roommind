"""DataUpdateCoordinator for RoomMind."""

from __future__ import annotations

import logging
import time
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DEFAULT_MOLD_COOLDOWN_MINUTES, DEFAULT_MOLD_HUMIDITY_THRESHOLD, DEFAULT_MOLD_SUSTAINED_MINUTES, DEFAULT_VALVE_PROTECTION_INTERVAL, DOMAIN, EKF_UPDATE_MIN_DT, HEATING_BOOST_TARGET, HISTORY_ROTATE_CYCLES, HISTORY_WRITE_CYCLES, MAX_PREDICTION_DELTA, MODE_HEATING, MODE_IDLE, MOLD_HYSTERESIS, MOLD_RISK_CRITICAL, MOLD_RISK_OK, MOLD_RISK_WARNING, MOLD_SURFACE_RH_WARNING, SCHEDULE_STATE_ON, THERMAL_SAVE_CYCLES, UPDATE_INTERVAL, VALVE_PROTECTION_CHECK_CYCLES, VALVE_PROTECTION_CYCLE_DURATION, build_override_live
from .mold_utils import calculate_mold_risk, mold_prevention_delta
from .notification_utils import NotificationThrottler, dismiss_mold_notification, async_send_mold_notification
from .history_store import HistoryStore
from .mpc_controller import DEFAULT_OUTDOOR_TEMP_FALLBACK, MPCController, async_turn_off_climate, check_acs_can_heat, get_can_heat_cool, is_mpc_active, resolve_hvac_mode
from .sensor_utils import read_sensor_value
from .solar import compute_q_solar_norm
from .temp_utils import celsius_delta_to_ha, celsius_to_ha_temp, ha_temp_to_celsius, ha_temp_unit_str
from .thermal_model import RoomModelManager

_LOGGER = logging.getLogger(__name__)


def _get_area_name(hass: HomeAssistant, area_id: str) -> str:
    """Get human-readable area name from area registry."""
    area_reg = ar.async_get(hass)
    area = area_reg.async_get_area(area_id)
    return area.name if area else area_id


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
        self._window_open_since: dict[str, float] = {}
        self._window_closed_since: dict[str, float] = {}
        self._window_paused: dict[str, bool] = {}
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
        self._outdoor_forecast: list[dict] = []
        # EKF accumulator: batch updates for better signal-to-noise ratio
        self._ekf_accumulated_dt: dict[str, float] = {}
        self._ekf_accumulated_mode: dict[str, str] = {}
        self._ekf_accumulated_pf: dict[str, float] = {}
        self._current_q_solar: float = 0.0
        # Valve protection (anti-seize)
        self._valve_protection_count: int = 0
        self._valve_cycling: dict[str, float] = {}
        self._valve_last_actuation: dict[str, float] = {}
        self._valve_actuation_dirty: bool = False
        # Mold risk tracking
        self._mold_risk_since: dict[str, float] = {}
        self._mold_prevention_active: dict[str, bool] = {}
        self._mold_throttler = NotificationThrottler()
        # Residual heat tracking (heating → idle transition)
        self._heating_off_since: dict[str, float] = {}
        self._heating_off_power: dict[str, float] = {}
        self._heating_on_since: dict[str, float] = {}

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
            self._valve_last_actuation = dict(settings.get("valve_last_actuation", {}))
            self._model_loaded = True

        # Initialize history store (once)
        if self._history_store is None:
            self._history_store = HistoryStore(
                self.hass.config.path(".storage/roommind_history")
            )

        room_states: dict[str, dict] = {}

        # Read weather forecast once for all rooms
        outdoor_forecast = await self._read_weather_forecast(settings)
        self._outdoor_forecast = outdoor_forecast

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
                            raw_pred = model.predict(current_temp, self.outdoor_temp, Q, 3.0, q_solar=self._current_q_solar)
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
        await self._async_valve_protection_finish()

        # Valve protection: check for stale valves (throttled)
        self._valve_protection_count += 1
        if self._valve_protection_count >= VALVE_PROTECTION_CHECK_CYCLES:
            self._valve_protection_count = 0
            await self._async_valve_protection_check(rooms, settings)

        # Persist valve actuation timestamps (piggyback on thermal save cycle)
        if self._valve_actuation_dirty and self._thermal_save_count == 0:
            await store.async_save_settings({"valve_last_actuation": self._valve_last_actuation})
            self._valve_actuation_dirty = False

        self.rooms = room_states
        return {"rooms": room_states}

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
        mold_risk_level = MOLD_RISK_OK
        mold_surface_rh = None
        mold_prevention_active_room = False
        mold_prevention_temp_delta = 0.0

        if settings.get("mold_detection_enabled") or settings.get("mold_prevention_enabled"):
            if current_humidity is not None and current_temp is not None:
                mold_risk_level, mold_surface_rh = calculate_mold_risk(
                    current_temp, current_humidity, self.outdoor_temp,
                )

                threshold = settings.get(
                    "mold_humidity_threshold", DEFAULT_MOLD_HUMIDITY_THRESHOLD,
                )

                now = time.time()
                is_risky = (
                    current_humidity >= threshold
                    or mold_risk_level in (MOLD_RISK_WARNING, MOLD_RISK_CRITICAL)
                )
                sustained_minutes = settings.get(
                    "mold_sustained_minutes", DEFAULT_MOLD_SUSTAINED_MINUTES,
                )

                if is_risky:
                    if area_id not in self._mold_risk_since:
                        self._mold_risk_since[area_id] = now

                    sustained_seconds = now - self._mold_risk_since[area_id]

                    # Notify if sustained long enough
                    if (
                        settings.get("mold_detection_enabled")
                        and settings.get("mold_notifications_enabled", True)
                        and sustained_seconds >= sustained_minutes * 60
                    ):
                        cooldown = (
                            settings.get(
                                "mold_notification_cooldown",
                                DEFAULT_MOLD_COOLDOWN_MINUTES,
                            )
                            * 60
                        )
                        if self._mold_throttler.should_send(
                            f"detect_{area_id}", cooldown,
                        ):
                            targets = settings.get("mold_notification_targets", [])
                            area_name = _get_area_name(self.hass, area_id)
                            await async_send_mold_notification(
                                self.hass, area_id, area_name, targets,
                                message=(
                                    f"Mold risk in {area_name}: "
                                    f"{current_humidity:.0f}% humidity, "
                                    f"estimated surface RH {mold_surface_rh:.0f}%"
                                ),
                                title="RoomMind: Mold Risk Warning",
                                tag_suffix="risk",
                            )
                            self._mold_throttler.record_sent(f"detect_{area_id}")

                    # Activate prevention
                    if (
                        settings.get("mold_prevention_enabled")
                        and mold_risk_level in (MOLD_RISK_WARNING, MOLD_RISK_CRITICAL)
                    ):
                        intensity = settings.get("mold_prevention_intensity", "medium")
                        mold_prevention_temp_delta = mold_prevention_delta(intensity)

                        if not self._mold_prevention_active.get(area_id):
                            self._mold_prevention_active[area_id] = True
                            if (
                                settings.get("mold_prevention_notify_enabled")
                                and settings.get("mold_notifications_enabled", True)
                            ):
                                prev_targets = settings.get(
                                    "mold_prevention_notify_targets", [],
                                )
                                area_name = _get_area_name(self.hass, area_id)
                                await async_send_mold_notification(
                                    self.hass, area_id, area_name, prev_targets,
                                    message=(
                                        f"Mold prevention active in {area_name}: "
                                        f"temperature raised by "
                                        f"{celsius_delta_to_ha(self.hass, mold_prevention_temp_delta):.0f}{ha_temp_unit_str(self.hass)}"
                                    ),
                                    title="RoomMind: Mold Prevention",
                                    tag_suffix="prevention",
                                )
                                self._mold_throttler.record_sent(
                                    f"prevent_{area_id}",
                                )
                        mold_prevention_active_room = True
                else:
                    # Risk cleared — use hysteresis for deactivation
                    if (
                        mold_surface_rh is not None
                        and mold_surface_rh < (MOLD_SURFACE_RH_WARNING - MOLD_HYSTERESIS)
                    ):
                        self._mold_risk_since.pop(area_id, None)
                        if self._mold_prevention_active.get(area_id):
                            self._mold_prevention_active[area_id] = False
                            dismiss_mold_notification(
                                self.hass, area_id, "risk",
                            )
                            dismiss_mold_notification(
                                self.hass, area_id, "prevention",
                            )
                        self._mold_throttler.clear(f"detect_{area_id}")
                        self._mold_throttler.clear(f"prevent_{area_id}")

        # Determine target temperature from HA schedule entity
        target_temp = self._resolve_target_temp(room, settings)

        # Apply mold prevention temperature delta (additive on resolved target)
        if mold_prevention_active_room and mold_prevention_temp_delta > 0:
            target_temp += mold_prevention_temp_delta

        # Read schedule blocks for MPC lookahead (pre-heating/pre-cooling)
        from .schedule_utils import get_active_schedule_entity, make_target_resolver, read_schedule_blocks
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
        q_residual = 0.0
        if system_type and area_id in self._heating_off_since and self._previous_modes.get(area_id, MODE_IDLE) != MODE_HEATING:
            from .residual_heat import compute_residual_heat as _compute_qr
            elapsed = (time.time() - self._heating_off_since[area_id]) / 60.0
            heat_dur = (
                self._heating_off_since[area_id]
                - self._heating_on_since.get(area_id, self._heating_off_since[area_id])
            ) / 60.0
            last_pf = self._heating_off_power.get(area_id, 1.0)
            q_residual = _compute_qr(elapsed, system_type, last_pf, heat_dur)

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
            cloud_series=self._extract_cloud_series(outdoor_forecast),
            q_residual=q_residual,
            heating_system_type=system_type,
        )
        mode, power_fraction = await controller.async_evaluate(current_temp, target_temp)

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
        open_delay = room.get("window_open_delay", 0)
        close_delay = room.get("window_close_delay", 0)
        now = time.time()
        was_paused = self._window_paused.get(area_id, False)

        if raw_open:
            self._window_closed_since.pop(area_id, None)
            if not was_paused:
                if area_id not in self._window_open_since:
                    self._window_open_since[area_id] = now
                if now - self._window_open_since[area_id] >= open_delay:
                    self._window_paused[area_id] = True
        else:
            self._window_open_since.pop(area_id, None)
            if was_paused:
                if area_id not in self._window_closed_since:
                    self._window_closed_since[area_id] = now
                if now - self._window_closed_since[area_id] >= close_delay:
                    self._window_paused[area_id] = False
                    self._window_closed_since.pop(area_id, None)

        window_open = self._window_paused.get(area_id, False)
        if window_open:
            mode = MODE_IDLE
            power_fraction = 0.0

        # --- Residual heat transition tracking ---
        # Update heating start/stop timestamps based on current mode.
        # q_residual was already computed above from previous cycle state.
        if system_type:
            if mode == MODE_HEATING:
                # Actively heating: track start time, clear residual
                self._heating_off_since.pop(area_id, None)
                self._heating_off_power[area_id] = power_fraction
                if self._previous_modes.get(area_id, MODE_IDLE) != MODE_HEATING:
                    self._heating_on_since[area_id] = time.time()
            elif self._previous_modes.get(area_id, MODE_IDLE) == MODE_HEATING:
                # Transition from heating: start residual tracking
                self._heating_off_since[area_id] = time.time()
            elif q_residual == 0.0 and area_id in self._heating_off_since:
                # Residual has fully decayed, clean up
                self._heating_off_since.pop(area_id, None)
                self._heating_off_power.pop(area_id, None)
                self._heating_on_since.pop(area_id, None)

        # Exclude TRVs currently being valve-protection-cycled from normal control
        cycling_eids = {eid for eid in room.get("thermostats", []) if eid in self._valve_cycling}

        if settings.get("climate_control_active", True):
            try:
                await controller.async_apply(
                    mode, target_temp, power_fraction=power_fraction,
                    current_temp=current_temp, exclude_eids=cycling_eids,
                )
            except Exception:  # noqa: BLE001
                _LOGGER.warning(
                    "Room '%s': climate service call failed",
                    area_id,
                    exc_info=True,
                )
        else:
            # Climate control disabled (learn-only) — do NOT send any commands.
            # Observe actual device state for accurate model training.
            observed_mode, observed_pf = self._observe_device_action(room)
            if observed_mode is not None and observed_mode != MODE_IDLE:
                _LOGGER.debug(
                    "Room '%s': device self-regulating (%s), using for training",
                    area_id, observed_mode,
                )
            mode = MODE_IDLE
            power_fraction = 0.0

        # Track valve actuation during normal heating
        if mode == MODE_HEATING:
            now_ts = time.time()
            for eid in room.get("thermostats", []):
                self._valve_last_actuation[eid] = now_ts
            self._valve_actuation_dirty = True

        # Determine mode for EKF training: when control is disabled, use
        # observed device state so self-regulating thermostats don't corrupt
        # the model (see #36).
        climate_active = settings.get("climate_control_active", True)
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
                self._flush_ekf_accumulator(area_id, current_temp, T_outdoor, room, q_residual=q_residual)
                self._model_manager.update_window_open(
                    area_id, current_temp, T_outdoor, dt_minutes,
                )
            elif ekf_mode is None:
                # Unobservable device state (control disabled, no hvac_action)
                # — flush pending data and skip training to prevent corruption.
                self._flush_ekf_accumulator(area_id, current_temp, T_outdoor, room, q_residual=q_residual)
                self._ekf_accumulated_dt.pop(area_id, None)
                self._ekf_accumulated_mode.pop(area_id, None)
                self._ekf_accumulated_pf.pop(area_id, None)
            else:
                # Normal: accumulate and batch EKF updates
                prev_mode = self._ekf_accumulated_mode.get(area_id)
                if prev_mode is not None and prev_mode != ekf_mode:
                    # Mode changed — flush with the previous mode
                    self._flush_ekf_accumulator(area_id, current_temp, T_outdoor, room, q_residual=q_residual)

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
                        q_solar=self._current_q_solar,
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

        # Compute MPC status for live data
        mpc_active = False
        if has_external_sensor and settings.get("control_mode") == "mpc":
            try:
                can_heat, can_cool = get_can_heat_cool(room, self.outdoor_temp, acs_can_heat=check_acs_can_heat(self.hass, room))
                T_out = self.outdoor_temp if self.outdoor_temp is not None else DEFAULT_OUTDOOR_TEMP_FALLBACK
                mpc_active = is_mpc_active(
                    self._model_manager, area_id, can_heat, can_cool,
                    current_temp or 20.0, T_out,
                )
            except Exception:  # noqa: BLE001
                mpc_active = False

        # Minimum max_temp across thermostats (for UI display clamping)
        trv_max_temps = []
        for eid in room.get("thermostats", []):
            st = self.hass.states.get(eid)
            if st and st.attributes.get("max_temp") is not None:
                trv_max_temps.append(st.attributes["max_temp"])
        device_max_temp = min(trv_max_temps) if trv_max_temps else None

        return {
            "area_id": area_id,
            "current_temp": current_temp,
            "current_humidity": current_humidity,
            "target_temp": target_temp,
            "mode": mode,
            "heating_power": round(power_fraction * 100) if mode != MODE_IDLE else 0,
            "trv_setpoint": self._compute_trv_setpoint(mode, power_fraction, current_temp, target_temp, has_external_sensor, device_max_temp),
            "window_open": window_open,
            **build_override_live(room),
            "active_schedule_index": self._get_active_schedule_index(room),
            "confidence": self._model_manager.get_confidence(area_id),
            "mpc_active": mpc_active,
            "presence_away": presence_away,
            "mold_risk_level": mold_risk_level,
            "mold_surface_rh": (
                round(mold_surface_rh, 1) if mold_surface_rh is not None else None
            ),
            "mold_prevention_active": mold_prevention_active_room,
            "mold_prevention_delta": mold_prevention_temp_delta,
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
        q_residual: float = 0.0,
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
                q_solar=self._current_q_solar,
                q_residual=q_residual,
            )

    async def _async_valve_protection_finish(self) -> None:
        """End valve protection cycles that have exceeded their duration."""
        if not self._valve_cycling:
            return
        now = time.time()
        finished = [
            eid for eid, start in self._valve_cycling.items()
            if now - start >= VALVE_PROTECTION_CYCLE_DURATION
        ]
        for eid in finished:
            try:
                await async_turn_off_climate(self.hass, eid, area_id="valve_protection")
            except Exception:  # noqa: BLE001
                _LOGGER.warning("Valve protection: failed to close '%s'", eid)
            self._valve_cycling.pop(eid, None)
            self._valve_last_actuation[eid] = now
            self._valve_actuation_dirty = True
            _LOGGER.info("Valve protection: cycle complete for '%s'", eid)

    async def _async_valve_protection_check(
        self, rooms: dict, settings: dict,
    ) -> None:
        """Scan for TRV valves that have been idle too long and start cycling them."""
        if not settings.get("valve_protection_enabled", False):
            # Disabled — close any active cycles before clearing
            for eid in list(self._valve_cycling):
                try:
                    await async_turn_off_climate(self.hass, eid, area_id="valve_protection")
                except Exception:  # noqa: BLE001
                    _LOGGER.warning("Valve protection: failed to close '%s' on disable", eid)
            self._valve_cycling.clear()
            return

        interval_days = settings.get(
            "valve_protection_interval_days", DEFAULT_VALVE_PROTECTION_INTERVAL,
        )
        threshold = interval_days * 86400
        now = time.time()

        # Collect all configured TRV entity IDs
        all_trvs: set[str] = set()
        for room in rooms.values():
            for eid in room.get("thermostats", []):
                all_trvs.add(eid)

        # Start cycling stale valves
        for eid in all_trvs:
            if eid in self._valve_cycling:
                continue
            last = self._valve_last_actuation.get(eid, 0)
            if now - last >= threshold:
                try:
                    eid_state = self.hass.states.get(eid)
                    vp_modes = (eid_state.attributes.get("hvac_modes") or []) if eid_state else []
                    vp_resolved = resolve_hvac_mode("heat", vp_modes)
                    if vp_resolved is None:
                        _LOGGER.debug(
                            "Valve protection: '%s' supports neither 'heat' nor 'auto', skipping",
                            eid,
                        )
                        continue
                    await self.hass.services.async_call(
                        "climate", "set_hvac_mode",
                        {"entity_id": eid, "hvac_mode": vp_resolved}, blocking=True,
                    )
                    boost_temp = celsius_to_ha_temp(self.hass, HEATING_BOOST_TARGET)
                    if eid_state:
                        dev_max = eid_state.attributes.get("max_temp")
                        if dev_max is not None and boost_temp > dev_max:
                            boost_temp = dev_max
                    await self.hass.services.async_call(
                        "climate", "set_temperature",
                        {"entity_id": eid, "temperature": boost_temp},
                        blocking=True,
                    )
                    self._valve_cycling[eid] = now
                    idle_days = int((now - last) / 86400) if last else 0
                    _LOGGER.info(
                        "Valve protection: cycling '%s' (idle for %d days)", eid, idle_days,
                    )
                except Exception:  # noqa: BLE001
                    _LOGGER.warning("Valve protection: failed to start cycle for '%s'", eid)

        # Cleanup stale entries (entities no longer configured)
        stale = [eid for eid in self._valve_last_actuation if eid not in all_trvs]
        for eid in stale:
            del self._valve_last_actuation[eid]
        if stale:
            self._valve_actuation_dirty = True

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

    def _is_window_open(self, room: dict) -> bool:
        """Return True if any configured window/door sensor reports 'on' (open)."""
        for entity_id in room.get("window_sensors", []):
            state = self.hass.states.get(entity_id)
            if state and state.state == "on":
                return True
        return False

    def _is_presence_away(self, room: dict, settings: dict) -> bool:
        """Return True if presence detection says all relevant persons are away."""
        from .presence_utils import is_presence_away
        return is_presence_away(self.hass, room, settings)  # all tracked persons are away

    def _get_active_schedule_index(self, room: dict) -> int:
        """Return the index of the active schedule in room['schedules'].

        Returns -1 if there are no schedules.
        """
        from .schedule_utils import resolve_schedule_index
        return resolve_schedule_index(self.hass, room)

    def _resolve_target_temp(self, room: dict, settings: dict) -> float:
        """Resolve target temperature.

        Priority: override > vacation > presence away > schedule block temp > comfort/eco temp.
        """
        # 1. Check active override
        override_until = room.get("override_until")
        if override_until is not None:
            if time.time() < override_until:
                override_temp = room.get("override_temp")
                if override_temp is not None:
                    return float(override_temp)
            else:
                # Expired — clear asynchronously
                area_id = room.get("area_id", "unknown")
                store = self.hass.data[DOMAIN]["store"]
                self.hass.async_create_task(
                    store.async_update_room(area_id, {
                        "override_temp": None,
                        "override_until": None,
                        "override_type": None,
                    })
                )

        # 2. Vacation mode: global setback temperature
        vacation_until = settings.get("vacation_until")
        if vacation_until is not None:
            if time.time() < vacation_until:
                vacation_temp = settings.get("vacation_temp")
                if vacation_temp is not None:
                    return float(vacation_temp)
            else:
                # Expired — clear asynchronously
                self.hass.async_create_task(
                    self.hass.data[DOMAIN]["store"].async_save_settings({
                        "vacation_until": None,
                    })
                )

        # 2.5 Presence-based eco
        if self._is_presence_away(room, settings):
            return room.get("eco_temp", 17.0)

        # 3. Schedule / comfort / eco
        comfort_temp = room.get("comfort_temp", 21.0)
        eco_temp = room.get("eco_temp", 17.0)

        idx = self._get_active_schedule_index(room)
        if idx < 0:
            return comfort_temp

        schedules = room.get("schedules", [])
        schedule_entity_id = schedules[idx].get("entity_id", "")

        if not schedule_entity_id:
            return comfort_temp

        state = self.hass.states.get(schedule_entity_id)
        if state is None or state.state in ("unavailable", "unknown"):
            _LOGGER.debug(
                "Area '%s': schedule entity '%s' unavailable, using comfort_temp",
                room.get("area_id", "unknown"),
                schedule_entity_id,
            )
            return comfort_temp

        if state.state == SCHEDULE_STATE_ON:
            # Check for temperature in schedule block data attributes
            block_temp = state.attributes.get("temperature")
            if block_temp is not None:
                try:
                    return ha_temp_to_celsius(self.hass, float(block_temp))
                except (ValueError, TypeError):
                    pass
            return comfort_temp

        # Schedule is "off" -> eco mode
        return eco_temp

    async def async_room_added(self, room: dict) -> None:
        """Create sensor entities for a newly added room and refresh data."""
        if hasattr(self, "async_add_entities") and self.async_add_entities:
            from .sensor import _create_room_entities

            entities = _create_room_entities(self, room["area_id"])
            self.async_add_entities(entities)
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
        self._window_open_since.pop(area_id, None)
        self._window_closed_since.pop(area_id, None)
        self._window_paused.pop(area_id, None)
        self._previous_modes.pop(area_id, None)
        self._last_temps.pop(area_id, None)
        self._pending_predictions.pop(area_id, None)
        self._heating_off_since.pop(area_id, None)
        self._heating_off_power.pop(area_id, None)
        self._heating_on_since.pop(area_id, None)
        self._model_manager.remove_room(area_id)
        if self._history_store:
            await self.hass.async_add_executor_job(self._history_store.remove_room, area_id)

        await self.async_request_refresh()

    async def _read_weather_forecast(self, settings: dict) -> list[dict]:
        """Read weather forecast from configured weather entity."""
        weather_entity = settings.get("weather_entity", "")
        if not weather_entity:
            return []

        # Modern approach: use weather.get_forecasts service (HA 2024.6+)
        try:
            response = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": weather_entity, "type": "hourly"},
                blocking=True,
                return_response=True,
            )
            forecasts = response.get(weather_entity, {}).get("forecast", [])
            if isinstance(forecasts, list) and forecasts:
                return self._convert_forecast_temps(forecasts)
        except Exception:  # noqa: BLE001
            _LOGGER.debug(
                "weather.get_forecasts service call failed for %s, "
                "falling back to state attributes",
                weather_entity,
            )

        # Fallback: read deprecated state attribute (older HA versions)
        state = self.hass.states.get(weather_entity)
        if state is None:
            return []
        forecast = state.attributes.get("forecast")
        if isinstance(forecast, list):
            return self._convert_forecast_temps(forecast)
        return []

    def _convert_forecast_temps(self, forecasts: list[dict]) -> list[dict]:
        """Convert forecast temperatures from HA units to Celsius."""
        result = []
        for f in forecasts:
            if "temperature" in f:
                result.append({**f, "temperature": ha_temp_to_celsius(self.hass, f["temperature"])})
            else:
                result.append(f)
        return result

    @staticmethod
    def _extract_cloud_series(forecast: list[dict]) -> list[float | None] | None:
        """Extract cloud_coverage values from forecast entries.

        Returns None if no cloud data is available (clear-sky fallback).
        """
        if not forecast:
            return None
        series: list[float | None] = []
        for entry in forecast:
            cc = entry.get("cloud_coverage")
            series.append(float(cc) if cc is not None else None)
        return series if any(v is not None for v in series) else None
