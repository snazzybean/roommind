"""Invariants checked over a whole run. Each returns a list of violations.

Add one: write ``def name(run, **args) -> list[Violation]`` and register it in INVARIANTS.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .load import Interval, RunData
from .metrics import ACTIVE_MODES, decided_mode

EXEMPT_MARGIN_S = 90.0
COORDINATOR_CYCLE_S = 35.0


@dataclass
class Violation:
    t: float
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {"t": self.t, "detail": self.detail}


def _groups(run: RunData) -> list[dict[str, Any]]:
    return list(run.settings().get("compressor_groups") or [])


def _room_of(run: RunData, eid: str) -> str | None:
    for d in run.scenario.all_devices():
        if d.entity_id == eid:
            return d.room
    return None


def _exempt(run: RunData, area: str | None, t: float, windows: dict[str, list[Interval]]) -> str | None:
    """Ends caused by a window pause or an explicit off are allowed to cut a run short."""
    if area is None:
        return None
    for iv in windows.get(area, []):
        if iv.start - EXEMPT_MARGIN_S <= t <= iv.end + EXEMPT_MARGIN_S:
            return "window"
    obs = run.observer_at(t + 35)
    room = (obs or {}).get("rooms", {}).get(area) or {}
    if room.get("force_off"):
        return "force_off"
    return None


def min_run_respected(run: RunData, tolerance_s: float = 75.0) -> list[Violation]:
    """The shared compressor physically runs at least ``min_run_minutes`` (#436).

    Uses the ground truth (any member's compressor active), not the commanded mode: in
    #436 the mode stayed "heat" while the unit's own controller stopped the compressor.
    Samples are 1 min apart, hence the tolerance.
    """
    out: list[Violation] = []
    windows = run.window_open_intervals()
    for group in _groups(run):
        min_run = float(group.get("min_run_minutes", 15)) * 60
        members = list(group.get("members", []))
        rooms = {m: _room_of(run, m) for m in members}
        since: float | None = None
        for s in run.samples:
            on = any(s["devices"].get(m, {}).get("active") for m in members)
            if on and since is None:
                since = s["t"]
            elif not on and since is not None:
                length = s["t"] - since
                exempt = any(_exempt(run, rooms[m], s["t"], windows) for m in members)
                if length + tolerance_s < min_run and not exempt:
                    out.append(
                        Violation(
                            since,
                            f"group {group.get('id')}: compressor ran {length / 60:.0f} min < min_run {min_run / 60:.0f} min",
                        )
                    )
                since = None
    return out


def min_run_commanded(run: RunData, tolerance_s: float = 45.0) -> list[Violation]:
    """RoomMind keeps the group commanded on for ``min_run_minutes``.

    The minimum run protects the shared compressor, so it counts per group: a member
    may stop early while another member keeps the compressor running.
    """
    out: list[Violation] = []
    windows = run.window_open_intervals()
    for group in _groups(run):
        min_run = float(group.get("min_run_minutes", 15)) * 60
        members = list(group.get("members", []))
        edges: list[tuple[float, int, str]] = []
        for eid in members:
            for iv in run.commanded_modes(eid):
                if iv.value in ACTIVE_MODES:
                    edges.append((iv.start, 1, eid))
                    edges.append((iv.end, -1, eid))
        edges.sort(key=lambda e: (e[0], -e[1]))
        active = 0
        since = 0.0
        for t, delta, eid in edges:
            if delta > 0:
                if active == 0:
                    since = t
                active += 1
                continue
            active -= 1
            if active == 0 and t < run.end - 1:
                length = t - since
                if length + tolerance_s < min_run and not _exempt(run, _room_of(run, eid), t, windows):
                    out.append(
                        Violation(
                            since,
                            f"group {group.get('id')}: commanded on for {length / 60:.1f} min < min_run {min_run / 60:.0f} min (last off: {eid})",
                        )
                    )
    return out


def _active_targets_before(run: RunData, area: str, t: float) -> dict[str, Any] | None:
    """Room state at the last observer tick before ``t`` in which the room heated or cooled."""
    for o in reversed(run.observer):
        if o["t"] > t:
            continue
        room = o["rooms"].get(area) or {}
        if decided_mode(room) in ("heating", "cooling"):
            return room
    return None


# RoomMind's HOLD_OVERSHOOT_MARGIN: past target + this the hold throttles the unit to minimum.
HOLD_THROTTLE_MARGIN_K = 0.5


def min_run_hold_keeps_setpoint(run: RunData, tolerance_k: float = 0.05) -> list[Violation]:
    """While the min-run holds a unit on, RoomMind does not cut its setpoint back (#436).

    A heating setpoint lowered (cooling setpoint raised) during the hold stops units
    whose own sensor already reads the room as warm (cold) enough; in #436 the mode
    stayed "heat" while the compressor stopped. Allowed: the room target itself moved
    that way since the last active tick (eco override, vacation, schedule), the room
    ran past the far side of its band (documented band-overshoot rule), or, in a room
    without a far side (heat_only / cool_only or no target there), the room is
    ``HOLD_THROTTLE_MARGIN_K`` past the target and the new setpoint stays on the demand
    side of it (throttle to minimum instead of boosting on).
    """
    rooms_cfg = run.rooms_config()
    area_of: dict[str, str | None] = {}
    for group in _groups(run):
        for m in group.get("members", []):
            area_of[m] = _room_of(run, m)
    out: list[Violation] = []
    setpoint: dict[str, float] = {}
    mode: dict[str, str] = {}
    for c in run.commands:
        eid = c["entity_id"]
        if eid not in area_of or not str(c.get("result", "")).startswith("accepted"):
            continue
        data = c["data"]
        if data.get("hvac_mode"):
            mode[eid] = data["hvac_mode"]
        if c["service"] != "set_temperature" or data.get("temperature") is None:
            continue
        new = float(data["temperature"])
        prev = setpoint.get(eid)
        setpoint[eid] = new
        area = area_of[eid]
        if prev is None or area is None:
            continue
        # The observer polls after the coordinator tick that sent the command.
        obs = run.observer_at(c["t"] + 35) or {}
        room = obs.get("rooms", {}).get(area) or {}
        if not room.get("compressor_protection_active") or decided_mode(room) != "idle":
            continue
        heating = mode.get(eid) == "heat"
        cooling = mode.get(eid) == "cool"
        if not ((heating and new < prev - tolerance_k) or (cooling and new > prev + tolerance_k)):
            continue
        key = "heat_target" if heating else "cool_target"
        ref = _active_targets_before(run, area, c["t"]) or {}
        now_t, ref_t = room.get(key), ref.get(key)
        if now_t is not None and ref_t is not None:
            if (heating and now_t < ref_t - tolerance_k) or (cooling and now_t > ref_t + tolerance_k):
                continue
        climate_mode = (rooms_cfg.get(area) or {}).get("climate_mode", "auto")
        cur = room.get("current_temp")
        far = room.get("cool_target") if heating else room.get("heat_target")
        one_sided = far is None or climate_mode == ("heat_only" if heating else "cool_only")
        if cur is not None and now_t is not None and one_sided:
            if heating and cur >= now_t + HOLD_THROTTLE_MARGIN_K - 1e-6 and new >= now_t - tolerance_k:
                continue
            if cooling and cur <= now_t - HOLD_THROTTLE_MARGIN_K + 1e-6 and new <= now_t + tolerance_k:
                continue
        if cur is not None:
            if heating and climate_mode != "heat_only" and room.get("cool_target") is not None:
                if cur >= room["cool_target"]:
                    continue
            if cooling and climate_mode != "cool_only" and room.get("heat_target") is not None:
                if cur <= room["heat_target"]:
                    continue
        out.append(Violation(c["t"], f"{eid}: setpoint {prev} -> {new} during the min-run hold ({area} idle)"))
    return out


def min_off_respected(run: RunData, tolerance_s: float = 45.0) -> list[Violation]:
    out: list[Violation] = []
    for group in _groups(run):
        min_off = float(group.get("min_off_minutes", 5)) * 60
        for eid in group.get("members", []):
            modes = run.commanded_modes(eid)
            for prev, iv in zip(modes, modes[1:], strict=False):
                if iv.value not in ACTIVE_MODES and prev.value in ACTIVE_MODES:
                    nxt = iv.end
                    if nxt < run.end - 1 and iv.duration + tolerance_s < min_off:
                        out.append(
                            Violation(
                                iv.start, f"{eid} off for {iv.duration / 60:.1f} min < min_off {min_off / 60:.0f} min"
                            )
                        )
    return out


def target_never_empty(run: RunData) -> list[Violation]:
    """A controlled room always has a resolved target unless forced off (#419)."""
    out: list[Violation] = []
    controlled = {a for a, r in run.rooms_config().items() if r.get("devices") and not r.get("is_outdoor")}
    reported: set[str] = set()
    for o in run.observer:
        if o["t"] < run.start + 120:
            continue
        for area, room in o["rooms"].items():
            if area not in controlled or area in reported or room.get("force_off"):
                continue
            if (
                room.get("heat_target") is None
                and room.get("cool_target") is None
                and room.get("target_temp") in (None, "")
            ):
                out.append(Violation(o["t"], f"{area}: no target (mode={room.get('mode')})"))
                reported.add(area)
    return out


def no_cooling_below_outdoor_min(run: RunData, tolerance_k: float = 0.3) -> list[Violation]:
    """No cooling while outdoor < outdoor_cooling_min unless an override is active (#447, #295).

    RoomMind sees a rounded, noisy sensor; the tolerance keeps the true value at the
    threshold from counting.
    """
    limit = float(run.settings().get("outdoor_cooling_min", 16)) - tolerance_k
    out: list[Violation] = []
    for o in run.observer:
        s = run.sample_at(o["t"])
        if s is None:
            continue
        t_out = s["outdoor"]["temp"]
        for area, room in o["rooms"].items():
            if decided_mode(room) == "cooling" and t_out < limit and not room.get("override_active"):
                out.append(Violation(o["t"], f"{area} cooling at outdoor {t_out:.1f} < {limit}"))
                break
    return out[:20]


def setpoints_within_device_range(run: RunData) -> list[Violation]:
    """RoomMind never sends a setpoint outside the device's min/max (#29, #396)."""
    limits = {
        d.entity_id: (float(d.capabilities.get("min_temp", -1e9)), float(d.capabilities.get("max_temp", 1e9)))
        for d in run.scenario.all_devices()
    }
    out: list[Violation] = []
    for c in run.commands:
        lo, hi = limits.get(c["entity_id"], (-1e9, 1e9))
        for key in ("temperature", "target_temp_low", "target_temp_high"):
            v = c["data"].get(key)
            if v is not None and not lo <= float(v) <= hi:
                out.append(Violation(c["t"], f"{c['entity_id']} {key}={v} outside [{lo}, {hi}]"))
    return out


def no_full_cooling_at_target(run: RunData, tolerance_k: float = 0.0, after_s: float = 35.0) -> list[Violation]:
    """No AC gets its lowest setpoint while the room is at or below its cool target (#450).

    Only MPC rooms. With efficiency weights the plan's no-demand fallback did this inside
    a cooling min run. Not a default: with comfort weights a closed-form fraction that
    saturates on a badly learned model sends it too. The room state is read from the
    observer record right after the command (same cycle).
    """
    floors = {
        d.entity_id: (d.room, float(d.capabilities["min_temp"]))
        for d in run.scenario.all_devices()
        if "min_temp" in d.capabilities
    }
    out: list[Violation] = []
    for c in run.commands:
        dev = floors.get(c["entity_id"])
        sp = c["data"].get("temperature")
        if dev is None or sp is None or c["service"] != "set_temperature" or c["data"].get("hvac_mode") != "cool":
            continue
        area, floor = dev
        room = ((run.observer_at(c["t"] + after_s) or {}).get("rooms") or {}).get(area) or {}
        temp, cool = room.get("current_temp"), room.get("cool_target")
        if not room.get("mpc_active") or temp is None or cool is None:
            continue
        if float(sp) <= floor + 0.05 and temp <= cool + tolerance_k:
            out.append(Violation(c["t"], f"{c['entity_id']} set to {sp} with {area} at {temp} (cool target {cool})"))
    return out


def no_rejected_commands(run: RunData) -> list[Violation]:
    return [
        Violation(c["t"], f"{c['entity_id']} {c['service']} {c['data']} -> {c['result']}")
        for c in run.commands
        if str(c.get("result", "")).startswith("rejected")
    ]


def window_open_pauses(run: RunData, grace_s: float = 120.0) -> list[Violation]:
    """While a window is open (past its delay) the room is idle (#437).

    Intervals end at the first sample that shows the window closed, so the real close
    lies up to one sample interval earlier; RoomMind may already resume there.
    """
    out: list[Violation] = []
    rooms_cfg = run.rooms_config()
    sample_s = float(run.scenario.sample_interval)
    for area, intervals in run.window_open_intervals().items():
        cfg = rooms_cfg.get(area) or {}
        if not cfg.get("window_sensors"):
            continue
        delay = float(cfg.get("window_open_delay", 0)) + grace_s
        for iv in intervals:
            for o in run.observer:
                if iv.start + delay <= o["t"] <= iv.end - sample_s:
                    room = o["rooms"].get(area) or {}
                    if room.get("mode") not in ("idle", None):
                        out.append(
                            Violation(
                                o["t"],
                                f"{area} {room.get('mode')} with window open since {(o['t'] - iv.start) / 60:.0f} min",
                            )
                        )
                        break
    return out


def no_heat_and_cool_same_group(run: RunData) -> list[Violation]:
    out: list[Violation] = []
    for group in _groups(run):
        members = group.get("members", [])
        for s in run.samples:
            actions = {s["devices"][m]["action"] for m in members if m in s["devices"] and s["devices"][m]["active"]}
            if "heating" in actions and "cooling" in actions:
                out.append(Violation(s["t"], f"group {group.get('id')}: heating and cooling at once"))
                break
    return out


def no_commands_when_climate_off(run: RunData) -> list[Violation]:
    """With climate control off RoomMind sends no device commands (#36, #74, #365).

    Handing a pinned valve back (degree to 100, #413) is the exception: the TRV could
    not regulate on its own otherwise.
    """
    settings = run.settings()
    rooms = run.rooms_config()
    off_rooms = {a for a, r in rooms.items() if r.get("climate_control_enabled") is False}
    if settings.get("climate_control_active") is False:
        off_rooms = set(rooms)
    devices = {d.entity_id for d in run.scenario.all_devices() if d.room in off_rooms}
    devices |= {n for d in run.scenario.all_devices() if d.room in off_rooms for n in d.valve_numbers().values()}
    return [
        Violation(c["t"], f"{c['entity_id']} got {c['service']}")
        for c in run.commands
        if c["entity_id"] in devices and not _valve_release(c)
    ]


def _valve_release(command: dict) -> bool:
    return bool(command["entity_id"].startswith("number.") and (command.get("data") or {}).get("value") == 100)


def max_commands_per_hour(run: RunData, limit: float = 12.0, entity_id: str | None = None) -> list[Violation]:
    """No device gets more than ``limit`` commands in any sliding hour (#416 beeps, #317)."""
    out: list[Violation] = []
    by_dev: dict[str, list[float]] = {}
    for c in run.commands:
        if entity_id and c["entity_id"] != entity_id:
            continue
        by_dev.setdefault(c["entity_id"], []).append(c["t"])
    for eid, times in by_dev.items():
        j = 0
        for i, t in enumerate(times):
            while times[j] < t - 3600:
                j += 1
            if i - j + 1 > limit:
                out.append(Violation(t, f"{eid}: {i - j + 1} commands in the hour before"))
                break
    return out


def hold_shows_running_unit(run: RunData) -> list[Violation]:
    """During a min-run hold the room shows what the held unit does, plus the time left (#452).

    Only ticks where the room's group members report the same running action in the
    sample at the observer tick and the one before it count (state lag around a stop).
    The observer reads the live state of the last coordinator cycle, so ``until`` may
    lie up to one cycle before the tick.
    """
    shown = {"heating": "heating", "preheating": "heating", "cooling": "cooling"}
    members_of: dict[str, list[str]] = {}
    for group in _groups(run):
        for m in group.get("members", []):
            area = _room_of(run, m)
            if area is not None:
                members_of.setdefault(area, []).append(m)
    out: list[Violation] = []
    for o in run.observer:
        for area, room in o["rooms"].items():
            if room.get("compressor_protection_reason") != "min_run" or decided_mode(room) != "idle":
                continue
            until = room.get("compressor_protection_until")
            if until is None or until <= o["t"] - COORDINATOR_CYCLE_S:
                out.append(Violation(o["t"], f"{area}: min-run hold without time left ({until})"))
                continue
            actions = set()
            for s in (run.sample_at(o["t"]), run.sample_at(o["t"] - COORDINATOR_CYCLE_S)):
                for m in members_of.get(area, []):
                    dev = (s or {}).get("devices", {}).get(m) or {}
                    if dev.get("mode") not in (None, "off"):
                        actions.add(shown.get(dev.get("action"), "idle"))
            if len(actions) == 1 and (expected := actions.pop()) != room.get("mode"):
                out.append(Violation(o["t"], f"{area}: held unit {expected}, room shows {room.get('mode')}"))
    return out[:20]


INVARIANTS: dict[str, Callable[..., list[Violation]]] = {
    f.__name__: f
    for f in (
        min_run_respected,
        min_run_commanded,
        min_run_hold_keeps_setpoint,
        hold_shows_running_unit,
        min_off_respected,
        target_never_empty,
        no_cooling_below_outdoor_min,
        setpoints_within_device_range,
        no_full_cooling_at_target,
        no_rejected_commands,
        window_open_pauses,
        no_heat_and_cool_same_group,
        no_commands_when_climate_off,
        max_commands_per_hour,
    )
}
DEFAULT_INVARIANTS = (
    "target_never_empty",
    "setpoints_within_device_range",
    "no_cooling_below_outdoor_min",
    "no_heat_and_cool_same_group",
)
