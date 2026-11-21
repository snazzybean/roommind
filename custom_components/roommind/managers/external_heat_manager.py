"""Unmanaged heat sources: stoves and fireplaces RoomMind does not control (#9).

Such a source still heats the room. While it burns, and for a cooldown after it goes out,
the room is paused like for an open window, and the thermal model does not learn: the rise
would otherwise be blamed on solar gain, occupancy or a lower heat loss.

Each configured entity votes on, off or "cannot tell": a temperature sensor next to the
source (compared with the room, with hysteresis), a power sensor (watt threshold) or an
on/off entity. One entity on is enough. An entity that cannot tell (unavailable, unknown,
no room temperature for a comparison) keeps its last vote for ``MAX_SENSOR_STALENESS``, as
a window sensor does, then counts as off: a dropout does not end the pause at once, a dead
sensor does not hold the room forever. An entity never read counts as off, so the room
heats normally until the source is seen burning.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from homeassistant.const import UnitOfPower, UnitOfTemperature

from ..const import (
    DEFAULT_EXTERNAL_HEAT_COOLDOWN,
    DEFAULT_EXTERNAL_HEAT_DELTA_OFF,
    DEFAULT_EXTERNAL_HEAT_DELTA_ON,
    DEFAULT_EXTERNAL_HEAT_POWER_THRESHOLD,
    MAX_SENSOR_STALENESS,
)

_LOGGER = logging.getLogger(__name__)

_UNAVAILABLE_STATES = (None, "unavailable", "unknown")
_ON_OFF_DOMAINS = ("binary_sensor", "switch", "input_boolean")
_POWER_UNIT_TO_WATTS = {UnitOfPower.WATT: 1.0, UnitOfPower.KILO_WATT: 1000.0}


@dataclass(frozen=True)
class ExternalHeatThresholds:
    """Per-room thresholds that decide when an unmanaged heat source counts as on.

    Kept as one value so the coordinator reads the room config once per cycle and the
    manager stays free of config lookups.

    Attributes:
        delta_on: degrees C a temperature sensor next to the source must exceed the room
            temperature by to switch the source on.
        delta_off: degrees C below which an active source counts as off again; lower than
            ``delta_on`` for hysteresis (the save validation enforces it).
        power_threshold: watts above which a power sensor counts as on.
        cooldown_minutes: minutes the room stays paused after the source goes off; 0
            releases the room at once.
    """

    delta_on: float
    delta_off: float
    power_threshold: float
    cooldown_minutes: int

    @classmethod
    def from_room(cls, room: dict) -> ExternalHeatThresholds:
        """Build the thresholds from a room config, with the defaults for missing keys.

        Args:
            room: the stored room config; rooms saved before this feature have none of the keys.
        """
        return cls(
            delta_on=float(room.get("external_heat_delta_on", DEFAULT_EXTERNAL_HEAT_DELTA_ON)),
            delta_off=float(room.get("external_heat_delta_off", DEFAULT_EXTERNAL_HEAT_DELTA_OFF)),
            power_threshold=float(room.get("external_heat_power_threshold", DEFAULT_EXTERNAL_HEAT_POWER_THRESHOLD)),
            cooldown_minutes=int(room.get("external_heat_cooldown", DEFAULT_EXTERNAL_HEAT_COOLDOWN)),
        )


class ExternalHeatManager:
    """Tracks per room whether an unmanaged heat source is burning or cooling down."""

    def __init__(self) -> None:
        self._source_on: dict[str, bool] = {}
        self._off_since: dict[str, float] = {}
        self._cooldown_seconds: dict[str, float] = {}
        # Per room and entity: last definite vote, and since when the entity cannot tell
        self._last_vote: dict[str, dict[str, bool]] = {}
        self._unreadable_since: dict[str, dict[str, float]] = {}
        self._warned: set[tuple[str, str]] = set()

    def is_active(self, area_id: str) -> bool:
        """Return True while the source burns or the room is in its cooldown.

        Args:
            area_id: the room.
        """
        if self._source_on.get(area_id, False):
            return True
        off_since = self._off_since.get(area_id)
        if off_since is None:
            return False
        return time.time() - off_since < self._cooldown_seconds.get(area_id, 0.0)

    def active_until(self, area_id: str) -> float | None:
        """Return the epoch time the cooldown ends, None while burning or inactive.

        Args:
            area_id: the room.
        """
        off_since = self._off_since.get(area_id)
        if off_since is None or not self.is_active(area_id) or self._source_on.get(area_id, False):
            return None
        return off_since + self._cooldown_seconds.get(area_id, 0.0)

    def update(
        self,
        area_id: str,
        source_states: dict[str, Any],
        room_temp: float | None,
        thresholds: ExternalHeatThresholds,
    ) -> bool:
        """Read the source entities, advance the state machine and return whether the room is paused.

        Args:
            area_id: the room.
            source_states: Home Assistant state objects of the configured entities, keyed by
                entity id; None for an entity without a state object.
            room_temp: the room temperature in degrees C; None when unknown, the temperature
                sensors then cannot tell this cycle.
            thresholds: the room's thresholds.
        """
        now = time.time()
        was_on = self._source_on.get(area_id, False)
        last = self._last_vote.setdefault(area_id, {})
        since = self._unreadable_since.setdefault(area_id, {})
        for gone in (set(last) | set(since)) - set(source_states):
            last.pop(gone, None)
            since.pop(gone, None)

        source_on = False
        for entity_id, state in source_states.items():
            vote = self._vote(area_id, entity_id, state, room_temp, thresholds, was_on)
            if vote is not None:
                last[entity_id] = vote
                since.pop(entity_id, None)
            elif now - since.setdefault(entity_id, now) >= MAX_SENSOR_STALENESS:
                if last.pop(entity_id, None):
                    _LOGGER.warning(
                        "Heat source sensor %s (room %s) unreadable for over %ds, treating the source as out",
                        entity_id,
                        area_id,
                        MAX_SENSOR_STALENESS,
                    )
            source_on = source_on or last.get(entity_id, False)

        if source_on != was_on:
            _LOGGER.debug("Room '%s': unmanaged heat source %s", area_id, "lit" if source_on else "out")
        self._source_on[area_id] = source_on
        self._cooldown_seconds[area_id] = thresholds.cooldown_minutes * 60.0
        if source_on:
            self._off_since.pop(area_id, None)
        elif was_on:
            self._off_since[area_id] = now

        active = self.is_active(area_id)
        if not active:
            self._off_since.pop(area_id, None)
        return active

    def remove_room(self, area_id: str) -> None:
        """Forget all state of a removed room.

        Args:
            area_id: the room.
        """
        self._source_on.pop(area_id, None)
        self._off_since.pop(area_id, None)
        self._cooldown_seconds.pop(area_id, None)
        self._last_vote.pop(area_id, None)
        self._unreadable_since.pop(area_id, None)
        self._warned = {key for key in self._warned if key[0] != area_id}

    def _vote(
        self,
        area_id: str,
        entity_id: str,
        state: Any,
        room_temp: float | None,
        thresholds: ExternalHeatThresholds,
        was_on: bool,
    ) -> bool | None:
        """Return what one entity says about the source: on, off, or None when it cannot tell.

        Args:
            area_id: the room, for the one-time warning about an unusable entity.
            entity_id: the entity; its domain picks the on/off reading.
            state: its Home Assistant state object, or None.
            room_temp: the room temperature in degrees C, or None.
            thresholds: the room's thresholds.
            was_on: whether the source was on last cycle; picks the hysteresis side.
        """
        if state is None or state.state in _UNAVAILABLE_STATES:
            return None
        if entity_id.split(".", 1)[0] in _ON_OFF_DOMAINS:
            return bool(state.state == "on")

        unit = state.attributes.get("unit_of_measurement")
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return None

        is_temperature = unit in (UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT) or (
            unit is None and state.attributes.get("device_class") == "temperature"
        )
        if is_temperature:
            if room_temp is None:
                return None
            source_temp = (value - 32.0) * 5.0 / 9.0 if unit == UnitOfTemperature.FAHRENHEIT else value
            delta = source_temp - room_temp
            return delta > thresholds.delta_off if was_on else delta >= thresholds.delta_on

        if unit in _POWER_UNIT_TO_WATTS:
            return value * _POWER_UNIT_TO_WATTS[unit] > thresholds.power_threshold

        if (area_id, entity_id) not in self._warned:
            self._warned.add((area_id, entity_id))
            _LOGGER.warning(
                "Heat source sensor %s is neither on/off, temperature nor power (unit %s): ignored",
                entity_id,
                unit,
            )
        return None
