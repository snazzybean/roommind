"""CSV-based rolling history store for RoomMind analytics."""

from __future__ import annotations

import csv
import logging
import os
import time

_LOGGER = logging.getLogger(__name__)

DETAIL_FIELDS = [
    "timestamp",
    "room_temp",
    "outdoor_temp",
    "target_temp",
    "mode",
    "predicted_temp",
    "window_open",
    "heating_power",
    "solar_irradiance",
    "blind_position",
    "cover_reason",
    "device_setpoint",
    "occupancy",
]
DETAIL_MAX_AGE = 48 * 3600  # 48 hours
HISTORY_MAX_AGE = 90 * 24 * 3600  # 90 days


class HistoryStore:
    """Per-room CSV rolling buffer for analytics data."""

    def __init__(self, base_dir: str) -> None:
        self._base_dir = base_dir

    def _ensure_dir(self) -> None:
        os.makedirs(self._base_dir, exist_ok=True)

    def _detail_path(self, area_id: str) -> str:
        return os.path.join(self._base_dir, f"{area_id}_detail.csv")

    def _history_path(self, area_id: str) -> str:
        return os.path.join(self._base_dir, f"{area_id}_history.csv")

    @staticmethod
    def _migrate_header(path: str) -> None:
        """Rewrite CSV with current DETAIL_FIELDS header if columns changed."""
        if not os.path.isfile(path):
            return
        try:
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames == DETAIL_FIELDS:
                    return
                rows = list(reader)
            with open(path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=DETAIL_FIELDS, extrasaction="ignore")
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, "") for k in DETAIL_FIELDS})
        except Exception:  # noqa: BLE001
            pass

    def record(self, area_id: str, data: dict, timestamp: float | None = None) -> None:
        """Append a data point to the detail CSV."""
        self._ensure_dir()
        ts = timestamp or time.time()
        path = self._detail_path(area_id)
        self._migrate_header(path)

        with open(path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=DETAIL_FIELDS)
            if os.path.getsize(path) == 0:
                writer.writeheader()
            writer.writerow(
                {
                    "timestamp": ts,
                    "room_temp": data.get("room_temp", ""),
                    "outdoor_temp": data.get("outdoor_temp", ""),
                    "target_temp": data.get("target_temp", ""),
                    "mode": data.get("mode", ""),
                    "predicted_temp": data.get("predicted_temp", ""),
                    "window_open": data.get("window_open", ""),
                    "heating_power": data.get("heating_power", ""),
                    "solar_irradiance": data.get("solar_irradiance", ""),
                    "blind_position": data.get("blind_position", ""),
                    "cover_reason": data.get("cover_reason", ""),
                    "device_setpoint": data.get("device_setpoint", ""),
                    "occupancy": data.get("occupancy", ""),
                }
            )

    def read_detail(
        self,
        area_id: str,
        max_age: float | None = None,
        start_ts: float | None = None,
        end_ts: float | None = None,
    ) -> list[dict]:
        """Read detail CSV rows, optionally filtered by age or timestamp range."""
        return self._read_csv(self._detail_path(area_id), max_age, start_ts, end_ts)

    def read_history(
        self,
        area_id: str,
        max_age: float | None = None,
        start_ts: float | None = None,
        end_ts: float | None = None,
    ) -> list[dict]:
        """Read history CSV rows."""
        return self._read_csv(self._history_path(area_id), max_age, start_ts, end_ts)

    def _read_csv(
        self,
        path: str,
        max_age: float | None = None,
        start_ts: float | None = None,
        end_ts: float | None = None,
    ) -> list[dict]:
        """Read CSV rows with safe timestamp parsing."""
        if not os.path.isfile(path):
            return []
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        cutoff_start: float | None = None
        if start_ts is not None:
            cutoff_start = start_ts
        elif max_age is not None:
            cutoff_start = time.time() - max_age
        if cutoff_start is not None or end_ts is not None:
            filtered = []
            for r in rows:
                try:
                    ts = float(r["timestamp"])
                    if cutoff_start is not None and ts < cutoff_start:
                        continue
                    if end_ts is not None and ts > end_ts:
                        continue
                    filtered.append(r)
                except (ValueError, TypeError, KeyError):
                    pass  # skip rows with corrupt timestamps
            rows = filtered
        return rows

    def rotate(self, area_id: str) -> None:
        """Downsample old detail rows to history, trim both files."""
        now = time.time()
        # Read detail, split into keep (< 48h) and archive (>= 48h)
        detail_rows = self.read_detail(area_id)
        cutoff = now - DETAIL_MAX_AGE
        keep = []
        archive = []
        for r in detail_rows:
            try:
                ts = float(r["timestamp"])
            except (ValueError, TypeError, KeyError):
                continue
            if ts >= cutoff:
                keep.append(r)
            else:
                archive.append(r)

        # Downsample archive to 5-min buckets and append to history
        if archive:
            downsampled = self._downsample(archive, bucket_seconds=300)
            self._append_history(area_id, downsampled)

        # Rewrite detail with only recent rows
        self._rewrite_csv(self._detail_path(area_id), keep)

        # Trim history older than 90 days
        history_rows = self.read_history(area_id)
        history_cutoff = now - HISTORY_MAX_AGE
        trimmed = [r for r in history_rows if self._safe_ts(r) >= history_cutoff]
        if len(trimmed) < len(history_rows):
            self._rewrite_csv(self._history_path(area_id), trimmed)

    def remove_room(self, area_id: str) -> None:
        """Delete all history files for a room."""
        for path in (self._detail_path(area_id), self._history_path(area_id)):
            if os.path.isfile(path):
                os.remove(path)

    def _downsample(self, rows: list[dict], bucket_seconds: int) -> list[dict]:
        """Average rows into time buckets."""
        if not rows:
            return []
        buckets: dict[int, list[dict]] = {}
        for row in rows:
            ts = float(row["timestamp"])
            bucket_key = int(ts // bucket_seconds)
            buckets.setdefault(bucket_key, []).append(row)

        result = []
        for bucket_key in sorted(buckets):
            bucket = buckets[bucket_key]
            avg_row = {
                "timestamp": bucket_key * bucket_seconds,
                "mode": bucket[0]["mode"],
                "window_open": bucket[0].get("window_open", ""),
                "device_setpoint": bucket[0].get("device_setpoint", ""),
            }
            for field in (
                "room_temp",
                "outdoor_temp",
                "target_temp",
                "predicted_temp",
                "heating_power",
                "solar_irradiance",
                "blind_position",
            ):
                vals = []
                for r in bucket:
                    v = r.get(field, "")
                    if v != "":
                        try:
                            vals.append(float(v))
                        except (ValueError, TypeError):
                            pass
                avg_row[field] = round(sum(vals) / len(vals), 2) if vals else ""
            result.append(avg_row)
        return result

    @staticmethod
    def _safe_ts(row: dict) -> float:
        """Return timestamp as float, or 0.0 on failure."""
        try:
            return float(row["timestamp"])
        except (ValueError, TypeError, KeyError):
            return 0.0

    def _append_history(self, area_id: str, rows: list[dict]) -> None:
        self._ensure_dir()
        path = self._history_path(area_id)
        file_exists = os.path.isfile(path)
        with open(path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=DETAIL_FIELDS)
            if not file_exists:
                writer.writeheader()
            writer.writerows(rows)

    def _rewrite_csv(self, path: str, rows: list[dict]) -> None:
        self._ensure_dir()
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=DETAIL_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
