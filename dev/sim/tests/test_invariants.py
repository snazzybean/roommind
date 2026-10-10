"""Invariants against synthetic timelines (the oracle autonomous runs rely on)."""

from __future__ import annotations

from helpers import scenario

from roommind_sim.analysis.invariants import (
    max_commands_per_hour,
    min_run_commanded,
    min_run_respected,
    no_cooling_below_outdoor_min,
    target_never_empty,
    window_open_pauses,
)
from roommind_sim.analysis.load import RunData
from roommind_sim.scenario import load_scenario_dict

AC = "climate.r_ac"


def _run(active: list[bool], commands=(), observer=None, windows=None, settings=None) -> RunData:  # noqa: ANN001
    rooms = {
        "r": {
            "devices": [{"entity_id": AC, "profile": "generic_split_ac"}],
            "windows": [{"sensor": "binary_sensor.r_win"}],
        }
    }
    scn = load_scenario_dict(scenario(rooms))
    t0 = scn.start
    samples = []
    for i, on in enumerate(active):
        samples.append(
            {
                "t": t0 + 60 * (i + 1),
                "outdoor": {"temp": 5.0},
                "rooms": {"r": {"t_air": 20.0, "windows_open": 1 if windows and windows[i] else 0}},
                "devices": {AC: {"active": on, "action": "heating" if on else "idle", "electric_w": 0, "heat_w": 0}},
            }
        )
    end = t0 + 60 * (len(active) + 1)
    storage = {
        "settings": settings
        or {"compressor_groups": [{"id": "g", "members": [AC], "min_run_minutes": 15, "min_off_minutes": 5}]},
        "rooms": {"r": {"devices": [{"entity_id": AC}], "window_sensors": ["binary_sensor.r_win"]}},
    }
    events = [
        {"t": t0 + t, "type": "command", "entity_id": AC, "service": svc, "data": data, "result": "accepted"}
        for t, svc, data in commands
    ]
    return RunData(None, scn, samples, observer or [], events, end, storage)  # type: ignore[arg-type]


def test_physical_short_run_is_a_violation_even_if_mode_stays_heat():
    run = _run([False] * 5 + [True] * 8 + [False] * 30, commands=[(240, "set_hvac_mode", {"hvac_mode": "heat"})])
    assert min_run_commanded(run) == []  # mode never left heat
    found = min_run_respected(run)
    assert len(found) == 1 and "ran 8 min" in found[0].detail


def test_full_run_passes_and_tolerance_covers_sample_grid():
    assert min_run_respected(_run([True] * 14 + [False] * 10)) == []
    assert min_run_respected(_run([True] * 16 + [False] * 10)) == []


def test_window_open_exempts_short_run():
    active = [True] * 6 + [False] * 10
    windows = [False] * 5 + [True] * 11
    assert min_run_respected(_run(active, windows=windows)) == []


def test_commanded_short_run():
    run = _run(
        [False] * 40,
        commands=[(60, "set_hvac_mode", {"hvac_mode": "heat"}), (400, "set_hvac_mode", {"hvac_mode": "off"})],
    )
    assert len(min_run_commanded(run)) == 1


def test_target_never_empty_flags_missing_target_but_not_force_off():
    base = _run([False] * 10)
    t = base.start + 300
    base.observer = [
        {"t": t, "rooms": {"r": {"heat_target": None, "cool_target": None, "target_temp": None, "mode": "idle"}}}
    ]
    assert len(target_never_empty(base)) == 1
    base.observer[0]["rooms"]["r"]["force_off"] = True
    assert target_never_empty(base) == []


def test_cooling_below_outdoor_min_unless_override():
    run = _run([False] * 10)
    run.observer = [{"t": run.start + 300, "rooms": {"r": {"mode": "cooling", "override_active": False}}}]
    assert len(no_cooling_below_outdoor_min(run)) == 1
    run.observer[0]["rooms"]["r"]["override_active"] = True
    assert no_cooling_below_outdoor_min(run) == []


def test_window_open_pause():
    run = _run([False] * 30, windows=[False] * 5 + [True] * 25)
    run.observer = [{"t": run.start + 60 * 12, "rooms": {"r": {"mode": "heating"}}}]
    assert len(window_open_pauses(run)) == 1
    run.observer = [{"t": run.start + 60 * 12, "rooms": {"r": {"mode": "idle"}}}]
    assert window_open_pauses(run) == []


def test_command_rate():
    run = _run([False] * 70, commands=[(30 * i, "set_temperature", {"temperature": 22}) for i in range(20)])
    assert max_commands_per_hour(run, limit=12)
    assert not max_commands_per_hour(run, limit=30)
