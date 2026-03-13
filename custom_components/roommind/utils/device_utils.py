"""Device helper utilities for the unified device model.

Pure utility module with NO dependencies on HA or other RoomMind modules.
"""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)

DEVICE_TYPE_TRV = "trv"
DEVICE_TYPE_AC = "ac"
DEVICE_TYPE_HEAT_PUMP = "heat_pump"
VALID_DEVICE_TYPES = {DEVICE_TYPE_TRV, DEVICE_TYPE_AC, DEVICE_TYPE_HEAT_PUMP}

DEVICE_ROLE_PRIMARY = "primary"
DEVICE_ROLE_SECONDARY = "secondary"
DEVICE_ROLE_AUTO = "auto"
VALID_DEVICE_ROLES = {DEVICE_ROLE_PRIMARY, DEVICE_ROLE_SECONDARY, DEVICE_ROLE_AUTO}

VALID_HEATING_SYSTEM_TYPES = {"", "radiator", "underfloor"}

# Heating system type priority: higher = longer residual heat tau
HST_PRIORITY = {"underfloor": 2, "radiator": 1, "": 0}


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
            }
        )
    for eid in acs:
        devices.append(
            {
                "entity_id": eid,
                "type": DEVICE_TYPE_AC,
                "role": DEVICE_ROLE_AUTO,
                "heating_system_type": "",
            }
        )
    return devices


def devices_to_legacy(devices: list[dict]) -> tuple[list[str], list[str]]:
    """Extract thermostats/acs lists from devices[].

    TRV -> thermostats, AC/heat_pump -> acs.
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
        elif dtype in (DEVICE_TYPE_AC, DEVICE_TYPE_HEAT_PUMP):
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
    """Shortcut for get_entity_ids_by_type(devices, "ac", "heat_pump")."""
    return get_entity_ids_by_type(devices, DEVICE_TYPE_AC, DEVICE_TYPE_HEAT_PUMP)


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
    """True if device type is AC or heat pump."""
    return device.get("type") in (DEVICE_TYPE_AC, DEVICE_TYPE_HEAT_PUMP)
