"""Pre-cooling towards a stricter cool target ahead runs at the power the plan judged it by (#450)."""

from __future__ import annotations

import types
from unittest.mock import MagicMock

from custom_components.roommind.const import MODE_COOLING, MODE_HEATING, MODE_IDLE, TargetTemps
from custom_components.roommind.control import mpc_controller as mc
from custom_components.roommind.control.mpc_controller import MPCController
from custom_components.roommind.control.mpc_optimizer import MPCOptimizer
from custom_components.roommind.control.thermal_model import RCModel, RoomModelManager
from tests.control.conftest import build_hass, make_room

START = 1_800_000_000.0
WEAK_AC = RCModel(C=1.0, U=0.1, Q_heat=3.0, Q_cool=3.0)


def _closed_loop(monkeypatch, steps=36):
    clock = {"now": START}
    monkeypatch.setattr(mc, "time", types.SimpleNamespace(time=lambda: clock["now"]))
    hass = build_hass()
    st = MagicMock()
    st.state = "off"
    st.attributes = {"hvac_modes": ["off", "cool"]}
    hass.states.get = MagicMock(return_value=st)
    room = make_room(climate_mode="cool_only", thermostats=[], acs=["climate.ac"])
    mgr = RoomModelManager()
    monkeypatch.setattr(mgr, "get_model", lambda _a: WEAK_AC)

    def resolver(ts):  # eco 27 °C, comfort 24 °C from +1 h
        return TargetTemps(heat=None, cool=27.0 if ts < START + 3600 else 24.0)

    prev, on_since, T = MODE_IDLE, None, 26.5
    log = []
    for _ in range(steps):
        ctrl = MPCController(
            hass,
            room,
            model_manager=mgr,
            outdoor_temp=32.0,
            settings={},
            previous_mode=prev,
            mode_on_since=on_since,
            has_external_sensor=True,
            target_resolver=resolver,
        )
        monkeypatch.setattr(ctrl, "_build_solar_series", lambda n: [0.0] * n)
        mode, pf = ctrl._evaluate_mpc(T, resolver(clock["now"]))
        Q = pf * WEAK_AC.Q_heat if mode == MODE_HEATING else -(pf * WEAK_AC.Q_cool) if mode == MODE_COOLING else 0.0
        T = WEAK_AC.predict(T, 32.0, Q, 5.0)
        log.append((mode, round(pf, 2), round(T, 2)))
        on_since = clock["now"] if (mode != MODE_IDLE and prev != mode) else (None if mode == MODE_IDLE else on_since)
        prev = mode
        clock["now"] += 300
    return log


def test_precool_reaches_the_comfort_target(monkeypatch):
    log = _closed_loop(monkeypatch)
    lead = [entry for entry in log[:12] if entry[0] == MODE_COOLING]
    print("lead window:", lead)
    print("T at +1h:", log[11][2], "+1h30:", log[17][2], "+2h:", log[23][2], "+3h:", log[35][2])
    # v1.7.9: pre-cool at pf 1.0 from +35 min, 26.81 -> 25.80 at +1 h, 24.64 at +1 h 30
    # #450:   pre-cool at pf 0.15 from +35 min, 26.81 -> 26.84 at +1 h, 25.63 at +1 h 30
    # deadline: full power from the start, 24.17 at +1 h (the 3 K/h unit needs the whole hour)
    first = next(i for i, entry in enumerate(log) if entry[0] == MODE_COOLING)
    assert first == 0, "waiting would miss the comfort target, so the pre-cool starts at once"
    assert log[11][2] < 24.3, "the room is near the comfort target when it starts"


def test_hypothesis_and_applied_power_agree():
    """The greedy step judges COOLING at full power, optimize() then applies 0.15."""
    opt = MPCOptimizer(WEAK_AC, can_heat=False, can_cool=True)
    n = 48
    cool = [27.0] * 3 + [24.0] * (n - 3)
    plan = opt.optimize(
        T_room=26.8,
        T_outdoor_series=[32.0] * n,
        heat_target_series=[min(26.8, c) for c in cool],
        cool_target_series=cool,
        dt_minutes=5,
    )
    judged = opt._hypothesis_power_fraction(
        MODE_COOLING, 26.8, 32.0, 27.0, 5, q_solar=0.0, q_residual=0.0, q_occupancy=0.0
    )
    print("action", plan.actions[0], "applied pf", plan.power_fractions[0], "judged pf", judged)
    assert plan.actions[0] == MODE_COOLING
    assert plan.power_fractions[0] == judged
