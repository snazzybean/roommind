"""Learned residual heat and the early stop it allows (radiators overshooting after a run)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from custom_components.roommind.const import (
    MODE_COOLING,
    MODE_HEATING,
    MODE_IDLE,
    RESIDUAL_LEARN_MIN_MINUTES,
    RESIDUAL_LEARN_WINDOW_MINUTES,
    RESIDUAL_SCALE_MAX,
    TargetTemps,
)
from custom_components.roommind.control.mpc_controller import MPCController
from custom_components.roommind.control.mpc_optimizer import MPCOptimizer
from custom_components.roommind.control.residual_heat import build_residual_series, compute_residual_heat
from custom_components.roommind.control.thermal_model import RCModel, RoomModelManager, ThermalEKF
from custom_components.roommind.managers.residual_heat_tracker import ResidualHeatLearner, ResidualHeatTracker

from .conftest import build_hass, make_room

ROOM = RCModel(C=1.0, U=0.1, Q_heat=4.0, Q_cool=0.0)
DT = 0.5  # coordinator cycle, minutes

# ---------------------------------------------------------------------------
# residual_heat: scale
# ---------------------------------------------------------------------------


def test_scale_multiplies_the_profile():
    base = compute_residual_heat(5.0, "radiator", 1.0, 60.0)
    assert compute_residual_heat(5.0, "radiator", 1.0, 60.0, scale=2.5) == pytest.approx(2.5 * base)
    assert compute_residual_heat(5.0, "radiator", 1.0, 60.0, scale=0.0) == 0.0
    series = build_residual_series(0.0, "radiator", 3, 5.0, 1.0, 60.0, scale=2.0)
    assert series == pytest.approx([2.0 * q for q in build_residual_series(0.0, "radiator", 3, 5.0, 1.0, 60.0)])


# ---------------------------------------------------------------------------
# ThermalEKF: learned scale, persistence
# ---------------------------------------------------------------------------


def test_first_sample_replaces_default_then_smoothed():
    ekf = ThermalEKF()
    assert ekf.residual_scale == 1.0
    ekf.update_residual_scale(3.0)
    assert ekf.residual_scale == pytest.approx(3.0)
    ekf.update_residual_scale(1.0)
    assert 1.0 < ekf.residual_scale < 3.0


def test_samples_are_clamped_and_non_finite_ignored():
    ekf = ThermalEKF()
    ekf.update_residual_scale(float("nan"))
    assert ekf.residual_scale == 1.0
    ekf.update_residual_scale(100.0)
    assert ekf.residual_scale == RESIDUAL_SCALE_MAX
    ekf2 = ThermalEKF()
    ekf2.update_residual_scale(-4.0)
    assert ekf2.residual_scale == 0.0


def test_scale_survives_persistence_and_old_data_defaults():
    mgr = RoomModelManager()
    mgr.update_residual_scale("bath", 2.2)
    restored = RoomModelManager.from_dict(mgr.to_dict())
    assert restored.get_residual_scale("bath") == pytest.approx(2.2)
    assert restored.get_residual_scale("unknown") == 1.0
    old = mgr.to_dict()["bath"]
    del old["residual_scale"], old["residual_scale_n"]
    assert ThermalEKF.from_dict(old).residual_scale == 1.0


# ---------------------------------------------------------------------------
# ResidualHeatTracker: run state, stop kept for the learning window
# ---------------------------------------------------------------------------


def test_run_state_reports_the_run_in_progress():
    tracker = ResidualHeatTracker()
    with patch("custom_components.roommind.managers.residual_heat_tracker.time") as t:
        t.time.return_value = 1000.0
        tracker.update("r", MODE_HEATING, 0.6, MODE_IDLE)
        t.time.return_value = 1000.0 + 1800
        assert tracker.get_run_state("r", MODE_HEATING) == pytest.approx((30.0, 0.6))
        assert tracker.get_run_state("r", MODE_IDLE) is None
        assert tracker.minutes_since_stop("r") is None
        tracker.update("r", MODE_IDLE, 0.0, MODE_HEATING)
        assert tracker.last_run_minutes("r") == pytest.approx(30.0)
        assert tracker.last_run_power("r") == pytest.approx(0.6)
        assert tracker.get_q_residual("r", "radiator", MODE_IDLE, 2.0) == pytest.approx(
            compute_residual_heat(0.0, "radiator", 0.6, 30.0, 2.0)
        )


def test_stop_is_kept_for_the_learning_window():
    tracker = ResidualHeatTracker()
    with patch("custom_components.roommind.managers.residual_heat_tracker.time") as t:
        t.time.return_value = 0.0
        tracker.update("r", MODE_HEATING, 1.0, MODE_IDLE)
        t.time.return_value = 600.0
        tracker.update("r", MODE_IDLE, 0.0, MODE_HEATING)
        t.time.return_value = 600.0 + 20 * 60
        tracker.update("r", MODE_IDLE, 0.0, MODE_IDLE, q_residual=0.0)
        assert tracker.minutes_since_stop("r") == pytest.approx(20.0)
        t.time.return_value = 600.0 + RESIDUAL_LEARN_WINDOW_MINUTES * 60
        tracker.update("r", MODE_IDLE, 0.0, MODE_IDLE, q_residual=0.0)
        assert tracker.minutes_since_stop("r") is None


# ---------------------------------------------------------------------------
# ResidualHeatLearner
# ---------------------------------------------------------------------------


def _afterglow_run(
    learner: ResidualHeatLearner,
    *,
    true_scale: float,
    minutes: float = RESIDUAL_LEARN_WINDOW_MINUTES,
    run_minutes: float = 60.0,
    disturb_at: float | None = None,
    restart_at: float | None = None,
) -> float | None:
    """Replay a room cooling after a run, warmed by *true_scale* x the radiator profile."""
    T = 21.0
    sample = None
    elapsed = DT
    while elapsed <= minutes + 1e-9:
        mode = MODE_HEATING if restart_at is not None and elapsed >= restart_at else MODE_IDLE
        if mode == MODE_IDLE:
            q = compute_residual_heat(elapsed - DT / 2, "radiator", 1.0, run_minutes, true_scale)
            T = ROOM.predict(T, 5.0, 0.0, DT, q_residual=q)
        sample = learner.step(
            "r",
            model=ROOM,
            system_type="radiator",
            mode=mode,
            current_temp=T,
            T_outdoor=5.0,
            dt_minutes=DT,
            minutes_since_stop=elapsed,
            run_minutes=run_minutes,
            run_power=1.0,
            q_solar=0.0,
            q_occupancy=0.0,
            disturbed=disturb_at is not None and elapsed >= disturb_at,
        )
        if sample is not None or mode == MODE_HEATING:
            return sample
        elapsed += DT
    return sample


@pytest.mark.parametrize("true_scale", [0.5, 1.0, 3.0])
def test_learner_recovers_the_true_scale(true_scale):
    sample = _afterglow_run(ResidualHeatLearner(), true_scale=true_scale)
    # Not exact: the replayed afterglow drops to zero at RESIDUAL_HEAT_CUTOFF at another
    # time than the learner's scale-1 reference (a real radiator has no cutoff)
    assert sample == pytest.approx(true_scale, rel=0.1)


def test_disturbed_observation_gives_no_sample():
    learner = ResidualHeatLearner()
    assert _afterglow_run(learner, true_scale=2.0, disturb_at=10.0) is None
    assert learner._obs == {}


def test_restart_after_min_minutes_still_counts():
    sample = _afterglow_run(ResidualHeatLearner(), true_scale=2.0, restart_at=RESIDUAL_LEARN_MIN_MINUTES + 5)
    assert sample == pytest.approx(2.0, rel=0.1)


def test_restart_before_min_minutes_gives_no_sample():
    assert _afterglow_run(ResidualHeatLearner(), true_scale=2.0, restart_at=RESIDUAL_LEARN_MIN_MINUTES - 5) is None


def test_short_run_carries_no_signal():
    # A 1-minute run barely charges the radiator: the expected rise is below the noise floor
    assert _afterglow_run(ResidualHeatLearner(), true_scale=2.0, run_minutes=1.0) is None


def test_observation_starts_only_right_after_the_stop():
    learner = ResidualHeatLearner()
    kwargs = dict(
        model=ROOM,
        system_type="radiator",
        current_temp=21.0,
        T_outdoor=5.0,
        dt_minutes=DT,
        run_minutes=60.0,
        run_power=1.0,
        q_solar=0.0,
        q_occupancy=0.0,
        disturbed=False,
    )
    assert learner.step("r", mode=MODE_IDLE, minutes_since_stop=10.0, **kwargs) is None
    assert learner._obs == {}
    assert learner.step("r", mode=MODE_IDLE, minutes_since_stop=DT, **kwargs) is None
    assert "r" in learner._obs
    assert learner.step("r", mode=MODE_COOLING, minutes_since_stop=1.0, **kwargs) is None
    assert learner._obs == {}
    learner.step("r", mode=MODE_IDLE, minutes_since_stop=DT, **kwargs)
    learner.remove_room("r")
    assert learner._obs == {}
    learner.step("r", mode=MODE_IDLE, minutes_since_stop=DT, **kwargs)
    learner.clear_all()
    assert learner._obs == {}


# ---------------------------------------------------------------------------
# Optimizer / controller: stop early on the stored heat
# ---------------------------------------------------------------------------


def _plan(T: float, *, scale: float, heat_run: tuple[float, float] | None, outdoor: float = 15.0):
    opt = MPCOptimizer(ROOM, can_cool=False, heating_system_type="radiator", residual_scale=scale)
    return opt.optimize(
        T_room=T,
        T_outdoor_series=[outdoor] * 24,
        heat_target_series=[21.0] * 24,
        cool_target_series=[24.0] * 24,
        dt_minutes=5,
        initial_mode=MODE_HEATING,
        heat_run=heat_run,
    )


def test_run_that_can_coast_to_the_target_stops():
    """Just below the target with hot radiators: idle, the stored heat carries the room."""
    assert _plan(20.9, scale=3.0, heat_run=(40.0, 1.0)).actions[0] == MODE_IDLE
    # Without knowing the run, or with little stored heat, it keeps heating
    assert _plan(20.9, scale=3.0, heat_run=None).actions[0] == MODE_HEATING
    assert _plan(20.9, scale=1.0, heat_run=(40.0, 1.0)).actions[0] == MODE_HEATING


def test_stopped_run_keeps_warming_the_plan():
    """The idle blocks after a stop carry that run's afterglow: the room rises past the start."""
    plan = _plan(20.9, scale=3.0, heat_run=(40.0, 1.0))
    assert plan.temperatures[1] > 20.9


@pytest.mark.parametrize("system", ["", "underfloor"])
def test_only_radiator_rooms_use_the_run_and_the_scale(system):
    """Underfloor and untyped rooms plan exactly as without the run in progress and the scale."""

    def plan(**kwargs):
        opt = MPCOptimizer(ROOM, can_cool=False, heating_system_type=system, **kwargs)
        return opt.optimize(
            T_room=20.9,
            T_outdoor_series=[15.0] * 24,
            heat_target_series=[21.0] * 24,
            cool_target_series=[24.0] * 24,
            dt_minutes=5,
            initial_mode=MODE_HEATING,
            **({"heat_run": (40.0, 1.0)} if kwargs else {}),
        )

    new, old = plan(residual_scale=3.0), plan()
    assert (new.actions, new.temperatures, new.power_fractions) == (old.actions, old.temperatures, old.power_fractions)


def test_no_run_state_without_heating_system_type():
    opt = MPCOptimizer(ROOM, can_cool=False, heating_system_type="", residual_scale=3.0)
    plan = opt.optimize(
        T_room=20.9,
        T_outdoor_series=[15.0] * 24,
        heat_target_series=[21.0] * 24,
        cool_target_series=[24.0] * 24,
        dt_minutes=5,
        initial_mode=MODE_HEATING,
        heat_run=(40.0, 1.0),
    )
    assert plan.actions[0] == MODE_HEATING


def _controller(heat_run: tuple[float, float] | None, scale: float) -> MPCController:
    manager = RoomModelManager()
    manager.get_model = lambda _area: ROOM  # type: ignore[method-assign]
    ctrl = MPCController(
        build_hass(),
        make_room(heating_system_type="radiator"),
        model_manager=manager,
        outdoor_temp=15.0,
        settings={},
        previous_mode=MODE_HEATING,
        mode_on_since=None,
        has_external_sensor=True,
        heating_system_type="radiator",
        residual_scale=scale,
        heat_run=heat_run,
    )
    ctrl._build_solar_series = lambda n: [0.0] * n  # type: ignore[method-assign]
    return ctrl


def test_controller_stops_the_run_on_stored_heat():
    targets = TargetTemps(heat=21.0, cool=24.0)
    mode, pf = _controller((40.0, 1.0), 3.0)._evaluate_mpc(20.9, targets)
    assert (mode, pf) == (MODE_IDLE, 0.0)
    mode, _ = _controller(None, 3.0)._evaluate_mpc(20.9, targets)
    assert mode == MODE_HEATING


# ---------------------------------------------------------------------------
# A real radiator room (7-day HA history): short runs, ~1 K rise after the stop
# ---------------------------------------------------------------------------

# The room's learned RoomMind model and one of its stops: a 24.5-min run on a TRV with
# boosted setpoints, valve closed and boiler off at the stop, then the room sensor still rose
# from 20.1 to 20.7 °C. (minutes after the stop, reading) as the recorder stored them.
REAL_ROOM = RCModel(C=1.0, U=0.01696, Q_heat=2.064, Q_cool=4.0, Q_solar=0.0064)
REAL_READINGS = [(-0.1, 20.1), (6.87, 20.3), (16.05, 20.5), (27.63, 20.7)]


def _real_reading(minute: float) -> float:
    return [temp for start, temp in REAL_READINGS if start <= minute][-1]


def test_learner_finds_the_real_rooms_stored_heat():
    """The profile's radiator heat is ~10x too small for this room; the cap leaves room for it."""
    learner = ResidualHeatLearner()
    minute, sample = DT, None
    while sample is None and minute <= RESIDUAL_LEARN_WINDOW_MINUTES + 1e-9:
        sample = learner.step(
            "real",
            model=REAL_ROOM,
            system_type="radiator",
            mode=MODE_IDLE,
            current_temp=_real_reading(minute),
            T_outdoor=7.9 if minute < 10 else 7.7 if minute < 40 else 8.2,
            dt_minutes=DT,
            minutes_since_stop=minute,
            run_minutes=24.5,
            run_power=1.0,
            q_solar=0.0,
            q_occupancy=0.0,
            disturbed=False,
        )
        minute += DT
    assert sample is not None
    assert 9.0 < sample < RESIDUAL_SCALE_MAX


def test_real_room_stops_early_on_its_learned_scale():
    """With the learned scale a run stops ~0.8 K short and the stored heat carries it to the target."""

    def plan(scale: float):
        opt = MPCOptimizer(REAL_ROOM, can_cool=False, heating_system_type="radiator", residual_scale=scale)
        return opt.optimize(
            T_room=19.2,
            T_outdoor_series=[8.0] * 24,
            heat_target_series=[20.0] * 24,
            cool_target_series=[24.0] * 24,
            dt_minutes=5,
            initial_mode=MODE_HEATING,
            heat_run=(20.0, 1.0),
        )

    assert plan(1.0).actions[0] == MODE_HEATING
    learned = plan(11.0)
    assert learned.actions[0] == MODE_IDLE
    assert max(learned.temperatures[:13]) >= 20.0 - 0.1
