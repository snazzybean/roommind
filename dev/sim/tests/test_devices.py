"""Device models and quirks from the issue tracker."""

from __future__ import annotations

import pytest
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
    run(w, 120)
    assert d.sensor_c >= 21.5  # return-air offset while heating
    assert d.running_mode == "heat"  # internal min run, although the sensor is past the setpoint
    run(w, 300)
    assert d.running_mode is None
    assert d.counters.starts == 1


def test_split_ac_throttles_to_minimum_past_its_setpoint():
    w, d = _one("generic_split_ac", temp=21.0)
    d.call("set_temperature", {"temperature": 22, "hvac_mode": "heat"}, w.now)
    run(w, 160)
    assert d.running_mode == "heat" and d.sensor_c > 22
    assert d.modulation == pytest.approx(0.3)


def test_split_ac_return_air_offset_builds_up_and_fades():
    w, d = _one("generic_split_ac", temp=17.0)
    d.call("set_temperature", {"temperature": 30, "hvac_mode": "heat"}, w.now)
    run(w, 20)
    assert 0 < d.sensor_offset_k < 0.5
    run(w, 900)
    assert d.sensor_offset_k == pytest.approx(1.5, abs=0.05)
    d.call("set_hvac_mode", {"hvac_mode": "off"}, w.now)
    run(w, 60)
    assert 0.5 < d.sensor_offset_k < 1.5


def test_split_ac_idle_offset_reads_the_warm_layer_once_stopped():
    w, d = _one("generic_split_ac", temp=26.0, sensor_offset_cool_k=1.0, sensor_offset_idle_k=2.0)
    run(w, 900)
    assert d.running_mode is None
    assert d.sensor_offset_k == pytest.approx(2.0, abs=0.05)
    d.call("set_temperature", {"temperature": 20, "hvac_mode": "cool"}, w.now)
    run(w, 900)
    assert d.running_mode == "cool"
    assert d.sensor_offset_k == pytest.approx(1.0, abs=0.05)


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


def test_split_ac_output_ramps_up_after_the_compressor_starts():
    w, d = _one("generic_split_ac", temp=28.0, capacity_tau_s=75)
    d.call("set_temperature", {"temperature": 16, "hvac_mode": "cool"}, w.now)
    run(w, 80)
    assert d.running_mode == "cool" and d.modulation == pytest.approx(1.0)
    assert 0.55 < d.output < 0.7  # first-order lag: ~63 % after one time constant
    run(w, 600)
    assert d.output > 0.99


def test_split_ac_coil_stops_cooling_once_switched_off():
    w, d = _one("generic_split_ac", temp=28.0, capacity_tau_s=75)
    d.call("set_temperature", {"temperature": 16, "hvac_mode": "cool"}, w.now)
    run(w, 600)
    d.call("set_hvac_mode", {"hvac_mode": "off"}, w.now)
    run(w, 10)
    assert d.output == 0.0


def test_split_ac_waits_for_its_restart_delay():
    w, d = _one("generic_split_ac", temp=28.0, min_off_s=180)
    d.call("set_temperature", {"temperature": 16, "hvac_mode": "cool"}, w.now)
    run(w, 300)
    d.call("set_hvac_mode", {"hvac_mode": "off"}, w.now)
    run(w, 30)
    d.call("set_hvac_mode", {"hvac_mode": "cool"}, w.now)
    run(w, 60)
    assert d.running_mode is None and d.hvac_action == "idle"
    run(w, 120)
    assert d.running_mode == "cool"
    assert d.counters.starts == 2


def test_heating_curve_supply():
    from roommind_sim.devices.models import curve_supply_c

    assert curve_supply_c({}, -12.0, 55.0) == pytest.approx(55.0)
    assert curve_supply_c({}, 4.0, 55.0) == pytest.approx(40.0)
    assert curve_supply_c({}, 25.0, 55.0) == pytest.approx(25.0)
    assert curve_supply_c({"heating_curve": False}, 10.0, 55.0) == pytest.approx(55.0)
    assert curve_supply_c({"supply_temp_c": 35, "supply_foot_c": 24}, -12.0, 35.0) == pytest.approx(35.0)


def _radiator_output(outdoor: float, **dev):  # noqa: ANN003
    w = world(
        {
            "r": {
                "initial": {"temperature": 20.0},
                "devices": [{"entity_id": "climate.d", "profile": "generic_trv", **dev}],
            }
        },
        weather={"profile": "temperate", "fixed": {"temperature": outdoor, "cloud": 100.0, "humidity": 80.0}},
    )
    d = w.devices["climate.d"]
    d.call("set_temperature", {"temperature": 30, "hvac_mode": "heat"}, w.now)
    run(w, 3600)
    return d.heat_output_w(), d._size(DeviceEnvStub(w.zones["r"])) * d._design_dt(), w.zones["r"].t_air


class DeviceEnvStub:
    def __init__(self, zone):  # noqa: ANN001
        self.zone = zone


def test_radiator_keeps_its_design_output_and_follows_the_curve_in_mild_weather():
    cold, design_w, room = _radiator_output(-12.0)
    # at the design point the warmed-up open radiator gives its rated output (the room warms a little)
    assert 0.95 * design_w < cold <= design_w * 1.02
    assert room > 20.0
    mild, _, _ = _radiator_output(10.0)
    fixed, _, _ = _radiator_output(10.0, heating_curve=False)
    # 33 °C supply instead of 55 °C: a third of the output, not two thirds as with a linear radiator
    assert mild < 0.4 * cold
    assert fixed > 0.85 * cold


def _split_heating(outdoor: float, humidity: float, **dev):  # noqa: ANN003
    w = world(
        {
            "r": {
                "initial": {"temperature": 15.0},
                "devices": [{"entity_id": "climate.d", "profile": "generic_split_ac", **dev}],
            }
        },
        weather={"profile": "temperate", "fixed": {"temperature": outdoor, "cloud": 100.0, "humidity": humidity}},
    )
    d = w.devices["climate.d"]
    d.call("set_temperature", {"temperature": 30, "hvac_mode": "heat"}, w.now)
    cold = []
    run(w, 3 * 3600, every=lambda w_, t: cold.append(d.active and d.heat_output_w() < 1))
    return d, sum(cold) * 10


def test_split_ac_defrosts_in_humid_cold_but_not_in_mild_or_dry_air():
    d, cold_s = _split_heating(1.0, 90.0)
    # 45 min of heating per 5 min defrost: three to four defrosts in three hours
    assert 900 <= cold_s <= 1300
    assert d.hvac_action == "heating" or d.hvac_action == "idle"
    assert _split_heating(10.0, 90.0)[1] == 0
    assert _split_heating(1.0, 50.0)[1] == 0
    assert _split_heating(1.0, 90.0, defrost_interval_s=0)[1] == 0


def test_split_ac_max_output_caps_the_eco_mode():
    w, d = _one("generic_split_ac", 28.0, max_output=0.35)
    d.call("set_temperature", {"temperature": 16, "hvac_mode": "cool"}, w.now)
    run(w, 600)
    assert d.modulation == pytest.approx(0.35)


def test_tado_x_falls_back_to_its_setpoint_after_switching_on():
    w, d = _one("tado_x_matter")
    d.call("set_hvac_mode", {"hvac_mode": "off"}, w.now)
    d.call("set_temperature", {"temperature": 5}, w.now)
    d.call("set_hvac_mode", {"hvac_mode": "heat"}, w.now)
    d.call("set_temperature", {"temperature": 29, "hvac_mode": "heat"}, w.now)
    assert d.target == 29
    run(w, 10)
    assert d.hvac_mode == "heat" and d.target == 5
    d.call("set_temperature", {"temperature": 29}, w.now)
    run(w, 10)
    assert d.target == 29
