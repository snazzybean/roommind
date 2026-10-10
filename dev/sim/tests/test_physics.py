"""Physics plausibility: relaxation, emitters, solar, windows, humidity, ground truth."""

from __future__ import annotations

import math

from helpers import run, world

from roommind_sim.physics.psychro import abs_humidity, rel_humidity
from roommind_sim.physics.solar import irradiance, sun_position, window_gain_w


def test_unheated_room_relaxes_towards_outdoor():
    w = world({"r": {"initial": {"temperature": 20.0}}})
    tau_h = w.ground_truth()["r"]["tau_h"]
    assert 10 < tau_h < 80  # partly renovated masonry: one to three days
    run(w, 6 * 3600)
    t6 = w.zones["r"].t_air
    assert 0 < t6 < 20
    # air drops faster than the mass, which keeps storing heat
    assert w.zones["r"].t_mass > t6


def test_radiator_responds_in_minutes():
    w = world(
        {"r": {"initial": {"temperature": 18.0}, "devices": [{"entity_id": "climate.r_trv", "profile": "generic_trv"}]}}
    )
    dev = w.devices["climate.r_trv"]
    assert dev.call("set_temperature", {"temperature": 22, "hvac_mode": "heat"}, w.now).ok
    run(w, 600)
    assert dev.valve > 0.9 and dev.active
    assert 600 < dev.heat_output_w() < 1500  # radiator warmed up within 10 min
    run(w, 2 * 3600)
    assert w.zones["r"].t_air > 19.0


def test_trv_head_bias_closes_valve_before_room_reaches_setpoint():
    w = world(
        {"r": {"initial": {"temperature": 19.0}, "devices": [{"entity_id": "climate.r_trv", "profile": "generic_trv"}]}}
    )
    dev = w.devices["climate.r_trv"]
    dev.call("set_temperature", {"temperature": 21, "hvac_mode": "heat"}, w.now)
    run(w, 8 * 3600)
    # P controller on a biased sensor: the room settles below the TRV setpoint
    assert w.zones["r"].t_air < 21.0
    assert dev.sensor_c > w.zones["r"].t_air


def test_underfloor_keeps_heating_after_switch_off():
    w = world(
        {"r": {"initial": {"temperature": 19.0}, "devices": [{"entity_id": "climate.r_fbh", "profile": "ufh_zone"}]}}
    )
    dev = w.devices["climate.r_fbh"]
    dev.call("set_temperature", {"temperature": 23, "hvac_mode": "heat"}, w.now)
    run(w, 30 * 60)
    early = w.zones["r"].t_air
    run(w, 4 * 3600)
    assert w.zones["r"].t_air > early + 0.5  # slow response
    dev.call("set_hvac_mode", {"hvac_mode": "off"}, w.now)
    at_off = w.zones["r"].t_air
    peak = at_off
    for _ in range(12):
        run(w, 300)
        peak = max(peak, w.zones["r"].t_air)
    assert peak > at_off + 0.05  # residual heat from the slab
    assert dev.heat_output_w() > 100


def test_open_window_cools_fast():
    rooms = {"r": {"initial": {"temperature": 21.0}, "windows": [{"area_m2": 2, "sensor": "binary_sensor.r_win"}]}}
    closed = world(rooms)
    opened = world(rooms)
    opened.apply_action("window.open", {"entity_id": "binary_sensor.r_win", "for": 900}, opened.now)
    run(closed, 900)
    run(opened, 900)
    assert closed.zones["r"].t_air - opened.zones["r"].t_air > 1.0
    assert not opened.window_sensors["binary_sensor.r_win"].open  # closed again after "for"


def test_solar_gain_noon_south_not_at_night():
    noon = 1768219200  # 2026-01-12 12:00 UTC
    sun = sun_position(noon, 52.5, 13.4)
    assert 10 < sun.elevation_deg < 20 and 160 < sun.azimuth_deg < 200
    irr = irradiance(sun, 0)
    assert window_gain_w(sun, irr, "S", 4, 0.6) > 500
    assert window_gain_w(sun, irr, "N", 4, 0.6) < window_gain_w(sun, irr, "S", 4, 0.6) / 3
    night = sun_position(noon - 12 * 3600, 52.5, 13.4)
    assert night.elevation_deg < 0 and irradiance(night, 0).ghi == 0


def test_shower_raises_humidity_and_airing_lowers_it():
    w = world(
        {
            "bad": {
                "floor_area_m2": 6,
                "initial": {"temperature": 21.0, "humidity": 50.0},
                "windows": [{"area_m2": 0.8, "sensor": "binary_sensor.bad_win"}],
            }
        }
    )
    w.apply_action("humidity.event", {"room": "bad", "grams": 400, "for": 900}, w.now)
    run(w, 900)
    peak = w.zones["bad"].rh
    assert peak > 65
    w.apply_action("window.open", {"entity_id": "binary_sensor.bad_win"}, w.now)
    run(w, 1800)
    assert w.zones["bad"].rh < peak - 10


def test_psychro_roundtrip():
    x = abs_humidity(21.0, 55.0)
    assert math.isclose(rel_humidity(21.0, x), 55.0, rel_tol=1e-6)
