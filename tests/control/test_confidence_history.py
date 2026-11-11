"""Daily confidence snapshots for the analytics model chart."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.roommind.control.thermal_model import CONFIDENCE_HISTORY_DAYS, ThermalEKF


def test_same_day_replaces_new_day_appends():
    ekf = ThermalEKF()
    ekf.note_confidence_day("2026-11-10", False)
    ekf.note_confidence_day("2026-11-10", True)
    ekf.note_confidence_day("2026-11-11", True)
    hist = ekf.confidence_history
    assert [e[0] for e in hist] == ["2026-11-10", "2026-11-11"]
    assert hist[0][3] is True
    assert 0.0 <= hist[0][1] <= 1.0


def test_older_day_is_ignored_and_history_is_capped():
    ekf = ThermalEKF()
    for d in range(CONFIDENCE_HISTORY_DAYS + 5):
        ekf.note_confidence_day(f"2026-01-{d:03d}", False)
    ekf.note_confidence_day("2025-12-31", True)
    hist = ekf.confidence_history
    assert len(hist) == CONFIDENCE_HISTORY_DAYS
    assert hist[-1][0] == f"2026-01-{CONFIDENCE_HISTORY_DAYS + 4:03d}"


def test_roundtrip_and_tolerant_load():
    ekf = ThermalEKF()
    ekf.note_confidence_day("2026-11-11", True)
    restored = ThermalEKF.from_dict(ekf.to_dict())
    assert restored.confidence_history == ekf.confidence_history

    data = ekf.to_dict()
    data["confidence_history"] = [
        ["2026-11-08", 0.4, 5, False],
        ["2026-11-09", 0.5, 10, False, 0.07, 300],
        ["2026-11-10", 0.6, 12, True, "x", 3],
        "junk",
        [1, 2],
        ["2026-11-10", "x", 1, True],
    ]
    assert ThermalEKF.from_dict(data).confidence_history == [
        ["2026-11-08", 0.4, 5, False, None, 0],
        ["2026-11-09", 0.5, 10, False, 0.07, 300],
        ["2026-11-10", 0.6, 12, True, None, 0],
    ]
    del data["confidence_history"]
    assert ThermalEKF.from_dict(data).confidence_history == []


def _feed(ekf: ThermalEKF, temps: list[float]) -> None:
    for t in temps:
        ekf.update(t, 5.0, "idle", 3.0)


def test_day_entry_carries_the_mean_absolute_forecast_error():
    ekf = ThermalEKF(20.0)
    _feed(ekf, [20.0])  # first call only initialises
    assert ekf.to_dict()["forecast_error"]["n"] == 0
    preds = []
    for t in (20.2, 19.9, 20.1):
        preds.append(ekf.get_model().predict(ekf._x[0], 5.0, 0.0, 3.0))
        _feed(ekf, [t])
    expected = sum(abs(t - p) for t, p in zip((20.2, 19.9, 20.1), preds, strict=True)) / 3
    ekf.note_confidence_day("2026-11-11", False)
    entry = ekf.confidence_history[-1]
    assert entry[5] == 3
    assert entry[4] == pytest.approx(expected, abs=2e-3)


def test_outliers_stay_out_of_the_forecast_error():
    ekf = ThermalEKF(20.0)
    _feed(ekf, [20.0, 20.0, 20.0])
    _feed(ekf, [35.0])  # far past 4 sigma
    ekf.note_confidence_day("2026-11-11", False)
    assert ekf.confidence_history[-1][5] == 2
    assert ekf.confidence_history[-1][4] < 1.0


def test_new_day_closes_yesterday_and_starts_from_zero():
    ekf = ThermalEKF(20.0)
    _feed(ekf, [20.0, 20.1])
    ekf.note_confidence_day("2026-11-10", False)
    _feed(ekf, [20.3, 20.2])  # after the last note of the day, before midnight's
    ekf.note_confidence_day("2026-11-11", False)
    hist = ekf.confidence_history
    assert hist[0][5] == 3
    assert hist[1][4:] == [None, 0]
    _feed(ekf, [20.2])
    ekf.note_confidence_day("2026-11-11", False)
    assert ekf.confidence_history[1][5] == 1


def test_day_sums_survive_a_restart_but_not_into_the_next_day():
    ekf = ThermalEKF(20.0)
    _feed(ekf, [20.0, 20.1, 20.0])
    ekf.note_confidence_day("2026-11-10", False)
    restored = ThermalEKF.from_dict(ekf.to_dict())
    _feed(restored, [20.1])
    restored.note_confidence_day("2026-11-10", False)
    assert restored.confidence_history[-1][5] == 3

    again = ThermalEKF.from_dict(restored.to_dict())
    again.note_confidence_day("2026-11-11", False)
    assert [e[5] for e in again.confidence_history] == [3, 0]

    data = ekf.to_dict()
    data["forecast_error"] = {"day": 1, "sum": "x"}
    assert ThermalEKF.from_dict(data).to_dict()["forecast_error"] == {"day": None, "sum": 0.0, "n": 0}


@pytest.mark.asyncio
async def test_coordinator_notes_learned_rooms_on_thermal_save(hass, mock_config_entry):
    from custom_components.roommind.const import THERMAL_SAVE_CYCLES
    from tests.coordinator.conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get

    store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(side_effect=make_mock_states_get())
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    coordinator._model_manager.get_estimator("living_room_abc12345")
    coordinator._thermal_save_count = THERMAL_SAVE_CYCLES - 1
    await coordinator._async_update_data()

    hist = coordinator._model_manager.get_estimator("living_room_abc12345").confidence_history
    assert len(hist) == 1
    assert "outdoor" not in coordinator._model_manager.get_room_ids()
