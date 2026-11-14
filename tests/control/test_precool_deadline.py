"""Pre-cooling starts as late as possible so a falling cool target is reached in time."""

from __future__ import annotations

from custom_components.roommind.const import MODE_COOLING, MODE_HEATING, MODE_IDLE
from custom_components.roommind.control.mpc_optimizer import MPCOptimizer
from custom_components.roommind.control.thermal_model import RCModel

# A small AC in a warm room: ~1.2 K/h net at full power with 32 °C outside
SMALL_AC = RCModel(C=1.0, U=0.05, Q_heat=3.0, Q_cool=2.0)


def _plan(
    T_room,
    fall_at,
    *,
    n=72,
    eco=27.0,
    comfort=24.0,
    initial_mode=MODE_IDLE,
    can_cool=True,
    preheat_max_blocks=None,
    schedule_cool=None,
    cool=None,
):
    opt = MPCOptimizer(
        SMALL_AC, can_heat=False, can_cool=can_cool, cool_min_run_blocks=2, preheat_max_blocks=preheat_max_blocks
    )
    cool = cool if cool is not None else [eco] * fall_at + [comfort] * (n - fall_at)
    return opt.optimize(
        T_room=T_room,
        T_outdoor_series=[32.0] * n,
        heat_target_series=[min(T_room, c) for c in cool],
        cool_target_series=cool,
        dt_minutes=5,
        initial_mode=initial_mode,
        schedule_cool_series=schedule_cool,
    )


def test_cools_now_when_waiting_would_miss_the_comfort_block():
    plan = _plan(26.8, fall_at=18)  # -2.8 K in 1.5 h: full power needs ~1.6 h
    assert plan.actions[0] == MODE_COOLING
    assert plan.power_fractions[0] == 1.0
    assert plan.preheat_blocks == 18


def test_waits_while_a_later_start_still_reaches_the_target():
    plan = _plan(24.5, fall_at=60)  # -0.5 K in 5 h: plenty of time
    assert plan.actions[0] == MODE_IDLE
    assert plan.preheat_blocks == 0


def test_no_fall_no_precool():
    plan = _plan(26.8, fall_at=72)
    assert plan.actions[0] == MODE_IDLE
    assert plan.preheat_blocks == 0


def test_room_already_below_the_coming_target_is_no_precool():
    plan = _plan(23.5, fall_at=12)
    assert plan.actions[0] == MODE_IDLE
    assert plan.preheat_blocks == 0


def test_running_precool_keeps_going_at_the_deadline_edge():
    # Waiting one block would still make it, so a fresh start waits ...
    assert _plan(24.6, fall_at=10).actions[0] == MODE_IDLE
    # ... but a pre-cool already running keeps going instead of toggling at the edge
    plan = _plan(24.6, fall_at=10, initial_mode=MODE_COOLING)
    assert plan.actions[0] == MODE_COOLING
    assert plan.preheat_blocks == 10


def test_running_precool_stops_at_the_target():
    plan = _plan(24.05, fall_at=24, initial_mode=MODE_COOLING)
    assert plan.actions[0] == MODE_IDLE


def test_no_precool_without_cooling():
    plan = _plan(26.8, fall_at=24, can_cool=False)
    assert plan.actions[0] == MODE_IDLE
    assert plan.preheat_blocks == 0


def test_room_switch_and_slider_limit_the_precool_lead():
    assert _plan(26.8, fall_at=18, preheat_max_blocks=0).actions[0] == MODE_IDLE
    assert _plan(26.8, fall_at=18, preheat_max_blocks=12).actions[0] == MODE_IDLE
    assert _plan(26.8, fall_at=18, preheat_max_blocks=24).actions[0] == MODE_COOLING


def test_end_of_an_expensive_stretch_is_no_precool_target():
    """The price shift raised the cool target to 25 in expensive hours; the schedule stays at 24."""
    n = 72
    cool = [25.0] * 24 + [24.0] * (n - 24)
    schedule = [24.0] * n
    plan = _plan(24.9, fall_at=0, cool=cool, schedule_cool=schedule)
    assert plan.actions[0] == MODE_IDLE
    assert plan.preheat_blocks == 0


def test_schedule_fall_still_precools_under_a_price_shift():
    n = 72
    schedule = [27.0] * 12 + [24.0] * (n - 12)
    cool = [27.0] * 12 + [25.0] * (n - 12)  # expensive at the comfort start: the shift raises it to 25
    plan = _plan(26.8, fall_at=0, cool=cool, schedule_cool=schedule)
    assert plan.actions[0] == MODE_COOLING
    assert plan.preheat_blocks == 12


def test_heat_deadline_wins_over_cooling():
    """Rooms that can do both: a coming heat rise keeps its pre-heat, no cooling hypothesis on top."""
    opt = MPCOptimizer(SMALL_AC, can_heat=True, can_cool=True, cool_min_run_blocks=2)
    n = 72
    plan = opt.optimize(
        T_room=19.0,
        T_outdoor_series=[0.0] * n,
        heat_target_series=[17.0] * 24 + [21.0] * (n - 24),
        cool_target_series=[27.0] * 24 + [24.0] * (n - 24),
        dt_minutes=5,
        initial_mode=MODE_IDLE,
    )
    assert plan.actions[0] in (MODE_HEATING, MODE_IDLE)


def test_cheap_charge_is_no_precool_target():
    """A cheap stretch lowers the target below the schedule: charging is the cheap hours' job."""
    n = 72
    cool = [24.0] * 24 + [23.0] * (n - 24)
    schedule = [24.0] * n
    plan = _plan(24.0, fall_at=0, cool=cool, schedule_cool=schedule)
    assert plan.preheat_blocks == 0


def test_air_pull_down_lets_the_precool_start_later():
    """With a learned air/mass offset the sensor reaches the target sooner: the deadline waits longer."""
    n = 72
    cool = [27.0] * 18 + [24.0] * (n - 18)

    def first_cooling(model, charge):
        opt = MPCOptimizer(model, can_heat=False, can_cool=True, cool_min_run_blocks=2)
        for start in range(18):
            plan = opt.optimize(
                T_room=26.8,
                T_outdoor_series=[32.0] * (n - start),
                heat_target_series=[24.0] * (n - start),
                cool_target_series=cool[start:],
                dt_minutes=5,
                rebound_charge=charge,
            )
            if plan.actions[0] == MODE_COOLING:
                return start
        return None

    plain = first_cooling(SMALL_AC, None)
    fast = RCModel(C=1.0, U=0.05, Q_heat=3.0, Q_cool=2.0, Q_fast=6.0)
    with_air = first_cooling(fast, 0.0)
    assert plain == 0
    assert with_air is not None and with_air > plain


def test_room_held_at_its_eco_target_still_gets_the_lead():
    """At the eco edge the greedy step already cools; the plan still names the lead for the controller."""
    model = RCModel(C=1.0, U=0.011, Q_heat=3.0, Q_cool=0.74, Q_fast=10.9, Q_solar=0.3)
    opt = MPCOptimizer(model, can_heat=False, can_cool=True, cool_min_run_blocks=2)
    n = 72
    cool = [27.0] * 20 + [24.0] * (n - 20)
    plan = opt.optimize(
        T_room=27.0,
        T_outdoor_series=[30.0] * n,
        heat_target_series=[24.0] * n,
        cool_target_series=cool,
        dt_minutes=5,
        rebound_charge=0.0,
    )
    assert plan.actions[0] == MODE_COOLING
    assert plan.preheat_blocks == 20
    assert plan.power_fractions[0] == 1.0


def test_a_heating_block_is_not_turned_into_a_precool():
    """A boost band now (heat 23, room 21) ending into a lower band (cool 20): the room heats, no pre-cool."""
    opt = MPCOptimizer(SMALL_AC, can_heat=True, can_cool=True, cool_min_run_blocks=2)
    n = 72
    plan = opt.optimize(
        T_room=21.0,
        T_outdoor_series=[20.0] * n,
        heat_target_series=[23.0] * 6 + [18.0] * (n - 6),
        cool_target_series=[26.0] * 6 + [20.0] * (n - 6),
        dt_minutes=5,
    )
    assert plan.actions[0] == MODE_HEATING
