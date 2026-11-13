"""The inputs the EKF learned from are kept per room and written to the history (backtest)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.roommind.const import HISTORY_WRITE_CYCLES

from .conftest import _create_coordinator, _make_store_mock, make_mock_states_get
from .test_ghost_heating_guard import _room_for_guard


def _states(action: str):
    return make_mock_states_get(
        temp="19.5",
        humidity="55.0",
        schedule_state="on",
        outdoor_temp="5.0",
        extra={
            "climate.living_room": (
                "heat",
                {"hvac_action": action, "current_temperature": 19.5, "temperature": 21.0},
            ),
        },
    )


async def _run(hass, entry, action: str, settings: dict | None = None):
    room = _room_for_guard()
    store = _make_store_mock({room["area_id"]: room})
    if settings:
        store.get_settings.return_value = settings
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(side_effect=_states(action))
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, entry)
    history = MagicMock()
    coordinator._history_store = history
    coordinator._history_write_count = HISTORY_WRITE_CYCLES - 1
    await coordinator._async_update_data()
    records = [c for c in hass.async_add_executor_job.call_args_list if c[0] and c[0][0] is history.record]
    return coordinator, room["area_id"], records


@pytest.mark.asyncio
async def test_a_heating_run_records_the_delivered_share(hass, mock_config_entry):
    coordinator, area_id, records = await _run(hass, mock_config_entry, "heating")
    inputs = coordinator._model_inputs[area_id]
    # The device reports heating: delivered share 1.0, whatever share was commanded
    assert inputs["model_power"] == 1.0
    assert set(inputs) == {"model_power", "model_solar", "model_residual", "model_occupancy"}
    assert records[0][0][2]["model_power"] == 1.0


@pytest.mark.asyncio
async def test_the_ghost_heating_guard_records_idle(hass, mock_config_entry):
    coordinator, area_id, records = await _run(hass, mock_config_entry, "idle")
    assert coordinator._model_inputs[area_id]["model_power"] == 0.0
    assert coordinator._model_inputs[area_id]["model_residual"] == 0.0


@pytest.mark.asyncio
async def test_no_inputs_while_the_room_does_not_learn(hass, mock_config_entry):
    room_id = _room_for_guard()["area_id"]
    coordinator, area_id, records = await _run(
        hass, mock_config_entry, "heating", settings={"learning_disabled_rooms": [room_id]}
    )
    assert area_id not in coordinator._model_inputs


def test_an_unknown_training_mode_records_nothing(hass, mock_config_entry):
    hass.data = {"roommind": {"store": _make_store_mock({})}}
    coordinator = _create_coordinator(hass, mock_config_entry)
    coordinator._model_inputs["room"] = {"model_power": 1.0}
    coordinator._note_model_inputs("room", None, 0.0, None, 0.0, 0.0)
    assert "room" not in coordinator._model_inputs
    coordinator._note_model_inputs("room", "cooling", 0.5, None, 0.0, 1.0)
    assert coordinator._model_inputs["room"]["model_power"] == -0.5
    assert coordinator._model_inputs["room"]["model_solar"] == 0.0
