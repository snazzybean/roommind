"""Builders for small worlds in tests."""

from __future__ import annotations

from typing import Any

from roommind_sim.scenario import load_scenario_dict
from roommind_sim.world import World

START = "2026-01-12T00:00"


def scenario(rooms: dict[str, Any], **extra: Any) -> dict[str, Any]:
    data = {
        "name": "unit",
        "start": START,
        "duration": "10d",
        "location": {"time_zone": "Europe/Berlin", "latitude": 52.5, "longitude": 13.4},
        "weather": {"profile": "temperate", "fixed": {"temperature": 0.0, "cloud": 100.0, "humidity": 80.0}},
        "house": {"building": "bestand_teilsaniert", "rooms": rooms},
    }
    data.update(extra)
    return data


def world(rooms: dict[str, Any], **extra: Any) -> World:
    return World(load_scenario_dict(scenario(rooms, **extra)))


def run(w: World, seconds: float, dt: float = 10.0, every=None) -> None:  # noqa: ANN001
    t = w.now
    end = t + seconds
    while t < end - 1e-9:
        t += dt
        w.step(dt, t)
        if every:
            every(w, t)
