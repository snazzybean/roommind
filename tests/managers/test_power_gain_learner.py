"""PowerGainLearner: heat of each power sensor learned from the prediction error, used only when it helps."""

from __future__ import annotations

import random
from collections.abc import Callable

import pytest

from custom_components.roommind.const import MODE_HEATING, MODE_IDLE
from custom_components.roommind.control.thermal_model import RCModel
from custom_components.roommind.managers.power_gain_learner import (
    POWER_ACTIVE_MIN_WINDOWS,
    STATUS_ACTIVE,
    STATUS_LEARNING,
    STATUS_NO_EFFECT,
    PowerGainLearner,
)

DT = 1.5  # minutes per cycle
ROOM = RCModel(C=1.0, U=0.05)


def _office_pc(t_h: float) -> float:
    """400 W from 9 to 17 on every day."""
    return 0.4 if 9 <= t_h % 24 < 17 else 0.0


def _evening_load(t_h: float) -> float:
    """2 kW from 19 to 20:30."""
    return 2.0 if 19 <= t_h % 24 < 20.5 else 0.0


def _simulate(
    learner: PowerGainLearner,
    loads: dict[str, tuple[Callable[[float], float], float]],
    days: float,
    *,
    noise: float = 0.01,
    mode: str = MODE_IDLE,
    seed: int = 1,
) -> list[float]:
    """Run an idle room whose loads heat it by their gain [degC/h per kW]; returns device_heat per cycle."""
    rng = random.Random(seed)
    T = 20.0
    heats = []
    steps = int(days * 24 * 60 / DT)
    sensors = list(loads)
    for k in range(steps):
        t_h = k * DT / 60.0
        readings = {eid: fn(t_h) for eid, (fn, _) in loads.items()}
        heats.append(learner.begin_cycle("r", sensors, readings, DT))
        true_heat = sum(gain * readings[eid] for eid, (_, gain) in loads.items())
        T = ROOM.predict(T, 5.0, 0.0, DT, u_device=true_heat)
        learner.observe(
            "r",
            model=ROOM,
            mode=mode,
            disturbed=False,
            current_temp=T + rng.gauss(0.0, noise),
            T_outdoor=5.0,
            dt_minutes=DT,
        )
    return heats


def _info(learner: PowerGainLearner, eid: str) -> dict:
    return next(i for i in learner.info("r") if i["entity_id"] == eid)


def test_a_pc_is_learned_and_used():
    learner = PowerGainLearner()
    heats = _simulate(learner, {"sensor.pc": (_office_pc, 1.2)}, days=6)
    info = _info(learner, "sensor.pc")
    assert info["status"] == STATUS_ACTIVE
    assert info["gain"] == pytest.approx(1.2, rel=0.2)
    assert info["improvement"] > 0.5
    # once active its heat is a model input: warmer than usual while on, cooler while off
    assert max(heats[-960:]) > 0.1
    assert min(heats[-960:]) < 0.0


def test_a_load_without_room_heat_shows_no_effect():
    """A dishwasher's power leaves with the water: it never helps the prediction."""
    learner = PowerGainLearner()
    heats = _simulate(learner, {"sensor.dishwasher": (_evening_load, 0.0)}, days=12)
    info = _info(learner, "sensor.dishwasher")
    assert info["windows"] >= 80
    assert info["status"] == STATUS_NO_EFFECT
    assert all(h == 0.0 for h in heats)


def test_a_constant_load_never_touches_the_model():
    """A fridge or server sits on its usual load: no excitation, no effect, no device heat."""
    learner = PowerGainLearner()
    heats = _simulate(learner, {"sensor.fridge": (lambda _t: 0.08, 1.2)}, days=8)
    info = _info(learner, "sensor.fridge")
    assert info["windows"] == 0
    assert info["status"] == STATUS_NO_EFFECT
    assert all(h == pytest.approx(0.0, abs=1e-9) for h in heats)


def test_two_loads_running_together_keep_their_own_heat():
    learner = PowerGainLearner()
    loads = {
        "sensor.pc": (_office_pc, 1.2),
        # overlaps the PC from 12 to 14 and also runs alone in the evening, gives no room heat
        "sensor.boiler_plug": (lambda t: 1.0 if 12 <= t % 24 < 14 or 18 <= t % 24 < 20 else 0.0, 0.0),
    }
    _simulate(learner, loads, days=12)
    pc, plug = _info(learner, "sensor.pc"), _info(learner, "sensor.boiler_plug")
    assert pc["status"] == STATUS_ACTIVE
    assert pc["gain"] == pytest.approx(1.2, rel=0.25)
    assert plug["status"] != STATUS_ACTIVE
    assert abs(plug["gain"]) < 0.3


def test_heating_windows_teach_nothing():
    learner = PowerGainLearner()
    _simulate(learner, {"sensor.pc": (_office_pc, 1.2)}, days=3, mode=MODE_HEATING)
    assert _info(learner, "sensor.pc")["windows"] == 0
    assert _info(learner, "sensor.pc")["status"] == STATUS_LEARNING


def test_a_window_needs_every_reading_and_an_undisturbed_room():
    learner = PowerGainLearner()
    learner.begin_cycle("r", ["sensor.pc", "sensor.tv"], {"sensor.pc": 0.4}, DT)
    learner.observe("r", model=ROOM, mode=MODE_IDLE, disturbed=False, current_temp=20.0, T_outdoor=5.0, dt_minutes=DT)
    assert learner._rooms["r"].window is None
    learner.begin_cycle("r", ["sensor.pc", "sensor.tv"], {"sensor.pc": 0.4, "sensor.tv": 0.1}, DT)
    learner.observe("r", model=ROOM, mode=MODE_IDLE, disturbed=False, current_temp=20.0, T_outdoor=5.0, dt_minutes=DT)
    assert learner._rooms["r"].window is not None
    learner.observe("r", model=ROOM, mode=MODE_IDLE, disturbed=True, current_temp=20.0, T_outdoor=5.0, dt_minutes=DT)
    assert learner._rooms["r"].window is None
    learner.begin_cycle("r", ["sensor.pc", "sensor.tv"], {"sensor.pc": 0.4, "sensor.tv": 0.1}, DT)
    learner.observe("r", model=ROOM, mode=MODE_IDLE, disturbed=False, current_temp=20.0, T_outdoor=5.0, dt_minutes=DT)
    learner.interrupt("r")
    assert learner._rooms["r"].window is None
    learner.interrupt("unknown")


def test_an_active_sensor_drops_out_when_it_stops_helping():
    learner = PowerGainLearner()
    _simulate(learner, {"sensor.pc": (_office_pc, 1.2)}, days=6)
    assert learner.status("r", "sensor.pc") == STATUS_ACTIVE
    # the device moved to another room: its power no longer heats this one
    _simulate(learner, {"sensor.pc": (_office_pc, 0.0)}, days=10, seed=2)
    assert learner.status("r", "sensor.pc") != STATUS_ACTIVE


def test_room_without_sensors_has_no_state():
    learner = PowerGainLearner()
    assert learner.begin_cycle("r", [], {}, DT) == 0.0
    learner.observe("r", model=ROOM, mode=MODE_IDLE, disturbed=False, current_temp=20.0, T_outdoor=5.0, dt_minutes=DT)
    assert learner.to_dict() == {}
    assert learner.info("r") == []
    assert learner.device_heat("r") == 0.0
    assert learner.status("r", "sensor.pc") == STATUS_LEARNING


def test_removing_a_sensor_forgets_it_and_keeps_the_others():
    learner = PowerGainLearner()
    _simulate(learner, {"sensor.pc": (_office_pc, 1.2), "sensor.tv": (_evening_load, 0.5)}, days=4)
    pc_gain = _info(learner, "sensor.pc")["gain"]
    learner.begin_cycle("r", ["sensor.pc"], {"sensor.pc": 0.0}, DT)
    assert [i["entity_id"] for i in learner.info("r")] == ["sensor.pc"]
    assert _info(learner, "sensor.pc")["gain"] == pc_gain
    learner.begin_cycle("r", [], {}, DT)
    assert learner.info("r") == []


def test_persistence_round_trip():
    learner = PowerGainLearner()
    _simulate(learner, {"sensor.pc": (_office_pc, 1.2)}, days=6)
    restored = PowerGainLearner.from_dict(learner.to_dict())
    assert restored.to_dict() == learner.to_dict()
    restored.begin_cycle("r", ["sensor.pc"], {"sensor.pc": 0.4}, DT)
    assert restored.status("r", "sensor.pc") == STATUS_ACTIVE
    assert restored.device_heat("r") > 0.0


@pytest.mark.parametrize(
    "data",
    [
        None,
        "bad",
        {"r": {"sensors": ["a"], "gain": [1.0], "P": [[1.0, 0.0]], "state": {"a": {}}}},
        {"r": {"sensors": ["a"], "gain": [1.0], "P": [[1.0]], "state": {}}},
        {"r": {"sensors": ["a"], "gain": ["x"], "P": [[1.0]], "state": {"a": {}}}},
    ],
)
def test_malformed_state_starts_over(data):
    assert PowerGainLearner.from_dict(data).to_dict() == {}


def test_reset_and_remove():
    learner = PowerGainLearner()
    learner.begin_cycle("r", ["sensor.pc"], {"sensor.pc": 0.4}, DT)
    learner.reset("r")
    assert learner.to_dict() == {}
    learner.begin_cycle("r", ["sensor.pc"], {"sensor.pc": 0.4}, DT)
    learner.remove_room("r")
    assert learner.to_dict() == {}


def test_needs_enough_windows_before_it_counts():
    learner = PowerGainLearner()
    _simulate(learner, {"sensor.pc": (_office_pc, 1.2)}, days=1)
    info = _info(learner, "sensor.pc")
    assert info["windows"] < POWER_ACTIVE_MIN_WINDOWS
    assert info["status"] == STATUS_LEARNING
    assert info["windows_needed"] == POWER_ACTIVE_MIN_WINDOWS
