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


class RecentTemps:
    """Last six hours of room temperature and target in five-minute steps.

    Kept in memory and seeded once from the history detail after a start, so the cards show
    a curve right away. Compact on purpose: `rooms/list` is polled every few seconds.
    """

    def __init__(self) -> None:
        self._series: dict[str, deque[tuple[float, float, float | None]]] = {}
        self._seeded: set[str] = set()

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
            target = _num(row.get("heat_target"))
            if target is None:
                target = _num(row.get("target_temp"))
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
        self._seeded.discard(area_id)
