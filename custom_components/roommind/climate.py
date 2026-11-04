"""Climate platform for RoomMind."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, cast

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_NONE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, PRECISION_TENTHS, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.temperature import display_temp
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    CLIMATE_MODE_AUTO,
    CLIMATE_MODE_COOL_ONLY,
    CLIMATE_MODE_HEAT_ONLY,
    DEFAULT_COMFORT_COOL,
    DEFAULT_COMFORT_HEAT,
    DOMAIN,
    MAX_TARGET_TEMP,
    MIN_TARGET_TEMP,
    MODE_COOLING,
    MODE_HEATING,
    OVERRIDE_BOOST,
    OVERRIDE_CUSTOM,
    OVERRIDE_ECO,
    OVERRIDE_TURN_ON_REFRESH_DELAY_S,
    is_override_active,
)
from .control.mpc_controller import check_acs_can_heat
from .coordinator import RoomMindCoordinator, _get_area_name
from .deprecation import warn_deprecated_use
from .utils.area_utils import rooms_with_area
from .utils.device_utils import get_ac_eids, get_trv_eids
from .utils.schedule_utils import mask_override_band, next_schedule_change, override_preset_band

_CLIMATE_MODE_TO_HVAC = {
    CLIMATE_MODE_AUTO: HVACMode.HEAT_COOL,
    CLIMATE_MODE_HEAT_ONLY: HVACMode.HEAT,
    CLIMATE_MODE_COOL_ONLY: HVACMode.COOL,
}
_HVAC_TO_CLIMATE_MODE = {hvac: mode for mode, hvac in _CLIMATE_MODE_TO_HVAC.items()}
# A held temperature from the slider, a display or a voice assistant
PRESET_MANUAL = "manual"
_OVERRIDE_TO_PRESET: dict[str, str] = {
    OVERRIDE_BOOST: PRESET_COMFORT,
    OVERRIDE_ECO: PRESET_ECO,
    OVERRIDE_CUSTOM: PRESET_MANUAL,
}
_PRESET_TO_OVERRIDE: dict[str, str] = {PRESET_COMFORT: OVERRIDE_BOOST, PRESET_ECO: OVERRIDE_ECO}


def _create_room_climates(
    coordinator: RoomMindCoordinator,
    area_id: str,
) -> list[ClimateEntity]:
    """Create climate entities for a room."""
    return [RoomMindOverrideClimate(coordinator, area_id), RoomMindRoomClimate(coordinator, area_id)]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RoomMind climate entities from a config entry."""
    coordinator: RoomMindCoordinator = hass.data[DOMAIN][entry.entry_id]
    store = hass.data[DOMAIN]["store"]
    coordinator.async_add_climate_entities = async_add_entities
    rooms = rooms_with_area(hass, store.get_rooms())
    entities: list[ClimateEntity] = []
    for area_id in rooms:
        entities.extend(_create_room_climates(coordinator, area_id))
        coordinator._climate_entity_areas.add(area_id)
    if entities:
        async_add_entities(entities)


def _current_band(coordinator: RoomMindCoordinator, area_id: str, room: dict) -> tuple[float | None, float | None]:
    """Return the (heat, cool) band currently in force for this room.

    An active override wins. Otherwise it is the band the coordinator resolved
    last cycle (minus mold prevention, which is not part of the user's band).
    Falls back to the comfort band when no live targets exist yet or the room
    is forced off.
    """
    if is_override_active(room):
        return room.get("override_heat"), room.get("override_cool")
    live = ((coordinator.data or {}).get("rooms") or {}).get(area_id) or {}
    heat = live.get("heat_target")
    cool = live.get("cool_target")
    if heat is None and cool is None:
        return override_preset_band(room, OVERRIDE_BOOST)
    if heat is not None and live.get("mold_prevention_active"):
        heat -= live.get("mold_prevention_delta") or 0
    return heat, cool


def _band_from_temperature_call(
    kwargs: dict[str, Any],
    climate_mode: str,
    current_band: Callable[[], tuple[float | None, float | None]],
    room: dict,
) -> tuple[float | None, float | None] | None:
    """Turn the arguments of a set_temperature call into an override band, None without targets."""
    low = kwargs.get(ATTR_TARGET_TEMP_LOW)
    high = kwargs.get(ATTR_TARGET_TEMP_HIGH)
    single = kwargs.get(ATTR_TEMPERATURE)
    if low is not None or high is not None:
        # A half-specified range keeps the other side of what is already in
        # force instead of dropping it, so a follow-up call cannot open a
        # one-sided band in between (#447).
        cur_heat, cur_cool = current_band()
        heat = low if low is not None else cur_heat
        cool = high if high is not None else cur_cool
        if (low is None) != (high is None) and heat is not None and cool is not None and cool < heat:
            if high is None:
                cool = heat
            else:
                heat = cool
        return heat, cool
    if single is None:
        return None
    if climate_mode == "cool_only":
        return None, single
    if climate_mode == "heat_only":
        return single, None
    # Auto: a bare `temperature` (legacy/external automation) must NOT
    # collapse to a single point (that is the cycling bug). Derive a
    # dead-band identically to the store migration.
    return single, max(single, room.get("comfort_cool", DEFAULT_COMFORT_COOL))


def _fill_auto_band(heat: float | None, cool: float | None, room: dict) -> tuple[float | None, float | None]:
    """Give a one-sided band its missing side, the way a bare temperature widens in auto."""
    if heat is not None and cool is None:
        cool = max(heat, room.get("comfort_cool", DEFAULT_COMFORT_COOL))
    elif cool is not None and heat is None:
        heat = min(cool, room.get("comfort_heat", room.get("comfort_temp", DEFAULT_COMFORT_HEAT)))
    return heat, cool


class RoomMindOverrideClimate(CoordinatorEntity, ClimateEntity):
    """Climate entity for room override control."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:thermometer-alert"
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
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
        return _current_band(self.coordinator, self._area_id, self._room() or {})

    @property
    def supported_features(self) -> ClimateEntityFeature:
        base = ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF | ClimateEntityFeature.TARGET_TEMPERATURE
        if self._climate_mode() == "auto":
            # A single temperature stays accepted in auto and widens to a band (#471)
            return base | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        return base

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
    def native_target_temperature(self) -> float | None:
        mode = self._climate_mode()
        if mode == "auto" or not self._is_override_active():
            # None keeps the dual slider in the HA thermostat card
            return None
        room = self._room() or {}
        if mode == "cool_only":
            val = room.get("override_cool")
        else:
            val = room.get("override_heat")
        return float(val) if isinstance(val, (int, float)) else None

    @property
    def native_target_temperature_low(self) -> float | None:
        if not self._is_override_active():
            return None
        val = (self._room() or {}).get("override_heat")
        return float(val) if isinstance(val, (int, float)) else None

    @property
    def native_target_temperature_high(self) -> float | None:
        if not self._is_override_active():
            return None
        val = (self._room() or {}).get("override_cool")
        return float(val) if isinstance(val, (int, float)) else None

    @property
    def native_current_temperature(self) -> float | None:
        """Return the room's current temperature from coordinator data."""
        data = self.coordinator.data
        if not data:
            return None
        room_data = data.get("rooms", {}).get(self._area_id)
        if not room_data:
            return None
        val = room_data.get("current_temp")
        return float(val) if isinstance(val, (int, float)) else None

    # HA before 2026.11 reads the old names; a class providing both makes newer HA use native_*
    current_temperature = native_current_temperature
    target_temperature = native_target_temperature
    target_temperature_low = native_target_temperature_low
    target_temperature_high = native_target_temperature_high

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set override targets from range or single temperature."""
        warn_deprecated_use(self.entity_id, self._area_id)
        store = self.coordinator.hass.data[DOMAIN]["store"]
        band = _band_from_temperature_call(kwargs, self._climate_mode(), self._current_band, self._room() or {})
        if band is None:
            return
        heat, cool = band
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
        warn_deprecated_use(self.entity_id, self._area_id)
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
        elif self.coordinator.is_override_seed_pending(self._area_id):
            # A repeated turn_on on the fresh seed must not lift the masking early (#447);
            # the running timer refreshes once the grace period ends.
            return
        await self._request_refresh()


class RoomMindRoomClimate(CoordinatorEntity, ClimateEntity):
    """The room as one thermostat: mode, presets, target band and what RoomMind is doing (#238).

    Changing the target or picking a preset sets an override that holds until the
    active schedule's next change, like a thermostat's temporary hold.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:home-thermometer"
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_min_temp = MIN_TARGET_TEMP
    _attr_max_temp = MAX_TARGET_TEMP
    _attr_translation_key = "room"
    _attr_preset_modes = [PRESET_NONE, PRESET_COMFORT, PRESET_ECO, PRESET_MANUAL]

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator)
        self._area_id = area_id
        self._attr_unique_id = f"{DOMAIN}_{area_id}_climate"
        self.entity_id = f"climate.{DOMAIN}_{area_id}"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._assign_area_once()

    @callback
    def _assign_area_once(self) -> None:
        """Put the entity into its room's area the first time it appears (area cards, Assist).

        Marked in the entity's registry options, so an area the user removes or changes stays that way.
        """
        registry = er.async_get(self.hass)
        entry = registry.async_get(self.entity_id)
        if entry is None:
            return
        options = dict(entry.options.get(DOMAIN, {}))
        if options.get("area_assigned"):
            return
        if entry.area_id is None and ar.async_get(self.hass).async_get_area(self._area_id) is not None:
            registry.async_update_entity(self.entity_id, area_id=self._area_id)
        registry.async_update_entity_options(self.entity_id, DOMAIN, {**options, "area_assigned": True})

    def _store(self) -> Any:
        return self.coordinator.hass.data[DOMAIN]["store"]

    def _room(self) -> dict:
        room: dict | None = self._store().get_room(self._area_id)
        return room or {}

    def _live(self) -> dict:
        live: dict = ((self.coordinator.data or {}).get("rooms") or {}).get(self._area_id) or {}
        return live

    def _climate_mode(self) -> str:
        mode: str = self._room().get("climate_mode", CLIMATE_MODE_AUTO)
        return mode

    def _override_in_force(self) -> bool:
        return is_override_active(self._room()) and not self._live().get("override_suppressed", False)

    @property
    def name(self) -> str:
        return self._room().get("display_name") or _get_area_name(self.coordinator.hass, self._area_id)

    @property
    def supported_features(self) -> ClimateEntityFeature:
        if self._room().get("is_outdoor", False):
            return ClimateEntityFeature(0)
        base = (
            ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.PRESET_MODE
            | ClimateEntityFeature.TARGET_TEMPERATURE
        )
        if self._climate_mode() == CLIMATE_MODE_AUTO:
            # A single temperature stays accepted in auto (Assist only matches that feature) and widens to a band
            return base | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        return base

    @property
    def hvac_modes(self) -> list[HVACMode]:
        room = self._room()
        if room.get("is_outdoor", False):
            return [HVACMode.OFF]
        devices = room.get("devices", [])
        can_cool = bool(get_ac_eids(devices))
        can_heat = bool(get_trv_eids(devices)) or (can_cool and check_acs_can_heat(self.coordinator.hass, room))
        current = _CLIMATE_MODE_TO_HVAC.get(self._climate_mode(), HVACMode.HEAT_COOL)
        modes = [HVACMode.OFF]
        for hvac, available in (
            (HVACMode.HEAT, can_heat),
            (HVACMode.COOL, can_cool),
            (HVACMode.HEAT_COOL, can_heat and can_cool),
        ):
            if available or hvac == current:
                modes.append(hvac)
        return modes

    @property
    def hvac_mode(self) -> HVACMode:
        room = self._room()
        if room.get("is_outdoor", False) or not room.get("climate_control_enabled", True):
            return HVACMode.OFF
        return _CLIMATE_MODE_TO_HVAC.get(self._climate_mode(), HVACMode.HEAT_COOL)

    @property
    def hvac_action(self) -> HVACAction | None:
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        if not self._store().get_settings().get("climate_control_active", True):
            return HVACAction.OFF
        live = self._live()
        if not live:
            return None
        if live.get("force_off"):
            return HVACAction.OFF
        mode = live.get("mode")
        if mode == MODE_HEATING:
            return HVACAction.HEATING
        if mode == MODE_COOLING:
            return HVACAction.COOLING
        return HVACAction.IDLE

    @property
    def native_current_temperature(self) -> float | None:
        val = self._live().get("current_temp")
        return float(val) if isinstance(val, (int, float)) else None

    @property
    def current_humidity(self) -> float | None:
        val = self._live().get("current_humidity")
        return float(val) if isinstance(val, (int, float)) else None

    def _band(self) -> tuple[float | None, float | None]:
        """The band the room is held at, without mold prevention (not part of the user's band)."""
        room = self._room()
        if self._override_in_force():
            heat, cool = room.get("override_heat"), room.get("override_cool")
        else:
            live = self._live()
            heat, cool = live.get("heat_target"), live.get("cool_target")
            if heat is not None and live.get("mold_prevention_active"):
                heat -= live.get("mold_prevention_delta") or 0
        if self._climate_mode() == CLIMATE_MODE_AUTO:
            # The dual slider sends both sides, HA rejects a call with only one of them
            return _fill_auto_band(heat, cool, room)
        return heat, cool

    @property
    def native_target_temperature(self) -> float | None:
        mode = self._climate_mode()
        if mode == CLIMATE_MODE_AUTO:
            # None keeps the dual slider in the HA thermostat card
            return None
        heat, cool = self._band()
        val = cool if mode == CLIMATE_MODE_COOL_ONLY else heat
        return float(val) if isinstance(val, (int, float)) else None

    @property
    def native_target_temperature_low(self) -> float | None:
        heat, _ = self._band()
        return float(heat) if isinstance(heat, (int, float)) else None

    @property
    def native_target_temperature_high(self) -> float | None:
        _, cool = self._band()
        return float(cool) if isinstance(cool, (int, float)) else None

    # HA before 2026.11 reads the old names; a class providing both makes newer HA use native_*
    current_temperature = native_current_temperature
    target_temperature = native_target_temperature
    target_temperature_low = native_target_temperature_low
    target_temperature_high = native_target_temperature_high

    @property
    def preset_mode(self) -> str | None:
        if not self._override_in_force():
            return str(PRESET_NONE)
        return _OVERRIDE_TO_PRESET.get(self._room().get("override_type") or "")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        room = self._room()
        live = self._live()
        until = room.get("override_until") if self._override_in_force() else None
        vacation_until = self._store().get_settings().get("vacation_until")
        return {
            "override_until": dt_util.utc_from_timestamp(until).isoformat() if until else None,
            "window_open": bool(live.get("window_open", False)),
            "presence_away": bool(live.get("presence_away", False)),
            "occupancy_vacant": bool(live.get("occupancy_vacant", False)),
            "vacation": vacation_until is not None and time.time() < vacation_until,
        }

    async def _async_set_override(self, heat: float | None, cool: float | None, override_type: str) -> None:
        heat, cool = mask_override_band(heat, cool, self._climate_mode())
        await self._store().async_update_room(
            self._area_id,
            {
                "override_heat": heat,
                "override_cool": cool,
                "override_until": next_schedule_change(self.coordinator.hass, self._room()),
                "override_type": override_type,
            },
        )
        self.coordinator.clear_override_seed(self._area_id)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    def _already_in_force(self, kwargs: dict[str, Any]) -> bool:
        """True when every given target equals the band that applies now.

        A wall display mirrored from this entity echoes that band back. Without an
        override it must not become one (an override outranks presence and vacation),
        with one it must keep the override's preset and end time.
        """
        heat, cool = self._band()
        single_side = cool if self._climate_mode() == CLIMATE_MODE_COOL_ONLY else heat
        pairs = [
            (kwargs.get(ATTR_TARGET_TEMP_LOW), heat),
            (kwargs.get(ATTR_TARGET_TEMP_HIGH), cool),
            (kwargs.get(ATTR_TEMPERATURE), single_side),
        ]
        given = [(want, have) for want, have in pairs if want is not None]
        known = [(want, have) for want, have in given if have is not None]
        if not given or len(known) < len(given):
            return False
        unit, precision = UnitOfTemperature.CELSIUS, self.precision
        if unit == self.hass.config.units.temperature_unit:
            return all(abs(want - have) < self._attr_target_temperature_step / 2 for want, have in known)
        # Compared as shown: a °F display rounds to whole degrees, its echo is up to 0.28 K off
        tolerance = max(self._attr_target_temperature_step, precision) / 2

        def shown(value: float, digits: float) -> float:
            return cast(float, display_temp(self.hass, value, unit, digits))

        return all(abs(shown(want, PRECISION_TENTHS) - shown(have, precision)) < tolerance for want, have in known)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Hold the given target until the schedule changes next."""
        hvac_mode = kwargs.pop(ATTR_HVAC_MODE, None)
        if hvac_mode is not None:
            # HA passes it through unchecked here, unlike the set_hvac_mode service
            if hvac_mode not in self.hvac_modes:
                raise ServiceValidationError(f"{self.entity_id} does not support hvac_mode {hvac_mode}")
            await self.async_set_hvac_mode(hvac_mode)
        if self._already_in_force(kwargs):
            return
        room = self._room()
        band = _band_from_temperature_call(
            kwargs, self._climate_mode(), lambda: _current_band(self.coordinator, self._area_id, room), room
        )
        if band is not None:
            await self._async_set_override(*band, OVERRIDE_CUSTOM)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Comfort/eco hold until the next schedule change, manual holds the band in force, none returns to the schedule."""
        if preset_mode == PRESET_MANUAL:
            heat, cool = self._band()
            if self.preset_mode != PRESET_MANUAL and (heat is not None or cool is not None):
                await self._async_set_override(heat, cool, OVERRIDE_CUSTOM)
            return
        override_type = _PRESET_TO_OVERRIDE.get(preset_mode)
        if override_type is not None:
            await self._async_set_override(*override_preset_band(self._room(), override_type), override_type)
            return
        await self._store().async_update_room(
            self._area_id,
            {"override_heat": None, "override_cool": None, "override_until": None, "override_type": None},
        )
        self.coordinator.clear_override_seed(self._area_id)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Off switches the room's devices off and stops control; heat/cool/heat_cool pick the climate mode."""
        if self._room().get("is_outdoor", False):
            return
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.async_turn_room_off(self._area_id)
            self.async_write_ha_state()
            return
        changes: dict[str, Any] = {"climate_control_enabled": True}
        climate_mode = _HVAC_TO_CLIMATE_MODE.get(hvac_mode)
        if climate_mode is not None:
            changes["climate_mode"] = climate_mode
            room = self._room()
            if climate_mode != self._climate_mode() and is_override_active(room):
                # A held band keeps fitting the mode: heat_only drops the cool side, auto needs both again
                heat, cool = room.get("override_heat"), room.get("override_cool")
                if climate_mode == CLIMATE_MODE_AUTO:
                    heat, cool = _fill_auto_band(heat, cool, room)
                changes["override_heat"], changes["override_cool"] = mask_override_band(heat, cool, climate_mode)
        await self._store().async_update_room(self._area_id, changes)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(_CLIMATE_MODE_TO_HVAC.get(self._climate_mode(), HVACMode.HEAT_COOL))

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)
