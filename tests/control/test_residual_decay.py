"""Learned afterglow decay time (radiators) and the pre-heat that uses it."""

from __future__ import annotations

import math

import pytest

from custom_components.roommind.const import (
    MODE_HEATING,
    MODE_IDLE,
    RESIDUAL_LEARN_MIN_MINUTES,
    RESIDUAL_LEARN_WINDOW_MINUTES,
    RESIDUAL_SCALE_MAX,
    RESIDUAL_TAU_GRID,
    RESIDUAL_TAU_MAX,
    RESIDUAL_TAU_MIN,
)
from custom_components.roommind.control.mpc_optimizer import LOOKAHEAD_BASE_BLOCKS, MPCOptimizer
from custom_components.roommind.control.residual_heat import compute_residual_heat, residual_tau
from custom_components.roommind.control.thermal_model import RCModel, RoomModelManager, ThermalEKF
from custom_components.roommind.managers.residual_heat_tracker import ResidualHeatLearner

ROOM = RCModel(C=1.0, U=0.1, Q_heat=4.0, Q_cool=0.0)
DT = 0.5  # coordinator cycle, minutes
# A real bedroom's learned model (its afterglow fitted a 30-40 min decay)
BEDROOM = RCModel(C=1.0, U=0.005, Q_heat=1.935, Q_cool=4.0)


def _replay(
    *,
    tau: float,
    scale: float,
    tau_minutes: float | None = None,
    run_minutes: float = 60.0,
    restart_at: float | None = None,
) -> tuple[ResidualHeatLearner, float | None]:
    """A room cooling after a run, warmed by an afterglow of decay *tau* and *scale*."""
    learner = ResidualHeatLearner()
    T, elapsed, sample = 21.0, DT, None
    while elapsed <= RESIDUAL_LEARN_WINDOW_MINUTES + 1e-9:
        mode = MODE_HEATING if restart_at is not None and elapsed >= restart_at else MODE_IDLE
        if mode == MODE_IDLE:
            q = compute_residual_heat(elapsed - DT / 2, "radiator", 1.0, run_minutes, scale, tau)
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
            disturbed=False,
            tau_minutes=tau_minutes,
        )
        if sample is not None or mode == MODE_HEATING:
            break
        elapsed += DT
    return learner, sample


# ---------------------------------------------------------------------------
# compute_residual_heat with a decay time
# ---------------------------------------------------------------------------


def test_decay_time_spreads_the_same_start_over_longer():
    fast = compute_residual_heat(20.0, "radiator", 1.0, 60.0, 1.0)
    slow = compute_residual_heat(20.0, "radiator", 1.0, 60.0, 1.0, 40.0)
    assert slow > fast
    # Same start: the decay time changes the shape, the scale sets the size
    assert compute_residual_heat(0.0, "radiator", 1.0, 60.0, 1.0, 40.0) == pytest.approx(
        compute_residual_heat(0.0, "radiator", 1.0, 60.0, 1.0)
    )
    # None keeps the profile
    assert compute_residual_heat(20.0, "radiator", 1.0, 60.0, 1.0, None) == fast


def test_residual_tau_falls_back_to_the_profile():
    assert residual_tau("radiator") == 10.0
    assert residual_tau("radiator", 35.0) == 35.0
    assert residual_tau("") == 0.0


# ---------------------------------------------------------------------------
# ResidualHeatLearner: fitting the decay time
# ---------------------------------------------------------------------------


def _neighbours(tau: float) -> set[float]:
    idx = RESIDUAL_TAU_GRID.index(tau)
    return set(RESIDUAL_TAU_GRID[max(0, idx - 1) : idx + 2])


@pytest.mark.parametrize(("tau", "scale"), [(10.0, 3.0), (30.0, 1.0), (40.0, 0.8)])
def test_learner_fits_the_decay_time(tau, scale):
    learner, sample = _replay(tau=tau, scale=scale)
    assert sample is not None
    assert learner.take_tau_sample("r") in _neighbours(tau)
    # Handed over once
    assert learner.take_tau_sample("r") is None


def test_scale_is_measured_against_the_rooms_decay_time():
    """Against its own decay time a slow afterglow measures its true scale."""
    _, own = _replay(tau=40.0, scale=1.0, tau_minutes=40.0)
    assert own == pytest.approx(1.0, rel=0.1)
    # Against the profile's 10 min the same heat reads as a larger scale
    _, profile = _replay(tau=40.0, scale=1.0)
    assert profile is not None and profile > 2.0


def test_no_decay_time_from_a_small_rise():
    learner, _ = _replay(tau=10.0, scale=0.15)
    assert learner.take_tau_sample("r") is None


def test_no_decay_time_from_a_cut_window():
    """A run restarting before the window ends still gives a scale, not a shape."""
    learner, sample = _replay(tau=30.0, scale=1.0, restart_at=RESIDUAL_LEARN_MIN_MINUTES + 10)
    assert sample is not None
    assert learner.take_tau_sample("r") is None


def test_no_decay_time_without_a_scale_sample():
    """A short run's rise is mostly not its own heat: no scale, so no shape either."""
    learner, sample = _replay(tau=30.0, scale=1.0, run_minutes=1.0)
    assert sample is None
    assert learner.take_tau_sample("r") is None


def test_tau_samples_are_dropped_with_the_room():
    learner, _ = _replay(tau=30.0, scale=1.0)
    learner.remove_room("r")
    assert learner.take_tau_sample("r") is None
    learner, _ = _replay(tau=30.0, scale=1.0)
    learner.clear_all()
    assert learner.take_tau_sample("r") is None


# ---------------------------------------------------------------------------
# ThermalEKF: learned decay time
# ---------------------------------------------------------------------------


def test_decay_time_is_weighed_against_the_profile_in_log_space():
    ekf = ThermalEKF()
    assert ekf.residual_tau is None
    ekf.update_residual_tau(40.0, 10.0)
    assert ekf.residual_tau == pytest.approx(10.0 * 4.0 ** (1 / 3))


def test_new_decay_time_keeps_the_learned_total_heat():
    ekf = ThermalEKF()
    for _ in range(3):
        ekf.update_residual_scale(5.0)
    total = ekf.residual_scale * 10.0
    ekf.update_residual_tau(40.0, 10.0)
    assert ekf.residual_scale * ekf.residual_tau == pytest.approx(total)
    ekf.update_residual_tau(40.0, 10.0)
    assert ekf.residual_scale * ekf.residual_tau == pytest.approx(total)


def test_decay_time_converges_and_is_clamped():
    ekf = ThermalEKF()
    for _ in range(60):
        ekf.update_residual_tau(35.0, 10.0)
    assert ekf.residual_tau == pytest.approx(35.0, rel=0.01)
    ekf.update_residual_tau(1000.0, 10.0)
    assert ekf.residual_tau <= RESIDUAL_TAU_MAX
    other = ThermalEKF()
    other.update_residual_tau(0.1, 10.0)
    assert other.residual_tau >= RESIDUAL_TAU_MIN
    # Nonsense is ignored
    other.update_residual_tau(float("nan"), 10.0)
    other.update_residual_tau(20.0, 0.0)
    assert other._residual_tau_n == 1


def test_rescaled_scale_stays_within_its_bounds():
    ekf = ThermalEKF()
    for _ in range(40):
        ekf.update_residual_scale(RESIDUAL_SCALE_MAX)
    ekf.update_residual_tau(RESIDUAL_TAU_MIN, 10.0)
    assert ekf.residual_scale <= RESIDUAL_SCALE_MAX


def test_decay_time_survives_persistence_and_old_data_defaults():
    mgr = RoomModelManager()
    mgr.update_residual_tau("bed", 40.0, 10.0)
    learned = mgr.get_residual_tau("bed")
    restored = RoomModelManager.from_dict(mgr.to_dict())
    assert restored.get_residual_tau("bed") == pytest.approx(learned)
    assert restored.get_residual_tau("unknown") is None
    old = mgr.to_dict()["bed"]
    del old["residual_tau"], old["residual_tau_n"]
    assert ThermalEKF.from_dict(old).residual_tau is None


# ---------------------------------------------------------------------------
# Optimizer: lookahead and pre-heat with a slow afterglow
# ---------------------------------------------------------------------------

SLOW = {"residual_tau": 35.0, "residual_scale": 150 / 35}
# Eco until the 20 °C block 40 min ahead (8 blocks), then 30 min of comfort
MORNING = [18.5] * 8 + [20.0] * 6 + [12.0] * 16


def _optimizer(system: str = "radiator", **kwargs) -> MPCOptimizer:
    return MPCOptimizer(BEDROOM, can_cool=False, heating_system_type=system, min_run_blocks=2, **kwargs)


def _run(opt: MPCOptimizer, targets: list[float], T: float = 19.3, **kwargs):
    return opt.optimize(
        T_room=T,
        T_outdoor_series=[6.4] * len(targets),
        heat_target_series=targets,
        cool_target_series=[max(t, T) for t in targets],
        dt_minutes=5,
        **kwargs,
    )


def test_radiator_lookahead_follows_the_learned_decay_time():
    opt = _optimizer()
    _run(opt, [20.0] * 30)
    assert opt._lookahead_blocks == LOOKAHEAD_BASE_BLOCKS  # profile's 10 min: unchanged
    opt = _optimizer(**SLOW)
    _run(opt, [20.0] * 30)
    assert opt._lookahead_blocks == 2 + math.ceil(2.0 * 35.0 / 5)


def test_long_radiator_lookahead_keeps_the_learned_afterglow():
    """A long lookahead must not switch radiators to the underfloor synthesis (scale 1, no run)."""
    plan = _run(_optimizer(**SLOW), [20.0] * 30, T=19.9, initial_mode=MODE_HEATING, heat_run=(30.0, 1.0))
    assert plan.actions[0] == MODE_IDLE


def test_slow_afterglow_preheats_with_a_short_early_run():
    """Shortest run, started as late as it still reaches the block: least heat after it."""
    plan = _run(_optimizer(**SLOW), MORNING)
    heated = [i for i, a in enumerate(plan.actions) if a == MODE_HEATING]
    assert heated, "pre-heats"
    assert len(heated) <= 3
    assert heated[0] < 8
    # The block is held on the stored heat
    assert min(plan.temperatures[9:15]) >= 20.0 - 0.15


def test_slow_afterglow_waits_while_a_later_short_run_still_makes_it():
    opt = _optimizer(**SLOW)
    assert opt._preheat_deadline(0, 19.3, [6.4] * 30, MORNING, 5.0, q_solar=[], q_occupancy=[]) == 0


def test_little_stored_heat_falls_back_to_heating_into_the_block():
    """With the profile's small afterglow a short run cannot hold the block: heat as before."""
    plan = _run(_optimizer(), MORNING)
    assert plan.actions[:14].count(MODE_HEATING) > 3


@pytest.mark.parametrize("system", ["", "underfloor"])
def test_short_run_rule_is_radiator_only(system):
    assert not _optimizer(system, **SLOW)._radiator


def test_a_later_block_does_not_block_the_short_preheat():
    """One pre-heat run is not meant to hold tonight's block too: the morning still gets a short run."""
    with_evening = MORNING[:20] + [20.0] * 6 + [12.0] * 10
    plan = _run(_optimizer(**SLOW), with_evening)
    heated = [i for i, a in enumerate(plan.actions[:14]) if a == MODE_HEATING]
    assert 0 < len(heated) <= 3


def test_short_run_check_is_skipped_for_a_far_block():
    """A block beyond the reach of a short run's stored heat goes straight to the regular check."""
    far = [18.5] * 60 + [20.0] * 6 + [12.0] * 10
    opt = _optimizer(**SLOW)
    _run(opt, [20.0] * 5)  # sizes the lookahead
    calls = []
    original = opt._short_run_reaches
    opt._short_run_reaches = lambda *a, **k: calls.append(a) or original(*a, **k)
    opt._preheat_deadline(0, 19.3, [6.4] * len(far), far, 5.0, q_solar=[], q_occupancy=[])
    assert calls == []


def test_heavy_radiators_get_a_single_block_min_run():
    """A room that learned a large afterglow (real-house fit: scale ~9, tau ~23 min) heats in
    5-min runs: the stored heat of a 10-min run alone carried it ~0.9 K past its target."""
    from custom_components.roommind.control.residual_heat import get_min_run_blocks, heat_min_run_blocks

    base = get_min_run_blocks("radiator", 5.0)
    assert base == 2
    assert heat_min_run_blocks("radiator", 5.0, q_heat=1.95, scale=8.75, tau_minutes=22.9) == 1


def test_light_radiators_keep_the_regular_min_run():
    from custom_components.roommind.control.residual_heat import heat_min_run_blocks

    assert heat_min_run_blocks("radiator", 5.0, q_heat=3.0) == 2  # the profile: ~0.07 K
    assert heat_min_run_blocks("radiator", 5.0, q_heat=0.0, scale=10.0) == 2
    assert heat_min_run_blocks("underfloor", 5.0, q_heat=3.0, scale=10.0) == 6
    assert heat_min_run_blocks("", 5.0, q_heat=3.0, scale=10.0) == 2


def test_controller_min_run_follows_the_learned_afterglow():
    import time
    from unittest.mock import MagicMock

    from custom_components.roommind.control.mpc_controller import MPCController

    from .conftest import build_hass, make_room

    manager = MagicMock()
    manager.get_model.return_value = BEDROOM
    room = make_room(heating_system_type="radiator")

    def ctrl(scale):
        c = MPCController(
            build_hass(),
            room,
            model_manager=manager,
            outdoor_temp=0.0,
            settings={},
            has_external_sensor=True,
            heating_system_type="radiator",
            residual_scale=scale,
            residual_tau=30.0,
        )
        c.previous_mode = MODE_HEATING
        c._mode_on_since = time.time() - 6 * 60
        return c

    heavy, light = ctrl(9.0), ctrl(1.0)
    assert heavy._heat_min_run("radiator") == 1
    assert light._heat_min_run("radiator") == 2
    assert not heavy._within_min_run(MODE_HEATING)
    assert light._within_min_run(MODE_HEATING)


def test_a_long_afterglow_lookahead_does_not_pre_heat_past_the_switch():
    """Pre-heat switched off (#478): the radiator's long lookahead must not start a run
    for a target two hours away, only the greedy 30 min may see it."""
    targets = [15.0] * 24 + [21.0] * 24
    for tau in (10.0, 40.0, 60.0):
        opt = MPCOptimizer(
            BEDROOM,
            can_cool=False,
            heating_system_type="radiator",
            min_run_blocks=2,
            residual_scale=5.0,
            residual_tau=tau,
            preheat_max_blocks=0,
        )
        plan = _run(opt, targets, T=17.5)
        # the greedy 30 min: the run starts at most 6 blocks before the rise (block 24)
        assert plan.actions.index(MODE_HEATING) >= 24 - LOOKAHEAD_BASE_BLOCKS, tau


def test_a_radiator_room_with_an_ac_keeps_the_base_lookahead():
    opt = MPCOptimizer(BEDROOM, can_cool=True, heating_system_type="radiator", min_run_blocks=2, residual_tau=60.0)
    _run(opt, [20.0] * 48)
    assert opt._lookahead_blocks == LOOKAHEAD_BASE_BLOCKS


def test_a_heat_capable_ac_keeps_the_regular_min_run():
    from custom_components.roommind.control.residual_heat import heat_min_run_blocks

    assert heat_min_run_blocks("radiator", 5.0, q_heat=1.95, scale=8.75, tau_minutes=22.9, fast_heater=True) == 2


def test_a_radiator_run_is_not_paused_for_a_block():
    """The stop hypothesis gets the whole run's afterglow, so the plan stopped for one block
    and heated again right after: two commands and a restart for nothing (sim, a radiator
    that barely holds its target)."""
    model = RCModel(C=1.0, U=0.0272, Q_heat=1.094, Q_cool=4.0, Q_solar=0.317, Q_occupancy=0.3)
    opt = MPCOptimizer(
        model,
        can_cool=False,
        heating_system_type="radiator",
        min_run_blocks=2,
        residual_scale=6.66,
        w_comfort=7.0,
        w_energy=3.0,
    )
    n = 36
    # cheap-price target for two more blocks, then the schedule again
    heat = [20.0] * 2 + [19.0] * (n - 2)
    plan = opt.optimize(19.3, [-1.0] * n, heat, [24.0] * n, 5.0, initial_mode=MODE_HEATING, heat_run=(13.0, 1.0))
    assert plan.actions[0] == MODE_HEATING
    assert plan.get_current_power_fraction() > 0
