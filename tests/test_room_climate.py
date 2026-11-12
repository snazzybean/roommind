"""Tests for the room climate entity (#238)."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.climate import (
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.exceptions import ServiceValidationError

from custom_components.roommind.climate import RoomMindRoomClimate
from custom_components.roommind.const import DOMAIN, SCHEDULE_UNREADABLE_HOLD_HOURS

TRV = {"entity_id": "climate.trv", "type": "trv"}
AC = {"entity_id": "climate.ac", "type": "ac"}
NEXT_EVENT = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(days=1)


def _room(**overrides):
    room = {
        "area_id": "living_room",
        "climate_mode": "auto",
        "devices": [TRV, AC],
        "comfort_heat": 21.0,
        "comfort_cool": 24.0,
        "eco_heat": 17.0,
        "eco_cool": 27.0,
        "override_heat": None,
        "override_cool": None,
        "override_until": None,
        "override_type": None,
        "climate_control_enabled": True,
        "schedules": [{"entity_id": "schedule.living"}],
    }
    room.update(overrides)
    return room


def _live(**overrides):
    live = {
        "current_temp": 20.4,
        "current_humidity": 48.0,
        "heat_target": 21.0,
        "cool_target": 24.0,
        "mode": "heating",
        "force_off": False,
        "window_open": False,
        "presence_away": False,
        "override_suppressed": False,
        "mold_prevention_active": False,
        "mold_prevention_delta": 0,
    }
    live.update(overrides)
    return live


@pytest.fixture
def setup():
    coordinator = MagicMock()
    coordinator.hass = MagicMock()
    coordinator.hass.config.units.temperature_unit = UnitOfTemperature.CELSIUS
    coordinator.async_request_refresh = AsyncMock()
    coordinator.async_turn_room_off = AsyncMock()
    store = MagicMock()
    store.async_update_room = AsyncMock()
    store.get_settings.return_value = {}
    coordinator.hass.data = {DOMAIN: {"store": store}}
    coordinator.data = {"rooms": {"living_room": _live()}}
    schedule = MagicMock()
    schedule.attributes = {"next_event": NEXT_EVENT}
    states = {"schedule.living": schedule}
    coordinator.hass.states.get = states.get

    def make(room=None, live=None):
        store.get_room.return_value = room if room is not None else _room()
        if live is not None:
            coordinator.data = {"rooms": {"living_room": live}}
        entity = RoomMindRoomClimate(coordinator, "living_room")
        entity.hass = coordinator.hass
        return entity

    with patch.object(RoomMindRoomClimate, "async_write_ha_state") as write:
        coordinator.write_state = write
        yield make, coordinator, store, states


def _written(store) -> dict:
    return store.async_update_room.call_args[0][1]


def test_ids_and_name(setup):
    make, *_ = setup
    entity = make(_room(display_name="Wohnzimmer"))
    assert entity.unique_id == "roommind_living_room_climate"
    assert entity.entity_id == "climate.roommind_living_room"
    assert entity.name == "Wohnzimmer"


def test_name_falls_back_to_area_name(setup):
    make, *_ = setup
    entity = make()
    with patch("custom_components.roommind.climate._get_area_name", return_value="Living Room"):
        assert entity.name == "Living Room"


@pytest.mark.parametrize(
    ("devices", "climate_mode", "acs_heat", "expected"),
    [
        ([TRV], "heat_only", False, [HVACMode.OFF, HVACMode.HEAT]),
        ([AC], "cool_only", False, [HVACMode.OFF, HVACMode.COOL]),
        ([AC], "auto", True, [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.HEAT_COOL]),
        ([TRV, AC], "auto", False, [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.HEAT_COOL]),
        ([TRV], "auto", False, [HVACMode.OFF, HVACMode.HEAT, HVACMode.HEAT_COOL]),
        ([], "heat_only", False, [HVACMode.OFF, HVACMode.HEAT]),
    ],
)
def test_hvac_modes_follow_devices(setup, devices, climate_mode, acs_heat, expected):
    """Modes the devices can serve, plus the room's current mode."""
    make, *_ = setup
    entity = make(_room(devices=devices, climate_mode=climate_mode))
    with patch("custom_components.roommind.climate.check_acs_can_heat", return_value=acs_heat):
        assert entity.hvac_modes == expected


def test_outdoor_room_is_display_only(setup):
    make, *_ = setup
    entity = make(_room(is_outdoor=True))
    assert entity.hvac_modes == [HVACMode.OFF]
    assert entity.hvac_mode == HVACMode.OFF
    assert entity.supported_features == ClimateEntityFeature(0)
    assert entity.current_temperature == 20.4


@pytest.mark.parametrize(
    ("climate_mode", "expected"),
    [("auto", HVACMode.HEAT_COOL), ("heat_only", HVACMode.HEAT), ("cool_only", HVACMode.COOL)],
)
def test_hvac_mode_maps_climate_mode(setup, climate_mode, expected):
    make, *_ = setup
    assert make(_room(climate_mode=climate_mode)).hvac_mode == expected


def test_hvac_mode_off_when_room_control_disabled(setup):
    make, *_ = setup
    entity = make(_room(climate_control_enabled=False))
    assert entity.hvac_mode == HVACMode.OFF
    assert entity.hvac_action == HVACAction.OFF


@pytest.mark.parametrize(
    ("live", "expected"),
    [
        (_live(mode="heating"), HVACAction.HEATING),
        (_live(mode="cooling"), HVACAction.COOLING),
        (_live(mode="idle"), HVACAction.IDLE),
        (_live(mode="heating", force_off=True), HVACAction.OFF),
        ({}, None),
    ],
)
def test_hvac_action_from_live_mode(setup, live, expected):
    make, *_ = setup
    assert make(live=live).hvac_action == expected


def test_hvac_action_off_when_global_control_off(setup):
    make, _, store, _ = setup
    store.get_settings.return_value = {"climate_control_active": False}
    entity = make()
    assert entity.hvac_mode == HVACMode.HEAT_COOL
    assert entity.hvac_action == HVACAction.OFF


def test_features_range_in_auto_single_otherwise(setup):
    """Auto also takes a single temperature (Assist matches only that feature) but shows the range."""
    make, *_ = setup
    auto = make()
    assert auto.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
    assert auto.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE
    assert auto.target_temperature is None
    single = make(_room(climate_mode="heat_only")).supported_features
    assert single & ClimateEntityFeature.TARGET_TEMPERATURE
    assert not single & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
    assert single & ClimateEntityFeature.PRESET_MODE


def test_targets_follow_live_band_without_mold_boost(setup):
    """Without an override the entity shows what the room is held at, minus mold prevention."""
    make, *_ = setup
    entity = make(live=_live(heat_target=19.0, cool_target=26.0, mold_prevention_active=True, mold_prevention_delta=2))
    assert entity.target_temperature_low == 17.0
    assert entity.target_temperature_high == 26.0
    assert entity.preset_mode == "none"


def test_targets_from_store_while_override_active(setup):
    """The stored override shows at once, before the coordinator has refreshed."""
    make, *_ = setup
    entity = make(_room(override_heat=22.5, override_cool=25.0, override_type="custom"))
    assert entity.target_temperature_low == 22.5
    assert entity.target_temperature_high == 25.0
    assert entity.preset_mode == "manual"


def test_suppressed_override_shows_live_band(setup):
    make, *_ = setup
    entity = make(
        _room(override_heat=22.5, override_cool=25.0, override_type="boost", override_until=NEXT_EVENT.timestamp()),
        live=_live(heat_target=17.0, cool_target=27.0, override_suppressed=True),
    )
    assert entity.target_temperature_low == 17.0
    assert entity.preset_mode == "none"
    assert entity.extra_state_attributes["override_until"] is None


@pytest.mark.parametrize(("climate_mode", "expected"), [("heat_only", 21.0), ("cool_only", 24.0)])
def test_single_target_by_climate_mode(setup, climate_mode, expected):
    make, *_ = setup
    assert make(_room(climate_mode=climate_mode)).target_temperature == expected


def test_no_target_when_room_forced_off(setup):
    make, *_ = setup
    entity = make(live=_live(heat_target=None, cool_target=None, force_off=True))
    assert entity.target_temperature_low is None
    assert entity.target_temperature_high is None
    assert entity.target_temperature is None


@pytest.mark.parametrize(("override_type", "preset"), [("boost", "comfort"), ("eco", "eco")])
def test_preset_reflects_override_type(setup, override_type, preset):
    make, *_ = setup
    entity = make(_room(override_heat=21.0, override_cool=24.0, override_type=override_type))
    assert entity.preset_mode == preset


def test_expired_override_is_no_preset(setup):
    make, *_ = setup
    entity = make(_room(override_heat=21.0, override_cool=24.0, override_type="eco", override_until=time.time() - 1))
    assert entity.preset_mode == "none"
    assert entity.extra_state_attributes["override_until"] is None


def test_extra_attributes(setup):
    make, _, store, _ = setup
    store.get_settings.return_value = {"vacation_until": time.time() + 3600}
    entity = make(
        _room(override_heat=21.0, override_cool=24.0, override_type="eco", override_until=NEXT_EVENT.timestamp()),
        live=_live(window_open=True, presence_away=True, current_humidity=55.0),
    )
    assert entity.extra_state_attributes == {
        "override_until": NEXT_EVENT.isoformat(),
        "window_open": True,
        "presence_away": True,
        "occupancy_vacant": False,
        "vacation": True,
        "price_level": None,
    }
    assert entity.current_humidity == 55.0


@pytest.mark.asyncio
async def test_set_temperature_holds_until_next_schedule_change(setup):
    make, coordinator, store, _ = setup
    entity = make()
    await entity.async_set_temperature(**{ATTR_TARGET_TEMP_LOW: 22.0, ATTR_TARGET_TEMP_HIGH: 25.0})
    assert _written(store) == {
        "override_heat": 22.0,
        "override_cool": 25.0,
        "override_until": NEXT_EVENT.timestamp(),
        "override_type": "custom",
    }
    coordinator.clear_override_seed.assert_called_once_with("living_room")
    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_temperature_without_schedule_holds_until_changed(setup):
    make, _, store, _ = setup
    entity = make(_room(schedules=[]))
    await entity.async_set_temperature(**{ATTR_TARGET_TEMP_LOW: 22.0, ATTR_TARGET_TEMP_HIGH: 25.0})
    assert _written(store)["override_until"] is None


@pytest.mark.asyncio
async def test_set_temperature_under_unavailable_schedule_holds_for_the_fallback(setup):
    make, _, store, states = setup
    states["schedule.living"].state = "unavailable"
    states["schedule.living"].attributes = {}
    before = time.time()
    await make().async_set_temperature(**{ATTR_TARGET_TEMP_LOW: 22.0, ATTR_TARGET_TEMP_HIGH: 25.0})
    until = _written(store)["override_until"]
    assert until is not None
    assert (
        before + SCHEDULE_UNREADABLE_HOLD_HOURS * 3600 <= until <= time.time() + SCHEDULE_UNREADABLE_HOLD_HOURS * 3600
    )


@pytest.mark.asyncio
async def test_set_temperature_reads_iso_next_event(setup):
    make, _, store, states = setup
    states["schedule.living"].attributes = {"next_event": NEXT_EVENT.isoformat()}
    await make().async_set_temperature(**{ATTR_TARGET_TEMP_LOW: 22.0, ATTR_TARGET_TEMP_HIGH: 25.0})
    assert _written(store)["override_until"] == NEXT_EVENT.timestamp()


@pytest.mark.asyncio
async def test_set_low_only_keeps_live_cool_side(setup):
    """A wall display that only sends the heating side keeps the cooling side in force."""
    make, _, store, _ = setup
    entity = make(live=_live(heat_target=21.0, cool_target=24.5))
    await entity.async_set_temperature(**{ATTR_TARGET_TEMP_LOW: 22.0})
    assert (_written(store)["override_heat"], _written(store)["override_cool"]) == (22.0, 24.5)


@pytest.mark.asyncio
async def test_set_single_temperature_in_heat_only_room(setup):
    make, _, store, _ = setup
    entity = make(_room(climate_mode="heat_only"))
    await entity.async_set_temperature(**{ATTR_TEMPERATURE: 22.0})
    assert (_written(store)["override_heat"], _written(store)["override_cool"]) == (22.0, None)


@pytest.mark.asyncio
async def test_set_temperature_without_targets_does_nothing(setup):
    make, coordinator, store, _ = setup
    await make().async_set_temperature()
    store.async_update_room.assert_not_awaited()
    coordinator.async_request_refresh.assert_not_awaited()


@pytest.mark.parametrize(
    ("preset", "override_type", "band"), [("comfort", "boost", (21.0, 24.0)), ("eco", "eco", (17.0, 27.0))]
)
@pytest.mark.asyncio
async def test_preset_sets_override_until_next_change(setup, preset, override_type, band):
    make, _, store, _ = setup
    await make().async_set_preset_mode(preset)
    assert _written(store) == {
        "override_heat": band[0],
        "override_cool": band[1],
        "override_until": NEXT_EVENT.timestamp(),
        "override_type": override_type,
    }


@pytest.mark.asyncio
async def test_eco_preset_masked_in_heat_only_room(setup):
    make, _, store, _ = setup
    await make(_room(climate_mode="heat_only")).async_set_preset_mode("eco")
    assert (_written(store)["override_heat"], _written(store)["override_cool"]) == (17.0, None)


@pytest.mark.asyncio
async def test_preset_none_returns_to_schedule(setup):
    make, coordinator, store, _ = setup
    entity = make(_room(override_heat=21.0, override_cool=24.0, override_type="boost"))
    await entity.async_set_preset_mode("none")
    assert _written(store) == {
        "override_heat": None,
        "override_cool": None,
        "override_until": None,
        "override_type": None,
    }
    coordinator.clear_override_seed.assert_called_once_with("living_room")
    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_hvac_off_switches_room_off(setup):
    make, coordinator, store, _ = setup
    await make().async_set_hvac_mode(HVACMode.OFF)
    coordinator.async_turn_room_off.assert_awaited_once_with("living_room")
    store.async_update_room.assert_not_awaited()
    coordinator.write_state.assert_called_once()


@pytest.mark.parametrize(
    ("hvac_mode", "climate_mode"),
    [(HVACMode.HEAT, "heat_only"), (HVACMode.COOL, "cool_only"), (HVACMode.HEAT_COOL, "auto")],
)
@pytest.mark.asyncio
async def test_hvac_mode_enables_control_and_sets_climate_mode(setup, hvac_mode, climate_mode):
    make, coordinator, store, _ = setup
    await make(_room(climate_control_enabled=False)).async_set_hvac_mode(hvac_mode)
    assert _written(store) == {"climate_control_enabled": True, "climate_mode": climate_mode}
    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_turn_on_keeps_climate_mode(setup):
    make, _, store, _ = setup
    await make(_room(climate_mode="cool_only", climate_control_enabled=False)).async_turn_on()
    assert _written(store) == {"climate_control_enabled": True, "climate_mode": "cool_only"}


@pytest.mark.asyncio
async def test_turn_off_switches_room_off(setup):
    make, coordinator, *_ = setup
    await make().async_turn_off()
    coordinator.async_turn_room_off.assert_awaited_once_with("living_room")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("room", "kwargs"),
    [
        (_room(), {ATTR_TARGET_TEMP_LOW: 21.0, ATTR_TARGET_TEMP_HIGH: 24.0}),
        (_room(), {ATTR_TARGET_TEMP_LOW: 21.1}),
        (_room(climate_mode="heat_only"), {ATTR_TEMPERATURE: 21.0}),
        (_room(climate_mode="cool_only"), {ATTR_TEMPERATURE: 24.0}),
    ],
)
async def test_echo_of_the_target_in_force_sets_no_override(setup, room, kwargs):
    """A display mirrored from the entity sends the schedule's value back; that is no override."""
    make, coordinator, store, _ = setup
    await make(room).async_set_temperature(**kwargs)
    store.async_update_room.assert_not_awaited()
    coordinator.async_request_refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_echo_during_an_override_keeps_preset_and_end(setup):
    make, _, store, _ = setup
    entity = make(_room(climate_mode="heat_only", override_heat=17.0, override_type="eco", override_until=None))
    await entity.async_set_temperature(**{ATTR_TEMPERATURE: 17.0})
    store.async_update_room.assert_not_awaited()


@pytest.mark.asyncio
async def test_new_value_during_an_override_replaces_it(setup):
    make, _, store, _ = setup
    entity = make(_room(climate_mode="heat_only", override_heat=17.0, override_type="eco"))
    await entity.async_set_temperature(**{ATTR_TEMPERATURE: 19.0})
    assert (_written(store)["override_heat"], _written(store)["override_type"]) == (19.0, "custom")


@pytest.mark.asyncio
async def test_change_while_forced_off_sets_override(setup):
    make, _, store, _ = setup
    entity = make(live=_live(heat_target=None, cool_target=None, force_off=True))
    await entity.async_set_temperature(**{ATTR_TARGET_TEMP_LOW: 21.0})
    assert _written(store)["override_heat"] == 21.0


@pytest.mark.asyncio
async def test_single_temperature_in_auto_widens_to_band(setup):
    """Assist sends a bare temperature to an auto room."""
    make, _, store, _ = setup
    await make().async_set_temperature(**{ATTR_TEMPERATURE: 22.5})
    assert (_written(store)["override_heat"], _written(store)["override_cool"]) == (22.5, 24.0)


@pytest.mark.asyncio
async def test_set_temperature_with_hvac_mode_switches_mode_first(setup):
    make, _, store, _ = setup
    entity = make(_room(climate_mode="heat_only", climate_control_enabled=False))
    await entity.async_set_temperature(**{ATTR_TEMPERATURE: 22.0, "hvac_mode": HVACMode.HEAT})
    assert store.async_update_room.await_args_list[0].args[1] == {
        "climate_control_enabled": True,
        "climate_mode": "heat_only",
    }
    assert store.async_update_room.await_args_list[1].args[1]["override_heat"] == 22.0


@pytest.mark.asyncio
async def test_set_temperature_rejects_hvac_mode_the_room_cannot_do(setup):
    """A TRV-only room must not become cool_only through set_temperature's hvac_mode."""
    make, _, store, _ = setup
    entity = make(_room(devices=[TRV], climate_mode="heat_only"))
    with pytest.raises(ServiceValidationError):
        await entity.async_set_temperature(**{ATTR_TEMPERATURE: 22.0, "hvac_mode": HVACMode.COOL})
    store.async_update_room.assert_not_awaited()


@pytest.mark.asyncio
async def test_outdoor_room_ignores_hvac_mode(setup):
    make, coordinator, store, _ = setup
    entity = make(_room(is_outdoor=True))
    await entity.async_set_hvac_mode(HVACMode.OFF)
    await entity.async_set_hvac_mode(HVACMode.HEAT)
    coordinator.async_turn_room_off.assert_not_awaited()
    store.async_update_room.assert_not_awaited()


def test_one_sided_override_shows_both_sides_in_auto(setup):
    """The dual slider sends both sides; a missing one made HA reject every drag."""
    make, *_ = setup
    entity = make(_room(override_heat=15.5, override_cool=None, override_type="custom"))
    assert (entity.target_temperature_low, entity.target_temperature_high) == (15.5, 24.0)
    entity = make(_room(override_heat=None, override_cool=26.0, override_type="custom"))
    assert (entity.target_temperature_low, entity.target_temperature_high) == (21.0, 26.0)


def test_live_band_missing_a_side_in_auto_is_filled(setup):
    make, *_ = setup
    entity = make(live=_live(heat_target=22.0, cool_target=None))
    assert (entity.target_temperature_low, entity.target_temperature_high) == (22.0, 24.0)


@pytest.mark.asyncio
async def test_mode_change_to_auto_completes_the_held_band(setup):
    make, _, store, _ = setup
    entity = make(_room(climate_mode="heat_only", override_heat=15.5, override_cool=None, override_type="custom"))
    await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)
    assert _written(store) == {
        "climate_control_enabled": True,
        "climate_mode": "auto",
        "override_heat": 15.5,
        "override_cool": 24.0,
    }


@pytest.mark.asyncio
async def test_mode_change_to_heat_only_drops_the_cool_side(setup):
    make, _, store, _ = setup
    entity = make(_room(override_heat=22.0, override_cool=25.0, override_type="custom"))
    await entity.async_set_hvac_mode(HVACMode.HEAT)
    assert (_written(store)["override_heat"], _written(store)["override_cool"]) == (22.0, None)


@pytest.mark.asyncio
async def test_same_mode_leaves_the_held_band_alone(setup):
    make, _, store, _ = setup
    entity = make(_room(override_heat=22.0, override_cool=25.0, override_type="custom", climate_control_enabled=False))
    await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)
    assert _written(store) == {"climate_control_enabled": True, "climate_mode": "auto"}


def test_manual_preset_is_offered(setup):
    make, *_ = setup
    assert make().preset_modes == ["none", "comfort", "eco", "manual"]


@pytest.mark.asyncio
async def test_manual_preset_holds_the_band_in_force(setup):
    make, _, store, _ = setup
    await make(live=_live(heat_target=20.0, cool_target=25.0)).async_set_preset_mode("manual")
    assert _written(store) == {
        "override_heat": 20.0,
        "override_cool": 25.0,
        "override_until": NEXT_EVENT.timestamp(),
        "override_type": "custom",
    }


@pytest.mark.asyncio
async def test_manual_preset_turns_a_comfort_hold_into_manual(setup):
    make, _, store, _ = setup
    entity = make(_room(override_heat=21.0, override_cool=24.0, override_type="boost"))
    await entity.async_set_preset_mode("manual")
    assert (_written(store)["override_heat"], _written(store)["override_type"]) == (21.0, "custom")


@pytest.mark.asyncio
async def test_manual_preset_while_manual_changes_nothing(setup):
    make, _, store, _ = setup
    entity = make(_room(override_heat=22.0, override_cool=25.0, override_type="custom", override_until=None))
    await entity.async_set_preset_mode("manual")
    store.async_update_room.assert_not_awaited()


@pytest.mark.asyncio
async def test_manual_preset_without_targets_changes_nothing(setup):
    make, _, store, _ = setup
    entity = make(live=_live(heat_target=None, cool_target=None, force_off=True))
    await entity.async_set_preset_mode("manual")
    store.async_update_room.assert_not_awaited()


class TestAreaAssignment:
    """The room entity lands in its room's area once (#238, #83)."""

    @staticmethod
    def _run(setup, *, area_id=None, options=None, area_exists=True, entry_exists=True):
        make, coordinator, _, _ = setup
        entity = make()
        entity.hass = coordinator.hass
        entry = MagicMock()
        entry.area_id = area_id
        entry.options = {DOMAIN: options} if options is not None else {}
        registry = MagicMock()
        registry.async_get.return_value = entry if entry_exists else None
        areas = MagicMock()
        areas.async_get_area.return_value = MagicMock() if area_exists else None
        with (
            patch("custom_components.roommind.climate.er.async_get", return_value=registry),
            patch("custom_components.roommind.climate.ar.async_get", return_value=areas),
        ):
            entity._assign_area_once()
        return registry

    def test_first_time_assigns_area_and_marks_it(self, setup):
        registry = self._run(setup)
        registry.async_update_entity.assert_called_once_with("climate.roommind_living_room", area_id="living_room")
        registry.async_update_entity_options.assert_called_once_with(
            "climate.roommind_living_room", DOMAIN, {"area_assigned": True}
        )

    def test_already_marked_leaves_a_removed_area_alone(self, setup):
        registry = self._run(setup, options={"area_assigned": True})
        registry.async_update_entity.assert_not_called()
        registry.async_update_entity_options.assert_not_called()

    def test_area_chosen_by_the_user_stays(self, setup):
        registry = self._run(setup, area_id="kitchen")
        registry.async_update_entity.assert_not_called()
        registry.async_update_entity_options.assert_called_once()

    def test_missing_area_only_marks(self, setup):
        registry = self._run(setup, area_exists=False)
        registry.async_update_entity.assert_not_called()
        registry.async_update_entity_options.assert_called_once()

    def test_no_registry_entry_does_nothing(self, setup):
        registry = self._run(setup, entry_exists=False)
        registry.async_update_entity_options.assert_not_called()


@pytest.mark.asyncio
async def test_added_to_hass_assigns_the_area(setup):
    make, coordinator, *_ = setup
    entity = make()
    with (
        patch("homeassistant.helpers.update_coordinator.CoordinatorEntity.async_added_to_hass", new=AsyncMock()),
        patch.object(RoomMindRoomClimate, "_assign_area_once") as assign,
    ):
        await entity.async_added_to_hass()
    assign.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("target", [21.0, 22.5, 17.5, 20.25])
async def test_fahrenheit_display_echo_is_a_no_op(setup, target):
    """A °F display shows whole degrees; echoing 72 °F for a 22.5 °C band is no new target."""
    make, coordinator, store, _ = setup
    coordinator.hass.config.units.temperature_unit = UnitOfTemperature.FAHRENHEIT
    entity = make(_room(climate_mode="heat_only"), _live(heat_target=target))
    shown = round(target * 9 / 5 + 32)

    await entity.async_set_temperature(temperature=(shown - 32) * 5 / 9)

    store.async_update_room.assert_not_called()


@pytest.mark.asyncio
async def test_fahrenheit_one_degree_step_is_a_new_target(setup):
    make, coordinator, store, _ = setup
    coordinator.hass.config.units.temperature_unit = UnitOfTemperature.FAHRENHEIT
    entity = make(_room(climate_mode="heat_only"), _live(heat_target=22.5))

    await entity.async_set_temperature(temperature=(73 - 32) * 5 / 9)

    store.async_update_room.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(("want", "kept"), [(21.2, True), (21.25, False), (20.75, False), (21.24, True)])
async def test_celsius_echo_tolerance_is_half_a_step(setup, want, kept):
    make, _, store, _ = setup
    entity = make(_room(climate_mode="heat_only"), _live(heat_target=21.0))

    await entity.async_set_temperature(temperature=want)

    assert store.async_update_room.called is not kept
