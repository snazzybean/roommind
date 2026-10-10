"""Scenario loader: profiles, references, time specs, error locations."""

from __future__ import annotations

import time

import pytest

from roommind_sim.scenario import ScenarioError, load_scenario_dict
from roommind_sim.scenario.loader import deep_merge
from roommind_sim.scenario.timespec import format_offset, parse_at, parse_duration, parse_start


def base() -> dict:
    return {
        "name": "t",
        "location": {"time_zone": "Europe/Berlin"},
        "start": "2026-01-12T00:00",
        "duration": "2d",
        "house": {
            "building": "neubau_kfw55",
            "outdoor": {"sensors": {"temperature": "sensor.aussen_temp"}},
            "rooms": {
                "wohnzimmer": {
                    "floor_area_m2": 30,
                    "windows": [{"orientation": "S", "area_m2": 4, "sensor": "binary_sensor.wz_fenster"}],
                    "devices": [{"entity_id": "climate.wz_trv", "profile": "sonoff_trvzb", "power_w": 900}],
                    "sensors": {"temperature": {"entity_id": "sensor.wz_temp", "profile": "aqara_th"}},
                }
            },
        },
        "helpers": {"schedule": {"wz_plan": {"weekdays": ["06:00-22:00"]}}},
        "roommind": {
            "settings": {"outdoor_temp_sensor": "sensor.aussen_temp"},
            "rooms": {
                "wohnzimmer": {
                    "devices": [{"entity_id": "climate.wz_trv", "type": "trv"}],
                    "temperature_sensor": "sensor.wz_temp",
                    "window_sensors": ["binary_sensor.wz_fenster"],
                    "schedules": [{"entity_id": "schedule.wz_plan"}],
                }
            },
        },
        "timeline": [
            {"at": "+1d", "do": "window.open", "entity_id": "binary_sensor.wz_fenster", "for": "15m"},
            {"at": "2026-01-12T06:00", "do": "mark", "label": "morning"},
        ],
        "expect": [{"invariant": "target_never_empty"}],
    }


def test_loads_and_merges_profiles():
    scn = load_scenario_dict(base())
    room = scn.rooms["wohnzimmer"]
    dev = room.devices[0]
    assert dev.model == "trv"
    assert dev.capabilities["max_temp"] == 35  # sonoff overrides generic 30
    assert dev.capabilities["hvac_modes"] == ["off", "heat"]  # inherited
    assert dev.params["power_w"] == 900  # shortcut key lands in params
    assert dev.quirks[0]["type"] == "reject_values"
    assert room.thermal["u_wall"] == 0.2 and room.thermal["floor_area_m2"] == 30
    assert room.sensors[0].params["report"]["min_delta"] == 0.5
    assert scn.duration == 2 * 86400
    # timeline sorted by time, ISO interpreted in scenario TZ (06:00 Berlin = 05:00 UTC)
    assert [t.action for t in scn.timeline] == ["mark", "window.open"]
    assert scn.timeline[0].at == 6 * 3600
    assert scn.timeline[1].args["for"] == 900


@pytest.mark.parametrize(
    ("mutate", "where", "fragment"),
    [
        (
            lambda d: d["house"]["rooms"]["wohnzimmer"]["devices"][0].update(profile="nope"),
            "devices[0]",
            "unknown devices profile",
        ),
        (
            lambda d: d["roommind"]["rooms"]["wohnzimmer"].update(temperature_sensor="sensor.typo"),
            "temperature_sensor",
            "does not define",
        ),
        (lambda d: d["timeline"][0].update(at="tomorrow"), "timeline[0]", "invalid"),
        (lambda d: d["timeline"][0].update(do="window.explode"), "timeline[0]", "unknown action"),
        (lambda d: d["timeline"][0].update(at="+5d"), "timeline[0]", "outside the scenario"),
        (
            lambda d: d["house"]["rooms"]["wohnzimmer"]["devices"][0].update(entity_id="climate.roommind_x"),
            "devices[0]",
            "reserved",
        ),
        (
            lambda d: d["house"]["rooms"]["wohnzimmer"]["devices"][0].update(entity_id="sensor.x"),
            "devices[0]",
            "domain climate",
        ),
        (lambda d: d["roommind"]["rooms"].update(kueche={}), "roommind.rooms.kueche", "not defined"),
        (lambda d: d.update(duration="2 Tage"), "duration", "invalid duration"),
        (lambda d: d["expect"].append({"foo": 1}), "expect[1]", "metric, invariant or check"),
    ],
)
def test_errors_name_the_spot(mutate, where, fragment):
    data = base()
    mutate(data)
    with pytest.raises(ScenarioError) as err:
        load_scenario_dict(data)
    assert where in str(err.value)
    assert fragment in str(err.value)


def test_external_entities_allow_missing_references():
    data = base()
    data["roommind"]["rooms"]["wohnzimmer"]["humidity_sensor"] = "sensor.gone"
    data["external_entities"] = ["sensor.gone"]
    load_scenario_dict(data)


def test_duplicate_entity_ids_rejected():
    data = base()
    data["house"]["rooms"]["wohnzimmer"]["sensors"]["humidity"] = {"entity_id": "sensor.wz_temp"}
    with pytest.raises(ScenarioError, match="defined twice"):
        load_scenario_dict(data)


def test_durations_and_times():
    assert parse_duration("3h30m") == 12600
    assert parse_duration("1w2d") == 9 * 86400
    assert parse_duration(90) == 90
    with pytest.raises(ScenarioError):
        parse_duration("3x")
    start = parse_start("2026-01-12T00:00", "UTC")
    assert parse_at("+3d+30m", start, "UTC") == 3 * 86400 + 1800
    assert abs(parse_start("now-1d", "UTC") - (time.time() - 86400)) < 61
    assert format_offset(2 * 86400 + 3 * 3600 + 15 * 60) == "+2d03h15m"


def test_deep_merge_appends_with_plus():
    assert deep_merge({"q": [1], "a": {"b": 1}}, {"q+": [2], "a": {"c": 2}}) == {"q": [1, 2], "a": {"b": 1, "c": 2}}


def test_all_device_profiles_load():
    from roommind_sim.scenario.loader import PROFILE_DIR, load_profile

    for kind in ("devices", "buildings", "sensors", "covers", "people", "weather"):
        for path in (PROFILE_DIR / kind).glob("*.yaml"):
            assert load_profile(kind, path.stem, "test") is not None
