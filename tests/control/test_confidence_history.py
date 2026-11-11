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
    data["confidence_history"] = [["2026-11-09", 0.5, 10, False], "junk", [1, 2], ["2026-11-10", "x", 1, True]]
    assert ThermalEKF.from_dict(data).confidence_history == [["2026-11-09", 0.5, 10, False]]
    del data["confidence_history"]
    assert ThermalEKF.from_dict(data).confidence_history == []


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
