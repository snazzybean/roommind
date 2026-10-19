"""Analytics temperature prediction simulator for RoomMind."""

from __future__ import annotations

import time
from functools import partial
from typing import cast

from ..const import (
    APPROACH_RATE_MIN,
    BANGBANG_COOL_HYSTERESIS,
    BANGBANG_HEAT_HYSTERESIS,
    DEFAULT_COMFORT_WEIGHT,
    DEFAULT_OUTDOOR_COOLING_MIN,
    DEFAULT_OUTDOOR_HEATING_MAX,
    MODE_COOLING,
    MODE_HEATING,
    MODE_IDLE,
    is_override_active,
)
from ..utils.device_utils import get_ac_eids, get_trv_eids
from .mpc_controller import (
    HARD_OVERSHOOT_CEILING,
    PLAN_DT_MINUTES,
    SAFETY_GUARD_MIN_BLOCKS,
    compute_horizon_blocks,
    decide_mpc_action,
    fill_missing_targets,
    gentle_power,
    get_can_heat_cool,
    heat_start_hysteresis,
    is_mpc_enabled,
    is_slow_heat,
    is_valve_modulating,
    outdoor_gate_limits,
    valve_demand,
)
from .mpc_optimizer import MPCOptimizer, preheat_max_blocks, slow_start_penalty
from .residual_heat import (
    advance_rebound,
    build_residual_series,
    compute_residual_heat,
    get_min_run_blocks,
    mean_rebound,
)
from .thermal_model import RCModel, ThermalEKF


def build_forecast_outdoor_series(
    forecast: list[dict] | None,
    current_outdoor: float,
    n_blocks: int,
) -> list[float]:
    """Build outdoor temperature series for analytics prediction.

    Block 0 uses ``current_outdoor`` (real-time sensor reading). Subsequent
    blocks expand each hourly forecast entry to ``60 // PLAN_DT_MINUTES`` blocks.
    Padded with the last forecast value when the horizon exceeds the forecast.
    """
    if not forecast:
        return [current_outdoor] * n_blocks

    from .mpc_controller import PLAN_DT_MINUTES

    blocks_per_hour = 60 // PLAN_DT_MINUTES

    series: list[float] = []
    for f in forecast:
        temp = f.get("temperature", current_outdoor)
        series.extend([temp] * blocks_per_hour)
        if len(series) >= n_blocks:
            break

    series[0] = current_outdoor

    while len(series) < n_blocks:
        series.append(series[-1])

    return series[:n_blocks]


def build_forecast_solar_series(
    latitude: float,
    longitude: float,
    forecast: list[dict],
    n_blocks: int,
    shading_factor: float = 1.0,
) -> list[float] | None:
    """Build solar series for analytics prediction from forecast cloud coverage.

    Expands hourly ``cloud_coverage`` entries to ``60 // PLAN_DT_MINUTES`` blocks
    before passing to the solar module, matching the MPC controller's solar
    series construction. Returns None if latitude/longitude are not available.
    """
    if latitude == 0.0 and longitude == 0.0:
        return None
    from .mpc_controller import PLAN_DT_MINUTES
    from .solar import build_solar_series

    cloud_series: list[float | None] | None = None
    if forecast:
        blocks_per_hour = 60 // PLAN_DT_MINUTES
        expanded: list[float | None] = []
        for f in forecast:
            cc = f.get("cloud_coverage")
            expanded.extend([cc] * blocks_per_hour)
        cloud_series = expanded[:n_blocks]
        while len(cloud_series) < n_blocks:
            cloud_series.append(cloud_series[-1] if cloud_series else None)

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
    q_occupancy: float = 0.0,
    previous_mode: str = MODE_IDLE,
    mode_elapsed_minutes: float | None = None,
    q_rebound: float | None = None,
    run_system: str | None = None,
    outdoor_known: bool = True,
) -> list[float]:
    """Simulate temperature prediction for the analytics chart.

    Dispatches to the appropriate simulation strategy:
    - Window open: pure heat exchange via window
    - MPC active: rolling-horizon optimizer simulation
    - Fallback: bang-bang with hysteresis
    """
    # Run rules follow the system actually heating (AC alone in a UFH room, as in the controller)
    rules = heating_system_type if run_system is None else run_system
    if window_open:
        return _simulate_window_open(model, estimator, target_forecast, outdoor_series, current_temp)

    if mpc_active:
        return _simulate_mpc(
            model,
            target_forecast,
            outdoor_series,
            current_temp,
            room_config,
            settings,
            solar_series=solar_series,
            acs_can_heat=acs_can_heat,
            q_residual=q_residual,
            heating_system_type=heating_system_type,
            heating_duration_minutes=heating_duration_minutes,
            last_power_fraction=last_power_fraction,
            q_occupancy=q_occupancy,
            previous_mode=previous_mode,
            mode_elapsed_minutes=mode_elapsed_minutes,
            q_rebound=q_rebound,
            run_system=rules,
            outdoor_known=outdoor_known,
        )

    return _simulate_bangbang(
        model,
        target_forecast,
        outdoor_series,
        current_temp,
        room_config,
        all_points,
        solar_series=solar_series,
        acs_can_heat=acs_can_heat,
        q_residual=q_residual,
        heating_system_type=heating_system_type,
        heating_duration_minutes=heating_duration_minutes,
        last_power_fraction=last_power_fraction,
        q_occupancy=q_occupancy,
        previous_mode=previous_mode,
        mode_elapsed_minutes=mode_elapsed_minutes,
        q_rebound=q_rebound,
        run_system=rules,
        capped=is_mpc_enabled(settings) and not is_slow_heat(get_min_run_blocks(rules, PLAN_DT_MINUTES)),
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


def _idle_drift(
    model: RCModel,
    T: float,
    T_out: float,
    q_solar: float,
    q_residual: float,
    q_occupancy: float,
    charge: float | None,
    minutes: float,
) -> float:
    return model.predict(
        T,
        T_out,
        0.0,
        minutes,
        q_solar=q_solar,
        q_residual=q_residual,
        q_occupancy=q_occupancy,
        q_rebound=None if charge is None else mean_rebound(charge, 0.0, minutes),
    )


def _continuation_power(
    optimizer: MPCOptimizer,
    T: float,
    T_out: float,
    q_solar: float,
    q_residual: float,
    q_occupancy: float,
    charge: float | None,
    mode: str,
    target: float,
) -> float:
    return gentle_power(
        optimizer,
        mode,
        T,
        T_out,
        target,
        q_solar=q_solar,
        q_residual=q_residual,
        q_occupancy=q_occupancy,
        rebound_charge=charge,
    )


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
    q_occupancy: float = 0.0,
    previous_mode: str = MODE_IDLE,
    mode_elapsed_minutes: float | None = None,
    q_rebound: float | None = None,
    run_system: str | None = None,
    outdoor_known: bool = True,
) -> list[float]:
    """Rolling-horizon MPC simulation matching the real controller.

    Every 5-min step runs the optimizer over the controller's horizon and then the
    controller's own rules (``decide_mpc_action``: hard ceiling, guard, start
    hysteresis, min-run continuation at gentle power, drift pre-heat only for slow
    heat). ``previous_mode``/``mode_elapsed_minutes`` seed the run in progress, so a
    room inside the hysteresis band keeps heating like the real one. ``outdoor_known=False``
    (no reading, no forecast): the series is the placeholder and gates nothing, as in the controller.
    """
    ocm, ohm = outdoor_gate_limits(
        outdoor_known,
        settings.get("outdoor_cooling_min", DEFAULT_OUTDOOR_COOLING_MIN),
        settings.get("outdoor_heating_max", DEFAULT_OUTDOOR_HEATING_MAX),
    )
    override_active = is_override_active(room_config)
    cw = settings.get("comfort_weight", 70)
    w_comfort = max(1.0, cw / 10.0)
    w_energy = max(1.0, (100 - cw) / 10.0)
    approach_rate = min(1.0, APPROACH_RATE_MIN + (1.0 - APPROACH_RATE_MIN) * cw / DEFAULT_COMFORT_WEIGHT)
    valve_modulating = is_valve_modulating(
        room_config.get("devices", []), acs_can_heat, bool(room_config.get("temperature_sensor"))
    )

    rules = heating_system_type if run_system is None else run_system
    min_run = get_min_run_blocks(rules, PLAN_DT_MINUTES)
    cool_min_run = get_min_run_blocks("", PLAN_DT_MINUTES)
    slow_heat = is_slow_heat(min_run)
    start_penalty = slow_start_penalty(min_run, PLAN_DT_MINUTES)
    heat_hysteresis = heat_start_hysteresis(acs_can_heat, bool(get_trv_eids(room_config.get("devices", []))))
    block_seconds = PLAN_DT_MINUTES * 60

    T = current_temp
    prev_action = previous_mode
    # Seconds the current run has been on at the start of the step (None = idle)
    run_seconds: float | None = (
        mode_elapsed_minutes * 60 if previous_mode != MODE_IDLE and mode_elapsed_minutes is not None else None
    )
    # Track residual heat through simulated mode transitions
    sim_residual_elapsed = 0.0  # minutes since simulated heating stopped
    sim_heating_blocks = 0  # blocks of simulated heating for charge fraction
    sim_was_heating = False
    # Seed with real residual state
    current_q_residual = q_residual
    charge = q_rebound
    pred_temps: list[float] = []

    for i in range(len(target_forecast)):
        tgt = target_forecast[i]["target_temp"]
        h_tgt = target_forecast[i].get("heat_target", tgt)
        c_tgt = target_forecast[i].get("cool_target", tgt)
        qs = solar_series[i] if solar_series and i < len(solar_series) else 0.0
        T_out = outdoor_series[i]

        # Force idle when both targets are None (devices turned off)
        if h_tgt is None and c_tgt is None:
            action = MODE_IDLE
            pf = 0.0
        else:
            can_heat, can_cool = get_can_heat_cool(
                room_config, T_out, ocm, ohm, acs_can_heat=acs_can_heat, override_active=override_active
            )
            horizon = compute_horizon_blocks(model, T, h_tgt if h_tgt is not None else c_tgt)
            window = target_forecast[i : i + horizon]
            filled = [
                fill_missing_targets(
                    tf.get("heat_target", tf["target_temp"]),
                    tf.get("cool_target", tf["target_temp"]),
                    T,
                )
                for tf in window
            ]
            heat_series = [h for h, _ in filled]
            cool_series = [c for _, c in filled]
            remaining_outdoor = outdoor_series[i : i + len(window)]
            remaining_solar = solar_series[i : i + len(window)] if solar_series else None
            # Build residual series for remaining blocks
            remaining_residual = None
            if heating_system_type and current_q_residual > 0:
                remaining_residual = build_residual_series(
                    sim_residual_elapsed,
                    heating_system_type,
                    len(remaining_outdoor),
                    PLAN_DT_MINUTES,
                    last_power_fraction,
                    sim_heating_blocks * PLAN_DT_MINUTES if sim_was_heating else heating_duration_minutes,
                )
            optimizer = MPCOptimizer(
                model=model,
                can_heat=can_heat,
                can_cool=can_cool,
                w_comfort=w_comfort,
                w_energy=w_energy,
                outdoor_cooling_min=ocm,
                outdoor_heating_max=ohm,
                min_run_blocks=min_run,
                cool_min_run_blocks=cool_min_run,
                override_active=override_active,
                heating_system_type=rules,
                approach_rate=approach_rate,
                start_penalty=start_penalty,
                fast_heater_shares_model=acs_can_heat,
                preheat_max_blocks=preheat_max_blocks(cw, PLAN_DT_MINUTES),
            )
            plan = optimizer.optimize(
                T_room=T,
                T_outdoor_series=remaining_outdoor,
                heat_target_series=heat_series,
                cool_target_series=cool_series,
                dt_minutes=PLAN_DT_MINUTES,
                solar_series=remaining_solar,
                residual_series=remaining_residual,
                occupancy_series=[q_occupancy] * len(remaining_outdoor),
                rebound_charge=charge,
                initial_mode=prev_action,
            )
            in_run = run_seconds is not None
            action, pf = decide_mpc_action(
                plan.get_current_action(),
                plan.get_current_power_fraction(),
                T,
                heat_series,
                cool_series,
                guard_blocks=max(SAFETY_GUARD_MIN_BLOCKS, min_run, plan.lookahead_blocks, plan.preheat_blocks + 1),
                slow_heat=slow_heat,
                previous_mode=prev_action,
                heat_in_min_run=in_run
                and prev_action == MODE_HEATING
                and cast(float, run_seconds) < min_run * block_seconds,
                cool_in_min_run=in_run
                and prev_action == MODE_COOLING
                and cast(float, run_seconds) < cool_min_run * block_seconds,
                can_heat=can_heat,
                can_cool=can_cool,
                heat_hysteresis=heat_hysteresis,
                idle_drift=partial(_idle_drift, model, T, T_out, qs, current_q_residual, q_occupancy, charge),
                continuation_power=partial(
                    _continuation_power, optimizer, T, T_out, qs, current_q_residual, q_occupancy, charge
                ),
                valve_demand=(
                    partial(valve_demand, model, T, T_out, q_solar=qs, q_occupancy=q_occupancy)
                    if valve_modulating
                    else None
                ),
            )
        if action == MODE_HEATING:
            Q = pf * model.Q_heat
        elif action == MODE_COOLING:
            Q = -(pf * model.Q_cool)
        else:
            Q = 0.0
        T_new = model.predict(
            T,
            T_out,
            Q,
            PLAN_DT_MINUTES,
            q_solar=qs,
            q_residual=current_q_residual if Q == 0.0 else 0.0,
            q_occupancy=q_occupancy,
            q_rebound=None if charge is None or Q != 0.0 else mean_rebound(charge, 0.0, PLAN_DT_MINUTES),
        )
        if charge is not None:
            charge = advance_rebound(charge, 0.0, PLAN_DT_MINUTES)
        T = max(5.0, min(40.0, T_new))

        # Update simulated residual tracking
        if action == MODE_HEATING:
            sim_heating_blocks += 1
            sim_was_heating = True
            sim_residual_elapsed = 0.0
            current_q_residual = 0.0
        else:
            sim_residual_elapsed += PLAN_DT_MINUTES
            if heating_system_type and sim_was_heating:
                current_q_residual = compute_residual_heat(
                    sim_residual_elapsed,
                    heating_system_type,
                    last_power_fraction,
                    sim_heating_blocks * PLAN_DT_MINUTES,
                )

        if action == MODE_IDLE:
            run_seconds = None
        elif action != prev_action or run_seconds is None:
            run_seconds = block_seconds
        else:
            run_seconds += block_seconds
        prev_action = action

        pred_temps.append(round(T, 2))

    return pred_temps


def _past_ceiling(mode: str, T: float, heat: float | None, cool: float | None, capped: bool) -> bool:
    if not capped:
        return False
    if mode == MODE_HEATING:
        return heat is not None and T >= heat + HARD_OVERSHOOT_CEILING
    return mode == MODE_COOLING and cool is not None and T <= cool - HARD_OVERSHOOT_CEILING


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
    q_occupancy: float = 0.0,
    previous_mode: str = MODE_IDLE,
    mode_elapsed_minutes: float | None = None,
    q_rebound: float | None = None,
    run_system: str | None = None,
    capped: bool = True,
) -> list[float]:
    """Bang-bang fallback simulation with mode stickiness + idle rate cap.

    ``capped``: the learning-phase min run stops at the hard ceiling; Simple mode
    (``control_mode`` bangbang) keeps the plain rule.
    """
    observed_idle_rate = compute_observed_idle_rate(all_points)
    has_heat = bool(get_trv_eids(room_config.get("devices", []))) or acs_can_heat
    has_cool = bool(get_ac_eids(room_config.get("devices", [])))

    rules = heating_system_type if run_system is None else run_system
    min_run = get_min_run_blocks(rules, PLAN_DT_MINUTES)
    # Cooling always runs on an AC, also in a UFH room
    cool_min_run = get_min_run_blocks("", PLAN_DT_MINUTES)

    T = current_temp
    sim_mode = previous_mode
    # A run without a known start counts as past its min run, like the controller's
    blocks_in_mode = int(mode_elapsed_minutes // PLAN_DT_MINUTES) if mode_elapsed_minutes is not None else min_run
    # Track residual heat through simulated mode transitions
    sim_residual_elapsed = 0.0
    sim_heating_blocks = 0
    sim_was_heating = False
    current_q_residual = q_residual
    charge = q_rebound
    pred_temps: list[float] = []

    for i, tf in enumerate(target_forecast):
        tgt = tf["target_temp"]
        h_tgt = tf.get("heat_target", tgt)
        c_tgt = tf.get("cool_target", tgt)
        if h_tgt is None and c_tgt is None:
            # Force idle when both targets are None (devices turned off)
            sim_mode = MODE_IDLE
            blocks_in_mode = 0
        elif (
            sim_mode != MODE_IDLE
            and blocks_in_mode < (min_run if sim_mode == MODE_HEATING else cool_min_run)
            and not _past_ceiling(sim_mode, T, h_tgt, c_tgt, capped)
        ):
            pass  # honour minimum run time, up to the hard ceiling like the controller
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
            T,
            outdoor_series[i],
            Q,
            5.0,
            q_solar=qs,
            q_residual=current_q_residual if Q == 0.0 else 0.0,
            q_occupancy=q_occupancy,
            q_rebound=None if charge is None or Q != 0.0 else mean_rebound(charge, 0.0, 5.0),
        )
        if charge is not None:
            charge = advance_rebound(charge, 0.0, 5.0)
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
                current_q_residual = compute_residual_heat(
                    sim_residual_elapsed,
                    heating_system_type,
                    last_power_fraction,
                    sim_heating_blocks * 5.0,
                )

        pred_temps.append(round(T, 2))

    return pred_temps
