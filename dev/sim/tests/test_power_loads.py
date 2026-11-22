"""Metered device loads (power.set): one per name, a heat share and a lag, one sensor per load."""

from __future__ import annotations

import pytest
from helpers import run, world

from roommind_sim.scenario import ScenarioError, load_scenario_dict
from roommind_sim.world import World, WorldError

ROOM = {
    "office": {
        "floor_area_m2": 14,
        "sensors": {
            "temperature": "sensor.office_temp",
            "power": "sensor.office_power",
            "power_pc": "sensor.office_pc",
            "power_oven": "sensor.office_oven",
        },
    }
}


def _sensor_params(w: World, eid: str) -> dict:
    return w.sensors[eid].spec.params


def test_power_sensor_per_load_and_for_the_room():
    w = world(ROOM)
    assert w.sensors["sensor.office_pc"].spec.kind == "power"
    assert _sensor_params(w, "sensor.office_pc")["load"] == "pc"
    assert "load" not in _sensor_params(w, "sensor.office_power")
    w.apply_action("power.set", {"room": "office", "load": "pc", "watts": 400}, w.now)
    w.apply_action("power.set", {"room": "office", "load": "oven", "watts": 2000}, w.now)
    assert w.power_w("office", "pc") == 400
    assert w.power_w("office", "oven") == 2000
    assert w.power_w("office") == 2400


def test_heat_share_and_lag():
    w = world(ROOM)
    w.apply_action("power.set", {"room": "office", "load": "dishwasher", "watts": 2000, "heat": 0.1}, w.now)
    w.apply_action("power.set", {"room": "office", "load": "oven", "watts": 2000, "heat_tau": 30}, w.now)
    run(w, 60.0)
    # the dishwasher leaves 10 % at once, the oven releases its heat with a 30 min lag
    dishwasher = w.power_load["office/dishwasher"]
    oven = w.power_load["office/oven"]
    assert dishwasher.released_w == pytest.approx(200.0)
    assert 0 < oven.released_w < 200.0
    run(w, 3 * 3600.0)
    assert oven.released_w == pytest.approx(2000.0, rel=0.01)
    assert w.power_heat_w("office") == pytest.approx(2200.0, rel=0.01)


def test_a_load_that_ends_keeps_releasing_its_heat():
    w = world(ROOM)
    w.apply_action("power.set", {"room": "office", "load": "oven", "watts": 2000, "heat_tau": 30, "for": 3600}, w.now)
    run(w, 2 * 3600.0)
    load = w.power_load["office/oven"]
    assert load.watts == 0.0
    assert load.released_w > 100.0
    run(w, 6 * 3600.0)
    assert "office/oven" not in w.power_load


def test_power_loads_survive_a_restart():
    w = world(ROOM)
    w.apply_action("power.set", {"room": "office", "load": "pc", "watts": 400, "heat": 0.9}, w.now)
    run(w, 60.0)
    again = World(w.scn)
    again.restore(w.snapshot())
    assert again.power_load["office/pc"] == w.power_load["office/pc"]


@pytest.mark.parametrize("args", [{"heat": 1.5}, {"heat": -0.1}, {"heat_tau": -1}])
def test_invalid_heat_share_or_lag(args):
    w = world(ROOM)
    with pytest.raises(WorldError):
        w.apply_action("power.set", {"room": "office", "watts": 100, **args}, w.now)


def test_unknown_room():
    w = world(ROOM)
    with pytest.raises(WorldError):
        w.apply_action("power.set", {"room": "attic", "watts": 100}, w.now)


def test_outdoor_power_sensor_is_no_kind():
    from helpers import scenario

    data = scenario(ROOM)
    data["house"]["outdoor"] = {"sensors": {"power_pc": "sensor.out_pc"}}
    with pytest.raises(ScenarioError):
        load_scenario_dict(data)
