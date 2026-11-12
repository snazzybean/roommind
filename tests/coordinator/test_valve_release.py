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


def _climate_calls(hass):
    return [(c[0][1], dict(c[0][2])) for c in hass.services.async_call.call_args_list if c[0][0] == "climate"]


def _pinned_trv_off(hass, idle_action):
    from custom_components.roommind.control import direct_valve

    device = {**VALVE_ROOM["devices"][0], "idle_action": idle_action}
    _setup(hass, {**VALVE_ROOM, "devices": [device], "climate_control_enabled": False}, {})
    trv = MagicMock()
    trv.state = "heat"
    trv.attributes = {"hvac_modes": ["off", "heat"], "min_temp": 5.0, "max_temp": 30.0, "temperature": 25.0}
    base = hass.states.get.side_effect
    hass.states.get = MagicMock(side_effect=lambda eid: trv if eid == "climate.living_room" else base(eid))
    direct_valve._valve_sent["climate.living_room"] = direct_valve._Held(0.0, 40, 21.0, OPEN, CLOSE)


@pytest.mark.asyncio
@pytest.mark.parametrize("idle_action", ["low", "off"])
async def test_room_switched_off_does_not_hand_the_target_back(hass, mock_config_entry, idle_action):
    """Room entity off: the TRV keeps its off/low setpoint, the room target would heat on (#413/#238)."""
    _pinned_trv_off(hass, idle_action)
    coordinator = _create_coordinator(hass, mock_config_entry)
    coordinator._rooms_to_switch_off.add("living_room_abc12345")

    await coordinator._async_update_data()

    assert _number_calls(hass) == [(OPEN, 100.0), (CLOSE, 100.0)]
    setpoints = [d["temperature"] for svc, d in _climate_calls(hass) if svc == "set_temperature"]
    assert setpoints == [5.0]


@pytest.mark.asyncio
async def test_a_retried_release_after_room_off_does_not_hand_the_target_back(hass, mock_config_entry):
    _pinned_trv_off(hass, "low")
    coordinator = _create_coordinator(hass, mock_config_entry)
    coordinator._rooms_to_switch_off.add("living_room_abc12345")

    with patch("custom_components.roommind.coordinator.async_release_valve", side_effect=RuntimeError("unavailable")):
        await coordinator._async_update_data()
    hass.services.async_call.reset_mock()
    await coordinator._async_update_data()

    assert _number_calls(hass) == [(OPEN, 100.0), (CLOSE, 100.0)]
    assert [c for c in _climate_calls(hass) if c[0] == "set_temperature"] == []


@pytest.mark.asyncio
async def test_room_switched_on_again_hands_back_on_the_next_release(hass, mock_config_entry):
    """Once the room runs again, a later disable through the old switch keeps the #36 hand-back."""
    coordinator = _create_coordinator(hass, mock_config_entry)
    coordinator._rooms_switched_off.add("living_room_abc12345")
    _setup(hass, VALVE_ROOM, {})

    await coordinator._async_update_data()

    assert "living_room_abc12345" not in coordinator._rooms_switched_off


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
async def test_unload_leaves_the_valves_of_a_resting_room_alone(hass):
    """Resting (#494) already handed them back; the user may have set them by hand since."""
    from types import SimpleNamespace

    from custom_components.roommind import _async_release_all_valves

    _setup(hass, VALVE_ROOM, {})
    registry = MagicMock()
    registry.async_list_areas.return_value = [SimpleNamespace(id="other_area")]
    with patch("custom_components.roommind.utils.area_utils.ar.async_get", return_value=registry):
        await _async_release_all_valves(hass)

    assert _number_calls(hass) == []


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


@pytest.mark.asyncio
async def test_held_valve_trv_shows_the_opening_it_is_held_at(hass, mock_config_entry):
    """Min-run hold pins the valve at the minimum opening; the card must not show the last run (#452/#413)."""
    from custom_components.roommind.const import MIN_POWER_FRACTION, MODE_HEATING
    from custom_components.roommind.control import direct_valve
    from custom_components.roommind.control.mpc_controller import MPCController

    area = "living_room_abc12345"
    group = {"id": "boiler", "name": "Boiler", "members": ["climate.living_room"], "min_run_minutes": 15}
    store = _make_store_mock({area: VALVE_ROOM}, settings={"compressor_groups": [group]})
    hass.data = {"roommind": {"store": store}}
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)

    def wire(trv_state, temp, **attrs):
        trv = MagicMock()
        trv.state = trv_state
        trv.attributes = {"hvac_modes": ["off", "heat"], "min_temp": 5.0, "max_temp": 30.0, "target_temp_step": 0.5}
        trv.attributes.update(attrs)
        base = make_mock_states_get(temp=temp, extra={OPEN: ("80", NUMBER_ATTRS), CLOSE: ("20", NUMBER_ATTRS)})
        hass.states.get = MagicMock(side_effect=lambda eid: trv if eid == "climate.living_room" else base(eid))

    wire("off", "18.0", temperature=5.0)
    with patch.object(MPCController, "async_evaluate", AsyncMock(return_value=(MODE_HEATING, 0.8))):
        data = await coordinator._async_update_data()
    assert data["rooms"][area]["heating_power"] == 80

    wire("heat", "21.3", temperature=25.0, hvac_action="heating")
    coordinator._mode_on_since[area] -= 3600
    room = (await coordinator._async_update_data())["rooms"][area]

    assert room["compressor_protection_reason"] == "min_run"
    assert direct_valve.held_opening("climate.living_room") == MIN_POWER_FRACTION
    assert room["heating_power"] == round(MIN_POWER_FRACTION * 100)


@pytest.mark.asyncio
async def test_mixed_hold_shows_the_ac_boost_not_the_valve_minimum(hass, mock_config_entry):
    """A held AC keeps its boost next to a held valve: the room shows the last run, not 15 % (#452/#413)."""
    from custom_components.roommind.const import MIN_POWER_FRACTION, MODE_HEATING
    from custom_components.roommind.control import direct_valve
    from custom_components.roommind.control.mpc_controller import MPCController

    AREA = "living_room_abc12345"
    AC = "climate.living_room_ac"
    room = {
        **VALVE_ROOM,
        "acs": [AC],
        "devices": [*VALVE_ROOM["devices"], {"entity_id": AC, "type": "ac", "role": "auto", "heating_system_type": ""}],
    }
    groups = [
        {"id": "boiler", "name": "Boiler", "members": ["climate.living_room"], "min_run_minutes": 15},
        {"id": "outdoor", "name": "Outdoor", "members": [AC], "min_run_minutes": 15},
    ]
    store = _make_store_mock({AREA: room}, settings={"compressor_groups": groups})
    hass.data = {"roommind": {"store": store}}
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)

    def wire(state, temp, action=None, **attrs):
        trv = MagicMock()
        trv.state = state
        trv.attributes = {"hvac_modes": ["off", "heat"], "min_temp": 5.0, "max_temp": 30.0, "target_temp_step": 0.5}
        trv.attributes.update(attrs)
        ac = MagicMock()
        ac.state = state
        ac.attributes = {
            "hvac_modes": ["off", "heat", "cool"],
            "min_temp": 16.0,
            "max_temp": 30.0,
            "target_temp_step": 0.5,
            **attrs,
        }
        if action:
            trv.attributes["hvac_action"] = action
            ac.attributes["hvac_action"] = action
        base = make_mock_states_get(temp=temp, extra={OPEN: ("80", NUMBER_ATTRS), CLOSE: ("20", NUMBER_ATTRS)})
        devs = {"climate.living_room": trv, AC: ac}
        hass.states.get = MagicMock(side_effect=lambda eid: devs.get(eid) or base(eid))

    wire("off", "18.0", temperature=5.0)
    with patch.object(MPCController, "async_evaluate", AsyncMock(return_value=(MODE_HEATING, 0.8))):
        await coordinator._async_update_data()

    wire("heat", "21.3", action="heating", temperature=25.0)
    coordinator._mode_on_since[AREA] -= 3600
    rs = (await coordinator._async_update_data())["rooms"][AREA]
    assert direct_valve.held_opening("climate.living_room") == MIN_POWER_FRACTION
    assert rs["compressor_protection_reason"] == "min_run"
    assert rs["heating_power"] == 80


@pytest.mark.asyncio
async def test_a_held_valve_stays_held_over_cycles(hass, mock_config_entry):
    """The closing mode in the valve config must not make every cycle see an orphan (#482)."""
    from custom_components.roommind.const import MODE_HEATING
    from custom_components.roommind.control import direct_valve
    from custom_components.roommind.control.mpc_controller import MPCController

    _setup(hass, VALVE_ROOM, {})
    coordinator = _create_coordinator(hass, mock_config_entry)

    with patch.object(MPCController, "async_evaluate", AsyncMock(return_value=(MODE_HEATING, 0.4))):
        for _ in range(3):
            await coordinator._async_update_data()

    assert direct_valve.held_opening("climate.living_room") == 0.4
    assert (OPEN, 100.0) not in _number_calls(hass)


@pytest.mark.asyncio
async def test_disabled_climate_control_releases_an_idle_opening_valve_closed(hass, mock_config_entry):
    room = {**VALVE_ROOM, "devices": [{**VALVE_ROOM["devices"][0], "valve_closing_mode": "idle_opening"}]}
    _setup(hass, room, {"climate_control_active": False})
    coordinator = _create_coordinator(hass, mock_config_entry)

    await coordinator._async_update_data()

    assert _number_calls(hass) == [(OPEN, 100.0), (CLOSE, 0.0)]


@pytest.mark.asyncio
async def test_a_mode_change_while_heating_reaches_the_valve_next_cycle(hass, mock_config_entry):
    from custom_components.roommind.const import MODE_HEATING
    from custom_components.roommind.control import direct_valve
    from custom_components.roommind.control.mpc_controller import MPCController

    _setup(hass, VALVE_ROOM, {})
    coordinator = _create_coordinator(hass, mock_config_entry)
    store = hass.data["roommind"]["store"]
    with patch.object(MPCController, "async_evaluate", AsyncMock(return_value=(MODE_HEATING, 0.4))):
        await coordinator._async_update_data()
        assert direct_valve.held_opening("climate.living_room") == 0.4  # degrees already at 40/60

        idle_room = {**VALVE_ROOM, "devices": [{**VALVE_ROOM["devices"][0], "valve_closing_mode": "idle_opening"}]}
        store.get_rooms.return_value = {VALVE_ROOM["area_id"]: idle_room}
        hass.services.async_call.reset_mock()
        await coordinator._async_update_data()

    assert _number_calls(hass) == [(CLOSE, 40.0)]
