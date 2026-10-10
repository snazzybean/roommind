"""Tests for the MPC optimizer: MPCOptimizer, MPCPlan."""

from __future__ import annotations

import math

import pytest

from custom_components.roommind.const import MIN_POWER_FRACTION, MODE_COOLING, MODE_HEATING, MODE_IDLE
from custom_components.roommind.control.mpc_optimizer import MPCOptimizer, MPCPlan
from custom_components.roommind.control.thermal_model import RCModel


def test_optimizer_idle_at_target():
    """When at target with no heat loss, plan should be all idle."""
    model = RCModel(C=2.0, U=50.0, Q_heat=1000.0, Q_cool=1500.0)
    opt = MPCOptimizer(model)
    # Outdoor == room temp → no heat loss → idle is cheapest
    plan = opt.optimize(
        T_room=21.0,
        T_outdoor_series=[21.0] * 12,
        heat_target_series=[21.0] * 12,
        dt_minutes=5,
    )
    assert plan.actions[0] == "idle"


def test_optimizer_heats_when_cold():
    """When below target, plan should start heating."""
    model = RCModel(C=2.0, U=50.0, Q_heat=1000.0, Q_cool=1500.0)
    opt = MPCOptimizer(model)
    plan = opt.optimize(
        T_room=17.0,
        T_outdoor_series=[5.0] * 24,
        heat_target_series=[21.0] * 24,
        dt_minutes=5,
    )
    assert plan.actions[0] == "heating"


def test_optimizer_cools_when_hot():
    """When above target, plan should start cooling."""
    # Use moderate Q_cool so one block doesn't overshoot wildly
    model = RCModel(C=2.0, U=50.0, Q_heat=1000.0, Q_cool=200.0)
    opt = MPCOptimizer(model, can_heat=False, can_cool=True)
    plan = opt.optimize(
        T_room=27.0,
        T_outdoor_series=[30.0] * 24,
        heat_target_series=[23.0] * 24,
        dt_minutes=5,
    )
    assert plan.actions[0] == "cooling"


def test_optimizer_preheats():
    """Should start heating BEFORE target time to reach temp on time."""
    # Large thermal mass so pre-heating actually raises temperature that persists
    model = RCModel(C=200.0, U=50.0, Q_heat=1000.0, Q_cool=1500.0)
    opt = MPCOptimizer(model)
    # Target is eco (17°C) for first 6 blocks, then comfort (21°C)
    targets = [17.0] * 6 + [21.0] * 18
    plan = opt.optimize(
        T_room=17.0,
        T_outdoor_series=[17.0] * 24,
        heat_target_series=targets,
        dt_minutes=5,
    )
    # Should start heating before block 6 (pre-heating)
    first_heat = next(i for i, a in enumerate(plan.actions) if a == "heating")
    assert first_heat < 6  # starts before target changes


def test_optimizer_stops_near_target():
    """Should not overshoot far past target; proportional power keeps temp controlled."""
    # Realistic thermal mass: time constant = C/U = 200/50 = 4 hours
    model = RCModel(C=200.0, U=50.0, Q_heat=1000.0, Q_cool=1500.0)
    opt = MPCOptimizer(model)
    plan = opt.optimize(
        T_room=18.0,
        T_outdoor_series=[5.0] * 72,
        heat_target_series=[21.0] * 72,
        dt_minutes=5,
    )
    assert plan.actions[0] == "heating", "Should heat when below target"
    # With proportional control, power fraction decreases as temp approaches target
    # Final temperature should be near target, not wildly overshooting
    assert plan.temperatures[-1] < 22.0
    # Power fractions should decrease over time as room warms up
    assert plan.power_fractions[0] > plan.power_fractions[-1] or plan.actions[-1] == "idle"


def test_optimizer_min_run_time():
    """Should not create runs shorter than min_run_blocks."""
    model = RCModel(C=2.0, U=50.0, Q_heat=1000.0, Q_cool=1500.0)
    opt = MPCOptimizer(model, min_run_blocks=2)
    plan = opt.optimize(
        T_room=20.5,
        T_outdoor_series=[5.0] * 12,
        heat_target_series=[21.0] * 12,
        dt_minutes=5,
    )
    # Any heating run should be at least 2 blocks
    in_run = False
    run_length = 0
    for a in plan.actions:
        if a == "heating":
            run_length += 1
            in_run = True
        elif in_run:
            assert run_length >= 2
            run_length = 0
            in_run = False


def test_optimizer_outdoor_gating():
    """Cooling blocked when outdoor below threshold."""
    model = RCModel(C=2.0, U=50.0, Q_heat=1000.0, Q_cool=1500.0)
    opt = MPCOptimizer(model, can_heat=False, can_cool=True, outdoor_cooling_min=16.0)
    plan = opt.optimize(
        T_room=25.0,
        T_outdoor_series=[10.0] * 12,  # below 16°C
        heat_target_series=[22.0] * 12,
        dt_minutes=5,
    )
    assert all(a == "idle" for a in plan.actions)


def test_optimizer_outdoor_gating_bypassed_by_override():
    """Cooling allowed when outdoor below threshold but override active."""
    model = RCModel(C=1.0, U=0.1, Q_heat=5.0, Q_cool=5.0)
    opt = MPCOptimizer(model, can_heat=False, can_cool=True, outdoor_cooling_min=16.0, override_active=True)
    plan = opt.optimize(
        T_room=25.0,
        T_outdoor_series=[10.0] * 12,
        heat_target_series=[22.0] * 12,
        dt_minutes=5,
    )
    assert any(a == "cooling" for a in plan.actions)


def test_plan_get_current_action():
    """MPCPlan returns correct action for current time."""
    plan = MPCPlan(
        actions=["heating", "heating", "idle", "idle"],
        temperatures=[18.0, 19.0, 20.5, 21.0, 21.0],
        dt_minutes=5,
    )
    assert plan.get_current_action() == "heating"


def test_plan_empty():
    """Empty plan returns idle."""
    plan = MPCPlan(actions=[], temperatures=[20.0], dt_minutes=5)
    assert plan.get_current_action() == "idle"


# ---------------------------------------------------------------------------
# Proportional control tests
# ---------------------------------------------------------------------------


def test_compute_optimal_power_cold_room():
    """Cold room needs high power fraction."""
    model = RCModel(C=2.0, U=50.0, Q_heat=1000.0, Q_cool=1500.0)
    opt = MPCOptimizer(model)
    pf, mode = opt.compute_optimal_power(
        T_room=15.0,
        T_outdoor=5.0,
        target=21.0,
        dt_minutes=5.0,
    )
    assert mode == "heating"
    assert pf >= 0.5  # large error → high power


def test_compute_optimal_power_at_target():
    """At target with matching outdoor → near-zero or idle."""
    model = RCModel(C=2.0, U=50.0, Q_heat=1000.0, Q_cool=1500.0)
    opt = MPCOptimizer(model)
    pf, mode = opt.compute_optimal_power(
        T_room=21.0,
        T_outdoor=21.0,
        target=21.0,
        dt_minutes=5.0,
    )
    assert mode == "idle"
    assert pf == 0.0


def test_power_fractions_in_plan():
    """Optimize returns power_fractions list matching actions length."""
    model = RCModel(C=2.0, U=50.0, Q_heat=1000.0, Q_cool=1500.0)
    opt = MPCOptimizer(model)
    plan = opt.optimize(
        T_room=17.0,
        T_outdoor_series=[5.0] * 12,
        heat_target_series=[21.0] * 12,
        dt_minutes=5,
    )
    assert len(plan.power_fractions) == len(plan.actions)
    # Heating blocks should have positive power fractions
    for i, a in enumerate(plan.actions):
        if a == "heating":
            assert plan.power_fractions[i] > 0.0
        elif a == "idle":
            assert plan.power_fractions[i] == 0.0


def test_get_current_power_fraction_fallback():
    """Empty power_fractions → backward-compatible defaults."""
    plan_heat = MPCPlan(actions=["heating", "idle"], temperatures=[18.0, 19.0, 19.5], dt_minutes=5)
    assert plan_heat.get_current_power_fraction() == 1.0  # active → 1.0

    plan_idle = MPCPlan(actions=["idle"], temperatures=[21.0, 21.0], dt_minutes=5)
    assert plan_idle.get_current_power_fraction() == 0.0  # idle → 0.0

    plan_empty = MPCPlan(actions=[], temperatures=[21.0], dt_minutes=5)
    assert plan_empty.get_current_power_fraction() == 0.0  # no actions → 0.0


def test_power_fraction_clamped():
    """Power fraction should always be in [MIN_POWER_FRACTION, 1.0] when active."""
    from custom_components.roommind.const import MIN_POWER_FRACTION

    model = RCModel(C=2.0, U=50.0, Q_heat=1000.0, Q_cool=1500.0)
    opt = MPCOptimizer(model)
    plan = opt.optimize(
        T_room=17.0,
        T_outdoor_series=[5.0] * 12,
        heat_target_series=[21.0] * 12,
        dt_minutes=5,
    )
    for i, a in enumerate(plan.actions):
        pf = plan.power_fractions[i]
        if a != "idle":
            assert pf >= MIN_POWER_FRACTION
            assert pf <= 1.0


# ---------------------------------------------------------------------------
# Residual heat tests
# ---------------------------------------------------------------------------


def test_optimizer_residual_reduces_heating():
    """With residual heat, optimizer should heat less or stop sooner."""
    model = RCModel(C=2.0, U=50.0, Q_heat=1000.0, Q_cool=1500.0)
    opt = MPCOptimizer(model)
    n = 12
    # Without residual
    plan_no_res = opt.optimize(
        T_room=19.5,
        T_outdoor_series=[10.0] * n,
        heat_target_series=[21.0] * n,
        dt_minutes=5,
    )
    # With significant residual heat
    plan_res = opt.optimize(
        T_room=19.5,
        T_outdoor_series=[10.0] * n,
        heat_target_series=[21.0] * n,
        dt_minutes=5,
        residual_series=[0.5, 0.4, 0.3, 0.2, 0.15, 0.1, 0.05, 0.0, 0.0, 0.0, 0.0, 0.0],
    )
    # With residual, temperatures during idle blocks should be higher
    heating_blocks_no = sum(1 for a in plan_no_res.actions if a == "heating")
    heating_blocks_res = sum(1 for a in plan_res.actions if a == "heating")
    # Residual heat should reduce need for active heating
    assert heating_blocks_res <= heating_blocks_no


def test_compute_optimal_power_with_residual():
    """Residual heat in drift should reduce required heating power."""
    model = RCModel(C=2.0, U=50.0, Q_heat=1000.0, Q_cool=1500.0)
    opt = MPCOptimizer(model)
    pf_no_res, mode_no_res = opt.compute_optimal_power(
        19.5,
        10.0,
        21.0,
        5.0,
        q_residual=0.0,
    )
    pf_res, mode_res = opt.compute_optimal_power(
        19.5,
        10.0,
        21.0,
        5.0,
        q_residual=0.5,
    )
    # With residual, either lower power or idle
    if mode_res == "heating":
        assert pf_res <= pf_no_res
    else:
        assert mode_res == "idle"  # residual is enough


def test_optimizer_min_run_blocks_from_profile():
    """min_run_blocks is respected in the plan."""
    model = RCModel(C=2.0, U=50.0, Q_heat=1000.0, Q_cool=1500.0)
    opt = MPCOptimizer(model, min_run_blocks=6)  # underfloor-like
    plan = opt.optimize(
        T_room=17.0,
        T_outdoor_series=[5.0] * 12,
        heat_target_series=[21.0] * 12,
        dt_minutes=5,
    )
    # If heating starts, it should run for at least 6 blocks
    if plan.actions[0] == "heating":
        heating_count = 0
        for a in plan.actions:
            if a == "heating":
                heating_count += 1
            else:
                break
        assert heating_count >= 6


# ---------------------------------------------------------------------------
# Dead-band tests (split heat/cool targets)
# ---------------------------------------------------------------------------


def test_optimizer_deadband_idle():
    """Inside the dead band (between heat and cool targets) should be idle."""
    model = RCModel(C=2.0, U=50.0, Q_heat=1000.0, Q_cool=1500.0)
    opt = MPCOptimizer(model)
    plan = opt.optimize(
        T_room=22.5,
        T_outdoor_series=[22.5] * 12,
        heat_target_series=[21.0] * 12,
        cool_target_series=[24.0] * 12,
        dt_minutes=5,
    )
    assert plan.actions[0] == "idle"


def test_optimizer_heats_below_heat_target():
    """Below heat target with dead band should heat."""
    model = RCModel(C=2.0, U=50.0, Q_heat=1000.0, Q_cool=1500.0)
    opt = MPCOptimizer(model)
    plan = opt.optimize(
        T_room=19.0,
        T_outdoor_series=[5.0] * 12,
        heat_target_series=[21.0] * 12,
        cool_target_series=[24.0] * 12,
        dt_minutes=5,
    )
    assert plan.actions[0] == "heating"


def test_optimizer_cools_above_cool_target():
    """Above cool target with dead band should cool."""
    model = RCModel(C=2.0, U=50.0, Q_heat=1000.0, Q_cool=200.0)
    opt = MPCOptimizer(model, can_heat=False, can_cool=True)
    plan = opt.optimize(
        T_room=25.0,
        T_outdoor_series=[30.0] * 12,
        heat_target_series=[21.0] * 12,
        cool_target_series=[24.0] * 12,
        dt_minutes=5,
    )
    assert plan.actions[0] == "cooling"


def test_optimizer_inverted_targets_clamped():
    """Inverted heat > cool targets should be clamped to equal."""
    model = RCModel(C=2.0, U=50.0, Q_heat=1000.0, Q_cool=1500.0)
    opt = MPCOptimizer(model)
    # heat=25 > cool=21 is inverted; after clamping cool becomes 25
    # Room at 23 < 25 → should heat
    plan = opt.optimize(
        T_room=23.0,
        T_outdoor_series=[20.0] * 12,
        heat_target_series=[25.0] * 12,
        cool_target_series=[21.0] * 12,
        dt_minutes=5,
    )
    assert plan.actions[0] == "heating"


# ---------------------------------------------------------------------------
# Coverage: uncovered lines
# ---------------------------------------------------------------------------


def test_optimize_empty_series_returns_empty_plan():
    model = RCModel(C=2.0, U=50.0, Q_heat=1000.0, Q_cool=1500.0)
    opt = MPCOptimizer(model)
    plan = opt.optimize(
        T_room=21.0,
        T_outdoor_series=[],
        heat_target_series=[],
        dt_minutes=5,
    )
    assert plan.actions == []
    assert plan.temperatures == [21.0]


def test_optimize_nan_t_room_returns_empty_plan():
    model = RCModel(C=2.0, U=50.0, Q_heat=1000.0, Q_cool=1500.0)
    opt = MPCOptimizer(model)
    plan = opt.optimize(
        T_room=float("nan"),
        T_outdoor_series=[10.0] * 6,
        heat_target_series=[21.0] * 6,
        dt_minutes=5,
    )
    assert plan.actions == []


def test_min_run_forced_idle_when_mode_gated():
    model = RCModel(C=2.0, U=50.0, Q_heat=1000.0, Q_cool=200.0)
    opt = MPCOptimizer(model, can_heat=True, can_cool=True, min_run_blocks=4, outdoor_cooling_min=20.0)
    outdoor = [25.0] * 2 + [10.0] * 10
    targets_heat = [30.0] * 12
    targets_cool = [18.0] * 12
    plan = opt.optimize(
        T_room=27.0,
        T_outdoor_series=outdoor,
        heat_target_series=targets_heat,
        cool_target_series=targets_cool,
        dt_minutes=5,
    )
    cooling_started = False
    for i, a in enumerate(plan.actions):
        if a == "cooling":
            cooling_started = True
        if cooling_started and a == "idle" and i < 4:
            break
    assert len(plan.actions) == 12


def test_compute_optimal_power_nan_inputs():
    model = RCModel(C=2.0, U=50.0, Q_heat=1000.0, Q_cool=1500.0)
    opt = MPCOptimizer(model)
    pf, mode = opt.compute_optimal_power(float("nan"), 10.0, 21.0, 5.0)
    assert pf == 0.0
    assert mode == "idle"
    pf2, mode2 = opt.compute_optimal_power(21.0, 10.0, float("inf"), 5.0)
    assert pf2 == 0.0
    assert mode2 == "idle"


def test_compute_optimal_power_tiny_alpha():
    model = RCModel(C=2.0, U=0.005, Q_heat=1000.0, Q_cool=1500.0)
    opt = MPCOptimizer(model)
    pf, mode = opt.compute_optimal_power(19.0, 10.0, 21.0, 5.0)
    assert mode in ("heating", "idle")


def test_compute_optimal_power_zero_alpha():
    model = RCModel(C=2.0, U=0.0, Q_heat=1000.0, Q_cool=1500.0)
    opt = MPCOptimizer(model)
    pf, mode = opt.compute_optimal_power(19.0, 10.0, 21.0, 5.0)
    assert pf == 0.0
    assert mode == "idle"


def test_compute_optimal_power_solar_with_tiny_alpha():
    model = RCModel(C=2.0, U=0.005, Q_heat=1000.0, Q_cool=1500.0, Q_solar=100.0)
    opt = MPCOptimizer(model)
    pf, mode = opt.compute_optimal_power(20.0, 10.0, 21.0, 5.0, q_solar=0.8)
    assert mode in ("heating", "idle")


def test_compute_optimal_power_residual_with_tiny_alpha():
    model = RCModel(C=2.0, U=0.005, Q_heat=1000.0, Q_cool=1500.0)
    opt = MPCOptimizer(model)
    pf_no, _ = opt.compute_optimal_power(19.0, 10.0, 21.0, 5.0, q_residual=0.0)
    pf_res, _ = opt.compute_optimal_power(19.0, 10.0, 21.0, 5.0, q_residual=0.5)
    assert pf_res <= pf_no or pf_res == pf_no


def test_compute_optimal_power_occupancy_with_tiny_alpha():
    model = RCModel(C=2.0, U=0.005, Q_heat=1000.0, Q_cool=1500.0, Q_occupancy=200.0)
    opt = MPCOptimizer(model)
    pf_no, _ = opt.compute_optimal_power(19.0, 10.0, 21.0, 5.0, q_occupancy=0.0)
    pf_occ, _ = opt.compute_optimal_power(19.0, 10.0, 21.0, 5.0, q_occupancy=1.0)
    assert pf_occ <= pf_no or pf_occ == pf_no


def test_compute_optimal_power_occupancy_with_normal_alpha():
    model = RCModel(C=2.0, U=50.0, Q_heat=1000.0, Q_cool=1500.0, Q_occupancy=200.0)
    opt = MPCOptimizer(model)
    pf_no, _ = opt.compute_optimal_power(19.0, 10.0, 21.0, 5.0, q_occupancy=0.0)
    pf_occ, _ = opt.compute_optimal_power(19.0, 10.0, 21.0, 5.0, q_occupancy=1.0)
    assert pf_occ <= pf_no


def test_get_current_power_fraction_with_fractions():
    plan = MPCPlan(
        actions=["heating", "idle"],
        temperatures=[18.0, 19.0, 19.5],
        dt_minutes=5,
        power_fractions=[0.75, 0.0],
    )
    assert plan.get_current_power_fraction() == 0.75


def test_min_run_forced_idle_outdoor_gate_mid_run():
    model = RCModel(C=200.0, U=50.0, Q_heat=1000.0, Q_cool=200.0)
    opt = MPCOptimizer(
        model,
        can_heat=False,
        can_cool=True,
        min_run_blocks=6,
        outdoor_cooling_min=20.0,
    )
    outdoor = [25.0] + [10.0] * 11
    plan = opt.optimize(
        T_room=28.0,
        T_outdoor_series=outdoor,
        heat_target_series=[22.0] * 12,
        cool_target_series=[22.0] * 12,
        dt_minutes=5,
    )
    if len(plan.actions) > 1 and plan.actions[0] == "cooling":
        assert plan.actions[1] == "idle"


# ---------------------------------------------------------------------------
# Issue #131: UFH proactive pre-heating
# ---------------------------------------------------------------------------


def _ufh_optimizer(**overrides):
    """Construct an optimizer with UFH heat-only profile settings.

    Default can_cool=False matches pure UFH rooms (primary fix target).
    Override can_cool=True to exercise the hybrid UFH+AC code path.
    """
    model = overrides.pop("model", RCModel(C=2.0, U=50.0, Q_heat=1000.0, Q_cool=1500.0))
    defaults = {
        "can_cool": False,
        "w_comfort": 7.0,
        "w_energy": 3.0,
        "min_run_blocks": 6,
        "heating_system_type": "underfloor",
    }
    defaults.update(overrides)
    return MPCOptimizer(model=model, **defaults)


def test_ufh_proactive_preheat_at_target():
    """UFH room at target with cold outdoor should pre-heat, not wait for drop."""
    opt = _ufh_optimizer()
    n = 30
    plan = opt.optimize(
        T_room=20.0,
        T_outdoor_series=[5.0] * n,
        heat_target_series=[20.0] * n,
        cool_target_series=[20.0] * n,
        dt_minutes=5,
    )
    assert plan.actions[0] == "heating", f"UFH at target should pre-heat, got {plan.actions[0]}"


def test_ufh_afterglow_visible_in_cost():
    """Synthesis reduces HEATING cost vs non-synthesized path at equal lookahead.

    Isolates the synthesis effect by forcing both optimizers to the same
    lookahead. Only the heating_system_type-based synthesis gate differs.
    """
    model = RCModel(C=200.0, U=50.0, Q_heat=300.0, Q_cool=1500.0)
    shared = {
        "T_room": 20.0,
        "T_outdoor": 5.0,
        "heat_target": 20.0,
        "cool_target": 20.0,
        "future_T_outdoor": [5.0] * 30,
        "future_heat_targets": [20.0] * 30,
        "future_cool_targets": [20.0] * 30,
        "dt_minutes": 5.0,
    }

    opt_ufh = MPCOptimizer(
        model=model,
        can_cool=False,
        w_comfort=7.0,
        w_energy=3.0,
        min_run_blocks=6,
        heating_system_type="underfloor",
    )
    opt_empty = MPCOptimizer(
        model=model,
        can_cool=False,
        w_comfort=7.0,
        w_energy=3.0,
        min_run_blocks=6,
        heating_system_type="",
    )
    # Force equal lookahead — isolate synthesis from horizon-size effect.
    opt_ufh._lookahead_blocks = 24
    opt_empty._lookahead_blocks = 24

    cost_ufh = opt_ufh._evaluate_action("heating", **shared)
    cost_empty = opt_empty._evaluate_action("heating", **shared)

    assert cost_ufh < cost_empty, (
        f"UFH heating cost {cost_ufh} should be lower than empty-type {cost_empty} "
        "due to afterglow synthesis reducing post-run comfort penalty"
    )


def test_radiator_plan_matches_empty_plan():
    """Radiator and empty-type plans must be byte-identical (no radiator regression)."""
    model = RCModel(C=2.0, U=50.0, Q_heat=1000.0, Q_cool=1500.0)
    kwargs = {
        "T_room": 19.5,
        "T_outdoor_series": [5.0] * 12,
        "heat_target_series": [21.0] * 12,
        "dt_minutes": 5,
    }
    plan_rad = MPCOptimizer(model=model, heating_system_type="radiator").optimize(**kwargs)
    plan_empty = MPCOptimizer(model=model, heating_system_type="").optimize(**kwargs)
    assert plan_rad.actions == plan_empty.actions
    assert plan_rad.temperatures == plan_empty.temperatures
    assert plan_rad.power_fractions == plan_empty.power_fractions


def test_unknown_system_no_regression():
    """Empty heating_system_type keeps base lookahead and synthesis off."""
    model = RCModel(C=2.0, U=50.0, Q_heat=1000.0, Q_cool=1500.0)
    opt = MPCOptimizer(model=model, heating_system_type="")
    plan = opt.optimize(
        T_room=19.5,
        T_outdoor_series=[5.0] * 12,
        heat_target_series=[21.0] * 12,
        dt_minutes=5,
    )
    assert plan.lookahead_blocks == 6


def test_cooling_lookahead_no_afterglow_synthesis():
    """COOLING uses the provided future_residual; never synthesizes afterglow.

    Exercised on an extended-lookahead UFH setup (can_cool=False keeps the
    extension active). With lookahead=24 and min_run=6, the 18 post-run blocks
    see block_Q=0 and let residual through. Proves residual drives COOLING
    cost, not synthesis.
    """
    model = RCModel(C=2.0, U=50.0, Q_heat=1000.0, Q_cool=200.0)
    opt = _ufh_optimizer(model=model)  # can_cool=False by helper default
    opt.optimize(
        T_room=25.0,
        T_outdoor_series=[28.0] * 30,
        heat_target_series=[22.0] * 30,
        cool_target_series=[22.0] * 30,
        dt_minutes=5,
    )
    shared = {
        "T_room": 25.0,
        "T_outdoor": 28.0,
        "heat_target": 22.0,
        "cool_target": 22.0,
        "future_T_outdoor": [28.0] * 30,
        "future_heat_targets": [22.0] * 30,
        "future_cool_targets": [22.0] * 30,
        "dt_minutes": 5.0,
    }
    cost_with_residual = opt._evaluate_action("cooling", **shared, future_residual=[0.5] * 30)
    cost_without_residual = opt._evaluate_action("cooling", **shared, future_residual=[0.0] * 30)
    assert cost_with_residual != cost_without_residual


def test_lookahead_clamps_to_horizon():
    """Short outer horizon clamps lookahead without errors."""
    opt = _ufh_optimizer()
    plan = opt.optimize(
        T_room=20.0,
        T_outdoor_series=[5.0] * 8,
        heat_target_series=[20.0] * 8,
        cool_target_series=[20.0] * 8,
        dt_minutes=5,
    )
    assert len(plan.actions) == 8  # no crash, plan produced


def test_lookahead_blocks_attribute_exposed():
    """Plan exposes lookahead_blocks for guard integration; covers all setups."""
    model = RCModel(C=2.0, U=50.0, Q_heat=1000.0, Q_cool=1500.0)
    cases = [
        # (heating_system_type, can_cool, min_run_blocks, expected_lookahead)
        ("", False, 2, 6),
        ("", True, 2, 6),
        ("radiator", False, 2, 6),
        ("radiator", True, 2, 6),
        ("underfloor", False, 6, 24),
        ("underfloor", True, 6, 6),  # hybrid UFH+AC keeps base lookahead
    ]
    for hst, can_cool, mrb, exp_blocks in cases:
        opt = MPCOptimizer(
            model=model,
            can_cool=can_cool,
            min_run_blocks=mrb,
            heating_system_type=hst,
        )
        plan = opt.optimize(
            T_room=20.0,
            T_outdoor_series=[10.0] * 30,
            heat_target_series=[20.0] * 30,
            dt_minutes=5,
        )
        assert plan.lookahead_blocks == exp_blocks, (
            f"hst={hst!r} can_cool={can_cool}: expected {exp_blocks}, got {plan.lookahead_blocks}"
        )


def test_hybrid_ufh_ac_cooling_balance_preserved():
    """Hybrid UFH+AC rooms keep base lookahead → cooling plan matches pre-fix."""
    model = RCModel(C=2.0, U=50.0, Q_heat=1000.0, Q_cool=200.0)
    kwargs = {
        "T_room": 25.0,
        "T_outdoor_series": [28.0] * 24,
        "heat_target_series": [21.0] * 24,
        "cool_target_series": [23.0] * 24,
        "dt_minutes": 5,
    }
    # Hybrid: UFH TRV + AC cooling. With the fix gated on not can_cool, the
    # UFH profile must NOT extend the lookahead — cooling stays at base=6.
    plan_hybrid = MPCOptimizer(
        model=model,
        can_heat=True,
        can_cool=True,
        min_run_blocks=6,
        heating_system_type="underfloor",
    ).optimize(**kwargs)
    # Reference: same room without UFH profile — the baseline cooling plan.
    plan_baseline = MPCOptimizer(
        model=model,
        can_heat=True,
        can_cool=True,
        min_run_blocks=6,
        heating_system_type="",
    ).optimize(**kwargs)
    assert plan_hybrid.lookahead_blocks == 6
    assert plan_hybrid.actions == plan_baseline.actions
    assert plan_hybrid.temperatures == plan_baseline.temperatures
    assert plan_hybrid.power_fractions == plan_baseline.power_fractions


# ---------------------------------------------------------------------------
# approach_rate tests
# ---------------------------------------------------------------------------


def test_approach_rate_one_matches_legacy_deadbeat_formula():
    """approach_rate=1.0 must reproduce the original one-block formula exactly."""
    model = RCModel(C=1.0, U=0.3, Q_heat=4.0, Q_cool=6.0)
    opt = MPCOptimizer(model=model, approach_rate=1.0)
    T_room, T_out, target, dt = 19.0, 5.0, 21.0, 5.0
    pf, mode = opt.compute_optimal_power(T_room, T_out, target, dt)

    dt_h = dt / 60.0
    alpha = model.U
    beta = 1.0 - math.exp(-alpha * dt_h)
    T_drift = T_room + beta * (T_out - T_room)
    energy_bias = (opt.w_energy / max(opt.w_comfort, 0.01)) * alpha / beta * 0.1
    q_req = max(0.0, (target - T_drift) * alpha / beta - energy_bias)
    expected = max(min(q_req / max(model.Q_heat, 0.01), 1.0), MIN_POWER_FRACTION)

    assert mode == MODE_HEATING
    assert pf == pytest.approx(expected)


def test_approach_rate_below_one_widens_heating_band():
    """Gentler approach_rate lowers pf for the same gap (less saturation)."""
    model = RCModel(C=1.0, U=0.3, Q_heat=20.0, Q_cool=6.0)
    args = (19.0, 5.0, 21.0, 5.0)
    pf_full, _ = MPCOptimizer(model=model, approach_rate=1.0).compute_optimal_power(*args)
    pf_gentle, _ = MPCOptimizer(model=model, approach_rate=0.3).compute_optimal_power(*args)
    assert pf_full == 1.0
    assert pf_gentle < pf_full
    assert pf_gentle >= MIN_POWER_FRACTION


def test_holding_power_independent_of_approach_rate():
    """At target, only holding power is needed; approach_rate must not change it."""
    model = RCModel(C=1.0, U=0.3, Q_heat=20.0, Q_cool=6.0)
    args = (21.0, 5.0, 21.0, 5.0)
    pf_full, _ = MPCOptimizer(model=model, approach_rate=1.0).compute_optimal_power(*args)
    pf_gentle, _ = MPCOptimizer(model=model, approach_rate=0.2).compute_optimal_power(*args)
    assert pf_full == pytest.approx(pf_gentle)


def test_approach_rate_widens_cooling_band_symmetrically():
    """Cooling path is gentled the same way as heating."""
    model = RCModel(C=1.0, U=0.3, Q_heat=4.0, Q_cool=20.0)
    args = (26.0, 30.0, 23.0, 5.0)
    pf_full, m1 = MPCOptimizer(model=model, approach_rate=1.0).compute_optimal_power(*args)
    pf_gentle, m2 = MPCOptimizer(model=model, approach_rate=0.3).compute_optimal_power(*args)
    assert m1 == MODE_COOLING and m2 == MODE_COOLING
    assert pf_gentle < pf_full
    assert pf_gentle >= MIN_POWER_FRACTION


# ---------------------------------------------------------------------------
# Regulated cooling: a setpoint-following AC never drives past its own target
# ---------------------------------------------------------------------------


def _regulated_ac_optimizer(q_cool: float = 11.3) -> MPCOptimizer:
    """Bedroom-like C=1 model: weak envelope, strong AC, warm outdoor load."""
    model = RCModel(C=1.0, U=0.08, Q_heat=3.0, Q_cool=q_cool)
    return MPCOptimizer(model, can_heat=False, can_cool=True, min_run_blocks=3)


def _held_cooling_cost(q_cool: float) -> float:
    """Cost of the COOLING hypothesis for a room already below its target."""
    opt = _regulated_ac_optimizer(q_cool)
    opt._lookahead_blocks = 24
    return opt._evaluate_action(
        MODE_COOLING,
        T_room=21.4,
        T_outdoor=26.0,
        heat_target=5.0,
        cool_target=21.5,
        future_T_outdoor=[26.0] * 24,
        future_heat_targets=[5.0] * 24,
        future_cool_targets=[21.5] * 24,
        dt_minutes=5.0,
    )


def test_cooling_plan_does_not_predict_overshoot_past_the_target():
    """Once at target the forward simulation must follow drift, not full power.

    A proportional AC closes its own valve at its setpoint, so predicting
    MIN * Q_cool for every holding block forecasts a plunge the device would
    never deliver — here a full degree below the 21.5 target.
    """
    plan = _regulated_ac_optimizer().optimize(
        T_room=23.0,
        T_outdoor_series=[26.0] * 24,
        heat_target_series=[5.0] * 24,
        cool_target_series=[21.5] * 24,
        dt_minutes=5,
    )
    assert plan.actions[0] == MODE_COOLING
    assert min(plan.temperatures) >= 21.2, plan.temperatures


def test_held_cooling_hypothesis_is_independent_of_cooling_power():
    """Below target, the hypothesis delivers nothing, so Q_cool cannot matter.

    This is the invariant the duty-cycling bug violated: a stronger AC made
    "keep cooling" look like a deeper (cheaper or costlier) excursion, even
    though a regulated unit sitting at its setpoint delivers the same nothing
    either way.
    """
    assert _held_cooling_cost(5.0) == pytest.approx(_held_cooling_cost(20.0))


def test_heating_hypothesis_still_charges_past_the_target():
    """Heating is deliberately left unregulated: UFH pre-heat is intentional.

    Charging thermal mass beyond the current target is how a slow floor rides
    out the next setback, so the heating hypothesis must keep simulating real
    power — and therefore stay sensitive to Q_heat.
    """

    def cost(q_heat: float) -> float:
        opt = MPCOptimizer(
            RCModel(C=1.0, U=0.08, Q_heat=q_heat, Q_cool=11.3),
            can_heat=True,
            can_cool=False,
            min_run_blocks=3,
        )
        opt._lookahead_blocks = 24
        return opt._evaluate_action(
            MODE_HEATING,
            T_room=21.4,
            T_outdoor=5.0,
            heat_target=21.0,
            cool_target=26.0,
            future_T_outdoor=[5.0] * 24,
            future_heat_targets=[21.0] * 24,
            future_cool_targets=[26.0] * 24,
            dt_minutes=5.0,
        )

    assert cost(3.0) != pytest.approx(cost(12.0))


def test_simulate_plan_reproduces_a_plan_that_holds_at_target():
    """The replay helper must mirror the regulated forward step, not full power.

    simulate_plan() exists to answer "what would this plan have produced
    without disturbance X", so it has to reproduce the plan exactly when
    handed the plan's own inputs — including the blocks where the AC was
    holding at its setpoint and delivering nothing.
    """
    opt = _regulated_ac_optimizer()
    outdoor = [26.0] * 24
    plan = opt.optimize(
        T_room=23.0,
        T_outdoor_series=outdoor,
        heat_target_series=[5.0] * 24,
        cool_target_series=[21.5] * 24,
        dt_minutes=5,
    )
    # The scenario has to contain a hold for this to mean anything.
    held = [i for i, a in enumerate(plan.actions) if a == MODE_COOLING and plan.temperatures[i] <= 21.5]
    assert held, plan.actions

    assert opt.simulate_plan(plan, 23.0, outdoor, 5) == plan.temperatures


# ---------------------------------------------------------------------------
# Starting a run costs something: steady-state cycling consolidates
# ---------------------------------------------------------------------------


def _cooling_runs(actions: list[str]) -> int:
    """Number of separate cooling runs in a plan (a run is a C block group)."""
    return sum(1 for i, a in enumerate(actions) if a == MODE_COOLING and (i == 0 or actions[i - 1] != MODE_COOLING))


def _steady_state_plan(initial_mode: str, n: int = 48):
    """Plan for a room sitting just above target under a persistent warm load."""
    return _regulated_ac_optimizer().optimize(
        T_room=21.6,
        T_outdoor_series=[26.0] * n,
        heat_target_series=[5.0] * n,
        cool_target_series=[21.5] * n,
        dt_minutes=5,
        initial_mode=initial_mode,
    )


def test_continuing_the_running_mode_is_free():
    """The same state continues a live run but would not start a fresh one.

    Without initial_mode the optimizer assumed every plan began from idle, so
    continuing a run was priced as if it were a restart.
    """
    assert _steady_state_plan(MODE_COOLING).actions[0] == MODE_COOLING
    assert _steady_state_plan(MODE_IDLE).actions[0] == MODE_IDLE


def test_start_penalty_consolidates_steady_state_cycling(monkeypatch):
    """Near steady state, pricing starts stretches cycles instead of chattering.

    Unpriced, a run that buys a few hundredths of a degree-squared starts
    again as soon as the min-run floor allows -- forever. The room is allowed
    to drift a little further instead, well inside the comfort band.
    """
    priced = _cooling_runs(_steady_state_plan(MODE_COOLING).actions)
    monkeypatch.setattr("custom_components.roommind.control.mpc_optimizer.MODE_START_PENALTY", 0.0)
    unpriced = _cooling_runs(_steady_state_plan(MODE_COOLING).actions)
    assert priced < unpriced, f"priced {priced} runs, unpriced {unpriced}"


def test_start_penalty_does_not_block_a_real_demand():
    """A room well above target still starts cooling immediately."""
    plan = _regulated_ac_optimizer().optimize(
        T_room=23.0,
        T_outdoor_series=[26.0] * 24,
        heat_target_series=[5.0] * 24,
        cool_target_series=[21.5] * 24,
        dt_minutes=5,
        initial_mode=MODE_IDLE,
    )
    assert plan.actions[0] == MODE_COOLING
