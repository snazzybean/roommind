"""Tests for room_fan_manager.py: when a room wants its fan while RoomMind heats or cools (#266)."""

from __future__ import annotations

import pytest

from custom_components.roommind.const import (
    MODE_COOLING,
    MODE_HEATING,
    MODE_IDLE,
    ROOM_FAN_POST_HEAT_MAX_MINUTES,
    ROOM_FAN_POST_RUN_MINUTES,
)
from custom_components.roommind.managers.room_fan_manager import (
    RoomFanTracker,
    room_fan_claims,
    room_fan_mode,
)

FAN = "fan.living_ceiling"
AREA = "living"


def _room(fan_mode: str | None = None, system: str = "radiator", **extra) -> dict:
    room = {"room_fan_entity": FAN, "heating_system_type": system, **extra}
    if fan_mode is not None:
        room["room_fan_mode"] = fan_mode
    return room


def _claims(tracker, room, rs, now, running=frozenset()):
    return room_fan_claims({AREA: room}, {AREA: rs}, tracker, now, lambda e: e in running)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, "both"), ("heat", "heat"), ("cool", "cool"), ("both", "both"), ("bogus", "both")],
)
def test_room_fan_mode_defaults_to_both(value, expected):
    room = {} if value is None else {"room_fan_mode": value}
    assert room_fan_mode(room) == expected


def test_no_fan_entity_claims_nothing():
    tracker = RoomFanTracker()
    wanted, blocked = room_fan_claims(
        {AREA: {"heating_system_type": "radiator"}}, {AREA: {"mode": MODE_HEATING}}, tracker, 0, lambda e: False
    )
    assert wanted == {} and blocked == set()


@pytest.mark.parametrize(
    ("fan_mode", "mode", "want"),
    [
        ("both", MODE_HEATING, True),
        ("both", MODE_COOLING, True),
        ("heat", MODE_HEATING, True),
        ("heat", MODE_COOLING, False),
        ("cool", MODE_HEATING, False),
        ("cool", MODE_COOLING, True),
        ("both", MODE_IDLE, False),
    ],
)
def test_runs_while_the_room_heats_or_cools_as_chosen(fan_mode, mode, want):
    wanted, _ = _claims(RoomFanTracker(), _room(fan_mode), {"mode": mode}, 1000.0)
    # An entry also when not wanted: an owned fan then goes off after its min run, not at once
    assert wanted == {FAN: want}


def test_the_stop_cycle_keeps_the_fan_although_no_afterglow_shows_yet():
    """In the first idle cycle after a run q_residual is still 0 (it is computed from the previous mode)."""
    tracker = RoomFanTracker()
    _claims(tracker, _room(), {"mode": MODE_HEATING}, 0.0)
    wanted, _ = _claims(tracker, _room(), {"mode": MODE_IDLE, "q_residual": 0.0}, 30.0)
    assert wanted[FAN] is True


@pytest.mark.parametrize("system", ["", "radiator"])
def test_post_run_after_heating_lasts_the_fixed_minutes_without_afterglow(system):
    tracker = RoomFanTracker()
    _claims(tracker, _room(system=system), {"mode": MODE_HEATING}, 0.0)
    rs = {"mode": MODE_IDLE, "q_residual": 0.0}
    end = ROOM_FAN_POST_RUN_MINUTES * 60
    assert _claims(tracker, _room(system=system), rs, end - 1)[0][FAN] is True
    assert _claims(tracker, _room(system=system), rs, end)[0][FAN] is False


def test_radiator_post_run_follows_the_afterglow_up_to_the_cap():
    tracker = RoomFanTracker()
    _claims(tracker, _room(), {"mode": MODE_HEATING}, 0.0)
    glowing = {"mode": MODE_IDLE, "q_residual": 0.05}
    assert _claims(tracker, _room(), glowing, ROOM_FAN_POST_RUN_MINUTES * 60 + 60)[0][FAN] is True
    cap = ROOM_FAN_POST_HEAT_MAX_MINUTES * 60
    assert _claims(tracker, _room(), glowing, cap - 1)[0][FAN] is True
    assert _claims(tracker, _room(), glowing, cap)[0][FAN] is False


def test_radiator_post_run_ends_with_the_afterglow_and_does_not_come_back():
    tracker = RoomFanTracker()
    _claims(tracker, _room(), {"mode": MODE_HEATING}, 0.0)
    t = ROOM_FAN_POST_RUN_MINUTES * 60 + 60
    assert _claims(tracker, _room(), {"mode": MODE_IDLE, "q_residual": 0.0}, t)[0][FAN] is False
    assert _claims(tracker, _room(), {"mode": MODE_IDLE, "q_residual": 0.05}, t + 30)[0][FAN] is False


def test_underfloor_has_no_post_run():
    """A screed glows for hours; the fan ran through the whole long run already."""
    tracker = RoomFanTracker()
    room = _room(system="underfloor")
    _claims(tracker, room, {"mode": MODE_HEATING}, 0.0)
    assert _claims(tracker, room, {"mode": MODE_IDLE, "q_residual": 0.8}, 30.0)[0][FAN] is False


def test_short_post_run_after_cooling_bridges_the_pauses_between_ac_runs():
    tracker = RoomFanTracker()
    _claims(tracker, _room(), {"mode": MODE_COOLING}, 0.0)
    end = ROOM_FAN_POST_RUN_MINUTES * 60
    # No afterglow after cooling: q_residual does not stretch it
    assert _claims(tracker, _room(), {"mode": MODE_IDLE, "q_residual": 0.2}, end - 1)[0][FAN] is True
    assert _claims(tracker, _room(), {"mode": MODE_IDLE, "q_residual": 0.2}, end)[0][FAN] is False


def test_heating_ends_a_cool_post_run_of_a_cooling_fan():
    tracker = RoomFanTracker()
    _claims(tracker, _room("cool"), {"mode": MODE_COOLING}, 0.0)
    assert _claims(tracker, _room("cool"), {"mode": MODE_HEATING}, 30.0)[0][FAN] is False
    assert _claims(tracker, _room("cool"), {"mode": MODE_IDLE}, 60.0)[0][FAN] is False


def test_cooling_ends_a_heat_post_run():
    tracker = RoomFanTracker()
    _claims(tracker, _room("heat"), {"mode": MODE_HEATING}, 0.0)
    assert _claims(tracker, _room("heat"), {"mode": MODE_COOLING}, 30.0)[0][FAN] is False
    assert _claims(tracker, _room("heat"), {"mode": MODE_IDLE}, 60.0)[0][FAN] is False


def test_heating_with_a_cool_only_fan_leaves_no_post_run():
    tracker = RoomFanTracker()
    _claims(tracker, _room("cool"), {"mode": MODE_HEATING}, 0.0)
    assert _claims(tracker, _room("cool"), {"mode": MODE_IDLE}, 30.0)[0][FAN] is False


def test_open_window_blocks_the_fan_and_drops_the_post_run():
    tracker = RoomFanTracker()
    _claims(tracker, _room(), {"mode": MODE_HEATING}, 0.0)
    wanted, blocked = _claims(tracker, _room(), {"mode": MODE_IDLE, "window_open": True}, 30.0)
    assert wanted == {} and blocked == {FAN}
    # The heat left through the window: no post-run once it is closed
    assert _claims(tracker, _room(), {"mode": MODE_IDLE}, 60.0)[0][FAN] is False


def test_waiting_for_data_holds_the_fan_as_it_is():
    """After a restart the room idles until its sensors report; the fan RoomMind runs is not cut."""
    rs = {"mode": MODE_IDLE, "waiting_for_data": True}
    assert _claims(RoomFanTracker(), _room(), rs, 0.0, running={FAN})[0][FAN] is True
    assert _claims(RoomFanTracker(), _room(), rs, 0.0)[0][FAN] is False


def test_one_fan_in_two_rooms_runs_while_either_wants_it_and_a_window_blocks_it():
    tracker = RoomFanTracker()
    rooms = {"a": _room(), "b": _room()}
    wanted, _ = room_fan_claims(
        rooms, {"a": {"mode": MODE_IDLE}, "b": {"mode": MODE_HEATING}}, tracker, 0, lambda e: False
    )
    assert wanted == {FAN: True}
    wanted, blocked = room_fan_claims(
        rooms,
        {"a": {"mode": MODE_IDLE, "window_open": True}, "b": {"mode": MODE_HEATING}},
        tracker,
        30,
        lambda e: False,
    )
    assert wanted == {} and blocked == {FAN}


def test_outdoor_room_claims_nothing():
    wanted, blocked = _claims(RoomFanTracker(), _room(is_outdoor=True), {"mode": MODE_HEATING}, 0.0)
    assert wanted == {} and blocked == set()


def test_rooms_no_longer_passed_lose_their_post_run():
    """Climate control off in the room: on again later, no stale post-run starts the fan."""
    tracker = RoomFanTracker()
    _claims(tracker, _room(), {"mode": MODE_HEATING}, 0.0)
    room_fan_claims({}, {}, tracker, 30.0, lambda e: False)
    assert _claims(tracker, _room(), {"mode": MODE_IDLE}, 60.0)[0][FAN] is False


def test_remove_room_drops_the_post_run():
    tracker = RoomFanTracker()
    _claims(tracker, _room(), {"mode": MODE_HEATING}, 0.0)
    tracker.remove_room(AREA)
    assert _claims(tracker, _room(), {"mode": MODE_IDLE}, 30.0)[0][FAN] is False
