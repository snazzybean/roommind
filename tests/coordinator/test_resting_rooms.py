"""Rooms whose Home Assistant area was deleted rest in the coordinator cycle (#494)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.const import TargetTemps
from custom_components.roommind.utils.area_utils import REST_SWITCHED_OFF

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get

AREA_REGISTRY = "custom_components.roommind.utils.area_utils.ar.async_get"


def _registry(*area_ids: str) -> MagicMock:
    registry = MagicMock()
    registry.async_list_areas.return_value = [SimpleNamespace(id=a) for a in area_ids]
    return registry


def _resting_room(**extra) -> dict:
    return {
        **SAMPLE_ROOM,
        "area_id": "old_room",
        "devices": [
            {"entity_id": "climate.old_trv", "type": "trv", "role": "auto", "heating_system_type": ""},
            {"entity_id": "climate.living_room", "type": "trv", "role": "auto", "heating_system_type": ""},
        ],
        **extra,
    }


def _coordinator(hass, entry, rooms: dict):
    store = _make_store_mock(rooms)
    store.async_update_room = AsyncMock()
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(side_effect=make_mock_states_get())
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, entry)
    coordinator._async_switch_devices_off = AsyncMock()
    coordinator._async_release_valves = AsyncMock()
    return coordinator, store


@pytest.mark.asyncio
async def test_a_resting_room_is_not_controlled(hass, mock_config_entry):
    coordinator, _ = _coordinator(
        hass, mock_config_entry, {"living_room": SAMPLE_ROOM, "old_room": _resting_room(**{REST_SWITCHED_OFF: True})}
    )

    with patch(AREA_REGISTRY, return_value=_registry("living_room")):
        data = await coordinator._async_update_data()

    assert set(data["rooms"]) == {"living_room"}
    coordinator._async_switch_devices_off.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_room_starting_to_rest_switches_its_own_devices_off_once(hass, mock_config_entry):
    coordinator, store = _coordinator(
        hass, mock_config_entry, {"living_room": SAMPLE_ROOM, "old_room": _resting_room()}
    )
    coordinator.rooms = {"old_room": {"heat_target": 21.0, "cool_target": 24.0}}

    with patch(AREA_REGISTRY, return_value=_registry("living_room")):
        await coordinator._async_update_data()

    # The living room still drives its own thermostat, the resting room only lets go of its own
    coordinator._async_switch_devices_off.assert_awaited_once_with(
        "old_room",
        [{"entity_id": "climate.old_trv", "type": "trv", "role": "auto", "heating_system_type": ""}],
        TargetTemps(heat=21.0, cool=24.0),
    )
    store.async_update_room.assert_any_await("old_room", {REST_SWITCHED_OFF: True})


@pytest.mark.asyncio
async def test_climate_control_off_sends_nothing_to_a_resting_room(hass, mock_config_entry):
    coordinator, store = _coordinator(
        hass, mock_config_entry, {"old_room": _resting_room(climate_control_enabled=False)}
    )

    with patch(AREA_REGISTRY, return_value=_registry("living_room")):
        await coordinator._async_update_data()

    coordinator._async_switch_devices_off.assert_not_awaited()
    # Not marked: once control is on again, the next cycle switches the devices off
    store.async_update_room.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_area_deleted_during_the_cycle_is_skipped(hass, mock_config_entry):
    """The cycle's snapshot still has the room; the live check before processing it does not."""
    coordinator, _ = _coordinator(hass, mock_config_entry, {"living_room": SAMPLE_ROOM})
    coordinator._async_process_room = AsyncMock()
    snapshot_then_gone = MagicMock(side_effect=[{"living_room": SAMPLE_ROOM}, {}, {}, {}, {}, {}])

    with patch("custom_components.roommind.coordinator.rooms_with_area", snapshot_then_gone):
        await coordinator._async_update_data()

    coordinator._async_process_room.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_resting_room_keeps_its_learned_ac_offsets(hass, mock_config_entry):
    coordinator, _ = _coordinator(
        hass, mock_config_entry, {"living_room": SAMPLE_ROOM, "old_room": _resting_room(**{REST_SWITCHED_OFF: True})}
    )
    coordinator._head_offsets.prune = MagicMock()

    with patch(AREA_REGISTRY, return_value=_registry("living_room")):
        await coordinator._async_update_data()

    kept = coordinator._head_offsets.prune.call_args[0][0]
    assert "climate.old_trv" in kept


@pytest.mark.asyncio
async def test_a_room_running_again_loses_the_mark(hass, mock_config_entry):
    """Its area came back without an event (restored backup): resting later must switch off again."""
    coordinator, store = _coordinator(
        hass, mock_config_entry, {"living_room": {**SAMPLE_ROOM, REST_SWITCHED_OFF: True}}
    )

    with patch(AREA_REGISTRY, return_value=_registry("living_room")):
        await coordinator._async_update_data()

    store.async_update_room.assert_any_await("living_room", {REST_SWITCHED_OFF: False})


@pytest.mark.asyncio
async def test_a_room_deleted_while_switching_off_does_not_break_the_cycle(hass, mock_config_entry):
    coordinator, store = _coordinator(
        hass, mock_config_entry, {"living_room": SAMPLE_ROOM, "old_room": _resting_room()}
    )
    store.async_update_room = AsyncMock(side_effect=KeyError("old_room"))

    with patch(AREA_REGISTRY, return_value=_registry("living_room")):
        data = await coordinator._async_update_data()

    assert set(data["rooms"]) == {"living_room"}


# A room deleted in the panel lets go of its devices like a resting room


def _deleted_room(**extra) -> dict:
    return _resting_room(area_id="old_room", **extra)


@pytest.mark.asyncio
async def test_a_deleted_room_switches_its_own_devices_off_in_the_next_cycle(hass, mock_config_entry):
    coordinator, _ = _coordinator(hass, mock_config_entry, {"living_room": SAMPLE_ROOM})
    coordinator.rooms = {"old_room": {"heat_target": 21.0, "cool_target": 24.0}}

    assert coordinator.note_room_deleted("old_room", _deleted_room())
    with patch(AREA_REGISTRY, return_value=_registry("living_room", "old_room")):
        await coordinator._async_update_data()
        await coordinator._async_update_data()

    own = [{"entity_id": "climate.old_trv", "type": "trv", "role": "auto", "heating_system_type": ""}]
    coordinator._async_switch_devices_off.assert_awaited_once_with("old_room", own, TargetTemps(heat=21.0, cool=24.0))
    coordinator._async_release_valves.assert_awaited_once_with("old_room", own, hand_back=False)


@pytest.mark.parametrize(
    "room",
    [
        _deleted_room(**{REST_SWITCHED_OFF: True}),
        _deleted_room(climate_control_enabled=False),
        _deleted_room(is_outdoor=True),
    ],
    ids=["already-resting", "room-control-off", "outdoor"],
)
def test_a_deleted_room_whose_devices_were_not_driven_sends_nothing(hass, mock_config_entry, room):
    coordinator, _ = _coordinator(hass, mock_config_entry, {})

    assert not coordinator.note_room_deleted("old_room", room)


@pytest.mark.asyncio
async def test_climate_control_off_sends_nothing_to_a_deleted_room(hass, mock_config_entry):
    coordinator, store = _coordinator(hass, mock_config_entry, {"living_room": SAMPLE_ROOM})
    store.get_settings.return_value = {"climate_control_active": False}

    coordinator.note_room_deleted("old_room", _deleted_room())
    with patch(AREA_REGISTRY, return_value=_registry("living_room")):
        await coordinator._async_update_data()

    coordinator._async_switch_devices_off.assert_not_awaited()
    # Dropped, not held: switching control on later must not reach devices nobody configured anymore
    assert coordinator._deleted_rooms_to_switch_off == {}


@pytest.mark.asyncio
async def test_a_room_created_again_before_the_cycle_keeps_its_devices(hass, mock_config_entry):
    coordinator, _ = _coordinator(hass, mock_config_entry, {"old_room": _deleted_room()})

    coordinator.note_room_deleted("old_room", _deleted_room())
    with patch(AREA_REGISTRY, return_value=_registry("old_room")):
        await coordinator._async_update_data()

    coordinator._async_switch_devices_off.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_room_deleted_during_the_cycle_is_skipped(hass, mock_config_entry):
    """The snapshot still has the room; the store no longer does."""
    coordinator, store = _coordinator(hass, mock_config_entry, {"living_room": SAMPLE_ROOM})
    store.get_room.return_value = None
    coordinator._async_process_room = AsyncMock()

    with patch(AREA_REGISTRY, return_value=_registry("living_room")):
        await coordinator._async_update_data()

    coordinator._async_process_room.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_room_deleted_after_the_cycle_took_its_snapshot_is_still_switched_off(hass, mock_config_entry):
    """The delete lands while the cycle awaits the forecast: the snapshot still has the room."""
    coordinator, store = _coordinator(
        hass, mock_config_entry, {"living_room": SAMPLE_ROOM, "old_room": _deleted_room()}
    )
    coordinator._async_process_room = AsyncMock(return_value={})

    async def delete_meanwhile(_settings):
        coordinator.note_room_deleted("old_room", _deleted_room())
        store.get_rooms.return_value = {"living_room": SAMPLE_ROOM}

    coordinator._weather_manager.async_read_forecast = AsyncMock(side_effect=delete_meanwhile)
    with patch(AREA_REGISTRY, return_value=_registry("living_room", "old_room")):
        await coordinator._async_update_data()

    own = [{"entity_id": "climate.old_trv", "type": "trv", "role": "auto", "heating_system_type": ""}]
    coordinator._async_switch_devices_off.assert_awaited_once_with("old_room", own, TargetTemps(heat=None, cool=None))


@pytest.mark.asyncio
async def test_an_area_deleted_while_its_room_is_processed_leaves_no_run_state(hass, mock_config_entry):
    """The pause drops the run state while the room awaits a device; the rest of its processing must not bring it back."""
    coordinator, _ = _coordinator(hass, mock_config_entry, {"living_room": {**SAMPLE_ROOM, "area_id": "living_room"}})
    areas = {"living_room"}

    async def area_deleted_meanwhile(room, _settings, _forecast):
        await coordinator.async_room_paused(room["area_id"])
        areas.clear()
        coordinator._previous_modes[room["area_id"]] = "heating"
        coordinator._ekf_training._synced.add(room["area_id"])
        coordinator._model_manager.get_estimator(room["area_id"])
        return {"mode": "heating"}

    coordinator._async_process_room = AsyncMock(side_effect=area_deleted_meanwhile)
    registry = MagicMock()
    registry.async_list_areas.side_effect = lambda: [SimpleNamespace(id=a) for a in areas]
    with (
        patch(AREA_REGISTRY, return_value=registry),
        patch("homeassistant.helpers.entity_registry.async_get", return_value=MagicMock(entities={})),
    ):
        data = await coordinator._async_update_data()

    assert "living_room" not in data["rooms"]
    assert "living_room" not in coordinator._previous_modes
    # Back with its area, the model first resyncs to the room instead of learning the pause
    assert "living_room" not in coordinator._ekf_training._synced
    # Resting keeps what the room learned
    assert "living_room" in coordinator._model_manager._estimators


@pytest.mark.asyncio
async def test_a_room_deleted_while_it_is_processed_leaves_no_model(hass, mock_config_entry):
    """The delete removed the model; a training step of the same cycle must not create it again."""
    coordinator, store = _coordinator(
        hass, mock_config_entry, {"living_room": {**SAMPLE_ROOM, "area_id": "living_room"}}
    )

    async def deleted_meanwhile(room, _settings, _forecast):
        store.get_room.return_value = None
        coordinator._previous_modes[room["area_id"]] = "heating"
        coordinator._model_manager.get_estimator(room["area_id"])
        return {"mode": "heating"}

    coordinator._async_process_room = AsyncMock(side_effect=deleted_meanwhile)
    with (
        patch(AREA_REGISTRY, return_value=_registry("living_room")),
        patch("homeassistant.helpers.entity_registry.async_get", return_value=MagicMock(entities={})),
    ):
        data = await coordinator._async_update_data()

    assert "living_room" not in data["rooms"]
    assert "living_room" not in coordinator._previous_modes
    assert "living_room" not in coordinator._model_manager._estimators
