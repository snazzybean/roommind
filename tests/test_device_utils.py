"""Tests for custom_components.roommind.utils.device_utils."""

from __future__ import annotations

from custom_components.roommind.utils.device_utils import (
    VALID_DEVICE_TYPES,
    VALID_HEATING_SYSTEM_TYPES,
    devices_to_legacy,
    ensure_room_has_devices,
    get_ac_eids,
    get_all_entity_ids,
    get_device_by_eid,
    get_entity_ids_by_type,
    get_idle_action,
    get_room_heating_system_type,
    get_trv_eids,
    is_ac_type,
    is_trv_type,
    legacy_to_devices,
    migrate_heat_pump_devices,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_valid_device_types():
    assert VALID_DEVICE_TYPES == {"trv", "ac"}


def test_device_role_auto_constant():
    from custom_components.roommind.utils.device_utils import DEVICE_ROLE_AUTO

    assert DEVICE_ROLE_AUTO == "auto"


def test_valid_heating_system_types():
    assert VALID_HEATING_SYSTEM_TYPES == {"", "radiator", "underfloor"}


# ---------------------------------------------------------------------------
# legacy_to_devices
# ---------------------------------------------------------------------------


def test_legacy_to_devices_basic():
    devices = legacy_to_devices(
        ["climate.trv1", "climate.trv2"],
        ["climate.ac1"],
    )
    assert len(devices) == 3
    assert devices[0] == {
        "entity_id": "climate.trv1",
        "type": "trv",
        "role": "auto",
        "heating_system_type": "",
        "idle_action": "off",
        "idle_fan_mode": "low",
    }
    assert devices[2]["type"] == "ac"
    assert devices[2]["heating_system_type"] == ""


def test_legacy_to_devices_heating_system_type_transferred_to_trvs():
    devices = legacy_to_devices(
        ["climate.trv1"],
        ["climate.ac1"],
        heating_system_type="underfloor",
    )
    assert devices[0]["heating_system_type"] == "underfloor"
    assert devices[1]["heating_system_type"] == ""


def test_legacy_to_devices_empty_lists():
    assert legacy_to_devices([], []) == []


# ---------------------------------------------------------------------------
# devices_to_legacy
# ---------------------------------------------------------------------------


def test_devices_to_legacy_basic():
    devices = [
        {"entity_id": "climate.trv1", "type": "trv"},
        {"entity_id": "climate.ac1", "type": "ac"},
    ]
    thermostats, acs = devices_to_legacy(devices)
    assert thermostats == ["climate.trv1"]
    assert acs == ["climate.ac1"]


def test_devices_to_legacy_unknown_type_skipped():
    """Unknown device types are logged and skipped, not silently added to acs."""
    devices = [{"entity_id": "climate.mystery", "type": "unknown_thing"}]
    thermostats, acs = devices_to_legacy(devices)
    assert thermostats == []
    assert acs == []


def test_devices_to_legacy_missing_entity_id_skipped():
    """Devices without entity_id are logged and skipped."""
    devices = [{"type": "trv"}, {"entity_id": "climate.ok", "type": "ac"}]
    thermostats, acs = devices_to_legacy(devices)
    assert thermostats == []
    assert acs == ["climate.ok"]


def test_round_trip_legacy_devices_legacy():
    original_thermostats = ["climate.trv1", "climate.trv2"]
    original_acs = ["climate.ac1"]
    devices = legacy_to_devices(original_thermostats, original_acs, "radiator")
    thermostats, acs = devices_to_legacy(devices)
    assert thermostats == original_thermostats
    assert acs == original_acs


# ---------------------------------------------------------------------------
# ensure_room_has_devices
# ---------------------------------------------------------------------------


def test_ensure_room_has_devices_migration_from_legacy():
    room = {
        "thermostats": ["climate.trv1"],
        "acs": ["climate.ac1"],
        "heating_system_type": "radiator",
    }
    result = ensure_room_has_devices(room)
    assert result is room  # mutates in place
    assert len(room["devices"]) == 2
    assert room["devices"][0]["type"] == "trv"
    assert room["devices"][0]["heating_system_type"] == "radiator"
    assert room["devices"][1]["type"] == "ac"
    assert room["thermostats"] == ["climate.trv1"]
    assert room["acs"] == ["climate.ac1"]
    assert room["heating_system_type"] == "radiator"


def test_ensure_room_has_devices_idempotent():
    room = {
        "thermostats": ["climate.trv1"],
        "acs": [],
        "heating_system_type": "underfloor",
    }
    ensure_room_has_devices(room)
    devices_snapshot = list(room["devices"])
    ensure_room_has_devices(room)
    assert room["devices"] == devices_snapshot


def test_ensure_room_has_devices_consistent_devices_regenerates_legacy():
    """When devices match legacy, devices remain source of truth."""
    room = {
        "devices": [
            {"entity_id": "climate.trv1", "type": "trv", "role": "auto", "heating_system_type": "radiator"},
            {"entity_id": "climate.ac1", "type": "ac", "role": "auto", "heating_system_type": ""},
        ],
        "thermostats": ["climate.trv1"],
        "acs": ["climate.ac1"],
        "heating_system_type": "stale",
    }
    ensure_room_has_devices(room)
    assert room["thermostats"] == ["climate.trv1"]
    assert room["acs"] == ["climate.ac1"]
    assert room["heating_system_type"] == "radiator"


def test_ensure_room_has_devices_downgrade_recovery():
    """When legacy fields were edited during downgrade, prefer legacy over stale devices."""
    room = {
        "devices": [
            {"entity_id": "climate.old_trv", "type": "trv", "role": "auto", "heating_system_type": ""},
        ],
        "thermostats": ["climate.new_trv"],
        "acs": ["climate.new_ac"],
        "heating_system_type": "radiator",
    }
    ensure_room_has_devices(room)
    # Legacy was edited during downgrade -> devices re-generated from legacy
    assert len(room["devices"]) == 2
    assert room["devices"][0]["entity_id"] == "climate.new_trv"
    assert room["devices"][0]["type"] == "trv"
    assert room["devices"][0]["heating_system_type"] == "radiator"
    assert room["devices"][1]["entity_id"] == "climate.new_ac"
    assert room["devices"][1]["type"] == "ac"
    assert room["thermostats"] == ["climate.new_trv"]
    assert room["acs"] == ["climate.new_ac"]


def test_ensure_room_has_devices_derives_heating_system_type():
    room = {
        "devices": [
            {"entity_id": "climate.trv1", "type": "trv", "role": "auto", "heating_system_type": "underfloor"},
            {"entity_id": "climate.trv2", "type": "trv", "role": "auto", "heating_system_type": "radiator"},
        ],
        "thermostats": ["climate.trv1", "climate.trv2"],
        "acs": [],
    }
    ensure_room_has_devices(room)
    assert room["heating_system_type"] == "underfloor"


def test_ensure_room_has_devices_empty_room():
    room = {}
    ensure_room_has_devices(room)
    assert room["devices"] == []
    assert room["thermostats"] == []
    assert room["acs"] == []
    assert room["heating_system_type"] == ""


# ---------------------------------------------------------------------------
# get_room_heating_system_type
# ---------------------------------------------------------------------------


def test_get_room_heating_system_type_single():
    devices = [{"type": "trv", "heating_system_type": "radiator"}]
    assert get_room_heating_system_type(devices) == "radiator"


def test_get_room_heating_system_type_mixed_underfloor_wins():
    devices = [
        {"type": "trv", "heating_system_type": "radiator"},
        {"type": "trv", "heating_system_type": "underfloor"},
    ]
    assert get_room_heating_system_type(devices) == "underfloor"


def test_get_room_heating_system_type_only_trvs_considered():
    devices = [
        {"type": "ac", "heating_system_type": "underfloor"},
        {"type": "trv", "heating_system_type": "radiator"},
    ]
    assert get_room_heating_system_type(devices) == "radiator"


def test_get_room_heating_system_type_empty():
    assert get_room_heating_system_type([]) == ""


def test_get_room_heating_system_type_no_trvs():
    devices = [{"type": "ac", "heating_system_type": "underfloor"}]
    assert get_room_heating_system_type(devices) == ""


# ---------------------------------------------------------------------------
# get_all_entity_ids / get_trv_eids / get_ac_eids
# ---------------------------------------------------------------------------

_MIXED_DEVICES = [
    {"entity_id": "climate.trv1", "type": "trv"},
    {"entity_id": "climate.ac1", "type": "ac"},
    {"entity_id": "climate.ac2", "type": "ac"},
]


def test_get_all_entity_ids():
    # TRVs first for deterministic ordering, then others
    assert get_all_entity_ids(_MIXED_DEVICES) == [
        "climate.trv1",
        "climate.ac1",
        "climate.ac2",
    ]


def test_get_all_entity_ids_trvs_first():
    """Even when ACs come first in the array, TRVs are returned first."""
    devices = [
        {"entity_id": "climate.ac1", "type": "ac"},
        {"entity_id": "climate.trv1", "type": "trv"},
        {"entity_id": "climate.ac2", "type": "ac"},
    ]
    assert get_all_entity_ids(devices) == [
        "climate.trv1",
        "climate.ac1",
        "climate.ac2",
    ]


def test_get_all_entity_ids_skips_missing_entity_id():
    devices = [{"type": "trv"}, {"entity_id": "climate.ok", "type": "ac"}]
    assert get_all_entity_ids(devices) == ["climate.ok"]


def test_get_trv_eids():
    assert get_trv_eids(_MIXED_DEVICES) == ["climate.trv1"]


def test_get_ac_eids():
    assert get_ac_eids(_MIXED_DEVICES) == ["climate.ac1", "climate.ac2"]


def test_get_entity_ids_by_type_multi():
    result = get_entity_ids_by_type(_MIXED_DEVICES, "trv", "ac")
    assert result == ["climate.trv1", "climate.ac1", "climate.ac2"]


def test_get_entity_ids_by_type_no_match():
    assert get_entity_ids_by_type(_MIXED_DEVICES, "nonexistent") == []


# ---------------------------------------------------------------------------
# get_device_by_eid
# ---------------------------------------------------------------------------


def test_get_device_by_eid_found():
    device = get_device_by_eid(_MIXED_DEVICES, "climate.ac1")
    assert device is not None
    assert device["type"] == "ac"


def test_get_device_by_eid_not_found():
    assert get_device_by_eid(_MIXED_DEVICES, "climate.nope") is None


# ---------------------------------------------------------------------------
# is_trv_type / is_ac_type
# ---------------------------------------------------------------------------


def test_is_trv_type_true():
    assert is_trv_type({"type": "trv"}) is True


def test_is_trv_type_false():
    assert is_trv_type({"type": "ac"}) is False


def test_is_ac_type_ac():
    assert is_ac_type({"type": "ac"}) is True


def test_is_ac_type_trv():
    assert is_ac_type({"type": "trv"}) is False


# ---------------------------------------------------------------------------
# migrate_heat_pump_devices
# ---------------------------------------------------------------------------


def test_migrate_heat_pump_devices():
    devices = [
        {"entity_id": "climate.hp1", "type": "heat_pump", "role": "auto"},
        {"entity_id": "climate.trv1", "type": "trv", "role": "auto"},
        {"entity_id": "climate.ac1", "type": "ac", "role": "auto"},
    ]
    result = migrate_heat_pump_devices(devices)
    assert result is True
    assert devices[0]["type"] == "ac"
    assert devices[1]["type"] == "trv"
    assert devices[2]["type"] == "ac"


def test_migrate_heat_pump_devices_no_change():
    devices = [{"entity_id": "climate.trv1", "type": "trv"}]
    result = migrate_heat_pump_devices(devices)
    assert result is False


# ---------------------------------------------------------------------------
# get_idle_action
# ---------------------------------------------------------------------------


def test_legacy_to_devices_includes_idle_defaults():
    """legacy_to_devices produces devices with idle_action='off' and idle_fan_mode='low'."""
    devices = legacy_to_devices(["climate.x"], [])
    assert len(devices) == 1
    assert devices[0]["idle_action"] == "off"
    assert devices[0]["idle_fan_mode"] == "low"


def test_get_idle_action_defaults():
    """Empty devices list returns default ('off', 'low')."""
    action, fan_mode = get_idle_action([], "climate.nonexistent")
    assert action == "off"
    assert fan_mode == "low"


def test_get_idle_action_configured():
    """Device with idle_action='fan_only' and idle_fan_mode='auto' returns configured values."""
    devices = [
        {
            "entity_id": "climate.ac1",
            "type": "ac",
            "role": "auto",
            "idle_action": "fan_only",
            "idle_fan_mode": "auto",
        }
    ]
    action, fan_mode = get_idle_action(devices, "climate.ac1")
    assert action == "fan_only"
    assert fan_mode == "auto"
