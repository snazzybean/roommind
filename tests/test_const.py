"""Tests for const.py helper functions."""

from __future__ import annotations

import time

from custom_components.roommind.const import is_override_active


class TestIsOverrideActive:
    """Unit tests for is_override_active."""

    def test_no_override_temp(self):
        """No override_temp → inactive."""
        assert is_override_active({}) is False

    def test_override_temp_none(self):
        """override_temp=None → inactive."""
        assert is_override_active({"override_temp": None}) is False

    def test_permanent_override(self):
        """override_temp set, override_until=None → permanent, active."""
        assert is_override_active({"override_temp": 20.0, "override_until": None}) is True

    def test_future_override(self):
        """override_until in the future → active."""
        future = time.time() + 3600
        assert is_override_active({"override_temp": 20.0, "override_until": future}) is True

    def test_expired_override(self):
        """override_until in the past → inactive."""
        past = time.time() - 3600
        assert is_override_active({"override_temp": 20.0, "override_until": past}) is False
