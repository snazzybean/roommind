"""The coordinator hands pinned valves back to their TRVs when RoomMind stops controlling them (#413)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get

OPEN = "number.living_room_valve_opening_degree"
CLOSE = "number.living_room_valve_closing_degree"
NUMBER_ATTRS = {"min": 0, "max": 100, "step": 1}

VALVE_ROOM = {
    **SAMPLE_ROOM,
    "devices": [
        {
            "entity_id": "climate.living_room",
            "type": "trv",
            "role": "auto",
            "heating_system_type": "",
            "valve_opening_entity": OPEN,
            "valve_closing_entity": CLOSE,
        }
    ],
}


def _number_calls(hass):
    return [
        (c[0][2]["entity_id"], c[0][2]["value"])
        for c in hass.services.async_call.call_args_list
        if c[0][0] == "number" and c[0][1] == "set_value"
    ]


def _setup(hass, room, settings):
    store = _make_store_mock({room["area_id"]: room})
    store.get_settings.return_value = {"outdoor_temp_sensor": "sensor.outdoor_temp", **settings}
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(
        side_effect=make_mock_states_get(
            temp="18.0",
            humidity="55.0",
            extra={OPEN: ("40", NUMBER_ATTRS), CLOSE: ("60", NUMBER_ATTRS)},
        )
    )
    hass.services.async_call = AsyncMock()


@pytest.mark.asyncio
async def test_disabled_climate_control_releases_the_valve(hass, mock_config_entry):
    _setup(hass, VALVE_ROOM, {"climate_control_active": False})
    coordinator = _create_coordinator(hass, mock_config_entry)

    await coordinator._async_update_data()

    assert _number_calls(hass) == [(OPEN, 100.0), (CLOSE, 100.0)]
    assert [c for c in hass.services.async_call.call_args_list if c[0][0] == "climate"] == []


@pytest.mark.asyncio
async def test_outdoor_area_releases_the_valve(hass, mock_config_entry):
    _setup(hass, {**VALVE_ROOM, "is_outdoor": True}, {})
    coordinator = _create_coordinator(hass, mock_config_entry)

    await coordinator._async_update_data()

    assert _number_calls(hass) == [(OPEN, 100.0), (CLOSE, 100.0)]


@pytest.mark.asyncio
async def test_room_switched_off_releases_the_valve(hass, mock_config_entry):
    _setup(hass, {**VALVE_ROOM, "climate_control_enabled": False}, {})
    coordinator = _create_coordinator(hass, mock_config_entry)
    coordinator._rooms_to_switch_off.add("living_room_abc12345")

    await coordinator._async_update_data()

    assert _number_calls(hass) == [(OPEN, 100.0), (CLOSE, 100.0)]


@pytest.mark.asyncio
async def test_release_failure_is_logged(hass, mock_config_entry, caplog):
    _setup(hass, VALVE_ROOM, {})
    coordinator = _create_coordinator(hass, mock_config_entry)

    with patch("custom_components.roommind.coordinator.async_release_valve", side_effect=RuntimeError("boom")):
        await coordinator._async_release_valves("living_room_abc12345", VALVE_ROOM["devices"])

    assert "releasing the valve" in caplog.text


@pytest.mark.asyncio
async def test_a_valve_pinned_by_a_stale_cycle_is_released(hass, mock_config_entry):
    """Saved without the valve while a cycle ran: the cycle pins it, its end releases it."""
    from custom_components.roommind.control import direct_valve

    _setup(hass, SAMPLE_ROOM, {})
    direct_valve._valve_sent["climate.living_room"] = direct_valve._Held(0.0, 40, 21.0, OPEN, CLOSE)
    coordinator = _create_coordinator(hass, mock_config_entry)

    await coordinator._async_update_data()

    assert (OPEN, 100.0) in _number_calls(hass)
    assert direct_valve.held_opening("climate.living_room") is None


@pytest.mark.asyncio
async def test_orphan_release_failure_does_not_break_the_cycle(hass, mock_config_entry, caplog):
    _setup(hass, SAMPLE_ROOM, {})
    coordinator = _create_coordinator(hass, mock_config_entry)

    with patch(
        "custom_components.roommind.coordinator.async_release_orphaned_valves", side_effect=RuntimeError("boom")
    ):
        data = await coordinator._async_update_data()

    assert "living_room_abc12345" in data["rooms"]
    assert "Releasing unconfigured valves failed" in caplog.text


@pytest.mark.asyncio
async def test_unload_releases_every_configured_valve(hass):
    from custom_components.roommind import _async_release_all_valves

    _setup(hass, VALVE_ROOM, {})
    await _async_release_all_valves(hass)
    assert _number_calls(hass) == [(OPEN, 100.0), (CLOSE, 100.0)]

    hass.data = {}
    await _async_release_all_valves(hass)


@pytest.mark.asyncio
async def test_a_held_valve_trains_as_heating_although_its_trv_reports_idle(hass, mock_config_entry):
    """The TRVZB reports idle once its own sensor is warm; the pinned valve still heats."""
    from custom_components.roommind.const import MODE_HEATING
    from custom_components.roommind.control import direct_valve

    _setup(hass, VALVE_ROOM, {})
    coordinator = _create_coordinator(hass, mock_config_entry)
    room = VALVE_ROOM
    hass.states.get = MagicMock(
        side_effect=make_mock_states_get(
            temp="20.5",
            extra={"climate.living_room": ("heat", {"hvac_action": "idle"}), OPEN: ("40", NUMBER_ATTRS)},
        )
    )
    assert coordinator._observe_device_action(room)[0] == "idle"
    direct_valve._valve_sent["climate.living_room"] = direct_valve._Held(0.0, 40, 21.0, OPEN, CLOSE)
    assert coordinator._delivered_training_power(room, MODE_HEATING, 0.4, None) == 0.4


@pytest.mark.asyncio
async def test_switching_climate_control_off_hands_the_room_target_back(hass, mock_config_entry):
    """Without it the TRV would heat on its proportional setpoint once the valve is free."""
    from custom_components.roommind.control import direct_valve

    _setup(hass, VALVE_ROOM, {"climate_control_active": False})
    hass.config.units.temperature_unit = "°C"
    direct_valve._valve_sent["climate.living_room"] = direct_valve._Held(0.0, 40, 21.0, OPEN, CLOSE)
    coordinator = _create_coordinator(hass, mock_config_entry)

    await coordinator._async_update_data()

    setpoints = [
        c[0][2]["temperature"]
        for c in hass.services.async_call.call_args_list
        if c[0][0] == "climate" and c[0][1] == "set_temperature"
    ]
    assert setpoints == [21.0]
    assert _number_calls(hass) == [(OPEN, 100.0), (CLOSE, 100.0)]
