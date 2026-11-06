"""Tests for DeviceSetpointTracker: setpoints changed on the device itself (#259)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.core import Context, Event

from custom_components.roommind.const import (
    DEVICE_SETPOINT_ECHO_SECONDS,
    DEVICE_SETPOINT_GAP_SECONDS,
    DEVICE_SETPOINT_MODE_REPORT_SECONDS,
    DEVICE_SETPOINT_SETTLE_SECONDS,
    make_roommind_context,
)
from custom_components.roommind.managers.device_setpoint_tracker import DeviceSetpointTracker, _mode_switched_to

EID = "climate.trv"
TOL = 0.25


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def _tracker() -> tuple[DeviceSetpointTracker, Clock]:
    clock = Clock()
    return DeviceSetpointTracker(clock), clock


def _observe(tracker, value, attr="temperature", echo_tolerance=TOL, state="heat"):
    return tracker.observe(EID, state, {attr: value}, TOL, echo_tolerance)


def _send(tracker, value):
    tracker.note_command(EID, "set_temperature", {"entity_id": EID, "temperature": value})


def test_first_reading_is_only_the_baseline():
    tracker, _ = _tracker()
    assert _observe(tracker, 21.0) == {}


def test_a_change_nobody_at_roommind_sent_is_reported():
    tracker, clock = _tracker()
    _observe(tracker, 21.0)
    clock.t += 30
    assert _observe(tracker, 23.0) == {"temperature": (21.0, 23.0)}
    clock.t += 30
    assert _observe(tracker, 23.0) == {}


def test_own_setpoint_reported_late_is_not_a_change():
    tracker, clock = _tracker()
    _observe(tracker, 21.0)
    _send(tracker, 26.3)
    clock.t += 600
    # A device without a known step rounds the unrounded value
    assert _observe(tracker, 26.0, echo_tolerance=0.5) == {}


def test_a_turn_right_after_an_own_setpoint_counts():
    tracker, clock = _tracker()
    _observe(tracker, 28.0)
    _send(tracker, 29.5)
    clock.t += 30
    assert _observe(tracker, 29.5) == {}
    clock.t += 10
    assert _observe(tracker, 22.0) == {"temperature": (29.5, 22.0)}


def test_a_turn_reported_in_steps_counts_every_step():
    tracker, clock = _tracker()
    _observe(tracker, 29.5)
    clock.t += 30
    assert _observe(tracker, 26.0) == {"temperature": (29.5, 26.0)}
    _send(tracker, 27.5)
    clock.t += 30
    # The rest of the turn arrives before the setpoint RoomMind sent for the first part
    assert _observe(tracker, 22.0) == {"temperature": (26.0, 22.0)}


def test_value_restored_with_a_mode_switch_is_ours():
    tracker, clock = _tracker()
    _observe(tracker, 28.0)
    tracker.note_command(EID, "set_hvac_mode", {"entity_id": EID, "hvac_mode": "off"}, switch_to="off")
    clock.t += 30
    # Mode shown first, the stored setpoint follows in a separate update
    assert _observe(tracker, 28.0, state="off") == {}
    clock.t += DEVICE_SETPOINT_MODE_REPORT_SECONDS - 31
    assert _observe(tracker, 5.0, state="off") == {}
    clock.t += 60
    assert _observe(tracker, 7.0, state="off") == {"temperature": (5.0, 7.0)}


def test_mode_and_setpoint_reported_late_together_are_ours():
    tracker, clock = _tracker()
    _observe(tracker, 28.0)
    tracker.note_command(EID, "set_hvac_mode", {"entity_id": EID, "hvac_mode": "off"}, switch_to="off")
    clock.t += DEVICE_SETPOINT_SETTLE_SECONDS - 30
    assert _observe(tracker, 28.0) == {}
    clock.t += 20
    assert _observe(tracker, 5.0, state="off") == {}


def test_a_turn_minutes_after_a_mode_switch_counts():
    tracker, clock = _tracker()
    _observe(tracker, 16.0, state="heat")
    tracker.note_command(EID, "set_hvac_mode", {"entity_id": EID, "hvac_mode": "off"}, switch_to="off")
    clock.t += 30
    _observe(tracker, 16.0, state="off")
    clock.t += DEVICE_SETPOINT_MODE_REPORT_SECONDS + 30
    assert _observe(tracker, 30.0, state="off") == {"temperature": (16.0, 30.0)}


def test_rounding_within_the_tolerance_is_not_a_change():
    tracker, clock = _tracker()
    _observe(tracker, 21.0)
    clock.t += 30
    assert _observe(tracker, 21.2) == {}


def test_a_value_the_device_already_showed_is_no_echo_any_more():
    tracker, clock = _tracker()
    _observe(tracker, 17.0)
    _send(tracker, 21.0)
    clock.t += 30
    _observe(tracker, 21.0)
    _send(tracker, 17.0)
    clock.t += 30
    _observe(tracker, 17.0)
    clock.t += 30
    # Turned back to the earlier value: RoomMind's 21 was shown long ago
    assert _observe(tracker, 21.0) == {"temperature": (17.0, 21.0)}


def test_an_old_send_no_longer_explains_a_value():
    tracker, clock = _tracker()
    _send(tracker, 23.0)
    _observe(tracker, 21.0)
    for _ in range(DEVICE_SETPOINT_ECHO_SECONDS // 60 + 1):
        clock.t += 60
        _observe(tracker, 21.0)
    assert _observe(tracker, 23.0) == {"temperature": (21.0, 23.0)}


def test_a_device_back_from_unavailable_starts_over():
    tracker, clock = _tracker()
    _observe(tracker, 29.5)
    tracker.forget_readings(EID)
    clock.t += 30
    assert _observe(tracker, 20.0) == {}


def test_range_sides_are_tracked_apart_and_missing_values_skipped():
    tracker, clock = _tracker()
    tracker.observe(
        EID, "heat_cool", {"target_temp_low": 20.0, "target_temp_high": 25.0, "temperature": None}, TOL, TOL
    )
    clock.t += 30
    changes = tracker.observe(
        EID, "heat_cool", {"target_temp_low": 20.0, "target_temp_high": 26.0, "temperature": "n/a"}, TOL, TOL
    )
    assert changes == {"target_temp_high": (25.0, 26.0)}


def test_set_temperature_without_setpoint_is_not_an_echo():
    tracker, clock = _tracker()
    _observe(tracker, 21.0)
    tracker.note_command(EID, "set_temperature", {"hvac_mode": "heat"})
    clock.t += 5
    assert _observe(tracker, 22.0) == {"temperature": (21.0, 22.0)}


def test_prune_forgets_removed_devices():
    tracker, clock = _tracker()
    _observe(tracker, 21.0)
    tracker.note_command(EID, "set_hvac_mode", {"hvac_mode": "heat"}, switch_to="heat")
    tracker.prune(set())
    # Baseline gone: the next reading starts over
    assert _observe(tracker, 25.0) == {}
    assert _observe(tracker, 26.0) == {"temperature": (25.0, 26.0)}


@pytest.mark.parametrize(
    ("service", "data", "current", "expected"),
    [
        ("turn_off", {}, "heat", "off"),
        ("turn_off", {}, "off", None),
        ("turn_on", {}, "off", "*on"),
        ("turn_on", {}, "heat", None),
        ("set_hvac_mode", {"hvac_mode": "heat"}, "off", "heat"),
        ("set_temperature", {"temperature": 22, "hvac_mode": "heat"}, "heat", None),
        ("set_temperature", {"temperature": 22}, "heat", None),
        ("set_fan_mode", {"fan_mode": "low"}, "fan_only", None),
    ],
)
def test_mode_switched_to(service, data, current, expected):
    assert _mode_switched_to(service, data, current) == expected


def test_own_range_send_is_no_change():
    tracker, clock = _tracker()
    tracker.observe(EID, "heat_cool", {"target_temp_low": 21.0, "target_temp_high": 24.0}, TOL, TOL)
    tracker.note_command(EID, "set_temperature", {"target_temp_low": 21.0, "target_temp_high": 19.0})
    clock.t += 30
    assert tracker.observe(EID, "heat_cool", {"target_temp_low": 21.0, "target_temp_high": 19.0}, TOL, TOL) == {}


def test_a_mode_someone_else_picks_is_no_restore():
    tracker, clock = _tracker()
    _observe(tracker, 24.0, state="heat")
    tracker.note_command(EID, "set_hvac_mode", {"hvac_mode": "off"}, switch_to="off")
    clock.t += 30
    _observe(tracker, 24.0, state="off")
    clock.t += 90
    # Remote: on to heat at 25 two minutes after RoomMind stopped the unit
    assert _observe(tracker, 25.0, state="heat") == {"temperature": (24.0, 25.0)}


def test_setpoint_reported_before_the_commanded_mode_is_ours():
    tracker, clock = _tracker()
    _observe(tracker, 29.5, state="heat")
    tracker.note_command(EID, "set_hvac_mode", {"hvac_mode": "off"}, switch_to="off")
    clock.t += 30
    assert _observe(tracker, 5.0, state="heat") == {}
    clock.t += 30
    assert _observe(tracker, 5.0, state="off") == {}


def test_turn_on_counts_any_mode_but_off():
    tracker, clock = _tracker()
    _observe(tracker, 5.0, state="off")
    tracker.note_command(EID, "turn_on", {}, switch_to="*on")
    clock.t += 30
    assert _observe(tracker, 21.0, state="heat") == {}


def test_track_records_roommind_climate_calls_only():
    tracker, clock = _tracker()
    hass = MagicMock()
    hass.states.get.return_value = MagicMock(state="heat")
    unsub = tracker.async_track(hass)
    assert unsub is hass.bus.async_listen.return_value
    _, record = hass.bus.async_listen.call_args.args
    event_filter = hass.bus.async_listen.call_args.kwargs["event_filter"]
    assert event_filter({"domain": "climate"}) is True
    assert event_filter({"domain": "light"}) is False

    def call(service, data, context):
        record(Event("call_service", {"domain": "climate", "service": service, "service_data": data}, context=context))

    tracker.observe(EID, "heat", {"temperature": 21.0}, TOL, TOL)
    tracker.observe("climate.other", "heat", {"temperature": 21.0}, TOL, TOL)
    # Someone else's call is not RoomMind's command
    call("set_temperature", {"entity_id": EID, "temperature": 24.0}, Context())
    call("set_temperature", {"entity_id": ["climate.other"], "temperature": 22.0}, make_roommind_context())
    call("set_hvac_mode", {"entity_id": "climate.third", "hvac_mode": "off"}, make_roommind_context())
    clock.t += 30
    assert tracker.observe(EID, "heat", {"temperature": 24.0}, TOL, TOL) == {"temperature": (21.0, 24.0)}
    assert tracker.observe("climate.other", "heat", {"temperature": 22.0}, TOL, TOL) == {}
    tracker.observe("climate.third", "heat", {"temperature": 21.0}, TOL, TOL)
    assert tracker.observe("climate.third", "heat", {"temperature": 5.0}, TOL, TOL) == {}


def test_a_reading_from_before_a_gap_is_no_baseline():
    tracker, clock = _tracker()
    _observe(tracker, 29.5)
    # Room rested meanwhile and RoomMind switched the device off long ago
    clock.t += DEVICE_SETPOINT_GAP_SECONDS
    assert _observe(tracker, 5.0) == {}
    clock.t += 30
    assert _observe(tracker, 7.0) == {"temperature": (5.0, 7.0)}


def test_a_mode_switch_resent_every_cycle_keeps_its_start():
    tracker, clock = _tracker()
    _observe(tracker, 21.0, state="auto")
    for _ in range(12):
        # A device that keeps showing "auto" gets "heat" again every cycle
        tracker.note_command(EID, "set_hvac_mode", {"hvac_mode": "heat"}, switch_to="heat")
        clock.t += 30
        _observe(tracker, 21.0, state="auto")
    assert _observe(tracker, 23.0, state="auto") == {"temperature": (21.0, 23.0)}
