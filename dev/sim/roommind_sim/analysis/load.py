"""Load a run directory into memory."""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..scenario import Scenario, load_scenario_dict


@dataclass
class Interval:
    start: float
    end: float
    value: Any

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class RunData:
    dir: Path
    scenario: Scenario
    samples: list[dict[str, Any]]
    observer: list[dict[str, Any]]
    events: list[dict[str, Any]]
    end: float
    storage: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def start(self) -> float:
        return self.scenario.start

    @property
    def commands(self) -> list[dict[str, Any]]:
        return [e for e in self.events if e.get("type") == "command"]

    def settings(self) -> dict[str, Any]:
        return (self.storage.get("settings") or {}) | {}

    def rooms_config(self) -> dict[str, Any]:
        return self.storage.get("rooms") or {}

    def observer_at(self, t: float) -> dict[str, Any] | None:
        """Last observer record at or before ``t``."""
        lo, hi = 0, len(self.observer) - 1
        best = None
        while lo <= hi:
            mid = (lo + hi) // 2
            if self.observer[mid]["t"] <= t:
                best = self.observer[mid]
                lo = mid + 1
            else:
                hi = mid - 1
        return best

    def sample_at(self, t: float) -> dict[str, Any] | None:
        lo, hi = 0, len(self.samples) - 1
        best = None
        while lo <= hi:
            mid = (lo + hi) // 2
            if self.samples[mid]["t"] <= t:
                best = self.samples[mid]
                lo = mid + 1
            else:
                hi = mid - 1
        return best

    def commanded_modes(self, entity_id: str) -> list[Interval]:
        """HVAC mode RoomMind commanded over time (from the service log, accepted only)."""
        out: list[Interval] = []
        mode = None
        since = self.start
        for c in self.commands:
            if c["entity_id"] != entity_id or not str(c.get("result", "")).startswith("accepted"):
                continue
            new = None
            if c["service"] == "set_hvac_mode":
                new = c["data"].get("hvac_mode")
            elif c["service"] == "set_temperature" and c["data"].get("hvac_mode"):
                new = c["data"]["hvac_mode"]
            elif c["service"] == "turn_off":
                new = "off"
            elif c["service"] == "turn_on":
                new = mode if mode and mode != "off" else "on"
            if new is not None and new != mode:
                if mode is not None:
                    out.append(Interval(since, c["t"], mode))
                mode, since = new, c["t"]
        if mode is not None:
            out.append(Interval(since, self.end, mode))
        return out

    def window_open_intervals(self) -> dict[str, list[Interval]]:
        """Per room, intervals with at least one window open (ground truth samples)."""
        out: dict[str, list[Interval]] = {a: [] for a in self.scenario.rooms}
        open_since: dict[str, float | None] = dict.fromkeys(self.scenario.rooms)
        for s in self.samples:
            for area, r in s["rooms"].items():
                is_open = r.get("windows_open", 0) > 0
                if is_open and open_since[area] is None:
                    open_since[area] = s["t"]
                elif not is_open and open_since[area] is not None:
                    out[area].append(Interval(open_since[area], s["t"], True))  # type: ignore[arg-type]
                    open_since[area] = None
        for area, since in open_since.items():
            if since is not None:
                out[area].append(Interval(since, self.end, True))
        return out


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if path.exists():
        lines = path.read_text().splitlines()
    elif path.with_suffix(".jsonl.gz").exists():
        lines = gzip.decompress(path.with_suffix(".jsonl.gz").read_bytes()).decode().splitlines()
    else:
        return []
    out = []
    for line in lines:
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a crash can leave a half-written last line
    return out


def load_run(run_dir: Path) -> RunData:
    scenario = load_scenario_dict(json.loads((run_dir / "scenario.json").read_text()))
    tl = run_dir / "timeline"
    samples = _read_jsonl(tl / "samples.jsonl")
    observer = _read_jsonl(tl / "observer.jsonl")
    events = _read_jsonl(tl / "events.jsonl")
    clock_file = run_dir / "state" / "clock.json"
    if clock_file.exists():
        clock = json.loads(clock_file.read_text())
        end = clock["epoch_start"] + clock["mono"]
    else:
        end = max([r["t"] for r in samples[-1:]] + [scenario.start])
    storage_file = run_dir / "config" / ".storage" / "roommind"
    storage = json.loads(storage_file.read_text()).get("data", {}) if storage_file.exists() else {}
    meta_file = run_dir / "meta.json"
    meta = json.loads(meta_file.read_text()) if meta_file.exists() else {}
    for rows in (samples, observer, events):
        rows.sort(key=lambda r: r.get("t", 0))
    return RunData(run_dir, scenario, samples, observer, events, end, storage, meta)
