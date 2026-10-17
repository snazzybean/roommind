"""Tests for the predictive learned-occupancy schedule (utils/learned_schedule)."""

from datetime import UTC, datetime

import pytest
from homeassistant.util import dt as dt_util

from custom_components.roommind.const import TargetTemps
from custom_components.roommind.utils.learned_schedule import (
    build_prior_matrix,
    make_learned_target_resolver,
    prior_at,
    resolve_prior_window,
)


@pytest.fixture(autouse=True)
def _utc_tz():
    """Pin HA local time to UTC so (day, slot) bucketing is deterministic."""
    orig = dt_util.DEFAULT_TIME_ZONE
    dt_util.set_default_time_zone(dt_util.UTC)
    yield
    dt_util.set_default_time_zone(orig)


def _ts(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=UTC).timestamp()


ROOM = {"comfort_heat": 21.0, "comfort_cool": 24.0, "eco_heat": 17.0, "eco_cool": 27.0}


# --- build_prior_matrix -------------------------------------------------------


def test_build_prior_matrix_extracts_area():
    resp = {
        "slot_minutes": 60,
        "areas": {
            "Soggiorno": {"area_id": "soggiorno", "slot_minutes": 60, "slots": {"0,8": 0.82, "6,20": 0.9}},
            "Cucina": {"area_id": "cucina", "slots": {"0,8": 0.1}},
        },
    }
    matrix, slot_minutes = build_prior_matrix(resp, "soggiorno")
    assert slot_minutes == 60
    assert matrix == {(0, 8): 0.82, (6, 20): 0.9}


@pytest.mark.parametrize("resp", [None, {}, {"areas": {}}, "nope", {"areas": {"x": {"area_id": "other"}}}])
def test_build_prior_matrix_unavailable_falls_back(resp):
    matrix, slot_minutes = build_prior_matrix(resp, "soggiorno")
    assert matrix is None
    assert slot_minutes == 60


def test_build_prior_matrix_skips_malformed_slots():
    resp = {"areas": {"a": {"area_id": "soggiorno", "slots": {"0,8": 0.5, "bad": 0.9, "1,x": 0.4}}}}
    matrix, _ = build_prior_matrix(resp, "soggiorno")
    assert matrix == {(0, 8): 0.5}


def test_build_prior_matrix_empty_slots_returns_none():
    resp = {"areas": {"a": {"area_id": "soggiorno", "slots": {}}}}
    matrix, _ = build_prior_matrix(resp, "soggiorno")
    assert matrix is None


def test_build_prior_matrix_prefers_raw_slots_over_combined():
    # ``slots`` is the combined prior (blended with the area's global prior in
    # logit space); the raw per-slot prior is the anticipatory signal we want.
    resp = {
        "areas": {
            "a": {
                "area_id": "soggiorno",
                "slots": {"0,8": 0.12},
                "slots_raw": {"0,8": 0.71},
            }
        }
    }
    matrix, _ = build_prior_matrix(resp, "soggiorno")
    assert matrix == {(0, 8): 0.71}


def test_build_prior_matrix_falls_back_to_combined_without_raw():
    # An Area Occupancy build that predates ``slots_raw`` still works.
    resp = {"areas": {"a": {"area_id": "soggiorno", "slots": {"0,8": 0.12}}}}
    matrix, _ = build_prior_matrix(resp, "soggiorno")
    assert matrix == {(0, 8): 0.12}


def test_build_prior_matrix_drops_never_observed_slots():
    # data_points == 0 marks a slot whose value is an area-level fallback, not
    # evidence — it must not be able to cross the comfort threshold.
    resp = {
        "areas": {
            "a": {
                "area_id": "soggiorno",
                "slots_raw": {"0,8": 0.71, "0,9": 0.66},
                "data_points": {"0,8": 4, "0,9": 0},
            }
        }
    }
    matrix, _ = build_prior_matrix(resp, "soggiorno")
    assert matrix == {(0, 8): 0.71}


def test_build_prior_matrix_all_slots_unobserved_returns_none():
    # A room that has learned nothing yet reverts to its manual schedule.
    resp = {
        "areas": {
            "a": {
                "area_id": "soggiorno",
                "slots_raw": {"0,8": 0.66, "0,9": 0.66},
                "data_points": {"0,8": 0, "0,9": 0},
            }
        }
    }
    matrix, _ = build_prior_matrix(resp, "soggiorno")
    assert matrix is None


# --- prior_at -----------------------------------------------------------------


def test_prior_at_maps_local_day_and_slot():
    # 2024-01-01 is a Monday (weekday 0); 08:00 → slot 8 at 60-min slots.
    matrix = {(0, 8): 0.77}
    assert prior_at(_ts(2024, 1, 1, 8), matrix, 60) == 0.77


def test_prior_at_future_timestamp_uses_future_slot():
    # The whole point: evaluating a *future* ts reads that slot's learned prior.
    matrix = {(0, 8): 0.2, (2, 18): 0.9}  # Monday 08:00 low, Wednesday 18:00 high
    assert prior_at(_ts(2024, 1, 3, 18), matrix, 60) == 0.9  # 2024-01-03 = Wednesday


def test_prior_at_missing_or_empty_returns_none():
    assert prior_at(_ts(2024, 1, 1, 8), {(0, 9): 0.5}, 60) is None
    assert prior_at(_ts(2024, 1, 1, 8), None, 60) is None


# --- resolve_prior_window -----------------------------------------------------


def test_resolve_prior_window_comfort_above_threshold():
    matrix = {(0, 8): 0.8}
    assert resolve_prior_window(_ts(2024, 1, 1, 8), matrix, 0.5, 60, 21, 24, 17, 27) == TargetTemps(21, 24)


def test_resolve_prior_window_eco_below_threshold():
    matrix = {(0, 8): 0.3}
    assert resolve_prior_window(_ts(2024, 1, 1, 8), matrix, 0.5, 60, 21, 24, 17, 27) == TargetTemps(17, 27)


def test_resolve_prior_window_off_action_below_threshold():
    matrix = {(0, 8): 0.3}
    assert resolve_prior_window(
        _ts(2024, 1, 1, 8), matrix, 0.5, 60, 21, 24, 17, 27, schedule_off_action="off"
    ) == TargetTemps(None, None)


def test_resolve_prior_window_no_data_is_eco():
    assert resolve_prior_window(_ts(2024, 1, 1, 8), {}, 0.5, 60, 21, 24, 17, 27) == TargetTemps(17, 27)


# --- make_learned_target_resolver (ladder + anticipation) ---------------------


def test_resolver_comfort_and_eco_by_prior():
    matrix = {(0, 8): 0.9, (0, 3): 0.1}
    resolver = make_learned_target_resolver(matrix, 0.5, 60, ROOM, {})
    assert resolver(_ts(2024, 1, 1, 8)) == TargetTemps(21.0, 24.0)  # occupied slot → comfort
    assert resolver(_ts(2024, 1, 1, 3)) == TargetTemps(17.0, 27.0)  # empty slot → eco


def test_resolver_anticipates_future_slot():
    # Now (03:00) is empty, but the 08:00 slot is habitually occupied: evaluating
    # the future timestep yields comfort, which is what lets the MPC pre-heat.
    matrix = {(0, 3): 0.1, (0, 8): 0.9}
    resolver = make_learned_target_resolver(matrix, 0.5, 60, ROOM, {})
    assert resolver(_ts(2024, 1, 1, 3)) == TargetTemps(17.0, 27.0)
    assert resolver(_ts(2024, 1, 1, 8)) == TargetTemps(21.0, 24.0)


def test_resolver_override_wins():
    room = {**ROOM, "override_heat": 30.0, "override_cool": 20.0}
    resolver = make_learned_target_resolver({(0, 8): 0.9}, 0.5, 60, room, {})
    assert resolver(_ts(2024, 1, 1, 8)) == TargetTemps(30.0, 20.0)


def test_resolver_presence_away_forces_eco():
    resolver = make_learned_target_resolver({(0, 8): 0.9}, 0.5, 60, ROOM, {}, presence_away=True)
    assert resolver(_ts(2024, 1, 1, 8)) == TargetTemps(17.0, 27.0)


def test_resolver_presence_away_off_action():
    resolver = make_learned_target_resolver(
        {(0, 8): 0.9}, 0.5, 60, ROOM, {"presence_away_action": "off"}, presence_away=True
    )
    assert resolver(_ts(2024, 1, 1, 8)) == TargetTemps(None, None)


def test_resolver_vacation_wins():
    resolver = make_learned_target_resolver(
        {(0, 8): 0.9},
        0.5,
        60,
        ROOM,
        {"vacation_until": _ts(2024, 1, 2, 0), "vacation_temp": 12.0},
    )
    result = resolver(_ts(2024, 1, 1, 8))
    assert result.heat == 12.0
    assert result.cool == max(12.0, 27.0)


def test_resolver_applies_mold_delta_to_heat():
    resolver = make_learned_target_resolver({(0, 8): 0.9}, 0.5, 60, ROOM, {}, mold_prevention_delta=2.0)
    assert resolver(_ts(2024, 1, 1, 8)) == TargetTemps(23.0, 24.0)


def test_resolver_off_action_forces_off_without_mold_delta():
    # Below threshold + schedule_off_action "off" → force off; the mold delta
    # tail is skipped when both targets are None.
    resolver = make_learned_target_resolver(
        {(0, 8): 0.1}, 0.5, 60, ROOM, {"schedule_off_action": "off"}, mold_prevention_delta=2.0
    )
    assert resolver(_ts(2024, 1, 1, 8)) == TargetTemps(None, None)
