"""Load a scenario YAML, merge profiles and validate references before HA starts."""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import yaml

from .errors import ScenarioError
from .model import (
    CoverSpec,
    DeviceSpec,
    Location,
    PersonSpec,
    RoomSpec,
    Scenario,
    SensorSpec,
    TimelineItem,
    WindowSpec,
)
from .timespec import parse_at, parse_duration, parse_start

SIM_ROOT = Path(__file__).resolve().parents[2]
PROFILE_DIR = SIM_ROOT / "profiles"
SCENARIO_DIR = SIM_ROOT / "scenarios"

_ENTITY_RE = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")
_DEVICE_KEYS = {"entity_id", "profile", "name"}
_HELPER_DOMAINS = {"schedule", "input_boolean", "input_number", "input_select"}
DEVICE_MODELS = {"trv", "ac", "heat_pump", "heater", "boiler", "ufh"}
SENSOR_KINDS = {"temperature", "humidity", "occupancy"}

# Timeline actions and their required arguments; implementations live in simhome.actions.
ACTIONS: dict[str, set[str]] = {
    "window.open": {"entity_id"},
    "window.close": {"entity_id"},
    "person.leave": {"person"},
    "person.arrive": {"person"},
    "occupancy.set": {"room", "count"},
    "cover.manual": {"entity_id", "position"},
    "device.manual": {"entity_id"},
    "entity.unavailable": {"entity_id"},
    "entity.available": {"entity_id"},
    "entity.remove": {"entity_id"},
    "weather.set": set(),
    "weather.forecast_unavailable": set(),
    "humidity.event": {"room"},
    "ha.service": {"service"},
    "ha.restart": set(),
    "roommind.reload": set(),
    "roommind.ws": {"type"},
    "sim.param": {"path", "value"},
    "clock.speed": {"factor"},
    "clock.pause": set(),
    "mark": {"label"},
}


def deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    """Merge ``over`` into a copy of ``base``; ``key+`` appends to a list."""
    out = copy.deepcopy(base)
    for key, value in over.items():
        if key.endswith("+"):
            real = key[:-1]
            out[real] = list(out.get(real, [])) + list(value)
        elif isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_profile(kind: str, name: str, where: str, _seen: tuple[str, ...] = ()) -> dict[str, Any]:
    path = PROFILE_DIR / kind / f"{name}.yaml"
    if not path.is_file():
        available = sorted(p.stem for p in (PROFILE_DIR / kind).glob("*.yaml"))
        raise ScenarioError(f"unknown {kind} profile {name!r} (available: {', '.join(available)})", where)
    if name in _seen:
        raise ScenarioError(f"profile cycle {' -> '.join((*_seen, name))}", where)
    data = yaml.safe_load(path.read_text()) or {}
    parent = data.pop("extends", None)
    data.pop("description", None)
    if parent:
        return deep_merge(load_profile(kind, parent, where, (*_seen, name)), data)
    return data


def _set_path(data: dict[str, Any], dotted: str, value: Any) -> None:
    node = data
    parts = dotted.split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, {})
        if not isinstance(node, dict):
            raise ScenarioError(f"cannot set {dotted!r}: {part!r} is not a mapping", "--set")
    node[parts[-1]] = value


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        candidate = SCENARIO_DIR / f"{path}.yaml" if path.suffix == "" else SCENARIO_DIR / path.name
        if candidate.is_file():
            path = candidate
        else:
            raise ScenarioError(f"scenario file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as err:
        raise ScenarioError(f"YAML error: {err}", str(path)) from err
    parent = data.pop("extends", None)
    if parent:
        parent_path = (
            (path.parent / parent).with_suffix(".yaml") if not str(parent).endswith(".yaml") else path.parent / parent
        )
        data = deep_merge(_read_yaml(parent_path), data)
    data["__path__"] = str(path)
    return data


def load_scenario(path: str | Path, overrides: dict[str, Any] | None = None) -> Scenario:
    """Load ``path`` (file or name in ``dev/sim/scenarios``) with ``--set`` overrides."""
    data = _read_yaml(Path(path))
    for dotted, value in (overrides or {}).items():
        _set_path(data, dotted, value)
    return load_scenario_dict(data)


def load_scenario_dict(data: dict[str, Any]) -> Scenario:
    data = copy.deepcopy(data)
    source = data.pop("__path__", None)
    name = data.get("name") or (Path(source).stem if source else "")
    if not name:
        raise ScenarioError("scenario needs a name")

    loc = Location(**(data.get("location") or {}))
    start = parse_start(data.get("start"), loc.time_zone)
    duration = parse_duration(data.get("duration", "1d"), "duration")
    house = data.get("house") or {}
    building = house.get("building", "bestand_teilsaniert")

    floors = {str(k): str(v) for k, v in (house.get("floors") or {}).items()}
    rooms: dict[str, RoomSpec] = {}
    for area_id, rdata in (house.get("rooms") or {}).items():
        rooms[area_id] = _room(area_id, rdata or {}, building, floors)

    outdoor = []
    for kind, sdata in ((house.get("outdoor") or {}).get("sensors") or {}).items():
        outdoor.append(_sensor(f"outdoor_{kind}", sdata, None, f"house.outdoor.sensors.{kind}"))

    people = [_person(i, p) for i, p in enumerate(data.get("people") or [])]
    helpers = data.get("helpers") or {}
    for domain in helpers:
        if domain not in _HELPER_DOMAINS:
            raise ScenarioError(f"unknown helper domain {domain!r} (allowed: {sorted(_HELPER_DOMAINS)})", "helpers")

    weather = {"entity_id": "weather.simhome", "profile": "temperate"} | (data.get("weather") or {})

    timeline = []
    for i, item in enumerate(data.get("timeline") or []):
        timeline.append(_timeline_item(i, item, start, loc.time_zone))
    timeline.sort(key=lambda t: (t.at, t.index))

    expect = list(data.get("expect") or [])
    for i, exp in enumerate(expect):
        if not isinstance(exp, dict) or not ({"metric", "invariant", "check"} & exp.keys()):
            raise ScenarioError("expectation needs metric, invariant or check", f"expect[{i}]")

    scn = Scenario(
        name=name,
        description=str(data.get("description", "")).strip(),
        refs=[int(r) for r in data.get("refs") or []],
        tags=list(data.get("tags") or []),
        location=loc,
        start=start,
        duration=duration,
        seed=int(data.get("seed", 1)),
        physics_step=parse_duration(data.get("physics_step", "10s"), "physics_step"),
        sample_interval=parse_duration(data.get("sample_interval", "1m"), "sample_interval"),
        weather=weather,
        rooms=rooms,
        floors=floors,
        outdoor_sensors=outdoor,
        people=people,
        helpers=helpers,
        roommind=data.get("roommind") or {},
        timeline=timeline,
        expect=expect,
        known_failure=data.get("known_failure"),
        external_entities=list(data.get("external_entities") or []),
        assumptions=list(data.get("assumptions") or []),
        replay=data.get("replay") or {},
        source_path=Path(source) if source else None,
        raw=data,
    )
    _validate(scn)
    return scn


def _room(area_id: str, rdata: dict[str, Any], building: str, floors: dict[str, str]) -> RoomSpec:
    where = f"house.rooms.{area_id}"
    if not re.fullmatch(r"[a-z0-9_]+", area_id):
        raise ScenarioError("area id must be lowercase snake_case", where)
    preset = rdata.get("building", building)
    thermal = load_profile("buildings", preset, f"{where}.building")
    for key in ("floor_area_m2", "height_m", "exterior_wall_m2"):
        if key in rdata:
            thermal[key] = rdata[key]
    thermal = deep_merge(thermal, rdata.get("thermal") or {})
    floor = rdata.get("floor")
    if floor is not None and floor not in floors:
        raise ScenarioError(f"unknown floor {floor!r} (define it in house.floors)", where)

    devices = []
    for i, ddata in enumerate(rdata.get("devices") or []):
        devices.append(_device(area_id, ddata, f"{where}.devices[{i}]"))
    sensors = [
        _sensor(kind, sdata, area_id, f"{where}.sensors.{kind}") for kind, sdata in (rdata.get("sensors") or {}).items()
    ]
    windows = []
    for i, wraw in enumerate(rdata.get("windows") or []):
        wdata = dict(wraw or {})
        sensor = wdata.pop("sensor", None)
        if sensor is not None:
            _check_entity_id(sensor, "binary_sensor", f"{where}.windows[{i}].sensor")
        windows.append(WindowSpec(room=area_id, index=i, sensor=sensor, **wdata))
    covers = []
    for i, craw in enumerate(rdata.get("covers") or []):
        cdata = dict(craw)
        eid = cdata.pop("entity_id", None)
        _check_entity_id(eid, "cover", f"{where}.covers[{i}]")
        profile = load_profile("covers", cdata.pop("profile", "roller_shutter"), f"{where}.covers[{i}]")
        name = cdata.pop("name", _name_from(eid))
        win = cdata.pop("windows", list(range(len(windows))))
        covers.append(CoverSpec(entity_id=eid, room=area_id, name=name, windows=win, params=deep_merge(profile, cdata)))
    return RoomSpec(
        area_id=area_id,
        name=rdata.get("name", area_id.replace("_", " ").title()),
        floor=floor,
        thermal=thermal,
        devices=devices,
        sensors=sensors,
        windows=windows,
        covers=covers,
        neighbors=dict(rdata.get("neighbors") or {}),
        initial=dict(rdata.get("initial") or {}),
    )


def _device(room: str, ddata: dict[str, Any], where: str) -> DeviceSpec:
    if not isinstance(ddata, dict):
        raise ScenarioError("device must be a mapping", where)
    eid = ddata.get("entity_id")
    _check_entity_id(eid, "climate", where)
    if "profile" not in ddata:
        raise ScenarioError("device needs a profile", where)
    profile = load_profile("devices", ddata["profile"], where)
    extra = {k: v for k, v in ddata.items() if k not in _DEVICE_KEYS}
    known = {"model", "capabilities", "params", "quirks", "quirks+"}
    shortcut = {k: v for k, v in extra.items() if k not in known}
    merged = deep_merge(profile, {k: v for k, v in extra.items() if k in known})
    merged["params"] = deep_merge(merged.get("params") or {}, shortcut)
    model = merged.get("model")
    if model not in DEVICE_MODELS:
        raise ScenarioError(f"profile model {model!r} unknown (allowed: {sorted(DEVICE_MODELS)})", where)
    return DeviceSpec(
        entity_id=eid,
        room=room,
        model=model,
        name=ddata.get("name", _name_from(eid)),
        profile=ddata["profile"],
        capabilities=merged.get("capabilities") or {},
        params=merged["params"],
        quirks=list(merged.get("quirks") or []),
    )


def _sensor(kind: str, sdata: dict[str, Any] | str, room: str | None, where: str) -> SensorSpec:
    if isinstance(sdata, str):
        sdata = {"entity_id": sdata}
    sdata = dict(sdata or {})
    eid = sdata.pop("entity_id", None)
    base_kind = kind.removeprefix("outdoor_")
    if base_kind not in SENSOR_KINDS:
        raise ScenarioError(f"unknown sensor kind {kind!r} (allowed: {sorted(SENSOR_KINDS)})", where)
    _check_entity_id(eid, "binary_sensor" if base_kind == "occupancy" else "sensor", where)
    profile_name = sdata.pop("profile", f"default_{base_kind}")
    params = deep_merge(load_profile("sensors", profile_name, where), sdata)
    name = params.pop("name", _name_from(eid))
    return SensorSpec(entity_id=eid, kind=kind, room=room, name=name, params=params)


def _person(i: int, pdata: dict[str, Any]) -> PersonSpec:
    where = f"people[{i}]"
    pid = pdata.get("id")
    if not pid or not re.fullmatch(r"[a-z0-9_]+", str(pid)):
        raise ScenarioError("person needs a snake_case id", where)
    plan = load_profile("people", pdata.get("profile", "commuter"), where)
    plan = deep_merge(plan, pdata.get("plan") or {})
    tracker = pdata.get("tracker", f"device_tracker.{pid}_phone")
    _check_entity_id(tracker, "device_tracker", where)
    rooms = {str(k): str(v) for k, v in (pdata.get("rooms") or {}).items()}
    return PersonSpec(id=pid, name=pdata.get("name", pid.title()), tracker=tracker, plan=plan, rooms=rooms)


def _timeline_item(i: int, item: dict[str, Any], start: float, tz: str) -> TimelineItem:
    where = f"timeline[{i}]"
    if not isinstance(item, dict) or "at" not in item or "do" not in item:
        raise ScenarioError("timeline item needs 'at' and 'do'", where)
    args = {k: v for k, v in item.items() if k not in ("at", "do")}
    action = str(item["do"])
    if action not in ACTIONS:
        raise ScenarioError(f"unknown action {action!r} (known: {', '.join(sorted(ACTIONS))})", where)
    missing = ACTIONS[action] - args.keys()
    if missing:
        raise ScenarioError(f"action {action} needs {sorted(missing)}", where)
    if "for" in args:
        args["for"] = parse_duration(args["for"], f"{where}.for")
    return TimelineItem(index=i, at=parse_at(item["at"], start, tz, where), action=action, args=args)


def _check_entity_id(eid: Any, domain: str, where: str) -> None:
    if not isinstance(eid, str) or not _ENTITY_RE.match(eid):
        raise ScenarioError(f"invalid entity_id {eid!r}", where)
    if not eid.startswith(f"{domain}."):
        raise ScenarioError(f"entity_id {eid!r} must be in domain {domain}", where)
    if eid.split(".", 1)[1].startswith("roommind_"):
        raise ScenarioError("entity ids starting with roommind_ are reserved by RoomMind", where)


def _name_from(eid: str) -> str:
    return eid.split(".", 1)[1].replace("_", " ").title()


_ROOM_ENTITY_FIELDS = (
    "temperature_sensor",
    "humidity_sensor",
    "schedule_selector_entity",
    "cover_schedule_selector_entity",
)
_ROOM_LIST_FIELDS = ("window_sensors", "occupancy_sensors", "covers", "presence_persons", "valve_protection_exclude")


def _validate(scn: Scenario) -> None:
    known = scn.entity_ids() | set(scn.external_entities)
    duplicates = _duplicates(
        [d.entity_id for d in scn.all_devices()]
        + [s.entity_id for s in scn.all_sensors()]
        + [w.sensor for r in scn.rooms.values() for w in r.windows if w.sensor]
    )
    if duplicates:
        raise ScenarioError(f"entity ids defined twice: {sorted(duplicates)}", "house")

    def check(eid: Any, where: str) -> None:
        if eid in ("", None):
            return
        if eid not in known:
            raise ScenarioError(f"references {eid!r}, which the scenario does not define", where)

    rm = scn.roommind
    for area_id, room in (rm.get("rooms") or {}).items():
        where = f"roommind.rooms.{area_id}"
        if area_id not in scn.rooms:
            raise ScenarioError("room is not defined in house.rooms", where)
        for i, dev in enumerate(room.get("devices") or []):
            check(dev.get("entity_id"), f"{where}.devices[{i}]")
        for key in _ROOM_ENTITY_FIELDS:
            check(room.get(key), f"{where}.{key}")
        for key in _ROOM_LIST_FIELDS:
            for i, eid in enumerate(room.get(key) or []):
                check(eid, f"{where}.{key}[{i}]")
        for key in ("schedules", "cover_schedules"):
            for i, sched in enumerate(room.get(key) or []):
                check(sched.get("entity_id"), f"{where}.{key}[{i}]")
    settings = rm.get("settings") or {}
    for key in ("outdoor_temp_sensor", "outdoor_humidity_sensor", "weather_entity"):
        check(settings.get(key), f"roommind.settings.{key}")
    for i, eid in enumerate(settings.get("presence_persons") or []):
        check(eid, f"roommind.settings.presence_persons[{i}]")
    for i, group in enumerate(settings.get("compressor_groups") or []):
        for eid in group.get("members") or []:
            check(eid, f"roommind.settings.compressor_groups[{i}].members")
        check(group.get("master_entity"), f"roommind.settings.compressor_groups[{i}].master_entity")
    for item in scn.timeline:
        for key in ("entity_id",):
            if key in item.args and item.action not in ("entity.remove",):
                check(item.args[key], f"timeline[{item.index}].{key}")
        if item.at < 0 or item.at > scn.duration:
            raise ScenarioError(
                f"time {item.at:.0f}s lies outside the scenario (0..{scn.duration:.0f}s)", f"timeline[{item.index}]"
            )
    for person in scn.people:
        for role, area in person.rooms.items():
            if area not in scn.rooms:
                raise ScenarioError(f"role {role!r} maps to unknown room {area!r}", f"people.{person.id}.rooms")
    for room in scn.rooms.values():
        for other in room.neighbors:
            if other not in scn.rooms:
                raise ScenarioError(f"unknown neighbor room {other!r}", f"house.rooms.{room.area_id}.neighbors")


def _duplicates(items: list[str]) -> set[str]:
    seen: set[str] = set()
    dup: set[str] = set()
    for item in items:
        if item in seen:
            dup.add(item)
        seen.add(item)
    return dup
