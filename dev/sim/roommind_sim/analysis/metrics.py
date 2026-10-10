"""Metrics per room and device, computed from the ground truth and the service log."""

from __future__ import annotations

from typing import Any

from .load import RunData

ACTIVE_MODES = ("heat", "cool", "heat_cool", "auto", "dry", "on")


def compute_metrics(run: RunData) -> dict[str, Any]:
    duration_h = max(1e-9, (run.end - run.start) / 3600)
    return {
        "duration_h": round(duration_h, 3),
        "rooms": {area: _room_metrics(run, area) for area in run.scenario.rooms},
        "devices": {eid: _device_metrics(run, eid, duration_h) for eid in _device_ids(run)},
        "model": _model_metrics(run),
    }


def _device_ids(run: RunData) -> list[str]:
    return [d.entity_id for d in run.scenario.all_devices()]


def _room_metrics(run: RunData, area: str) -> dict[str, Any]:
    under = over = in_band = covered = 0.0
    pred_err: list[float] = []
    prev_t = None
    for s in run.samples:
        if prev_t is None:
            prev_t = s["t"]
            continue
        dt_h = (s["t"] - prev_t) / 3600
        prev_t = s["t"]
        obs = run.observer_at(s["t"])
        room = (obs or {}).get("rooms", {}).get(area)
        t_air = s["rooms"][area]["t_air"]
        if not room:
            continue
        heat = room.get("heat_target")
        cool = room.get("cool_target")
        if heat is None and cool is None:
            continue
        covered += dt_h
        if heat is not None and t_air < heat:
            under += (heat - t_air) * dt_h
        if cool is not None and t_air > cool:
            over += (t_air - cool) * dt_h
        if (heat is None or t_air >= heat - 0.5) and (cool is None or t_air <= cool + 0.5):
            in_band += dt_h
    for o in run.observer:
        room = o["rooms"].get(area) or {}
        pred = room.get("predicted_temp")
        if pred is None:
            continue
        later = run.sample_at(o["t"] + 1800)
        if later and later["t"] > o["t"] + 1700:
            pred_err.append(abs(later["rooms"][area]["t_air"] - pred))
    temps = [s["rooms"][area]["t_air"] for s in run.samples]
    return {
        "undershoot_kh": round(under, 3),
        "overshoot_kh": round(over, 3),
        "in_band_pct": round(100 * in_band / covered, 1) if covered else None,
        "temp_min": round(min(temps), 2) if temps else None,
        "temp_max": round(max(temps), 2) if temps else None,
        "prediction_mae_30m": round(sum(pred_err) / len(pred_err), 3) if pred_err else None,
    }


def _device_metrics(run: RunData, eid: str, duration_h: float) -> dict[str, Any]:
    cmds = [c for c in run.commands if c["entity_id"] == eid]
    rejected = [c for c in cmds if str(c.get("result", "")).startswith("rejected")]
    noop = [c for c in cmds if c.get("result") == "accepted:no_change"]
    modes = run.commanded_modes(eid)
    runs = [iv for iv in modes if iv.value in ACTIVE_MODES]
    electric_wh = heat_wh = active_h = 0.0
    starts = 0
    prev = None
    was_active = False
    for s in run.samples:
        d = s["devices"].get(eid)
        if d is None:
            continue
        if prev is not None:
            dt_h = (s["t"] - prev) / 3600
            electric_wh += d["electric_w"] * dt_h
            heat_wh += d["heat_w"] * dt_h
            if d["active"]:
                active_h += dt_h
        if d["active"] and not was_active:
            starts += 1
        was_active = d["active"]
        prev = s["t"]
    days = max(duration_h / 24, 1e-9)
    return {
        "commands": len(cmds),
        "commands_per_hour": round(len(cmds) / duration_h, 2),
        "redundant_commands": len(noop),
        "rejected_commands": len(rejected),
        "rejections": sorted({c["result"] for c in rejected}),
        "commanded_runs": len(runs),
        "shortest_run_min": round(min(iv.duration for iv in runs) / 60, 1) if runs else None,
        "device_starts": starts,
        "starts_per_day": round(starts / days, 2),
        "active_h": round(active_h, 2),
        "electric_kwh": round(electric_wh / 1000, 3),
        "heat_kwh": round(heat_wh / 1000, 3),
    }


def _model_metrics(run: RunData) -> dict[str, Any]:
    """RoomMind's learned EKF parameters next to the simulation's lumped ground truth."""
    from ..physics.zone import ZoneParams

    thermal = run.storage.get("thermal_data") or {}
    out: dict[str, Any] = {}
    for area, room in run.scenario.rooms.items():
        truth = ZoneParams.from_thermal(room.thermal, sum(w.area_m2 for w in room.windows)).equivalent_first_order()
        learned = thermal.get(area) or {}
        x = learned.get("x") or []
        out[area] = {
            "truth_alpha_per_h": round(truth["alpha_per_h"], 4),
            "truth_tau_h": round(truth["tau_h"], 1),
            "learned_alpha_per_h": round(x[1], 4) if len(x) > 1 else None,
            "learned_beta_h": round(x[2], 3) if len(x) > 2 else None,
            "learned_beta_c": round(x[3], 3) if len(x) > 3 else None,
            "learned_beta_s": round(x[4], 3) if len(x) > 4 else None,
            "n_updates": learned.get("n_updates"),
        }
    return out
