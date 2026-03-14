"""Tests for CompressorGroupManager."""

import time

from custom_components.roommind.managers.compressor_group_manager import (
    CompressorGroupManager,
)


def _make_group(gid="g1", members=None, min_run=15, min_off=5):
    return {
        "id": gid,
        "name": f"Group {gid}",
        "members": members or ["climate.ac1"],
        "min_run_minutes": min_run,
        "min_off_minutes": min_off,
    }


class TestCompressorGroupManager:
    def test_no_groups_no_constraints(self):
        mgr = CompressorGroupManager()
        mgr.load_groups([])
        assert mgr.check_can_activate("climate.ac1") is True
        assert mgr.check_must_stay_active("climate.ac1") is False

    def test_entity_not_in_group(self):
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group(members=["climate.ac1"])])
        assert mgr.check_can_activate("climate.other") is True
        assert mgr.check_must_stay_active("climate.other") is False

    def test_get_group_for_entity(self):
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group(gid="g1", members=["climate.ac1"])])
        assert mgr.get_group_for_entity("climate.ac1") == "g1"
        assert mgr.get_group_for_entity("climate.other") is None

    def test_min_off_blocks_activation(self):
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group(min_off=5)])
        # Simulate: compressor was running, just turned off
        mgr.update_member("climate.ac1", True)
        mgr.update_member("climate.ac1", False)
        # Now compressor_off_since is set to now
        assert mgr.check_can_activate("climate.ac1") is False

    def test_min_off_expired_allows_activation(self):
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group(min_off=5)])
        mgr.update_member("climate.ac1", True)
        mgr.update_member("climate.ac1", False)
        # Fake time: 6 minutes ago
        mgr._states["g1"].compressor_off_since = time.monotonic() - 360
        assert mgr.check_can_activate("climate.ac1") is True

    def test_min_off_ignored_if_compressor_running(self):
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group(members=["climate.ac1", "climate.ac2"])])
        mgr.update_member("climate.ac1", True)
        # ac2 wants to activate while ac1 is running
        assert mgr.check_can_activate("climate.ac2") is True

    def test_min_run_blocks_last_member_off(self):
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group(min_run=15)])
        mgr.update_member("climate.ac1", True)
        # compressor_on_since is now, min_run is 15 min
        assert mgr.check_must_stay_active("climate.ac1") is True

    def test_min_run_allows_off_if_others_active(self):
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group(members=["climate.ac1", "climate.ac2"], min_run=15)])
        mgr.update_member("climate.ac1", True)
        mgr.update_member("climate.ac2", True)
        # ac1 is not the last member
        assert mgr.check_must_stay_active("climate.ac1") is False

    def test_min_run_expired_allows_off(self):
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group(min_run=15)])
        mgr.update_member("climate.ac1", True)
        # Fake: been running for 20 minutes
        mgr._states["g1"].compressor_on_since = time.monotonic() - 1200
        assert mgr.check_must_stay_active("climate.ac1") is False

    def test_not_active_member_does_not_need_to_stay(self):
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group(members=["climate.ac1", "climate.ac2"], min_run=15)])
        mgr.update_member("climate.ac1", True)
        # ac2 is not active
        assert mgr.check_must_stay_active("climate.ac2") is False

    def test_state_transition_off_to_on(self):
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group()])
        mgr.update_member("climate.ac1", True)
        state = mgr._states["g1"]
        assert state.compressor_on_since is not None
        assert state.compressor_off_since is None
        assert "climate.ac1" in state.active_members

    def test_state_transition_on_to_off(self):
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group()])
        mgr.update_member("climate.ac1", True)
        mgr.update_member("climate.ac1", False)
        state = mgr._states["g1"]
        assert state.compressor_off_since is not None
        assert state.compressor_on_since is None
        assert "climate.ac1" not in state.active_members

    def test_partial_off_does_not_trigger_compressor_off(self):
        """If one member turns off but another stays on, compressor stays on."""
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group(members=["climate.ac1", "climate.ac2"])])
        mgr.update_member("climate.ac1", True)
        mgr.update_member("climate.ac2", True)
        mgr.update_member("climate.ac1", False)
        state = mgr._states["g1"]
        assert state.compressor_on_since is not None  # Still running
        assert state.compressor_off_since is None
        assert mgr.is_compressor_running("g1") is True

    def test_multiple_groups_independent(self):
        mgr = CompressorGroupManager()
        mgr.load_groups(
            [
                _make_group(gid="g1", members=["climate.ac1"], min_off=5),
                _make_group(gid="g2", members=["climate.ac2"], min_off=5),
            ]
        )
        # g1 compressor just turned off
        mgr.update_member("climate.ac1", True)
        mgr.update_member("climate.ac1", False)
        # g2 is unaffected
        assert mgr.check_can_activate("climate.ac2") is True
        assert mgr.check_can_activate("climate.ac1") is False

    def test_load_groups_preserves_state(self):
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group(gid="g1")])
        mgr.update_member("climate.ac1", True)
        on_since = mgr._states["g1"].compressor_on_since
        # Reload same group
        mgr.load_groups([_make_group(gid="g1")])
        assert mgr._states["g1"].compressor_on_since == on_since

    def test_load_groups_removes_deleted(self):
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group(gid="g1")])
        mgr.update_member("climate.ac1", True)
        assert "g1" in mgr._states
        # Remove g1
        mgr.load_groups([])
        assert "g1" not in mgr._states

    def test_after_restart_no_constraints(self):
        """Fresh state (no timestamps) means no constraints."""
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group()])
        # No update_member calls -> fresh state
        assert mgr.check_can_activate("climate.ac1") is True
        assert mgr.check_must_stay_active("climate.ac1") is False

    def test_is_compressor_running(self):
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group(gid="g1")])
        assert mgr.is_compressor_running("g1") is False
        mgr.update_member("climate.ac1", True)
        assert mgr.is_compressor_running("g1") is True
        mgr.update_member("climate.ac1", False)
        assert mgr.is_compressor_running("g1") is False

    def test_update_member_unknown_entity_is_noop(self):
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group()])
        mgr.update_member("climate.unknown", True)  # Should not crash

    def test_settings_change_updates_min_run(self):
        """Changed min_run takes effect immediately."""
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group(min_run=15)])
        mgr.update_member("climate.ac1", True)
        # Running for 10 min (< 15 min original)
        mgr._states["g1"].compressor_on_since = time.monotonic() - 600
        assert mgr.check_must_stay_active("climate.ac1") is True
        # Change min_run to 5 min
        mgr.load_groups([_make_group(min_run=5)])
        # Now 10 min > 5 min -> can turn off
        assert mgr.check_must_stay_active("climate.ac1") is False
