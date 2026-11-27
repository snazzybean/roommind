"""Tests for const.py helper functions."""

from __future__ import annotations

import time

import pytest

from custom_components.roommind.const import (
    build_override_live,
    is_override_active,
    is_override_suppressed,
    presence_override_mode,
)


class TestIsOverrideActive:
    """Unit tests for is_override_active."""

    def test_no_override_fields(self):
        """No override fields → inactive."""
        assert is_override_active({}) is False

    def test_both_targets_none(self):
        """override_heat=None and override_cool=None → inactive."""
        assert is_override_active({"override_heat": None, "override_cool": None}) is False

    def test_heat_only_active(self):
        """Only override_heat set → active."""
        assert is_override_active({"override_heat": 21.0, "override_cool": None}) is True

    def test_cool_only_active(self):
        """Only override_cool set → active."""
        assert is_override_active({"override_heat": None, "override_cool": 24.0}) is True

    def test_permanent_override(self):
        """Targets set, override_until=None → permanent, active."""
        assert is_override_active({"override_heat": 20.0, "override_cool": 24.0, "override_until": None}) is True

    def test_future_override(self):
        """override_until in the future → active."""
        future = time.time() + 3600
        assert is_override_active({"override_heat": 20.0, "override_cool": 24.0, "override_until": future}) is True

    def test_expired_override(self):
        """override_until in the past → inactive."""
        past = time.time() - 3600
        assert is_override_active({"override_heat": 20.0, "override_until": past}) is False


class TestIsOverrideSuppressed:
    """Unit tests for is_override_suppressed (#306)."""

    def test_presence_home_never_suppresses(self):
        assert is_override_suppressed({}, {"presence_clears_override": True}, False) is False

    def test_setting_disabled_never_suppresses(self):
        assert is_override_suppressed({}, {"presence_clears_override": False}, True) is False

    def test_setting_missing_defaults_off(self):
        assert is_override_suppressed({}, {}, True) is False

    def test_ignore_presence_room_never_suppressed(self):
        room = {"ignore_presence": True}
        assert is_override_suppressed(room, {"presence_clears_override": True}, True) is False

    def test_suppressed_when_all_conditions_met(self):
        assert is_override_suppressed({}, {"presence_clears_override": True}, True) is True


class TestPresenceOverrideMode:
    """keep / pause / end from presence_clears_override and presence_ends_override."""

    @pytest.mark.parametrize(
        ("settings", "mode"),
        [
            ({}, "keep"),
            ({"presence_clears_override": True}, "pause"),
            ({"presence_ends_override": True}, "end"),
            ({"presence_clears_override": True, "presence_ends_override": True}, "end"),
        ],
    )
    def test_mode(self, settings, mode):
        assert presence_override_mode(settings) == mode

    def test_end_does_not_pause(self):
        settings = {"presence_clears_override": True, "presence_ends_override": True}
        assert is_override_suppressed({}, settings, True) is False


class TestBuildOverrideLive:
    """Unit tests for build_override_live (#306)."""

    def test_inactive_override(self):
        result = build_override_live({})
        assert result["override_active"] is False
        assert result["override_suppressed"] is False

    def test_active_override_not_suppressed(self):
        room = {"override_heat": 22.0, "override_cool": 25.0, "override_until": None, "override_type": "boost"}
        result = build_override_live(room, suppressed=False)
        assert result["override_active"] is True
        assert result["override_type"] == "boost"
        assert result["override_suppressed"] is False

    def test_active_override_suppressed(self):
        room = {"override_heat": 22.0, "override_cool": 25.0, "override_until": None, "override_type": "boost"}
        result = build_override_live(room, suppressed=True)
        assert result["override_active"] is True
        assert result["override_suppressed"] is True

    def test_inactive_override_never_suppressed(self):
        """Suppressed flag is meaningless when override is not active."""
        result = build_override_live({}, suppressed=True)
        assert result["override_active"] is False
        assert result["override_suppressed"] is False

    def test_exposes_split_targets(self):
        room = {"override_type": "custom", "override_heat": 21.0, "override_cool": 24.0, "override_until": None}
        live = build_override_live(room)
        assert live["override_active"] is True
        assert live["override_heat"] == 21.0
        assert live["override_cool"] == 24.0
        assert "override_temp" not in live

    def test_inactive_nulls_targets(self):
        live = build_override_live({"override_heat": None, "override_cool": None})
        assert live["override_active"] is False
        assert live["override_heat"] is None
        assert live["override_cool"] is None
