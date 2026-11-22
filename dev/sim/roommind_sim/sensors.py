"""Sensor models: noise, offset, resolution, report policy, availability."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

from .scenario.model import SensorSpec


@dataclass
class SimSensor:
    spec: SensorSpec
    seed: int
    value: float | None = None  # last reported (what HA shows)
    last_report: float = -1e12
    unavailable_until: float = 0.0  # epoch; inf = until made available again
    sensed: float | None = None  # element temperature behind the housing (``time_constant_s``)
    sensed_at: float = 0.0
    _rng: random.Random = field(init=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(f"{self.seed}:{self.spec.entity_id}")

    @property
    def entity_id(self) -> str:
        return self.spec.entity_id

    def available(self, now: float) -> bool:
        return now >= self.unavailable_until

    def update(self, true_value: float, now: float, boot_time: float) -> bool:
        """Feed the true value; returns True when the reported state changed."""
        p = self.spec.params
        tau = float(p.get("time_constant_s", 0.0))
        if tau > 0:
            if self.sensed is None:
                self.sensed = true_value
            else:
                self.sensed += (true_value - self.sensed) * (1 - math.exp(-max(0.0, now - self.sensed_at) / tau))
            self.sensed_at = now
            true_value = self.sensed
        if now - boot_time < float(p.get("unavailable_after_start_s", 0)):
            return False
        noise = float(p.get("noise", 0.0))
        measured = true_value + float(p.get("offset", 0.0)) + (self._rng.gauss(0, noise) if noise else 0.0)
        noise_rel = float(p.get("noise_rel", 0.0))
        if noise_rel:
            measured += self._rng.gauss(0, noise_rel * abs(true_value))
        if p.get("min_value") is not None:
            measured = max(float(p["min_value"]), measured)
        if p.get("max_value") is not None:
            measured = min(float(p["max_value"]), measured)
        res = float(p.get("resolution", 0.1))
        measured = round(round(measured / res) * res, 4)
        rep: dict[str, Any] = p.get("report") or {}
        since = now - self.last_report
        if since < float(rep.get("min_interval_s", 0)):
            return False
        heartbeat = since >= float(rep.get("heartbeat_s", 600))
        if self.value is None or abs(measured - self.value) >= float(rep.get("min_delta", 0.0)) - 1e-9 or heartbeat:
            changed = measured != self.value
            self.value = measured
            self.last_report = now
            return changed or heartbeat
        return False

    def snapshot(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "last_report": self.last_report,
            "unavailable_until": self.unavailable_until,
            "sensed": self.sensed,
            "sensed_at": self.sensed_at,
        }

    def restore(self, data: dict[str, Any]) -> None:
        self.value = data.get("value")
        self.last_report = data.get("last_report", -1e12)
        self.unavailable_until = data.get("unavailable_until", 0.0)
        self.sensed = data.get("sensed")
        self.sensed_at = data.get("sensed_at", 0.0)


@dataclass
class SimOccupancy:
    spec: SensorSpec
    on: bool = False
    last_seen: float = -1e12
    unavailable_until: float = 0.0

    @property
    def entity_id(self) -> str:
        return self.spec.entity_id

    def available(self, now: float) -> bool:
        return now >= self.unavailable_until

    def update(self, occupants: int, now: float) -> bool:
        if occupants > 0:
            self.last_seen = now
        new = occupants > 0 or now - self.last_seen < float(self.spec.params.get("off_delay_s", 120))
        changed = new != self.on
        self.on = new
        return changed

    def snapshot(self) -> dict[str, Any]:
        return {"on": self.on, "last_seen": self.last_seen, "unavailable_until": self.unavailable_until}

    def restore(self, data: dict[str, Any]) -> None:
        self.on = data.get("on", False)
        self.last_seen = data.get("last_seen", -1e12)
        self.unavailable_until = data.get("unavailable_until", 0.0)
