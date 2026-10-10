"""Outdoor conditions: deterministic synthetic climate, CSV replay, overrides, forecasts.

Noise is a sum of seeded sinusoids, so the "future" is defined and a perfect
forecast (optionally with lead-time error) can be produced for weather.get_forecasts.
"""

from __future__ import annotations

import csv
import math
import random
from bisect import bisect_left
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .physics.psychro import abs_humidity
from .physics.solar import Irradiance, SunPosition, irradiance, sun_position
from .scenario.loader import deep_merge, load_profile

_NOISE_PERIODS_H = (31.0, 65.0, 122.0, 233.0)
_CLOUD_PERIODS_H = (5.0, 11.0, 23.0, 47.0)


@dataclass
class Outdoor:
    temp_c: float
    rh: float
    cloud_pct: float
    wind_kmh: float
    sun: SunPosition
    irradiance: Irradiance

    @property
    def x(self) -> float:
        return abs_humidity(self.temp_c, self.rh)

    @property
    def condition(self) -> str:
        if self.sun.elevation_deg <= 0:
            return "clear-night" if self.cloud_pct < 40 else "cloudy"
        if self.cloud_pct < 25:
            return "sunny"
        if self.cloud_pct < 70:
            return "partlycloudy"
        return "cloudy"


@dataclass
class _Override:
    start: float
    end: float | None
    values: dict[str, float]


class WeatherModel:
    def __init__(self, spec: dict[str, Any], latitude: float, longitude: float, time_zone: str, seed: int) -> None:
        profile = spec.get("profile", "temperate")
        base = load_profile("weather", profile, "weather.profile") if profile else {}
        self.p = deep_merge(base, {k: v for k, v in spec.items() if k not in ("profile", "entity_id")})
        self.lat = latitude
        self.lon = longitude
        self.tz = ZoneInfo(time_zone)
        rng = random.Random(f"weather:{seed}")
        self._phases = [rng.uniform(0, 2 * math.pi) for _ in range(8)]
        self._overrides: list[_Override] = []
        self.forecast_available = bool(self.p.get("forecast", True))
        self.forecast_error_c_per_day = float(self.p.get("forecast_error_c_per_day", 0.0))
        self._replay = _CsvReplay(Path(self.p["csv"]), self.p.get("columns") or {}) if self.p.get("csv") else None

    # --- public ----------------------------------------------------------------------

    def at(self, epoch: float) -> Outdoor:
        temp, rh, cloud, wind = self._base(epoch)
        for ov in self._overrides:
            if ov.start <= epoch and (ov.end is None or epoch < ov.end):
                temp = ov.values.get("temperature", temp) + ov.values.get("temperature_delta", 0.0)
                rh = ov.values.get("humidity", rh)
                cloud = ov.values.get("cloud", cloud)
                wind = ov.values.get("wind", wind)
        sun = sun_position(epoch, self.lat, self.lon)
        return Outdoor(temp, rh, cloud, wind, sun, irradiance(sun, cloud))

    def set_override(self, start: float, end: float | None, values: dict[str, float]) -> None:
        self._overrides.append(_Override(start, end, values))

    def forecast(self, epoch: float, kind: str = "hourly", hours: int = 48) -> list[dict[str, Any]]:
        """Forecast entries in HA's weather.get_forecasts shape (metric)."""
        out: list[dict[str, Any]] = []
        if kind == "daily":
            local = datetime.fromtimestamp(epoch, self.tz).replace(hour=0, minute=0, second=0, microsecond=0)
            for day in range(7):
                d0 = local + timedelta(days=day)
                samples = [self._fc(d0.timestamp() + h * 3600, epoch) for h in range(0, 24, 2)]
                out.append(
                    {
                        "datetime": d0.astimezone(UTC).isoformat(),
                        "temperature": round(max(s.temp_c for s in samples), 1),
                        "templow": round(min(s.temp_c for s in samples), 1),
                        "humidity": round(sum(s.rh for s in samples) / len(samples)),
                        "cloud_coverage": round(sum(s.cloud_pct for s in samples) / len(samples)),
                        "condition": samples[6].condition,
                        "wind_speed": round(samples[6].wind_kmh, 1),
                    }
                )
            return out
        first = (int(epoch) // 3600 + 1) * 3600
        for h in range(hours):
            ts = first + h * 3600
            s = self._fc(ts, epoch)
            out.append(
                {
                    "datetime": datetime.fromtimestamp(ts, UTC).isoformat(),
                    "temperature": round(s.temp_c, 1),
                    "humidity": round(s.rh),
                    "cloud_coverage": round(s.cloud_pct),
                    "condition": s.condition,
                    "wind_speed": round(s.wind_kmh, 1),
                }
            )
        return out

    # --- internals ---------------------------------------------------------------------

    def _fc(self, ts: float, now: float) -> Outdoor:
        o = self.at(ts)
        if self.forecast_error_c_per_day:
            lead_days = max(0.0, (ts - now) / 86400)
            o.temp_c += self.forecast_error_c_per_day * lead_days * math.sin(ts / 40000 + self._phases[7])
        return o

    def _base(self, epoch: float) -> tuple[float, float, float, float]:
        fixed = self.p.get("fixed") or {}
        if self._replay is not None:
            temp, rh, cloud = self._replay.at(epoch)
        else:
            local = datetime.fromtimestamp(epoch, self.tz)
            month_pos = local.month - 1 + (local.day - 1) / 30.4 - 0.5
            mean = _monthly(self.p["monthly_mean_c"], month_pos)
            amp = _monthly(self.p["daily_amplitude_c"], month_pos)
            hour = local.hour + local.minute / 60
            diurnal = amp / 2 * math.cos(2 * math.pi * (hour - 15) / 24)
            hours = epoch / 3600
            noise = float(self.p.get("noise_c", 1.5)) * _smooth_noise(hours, _NOISE_PERIODS_H, self._phases[:4])
            temp = mean + diurnal + noise
            cloud_mean = _monthly(self.p["mean_cloud"], month_pos)
            cloud = cloud_mean + 45 * _smooth_noise(hours, _CLOUD_PERIODS_H, self._phases[4:8])
            rh_mean = _monthly(self.p["humidity_rh"], month_pos)
            rh = rh_mean - 1.5 * diurnal + 0.1 * (cloud - cloud_mean)
        wind = 8 + 6 * _smooth_noise(epoch / 3600, (7.0, 19.0), self._phases[2:4])
        temp = fixed.get("temperature", temp)
        rh = fixed.get("humidity", rh)
        cloud = fixed.get("cloud", cloud)
        return temp, max(15.0, min(100.0, rh)), max(0.0, min(100.0, cloud)), max(0.0, wind)


def _monthly(values: list[float], pos: float) -> float:
    i = math.floor(pos)
    frac = pos - i
    a = values[i % 12]
    b = values[(i + 1) % 12]
    w = (1 - math.cos(math.pi * frac)) / 2
    return a + (b - a) * w


def _smooth_noise(hours: float, periods: tuple[float, ...], phases: list[float]) -> float:
    total = sum(math.sin(2 * math.pi * hours / p + ph) for p, ph in zip(periods, phases, strict=False))
    return total / math.sqrt(len(periods) / 2)


class _CsvReplay:
    """Replay outdoor values from a CSV (timestamp epoch or ISO; temp, humidity, cloud columns)."""

    def __init__(self, path: Path, columns: dict[str, str]) -> None:
        cols = {"timestamp": "timestamp", "temperature": "outdoor_temp", "humidity": "", "cloud": ""} | columns
        self.ts: list[float] = []
        self.rows: list[tuple[float, float | None, float | None]] = []
        with path.open() as fh:
            for row in csv.DictReader(fh):
                raw_ts = row.get(cols["timestamp"], "")
                temp = row.get(cols["temperature"], "")
                if not raw_ts or temp in ("", None):
                    continue
                try:
                    ts = float(raw_ts)
                except ValueError:
                    ts = datetime.fromisoformat(raw_ts).timestamp()
                hum = row.get(cols["humidity"]) if cols["humidity"] else None
                cloud = row.get(cols["cloud"]) if cols["cloud"] else None
                self.ts.append(ts)
                self.rows.append((float(temp), float(hum) if hum else None, float(cloud) if cloud else None))
        if not self.ts:
            raise ValueError(f"no usable rows in {path}")

    def at(self, epoch: float) -> tuple[float, float, float]:
        i = bisect_left(self.ts, epoch)
        if i <= 0:
            row = self.rows[0]
        elif i >= len(self.ts):
            row = self.rows[-1]
        else:
            t0, t1 = self.ts[i - 1], self.ts[i]
            a, b = self.rows[i - 1], self.rows[i]
            w = (epoch - t0) / (t1 - t0) if t1 > t0 else 0
            row = (a[0] + (b[0] - a[0]) * w, a[1], a[2])
        return row[0], row[1] if row[1] is not None else 75.0, row[2] if row[2] is not None else 60.0
