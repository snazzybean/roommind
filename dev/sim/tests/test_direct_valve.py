"""Direct valve control: TRVZB opening/closing degree numbers and the valve flow characteristic."""

from __future__ import annotations

import pytest
from helpers import run, scenario, world

from roommind_sim.analysis.invariants import no_commands_when_climate_off
from roommind_sim.analysis.load import RunData
from roommind_sim.analysis.metrics import _device_metrics
from roommind_sim.scenario import load_scenario_dict
from roommind_sim.world import World

OPEN = "number.d_valve_opening_degree"
CLOSE = "number.d_valve_closing_degree"


def _one(profile: str = "sonoff_trvzb", temp: float = 19.0, **dev):  # noqa: ANN003
    w = world(
        {"r": {"initial": {"temperature": temp}, "devices": [{"entity_id": "climate.d", "profile": profile, **dev}]}}
    )
    d = w.devices["climate.d"]
    d.boot_time = w.now - 3600  # past the TRVZB's start-up unavailability
    return w, d


def _heat(d, w, target: float) -> None:  # noqa: ANN001
    assert d.call("set_temperature", {"temperature": target, "hvac_mode": "heat"}, w.now).ok


def test_number_entities_named_after_the_climate_entity():
    w, d = _one()
    assert d.spec.valve_numbers() == {"opening": OPEN, "closing": CLOSE}
    assert w.valve_numbers == {OPEN: ("climate.d", "opening"), CLOSE: ("climate.d", "closing")}
    assert {OPEN, CLOSE} <= w.scn.entity_ids()
    assert (d.valve_opening_deg, d.valve_closing_deg) == (100, 100)


def test_plain_trv_has_no_number_entities():
    w, d = _one("generic_trv")
    assert d.spec.valve_numbers() == {}
    assert not w.valve_numbers
    assert not d.call("set_valve_opening_degree", {"value": 30}, w.now).ok
    assert "valve_open_deg" not in w.sample()["devices"]["climate.d"]


def test_defaults_keep_the_valve_and_room_unchanged():
    def trace(**dev):  # noqa: ANN003
        w, d = _one("generic_trv", **dev)
        out = []
        for target in (22.0, 19.5, 21.0, 18.0, 23.0):
            _heat(d, w, target)
            run(w, 3 * 3600)
            out.append((d.valve, d.t_rad, w.zones["r"].t_air, d.counters.heat_j))
        return out

    plain = trace()
    numbers = trace(capabilities={"valve_numbers": True}, valve_flow_exponent=1.0, valve_dead_zone=0.0)
    assert plain == numbers
    assert any(0.0 < v[0] < 1.0 for v in plain)


def test_pinned_degrees_hold_the_valve_regardless_of_the_setpoint():
    w, d = _one()
    assert w.valve_call(OPEN, 30, w.now).ok
    assert w.valve_call(CLOSE, 70, w.now).ok
    for target in (30.0, 5.0, 21.0):
        _heat(d, w, target)
        run(w, 600)
        assert d.valve == pytest.approx(0.3)
    sample = w.sample()["devices"]["climate.d"]
    assert (sample["valve_open_deg"], sample["valve_close_deg"], sample["valve"]) == (30, 70, 0.3)


def test_opening_degree_caps_full_demand():
    w, d = _one(temp=15.0)
    w.valve_call(OPEN, 40, w.now)
    _heat(d, w, 30.0)
    run(w, 600)
    assert d.valve == pytest.approx(0.4)


def test_off_rests_on_the_closing_degree():
    w, d = _one()
    w.valve_call(CLOSE, 80, w.now)
    d.call("set_hvac_mode", {"hvac_mode": "off"}, w.now)
    run(w, 600)
    assert d.valve == pytest.approx(0.2)
    assert d.hvac_action == "off"
    assert d.heat_output_w() > 0


def test_crossed_degrees_stay_between_both():
    w, d = _one(temp=15.0)
    w.valve_call(OPEN, 20, w.now)
    w.valve_call(CLOSE, 20, w.now)  # crossed: the position follows demand, clamped to 20..80 %
    _heat(d, w, 30.0)
    run(w, 600)
    assert d.valve == pytest.approx(0.8)
    d.call("set_hvac_mode", {"hvac_mode": "off"}, w.now)
    run(w, 600)
    assert d.valve == pytest.approx(0.2)


def test_flow_exponent_and_dead_zone():
    w, d = _one("generic_trv", valve_flow_exponent=0.5, valve_dead_zone=0.1)
    for valve, share in ((0.0, 0.0), (0.1, 0.0), (0.55, 0.5**0.5), (1.0, 1.0)):
        d.valve = valve
        assert d.flow_share() == pytest.approx(share)


def test_dead_zone_blocks_heat_below_it():
    w, d = _one("generic_trv", valve_dead_zone=0.5, capabilities={"valve_numbers": True})
    w.valve_call("number.d_valve_opening_degree", 40, w.now)
    _heat(d, w, 30.0)
    run(w, 1800)
    assert d.valve == pytest.approx(0.4)
    assert d.water_draw_w == 0.0
    assert not d.active


def test_degrees_persist():
    w, d = _one()
    w.valve_call(OPEN, 35, w.now)
    w.valve_call(CLOSE, 90, w.now)
    snap = w.snapshot()
    w2 = World(w.scn)
    w2.restore(snap)
    d2 = w2.devices["climate.d"]
    assert (d2.valve_opening_deg, d2.valve_closing_deg) == (35, 90)


def test_set_is_rejected_while_the_trv_is_unavailable():
    w, d = _one()
    d.boot_time = w.now  # TRVZB: unavailable for 40 s after HA start
    run(w, 10)
    assert not w.is_available(OPEN, w.now)
    res = w.valve_call(OPEN, 30, w.now)
    assert res.status == "rejected:unavailable"
    assert d.valve_opening_deg == 100
    run(w, 60)
    assert w.is_available(OPEN, w.now)
    assert w.valve_call(OPEN, 30, w.now).status == "accepted"
    assert w.valve_call(OPEN, 30, w.now).status == "accepted:no_change"


def test_numbers_change_with_the_device_state():
    w, d = _one()
    assert {OPEN, CLOSE} <= w.step(10, w.now + 10)


def test_unknown_number_entity():
    w, _ = _one()
    assert w.valve_call("number.nope", 10, w.now).reason == "unknown_entity"


def _metrics_run(commands: list[dict], valves: list[float], rooms: dict | None = None) -> RunData:
    devices = [
        {"entity_id": "climate.d", "profile": "sonoff_trvzb"},
        {"entity_id": "climate.k", "profile": "generic_boiler"},
    ]
    scn = load_scenario_dict(scenario({"r": {"devices": devices}}, duration="1d"))
    step = 86400 / (len(valves) - 1)
    samples = [
        {
            "t": scn.start + i * step,
            "devices": {
                "climate.d": {"active": False, "heat_w": 0, "electric_w": 0, "valve": v},
                "climate.k": {"active": False, "heat_w": 0, "electric_w": 0},
            },
        }
        for i, v in enumerate(valves)
    ]
    events = [{"type": "command", "t": scn.start + 60 * i, **c} for i, c in enumerate(commands)]
    return RunData(None, scn, samples, [], events, scn.start + 86400, {"rooms": rooms or {}})  # type: ignore[arg-type]


def test_valve_metrics():
    cmd = {"service": "set_value", "data": {"value": 30.0}, "result": "accepted"}
    run_data = _metrics_run(
        [{"entity_id": OPEN, **cmd}, {"entity_id": CLOSE, **cmd}, {"entity_id": OPEN, **cmd}],
        [0.0, 0.5, 0.2, 1.0, 1.0],
    )
    m = {eid: _device_metrics(run_data, eid, 24.0) for eid in ("climate.d", "climate.k")}
    assert m["climate.d"]["valve_travel_per_day"] == pytest.approx(1.6)
    assert m["climate.d"]["valve_commands_per_hour"] == pytest.approx(round(3 / 24, 2))
    assert m["climate.d"]["commands"] == 0
    assert m["climate.k"]["valve_travel_per_day"] is None
    assert m["climate.k"]["valve_commands_per_hour"] is None
    assert list(m["climate.k"]) == list(m["climate.d"])


def test_valve_commands_count_when_climate_is_off():
    cmd = {"entity_id": OPEN, "service": "set_value", "data": {"value": 0.0}, "result": "accepted"}
    run_data = _metrics_run([cmd], [0.0, 0.0], rooms={"r": {"climate_control_enabled": False}})
    assert len(no_commands_when_climate_off(run_data)) == 1


def test_handing_the_valve_back_is_allowed_when_climate_is_off():
    cmd = {"entity_id": OPEN, "service": "set_value", "data": {"value": 100}, "result": "accepted"}
    run_data = _metrics_run([cmd], [0.0, 0.0], rooms={"r": {"climate_control_enabled": False}})
    assert no_commands_when_climate_off(run_data) == []
