"""Device helper utilities for the unified device model.

Pure utility module with NO dependencies on HA or other RoomMind modules.
"""

from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

DEVICE_TYPE_TRV = "trv"
DEVICE_TYPE_AC = "ac"
VALID_DEVICE_TYPES = {DEVICE_TYPE_TRV, DEVICE_TYPE_AC}

DEVICE_ROLE_AUTO = "auto"

VALID_HEATING_SYSTEM_TYPES = {"", "radiator", "underfloor"}

# Heating system type priority: higher = longer residual heat tau
HST_PRIORITY = {"underfloor": 2, "radiator": 1, "": 0}

IDLE_ACTION_OFF = "off"
IDLE_ACTION_FAN_ONLY = "fan_only"
DEFAULT_IDLE_FAN_MODE = "low"
IDLE_ACTION_SETBACK = "setback"
IDLE_ACTION_LOW = "low"
DEFAULT_IDLE_SETBACK_OFFSET = 2.0

SETPOINT_MODE_PROPORTIONAL = "proportional"
SETPOINT_MODE_DIRECT = "direct"

# Active HVAC modes that indicate real device capabilities.
_ACTIVE_HVAC_MODES = {"heat", "cool", "heat_cool", "auto"}


def has_reliable_hvac_modes(state: Any) -> bool:
    """Check if a device's hvac_modes attribute is trustworthy.

    Some integrations report only limited modes like ``["off", "fan_only"]``
    regardless of device state, hiding actual capabilities (see #100).
    Returns *False* when modes are likely incomplete.
    """
    if state is None:
        return False
    modes = set(state.attributes.get("hvac_modes") or [])
    return bool(modes & _ACTIVE_HVAC_MODES)


def legacy_to_devices(
    thermostats: list[str],
    acs: list[str],
    heating_system_type: str = "",
) -> list[dict]:
    """Create devices[] from legacy thermostats/acs lists.

    heating_system_type is transferred to TRV devices (was previously room-level).
    ACs get "" (no heating system profile).
    """
    devices: list[dict] = []
    for eid in thermostats:
        devices.append(
            {
                "entity_id": eid,
                "type": DEVICE_TYPE_TRV,
                "role": DEVICE_ROLE_AUTO,
                "heating_system_type": heating_system_type,
                "idle_action": IDLE_ACTION_OFF,
                "idle_fan_mode": DEFAULT_IDLE_FAN_MODE,
                "setpoint_mode": SETPOINT_MODE_PROPORTIONAL,
            }
        )
    for eid in acs:
        devices.append(
            {
                "entity_id": eid,
                "type": DEVICE_TYPE_AC,
                "role": DEVICE_ROLE_AUTO,
                "heating_system_type": "",
                "idle_action": IDLE_ACTION_OFF,
                "idle_fan_mode": DEFAULT_IDLE_FAN_MODE,
                "setpoint_mode": SETPOINT_MODE_PROPORTIONAL,
            }
        )
    return devices


def devices_to_legacy(devices: list[dict]) -> tuple[list[str], list[str]]:
    """Extract thermostats/acs lists from devices[].

    TRV -> thermostats, AC -> acs.
    Devices with unknown types or missing entity_id are logged and skipped.
    """
    thermostats: list[str] = []
    acs: list[str] = []
    for d in devices:
        eid = d.get("entity_id")
        if not eid:
            _LOGGER.warning("Skipping device with missing entity_id: %s", d)
            continue
        dtype = d.get("type")
        if dtype == DEVICE_TYPE_TRV:
            thermostats.append(eid)
        elif dtype == DEVICE_TYPE_AC:
            acs.append(eid)
        else:
            _LOGGER.warning("Skipping device with unknown type '%s': %s", dtype, eid)
    return thermostats, acs


def ensure_room_has_devices(room: dict) -> dict:
    """One-time migration + read-time safety net.

    - No 'devices' key: generate from legacy + room-level heating_system_type
    - 'devices' present but inconsistent with legacy: prefer legacy (downgrade recovery)
    - 'devices' present and consistent: regenerate legacy from devices
    Mutates and returns room.
    """
    if "devices" not in room:
        room["devices"] = legacy_to_devices(
            room.get("thermostats", []),
            room.get("acs", []),
            room.get("heating_system_type", ""),
        )
    else:
        # Downgrade recovery: if legacy fields were edited while devices was stale,
        # the legacy entity sets won't match devices. Prefer legacy in that case.
        expected_t, expected_a = devices_to_legacy(room["devices"])
        actual_t = room.get("thermostats", [])
        actual_a = room.get("acs", [])
        if set(expected_t) != set(actual_t) or set(expected_a) != set(actual_a):
            _LOGGER.info(
                "Device list inconsistent with legacy fields for room '%s', "
                "re-generating devices from legacy (downgrade recovery)",
                room.get("area_id", "unknown"),
            )
            room["devices"] = legacy_to_devices(
                actual_t,
                actual_a,
                room.get("heating_system_type", ""),
            )
    # Always regenerate legacy from devices (devices is source of truth after migration)
    thermostats, acs = devices_to_legacy(room["devices"])
    room["thermostats"] = thermostats
    room["acs"] = acs
    # Room-level heating_system_type derived from devices for backend compat
    room["heating_system_type"] = get_room_heating_system_type(room["devices"])
    return room


def get_room_heating_system_type(devices: list[dict]) -> str:
    """Return the most conservative heating_system_type for a room.

    With mixed types (e.g., radiator TRV + underfloor TRV), the one with the
    longest residual heat tau wins:
    underfloor (tau=90min) > radiator (tau=10min) > "" (no residual heat).
    Only TRV devices are considered (ACs/HPs have no heating system profile).
    """
    best = ""
    for d in devices:
        if d.get("type") != DEVICE_TYPE_TRV:
            continue
        hst = d.get("heating_system_type", "")
        if HST_PRIORITY.get(hst, 0) > HST_PRIORITY.get(best, 0):
            best = hst
    return best


def get_all_entity_ids(devices: list[dict]) -> list[str]:
    """All entity_ids from devices, TRVs first for deterministic ordering.

    Preserves relative order within each group (TRV, non-TRV).
    This matters for functions like _read_device_temp that take the first
    entity with a valid value.
    """
    trvs = [d["entity_id"] for d in devices if "entity_id" in d and d.get("type") == DEVICE_TYPE_TRV]
    others = [d["entity_id"] for d in devices if "entity_id" in d and d.get("type") != DEVICE_TYPE_TRV]
    return trvs + others


def get_entity_ids_by_type(devices: list[dict], *types: str) -> list[str]:
    """Entity IDs filtered by type(s)."""
    return [d["entity_id"] for d in devices if "entity_id" in d and d.get("type") in types]


def get_trv_eids(devices: list[dict]) -> list[str]:
    """Shortcut for get_entity_ids_by_type(devices, "trv")."""
    return get_entity_ids_by_type(devices, DEVICE_TYPE_TRV)


def get_ac_eids(devices: list[dict]) -> list[str]:
    """Shortcut for get_entity_ids_by_type(devices, "ac")."""
    return get_entity_ids_by_type(devices, DEVICE_TYPE_AC)


def get_device_by_eid(devices: list[dict], entity_id: str) -> dict | None:
    """Find a single device by entity_id."""
    for d in devices:
        if d.get("entity_id") == entity_id:
            return d
    return None


def is_trv_type(device: dict) -> bool:
    """True if device type is TRV."""
    return device.get("type") == DEVICE_TYPE_TRV


def is_ac_type(device: dict) -> bool:
    """True if device type is AC."""
    return device.get("type") == DEVICE_TYPE_AC


def get_idle_action(devices: list[dict], entity_id: str) -> tuple[str, str]:
    """Return (idle_action, idle_fan_mode) for a device."""
    dev = get_device_by_eid(devices, entity_id)
    if dev is None:
        return (IDLE_ACTION_OFF, DEFAULT_IDLE_FAN_MODE)
    return (
        dev.get("idle_action", IDLE_ACTION_OFF),
        dev.get("idle_fan_mode", DEFAULT_IDLE_FAN_MODE),
    )


def get_direct_setpoint_eids(devices: list[dict]) -> set[str]:
    """Return entity IDs of devices with setpoint_mode='direct'."""
    return {d["entity_id"] for d in devices if d.get("entity_id") and d.get("setpoint_mode") == SETPOINT_MODE_DIRECT}


def build_rooms_devices_map(rooms: dict) -> dict[str, list[dict]]:
    """Return {entity_id: devices[]} map across all rooms.

    Used by managers that need to resolve a device's configuration (e.g.
    idle_action) by entity_id without carrying the full rooms dict.
    """
    return {
        d["entity_id"]: room.get("devices", [])
        for room in rooms.values()
        for d in room.get("devices", [])
        if d.get("entity_id")
    }


def migrate_heat_pump_devices(devices: list[dict]) -> bool:
    """Convert any heat_pump devices to ac. Returns True if any were migrated."""
    migrated = False
    for d in devices:
        if d.get("type") == "heat_pump":
            d["type"] = DEVICE_TYPE_AC
            migrated = True
    return migrated


def room_contributes_to_group(
    room_devices: list[dict],
    member_set: set[str],
    active_heat_sources: str | None,
) -> bool:
    """Whether a room's group members are heating-active per orchestration.

    Used by coordinator._collect_member_room_modes to decide whether a
    heating room contributes heating demand to a compressor group's
    master device.

    - ``None``       -> no orchestration data (disabled, missing temp,
                        no TRV+AC, or popped state). Preserve legacy
                        behavior: count the room.
    - ``"none"``     -> orchestration chose nothing (delta_t <= 0) ->
                        False (all devices idled by orchestrator).
    - ``"both"``     -> TRV + AC both active -> True.
    - ``"primary"``  -> only TRVs active -> True iff any group member
                        in this room is a TRV.
    - ``"secondary"``-> only ACs active -> True iff any group member
                        in this room is an AC.

    Unknown string values -> False (fail-safe: master stays idle).
    """
    if active_heat_sources is None:
        return True
    if active_heat_sources == "none":
        return False
    if active_heat_sources == "both":
        return True
    if active_heat_sources == "primary":
        required_type = DEVICE_TYPE_TRV
    elif active_heat_sources == "secondary":
        required_type = DEVICE_TYPE_AC
    else:
        return False  # defensive: unknown orchestration state
    for dev in room_devices:
        eid = dev.get("entity_id", "")
        if eid and eid in member_set and dev.get("type") == required_type:
            return True
    return False
