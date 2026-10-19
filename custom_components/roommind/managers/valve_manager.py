"""Valve protection (anti-seize) manager for RoomMind."""

from __future__ import annotations

import logging
import time

from homeassistant.core import HomeAssistant

from ..const import (
    DEFAULT_COMFORT_HEAT,
    DEFAULT_VALVE_PROTECTION_INTERVAL,
    HEATING_BOOST_TARGET,
    VALVE_PROTECTION_CHECK_CYCLES,
    VALVE_PROTECTION_CYCLE_DURATION,
    TargetTemps,
    make_roommind_context,
)
from ..control.mpc_controller import async_idle_device, async_turn_off_climate, resolve_hvac_mode
from ..utils.device_utils import build_rooms_devices_map, get_trv_eids
from ..utils.temp_utils import celsius_to_ha_temp

_LOGGER = logging.getLogger(__name__)


class ValveManager:
    """Manages valve protection cycling for TRV anti-seize."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._cycling: dict[str, float] = {}
        self._last_actuation: dict[str, float] = {}
        self._actuation_dirty: bool = False
        self._check_count: int = 0

    def should_run_cycle_check(self) -> bool:
        """Increment throttle counter and return True if cycle check is due."""
        self._check_count += 1
        if self._check_count >= VALVE_PROTECTION_CHECK_CYCLES:
            self._check_count = 0
            return True
        return False

    def is_entity_cycling(self, entity_id: str) -> bool:
        """Check if a specific entity is currently being valve-cycled."""
        return entity_id in self._cycling

    @property
    def cycling_eids(self) -> set[str]:
        """Return set of entity IDs currently being cycled."""
        return set(self._cycling)

    @property
    def actuation_dirty(self) -> bool:
        return self._actuation_dirty

    @actuation_dirty.setter
    def actuation_dirty(self, value: bool) -> None:
        self._actuation_dirty = value

    def load_actuation_data(self, data: dict) -> None:
        """Load persisted valve actuation timestamps."""
        self._last_actuation = dict(data)

    def get_actuation_data(self) -> dict:
        """Return actuation timestamps for persistence."""
        return dict(self._last_actuation)

    def record_heating(self, thermostat_eids: list[str]) -> None:
        """Record that thermostats are actively heating (updates actuation timestamps)."""
        now_ts = time.time()
        for eid in thermostat_eids:
            self._last_actuation[eid] = now_ts
        self._actuation_dirty = True

    async def _async_close_valve(
        self,
        eid: str,
        rooms_devices: dict[str, list[dict]] | None,
        log_context: str,
    ) -> None:
        """Close a valve respecting the device's idle_action when possible.

        When rooms_devices provides the device list for this entity, delegates
        to async_idle_device so idle_action="low" TRVs stay awake. Otherwise
        falls back to async_turn_off_climate for backward compatibility.
        """
        try:
            devices = rooms_devices.get(eid) if rooms_devices else None
            if devices is not None:
                # Synthetic fallback targets so idle_action="low" has a sensible
                # setpoint when the device reports a broken min_temp (=0). Without
                # this the LOW branch would be a no-op and the TRV would stay on
                # the valve-protection boost setpoint until the next coordinator
                # tick (see review of PR #271).
                fallback_targets = TargetTemps(heat=DEFAULT_COMFORT_HEAT, cool=None)
                await async_idle_device(
                    self.hass,
                    eid,
                    devices,
                    area_id="valve_protection",
                    targets=fallback_targets,
                )
            else:
                await async_turn_off_climate(self.hass, eid, area_id="valve_protection")
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Valve protection: failed to close '%s' %s", eid, log_context)

    async def async_finish_cycles(
        self,
        rooms_devices: dict[str, list[dict]] | None = None,
    ) -> None:
        """End valve protection cycles that have exceeded their duration.

        rooms_devices: optional {eid: devices[]} map. When provided, the
        device's configured idle_action is respected (so idle_action="low"
        TRVs stay awake after the cycle). If omitted, falls back to
        async_turn_off_climate for backward compatibility.
        """
        if not self._cycling:
            return
        now = time.time()
        finished = [eid for eid, start in self._cycling.items() if now - start >= VALVE_PROTECTION_CYCLE_DURATION]
        for eid in finished:
            await self._async_close_valve(eid, rooms_devices, log_context="after cycle")
            self._cycling.pop(eid, None)
            self._last_actuation[eid] = now
            self._actuation_dirty = True
            _LOGGER.info("Valve protection: cycle complete for '%s'", eid)

    async def async_check_and_cycle(self, rooms: dict, settings: dict) -> None:
        """Scan for TRV valves that have been idle too long and start cycling them."""
        if not settings.get("valve_protection_enabled", False):
            # Disabled -- close any active cycles before clearing
            rooms_devices = build_rooms_devices_map(rooms)
            for eid in list(self._cycling):
                await self._async_close_valve(eid, rooms_devices, log_context="on disable")
            self._cycling.clear()
            return

        interval_days = settings.get(
            "valve_protection_interval_days",
            DEFAULT_VALVE_PROTECTION_INTERVAL,
        )
        threshold = interval_days * 86400
        now = time.time()

        # Collect all configured TRV entity IDs, excluding entities marked
        # in *any* room (a boiler excluded in one room must not be cycled
        # even if it also appears in another room).
        all_trvs: set[str] = set()
        all_excluded: set[str] = set()
        for room in rooms.values():
            all_excluded.update(room.get("valve_protection_exclude", []))
            for eid in get_trv_eids(room.get("devices", [])):
                all_trvs.add(eid)
        all_trvs -= all_excluded

        # Start cycling stale valves
        for eid in all_trvs:
            if eid in self._cycling:
                continue
            last = self._last_actuation.get(eid, 0)
            if now - last >= threshold:
                try:
                    eid_state = self.hass.states.get(eid)
                    vp_modes = (eid_state.attributes.get("hvac_modes") or []) if eid_state else []
                    vp_resolved = resolve_hvac_mode("heat", vp_modes)
                    if vp_resolved is None:
                        _LOGGER.debug(
                            "Valve protection: '%s' supports neither 'heat' nor 'auto', skipping",
                            eid,
                        )
                        continue
                    await self.hass.services.async_call(
                        "climate",
                        "set_hvac_mode",
                        {"entity_id": eid, "hvac_mode": vp_resolved},
                        blocking=True,
                        context=make_roommind_context(),
                    )
                    boost_temp = celsius_to_ha_temp(self.hass, HEATING_BOOST_TARGET)
                    if eid_state:
                        dev_max = eid_state.attributes.get("max_temp")
                        if dev_max is not None and boost_temp > dev_max:
                            boost_temp = dev_max
                    is_range = eid_state and eid_state.attributes.get("target_temp_low") is not None
                    if is_range:
                        cur_high = eid_state.attributes.get("target_temp_high", boost_temp)
                        await self.hass.services.async_call(
                            "climate",
                            "set_temperature",
                            {
                                "entity_id": eid,
                                "target_temp_low": boost_temp,
                                "target_temp_high": max(boost_temp, cur_high),
                            },
                            blocking=True,
                            context=make_roommind_context(),
                        )
                    else:
                        await self.hass.services.async_call(
                            "climate",
                            "set_temperature",
                            {"entity_id": eid, "temperature": boost_temp},
                            blocking=True,
                            context=make_roommind_context(),
                        )
                    self._cycling[eid] = now
                    idle_days = int((now - last) / 86400) if last else 0
                    _LOGGER.info(
                        "Valve protection: cycling '%s' (idle for %d days)",
                        eid,
                        idle_days,
                    )
                except Exception:  # noqa: BLE001
                    _LOGGER.warning("Valve protection: failed to start cycle for '%s'", eid)

        # Cleanup stale entries (entities no longer configured)
        stale = [eid for eid in self._last_actuation if eid not in all_trvs]
        for eid in stale:
            del self._last_actuation[eid]
        if stale:
            self._actuation_dirty = True
