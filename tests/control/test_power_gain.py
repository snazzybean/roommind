"""Heat of a room's metered devices as a known model input (u_device, degC/h), not a model state."""

from __future__ import annotations

import math

import pytest

from custom_components.roommind.control.thermal_model import RCModel, RoomModelManager, ThermalEKF

# ---------------------------------------------------------------------------
# RCModel
# ---------------------------------------------------------------------------


def test_rc_model_device_heat_adds_to_the_prediction():
    model = RCModel(C=1.0, U=0.2)
    without = model.predict(20.0, 10.0, 0.0, 60.0)
    with_device = model.predict(20.0, 10.0, 0.0, 60.0, u_device=1.0)
    # T_eq rises by u_device / U = 5 K, reached by 1 - exp(-0.2) in an hour
    assert with_device - without == pytest.approx(5.0 * (1 - math.exp(-0.2)))
    # below the usual load it cools: the input is signed
    assert model.predict(20.0, 10.0, 0.0, 60.0, u_device=-1.0) < without


def test_rc_model_device_trajectory_follows_series():
    model = RCModel(C=1.0, U=0.2)
    flat = model.predict_trajectory(20.0, [10.0] * 3, [0.0] * 3, 60.0)
    warmed = model.predict_trajectory(20.0, [10.0] * 3, [0.0] * 3, 60.0, u_device_series=[1.0])
    assert warmed[1] > flat[1]
    # the series ends after the first step: no device heat afterwards
    assert warmed[2] - warmed[1] < warmed[1] - warmed[0]


def test_rc_model_has_no_power_parameter():
    """Nothing about power sensors is stored with a room's model."""
    assert "Q_power" not in RCModel().to_dict()


# ---------------------------------------------------------------------------
# ThermalEKF: a known input, no state, no new stored field
# ---------------------------------------------------------------------------


def test_ekf_device_heat_moves_the_prediction_only():
    a, b = ThermalEKF(), ThermalEKF()
    for ekf in (a, b):
        ekf.update(20.0, 10.0, "idle", 3.0)
    a._predict_step(10.0, "idle", 0.5)
    b._predict_step(10.0, "idle", 0.5, u_device=2.0)
    assert b._x[0] > a._x[0]
    # the parameters are untouched by a known input
    assert b._x[1:] == a._x[1:]


def test_ekf_without_devices_is_unchanged():
    """u_device=0 is exactly the model without power sensors."""
    a, b = ThermalEKF(), ThermalEKF()
    for T in (20.0, 20.1, 20.05, 20.2, 20.15):
        a.update(T, 5.0, "idle", 3.0, q_solar=0.2)
        b.update(T, 5.0, "idle", 3.0, q_solar=0.2, u_device=0.0)
    assert a._x == b._x
    assert a._P == b._P
    stored_a, stored_b = a.to_dict(), b.to_dict()
    stored_a.pop("last_update_at")
    stored_b.pop("last_update_at")
    assert stored_a == stored_b


def test_ekf_stored_model_keeps_its_layout():
    data = ThermalEKF().to_dict()
    assert data["ekf_version"] == 6
    assert len(data["x"]) == 6
    assert not any("power" in k or k == "beta_p" for k in data)


def test_ekf_with_device_heat_does_not_book_it_on_the_room():
    """Told about the device heat, the EKF learns the room as without the device."""
    truth = RCModel(C=1.0, U=0.05, Q_heat=1.5)
    told, untold = ThermalEKF(), ThermalEKF()
    T = 20.0
    for k in range(400):
        on = (k // 40) % 2 == 0
        device = 0.6 if on else 0.0
        T_next = truth.predict(T, 5.0, 0.0, 3.0, u_device=device)
        told.update(T_next, 5.0, "idle", 3.0, u_device=device)
        untold.update(T_next, 5.0, "idle", 3.0)
        T = T_next
    told_err = abs(told.get_model().U - truth.U)
    untold_err = abs(untold.get_model().U - truth.U)
    assert told_err < untold_err


# ---------------------------------------------------------------------------
# RoomModelManager
# ---------------------------------------------------------------------------


def test_manager_forwards_device_heat():
    mgr = RoomModelManager()
    mgr.update("living", 20.0, 10.0, "idle", 3.0)
    before = mgr.get_estimator("living")._x[0]
    other = RoomModelManager()
    other.update("living", 20.0, 10.0, "idle", 3.0)
    mgr.update("living", 20.0, 10.0, "idle", 3.0, u_device=3.0)
    other.update("living", 20.0, 10.0, "idle", 3.0)
    # same measurement, but the warmer prediction leaves a smaller innovation behind
    assert mgr.get_estimator("living")._x[0] != other.get_estimator("living")._x[0]
    assert before is not None


# ---------------------------------------------------------------------------
# MPC
# ---------------------------------------------------------------------------


def test_device_heat_series():
    from custom_components.roommind.const import POWER_GAIN_DECAY_H
    from custom_components.roommind.control.mpc_optimizer import device_heat_series

    series = device_heat_series(0.5, 24, 5.0)
    assert len(series) == 24
    # each block holds the mean of the decay over it; the first one starts at the value now
    k = 5.0 / 60.0 / POWER_GAIN_DECAY_H
    assert series[0] == pytest.approx(0.5 * (1 - math.exp(-k)) / k)
    assert series[12] == pytest.approx(series[0] * math.exp(-1.0 / POWER_GAIN_DECAY_H))
    assert all(a > b for a, b in zip(series, series[1:], strict=False))
    # below the usual load it fades back up the same way
    assert device_heat_series(-0.5, 24, 5.0)[0] == pytest.approx(-series[0])
    assert device_heat_series(0.0, 24, 5.0) == []
    assert device_heat_series(0.5, 0, 5.0) == []


@pytest.mark.parametrize("alpha", [0.25, 0.005])
def test_compute_optimal_power_counts_device_heat(alpha):
    from custom_components.roommind.control.mpc_optimizer import MPCOptimizer

    # strong heater, room just below target: a proportional answer, not full power
    opt = MPCOptimizer(RCModel(C=1.0, U=alpha, Q_heat=10.0, Q_cool=10.0))
    pf_without, _ = opt.compute_optimal_power(20.5, 5.0, 21.0, 5.0)
    pf_with, _ = opt.compute_optimal_power(20.5, 5.0, 21.0, 5.0, u_device=2.0)
    assert 0.0 < pf_with < pf_without < 1.0


def test_optimizer_heats_less_while_devices_run():
    from custom_components.roommind.control.mpc_optimizer import MPCOptimizer, device_heat_series

    opt = MPCOptimizer(RCModel(C=1.0, U=0.2, Q_heat=3.0, Q_cool=3.0), can_heat=True, can_cool=False)
    common = dict(T_room=20.5, T_outdoor_series=[5.0] * 24, heat_target_series=[21.0] * 24, dt_minutes=5)
    series = device_heat_series(2.4, 24, 5.0)
    without = opt.optimize(**common)
    with_device = opt.optimize(**common, device_series=series)
    assert sum(with_device.power_fractions) < sum(without.power_fractions)
    # the replay with the same series reproduces the plan, without it the room ends cooler
    assert opt.simulate_plan(with_device, 20.5, [5.0] * 24, 5, device_series=series) == with_device.temperatures
    assert opt.simulate_plan(with_device, 20.5, [5.0] * 24, 5)[-1] < with_device.temperatures[-1]


def _device_controller(u_device: float):
    from unittest.mock import MagicMock

    from custom_components.roommind.control.mpc_controller import MPCController
    from tests.control.conftest import build_hass, make_room

    mgr = RoomModelManager()
    mgr.get_model = MagicMock(return_value=RCModel(C=1.0, U=0.25, Q_heat=1.0, Q_cool=1.0))
    return MPCController(
        build_hass(),
        make_room(),
        model_manager=mgr,
        outdoor_temp=24.0,
        settings={},
        has_external_sensor=True,
        u_device=u_device,
    )


def test_shading_peak_excludes_device_heat():
    """Covers cannot counter a running PC: the cover logic reads a peak without it (#418)."""
    from custom_components.roommind.const import TargetTemps

    running = _device_controller(1.5)
    idle = _device_controller(0.0)
    running._evaluate_mpc(22.0, TargetTemps(heat=21.0, cool=24.0))
    idle._evaluate_mpc(22.0, TargetTemps(heat=21.0, cool=24.0))
    assert running.last_plan is not None and idle.last_plan is not None
    # the control plan sees the device heat ...
    assert max(running.last_plan.temperatures[1:]) > max(idle.last_plan.temperatures[1:])
    # ... the shading peak does not
    assert running.predicted_peak_temp == pytest.approx(idle.predicted_peak_temp, abs=0.05)
    assert idle._peak_temps_unoccupied is None


def test_idle_drift_sees_device_heat():
    running = _device_controller(1.5)
    idle = _device_controller(0.0)
    assert running._predict_idle_drift(20.0, 60.0) > idle._predict_idle_drift(20.0, 60.0)


def test_valve_demand_counts_device_heat():
    """A valve held by RoomMind (#413) opens less while metered devices heat the room."""
    from custom_components.roommind.control.mpc_controller import valve_demand

    model = RCModel(C=1.0, U=0.1, Q_heat=4.0)
    without = valve_demand(model, 21.0, 1.0, 21.0, q_solar=0.0, q_occupancy=0.0)
    with_device = valve_demand(model, 21.0, 1.0, 21.0, q_solar=0.0, q_occupancy=0.0, u_device=1.0)
    assert with_device == pytest.approx(without - 1.0 / 4.0)
