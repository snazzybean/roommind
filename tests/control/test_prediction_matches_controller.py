"""The analytics prediction must follow the controller's decisions step by step.

Before, ``_simulate_mpc`` had its own run rules (heat on until the target at full
power, min run at full power, no start hysteresis, drift pre-heat for every
system), so the prediction line showed runs RoomMind never makes. Both now share
``decide_mpc_action``; these tests drive the real controller in a closed loop and
compare it with the prediction on identical inputs.
"""

from __future__ import annotations

import types
from unittest.mock import MagicMock

import pytest

from custom_components.roommind.const import MODE_COOLING, MODE_HEATING, MODE_IDLE, TargetTemps
from custom_components.roommind.control import mpc_controller as mc
from custom_components.roommind.control.analytics_simulator import _simulate_mpc
from custom_components.roommind.control.mpc_controller import MPCController
from custom_components.roommind.control.residual_heat import compute_residual_heat
from custom_components.roommind.control.thermal_model import RCModel, RoomModelManager

from .conftest import build_hass, make_room

START = 1_800_000_000.0
STEPS = 36  # 3 h


def _closed_loop(
    monkeypatch,
    model: RCModel,
    room: dict,
    *,
    T0: float,
    targets: TargetTemps,
    outdoor: float,
    heating_system_type: str = "",
    previous_mode: str = MODE_IDLE,
    elapsed_minutes: float | None = None,
    ac_modes: list[str] | None = None,
    outdoor_known: bool = True,
) -> list[float]:
    """Run the controller every 5 min like the coordinator does and return the temperatures."""
    clock = {"now": START}
    monkeypatch.setattr(mc, "time", types.SimpleNamespace(time=lambda: clock["now"]))
    hass = build_hass()
    if ac_modes is not None:
        ac_state = MagicMock()
        ac_state.state = "off"
        ac_state.attributes = {"hvac_modes": ac_modes}
        hass.states.get = MagicMock(return_value=ac_state)
    manager = RoomModelManager()
    monkeypatch.setattr(manager, "get_model", lambda _area: model)

    prev = previous_mode
    on_since = START - elapsed_minutes * 60 if previous_mode != MODE_IDLE and elapsed_minutes is not None else None
    T = T0
    temps: list[float] = []
    # Residual heat bookkeeping as the prediction does it (the coordinator's tracker
    # differs in detail: last real power fraction instead of 1.0)
    q_residual = 0.0
    heating_blocks = 0
    since_stop = 0.0
    was_heating = False
    for _ in range(STEPS):
        ctrl = MPCController(
            hass,
            room,
            model_manager=manager,
            outdoor_temp=outdoor if outdoor_known else None,
            settings={},
            previous_mode=prev,
            mode_on_since=on_since,
            has_external_sensor=True,
            heating_system_type=heating_system_type,
            q_residual=q_residual,
        )
        monkeypatch.setattr(ctrl, "_build_solar_series", lambda n: [0.0] * n)
        mode, pf = ctrl._evaluate_mpc(T, targets)
        Q = pf * model.Q_heat if mode == MODE_HEATING else -(pf * model.Q_cool) if mode == MODE_COOLING else 0.0
        T = max(5.0, min(40.0, model.predict(T, outdoor, Q, 5.0, q_residual=q_residual if Q == 0.0 else 0.0)))
        temps.append(round(T, 2))
        if mode == MODE_HEATING:
            heating_blocks += 1
            was_heating = True
            since_stop = 0.0
            q_residual = 0.0
        else:
            since_stop += 5.0
            if heating_system_type and was_heating:
                q_residual = compute_residual_heat(since_stop, heating_system_type, 1.0, heating_blocks * 5.0)
        if mode != MODE_IDLE and prev != mode:
            on_since = clock["now"]
        elif mode == MODE_IDLE:
            on_since = None
        prev = mode
        clock["now"] += 300
    return temps


def _prediction(
    model: RCModel,
    room: dict,
    *,
    T0: float,
    targets: TargetTemps,
    outdoor: float,
    heating_system_type: str = "",
    previous_mode: str = MODE_IDLE,
    elapsed_minutes: float | None = None,
    acs_can_heat: bool = False,
    outdoor_known: bool = True,
) -> list[float]:
    # Long enough that the controller's horizon never runs past the forecast
    n = STEPS + 400
    forecast = [{"target_temp": targets.heat, "heat_target": targets.heat, "cool_target": targets.cool}] * n
    return _simulate_mpc(
        model,
        forecast,
        [outdoor] * n,
        T0,
        room,
        {},
        acs_can_heat=acs_can_heat,
        heating_system_type=heating_system_type,
        previous_mode=previous_mode,
        mode_elapsed_minutes=elapsed_minutes,
        outdoor_known=outdoor_known,
    )[:STEPS]


TRV = RCModel(C=1.0, U=0.3, Q_heat=10.0, Q_cool=0.0)
AC = RCModel(C=1.0, U=0.3, Q_heat=20.0, Q_cool=20.0)
UFH = RCModel(C=1.0, U=0.2, Q_heat=6.0, Q_cool=0.0)
SLOW_UFH = RCModel(C=1.0, U=0.02, Q_heat=2.0, Q_cool=0.0)
# Tight room: the drift towards the 10 °C placeholder alone does not bring it to the target
TIGHT_AC = RCModel(C=1.0, U=0.02, Q_heat=20.0, Q_cool=20.0)


@pytest.mark.parametrize(
    ("label", "model", "room", "kwargs"),
    [
        ("trv inside the hysteresis", TRV, {"climate_mode": "heat_only"}, {"T0": 20.95}),
        ("trv below the hysteresis", TRV, {"climate_mode": "heat_only"}, {"T0": 20.0}),
        (
            "trv run in progress",
            TRV,
            {"climate_mode": "heat_only"},
            {"T0": 20.95, "previous_mode": MODE_HEATING, "elapsed_minutes": 3.0},
        ),
        (
            "trv run past min run, unknown start",
            TRV,
            {"climate_mode": "heat_only"},
            {"T0": 21.05, "previous_mode": MODE_HEATING},
        ),
        ("radiator", TRV, {"climate_mode": "heat_only", "heating_system_type": "radiator"}, {"T0": 20.5}),
        (
            "ufh at target, cold outside",
            UFH,
            {"climate_mode": "heat_only", "heating_system_type": "underfloor"},
            {"T0": 21.0, "outdoor": -5.0},
        ),
        ("ufh below target", UFH, {"climate_mode": "heat_only", "heating_system_type": "underfloor"}, {"T0": 20.0}),
        (
            "ufh start penalty at the target",
            SLOW_UFH,
            {"climate_mode": "heat_only", "heating_system_type": "underfloor"},
            {"T0": 21.1, "outdoor": 10.0},
        ),
        (
            "ac heating",
            AC,
            {"climate_mode": "heat_only", "thermostats": [], "acs": ["climate.ac"]},
            {"T0": 20.85, "ac": True},
        ),
        (
            "ac cooling",
            AC,
            {"climate_mode": "cool_only", "thermostats": [], "acs": ["climate.ac"]},
            {"T0": 24.6, "outdoor": 30.0, "targets": TargetTemps(heat=None, cool=24.0)},
        ),
        (
            "ac cooling run in progress",
            AC,
            {"climate_mode": "cool_only", "thermostats": [], "acs": ["climate.ac"]},
            {
                "T0": 24.05,
                "outdoor": 30.0,
                "targets": TargetTemps(heat=None, cool=24.0),
                "previous_mode": MODE_COOLING,
                "elapsed_minutes": 2.0,
            },
        ),
        (
            # #464: without a reading or forecast the series is the 10 °C placeholder,
            # which must not gate cooling in the prediction either
            "ac cooling without an outdoor reading",
            TIGHT_AC,
            {"climate_mode": "cool_only", "thermostats": [], "acs": ["climate.ac"]},
            {
                "T0": 26.0,
                "outdoor": mc.DEFAULT_OUTDOOR_TEMP_FALLBACK,
                "outdoor_known": False,
                "targets": TargetTemps(heat=None, cool=24.0),
            },
        ),
        (
            "hard ceiling ends a run",
            TRV,
            {"climate_mode": "heat_only"},
            {"T0": 22.5, "previous_mode": MODE_HEATING, "elapsed_minutes": 1.0},
        ),
        ("valve below the hysteresis", TRV, {"climate_mode": "heat_only", "valve": True}, {"T0": 20.0}),
        (
            "valve holding at the target",
            TRV,
            {"climate_mode": "heat_only", "valve": True},
            {"T0": 21.0, "outdoor": -5.0, "previous_mode": MODE_HEATING, "elapsed_minutes": 30.0},
        ),
    ],
)
def test_prediction_follows_the_controller(monkeypatch, label, model, room, kwargs):
    kwargs = dict(kwargs)
    is_ac = kwargs.pop("ac", False)
    common = {
        "T0": kwargs.pop("T0"),
        "targets": kwargs.pop("targets", TargetTemps(heat=21.0, cool=24.0)),
        "outdoor": kwargs.pop("outdoor", 5.0),
        "heating_system_type": room.get("heating_system_type", ""),
        **kwargs,
    }
    room = dict(room)
    valve = room.pop("valve", False)
    room_config = make_room(**room)
    if valve:
        for device in room_config["devices"]:
            device["valve_opening_entity"] = "number.valve_opening_degree"
            device["valve_closing_entity"] = "number.valve_closing_degree"
    has_ac = bool(room_config.get("acs"))
    real = _closed_loop(
        monkeypatch,
        model,
        room_config,
        ac_modes=["off", "heat", "cool"] if has_ac else None,
        **common,
    )
    predicted = _prediction(model, room_config, acs_can_heat=has_ac or is_ac, **common)
    assert predicted == real, label
    if not common.get("outdoor_known", True):
        assert real[0] < common["T0"] - 0.5, "the controller must actually cool"


def test_prediction_without_the_controller_rules_would_differ(monkeypatch):
    """Guards the comparison itself: inside the hysteresis band the controller idles,
    where a bare optimizer heats (the old prediction)."""
    room = make_room(climate_mode="heat_only")
    real = _closed_loop(monkeypatch, TRV, room, T0=20.95, targets=TargetTemps(heat=21.0, cool=24.0), outdoor=5.0)
    monkeypatch.setattr(
        "custom_components.roommind.control.analytics_simulator.decide_mpc_action",
        lambda action, pf, *a, **kw: (action, pf),
    )
    bare = _prediction(TRV, room, T0=20.95, targets=TargetTemps(heat=21.0, cool=24.0), outdoor=5.0)
    assert bare != real


def test_valve_room_holds_where_a_setpoint_room_switches():
    """The valve rule changes the prediction: a steadier room around the target (#413)."""
    setpoint_room = make_room(climate_mode="heat_only")
    valve_room = make_room(climate_mode="heat_only")
    valve_room["devices"][0]["valve_opening_entity"] = "number.valve_opening_degree"
    valve_room["devices"][0]["valve_closing_entity"] = "number.valve_closing_degree"
    common = {
        "T0": 21.0,
        "targets": TargetTemps(heat=21.0, cool=24.0),
        "outdoor": -5.0,
        "previous_mode": MODE_HEATING,
        "elapsed_minutes": 30.0,
    }
    setpoint = _prediction(TRV, setpoint_room, **common)
    valve = _prediction(TRV, valve_room, **common)
    assert max(valve) - min(valve) < max(setpoint) - min(setpoint)
