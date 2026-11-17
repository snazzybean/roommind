"""Compressor group manager for short-cycle protection.

Prevents outdoor compressor units from short-cycling by enforcing
minimum run and off times across all indoor units sharing a compressor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from time import monotonic

from ..const import (
    DEFAULT_COMPRESSOR_MIN_OFF_MINUTES,
    DEFAULT_COMPRESSOR_MIN_RUN_MINUTES,
    DEFAULT_CONFLICT_RESOLUTION,
    UNIFORM_SWITCH_MAX_WAIT_S,
)

_LOGGER = logging.getLogger(__name__)

# hvac modes an indoor unit must not hold while the shared outdoor unit runs the given way (#533):
# heating takes the whole circuit, cooling shares it with dry and fan (Daikin, Pioneer, Panasonic manuals).
UNIFORM_MODE_CONFLICTS: dict[str, frozenset[str]] = {
    "heat": frozenset({"cool", "dry", "fan_only"}),
    "cool": frozenset({"heat"}),
}


@dataclass
class CompressorGroupConfig:
    """Persisted configuration for a compressor group."""

    id: str
    name: str
    members: list[str]
    min_run_seconds: float
    min_off_seconds: float
    master_entity: str = ""
    conflict_resolution: str = "heating_priority"
    action_script: str = ""
    enforce_uniform_mode: bool = False


@dataclass
class CompressorGroupState:
    """In-memory runtime state for a compressor group."""

    active_members: set[str] = field(default_factory=set)
    compressor_on_since: float | None = None
    compressor_off_since: float | None = None
    master_action: str | None = None
    # What the members' rooms ask for, before the master guard and command (#533)
    desired_action: str | None = None
    # The way the outdoor unit last ran or was wanted to: units resting in it may restart any time
    last_mode_action: str | None = None
    # A switch to this action waiting for members in the other mode, since (monotonic)
    switch_wait_action: str | None = None
    switch_wait_since: float | None = None
    # Members the group stopped waiting for, with the mode they kept (a unit RoomMind may not touch)
    switch_ignored: dict[str, str] = field(default_factory=dict)
    # Uniform-mode group whose master can't be read: its applied mode is not trusted meanwhile
    master_unreadable: bool = False
    master_on_since: float | None = None
    master_off_since: float | None = None
    member_started_at: dict[str, float] = field(default_factory=dict)


class CompressorGroupManager:
    """Manage compressor groups and enforce min-run/min-off constraints."""

    def __init__(self) -> None:
        self._groups: dict[str, CompressorGroupConfig] = {}
        self._states: dict[str, CompressorGroupState] = {}
        self._entity_to_group: dict[str, str] = {}

    def load_groups(self, groups: list[dict]) -> None:
        """Load groups from settings. Preserve state for unchanged groups."""
        new_groups: dict[str, CompressorGroupConfig] = {}
        new_entity_map: dict[str, str] = {}
        for g in groups:
            gid = g["id"]
            new_groups[gid] = CompressorGroupConfig(
                id=gid,
                name=g.get("name", ""),
                members=g.get("members", []),
                min_run_seconds=g.get("min_run_minutes", DEFAULT_COMPRESSOR_MIN_RUN_MINUTES) * 60,
                min_off_seconds=g.get("min_off_minutes", DEFAULT_COMPRESSOR_MIN_OFF_MINUTES) * 60,
                master_entity=g.get("master_entity", ""),
                conflict_resolution=g.get("conflict_resolution", DEFAULT_CONFLICT_RESOLUTION),
                action_script=g.get("action_script", ""),
                enforce_uniform_mode=g.get("enforce_uniform_mode", False),
            )
            for eid in g.get("members", []):
                new_entity_map[eid] = gid
            if gid not in self._states:
                self._states[gid] = CompressorGroupState()
            else:
                state = self._states[gid]
                state.active_members &= set(g.get("members", []))
                for stale in set(state.member_started_at) - state.active_members:
                    del state.member_started_at[stale]
        # Remove state for deleted groups
        for old_id in list(self._states):
            if old_id not in new_groups:
                del self._states[old_id]
        self._groups = new_groups
        self._entity_to_group = new_entity_map

    def check_can_activate(self, entity_id: str) -> bool:
        """Can this entity be turned on?

        Returns False if the entity's compressor group is in min-off phase
        (compressor recently turned off and hasn't waited long enough).
        Returns True if entity is not in any group.
        """
        group_id = self._entity_to_group.get(entity_id)
        if group_id is None:
            return True
        state = self._states[group_id]
        if state.active_members:
            return True  # Compressor already running, can join
        if state.compressor_off_since is None:
            return True  # No known off time (e.g. after restart)
        elapsed = monotonic() - state.compressor_off_since
        return elapsed >= self._groups[group_id].min_off_seconds

    def check_must_stay_active(self, entity_id: str) -> bool:
        """Must this entity stay active?

        Returns True if this is the last active member in its group
        AND the compressor hasn't run long enough (min-run not reached).
        Returns False if entity is not in any group.
        """
        group_id = self._entity_to_group.get(entity_id)
        if group_id is None:
            return False
        state = self._states[group_id]
        if entity_id not in state.active_members:
            return False  # Not active, doesn't need to stay active
        if len(state.active_members) > 1:
            return False  # Other members still active, this one can turn off
        if state.compressor_on_since is None:
            return False  # No known on time (e.g. after restart)
        elapsed = monotonic() - state.compressor_on_since
        return elapsed < self._groups[group_id].min_run_seconds

    def min_run_left(self, entity_id: str) -> float:
        """Seconds until the group's compressor may stop (0 when not running or unknown)."""
        group_id = self._entity_to_group.get(entity_id)
        if group_id is None:
            return 0.0
        on_since = self._states[group_id].compressor_on_since
        if on_since is None:
            return 0.0
        return max(0.0, self._groups[group_id].min_run_seconds - (monotonic() - on_since))

    def min_off_left(self, entity_id: str) -> float:
        """Seconds until the group's compressor may start again (0 when running or unknown)."""
        group_id = self._entity_to_group.get(entity_id)
        if group_id is None:
            return 0.0
        state = self._states[group_id]
        if state.active_members or state.compressor_off_since is None:
            return 0.0
        return max(0.0, self._groups[group_id].min_off_seconds - (monotonic() - state.compressor_off_since))

    def update_member(self, entity_id: str, is_active: bool) -> None:
        """Update tracking after commands are sent."""
        group_id = self._entity_to_group.get(entity_id)
        if group_id is None:
            return
        state = self._states[group_id]
        was_running = len(state.active_members) > 0
        if is_active:
            if entity_id not in state.active_members:
                state.member_started_at[entity_id] = monotonic()
            state.active_members.add(entity_id)
        else:
            state.active_members.discard(entity_id)
            state.member_started_at.pop(entity_id, None)
        is_running = len(state.active_members) > 0
        # Track transitions
        if not was_running and is_running:
            state.compressor_on_since = monotonic()
            state.compressor_off_since = None
        elif was_running and not is_running:
            state.compressor_off_since = monotonic()
            state.compressor_on_since = None

    def recently_started(self, entity_id: str, within_seconds: float) -> bool:
        """True if this member was marked active less than *within_seconds* ago.

        Devices report their new state with a delay (polling integrations), so
        an "off" reading right after a start is not a manual switch-off.
        """
        group_id = self._entity_to_group.get(entity_id)
        if group_id is None:
            return False
        started = self._states[group_id].member_started_at.get(entity_id)
        return started is not None and monotonic() - started < within_seconds

    def get_group_for_entity(self, entity_id: str) -> str | None:
        """Return group ID for an entity, or None."""
        return self._entity_to_group.get(entity_id)

    def is_compressor_running(self, group_id: str) -> bool:
        """True if any member in the group is active."""
        state = self._states.get(group_id)
        return bool(state and state.active_members)

    def get_groups(self) -> dict[str, CompressorGroupConfig]:
        """Return all group configs."""
        return self._groups

    def get_state(self, group_id: str) -> CompressorGroupState | None:
        """Return runtime state for a group."""
        return self._states.get(group_id)

    def get_enforced_action(self, entity_id: str) -> str | None:
        """Return the group's resolved action if uniform mode is enforced, else None."""
        gid = self._entity_to_group.get(entity_id)
        if gid is None:
            return None
        group = self._groups.get(gid)
        if group is None or not group.enforce_uniform_mode:
            return None
        state = self._states.get(gid)
        if state is None or state.master_unreadable:
            return None
        return state.master_action

    def is_uniform(self, entity_id: str) -> bool:
        """Whether the entity belongs to a group with "All in the same mode"."""
        gid = self._entity_to_group.get(entity_id)
        group = self._groups.get(gid) if gid is not None else None
        return group is not None and group.enforce_uniform_mode

    def group_mode(self, entity_id: str, *, resting: bool = True) -> str | None:
        """The way a uniform-mode group runs or turns to (heat/cool), None without one (#533)."""
        gid = self._entity_to_group.get(entity_id)
        group = self._groups.get(gid) if gid is not None else None
        state = self._states.get(gid) if gid is not None else None
        if group is None or state is None or not group.enforce_uniform_mode:
            return None
        applied = None if state.master_unreadable else state.master_action
        for action in (state.desired_action, applied, state.last_mode_action if resting else None):
            if action in UNIFORM_MODE_CONFLICTS:
                return action
        return None

    def managed_mode(self, entity_id: str) -> str | None:
        """What a Managed auto room's unit runs in a uniform-mode group (#533).

        The applied mode once the group runs; "off" while it turns to the other way (no direct
        reversal next to an outdoor unit still in the old mode); None while the group is idle,
        so the room keeps its own way (heat_cool or by the unit's reading).
        """
        gid = self._entity_to_group.get(entity_id)
        group = self._groups.get(gid) if gid is not None else None
        state = self._states.get(gid) if gid is not None else None
        if group is None or state is None or not group.enforce_uniform_mode:
            return None
        applied = state.master_action if not state.master_unreadable else None
        applied = applied if applied in UNIFORM_MODE_CONFLICTS else None
        desired = state.desired_action if state.desired_action in UNIFORM_MODE_CONFLICTS else None
        if desired is not None and desired != applied:
            return "off"
        return applied

    def conflicting_modes(self, entity_id: str, *, resting: bool = True) -> frozenset[str]:
        """hvac modes a member must not hold while its uniform-mode group runs or turns the other way (#533).

        The wanted action counts before the applied one: a master that refuses the switch while
        a unit still sits in the old mode, or waits out its min off, must not keep that unit there.
        For units at rest (``resting``) an idle group keeps the way it last ran, since its units
        resting in that mode may start again; a room that wants to run is judged without it.
        """
        return UNIFORM_MODE_CONFLICTS.get(self.group_mode(entity_id, resting=resting) or "", frozenset())

    def switch_wait_over(self, group_id: str, action: str) -> bool:
        """Whether a switch to ``action`` has waited long enough for members in the other mode (#533)."""
        state = self._states.get(group_id)
        group = self._groups.get(group_id)
        if state is None or group is None:
            return True
        if state.switch_wait_action != action or state.switch_wait_since is None:
            state.switch_wait_action = action
            state.switch_wait_since = monotonic()
        return monotonic() - state.switch_wait_since >= UNIFORM_SWITCH_MAX_WAIT_S

    def clear_switch_wait(self, group_id: str) -> None:
        """No member in the other mode any more: a later switch waits afresh."""
        state = self._states.get(group_id)
        if state is not None:
            state.switch_wait_action = None
            state.switch_wait_since = None

    def note_master_readable(self, group_id: str, readable: bool) -> None:
        """A master that can't be read: no stale wish, and a uniform-mode group follows its members.

        The applied action and its min run/off timers stay, so the master guard holds on its return.
        """
        state = self._states.get(group_id)
        group = self._groups.get(group_id)
        if state is None or group is None:
            return
        if not readable:
            state.desired_action = None
        state.master_unreadable = not readable and group.enforce_uniform_mode

    def seed_last_mode(self, group_id: str, action: str) -> None:
        """After a restart: the way the group ran before, read from its devices."""
        state = self._states.get(group_id)
        if state is not None and state.last_mode_action is None and action in UNIFORM_MODE_CONFLICTS:
            state.last_mode_action = action

    def check_master_can_switch(self, group_id: str, new_action: str) -> bool:
        """Check if the master device is allowed to switch to *new_action*.

        Enforces min-run (must stay active long enough) and min-off (must stay
        off long enough) timing constraints, mirroring the member-level guards.
        """
        state = self._states.get(group_id)
        if state is None:
            return True
        group = self._groups.get(group_id)
        if group is None:
            return True
        prev = state.master_action
        if prev == new_action:
            return True  # no transition

        # Min-run: master is active and hasn't run long enough
        if prev is not None and prev != "idle" and new_action == "idle":
            if state.master_on_since is not None:
                elapsed = monotonic() - state.master_on_since
                if elapsed < group.min_run_seconds:
                    return False

        # Min-off: master is idle and hasn't been off long enough
        if (prev is None or prev == "idle") and new_action != "idle":
            if state.master_off_since is not None:
                elapsed = monotonic() - state.master_off_since
                if elapsed < group.min_off_seconds:
                    return False

        return True

    def set_desired_action(self, group_id: str, action: str | None) -> None:
        """Record the action the member rooms ask for this cycle, whether or not the master follows yet."""
        state = self._states.get(group_id)
        if state is not None:
            state.desired_action = action
            if action in UNIFORM_MODE_CONFLICTS:
                state.last_mode_action = action

    def set_master_action(self, group_id: str, action: str) -> None:
        """Record the master entity's resolved action after commands are sent."""
        state = self._states.get(group_id)
        if state is None:
            return
        prev = state.master_action
        state.master_action = action
        if action != prev:
            state.switch_wait_action = None
            state.switch_wait_since = None
        if action in UNIFORM_MODE_CONFLICTS:
            state.last_mode_action = action
        if action != "idle" and (prev is None or prev == "idle"):
            state.master_on_since = monotonic()
            state.master_off_since = None
        elif action == "idle" and prev is not None and prev != "idle":
            state.master_on_since = None
            state.master_off_since = monotonic()


def resolve_master_action(
    room_modes: list[str],
    conflict_resolution: str,
    outdoor_temp: float | None,
    outdoor_heating_max: float,
) -> str:
    """Determine master entity action from aggregate room modes.

    Returns "heat", "cool", or "idle".
    """
    n_heating = sum(1 for m in room_modes if m == "heating")
    n_cooling = sum(1 for m in room_modes if m == "cooling")

    if n_heating == 0 and n_cooling == 0:
        return "idle"
    if n_heating > 0 and n_cooling == 0:
        return "heat"
    if n_cooling > 0 and n_heating == 0:
        return "cool"

    # Conflict: both heating and cooling rooms exist
    if conflict_resolution == "cooling_priority":
        return "cool"
    if conflict_resolution == "majority":
        if n_cooling > n_heating:
            return "cool"
        return "heat"  # heating wins on tie (frost-safe)
    if conflict_resolution == "outdoor_temp":
        if outdoor_temp is None:
            return "heat"  # no sensor → frost-safe fallback
        return "heat" if outdoor_temp <= outdoor_heating_max else "cool"
    # Default: heating_priority
    return "heat"
