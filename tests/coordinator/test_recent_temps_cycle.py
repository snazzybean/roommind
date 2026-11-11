"""The coordinator feeds the short series the dashboard cards draw."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get


@pytest.mark.asyncio
async def test_cycle_records_recent_temps_and_seeds_from_history(hass, mock_config_entry):
    store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(side_effect=make_mock_states_get())
    hass.services.async_call = AsyncMock()

    coordinator = _create_coordinator(hass, mock_config_entry)
    history = MagicMock()
    history.read_detail = MagicMock(return_value=[])
    coordinator._history_store = history
    await coordinator._async_update_data()

    series = coordinator.recent_temps.get("living_room_abc12345")
    assert len(series) == 1
    assert series[0][1] == 18.0
    history.read_detail.assert_called_once()

    await coordinator._async_update_data()
    history.read_detail.assert_called_once()


@pytest.mark.asyncio
async def test_seed_failure_does_not_break_the_cycle(hass, mock_config_entry):
    store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(side_effect=make_mock_states_get())
    hass.services.async_call = AsyncMock()

    coordinator = _create_coordinator(hass, mock_config_entry)
    history = MagicMock()
    history.read_detail = MagicMock(side_effect=OSError("disk"))
    coordinator._history_store = history
    data = await coordinator._async_update_data()

    assert "living_room_abc12345" in data["rooms"]
    assert len(coordinator.recent_temps.get("living_room_abc12345")) == 1


@pytest.mark.asyncio
async def test_forget_room_clears_recent_temps(hass, mock_config_entry):
    coordinator = _create_coordinator(hass, mock_config_entry)
    coordinator.recent_temps.add("gone", 1000.0, 20.0, 21.0)
    registry = MagicMock()
    registry.entities.values.return_value = []
    with patch("homeassistant.helpers.entity_registry.async_get", return_value=registry):
        coordinator._forget_room("gone")
    assert coordinator.recent_temps.get("gone") == []
