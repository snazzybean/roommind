"""Snapshot tests for RoomMindStore.async_save_room.

Captures exact device sync behavior to prevent regressions during store refactoring.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# 1. Create with devices[] — devices->legacy sync
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_with_devices_syncs_legacy(store):
    """Creating a room with devices[] populates thermostats/acs and derives heating_system_type."""
    await store.async_load()
    devices = [
        {"entity_id": "climate.living_trv", "type": "trv", "role": "auto", "heating_system_type": "radiator"},
        {"entity_id": "climate.living_ac", "type": "ac", "role": "auto", "heating_system_type": ""},
    ]
    room = await store.async_save_room("living_room", {"devices": devices})

    assert room["thermostats"] == ["climate.living_trv"]
    assert room["acs"] == ["climate.living_ac"]
    assert room["heating_system_type"] == "radiator"
    assert room["devices"] == devices


@pytest.mark.asyncio
async def test_create_with_underfloor_device(store):
    """Underfloor heating_system_type is derived from TRV devices."""
    await store.async_load()
    devices = [
        {"entity_id": "climate.floor_trv", "type": "trv", "role": "auto", "heating_system_type": "underfloor"},
    ]
    room = await store.async_save_room("floor_room", {"devices": devices})

    assert room["heating_system_type"] == "underfloor"
    assert room["thermostats"] == ["climate.floor_trv"]
    assert room["acs"] == []


@pytest.mark.asyncio
async def test_create_with_mixed_heating_types_most_conservative_wins(store):
    """With mixed heating types, underfloor (most conservative) wins."""
    await store.async_load()
    devices = [
        {"entity_id": "climate.trv1", "type": "trv", "role": "auto", "heating_system_type": "radiator"},
        {"entity_id": "climate.trv2", "type": "trv", "role": "auto", "heating_system_type": "underfloor"},
    ]
    room = await store.async_save_room("mixed_room", {"devices": devices})

    assert room["heating_system_type"] == "underfloor"


# ---------------------------------------------------------------------------
# 2. Create defaults — verify all default field values
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_defaults(store):
    """Creating a room with minimal config produces correct defaults."""
    await store.async_load()
    room = await store.async_save_room("default_room", {})

    assert room["area_id"] == "default_room"
    assert room["comfort_temp"] == 21.0
    assert room["eco_temp"] == 17.0
    assert room["comfort_heat"] == 21.0
    assert room["comfort_cool"] == 24.0
    assert room["eco_heat"] == 17.0
    assert room["eco_cool"] == 27.0
    assert room["climate_mode"] == "auto"
    assert room["temperature_sensor"] == ""
    assert room["humidity_sensor"] == ""
    assert room["occupancy_sensors"] == []
    assert room["devices"] == []
    assert room["thermostats"] == []
    assert room["acs"] == []
    assert room["schedules"] == []
    assert room["schedule_selector_entity"] == ""
    assert room["window_sensors"] == []
    assert room["window_open_delay"] == 0
    assert room["window_close_delay"] == 0
    assert room["presence_persons"] == []
    assert room["display_name"] == ""
    assert room["heating_system_type"] == ""
    assert room["covers"] == []
    assert room["covers_auto_enabled"] is False
    assert room["covers_deploy_threshold"] == 1.5
    assert room["covers_min_position"] == 0
    assert room["covers_outdoor_min_temp"] is None
    assert room["covers_override_minutes"] == 60
    assert room["cover_schedules"] == []
    assert room["cover_schedule_selector_entity"] == ""
    assert room["covers_night_close"] is False
    assert room["covers_night_close_elevation"] == 0
    assert room["covers_night_close_offset_minutes"] == 0
    assert room["covers_night_position"] == 0
    assert room["cover_min_positions"] == {}
    assert room["ignore_presence"] is False
    assert room["is_outdoor"] is False
    assert room["valve_protection_exclude"] == []
    assert room["heat_source_orchestration"] is False
    assert room["heat_source_primary_delta"] == 1.5
    assert room["heat_source_outdoor_threshold"] == 5.0
    assert room["heat_source_ac_min_outdoor"] == -15.0
    assert room["climate_control_enabled"] is True


# ---------------------------------------------------------------------------
# 3. Create with legacy — legacy->devices sync
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_with_legacy_syncs_devices(store):
    """Creating a room with thermostats/acs (no devices) populates devices[]."""
    await store.async_load()
    config = {
        "thermostats": ["climate.bedroom_trv"],
        "acs": ["climate.bedroom_ac"],
        "heating_system_type": "radiator",
    }
    room = await store.async_save_room("bedroom", config)

    assert room["thermostats"] == ["climate.bedroom_trv"]
    assert room["acs"] == ["climate.bedroom_ac"]
    assert len(room["devices"]) == 2

    trv_device = next(d for d in room["devices"] if d["entity_id"] == "climate.bedroom_trv")
    assert trv_device["type"] == "trv"
    assert trv_device["heating_system_type"] == "radiator"

    ac_device = next(d for d in room["devices"] if d["entity_id"] == "climate.bedroom_ac")
    assert ac_device["type"] == "ac"
    assert ac_device["heating_system_type"] == ""


@pytest.mark.asyncio
async def test_create_with_no_devices_or_legacy(store):
    """Creating a room with neither devices nor legacy fields gives empty lists."""
    await store.async_load()
    room = await store.async_save_room("empty_room", {"comfort_temp": 22.0})

    assert room["devices"] == []
    assert room["thermostats"] == []
    assert room["acs"] == []


# ---------------------------------------------------------------------------
# 4. Update with devices[] — verify legacy updated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_with_devices_syncs_legacy(store):
    """Updating an existing room with devices[] regenerates thermostats/acs."""
    await store.async_load()
    await store.async_save_room(
        "update_room",
        {
            "devices": [{"entity_id": "climate.trv1", "type": "trv", "role": "auto", "heating_system_type": ""}],
        },
    )

    updated = await store.async_save_room(
        "update_room",
        {
            "devices": [
                {"entity_id": "climate.trv1", "type": "trv", "role": "auto", "heating_system_type": ""},
                {"entity_id": "climate.ac1", "type": "ac", "role": "auto", "heating_system_type": ""},
            ],
        },
    )

    assert updated["thermostats"] == ["climate.trv1"]
    assert updated["acs"] == ["climate.ac1"]
    assert len(updated["devices"]) == 2


@pytest.mark.asyncio
async def test_update_devices_derives_heating_system_type(store):
    """Updating devices recalculates room-level heating_system_type."""
    await store.async_load()
    await store.async_save_room(
        "hst_room",
        {
            "devices": [{"entity_id": "climate.trv1", "type": "trv", "role": "auto", "heating_system_type": ""}],
        },
    )

    updated = await store.async_save_room(
        "hst_room",
        {
            "devices": [
                {"entity_id": "climate.trv1", "type": "trv", "role": "auto", "heating_system_type": "underfloor"}
            ],
        },
    )

    assert updated["heating_system_type"] == "underfloor"


# ---------------------------------------------------------------------------
# 5. Update with legacy — verify devices updated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_with_legacy_syncs_devices(store):
    """Updating with thermostats/acs (no devices) regenerates devices[]."""
    await store.async_load()
    await store.async_save_room(
        "legacy_update",
        {
            "devices": [{"entity_id": "climate.trv1", "type": "trv", "role": "auto", "heating_system_type": ""}],
        },
    )

    updated = await store.async_save_room(
        "legacy_update",
        {
            "thermostats": ["climate.trv1", "climate.trv2"],
            "acs": ["climate.ac1"],
        },
    )

    assert len(updated["devices"]) == 3
    types = {d["entity_id"]: d["type"] for d in updated["devices"]}
    assert types["climate.trv1"] == "trv"
    assert types["climate.trv2"] == "trv"
    assert types["climate.ac1"] == "ac"


# ---------------------------------------------------------------------------
# 6. Update non-device fields — devices unaffected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_nondevice_fields_preserves_devices(store):
    """Updating comfort_temp does not trigger device sync or alter devices."""
    await store.async_load()
    original_devices = [
        {"entity_id": "climate.trv1", "type": "trv", "role": "auto", "heating_system_type": "radiator"},
    ]
    await store.async_save_room("stable_room", {"devices": original_devices})

    updated = await store.async_save_room("stable_room", {"comfort_temp": 23.0})

    assert updated["devices"] == original_devices
    assert updated["thermostats"] == ["climate.trv1"]
    assert updated["acs"] == []
    assert updated["comfort_temp"] == 23.0


# ---------------------------------------------------------------------------
# 7. Split temp sync — comfort_heat <-> comfort_temp
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_comfort_heat_syncs_to_comfort_temp(store):
    """On create, comfort_heat sets comfort_temp to same value."""
    await store.async_load()
    room = await store.async_save_room("temp_room", {"comfort_heat": 22.5})

    assert room["comfort_heat"] == 22.5
    assert room["comfort_temp"] == 22.5


@pytest.mark.asyncio
async def test_create_comfort_temp_syncs_to_comfort_heat(store):
    """On create, comfort_temp (without comfort_heat) sets comfort_heat to same value."""
    await store.async_load()
    room = await store.async_save_room("temp_room2", {"comfort_temp": 23.0})

    assert room["comfort_temp"] == 23.0
    assert room["comfort_heat"] == 23.0


@pytest.mark.asyncio
async def test_create_eco_heat_syncs_to_eco_temp(store):
    """On create, eco_heat sets eco_temp to same value."""
    await store.async_load()
    room = await store.async_save_room("eco_room", {"eco_heat": 18.0})

    assert room["eco_heat"] == 18.0
    assert room["eco_temp"] == 18.0


@pytest.mark.asyncio
async def test_create_eco_temp_syncs_to_eco_heat(store):
    """On create, eco_temp (without eco_heat) sets eco_heat to same value."""
    await store.async_load()
    room = await store.async_save_room("eco_room2", {"eco_temp": 19.0})

    assert room["eco_temp"] == 19.0
    assert room["eco_heat"] == 19.0


@pytest.mark.asyncio
async def test_update_comfort_heat_syncs_to_comfort_temp(store):
    """On update, comfort_heat also updates comfort_temp."""
    await store.async_load()
    await store.async_save_room("sync_room", {})

    updated = await store.async_save_room("sync_room", {"comfort_heat": 22.0})

    assert updated["comfort_heat"] == 22.0
    assert updated["comfort_temp"] == 22.0


@pytest.mark.asyncio
async def test_update_comfort_temp_without_heat_syncs_to_comfort_heat(store):
    """On update, comfort_temp without comfort_heat also updates comfort_heat."""
    await store.async_load()
    await store.async_save_room("sync_room2", {})

    updated = await store.async_save_room("sync_room2", {"comfort_temp": 23.5})

    assert updated["comfort_temp"] == 23.5
    assert updated["comfort_heat"] == 23.5


@pytest.mark.asyncio
async def test_update_eco_heat_syncs_to_eco_temp(store):
    """On update, eco_heat also updates eco_temp."""
    await store.async_load()
    await store.async_save_room("eco_sync", {})

    updated = await store.async_save_room("eco_sync", {"eco_heat": 16.0})

    assert updated["eco_heat"] == 16.0
    assert updated["eco_temp"] == 16.0


@pytest.mark.asyncio
async def test_update_eco_temp_without_heat_syncs_to_eco_heat(store):
    """On update, eco_temp without eco_heat also updates eco_heat."""
    await store.async_load()
    await store.async_save_room("eco_sync2", {})

    updated = await store.async_save_room("eco_sync2", {"eco_temp": 18.5})

    assert updated["eco_temp"] == 18.5
    assert updated["eco_heat"] == 18.5


@pytest.mark.asyncio
async def test_update_comfort_heat_takes_precedence_over_comfort_temp(store):
    """When both comfort_heat and comfort_temp sent, comfort_heat wins for comfort_temp."""
    await store.async_load()
    await store.async_save_room("precedence_room", {})

    updated = await store.async_save_room(
        "precedence_room",
        {
            "comfort_heat": 22.0,
            "comfort_temp": 25.0,
        },
    )

    # comfort_heat sync runs and overwrites comfort_temp
    assert updated["comfort_heat"] == 22.0
    assert updated["comfort_temp"] == 22.0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_with_empty_devices_list(store):
    """Empty devices[] does not trigger device sync (falsy check)."""
    await store.async_load()
    room = await store.async_save_room("empty_dev", {"devices": []})

    assert room["devices"] == []
    assert room["thermostats"] == []
    assert room["acs"] == []


@pytest.mark.asyncio
async def test_update_removes_all_devices(store):
    """Updating with empty devices[] clears legacy fields."""
    await store.async_load()
    await store.async_save_room(
        "clear_room",
        {
            "devices": [{"entity_id": "climate.trv1", "type": "trv", "role": "auto", "heating_system_type": ""}],
        },
    )

    updated = await store.async_save_room("clear_room", {"devices": []})

    # devices key is in config, so device sync runs
    assert updated["devices"] == []
    assert updated["thermostats"] == []
    assert updated["acs"] == []
    assert updated["heating_system_type"] == ""


@pytest.mark.asyncio
async def test_save_persists_to_storage(store):
    """Each save call triggers async_save on the underlying store."""
    await store.async_load()
    initial_call_count = store._store.async_save.call_count

    await store.async_save_room("persist_room", {})

    assert store._store.async_save.call_count == initial_call_count + 1


@pytest.mark.asyncio
async def test_create_then_update_preserves_area_id(store):
    """area_id in config is ignored; the parameter area_id is used."""
    await store.async_load()
    room = await store.async_save_room("real_id", {"area_id": "fake_id"})
    assert room["area_id"] == "real_id"

    updated = await store.async_save_room("real_id", {"area_id": "another_fake", "comfort_temp": 20.0})
    assert updated["area_id"] == "real_id"
