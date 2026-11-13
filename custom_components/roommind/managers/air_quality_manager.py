"""Room air quality from CO2/VOC sensors, and the ventilation RoomMind runs for it (#267).

Air counts as bad from the threshold on and good again below ``AIR_QUALITY_CLEAR_FACTOR`` of it.
A ventilation entity (fan, switch, input_boolean) is switched on when the air turns bad while it
is off, and off again once no room wants it any more and its minimum run is over. RoomMind only
switches off what it switched on itself: a unit that was already running, or that someone
switched off meanwhile, is left alone.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from ..const import (
    AIR_QUALITY_CLEAR_FACTOR,
    MAX_SENSOR_STALENESS,
    VENTILATION_MIN_RUN_MINUTES,
    make_roommind_context,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

VENTILATION_MIN_RUN_S = VENTILATION_MIN_RUN_MINUTES * 60
# A unit may take a moment to report "on" after the command; only then does "off" mean someone switched it off
VENTILATION_REPORT_GRACE_S = 60


def next_air_bad(previous: bool, value: float | None, threshold: float | None) -> bool:
    """Hysteresis: bad from the threshold on, good below AIR_QUALITY_CLEAR_FACTOR of it."""
    if threshold is None or threshold <= 0:
        return False
    if value is None:
        return previous
    if value >= threshold:
        return True
    if value < threshold * AIR_QUALITY_CLEAR_FACTOR:
        return False
    return previous


class AirQualityTracker:
    """Per room and sensor kind: is the air bad, with hysteresis across cycles.

    A sensor without a reading keeps its last judgement for MAX_SENSOR_STALENESS, then counts as good.
    """

    def __init__(self) -> None:
        self._bad: dict[tuple[str, str], bool] = {}
        self._seen: dict[tuple[str, str], float] = {}

    def evaluate(self, area_id: str, kind: str, value: float | None, threshold: float | None, now: float) -> bool:
        key = (area_id, kind)
        if value is not None:
            self._seen[key] = now
        elif now - self._seen.get(key, -math.inf) > MAX_SENSOR_STALENESS:
            self._bad.pop(key, None)
            return False
        bad = next_air_bad(self._bad.get(key, False), value, threshold)
        self._bad[key] = bad
        return bad

    def remove_room(self, area_id: str) -> None:
        for store in (self._bad, self._seen):
            for key in [k for k in store if k[0] == area_id]:
                del store[key]


class VentilationController:
    """Switches ventilation entities on for bad air and off once nobody needs them.

    Ownership (entity -> time RoomMind switched it on) is persisted, so a restart still
    switches off what RoomMind switched on before it.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._owned: dict[str, float] = {}
        # Switched off by someone during a bad spell: not switched on again until the air was good
        self._declined: set[str] = set()
        self.dirty = False

    def load_state(self, data: dict) -> None:
        self._owned = {str(k): float(v) for k, v in (data or {}).items() if isinstance(v, int | float)}

    def get_state(self) -> dict[str, float]:
        return dict(self._owned)

    def is_running(self, entity_id: str) -> bool:
        return entity_id in self._owned

    async def async_reconcile(self, wanted: dict[str, bool], now: float) -> None:
        """Bring every ventilation entity in line with what the rooms want.

        ``wanted`` has an entry for every entity a room under control uses (True: some room
        needs fresh air). An owned entity missing there (room deleted, entity removed from the
        room, climate control off) goes off at once.
        """
        for entity_id, want in wanted.items():
            await self._async_reconcile_one(entity_id, want, now)
        for entity_id in [e for e in self._owned if e not in wanted]:
            state = self.hass.states.get(entity_id)
            if state is None or state.state != "on":
                self._release(entity_id)
            elif await self._async_switch(entity_id, False):
                self._release(entity_id)
        self._declined &= set(wanted)

    async def _async_reconcile_one(self, entity_id: str, want: bool, now: float) -> None:
        if not want:
            self._declined.discard(entity_id)
        state = self.hass.states.get(entity_id)
        if state is None or state.state not in ("on", "off"):
            return
        since = self._owned.get(entity_id)
        if since is not None:
            if state.state == "off":
                if now - since >= VENTILATION_REPORT_GRACE_S:
                    # Switched off by someone: stays off for this bad spell
                    self._release(entity_id)
                    if want:
                        self._declined.add(entity_id)
                return
            if not want and now - since >= VENTILATION_MIN_RUN_S and await self._async_switch(entity_id, False):
                self._release(entity_id)
            return
        if want and state.state == "off" and entity_id not in self._declined:
            if await self._async_switch(entity_id, True):
                self._owned[entity_id] = now
                self.dirty = True

    def _release(self, entity_id: str) -> None:
        if self._owned.pop(entity_id, None) is not None:
            self.dirty = True

    async def _async_switch(self, entity_id: str, on: bool) -> bool:
        domain = entity_id.split(".", 1)[0]
        try:
            await self.hass.services.async_call(
                domain,
                "turn_on" if on else "turn_off",
                {"entity_id": entity_id},
                blocking=True,
                context=make_roommind_context(),
            )
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Ventilation '%s': switching %s failed", entity_id, "on" if on else "off", exc_info=True)
            return False
        return True
