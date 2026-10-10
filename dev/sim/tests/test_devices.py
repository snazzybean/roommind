"""Device models and quirks from the issue tracker."""

from __future__ import annotations

from helpers import run, world


def _one(profile: str, temp: float = 20.0, **dev):  # noqa: ANN003
    w = world(
        {"r": {"initial": {"temperature": temp}, "devices": [{"entity_id": "climate.d", "profile": profile, **dev}]}}
    )
    return w, w.devices["climate.d"]


def test_dyson_rejects_its_own_max_temp_396():
    w, d = _one("dyson_hp")
    assert d.max_temp == 37
    res = d.call("set_temperature", {"temperature": 37, "hvac_mode": "heat"}, w.now)
    assert not res.ok and "274-310" in res.reason
    assert d.call("set_temperature", {"temperature": 36}, w.now).ok


def test_sonoff_rejects_zero_162():
    w, d = _one("sonoff_trvzb")
    assert not d.call("set_temperature", {"temperature": 0}, w.now).ok
    assert d.counters.rejected == 1


def test_midea_set_temperature_right_after_mode_turns_off_337():
    w, d = _one("midea_ac_lan")
    d.call("set_hvac_mode", {"hvac_mode": "cool"}, w.now)
    d.call("set_temperature", {"temperature": 22}, w.now + 1)
    assert d.hvac_mode == "off"
    d.call("set_hvac_mode", {"hvac_mode": "cool"}, w.now + 10)
    d.call("set_temperature", {"temperature": 22}, w.now + 20)
    assert d.hvac_mode == "cool"


def test_ir_ac_beeps_on_every_frame_416():
    w, d = _one("broadlink_ir_ac")
    for i in range(5):
        d.call("set_temperature", {"temperature": 22, "hvac_mode": "heat"}, w.now + i * 30)
    assert d.counters.beeps == 5
    assert d.attributes(w.now)["current_temperature"] is None


def test_homematic_duty_cycle_317():
    w, d = _one("homematic_ip_trv")
    results = [d.call("set_temperature", {"temperature": 20 + (i % 2)}, w.now + i) for i in range(35)]
    assert sum(not r.ok for r in results) == 5
    assert d.call("set_temperature", {"temperature": 19}, w.now + 3700).ok


def test_state_lag_shows_old_state():
    w, d = _one("daikin_ac")
    d.call("set_hvac_mode", {"hvac_mode": "cool"}, w.now)
    assert d.state(w.now + 5) == "off"
    assert d.state(w.now + 60) == "cool"


def test_battery_trv_goes_offline_when_held_off_183():
    w, d = _one("battery_trv_deep_sleep")
    d.call("set_hvac_mode", {"hvac_mode": "off"}, w.now)
    run(w, 1900)
    assert not d.available and d.state(w.now) == "unavailable"
    assert not d.call("set_hvac_mode", {"hvac_mode": "heat"}, w.now).ok


def test_sonoff_unavailable_after_ha_start():
    w, d = _one("sonoff_trvzb")
    w.ha_started(w.now)
    run(w, 20)
    assert not d.available
    run(w, 60)
    assert d.available


def test_ecobee_fahrenheit_range_and_whole_degrees():
    w, d = _one("ecobee", temp=18.0)
    assert d.unit == "F" and d.range_setpoint
    d.call("set_temperature", {"target_temp_low": 70, "target_temp_high": 76, "hvac_mode": "heat_cool"}, w.now)
    attrs = d.attributes(w.now)
    assert attrs["target_temp_low"] == 70 and attrs["temperature"] is None
    assert attrs["current_temperature"] == round(attrs["current_temperature"])
    run(w, 60)
    assert d.running_mode == "heat"  # 18 °C = 64.4 °F < 70 °F


def test_split_ac_holds_internal_min_run_and_reads_warm_while_heating():
    w, d = _one("generic_split_ac", temp=20.5)
    d.call("set_temperature", {"temperature": 21, "hvac_mode": "heat"}, w.now)
    run(w, 30)
    assert d.running_mode == "heat"
    assert d.sensor_c >= 21.5  # return-air offset while heating
    run(w, 30)
    assert d.running_mode == "heat"  # internal min run, although the sensor is past the setpoint
    run(w, 300)
    assert d.running_mode is None
    assert d.counters.starts == 1


def test_split_ac_cooling_dehumidifies():
    w, d = _one("generic_split_ac", temp=28.0)
    w.zones["r"].set_initial(28.0, 70.0)
    rh0 = w.zones["r"].x
    d.call("set_temperature", {"temperature": 22, "hvac_mode": "cool"}, w.now)
    run(w, 1800)
    assert w.zones["r"].x < rh0
    assert d.coil_water_kg > 0
    assert d.electric_w() > 100


def test_boiler_off_means_no_radiator_heat():
    w = world(
        {
            "r": {
                "initial": {"temperature": 18.0},
                "devices": [
                    {"entity_id": "climate.trv", "profile": "generic_trv"},
                    {"entity_id": "climate.boiler", "profile": "generic_boiler"},
                ],
            }
        }
    )
    trv, boiler = w.devices["climate.trv"], w.devices["climate.boiler"]
    trv.call("set_temperature", {"temperature": 22, "hvac_mode": "heat"}, w.now)
    run(w, 900)
    assert trv.heat_output_w() < 20 and not boiler.active
    boiler.call("set_hvac_mode", {"hvac_mode": "heat"}, w.now)
    run(w, 900)
    assert trv.heat_output_w() > 300 and boiler.active
    assert boiler.electric_w() > 300  # fuel, from the draw of the served TRV


def test_snapshot_restore_roundtrip():
    w, d = _one("homematic_ip_trv")
    d.call("set_temperature", {"temperature": 22, "hvac_mode": "heat"}, w.now)
    run(w, 1200)
    snap = w.snapshot()
    w2, _ = _one("homematic_ip_trv")
    w2.restore(snap)
    run(w, 600)
    run(w2, 600)
    assert abs(w.zones["r"].t_air - w2.zones["r"].t_air) < 1e-9
    assert w2.devices["climate.d"].quirks[0].sent
