"""Tests for humidity_manager.py: room humidity limits and the claims on the devices (#518, #526)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.roommind.const import MAX_SENSOR_STALENESS
from custom_components.roommind.managers.humidity_manager import (
    HUMIDITY_HIGH,
    HUMIDITY_LOW,
    HumidityTracker,
    humidity_device_claims,
    humidity_limits,
    humidity_regulated,
    next_humidity_level,
    outdoor_air_dries,
)
from custom_components.roommind.utils.mold_utils import absolute_humidity

DEHUM = "switch.cellar_dehumidifier"
HUM = "humidifier.bedroom"
FAN = "fan.bath"


@pytest.mark.parametrize(
    ("previous", "value", "expected"),
    [
        (None, 59.9, None),
        (None, 60, HUMIDITY_HIGH),
        (HUMIDITY_HIGH, 55.1, HUMIDITY_HIGH),  # inside the hysteresis: stays
        (HUMIDITY_HIGH, 54.9, None),
        (None, 40, HUMIDITY_LOW),
        (HUMIDITY_LOW, 44.9, HUMIDITY_LOW),
        (HUMIDITY_LOW, 45.0, None),
        (HUMIDITY_LOW, 70, HUMIDITY_HIGH),
        (HUMIDITY_HIGH, 30, HUMIDITY_LOW),
        (HUMIDITY_HIGH, None, HUMIDITY_HIGH),  # no reading: no new information
    ],
)
def test_level_with_hysteresis(previous, value, expected):
    assert next_humidity_level(previous, value, 40, 60) == expected


def test_one_sided_limits():
    assert next_humidity_level(None, 10, None, 60) is None
    assert next_humidity_level(None, 95, 40, None) is None
    assert next_humidity_level(HUMIDITY_HIGH, 58, None, None) is None


def test_limits_and_regulated():
    room = {"humidity_sensor": "sensor.h", "humidity_max": 65, "humidity_min": None}
    assert humidity_limits(room) == (None, 65.0)
    assert humidity_regulated(room)
    assert not humidity_regulated({**room, "humidity_sensor": ""})
    assert not humidity_regulated({**room, "is_outdoor": True})
    assert not humidity_regulated({"humidity_sensor": "sensor.h"})
    assert humidity_limits({"humidity_sensor": "sensor.h", "humidity_min": 35}) == (35.0, None)


def test_tracker_holds_through_a_dropout_then_forgets():
    t = HumidityTracker()
    assert t.evaluate("bath", 75, None, 60, 0) == HUMIDITY_HIGH
    assert t.is_too_humid("bath") and t.level("bath") == HUMIDITY_HIGH
    assert t.evaluate("bath", None, None, 60, MAX_SENSOR_STALENESS) == HUMIDITY_HIGH
    assert t.evaluate("bath", None, None, 60, MAX_SENSOR_STALENESS + 1) is None
    assert not t.is_too_humid("bath")
    assert t.evaluate("bath", 57, None, 60, MAX_SENSOR_STALENESS + 2) is None


def test_tracker_seed_continues_a_run_after_a_restart():
    t = HumidityTracker()
    assert t.evaluate("bath", 57, None, 60, 0, assume=HUMIDITY_HIGH) == HUMIDITY_HIGH
    # the seed only counts once, before the first judgement
    t2 = HumidityTracker()
    assert t2.evaluate("bath", 57, None, 60, 0) is None
    assert t2.evaluate("bath", 57, None, 60, 30, assume=HUMIDITY_HIGH) is None
    t3 = HumidityTracker()
    assert t3.evaluate("bed", 43, 40, None, 0, assume=HUMIDITY_LOW) == HUMIDITY_LOW


def test_tracker_without_limits_judges_nothing_and_rooms_are_separate():
    t = HumidityTracker()
    assert t.evaluate("bath", 90, None, None, 0) is None
    assert t.evaluate("bath", 90, None, 60, 0) == HUMIDITY_HIGH
    assert t.evaluate("bed", 50, None, 60, 0) is None
    t.remove_room("bath")
    assert not t.is_too_humid("bath")


def test_absolute_humidity_known_values():
    # 20 °C saturated: 17.3 g/m³; 0 °C / 80 %: about 3.9 g/m³
    assert absolute_humidity(20, 100) == pytest.approx(17.3, abs=0.1)
    assert absolute_humidity(0, 80) == pytest.approx(3.9, abs=0.1)


def test_outdoor_air_dries_with_hysteresis():
    # Shower in winter: outdoor air far drier
    assert outdoor_air_dries(22, 90, 2, 90, running=False)
    # Muggy summer: outdoor air wetter than the room
    assert not outdoor_air_dries(22, 65, 25, 75, running=False)
    # Inside 21 °C / 65 % = 11.9 g/m³; outdoor 18 °C / 75 % = 11.5: too close to start, ...
    assert not outdoor_air_dries(21, 65, 18, 75, running=False)
    # ... 1.5 g/m³ apart: not enough to start, enough to keep running
    assert not outdoor_air_dries(21, 65, 15, 81, running=False)
    assert outdoor_air_dries(21, 65, 15, 81, running=True)


@pytest.mark.parametrize("missing", ["in_t", "out_t", "out_rh"])
def test_outdoor_air_dries_without_readings_does_not_block(missing):
    args = {"in_t": 22.0, "in_rh": 70.0, "out_t": 25.0, "out_rh": 90.0}
    args[missing] = None
    assert outdoor_air_dries(args["in_t"], args["in_rh"], args["out_t"], args["out_rh"], running=False)


def _states(**on):
    return lambda eid: SimpleNamespace(state=on[eid]) if eid in on else None


def _room(**kw):
    return {"humidity_sensor": "sensor.h", **kw}


def test_claims_dehumidifier_for_a_humid_room_and_humidifier_for_a_dry_one():
    rooms = {
        "cellar": _room(humidity_max=60, dehumidifier_entity=DEHUM, humidifier_entity=""),
        "bed": _room(humidity_min=40, humidifier_entity=HUM),
    }
    states = {"cellar": {"humidity_high": True}, "bed": {"humidity_low": True}}
    wanted, blocked = humidity_device_claims(rooms, states, _states())
    assert wanted == {DEHUM: True, HUM: True}
    assert blocked == set()


def test_claims_in_band_keep_the_devices_claimed_but_unwanted():
    rooms = {"r": _room(humidity_max=60, humidity_min=40, dehumidifier_entity=DEHUM, humidifier_entity=HUM)}
    wanted, _ = humidity_device_claims(rooms, {"r": {}}, _states())
    assert wanted == {DEHUM: False, HUM: False}


def test_claims_drop_the_device_of_the_other_direction():
    """Too dry: a dehumidifier in its min run must go off at once, not after it."""
    rooms = {"r": _room(humidity_max=60, humidity_min=40, dehumidifier_entity=DEHUM, humidifier_entity=HUM)}
    wanted, _ = humidity_device_claims(rooms, {"r": {"humidity_low": True}}, _states())
    assert wanted == {HUM: True}
    wanted, _ = humidity_device_claims(rooms, {"r": {"humidity_high": True}}, _states())
    assert wanted == {DEHUM: True}


def test_claims_never_both_at_once():
    """The other device still reads on (by hand or not yet off): wait for it."""
    rooms = {"r": _room(humidity_max=60, humidity_min=40, dehumidifier_entity=DEHUM, humidifier_entity=HUM)}
    wanted, _ = humidity_device_claims(rooms, {"r": {"humidity_low": True}}, _states(**{DEHUM: "on"}))
    assert wanted == {HUM: False}


def test_claims_window_open_blocks_the_devices():
    rooms = {"r": _room(humidity_max=60, humidity_min=40, dehumidifier_entity=DEHUM, humidifier_entity=HUM)}
    wanted, blocked = humidity_device_claims(rooms, {"r": {"humidity_high": True, "window_open": True}}, _states())
    assert wanted == {}
    assert blocked == {DEHUM, HUM}


def test_claims_shared_device_runs_while_any_room_wants_it_and_a_window_blocks_it():
    rooms = {
        "a": _room(humidity_max=60, dehumidifier_entity=DEHUM),
        "b": _room(humidity_max=60, dehumidifier_entity=DEHUM),
    }
    wanted, _ = humidity_device_claims(rooms, {"a": {}, "b": {"humidity_high": True}}, _states())
    assert wanted == {DEHUM: True}
    wanted, blocked = humidity_device_claims(
        rooms, {"a": {"window_open": True}, "b": {"humidity_high": True}}, _states()
    )
    assert wanted == {} and blocked == {DEHUM}


def test_claims_skip_rooms_without_limit_or_sensor():
    rooms = {
        "no_limit": _room(dehumidifier_entity=DEHUM, humidifier_entity=HUM),
        "no_sensor": {"humidity_sensor": "", "humidity_max": 60, "dehumidifier_entity": "switch.x"},
        "only_max": _room(humidity_max=60, humidifier_entity=HUM),
    }
    wanted, blocked = humidity_device_claims(rooms, {}, _states())
    assert wanted == {} and blocked == set()


def test_no_reading_drops_a_level_whose_limit_was_removed():
    assert next_humidity_level(HUMIDITY_HIGH, None, 40, None) is None
    assert next_humidity_level(HUMIDITY_LOW, None, None, 60) is None
    assert next_humidity_level(HUMIDITY_LOW, None, 40, 60) == HUMIDITY_LOW


def test_ventilation_dries_keeps_its_own_hysteresis_per_room():
    t = HumidityTracker()
    assert t.ventilation_dries("bath", 21, 65, 15, 75)  # 2.3 g/m³ drier: starts
    assert t.ventilation_dries("bath", 21, 65, 15, 81)  # 1.5: goes on
    t.stop_venting("bath")
    assert not t.ventilation_dries("bath", 21, 65, 15, 81)  # 1.5: does not start


def test_venting_rooms_persist_and_seed():
    t = HumidityTracker()
    t.ventilation_dries("bath", 22, 90, 2, 90)
    t.ventilation_dries("bed", 21, 65, 25, 90)
    assert t.venting_rooms() == ["bath"]
    restarted = HumidityTracker()
    restarted.load_venting_rooms(t.venting_rooms())
    assert restarted.vented_before("bath") and not restarted.vented_before("bed")
    assert restarted.vented_rooms() == ["bath"]
    restarted.remove_room("bath")
    assert not restarted.vented_before("bath")
    restarted.load_venting_rooms("garbage")
    assert not restarted.vented_before("bath")
