"""Expected occupancy: a forecast of when a room is in use, as an input to the target logic.

A room's schedule says when it should be comfortable; an expected occupancy says when it
is likely to be used. A source (a learned occupancy model, for instance) hands the target
logic a probability per instant and the threshold at or above which that probability means
comfort. When a room has a source, the expected window takes the place of the schedule
window in ``schedule_utils.resolve_targets_at_time``; override, vacation, presence, price
shift, mold prevention and the cool-only cap work through the same path as for a schedule.

The input is kept free of any particular source, so several sources can plug into it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


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
    """

    probability: Callable[[float], float | None]
    threshold: float
    slot_minutes: int = 60

    def expected_at(self, ts: float) -> bool | None:
        """Whether the room is expected in use at ``ts``; None when the source does not know.

        Args:
            ts: Instant to look at, epoch seconds.
        """
        probability = self.probability(ts)
        if probability is None:
            return None
        return probability >= self.threshold
