"""Tests for WindowManager."""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from custom_components.roommind.const import MAX_SENSOR_STALENESS
from custom_components.roommind.managers.window_manager import WindowManager


def test_is_paused_default_false():
    """is_paused returns False for an unknown room."""
    mgr = WindowManager()
    assert mgr.is_paused("living_room") is False


def test_is_paused_after_window_opens():
    """is_paused returns True after window has been open past the delay."""
    mgr = WindowManager()
    # open_delay=0 → immediate pause
    mgr.update("living_room", raw_open=True, open_delay=0, close_delay=0)
    assert mgr.is_paused("living_room") is True


def test_open_delay_not_yet_reached():
    """Window opens with open_delay=30, update within 30s. Not paused yet."""
    mgr = WindowManager()
    with patch("custom_components.roommind.managers.window_manager.time") as mock_time:
        # Establish room as known (window closed initially)
        mock_time.time.return_value = 900.0
        mgr.update("living_room", raw_open=False, open_delay=30, close_delay=0)

        mock_time.time.return_value = 1000.0
        result = mgr.update("living_room", raw_open=True, open_delay=30, close_delay=0)
        assert result is False
        assert mgr.is_paused("living_room") is False

        # 15s later, still within delay
        mock_time.time.return_value = 1015.0
        result = mgr.update("living_room", raw_open=True, open_delay=30, close_delay=0)
        assert result is False
        assert mgr.is_paused("living_room") is False


def test_open_delay_reached():
    """Window opens with open_delay=30, update after 30s. Now paused."""
    mgr = WindowManager()
    with patch("custom_components.roommind.managers.window_manager.time") as mock_time:
        # Establish room as known (window closed initially)
        mock_time.time.return_value = 900.0
        mgr.update("living_room", raw_open=False, open_delay=30, close_delay=0)

        mock_time.time.return_value = 1000.0
        mgr.update("living_room", raw_open=True, open_delay=30, close_delay=0)
        assert mgr.is_paused("living_room") is False

        # Exactly 30s later
        mock_time.time.return_value = 1030.0
        result = mgr.update("living_room", raw_open=True, open_delay=30, close_delay=0)
        assert result is True
        assert mgr.is_paused("living_room") is True


def test_close_delay_not_yet_reached():
    """Window was open (paused), now closed. close_delay=30, within 30s. Still paused."""
    mgr = WindowManager()
    with patch("custom_components.roommind.managers.window_manager.time") as mock_time:
        # Open window, immediate pause
        mock_time.time.return_value = 1000.0
        mgr.update("living_room", raw_open=True, open_delay=0, close_delay=0)
        assert mgr.is_paused("living_room") is True

        # Close window at t=1010, close_delay=30
        mock_time.time.return_value = 1010.0
        result = mgr.update("living_room", raw_open=False, open_delay=0, close_delay=30)
        assert result is True
        assert mgr.is_paused("living_room") is True

        # 15s after close, still within delay
        mock_time.time.return_value = 1025.0
        result = mgr.update("living_room", raw_open=False, open_delay=0, close_delay=30)
        assert result is True
        assert mgr.is_paused("living_room") is True


def test_close_delay_reached():
    """Window closed, close_delay=30, update after 30s. Unpaused."""
    mgr = WindowManager()
    with patch("custom_components.roommind.managers.window_manager.time") as mock_time:
        # Open window, immediate pause
        mock_time.time.return_value = 1000.0
        mgr.update("living_room", raw_open=True, open_delay=0, close_delay=0)
        assert mgr.is_paused("living_room") is True

        # Close window at t=1010
        mock_time.time.return_value = 1010.0
        mgr.update("living_room", raw_open=False, open_delay=0, close_delay=30)
        assert mgr.is_paused("living_room") is True

        # 30s after close
        mock_time.time.return_value = 1040.0
        result = mgr.update("living_room", raw_open=False, open_delay=0, close_delay=30)
        assert result is False
        assert mgr.is_paused("living_room") is False


def test_zero_delays_instant():
    """open_delay=0, close_delay=0. State changes are immediate."""
    mgr = WindowManager()
    # Open → immediately paused
    result = mgr.update("living_room", raw_open=True, open_delay=0, close_delay=0)
    assert result is True

    # Close → immediately unpaused
    result = mgr.update("living_room", raw_open=False, open_delay=0, close_delay=0)
    assert result is False


def test_state_machine_open_close_open():
    """Window opens (paused), closes (unpaused), opens again (paused)."""
    mgr = WindowManager()
    # Open
    mgr.update("living_room", raw_open=True, open_delay=0, close_delay=0)
    assert mgr.is_paused("living_room") is True

    # Close
    mgr.update("living_room", raw_open=False, open_delay=0, close_delay=0)
    assert mgr.is_paused("living_room") is False

    # Open again
    mgr.update("living_room", raw_open=True, open_delay=0, close_delay=0)
    assert mgr.is_paused("living_room") is True


def test_remove_room():
    """After remove_room, is_paused returns False."""
    mgr = WindowManager()
    mgr.update("living_room", raw_open=True, open_delay=0, close_delay=0)
    assert mgr.is_paused("living_room") is True

    mgr.remove_room("living_room")
    assert mgr.is_paused("living_room") is False


def test_update_returns_paused_state():
    """update() return value matches is_paused()."""
    mgr = WindowManager()
    result = mgr.update("living_room", raw_open=True, open_delay=0, close_delay=0)
    assert result is mgr.is_paused("living_room")

    result = mgr.update("living_room", raw_open=False, open_delay=0, close_delay=0)
    assert result is mgr.is_paused("living_room")


def test_reopen_during_close_delay():
    """Window re-opens during close delay. Should clear close timer and stay paused."""
    mgr = WindowManager()
    with patch("custom_components.roommind.managers.window_manager.time") as mock_time:
        # Open window, immediate pause
        mock_time.time.return_value = 1000.0
        mgr.update("living_room", raw_open=True, open_delay=0, close_delay=30)
        assert mgr.is_paused("living_room") is True

        # Close window, start close delay
        mock_time.time.return_value = 1010.0
        mgr.update("living_room", raw_open=False, open_delay=0, close_delay=30)
        assert mgr.is_paused("living_room") is True  # still paused during delay

        # Re-open before close delay expires
        mock_time.time.return_value = 1020.0
        result = mgr.update("living_room", raw_open=True, open_delay=0, close_delay=30)
        assert result is True
        assert mgr.is_paused("living_room") is True

        # Much later, still open → still paused (close delay should have been cleared)
        mock_time.time.return_value = 1100.0
        result = mgr.update("living_room", raw_open=True, open_delay=0, close_delay=30)
        assert result is True

        # Now close AGAIN at t=1100. The close delay should restart from NOW,
        # not use the stale _closed_since from the first close at t=1010.
        mock_time.time.return_value = 1100.0
        mgr.update("living_room", raw_open=False, open_delay=0, close_delay=30)
        assert mgr.is_paused("living_room") is True  # still in close delay

        # At t=1120 (only 20s after second close), should still be paused
        mock_time.time.return_value = 1120.0
        result = mgr.update("living_room", raw_open=False, open_delay=0, close_delay=30)
        assert result is True  # would be False if stale timestamp from t=1010 was used

        # At t=1130 (30s after second close), should unpause
        mock_time.time.return_value = 1130.0
        result = mgr.update("living_room", raw_open=False, open_delay=0, close_delay=30)
        assert result is False


def test_multiple_windows_one_open():
    """Two window sensors, one open. Caller passes any_open=True, so paused."""
    mgr = WindowManager()
    # The caller is responsible for computing any_open from multiple sensors.
    # WindowManager receives the aggregated boolean.
    result = mgr.update("living_room", raw_open=True, open_delay=0, close_delay=0)
    assert result is True
    assert mgr.is_paused("living_room") is True


def test_multiple_windows_all_closed():
    """Two window sensors, all closed. Caller passes any_open=False, not paused."""
    mgr = WindowManager()
    # First make it paused
    mgr.update("living_room", raw_open=True, open_delay=0, close_delay=0)
    assert mgr.is_paused("living_room") is True

    # All closed
    result = mgr.update("living_room", raw_open=False, open_delay=0, close_delay=0)
    assert result is False
    assert mgr.is_paused("living_room") is False


def test_window_already_open_at_startup_skips_delay():
    """Window already open on first observation (e.g. after HA restart) skips open_delay."""
    mgr = WindowManager()
    with patch("custom_components.roommind.managers.window_manager.time") as mock_time:
        mock_time.time.return_value = 1000.0
        # First observation with window already open and a large open_delay
        result = mgr.update("living_room", raw_open=True, open_delay=300, close_delay=0)
        # Should be immediately paused despite 300s open_delay
        assert result is True
        assert mgr.is_paused("living_room") is True


def test_window_opens_after_startup_respects_delay():
    """Window closed on first observation, then opens later — normal delay applies."""
    mgr = WindowManager()
    with patch("custom_components.roommind.managers.window_manager.time") as mock_time:
        # First observation: window closed
        mock_time.time.return_value = 1000.0
        mgr.update("living_room", raw_open=False, open_delay=30, close_delay=0)
        assert mgr.is_paused("living_room") is False

        # Window opens later — normal delay should apply
        mock_time.time.return_value = 1100.0
        result = mgr.update("living_room", raw_open=True, open_delay=30, close_delay=0)
        assert result is False  # not yet, delay not elapsed

        mock_time.time.return_value = 1130.0
        result = mgr.update("living_room", raw_open=True, open_delay=30, close_delay=0)
        assert result is True  # now 30s have passed


def test_window_already_open_at_startup_close_delay_still_works():
    """After startup-paused, closing respects close_delay normally."""
    mgr = WindowManager()
    with patch("custom_components.roommind.managers.window_manager.time") as mock_time:
        # Startup: window already open → immediate pause
        mock_time.time.return_value = 1000.0
        mgr.update("living_room", raw_open=True, open_delay=60, close_delay=30)
        assert mgr.is_paused("living_room") is True

        # Window closes
        mock_time.time.return_value = 1010.0
        result = mgr.update("living_room", raw_open=False, open_delay=60, close_delay=30)
        assert result is True  # still paused during close_delay

        mock_time.time.return_value = 1040.0
        result = mgr.update("living_room", raw_open=False, open_delay=60, close_delay=30)
        assert result is False  # 30s close_delay elapsed


def test_remove_room_resets_seen_state():
    """After remove_room, the next observation is treated as first again."""
    mgr = WindowManager()
    with patch("custom_components.roommind.managers.window_manager.time") as mock_time:
        mock_time.time.return_value = 1000.0
        # Initial: window open → immediate pause (first observation)
        mgr.update("living_room", raw_open=True, open_delay=60, close_delay=0)
        assert mgr.is_paused("living_room") is True

        # Remove room
        mgr.remove_room("living_room")
        assert mgr.is_paused("living_room") is False

        # Re-add: window open again → should be treated as first observation
        mock_time.time.return_value = 2000.0
        result = mgr.update("living_room", raw_open=True, open_delay=60, close_delay=0)
        assert result is True  # immediate pause again


SENSOR = "binary_sensor.window"
OTHER = "binary_sensor.door"


def test_resolve_raw_plain_states():
    """Definitive readings map to open/closed; any open sensor wins."""
    mgr = WindowManager()
    assert mgr.resolve_raw("room", {SENSOR: "off", OTHER: "off"}) is False
    assert mgr.resolve_raw("room", {SENSOR: "off", OTHER: "on"}) is True
    assert mgr.is_pending("room") is False


@pytest.mark.parametrize("state", ["unavailable", "unknown", None])
def test_resolve_raw_unavailable_without_history_is_pending(state):
    """Right after startup an unavailable sensor is neither open nor closed."""
    mgr = WindowManager()
    assert mgr.resolve_raw("room", {SENSOR: state}) is None
    assert mgr.is_pending("room") is True


def test_resolve_raw_pending_does_not_consume_first_observation():
    """A pending cycle must leave the room unseen so an open window still skips open_delay."""
    mgr = WindowManager()
    assert mgr.resolve_raw("room", {SENSOR: "unavailable"}) is None
    assert mgr.resolve_raw("room", {SENSOR: "on"}) is True
    assert mgr.is_pending("room") is False
    assert mgr.update("room", raw_open=True, open_delay=60, close_delay=0) is True


def test_resolve_raw_holds_last_known_state():
    """A sensor dropping out keeps its last reading within the grace period."""
    mgr = WindowManager()
    with patch("custom_components.roommind.managers.window_manager.time") as mock_time:
        mock_time.time.return_value = 1000.0
        assert mgr.resolve_raw("room", {SENSOR: "on"}) is True
        mock_time.time.return_value = 1000.0 + MAX_SENSOR_STALENESS - 1
        assert mgr.resolve_raw("room", {SENSOR: "unavailable"}) is True
        assert mgr.resolve_raw("room", {SENSOR: "unknown"}) is True

        mock_time.time.return_value = 5000.0
        assert mgr.resolve_raw("room", {SENSOR: "off"}) is False
        mock_time.time.return_value = 5001.0
        assert mgr.resolve_raw("room", {SENSOR: "unavailable"}) is False


def test_resolve_raw_hold_expires_and_warns_once(caplog):
    """A sensor dead longer than the grace period counts as closed again, with one warning."""
    mgr = WindowManager()
    with patch("custom_components.roommind.managers.window_manager.time") as mock_time:
        mock_time.time.return_value = 1000.0
        assert mgr.resolve_raw("room", {SENSOR: "on"}) is True
        mock_time.time.return_value = 2000.0
        assert mgr.resolve_raw("room", {SENSOR: "unavailable"}) is True  # dropout starts
        mock_time.time.return_value = 2000.0 + MAX_SENSOR_STALENESS
        with caplog.at_level(logging.WARNING):
            assert mgr.resolve_raw("room", {SENSOR: "unavailable"}) is False
            assert mgr.resolve_raw("room", {SENSOR: "unavailable"}) is False
    assert len([r for r in caplog.records if SENSOR in r.getMessage()]) == 1


def test_resolve_raw_never_known_expires_to_closed():
    """A sensor that never reports stops blocking control after the grace period."""
    mgr = WindowManager()
    with patch("custom_components.roommind.managers.window_manager.time") as mock_time:
        mock_time.time.return_value = 1000.0
        assert mgr.resolve_raw("room", {SENSOR: None}) is None
        mock_time.time.return_value = 1000.0 + MAX_SENSOR_STALENESS
        assert mgr.resolve_raw("room", {SENSOR: None}) is False
    assert mgr.is_pending("room") is False


def test_resolve_raw_mixed_sensors():
    """Open wins over pending; pending wins over closed."""
    mgr = WindowManager()
    assert mgr.resolve_raw("room", {SENSOR: "off", OTHER: "unavailable"}) is None
    assert mgr.resolve_raw("room", {SENSOR: "on", OTHER: "unavailable"}) is True
    assert mgr.is_pending("room") is False


def test_resolve_raw_forgets_removed_sensors():
    """A sensor dropped from the config no longer holds or blocks anything."""
    mgr = WindowManager()
    assert mgr.resolve_raw("room", {SENSOR: "on", OTHER: "off"}) is True
    assert mgr.resolve_raw("room", {OTHER: "off"}) is False
    assert mgr.resolve_raw("room", {SENSOR: "unavailable", OTHER: "off"}) is None


def test_remove_room_clears_resolve_state():
    """remove_room drops held readings, pending flag and warning dedupe."""
    mgr = WindowManager()
    with patch("custom_components.roommind.managers.window_manager.time") as mock_time:
        mock_time.time.return_value = 1000.0
        mgr.resolve_raw("room", {SENSOR: "on"})
        mgr.resolve_raw("room", {SENSOR: "unavailable", OTHER: "unavailable"})
        mock_time.time.return_value = 1000.0 + MAX_SENSOR_STALENESS
        mgr.resolve_raw("room", {SENSOR: "unavailable", OTHER: "unavailable"})
    mgr.remove_room("room")
    assert mgr.is_pending("room") is False
    assert mgr.resolve_raw("room", {SENSOR: "unavailable"}) is None  # no held "on" any more


def test_resolve_raw_missing_sensor_counts_as_closed_immediately(caplog):
    """A sensor the caller reports as gone is closed at once, with a single warning (#437)."""
    mgr = WindowManager()
    with caplog.at_level(logging.WARNING):
        assert mgr.resolve_raw("room", {SENSOR: None}, frozenset({SENSOR})) is False
        assert mgr.resolve_raw("room", {SENSOR: None}, frozenset({SENSOR})) is False
    assert mgr.is_pending("room") is False
    assert [r.getMessage() for r in caplog.records].count(
        f"Window sensor {SENSOR} does not exist, treating as closed"
    ) == 1


def test_resolve_raw_missing_sensor_drops_held_reading_but_open_sibling_wins():
    mgr = WindowManager()
    assert mgr.resolve_raw("room", {SENSOR: "on", OTHER: "off"}) is True
    assert mgr.resolve_raw("room", {SENSOR: None, OTHER: "off"}, frozenset({SENSOR})) is False
    assert mgr.resolve_raw("room", {SENSOR: None, OTHER: "on"}, frozenset({SENSOR})) is True
    assert mgr.resolve_raw("room", {SENSOR: None}) is None  # no stale "on" survives once it reappears without state


def test_resolve_raw_missing_sensor_warns_again_after_it_returned(caplog):
    mgr = WindowManager()
    with caplog.at_level(logging.WARNING):
        mgr.resolve_raw("room", {SENSOR: None}, frozenset({SENSOR}))
        mgr.resolve_raw("room", {SENSOR: "off"})
        mgr.resolve_raw("room", {SENSOR: None}, frozenset({SENSOR}))
    assert sum("does not exist" in r.getMessage() for r in caplog.records) == 2
