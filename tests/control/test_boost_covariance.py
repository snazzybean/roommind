"""Learn faster: ThermalEKF.boost_covariance widens the parameter variances, keeping correlations."""

from __future__ import annotations

import copy
import math
import random

import pytest

from custom_components.roommind.control.thermal_model import RoomModelManager, ThermalEKF

ALPHA = 0.015  # 1/h, ~67 h time constant like the sim's radiator rooms
T_OUT = 2.0


def _run(ekf: ThermalEKF, hours: float, beta_h: float, rng: random.Random, T: float) -> float:
    """Room with heating 6 h on / 6 h off: 3-min steps, 0.03 K sensor noise."""
    steps = int(hours * 20)
    for k in range(steps):
        heating = (k // 120) % 2 == 0
        u = beta_h if heating else 0.0
        T += (u - ALPHA * (T - T_OUT)) * 0.05
        ekf.update(T + rng.gauss(0.0, 0.03), T_OUT, "heating" if heating else "idle", 3.0)
    return T


@pytest.fixture
def settled() -> tuple[ThermalEKF, float]:
    rng = random.Random(7)
    ekf = ThermalEKF()
    T = _run(ekf, 96, 0.8, rng, 19.0)
    return ekf, T


def _corr(P: list[list[float]], i: int, j: int) -> float:
    return P[i][j] / math.sqrt(P[i][i] * P[j][j])


def test_boost_widens_parameter_variances_and_keeps_correlations(settled):
    ekf, _ = settled
    before = copy.deepcopy(ekf._P)
    ekf.boost_covariance()
    P = ekf._P
    assert P[0][0] == pytest.approx(before[0][0])
    for i in (1, 2):
        assert P[i][i] == pytest.approx(before[i][i] * 2.5)
    for i, j in ((0, 1), (0, 2), (1, 2)):
        assert _corr(P, i, j) == pytest.approx(_corr(before, i, j))


def test_boost_never_raises_a_variance_past_its_initial_value(settled):
    ekf, _ = settled
    p_init = ekf._p_init_diag()
    # beta_c never learned in a heating-only room: already at its initial variance
    assert ekf._P[3][3] == pytest.approx(p_init[3])
    for _ in range(20):
        ekf.boost_covariance()
    for i in range(1, ekf._N):
        assert ekf._P[i][i] <= p_init[i] * (1 + 1e-9)
    assert ekf._P[3][3] == pytest.approx(p_init[3])


def test_boosted_model_stays_good_enough_for_mpc(settled):
    """The old floor (0.3 x initial variance) pushed the heating forecast std past 0.5 (MPC off)."""
    ekf, T = settled
    conf = ekf.confidence
    ekf.boost_covariance()
    assert ekf.prediction_std(ekf._x[2], T, T_OUT, 5.0) < 0.5
    assert ekf.confidence > conf - 0.1


def test_one_noisy_reading_after_the_boost_does_not_throw_alpha_around(settled):
    """Old boost: a 0.05 K reading moved alpha by its whole value (sim: 0.014 -> 0.035)."""
    ekf, T = settled
    ekf.boost_covariance()
    alpha = ekf._x[1]
    probe = copy.deepcopy(ekf)
    probe._predict_step(T_OUT, "idle", 0.05)
    ekf.update(probe._x[0] - 0.05, T_OUT, "idle", 3.0)
    assert abs(ekf._x[1] - alpha) < 0.25 * alpha


def test_boost_follows_a_bigger_radiator_at_least_as_fast(settled):
    ekf, T = settled
    plain = copy.deepcopy(ekf)
    ekf.boost_covariance()
    rng_a, rng_b = random.Random(3), random.Random(3)
    _run(plain, 6, 1.6, rng_a, T)
    _run(ekf, 6, 1.6, rng_b, T)
    assert abs(ekf._x[2] - 1.6) <= abs(plain._x[2] - 1.6)
    assert ekf._x[2] == pytest.approx(1.6, rel=0.3)


def test_manager_boost_without_a_model_returns_none_and_creates_none():
    mgr = RoomModelManager()
    assert mgr.boost_learning("kitchen") is None
    assert "kitchen" not in mgr._estimators


def test_manager_boost_widens_the_rooms_estimator_and_returns_its_update_count(settled):
    ekf, _ = settled
    mgr = RoomModelManager()
    mgr._estimators["kitchen"] = ekf
    before = copy.deepcopy(ekf._P)
    assert mgr.boost_learning("kitchen") == ekf._n_updates
    assert ekf._n_updates > 0
    assert ekf._P[1][1] == pytest.approx(before[1][1] * 2.5)
