"""Compressor group manager for short-cycle protection.

Prevents outdoor compressor units from short-cycling by enforcing
minimum run and off times across all indoor units sharing a compressor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from time import monotonic

from ..const import DEFAULT_COMPRESSOR_MIN_OFF_MINUTES, DEFAULT_COMPRESSOR_MIN_RUN_MINUTES

_LOGGER = logging.getLogger(__name__)


@dataclass
class CompressorGroupConfig:
    """Persisted configuration for a compressor group."""

    id: str
    name: str
    members: list[str]
    min_run_seconds: float
    min_off_seconds: float


@dataclass
class CompressorGroupState:
    """In-memory runtime state for a compressor group."""

    active_members: set[str] = field(default_factory=set)
    compressor_on_since: float | None = None
    compressor_off_since: float | None = None


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
            )
            for eid in g.get("members", []):
                new_entity_map[eid] = gid
            if gid not in self._states:
                self._states[gid] = CompressorGroupState()
            else:
                self._states[gid].active_members &= set(g.get("members", []))
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

    def update_member(self, entity_id: str, is_active: bool) -> None:
        """Update tracking after commands are sent."""
        group_id = self._entity_to_group.get(entity_id)
        if group_id is None:
            return
        state = self._states[group_id]
        was_running = len(state.active_members) > 0
        if is_active:
            state.active_members.add(entity_id)
        else:
            state.active_members.discard(entity_id)
        is_running = len(state.active_members) > 0
        # Track transitions
        if not was_running and is_running:
            state.compressor_on_since = monotonic()
            state.compressor_off_since = None
        elif was_running and not is_running:
            state.compressor_off_since = monotonic()
            state.compressor_on_since = None

    def get_group_for_entity(self, entity_id: str) -> str | None:
        """Return group ID for an entity, or None."""
        return self._entity_to_group.get(entity_id)

    def is_compressor_running(self, group_id: str) -> bool:
        """True if any member in the group is active."""
        state = self._states.get(group_id)
        return bool(state and state.active_members)
