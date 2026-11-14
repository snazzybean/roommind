"""Pre-heating starts as late as possible so a rising heat target is reached in time."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from custom_components.roommind.const import TargetTemps
from custom_components.roommind.control.mpc_controller import (
    MAX_HORIZON_HOURS,
    MODE_HEATING,
    MODE_IDLE,
    PLAN_DT_MINUTES,
    MPCController,
    clear_command_cache,
    compute_horizon_blocks,
)
from custom_components.roommind.control.mpc_optimizer import MPCOptimizer, MPCPlan
from custom_components.roommind.control.thermal_model import RCModel, RoomModelManager

from .conftest import build_hass, make_room

# Room with a radiator sized to its heat load: 0.56 K/h at full power, tau ~70 h
SLOW = RCModel(C=1.0, U=0.014, Q_heat=0.56, Q_cool=4.0)


def _plan(model, T_room, rise_at, *, n=72, eco=17.5, comfort=20.0, initial_mode=MODE_IDLE, can_heat=True):
    opt = MPCOptimizer(model, can_heat=can_heat, can_cool=False)
    heat = [eco] * rise_at + [comfort] * (n - rise_at)
    return opt.optimize(
        T_room=T_room,
        T_outdoor_series=[0.0] * n,
        heat_target_series=heat,
        dt_minutes=5,
        initial_mode=initial_mode,
    )


def test_heats_now_when_waiting_would_miss_the_comfort_block():
    plan = _plan(SLOW, 18.0, rise_at=36)  # +2 K in 3 h needs ~4 h at 0.56 K/h
    assert plan.actions[0] == MODE_HEATING
    assert plan.power_fractions[0] == 1.0
    assert plan.preheat_blocks == 36


def test_waits_while_a_later_start_still_reaches_the_target():
    plan = _plan(SLOW, 19.5, rise_at=60)  # +0.5 K in 5 h: plenty of time
    assert plan.actions[0] == MODE_IDLE
    assert plan.preheat_blocks == 0


def test_no_rise_no_preheat():
    plan = _plan(SLOW, 18.0, rise_at=72)
    assert plan.actions[0] == MODE_IDLE
    assert plan.preheat_blocks == 0


def test_running_preheat_keeps_going_at_the_deadline_edge():
    # Waiting one block would still make it, so a fresh start waits ...
    assert _plan(SLOW, 19.5, rise_at=20).actions[0] == MODE_IDLE
    # ... but a pre-heat already running keeps going instead of toggling at the edge
    plan = _plan(SLOW, 19.5, rise_at=20, initial_mode=MODE_HEATING)
    assert plan.actions[0] == MODE_HEATING
    assert plan.preheat_blocks == 20


def test_running_preheat_stops_at_the_target():
    plan = _plan(SLOW, 19.95, rise_at=24, initial_mode=MODE_HEATING)
    assert plan.actions[0] == MODE_IDLE


def test_no_preheat_without_heating():
    plan = _plan(SLOW, 18.0, rise_at=36, can_heat=False)
    assert plan.actions[0] == MODE_IDLE
    assert plan.preheat_blocks == 0


def test_horizon_uses_the_slower_rate_and_is_capped():
    # Heat-only room: the untrained cooling default (4 K/h) must not shorten the horizon
    blocks = compute_horizon_blocks(SLOW, 18.0, 17.5)
    assert blocks * PLAN_DT_MINUTES / 60 > 6
    very_slow = RCModel(C=1.0, U=0.01, Q_heat=0.05, Q_cool=4.0)
    assert compute_horizon_blocks(very_slow, 18.0, 17.5) == MAX_HORIZON_HOURS * 60 // PLAN_DT_MINUTES


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_command_cache()
    yield
    clear_command_cache()


def _controller(monkeypatch, plan: MPCPlan, rise_after_s: float):
    start = time.time()

    def resolve(ts: float) -> TargetTemps:
        return TargetTemps(20.0, None) if ts >= start + rise_after_s else TargetTemps(17.5, None)

    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0, "max_temp": 30.0}
    hass.states.get = MagicMock(return_value=state)
    ctrl = MPCController(
        hass,
        make_room(climate_mode="heat_only", heating_system_type="radiator"),
        model_manager=RoomModelManager(),
        outdoor_temp=0.0,
        settings={},
        has_external_sensor=True,
        target_resolver=resolve,
        heating_system_type="radiator",
    )
    monkeypatch.setattr(
        "custom_components.roommind.control.mpc_controller.MPCOptimizer.optimize",
        lambda *a, **kw: plan,
    )
    return ctrl


def test_guard_looks_as_far_ahead_as_the_preheat(monkeypatch):
    """Room above the eco target, comfort 90 min out: the 30-min guard would cancel the pre-heat."""
    plan = MPCPlan(actions=[MODE_HEATING] * 24, temperatures=[18.0] * 25, power_fractions=[1.0] * 24, preheat_blocks=18)
    ctrl = _controller(monkeypatch, plan, 90 * 60)
    assert ctrl._evaluate_mpc(18.0, TargetTemps(17.5, None))[0] == MODE_HEATING


def test_without_preheat_the_guard_keeps_the_short_window(monkeypatch):
    plan = MPCPlan(actions=[MODE_HEATING] * 24, temperatures=[18.0] * 25, power_fractions=[1.0] * 24)
    ctrl = _controller(monkeypatch, plan, 90 * 60)
    assert ctrl._evaluate_mpc(18.0, TargetTemps(17.5, None))[0] == MODE_IDLE


def test_an_eco_holding_run_does_not_turn_into_an_early_preheat():
    """A run holding the eco target ends normally; comfort 6 h out (~2 h needed) is no reason to keep heating."""
    medium = RCModel(C=1.0, U=0.014, Q_heat=1.5, Q_cool=4.0)
    plan = _plan(medium, 17.6, rise_at=72, n=96, initial_mode=MODE_HEATING)
    assert plan.actions[0] == MODE_IDLE
    assert plan.preheat_blocks == 0


def test_slider_limits_the_preheat_lead():
    from custom_components.roommind.control.mpc_optimizer import preheat_max_blocks

    assert preheat_max_blocks(70) is None
    assert preheat_max_blocks(100) is None
    assert preheat_max_blocks(35) == 72  # 6 h
    assert preheat_max_blocks(0) == 0


@pytest.mark.parametrize(
    ("limit", "expected"), [(None, MODE_HEATING), (48, MODE_HEATING), (24, MODE_IDLE), (0, MODE_IDLE)]
)
def test_efficiency_setting_starts_no_earlier_than_allowed(limit, expected):
    """Comfort 3 h out needs ~4 h: full comfort pre-heats now, efficiency waits."""
    opt = MPCOptimizer(SLOW, can_heat=True, can_cool=False, preheat_max_blocks=limit)
    plan = opt.optimize(
        T_room=18.0,
        T_outdoor_series=[0.0] * 72,
        heat_target_series=[17.5] * 36 + [20.0] * 36,
        dt_minutes=5,
    )
    assert plan.actions[0] == expected


def test_controller_and_analytics_take_the_limit_from_the_slider():
    ctrl = MPCController(
        build_hass(),
        make_room(),
        model_manager=RoomModelManager(),
        outdoor_temp=0.0,
        settings={"comfort_weight": 0},
        has_external_sensor=True,
    )
    assert ctrl._preheat_max_blocks == 0


def test_room_switch_turns_the_preheat_lead_off():
    """Pre-heating off for a room (#478): no lead, whatever the slider says."""
    from custom_components.roommind.control.mpc_optimizer import preheat_max_blocks

    assert preheat_max_blocks(70, enabled=False) == 0
    assert preheat_max_blocks(100, enabled=False) == 0
    assert preheat_max_blocks(70, enabled=True) is None


@pytest.mark.parametrize(("room_value", "expected"), [(False, 0), (True, None), ("missing", None)])
def test_controller_reads_the_room_switch(room_value, expected):
    room = make_room() if room_value == "missing" else make_room(preheat_enabled=room_value)
    ctrl = MPCController(
        build_hass(),
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=0.0,
        settings={"comfort_weight": 70},
        has_external_sensor=True,
    )
    assert ctrl._preheat_max_blocks == expected


def test_analytics_reads_the_room_switch():
    from unittest.mock import patch

    from custom_components.roommind.control import analytics_simulator

    seen = []
    real = analytics_simulator.MPCOptimizer

    def spy(*args, **kwargs):
        seen.append(kwargs.get("preheat_max_blocks"))
        return real(*args, **kwargs)

    forecast = [{"target_temp": 17.5, "heat_target": 17.5, "cool_target": 30.0}] * 6
    room = make_room(preheat_enabled=False, climate_mode="heat_only")
    with patch.object(analytics_simulator, "MPCOptimizer", side_effect=spy):
        analytics_simulator._simulate_mpc(
            SLOW, forecast, [0.0] * 6, current_temp=18.0, room_config=room, settings={"comfort_weight": 70}
        )
    assert seen and all(v == 0 for v in seen)


def _price_plan(model, T_room, heat, schedule, *, n=72):
    opt = MPCOptimizer(model, can_heat=True, can_cool=False)
    return opt.optimize(
        T_room=T_room,
        T_outdoor_series=[0.0] * n,
        heat_target_series=heat,
        schedule_heat_series=schedule,
        dt_minutes=5,
    )


def test_end_of_an_expensive_stretch_is_no_preheat_target():
    # Constant schedule 20, expensive for 3 h (coasting 2 K to 18): the 20 after it is not
    # worth heating for in the expensive hours, the user allowed the room to be 2 K lower
    heat = [18.0] * 36 + [20.0] * 36
    schedule = [20.0] * 72
    plan = _price_plan(SLOW, 18.2, heat, schedule)
    assert plan.preheat_blocks == 0
    assert plan.actions[0] == MODE_IDLE
    # The same series without the price information still pre-heats (as before)
    plan = _price_plan(SLOW, 18.2, heat, None)
    assert plan.preheat_blocks == 36


def test_schedule_rise_after_an_expensive_stretch_still_preheats():
    # Eco 17 (coasting to 16) until the comfort block 21: the schedule rises, so the room is
    # pre-heated in time even though the hours before are expensive
    heat = [16.0] * 36 + [21.0] * 36
    schedule = [17.0] * 36 + [21.0] * 36
    plan = _price_plan(SLOW, 18.0, heat, schedule)
    assert plan.preheat_blocks == 36
    assert plan.actions[0] == MODE_HEATING


def test_preheat_aims_at_the_schedule_not_the_charge_on_top():
    # Comfort 21 from block 36 on, charged to 22 there (cheap, expensive hours follow): the
    # pre-heat in the hours before aims at 21 and starts no earlier than for 21 alone
    room = 20.2
    charged = _price_plan(SLOW, room, [17.0] * 36 + [22.0] * 36, [17.0] * 36 + [21.0] * 36)
    plain = _price_plan(SLOW, room, [17.0] * 36 + [21.0] * 36, [17.0] * 36 + [21.0] * 36)
    assert charged.actions[0] == plain.actions[0] == MODE_IDLE
    # Without the price information the 22 pulls the start earlier (the old behaviour)
    assert _price_plan(SLOW, room, [17.0] * 36 + [22.0] * 36, None).actions[0] == MODE_HEATING


def test_start_of_a_charging_stretch_is_no_preheat_target():
    # A normal hour before cheap hours that charge +1 K: charging belongs to the cheap hours
    heat = [19.0] * 12 + [20.0] * 60
    schedule = [19.0] * 72
    plan = _price_plan(SLOW, 18.95, heat, schedule)
    assert plan.preheat_blocks == 0


def _spy_optimize(monkeypatch, module: str) -> list:
    seen: list = []
    real = MPCOptimizer.optimize

    def spy(self, *args, **kwargs):
        seen.append(kwargs.get("schedule_heat_series"))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(f"custom_components.roommind.control.{module}.MPCOptimizer.optimize", spy)
    return seen


def test_controller_hands_the_schedule_without_the_price_shift_to_the_plan(monkeypatch):
    seen = _spy_optimize(monkeypatch, "mpc_controller")
    ctrl = MPCController(
        build_hass(),
        make_room(climate_mode="heat_only"),
        model_manager=RoomModelManager(),
        outdoor_temp=0.0,
        settings={},
        has_external_sensor=True,
        target_resolver=lambda ts: TargetTemps(18.0, None),
        schedule_target_resolver=lambda ts: TargetTemps(None, None),
    )
    ctrl._evaluate_mpc(18.5, TargetTemps(18.0, None))
    # No schedule target: filled like the shifted series (room temperature)
    assert seen and seen[0] and set(seen[0]) == {18.5}


def test_controller_without_a_price_room_passes_no_schedule_series(monkeypatch):
    seen = _spy_optimize(monkeypatch, "mpc_controller")
    ctrl = MPCController(
        build_hass(),
        make_room(climate_mode="heat_only"),
        model_manager=RoomModelManager(),
        outdoor_temp=0.0,
        settings={},
        has_external_sensor=True,
        target_resolver=lambda ts: TargetTemps(18.0, None),
    )
    ctrl._evaluate_mpc(18.5, TargetTemps(18.0, None))
    assert seen == [None]


def test_prediction_unshifts_the_forecast_for_the_deadline(monkeypatch):
    from custom_components.roommind.control.analytics_simulator import _simulate_mpc

    seen = _spy_optimize(monkeypatch, "analytics_simulator")
    shifted = {"target_temp": 18.0, "heat_target": 18.0, "cool_target": None, "price_shift_heat": -1.0}
    plain = {"target_temp": 19.0, "heat_target": 19.0, "cool_target": None, "price_shift_heat": 0.0}
    _simulate_mpc(SLOW, [shifted] * 3 + [plain] * 3, [0.0] * 6, 18.5, make_room(climate_mode="heat_only"), {})
    assert seen[0] == [19.0] * 6
    seen.clear()
    _simulate_mpc(SLOW, [plain] * 6, [0.0] * 6, 18.5, make_room(climate_mode="heat_only"), {})
    assert seen[0] is None


def test_unshifted_forecast_has_no_float_noise():
    from custom_components.roommind.control.analytics_simulator import _schedule_series

    # A 60 °F block (15.6 °C) charged by 0.5: 16.1 - 0.5 must not read as a rise over 15.6
    charged = {"target_temp": 16.1, "heat_target": 16.1, "cool_target": None, "price_shift_heat": 0.5}
    plain = {"target_temp": 15.6, "heat_target": 15.6, "cool_target": None, "price_shift_heat": 0.0}
    series = _schedule_series([plain, charged], 15.0)
    assert series is not None and series[0] == [15.6, 15.6]


def test_controller_and_prediction_hand_the_unshifted_cool_schedule_to_the_plan(monkeypatch):
    from custom_components.roommind.control.analytics_simulator import _simulate_mpc

    seen: list = []
    real = MPCOptimizer.optimize

    def spy(self, *args, **kwargs):
        seen.append(kwargs.get("schedule_cool_series"))
        return real(self, *args, **kwargs)

    for module in ("mpc_controller", "analytics_simulator"):
        monkeypatch.setattr(f"custom_components.roommind.control.{module}.MPCOptimizer.optimize", spy)
    ctrl = MPCController(
        build_hass(),
        make_room(climate_mode="cool_only", thermostats=[], acs=["climate.ac"]),
        model_manager=RoomModelManager(),
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
        target_resolver=lambda ts: TargetTemps(None, 25.0),
        schedule_target_resolver=lambda ts: TargetTemps(None, 24.0),
    )
    ctrl._evaluate_mpc(25.5, TargetTemps(None, 25.0))
    assert seen and set(seen[0]) == {24.0}
    seen.clear()
    shifted = {"target_temp": 25.0, "heat_target": None, "cool_target": 25.0, "price_shift_cool": 1.0}
    _simulate_mpc(SLOW, [shifted] * 6, [30.0] * 6, 25.5, make_room(climate_mode="cool_only"), {})
    assert seen[0] == [24.0] * 6
