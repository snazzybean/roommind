"""Away temperature: presence_away_action "away" with a room's away_heat/away_cool."""

from __future__ import annotations

import time

import pytest

from custom_components.roommind.utils.schedule_utils import (
    TargetTemps,
    away_target_temps,
    make_target_resolver,
    resolve_target_at_time,
    resolve_targets_at_time,
)

_BASE = {
    "schedule_blocks": None,
    "override_until": None,
    "override_heat": None,
    "override_cool": None,
    "vacation_until": None,
    "vacation_temp": None,
    "comfort_heat": 21.0,
    "comfort_cool": 24.0,
    "eco_heat": 18.0,
    "eco_cool": 27.0,
}


def test_away_target_temps_falls_back_to_eco_per_side():
    assert away_target_temps(16.0, None, 18.0, 27.0) == TargetTemps(heat=16.0, cool=27.0)
    assert away_target_temps(None, 29.0, 18.0, 27.0) == TargetTemps(heat=18.0, cool=29.0)
    assert away_target_temps(None, None, 18.0, 27.0) == TargetTemps(heat=18.0, cool=27.0)


def test_resolve_targets_uses_away_levels():
    result = resolve_targets_at_time(
        time.time(), **_BASE, presence_away=True, presence_away_action="away", away_heat=16.0, away_cool=29.0
    )
    assert result == TargetTemps(heat=16.0, cool=29.0)


def test_resolve_targets_away_without_levels_is_eco():
    result = resolve_targets_at_time(time.time(), **_BASE, presence_away=True, presence_away_action="away")
    assert result == TargetTemps(heat=18.0, cool=27.0)


@pytest.mark.parametrize("action", ["eco", "off"])
def test_away_levels_ignored_by_other_actions(action):
    result = resolve_targets_at_time(
        time.time(), **_BASE, presence_away=True, presence_away_action=action, away_heat=16.0, away_cool=29.0
    )
    expected = TargetTemps(heat=18.0, cool=27.0) if action == "eco" else TargetTemps(heat=None, cool=None)
    assert result == expected


def test_away_levels_only_when_nobody_home():
    result = resolve_targets_at_time(
        time.time(), **_BASE, presence_away=False, presence_away_action="away", away_heat=16.0, away_cool=29.0
    )
    assert result == TargetTemps(heat=21.0, cool=24.0)


def test_vacation_and_override_still_come_first():
    now = time.time()
    vacation = {**_BASE, "vacation_until": now + 3600, "vacation_temp": 15.0}
    result = resolve_targets_at_time(now, **vacation, presence_away=True, presence_away_action="away", away_heat=16.0)
    assert result.heat == 15.0
    override = {**_BASE, "override_heat": 23.0, "override_cool": 25.0}
    result = resolve_targets_at_time(now, **override, presence_away=True, presence_away_action="away", away_heat=16.0)
    assert result == TargetTemps(heat=23.0, cool=25.0)


def test_single_target_resolver_uses_away_temp():
    common = {
        "schedule_blocks": None,
        "override_until": None,
        "override_temp": None,
        "vacation_until": None,
        "vacation_temp": None,
        "comfort_temp": 21.0,
        "eco_temp": 18.0,
        "presence_away": True,
        "presence_away_action": "away",
    }
    assert resolve_target_at_time(time.time(), **common, away_temp=16.0) == 16.0
    assert resolve_target_at_time(time.time(), **common) == 18.0


def test_make_target_resolver_reads_room_away_levels():
    room = {"comfort_heat": 21.0, "eco_heat": 18.0, "away_heat": 16.0, "climate_mode": "heat_only"}
    resolver = make_target_resolver(None, room, {"presence_away_action": "away"}, presence_away=True)
    assert resolver(time.time()).heat == 16.0
