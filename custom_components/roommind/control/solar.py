"""Solar irradiance estimation for thermal model solar gain.

Computes Global Horizontal Irradiance (GHI) from:
  1. Solar position (NOAA simplified equations) using latitude/longitude
  2. Clear-sky GHI via Meinel atmospheric transmittance model
  3. Cloud attenuation via Kasten-Czeplak (1980) model

No external dependencies — uses only ``math`` and ``time``.
"""

from __future__ import annotations

import math
import time
from datetime import UTC

# Solar constant (W/m²) — TSI at 1 AU
_SOLAR_CONSTANT: float = 1361.0


def _solar_position(latitude: float, longitude: float, timestamp: float) -> tuple[float, float]:
    """Return (elevation_deg, azimuth_deg) for a given location and time.

    Azimuth uses meteorological convention: 0=N, 90=E, 180=S, 270=W.
    Uses the NOAA simplified solar position equations.
    Negative elevation means the sun is below the horizon (night).
    """
    from datetime import datetime

    dt = datetime.fromtimestamp(timestamp, tz=UTC)
    day_of_year = dt.timetuple().tm_yday
    hour_utc = dt.hour + dt.minute / 60.0 + dt.second / 3600.0

    # Fractional year (radians)
    gamma = 2.0 * math.pi * (day_of_year - 1 + (hour_utc - 12.0) / 24.0) / 365.0

    # Equation of time (minutes)
    eqtime = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2.0 * gamma)
        - 0.040849 * math.sin(2.0 * gamma)
    )

    # Solar declination (radians)
    decl = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2.0 * gamma)
        + 0.000907 * math.sin(2.0 * gamma)
        - 0.002697 * math.cos(3.0 * gamma)
        + 0.00148 * math.sin(3.0 * gamma)
    )

    # True solar time and hour angle
    time_offset = eqtime + 4.0 * longitude  # minutes (UTC, no timezone offset)
    tst = hour_utc * 60.0 + time_offset
    ha = math.radians((tst / 4.0) - 180.0)

    # Solar elevation
    lat_rad = math.radians(latitude)
    sin_elev = math.sin(lat_rad) * math.sin(decl) + math.cos(lat_rad) * math.cos(decl) * math.cos(ha)
    sin_elev = max(-1.0, min(1.0, sin_elev))
    elevation_deg = math.degrees(math.asin(sin_elev))

    # Solar azimuth (meteorological: 0=N, 90=E, 180=S, 270=W)
    # NOAA convention: morning (ha<0) → 180+acos(…); afternoon (ha≥0) → (540-acos(…)) mod 360
    cos_elev = math.cos(math.radians(elevation_deg))
    if abs(cos_elev) < 1e-10:
        azimuth_deg = 180.0  # Sun directly overhead — arbitrary
    else:
        cos_az = (math.sin(lat_rad) * sin_elev - math.sin(decl)) / (cos_elev * math.cos(lat_rad))
        cos_az = max(-1.0, min(1.0, cos_az))
        arc = math.degrees(math.acos(cos_az))
        # ha < 0 = morning (sun in the east): azimuth ∈ [0°,180°]
        # ha ≥ 0 = afternoon/noon (sun in the south/west): azimuth ∈ [180°,360°]
        azimuth_deg = (540.0 - arc) % 360.0 if ha < 0 else 180.0 + arc

    return elevation_deg, azimuth_deg


def _solar_elevation(latitude: float, longitude: float, timestamp: float) -> float:
    """Return solar elevation angle in degrees (negative = below horizon)."""
    return _solar_position(latitude, longitude, timestamp)[0]


def solar_elevation(latitude: float, longitude: float, timestamp: float) -> float:
    """Public API: solar elevation angle in degrees (negative = below horizon)."""
    return _solar_position(latitude, longitude, timestamp)[0]


def solar_azimuth(latitude: float, longitude: float, timestamp: float) -> float:
    """Solar azimuth in degrees (0=N, 90=E, 180=S, 270=W)."""
    return _solar_position(latitude, longitude, timestamp)[1]


def surface_irradiance_factor(solar_az_deg: float, solar_el_deg: float, surface_az_deg: float) -> float:
    """Fraction of GHI that hits a vertical surface facing *surface_az_deg*.

    Returns 0–1. Night (elevation ≤ 0) or sun behind the surface → 0.
    """
    if solar_el_deg <= 0:
        return 0.0
    return max(
        0.0,
        math.cos(math.radians(solar_el_deg)) * math.cos(math.radians(solar_az_deg - surface_az_deg)),
    )


def _clear_sky_ghi(elevation_deg: float) -> float:
    """Estimate clear-sky GHI in W/m² using the Meinel model.

    Returns 0 when the sun is at or below the horizon.
    """
    if elevation_deg <= 0.0:
        return 0.0

    sin_elev = math.sin(math.radians(elevation_deg))

    # Air mass (Kasten & Young, 1989)
    am = 1.0 / (sin_elev + 0.50572 * (elevation_deg + 6.07995) ** (-1.6364))

    # Direct normal irradiance — Meinel model
    dni = _SOLAR_CONSTANT * 0.7 ** (am**0.678)

    # GHI = DNI × sin(elevation)
    return float(max(0.0, dni * sin_elev))


def _cloud_attenuation(cloud_coverage: float) -> float:
    """Kasten-Czeplak (1980) cloud attenuation factor.

    Args:
        cloud_coverage: 0-100 (percent).

    Returns:
        Multiplicative factor in (0, 1].
    """
    n = max(0.0, min(1.0, cloud_coverage / 100.0))
    return float(1.0 - 0.75 * (n**3.4))


# -- Public API --


def estimate_solar_ghi(
    latitude: float,
    longitude: float,
    timestamp: float,
    cloud_coverage: float | None = None,
) -> float:
    """Estimate Global Horizontal Irradiance in W/m².

    Args:
        latitude: degrees (from ``hass.config.latitude``).
        longitude: degrees (from ``hass.config.longitude``).
        timestamp: Unix timestamp (UTC).
        cloud_coverage: 0-100 percent (from weather entity).
            ``None`` → clear-sky (no attenuation).

    Returns:
        GHI in W/m² (0 at night, peaks ~900 W/m² at solar noon on clear day).
    """
    elev = _solar_elevation(latitude, longitude, timestamp)
    ghi = _clear_sky_ghi(elev)
    if cloud_coverage is not None and ghi > 0.0:
        ghi *= _cloud_attenuation(cloud_coverage)
    return ghi


def compute_q_solar_norm(
    latitude: float,
    longitude: float,
    timestamp: float,
    cloud_coverage: float | None = None,
) -> float:
    """Normalized solar irradiance for the thermal model.

    Returns ``GHI / 1000`` so that the value is in [0, ~1.0], making the
    learned parameter ``beta_s`` comparable in magnitude to ``beta_h`` and
    ``beta_c``.
    """
    return estimate_solar_ghi(latitude, longitude, timestamp, cloud_coverage) / 1000.0


def build_solar_series(
    latitude: float,
    longitude: float,
    n_blocks: int,
    dt_minutes: float = 5.0,
    *,
    start_ts: float | None = None,
    cloud_series: list[float | None] | None = None,
) -> list[float]:
    """Build a series of Q_solar_norm values for MPC/analytics lookahead.

    Args:
        latitude / longitude: site coordinates.
        n_blocks: number of future time blocks.
        dt_minutes: duration of each block.
        start_ts: start Unix timestamp (default: now).
        cloud_series: per-block cloud coverage (0-100 or None).
            If shorter than *n_blocks*, the last value is repeated.
            If ``None``, clear-sky is used for all blocks.
    """
    ts = start_ts if start_ts is not None else time.time()
    dt_sec = dt_minutes * 60.0

    # Prepare cloud values
    clouds: list[float | None]
    if cloud_series:
        clouds = list(cloud_series)
        while len(clouds) < n_blocks:
            clouds.append(clouds[-1])
    else:
        clouds = [None] * n_blocks

    series: list[float] = []
    for i in range(n_blocks):
        block_ts = ts + i * dt_sec
        cc = clouds[i] if i < len(clouds) else None
        series.append(compute_q_solar_norm(latitude, longitude, block_ts, cc))
    return series


def build_oriented_solar_series(
    latitude: float,
    longitude: float,
    n_blocks: int,
    surface_azimuths: list[float],
    dt_minutes: float = 5.0,
    *,
    start_ts: float | None = None,
    cloud_series: list[float | None] | None = None,
) -> list[float]:
    """Like *build_solar_series* but scaled by the average orientation factor.

    For each time step, the GHI is multiplied by the mean of
    ``surface_irradiance_factor(solar_az, solar_el, s)`` across all surface
    azimuths in *surface_azimuths*.  This correctly handles corner rooms with
    windows on multiple walls — each cover facing a different direction
    contributes equally to the average solar gain.

    Args:
        surface_azimuths: list of surface azimuths in degrees (0=N, 90=E …).
            Must not be empty.
    """
    ts = start_ts if start_ts is not None else time.time()
    base = build_solar_series(
        latitude,
        longitude,
        n_blocks,
        dt_minutes,
        start_ts=ts,
        cloud_series=cloud_series,
    )
    dt_sec = dt_minutes * 60.0
    result: list[float] = []
    for i, q in enumerate(base):
        step_ts = ts + i * dt_sec
        el, az = _solar_position(latitude, longitude, step_ts)
        avg_factor = sum(surface_irradiance_factor(az, el, s) for s in surface_azimuths) / len(surface_azimuths)
        result.append(q * avg_factor)
    return result
