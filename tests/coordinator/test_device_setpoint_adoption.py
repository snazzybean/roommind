"""A setpoint changed on a device becomes an override where the room opts in (#259)."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.const import DEVICE_SETPOINT_ECHO_SECONDS, ROOMMIND_CONTEXT_ID
from custom_components.roommind.coordinator import _setpoint_side

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get

AREA = "living_room_abc12345"
TRV = "climate.living_room"
AC = "climate.living_room_ac"
FOLLOW_ROOM = {**SAMPLE_ROOM, "follow_device_setpoint": True}


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def _setup(hass, mock_config_entry, room, settings=None):
    store = _make_store_mock({AREA: room}, settings)
    store.async_update_room = AsyncMock()
    hass.data = {"roommind": {"store": store}}
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    clock = Clock()
    coordinator.device_setpoints._now = clock
    return coordinator, store, clock


def _devices(hass, **devices):
    base = make_mock_states_get(temp="20.0")

    def _get(eid):
        if eid in devices:
            state, attrs = devices[eid]
            s = MagicMock()
            s.state = state
            s.attributes = attrs
            return s
        return base(eid)

    hass.states.get = _get


async def _cycle(coordinator, clock, seconds=30.0):
    clock.t += seconds
    data = await coordinator._async_update_data()
    coordinator.data = data
    return data["rooms"][AREA]


@pytest.mark.asyncio
async def test_dial_value_becomes_the_room_target(hass, mock_config_entry):
    coordinator, store, clock = _setup(hass, mock_config_entry, FOLLOW_ROOM)
    _devices(hass, **{TRV: ("heat", {"temperature": 26.0, "target_temp_step": 0.5})})
    first = await _cycle(coordinator, clock)
    assert first["heat_target"] == 21.0

    _devices(hass, **{TRV: ("heat", {"temperature": 28.0, "target_temp_step": 0.5})})
    room = await _cycle(coordinator, clock)

    store.async_update_room.assert_awaited_once()
    area, override = store.async_update_room.await_args.args
    assert area == AREA
    assert override["override_heat"] == 28.0
    assert override["override_cool"] == 28.0
    assert override["override_type"] == "custom"
    assert room["override_active"] is True
    assert room["heat_target"] == 28.0


@pytest.mark.asyncio
async def test_off_by_default(hass, mock_config_entry):
    coordinator, store, clock = _setup(hass, mock_config_entry, SAMPLE_ROOM)
    _devices(hass, **{TRV: ("heat", {"temperature": 26.0})})
    await _cycle(coordinator, clock)
    _devices(hass, **{TRV: ("heat", {"temperature": 28.0})})
    room = await _cycle(coordinator, clock)
    store.async_update_room.assert_not_awaited()
    assert room["override_active"] is False


@pytest.mark.asyncio
async def test_switching_it_on_later_does_not_adopt_an_old_change(hass, mock_config_entry):
    coordinator, store, clock = _setup(hass, mock_config_entry, SAMPLE_ROOM)
    _devices(hass, **{TRV: ("heat", {"temperature": 26.0})})
    await _cycle(coordinator, clock)
    _devices(hass, **{TRV: ("heat", {"temperature": 28.0})})
    await _cycle(coordinator, clock)
    store.get_rooms.return_value = {AREA: FOLLOW_ROOM}
    await _cycle(coordinator, clock)
    store.async_update_room.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_override_while_climate_control_is_off(hass, mock_config_entry):
    coordinator, store, clock = _setup(hass, mock_config_entry, FOLLOW_ROOM, {"climate_control_active": False})
    _devices(hass, **{TRV: ("heat", {"temperature": 21.0})})
    await _cycle(coordinator, clock)
    _devices(hass, **{TRV: ("heat", {"temperature": 23.0})})
    await _cycle(coordinator, clock)
    store.async_update_room.assert_not_awaited()


@pytest.mark.asyncio
async def test_own_command_is_not_taken_over(hass, mock_config_entry):
    coordinator, store, clock = _setup(hass, mock_config_entry, FOLLOW_ROOM)
    _devices(hass, **{TRV: ("heat", {"temperature": 21.0})})
    await _cycle(coordinator, clock)
    coordinator.device_setpoints.note_command(TRV, "set_temperature", {"entity_id": TRV, "temperature": 25.0})
    _devices(hass, **{TRV: ("heat", {"temperature": 25.0})})
    await _cycle(coordinator, clock, DEVICE_SETPOINT_ECHO_SECONDS - 60)
    store.async_update_room.assert_not_awaited()


@pytest.mark.asyncio
async def test_ac_remote_moves_the_cool_side(hass, mock_config_entry):
    room_cfg = {
        **FOLLOW_ROOM,
        "thermostats": [],
        "acs": [AC],
        "devices": [{"entity_id": AC, "type": "ac", "role": "auto", "heating_system_type": ""}],
    }
    coordinator, store, clock = _setup(hass, mock_config_entry, room_cfg)
    _devices(hass, **{AC: ("cool", {"temperature": 20.0, "target_temp_step": 1})})
    await _cycle(coordinator, clock)
    _devices(hass, **{AC: ("cool", {"temperature": 22.0, "target_temp_step": 1})})
    await _cycle(coordinator, clock)
    _, override = store.async_update_room.await_args.args
    assert (override["override_heat"], override["override_cool"]) == (21.0, 22.0)


@pytest.mark.asyncio
async def test_unclear_side_and_unavailable_devices_are_skipped(hass, mock_config_entry):
    room_cfg = {
        **FOLLOW_ROOM,
        "acs": [AC],
        "devices": [*FOLLOW_ROOM["devices"], {"entity_id": AC, "type": "ac", "role": "auto"}],
    }
    coordinator, store, clock = _setup(hass, mock_config_entry, room_cfg)
    _devices(hass, **{AC: ("off", {"temperature": 20.0}), TRV: ("unavailable", {})})
    await _cycle(coordinator, clock)
    _devices(hass, **{AC: ("off", {"temperature": 23.0}), TRV: ("unavailable", {})})
    await _cycle(coordinator, clock)
    store.async_update_room.assert_not_awaited()


@pytest.mark.asyncio
async def test_outdoor_room_is_not_observed(hass, mock_config_entry):
    coordinator, store, clock = _setup(hass, mock_config_entry, {**FOLLOW_ROOM, "is_outdoor": True})
    _devices(hass, **{TRV: ("heat", {"temperature": 21.0})})
    await _cycle(coordinator, clock)
    _devices(hass, **{TRV: ("heat", {"temperature": 23.0})})
    await _cycle(coordinator, clock)
    store.async_update_room.assert_not_awaited()


def test_setpoint_tolerances(hass, mock_config_entry):
    coordinator, _, _ = _setup(hass, mock_config_entry, FOLLOW_ROOM)
    state = MagicMock()
    state.attributes = {"target_temp_step": 0.1}
    assert coordinator._setpoint_tolerances(state) == pytest.approx((0.05, 0.05))
    state.attributes = {"target_temp_step": "bad"}
    assert coordinator._setpoint_tolerances(state) == (0.25, 0.5)
    hass.config.units.temperature_unit = "°F"
    state.attributes = {}
    assert coordinator._setpoint_tolerances(state) == (0.5, 1.0)


def _state(state, **attrs):
    s = MagicMock()
    s.state = state
    s.attributes = attrs
    return s


@pytest.mark.parametrize(
    ("attr", "state", "dev_type", "mode", "side"),
    [
        ("target_temp_low", _state("heat_cool"), "ac", "auto", "heat"),
        ("target_temp_high", _state("heat_cool"), "ac", "auto", "cool"),
        ("temperature", _state("off"), "trv", "auto", "heat"),
        ("temperature", _state("heat"), "ac", "auto", "heat"),
        ("temperature", _state("dry"), "ac", "auto", "cool"),
        ("temperature", _state("auto", hvac_action="preheating"), "ac", "auto", "heat"),
        ("temperature", _state("heat_cool", hvac_action="cooling"), "ac", "auto", "cool"),
        ("temperature", _state("off"), "ac", "heat_only", "heat"),
        ("temperature", _state("fan_only"), "ac", "cool_only", "cool"),
        ("temperature", _state("auto", hvac_action="idle"), "ac", "auto", None),
    ],
)
def test_setpoint_side(attr, state, dev_type, mode, side):
    assert _setpoint_side(attr, state, dev_type, mode) == side


@pytest.mark.asyncio
async def test_a_side_the_room_does_not_use_is_ignored(hass, mock_config_entry):
    coordinator, store, clock = _setup(hass, mock_config_entry, {**FOLLOW_ROOM, "climate_mode": "cool_only"})
    _devices(hass, **{TRV: ("heat", {"temperature": 21.0})})
    await _cycle(coordinator, clock)
    _devices(hass, **{TRV: ("heat", {"temperature": 23.0})})
    await _cycle(coordinator, clock)
    store.async_update_room.assert_not_awaited()


@pytest.mark.asyncio
async def test_direct_offset_comes_off_and_the_biggest_turn_wins(hass, mock_config_entry):
    trv2 = "climate.living_room_2"
    room_cfg = {
        **FOLLOW_ROOM,
        "thermostats": [TRV, trv2],
        "devices": [
            {"entity_id": TRV, "type": "trv", "setpoint_mode": "direct", "setpoint_offset": 1.0},
            {"entity_id": trv2, "type": "trv"},
        ],
    }
    coordinator, store, clock = _setup(hass, mock_config_entry, room_cfg)
    _devices(hass, **{TRV: ("heat", {"temperature": 22.0}), trv2: ("heat", {"temperature": 26.0})})
    await _cycle(coordinator, clock)
    _devices(hass, **{TRV: ("heat", {"temperature": 24.0}), trv2: ("heat", {"temperature": 26.5})})
    await _cycle(coordinator, clock)
    _, override = store.async_update_room.await_args.args
    assert override["override_heat"] == 23.0


class FakeTrv:
    """A TRV that takes RoomMind's commands, so its own sends reach the tracker like on the HA bus."""

    def __init__(self, coordinator, state="heat", temperature=21.0):
        self.state = state
        self.temperature = temperature
        self.coordinator = coordinator

    async def call(self, domain, service, data, blocking=False, context=None, **_):
        if domain != "climate" or data.get("entity_id") != TRV:
            return
        if context is not None and context.parent_id == ROOMMIND_CONTEXT_ID:
            mode = data.get("hvac_mode")
            self.coordinator.device_setpoints.note_command(
                TRV, service, data, switch_to=mode if mode is not None and mode != self.state else None
            )
        self.state = data.get("hvac_mode", "off" if service == "turn_off" else self.state)
        if "temperature" in data:
            self.temperature = data["temperature"]


@pytest.mark.asyncio
async def test_own_commands_over_many_cycles_are_never_taken_over(hass, mock_config_entry):
    coordinator, store, clock = _setup(hass, mock_config_entry, FOLLOW_ROOM)
    trv = FakeTrv(coordinator, state="off", temperature=5.0)
    hass.services.async_call = trv.call
    for minute in range(40):
        _devices(hass, **{TRV: (trv.state, {"temperature": trv.temperature, "target_temp_step": 0.5})})
        await _cycle(coordinator, clock)
        if minute == 20:
            assert trv.state == "heat"
    store.async_update_room.assert_not_awaited()

    # A turn during the run is taken over although RoomMind keeps sending setpoints
    _devices(hass, **{TRV: (trv.state, {"temperature": 23.0, "target_temp_step": 0.5})})
    room = await _cycle(coordinator, clock)
    assert room["heat_target"] == 23.0


@pytest.mark.asyncio
async def test_a_device_back_from_unavailable_is_no_change(hass, mock_config_entry):
    coordinator, store, clock = _setup(hass, mock_config_entry, FOLLOW_ROOM)
    _devices(hass, **{TRV: ("heat", {"temperature": 29.5})})
    await _cycle(coordinator, clock)
    _devices(hass, **{TRV: ("unavailable", {})})
    await _cycle(coordinator, clock)
    _devices(hass, **{TRV: ("heat", {"temperature": 20.0})})
    await _cycle(coordinator, clock)
    store.async_update_room.assert_not_awaited()


@pytest.mark.asyncio
async def test_own_range_send_in_auto_is_not_taken_over(hass, mock_config_entry):
    room_cfg = {
        **FOLLOW_ROOM,
        "thermostats": [],
        "acs": [AC],
        "devices": [{"entity_id": AC, "type": "ac", "role": "auto", "heating_system_type": ""}],
    }
    coordinator, store, clock = _setup(hass, mock_config_entry, room_cfg)
    _devices(hass, **{AC: ("heat_cool", {"target_temp_low": 21.0, "target_temp_high": 24.0})})
    await _cycle(coordinator, clock)
    coordinator.device_setpoints.note_command(
        AC, "set_temperature", {"target_temp_low": 21.0, "target_temp_high": 27.0}
    )
    _devices(hass, **{AC: ("heat_cool", {"target_temp_low": 21.0, "target_temp_high": 27.0})})
    await _cycle(coordinator, clock)
    store.async_update_room.assert_not_awaited()


@pytest.mark.asyncio
async def test_fahrenheit_value_and_schedule_end(hass, mock_config_entry):
    coordinator, store, clock = _setup(hass, mock_config_entry, FOLLOW_ROOM)
    hass.config.units.temperature_unit = "°F"
    _devices(hass, **{TRV: ("heat", {"temperature": 70.0, "target_temp_step": 1})})
    await _cycle(coordinator, clock)
    _devices(hass, **{TRV: ("heat", {"temperature": 74.0, "target_temp_step": 1})})
    until = time.time() + 3600
    with patch("custom_components.roommind.coordinator.override_hold_until", return_value=until):
        await _cycle(coordinator, clock)
    _, override = store.async_update_room.await_args.args
    assert override["override_heat"] == 23.3
    assert override["override_until"] == until


@pytest.mark.asyncio
async def test_a_send_reported_after_a_reload_is_ours(hass, mock_config_entry):
    coordinator, store, clock = _setup(hass, mock_config_entry, FOLLOW_ROOM)
    _devices(hass, **{TRV: ("heat", {"temperature": 21.0})})
    await _cycle(coordinator, clock)
    coordinator.device_setpoints.note_command(TRV, "set_temperature", {"entity_id": TRV, "temperature": 29.5})

    reloaded = _create_coordinator(hass, mock_config_entry)
    assert reloaded.device_setpoints is coordinator.device_setpoints
    reloaded.data = coordinator.data
    await _cycle(reloaded, clock)
    _devices(hass, **{TRV: ("heat", {"temperature": 29.5})})
    await _cycle(reloaded, clock)
    store.async_update_room.assert_not_awaited()


@pytest.mark.asyncio
async def test_managed_mode_ignores_the_direct_offset(hass, mock_config_entry):
    room_cfg = {
        **FOLLOW_ROOM,
        "temperature_sensor": "",
        "devices": [{"entity_id": TRV, "type": "trv", "setpoint_mode": "direct", "setpoint_offset": 1.0}],
    }
    coordinator, store, clock = _setup(hass, mock_config_entry, room_cfg)
    _devices(hass, **{TRV: ("heat", {"temperature": 21.0})})
    await _cycle(coordinator, clock)
    _devices(hass, **{TRV: ("heat", {"temperature": 22.5})})
    await _cycle(coordinator, clock)
    _, override = store.async_update_room.await_args.args
    assert override["override_heat"] == 22.5


@pytest.mark.asyncio
async def test_no_override_while_the_room_is_switched_off(hass, mock_config_entry):
    coordinator, store, clock = _setup(hass, mock_config_entry, {**FOLLOW_ROOM, "climate_control_enabled": False})
    _devices(hass, **{TRV: ("heat", {"temperature": 21.0})})
    await _cycle(coordinator, clock)
    _devices(hass, **{TRV: ("heat", {"temperature": 23.0})})
    await _cycle(coordinator, clock)
    store.async_update_room.assert_not_awaited()


class BusTrv:
    """A TRV behind HA's service bus: RoomMind's calls reach the tracker through its real listener."""

    def __init__(self, hass, coordinator, state="off", temperature=5.0):
        self.hass = hass
        self.state = state
        self.temperature = temperature
        coordinator.device_setpoints.async_track(hass)
        self.record = hass.bus.async_listen.call_args.args[1]

    async def call(self, domain, service, data, blocking=False, context=None, **_):
        from homeassistant.core import Context, Event

        self.record(
            Event(
                "call_service",
                {"domain": domain, "service": service, "service_data": data},
                context=context or Context(),
            )
        )
        if domain != "climate" or data.get("entity_id") != TRV:
            return
        self.state = data.get("hvac_mode", "off" if service == "turn_off" else self.state)
        if "temperature" in data:
            self.temperature = data["temperature"]

    def publish(self):
        _devices(self.hass, **{TRV: (self.state, {"temperature": self.temperature, "target_temp_step": 0.5})})


@pytest.mark.asyncio
async def test_own_commands_through_the_service_bus_are_never_taken_over(hass, mock_config_entry):
    coordinator, store, clock = _setup(hass, mock_config_entry, FOLLOW_ROOM)
    trv = BusTrv(hass, coordinator)
    hass.services.async_call = trv.call
    heated = False
    for _ in range(40):
        trv.publish()
        await _cycle(coordinator, clock)
        heated = heated or trv.state == "heat"
    assert heated
    store.async_update_room.assert_not_awaited()
