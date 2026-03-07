"""Tests for RoomMind room store."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.roommind.const import DEFAULT_COMFORT_TEMP, DEFAULT_ECO_TEMP


@pytest.mark.asyncio
async def test_save_room_creates_new(store):
    """Saving a room with a new area_id creates it with defaults."""
    await store.async_load()

    room = await store.async_save_room("wohnzimmer", {})

    assert room["area_id"] == "wohnzimmer"
    assert room["thermostats"] == []
    assert room["acs"] == []
    assert room["temperature_sensor"] == ""
    assert room["humidity_sensor"] == ""
    assert room["climate_mode"] == "auto"
    assert room["schedules"] == []
    assert room["schedule_selector_entity"] == ""
    assert room["comfort_temp"] == DEFAULT_COMFORT_TEMP
    assert room["eco_temp"] == DEFAULT_ECO_TEMP


@pytest.mark.asyncio
async def test_save_room_updates_existing(store):
    """Saving a room twice updates the existing room."""
    await store.async_load()

    await store.async_save_room("wohnzimmer", {"thermostats": ["climate.wz_trv"]})
    updated = await store.async_save_room(
        "wohnzimmer", {"thermostats": ["climate.wz_trv", "climate.wz_trv2"]}
    )

    assert updated["area_id"] == "wohnzimmer"
    assert updated["thermostats"] == ["climate.wz_trv", "climate.wz_trv2"]


@pytest.mark.asyncio
async def test_save_room_with_all_fields(store):
    """Saving a room with all fields stores them correctly."""
    await store.async_load()

    room = await store.async_save_room(
        "schlafzimmer",
        {
            "thermostats": ["climate.sz_trv"],
            "acs": ["climate.sz_ac"],
            "temperature_sensor": "sensor.sz_temp",
            "humidity_sensor": "sensor.sz_humidity",
            "climate_mode": "heat_only",
            "schedules": [{"entity_id": "schedule.bedroom_heating"}],
            "schedule_selector_entity": "",
            "comfort_temp": 22.0,
            "eco_temp": 18.0,
        },
    )

    assert room["area_id"] == "schlafzimmer"
    assert room["thermostats"] == ["climate.sz_trv"]
    assert room["acs"] == ["climate.sz_ac"]
    assert room["temperature_sensor"] == "sensor.sz_temp"
    assert room["humidity_sensor"] == "sensor.sz_humidity"
    assert room["climate_mode"] == "heat_only"
    assert room["schedules"] == [{"entity_id": "schedule.bedroom_heating"}]
    assert room["schedule_selector_entity"] == ""
    assert room["comfort_temp"] == 22.0
    assert room["eco_temp"] == 18.0


@pytest.mark.asyncio
async def test_get_rooms(store):
    """After saving a room it appears in get_rooms()."""
    await store.async_load()

    await store.async_save_room("wohnzimmer", {"thermostats": ["climate.wz_trv"]})

    rooms = store.get_rooms()
    assert "wohnzimmer" in rooms
    assert rooms["wohnzimmer"]["thermostats"] == ["climate.wz_trv"]


@pytest.mark.asyncio
async def test_get_room(store):
    """get_room returns the correct room or None."""
    await store.async_load()

    await store.async_save_room("kueche", {"temperature_sensor": "sensor.kueche_temp"})

    result = store.get_room("kueche")
    assert result is not None
    assert result["area_id"] == "kueche"
    assert result["temperature_sensor"] == "sensor.kueche_temp"

    assert store.get_room("nonexistent_id") is None


@pytest.mark.asyncio
async def test_delete_room(store):
    """Deleting a room removes it from the store."""
    await store.async_load()

    await store.async_save_room("badezimmer", {})
    await store.async_delete_room("badezimmer")

    assert store.get_rooms() == {}


@pytest.mark.asyncio
async def test_delete_nonexistent_raises(store):
    """Deleting a room that doesn't exist raises KeyError."""
    await store.async_load()

    with pytest.raises(KeyError):
        await store.async_delete_room("nonexistent_id")


@pytest.mark.asyncio
async def test_default_climate_mode_is_auto(store):
    """Saving without climate_mode defaults to 'auto'."""
    await store.async_load()

    room = await store.async_save_room("flur", {})

    assert room["climate_mode"] == "auto"


@pytest.mark.asyncio
async def test_default_schedules_is_empty(store):
    """Saving without schedules defaults to empty list."""
    await store.async_load()

    room = await store.async_save_room("flur", {})

    assert room["schedules"] == []
    assert room["schedule_selector_entity"] == ""


@pytest.mark.asyncio
async def test_default_comfort_and_eco_temps(store):
    """Saving without temps defaults to DEFAULT_COMFORT_TEMP and DEFAULT_ECO_TEMP."""
    await store.async_load()

    room = await store.async_save_room("flur", {})

    assert room["comfort_temp"] == DEFAULT_COMFORT_TEMP
    assert room["eco_temp"] == DEFAULT_ECO_TEMP


@pytest.mark.asyncio
async def test_load_restores_data(store):
    """Loading from store restores room data correctly."""
    stored_data = {
        "rooms": {
            "wohnzimmer": {
                "area_id": "wohnzimmer",
                "thermostats": ["climate.wz_trv"],
                "acs": [],
                "temperature_sensor": "sensor.wz_temp",
                "climate_mode": "auto",
                "schedules": [{"entity_id": "schedule.wz_heating"}],
                "schedule_selector_entity": "",
                "comfort_temp": 21.0,
                "eco_temp": 17.0,
            }
        }
    }
    store._store.async_load = AsyncMock(return_value=stored_data)

    await store.async_load()

    rooms = store.get_rooms()
    assert "wohnzimmer" in rooms
    assert rooms["wohnzimmer"]["thermostats"] == ["climate.wz_trv"]
    assert rooms["wohnzimmer"]["schedules"] == [{"entity_id": "schedule.wz_heating"}]
    assert rooms["wohnzimmer"]["schedule_selector_entity"] == ""
    assert rooms["wohnzimmer"]["comfort_temp"] == 21.0
    assert rooms["wohnzimmer"]["eco_temp"] == 17.0


@pytest.mark.asyncio
async def test_get_rooms_returns_copy(store):
    """get_rooms returns a copy, not the internal dict."""
    await store.async_load()

    await store.async_save_room("wohnzimmer", {})

    rooms = store.get_rooms()
    rooms.clear()
    assert store.get_rooms() != {}


@pytest.mark.asyncio
async def test_save_room_with_multiple_schedules(store):
    """Saving a room with multiple schedules stores them correctly."""
    await store.async_load()

    room = await store.async_save_room(
        "wohnzimmer",
        {
            "schedules": [
                {"entity_id": "schedule.morning"},
                {"entity_id": "schedule.evening"},
            ],
            "schedule_selector_entity": "input_boolean.schedule_toggle",
        },
    )

    assert room["schedules"] == [
        {"entity_id": "schedule.morning"},
        {"entity_id": "schedule.evening"},
    ]
    assert room["schedule_selector_entity"] == "input_boolean.schedule_toggle"


@pytest.mark.asyncio
async def test_get_settings_default_empty(store):
    """Fresh store returns empty settings dict."""
    await store.async_load()
    assert store.get_settings() == {}


@pytest.mark.asyncio
async def test_save_settings_persists(store):
    """Saving settings merges and persists."""
    await store.async_load()
    result = await store.async_save_settings({"outdoor_temp_sensor": "sensor.outdoor"})
    assert result["outdoor_temp_sensor"] == "sensor.outdoor"
    saved_data = store._store.async_save.call_args[0][0]
    assert saved_data["settings"]["outdoor_temp_sensor"] == "sensor.outdoor"
    assert "rooms" in saved_data


@pytest.mark.asyncio
async def test_settings_migration_from_old_store(store):
    """Stores without 'settings' key get an empty dict."""
    store._store.async_load = AsyncMock(return_value={
        "rooms": {"r1": {"area_id": "r1", "schedules": []}}
    })
    await store.async_load()
    assert store.get_settings() == {}


@pytest.mark.asyncio
async def test_thermal_data_persistence(store):
    """Thermal data can be saved and retrieved."""
    await store.async_load()
    data = {"room1": {"heating_rate": 0.5, "cooling_rate": -0.3}}
    await store.async_save_thermal_data(data)
    result = store.get_thermal_data()
    assert result == data


@pytest.mark.asyncio
async def test_thermal_data_migration_from_old_store(store):
    """Old store without thermal_data key loads cleanly."""
    store._store.async_load = AsyncMock(return_value={
        "rooms": {"r1": {"area_id": "r1", "schedules": []}}
    })
    await store.async_load()
    # After fresh load, thermal data should be empty dict
    assert store.get_thermal_data() == {}


# ---------------------------------------------------------------------------
# Split heat/cool temperature migration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migrate_room_temps_adds_split_fields(store):
    """Room with only comfort_temp/eco_temp gets split fields on read."""
    from custom_components.roommind.const import DEFAULT_COMFORT_COOL, DEFAULT_ECO_COOL

    stored_data = {
        "rooms": {
            "wohnzimmer": {
                "area_id": "wohnzimmer",
                "comfort_temp": 22.0,
                "eco_temp": 18.0,
                "thermostats": [],
                "acs": [],
                "schedules": [],
            }
        }
    }
    store._store.async_load = AsyncMock(return_value=stored_data)
    await store.async_load()

    room = store.get_room("wohnzimmer")
    assert room is not None
    assert room["comfort_heat"] == 22.0
    assert room["comfort_cool"] == DEFAULT_COMFORT_COOL  # 24.0
    assert room["eco_heat"] == 18.0
    assert room["eco_cool"] == DEFAULT_ECO_COOL  # 27.0


@pytest.mark.asyncio
async def test_migrate_room_temps_preserves_existing(store):
    """Room that already has split fields is not overwritten by migration."""
    stored_data = {
        "rooms": {
            "wohnzimmer": {
                "area_id": "wohnzimmer",
                "comfort_temp": 22.0,
                "eco_temp": 18.0,
                "comfort_heat": 20.0,
                "comfort_cool": 25.0,
                "eco_heat": 16.0,
                "eco_cool": 28.0,
                "thermostats": [],
                "acs": [],
                "schedules": [],
            }
        }
    }
    store._store.async_load = AsyncMock(return_value=stored_data)
    await store.async_load()

    room = store.get_room("wohnzimmer")
    assert room is not None
    # Migration must NOT overwrite existing split fields
    assert room["comfort_heat"] == 20.0
    assert room["comfort_cool"] == 25.0
    assert room["eco_heat"] == 16.0
    assert room["eco_cool"] == 28.0


# ---------------------------------------------------------------------------
# Reverse-sync: comfort_temp/eco_temp → comfort_heat/eco_heat
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_comfort_temp_reverse_syncs_comfort_heat(store):
    """Saving comfort_temp without comfort_heat should update comfort_heat too."""
    await store.async_load()

    # Create a room first (so it has comfort_heat from defaults)
    await store.async_save_room("wohnzimmer", {"thermostats": ["climate.wz_trv"]})

    # Now update with only comfort_temp (no comfort_heat in the dict)
    updated = await store.async_save_room("wohnzimmer", {"comfort_temp": 22.0})

    assert updated["comfort_heat"] == 22.0


@pytest.mark.asyncio
async def test_save_eco_temp_reverse_syncs_eco_heat(store):
    """Saving eco_temp without eco_heat should update eco_heat too."""
    await store.async_load()

    # Create a room first
    await store.async_save_room("wohnzimmer", {"thermostats": ["climate.wz_trv"]})

    # Now update with only eco_temp (no eco_heat in the dict)
    updated = await store.async_save_room("wohnzimmer", {"eco_temp": 16.0})

    assert updated["eco_heat"] == 16.0


@pytest.mark.asyncio
async def test_save_room_syncs_comfort_heat_to_comfort_temp_on_update(store):
    """Updating an existing room with comfort_heat should sync comfort_temp."""
    await store.async_load()
    await store.async_save_room("wohnzimmer", {})
    updated = await store.async_save_room("wohnzimmer", {"comfort_heat": 23.0})
    assert updated["comfort_temp"] == 23.0


@pytest.mark.asyncio
async def test_save_room_syncs_eco_heat_to_eco_temp_on_update(store):
    """Updating an existing room with eco_heat should sync eco_temp."""
    await store.async_load()
    await store.async_save_room("wohnzimmer", {})
    updated = await store.async_save_room("wohnzimmer", {"eco_heat": 15.0})
    assert updated["eco_temp"] == 15.0


@pytest.mark.asyncio
async def test_update_room_missing_raises_key_error(store):
    """async_update_room on a non-existent room should raise KeyError."""
    await store.async_load()
    with pytest.raises(KeyError):
        await store.async_update_room("nonexistent", {"comfort_temp": 21.0})
