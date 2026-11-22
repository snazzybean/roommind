"""Appliances (exhaust fan, dehumidifier, humidifier, room fan) and the per-room solar sensor."""

from __future__ import annotations

import copy

import pytest
from helpers import run, scenario, world

from roommind_sim.physics.psychro import AIR_DENSITY, LATENT_HEAT
from roommind_sim.scenario import ScenarioError, load_scenario_dict
from roommind_sim.world import World

BATH = {"floor_area_m2": 6, "initial": {"temperature": 22.0, "humidity": 85}}


def _bath(appliance: dict | None = None, **room) -> dict:
    data = copy.deepcopy(BATH) | room
    if appliance is not None:
        data["appliances"] = [appliance]
    return {"bad": data}


def test_exhaust_fan_exchanges_air_with_outdoors():
    fan = {"entity_id": "fan.bad_luefter", "profile": "exhaust_fan", "airflow_m3_h": 80}
    a, b = world(_bath(fan)), world(_bath())
    app = a.appliances["fan.bad_luefter"]
    assert app.call("turn_on", {}, a.now).ok
    a.step(10, a.now + 10)
    b.step(10, b.now + 10)
    za, zb = a.zones["bad"], b.zones["bad"]
    air_kg = za.params.volume_m3 * AIR_DENSITY * za.params.moisture_buffer
    # the zone applies exactly the moisture the fan books (one 10 s step)
    assert za.x - zb.x == pytest.approx(app.moisture_kg_s * 10 / air_kg, rel=1e-3)
    assert app.moisture_kg_s < 0 and app.heat_w < 0
    run(a, 3600)
    run(b, 3600)
    assert za.rh < zb.rh - 10
    assert za.t_air < zb.t_air
    assert a.appliances["fan.bad_luefter"].counters.starts == 1


def test_exhaust_fan_with_makeup_room_draws_air_from_the_hall():
    fan = {"entity_id": "fan.bad_luefter", "profile": "exhaust_fan", "makeup_room": "flur"}
    rooms = _bath(fan) | {"flur": {"floor_area_m2": 8, "initial": {"temperature": 20.0, "humidity": 40}}}
    plain = _bath() | {"flur": {"floor_area_m2": 8, "initial": {"temperature": 20.0, "humidity": 40}}}
    a, b = world(rooms), world(plain)
    a.appliances["fan.bad_luefter"].call("turn_on", {}, a.now)
    run(a, 1800)
    run(b, 1800)
    # the bathroom dries towards the hall and barely cools; the hall pays with outdoor air
    assert a.zones["bad"].rh < b.zones["bad"].rh - 10
    assert a.zones["bad"].t_air > b.zones["bad"].t_air - 1.0
    assert a.zones["flur"].t_air < b.zones["flur"].t_air - 0.5
    with pytest.raises(ScenarioError, match="makeup_room"):
        load_scenario_dict(scenario(_bath(fan)))


def test_dehumidifier_extraction_depends_on_humidity_and_heats_the_room():
    dh = {"entity_id": "humidifier.keller_entfeuchter", "profile": "dehumidifier"}
    rates = {}
    for rh in (80, 60, 45, 35):
        w = world({"keller": {"initial": {"temperature": 20.0, "humidity": rh}, "appliances": [dh]}})
        app = w.appliances["humidifier.keller_entfeuchter"]
        app.call("turn_on", {}, w.now)
        w.step(10, w.now + 10)
        rates[rh] = -app.moisture_kg_s * 3600
        if rh == 60:
            assert app.heat_w == pytest.approx(300 + 0.4 / 3600 * LATENT_HEAT, rel=0.01)
    assert rates[60] == pytest.approx(0.4, rel=0.01)
    assert rates[80] > rates[60] > rates[45] > rates[35] == 0.0
    w = world({"keller": {"initial": {"temperature": 20.0, "humidity": 75}, "appliances": [dh]}})
    w.appliances["humidifier.keller_entfeuchter"].call("turn_on", {}, w.now)
    t0 = w.zones["keller"].t_air
    run(w, 3 * 3600)
    assert w.zones["keller"].rh < 65
    assert w.zones["keller"].t_air > t0


def test_dehumidifier_hygrostat_stops_at_target_and_waits_before_restart():
    dh = {"entity_id": "switch.keller_entfeuchter", "profile": "dehumidifier", "target_humidity": 60}
    humid = {"profile": "temperate", "fixed": {"temperature": 18.0, "cloud": 100.0, "humidity": 90.0}}
    w = world(
        {"keller": {"floor_area_m2": 8, "initial": {"temperature": 18.0, "humidity": 75}, "appliances": [dh]}},
        weather=humid,
    )
    app = w.appliances["switch.keller_entfeuchter"]
    app.call("turn_on", {}, w.now)
    states = []
    run(w, 24 * 3600, every=lambda ww, t: states.append((t, app.running, ww.zones["keller"].rh)))
    assert app.counters.starts >= 2  # moisture keeps coming back, the hygrostat cycles
    later = [rh for _, _, rh in states[len(states) // 2 :]]
    assert max(later) < 64 and min(later) > 55
    edges = [(t, r) for (_, was, _), (t, r, _) in zip(states, states[1:], strict=False) if r != was]
    stops = [t for t, r in edges if not r]
    restarts = [t for t, r in edges if r]
    assert stops and restarts
    assert all(b - a >= 180 for a in stops for b in restarts if 0 < b - a < 3600)
    # a switch has no set_humidity
    assert not app.call("set_humidity", {"humidity": 50}, w.now).ok


def test_humidifier_adds_moisture_cools_and_tapers_near_saturation():
    hum = {"entity_id": "humidifier.sz_befeuchter", "profile": "humidifier"}
    w = world({"sz": {"initial": {"temperature": 21.0, "humidity": 30}, "appliances": [hum]}})
    app = w.appliances["humidifier.sz_befeuchter"]
    assert not app.call("set_humidity", {"humidity": 95}, w.now).ok  # above max_humidity
    assert app.call("set_humidity", {"humidity": 45}, w.now).ok
    app.call("turn_on", {}, w.now)
    w.step(10, w.now + 10)
    assert app.moisture_kg_s * 3600 == pytest.approx(0.3, rel=0.01)
    assert app.heat_w < 0  # evaporation takes heat from the air
    run(w, 12 * 3600)
    assert 40 < w.zones["sz"].rh < 50
    assert app.counters.starts >= 1
    sat = world({"sz": {"initial": {"temperature": 21.0, "humidity": 99}, "appliances": [hum]}})
    sat.appliances["humidifier.sz_befeuchter"].call("turn_on", {}, sat.now)
    sat.step(10, sat.now + 10)
    assert sat.appliances["humidifier.sz_befeuchter"].moisture_kg_s * 3600 < 0.05


def _radiator_room(fan_on: bool | None) -> World:
    room = {
        "initial": {"temperature": 18.0},
        "devices": [{"entity_id": "climate.wz_trv", "profile": "generic_trv"}],
    }
    if fan_on is not None:
        room["appliances"] = [{"entity_id": "fan.wz_decke", "profile": "ceiling_fan", "initial_on": fan_on}]
    return world({"wz": room})


def test_room_fan_speeds_up_radiator_output_and_afterglow():
    plain, fan = _radiator_room(None), _radiator_room(True)
    for w in (plain, fan):
        w.devices["climate.wz_trv"].call("set_temperature", {"temperature": 23, "hvac_mode": "heat"}, w.now)
    run(plain, 1800)
    run(fan, 1800)
    p_dev, f_dev = plain.devices["climate.wz_trv"], fan.devices["climate.wz_trv"]
    assert f_dev.t_rad < p_dev.t_rad  # more output at the same water flow, the radiator runs cooler
    assert fan.zones["wz"].t_air > plain.zones["wz"].t_air
    for w in (plain, fan):
        w.devices["climate.wz_trv"].call("set_hvac_mode", {"hvac_mode": "off"}, w.now)
    run(plain, 2400)
    run(fan, 2400)
    # afterglow: the fan pulls the residual heat out faster
    assert f_dev.t_rad - fan.zones["wz"].t_air < p_dev.t_rad - plain.zones["wz"].t_air


def test_room_fan_while_cooling_adds_only_motor_heat_and_mixing():
    w = world(
        {
            "wz": {
                "initial": {"temperature": 26.0},
                "appliances": [{"entity_id": "fan.wz_decke", "profile": "ceiling_fan"}],
            }
        }
    )
    app = w.appliances["fan.wz_decke"]
    assert app.call("set_percentage", {"percentage": 50}, w.now).ok and app.on
    w.step(10, w.now + 10)
    assert app.heat_w == pytest.approx(20.0)
    assert app.mixing_factor() == pytest.approx(1.05)
    assert app.call("set_percentage", {"percentage": 0}, w.now).ok and not app.on
    w.step(10, w.now + 10)
    assert app.heat_w == 0.0 and not app.running


def test_room_fan_off_is_identical_to_no_fan():
    plain, fan = _radiator_room(None), _radiator_room(False)
    for w in (plain, fan):
        w.devices["climate.wz_trv"].call("set_temperature", {"temperature": 23, "hvac_mode": "heat"}, w.now)
        run(w, 3600)
    a, b = plain.sample(), fan.sample()
    b.pop("appliances")
    assert a == b


def test_switch_fan_has_no_speeds_and_manual_counts():
    w = world(_bath({"entity_id": "switch.bad_luefter", "profile": "exhaust_fan"}))
    app = w.appliances["switch.bad_luefter"]
    assert not app.call("set_percentage", {"percentage": 50}, w.now).ok
    assert app.counters.rejected == 1
    w.apply_action("device.manual", {"entity_id": "switch.bad_luefter", "state": "on"}, w.now)
    assert app.on and app.counters.manual == 1 and app.counters.commands == 1
    w.apply_action("device.manual", {"entity_id": "switch.bad_luefter", "state": False}, w.now)
    assert not app.on
    w.apply_action("device.manual", {"entity_id": "switch.bad_luefter", "state": True}, w.now)
    w.apply_action("entity.unavailable", {"entity_id": "switch.bad_luefter"}, w.now)
    assert not w.is_available("switch.bad_luefter", w.now)
    w.step(10, w.now + 10)
    assert not app.running


def test_appliance_snapshot_restore_roundtrip():
    rooms = _bath({"entity_id": "humidifier.bad_entfeuchter", "profile": "dehumidifier", "target_humidity": 60})
    a = world(rooms)
    a.appliances["humidifier.bad_entfeuchter"].call("turn_on", {}, a.now)
    run(a, 1800)
    b = world(rooms)
    b.restore(a.snapshot())
    app_a, app_b = a.appliances["humidifier.bad_entfeuchter"], b.appliances["humidifier.bad_entfeuchter"]
    assert app_b.snapshot() == app_a.snapshot()


def test_loader_checks_appliance_domain_and_model():
    bad = _bath({"entity_id": "climate.bad_luefter", "profile": "exhaust_fan"})
    with pytest.raises(ScenarioError, match="fan or switch"):
        load_scenario_dict(scenario(bad))
    with pytest.raises(ScenarioError, match="unknown appliances profile"):
        load_scenario_dict(scenario(_bath({"entity_id": "fan.bad_luefter", "profile": "nope"})))
    scn = load_scenario_dict(scenario(_bath({"entity_id": "fan.bad_luefter", "profile": "exhaust_fan"})))
    assert "fan.bad_luefter" in scn.entity_ids()


def test_world_without_new_config_keeps_its_sample_keys():
    w = world({"r": {"sensors": {"temperature": {"entity_id": "sensor.r_temp"}}}})
    w.step(10, w.now + 10)
    assert list(w.sample()) == ["outdoor", "rooms", "devices", "covers", "people"]


# --- solar sensor ---------------------------------------------------------------------------

SUMMER = {
    "start": "2026-07-06T00:00",
    "weather": {"profile": "temperate", "fixed": {"temperature": 25.0, "cloud": 0.0, "humidity": 50.0}},
}


def _sunroom(sensors: dict, covers: list | None = None) -> World:
    room = {
        "windows": [{"orientation": "E", "area_m2": 2.0}, {"orientation": "W", "area_m2": 2.0}],
        "sensors": sensors,
    }
    if covers:
        room["covers"] = covers
    return world({"wz": room}, **SUMMER)


def _at(w: World, hour: float) -> None:
    target = w.scn.start + hour * 3600
    run(w, target - w.now, dt=60)


def test_solar_sensor_east_west_and_night():
    w = _sunroom(
        {
            "solar_ost": {"entity_id": "sensor.wz_sonne_ost", "windows": [0], "noise_rel": 0},
            "solar_west": {"entity_id": "sensor.wz_sonne_west", "windows": [1], "noise_rel": 0},
        }
    )
    east, west = w.sensors["sensor.wz_sonne_ost"], w.sensors["sensor.wz_sonne_west"]
    _at(w, 2)
    assert east.value == 0 and west.value == 0
    _at(w, 8)
    assert east.value > 3 * west.value > 0
    _at(w, 18)
    assert west.value > 3 * east.value > 0
    assert w.sample()["solar_sensors"]["sensor.wz_sonne_west"] == west.value


def test_solar_sensor_inside_sees_the_cover_outside_does_not():
    cover = [{"entity_id": "cover.wz_rollo", "profile": "roller_shutter", "windows": [0]}]
    w = _sunroom(
        {
            "solar": {"entity_id": "sensor.wz_sonne_innen", "windows": [0], "noise_rel": 0},
            "solar_aussen": {
                "entity_id": "sensor.wz_sonne_aussen",
                "windows": [0],
                "position": "outside",
                "noise_rel": 0,
            },
        },
        cover,
    )
    _at(w, 8)
    inside, outside = w.sensors["sensor.wz_sonne_innen"], w.sensors["sensor.wz_sonne_aussen"]
    assert 0 < inside.value < outside.value
    open_in, open_out = inside.value, outside.value
    w.apply_action("cover.manual", {"entity_id": "cover.wz_rollo", "position": 0}, w.now)
    run(w, 900, dt=60)
    assert inside.value < 0.2 * open_in
    assert outside.value == pytest.approx(open_out, rel=0.2)


def test_solar_sensor_units_lux_saturates_percent_caps():
    w = _sunroom(
        {
            "solar": {"entity_id": "sensor.wz_sonne_wm2", "windows": [0], "position": "outside", "noise_rel": 0},
            "solar_lux": {
                "entity_id": "sensor.wz_lux",
                "unit": "lx",
                "windows": [0],
                "position": "outside",
                "noise_rel": 0,
                "max_value": 40000,
            },
            "solar_pct": {
                "entity_id": "sensor.wz_sonne_pct",
                "unit": "%",
                "windows": [0],
                "position": "outside",
                "noise_rel": 0,
            },
        }
    )
    _at(w, 8)
    wm2 = w.sensors["sensor.wz_sonne_wm2"].value
    assert wm2 > 400
    assert w.sensors["sensor.wz_lux"].value == 40000  # 120 lx per W/m² is past the cap
    assert w.sensors["sensor.wz_sonne_pct"].value == pytest.approx(min(100, wm2 / 10), abs=1.5)
    with pytest.raises(ScenarioError, match="unit"):
        load_scenario_dict(scenario({"wz": {"sensors": {"solar": {"entity_id": "sensor.x", "unit": "klx"}}}}))
    with pytest.raises(ScenarioError, match="position"):
        load_scenario_dict(scenario({"wz": {"sensors": {"solar": {"entity_id": "sensor.x", "position": "roof"}}}}))
    with pytest.raises(ScenarioError, match="window"):
        load_scenario_dict(scenario({"wz": {"sensors": {"solar": {"entity_id": "sensor.x", "windows": [3]}}}}))


# --- metrics and evaluation -------------------------------------------------------------------


def _appliance_run():
    from roommind_sim.analysis.load import RunData

    rooms = _bath({"entity_id": "fan.bad_luefter", "profile": "exhaust_fan"})
    rooms["bad"]["windows"] = [{"orientation": "S", "area_m2": 1.0}]
    rooms["bad"]["sensors"] = {"solar_lux": {"entity_id": "sensor.bad_lux", "unit": "lx", "max_value": 1000}}
    scn = load_scenario_dict(scenario(rooms))
    t0 = scn.start
    # one sample per 30 min: off, on, on, off (by hand), on, off
    pattern = [False, True, True, False, True, False]
    lux = [0, 500, 1000, 1000, 200, 0]
    samples = [
        {
            "t": t0 + 1800 * i,
            "rooms": {"bad": {"t_air": 21.0, "rh": 50 + 10 * i}},
            "appliances": {
                "fan.bad_luefter": {
                    "on": on,
                    "running": on,
                    "available": True,
                    "electric_w": 15 if on else 0,
                    "heat_w": -400 if on else 0,
                    "moisture_g_h": -1000 if on else 0,
                }
            },
            "solar_sensors": {"sensor.bad_lux": lux[i]},
        }
        for i, on in enumerate(pattern)
    ]
    events = [
        {
            "t": t0 + 1700,
            "type": "command",
            "entity_id": "fan.bad_luefter",
            "service": "turn_on",
            "data": {},
            "result": "accepted",
        },
        {
            "t": t0 + 5000,
            "type": "action",
            "action": "device.manual",
            "args": {"entity_id": "fan.bad_luefter", "state": "off"},
            "ok": True,
        },
        {
            "t": t0 + 7000,
            "type": "command",
            "entity_id": "fan.bad_luefter",
            "service": "set_percentage",
            "data": {"percentage": 50},
            "result": "rejected:unsupported_service:set_percentage",
        },
    ]
    return RunData(None, scn, samples, [{"t": t0, "rooms": {}}], events, t0 + 1800 * 6, {})  # type: ignore[arg-type]


def _metrics(run_data):
    from roommind_sim.analysis.metrics import _appliance_metrics, _humidity_metrics, _solar_sensor_metrics

    lux = next(s for s in run_data.scenario.all_sensors() if s.kind == "solar")
    return {
        "rooms": {"bad": _humidity_metrics(run_data, "bad")},
        "appliances": {"fan.bad_luefter": _appliance_metrics(run_data, "fan.bad_luefter", 3.0)},
        "sensors": {lux.entity_id: _solar_sensor_metrics(run_data, lux.entity_id, lux.params)},
    }


def test_appliance_humidity_and_solar_metrics():
    m = _metrics(_appliance_run())
    fan = m["appliances"]["fan.bad_luefter"]
    assert fan["commands"] == 2 and fan["rejected_commands"] == 1 and fan["manual_switches"] == 1
    assert fan["starts"] == 2 and fan["power_ons"] == 2
    assert fan["run_h"] == pytest.approx(1.5) and fan["on_h"] == pytest.approx(1.5)
    assert fan["shortest_run_min"] == 30 and fan["longest_run_min"] == 60
    assert fan["moisture_removed_kg"] == pytest.approx(1.5) and fan["moisture_added_kg"] == 0
    room = m["rooms"]["bad"]
    assert (
        room["rh_max"] == 100
        and room["rh_over_60_h"] == pytest.approx(2.0)
        and room["rh_over_80_h"] == pytest.approx(1.0)
    )
    lux = m["sensors"]["sensor.bad_lux"]
    assert lux["max"] == 1000 and lux["sun_h"] == pytest.approx(2.0) and lux["saturated_h"] == pytest.approx(1.0)


def test_expectations_read_appliance_and_sensor_metrics():
    from roommind_sim.analysis.evaluate import _check, _metric

    run_data = _appliance_run()
    metrics = _metrics(run_data)
    ok = _metric(run_data, metrics, {"metric": "appliance.starts", "entity_id": "fan.bad_luefter", "min": 2, "max": 2})
    assert ok["passed"]
    sat = _metric(run_data, metrics, {"metric": "sensor.saturated_h", "entity_id": "sensor.bad_lux", "max": 0.5})
    assert not sat["passed"]
    check = _check(
        run_data,
        {
            "check": "appliance('fan.bad_luefter').running and sensor('sensor.bad_lux') == 1000 and rh('bad') == 70",
            "at": "+0d01h",
        },
    )
    assert check["passed"], check
