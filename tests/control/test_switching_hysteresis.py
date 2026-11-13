"""MPC must not toggle a fast system heat/idle every cycle around the target.

Seen in the simulation with split ACs: the air node heats within a minute and
relaxes into the walls right after a stop, so the optimizer (no memory, no
hysteresis) restarted the device on every other 30 s cycle (~45 commands/h).
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from custom_components.roommind.const import MIN_POWER_FRACTION, TargetTemps
from custom_components.roommind.control.mpc_controller import (
    MODE_COOLING,
    MODE_HEATING,
    MODE_IDLE,
    MPCController,
)
from custom_components.roommind.control.mpc_optimizer import MPCOptimizer, MPCPlan
from custom_components.roommind.control.thermal_model import RCModel, RoomModelManager

from .conftest import build_hass, make_room

HEAT_ROOM = {"climate_mode": "heat_only"}
COOL_ROOM = {"acs": ["climate.ac1"], "thermostats": [], "climate_mode": "cool_only"}


def _controller(room_overrides=None, **kwargs) -> MPCController:
    room = make_room(**(room_overrides or HEAT_ROOM))
    return MPCController(
        build_hass(),
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=kwargs.pop("outdoor_temp", 5.0),
        settings={},
        has_external_sensor=True,
        **kwargs,
    )


def _fake_plan(monkeypatch, action: str, pf: float = 0.6, lookahead_blocks: int = 6) -> None:
    plan = MPCPlan(
        actions=[action] * 24,
        temperatures=[21.0] * 25,
        power_fractions=[pf if action != MODE_IDLE else 0.0] * 24,
        lookahead_blocks=lookahead_blocks,
    )
    monkeypatch.setattr(
        "custom_components.roommind.control.mpc_controller.MPCOptimizer.optimize",
        lambda *a, **kw: plan,
    )


def _within_min_run(mode: str) -> dict:
    return {"previous_mode": mode, "mode_on_since": time.time() - 60}


# --- starting -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("temp", "expected"),
    [
        (21.0, MODE_IDLE),
        (20.9, MODE_IDLE),
        (20.899999999999995, MODE_IDLE),
        (20.8, MODE_HEATING),
        (20.800000000000004, MODE_HEATING),
    ],
)
def test_heating_starts_only_past_the_hysteresis(monkeypatch, temp, expected):
    _fake_plan(monkeypatch, MODE_HEATING)
    mode, _ = _controller()._evaluate_mpc(temp, TargetTemps(heat=21.0, cool=24.0))
    assert mode == expected


@pytest.mark.parametrize(
    ("temp", "expected"), [(20.8, MODE_IDLE), (20.800000000000004, MODE_IDLE), (20.7, MODE_HEATING)]
)
def test_ac_heated_room_uses_the_bang_bang_hysteresis(monkeypatch, temp, expected):
    _fake_plan(monkeypatch, MODE_HEATING)
    ctrl = _controller({"climate_mode": "heat_only", "acs": ["climate.ac1"], "thermostats": []})
    ctrl._get_can_heat_cool = lambda: (True, False)
    mode, _ = ctrl._evaluate_mpc(temp, TargetTemps(heat=21.0, cool=24.0))
    assert mode == expected


def test_running_heat_is_not_stopped_by_the_start_hysteresis(monkeypatch):
    _fake_plan(monkeypatch, MODE_HEATING, pf=0.6)
    ctrl = _controller(previous_mode=MODE_HEATING, mode_on_since=time.time() - 3600)
    assert ctrl._evaluate_mpc(20.9, TargetTemps(heat=21.0, cool=24.0)) == (MODE_HEATING, 0.6)


def test_preheat_for_a_rising_target_may_start_early(monkeypatch):
    """A schedule step up inside the guard horizon keeps pre-heating the optimizer's call."""
    _fake_plan(monkeypatch, MODE_HEATING, pf=1.0)
    rise_at = time.time() + 15 * 60
    ctrl = _controller(
        target_resolver=lambda ts: TargetTemps(heat=21.0 if ts >= rise_at else 18.0, cool=24.0),
    )
    mode, pf = ctrl._evaluate_mpc(20.5, TargetTemps(heat=18.0, cool=24.0))
    assert (mode, pf) == (MODE_HEATING, 1.0)


@pytest.mark.parametrize(
    ("temp", "expected"),
    [
        (24.0, MODE_IDLE),
        (24.1, MODE_IDLE),
        (24.100000000000005, MODE_IDLE),
        (24.2, MODE_COOLING),
        (24.199999999999996, MODE_COOLING),
    ],
)
def test_cooling_starts_only_past_the_hysteresis(monkeypatch, temp, expected):
    """Cooling starts one sensor step past the target; a wider band let the sun push the room over it."""
    _fake_plan(monkeypatch, MODE_COOLING)
    mode, _ = _controller(COOL_ROOM, outdoor_temp=30.0)._evaluate_mpc(temp, TargetTemps(heat=None, cool=24.0))
    assert mode == expected


def test_precool_for_a_falling_target_may_start_early(monkeypatch):
    _fake_plan(monkeypatch, MODE_COOLING, pf=1.0)
    drop_at = time.time() + 15 * 60
    ctrl = _controller(
        COOL_ROOM,
        outdoor_temp=30.0,
        target_resolver=lambda ts: TargetTemps(heat=None, cool=24.0 if ts >= drop_at else 27.0),
    )
    assert ctrl._evaluate_mpc(25.0, TargetTemps(heat=None, cool=27.0)) == (MODE_COOLING, 1.0)


# --- stopping -------------------------------------------------------------------


def test_heating_run_survives_an_idle_plan_until_min_run_is_over(monkeypatch):
    _fake_plan(monkeypatch, MODE_IDLE)
    ctrl = _controller(**_within_min_run(MODE_HEATING))
    mode, pf = ctrl._evaluate_mpc(21.0, TargetTemps(heat=21.0, cool=24.0))
    assert mode == MODE_HEATING
    assert MIN_POWER_FRACTION <= pf < 1.0


def test_gentle_power_follows_the_closed_form_below_target(monkeypatch):
    """Below the target the kept run uses the proportional power, not just the floor."""
    _fake_plan(monkeypatch, MODE_IDLE)
    ctrl = _controller(**_within_min_run(MODE_HEATING))
    _, pf = ctrl._evaluate_mpc(19.0, TargetTemps(heat=21.0, cool=24.0))
    assert pf > MIN_POWER_FRACTION


def test_heating_run_ends_after_min_run(monkeypatch):
    _fake_plan(monkeypatch, MODE_IDLE)
    ctrl = _controller(previous_mode=MODE_HEATING, mode_on_since=time.time() - 3600)
    assert ctrl._evaluate_mpc(21.0, TargetTemps(heat=21.0, cool=24.0)) == (MODE_IDLE, 0.0)


def test_heating_run_ends_when_heating_is_no_longer_allowed(monkeypatch):
    """Outdoor gate (heating_max 22) closed: the min run does not force heat."""
    _fake_plan(monkeypatch, MODE_IDLE)
    ctrl = _controller(outdoor_temp=25.0, **_within_min_run(MODE_HEATING))
    assert ctrl._evaluate_mpc(21.0, TargetTemps(heat=21.0, cool=24.0)) == (MODE_IDLE, 0.0)


def test_hard_ceiling_still_ends_a_fast_run_inside_min_run(monkeypatch):
    _fake_plan(monkeypatch, MODE_HEATING, pf=1.0)
    ctrl = _controller(**_within_min_run(MODE_HEATING))
    assert ctrl._evaluate_mpc(22.1, TargetTemps(heat=21.0, cool=24.0)) == (MODE_IDLE, 0.0)


def test_idle_plan_past_the_ceiling_is_not_reenabled(monkeypatch):
    _fake_plan(monkeypatch, MODE_IDLE)
    ctrl = _controller(**_within_min_run(MODE_HEATING))
    assert ctrl._evaluate_mpc(22.1, TargetTemps(heat=21.0, cool=24.0)) == (MODE_IDLE, 0.0)


def test_cooling_run_survives_an_idle_plan_until_min_run_is_over(monkeypatch):
    _fake_plan(monkeypatch, MODE_IDLE)
    ctrl = _controller(COOL_ROOM, outdoor_temp=30.0, **_within_min_run(MODE_COOLING))
    mode, pf = ctrl._evaluate_mpc(24.0, TargetTemps(heat=None, cool=24.0))
    assert mode == MODE_COOLING
    assert MIN_POWER_FRACTION <= pf < 1.0


# --- slow systems keep the optimizer's decision ----------------------------------


def test_slow_system_skips_the_hysteresis(monkeypatch):
    _fake_plan(monkeypatch, MODE_HEATING, pf=0.8, lookahead_blocks=24)
    ctrl = _controller({**HEAT_ROOM, "heating_system_type": "underfloor"}, heating_system_type="underfloor")
    assert ctrl._evaluate_mpc(20.9, TargetTemps(heat=21.0, cool=24.0)) == (MODE_HEATING, 0.8)


# --- optimizer: candidates are judged at the power they would get ------------------


def test_strong_device_below_target_is_not_left_idle():
    """Large learned Q (AC heating the air node): full-power look-ahead overshot the
    cool side of the band, so idle won and the room sat ~0.7 K below target."""
    model = RCModel(C=1.0, U=0.01, Q_heat=32.0, Q_cool=4.0)
    opt = MPCOptimizer(model=model, can_heat=True, can_cool=False, w_comfort=7.0, w_energy=3.0, min_run_blocks=2)
    n = 24
    plan = opt.optimize(
        T_room=20.4,
        T_outdoor_series=[0.0] * n,
        heat_target_series=[21.0] * n,
        cool_target_series=[24.5] * n,
        dt_minutes=5,
    )
    assert plan.actions[0] == MODE_HEATING
    assert plan.power_fractions[0] < 1.0


def test_hypothesis_power_fraction():
    model = RCModel(C=1.0, U=0.05, Q_heat=10.0, Q_cool=10.0)
    opt = MPCOptimizer(model=model, can_heat=True, can_cool=True)
    kw = {"q_solar": 0.0, "q_residual": 0.0, "q_occupancy": 0.0}
    below = opt._hypothesis_power_fraction(MODE_HEATING, 20.8, 5.0, 21.0, 5.0, **kw)
    assert 0.0 < below < 1.0
    # at/above target there is no proportional answer -> full power, as before
    assert opt._hypothesis_power_fraction(MODE_HEATING, 22.0, 5.0, 21.0, 5.0, **kw) == 1.0
    # closed form answers with the other mode -> full power for this candidate
    assert opt._hypothesis_power_fraction(MODE_COOLING, 20.0, 5.0, 21.0, 5.0, **kw) == 1.0


def test_hybrid_ufh_and_ac_room_keeps_ufh_preheat(monkeypatch):
    """UFH + AC (auto): the optimizer keeps the base lookahead because the room can cool,
    but the UFH side is still slow and keeps its drift pre-heat (#131)."""
    _fake_plan(monkeypatch, MODE_HEATING, pf=0.8, lookahead_blocks=6)
    ctrl = _controller(
        {"climate_mode": "auto", "acs": ["climate.ac1"], "heating_system_type": "underfloor"},
        heating_system_type="underfloor",
    )
    assert ctrl._predict_idle_drift(21.0, 30.0) < 20.8
    assert ctrl._evaluate_mpc(21.0, TargetTemps(heat=21.0, cool=24.0)) == (MODE_HEATING, 0.8)


def test_radiator_counts_as_fast(monkeypatch):
    _fake_plan(monkeypatch, MODE_HEATING)
    ctrl = _controller({**HEAT_ROOM, "heating_system_type": "radiator"}, heating_system_type="radiator")
    assert ctrl._evaluate_mpc(20.9, TargetTemps(heat=21.0, cool=24.0)) == (MODE_IDLE, 0.0)


def _ac_state(modes):
    state = MagicMock()
    state.state = "off"
    state.attributes = {"hvac_modes": modes}
    return state


@pytest.mark.parametrize(
    ("ac_modes", "expected"),
    [(["off", "heat", "cool"], MODE_IDLE), (["off", "cool"], MODE_HEATING)],
)
def test_trv_room_with_a_heating_ac_uses_the_bang_bang_hysteresis(monkeypatch, ac_modes, expected):
    """TRV + heat pump: the AC heats along (orchestrated or not), so its air-node hysteresis applies."""
    _fake_plan(monkeypatch, MODE_HEATING)
    ctrl = _controller({"climate_mode": "auto", "acs": ["climate.ac1"]})
    ctrl.hass.states.get = MagicMock(return_value=_ac_state(ac_modes))
    mode, _ = ctrl._evaluate_mpc(20.8, TargetTemps(heat=21.0, cool=24.0))
    assert mode == expected


def test_cooling_min_run_is_the_ac_one_in_a_ufh_room():
    """A hybrid UFH + AC room must not keep the AC cooling for the 30-min UFH run time."""
    room = {"climate_mode": "auto", "acs": ["climate.ac1"], "heating_system_type": "underfloor"}
    after_ac_min_run = {"previous_mode": MODE_COOLING, "mode_on_since": time.time() - 15 * 60}
    ctrl = _controller(room, outdoor_temp=30.0, heating_system_type="underfloor", **after_ac_min_run)
    assert ctrl._within_min_run(MODE_COOLING) is False
    ctrl.previous_mode = MODE_HEATING
    assert ctrl._within_min_run(MODE_HEATING) is True


def test_optimizer_gets_the_ac_min_run_for_cooling(monkeypatch):
    """UFH + AC room: the optimizer plans cooling runs with the AC profile like the guard does."""
    seen: dict = {}
    real_init = MPCOptimizer.__init__

    def spy(self, *args, **kwargs):
        seen.update(kwargs)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(MPCOptimizer, "__init__", spy)
    _fake_plan(monkeypatch, MODE_IDLE)
    room = {"climate_mode": "auto", "acs": ["climate.ac1"], "heating_system_type": "underfloor"}
    ctrl = _controller(room, outdoor_temp=30.0, heating_system_type="underfloor")
    ctrl._evaluate_mpc(25.0, TargetTemps(heat=21.0, cool=24.0))
    assert seen["min_run_blocks"] == 6
    assert seen["cool_min_run_blocks"] == 2


# --- heat source orchestration: an AC heating alone in a UFH room -----------------

ORCH_UFH_ROOM = {
    "climate_mode": "heat_only",
    "acs": ["climate.ac1"],
    "heating_system_type": "underfloor",
    "heat_source_orchestration": True,
}


def _orchestrated(outdoor_temp: float, **kwargs) -> MPCController:
    ctrl = _controller(ORCH_UFH_ROOM, outdoor_temp=outdoor_temp, heating_system_type="underfloor", **kwargs)
    ac = MagicMock()
    ac.state = "off"
    ac.attributes = {"hvac_modes": ["off", "heat", "cool"]}
    trv = MagicMock()
    trv.state = "heat"
    trv.attributes = {"hvac_modes": ["off", "heat"]}
    ctrl.hass.states.get = MagicMock(side_effect=lambda eid: ac if eid == "climate.ac1" else trv)
    return ctrl


def test_ac_heating_alone_gets_the_ac_start_hysteresis(monkeypatch):
    """Mild weather, small gap: the orchestrator routes to the AC, so the AC's start
    hysteresis applies, not the UFH 'start whenever the optimizer says so'."""
    _fake_plan(monkeypatch, MODE_HEATING, lookahead_blocks=24)
    assert _orchestrated(10.0)._evaluate_mpc(20.9, TargetTemps(heat=21.0, cool=None)) == (MODE_IDLE, 0.0)
    # cold outside: the boiler/UFH side heats, UFH rules stay
    assert _orchestrated(0.0)._evaluate_mpc(20.9, TargetTemps(heat=21.0, cool=None))[0] == MODE_HEATING


def test_ac_heating_alone_uses_the_ac_min_run():
    after_ac_min_run = {"previous_mode": MODE_HEATING, "mode_on_since": time.time() - 15 * 60}
    ctrl = _orchestrated(10.0, previous_heat_sources="secondary", **after_ac_min_run)
    ctrl._resolve_run_system(21.0, 21.0)  # at target: the running sources decide
    assert ctrl._within_min_run(MODE_HEATING) is False
    ufh = _orchestrated(0.0, previous_heat_sources="primary", **after_ac_min_run)
    ufh._resolve_run_system(21.0, 21.0)
    assert ufh._within_min_run(MODE_HEATING) is True


def test_ac_heating_alone_does_not_preheat_on_drift(monkeypatch):
    """At the target, a UFH room may pre-heat on a predicted dip; an AC alone may not."""
    _fake_plan(monkeypatch, MODE_HEATING, pf=0.8, lookahead_blocks=24)
    ctrl = _orchestrated(10.0, previous_heat_sources="secondary")
    monkeypatch.setattr(ctrl, "_predict_idle_drift", lambda *_: 20.0)
    assert ctrl._evaluate_mpc(21.0, TargetTemps(heat=21.0, cool=None)) == (MODE_IDLE, 0.0)
    ufh = _orchestrated(0.0)
    monkeypatch.setattr(ufh, "_predict_idle_drift", lambda *_: 20.0)
    assert ufh._evaluate_mpc(21.0, TargetTemps(heat=21.0, cool=None)) == (MODE_HEATING, 0.8)


def test_a_run_from_idle_at_the_target_follows_the_source_that_would_heat(monkeypatch):
    """From idle at the target the source the orchestrator prefers sets the rules: on a mild
    day the AC would carry the run, so no drift pre-heat (it started the screed for one
    cycle, then the first 0.1 K dip handed the run to the AC); on a cold day the screed."""
    _fake_plan(monkeypatch, MODE_HEATING, pf=0.8, lookahead_blocks=24)
    mild = _orchestrated(10.0, previous_heat_sources="none")
    monkeypatch.setattr(mild, "_predict_idle_drift", lambda *_: 20.0)
    assert mild._evaluate_mpc(21.0, TargetTemps(heat=21.0, cool=None)) == (MODE_IDLE, 0.0)
    cold = _orchestrated(0.0, previous_heat_sources="none")
    monkeypatch.setattr(cold, "_predict_idle_drift", lambda *_: 20.0)
    assert cold._evaluate_mpc(21.0, TargetTemps(heat=21.0, cool=None)) == (MODE_HEATING, 0.8)


def test_ac_heating_alone_in_the_bang_bang_fallback():
    after_ac_min_run = {"previous_mode": MODE_HEATING, "mode_on_since": time.time() - 15 * 60}
    ctrl = _orchestrated(10.0, previous_heat_sources="secondary", **after_ac_min_run)
    assert ctrl._evaluate_bangbang(21.1, TargetTemps(heat=21.0, cool=None)) == MODE_IDLE
    ufh = _orchestrated(0.0, previous_heat_sources="primary", **after_ac_min_run)
    assert ufh._evaluate_bangbang(21.1, TargetTemps(heat=21.0, cool=None)) == MODE_HEATING


def _preheat_only_on_floor_rules(monkeypatch) -> list[str]:
    """The floor's rules start the pre-heat for a comfort block 30 min ahead, the AC's not yet."""
    systems: list[str] = []

    def optimize(self, *args, **kwargs):
        systems.append(self.heating_system_type)
        action = MODE_HEATING if self.heating_system_type == "underfloor" else MODE_IDLE
        return MPCPlan(
            actions=[action] * 24,
            temperatures=[19.5] * 25,
            power_fractions=[1.0 if action == MODE_HEATING else 0.0] * 24,
            lookahead_blocks=24,
        )

    monkeypatch.setattr(MPCOptimizer, "optimize", optimize)
    return systems


def _eco_then_comfort():
    switch = time.time() + 30 * 60
    return lambda ts: TargetTemps(heat=18.0 if ts < switch else 21.0, cool=None)


@pytest.mark.parametrize(
    ("outdoor", "expected_mode", "expected_systems"),
    [
        # mild: the AC alone would run the pre-heat, so the AC's rules decide (not yet),
        # from the first pass on (above the target in force the preferred source counts)
        (10.0, MODE_IDLE, [""]),
        # cold: the floor runs it, its rules stand
        (0.0, MODE_HEATING, ["underfloor"]),
    ],
)
def test_preheat_follows_the_rules_of_the_sources_that_run_it(monkeypatch, outdoor, expected_mode, expected_systems):
    """Above eco, before comfort: the target in force shows no gap, so the floor's rules
    applied; the orchestrator then sent the AC alone, whose rules stopped it again the next
    cycle (heat/off every 30 s)."""
    systems = _preheat_only_on_floor_rules(monkeypatch)
    ctrl = _orchestrated(outdoor, target_resolver=_eco_then_comfort())
    assert ctrl._evaluate_mpc(19.5, TargetTemps(heat=18.0, cool=None))[0] == expected_mode
    assert systems == expected_systems
    assert ctrl._run_system == expected_systems[-1]


def test_a_large_gap_to_the_lead_brings_back_the_floor_rules(monkeypatch):
    """Just below eco the AC alone would close the gap, but the run heats for comfort
    4 K up: both sources run it, so the floor's rules apply."""
    systems: list[str] = []

    def optimize(self, *args, **kwargs):
        systems.append(self.heating_system_type)
        return MPCPlan(
            actions=[MODE_HEATING] * 24, temperatures=[17.0] * 25, power_fractions=[1.0] * 24, lookahead_blocks=24
        )

    monkeypatch.setattr(MPCOptimizer, "optimize", optimize)
    ctrl = _orchestrated(10.0, target_resolver=_eco_then_comfort())
    assert ctrl._evaluate_mpc(16.9, TargetTemps(heat=18.0, cool=None))[0] == MODE_HEATING
    assert systems == ["", "underfloor"]
    assert ctrl._run_system == "underfloor"


def test_orchestration_without_ufh_keeps_the_room_rules():
    ctrl = _controller({**ORCH_UFH_ROOM, "heating_system_type": ""}, outdoor_temp=10.0)
    assert ctrl._resolve_run_system(20.0, 21.0) == ""


# --- bang-bang min run: no full boost far past the target ---------------------------


@pytest.mark.parametrize(
    ("temp", "expected"),
    [(20.5, (MODE_HEATING, 1.0)), (21.5, (MODE_HEATING, 1.0)), (22.0, (MODE_IDLE, 0.0))],
)
@pytest.mark.asyncio
async def test_bangbang_min_run_continues_up_to_the_ceiling(temp, expected):
    """Learning phase: a strong AC in a small room used to run its whole min run at full
    boost and overheat by 4-8 K before the compressor hold even started. Power stays
    binary so the EKF learns what the device delivers."""
    ctrl = _controller(**_within_min_run(MODE_HEATING))
    assert await ctrl.async_evaluate(temp, TargetTemps(heat=21.0, cool=24.0)) == expected


@pytest.mark.parametrize(
    ("temp", "expected"),
    [(24.5, (MODE_COOLING, 1.0)), (23.5, (MODE_COOLING, 1.0)), (23.0, (MODE_IDLE, 0.0))],
)
@pytest.mark.asyncio
async def test_bangbang_cooling_min_run_continues_up_to_the_ceiling(temp, expected):
    ctrl = _controller(COOL_ROOM, outdoor_temp=30.0, **_within_min_run(MODE_COOLING))
    assert await ctrl.async_evaluate(temp, TargetTemps(heat=None, cool=24.0)) == expected


@pytest.mark.asyncio
async def test_simple_mode_keeps_the_plain_min_run():
    """control_mode bangbang (Simple): plain on/off, the capped min run cycled IR ACs 3x as often."""
    room = make_room(climate_mode="heat_only")
    ctrl = MPCController(
        build_hass(),
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={"control_mode": "bangbang"},
        has_external_sensor=True,
        **_within_min_run(MODE_HEATING),
    )
    assert await ctrl.async_evaluate(22.5, TargetTemps(heat=21.0, cool=24.0)) == (MODE_HEATING, 1.0)


def test_prediction_bangbang_capped_only_while_learning():
    from custom_components.roommind.control.analytics_simulator import _simulate_bangbang

    model = RCModel(C=1.0, U=0.3, Q_heat=40.0, Q_cool=0.0)
    room = make_room(climate_mode="heat_only")
    kw = {"previous_mode": MODE_HEATING, "mode_elapsed_minutes": 0.0}
    forecast = [{"target_temp": 21.0, "heat_target": 21.0, "cool_target": 24.0}] * 2
    capped = _simulate_bangbang(model, forecast, [5.0] * 2, 22.5, room, [], **kw)
    plain = _simulate_bangbang(model, forecast, [5.0] * 2, 22.5, room, [], capped=False, **kw)
    assert plain[0] > capped[0]


@pytest.mark.asyncio
async def test_slow_heating_room_keeps_the_plain_min_run_while_learning():
    """UFH + split: the capped learning runs left the screed idle for hours on one seed."""
    ctrl = _controller(
        {"climate_mode": "heat_only", "heating_system_type": "underfloor"},
        heating_system_type="underfloor",
        **_within_min_run(MODE_HEATING),
    )
    assert await ctrl.async_evaluate(22.5, TargetTemps(heat=21.0, cool=24.0)) == (MODE_HEATING, 1.0)


@pytest.mark.parametrize(("ac_modes", "expected"), [(["off", "heat", "cool"], True), (["off", "cool"], False)])
def test_optimizer_knows_when_a_heating_ac_shares_the_model(monkeypatch, ac_modes, expected):
    seen: dict = {}
    real_init = MPCOptimizer.__init__

    def spy(self, *args, **kwargs):
        seen.update(kwargs)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(MPCOptimizer, "__init__", spy)
    _fake_plan(monkeypatch, MODE_IDLE)
    room = {"climate_mode": "auto", "acs": ["climate.ac1"], "heating_system_type": "underfloor"}
    ctrl = _controller(room, heating_system_type="underfloor")
    ctrl.hass.states.get = MagicMock(return_value=_ac_state(ac_modes))
    ctrl._evaluate_mpc(20.0, TargetTemps(heat=21.0, cool=None))
    assert seen["fast_heater_shares_model"] is expected


def test_run_rules_follow_the_price_choice_of_a_price_aware_room():
    """Expensive electricity hands a mild-day run to the floor heating: its rules must apply,
    else the AC's 10-min rules would stop the floor every few cycles."""
    assert _orchestrated(12.0)._resolve_run_system(20.5, 21.0) == ""
    assert _orchestrated(12.0, price_level="expensive")._resolve_run_system(20.5, 21.0) == "underfloor"


def test_cheap_electricity_in_the_cold_leaves_a_preheat_to_the_primary_rules():
    """Frost, cheap hour: the AC takes a small gap, a pre-heat towards comfort stays with the
    floor, and so do its run rules (same answer as the coordinator's orchestration)."""
    assert _orchestrated(0.0, price_level="cheap")._resolve_run_system(20.5, 21.0) == ""
    assert _orchestrated(0.0, price_level="cheap")._resolve_run_system(19.0, 21.0) == "underfloor"
    running_floor = _orchestrated(0.0, price_level="cheap", previous_heat_sources="primary")
    assert running_floor._resolve_run_system(20.5, 21.0) == "underfloor"
