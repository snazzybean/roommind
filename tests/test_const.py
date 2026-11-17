"""Tests for const.py helper functions."""

from __future__ import annotations

import json
import pathlib
import time

from custom_components.roommind.const import (
    VERSION,
    build_override_live,
    is_override_active,
    is_override_suppressed,
)


class TestVersionLockstep:
    """const.VERSION and manifest.json must always agree.

    The boot check in _async_check_version_mismatch compares the in-memory
    const.VERSION against the on-disk manifest to offer a "restart required"
    repair after a hot file deploy. A release that bumps only one of the two
    makes the pair disagree *forever* - the repair is recreated every boot and
    no restart can ever converge it (both values are baked into the deployed
    files). That loop shipped on beta.18 through beta.21; this test is the
    fence.
    """

    def test_version_matches_manifest(self):
        manifest_path = pathlib.Path(__file__).parent.parent / "custom_components" / "roommind" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["version"] == VERSION, (
            f"bump custom_components/roommind/const.py VERSION ({VERSION}) together "
            f"with manifest.json version ({manifest['version']})"
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
