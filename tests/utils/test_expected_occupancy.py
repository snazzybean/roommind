"""Tests for the expected occupancy input of the target logic."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from unittest.mock import MagicMock

from homeassistant.core import State
from homeassistant.util import dt as dt_util

from custom_components.roommind.const import TargetTemps
from custom_components.roommind.utils.expected_occupancy import ExpectedOccupancy, check_expected_occupancy
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


# ---------------------------------------------------------------------------
# Window bounds and the check against the occupancy sensors
# ---------------------------------------------------------------------------

SENSOR = "binary_sensor.motion"
SENSOR_ROOM = {**ROOM, "occupancy_sensors": [SENSOR], "occupancy_eco_enabled": True, "occupancy_eco_delay": 15}


def _hass(state: str | None, changed_ts: float = 0.0):
    """A hass whose only occupancy sensor has ``state`` since ``changed_ts`` (None = missing)."""
    hass = MagicMock()
    sensor = State(SENSOR, state, last_changed=dt_util.utc_from_timestamp(changed_ts)) if state else None
    hass.states.get = lambda eid: sensor if eid == SENSOR else None
    return hass


class TestWindowBounds:
    def test_consecutive_slots_form_one_window(self):
        assert EVENING.window_bounds(_monday(19, 30)) == (_monday(18), _monday(22))

    def test_outside_the_window_there_is_none(self):
        assert EVENING.window_bounds(_monday(12)) is None
        assert EVENING.window_bounds(_monday(3)) is None

    def test_slot_bounds_follow_the_slot_width(self):
        half_hours = ExpectedOccupancy(probability=_evening_use, threshold=0.5, slot_minutes=30)
        assert half_hours.slot_bounds(_monday(19, 40)) == (_monday(19, 30), _monday(20))


class TestCheckExpectedOccupancy:
    def test_needs_occupancy_eco_with_sensors(self):
        room = {**SENSOR_ROOM, "occupancy_eco_enabled": False}
        checked, lifted = check_expected_occupancy(_hass("off"), room, EVENING, _monday(20), False)
        assert checked == EVENING
        assert lifted is False

    def test_empty_in_the_window_is_eco_until_the_window_ends(self):
        checked, _ = check_expected_occupancy(_hass("off", _monday(12)), SENSOR_ROOM, EVENING, _monday(18, 20), False)
        assert checked.vacant_until == _monday(22)

    def test_vacancy_delay_counts_from_the_window_start(self):
        # Empty since noon, but the window began 10 minutes ago: someone arriving late finds it warm
        checked, _ = check_expected_occupancy(_hass("off", _monday(12)), SENSOR_ROOM, EVENING, _monday(18, 10), False)
        assert checked.vacant_until is None

    def test_vacancy_delay_counts_from_the_last_change_inside_the_window(self):
        checked, _ = check_expected_occupancy(_hass("off", _monday(19)), SENSOR_ROOM, EVENING, _monday(19, 10), False)
        assert checked.vacant_until is None
        checked, _ = check_expected_occupancy(_hass("off", _monday(19)), SENSOR_ROOM, EVENING, _monday(19, 16), False)
        assert checked.vacant_until == _monday(22)

    def test_unavailable_sensor_never_counts_as_empty(self):
        checked, _ = check_expected_occupancy(
            _hass("unavailable", _monday(12)), SENSOR_ROOM, EVENING, _monday(20), False
        )
        assert checked.vacant_until is None

    def test_confirmed_occupancy_outside_the_window_lifts_to_comfort(self):
        checked, lifted = check_expected_occupancy(
            _hass("on", _monday(12)), SENSOR_ROOM, EVENING, _monday(12, 5), False
        )
        assert lifted is True
        assert checked.occupied_until == _monday(13, 5)

    def test_short_visit_does_not_lift(self):
        checked, lifted = check_expected_occupancy(
            _hass("on", _monday(12)), SENSOR_ROOM, EVENING, _monday(12, 4), False
        )
        assert lifted is False
        assert checked.occupied_until is None

    def test_lift_is_held_until_every_sensor_is_off_for_the_release_time(self):
        held, lifted = check_expected_occupancy(_hass("off", _monday(12)), SENSOR_ROOM, EVENING, _monday(12, 4), True)
        assert lifted is True
        assert held.occupied_at(_monday(12, 4))
        released, lifted = check_expected_occupancy(
            _hass("off", _monday(12)), SENSOR_ROOM, EVENING, _monday(12, 5), True
        )
        assert lifted is False
        assert released.occupied_until is None

    def test_unavailable_sensor_never_holds_comfort(self):
        checked, lifted = check_expected_occupancy(
            _hass("unavailable", _monday(12)), SENSOR_ROOM, EVENING, _monday(12, 1), True
        )
        assert lifted is False
        assert checked.occupied_until is None

    def test_inside_the_window_the_lift_ends(self):
        _, lifted = check_expected_occupancy(_hass("on", _monday(12)), SENSOR_ROOM, EVENING, _monday(19), True)
        assert lifted is False

    def test_unknown_instant_uses_plain_occupancy_eco_until_the_slot_ends(self):
        checked, lifted = check_expected_occupancy(
            _hass("off", _monday(1)), SENSOR_ROOM, EVENING, _monday(3, 20), False
        )
        assert checked.vacant_until == _monday(4)
        assert lifted is False


class TestScopedVacancyAndLift:
    def test_vacancy_caps_only_the_current_window(self):
        expected = replace(EVENING, vacant_until=_monday(22))
        resolver = make_target_resolver(None, ROOM, {}, expected_occupancy=expected)
        assert resolver(_monday(20)) == ECO
        # Tuesday's window is still pre-heated
        assert resolver(_monday(18) + 86400) == COMFORT

    def test_no_price_shift_while_vacant(self):
        signal = MagicMock()
        signal.direction_at.return_value = 1
        expected = replace(EVENING, vacant_until=_monday(22))
        resolver = make_target_resolver(
            None, {**ROOM, "price_shift": 1.0}, {}, price_signal=signal, expected_occupancy=expected
        )
        assert resolver(_monday(20)) == ECO

    def test_lift_gives_comfort_outside_the_window(self):
        expected = replace(EVENING, occupied_until=_monday(13))
        resolver = make_target_resolver(BLOCKS, ROOM, {}, expected_occupancy=expected)
        assert resolver(_monday(12, 30)) == COMFORT
        assert resolver(_monday(13, 30)) == ECO

    def test_presence_away_beats_the_lift(self):
        expected = replace(EVENING, occupied_until=_monday(13))
        assert _resolve(_monday(12), expected=expected, presence_away=True) == ECO


def test_comfort_hours_per_week_count_the_expected_slots():
    # 18:00-22:00 every day, unknown before 06:00: 4 hours a day
    assert EVENING.comfort_hours_per_week(_monday(12)) == 28.0
