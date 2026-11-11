"""Short in-memory temperature series per room for the dashboard cards."""

from __future__ import annotations

from collections import deque

RECENT_WINDOW_S = 6 * 3600
RECENT_STEP_S = 300


def _num(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def target_of(heat: object, target: object, cool: object, side: str = "heat") -> float | None:
    """The line the cards draw: the given side first, then the single target, then the other side."""
    order = (cool, target, heat) if side == "cool" else (heat, target, cool)
    for value in order:
        num = _num(value)
        if num is not None:
            return num
    return None


class RecentTemps:
    """Last six hours of room temperature and target in five-minute steps.

    Kept in memory and seeded once from the history detail after a start, so the cards show
    a curve right away. Compact on purpose: `rooms/list` is polled every few seconds.
    """

    def __init__(self) -> None:
        self._series: dict[str, deque[tuple[float, float, float | None]]] = {}
        self._seeded: set[str] = set()
        # Side of the last run per room: an auto room cooling in summer shows its cool target,
        # and keeps it while idle between runs instead of jumping to the heat target
        self._side: dict[str, str] = {}

    def target_for(self, area_id: str, mode: object, heat: object, target: object, cool: object) -> float | None:
        """Target of the side in force: cooling -> cool, heating -> heat, idle -> the last run's side."""
        if mode == "cooling":
            self._side[area_id] = "cool"
        elif mode == "heating":
            self._side[area_id] = "heat"
        return target_of(heat, target, cool, self._side.get(area_id, "heat"))

    def needs_seed(self, area_id: str) -> bool:
        return area_id not in self._seeded

    def seed(self, area_id: str, rows: list[dict], now: float) -> None:
        """Fill a room from history rows (CSV strings); points already recorded win."""
        self._seeded.add(area_id)
        existing = self._series.get(area_id)
        first_live = existing[0][0] if existing else None
        seeded: deque[tuple[float, float, float | None]] = deque()
        for row in rows:
            ts = _num(row.get("timestamp"))
            temp = _num(row.get("room_temp"))
            if ts is None or temp is None or ts < now - RECENT_WINDOW_S:
                continue
            if first_live is not None and ts > first_live - RECENT_STEP_S:
                continue
            if seeded and ts - seeded[-1][0] < RECENT_STEP_S:
                continue
            target = self.target_for(
                area_id, row.get("mode"), row.get("heat_target"), row.get("target_temp"), row.get("cool_target")
            )
            seeded.append((ts, round(temp, 2), None if target is None else round(target, 1)))
        if existing:
            seeded.extend(existing)
        if seeded:
            self._series[area_id] = seeded

    def add(self, area_id: str, ts: float, temp: float | None, target: float | None) -> None:
        if temp is None:
            return
        series = self._series.setdefault(area_id, deque())
        if series and ts - series[-1][0] < RECENT_STEP_S:
            return
        series.append((ts, round(temp, 2), None if target is None else round(target, 1)))
        while series and series[0][0] < ts - RECENT_WINDOW_S:
            series.popleft()

    def get(self, area_id: str) -> list[list[float | None]]:
        """`[[unix_ts, temp, target], ...]`, oldest first; target may be None."""
        return [[int(ts), temp, target] for ts, temp, target in self._series.get(area_id, ())]

    def forget(self, area_id: str) -> None:
        self._series.pop(area_id, None)
        self._side.pop(area_id, None)
        self._seeded.discard(area_id)
