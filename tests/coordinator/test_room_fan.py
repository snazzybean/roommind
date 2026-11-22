"""Room fan in the coordinator cycle: on while the room heats or cools (#266)."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.const import DOMAIN

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get

AREA = "living_room_abc12345"
FAN = "fan.living_ceiling"
TEMP = "sensor.living_room_temp"
WINDOW = "binary_sensor.window"

ROOM = {**SAMPLE_ROOM, "room_fan_entity": FAN, "window_sensors": [WINDOW]}


def _setup(hass, mock_config_entry, room, settings=None, temp="18.0", fan="off"):
    store = _make_store_mock({AREA: room}, settings)
    hass.data = {DOMAIN: {"store": store}}
    readings = {TEMP: temp, WINDOW: "off", FAN: fan}
    base = make_mock_states_get(temp=temp)

    def get(eid):
        if eid in readings:
            value = readings[eid]
            return None if value is None else SimpleNamespace(state=value, attributes={})
        return base(eid)

    hass.states.get = get
    calls = []

    async def _call(domain, service, data, **_kw):
        eid = data.get("entity_id")
        calls.append((domain, service, eid))
        if eid == FAN and service in ("turn_on", "turn_off"):
            readings[FAN] = "on" if service == "turn_on" else "off"

    hass.services.async_call = AsyncMock(side_effect=_call)
    coordinator = _create_coordinator(hass, mock_config_entry)
    return coordinator, store, readings, calls


def _fan_calls(calls):
    return [c for c in calls if c[2] == FAN]


async def _cycle(coordinator):
    return (await coordinator._async_update_data())["rooms"][AREA]


def _age(coordinator, seconds):
    """Let time pass for the fan: its min run and the room's post-run."""
    coordinator._room_fans._owned = {e: t - seconds for e, t in coordinator._room_fans._owned.items()}
    coordinator._room_fan._ran = {a: (m, t - seconds) for a, (m, t) in coordinator._room_fan._ran.items()}


@pytest.mark.asyncio
async def test_without_a_fan_nothing_changes(hass, mock_config_entry):
    coordinator, store, _, calls = _setup(hass, mock_config_entry, SAMPLE_ROOM)
    room = await _cycle(coordinator)
    assert room["mode"] == "heating"
    assert room["room_fan_active"] is False
    assert _fan_calls(calls) == []
    saved = [c.args[0] for c in store.async_save_settings.await_args_list]
    assert not any("room_fan_state" in s for s in saved)


@pytest.mark.asyncio
async def test_heating_runs_the_fan_and_the_post_run_ends_it(hass, mock_config_entry):
    coordinator, store, readings, calls = _setup(hass, mock_config_entry, ROOM)
    room = await _cycle(coordinator)
    assert room["mode"] == "heating" and room["room_fan_active"] is True
    assert _fan_calls(calls) == [("fan", "turn_on", FAN)]
    store.async_save_settings.assert_any_await(
        {"room_fan_state": {FAN: pytest.approx(coordinator._room_fans.get_state()[FAN])}}
    )
    # Warm: the room stops heating, the post-run keeps the fan
    readings[TEMP] = "23.0"
    room = await _cycle(coordinator)
    assert room["mode"] == "idle" and room["room_fan_active"] is True
    _age(coordinator, 3600)
    room = await _cycle(coordinator)
    assert room["room_fan_active"] is False
    assert _fan_calls(calls)[-1] == ("fan", "turn_off", FAN)
    store.async_save_settings.assert_any_await({"room_fan_state": {}})


@pytest.mark.asyncio
async def test_a_fan_for_cooling_only_stays_off_while_heating(hass, mock_config_entry):
    coordinator, _, _, calls = _setup(hass, mock_config_entry, {**ROOM, "room_fan_mode": "cool"})
    room = await _cycle(coordinator)
    assert room["mode"] == "heating" and room["room_fan_active"] is False
    assert _fan_calls(calls) == []


@pytest.mark.asyncio
async def test_open_window_switches_the_fan_off_at_once(hass, mock_config_entry):
    coordinator, _, readings, calls = _setup(hass, mock_config_entry, ROOM)
    await _cycle(coordinator)
    readings[WINDOW] = "on"
    room = await _cycle(coordinator)
    assert room["window_open"] is True and room["room_fan_active"] is False
    assert _fan_calls(calls) == [("fan", "turn_on", FAN), ("fan", "turn_off", FAN)]


@pytest.mark.asyncio
async def test_switched_off_by_hand_stays_off_until_heating_ends(hass, mock_config_entry):
    coordinator, _, readings, calls = _setup(hass, mock_config_entry, ROOM)
    await _cycle(coordinator)
    _age(coordinator, 120)
    readings[FAN] = "off"
    await _cycle(coordinator)
    room = await _cycle(coordinator)
    assert room["mode"] == "heating" and room["room_fan_active"] is False
    assert _fan_calls(calls) == [("fan", "turn_on", FAN)]


@pytest.mark.asyncio
async def test_a_fan_already_on_by_hand_is_never_switched_off(hass, mock_config_entry):
    coordinator, _, readings, calls = _setup(hass, mock_config_entry, ROOM, fan="on")
    await _cycle(coordinator)
    readings[TEMP] = "23.0"
    _age(coordinator, 3600)
    room = await _cycle(coordinator)
    assert room["room_fan_active"] is False
    assert _fan_calls(calls) == []


@pytest.mark.asyncio
async def test_climate_control_off_in_the_room_switches_nothing_on(hass, mock_config_entry):
    coordinator, _, _, calls = _setup(hass, mock_config_entry, {**ROOM, "climate_control_enabled": False})
    await _cycle(coordinator)
    assert _fan_calls(calls) == []


@pytest.mark.asyncio
async def test_global_control_off_switches_the_owned_fan_off_once(hass, mock_config_entry):
    coordinator, store, _, calls = _setup(hass, mock_config_entry, ROOM)
    await _cycle(coordinator)
    store.get_settings.return_value = {**store.get_settings.return_value, "climate_control_active": False}
    await _cycle(coordinator)
    room = await _cycle(coordinator)
    assert room["room_fan_active"] is False
    assert _fan_calls(calls) == [("fan", "turn_on", FAN), ("fan", "turn_off", FAN)]


@pytest.mark.asyncio
async def test_a_run_from_before_the_restart_is_held_while_the_sensor_is_missing(hass, mock_config_entry):
    """After a restart the room waits for its temperature; the fan RoomMind runs is not cut."""
    since = time.time() - 3600
    coordinator, _, _, calls = _setup(
        hass, mock_config_entry, ROOM, settings={"room_fan_state": {FAN: since}}, temp=None, fan="on"
    )
    room = await _cycle(coordinator)
    assert room["waiting_for_data"] is True
    assert room["room_fan_active"] is True
    assert _fan_calls(calls) == []


@pytest.mark.asyncio
async def test_failing_room_fan_reconcile_does_not_break_the_cycle(hass, mock_config_entry):
    coordinator, _, _, _ = _setup(hass, mock_config_entry, ROOM)
    coordinator._room_fans.async_reconcile = AsyncMock(side_effect=RuntimeError("boom"))
    room = await _cycle(coordinator)
    assert room["room_fan_active"] is False


@pytest.mark.asyncio
async def test_forget_room_drops_the_post_run(hass, mock_config_entry):
    coordinator, _, _, _ = _setup(hass, mock_config_entry, ROOM)
    await _cycle(coordinator)
    assert AREA in coordinator._room_fan._ran
    reg = MagicMock()
    reg.entities.values.return_value = []
    with patch("homeassistant.helpers.entity_registry.async_get", return_value=reg):
        coordinator._forget_room(AREA)
    assert AREA not in coordinator._room_fan._ran
