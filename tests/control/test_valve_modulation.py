"""Rooms with direct valve control hold the valve instead of switching on and off (#413)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.roommind.const import MIN_POWER_FRACTION, VALVE_PROPORTIONAL_BAND_K
from custom_components.roommind.control.mpc_controller import (
    HARD_OVERSHOOT_CEILING,
    MODE_COOLING,
    MODE_HEATING,
    MODE_IDLE,
    MPCController,
    decide_mpc_action,
    is_valve_modulating,
    valve_demand,
)
from custom_components.roommind.control.thermal_model import RCModel, RoomModelManager

from .conftest import build_hass, make_room

TRV = {
    "entity_id": "climate.trv",
    "type": "trv",
    "valve_opening_entity": "number.trv_open",
    "valve_closing_entity": "number.trv_close",
}
PLAIN_TRV = {"entity_id": "climate.trv2", "type": "trv"}
AC = {"entity_id": "climate.ac", "type": "ac"}


def test_is_valve_modulating():
    assert is_valve_modulating([TRV], False, True)
    assert is_valve_modulating([TRV, AC], False, True)  # AC only cools
    assert not is_valve_modulating([TRV], False, False)  # Managed Mode
    assert not is_valve_modulating([TRV, AC], True, True)  # AC heats too
    assert not is_valve_modulating([TRV, PLAIN_TRV], False, True)
    assert not is_valve_modulating([AC], False, True)


def _decide(action, pf, temp, *, previous=MODE_HEATING, demand=0.3, heat=None, slow=False, in_min_run=False):
    heat = heat or [21.0] * 12
    return decide_mpc_action(
        action,
        pf,
        temp,
        heat,
        [24.0] * 12,
        guard_blocks=6,
        slow_heat=slow,
        previous_mode=previous,
        heat_in_min_run=in_min_run,
        cool_in_min_run=False,
        can_heat=True,
        can_cool=True,
        heat_hysteresis=0.1,
        idle_drift=lambda minutes: temp,
        continuation_power=lambda mode, target: MIN_POWER_FRACTION,
        valve_demand=None if demand is None else (lambda target: demand),
    )


def test_running_valve_holds_at_the_target_where_a_setpoint_trv_stops():
    assert _decide(MODE_IDLE, 0.0, 21.05, demand=None) == (MODE_IDLE, 0.0)
    assert _decide(MODE_IDLE, 0.0, 21.05, demand=0.3) == (MODE_HEATING, 0.3)


def test_running_valve_stops_once_the_room_needs_no_heat():
    assert _decide(MODE_HEATING, 1.0, 21.2, demand=0.0) == (MODE_IDLE, 0.0)


def test_below_target_the_valve_keeps_at_least_the_minimum():
    assert _decide(MODE_IDLE, 0.0, 20.95, demand=0.0) == (MODE_HEATING, MIN_POWER_FRACTION)
    assert _decide(MODE_HEATING, 1.0, 20.5, demand=0.6) == (MODE_HEATING, 0.6)


def test_rising_target_keeps_the_optimizers_preheat_power():
    rising = [21.0] * 3 + [22.0] * 9
    assert _decide(MODE_HEATING, 1.0, 21.0, demand=0.3, heat=rising) == (MODE_HEATING, 1.0)


def test_valve_closes_half_a_kelvin_above_the_target_whatever_the_model_says():
    assert _decide(MODE_IDLE, 0.0, 21.5, demand=0.9) == (MODE_IDLE, 0.0)
    assert _decide(MODE_IDLE, 0.0, 21.45, demand=0.9) == (MODE_HEATING, 0.9)


def test_hard_ceiling_still_ends_a_valve_run():
    assert _decide(MODE_HEATING, 1.0, 21.0 + HARD_OVERSHOOT_CEILING + 0.1, demand=0.5) == (MODE_IDLE, 0.0)


def test_valve_start_runs_at_the_demand_not_at_full_power():
    assert _decide(MODE_HEATING, 1.0, 20.7, previous=MODE_IDLE, demand=0.25) == (MODE_HEATING, 0.25)
    assert _decide(MODE_HEATING, 1.0, 20.7, previous=MODE_IDLE, demand=0.0) == (MODE_HEATING, MIN_POWER_FRACTION)


def test_valve_start_still_waits_for_the_hysteresis():
    assert _decide(MODE_HEATING, 1.0, 20.95, previous=MODE_IDLE, demand=0.3) == (MODE_IDLE, 0.0)


def test_slow_systems_keep_their_rules():
    assert _decide(MODE_IDLE, 0.0, 21.05, demand=0.3, slow=True) == (MODE_IDLE, 0.0)


def test_cooling_decision_is_left_alone():
    assert _decide(MODE_COOLING, 0.5, 24.5, demand=0.3) == (MODE_COOLING, 0.5)


def _controller(devices, *, has_external_sensor=True, settings=None):
    room = make_room()
    room["devices"] = devices
    room["thermostats"] = [d["entity_id"] for d in devices if d["type"] == "trv"]
    hass = build_hass()
    hass.states.get = MagicMock(return_value=None)
    return MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings=settings or {},
        has_external_sensor=has_external_sensor,
    )


def test_valve_demand_is_holding_power_plus_a_proportional_term():
    model = RCModel(C=1.0, U=0.1, Q_heat=4.0, Q_solar=2.0, Q_occupancy=0.4)
    # Holding 21 °C at 1 °C outside: 0.1 * 20 = 2 K/h of 4 K/h
    assert valve_demand(model, 21.0, 1.0, 21.0, q_solar=0.0, q_occupancy=0.0) == pytest.approx(0.5)
    below = valve_demand(model, 20.8, 1.0, 21.0, q_solar=0.0, q_occupancy=0.0)
    assert below == pytest.approx(0.5 + 0.2 / VALVE_PROPORTIONAL_BAND_K)
    # Sun and people cover part of the losses
    assert valve_demand(model, 21.0, 1.0, 21.0, q_solar=0.5, q_occupancy=1.0) == pytest.approx(0.15)
    # Far above the target, or no learned heating power: nothing
    assert valve_demand(model, 22.0, 1.0, 21.0, q_solar=0.0, q_occupancy=0.0) == 0.0
    assert valve_demand(RCModel(Q_heat=0.0), 20.0, 1.0, 21.0, q_solar=0.0, q_occupancy=0.0) == 0.0
    # Saturates at a fully open valve
    assert valve_demand(model, 19.0, 1.0, 21.0, q_solar=0.0, q_occupancy=0.0) == 1.0


@pytest.mark.asyncio
async def test_controller_passes_the_valve_demand(monkeypatch):
    seen = {}

    def fake_decide(*args, **kwargs):
        seen["valve_demand"] = kwargs.get("valve_demand")
        return MODE_IDLE, 0.0

    monkeypatch.setattr("custom_components.roommind.control.mpc_controller.decide_mpc_action", fake_decide)
    from custom_components.roommind.const import TargetTemps

    for devices, expected in (([TRV], True), ([PLAIN_TRV], False)):
        ctrl = _controller(devices)
        ctrl._evaluate_mpc(20.5, TargetTemps(heat=21.0, cool=24.0))
        assert (seen["valve_demand"] is not None) is expected
        if expected:
            assert 0.0 <= seen["valve_demand"](21.0) <= 1.0
