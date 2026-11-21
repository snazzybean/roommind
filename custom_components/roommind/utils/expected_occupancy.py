"""Expected occupancy: a forecast of when a room is in use, as an input to the target logic.

A room's schedule says when it should be comfortable; an expected occupancy says when it
is likely to be used. A source (a learned occupancy model, for instance) hands the target
logic a probability per instant and the threshold at or above which that probability means
comfort. When a room has a source, the expected window takes the place of the schedule
window in ``schedule_utils.resolve_targets_at_time``; override, vacation, presence, price
shift, mold prevention and the cool-only cap work through the same path as for a schedule.

The input is kept free of any particular source, so several sources can plug into it.

The forecast is checked against the room's occupancy sensors (check_expected_occupancy):
an expected window the room stays empty in drops to eco until the window ends, and a room
used outside its expected window is lifted to comfort while it is in use.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from ..const import (
    DEFAULT_OCCUPANCY_ECO_DELAY_MINUTES,
    EXPECTED_OCCUPANCY_CONFIRM_MINUTES,
    EXPECTED_OCCUPANCY_RELEASE_MINUTES,
)
from .presence_utils import is_occupancy_held, is_room_occupied, is_room_vacant, occupancy_quiet_since

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


@dataclass(frozen=True)
class ExpectedOccupancy:
    """When a room is expected to be in use, as seen by the target logic.

    Attributes:
        probability: Probability (0..1) that the room is in use at an instant (epoch seconds);
            None where the source knows nothing about that instant, which leaves the decision
            to the room's schedule.
        threshold: Probability (0..1) at or above which the room is expected in use (comfort).
        slot_minutes: Time resolution of the source in minutes: ``probability`` is constant
            within slots of this width aligned to local midnight.
        vacant_until: The room stayed empty in its current expected window: eco up to this
            instant (the window end, epoch seconds), so later windows are still pre-heated.
            None when the room is not found empty.
        occupied_until: The room is in use outside its expected window: comfort up to this
            instant (epoch seconds), the horizon assuming the stay lasts one slot. None when
            nobody is confirmed in the room.
    """

    probability: Callable[[float], float | None]
    threshold: float
    slot_minutes: int = 60
    vacant_until: float | None = None
    occupied_until: float | None = None

    def expected_at(self, ts: float) -> bool | None:
        """Whether the room is expected in use at ``ts``; None when the source does not know.

        Args:
            ts: Instant to look at, epoch seconds.
        """
        probability = self.probability(ts)
        if probability is None:
            return None
        return probability >= self.threshold

    def vacant_at(self, ts: float) -> bool:
        """Whether the room counts as empty at ``ts`` (eco at most).

        Args:
            ts: Instant to look at, epoch seconds.
        """
        return self.vacant_until is not None and ts < self.vacant_until

    def occupied_at(self, ts: float) -> bool:
        """Whether the room counts as in use at ``ts`` whatever the forecast says (comfort).

        Args:
            ts: Instant to look at, epoch seconds.
        """
        return self.occupied_until is not None and ts < self.occupied_until

    def slot_bounds(self, ts: float) -> tuple[float, float]:
        """Start and end (epoch seconds) of the source's slot containing ``ts``, aligned to local midnight.

        Args:
            ts: Instant to look at, epoch seconds.
        """
        slot_minutes = self.slot_minutes or 60
        local = dt_util.as_local(datetime.fromtimestamp(ts, tz=UTC))
        into_slot = ((local.hour * 60 + local.minute) % slot_minutes) * 60 + local.second + local.microsecond / 1e6
        start = ts - into_slot
        return start, start + slot_minutes * 60

    def window_bounds(self, ts: float) -> tuple[float, float] | None:
        """Start and end (epoch seconds) of the expected window containing ``ts``, None outside one.

        The sensor check needs the window, not only the slot: the vacancy delay must not run
        before the window starts (someone arriving a few minutes late still finds the room
        warm), and an empty room drops to eco only until the window ends. Consecutive expected
        slots form one window, searched at most one week each way.

        Args:
            ts: Instant to look at, epoch seconds.
        """
        if not self.expected_at(ts):
            return None
        slot_minutes = self.slot_minutes or 60
        slot_seconds = slot_minutes * 60
        start, end = self.slot_bounds(ts)
        max_steps = 7 * 24 * 60 // slot_minutes
        for _ in range(max_steps):
            if not self.expected_at(start - slot_seconds / 2):
                break
            start -= slot_seconds
        for _ in range(max_steps):
            if not self.expected_at(end + slot_seconds / 2):
                break
            end += slot_seconds
        return start, end


def check_expected_occupancy(
    hass: HomeAssistant,
    room: dict,
    expected: ExpectedOccupancy,
    now: float,
    lifted: bool,
) -> tuple[ExpectedOccupancy, bool]:
    """Check the forecast against the room's occupancy sensors.

    The expected window is a forecast, the sensors tell whether it comes true. Inside the
    window a room that stays empty for the occupancy-eco delay, counted from the later of
    the last sensor change and the window start, drops to eco until the window ends; the
    next window is still pre-heated. Outside the window a sensor on for
    EXPECTED_OCCUPANCY_CONFIRM_MINUTES lifts the room to comfort, held until every sensor
    has been off for EXPECTED_OCCUPANCY_RELEASE_MINUTES. Where the source does not know
    the current instant, the schedule decides and plain occupancy eco applies until the
    end of the slot. An unavailable sensor never counts as empty and never holds comfort.
    Applies only with occupancy eco switched on and sensors assigned; otherwise the
    forecast acts alone.

    Args:
        hass: Home Assistant instance, read for the sensor states.
        room: Stored room config (occupancy sensors, occupancy eco switch and delay).
        expected: The room's expected occupancy from its source.
        now: Current time, epoch seconds.
        lifted: The room was lifted to comfort outside its window in the previous cycle.

    Returns:
        The expected occupancy with ``vacant_until`` / ``occupied_until`` set from the
        sensors, and whether the room is lifted to comfort now (to pass back as ``lifted``).
    """
    if not room.get("occupancy_eco_enabled", False) or not room.get("occupancy_sensors"):
        return expected, False
    slot_seconds = (expected.slot_minutes or 60) * 60
    if expected.expected_at(now) is None:
        if is_room_vacant(hass, room, now):
            return replace(expected, vacant_until=expected.slot_bounds(now)[1]), False
        return expected, False
    window = expected.window_bounds(now)
    if window is None:
        if is_room_occupied(hass, room, now, EXPECTED_OCCUPANCY_CONFIRM_MINUTES):
            lifted = True
        elif lifted and not is_occupancy_held(hass, room, now, EXPECTED_OCCUPANCY_RELEASE_MINUTES):
            lifted = False
        if lifted:
            return replace(expected, occupied_until=now + slot_seconds), True
        return expected, False
    # Inside the window the forecast already gives comfort; a lift starts afresh after it
    window_start, window_end = window
    quiet_since = occupancy_quiet_since(hass, room)
    delay_minutes = float(room.get("occupancy_eco_delay", DEFAULT_OCCUPANCY_ECO_DELAY_MINUTES))
    if quiet_since is not None and now - max(quiet_since, window_start) >= delay_minutes * 60:
        return replace(expected, vacant_until=window_end), False
    return expected, False
