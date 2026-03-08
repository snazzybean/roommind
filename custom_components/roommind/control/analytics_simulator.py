"""Analytics temperature prediction simulator for RoomMind."""

from __future__ import annotations

import time

from ..const import (
    BANGBANG_COOL_HYSTERESIS,
    BANGBANG_HEAT_HYSTERESIS,
    DEFAULT_OUTDOOR_COOLING_MIN,
    DEFAULT_OUTDOOR_HEATING_MAX,
    MODE_COOLING,
    MODE_HEATING,
    MODE_IDLE,
)
from .mpc_controller import DEFAULT_OUTDOOR_TEMP_FALLBACK, get_can_heat_cool
from .mpc_optimizer import MPCOptimizer
from .residual_heat import build_residual_series, get_min_run_blocks
from .thermal_model import RCModel, ThermalEKF


def build_forecast_outdoor_series(
    forecast: list[dict], current_outdoor: float, n_blocks: int,
) -> list[float]:
    """Build outdoor temperature series from weather forecast or fallback."""
    if forecast:
        series = [
            f.get("temperature", current_outdoor) for f in forecast
        ]
        while len(series) < n_blocks:
            series.append(series[-1] if series else current_outdoor)
        return series[:n_blocks]
    return [current_outdoor] * n_blocks


def build_forecast_solar_series(
    latitude: float, longitude: float,
    forecast: list[dict], n_blocks: int,
    shading_factor: float = 1.0,
) -> list[float] | None:
    """Build solar series for analytics prediction from forecast cloud coverage.

    Returns None if latitude/longitude are not available (clear-sky handled
    inside solar module).
    """
    if latitude == 0.0 and longitude == 0.0:
        return None
    from .solar import build_solar_series

    cloud_series: list[float | None] | None = None
    if forecast:
        cloud_series = [f.get("cloud_coverage") for f in forecast]
    series = build_solar_series(latitude, longitude, n_blocks, 5.0, cloud_series=cloud_series)
    if series is not None and shading_factor != 1.0:
        series = [s * shading_factor for s in series]
    return series


def compute_observed_idle_rate(
    all_points: list[dict],
) -> float | None:
    """Compute observed idle cooling/heating rate from recent history.

    Returns the rate in degC per 5 minutes, or None if insufficient data.
    Used to cap the bang-bang fallback simulation so it doesn't predict
    faster change than what we actually observe.
    """
    if not all_points:
        return None
    now_ts = time.time()
    idle_pts: list[tuple[float, float]] = []
    for p in reversed(all_points):
        if now_ts - p["ts"] > 3600:
            break
        mode_str = p.get("mode") or ""
        rt = p.get("room_temp")
        if rt is not None and mode_str in ("", "idle"):
            idle_pts.append((p["ts"], rt))
    if len(idle_pts) < 2:
        return None
    idle_pts.sort(key=lambda x: x[0])
    dt_sec = idle_pts[-1][0] - idle_pts[0][0]
    if dt_sec <= 60:
        return None
    rate_per_sec = (idle_pts[-1][1] - idle_pts[0][1]) / dt_sec
    return rate_per_sec * 300  # per 5 min


def simulate_prediction(
    *,
    model: RCModel,
    estimator: ThermalEKF,
    target_forecast: list[dict],
    outdoor_series: list[float],
    current_temp: float,
    window_open: bool,
    mpc_active: bool,
    room_config: dict,
    settings: dict,
    all_points: list[dict],
    solar_series: list[float] | None = None,
    acs_can_heat: bool = False,
    q_residual: float = 0.0,
    heating_system_type: str = "",
    heating_duration_minutes: float = 0.0,
    last_power_fraction: float = 1.0,
) -> list[float]:
    """Simulate temperature prediction for the analytics chart.

    Dispatches to the appropriate simulation strategy:
    - Window open: pure heat exchange via window
    - MPC active: rolling-horizon optimizer simulation
    - Fallback: bang-bang with hysteresis
    """
    if window_open:
        return _simulate_window_open(model, estimator, target_forecast, outdoor_series, current_temp)

    if mpc_active:
        return _simulate_mpc(
            model, target_forecast, outdoor_series, current_temp, room_config, settings,
            solar_series=solar_series, acs_can_heat=acs_can_heat,
            q_residual=q_residual, heating_system_type=heating_system_type,
            heating_duration_minutes=heating_duration_minutes,
            last_power_fraction=last_power_fraction,
        )

    return _simulate_bangbang(
        model, target_forecast, outdoor_series, current_temp, room_config, all_points,
        solar_series=solar_series, acs_can_heat=acs_can_heat,
        q_residual=q_residual, heating_system_type=heating_system_type,
        heating_duration_minutes=heating_duration_minutes,
        last_power_fraction=last_power_fraction,
    )


def _simulate_window_open(
    model: RCModel,
    estimator: ThermalEKF,
    target_forecast: list[dict],
    outdoor_series: list[float],
    current_temp: float,
) -> list[float]:
    """Simulate with window open — HVAC paused, pure heat exchange."""
    k_win = estimator.k_window
    T = current_temp
    pred_temps: list[float] = []
    for i, _tf in enumerate(target_forecast):
        T = model.predict_window_open(T, outdoor_series[i], k_win, 5.0)
        T = max(5.0, min(40.0, T))
        pred_temps.append(round(T, 2))
    return pred_temps


def _simulate_mpc(
    model: RCModel,
    target_forecast: list[dict],
    outdoor_series: list[float],
    current_temp: float,
    room_config: dict,
    settings: dict,
    *,
    solar_series: list[float] | None = None,
    acs_can_heat: bool = False,
    q_residual: float = 0.0,
    heating_system_type: str = "",
    heating_duration_minutes: float = 0.0,
    last_power_fraction: float = 1.0,
) -> list[float]:
    """Rolling-horizon MPC simulation matching the real controller."""
    ocm = settings.get("outdoor_cooling_min", DEFAULT_OUTDOOR_COOLING_MIN)
    ohm = settings.get("outdoor_heating_max", DEFAULT_OUTDOOR_HEATING_MAX)
    can_heat, can_cool = get_can_heat_cool(room_config, None, ocm, ohm, acs_can_heat=acs_can_heat)
    cw = settings.get("comfort_weight", 70)

    min_run = get_min_run_blocks(heating_system_type, 5.0)

    optimizer = MPCOptimizer(
        model=model,
        can_heat=can_heat,
        can_cool=can_cool,
        w_comfort=max(1.0, cw / 10.0),
        w_energy=max(1.0, (100 - cw) / 10.0),
        outdoor_cooling_min=ocm,
        outdoor_heating_max=ohm,
        min_run_blocks=min_run,
    )

    T = current_temp
    prev_action = MODE_IDLE
    blocks_in_action = 0
    # Track residual heat through simulated mode transitions
    sim_residual_elapsed = 0.0  # minutes since simulated heating stopped
    sim_heating_blocks = 0  # blocks of simulated heating for charge fraction
    sim_was_heating = False
    # Seed with real residual state
    current_q_residual = q_residual
    pred_temps: list[float] = []

    for i in range(len(target_forecast)):
        tgt = target_forecast[i]["target_temp"]
        h_tgt = target_forecast[i].get("heat_target", tgt)
        c_tgt = target_forecast[i].get("cool_target", tgt)

        # Force idle when both targets are None (devices turned off)
        if h_tgt is None and c_tgt is None:
            action = MODE_IDLE
            pf = 0.0
        # External stickiness: once heating/cooling, continue until
        # target is reached.  Mirrors real HVAC behaviour.
        elif prev_action == MODE_HEATING and h_tgt is not None and T < h_tgt and can_heat:
            action = MODE_HEATING
            pf = 1.0
        elif prev_action == MODE_COOLING and c_tgt is not None and T > c_tgt and can_cool:
            action = MODE_COOLING
            pf = 1.0
        elif prev_action != MODE_IDLE and blocks_in_action < min_run:
            action = prev_action
            pf = 1.0
        else:
            remaining_outdoor = outdoor_series[i:]
            remaining_heat_targets = [
                tf.get("heat_target", tf["target_temp"]) if tf.get("heat_target", tf["target_temp"]) is not None else T
                for tf in target_forecast[i:]
            ]
            remaining_cool_targets = [
                tf.get("cool_target", tf["target_temp"]) if tf.get("cool_target", tf["target_temp"]) is not None else T
                for tf in target_forecast[i:]
            ]
            remaining_solar = solar_series[i:] if solar_series else None
            # Build residual series for remaining blocks
            remaining_residual = None
            if heating_system_type and current_q_residual > 0:
                remaining_residual = build_residual_series(
                    sim_residual_elapsed, heating_system_type,
                    len(remaining_outdoor), 5.0,
                    last_power_fraction,
                    sim_heating_blocks * 5.0 if sim_was_heating else heating_duration_minutes,
                )
            plan = optimizer.optimize(
                T_room=T,
                T_outdoor_series=remaining_outdoor,
                heat_target_series=remaining_heat_targets,
                cool_target_series=remaining_cool_targets,
                dt_minutes=5.0,
                solar_series=remaining_solar,
                residual_series=remaining_residual,
            )
            action = plan.get_current_action()
            pf = plan.get_current_power_fraction()
        if action == MODE_HEATING:
            Q = pf * model.Q_heat
        elif action == MODE_COOLING:
            Q = -(pf * model.Q_cool)
        else:
            Q = 0.0
        qs = solar_series[i] if solar_series and i < len(solar_series) else 0.0
        T_new = model.predict(
            T, outdoor_series[i], Q, 5.0, q_solar=qs,
            q_residual=current_q_residual if Q == 0.0 else 0.0,
        )
        T = max(5.0, min(40.0, T_new))

        # Update simulated residual tracking
        if action == MODE_HEATING:
            sim_heating_blocks += 1
            sim_was_heating = True
            sim_residual_elapsed = 0.0
            current_q_residual = 0.0
        else:
            if sim_was_heating and sim_residual_elapsed == 0.0:
                # Just transitioned from heating to non-heating
                pass
            sim_residual_elapsed += 5.0
            if heating_system_type and sim_was_heating:
                from .residual_heat import compute_residual_heat
                current_q_residual = compute_residual_heat(
                    sim_residual_elapsed, heating_system_type,
                    last_power_fraction,
                    sim_heating_blocks * 5.0,
                )

        if action == prev_action:
            blocks_in_action += 1
        else:
            prev_action = action
            blocks_in_action = 1

        pred_temps.append(round(T, 2))

    return pred_temps


def _simulate_bangbang(
    model: RCModel,
    target_forecast: list[dict],
    outdoor_series: list[float],
    current_temp: float,
    room_config: dict,
    all_points: list[dict],
    *,
    solar_series: list[float] | None = None,
    acs_can_heat: bool = False,
    q_residual: float = 0.0,
    heating_system_type: str = "",
    heating_duration_minutes: float = 0.0,
    last_power_fraction: float = 1.0,
) -> list[float]:
    """Bang-bang fallback simulation with mode stickiness + idle rate cap."""
    observed_idle_rate = compute_observed_idle_rate(all_points)
    has_heat = bool(room_config.get("thermostats")) or acs_can_heat
    has_cool = bool(room_config.get("acs"))

    min_run = get_min_run_blocks(heating_system_type, 5.0)

    T = current_temp
    sim_mode = MODE_IDLE
    blocks_in_mode = 0
    # Track residual heat through simulated mode transitions
    sim_residual_elapsed = 0.0
    sim_heating_blocks = 0
    sim_was_heating = False
    current_q_residual = q_residual
    pred_temps: list[float] = []

    for i, tf in enumerate(target_forecast):
        tgt = tf["target_temp"]
        h_tgt = tf.get("heat_target", tgt)
        c_tgt = tf.get("cool_target", tgt)
        if h_tgt is None and c_tgt is None:
            # Force idle when both targets are None (devices turned off)
            sim_mode = MODE_IDLE
            blocks_in_mode = 0
        elif sim_mode != MODE_IDLE and blocks_in_mode < min_run:
            pass  # honour minimum run time
        elif sim_mode == MODE_HEATING:
            if h_tgt is None or T >= h_tgt:
                sim_mode = MODE_IDLE
                blocks_in_mode = 0
        elif sim_mode == MODE_COOLING:
            if c_tgt is None or T <= c_tgt:
                sim_mode = MODE_IDLE
                blocks_in_mode = 0
        else:
            if has_heat and h_tgt is not None and T < h_tgt - BANGBANG_HEAT_HYSTERESIS:
                sim_mode = MODE_HEATING
                blocks_in_mode = 0
            elif has_cool and c_tgt is not None and T > c_tgt + BANGBANG_COOL_HYSTERESIS:
                sim_mode = MODE_COOLING
                blocks_in_mode = 0

        if sim_mode == MODE_HEATING:
            Q = model.Q_heat
        elif sim_mode == MODE_COOLING:
            Q = -model.Q_cool
        else:
            Q = 0.0

        qs = solar_series[i] if solar_series and i < len(solar_series) else 0.0
        T_new = model.predict(
            T, outdoor_series[i], Q, 5.0, q_solar=qs,
            q_residual=current_q_residual if Q == 0.0 else 0.0,
        )
        if Q == 0.0 and observed_idle_rate is not None:
            model_delta = T_new - T
            max_delta = observed_idle_rate * 2.0
            if model_delta < 0 and max_delta < 0 and model_delta < max_delta:
                T_new = T + max_delta
            elif model_delta > 0 and max_delta > 0 and model_delta > max_delta:
                T_new = T + max_delta

        T = max(5.0, min(40.0, T_new))
        blocks_in_mode += 1

        # Update simulated residual tracking
        if sim_mode == MODE_HEATING:
            sim_heating_blocks += 1
            sim_was_heating = True
            sim_residual_elapsed = 0.0
            current_q_residual = 0.0
        else:
            sim_residual_elapsed += 5.0
            if heating_system_type and sim_was_heating:
                from .residual_heat import compute_residual_heat
                current_q_residual = compute_residual_heat(
                    sim_residual_elapsed, heating_system_type,
                    last_power_fraction,
                    sim_heating_blocks * 5.0,
                )

        pred_temps.append(round(T, 2))

    return pred_temps
