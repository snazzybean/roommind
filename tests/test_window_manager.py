"""Tests for WindowManager."""

from __future__ import annotations

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
