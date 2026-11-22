"""Away temperature: presence_away_action "away" with a room's away_heat/away_cool."""

from __future__ import annotations

import time

import pytest

from custom_components.roommind.utils.schedule_utils import (
    TargetTemps,
    away_target_temps,
    make_target_resolver,
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


def _comfort():
    return TargetTemps(heat=21.0, cool=24.0)


def test_away_target_temps_falls_back_to_eco_per_side():
    assert away_target_temps(16.0, None, 18.0, 27.0, _comfort) == TargetTemps(heat=16.0, cool=27.0)
    assert away_target_temps(None, 29.0, 18.0, 27.0, _comfort) == TargetTemps(heat=18.0, cool=29.0)


def test_away_target_temps_unset_does_not_read_the_schedule():
    def boom():
        raise AssertionError("schedule read although no away level is set")

    assert away_target_temps(None, None, 18.0, 27.0, boom) == TargetTemps(heat=18.0, cool=27.0)


def test_away_never_asks_for_more_than_the_schedule():
    """D480: away 19 °C during an 18 °C night block stays at 18; cooling likewise never lower."""
    night = lambda: TargetTemps(heat=18.0, cool=28.0)  # noqa: E731
    assert away_target_temps(19.0, 26.0, 17.0, 27.0, night) == TargetTemps(heat=18.0, cool=28.0)
    assert away_target_temps(16.0, 29.0, 17.0, 27.0, night) == TargetTemps(heat=16.0, cool=29.0)


def test_away_keeps_a_side_off_that_the_schedule_has_off():
    off = lambda: TargetTemps(heat=None, cool=None)  # noqa: E731
    assert away_target_temps(16.0, None, 17.0, 27.0, off) == TargetTemps(heat=None, cool=27.0)
    assert away_target_temps(None, 29.0, 17.0, 27.0, off) == TargetTemps(heat=17.0, cool=None)


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


def test_make_target_resolver_reads_room_away_levels():
    room = {"comfort_heat": 21.0, "eco_heat": 18.0, "away_heat": 16.0, "climate_mode": "heat_only"}
    resolver = make_target_resolver(None, room, {"presence_away_action": "away"}, presence_away=True)
    assert resolver(time.time()).heat == 16.0


def test_resolve_targets_caps_away_at_the_schedule_block():
    days = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    block = [{"from": "00:00:00", "to": "23:59:59", "data": {"heat_temperature": 18.0}}]
    base = {**_BASE, "schedule_blocks": {day: block for day in days}}
    result = resolve_targets_at_time(
        time.time(), **base, presence_away=True, presence_away_action="away", away_heat=19.0
    )
    assert result.heat == 18.0
    off = {**_BASE, "schedule_blocks": {}}
    result = resolve_targets_at_time(
        time.time(), **off, presence_away=True, presence_away_action="away", schedule_off_action="off", away_heat=16.0
    )
    assert result == TargetTemps(heat=None, cool=27.0)
