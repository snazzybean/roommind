"""Invariants against synthetic timelines (the oracle autonomous runs rely on)."""

from __future__ import annotations

from helpers import scenario

from roommind_sim.analysis.invariants import (
    hold_shows_running_unit,
    max_commands_per_hour,
    min_run_commanded,
    min_run_hold_keeps_setpoint,
    min_run_respected,
    no_cooling_below_outdoor_min,
    no_cover_lowered_over_open_window,
    no_full_cooling_at_target,
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


def test_window_open_pause_allows_resume_between_close_and_next_sample():
    """Windows close between two samples; a resume in that gap is not a violation."""
    run = _run([False] * 30, windows=[False] * 5 + [True] * 15 + [False] * 10)
    end = run.start + 60 * 21  # first sample that shows the window closed
    run.observer = [{"t": end - 30, "rooms": {"r": {"mode": "heating"}}}]
    assert window_open_pauses(run) == []
    run.observer = [{"t": end - 90, "rooms": {"r": {"mode": "heating"}}}]
    assert len(window_open_pauses(run)) == 1


def test_command_rate():
    run = _run([False] * 70, commands=[(30 * i, "set_temperature", {"temperature": 22}) for i in range(20)])
    assert max_commands_per_hour(run, limit=12)
    assert not max_commands_per_hour(run, limit=30)


def test_commanded_min_run_counts_per_group():
    rooms = {
        "a": {"devices": [{"entity_id": "climate.a", "profile": "generic_split_ac"}]},
        "b": {"devices": [{"entity_id": "climate.b", "profile": "generic_split_ac"}]},
    }
    scn = load_scenario_dict(scenario(rooms))
    t0 = scn.start
    cmds = [
        (0, "climate.a", "heat"),
        (60, "climate.b", "heat"),
        (300, "climate.a", "off"),  # a stops after 5 min, b keeps the compressor running
        (1200, "climate.b", "off"),
    ]
    events = [
        {
            "t": t0 + t,
            "type": "command",
            "entity_id": e,
            "service": "set_hvac_mode",
            "data": {"hvac_mode": m},
            "result": "accepted",
        }
        for t, e, m in cmds
    ]
    storage = {
        "settings": {"compressor_groups": [{"id": "g", "members": ["climate.a", "climate.b"], "min_run_minutes": 15}]},
        "rooms": {},
    }
    run = RunData(None, scn, [], [], events, t0 + 3600, storage)  # type: ignore[arg-type]
    assert min_run_commanded(run) == []
    events[3]["t"] = t0 + 600  # whole group off after 10 min
    assert len(min_run_commanded(run)) == 1


def _hold_run(setpoints, heat_targets=(21.0, 21.0), cool_target=None, climate_mode="heat_only", current_temp=21.2):  # noqa: ANN001
    """Heat at 30 °C, the room goes idle into the min-run hold, then ``setpoints`` are sent."""
    run = _run(
        [False] * 30,
        commands=[(60, "set_temperature", {"temperature": 30.0, "hvac_mode": "heat"})]
        + [(120 + 30 * i, "set_temperature", {"temperature": v}) for i, v in enumerate(setpoints)],
    )
    run.storage["rooms"]["r"]["climate_mode"] = climate_mode
    room = {"heat_target": heat_targets[0], "cool_target": cool_target, "current_temp": current_temp}
    run.observer = [{"t": run.start + 90, "rooms": {"r": {**room, "mode": "heating"}}}] + [
        {
            "t": run.start + 150 + 30 * i,
            "rooms": {
                "r": {**room, "heat_target": heat_targets[1], "mode": "idle", "compressor_protection_active": True}
            },
        }
        for i in range(len(setpoints))
    ]
    return run


def test_hold_must_not_cut_the_setpoint_to_the_target_436():
    assert len(min_run_hold_keeps_setpoint(_hold_run([21.0]))) == 1
    assert min_run_hold_keeps_setpoint(_hold_run([])) == []
    assert min_run_hold_keeps_setpoint(_hold_run([30.0])) == []


def test_hold_passes_a_lowered_target_on():
    assert min_run_hold_keeps_setpoint(_hold_run([17.0], heat_targets=(21.0, 17.0))) == []


def test_hold_band_overshoot_may_send_the_target():
    run = _hold_run([21.0], cool_target=21.5, climate_mode="auto", current_temp=21.5)
    assert min_run_hold_keeps_setpoint(run) == []


def test_hold_may_throttle_past_the_margin_but_not_below_the_target():
    assert min_run_hold_keeps_setpoint(_hold_run([23.0], current_temp=21.5)) == []
    assert min_run_hold_keeps_setpoint(_hold_run([21.0], current_temp=21.6)) == []
    assert len(min_run_hold_keeps_setpoint(_hold_run([23.0], current_temp=21.4))) == 1
    assert len(min_run_hold_keeps_setpoint(_hold_run([20.0], current_temp=21.6))) == 1


def test_hold_throttle_is_not_allowed_in_a_room_with_both_sides():
    run = _hold_run([23.0], cool_target=24.0, climate_mode="auto", current_temp=21.6)
    assert len(min_run_hold_keeps_setpoint(run)) == 1
    run = _hold_run([23.0], cool_target=None, climate_mode="auto", current_temp=21.6)
    assert min_run_hold_keeps_setpoint(run) == []


def test_hold_is_found_by_the_decision_while_the_room_shows_the_running_unit_452():
    run = _hold_run([21.0])
    for o in run.observer[1:]:
        o["rooms"]["r"].update(mode="heating", commanded_mode="idle")
    assert len(min_run_hold_keeps_setpoint(run)) == 1


def _shown_hold_run(shown: str, action: str = "heating", left_s: float | None = 600.0) -> RunData:
    run = _run([True] * 10)
    for smp in run.samples:
        smp["devices"][AC].update(mode="heat", action=action)
    t = run.start + 300
    room = {
        "mode": shown,
        "commanded_mode": "idle",
        "compressor_protection_reason": "min_run",
        "compressor_protection_until": t + left_s if left_s is not None else None,
    }
    run.observer = [{"t": t, "rooms": {"r": room}}]
    return run


def test_hold_shows_the_running_unit_and_the_time_left_452():
    assert hold_shows_running_unit(_shown_hold_run("heating")) == []
    assert hold_shows_running_unit(_shown_hold_run("idle", action="idle")) == []
    found = hold_shows_running_unit(_shown_hold_run("idle"))
    assert len(found) == 1 and "held unit heating, room shows idle" in found[0].detail
    found = hold_shows_running_unit(_shown_hold_run("heating", left_s=None))
    assert len(found) == 1 and "without time left" in found[0].detail


def test_setpoint_drop_outside_the_hold_is_fine():
    run = _hold_run([21.0])
    for o in run.observer:
        o["rooms"]["r"]["compressor_protection_active"] = False
    assert min_run_hold_keeps_setpoint(run) == []


def _cooling_observer(t: float, temp: float) -> dict:
    return {"t": t, "rooms": {"r": {"mpc_active": True, "current_temp": temp, "cool_target": 24.5}}}


def test_lowest_cool_setpoint_at_the_target_450():
    probe = _run([False] * 10)
    t0 = probe.scenario.start
    cool = {"temperature": 16.0, "hvac_mode": "cool"}
    observer = [_cooling_observer(t0 + 30, 24.4), _cooling_observer(t0 + 330, 24.7)]
    at_target = _run([False] * 10, commands=[(10, "set_temperature", cool)], observer=observer)
    assert no_full_cooling_at_target(at_target)
    above = _run([False] * 10, commands=[(310, "set_temperature", cool)], observer=observer)
    assert not no_full_cooling_at_target(above)
    gentle = _run([False] * 10, commands=[(10, "set_temperature", {**cool, "temperature": 23.3})], observer=observer)
    assert not no_full_cooling_at_target(gentle)


def _cover_run(commands, windows, position=100.0, window_sensors=True) -> RunData:  # noqa: ANN001
    cover = "cover.r_shutter"
    rooms = {
        "r": {
            "devices": [{"entity_id": AC, "profile": "generic_split_ac"}],
            "windows": [{"sensor": "binary_sensor.r_win"}],
            "covers": [{"entity_id": cover, "profile": "roller_shutter"}],
        }
    }
    scn = load_scenario_dict(scenario(rooms))
    t0 = scn.start
    samples = [
        {
            "t": t0 + 60 * (i + 1),
            "outdoor": {"temp": 5.0},
            "rooms": {"r": {"t_air": 20.0, "windows_open": 1 if w else 0}},
            "devices": {AC: {"active": False, "action": "idle", "electric_w": 0, "heat_w": 0}},
            "covers": {cover: {"position": position}},
        }
        for i, w in enumerate(windows)
    ]
    room_cfg = {"window_sensors": ["binary_sensor.r_win"]} if window_sensors else {}
    events = [
        {"t": t0 + t, "type": "command", "entity_id": cover, "service": svc, "data": data, "result": "accepted"}
        for t, svc, data in commands
    ]
    end = t0 + 60 * (len(windows) + 1)
    return RunData(None, scn, samples, [], events, end, {"settings": {}, "rooms": {"r": room_cfg}})  # type: ignore[arg-type]


def test_cover_lowered_over_open_window():
    windows = [False] * 5 + [True] * 10 + [False] * 5
    down = [(600, "set_cover_position", {"position": 0})]
    assert len(no_cover_lowered_over_open_window(_cover_run(down, windows))) == 1
    assert len(no_cover_lowered_over_open_window(_cover_run([(600, "close_cover", {})], windows))) == 1
    # raising, after the window closed, or right at the opening (cycle had not seen it yet)
    assert (
        no_cover_lowered_over_open_window(_cover_run([(600, "set_cover_position", {"position": 100})], windows, 40.0))
        == []
    )
    assert no_cover_lowered_over_open_window(_cover_run([(1080, "set_cover_position", {"position": 0})], windows)) == []
    assert no_cover_lowered_over_open_window(_cover_run([(370, "set_cover_position", {"position": 0})], windows)) == []
    # rooms without window sensors in RoomMind are not checked
    assert no_cover_lowered_over_open_window(_cover_run(down, windows, window_sensors=False)) == []
