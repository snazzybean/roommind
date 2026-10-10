"""Covers with travel time, tilt and shading of the room's windows (HA: 100 = open)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .devices.base import approach
from .scenario.model import CoverSpec


@dataclass
class SimCover:
    spec: CoverSpec
    position: float = 100.0
    tilt: float = 100.0
    target_position: float = 100.0
    target_tilt: float = 100.0
    available: bool = True

    @property
    def entity_id(self) -> str:
        return self.spec.entity_id

    @property
    def tilt_only(self) -> bool:
        return bool(self.spec.params.get("tilt_only"))

    @property
    def has_tilt(self) -> bool:
        return bool(self.spec.params.get("tilt"))

    def command(self, service: str, data: dict[str, Any]) -> bool:
        if service == "open_cover":
            self.target_position = 100
        elif service == "close_cover":
            self.target_position = 0
        elif service == "set_cover_position":
            self.target_position = float(data["position"])
        elif service == "stop_cover":
            self.target_position = self.position
            self.target_tilt = self.tilt
        elif service == "open_cover_tilt":
            self.target_tilt = 100
        elif service == "close_cover_tilt":
            self.target_tilt = 0
        elif service == "set_cover_tilt_position":
            self.target_tilt = float(data["tilt_position"])
        else:
            return False
        return True

    def step(self, dt: float) -> bool:
        p = self.spec.params
        before = (round(self.position), round(self.tilt))
        if not self.tilt_only:
            self.position = approach(self.position, self.target_position, 100 / float(p.get("travel_s", 25)), dt)
        if self.has_tilt:
            self.tilt = approach(self.tilt, self.target_tilt, 100 / float(p.get("tilt_travel_s", 3)), dt)
        return before != (round(self.position), round(self.tilt))

    @property
    def moving(self) -> str | None:
        if abs(self.position - self.target_position) > 0.5:
            return "opening" if self.target_position > self.position else "closing"
        return None

    def shading(self) -> float:
        """Fraction of solar gain blocked (0 = none)."""
        max_shading = float(self.spec.params.get("max_shading", 0.9))
        closed = 0.0 if self.tilt_only else 1 - self.position / 100
        if self.has_tilt:
            slats = 1 - self.tilt / 100
            closed = slats if self.tilt_only else closed * (0.4 + 0.6 * slats)
        return max_shading * max(0.0, min(1.0, closed))

    def snapshot(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in ("position", "tilt", "target_position", "target_tilt", "available")}

    def restore(self, data: dict[str, Any]) -> None:
        for k, v in data.items():
            setattr(self, k, v)
