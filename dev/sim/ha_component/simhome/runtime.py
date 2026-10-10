"""Runtime glue between the HA instance and the pure-Python World."""

from __future__ import annotations

import json
import logging
import time
from datetime import timedelta
from functools import partial
from pathlib import Path
from typing import Any

from homeassistant.auth.const import GROUP_ID_ADMIN
from homeassistant.auth.models import TOKEN_TYPE_LONG_LIVED_ACCESS_TOKEN
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import floor_registry as fr
from homeassistant.helpers.event import async_track_point_in_utc_time, async_track_time_interval
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from roommind_sim import clock as clockmod
from roommind_sim.scenario import Scenario, load_scenario_dict
from roommind_sim.world import World

from .bridge import WsBridge
from .const import FLUSH_INTERVAL_S, OBSERVE_INTERVAL_S, PERSIST_INTERVAL_S

_LOGGER = logging.getLogger(__name__)
SIM_USER_NAME = "Sim"


class SimRuntime:
    def __init__(
        self, hass: HomeAssistant, inst_dir: Path, scenario: Scenario, world: World, state: dict[str, Any]
    ) -> None:
        self.hass = hass
        self.dir = inst_dir
        self.scn = scenario
        self.world = world
        self.done: set[int] = set(state.get("timeline_done", []))
        self.provisioned: bool = state.get("provisioned", False)
        self.entities: dict[str, Any] = {}
        self.extra_entities: list[Any] = []  # weather etc., written on samples
        self.bridge: WsBridge | None = None
        self._unsubs: list[CALLBACK_TYPE] = []
        self._buffers: dict[str, list[str]] = {"samples": [], "observer": [], "events": []}
        self._last_step = time.time()
        self.removed: set[str] = set(state.get("removed", []))

    # --- loading ------------------------------------------------------------------------

    @classmethod
    def load(cls, hass: HomeAssistant, inst_dir: Path) -> SimRuntime:
        scn = load_scenario_dict(json.loads((inst_dir / "scenario.json").read_text()))
        world = World(scn)
        state_dir = inst_dir / "state"
        world_file = state_dir / "world.json"
        if world_file.is_file():
            world.restore(json.loads(world_file.read_text()))
        runtime_file = state_dir / "runtime.json"
        state = json.loads(runtime_file.read_text()) if runtime_file.is_file() else {}
        (inst_dir / "timeline").mkdir(exist_ok=True)
        return cls(hass, inst_dir, scn, world, state)

    @property
    def clock(self) -> clockmod.Clock | None:
        return clockmod.CLOCK

    # --- registries -----------------------------------------------------------------------

    @callback
    def setup_registries(self) -> None:
        floors = fr.async_get(self.hass)
        floor_ids: dict[str, str] = {}
        for key, name in self.scn.floors.items():
            entry = floors.async_get_floor(key) or floors.async_get_floor_by_name(name) or floors.async_create(name)
            floor_ids[key] = entry.floor_id
        areas = ar.async_get(self.hass)
        for area_id, room in self.scn.rooms.items():
            if areas.async_get_area(area_id) is None:
                seed_name = room.name if slugify(room.name) == area_id else area_id.replace("_", " ")
                created = areas.async_create(seed_name)
                if created.id != area_id:
                    _LOGGER.warning("area %s got id %s; RoomMind config refers to %s", room.name, created.id, area_id)
                areas.async_update(created.id, name=room.name)
            if room.floor:
                areas.async_update(area_id, floor_id=floor_ids[room.floor])

    @callback
    def assign_areas(self) -> None:
        reg = er.async_get(self.hass)
        rooms_by_entity: dict[str, str] = {}
        for room in self.scn.rooms.values():
            for d in room.devices:
                rooms_by_entity[d.entity_id] = room.area_id
            for s in room.sensors:
                rooms_by_entity[s.entity_id] = room.area_id
            for w in room.windows:
                if w.sensor:
                    rooms_by_entity[w.sensor] = room.area_id
            for c in room.covers:
                rooms_by_entity[c.entity_id] = room.area_id
        for eid, area in rooms_by_entity.items():
            if reg.async_get(eid) is not None:
                reg.async_update_entity(eid, area_id=area)

    # --- timers -------------------------------------------------------------------------

    @callback
    def start(self) -> None:
        self.world.ha_started(time.time())
        self._last_step = time.time()
        step = timedelta(seconds=self.scn.physics_step)
        self._unsubs.append(async_track_time_interval(self.hass, self._tick, step, name="simhome physics"))
        self._unsubs.append(
            async_track_time_interval(
                self.hass, self._sample, timedelta(seconds=self.scn.sample_interval), name="simhome sample"
            )
        )
        self._unsubs.append(
            async_track_time_interval(
                self.hass, self._observe, timedelta(seconds=OBSERVE_INTERVAL_S), name="simhome observe"
            )
        )
        self._unsubs.append(
            async_track_time_interval(
                self.hass, self._persist_cb, timedelta(seconds=PERSIST_INTERVAL_S), name="simhome persist"
            )
        )
        self._unsubs.append(
            async_track_time_interval(
                self.hass, self._flush_cb, timedelta(seconds=FLUSH_INTERVAL_S), name="simhome flush"
            )
        )
        self.event("ha", {"what": "started"})

    @callback
    def schedule_timeline(self) -> None:
        from .actions import run_timeline_item

        now = time.time()
        for item in self.scn.timeline:
            if item.index in self.done:
                continue
            when = self.scn.start + item.at
            if when <= now:
                self.hass.async_create_task(run_timeline_item(self, item))
            else:
                self._unsubs.append(
                    async_track_point_in_utc_time(
                        self.hass, partial(_run_at, self, item), dt_util.utc_from_timestamp(when)
                    )
                )

    @callback
    def _tick(self, _now: Any) -> None:
        now = time.time()
        dt = now - self._last_step
        if dt <= 0:
            return
        self._last_step = now
        changed = self.world.step(dt, now)
        self.write_states(changed)

    @callback
    def write_states(self, entity_ids: set[str] | None = None) -> None:
        targets = (
            self.entities if entity_ids is None else {e: self.entities[e] for e in entity_ids if e in self.entities}
        )
        for eid, ent in targets.items():
            if eid not in self.removed and ent.hass is not None:
                ent.async_write_ha_state()

    @callback
    def _sample(self, _now: Any) -> None:
        rec = self.world.sample()
        rec["t"] = round(time.time(), 1)
        self._buffers["samples"].append(json.dumps(rec, separators=(",", ":")))
        for ent in self.extra_entities:
            if ent.hass is not None:
                ent.async_write_ha_state()

    @callback
    def _observe(self, _now: Any) -> None:
        coordinator = (self.hass.data.get("roommind") or {}).get("coordinator")
        if coordinator is None:
            return
        rooms = {}
        for area_id, live in (getattr(coordinator, "rooms", None) or {}).items():
            rooms[area_id] = {k: v for k, v in live.items() if _jsonable(v)}
        rec = {"t": round(time.time(), 1), "rooms": rooms}
        self._buffers["observer"].append(json.dumps(rec, separators=(",", ":"), default=str))

    @callback
    def event(self, kind: str, data: dict[str, Any]) -> None:
        rec = {"t": round(time.time(), 3), "type": kind, **data}
        self._buffers["events"].append(json.dumps(rec, separators=(",", ":"), default=str))

    def log_command(self, entity_id: str, service: str, data: dict[str, Any], status: str) -> None:
        self.event("command", {"entity_id": entity_id, "service": service, "data": data, "result": status})

    # --- persistence ----------------------------------------------------------------------

    @callback
    def _persist_cb(self, _now: Any) -> None:
        self.hass.async_create_task(self.async_persist())

    @callback
    def _flush_cb(self, _now: Any) -> None:
        self.hass.async_create_task(self.async_flush())

    async def async_flush(self) -> None:
        buffers = {k: v for k, v in self._buffers.items() if v}
        self._buffers = {k: [] for k in self._buffers}
        if buffers:
            await self.hass.async_add_executor_job(_append_lines, self.dir / "timeline", buffers)

    async def async_persist(self) -> None:
        world = self.world.snapshot()
        runtime = {"timeline_done": sorted(self.done), "provisioned": self.provisioned, "removed": sorted(self.removed)}
        clock = self.clock.state() if self.clock else None
        await self.hass.async_add_executor_job(_write_state, self.dir / "state", world, runtime, clock)
        await self.async_flush()

    async def async_stop(self, _event: Any = None) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        self.event("ha", {"what": "stopping"})
        await self.async_persist()

    # --- provisioning -----------------------------------------------------------------------

    async def async_ensure_user(self) -> Any:
        auth = self.hass.auth
        users = [u for u in await auth.async_get_users() if u.name == SIM_USER_NAME and not u.system_generated]
        if users:
            user = users[0]
        else:
            user = await auth.async_create_user(SIM_USER_NAME, group_ids=[GROUP_ID_ADMIN])
            user.is_owner = True
            provider = next(p for p in auth.auth_providers if p.type == "trusted_networks")
            credentials = await provider.async_get_or_create_credentials({"user": user.id})
            await auth.async_link_user(user, credentials)
        token_file = self.dir / "token"
        if not token_file.exists():
            refresh = await auth.async_create_refresh_token(
                user,
                client_name="roommind-sim",
                token_type=TOKEN_TYPE_LONG_LIVED_ACCESS_TOKEN,
                access_token_expiration=timedelta(days=3650),
            )
            token = auth.async_create_access_token(refresh)
            await self.hass.async_add_executor_job(_write_secret, token_file, token)
        self.bridge = WsBridge(self.hass, user)
        return user

    async def async_provision(self) -> None:
        if self.provisioned:
            return
        assert self.bridge is not None
        if not self.hass.config_entries.async_entries("roommind"):
            await self.hass.config_entries.flow.async_init("roommind", context={"source": "user"}, data={})
            await self.hass.async_block_till_done()
        rm = self.scn.roommind
        settings = rm.get("settings") or {}
        if settings:
            await self.bridge.call("roommind/settings/save", settings)
        for area_id, room in (rm.get("rooms") or {}).items():
            payload = {"area_id": area_id, **room}
            await self.bridge.call("roommind/rooms/save", payload)
        self.provisioned = True
        self.event("ha", {"what": "provisioned", "rooms": sorted((rm.get("rooms") or {}).keys())})
        await self.async_persist()
        coordinator = (self.hass.data.get("roommind") or {}).get("coordinator")
        if coordinator is not None:
            await coordinator.async_refresh()


async def _run_at(rt: SimRuntime, item: Any, _now: Any) -> None:
    from .actions import run_timeline_item

    await run_timeline_item(rt, item)


def _jsonable(value: Any) -> bool:
    return isinstance(value, str | int | float | bool | type(None) | list | dict)


def _append_lines(folder: Path, buffers: dict[str, list[str]]) -> None:
    for name, lines in buffers.items():
        with (folder / f"{name}.jsonl").open("a") as fh:
            fh.write("\n".join(lines) + "\n")


def _write_state(folder: Path, world: dict[str, Any], runtime: dict[str, Any], clock: dict[str, Any] | None) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name, data in (("world", world), ("runtime", runtime), ("clock", clock)):
        if data is None:
            continue
        tmp = folder / f"{name}.json.tmp"
        tmp.write_text(json.dumps(data, default=_json_default))
        tmp.replace(folder / f"{name}.json")


def _json_default(value: Any) -> Any:
    if value == float("inf"):
        return 1e300
    return str(value)


def _write_secret(path: Path, token: str) -> None:
    path.write_text(token)
    path.chmod(0o600)
