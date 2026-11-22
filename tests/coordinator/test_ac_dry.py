"""AC dry for a too humid room in the coordinator cycle (#440)."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import custom_components.roommind.managers.ac_dry_manager as ac_dry_mod
from custom_components.roommind.const import AC_DRY_DEHUMIDIFIER_GONE_MINUTES, DOMAIN

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get

AREA = "living_room_abc12345"
AC = "climate.living_ac"
HUM_SENSOR = "sensor.living_room_humidity"
DEHUM = "humidifier.dehumidifier"
WINDOW = "binary_sensor.window"

AC_ROOM = {
    **SAMPLE_ROOM,
    "thermostats": [],
    "acs": [AC],
    "devices": [{"entity_id": AC, "type": "ac", "role": "auto", "idle_action": "off"}],
    "schedules": [],
    "humidity_max": 60,
}


def _ac(state="off", **attrs):
    return SimpleNamespace(
        state=state,
        attributes={
            "hvac_modes": ["off", "cool", "heat", "dry", "fan_only"],
            "min_temp": 16.0,
            "max_temp": 30.0,
            "target_temp_step": 0.5,
            "temperature": 24.0,
            "hvac_action": "off" if state == "off" else "idle",
            **attrs,
        },
    )


def _setup(hass, mock_config_entry, room, *, settings=None, temp="22.5", humidity="75", outdoor="28.0", **extra):
    store = _make_store_mock({AREA: room}, settings)
    hass.data = {DOMAIN: {"store": store}}
    devices = {AC: _ac(), **extra}
    world = {"temp": temp, "humidity": humidity, "window": "off"}

    def get(eid):
        if eid in devices:
            return devices[eid]
        if eid == HUM_SENSOR:
            return SimpleNamespace(state=world["humidity"], attributes={"unit_of_measurement": "%"})
        return make_mock_states_get(temp=world["temp"], outdoor_temp=outdoor, window_sensors={WINDOW: world["window"]})(
            eid
        )

    hass.states.get = get
    calls: list[tuple[str, str, dict]] = []

    async def _call(domain, service, data, **_kw):
        eid = data.get("entity_id")
        calls.append((service, eid, {k: v for k, v in data.items() if k != "entity_id"}))
        dev = devices.get(eid)
        if dev is not None and domain == "climate":
            if "hvac_mode" in data:
                dev.state = data["hvac_mode"]
            if "temperature" in data:
                dev.attributes["temperature"] = data["temperature"]

    hass.services.async_call = AsyncMock(side_effect=_call)
    coordinator = _create_coordinator(hass, mock_config_entry)
    return coordinator, store, devices, world, calls


def _ac_calls(calls):
    return [(service, data) for service, eid, data in calls if eid == AC]


async def _cycle(coordinator):
    return (await coordinator._async_update_data())["rooms"][AREA]


def _saved(store, key):
    return [c.args[0][key] for c in store.async_save_settings.await_args_list if key in c.args[0]]


@pytest.mark.asyncio
async def test_without_an_upper_limit_nothing_changes(hass, mock_config_entry):
    room_cfg = {k: v for k, v in AC_ROOM.items() if k != "humidity_max"}
    coordinator, store, devices, _, calls = _setup(hass, mock_config_entry, room_cfg, humidity="90")
    room = await _cycle(coordinator)
    assert room["ac_dry_active"] is False and room["ac_dry_entities"] == []
    assert devices[AC].state == "off"
    assert not any(data.get("hvac_mode") == "dry" for _, data in _ac_calls(calls))
    assert _saved(store, "ac_dry_state") == []


@pytest.mark.asyncio
async def test_humid_room_in_its_band_dries(hass, mock_config_entry):
    coordinator, store, devices, world, calls = _setup(hass, mock_config_entry, AC_ROOM)
    with (
        patch.object(coordinator._ekf_training, "process") as train,
        patch.object(coordinator._rebound_tracker, "update") as rebound,
    ):
        room = await _cycle(coordinator)
        train.assert_not_called()  # dry cools: not learned as idle
        rebound.assert_called_once_with(AREA, "idle")
    assert room["humidity_high"] is True and room["mode"] == "idle"
    assert room["ac_dry_active"] is True and room["ac_dry_entities"] == [AC]
    assert _ac_calls(calls) == [("set_hvac_mode", {"hvac_mode": "dry"}), ("set_temperature", {"temperature": 21.5})]
    assert _saved(store, "ac_dry_state")[-1][AC]["area_id"] == AREA
    # The next cycle async_apply leaves the unit alone
    calls.clear()
    assert (await _cycle(coordinator))["ac_dry_active"] is True
    assert _ac_calls(calls) == []


@pytest.mark.asyncio
async def test_room_needing_cooling_cools_instead(hass, mock_config_entry):
    coordinator, _, devices, world, calls = _setup(hass, mock_config_entry, AC_ROOM)
    await _cycle(coordinator)
    world["temp"] = "27.0"
    room = await _cycle(coordinator)
    assert room["mode"] == "cooling" and room["ac_dry_active"] is False
    assert devices[AC].state == "cool"


@pytest.mark.asyncio
async def test_open_window_ends_dry(hass, mock_config_entry):
    room_cfg = {**AC_ROOM, "window_sensors": [WINDOW]}
    coordinator, _, devices, world, _ = _setup(hass, mock_config_entry, room_cfg)
    assert (await _cycle(coordinator))["ac_dry_active"] is True
    world["window"] = "on"
    room = await _cycle(coordinator)
    assert room["window_open"] is True and room["ac_dry_active"] is False
    assert devices[AC].state == "off"


@pytest.mark.asyncio
async def test_open_window_switches_a_setback_unit_off_without_its_setback_first(hass, mock_config_entry):
    room_cfg = {
        **AC_ROOM,
        "window_sensors": [WINDOW],
        "devices": [{"entity_id": AC, "type": "ac", "role": "auto", "idle_action": "setback"}],
    }
    coordinator, _, devices, world, calls = _setup(
        hass, mock_config_entry, room_cfg, **{AC: _ac(state="cool", temperature=27.0)}
    )
    assert (await _cycle(coordinator))["ac_dry_active"] is True
    world["window"] = "on"
    calls.clear()
    room = await _cycle(coordinator)
    assert room["window_open"] is True and room["ac_dry_active"] is False
    assert devices[AC].state == "off"
    assert not any(data.get("hvac_mode") == "cool" for _, data in _ac_calls(calls))


@pytest.mark.parametrize(
    ("room_patch", "kw"),
    [
        ({"temperature_sensor": ""}, {}),  # Managed: the unit regulates itself
        ({"climate_mode": "heat_only"}, {}),  # may not cool
        ({}, {"outdoor": "12.0"}),  # below the cooling minimum
        ({"dehumidifier_entity": DEHUM}, {DEHUM: SimpleNamespace(state="off", attributes={})}),
        ({}, {"temp": "21.8"}),  # below the start margin
    ],
)
@pytest.mark.asyncio
async def test_no_dry(hass, mock_config_entry, room_patch, kw):
    coordinator, _, _, _, calls = _setup(hass, mock_config_entry, {**AC_ROOM, **room_patch}, **kw)
    room = await _cycle(coordinator)
    assert room["ac_dry_active"] is False
    assert not any(data.get("hvac_mode") == "dry" for _, data in _ac_calls(calls))


@pytest.mark.parametrize("dehumidifier", [SimpleNamespace(state="unavailable", attributes={}), None])
@pytest.mark.asyncio
async def test_dehumidifier_gone_for_a_while_lets_the_ac_dry(hass, mock_config_entry, monkeypatch, dehumidifier):
    """Unavailable or without any state yet (HA still starting): the AC waits some minutes, then dries."""
    clock = [time.time()]
    monkeypatch.setattr(ac_dry_mod.time, "time", lambda: clock[0])
    room_cfg = {**AC_ROOM, "dehumidifier_entity": DEHUM}
    coordinator, *_ = _setup(hass, mock_config_entry, room_cfg, **{DEHUM: dehumidifier})
    assert (await _cycle(coordinator))["ac_dry_active"] is False
    clock[0] += AC_DRY_DEHUMIDIFIER_GONE_MINUTES * 60
    assert (await _cycle(coordinator))["ac_dry_active"] is True


@pytest.mark.asyncio
async def test_climate_control_off_switches_the_dry_unit_off_once(hass, mock_config_entry):
    coordinator, store, devices, _, calls = _setup(hass, mock_config_entry, AC_ROOM)
    await _cycle(coordinator)
    store.get_settings.return_value = {**store.get_settings.return_value, "climate_control_active": False}
    calls.clear()
    room = await _cycle(coordinator)
    assert room["ac_dry_active"] is False and devices[AC].state == "off"
    calls.clear()
    await _cycle(coordinator)
    assert _ac_calls(calls) == []


@pytest.mark.asyncio
async def test_restart_keeps_drying_inside_the_hysteresis(hass, mock_config_entry):
    """A unit RoomMind ran in dry before the restart: the room counts as too humid until the release."""
    settings = {"ac_dry_state": {AC: {"area_id": AREA, "since": 1.0}}}
    coordinator, _, devices, _, calls = _setup(hass, mock_config_entry, AC_ROOM, settings=settings, humidity="57")
    devices[AC].state = "dry"
    devices[AC].attributes["temperature"] = 21.5
    room = await _cycle(coordinator)
    assert room["humidity_high"] is True and room["ac_dry_active"] is True
    assert _ac_calls(calls) == []


@pytest.mark.asyncio
async def test_dry_wets_the_coil_and_coil_dry_follows(hass, mock_config_entry, monkeypatch):
    import custom_components.roommind.managers.ac_coil_dry_manager as coil_mod
    import custom_components.roommind.managers.ac_dry_manager as dry_mod

    clock = [100_000.0]
    monkeypatch.setattr(coil_mod.time, "time", lambda: clock[0])
    monkeypatch.setattr(dry_mod.time, "time", lambda: clock[0])
    settings = {"coil_dry_enabled": True, "coil_dry_min_cooling_minutes": 1, "coil_dry_mode": "fan_only"}
    coordinator, _, devices, world, _ = _setup(hass, mock_config_entry, AC_ROOM, settings=settings)
    assert (await _cycle(coordinator))["ac_dry_active"] is True
    clock[0] += 600
    room = await _cycle(coordinator)
    assert room["ac_dry_active"] is True and room["coil_dry_active"] is False
    world["humidity"] = "50"
    clock[0] += 60
    room = await _cycle(coordinator)  # dry ends, the unit goes to its idle action
    assert room["ac_dry_active"] is False
    clock[0] += 30
    room = await _cycle(coordinator)
    assert room["coil_dry_active"] is True and devices[AC].state == "fan_only"


@pytest.mark.asyncio
async def test_dry_unit_counts_as_running_group_member(hass, mock_config_entry):
    settings = {"compressor_groups": [{"id": "g1", "name": "Outdoor", "members": [AC], "min_run_minutes": 5}]}
    coordinator, *_ = _setup(hass, mock_config_entry, AC_ROOM, settings=settings)
    await _cycle(coordinator)
    assert AC in coordinator._compressor_manager.get_state("g1").active_members
    # The group's min run holds the drying unit: the room shows dry, not compressor protection
    room = await _cycle(coordinator)
    assert room["ac_dry_active"] is True
    assert room["compressor_protection_active"] is False and room["compressor_protection_until"] is None


def test_drying_room_asks_the_master_for_cooling_unless_a_room_heats(hass, mock_config_entry):
    coordinator, *_ = _setup(hass, mock_config_entry, AC_ROOM)
    other = {**SAMPLE_ROOM, "devices": [{"entity_id": "climate.bed_ac", "type": "ac"}]}
    rooms = {AREA: AC_ROOM, "bed": other}
    members = [AC, "climate.bed_ac"]
    drying = {"mode": "idle", "ac_dry_entities": [AC]}
    states = {AREA: drying, "bed": {"mode": "idle"}}
    assert coordinator._collect_member_room_modes(members, states, rooms, {}) == ["idle", "idle", "cooling"]
    states["bed"] = {"mode": "heating"}
    assert coordinator._collect_member_room_modes(members, states, rooms, {}) == ["idle", "heating"]
    states[AREA] = {"mode": "idle"}
    states["bed"] = {"mode": "idle"}
    assert coordinator._collect_member_room_modes(members, states, rooms, {}) == ["idle", "idle"]


async def _follow_setup(hass, mock_config_entry, monkeypatch):
    """A room taking device setpoints over, its AC drying; RoomMind's own sends reach the tracker."""
    clock = [time.time()]
    monkeypatch.setattr(ac_dry_mod.time, "time", lambda: clock[0])
    coordinator, store, devices, world, calls = _setup(
        hass, mock_config_entry, {**AC_ROOM, "follow_device_setpoint": True}
    )
    coordinator.device_setpoints._now = lambda: clock[0]
    store.async_update_room = AsyncMock()
    send = hass.services.async_call.side_effect

    async def _noted(domain, service, data, **kw):
        coordinator.device_setpoints.note_command(data["entity_id"], service, data, switch_to=data.get("hvac_mode"))
        await send(domain, service, data, **kw)

    hass.services.async_call = AsyncMock(side_effect=_noted)
    assert (await _cycle(coordinator))["ac_dry_active"] is True
    clock[0] += 600
    await _cycle(coordinator)
    return coordinator, store, devices, world, calls, clock


@pytest.mark.asyncio
async def test_setpoint_turned_on_a_drying_unit_is_no_cooling_override(hass, mock_config_entry, monkeypatch):
    """The remote moves how far the unit dries, not the room band: no override, the unit keeps the value."""
    coordinator, store, devices, world, calls, clock = await _follow_setup(hass, mock_config_entry, monkeypatch)
    devices[AC].attributes["temperature"] = 22.0
    calls.clear()
    clock[0] += 30
    room = await _cycle(coordinator)
    store.async_update_room.assert_not_awaited()
    assert room["ac_dry_active"] is True and room["override_active"] is False
    assert devices[AC].state == "dry" and _ac_calls(calls) == []
    # Nor later, once dry has ended
    world["humidity"] = "50"
    clock[0] += 600
    assert (await _cycle(coordinator))["ac_dry_active"] is False
    clock[0] += 30
    await _cycle(coordinator)
    store.async_update_room.assert_not_awaited()


@pytest.mark.asyncio
async def test_unit_switched_from_dry_to_cool_on_the_remote_is_taken_over(hass, mock_config_entry, monkeypatch):
    coordinator, store, devices, _, _, clock = await _follow_setup(hass, mock_config_entry, monkeypatch)
    devices[AC].state = "cool"
    devices[AC].attributes["temperature"] = 22.0
    clock[0] += 30
    await _cycle(coordinator)
    _, override = store.async_update_room.await_args.args
    assert override["override_cool"] == 22.0


@pytest.mark.asyncio
async def test_room_switch_off_keeps_the_ac_out_of_dry(hass, mock_config_entry):
    coordinator, _, _, _, calls = _setup(hass, mock_config_entry, {**AC_ROOM, "ac_dry_enabled": False})
    room = await _cycle(coordinator)
    assert room["humidity_high"] is True and room["ac_dry_active"] is False
    assert not any(data.get("hvac_mode") == "dry" for _, data in _ac_calls(calls))


@pytest.mark.asyncio
async def test_room_switch_off_ends_a_running_dry_and_gives_the_setback_back(hass, mock_config_entry):
    devices_cfg = [{"entity_id": AC, "type": "ac", "role": "auto", "idle_action": "setback"}]
    room_cfg = {**AC_ROOM, "devices": devices_cfg}
    coordinator, store, devices, _, calls = _setup(
        hass, mock_config_entry, room_cfg, **{AC: _ac(state="cool", temperature=27.0)}
    )
    assert (await _cycle(coordinator))["ac_dry_active"] is True
    store.get_rooms.return_value = {AREA: {**room_cfg, "ac_dry_enabled": False}}
    calls.clear()
    room = await _cycle(coordinator)
    assert room["ac_dry_active"] is False
    assert _ac_calls(calls) == [("set_temperature", {"hvac_mode": "cool", "temperature": 27.0})]
    assert devices[AC].state == "cool"
