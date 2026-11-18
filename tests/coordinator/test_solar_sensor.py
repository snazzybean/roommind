"""A room's sun sensor feeds every consumer of the room's solar input (#303)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind import coordinator as coordinator_module
from custom_components.roommind.const import HISTORY_WRITE_CYCLES
from custom_components.roommind.managers.solar_sensor_manager import RoomSolar

from .conftest import _create_coordinator, _make_store_mock
from .test_ghost_heating_guard import _room_for_guard
from .test_model_inputs import _states

SUN = RoomSolar(
    q_now=0.6,
    q_effective=0.12,
    measured=True,
    latitude=52.5,
    longitude=13.4,
    now=0.0,
    profile=(1.0,) * 24,
    deviation=1.0,
)


async def _cycle(hass, entry, sensor: str, room_solar: RoomSolar | None):
    room = {**_room_for_guard(), "solar_sensor": sensor}
    store = _make_store_mock({room["area_id"]: room})
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(side_effect=_states("heating"))
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, entry)
    coordinator._history_store = MagicMock()
    coordinator._history_write_count = HISTORY_WRITE_CYCLES - 1
    coordinator._solar_sensors.update = MagicMock(return_value=room_solar)
    training = MagicMock()
    coordinator._ekf_training.process = training
    cover = AsyncMock(wraps=coordinator._cover_orchestrator.async_process)
    coordinator._cover_orchestrator.async_process = cover
    controllers: list[dict] = []
    real = coordinator_module.MPCController

    def _controller(*args, **kwargs):
        controllers.append(kwargs)
        return real(*args, **kwargs)

    with patch.object(coordinator_module, "MPCController", side_effect=_controller):
        await coordinator._async_update_data()
    return coordinator, room["area_id"], training, cover, controllers


@pytest.mark.asyncio
async def test_the_sensor_input_reaches_training_controller_covers_and_history(hass, mock_config_entry):
    coordinator, area_id, training, cover, controllers = await _cycle(hass, mock_config_entry, "sensor.sun", SUN)
    update = coordinator._solar_sensors.update.call_args[0]
    assert update[0] == area_id and update[1] == "sensor.sun"
    # Already behind the covers: trained as it is, not shaded again
    kwargs = training.call_args.kwargs
    assert kwargs["q_solar"] == 0.12 and kwargs["shading_factor"] == 1.0
    assert coordinator._model_inputs[area_id]["model_solar"] == 0.12
    assert controllers[0]["q_solar"] == 0.6 and controllers[0]["room_solar"] is SUN
    assert cover.call_args.kwargs["q_solar"] == 0.6 and cover.call_args.kwargs["room_solar"] is SUN
    state = coordinator.rooms[area_id]
    assert state["solar_input"] == 0.12
    assert coordinator.room_solar(area_id) is SUN


@pytest.mark.asyncio
async def test_without_a_sensor_everything_runs_on_the_weather_model(hass, mock_config_entry):
    coordinator, area_id, training, cover, controllers = await _cycle(hass, mock_config_entry, "", None)
    q = coordinator._current_q_solar
    kwargs = training.call_args.kwargs
    assert kwargs["q_solar"] == q and kwargs["shading_factor"] == 1.0
    assert controllers[0]["q_solar"] == q and controllers[0]["room_solar"] is None
    assert cover.call_args.kwargs["room_solar"] is None
    # Nothing new in the room state of a room without one (the sim compares it record by record)
    assert "solar_input" not in coordinator.rooms[area_id]
    assert "solar_sensor" not in coordinator.rooms[area_id]
    assert coordinator.room_solar(area_id) is None


@pytest.mark.asyncio
async def test_a_calibration_is_saved_at_once(hass, mock_config_entry):
    coordinator, area_id, *_ = await _cycle(hass, mock_config_entry, "sensor.sun", None)
    store = hass.data["roommind"]["store"]
    store.async_save_settings.reset_mock()
    coordinator._solar_sensors.dirty = True
    with patch.object(coordinator._solar_sensors, "get_state", return_value={"x": 1}):
        await coordinator._async_update_data()
    store.async_save_settings.assert_any_call({"solar_sensor_state": {"x": 1}})
    assert not coordinator._solar_sensors.dirty


@pytest.mark.asyncio
async def test_removing_the_room_forgets_its_sensor_input(hass, mock_config_entry):
    coordinator, area_id, *_ = await _cycle(hass, mock_config_entry, "sensor.sun", SUN)
    registry = MagicMock()
    registry.entities = {}
    with patch("homeassistant.helpers.entity_registry.async_get", return_value=registry):
        await coordinator.async_room_paused(area_id)
    assert coordinator.room_solar(area_id) is None


@pytest.mark.asyncio
async def test_a_new_sensor_shows_it_is_learning(hass, mock_config_entry):
    room = {**_room_for_guard(), "solar_sensor": "sensor.sun"}
    store = _make_store_mock({room["area_id"]: room})
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(side_effect=_states("heating"))
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    await coordinator._async_update_data()
    state = coordinator.rooms[room["area_id"]]
    assert state["solar_sensor"]["state"] == "learning"
    assert "solar_input" not in state
