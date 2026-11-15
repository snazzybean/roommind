"""AfterglowReading: planning from the stopping plan while the sensor lags a radiator's afterglow."""

from __future__ import annotations

import math
from unittest.mock import patch

import pytest

from custom_components.roommind.const import MODE_HEATING, MODE_IDLE
from custom_components.roommind.control.mpc_controller import (
    SAFETY_GUARD_MIN_BLOCKS,
    decide_mpc_action,
    gentle_power,
    heat_start_hysteresis,
)
from custom_components.roommind.control.mpc_optimizer import MPCOptimizer, preheat_max_blocks
from custom_components.roommind.control.residual_heat import compute_residual_heat, heat_min_run_blocks
from custom_components.roommind.control.thermal_model import RCModel
from custom_components.roommind.managers.residual_heat_tracker import AfterglowReading

CLOCK = "custom_components.roommind.managers.residual_heat_tracker.time.time"
# Stopping plan: 21.5 now, then +0.2 K per 5-min block
RISING = [21.5, 21.7, 21.9, 22.1, 22.2]


def _stopped(at: float = 1000.0) -> AfterglowReading:
    reading = AfterglowReading()
    reading.observe("wz", 21.3)
    reading.observe("wz", 21.5)  # the sensor moves in 0.2 K steps
    with patch(CLOCK, return_value=at):
        reading.note_stop("wz", 21.5, RISING, 5.0)
    return reading


def test_plans_from_the_stopping_plan_at_most_a_step_above_the_reading():
    reading = _stopped()
    with patch(CLOCK, return_value=1000.0 + 150):  # 2.5 min: plan expects 21.6
        assert reading.estimate("wz", 21.5) == pytest.approx(21.6)
    with patch(CLOCK, return_value=1000.0 + 900):  # 15 min: plan expects 22.1, capped at a step
        assert reading.estimate("wz", 21.5) == pytest.approx(21.7)
        # A newer reading moves the window along
        assert reading.estimate("wz", 21.9) == pytest.approx(22.1)


def test_never_below_the_reading():
    reading = _stopped()
    with patch(CLOCK, return_value=1000.0 + 300):
        assert reading.estimate("wz", 22.0) == 22.0


def test_a_reading_below_the_stop_ends_it():
    """The stored heat was smaller than planned: the reading leads from then on."""
    reading = _stopped()
    with patch(CLOCK, return_value=1000.0 + 300):
        assert reading.estimate("wz", 21.3) == 21.3
        assert reading.estimate("wz", 21.5) == 21.5


def test_ends_after_the_afterglow_window():
    reading = _stopped()
    with patch(CLOCK, return_value=1000.0 + 61 * 60):
        assert reading.estimate("wz", 21.5) == 21.5


def test_no_step_seen_no_estimate():
    reading = AfterglowReading()
    reading.observe("wz", 21.5)
    reading.note_stop("wz", 21.5, RISING, 5.0)
    assert reading.estimate("wz", 21.5) == 21.5


def test_step_is_capped():
    reading = AfterglowReading()
    reading.observe("wz", 20.0)
    reading.observe("wz", 22.0)  # a jump, not a reporting step
    with patch(CLOCK, return_value=1000.0):
        reading.note_stop("wz", 22.0, [22.0, 23.0, 24.0], 5.0)
    with patch(CLOCK, return_value=1000.0 + 600):
        assert reading.estimate("wz", 22.0) == pytest.approx(22.5)


def test_clear_and_remove_room():
    reading = _stopped()
    reading.clear("wz")
    with patch(CLOCK, return_value=1000.0 + 300):
        assert reading.estimate("wz", 21.5) == 21.5
    reading = _stopped()
    reading.remove_room("wz")
    with patch(CLOCK, return_value=1000.0 + 300):
        assert reading.estimate("wz", 21.5) == 21.5


# ---------------------------------------------------------------------------
# Closed loop: a short pre-heat with heavy radiators and a 0.2 K sensor
# ---------------------------------------------------------------------------

# A living room's learned model (2026-11-15): a 5-min run leaves ~0.6 K of stored heat
LIVING = RCModel(C=1.0, U=0.0085, Q_heat=3.135, Q_cool=0.0)
SCALE, TAU = 6.5, 20.2


def _morning(with_estimate: bool) -> list[tuple[float, str]]:
    """30-s cycles from 06:30, comfort 22 at 07:00 over eco 20; the room behaves like the model.

    Returns the mode changes as (minutes after 06:30, mode).
    """
    clock = [0.0]
    mr = heat_min_run_blocks("radiator", 5.0, q_heat=LIVING.Q_heat, scale=SCALE, tau_minutes=TAU)
    reading = AfterglowReading()
    true_t, mode, on, off, changes = 21.3, MODE_IDLE, None, None, []
    with patch(CLOCK, side_effect=lambda: clock[0]):
        for k in range(70):
            now = k * 30.0
            clock[0] = now
            if k:
                if mode == MODE_HEATING:
                    q, qr = LIVING.Q_heat, 0.0
                else:
                    q = 0.0
                    qr = (
                        compute_residual_heat((now - off) / 60, "radiator", 1.0, (off - on) / 60, SCALE, TAU)
                        if off
                        else 0.0
                    )
                true_t = LIVING.predict(true_t, 1.8, q, 0.5, q_residual=qr)
            sensed = math.floor(true_t / 0.2 + 1e-9) * 0.2
            reading.observe("wz", sensed)
            plan_t = reading.estimate("wz", sensed) if with_estimate and mode != MODE_HEATING else sensed
            heat = [20.0 if now + 300 * i < 1800 else 22.0 for i in range(144)]
            q_res = (
                compute_residual_heat((now - off) / 60, "radiator", 1.0, (off - on) / 60, SCALE, TAU) if off else 0.0
            )
            opt = MPCOptimizer(
                LIVING,
                can_cool=False,
                w_comfort=6.5,
                w_energy=3.5,
                min_run_blocks=mr,
                heating_system_type="radiator",
                approach_rate=0.2 + 0.8 * 65 / 70,
                preheat_max_blocks=preheat_max_blocks(65),
                residual_scale=SCALE,
                residual_tau=TAU,
            )
            plan = opt.optimize(
                T_room=plan_t,
                T_outdoor_series=[1.8] * 144,
                heat_target_series=heat,
                cool_target_series=[30.0] * 144,
                dt_minutes=5,
                residual_series=[q_res * math.exp(-i * 5 / TAU) for i in range(144)] if q_res else None,
                initial_mode=mode,
                heat_run=((now - on) / 60, 1.0) if mode == MODE_HEATING else None,
            )
            action, _ = decide_mpc_action(
                plan.get_current_action(),
                plan.get_current_power_fraction(),
                plan_t,
                heat,
                [30.0] * 144,
                guard_blocks=max(SAFETY_GUARD_MIN_BLOCKS, mr, plan.lookahead_blocks, plan.preheat_blocks + 1),
                slow_heat=False,
                previous_mode=mode,
                heat_in_min_run=mode == MODE_HEATING and now - on < mr * 300,
                cool_in_min_run=False,
                can_heat=True,
                can_cool=False,
                heat_hysteresis=heat_start_hysteresis(False, True),
                idle_drift=lambda _m, t0=plan_t: t0,
                continuation_power=lambda m, t, o=opt, t0=plan_t, q=q_res: gentle_power(
                    o, m, t0, 1.8, t, q_solar=0.0, q_residual=q, q_occupancy=0.0
                ),
            )
            if action == MODE_HEATING:
                reading.clear("wz")
                if mode != MODE_HEATING:
                    on, off = now, None
            elif mode == MODE_HEATING:
                off = now
                reading.note_stop("wz", sensed, plan.temperatures, 5.0)
            if action != mode:
                changes.append((now / 60, action))
            mode = action
    return changes


def test_a_sensor_step_behind_the_afterglow_no_longer_restarts_the_preheat():
    """Planned from the stale reading, the stored heat looked short and the run started again
    minutes after the stop; planned from where the stopping plan put the room, it runs once."""
    before = _morning(with_estimate=False)
    assert [m for _, m in before].count(MODE_HEATING) >= 2
    after = _morning(with_estimate=True)
    assert [m for _, m in after].count(MODE_HEATING) == 1
