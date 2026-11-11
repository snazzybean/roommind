"""Model trace in the observer (learned EKF state per room every few minutes)."""

from __future__ import annotations

from types import SimpleNamespace

from ha_component.simhome.runtime import model_snapshot


def _estimator() -> SimpleNamespace:
    n = 3
    p = [[0.5 if i == j else 0.01 * (i + j) for j in range(n)] for i in range(n)]
    return SimpleNamespace(
        _x=[20.123456, 0.0123456, 0.51234],
        _P=p,
        _n_updates=42,
        _err_sum=1.23456,
        _err_n=7,
        prediction_std=lambda *a, **k: 0.212345,
    )


def test_snapshot_lists_state_covariance_and_error_sums():
    coordinator = SimpleNamespace(_model_manager=SimpleNamespace(_estimators={"kueche": _estimator()}))
    snap = model_snapshot(coordinator)["kueche"]
    assert snap["x"] == [20.12, 0.01235, 0.5123]
    assert snap["pd"] == [0.5, 0.5, 0.5]
    assert snap["p0"] == [0.5, 0.01, 0.02]
    assert snap["p12"] == 0.03
    assert (snap["n"], snap["err_sum"], snap["err_n"], snap["std_h"]) == (42, 1.2346, 7, 0.2123)


def test_snapshot_without_model_manager_is_empty():
    assert model_snapshot(SimpleNamespace()) == {}
