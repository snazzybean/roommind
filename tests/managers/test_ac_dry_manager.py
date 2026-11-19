"""Tests for the AC dry manager (#440)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import custom_components.roommind.managers.ac_dry_manager as mod
from custom_components.roommind.control.mpc_controller import clear_command_cache
from custom_components.roommind.managers.ac_dry_manager import AcDryManager, dry_stop_temp

AC = "climate.living_ac"
AREA = "living"
STOP = 21.5  # heat 21 + 0.5


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_command_cache()
    yield
    clear_command_cache()


@pytest.fixture
def now(monkeypatch):
    clock = [10_000.0]
    monkeypatch.setattr(mod.time, "time", lambda: clock[0])
    return clock


def _hass(state="off", **attrs):
    hass = MagicMock()
    hass.config.units.temperature_unit = "°C"
    ac = SimpleNamespace(
        state=state,
        attributes={
            "hvac_modes": ["off", "cool", "heat", "dry", "fan_only"],
            "min_temp": 16.0,
            "max_temp": 30.0,
            "target_temp_step": 0.5,
            "temperature": 24.0,
            **attrs,
        },
    )
    hass.states.get = MagicMock(side_effect=lambda eid: ac if eid == AC else None)
    calls: list[tuple[str, dict]] = []

    async def _call(domain, service, data, **_kw):
        calls.append((service, {k: v for k, v in data.items() if k != "entity_id"}))
        if service == "set_hvac_mode":
            ac.state = data["hvac_mode"]
        if service == "set_temperature":
            ac.attributes["temperature"] = data["temperature"]
            if "hvac_mode" in data:
                ac.state = data["hvac_mode"]

    hass.services.async_call = AsyncMock(side_effect=_call)
    return hass, ac, calls


def _room(**device):
    return {"devices": [{"entity_id": AC, "type": "ac", "idle_action": "off", **device}]}


async def _process(mgr, *, room=None, **kw):
    args = {
        "area_id": AREA,
        "room": room or _room(),
        "mode": "idle",
        "too_humid": True,
        "allowed": True,
        "may_cool": True,
        "control_active": True,
        "waiting": False,
        "room_temp": 23.0,
        "stop_temp": STOP,
        "compressor_forced_on": set(),
        "blocked_eids": set(),
        "group_conflicts": {},
        "can_start": lambda _eid: True,
    }
    args.update(kw)
    return await mgr.async_process_room(**args)


# --- stop point ---------------------------------------------------------


@pytest.mark.parametrize(
    ("heat", "cool", "mode", "expected"),
    [
        (21.0, 24.0, "auto", 21.5),
        (17.0, 27.0, "auto", 24.5),  # wide eco band: not more than 3 K under the cool target
        (24.0, 24.0, "cool_only", 21.5),
        (None, 24.0, "auto", 21.5),
        (21.0, None, "heat_only", 21.5),
        (None, None, "auto", None),
    ],
)
def test_stop_point(heat, cool, mode, expected):
    assert dry_stop_temp(heat, cool, mode) == expected


# --- start --------------------------------------------------------------


@pytest.mark.asyncio
async def test_too_humid_idle_room_starts_dry_with_the_stop_point_as_setpoint(now):
    hass, ac, calls = _hass()
    mgr = AcDryManager(hass)
    result = await _process(mgr)
    assert result.drying_eids == {AC} and result.active and result.excluded_eids == {AC}
    assert calls == [("set_hvac_mode", {"hvac_mode": "dry"}), ("set_temperature", {"temperature": 21.5})]
    assert mgr.is_running(AC) and mgr.running_eids(AREA) == {AC}
    assert mgr.state_dirty
    # Next cycle: nothing new to send
    calls.clear()
    assert (await _process(mgr)).drying_eids == {AC}
    assert calls == []


@pytest.mark.asyncio
async def test_unit_already_in_dry_only_gets_the_setpoint(now):
    hass, _, calls = _hass(state="dry")
    await _process(AcDryManager(hass))
    assert calls == [("set_temperature", {"temperature": 21.5})]


@pytest.mark.asyncio
async def test_unit_without_a_single_setpoint_gets_only_the_mode(now):
    hass, ac, calls = _hass()
    del ac.attributes["temperature"]
    await _process(AcDryManager(hass))
    assert calls == [("set_hvac_mode", {"hvac_mode": "dry"})]


@pytest.mark.parametrize(
    "kw",
    [
        {"too_humid": False},
        {"allowed": False},
        {"may_cool": False},
        {"mode": "cooling"},
        {"mode": "heating"},
        {"control_active": False},
        {"waiting": True},
        {"stop_temp": None},
        {"room_temp": None},
        {"room_temp": 21.9},  # above the stop point, below the start margin
        {"blocked_eids": {AC}},
        {"window_open": True},
        {"compressor_forced_on": {AC}},
        {"group_conflicts": {AC: frozenset({"cool", "dry", "fan_only"})}},
        {"can_start": lambda _eid: False},
    ],
)
@pytest.mark.asyncio
async def test_no_start(now, kw):
    hass, _, calls = _hass()
    result = await _process(AcDryManager(hass), **kw)
    assert not result.active and calls == []


@pytest.mark.parametrize("attrs", [{"hvac_modes": ["off", "cool", "heat"]}, {"hvac_modes": None}])
@pytest.mark.asyncio
async def test_no_start_without_dry_mode(now, attrs):
    hass, _, calls = _hass(**attrs)
    assert not (await _process(AcDryManager(hass))).active and calls == []


@pytest.mark.asyncio
async def test_no_start_while_the_unit_does_not_read(now):
    hass, _, calls = _hass(state="unavailable")
    assert not (await _process(AcDryManager(hass))).active and calls == []


@pytest.mark.asyncio
async def test_start_margin_after_the_stop_point(now):
    """Below the stop point the room waits for the start margin (1 K above the heat target)."""
    hass, _, _ = _hass()
    mgr = AcDryManager(hass)
    assert not (await _process(mgr, room_temp=21.4)).active
    assert not (await _process(mgr, room_temp=21.9)).active
    assert (await _process(mgr, room_temp=22.0)).active


@pytest.mark.asyncio
async def test_no_dry_within_an_hour_of_heating(now):
    hass, _, _ = _hass()
    mgr = AcDryManager(hass)
    assert not (await _process(mgr, mode="heating")).active
    now[0] += 59 * 60
    assert not (await _process(mgr)).active
    now[0] += 60
    assert (await _process(mgr)).active


# --- the room's own dehumidifier ---------------------------------------


@pytest.mark.asyncio
async def test_dehumidifier_that_reads_keeps_the_ac_out(now):
    hass, _, calls = _hass()
    mgr = AcDryManager(hass)
    for _ in range(40):
        assert not (await _process(mgr, dehumidifier_reads=True)).active
        now[0] += 30
    assert calls == []


@pytest.mark.asyncio
async def test_dehumidifier_dropping_out_for_a_cycle_does_not_start_the_ac(now):
    hass, _, calls = _hass()
    mgr = AcDryManager(hass)
    for reads in (True, False, True, False, True):
        assert not (await _process(mgr, dehumidifier_reads=reads)).active
        now[0] += 30
    assert calls == []


@pytest.mark.asyncio
async def test_ac_steps_in_once_the_dehumidifier_was_gone_for_a_while(now):
    hass, _, _ = _hass()
    mgr = AcDryManager(hass)
    assert not (await _process(mgr, dehumidifier_reads=False)).active
    now[0] += mod.AC_DRY_DEHUMIDIFIER_GONE_MINUTES * 60 - 1
    assert not (await _process(mgr, dehumidifier_reads=False)).active
    now[0] += 1
    assert (await _process(mgr, dehumidifier_reads=False)).active
    # Still gone: dry goes on
    now[0] += 3600
    assert (await _process(mgr, dehumidifier_reads=False)).active


@pytest.mark.asyncio
async def test_dehumidifier_back_ends_dry_after_the_min_run_and_gives_the_setback_back(now):
    hass, _, calls = _hass(state="cool", temperature=27.0)
    mgr = AcDryManager(hass)
    room = _room(idle_action="setback")
    await _process(mgr, room=room, dehumidifier_reads=False)
    now[0] += mod.AC_DRY_DEHUMIDIFIER_GONE_MINUTES * 60
    assert (await _process(mgr, room=room, dehumidifier_reads=False)).active
    calls.clear()
    now[0] += 30
    assert (await _process(mgr, room=room, dehumidifier_reads=True)).active
    assert calls == []
    now[0] += mod.AC_DRY_MIN_RUN_MINUTES * 60
    result = await _process(mgr, room=room, dehumidifier_reads=True)
    assert not result.active and result.excluded_eids == {AC}
    assert calls == [("set_temperature", {"hvac_mode": "cool", "temperature": 27.0})]
    # Gone again for a moment: the AC does not jump back in
    now[0] += 30
    assert not (await _process(mgr, room=room, dehumidifier_reads=False)).active


# --- end ----------------------------------------------------------------


@pytest.mark.parametrize(
    "kw",
    [
        {"mode": "cooling"},
        {"mode": "heating"},
        {"allowed": False},
        {"window_open": True},
        {"group_conflicts": {AC: frozenset({"cool", "dry", "fan_only"})}},
    ],
)
@pytest.mark.asyncio
async def test_demand_or_a_block_ends_dry_at_once_and_leaves_the_unit_to_async_apply(now, kw):
    hass, _, calls = _hass()
    mgr = AcDryManager(hass)
    await _process(mgr)
    calls.clear()
    result = await _process(mgr, **kw)
    assert not result.active and result.excluded_eids == set()
    assert calls == [] and not mgr.is_running(AC)


@pytest.mark.asyncio
async def test_outdoor_reading_around_the_cooling_minimum_does_not_end_a_run(now):
    hass, _, _ = _hass()
    mgr = AcDryManager(hass)
    await _process(mgr)
    now[0] += 3600
    assert (await _process(mgr, may_cool=False)).active


@pytest.mark.asyncio
async def test_dry_enough_ends_after_the_min_run(now):
    hass, _, _ = _hass()
    mgr = AcDryManager(hass)
    await _process(mgr)
    now[0] += 9 * 60
    assert (await _process(mgr, too_humid=False)).active
    now[0] += 60
    assert not (await _process(mgr, too_humid=False)).active


@pytest.mark.asyncio
async def test_settling_for_half_an_hour_after_dry(now):
    hass, _, _ = _hass()
    mgr = AcDryManager(hass)
    assert not (await _process(mgr, too_humid=False)).settling
    assert (await _process(mgr)).settling
    now[0] += 3600
    ended = await _process(mgr, too_humid=False)
    assert not ended.active and ended.settling
    now[0] += 29 * 60
    assert (await _process(mgr, too_humid=False)).settling
    now[0] += 60
    assert not (await _process(mgr, too_humid=False)).settling


@pytest.mark.asyncio
async def test_compressor_hold_keeps_dry(now):
    """The group's min run holds the unit: it stays in dry and counts as drying (no EKF training)."""
    hass, _, _ = _hass()
    mgr = AcDryManager(hass)
    await _process(mgr)
    now[0] += 3600
    assert (await _process(mgr, too_humid=False, compressor_forced_on={AC})).active
    assert not (await _process(mgr, too_humid=False)).active


@pytest.mark.asyncio
async def test_stop_point_ends_dry_after_the_min_run(now):
    hass, _, _ = _hass()
    mgr = AcDryManager(hass)
    await _process(mgr)
    now[0] += 5 * 60
    assert (await _process(mgr, room_temp=21.5)).active
    now[0] += 5 * 60
    assert not (await _process(mgr, room_temp=21.5)).active
    # Back up to 21.9: still waiting for the start margin
    assert not (await _process(mgr, room_temp=21.9)).active
    # The air is back at the walls' temperature within minutes: a pause before the next run
    now[0] += 14 * 60
    assert not (await _process(mgr, room_temp=22.5)).active
    now[0] += 60
    assert (await _process(mgr, room_temp=22.5)).active


@pytest.mark.asyncio
async def test_hand_on_the_device_ends_dry_until_the_room_was_dry_enough(now):
    hass, ac, calls = _hass()
    mgr = AcDryManager(hass)
    await _process(mgr)
    assert (await _process(mgr)).active  # shown in dry: confirmed
    ac.state = "cool"
    calls.clear()
    assert not (await _process(mgr)).active
    now[0] += 3600
    assert not (await _process(mgr)).active
    assert calls == []
    # The room dried (by other means), then turns humid again: dry may start again
    await _process(mgr, too_humid=False)
    assert (await _process(mgr)).active


@pytest.mark.asyncio
async def test_unit_that_does_not_take_dry_is_left_alone(now):
    hass, ac, calls = _hass()

    async def _ignore(domain, service, data, **_kw):
        calls.append((service, data))

    hass.services.async_call = AsyncMock(side_effect=_ignore)
    mgr = AcDryManager(hass)
    await _process(mgr)
    now[0] += 240
    assert (await _process(mgr)).active  # may still be reporting late
    now[0] += 60
    assert not (await _process(mgr)).active
    assert not (await _process(mgr)).active


@pytest.mark.asyncio
async def test_unknown_state_keeps_dry_without_judging(now):
    hass, ac, _ = _hass()
    mgr = AcDryManager(hass)
    await _process(mgr)
    ac.state = "unknown"
    now[0] += 3600
    assert (await _process(mgr)).active


@pytest.mark.asyncio
async def test_waiting_for_data_keeps_dry_and_sends_nothing(now):
    hass, ac, calls = _hass()
    mgr = AcDryManager(hass)
    await _process(mgr)
    calls.clear()
    now[0] += 3600
    result = await _process(mgr, waiting=True, too_humid=False)
    assert result.drying_eids == {AC} and calls == []


@pytest.mark.asyncio
async def test_climate_control_off_switches_the_dry_unit_off_once(now):
    hass, ac, calls = _hass()
    mgr = AcDryManager(hass)
    await _process(mgr)
    calls.clear()
    assert not (await _process(mgr, control_active=False)).active
    assert ("set_hvac_mode", {"hvac_mode": "off"}) in calls
    calls.clear()
    await _process(mgr, control_active=False)
    assert calls == []


@pytest.mark.asyncio
async def test_climate_control_off_leaves_a_unit_no_longer_in_dry(now):
    hass, ac, calls = _hass()
    mgr = AcDryManager(hass)
    await _process(mgr)
    ac.state = "heat"
    calls.clear()
    await _process(mgr, control_active=False)
    assert calls == []


@pytest.mark.asyncio
async def test_setback_unit_gets_its_mode_and_setpoint_back(now):
    hass, ac, calls = _hass(state="cool", temperature=27.0)
    mgr = AcDryManager(hass)
    room = _room(idle_action="setback")
    await _process(mgr, room=room)
    now[0] += 3600
    calls.clear()
    result = await _process(mgr, room=room, too_humid=False)
    assert not result.active and result.excluded_eids == {AC}
    assert calls == [("set_temperature", {"hvac_mode": "cool", "temperature": 27.0})]


@pytest.mark.asyncio
async def test_setback_unit_gets_its_mode_back_when_the_room_may_no_longer_dry(now):
    hass, ac, calls = _hass(state="cool", temperature=27.0)
    mgr = AcDryManager(hass)
    room = _room(idle_action="setback")
    await _process(mgr, room=room)
    calls.clear()
    result = await _process(mgr, room=room, allowed=False)
    assert result.excluded_eids == {AC}
    assert calls == [("set_temperature", {"hvac_mode": "cool", "temperature": 27.0})]


@pytest.mark.asyncio
async def test_open_window_ends_dry_at_once_and_leaves_the_setback_unit_to_async_apply(now):
    """The window pause switches the unit off; a setback sent first would cool against the open window."""
    hass, ac, calls = _hass(state="cool", temperature=27.0)
    mgr = AcDryManager(hass)
    room = _room(idle_action="setback")
    await _process(mgr, room=room)
    calls.clear()
    result = await _process(mgr, room=room, window_open=True)
    assert not result.active and result.excluded_eids == set()
    assert calls == [] and not mgr.is_running(AC)


@pytest.mark.parametrize(
    "kw",
    [
        {"switched_off": True},  # async_apply switches it off
        {"group_conflicts": {AC: frozenset({"heat"})}},  # the group cools: no heat setback next to it
    ],
)
@pytest.mark.asyncio
async def test_setback_unit_is_not_restored(now, kw):
    hass, ac, calls = _hass(state="heat", temperature=19.0)
    mgr = AcDryManager(hass)
    room = _room(idle_action="setback")
    await _process(mgr, room=room)
    now[0] += 3600
    calls.clear()
    result = await _process(mgr, room=room, allowed=False, **kw)
    assert not result.active and result.excluded_eids == set() and calls == []


@pytest.mark.asyncio
async def test_unit_moved_to_another_room_dries_there(now):
    hass, _, _ = _hass()
    mgr = AcDryManager(hass)
    await _process(mgr)
    assert (await _process(mgr, area_id="bedroom")).active
    assert mgr.running_eids("bedroom") == {AC} and mgr.running_eids(AREA) == set()


@pytest.mark.asyncio
async def test_setback_unit_is_left_to_coil_dry(now):
    hass, ac, calls = _hass(state="cool", temperature=27.0)
    mgr = AcDryManager(hass)
    room = _room(idle_action="setback")
    await _process(mgr, room=room)
    now[0] += 3600
    calls.clear()
    result = await _process(mgr, room=room, too_humid=False, coil_dry_follows=lambda _eid: True)
    assert result.excluded_eids == set() and calls == []


@pytest.mark.asyncio
async def test_setback_unit_is_not_restored_when_the_room_cools(now):
    hass, ac, calls = _hass(state="cool", temperature=27.0)
    mgr = AcDryManager(hass)
    room = _room(idle_action="setback")
    await _process(mgr, room=room)
    calls.clear()
    result = await _process(mgr, room=room, mode="cooling")
    assert result.excluded_eids == set() and calls == []


@pytest.mark.asyncio
async def test_setpoint_follows_a_moved_stop_point(now):
    hass, _, calls = _hass()
    mgr = AcDryManager(hass)
    await _process(mgr)
    calls.clear()
    await _process(mgr, stop_temp=22.5, room_temp=23.5)
    assert calls == [("set_temperature", {"temperature": 22.5})]
    calls.clear()
    await _process(mgr, stop_temp=22.5, room_temp=23.5)
    assert calls == []


@pytest.mark.asyncio
async def test_direct_unit_gets_its_offset_on_the_setpoint(now):
    hass, _, calls = _hass()
    room = _room(setpoint_mode="direct", setpoint_offset=-1.0)
    await _process(AcDryManager(hass), room=room)
    assert ("set_temperature", {"temperature": 20.5}) in calls


# --- persistence --------------------------------------------------------


@pytest.mark.asyncio
async def test_state_round_trip_and_a_hand_after_the_restart(now):
    hass, ac, _ = _hass(state="cool", temperature=27.0)
    mgr = AcDryManager(hass)
    await _process(mgr, room=_room(idle_action="setback"))
    saved = mgr.get_state()
    assert saved == {
        AC: {"area_id": AREA, "since": 10_000.0, "setpoint": 21.5, "prev_mode": "cool", "prev_temperature": 27.0}
    }
    restored = AcDryManager(hass)
    restored.load_state(saved)
    assert restored.get_state() == saved and restored.running_eids(AREA) == {AC}
    # Restart while the unit was switched by hand: counts as a hand, dry ends
    ac.state = "off"
    assert not (await _process(restored)).active


@pytest.mark.parametrize(
    "data",
    [None, [], {AC: "x"}, {AC: {"since": 1.0}}, {AC: {"area_id": AREA}}, {AC: {"area_id": AREA, "since": "x"}}],
)
def test_load_ignores_malformed_state(data):
    mgr = AcDryManager(MagicMock())
    mgr.load_state(data)
    assert mgr.get_state() == {}


def test_load_drops_unknown_previous_mode():
    mgr = AcDryManager(MagicMock())
    mgr.load_state({AC: {"area_id": AREA, "since": 1, "prev_mode": "dry", "setpoint": "x"}})
    assert mgr.get_state()[AC] == {
        "area_id": AREA,
        "since": 1.0,
        "setpoint": None,
        "prev_mode": None,
        "prev_temperature": None,
    }


@pytest.mark.asyncio
async def test_prune_and_remove_room(now):
    hass, _, _ = _hass()
    mgr = AcDryManager(hass)
    await _process(mgr)
    mgr.state_dirty = False
    mgr.prune({AC})
    assert mgr.is_running(AC) and not mgr.state_dirty
    mgr.prune(set())
    assert not mgr.is_running(AC) and mgr.state_dirty
    await _process(mgr)
    mgr.remove_room(AREA)
    assert not mgr.is_running(AC)
