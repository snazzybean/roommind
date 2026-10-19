"""Central heating: switch a boiler on while enough rooms ask for heat.

A room demands heat while RoomMind heats it (its commanded mode), not while a
radiator valve happens to be open. The boiler starts once at least
``min_rooms`` rooms demand heat for ``start_delay_s`` and stops once fewer do
for ``stop_delay_s``. Both delays run on their own timer, not only on the
30 s cycle.

The target is a ``switch``/``input_boolean`` (turned on and off) or a
``climate`` entity: on sets the on temperature in heat mode, off sets the off
temperature and, with ``climate_off_mode`` "off", switches it off as well.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later

from ..const import (
    CENTRAL_HEATING_OFF_MODE_OFF,
    CENTRAL_HEATING_OFF_MODE_TEMPERATURE,
    MODE_HEATING,
    make_roommind_context,
)
from ..utils.device_utils import get_trv_eids

_LOGGER = logging.getLogger(__name__)

_SWITCH_DOMAINS = ("switch", "input_boolean")
_TEMP_TOLERANCE = 0.25


@dataclass(frozen=True)
class CentralHeatingConfig:
    """Central heating settings (``settings["central_heating"]``)."""

    entity_id: str
    min_rooms: int = 1
    start_delay_s: float = 0.0
    stop_delay_s: float = 0.0
    on_temperature: float | None = None
    off_temperature: float | None = None
    climate_off_mode: str = CENTRAL_HEATING_OFF_MODE_TEMPERATURE

    @property
    def domain(self) -> str:
        return self.entity_id.split(".", 1)[0]

    @classmethod
    def from_settings(cls, settings: dict) -> CentralHeatingConfig | None:
        """The configuration in force, None while switched off or without a target."""
        raw = settings.get("central_heating") or {}
        entity_id = raw.get("entity_id") or ""
        if not raw.get("enabled") or entity_id.split(".", 1)[0] not in (*_SWITCH_DOMAINS, "climate"):
            return None
        return cls(
            entity_id=entity_id,
            min_rooms=max(1, int(raw.get("min_rooms", 1))),
            start_delay_s=max(0.0, float(raw.get("start_delay_s", 0))),
            stop_delay_s=max(0.0, float(raw.get("stop_delay_s", 0))),
            on_temperature=raw.get("on_temperature"),
            off_temperature=raw.get("off_temperature"),
            climate_off_mode=raw.get("climate_off_mode", CENTRAL_HEATING_OFF_MODE_TEMPERATURE),
        )


def room_counts_for_central_heating(room: dict) -> bool:
    """A room's setting, by default every room with radiator thermostats (TRVs)."""
    if room.get("is_outdoor"):
        return False
    explicit = room.get("central_heating")
    if explicit is not None:
        return bool(explicit)
    return bool(get_trv_eids(room.get("devices", [])))


class CentralHeatingManager:
    """Switches the central heating target from the rooms' heat demand."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._config: CentralHeatingConfig | None = None
        # Commanded state: None until known (read from the entity on the first cycle)
        self._on: bool | None = None
        self._demand_since: float | None = None  # monotonic
        self._idle_since: float | None = None  # monotonic
        self._cancel_timer: Callable[[], None] | None = None
        self.demanding_rooms: list[str] = []

    # ─── State for entities and diagnostics ─────────────────────────

    def state(self) -> dict[str, Any]:
        config = self._config
        if config is None:
            return {"enabled": False}
        pending, remaining = self._pending()
        return {
            "enabled": True,
            "entity_id": config.entity_id,
            "on": bool(self._on),
            "demanding_rooms": list(self.demanding_rooms),
            "demanding_count": len(self.demanding_rooms),
            "min_rooms": config.min_rooms,
            "pending": pending,
            "pending_seconds": round(remaining) if remaining is not None else None,
        }

    def _pending(self) -> tuple[str | None, float | None]:
        config = self._config
        if config is None:
            return None, None
        now = time.monotonic()
        if not self._on and self._demand_since is not None:
            return "start", max(0.0, config.start_delay_s - (now - self._demand_since))
        if self._on and self._idle_since is not None:
            return "stop", max(0.0, config.stop_delay_s - (now - self._idle_since))
        return None, None

    # ─── Cycle ──────────────────────────────────────────────────────

    async def async_update(self, settings: dict, rooms: dict[str, dict], room_states: dict[str, dict]) -> None:
        """Count the rooms demanding heat and switch the target (once per coordinator cycle)."""
        config = CentralHeatingConfig.from_settings(settings)
        if config != self._config:
            self._cancel()
            if config is None or self._config is None or config.entity_id != self._config.entity_id:
                self._on = None  # another target: read its state again
            self._config = config
        if config is None:
            self.demanding_rooms = []
            self._demand_since = self._idle_since = None
            return
        if settings.get("climate_control_active", True):
            self.demanding_rooms = sorted(
                area_id
                for area_id, room in rooms.items()
                if room_counts_for_central_heating(room)
                and room.get("climate_control_enabled", True)
                and (room_states.get(area_id) or {}).get("commanded_mode") == MODE_HEATING
            )
        else:
            self.demanding_rooms = []
        demand = len(self.demanding_rooms) >= config.min_rooms
        now = time.monotonic()
        if demand:
            self._idle_since = None
            if self._demand_since is None:
                self._demand_since = now
        else:
            self._demand_since = None
            if self._idle_since is None:
                self._idle_since = now
        await self._async_apply()

    async def _async_apply(self) -> None:
        config = self._config
        if config is None:
            return
        state = self.hass.states.get(config.entity_id)
        if state is None or state.state in ("unavailable", "unknown"):
            return
        actual = self._entity_is_on(state, config)
        if self._on is None:
            # First cycle (start, reload, new target): take over what the target does
            self._on = actual
        now = time.monotonic()
        want = self._on
        if not self._on and self._demand_since is not None and now - self._demand_since >= config.start_delay_s:
            want = True
        elif self._on and self._idle_since is not None and now - self._idle_since >= config.stop_delay_s:
            want = False
        if want != self._on or want != actual:
            # A change, or the target was switched elsewhere: send what applies
            if await self._async_switch(config, want):
                if want != self._on:
                    _LOGGER.info(
                        "Central heating %s (%d of %d rooms demand heat: %s)",
                        "on" if want else "off",
                        len(self.demanding_rooms),
                        config.min_rooms,
                        ", ".join(self.demanding_rooms) or "none",
                    )
                self._on = want
        self._schedule_tick()

    def _schedule_tick(self) -> None:
        """Re-check exactly when a running delay ends, not only on the next cycle."""
        self._cancel()
        _, remaining = self._pending()
        if remaining is None:
            return
        self._cancel_timer = async_call_later(self.hass, remaining + 0.1, self._async_tick)

    async def _async_tick(self, _now: Any) -> None:
        self._cancel_timer = None
        await self._async_apply()

    @callback
    def _cancel(self) -> None:
        if self._cancel_timer is not None:
            self._cancel_timer()
            self._cancel_timer = None

    @callback
    def async_stop(self) -> None:
        self._cancel()

    # ─── Target ─────────────────────────────────────────────────────

    @staticmethod
    def _entity_is_on(state: Any, config: CentralHeatingConfig) -> bool:
        if config.domain in _SWITCH_DOMAINS:
            return bool(state.state == "on")
        if state.state == "off":
            return False
        if config.on_temperature is None:
            return True
        current = state.attributes.get("temperature")
        return isinstance(current, (int, float)) and abs(current - config.on_temperature) < _TEMP_TOLERANCE

    async def _async_switch(self, config: CentralHeatingConfig, on: bool) -> bool:
        """Send the on/off command; False when it failed (retried next cycle)."""
        try:
            for domain, service, data in self._commands(config, on):
                await self.hass.services.async_call(
                    domain,
                    service,
                    {"entity_id": config.entity_id, **data},
                    blocking=True,
                    context=make_roommind_context(),
                )
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Central heating: switching '%s' %s failed", config.entity_id, "on" if on else "off")
            return False
        return True

    @staticmethod
    def _commands(config: CentralHeatingConfig, on: bool) -> list[tuple[str, str, dict[str, Any]]]:
        if config.domain in _SWITCH_DOMAINS:
            return [(config.domain, "turn_on" if on else "turn_off", {})]
        if on:
            if config.on_temperature is None:
                return [("climate", "set_hvac_mode", {"hvac_mode": "heat"})]
            return [("climate", "set_temperature", {"temperature": config.on_temperature, "hvac_mode": "heat"})]
        commands: list[tuple[str, str, dict[str, Any]]] = []
        if config.off_temperature is not None:
            commands.append(("climate", "set_temperature", {"temperature": config.off_temperature}))
        if config.climate_off_mode == CENTRAL_HEATING_OFF_MODE_OFF or config.off_temperature is None:
            commands.append(("climate", "set_hvac_mode", {"hvac_mode": "off"}))
        return commands
