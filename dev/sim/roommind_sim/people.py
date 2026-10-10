"""People: weekly presence plan, room roles, overrides from the timeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .scenario.model import PersonSpec

SENSIBLE_W = 100.0
MOISTURE_KG_S = 0.05 / 3600  # 50 g/h


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _in_window(window: str, minute: int) -> bool:
    start, end = (_minutes(x) for x in window.split("-"))
    return start <= minute < end if start <= end else minute >= start or minute < end


@dataclass
class SimPerson:
    spec: PersonSpec
    room_roles: dict[str, str]  # role -> area_id
    tz: ZoneInfo
    override: tuple[bool, float | None] | None = None  # (home, until)
    home: bool = True
    room: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.spec.id

    def update(self, now: float) -> bool:
        local = datetime.fromtimestamp(now, self.tz)
        minute = local.hour * 60 + local.minute
        plan = self.spec.plan.get("presence") or {}
        entries = plan.get("weekend" if local.weekday() >= 5 else "weekday") or ["home@00:00"]
        home = True
        for entry in entries:
            state, at = entry.split("@")
            if _minutes(at) <= minute:
                home = state == "home"
        if self.override is not None:
            ov_home, until = self.override
            if until is None or now < until:
                home = ov_home
            else:
                self.override = None
        room = None
        if home:
            roles = self.spec.plan.get("rooms") or {}
            default = None
            for role, window in roles.items():
                if window == "default":
                    default = role
                elif _in_window(window, minute):
                    room = self.room_roles.get(role)
                    break
            if room is None and default:
                room = self.room_roles.get(default)
        changed = home != self.home or room != self.room
        self.home, self.room = home, room
        return changed

    def snapshot(self) -> dict[str, Any]:
        return {"override": list(self.override) if self.override else None, "home": self.home, "room": self.room}

    def restore(self, data: dict[str, Any]) -> None:
        ov = data.get("override")
        self.override = (ov[0], ov[1]) if ov else None
        self.home = data.get("home", True)
        self.room = data.get("room")
