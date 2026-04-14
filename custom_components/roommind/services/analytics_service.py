"""Analytics data assembly service for RoomMind."""

from __future__ import annotations

import logging
import math
import time
from typing import Any, cast

from homeassistant.core import HomeAssistant

from ..const import (
    CLIMATE_MODE_COOL_ONLY,
    CLIMATE_MODE_HEAT_ONLY,
    DEFAULT_COMFORT_COOL,
    DEFAULT_COMFORT_HEAT,
    DEFAULT_ECO_COOL,
    DEFAULT_ECO_HEAT,
)
from ..control.mpc_controller import (
    DEFAULT_OUTDOOR_TEMP_FALLBACK,
    check_acs_can_heat,
    get_can_heat_cool,
    is_mpc_active,
)

_LOGGER = logging.getLogger(__name__)


def _safe_float(value: str) -> float | None:
    """Convert CSV string to float, or None for empty/invalid values."""
    if not value:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _safe_int(value: str) -> int | None:
    """Convert CSV string to int, or None for empty/invalid values."""
    if not value:
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def _csv_to_points(rows: list[dict]) -> list[dict]:
    """Convert CSV rows (string values, 'timestamp' key) to typed points ('ts' key)."""
    result = []
    for row in rows:
        ts = _safe_float(row.get("timestamp", ""))
        if ts is None:
            continue
        result.append(
            {
                "ts": ts,
                "room_temp": _safe_float(row.get("room_temp", "")),
                "outdoor_temp": _safe_float(row.get("outdoor_temp", "")),
                "target_temp": _safe_float(row.get("target_temp", "")),
                "mode": row.get("mode", ""),
                "predicted_temp": _safe_float(row.get("predicted_temp", "")),
                "window_open": row.get("window_open", "") in ("True", "true", "1"),
                "heating_power": _safe_float(row.get("heating_power", "")),
                "solar_irradiance": _safe_float(row.get("solar_irradiance", "")),
                "blind_position": _safe_int(row.get("blind_position", "")),
                "cover_reason": row.get("cover_reason", ""),
                "device_setpoint": _safe_float(row.get("device_setpoint", "")),
            }
        )
    return result


async def _compute_target_forecast(
    hass: HomeAssistant,
    room: dict,
    settings: dict,
    mold_prevention_delta: float = 0.0,
    hours: float = 3.0,
    interval_minutes: int = 5,
) -> list[dict]:
    """Compute target temperature forecast for the next N hours.

    Each point contains ``target_temp`` (chart display, mode-aware),
    ``heat_target`` and ``cool_target`` (for MPC simulator).
    """
    from ..utils.presence_utils import is_presence_away
    from ..utils.schedule_utils import (
        get_active_schedule_entity,
        read_schedule_blocks,
        resolve_targets_at_time,
    )
    from ..utils.temp_utils import ha_temp_to_celsius

    comfort_heat = room.get("comfort_heat", room.get("comfort_temp", DEFAULT_COMFORT_HEAT))
    comfort_cool = room.get("comfort_cool", DEFAULT_COMFORT_COOL)
    eco_heat = room.get("eco_heat", room.get("eco_temp", DEFAULT_ECO_HEAT))
    eco_cool = room.get("eco_cool", DEFAULT_ECO_COOL)
    override_until = room.get("override_until")
    override_temp = room.get("override_temp")
    vacation_until = settings.get("vacation_until")
    vacation_temp = settings.get("vacation_temp")
    climate_mode = room.get("climate_mode", "auto")

    presence_away = not room.get("ignore_presence", False) and is_presence_away(hass, room, settings)

    entity_id = get_active_schedule_entity(hass, room)
    schedule_blocks = await read_schedule_blocks(hass, entity_id) if entity_id else None

    _hass = hass
    converter = lambda v: ha_temp_to_celsius(_hass, v)  # noqa: E731

    # Generate forecast points
    now = time.time()
    end_ts = now + hours * 3600
    result: list[dict] = []
    ts = now
    while ts <= end_ts:
        targets = resolve_targets_at_time(
            ts,
            schedule_blocks,
            override_until,
            override_temp,
            vacation_until,
            vacation_temp,
            comfort_heat,
            comfort_cool,
            eco_heat,
            eco_cool,
            presence_away=presence_away,
            block_temp_converter=converter,
            presence_away_action=settings.get("presence_away_action", "eco"),
            schedule_off_action=settings.get("schedule_off_action", "eco"),
        )
        heat_target = targets.heat
        cool_target = targets.cool

        # Apply mold prevention delta to heat target only
        if heat_target is not None:
            heat_target = round(heat_target + mold_prevention_delta, 1)
        elif mold_prevention_delta > 0:
            heat_target = round(eco_heat + mold_prevention_delta, 1)

        # Chart display: mode-aware single value
        if climate_mode == CLIMATE_MODE_COOL_ONLY:
            target = cool_target
        elif climate_mode == CLIMATE_MODE_HEAT_ONLY:
            target = heat_target
        else:
            # Auto mode: show heat target (primary for chart line)
            target = heat_target

        result.append(
            {
                "ts": round(ts, 1),
                "target_temp": target,
                "heat_target": heat_target,
                "cool_target": cool_target,
            }
        )
        ts += interval_minutes * 60
    return result


async def build_analytics_data(
    hass: HomeAssistant,
    area_id: str,
    range_key: str,
    store: Any,
    coordinator: Any,
    custom_start: float | None = None,
    custom_end: float | None = None,
) -> dict:
    """Build analytics response data for a room.

    This is the core data assembly extracted from websocket_get_analytics.
    """
    settings = store.get_settings()
    history_store = getattr(coordinator, "_history_store", None)

    # Read history data -- custom timestamps take precedence over range preset
    detail: list = []
    history: list = []
    if history_store:
        if custom_start is not None:
            detail = _csv_to_points(
                await hass.async_add_executor_job(history_store.read_detail, area_id, None, custom_start, custom_end)
            )
            history = _csv_to_points(
                await hass.async_add_executor_job(history_store.read_history, area_id, None, custom_start, custom_end)
            )
        else:
            max_age_map = {
                "12h": 43200,
                "24h": 86400,
                "2d": 172800,
                "7d": 604800,
                "14d": 1209600,
                "30d": 2592000,
                "90d": 7776000,
            }
            max_age = max_age_map.get(range_key, 43200)
            detail = _csv_to_points(await hass.async_add_executor_job(history_store.read_detail, area_id, max_age))
            history = _csv_to_points(await hass.async_add_executor_job(history_store.read_history, area_id, max_age))

    # Model info (only if estimator exists -- avoid auto-creating for unknown rooms)
    model_info: dict = {}
    mpc_active = False
    if coordinator:
        mgr = coordinator._model_manager
        if area_id in mgr._estimators:
            est = mgr._estimators[area_id]
            rc = est.get_model()
            pred_std_idle = est.prediction_std(0.0, 20.0, 15.0, 5.0)
            pred_std_heat = est.prediction_std(rc.Q_heat, 20.0, 10.0, 5.0)
            room_config = store.get_room(area_id) or {}
            has_ext_sensor = bool(room_config.get("temperature_sensor"))
            if has_ext_sensor:
                can_heat, can_cool = get_can_heat_cool(
                    room_config, coordinator.outdoor_temp, acs_can_heat=check_acs_can_heat(hass, room_config)
                )
                T_out = (
                    coordinator.outdoor_temp if coordinator.outdoor_temp is not None else DEFAULT_OUTDOOR_TEMP_FALLBACK
                )
                mpc_active = is_mpc_active(mgr, area_id, can_heat, can_cool, 20.0, T_out)
            else:
                mpc_active = False
            # EKF uncertainty: sqrt(P[0][0]) as proxy for sigma_e
            sigma_proxy = math.sqrt(max(est._P[0][0], 0.0))
            model_info = {
                "confidence": est.confidence,
                "model": rc.to_dict(),
                "n_samples": est._n_updates,
                "n_observations": est._n_updates,
                "n_heating": est._n_heating,
                "n_cooling": est._n_cooling,
                "applicable_modes": sorted(est._applicable_modes),
                "mpc_active": mpc_active,
                "sigma_e": round(sigma_proxy, 4),
                "prediction_std_idle": round(pred_std_idle, 4),
                "prediction_std_heating": round(pred_std_heat, 4),
            }

    # Build merged forecast: same format as history points, on a shared 5-min grid
    room_config = store.get_room(area_id) or {}
    mold_delta = 0.0
    if coordinator:
        live = coordinator.rooms.get(area_id, {})
        mold_delta = live.get("mold_prevention_delta", 0.0)
    try:
        target_forecast = await _compute_target_forecast(
            hass,
            room_config,
            settings,
            mold_prevention_delta=mold_delta,
        )
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Target forecast computation failed for '%s'", area_id)
        target_forecast = []

    # Forward-simulate temperature prediction for the forecast period.
    from ..control.analytics_simulator import (
        build_forecast_outdoor_series,
        build_forecast_solar_series,
        simulate_prediction,
    )

    pred_temps: list[float | None] = list()
    prediction_enabled = settings.get("prediction_enabled", True)
    if prediction_enabled and target_forecast and coordinator:
        mgr = coordinator._model_manager
        if area_id in mgr._estimators:
            model = mgr.get_model(area_id)
            est = mgr._estimators[area_id]
            all_points = detail if detail else history
            current_t: float | None = None
            for p in reversed(all_points):
                if p.get("room_temp") is not None:
                    current_t = p["room_temp"]
                    break
            if current_t is not None:
                T_out_now = (
                    coordinator.outdoor_temp if coordinator.outdoor_temp is not None else DEFAULT_OUTDOOR_TEMP_FALLBACK
                )
                outdoor_series = build_forecast_outdoor_series(
                    coordinator._weather_manager._outdoor_forecast,
                    T_out_now,
                    len(target_forecast),
                )
                # Shading factor from current cover positions
                live = coordinator.rooms.get(area_id, {})
                _shading = 1.0
                if live.get("blind_position") is not None:
                    from ..managers.cover_manager import compute_shading_factor

                    _shading = compute_shading_factor([live["blind_position"]])
                solar_series = build_forecast_solar_series(
                    hass.config.latitude,
                    hass.config.longitude,
                    coordinator._weather_manager._outdoor_forecast,
                    len(target_forecast),
                    shading_factor=_shading,
                )
                # Residual heat state for analytics simulation
                system_type = room_config.get("heating_system_type", "")
                sim_q_residual = 0.0
                sim_heat_dur = 0.0
                sim_last_pf = 1.0
                if system_type and area_id in getattr(coordinator._residual_tracker, "_off_since", {}):
                    import time as _time

                    off_since = coordinator._residual_tracker._off_since[area_id]
                    elapsed = (_time.time() - off_since) / 60.0
                    sim_heat_dur = (off_since - coordinator._residual_tracker._on_since.get(area_id, off_since)) / 60.0
                    sim_last_pf = coordinator._residual_tracker._off_power.get(area_id, 1.0)
                    from ..control.residual_heat import compute_residual_heat

                    sim_q_residual = compute_residual_heat(elapsed, system_type, sim_last_pf, sim_heat_dur)

                sim_q_occupancy = 0.0
                for occ_eid in room_config.get("occupancy_sensors", []):
                    occ_state = hass.states.get(occ_eid)
                    if occ_state and occ_state.state == "on":
                        sim_q_occupancy = 1.0
                        break

                pred_temps = cast(
                    list[float | None],
                    simulate_prediction(
                        model=model,
                        estimator=est,
                        target_forecast=target_forecast,
                        outdoor_series=outdoor_series,
                        current_temp=current_t,
                        window_open=coordinator._window_manager._paused.get(area_id, False),
                        mpc_active=mpc_active,
                        room_config=room_config,
                        settings=settings,
                        all_points=all_points,
                        solar_series=solar_series,
                        acs_can_heat=check_acs_can_heat(hass, room_config),
                        q_residual=sim_q_residual,
                        heating_system_type=system_type,
                        heating_duration_minutes=sim_heat_dur,
                        last_power_fraction=sim_last_pf,
                        q_occupancy=sim_q_occupancy,
                    ),
                )

    # Merge into unified forecast points on shared 5-min grid
    forecast: list[dict] = []
    grid = 300  # 5 minutes
    for i, tf in enumerate(target_forecast):
        snapped = round(tf["ts"] / grid) * grid
        forecast.append(
            {
                "ts": snapped,
                "room_temp": None,
                "outdoor_temp": None,
                "target_temp": tf["target_temp"],
                "mode": "forecast",
                "predicted_temp": pred_temps[i] if i < len(pred_temps) else None,
                "window_open": False,
                "device_setpoint": None,
            }
        )

    return {
        "detail": detail,
        "history": history,
        "model": model_info,
        "forecast": forecast,
    }
