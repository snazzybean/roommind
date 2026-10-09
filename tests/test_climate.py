"""Tests for RoomMind climate platform."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.climate import ClimateEntityFeature, HVACMode

from custom_components.roommind.climate import (
    RoomMindOverrideClimate,
    _create_room_climates,
    async_setup_entry,
)
from custom_components.roommind.const import (
    DEFAULT_COMFORT_COOL,
    DEFAULT_COMFORT_HEAT,
    DOMAIN,
    OVERRIDE_CUSTOM,
)


@pytest.fixture
def mock_coordinator():
    coordinator = MagicMock()
    coordinator.hass = MagicMock()
    coordinator.async_request_refresh = AsyncMock()
    store = MagicMock()
    coordinator.hass.data = {DOMAIN: {"store": store}}
    coordinator.data = {}
    return coordinator, store


def _active_auto_room(**overrides):
    room = {
        "climate_mode": "auto",
        "override_heat": 21.0,
        "override_cool": 24.0,
        "override_until": None,
        "override_type": "custom",
    }
    room.update(overrides)
    return room


def test_create_room_climates(mock_coordinator):
    """Factory creates exactly one climate entity per room."""
    coordinator, _ = mock_coordinator
    climates = _create_room_climates(coordinator, "living_room")
    assert len(climates) == 1
    assert isinstance(climates[0], RoomMindOverrideClimate)


def test_unique_id_and_entity_id(mock_coordinator):
    """Climate entity has correct unique_id and entity_id."""
    coordinator, _ = mock_coordinator
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    assert entity.unique_id == "roommind_living_room_override"
    assert entity.entity_id == "climate.roommind_living_room_override"


def test_hvac_mode_off_when_no_override(mock_coordinator):
    """hvac_mode returns OFF when no override is set."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {
        "override_heat": None,
        "override_cool": None,
        "override_until": None,
        "override_type": None,
    }
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    assert entity.hvac_mode == HVACMode.OFF


def test_hvac_mode_heat_cool_when_permanent_override(mock_coordinator):
    """hvac_mode returns HEAT_COOL when permanent override is active in auto mode."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = _active_auto_room()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    assert entity.hvac_mode == HVACMode.HEAT_COOL


def test_hvac_mode_heat_cool_when_timed_override_active(mock_coordinator):
    """hvac_mode returns HEAT_COOL when timed override is still active."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = _active_auto_room(override_until=time.time() + 3600, override_type="boost")
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    assert entity.hvac_mode == HVACMode.HEAT_COOL


def test_hvac_mode_off_when_timed_override_expired(mock_coordinator):
    """hvac_mode returns OFF when timed override has expired."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = _active_auto_room(override_until=time.time() - 100, override_type="boost")
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    assert entity.hvac_mode == HVACMode.OFF


def test_hvac_mode_heat_when_heat_only(mock_coordinator):
    """hvac_mode returns HEAT for active override in heat_only room."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = _active_auto_room(climate_mode="heat_only", override_cool=None)
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    assert entity.hvac_mode == HVACMode.HEAT


def test_hvac_mode_cool_when_cool_only(mock_coordinator):
    """hvac_mode returns COOL for active override in cool_only room."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = _active_auto_room(climate_mode="cool_only", override_heat=None)
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    assert entity.hvac_mode == HVACMode.COOL


def test_override_entity_auto_reports_range(mock_coordinator):
    """Auto mode exposes HEAT_COOL with range support and low/high targets."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = _active_auto_room()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    assert HVACMode.HEAT_COOL in entity.hvac_modes
    assert entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
    assert not entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE
    assert entity.target_temperature_low == 21.0
    assert entity.target_temperature_high == 24.0


def test_override_entity_heat_only_single_target(mock_coordinator):
    """heat_only mode exposes single-target HEAT with override_heat value."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = _active_auto_room(climate_mode="heat_only", override_cool=None)
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    assert entity.hvac_modes == [HVACMode.OFF, HVACMode.HEAT]
    assert entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE
    assert not entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
    assert entity.target_temperature == 21.0


def test_override_entity_cool_only_single_target(mock_coordinator):
    """cool_only mode exposes single-target COOL with override_cool value."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = _active_auto_room(climate_mode="cool_only", override_heat=None)
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    assert entity.hvac_modes == [HVACMode.OFF, HVACMode.COOL]
    assert entity.target_temperature == 24.0


def test_target_temperatures_none_when_no_override(mock_coordinator):
    """All target properties return None when no override is active."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {
        "climate_mode": "auto",
        "override_heat": None,
        "override_cool": None,
        "override_until": None,
        "override_type": None,
    }
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    assert entity.target_temperature is None
    assert entity.target_temperature_low is None
    assert entity.target_temperature_high is None


def test_current_temperature_from_coordinator_data(mock_coordinator):
    """current_temperature reads from coordinator.data."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"override_heat": None, "override_cool": None}
    coordinator.data = {"rooms": {"living_room": {"current_temp": 20.5}}}
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    assert entity.current_temperature == 20.5


def test_current_temperature_none_when_no_data(mock_coordinator):
    """current_temperature returns None when coordinator has no data."""
    coordinator, store = mock_coordinator
    coordinator.data = None
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    assert entity.current_temperature is None


def test_current_temperature_none_when_room_not_in_data(mock_coordinator):
    """current_temperature returns None when room not in coordinator data."""
    coordinator, store = mock_coordinator
    coordinator.data = {"rooms": {"other_room": {"current_temp": 20.0}}}
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    assert entity.current_temperature is None


@pytest.mark.asyncio
async def test_override_entity_set_range_writes_split(mock_coordinator):
    """Setting low/high in auto mode writes split override_heat/override_cool."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"climate_mode": "auto"}
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_temperature(target_temp_low=20.0, target_temp_high=25.0)
    store.async_update_room.assert_awaited_once_with(
        "living_room",
        {
            "override_heat": 20.0,
            "override_cool": 25.0,
            "override_until": None,
            "override_type": OVERRIDE_CUSTOM,
        },
    )
    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_single_temperature_auto_derives_dead_band(mock_coordinator):
    """Bare temperature in auto mode derives a dead-band from comfort_cool."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"climate_mode": "auto", "comfort_cool": 24.0}
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_temperature(temperature=22.0)
    store.async_update_room.assert_awaited_once_with(
        "living_room",
        {
            "override_heat": 22.0,
            "override_cool": 24.0,
            "override_until": None,
            "override_type": OVERRIDE_CUSTOM,
        },
    )


@pytest.mark.asyncio
async def test_set_single_temperature_auto_above_comfort_cool(mock_coordinator):
    """Bare temperature above comfort_cool collapses band to the higher value."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"climate_mode": "auto", "comfort_cool": 24.0}
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_temperature(temperature=26.0)
    written = store.async_update_room.await_args[0][1]
    assert written["override_heat"] == 26.0
    assert written["override_cool"] == 26.0


@pytest.mark.asyncio
async def test_set_single_temperature_heat_only(mock_coordinator):
    """Bare temperature in heat_only mode writes heat target only."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"climate_mode": "heat_only"}
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_temperature(temperature=22.0)
    written = store.async_update_room.await_args[0][1]
    assert written["override_heat"] == 22.0
    assert written["override_cool"] is None


@pytest.mark.asyncio
async def test_set_single_temperature_cool_only(mock_coordinator):
    """Bare temperature in cool_only mode writes cool target only."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"climate_mode": "cool_only"}
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_temperature(temperature=23.0)
    written = store.async_update_room.await_args[0][1]
    assert written["override_heat"] is None
    assert written["override_cool"] == 23.0


@pytest.mark.asyncio
async def test_set_temperature_no_temp_kwarg(mock_coordinator):
    """set_temperature does nothing when no temperature kwargs are given."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"climate_mode": "auto"}
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_temperature()
    store.async_update_room.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_hvac_mode_off_clears_override(mock_coordinator):
    """Setting hvac_mode to OFF clears override and refreshes."""
    coordinator, store = mock_coordinator
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_hvac_mode(HVACMode.OFF)
    store.async_update_room.assert_awaited_once_with(
        "living_room",
        {
            "override_heat": None,
            "override_cool": None,
            "override_until": None,
            "override_type": None,
        },
    )
    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_hvac_mode_heat_cool_activates_with_comfort_defaults(mock_coordinator):
    """Setting HEAT_COOL without active override activates with comfort targets."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {
        "climate_mode": "auto",
        "override_heat": None,
        "override_cool": None,
        "override_until": None,
        "override_type": None,
    }
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)
    store.async_update_room.assert_awaited_once_with(
        "living_room",
        {
            "override_heat": DEFAULT_COMFORT_HEAT,
            "override_cool": DEFAULT_COMFORT_COOL,
            "override_until": None,
            "override_type": OVERRIDE_CUSTOM,
        },
    )
    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_hvac_mode_heat_activates_heat_only(mock_coordinator):
    """Setting HEAT in heat_only room activates heat target only."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {
        "climate_mode": "heat_only",
        "comfort_heat": 22.0,
        "override_heat": None,
        "override_cool": None,
    }
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_hvac_mode(HVACMode.HEAT)
    written = store.async_update_room.await_args[0][1]
    assert written["override_heat"] == 22.0
    assert written["override_cool"] is None


@pytest.mark.asyncio
async def test_set_hvac_mode_cool_activates_cool_only(mock_coordinator):
    """Setting COOL in cool_only room activates cool target only."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {
        "climate_mode": "cool_only",
        "comfort_cool": 25.0,
        "override_heat": None,
        "override_cool": None,
    }
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_hvac_mode(HVACMode.COOL)
    written = store.async_update_room.await_args[0][1]
    assert written["override_heat"] is None
    assert written["override_cool"] == 25.0


@pytest.mark.asyncio
async def test_set_hvac_mode_noop_when_override_exists(mock_coordinator):
    """Setting a non-OFF mode does not update store if override already active."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = _active_auto_room(override_heat=23.0, override_cool=25.0)
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)
    store.async_update_room.assert_not_awaited()
    coordinator.async_request_refresh.assert_awaited_once()


def test_hvac_mode_off_when_room_missing(mock_coordinator):
    """hvac_mode returns OFF when room doesn't exist in store."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = None
    entity = RoomMindOverrideClimate(coordinator, "nonexistent")
    assert entity.hvac_mode == HVACMode.OFF


@pytest.mark.asyncio
async def test_async_setup_entry_creates_entities_for_all_rooms():
    """async_setup_entry creates climate entities for all rooms."""
    coordinator = MagicMock()
    coordinator._climate_entity_areas = set()

    store = MagicMock()
    store.get_rooms.return_value = {
        "living_room": {"thermostats": ["climate.living"]},
        "bedroom": {},
    }

    entry = MagicMock()
    entry.entry_id = "test_entry"

    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: coordinator, "store": store}}

    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)

    assert coordinator.async_add_climate_entities is async_add_entities
    async_add_entities.assert_called_once()
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 2
    assert all(isinstance(e, RoomMindOverrideClimate) for e in entities)
    assert "living_room" in coordinator._climate_entity_areas
    assert "bedroom" in coordinator._climate_entity_areas


@pytest.mark.asyncio
async def test_async_setup_entry_no_rooms():
    """async_setup_entry does not call async_add_entities when no rooms exist."""
    coordinator = MagicMock()
    coordinator._climate_entity_areas = set()

    store = MagicMock()
    store.get_rooms.return_value = {}

    entry = MagicMock()
    entry.entry_id = "test_entry"

    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: coordinator, "store": store}}

    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)

    async_add_entities.assert_not_called()


def _live(coordinator, **fields):
    coordinator.data = {"rooms": {"living_room": fields}}


@pytest.mark.asyncio
async def test_set_hvac_mode_seeds_override_from_effective_targets(mock_coordinator):
    """Switching on seeds the override from what is in force, not from comfort (#447)."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {
        "climate_mode": "auto",
        "comfort_heat": 22.5,
        "comfort_cool": 24.0,
        "override_heat": None,
        "override_cool": None,
    }
    _live(coordinator, heat_target=24.5, cool_target=26.0)
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)
    written = store.async_update_room.await_args[0][1]
    assert written["override_heat"] == 24.5
    assert written["override_cool"] == 26.0
    assert written["override_type"] == OVERRIDE_CUSTOM


@pytest.mark.asyncio
async def test_set_hvac_mode_seed_excludes_mold_prevention_delta(mock_coordinator):
    """The mold prevention boost is not part of the band the override freezes."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"climate_mode": "auto"}
    _live(
        coordinator,
        heat_target=23.0,
        cool_target=26.0,
        mold_prevention_active=True,
        mold_prevention_delta=2.0,
    )
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)
    assert store.async_update_room.await_args[0][1]["override_heat"] == 21.0


@pytest.mark.asyncio
async def test_set_hvac_mode_seed_falls_back_to_comfort_when_forced_off(mock_coordinator):
    """Force-off rooms have no live band, so the comfort band is used."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"climate_mode": "auto", "comfort_heat": 22.0, "comfort_cool": 25.0}
    _live(coordinator, heat_target=None, cool_target=None)
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)
    written = store.async_update_room.await_args[0][1]
    assert (written["override_heat"], written["override_cool"]) == (22.0, 25.0)


@pytest.mark.asyncio
async def test_set_hvac_mode_seed_masks_unusable_side(mock_coordinator):
    """heat_only rooms never get a cool side from the seed."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"climate_mode": "heat_only"}
    _live(coordinator, heat_target=21.0, cool_target=26.0)
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_hvac_mode(HVACMode.HEAT)
    written = store.async_update_room.await_args[0][1]
    assert (written["override_heat"], written["override_cool"]) == (21.0, None)


@pytest.mark.asyncio
async def test_set_range_low_only_keeps_active_cool_side(mock_coordinator):
    """A low-only call keeps the cool side of the active override."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = _active_auto_room(override_heat=21.0, override_cool=26.0)
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_temperature(target_temp_low=22.0)
    written = store.async_update_room.await_args[0][1]
    assert (written["override_heat"], written["override_cool"]) == (22.0, 26.0)


@pytest.mark.asyncio
async def test_set_range_high_only_keeps_active_heat_side(mock_coordinator):
    """A high-only call keeps the heat side of the active override."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = _active_auto_room(override_heat=21.0, override_cool=26.0)
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_temperature(target_temp_high=28.5)
    written = store.async_update_room.await_args[0][1]
    assert (written["override_heat"], written["override_cool"]) == (21.0, 28.5)


@pytest.mark.asyncio
async def test_set_range_half_without_override_uses_effective_band(mock_coordinator):
    """Without an override the missing side comes from the live targets."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"climate_mode": "auto"}
    _live(coordinator, heat_target=22.5, cool_target=26.0)
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_temperature(target_temp_high=28.5)
    written = store.async_update_room.await_args[0][1]
    assert (written["override_heat"], written["override_cool"]) == (22.5, 28.5)


@pytest.mark.asyncio
async def test_set_range_half_never_inverts_band(mock_coordinator):
    """A half-range value past the kept side pulls that side along."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = _active_auto_room(override_heat=21.0, override_cool=24.0)
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_temperature(target_temp_low=26.0)
    written = store.async_update_room.await_args[0][1]
    assert (written["override_heat"], written["override_cool"]) == (26.0, 26.0)
    await entity.async_set_temperature(target_temp_high=19.0)
    written = store.async_update_room.await_args[0][1]
    assert (written["override_heat"], written["override_cool"]) == (19.0, 19.0)


@pytest.mark.asyncio
async def test_set_hvac_mode_seed_widens_band_to_keep_idle_room_idle(mock_coordinator):
    """An idle room outside the band (gate holds it) stays idle after the seed (#447)."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"climate_mode": "auto"}
    _live(coordinator, heat_target=22.5, cool_target=24.0, current_temp=24.6, commanded_mode="idle")
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)
    written = store.async_update_room.await_args[0][1]
    assert (written["override_heat"], written["override_cool"]) == (22.5, 24.6)


@pytest.mark.asyncio
async def test_set_hvac_mode_seed_widens_heat_side_for_cold_idle_room(mock_coordinator):
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"climate_mode": "auto"}
    _live(coordinator, heat_target=22.5, cool_target=26.0, current_temp=20.0, commanded_mode="idle")
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)
    written = store.async_update_room.await_args[0][1]
    assert (written["override_heat"], written["override_cool"]) == (20.0, 26.0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("commanded", "temp", "expected"),
    [("cooling", 24.6, (22.5, 24.0)), ("heating", 20.0, (22.5, 24.0))],
)
async def test_set_hvac_mode_seed_keeps_band_for_side_already_running(mock_coordinator, commanded, temp, expected):
    """A room already heating/cooling keeps its band: nothing changes on turn-on."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"climate_mode": "auto"}
    _live(coordinator, heat_target=22.5, cool_target=24.0, current_temp=temp, commanded_mode=commanded)
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)
    written = store.async_update_room.await_args[0][1]
    assert (written["override_heat"], written["override_cool"]) == expected


@pytest.mark.asyncio
async def test_turn_on_does_not_start_cooling_below_outdoor_minimum(mock_coordinator):
    """Reported #447 sequence: turn on, then set the real targets.

    The room (24.6 C) sits above the cooling target (24 C) but idle, because it
    is 8 C outside with outdoor_cooling_min 10 C. An override lifts that gate,
    so the seed must not hand the controller a band that makes it cool.
    """
    from custom_components.roommind.const import TargetTemps
    from custom_components.roommind.control.mpc_controller import MPCController
    from custom_components.roommind.control.thermal_model import RoomModelManager

    from .control.conftest import build_hass, make_room

    coordinator, store = mock_coordinator
    store.get_room.return_value = {
        "climate_mode": "auto",
        "comfort_heat": 22.5,
        "comfort_cool": 24.0,
        "override_heat": None,
        "override_cool": None,
    }
    _live(coordinator, heat_target=22.5, cool_target=24.0, current_temp=24.6, commanded_mode="idle")
    store.async_update_room = AsyncMock()
    entity = RoomMindOverrideClimate(coordinator, "living_room")
    await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)
    written = store.async_update_room.await_args[0][1]

    room = make_room(thermostats=[], acs=["climate.ac"], **written)
    ctrl = MPCController(
        build_hass(),
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=8.0,
        settings={"outdoor_cooling_min": 10.0},
        has_external_sensor=True,
    )
    mode, _ = await ctrl.async_evaluate(
        current_temp=24.6, targets=TargetTemps(heat=written["override_heat"], cool=written["override_cool"])
    )
    assert mode == "idle"
