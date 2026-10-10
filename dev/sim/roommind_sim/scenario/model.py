"""Resolved scenario data model (profiles merged, times converted to seconds)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Location:
    latitude: float = 52.5
    longitude: float = 13.4
    elevation: float = 34.0
    time_zone: str = "Europe/Berlin"
    unit_system: str = "metric"  # or "us_customary"
    country: str = "DE"


@dataclass
class DeviceSpec:
    """A climate device: ``model`` picks the class, the rest configures it."""

    entity_id: str
    room: str
    model: str
    name: str
    profile: str
    capabilities: dict[str, Any] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    quirks: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SensorSpec:
    entity_id: str
    kind: str  # temperature | humidity | occupancy | outdoor_temperature | outdoor_humidity
    room: str | None
    name: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class WindowSpec:
    room: str
    index: int
    orientation: str = "S"
    area_m2: float = 1.5
    g_value: float = 0.6
    sensor: str | None = None
    name: str = ""


@dataclass
class CoverSpec:
    entity_id: str
    room: str
    name: str
    windows: list[int] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class RoomSpec:
    area_id: str
    name: str
    floor: str | None
    thermal: dict[str, Any]
    devices: list[DeviceSpec] = field(default_factory=list)
    sensors: list[SensorSpec] = field(default_factory=list)
    windows: list[WindowSpec] = field(default_factory=list)
    covers: list[CoverSpec] = field(default_factory=list)
    neighbors: dict[str, str | float] = field(default_factory=dict)
    initial: dict[str, float] = field(default_factory=dict)


@dataclass
class PersonSpec:
    id: str
    name: str
    tracker: str
    plan: dict[str, Any] = field(default_factory=dict)
    rooms: dict[str, str] = field(default_factory=dict)  # role (sleeping, living, ...) -> area_id


@dataclass
class TimelineItem:
    index: int
    at: float  # seconds since scenario start
    action: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class Scenario:
    name: str
    description: str
    refs: list[int]
    tags: list[str]
    location: Location
    start: float  # epoch seconds
    duration: float  # seconds
    seed: int
    physics_step: float
    sample_interval: float
    weather: dict[str, Any]
    rooms: dict[str, RoomSpec]
    floors: dict[str, str]
    outdoor_sensors: list[SensorSpec]
    people: list[PersonSpec]
    helpers: dict[str, Any]
    roommind: dict[str, Any]
    timeline: list[TimelineItem]
    expect: list[dict[str, Any]]
    known_failure: str | None = None
    external_entities: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    replay: dict[str, Any] = field(default_factory=dict)
    source_path: Path | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def all_devices(self) -> list[DeviceSpec]:
        return [d for r in self.rooms.values() for d in r.devices]

    def all_sensors(self) -> list[SensorSpec]:
        return [s for r in self.rooms.values() for s in r.sensors] + self.outdoor_sensors

    def entity_ids(self) -> set[str]:
        """Every entity the simulation (or HA helper YAML) will provide."""
        ids: set[str] = {d.entity_id for d in self.all_devices()}
        ids |= {s.entity_id for s in self.all_sensors()}
        for room in self.rooms.values():
            ids |= {w.sensor for w in room.windows if w.sensor}
            ids |= {c.entity_id for c in room.covers}
        for person in self.people:
            ids.add(f"person.{person.id}")
            ids.add(person.tracker)
        ids.add(self.weather.get("entity_id", "weather.simhome"))
        for domain, items in self.helpers.items():
            for object_id in items or {}:
                ids.add(object_id if "." in object_id else f"{domain}.{object_id}")
        return ids
