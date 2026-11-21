"""Mocked Area Occupancy Detection: the get_time_priors response a scenario declares."""

from __future__ import annotations

import pytest
from helpers import scenario

from roommind_sim.area_occupancy import build_time_priors
from roommind_sim.scenario import ScenarioError, load_scenario_dict

SPEC = {
    "areas": {
        "bad": {
            "global_prior": 0.05,
            "default": 0.02,
            "windows": [{"days": ["mon", "fri"], "from": "06:00", "to": "08:00", "prior": 0.4}],
            "unobserved": ["sun"],
        }
    }
}


def test_windows_overlay_the_default_in_slots_raw():
    area = build_time_priors(SPEC)["areas"]["sim_bad"]
    assert area["area_id"] == "bad"
    assert area["global_prior"] == 0.05
    assert area["slot_minutes"] == 60
    assert len(area["slots_raw"]) == 7 * 24
    assert area["slots_raw"]["0,6"] == 0.4
    assert area["slots_raw"]["0,7"] == 0.4
    assert area["slots_raw"]["0,8"] == 0.02
    assert area["slots_raw"]["4,6"] == 0.4
    assert area["slots_raw"]["1,6"] == 0.02


def test_unobserved_days_have_no_data_points():
    area = build_time_priors(SPEC)["areas"]["sim_bad"]
    assert area["data_points"]["6,10"] == 0
    assert area["data_points"]["0,10"] > 0


def test_evidence_conditioned_slots_do_not_carry_the_windows():
    """RoomMind must read slots_raw; slots only repeat the default, so a scenario shows a wrong read."""
    area = build_time_priors(SPEC)["areas"]["sim_bad"]
    assert set(area["slots"].values()) == {0.02}


def test_half_hour_slots():
    spec = {"slot_minutes": 30, "areas": {"bad": {"windows": [{"from": "06:30", "to": "07:00", "prior": 0.5}]}}}
    area = build_time_priors(spec)["areas"]["sim_bad"]
    assert len(area["slots_raw"]) == 7 * 48
    assert area["slots_raw"]["2,13"] == 0.5
    assert area["slots_raw"]["2,12"] == 0.0


@pytest.mark.parametrize(
    ("spec", "fragment"),
    [
        ({"slot_minutes": 7, "areas": {}}, "divide a day"),
        ({"areas": {"bad": {"windows": [{"days": ["monday"], "prior": 0.4}]}}}, "unknown days"),
        ({"areas": {"bad": {"windows": [{"from": "6", "prior": 0.4}]}}}, "HH:MM"),
        ({"areas": {"bad": {"default": 1.5}}}, "outside 0..1"),
    ],
)
def test_invalid_sections_are_rejected(spec, fragment):
    with pytest.raises(ScenarioError, match=fragment):
        build_time_priors(spec)


def test_scenario_carries_the_response():
    rooms = {"bad": {"floor_area_m2": 6}}
    scn = load_scenario_dict(scenario(rooms, area_occupancy=SPEC))
    assert scn.area_occupancy["areas"]["sim_bad"]["area_id"] == "bad"
    assert load_scenario_dict(scenario(rooms)).area_occupancy == {}
