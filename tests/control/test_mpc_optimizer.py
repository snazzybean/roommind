"""Tests for the MPC optimizer: MPCOptimizer, MPCPlan."""

from __future__ import annotations

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
