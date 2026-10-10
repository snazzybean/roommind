"""Durations and points in time used by scenarios ("14d", "+2d3h", "now-7d", ISO)."""

from __future__ import annotations

import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from .errors import ScenarioError

_UNITS = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}
_DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)\s*([wdhms])")


def parse_duration(value: str | int | float, where: str = "") -> float:
    """Return seconds for ``"14d"``, ``"3h30m"``, ``"90s"`` or a plain number of seconds."""
    if isinstance(value, bool):
        raise ScenarioError(f"invalid duration {value!r}", where)
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip().lower().replace(" ", "")
    if not text:
        raise ScenarioError("empty duration", where)
    pos = 0
    total = 0.0
    for match in _DURATION_RE.finditer(text):
        if match.start() != pos:
            break
        total += float(match.group(1)) * _UNITS[match.group(2)]
        pos = match.end()
    if pos != len(text):
        raise ScenarioError(f"invalid duration {value!r} (use e.g. 14d, 3h30m, 90s)", where)
    return total


def parse_start(value: str | int | float | datetime | None, tz: str, where: str = "start") -> float:
    """Return the scenario start as epoch seconds.

    ``now``/``now-14d`` are relative to real time, rounded down to the minute, so a
    scenario that should end "now" for UI inspection can say ``start: now-14d``.
    """
    if value is None:
        value = "now"
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=ZoneInfo(tz))
        return dt.timestamp()
    text = str(value).strip()
    if text.startswith("now"):
        rest = text[3:]
        now = (time.time() // 60) * 60
        if not rest:
            return now
        if rest[0] not in "+-":
            raise ScenarioError(f"invalid start {value!r}", where)
        sign = -1 if rest[0] == "-" else 1
        return now + sign * parse_duration(rest[1:], where)
    return _parse_iso(text, tz, where)


def parse_at(value: str | int | float | datetime, start: float, tz: str, where: str = "at") -> float:
    """Return seconds since scenario start for an ISO time or ``+2d``/``+3d+30m`` offset."""
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=ZoneInfo(tz))
        return dt.timestamp() - start
    text = str(value).strip()
    if text.startswith("+"):
        return sum(parse_duration(part, where) for part in text[1:].split("+"))
    return _parse_iso(text, tz, where) - start


def _parse_iso(text: str, tz: str, where: str) -> float:
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as err:
        raise ScenarioError(f"invalid time {text!r} (ISO like 2026-01-12T06:00 or +2d)", where) from err
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    return dt.timestamp()


def format_offset(seconds: float) -> str:
    """Human-readable offset like ``+2d03h15m`` for logs and reports."""
    sign = "-" if seconds < 0 else "+"
    s = int(abs(seconds))
    days, s = divmod(s, 86400)
    hours, s = divmod(s, 3600)
    minutes, secs = divmod(s, 60)
    out = f"{sign}{days}d{hours:02d}h{minutes:02d}m"
    return out + (f"{secs:02d}s" if secs else "")
