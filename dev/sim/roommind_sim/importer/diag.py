"""Turn a RoomMind diagnostics export (+ optional history CSVs) into a scenario.

Two modes:
- ``closed`` (default): the simulation starts at the export time with the reporter's
  temperatures, EKF state and history; physics continues and RoomMind controls it.
  Use it to check a fix against the reporter's setup.
- ``replay``: the reporter's recorded room and outdoor temperatures are replayed
  exactly over the history period; devices are simulated but cannot change the
  room. Use it to reproduce a logic bug with identical inputs (e.g. #419).

Everything the export does not tell is guessed and listed under ``assumptions``.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from ..paths import REPO_ROOT, sim_home
from ..physics.zone import ZoneParams
from ..scenario.loader import load_profile

DEFAULT_BUILDING = "bestand_teilsaniert"
NAME_HINTS: list[tuple[str, str]] = [
    (r"sonoff|trvzb", "sonoff_trvzb"),
    (r"hmip|homematic", "homematic_ip_trv"),
    (r"shelly", "shelly_trv"),
    (r"dyson", "dyson_hp"),
    (r"ecobee", "ecobee"),
    (r"midea", "midea_ac_lan"),
    (r"daikin", "daikin_ac"),
    (r"broadlink|smartir|(^|_)ir(_|$)", "broadlink_ir_ac"),
]


class ImportError_(ValueError):
    pass


def ws_keys(command: str) -> set[str]:
    """Keys the RoomMind WS command accepts (read from its schema, so new fields just work)."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from custom_components.roommind import websocket_api as ws

    for obj in vars(ws).values():
        if getattr(obj, "_ws_command", None) == command:
            schema = obj._ws_schema
            return {str(getattr(k, "schema", k)) for k in schema.schema} - {"type", "id"}
    raise ImportError_(f"WS command {command} not found")


def import_diagnostics(
    diag_path: Path,
    history: list[Path] | None = None,
    *,
    name: str | None = None,
    mode: str = "closed",
    duration: str = "2d",
    out_root: Path | None = None,
) -> Path:
    raw = json.loads(diag_path.read_text())
    data = raw.get("data", raw)
    if "rooms" not in data or "settings" not in data:
        raise ImportError_("not a RoomMind diagnostics export (no rooms/settings)")
    name = name or f"import-{diag_path.stem}"
    out = (out_root or sim_home() / "imports") / name
    out.mkdir(parents=True, exist_ok=True)
    imp = _Importer(data, raw, out, mode, duration)
    scenario = imp.build(history or [])
    path = out / "scenario.yaml"
    header = (
        "# Imported from a RoomMind diagnostics export. Lives outside the repo on purpose:\n"
        "# reporter data never goes into git. Review the assumptions below.\n"
    )
    path.write_text(header + yaml.safe_dump(scenario, sort_keys=False, allow_unicode=True, width=120))
    return path


class _Importer:
    def __init__(self, data: dict[str, Any], raw: dict[str, Any], out: Path, mode: str, duration: str) -> None:
        self.d = data
        self.raw = raw
        self.out = out
        self.mode = mode
        self.duration = duration
        self.assumptions: list[str] = []
        self.external: set[str] = set()
        self.version = int(data.get("schema_version", 1))
        integ = data.get("integration") or {}
        self.unit = "F" if integ.get("ha_temp_unit") == "°F" else "C"
        self.defined: set[str] = set()

    def note(self, text: str) -> None:
        if text not in self.assumptions:
            self.assumptions.append(text)

    # --- pieces ---------------------------------------------------------------------------

    def location(self) -> dict[str, Any]:
        integ = self.d.get("integration") or {}
        if self.version >= 2 and integ.get("time_zone"):
            return {
                "latitude": float(integ.get("latitude", 50)),
                "longitude": float(integ.get("longitude", 10)),
                "time_zone": integ["time_zone"],
                "unit_system": integ.get("unit_system", "metric"),
            }
        self.note("location/time zone not in the export (schema v1): Europe/Berlin, 50N 10E assumed")
        return {
            "latitude": 50.0,
            "longitude": 10.0,
            "time_zone": "Europe/Berlin",
            "unit_system": "us_customary" if self.unit == "F" else "metric",
        }

    def history_rows(self, extra: list[Path]) -> dict[str, list[dict[str, str]]]:
        rows: dict[str, list[dict[str, str]]] = {}
        for area, items in (self.d.get("history_48h") or self.d.get("recent_history") or {}).items():
            norm = [{**r, "timestamp": r.get("timestamp") or r.get("ts", "")} for r in items]
            rows[area] = [r for r in norm if r["timestamp"]]
        for path in extra:
            area = _area_from_csv_name(path, list(self.d["rooms"]))
            with path.open() as fh:
                rows[area] = list(csv.DictReader(fh))
            self.note(f"history CSV {path.name} mapped to room {area}")
        for items in rows.values():
            items.sort(key=lambda r: float(r["timestamp"]))
        return rows

    def device(self, area: str, cfg: dict[str, Any], state: dict[str, Any], room_cfg: dict[str, Any]) -> dict[str, Any]:
        eid = cfg["entity_id"]
        dtype = cfg.get("type", "trv")
        profile = None
        for pattern, prof in NAME_HINTS:
            if re.search(pattern, eid):
                profile = prof
                break
        if profile is None:
            if dtype == "trv":
                hst = cfg.get("heating_system_type") or room_cfg.get("heating_system_type", "")
                profile = "ufh_zone" if hst == "underfloor" else "generic_trv"
            else:
                modes = state.get("hvac_modes") or []
                profile = (
                    "generic_heat_cool_hp"
                    if "heat_cool" in modes and not state.get("fan_modes")
                    else "generic_split_ac"
                )
            self.note(f"{eid}: device behaviour from generic profile {profile} (no name hint)")
        else:
            self.note(f"{eid}: profile {profile} chosen from the entity name")
        out: dict[str, Any] = {"entity_id": eid, "profile": profile}
        caps: dict[str, Any] = {"unit": self.unit}
        for key in ("hvac_modes", "min_temp", "max_temp", "target_temp_step", "fan_modes"):
            if state.get(key) not in (None, []):
                caps[key] = state[key]
        if state.get("target_temp_low") is not None or "heat_cool" in (state.get("hvac_modes") or []):
            caps["range_setpoint"] = state.get("target_temp_low") is not None
        out["capabilities"] = caps
        quirks: list[dict[str, Any]] = []
        if state.get("assumed_state"):
            quirks.append({"type": "no_state_feedback"})
        if quirks:
            out["quirks+"] = quirks
        ha_state = state.get("ha_state")
        if ha_state in (state.get("hvac_modes") or []):
            out["initial_mode"] = ha_state
        if state.get("temperature") is not None:
            temp = float(state["temperature"])
            out["initial_target_c"] = (temp - 32) * 5 / 9 if self.unit == "F" else temp
        if ha_state in ("unavailable", "not_found", "unknown"):
            self.note(f"{eid} was {ha_state} at export time; simulated as available")
        self.defined.add(eid)
        return out

    def room(
        self, area: str, diag: dict[str, Any], rows: list[dict[str, str]], helpers: dict[str, Any]
    ) -> dict[str, Any]:
        cfg = diag.get("config") or {}
        live = diag.get("live") or {}
        entities = diag.get("entities") or {}
        states = {s["entity_id"]: s for s in diag.get("device_states") or []}
        room: dict[str, Any] = {
            "name": cfg.get("display_name") or area.replace("_", " ").title(),
            "building": DEFAULT_BUILDING,
        }
        temp = live.get("current_temp")
        if temp is None and rows:
            temp = _num(rows[-1].get("room_temp"))
        room["initial"] = {"temperature": float(temp) if temp is not None else 20.0}
        if live.get("current_humidity") is not None:
            room["initial"]["humidity"] = float(live["current_humidity"])
        room["thermal"] = self.thermal(area, diag)
        room["devices"] = [
            self.device(area, dev, states.get(dev["entity_id"], {}), cfg) for dev in cfg.get("devices") or []
        ]
        sensors: dict[str, Any] = {}
        if cfg.get("temperature_sensor"):
            sensors["temperature"] = {"entity_id": cfg["temperature_sensor"]}
        if cfg.get("humidity_sensor"):
            sensors["humidity"] = {"entity_id": cfg["humidity_sensor"]}
        occ = [e for e in cfg.get("occupancy_sensors") or [] if e.startswith("binary_sensor.")]
        if occ:
            sensors["occupancy"] = {"entity_id": occ[0]}
            for extra in occ[1:]:
                self.external.add(extra)
                self.note(f"{extra}: only one occupancy sensor per room is simulated; extra ones are left undefined")
        for eid in (s.get("entity_id") for s in sensors.values()):
            self.defined.add(eid)
        room["sensors"] = sensors
        windows = []
        for eid in cfg.get("window_sensors") or []:
            if not eid.startswith("binary_sensor."):
                self.external.add(eid)
                continue
            windows.append({"orientation": "S", "area_m2": 1.5, "sensor": eid})
            self.defined.add(eid)
            if (entities.get(eid) or {}).get("state") == "on":
                self.note(f"{eid} was open at export time; it starts closed")
        if windows:
            self.note(f"{area}: window orientation/size unknown, 1.5 m2 facing south assumed")
        room["windows"] = windows
        covers = []
        for eid in cfg.get("covers") or []:
            covers.append({"entity_id": eid, "profile": "roller_shutter"})
            self.defined.add(eid)
        if covers:
            room["covers"] = covers
        for sched in cfg.get("schedules") or []:
            self.schedule(sched.get("entity_id", ""), diag, helpers)
        for key in ("schedule_selector_entity", "cover_schedule_selector_entity"):
            self.selector(cfg.get(key) or "", entities, helpers)
        return room

    def thermal(self, area: str, diag: dict[str, Any]) -> dict[str, Any]:
        model = diag.get("model_state") or {}
        x = model.get("x") or []
        alpha = x[1] if len(x) > 1 else (diag.get("model") or {}).get("alpha")
        if not alpha or alpha <= 0:
            self.note(f"{area}: no learned model; building preset {DEFAULT_BUILDING} as is")
            return {}
        preset = load_profile("buildings", DEFAULT_BUILDING, area)
        base = ZoneParams.from_thermal(preset, 1.5).equivalent_first_order()["alpha_per_h"]
        factor = max(0.2, min(5.0, float(alpha) / base))
        self.note(
            f"{area}: envelope scaled x{factor:.2f} so the lumped loss rate matches the learned alpha {alpha:.4f}/h"
        )
        return {
            "u_wall": round(preset["u_wall"] * factor, 3),
            "u_window": round(preset["u_window"] * factor, 3),
            "ach_infiltration": round(preset["ach_infiltration"] * factor, 3),
        }

    def schedule(self, eid: str, diag: dict[str, Any], helpers: dict[str, Any]) -> None:
        if not eid or eid in self.defined:
            return
        domain = eid.split(".", 1)[0]
        if domain != "schedule":
            self.external.add(eid)
            self.note(f"{eid}: non-schedule entity as schedule is not simulated")
            return
        blocks = (diag.get("schedule_blocks") or {}).get(eid)
        if blocks:
            spec = {day: [_block(b) for b in items] for day, items in blocks.items() if items}
        else:
            spec = {"daily": ["06:00-22:00"]}
            self.note(f"{eid}: schedule blocks not in the export, 06:00-22:00 daily assumed")
        helpers.setdefault("schedule", {})[eid] = spec
        self.defined.add(eid)

    def selector(self, eid: str, entities: dict[str, Any], helpers: dict[str, Any]) -> None:
        if not eid or eid in self.defined:
            return
        domain = eid.split(".", 1)[0]
        state = (entities.get(eid) or {}).get("state")
        if domain == "input_boolean":
            helpers.setdefault("input_boolean", {})[eid] = {"initial": state == "on"}
        elif domain == "input_number":
            init = _num(state) or 1
            helpers.setdefault("input_number", {})[eid] = {"min": 1, "max": 10, "step": 1, "initial": init}
        else:
            self.external.add(eid)
            return
        self.defined.add(eid)

    def people(self, settings: dict[str, Any], rooms: dict[str, Any], helpers: dict[str, Any]) -> list[dict[str, Any]]:
        ids = set(settings.get("presence_persons") or [])
        for r in rooms.values():
            ids |= set((r.get("config") or {}).get("presence_persons") or [])
        states = (self.d.get("presence") or {}).get("person_states") or {}
        people = []
        for eid in sorted(ids):
            domain, obj = eid.split(".", 1)
            home = states.get(eid, "home") not in ("not_home", "away", "off")
            if domain == "person":
                plan = {
                    "presence": {
                        "weekday": [f"{'home' if home else 'away'}@00:00"],
                        "weekend": [f"{'home' if home else 'away'}@00:00"],
                    }
                }
                people.append({"id": obj, "profile": "commuter", "plan": plan})
                self.note(
                    f"{eid}: presence fixed to '{'home' if home else 'away'}' (state at export); use person.leave/arrive to change it"
                )
                self.defined.add(eid)
            elif domain == "input_boolean":
                helpers.setdefault("input_boolean", {})[eid] = {"initial": home}
                self.defined.add(eid)
            else:
                self.external.add(eid)
                self.note(f"{eid}: presence entity of domain {domain} is not simulated")
        return people

    def filtered(self, data: dict[str, Any], command: str) -> dict[str, Any]:
        keys = ws_keys(command)
        dropped = sorted(k for k in data if k not in keys and k not in ("area_id",))
        if dropped:
            self.note(
                f"{command}: internal fields dropped: {', '.join(dropped[:12])}{' ...' if len(dropped) > 12 else ''}"
            )
        return {k: v for k, v in data.items() if k in keys}

    # --- assembly --------------------------------------------------------------------------

    def build(self, csvs: list[Path]) -> dict[str, Any]:
        d = self.d
        settings = d.get("settings") or {}
        rows = self.history_rows(csvs)
        helpers: dict[str, Any] = {}
        rooms = {area: self.room(area, diag, rows.get(area, []), helpers) for area, diag in d["rooms"].items()}
        people = self.people(settings, d["rooms"], helpers)
        outdoor_sensors = {}
        if settings.get("outdoor_temp_sensor"):
            outdoor_sensors["temperature"] = settings["outdoor_temp_sensor"]
            self.defined.add(settings["outdoor_temp_sensor"])
        if settings.get("outdoor_humidity_sensor"):
            outdoor_sensors["humidity"] = settings["outdoor_humidity_sensor"]
            self.defined.add(settings["outdoor_humidity_sensor"])
        weather: dict[str, Any] = {"profile": "temperate"}
        if settings.get("weather_entity"):
            weather["entity_id"] = settings["weather_entity"]
        last_ts = max((float(r[-1]["timestamp"]) for r in rows.values() if r), default=None)
        first_ts = min((float(r[0]["timestamp"]) for r in rows.values() if r), default=None)
        timeline: list[dict[str, Any]] = []
        replay: dict[str, Any] = {}
        weather_csv = self._weather_csv(rows)
        if self.mode == "replay":
            if first_ts is None or last_ts is None:
                raise ImportError_("replay needs history (schema v2 export or --history CSVs)")
            start: Any = datetime.fromtimestamp(first_ts, UTC).isoformat()
            duration = f"{int(last_ts - first_ts)}s"
            replay = {"rooms": {}}
            for area, items in rows.items():
                path = self.out / f"replay-{area}.csv"
                _write_csv(path, items, ["timestamp", "room_temp"])
                replay["rooms"][area] = str(path)
            if weather_csv:
                weather = {
                    **weather,
                    "csv": str(weather_csv),
                    "columns": {"timestamp": "timestamp", "temperature": "outdoor_temp"},
                }
        else:
            start = datetime.fromtimestamp(last_ts, UTC).isoformat() if last_ts else "now"
            if last_ts is None:
                self.note("no history in the export: simulation starts now")
            duration = self.duration
            outdoor_now = (d.get("outdoor") or {}).get("temp")
            if outdoor_now is not None:
                weather["anchor_temperature"] = float(outdoor_now)
                self.note("future weather: temperate profile shifted to the outdoor temperature at export time")
            for area, diag in d["rooms"].items():
                live = diag.get("live") or {}
                until = live.get("override_until")
                if live.get("override_active") and live.get("override_type"):
                    hours = max(0.1, (float(until) - (last_ts or time.time())) / 3600) if until else 0
                    item = {
                        "at": "+0s",
                        "do": "roommind.ws",
                        "type": "roommind/override/set",
                        "area_id": area,
                        "override_type": live["override_type"],
                    }
                    if live.get("override_heat") is not None:
                        item["heat"] = live["override_heat"]
                    if live.get("override_cool") is not None:
                        item["cool"] = live["override_cool"]
                    if hours:
                        item["duration"] = round(hours, 2)
                    timeline.append(item)
        seed = self._seed(rows)
        rm_rooms = {}
        for area, diag in d["rooms"].items():
            cfg = dict(diag.get("config") or {})
            cfg.pop("area_id", None)
            rm_rooms[area] = self.filtered(cfg, "roommind/rooms/save")
        rm_settings = self.filtered(settings, "roommind/settings/save")
        referenced = _referenced(rm_rooms, rm_settings)
        external = sorted((referenced - self.defined - {weather.get("entity_id", "weather.simhome")}) | self.external)
        for eid in external:
            self.note(f"{eid}: referenced by RoomMind but not simulated (stays missing)")
        scenario: dict[str, Any] = {
            "name": self.out.name,
            "description": f"Imported from diagnostics (schema v{self.version}, RoomMind {(d.get('integration') or {}).get('version')}), mode {self.mode}.",
            "tags": ["import"],
            "start": start,
            "duration": duration,
            "location": self.location(),
            "weather": weather,
            "house": {"building": DEFAULT_BUILDING, "outdoor": {"sensors": outdoor_sensors}, "rooms": rooms},
            "people": people,
            "helpers": helpers,
            "roommind": {"settings": rm_settings, "rooms": rm_rooms},
            "timeline": timeline,
            "expect": [{"invariant": "target_never_empty"}, {"invariant": "no_rejected_commands"}],
            "external_entities": external,
            "assumptions": self.assumptions,
        }
        if seed:
            scenario["seed_data"] = seed
        if replay:
            scenario["replay"] = replay
        return scenario

    def _seed(self, rows: dict[str, list[dict[str, str]]]) -> dict[str, Any]:
        seed: dict[str, Any] = {}
        thermal = {area: diag["model_state"] for area, diag in self.d["rooms"].items() if diag.get("model_state")}
        if thermal:
            path = self.out / "thermal_data.json"
            path.write_text(json.dumps(thermal))
            seed["thermal_data"] = str(path)
        elif any(diag.get("model") for diag in self.d["rooms"].values()):
            self.note("schema v1: EKF state not exported, RoomMind starts learning from scratch")
        if rows and self.mode != "replay":
            hist = self.out / "history"
            hist.mkdir(exist_ok=True)
            for area, items in rows.items():
                fields = list(items[0].keys()) if items else ["timestamp"]
                _write_csv(hist / f"{area}_detail.csv", items, fields)
            seed["history_dir"] = str(hist)
        return seed

    def _weather_csv(self, rows: dict[str, list[dict[str, str]]]) -> Path | None:
        merged: dict[str, str] = {}
        for items in rows.values():
            for r in items:
                if r.get("outdoor_temp") not in (None, ""):
                    merged[r["timestamp"]] = r["outdoor_temp"]
        if not merged:
            return None
        path = self.out / "outdoor.csv"
        items = [{"timestamp": t, "outdoor_temp": v} for t, v in sorted(merged.items(), key=lambda kv: float(kv[0]))]
        _write_csv(path, items, ["timestamp", "outdoor_temp"])
        return path


def _time(value: Any) -> str:
    # HA's JSON encoder writes datetime.time as {"__type": ..., "isoformat": ...}.
    if isinstance(value, dict) and "isoformat" in value:
        value = value["isoformat"]
    return str(value)[:8]


def _block(b: dict[str, Any]) -> dict[str, Any]:
    out = {"from": _time(b.get("from")), "to": _time(b.get("to"))}
    if b.get("data"):
        out["data"] = b["data"]
    return out


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _area_from_csv_name(path: Path, areas: list[str]) -> str:
    stem = path.stem.removeprefix("roommind_")
    for area in sorted(areas, key=len, reverse=True):
        if stem.startswith(area):
            return area
    if len(areas) == 1:
        return areas[0]
    raise ImportError_(f"cannot tell which room {path.name} belongs to (rooms: {', '.join(areas)})")


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _referenced(rooms: dict[str, Any], settings: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for cfg in rooms.values():
        for key in (
            "temperature_sensor",
            "humidity_sensor",
            "schedule_selector_entity",
            "cover_schedule_selector_entity",
        ):
            if cfg.get(key):
                out.add(cfg[key])
        for key in ("window_sensors", "occupancy_sensors", "covers", "presence_persons", "valve_protection_exclude"):
            out |= set(cfg.get(key) or [])
        for key in ("schedules", "cover_schedules"):
            out |= {s.get("entity_id") for s in cfg.get(key) or [] if s.get("entity_id")}
        out |= {d["entity_id"] for d in cfg.get("devices") or []}
    for key in ("outdoor_temp_sensor", "outdoor_humidity_sensor"):
        if settings.get(key):
            out.add(settings[key])
    out |= set(settings.get("presence_persons") or [])
    for group in settings.get("compressor_groups") or []:
        out |= set(group.get("members") or [])
        if group.get("master_entity"):
            out.add(group["master_entity"])
    return out
