"""Metrics per room and device, computed from the ground truth and the service log."""

from __future__ import annotations

from bisect import bisect_right
from collections import Counter, deque
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .load import RunData

ACTIVE_MODES = ("heat", "cool", "heat_cool", "auto", "dry", "on")


def decided_mode(room: dict[str, Any]) -> str | None:
    """RoomMind's own decision; ``mode`` shows what a held unit does (#452)."""
    return room.get("commanded_mode") or room.get("mode")


def compute_metrics(run: RunData) -> dict[str, Any]:
    duration_h = max(1e-9, (run.end - run.start) / 3600)
    return {
        "duration_h": round(duration_h, 3),
        "rooms": {area: _room_metrics(run, area) for area in run.scenario.rooms},
        "devices": {eid: _device_metrics(run, eid, duration_h) for eid in _device_ids(run)},
        "covers": {c.entity_id: _cover_metrics(run, c.entity_id, c.room) for c in _covers(run)},
        "model": _model_metrics(run),
    }


def _device_ids(run: RunData) -> list[str]:
    return [d.entity_id for d in run.scenario.all_devices()]


HEAT_BAND_K = 0.5
COAST_REWARM_K = 0.3
PREHEAT_LOOKAHEAD_S = 3 * 3600
HOLD_REF_LOOKBACK_S = 1800
# A room idle this far below its heat target counts toward idle_below_target_max_h
IDLE_BELOW_TARGET_K = 1.0


def _upcoming_heat(run: RunData, area: str) -> list[tuple[float, float | None]]:
    """``(t, max heat target over [t, t + PREHEAT_LOOKAHEAD_S])`` per observer record."""
    obs = [(o["t"], (o["rooms"].get(area) or {}).get("heat_target")) for o in run.observer]
    out: list[tuple[float, float | None]] = []
    window: deque[tuple[float, float]] = deque()
    for i in range(len(obs) - 1, -1, -1):
        t = obs[i][0]
        while window and window[0][0] > t + PREHEAT_LOOKAHEAD_S:
            window.popleft()
        heat = obs[i][1]
        if heat is not None:
            while window and window[-1][1] <= heat:
                window.pop()
            window.append((t, heat))
        out.append((t, window[0][1] if window else None))
    out.reverse()
    return out


def _room_metrics(run: RunData, area: str) -> dict[str, Any]:
    """Comfort metrics against the targets RoomMind reported.

    Heat overshoot is measured against the highest heat target of the next
    ``PREHEAT_LOOKAHEAD_S``, so warming up ahead of a comfort block is not overshoot.
    After that reference drops (schedule to eco, presence away), a heat-only room
    can only cool passively; with a long time constant it stays above the new
    target for hours. That excess is booked as ``heat_coast_kh``, not as
    ``heat_overshoot_kh``. The coast ends once the room is back in the band or
    warms ``COAST_REWARM_K`` above its lowest point since the drop, so heating
    during a setback still counts as overshoot. ``heat_above_band_kh`` keeps the
    plain total above the current target + band for comparison with older runs.

    ``hold_heat_over_max_k`` / ``hold_heat_over_kh`` cover only the compressor min-run
    hold (room idle, protection active): how far the held unit carried the room past
    its heat target. The reference is the highest heat target from
    ``HOLD_REF_LOOKBACK_S`` before to ``PREHEAT_LOOKAHEAD_S`` after, so neither a hold
    that runs into a setback nor one during pre-heating is booked against the eco target.

    ``heating_without_source_h``: RoomMind decided to heat, but heat source
    orchestration picked no source, so nothing ran.
    """
    under = over = over_heat = coast_kh = above_band = in_band = covered = 0.0
    upcoming = _upcoming_heat(run, area)
    upcoming_t = [u[0] for u in upcoming]
    prev_ref: float | None = None
    coast_min: float | None = None
    pred_err: list[float] = []
    hold_max = hold_kh = 0.0
    idle_below_since: float | None = None
    idle_below_max_h = 0.0
    unsourced_h = 0.0
    recent_heat: deque[tuple[float, float]] = deque()
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
        if decided_mode(room) == "heating" and room.get("active_heat_sources") == "none":
            unsourced_h += dt_h
        heat = room.get("heat_target")
        cool = room.get("cool_target")
        if heat is not None:
            while recent_heat and recent_heat[-1][1] <= heat:
                recent_heat.pop()
            recent_heat.append((s["t"], heat))
        while recent_heat and recent_heat[0][0] < s["t"] - HOLD_REF_LOOKBACK_S:
            recent_heat.popleft()
        if heat is None and cool is None:
            continue
        covered += dt_h
        if heat is not None and t_air < heat:
            under += (heat - t_air) * dt_h
        if (
            heat is not None
            and t_air < heat - IDLE_BELOW_TARGET_K
            and decided_mode(room) == "idle"
            and not room.get("window_open")
        ):
            idle_below_since = idle_below_since if idle_below_since is not None else s["t"]
            idle_below_max_h = max(idle_below_max_h, (s["t"] - idle_below_since) / 3600)
        else:
            idle_below_since = None
        if heat is not None:
            above_band += max(0.0, t_air - heat - HEAT_BAND_K) * dt_h
            k = bisect_right(upcoming_t, s["t"]) - 1
            ref = max(heat, upcoming[k][1] or heat) if k >= 0 else heat
            if room.get("compressor_protection_active") and decided_mode(room) == "idle":
                hold_ref = max(ref, recent_heat[0][1])
                hold_max = max(hold_max, t_air - hold_ref)
                hold_kh += max(0.0, t_air - hold_ref - HEAT_BAND_K) * dt_h
            if prev_ref is not None and ref < prev_ref and t_air > ref + HEAT_BAND_K:
                coast_min = t_air
            prev_ref = ref
            if coast_min is not None:
                coast_min = min(coast_min, t_air)
                if t_air <= ref + HEAT_BAND_K or t_air > coast_min + COAST_REWARM_K:
                    coast_min = None
            if t_air > ref + HEAT_BAND_K:
                excess = (t_air - ref - HEAT_BAND_K) * dt_h
                if coast_min is not None:
                    coast_kh += excess
                else:
                    over_heat += excess
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
        "heat_overshoot_kh": round(over_heat, 3),
        "heat_coast_kh": round(coast_kh, 3),
        "heat_above_band_kh": round(above_band, 3),
        "hold_heat_over_max_k": round(hold_max, 2),
        "hold_heat_over_kh": round(hold_kh, 3),
        "idle_below_target_max_h": round(idle_below_max_h, 2),
        "heating_without_source_h": round(unsourced_h, 2),
        "in_band_pct": round(100 * in_band / covered, 1) if covered else None,
        "temp_min": round(min(temps), 2) if temps else None,
        "temp_max": round(max(temps), 2) if temps else None,
        "prediction_mae_30m": round(sum(pred_err) / len(pred_err), 3) if pred_err else None,
    }


def _device_metrics(run: RunData, eid: str, duration_h: float) -> dict[str, Any]:
    """Per device; ``commands*`` count only the climate entity.

    ``valve_travel_per_day`` (TRVs): summed valve movement in full strokes per day, from the
    samples, so reversals within one sample interval are missed. ``valve_commands_per_hour``
    (TRVs with direct valve control): ``number.set_value`` calls on its opening/closing entities.
    """
    cmds = [c for c in run.commands if c["entity_id"] == eid]
    spec = next(d for d in run.scenario.all_devices() if d.entity_id == eid)
    numbers = set(spec.valve_numbers().values())
    valve_cmds = [c for c in run.commands if c["entity_id"] in numbers]
    travel: float | None = None
    last_valve: float | None = None
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
        if "valve" in d:
            if last_valve is not None:
                travel = (travel or 0.0) + abs(d["valve"] - last_valve)
            last_valve = d["valve"]
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
        # every device gets the keys: the report table takes its columns from the first row
        "valve_travel_per_day": round(travel / days, 2) if travel is not None else None,
        "valve_commands_per_hour": round(len(valve_cmds) / duration_h, 2) if numbers else None,
    }


def _covers(run: RunData) -> list[Any]:
    return [c for r in run.scenario.rooms.values() for c in r.covers]


COVER_SHADED_BELOW = 90  # position (%) below which a cover counts as shading
SUNNY_GHI_W_M2 = 600.0  # daily GHI peak that makes a day "sunny"
SUNNY_HOURS = (11, 17)  # local hours in which a sunny day should see shading


def _cover_metrics(run: RunData, eid: str, area: str) -> dict[str, Any]:
    """Moves RoomMind commanded and how the cover shaded, per local calendar day.

    Manual moves from the timeline are world actions, not service calls, so only
    RoomMind's own commands count; ``earliest_first_move_h`` / ``mean_first_move_h``
    are the local time (decimal hours) of the first command of a day.
    ``max_commands_per_day_unattended`` leaves out days with a timeline
    ``cover.manual`` on this cover (RoomMind reacting to it is expected).
    ``mean_shaded_position`` averages the position while shading (below
    ``COVER_SHADED_BELOW``). ``sunny_days_unshaded`` counts days with a GHI
    peak of at least ``SUNNY_GHI_W_M2`` on which the cover never shaded within
    ``SUNNY_HOURS``; ``shaded_while_heating_h`` the hours a shading cover overlapped
    with RoomMind reporting the room as heating.
    """
    tz = ZoneInfo(run.scenario.location.time_zone)

    def day(t: float) -> str:
        return datetime.fromtimestamp(t, tz).date().isoformat()

    cmds = [c for c in run.commands if c["entity_id"] == eid and str(c.get("result", "")).startswith("accepted")]
    per_day = Counter(day(c["t"]) for c in cmds)
    manual_days = {
        day(e["t"])
        for e in run.events
        if e.get("type") == "action"
        and e.get("action") == "cover.manual"
        and (e.get("args") or {}).get("entity_id") == eid
    }
    first_move: dict[str, float] = {}
    for c in cmds:
        local = datetime.fromtimestamp(c["t"], tz)
        first_move.setdefault(day(c["t"]), local.hour + local.minute / 60)
    shaded_h = heating_h = shaded_pos_h = 0.0
    ghi_peak: dict[str, float] = {}
    shaded_days: set[str] = set()
    prev: tuple[float, bool, float] | None = None
    for s in run.samples:
        d = day(s["t"])
        ghi_peak[d] = max(ghi_peak.get(d, 0.0), s.get("outdoor", {}).get("ghi", 0.0))
        cover = s.get("covers", {}).get(eid)
        shaded = cover is not None and cover["position"] < COVER_SHADED_BELOW
        if shaded and SUNNY_HOURS[0] <= datetime.fromtimestamp(s["t"], tz).hour < SUNNY_HOURS[1]:
            shaded_days.add(d)
        if prev is not None and prev[1]:
            dt_h = (s["t"] - prev[0]) / 3600
            shaded_h += dt_h
            shaded_pos_h += prev[2] * dt_h
            obs = run.observer_at(prev[0])
            if obs is not None and (obs["rooms"].get(area) or {}).get("mode") == "heating":
                heating_h += dt_h
        prev = (s["t"], shaded, cover["position"] if cover is not None else 100.0)
    sunny = [d for d, peak in ghi_peak.items() if peak >= SUNNY_GHI_W_M2]
    days = max((run.end - run.start) / 86400, 1e-9)
    return {
        "commands": len(cmds),
        "commands_per_day": round(len(cmds) / days, 2),
        "max_commands_per_day": max(per_day.values(), default=0),
        "max_commands_per_day_unattended": max((n for d, n in per_day.items() if d not in manual_days), default=0),
        "earliest_first_move_h": round(min(first_move.values()), 2) if first_move else None,
        "mean_first_move_h": round(sum(first_move.values()) / len(first_move), 2) if first_move else None,
        "shaded_h": round(shaded_h, 2),
        "mean_shaded_position": round(shaded_pos_h / shaded_h, 1) if shaded_h else None,
        "shaded_while_heating_h": round(heating_h, 2),
        "sunny_days": len(sunny),
        "sunny_days_unshaded": sum(1 for d in sunny if d not in shaded_days),
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
        beta_s = _truth_beta_s(run, area, truth["capacity_j_k"])
        beta_h = _truth_beta_device(run, area, truth["capacity_j_k"], "heating")
        beta_c = _truth_beta_device(run, area, truth["capacity_j_k"], "cooling")
        # learned / truth: the expectation form for heating and cooling rates
        ratio = {
            key: round(x[i] / truth_val, 2) if len(x) > i and truth_val else None
            for key, i, truth_val in (("beta_h_ratio", 2, beta_h), ("beta_c_ratio", 3, beta_c))
        }
        out[area] = {
            "truth_alpha_per_h": round(truth["alpha_per_h"], 4),
            "truth_tau_h": round(truth["tau_h"], 1),
            "truth_beta_s": round(beta_s, 3) if beta_s is not None else None,
            "truth_beta_h": round(beta_h, 3) if beta_h is not None else None,
            "truth_beta_c": round(beta_c, 3) if beta_c is not None else None,
            "learned_alpha_per_h": round(x[1], 4) if len(x) > 1 else None,
            "learned_beta_h": round(x[2], 3) if len(x) > 2 else None,
            "learned_beta_c": round(x[3], 3) if len(x) > 3 else None,
            "learned_beta_s": round(x[4], 3) if len(x) > 4 else None,
            **ratio,
            "n_updates": learned.get("n_updates"),
        }
    return out


def _truth_beta_device(run: RunData, area: str, capacity_j_k: float, action: str) -> float | None:
    """Heating/cooling rate in RoomMind's units (K/h at full label), from the room's devices.

    RoomMind labels a step with the share of its devices that report ``action``, so the
    truth is the delivered sensible power per unit of that share: sum(P) / sum(share).
    """
    eids = [d.entity_id for d in run.scenario.rooms[area].devices]
    sign = 1.0 if action == "heating" else -1.0
    power = share = 0.0
    for s in run.samples:
        devs = [s.get("devices", {}).get(eid) or {} for eid in eids]
        running = sum(1 for d in devs if d.get("action") == action)
        if not eids or not running:
            continue
        power += sum(max(0.0, sign * d.get("heat_w", 0.0)) for d in devs)
        share += running / len(eids)
    if share <= 0 or capacity_j_k <= 0:
        return None
    return power / share * 3600.0 / capacity_j_k


def _truth_beta_s(run: RunData, area: str, capacity_j_k: float) -> float | None:
    """Solar gain in RoomMind's units (K/h per kW/m² GHI, lumped capacity), fitted over the run.

    Uses the simulation's GHI; RoomMind estimates its own from cloud cover, so expect
    some ten percent difference even for a perfect filter.
    """
    sxy = sxx = 0.0
    for s in run.samples:
        ghi = s["outdoor"].get("ghi", 0.0) / 1000.0
        sxy += s["rooms"][area].get("solar_w", 0.0) * ghi
        sxx += ghi * ghi
    if sxx <= 0 or capacity_j_k <= 0:
        return None
    return sxy / sxx * 3600.0 / capacity_j_k
