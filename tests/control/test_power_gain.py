"""Heat of the devices on a room's power sensors in the thermal model (beta_p)."""

from __future__ import annotations

import math

import pytest

from custom_components.roommind.control.thermal_model import RCModel, RoomModelManager, ThermalEKF

# ---------------------------------------------------------------------------
# RCModel
# ---------------------------------------------------------------------------


def test_rc_model_power_adds_heat():
    model = RCModel(C=1.0, U=0.2, Q_power=2.0)
    without = model.predict(20.0, 10.0, 0.0, 60.0)
    with_power = model.predict(20.0, 10.0, 0.0, 60.0, q_power=0.5)
    # T_eq rises by Q_power * q_power / U = 5 K, reached by 1 - exp(-0.2) in an hour
    assert with_power - without == pytest.approx(5.0 * (1 - math.exp(-0.2)))


def test_rc_model_power_trajectory_follows_series():
    model = RCModel(C=1.0, U=0.2, Q_power=2.0)
    flat = model.predict_trajectory(20.0, [10.0] * 3, [0.0] * 3, 60.0)
    powered = model.predict_trajectory(20.0, [10.0] * 3, [0.0] * 3, 60.0, q_power_series=[0.5])
    assert powered[1] > flat[1]
    # the series ends after the first step: no power afterwards
    assert powered[2] - powered[1] < powered[1] - powered[0]


def test_rc_model_power_serialization():
    model = RCModel(Q_power=1.25)
    assert RCModel.from_dict(model.to_dict()).Q_power == 1.25
    assert RCModel.from_dict({"U": 1.0}).Q_power == RCModel.DEFAULT_Q_POWER
    assert RCModel.from_dict({"Q_power": -3.0}).Q_power == 0.0
    assert "Q_power=1.2" in repr(model)


# ---------------------------------------------------------------------------
# EKF
# ---------------------------------------------------------------------------


def test_ekf_get_model_maps_beta_p():
    ekf = ThermalEKF()
    ekf._x[7] = 1.75
    assert ekf.get_model().Q_power == 1.75
    assert "beta_p=1.8" in repr(ekf) or "beta_p=1.7" in repr(ekf)


def _jacobian(ekf: ThermalEKF, alpha: float, q_power: float):
    return ekf._compute_jacobian(20.0, alpha, 0.0, 10.0, 0.05, "idle", q_power=q_power)


def test_ekf_jacobian_power_term_both_branches():
    ekf = ThermalEKF()
    assert _jacobian(ekf, 0.15, 0.4)[0][7] == pytest.approx(0.4 / 0.15 * (1 - math.exp(-0.15 * 0.05)))
    assert _jacobian(ekf, 0.001, 0.4)[0][7] == pytest.approx(0.4 * 0.05)
    assert _jacobian(ekf, 0.15, 0.0)[0][7] == 0.0


@pytest.mark.parametrize(
    ("mode", "q_power", "learns"),
    [("idle", 0.4, True), ("cooling", 0.4, True), ("heating", 0.4, False), ("idle", 0.01, False), ("idle", 0.0, False)],
)
def test_ekf_beta_p_learns_only_from_real_load_without_heating(mode, q_power, learns):
    ekf = ThermalEKF()
    ekf._initialized = True
    p77 = ekf._P[7][7]
    ekf._predict_step(10.0, mode, 0.05, q_power=q_power)
    assert ekf._excited[7] is learns
    assert (ekf._P[7][7] > p77) is learns


@pytest.mark.parametrize(
    ("alpha", "q_power", "teaches"),
    [(0.15, 0.0, True), (0.001, 0.0, True), (0.15, 0.4, False), (0.001, 0.4, False), (0.15, 0.01, True)],
)
def test_residual_teaches_beta_h_only_without_metered_device_heat(alpha, q_power, teaches):
    """After a run the PC heat and the afterglow rise together: beta_h must not take the PC's share."""
    ekf = ThermalEKF()
    F = ekf._compute_jacobian(20.0, alpha, 0.0, 10.0, 0.05, "idle", q_residual=0.3, q_power=q_power)
    assert (F[0][2] != 0.0) is teaches


def test_residual_still_warms_the_prediction_while_devices_run():
    ekf = ThermalEKF(T_init=20.0)
    ekf._initialized = True
    p22 = ekf._P[2][2]
    without = ThermalEKF(T_init=20.0)
    without._initialized = True
    ekf._predict_step(20.0, "idle", 0.5, q_residual=0.3, q_power=0.4)
    without._predict_step(20.0, "idle", 0.5, q_power=0.4)
    assert ekf._x[0] > without._x[0]
    assert ekf._excited[2] is False
    assert ekf._P[2][2] == pytest.approx(p22)


def test_ekf_power_heat_enters_prediction():
    ekf = ThermalEKF(T_init=20.0)
    ekf._initialized = True
    ekf._x[7] = 4.0
    ekf._predict_step(20.0, "idle", 0.5, q_power=0.5)
    # Room at outdoor temperature: only the device heat moves it
    assert ekf._x[0] > 20.0


def test_ekf_learns_beta_p_from_a_metered_load():
    """A 400 W device on half the time; the filter finds its gain."""
    true_alpha, true_beta_p = 0.12, 2.5
    model = RCModel(C=1.0, U=true_alpha, Q_power=true_beta_p)
    ekf = ThermalEKF(T_init=20.0)
    T = 20.0
    for step in range(2000):
        q_power = 0.4 if (step // 40) % 2 == 0 else 0.0
        T_out = 5.0 + 3.0 * math.sin(step / 200.0)
        T = model.predict(T, T_out, 0.0, 3.0, q_power=q_power)
        ekf.update(T, T_out, "idle", 3.0, q_power=q_power)
    assert ekf._x[7] == pytest.approx(true_beta_p, rel=0.2)
    assert ekf._x[1] == pytest.approx(true_alpha, rel=0.2)


def test_ekf_beta_p_clamped():
    ekf = ThermalEKF()
    ekf._x[7] = 99.0
    ekf._clamp_parameters()
    assert ekf._x[7] == ThermalEKF._BETA_P_MAX
    ekf._x[7] = -1.0
    ekf._clamp_parameters()
    assert ekf._x[7] == ThermalEKF._BETA_P_MIN


def test_prediction_std_counts_power_uncertainty():
    ekf = ThermalEKF()
    assert ekf.prediction_std(0.0, 20.0, 10.0, 60.0, q_power=1.0) > ekf.prediction_std(0.0, 20.0, 10.0, 60.0)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_ekf_persists_beta_p_beside_the_older_layouts():
    ekf = ThermalEKF()
    ekf._x[6] = 12.0
    ekf._x[7] = 1.4
    ekf._P[7][0] = ekf._P[0][7] = 0.2
    ekf._P[7][6] = ekf._P[6][7] = 0.05
    data = ekf.to_dict()
    assert data["ekf_version"] == 7
    # an older release reads 6 entries in x/P and a beta_f row of 7
    assert len(data["x"]) == 6
    assert len(data["beta_f"]["P"]) == 7
    assert len(data["beta_p"]["P"]) == 8
    restored = ThermalEKF.from_dict(data)
    assert restored._x[6] == pytest.approx(12.0)
    assert restored._x[7] == pytest.approx(1.4)
    assert restored._P[0][7] == pytest.approx(0.2)
    assert restored._P[6][7] == restored._P[7][6] == pytest.approx(0.05)


def test_ekf_from_v6_data_keeps_beta_f_and_defaults_beta_p():
    """Saved by the release before beta_p: beta_f's row has 7 entries."""
    old = ThermalEKF()
    old._x[6] = 21.0
    old._P[6][6] = 3.0
    data = old.to_dict()
    data["ekf_version"] = 6
    data["beta_f"] = {"x": 21.0, "P": [0.0] * 6 + [3.0]}
    del data["beta_p"]
    ekf = ThermalEKF.from_dict(data)
    assert ekf._x[6] == pytest.approx(21.0)
    assert ekf._P[6][6] == pytest.approx(3.0)
    assert ekf._x[7] == ThermalEKF._DEFAULT_BETA_P
    assert ekf._P[7][7] == ThermalEKF._P_INIT_BETA_P


@pytest.mark.parametrize(
    "beta_p",
    [None, "bad", {"x": "bad", "P": [0.0] * 8}, {"x": 2.0, "P": [0.0] * 7}, {"x": 2.0, "P": ["a"] * 8}],
)
def test_ekf_malformed_beta_p_keeps_default(beta_p):
    data = ThermalEKF().to_dict()
    data["beta_p"] = beta_p
    assert ThermalEKF.from_dict(data)._x[7] == ThermalEKF._DEFAULT_BETA_P


def test_ekf_from_full_8d_lists():
    ekf = ThermalEKF()
    ekf._x[7] = 3.0
    data = {"x": list(ekf._x), "P": [list(r) for r in ekf._P]}
    assert ThermalEKF.from_dict(data)._x[7] == pytest.approx(3.0)


def test_recovery_reset_restores_beta_p_default():
    data = {
        "ekf_version": 5,
        "x": [20.0, 2.0, 3.0, 4.0, 0.5, 0.3],
        "P": [[0.5 if i == j else 0.0 for j in range(6)] for i in range(6)],
        "beta_p": {"x": 9.0, "P": [0.0] * 7 + [1.0]},
        "n_updates": 100,
    }
    ekf = ThermalEKF.from_dict(data)
    assert ekf._x[7] == ThermalEKF._DEFAULT_BETA_P
    assert ekf._P[7][7] == ThermalEKF._P_INIT_BETA_P


# ---------------------------------------------------------------------------
# RoomModelManager
# ---------------------------------------------------------------------------


def test_manager_forwards_power():
    mgr = RoomModelManager()
    mgr.update("living", 20.0, 10.0, "idle", 3.0)
    est = mgr.get_estimator("living")
    p77 = est._P[7][7]
    mgr.update("living", 20.1, 10.0, "idle", 3.0, q_power=0.5)
    assert est._P[7][7] != p77
    assert mgr.get_prediction_std("living", 0.0, 20.0, 10.0, 60.0, q_power=1.0) > mgr.get_prediction_std(
        "living", 0.0, 20.0, 10.0, 60.0
    )


# ---------------------------------------------------------------------------
# MPC
# ---------------------------------------------------------------------------


def test_power_decay_series():
    from custom_components.roommind.const import POWER_GAIN_DECAY_H
    from custom_components.roommind.control.mpc_optimizer import power_decay_series

    series = power_decay_series(0.5, 24, 5.0)
    assert len(series) == 24
    # each block holds the mean of the decay over it; the first one starts at the reading
    k = 5.0 / 60.0 / POWER_GAIN_DECAY_H
    assert series[0] == pytest.approx(0.5 * (1 - math.exp(-k)) / k)
    assert series[12] == pytest.approx(series[0] * math.exp(-1.0 / POWER_GAIN_DECAY_H))
    assert all(a > b for a, b in zip(series, series[1:], strict=False))
    assert power_decay_series(0.0, 24, 5.0) == []
    assert power_decay_series(0.5, 0, 5.0) == []


@pytest.mark.parametrize("alpha", [0.25, 0.005])
def test_compute_optimal_power_counts_device_heat(alpha):
    from custom_components.roommind.control.mpc_optimizer import MPCOptimizer

    # strong heater, room just below target: a proportional answer, not full power
    opt = MPCOptimizer(RCModel(C=1.0, U=alpha, Q_heat=10.0, Q_cool=10.0, Q_power=4.0))
    pf_without, _ = opt.compute_optimal_power(20.5, 5.0, 21.0, 5.0)
    pf_with, _ = opt.compute_optimal_power(20.5, 5.0, 21.0, 5.0, q_power=0.5)
    assert 0.0 < pf_with < pf_without < 1.0


def test_optimizer_heats_less_while_devices_run():
    from custom_components.roommind.control.mpc_optimizer import MPCOptimizer, power_decay_series

    opt = MPCOptimizer(RCModel(C=1.0, U=0.2, Q_heat=3.0, Q_cool=3.0, Q_power=4.0), can_heat=True, can_cool=False)
    common = dict(T_room=20.5, T_outdoor_series=[5.0] * 24, heat_target_series=[21.0] * 24, dt_minutes=5)
    without = opt.optimize(**common)
    with_power = opt.optimize(**common, power_series=power_decay_series(0.6, 24, 5.0))
    assert sum(with_power.power_fractions) < sum(without.power_fractions)
    # the replay with the same series reproduces the plan, without it the room ends cooler
    series = power_decay_series(0.6, 24, 5.0)
    assert opt.simulate_plan(with_power, 20.5, [5.0] * 24, 5, power_series=series) == with_power.temperatures
    assert opt.simulate_plan(with_power, 20.5, [5.0] * 24, 5)[-1] < with_power.temperatures[-1]


def _power_controller(q_power: float):
    from unittest.mock import MagicMock

    from custom_components.roommind.control.mpc_controller import MPCController
    from tests.control.conftest import build_hass, make_room

    mgr = RoomModelManager()
    mgr.get_model = MagicMock(return_value=RCModel(C=1.0, U=0.25, Q_heat=1.0, Q_cool=1.0, Q_power=3.0))
    return MPCController(
        build_hass(),
        make_room(),
        model_manager=mgr,
        outdoor_temp=24.0,
        settings={},
        has_external_sensor=True,
        q_power=q_power,
    )


def test_shading_peak_excludes_device_heat():
    """Covers cannot counter a running PC: the cover logic reads a peak without it (#418)."""
    from custom_components.roommind.const import TargetTemps

    running = _power_controller(0.5)
    idle = _power_controller(0.0)
    running._evaluate_mpc(22.0, TargetTemps(heat=21.0, cool=24.0))
    idle._evaluate_mpc(22.0, TargetTemps(heat=21.0, cool=24.0))
    assert running.last_plan is not None and idle.last_plan is not None
    # the control plan sees the device heat ...
    assert max(running.last_plan.temperatures[1:]) > max(idle.last_plan.temperatures[1:])
    # ... the shading peak does not
    assert running.predicted_peak_temp == pytest.approx(idle.predicted_peak_temp, abs=0.05)
    assert idle._peak_temps_unoccupied is None


def test_idle_drift_and_gentle_power_see_device_heat():
    running = _power_controller(0.5)
    idle = _power_controller(0.0)
    assert running._predict_idle_drift(20.0, 60.0) > idle._predict_idle_drift(20.0, 60.0)


def test_valve_demand_counts_device_heat():
    """A valve held by RoomMind (#413) opens less while metered devices heat the room."""
    from custom_components.roommind.control.mpc_controller import valve_demand

    model = RCModel(C=1.0, U=0.1, Q_heat=4.0, Q_power=2.0)
    without = valve_demand(model, 21.0, 1.0, 21.0, q_solar=0.0, q_occupancy=0.0)
    with_power = valve_demand(model, 21.0, 1.0, 21.0, q_solar=0.0, q_occupancy=0.0, q_power=0.5)
    assert with_power == pytest.approx(without - 2.0 * 0.5 / 4.0)
