"""Area Occupancy Detection as an occupancy source for the expected occupancy input.

Area Occupancy Detection (``area_occupancy``) learns, per area, the share of each
weekly time slot the area is occupied and publishes it through its
``get_time_priors`` service. A room that opts in takes its expected occupancy from
that prior instead of its schedule window (see ``expected_occupancy``).

Opt-in per room and off by default. Every failure is fail-safe: without the
integration, without the area, or without any observed slot the room has no
expected occupancy and follows its schedule unchanged.

Fields of one area in the response: ``area_id``, ``global_prior`` (share of the
week the area is occupied), ``slot_minutes``, ``slots_raw`` (the learned prior per
``"weekday,slot"`` key, weekday 0 = Monday) and ``data_points`` (observations
behind each slot). ``slots`` and ``slots_baseline`` are conditioned on the area's
current evidence and are not a forecast, so they are not read.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from homeassistant.util import dt as dt_util

from ..const import (
    AREA_OCCUPANCY_DOMAIN,
    AREA_OCCUPANCY_PRIORS_SERVICE,
    AREA_OCCUPANCY_PRIORS_TTL_SECONDS,
    AREA_OCCUPANCY_THRESHOLD_CAP,
    AREA_OCCUPANCY_THRESHOLD_FACTOR,
    AREA_OCCUPANCY_THRESHOLD_FLOOR,
)
from .expected_occupancy import ExpectedOccupancy

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

_DEFAULT_SLOT_MINUTES = 60


@dataclass(frozen=True)
class AreaPriors:
    """The learned occupancy of one Area Occupancy area.

    Attributes:
        slots: Learned prior (0..1) per (weekday, slot index), weekday 0 = Monday. Only
            observed slots are present; a missing slot is unknown.
        slot_minutes: Width of one slot in minutes.
        global_prior: Share (0..1) of the week the area is occupied, None if not reported.
    """

    slots: dict[tuple[int, int], float]
    slot_minutes: int = _DEFAULT_SLOT_MINUTES
    global_prior: float | None = None

    def probability_at(self, ts: float) -> float | None:
        """Learned prior of the slot containing ``ts`` in Home Assistant local time, None if unobserved.

        Local time, because Area Occupancy learns its (weekday, slot) priors in local time.

        Args:
            ts: Instant to look at, epoch seconds.
        """
        local = dt_util.as_local(datetime.fromtimestamp(ts, tz=UTC))
        slot = (local.hour * 60 + local.minute) // self.slot_minutes
        return self.slots.get((local.weekday(), slot))

    def automatic_threshold(self) -> float:
        """Comfort threshold relative to how much the room is used, for a room that sets none.

        A slot prior is the share of that slot the room is occupied, so a fixed threshold
        suits only rooms used for whole hours. AREA_OCCUPANCY_THRESHOLD_FACTOR times the
        room's overall share picks its habitual slots instead, between the floor and the
        cap (see const.py). The mean of the observed slots stands in for a missing
        ``global_prior``.
        """
        base = self.global_prior
        if base is None and self.slots:
            base = sum(self.slots.values()) / len(self.slots)
        return min(
            AREA_OCCUPANCY_THRESHOLD_CAP,
            max(AREA_OCCUPANCY_THRESHOLD_FLOOR, AREA_OCCUPANCY_THRESHOLD_FACTOR * (base or 0.0)),
        )


def parse_area_priors(response: Any, area_id: str) -> AreaPriors | None:
    """One area's learned priors from a ``get_time_priors`` response, None when unusable.

    Slots without observations (``data_points`` 0) are dropped: their value is an area-level
    fallback, not evidence, and in a room whose overall share is above the threshold it would
    read as comfort on its own. None when the response or the area is missing, when the area
    has no ``slots_raw`` (an Area Occupancy release without it) or when no slot is observed.

    Args:
        response: The service response, any type (it is checked here).
        area_id: Area Occupancy area to read.
    """
    if not isinstance(response, dict):
        return None
    default_minutes = _slot_minutes(response.get("slot_minutes"), _DEFAULT_SLOT_MINUTES)
    for area in (response.get("areas") or {}).values():
        if not isinstance(area, dict) or area.get("area_id") != area_id:
            continue
        raw = area.get("slots_raw")
        if not isinstance(raw, dict):
            return None
        observations = area.get("data_points")
        observations = observations if isinstance(observations, dict) else {}
        slots: dict[tuple[int, int], float] = {}
        for key, value in raw.items():
            if observations and not observations.get(key):
                continue
            try:
                day, slot = (int(part) for part in str(key).split(","))
                slots[(day, slot)] = min(1.0, max(0.0, float(value)))
            except (TypeError, ValueError):
                continue
        if not slots:
            return None
        return AreaPriors(
            slots=slots,
            slot_minutes=_slot_minutes(area.get("slot_minutes"), default_minutes),
            global_prior=_fraction(area.get("global_prior")),
        )
    return None


def area_ids(response: Any) -> list[str]:
    """Ids of the areas a ``get_time_priors`` response reports, for the panel's area picker.

    Args:
        response: The service response, any type (it is checked here).
    """
    if not isinstance(response, dict):
        return []
    areas = response.get("areas") or {}
    if not isinstance(areas, dict):
        return []
    return sorted(
        {area["area_id"] for area in areas.values() if isinstance(area, dict) and isinstance(area.get("area_id"), str)}
    )


def _slot_minutes(raw: Any, default: int) -> int:
    """A usable slot width in minutes (divides a day), else ``default``.

    Args:
        raw: Value from the response.
        default: Width to use when ``raw`` is not usable.
    """
    try:
        minutes = int(raw)
    except (TypeError, ValueError):
        return default
    return minutes if 0 < minutes <= 1440 and 1440 % minutes == 0 else default


def _fraction(raw: Any) -> float | None:
    """``raw`` as a share between 0 and 1, None when it is not a number.

    Args:
        raw: Value from the response.
    """
    try:
        return min(1.0, max(0.0, float(raw)))
    except (TypeError, ValueError):
        return None


class AreaOccupancySource:
    """Reads Area Occupancy's learned priors for the rooms that opted in.

    One cached service call serves every room for AREA_OCCUPANCY_PRIORS_TTL_SECONDS. A
    failed call keeps the last good response, so a restart of Area Occupancy does not
    drop the rooms to their schedule for a cycle; with the service gone the rooms go
    back to their schedule.

    Attributes:
        hass: Home Assistant instance the service is called on.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Create the source with an empty cache.

        Args:
            hass: Home Assistant instance the service is called on.
        """
        self.hass = hass
        self._response: Any = None
        self._fetched_at: float | None = None

    @staticmethod
    def enabled(room: dict) -> bool:
        """Whether the room opted into this source and names an area.

        Args:
            room: Stored room config.
        """
        return bool(room.get("use_learned_schedule")) and bool(room.get("learned_occupancy_area_id"))

    def available(self) -> bool:
        """Whether Area Occupancy's ``get_time_priors`` service is registered."""
        return bool(self.hass.services.has_service(AREA_OCCUPANCY_DOMAIN, AREA_OCCUPANCY_PRIORS_SERVICE))

    async def async_response(self) -> Any:
        """The ``get_time_priors`` response, cached; None without the service or a good response."""
        if not self.available():
            self._response = None
            self._fetched_at = None
            return None
        now = time.time()
        if self._fetched_at is not None and now - self._fetched_at < AREA_OCCUPANCY_PRIORS_TTL_SECONDS:
            return self._response
        self._fetched_at = now
        try:
            response = await self.hass.services.async_call(
                AREA_OCCUPANCY_DOMAIN,
                AREA_OCCUPANCY_PRIORS_SERVICE,
                {},
                blocking=True,
                return_response=True,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "%s.%s failed; rooms using it keep the last priors or follow their schedule (error=%r)",
                AREA_OCCUPANCY_DOMAIN,
                AREA_OCCUPANCY_PRIORS_SERVICE,
                err,
            )
            return self._response
        if isinstance(response, dict):
            self._response = response
        return self._response

    async def async_priors(self, room: dict) -> AreaPriors | None:
        """Learned priors of the room's area, None when the room did not opt in or they are unusable.

        Args:
            room: Stored room config.
        """
        if not self.enabled(room):
            return None
        return parse_area_priors(await self.async_response(), room["learned_occupancy_area_id"])

    @staticmethod
    def threshold(room: dict, priors: AreaPriors) -> float:
        """Threshold in force for the room: its own, else the automatic one.

        Args:
            room: Stored room config; ``learned_occupancy_threshold`` None means automatic.
            priors: The room's learned priors.
        """
        manual = room.get("learned_occupancy_threshold")
        return float(manual) if manual is not None else priors.automatic_threshold()

    async def async_expected_occupancy(self, room: dict) -> ExpectedOccupancy | None:
        """The room's expected occupancy from its learned priors.

        Args:
            room: Stored room config.

        Returns:
            None when the room follows its schedule (not opted in, or no usable priors).
        """
        priors = await self.async_priors(room)
        if priors is None:
            return None
        return ExpectedOccupancy(
            probability=priors.probability_at,
            threshold=self.threshold(room, priors),
            slot_minutes=priors.slot_minutes,
        )
