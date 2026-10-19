"""Direct valve control (#413): validation and hand-back on save/delete."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import voluptuous as vol

from custom_components.roommind.const import DOMAIN
from custom_components.roommind.websocket_api import (
    _number_entity_or_empty,
    _validate_device_valve,
    websocket_delete_room,
    websocket_save_room,
)

_save_room = websocket_save_room.__wrapped__
_delete_room = websocket_delete_room.__wrapped__

OPEN = "number.trv_valve_opening_degree"
CLOSE = "number.trv_valve_closing_degree"


@pytest.fixture
def connection():
    conn = MagicMock()
    conn.send_result = MagicMock()
    conn.send_error = MagicMock()
    return conn


@pytest.fixture
def ws_hass(hass, store):
    hass.data[DOMAIN] = {"store": store}
    return hass


def _pinned(hass):
    states = {}
    for eid, value in ((OPEN, "30"), (CLOSE, "70")):
        s = MagicMock()
        s.state = value
        s.attributes = {"min": 0, "max": 100, "step": 1}
        states[eid] = s
    hass.states.get = MagicMock(side_effect=states.get)


def _number_calls(hass):
    return [
        (c[0][2]["entity_id"], c[0][2]["value"])
        for c in hass.services.async_call.call_args_list
        if c[0][0] == "number" and c[0][1] == "set_value"
    ]


def _device(**extra):
    return {"entity_id": "climate.trv", "type": "trv", "role": "auto", **extra}


async def _save(hass, connection, devices, msg_id=1):
    await _save_room(
        hass,
        connection,
        {"id": msg_id, "type": "roommind/rooms/save", "area_id": "living", "devices": devices},
    )


def test_number_entity_or_empty():
    assert _number_entity_or_empty(None) == ""
    assert _number_entity_or_empty("") == ""
    assert _number_entity_or_empty(OPEN) == OPEN
    with pytest.raises(vol.Invalid):
        _number_entity_or_empty("climate.trv")
    with pytest.raises(vol.Invalid):
        _number_entity_or_empty(5)


def test_validate_device_valve():
    assert _validate_device_valve(_device(valve_opening_entity=OPEN, valve_closing_entity=CLOSE))
    # Half a pair is stored (the other picker comes next) and simply has no effect yet
    assert _validate_device_valve(_device(valve_opening_entity=OPEN))
    assert _validate_device_valve(_device(valve_closing_entity=CLOSE))
    assert _validate_device_valve({"entity_id": "climate.ac", "type": "ac"})
    with pytest.raises(vol.Invalid):
        _validate_device_valve({"entity_id": "climate.ac", "type": "ac", "valve_opening_entity": OPEN})
    with pytest.raises(vol.Invalid):
        _validate_device_valve(_device(valve_opening_entity=OPEN, valve_closing_entity=OPEN))


@pytest.mark.asyncio
async def test_clearing_the_valve_entities_hands_the_valve_back(ws_hass, store, connection):
    await store.async_load()
    await _save(ws_hass, connection, [_device(valve_opening_entity=OPEN, valve_closing_entity=CLOSE)])
    _pinned(ws_hass)
    ws_hass.services.async_call.reset_mock()

    await _save(ws_hass, connection, [_device()], msg_id=2)

    assert _number_calls(ws_hass) == [(OPEN, 100.0), (CLOSE, 100.0)]


@pytest.mark.asyncio
async def test_unchanged_valve_entities_are_left_alone(ws_hass, store, connection):
    await store.async_load()
    await _save(ws_hass, connection, [_device(valve_opening_entity=OPEN, valve_closing_entity=CLOSE)])
    _pinned(ws_hass)
    ws_hass.services.async_call.reset_mock()

    await _save(ws_hass, connection, [_device(valve_opening_entity=OPEN, valve_closing_entity=CLOSE)], msg_id=2)

    assert _number_calls(ws_hass) == []


@pytest.mark.asyncio
async def test_deleting_the_room_hands_the_valve_back(ws_hass, store, connection):
    await store.async_load()
    await _save(ws_hass, connection, [_device(valve_opening_entity=OPEN, valve_closing_entity=CLOSE)])
    _pinned(ws_hass)
    ws_hass.services.async_call.reset_mock()

    await _delete_room(ws_hass, connection, {"id": 3, "type": "roommind/rooms/delete", "area_id": "living"})

    assert _number_calls(ws_hass) == [(OPEN, 100.0), (CLOSE, 100.0)]


@pytest.mark.asyncio
async def test_release_failure_does_not_break_the_save(ws_hass, store, connection, caplog):
    await store.async_load()
    await _save(ws_hass, connection, [_device(valve_opening_entity=OPEN, valve_closing_entity=CLOSE)])
    _pinned(ws_hass)
    with patch("custom_components.roommind.websocket_api.async_release_valve", side_effect=RuntimeError("boom")):
        await _save(ws_hass, connection, [_device()], msg_id=2)

    assert connection.send_result.call_count == 2
    assert "releasing the valve" in caplog.text
