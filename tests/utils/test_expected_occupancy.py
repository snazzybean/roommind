"""Tests for the expected occupancy input of the target logic."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from homeassistant.util import dt as dt_util

from custom_components.roommind.const import TargetTemps
from custom_components.roommind.utils.expected_occupancy import ExpectedOccupancy
from custom_components.roommind.utils.schedule_utils import (
    expected_targets_at_time,
    make_target_resolver,
    resolve_targets_at_time,
)

ROOM = {"comfort_heat": 21.0, "comfort_cool": 24.0, "eco_heat": 17.0, "eco_cool": 27.0}
COMFORT = TargetTemps(heat=21.0, cool=24.0)
ECO = TargetTemps(heat=17.0, cool=27.0)
# Monday 08:00-10:00 is a schedule block at 19 degrees
BLOCKS = {"monday": [{"from": "08:00:00", "to": "10:00:00", "data": {"temperature": 19.0}}]}


def _monday(hour: int, minute: int = 0) -> float:
    """Epoch seconds of Monday 2025-01-06 at the given local time."""
    return datetime(2025, 1, 6, hour, minute, tzinfo=dt_util.DEFAULT_TIME_ZONE).timestamp()


def _evening_use(ts: float) -> float | None:
    """Probability of a room used from 18:00 to 22:00 local time, unknown before 06:00."""
    hour = dt_util.as_local(dt_util.utc_from_timestamp(ts)).hour
    if hour < 6:
        return None
    return 0.8 if 18 <= hour < 22 else 0.05


EVENING = ExpectedOccupancy(probability=_evening_use, threshold=0.5)


def _resolve(ts: float, expected: ExpectedOccupancy | None = EVENING, blocks: dict | None = BLOCKS, **kwargs):
    """resolve_targets_at_time for ROOM with no override and no vacation."""
    return resolve_targets_at_time(
        ts,
        blocks,
        None,
        None,
        None,
        None,
        None,
        21.0,
        24.0,
        17.0,
        27.0,
        expected_occupancy=expected,
        **kwargs,
    )


class TestExpectedAt:
    def test_at_or_above_the_threshold_is_expected(self):
        assert ExpectedOccupancy(lambda _ts: 0.5, threshold=0.5).expected_at(0) is True

    def test_below_the_threshold_is_not_expected(self):
        assert ExpectedOccupancy(lambda _ts: 0.49, threshold=0.5).expected_at(0) is False

    def test_unknown_probability_is_unknown(self):
        assert ExpectedOccupancy(lambda _ts: None, threshold=0.5).expected_at(0) is None


class TestExpectedTargetsAtTime:
    def test_expected_use_gives_comfort(self):
        assert expected_targets_at_time(_monday(19), EVENING, COMFORT, ECO, "eco", lambda: ECO) == COMFORT

    def test_no_expected_use_gives_eco(self):
        assert expected_targets_at_time(_monday(12), EVENING, COMFORT, ECO, "eco", lambda: COMFORT) == ECO

    def test_no_expected_use_turns_off_with_schedule_off_action_off(self):
        targets = expected_targets_at_time(_monday(12), EVENING, COMFORT, ECO, "off", lambda: COMFORT)
        assert targets == TargetTemps(heat=None, cool=None)

    def test_unknown_instant_is_left_to_the_schedule(self):
        schedule = TargetTemps(heat=19.5, cool=25.0)
        assert expected_targets_at_time(_monday(3), EVENING, COMFORT, ECO, "eco", lambda: schedule) == schedule


class TestResolveTargetsWithExpectedOccupancy:
    def test_expected_window_replaces_the_schedule_block(self):
        # 09:00 is inside the schedule block but outside the expected window
        assert _resolve(_monday(9)) == ECO
        # 19:00 is outside the schedule block but inside the expected window
        assert _resolve(_monday(19)) == COMFORT

    def test_without_expected_occupancy_the_schedule_is_unchanged(self):
        assert _resolve(_monday(9), expected=None) == TargetTemps(heat=19.0, cool=19.0)
        assert _resolve(_monday(19), expected=None) == ECO

    def test_unknown_instant_follows_the_schedule_block(self):
        night_block = {"monday": [{"from": "02:00:00", "to": "04:00:00", "data": {"temperature": 19.0}}]}
        assert _resolve(_monday(3), blocks=night_block) == TargetTemps(heat=19.0, cool=19.0)
        assert _resolve(_monday(5), blocks=night_block) == ECO

    def test_unknown_instant_without_schedule_is_comfort(self):
        assert _resolve(_monday(3), blocks=None) == COMFORT

    def test_override_wins(self):
        targets = resolve_targets_at_time(
            _monday(12), BLOCKS, None, 23.0, 25.0, None, None, 21.0, 24.0, 17.0, 27.0, expected_occupancy=EVENING
        )
        assert targets == TargetTemps(heat=23.0, cool=25.0)

    def test_vacation_wins(self):
        targets = resolve_targets_at_time(
            _monday(19), BLOCKS, None, None, None, _monday(23), 15.0, 21.0, 24.0, 17.0, 27.0, expected_occupancy=EVENING
        )
        assert targets == TargetTemps(heat=15.0, cool=27.0)

    def test_presence_away_wins(self):
        assert _resolve(_monday(19), presence_away=True) == ECO
        assert _resolve(_monday(19), presence_away=True, presence_away_action="off") == TargetTemps(None, None)

    def test_room_vacant_caps_the_expected_window(self):
        assert _resolve(_monday(19), room_vacant=True) == ECO


class TestResolverWithExpectedOccupancy:
    def test_horizon_pre_heats_for_the_expected_window(self):
        resolver = make_target_resolver(BLOCKS, ROOM, {}, expected_occupancy=EVENING)
        assert resolver(_monday(17)) == ECO
        assert resolver(_monday(18)) == COMFORT

    def test_mold_delta_and_cool_only_cap_still_apply(self):
        resolver = make_target_resolver(
            None, {**ROOM, "climate_mode": "cool_only"}, {}, mold_prevention_delta=1.0, expected_occupancy=EVENING
        )
        # heat 21 + 1 = 22 stays below cool 24; at eco 17 + 1 = 18 below 27
        assert resolver(_monday(19)) == TargetTemps(heat=22.0, cool=24.0)
        capped = make_target_resolver(
            None,
            {**ROOM, "climate_mode": "cool_only", "comfort_cool": 21.5},
            {},
            mold_prevention_delta=1.0,
            expected_occupancy=EVENING,
        )
        assert capped(_monday(19)) == TargetTemps(heat=21.5, cool=21.5)

    def test_price_shift_moves_the_expected_window(self):
        signal = MagicMock()
        signal.direction_at.return_value = 1
        resolver = make_target_resolver(
            None, {**ROOM, "price_shift": 1.0}, {}, price_signal=signal, expected_occupancy=EVENING
        )
        assert resolver(_monday(19)) == TargetTemps(heat=22.0, cool=23.0)
        assert resolver(_monday(12)) == TargetTemps(heat=18.0, cool=26.0)
