"""One-hour backtest of the room model on recorded history."""

from __future__ import annotations

from custom_components.roommind.control.thermal_model import RCModel
from custom_components.roommind.services.model_backtest import (
    MIN_BACKTEST_WINDOWS,
    backtest,
)

TRUTH = RCModel(U=0.05, Q_heat=1.5, Q_cool=1.0, Q_solar=0.8, Q_occupancy=0.2)


def _history(
    hours: float = 6.0,
    step_s: float = 300.0,
    model: RCModel = TRUTH,
    power=lambda k: 1.0 if (k // 6) % 3 == 0 else 0.0,
    window=lambda k: False,
) -> list[dict]:
    """A room driven by *model* with the recorded inputs, one row every *step_s*."""
    points = []
    T = 20.0
    for k in range(int(hours * 3600 / step_s) + 1):
        share = power(k)
        p = {
            "ts": 1_000_000.0 + k * step_s,
            "room_temp": round(T, 3),
            "outdoor_temp": 5.0,
            "window_open": window(k),
            "model_power": share,
            "model_solar": 0.3,
            "model_residual": 0.0,
            "model_occupancy": 1.0,
        }
        points.append(p)
        dt = step_s / 60.0
        if p["window_open"]:
            T = model.predict_window_open(T, 5.0, 3.0, dt)
        else:
            Q = share * (model.Q_heat if share > 0 else model.Q_cool)
            T = model.predict(T, 5.0, Q, dt, q_solar=0.3, q_occupancy=1.0, q_rebound=0.0)
    return points


def test_the_true_model_is_almost_exact():
    result = backtest(_history(), TRUTH, 3.0)
    figures = result.figures()
    assert figures["horizon_minutes"] == 60
    assert figures["active"]["mae"] < 0.01
    assert figures["idle"]["n"] + figures["active"]["n"] == len(result.predicted)
    # The first hour has no reading an hour before
    assert min(result.predicted) >= 1_000_000.0 + 3600


def test_a_wrong_model_shows_its_error_and_its_direction():
    wrong = RCModel(U=0.05, Q_heat=0.75, Q_cool=1.0, Q_solar=0.8, Q_occupancy=0.2)
    figures = backtest(_history(), wrong, 3.0).figures()
    # Half the heating rate: the room ends up warmer than the model says
    assert figures["active"]["mae"] > 0.1
    assert figures["active"]["bias"] < -0.1


def test_hours_without_heating_count_as_idle():
    figures = backtest(_history(power=lambda k: 0.0), TRUTH, 3.0).figures()
    assert figures["active"]["n"] == 0
    assert figures["idle"]["mae"] < 0.01
    assert figures["active"]["mae"] is None


def test_cooling_counts_as_active():
    figures = backtest(_history(power=lambda k: -1.0 if k % 4 == 0 else 0.0), TRUTH, 3.0).figures()
    assert figures["active"]["n"] > 0
    assert figures["active"]["mae"] < 0.01


def test_rows_without_model_inputs_break_the_chain():
    points = _history()
    for p in points[30:40]:
        p["model_power"] = None
    result = backtest(points, TRUTH, 3.0)
    # No hour may run across the unknown rows
    for ts in result.predicted:
        start = ts - 3600
        assert not any(start <= p["ts"] < ts and p["model_power"] is None for p in points)
    assert points[35]["ts"] not in result.predicted


def test_a_gap_breaks_the_chain():
    points = _history()
    for p in points[40:]:
        p["ts"] += 3600
    result = backtest(points, TRUTH, 3.0)
    assert points[40]["ts"] not in result.predicted
    assert points[40 + 12]["ts"] in result.predicted


def test_open_windows_are_drawn_but_not_counted():
    points = _history(window=lambda k: 20 <= k < 24)
    result = backtest(points, TRUTH, 3.0)
    assert points[24]["ts"] in result.predicted
    assert abs(result.predicted[points[24]["ts"]] - points[24]["room_temp"]) < 0.01
    counted = result.idle.n + result.active.n
    assert counted < len(result.predicted)


def test_too_few_hours_show_no_figure():
    points = _history(hours=1.0 + (MIN_BACKTEST_WINDOWS - 2) * 300 / 3600)
    figures = backtest(points, TRUTH, 3.0).figures()
    assert figures["active"]["n"] + figures["idle"]["n"] < MIN_BACKTEST_WINDOWS
    assert figures["active"]["mae"] is None and figures["idle"]["mae"] is None


def test_nothing_to_compute():
    assert backtest([], TRUTH, 3.0).predicted == {}
    assert backtest(_history(), RCModel(U=0.0), 3.0).predicted == {}


def test_missing_readings_are_skipped():
    points = _history()
    points[50]["room_temp"] = None
    result = backtest(points, TRUTH, 3.0)
    assert points[50]["ts"] not in result.predicted
