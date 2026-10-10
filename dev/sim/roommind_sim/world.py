"""The simulated house: zones, devices, sensors, windows, covers, people, weather.

Pure Python. ``simhome`` (the HA integration) calls ``step()`` on a timer, mirrors the
changed entities into HA and routes service calls to ``device_call``/``cover_call``.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

from .covers import SimCover
from .devices import DeviceEnv, SimDevice, create_device
from .devices.base import CommandResult
from .devices.models import Boiler
from .people import MOISTURE_KG_S, SENSIBLE_W, SimPerson
from .physics.solar import window_gain_w
from .physics.zone import Gains, Zone, ZoneParams
from .scenario.model import Scenario, WindowSpec
from .sensors import SimOccupancy, SimSensor
from .weather import Outdoor, WeatherModel


def _load_replay(path: str) -> list[tuple[float, float]]:
    import csv

    with open(path) as fh:
        rows = [
            (float(r["timestamp"]), float(r["room_temp"]))
            for r in csv.DictReader(fh)
            if r.get("room_temp") not in (None, "")
        ]
    rows.sort()
    return rows


def _replay_value(rows: list[tuple[float, float]] | None, t: float) -> float | None:
    if not rows or t < rows[0][0] or t > rows[-1][0]:
        return None
    from bisect import bisect_left

    i = bisect_left(rows, (t, float("-inf")))
    if i == 0:
        return rows[0][1]
    (t0, v0), (t1, v1) = rows[i - 1], rows[min(i, len(rows) - 1)]
    return v0 if t1 <= t0 else v0 + (v1 - v0) * (t - t0) / (t1 - t0)


class WorldError(ValueError):
    """Invalid world action (unknown entity, wrong arguments)."""


@dataclass
class SimWindow:
    spec: WindowSpec
    open: bool = False
    unavailable_until: float = 0.0

    def vent_w_k(self, open_w_k_per_m2: float, dt_k: float) -> float:
        if not self.open:
            return 0.0
        return self.spec.area_m2 * open_w_k_per_m2 * (1 + 0.03 * abs(dt_k))


class World:
    def __init__(self, scenario: Scenario) -> None:
        self.scn = scenario
        self.tz = ZoneInfo(scenario.location.time_zone)
        self.weather = WeatherModel(
            scenario.weather,
            scenario.location.latitude,
            scenario.location.longitude,
            scenario.location.time_zone,
            scenario.seed,
        )
        self.boot_time = scenario.start
        self.zones: dict[str, Zone] = {}
        self.devices: dict[str, SimDevice] = {}
        self.sensors: dict[str, SimSensor] = {}
        self.occupancy: dict[str, SimOccupancy] = {}
        self.windows: dict[str, list[SimWindow]] = {}
        self.window_sensors: dict[str, SimWindow] = {}
        self.covers: dict[str, SimCover] = {}
        self.people: dict[str, SimPerson] = {}
        self.neighbors: list[tuple[str, str, float]] = []
        self.pending: list[dict[str, Any]] = []  # scheduled reverts, persisted
        self.occupancy_force: dict[str, tuple[int, float | None]] = {}
        self.moisture_events: list[tuple[str, float, float]] = []  # (room, until, kg/s)
        self.marks: list[tuple[float, str]] = []
        anchor = scenario.weather.get("anchor_temperature")
        if anchor is not None:
            # Imported setups: keep the profile's shape, but start at the reporter's outdoor temperature.
            delta = float(anchor) - self.weather.at(scenario.start).temp_c
            self.weather.set_override(scenario.start, None, {"temperature_delta": delta})
        self.replay = {area: _load_replay(path) for area, path in (scenario.replay.get("rooms") or {}).items()}
        self.outdoor: Outdoor = self.weather.at(scenario.start)
        self.now = scenario.start
        self.occupants: dict[str, int] = {}
        self._solar_cache: dict[str, float] = {}
        self._build()

    # --- construction ------------------------------------------------------------------

    def _build(self) -> None:
        scn = self.scn
        for area_id, room in scn.rooms.items():
            params = ZoneParams.from_thermal(room.thermal, sum(w.area_m2 for w in room.windows))
            zone = Zone(area_id, params)
            init = room.initial
            zone.set_initial(
                float(init.get("temperature", 20.0)), float(init.get("humidity", 50.0)), init.get("mass_temperature")
            )
            self.zones[area_id] = zone
            self.windows[area_id] = []
            for w in room.windows:
                sw = SimWindow(w)
                self.windows[area_id].append(sw)
                if w.sensor:
                    self.window_sensors[w.sensor] = sw
            for dev in room.devices:
                self.devices[dev.entity_id] = create_device(dev, random.Random(f"{scn.seed}:{dev.entity_id}"))
            for s in room.sensors:
                if s.kind == "occupancy":
                    self.occupancy[s.entity_id] = SimOccupancy(s)
                else:
                    self.sensors[s.entity_id] = SimSensor(s, scn.seed)
            for c in room.covers:
                self.covers[c.entity_id] = SimCover(c)
            coupling = room.thermal.get("coupling_w_k") or {}
            for other, kind in room.neighbors.items():
                value = float(kind) if isinstance(kind, int | float) else float(coupling.get(kind, 15.0))
                self.neighbors.append((area_id, other, value))
        for s in scn.outdoor_sensors:
            self.sensors[s.entity_id] = SimSensor(s, scn.seed)
        for p in scn.people:
            self.people[p.id] = SimPerson(p, p.rooms, self.tz)
        for dev in self.devices.values():
            dev.sensor_c = round(self.zones[dev.room].t_air, 1)

    def ha_started(self, now: float) -> None:
        """Called on every HA (re)start; device/sensor start-up quirks count from here."""
        self.boot_time = now
        for dev in self.devices.values():
            dev.boot_time = now

    # --- stepping ------------------------------------------------------------------------

    def step(self, dt: float, now: float) -> set[str]:
        """Advance physics to ``now``; return entity ids whose HA state may have changed."""
        self.now = now
        changed: set[str] = set()
        self._run_pending(now, changed)
        out = self.weather.at(now)
        self.outdoor = out
        occupants: dict[str, int] = dict.fromkeys(self.zones, 0)
        for person in self.people.values():
            if person.update(now):
                changed.add(person.spec.tracker)
            if person.home and person.room in occupants:
                occupants[person.room] += 1
        for room, (count, until) in list(self.occupancy_force.items()):
            if until is not None and now >= until:
                del self.occupancy_force[room]
            else:
                occupants[room] = count
        for cover in self.covers.values():
            if cover.step(dt):
                changed.add(cover.entity_id)

        gains = {area: Gains() for area in self.zones}
        boilers = [d for d in self.devices.values() if isinstance(d, Boiler)]
        loads = {b.entity_id: 0.0 for b in boilers}
        for dev in self.devices.values():
            if isinstance(dev, Boiler):
                continue
            supply = None
            server = next((b for b in boilers if b.serves(dev.entity_id)), None)
            if server is not None and dev.model in ("trv", "ufh"):
                supply = server.supply_temp(self.zones[dev.room].t_air)
            env = DeviceEnv(now=now, zone=self.zones[dev.room], outdoor=out, zones=self.zones, supply_temp_c=supply)
            for area, g in dev.step(dt, env).items():
                if area in gains:
                    gains[area].add(g)
            if server is not None:
                loads[server.entity_id] += getattr(dev, "water_draw_w", 0.0)
            changed.add(dev.entity_id)
        for b in boilers:
            b.load_w = loads[b.entity_id]
            b.step(dt, DeviceEnv(now=now, zone=self.zones[b.room], outdoor=out, zones=self.zones))
            changed.add(b.entity_id)

        for area, zone in self.zones.items():
            g = gains[area]
            solar = self._solar_w(area, out)
            g.conv_w += solar * 0.3 + occupants[area] * SENSIBLE_W * 0.6
            g.rad_w += solar * 0.7 + occupants[area] * SENSIBLE_W * 0.4
            g.moisture_kg_s += occupants[area] * MOISTURE_KG_S
            for room, until, rate in self.moisture_events:
                if room == area and now < until:
                    g.moisture_kg_s += rate
            for w in self.windows[area]:
                g.vent_w_k += w.vent_w_k(zone.params.window_open_w_k_per_m2, zone.t_air - out.temp_c)
            self._solar_cache[area] = solar
        self.moisture_events = [e for e in self.moisture_events if now < e[1]]
        flows = dict.fromkeys(self.zones, 0.0)
        for a, b, h in self.neighbors:
            q = h * (self.zones[b].t_air - self.zones[a].t_air)
            flows[a] += q
            flows[b] -= q
        x_out = out.x
        for area, zone in self.zones.items():
            zone.step(dt, out.temp_c, x_out, gains[area], flows[area])
            recorded = _replay_value(self.replay.get(area), now)
            if recorded is not None:
                # Open-loop replay: the reporter's room temperature wins over the physics.
                zone.t_mass += recorded - zone.t_air
                zone.t_air = recorded

        for sensor in self.sensors.values():
            if self._sensor_update(sensor, now):
                changed.add(sensor.entity_id)
        for area, room in self.scn.rooms.items():
            for s in room.sensors:
                if s.kind == "occupancy" and self.occupancy[s.entity_id].update(occupants[area], now):
                    changed.add(s.entity_id)
        self.occupants = occupants
        return changed

    def _solar_w(self, area: str, out: Outdoor) -> float:
        total = 0.0
        for w in self.windows[area]:
            gain = window_gain_w(out.sun, out.irradiance, w.spec.orientation, w.spec.area_m2, w.spec.g_value)
            if gain <= 0:
                continue
            shading = max(
                (c.shading() for c in self.covers.values() if c.spec.room == area and w.spec.index in c.spec.windows),
                default=0.0,
            )
            total += gain * (1 - shading)
        return total

    def _sensor_update(self, sensor: SimSensor, now: float) -> bool:
        kind = sensor.spec.kind
        if kind == "outdoor_temperature":
            true = self.outdoor.temp_c
        elif kind == "outdoor_humidity":
            true = self.outdoor.rh
        elif kind == "temperature":
            true = self.zones[sensor.spec.room].t_air
        elif kind == "humidity":
            true = self.zones[sensor.spec.room].rh
        else:
            return False
        return sensor.update(true, now, self.boot_time)

    # --- HA-facing calls ------------------------------------------------------------------

    def device_call(self, entity_id: str, service: str, data: dict[str, Any], now: float) -> CommandResult:
        dev = self.devices.get(entity_id)
        if dev is None:
            return CommandResult(False, "unknown_entity")
        return dev.call(service, data, now)

    def cover_call(self, entity_id: str, service: str, data: dict[str, Any]) -> bool:
        cover = self.covers[entity_id]
        return cover.available and cover.command(service, data)

    def is_available(self, entity_id: str, now: float) -> bool:
        if entity_id in self.devices:
            return self.devices[entity_id].available
        if entity_id in self.sensors:
            return self.sensors[entity_id].available(now) and self.sensors[entity_id].value is not None
        if entity_id in self.occupancy:
            return self.occupancy[entity_id].available(now)
        if entity_id in self.window_sensors:
            return now >= self.window_sensors[entity_id].unavailable_until
        if entity_id in self.covers:
            return self.covers[entity_id].available
        return True

    # --- actions (timeline / CLI) ------------------------------------------------------------

    WORLD_ACTIONS = (
        "window.open",
        "window.close",
        "person.leave",
        "person.arrive",
        "occupancy.set",
        "cover.manual",
        "device.manual",
        "entity.unavailable",
        "entity.available",
        "weather.set",
        "weather.forecast_unavailable",
        "humidity.event",
        "sim.param",
    )

    def apply_action(self, action: str, args: dict[str, Any], now: float) -> set[str]:
        """Apply a world action; ``for`` schedules the inverse. Returns touched entity ids."""
        duration = args.get("for")
        until = now + float(duration) if duration else None
        eid = args.get("entity_id")
        if action in ("window.open", "window.close"):
            window = self._window(eid)
            window.open = action == "window.open"
            if until:
                self._schedule(until, "window.close" if window.open else "window.open", {"entity_id": eid})
            return {eid}
        if action in ("person.leave", "person.arrive"):
            person = self.people.get(args["person"])
            if person is None:
                raise WorldError(f"unknown person {args['person']!r}")
            person.override = (action == "person.arrive", until)
            person.update(now)
            return {person.spec.tracker}
        if action == "occupancy.set":
            if args["room"] not in self.zones:
                raise WorldError(f"unknown room {args['room']!r}")
            self.occupancy_force[args["room"]] = (int(args["count"]), until)
            return set()
        if action == "cover.manual":
            cover = self.covers.get(eid)
            if cover is None:
                raise WorldError(f"unknown cover {eid!r}")
            cover.target_position = float(args["position"])
            if "tilt" in args:
                cover.target_tilt = float(args["tilt"])
            return {eid}
        if action == "device.manual":
            dev = self.devices.get(eid)
            if dev is None:
                raise WorldError(f"unknown device {eid!r}")
            if "hvac_mode" in args:
                dev.force_mode(args["hvac_mode"])
            if "temperature" in args:
                dev.target = dev._snap(float(args["temperature"]))
            if "fan_mode" in args:
                dev.fan_mode = args["fan_mode"]
            return {eid}
        if action in ("entity.unavailable", "entity.available"):
            down = action == "entity.unavailable"
            self._set_available(eid, not down, until if down else 0.0)
            if down and until:
                self._schedule(until, "entity.available", {"entity_id": eid})
            return {eid}
        if action == "weather.set":
            values = {
                k: float(v)
                for k, v in args.items()
                if k in ("temperature", "temperature_delta", "humidity", "cloud", "wind")
            }
            self.weather.set_override(now, until, values)
            return set(self.sensors)
        if action == "weather.forecast_unavailable":
            self.weather.forecast_available = False
            if until:
                self._schedule(until, "weather.forecast_available", {})
            return set()
        if action == "weather.forecast_available":
            self.weather.forecast_available = True
            return set()
        if action == "humidity.event":
            kg = float(args.get("grams", 300)) / 1000
            seconds = float(duration or 900)
            self.moisture_events.append((args["room"], now + seconds, kg / seconds))
            return set()
        if action == "sim.param":
            self._set_param(args["path"], args["value"])
            return set()
        raise WorldError(f"unknown world action {action!r}")

    def _window(self, eid: str | None) -> SimWindow:
        if eid not in self.window_sensors:
            raise WorldError(f"unknown window sensor {eid!r}")
        return self.window_sensors[eid]

    def _set_available(self, eid: str | None, available: bool, until: float | None) -> None:
        inf = float("inf")
        if eid in self.devices:
            self.devices[eid].available = available
            if not available:
                self.devices[eid].quirks = [q for q in self.devices[eid].quirks if q.name != "availability"]
        elif eid in self.sensors:
            self.sensors[eid].unavailable_until = 0.0 if available else inf
        elif eid in self.occupancy:
            self.occupancy[eid].unavailable_until = 0.0 if available else inf
        elif eid in self.window_sensors:
            self.window_sensors[eid].unavailable_until = 0.0 if available else inf
        elif eid in self.covers:
            self.covers[eid].available = available
        else:
            raise WorldError(f"unknown entity {eid!r}")

    def _set_param(self, path: str, value: Any) -> None:
        """``device.<entity_id>.<param>``, ``room.<area>.<zone param>``, ``weather.<key>``."""
        head, _, rest = path.partition(".")
        if head == "device":
            eid, _, key = rest.rpartition(".")
            if eid not in self.devices:
                raise WorldError(f"unknown device {eid!r}")
            self.devices[eid].spec.params[key] = value
        elif head == "room":
            area, _, key = rest.partition(".")
            zone = self.zones.get(area)
            if zone is None or not hasattr(zone.params, key):
                raise WorldError(f"unknown room parameter {path!r}")
            setattr(zone.params, key, float(value))
        elif head == "weather":
            self.weather.p[rest] = value
        else:
            raise WorldError(f"unknown parameter path {path!r}")

    def _schedule(self, at: float, action: str, args: dict[str, Any]) -> None:
        self.pending.append({"at": at, "action": action, "args": args})
        self.pending.sort(key=lambda p: p["at"])

    def _run_pending(self, now: float, changed: set[str]) -> None:
        while self.pending and self.pending[0]["at"] <= now:
            item = self.pending.pop(0)
            changed |= self.apply_action(item["action"], item["args"], now)

    # --- observation -----------------------------------------------------------------------

    def sample(self) -> dict[str, Any]:
        """Ground truth for the timeline (one record per sample interval)."""
        out = self.outdoor
        return {
            "outdoor": {
                "temp": round(out.temp_c, 3),
                "rh": round(out.rh, 1),
                "cloud": round(out.cloud_pct),
                "ghi": round(out.irradiance.ghi),
            },
            "rooms": {
                a: {
                    "t_air": round(z.t_air, 3),
                    "t_mass": round(z.t_mass, 3),
                    "rh": round(z.rh, 1),
                    "solar_w": round(self._solar_cache.get(a, 0.0)),
                    "occupants": self.occupants.get(a, 0),
                    "windows_open": sum(w.open for w in self.windows[a]),
                }
                for a, z in self.zones.items()
            },
            "devices": {
                e: {
                    "mode": d.hvac_mode,
                    "active": d.active,
                    "action": d.hvac_action,
                    "target": d.target,
                    "low": d.target_low,
                    "high": d.target_high,
                    "heat_w": round(d.heat_output_w()),
                    "electric_w": round(d.electric_w()),
                    "available": d.available,
                    **({"valve": round(d.valve, 3)} if hasattr(d, "valve") else {}),
                    **({"t_slab": round(d.t_slab, 2)} if getattr(d, "t_slab", None) is not None else {}),
                    **({"t_rad": round(d.t_rad, 2)} if getattr(d, "t_rad", None) is not None else {}),
                }
                for e, d in self.devices.items()
            },
            "covers": {e: {"position": round(c.position), "tilt": round(c.tilt)} for e, c in self.covers.items()},
            "people": {p: {"home": s.home, "room": s.room} for p, s in self.people.items()},
        }

    def ground_truth(self) -> dict[str, dict[str, float]]:
        return {a: z.params.equivalent_first_order() for a, z in self.zones.items()}

    # --- persistence -------------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        return {
            "now": self.now,
            "zones": {a: z.snapshot() for a, z in self.zones.items()},
            "devices": {e: d.snapshot() for e, d in self.devices.items()},
            "sensors": {e: s.snapshot() for e, s in self.sensors.items()},
            "occupancy": {e: s.snapshot() for e, s in self.occupancy.items()},
            "windows": {
                e: {"open": w.open, "unavailable_until": w.unavailable_until} for e, w in self.window_sensors.items()
            },
            "covers": {e: c.snapshot() for e, c in self.covers.items()},
            "people": {p: s.snapshot() for p, s in self.people.items()},
            "pending": self.pending,
            "occupancy_force": {k: list(v) for k, v in self.occupancy_force.items()},
            "moisture_events": [list(e) for e in self.moisture_events],
            "weather_overrides": [[o.start, o.end, o.values] for o in self.weather._overrides],
            "forecast_available": self.weather.forecast_available,
        }

    def restore(self, data: dict[str, Any]) -> None:
        self.now = data["now"]
        for a, zs in data["zones"].items():
            if a in self.zones:
                self.zones[a].restore(zs)
        for group, items in (
            ("devices", self.devices),
            ("sensors", self.sensors),
            ("occupancy", self.occupancy),
            ("covers", self.covers),
            ("people", self.people),
        ):
            for key, state in data.get(group, {}).items():
                if key in items:
                    items[key].restore(state)
        for e, ws in data.get("windows", {}).items():
            if e in self.window_sensors:
                self.window_sensors[e].open = ws["open"]
                self.window_sensors[e].unavailable_until = ws.get("unavailable_until", 0.0)
        self.pending = data.get("pending", [])
        self.occupancy_force = {k: (v[0], v[1]) for k, v in data.get("occupancy_force", {}).items()}
        self.moisture_events = [tuple(e) for e in data.get("moisture_events", [])]  # type: ignore[misc]
        for start, end, values in data.get("weather_overrides", []):
            self.weather.set_override(start, end, values)
        self.weather.forecast_available = data.get("forecast_available", True)
