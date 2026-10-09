"""Climate platform for RoomMind."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.climate import (
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEFAULT_COMFORT_COOL,
    DOMAIN,
    MAX_TARGET_TEMP,
    MIN_TARGET_TEMP,
    OVERRIDE_BOOST,
    OVERRIDE_CUSTOM,
    OVERRIDE_TURN_ON_REFRESH_DELAY_S,
    is_override_active,
)
from .coordinator import RoomMindCoordinator
from .utils.schedule_utils import mask_override_band, override_preset_band


def _create_room_climates(
    coordinator: RoomMindCoordinator,
    area_id: str,
) -> list[ClimateEntity]:
    """Create climate entities for a room."""
    return [RoomMindOverrideClimate(coordinator, area_id)]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RoomMind climate entities from a config entry."""
    coordinator: RoomMindCoordinator = hass.data[DOMAIN][entry.entry_id]
    store = hass.data[DOMAIN]["store"]
    coordinator.async_add_climate_entities = async_add_entities
    rooms = store.get_rooms()
    entities: list[ClimateEntity] = []
    for area_id in rooms:
        entities.extend(_create_room_climates(coordinator, area_id))
        coordinator._climate_entity_areas.add(area_id)
    if entities:
        async_add_entities(entities)


class RoomMindOverrideClimate(CoordinatorEntity, ClimateEntity):
    """Climate entity for room override control."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:thermometer-alert"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_min_temp = MIN_TARGET_TEMP
    _attr_max_temp = MAX_TARGET_TEMP

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator)
        self._area_id = area_id
        self._attr_unique_id = f"{DOMAIN}_{area_id}_override"
        self._attr_name = f"{area_id} Override"
        self.entity_id = f"climate.{DOMAIN}_{area_id}_override"
        self._cancel_deferred_refresh: Callable[[], None] | None = None

    async def async_will_remove_from_hass(self) -> None:
        self._drop_deferred_refresh()
        await super().async_will_remove_from_hass()

    def _drop_deferred_refresh(self) -> None:
        if self._cancel_deferred_refresh is not None:
            self._cancel_deferred_refresh()
            self._cancel_deferred_refresh = None

    async def _refresh_after_deferral(self, _now: Any) -> None:
        self._cancel_deferred_refresh = None
        self.coordinator.clear_override_seed(self._area_id)
        await self.coordinator.async_request_refresh()

    async def _request_refresh(self) -> None:
        """Refresh now; the stored override holds the caller's values, not a seed."""
        self._drop_deferred_refresh()
        self.coordinator.clear_override_seed(self._area_id)
        await self.coordinator.async_request_refresh()

    def _room(self) -> dict | None:
        store = self.coordinator.hass.data[DOMAIN]["store"]
        room: dict | None = store.get_room(self._area_id)
        return room

    def _climate_mode(self) -> str:
        room = self._room()
        return room.get("climate_mode", "auto") if room else "auto"

    def _is_override_active(self) -> bool:
        room = self._room()
        if room is None:
            return False
        return is_override_active(room)

    def _current_band(self) -> tuple[float | None, float | None]:
        """Return the (heat, cool) band currently in force for this room.

        An active override wins. Otherwise it is the band the coordinator resolved
        last cycle (minus mold prevention, which is not part of the user's band).
        Falls back to the comfort band when no live targets exist yet or the room
        is forced off.
        """
        room = self._room() or {}
        if is_override_active(room):
            return room.get("override_heat"), room.get("override_cool")
        live = ((self.coordinator.data or {}).get("rooms") or {}).get(self._area_id) or {}
        heat = live.get("heat_target")
        cool = live.get("cool_target")
        if heat is None and cool is None:
            return override_preset_band(room, OVERRIDE_BOOST)
        if heat is not None and live.get("mold_prevention_active"):
            heat -= live.get("mold_prevention_delta") or 0
        return heat, cool

    @property
    def supported_features(self) -> ClimateEntityFeature:
        base = ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        if self._climate_mode() == "auto":
            return base | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        return base | ClimateEntityFeature.TARGET_TEMPERATURE

    @property
    def hvac_modes(self) -> list[HVACMode]:
        mode = self._climate_mode()
        if mode == "auto":
            return [HVACMode.OFF, HVACMode.HEAT_COOL]
        if mode == "cool_only":
            return [HVACMode.OFF, HVACMode.COOL]
        return [HVACMode.OFF, HVACMode.HEAT]

    @property
    def hvac_mode(self) -> HVACMode:
        if not self._is_override_active():
            return HVACMode.OFF
        mode = self._climate_mode()
        if mode == "auto":
            return HVACMode.HEAT_COOL
        if mode == "cool_only":
            return HVACMode.COOL
        return HVACMode.HEAT

    @property
    def target_temperature(self) -> float | None:
        if not self._is_override_active():
            return None
        room = self._room() or {}
        if self._climate_mode() == "cool_only":
            val = room.get("override_cool")
        else:
            val = room.get("override_heat")
        return float(val) if isinstance(val, (int, float)) else None

    @property
    def target_temperature_low(self) -> float | None:
        if not self._is_override_active():
            return None
        val = (self._room() or {}).get("override_heat")
        return float(val) if isinstance(val, (int, float)) else None

    @property
    def target_temperature_high(self) -> float | None:
        if not self._is_override_active():
            return None
        val = (self._room() or {}).get("override_cool")
        return float(val) if isinstance(val, (int, float)) else None

    @property
    def current_temperature(self) -> float | None:
        """Return the room's current temperature from coordinator data."""
        data = self.coordinator.data
        if not data:
            return None
        room_data = data.get("rooms", {}).get(self._area_id)
        if not room_data:
            return None
        val = room_data.get("current_temp")
        return float(val) if isinstance(val, (int, float)) else None

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set override targets from range or single temperature."""
        store = self.coordinator.hass.data[DOMAIN]["store"]
        mode = self._climate_mode()
        low = kwargs.get(ATTR_TARGET_TEMP_LOW)
        high = kwargs.get(ATTR_TARGET_TEMP_HIGH)
        single = kwargs.get(ATTR_TEMPERATURE)
        if low is not None or high is not None:
            # A half-specified range keeps the other side of what is already in
            # force instead of dropping it, so a follow-up call cannot open a
            # one-sided band in between (#447).
            cur_heat, cur_cool = self._current_band()
            heat = low if low is not None else cur_heat
            cool = high if high is not None else cur_cool
            if (low is None) != (high is None) and heat is not None and cool is not None and cool < heat:
                if high is None:
                    cool = heat
                else:
                    heat = cool
        elif single is not None:
            room = self._room() or {}
            if mode == "cool_only":
                heat, cool = None, single
            elif mode == "heat_only":
                heat, cool = single, None
            else:
                # Auto: a bare `temperature` (legacy/external automation) must NOT
                # collapse to a single point (that is the cycling bug). Derive a
                # dead-band identically to the store migration.
                heat = single
                cool = max(single, room.get("comfort_cool", DEFAULT_COMFORT_COOL))
        else:
            return
        await store.async_update_room(
            self._area_id,
            {
                "override_heat": heat,
                "override_cool": cool,
                "override_until": None,
                "override_type": OVERRIDE_CUSTOM,
            },
        )
        await self._request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode: OFF clears override, any other mode activates it."""
        store = self.coordinator.hass.data[DOMAIN]["store"]
        if hvac_mode == HVACMode.OFF:
            await store.async_update_room(
                self._area_id,
                {
                    "override_heat": None,
                    "override_cool": None,
                    "override_until": None,
                    "override_type": None,
                },
            )
        elif not self._is_override_active():
            heat, cool = mask_override_band(*self._current_band(), self._climate_mode())
            # Marked before the write so a coordinator tick can never see the seed unflagged.
            self.coordinator.note_override_seed(self._area_id)
            await store.async_update_room(
                self._area_id,
                {
                    "override_heat": heat,
                    "override_cool": cool,
                    "override_until": None,
                    "override_type": OVERRIDE_CUSTOM,
                },
            )
            # The seed only exists so the entity reads as on. Callers switch it on and
            # then send the real targets; evaluating the seed in between can start
            # the AC against the outdoor gate, which an override lifts (#447). The
            # follow-up set_temperature refreshes right away; a bare turn_on still
            # gets its refresh after the grace period.
            self.async_write_ha_state()
            self._drop_deferred_refresh()
            self._cancel_deferred_refresh = async_call_later(
                self.coordinator.hass, OVERRIDE_TURN_ON_REFRESH_DELAY_S, self._refresh_after_deferral
            )
            return
        await self._request_refresh()
