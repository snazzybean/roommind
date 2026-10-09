"""Tests for CompressorGroupManager."""

import time

from custom_components.roommind.managers.compressor_group_manager import (
    CompressorGroupManager,
    resolve_master_action,
)


def _make_group(gid="g1", members=None, min_run=15, min_off=5, enforce_uniform_mode=False):
    g = {
        "id": gid,
        "name": f"Group {gid}",
        "members": members or ["climate.ac1"],
        "min_run_minutes": min_run,
        "min_off_minutes": min_off,
    }
    if enforce_uniform_mode:
        g["enforce_uniform_mode"] = True
    return g


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


class TestRecentlyStarted:
    def test_true_right_after_start_false_later(self):
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group(members=["climate.ac1"])])
        mgr.update_member("climate.ac1", True)
        assert mgr.recently_started("climate.ac1", 120) is True
        assert mgr.recently_started("climate.ac1", 0) is False

    def test_repeated_update_does_not_restart_the_window(self):
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group(members=["climate.ac1"])])
        mgr.update_member("climate.ac1", True)
        started = mgr.get_state("g1").member_started_at["climate.ac1"]
        mgr.update_member("climate.ac1", True)
        assert mgr.get_state("g1").member_started_at["climate.ac1"] == started

    def test_cleared_on_stop_and_for_unknown_entities(self):
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group(members=["climate.ac1"])])
        mgr.update_member("climate.ac1", True)
        mgr.update_member("climate.ac1", False)
        assert mgr.recently_started("climate.ac1", 120) is False
        assert mgr.recently_started("climate.other", 120) is False

    def test_reload_drops_start_time_of_removed_member(self):
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group(members=["climate.ac1", "climate.ac2"])])
        mgr.update_member("climate.ac2", True)
        mgr.load_groups([_make_group(members=["climate.ac1"])])
        assert "climate.ac2" not in mgr.get_state("g1").member_started_at


class TestResolveMasterAction:
    def test_all_idle(self):
        assert resolve_master_action(["idle", "idle"], "heating_priority", None, 22) == "idle"

    def test_empty_modes(self):
        assert resolve_master_action([], "heating_priority", None, 22) == "idle"

    def test_only_heating(self):
        assert resolve_master_action(["heating", "heating"], "heating_priority", None, 22) == "heat"

    def test_only_cooling(self):
        assert resolve_master_action(["cooling", "idle"], "heating_priority", None, 22) == "cool"

    def test_mixed_idle_heating(self):
        assert resolve_master_action(["idle", "heating", "idle"], "heating_priority", None, 22) == "heat"

    def test_conflict_heating_priority(self):
        assert resolve_master_action(["heating", "cooling"], "heating_priority", None, 22) == "heat"

    def test_conflict_cooling_priority(self):
        assert resolve_master_action(["heating", "cooling"], "cooling_priority", None, 22) == "cool"

    def test_conflict_majority_heating_wins(self):
        assert resolve_master_action(["heating", "heating", "cooling"], "majority", None, 22) == "heat"

    def test_conflict_majority_cooling_wins(self):
        assert resolve_master_action(["heating", "cooling", "cooling"], "majority", None, 22) == "cool"

    def test_conflict_majority_tie(self):
        assert resolve_master_action(["heating", "cooling"], "majority", None, 22) == "heat"

    def test_conflict_outdoor_cold(self):
        assert resolve_master_action(["heating", "cooling"], "outdoor_temp", 10.0, 22) == "heat"

    def test_conflict_outdoor_warm(self):
        assert resolve_master_action(["heating", "cooling"], "outdoor_temp", 25.0, 22) == "cool"

    def test_conflict_outdoor_at_threshold(self):
        assert resolve_master_action(["heating", "cooling"], "outdoor_temp", 22.0, 22) == "heat"

    def test_conflict_outdoor_none(self):
        assert resolve_master_action(["heating", "cooling"], "outdoor_temp", None, 22) == "heat"


class TestMasterDeviceState:
    def test_load_groups_without_master_fields(self):
        mgr = CompressorGroupManager()
        mgr.load_groups([{"id": "g1", "name": "G1", "members": ["climate.a"]}])
        cfg = mgr.get_groups()["g1"]
        assert cfg.master_entity == ""
        assert cfg.conflict_resolution == "heating_priority"
        assert cfg.action_script == ""

    def test_load_groups_with_master_fields(self):
        mgr = CompressorGroupManager()
        mgr.load_groups(
            [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.a"],
                    "master_entity": "climate.boiler",
                    "conflict_resolution": "majority",
                    "action_script": "script.boiler_control",
                }
            ]
        )
        cfg = mgr.get_groups()["g1"]
        assert cfg.master_entity == "climate.boiler"
        assert cfg.conflict_resolution == "majority"
        assert cfg.action_script == "script.boiler_control"

    def test_state_preserves_master_action_on_reload(self):
        mgr = CompressorGroupManager()
        mgr.load_groups([{"id": "g1", "name": "G1", "members": ["climate.a"]}])
        mgr.set_master_action("g1", "heat")
        assert mgr.get_state("g1").master_action == "heat"
        # Reload same group
        mgr.load_groups([{"id": "g1", "name": "G1", "members": ["climate.a"]}])
        assert mgr.get_state("g1").master_action == "heat"

    def test_set_master_action_idle_to_heat(self):
        mgr = CompressorGroupManager()
        mgr.load_groups([{"id": "g1", "name": "G1", "members": ["climate.a"]}])
        mgr.set_master_action("g1", "idle")
        assert mgr.get_state("g1").master_on_since is None
        mgr.set_master_action("g1", "heat")
        assert mgr.get_state("g1").master_on_since is not None

    def test_set_master_action_heat_to_idle(self):
        mgr = CompressorGroupManager()
        mgr.load_groups([{"id": "g1", "name": "G1", "members": ["climate.a"]}])
        mgr.set_master_action("g1", "heat")
        assert mgr.get_state("g1").master_on_since is not None
        mgr.set_master_action("g1", "idle")
        assert mgr.get_state("g1").master_on_since is None

    def test_set_master_action_unknown_group(self):
        mgr = CompressorGroupManager()
        mgr.set_master_action("nonexistent", "heat")  # Should not raise

    def test_get_groups_returns_all(self):
        mgr = CompressorGroupManager()
        mgr.load_groups(
            [
                {"id": "g1", "name": "G1", "members": ["climate.a"]},
                {"id": "g2", "name": "G2", "members": ["climate.b"]},
            ]
        )
        groups = mgr.get_groups()
        assert "g1" in groups
        assert "g2" in groups

    def test_get_state_returns_none_for_unknown(self):
        mgr = CompressorGroupManager()
        assert mgr.get_state("nonexistent") is None

    def test_check_master_can_switch_min_run_blocks_idle(self):
        """Master cannot switch to idle during min-run period."""
        mgr = CompressorGroupManager()
        mgr.load_groups([{"id": "g1", "name": "G1", "members": ["climate.a"], "min_run_minutes": 15}])
        mgr.set_master_action("g1", "heat")
        # Just started → cannot switch to idle
        assert mgr.check_master_can_switch("g1", "idle") is False
        # Same action is always allowed
        assert mgr.check_master_can_switch("g1", "heat") is True

    def test_check_master_can_switch_min_off_blocks_restart(self):
        """Master cannot restart during min-off period."""
        mgr = CompressorGroupManager()
        mgr.load_groups([{"id": "g1", "name": "G1", "members": ["climate.a"], "min_off_minutes": 5}])
        mgr.set_master_action("g1", "heat")
        mgr.set_master_action("g1", "idle")
        # Just turned off → cannot restart
        assert mgr.check_master_can_switch("g1", "heat") is False
        # Staying idle is allowed
        assert mgr.check_master_can_switch("g1", "idle") is True

    def test_check_master_can_switch_unknown_group(self):
        """Unknown group always returns True."""
        mgr = CompressorGroupManager()
        assert mgr.check_master_can_switch("nonexistent", "heat") is True

    def test_set_master_action_tracks_off_since(self):
        """Switching to idle should set master_off_since."""
        mgr = CompressorGroupManager()
        mgr.load_groups([{"id": "g1", "name": "G1", "members": ["climate.a"]}])
        mgr.set_master_action("g1", "heat")
        assert mgr.get_state("g1").master_off_since is None
        mgr.set_master_action("g1", "idle")
        assert mgr.get_state("g1").master_off_since is not None
        assert mgr.get_state("g1").master_on_since is None


class TestEnforceUniformMode:
    def test_load_groups_reads_enforce_uniform_mode(self):
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group(enforce_uniform_mode=True)])
        cfg = mgr.get_groups()["g1"]
        assert cfg.enforce_uniform_mode is True

    def test_load_groups_default_enforce_false(self):
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group()])
        cfg = mgr.get_groups()["g1"]
        assert cfg.enforce_uniform_mode is False

    def test_get_enforced_action_disabled(self):
        """enforce_uniform_mode=False → returns None."""
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group()])
        mgr.set_master_action("g1", "heat")
        assert mgr.get_enforced_action("climate.ac1") is None

    def test_get_enforced_action_enabled(self):
        """enforce_uniform_mode=True → returns stored action."""
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group(enforce_uniform_mode=True)])
        mgr.set_master_action("g1", "heat")
        assert mgr.get_enforced_action("climate.ac1") == "heat"

    def test_get_enforced_action_first_cycle(self):
        """enforce_uniform_mode=True, no action set yet → returns None."""
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group(enforce_uniform_mode=True)])
        assert mgr.get_enforced_action("climate.ac1") is None

    def test_get_enforced_action_entity_not_in_group(self):
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group(enforce_uniform_mode=True)])
        assert mgr.get_enforced_action("climate.unknown") is None

    def test_get_enforced_action_updates_with_master_action(self):
        """Action follows set_master_action transitions."""
        mgr = CompressorGroupManager()
        mgr.load_groups([_make_group(enforce_uniform_mode=True)])
        mgr.set_master_action("g1", "heat")
        assert mgr.get_enforced_action("climate.ac1") == "heat"
        mgr.set_master_action("g1", "cool")
        assert mgr.get_enforced_action("climate.ac1") == "cool"
        mgr.set_master_action("g1", "idle")
        assert mgr.get_enforced_action("climate.ac1") == "idle"
