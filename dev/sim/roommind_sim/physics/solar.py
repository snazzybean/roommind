"""Sun position (NOAA) and irradiance on vertical windows.

Deliberately independent of RoomMind's control/solar.py so the simulation does not
just confirm the controller's own assumptions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

ORIENTATION_DEG = {"N": 0, "NE": 45, "E": 90, "SE": 135, "S": 180, "SW": 225, "W": 270, "NW": 315}


@dataclass
class SunPosition:
    elevation_deg: float
    azimuth_deg: float  # clockwise from north


def sun_position(epoch: float, latitude: float, longitude: float) -> SunPosition:
    jd = epoch / 86400.0 + 2440587.5
    t = (jd - 2451545.0) / 36525.0
    l0 = (280.46646 + t * (36000.76983 + 0.0003032 * t)) % 360
    m = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    mr = math.radians(m)
    c = (
        math.sin(mr) * (1.914602 - t * (0.004817 + 0.000014 * t))
        + math.sin(2 * mr) * (0.019993 - 0.000101 * t)
        + math.sin(3 * mr) * 0.000289
    )
    true_long = l0 + c
    omega = 125.04 - 1934.136 * t
    app_long = true_long - 0.00569 - 0.00478 * math.sin(math.radians(omega))
    eps0 = 23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60
    eps = math.radians(eps0 + 0.00256 * math.cos(math.radians(omega)))
    decl = math.asin(math.sin(eps) * math.sin(math.radians(app_long)))
    y = math.tan(eps / 2) ** 2
    l0r = math.radians(l0)
    eq_time = 4 * math.degrees(
        y * math.sin(2 * l0r)
        - 2 * e * math.sin(mr)
        + 4 * e * y * math.sin(mr) * math.cos(2 * l0r)
        - 0.5 * y * y * math.sin(4 * l0r)
        - 1.25 * e * e * math.sin(2 * mr)
    )
    minutes_utc = (epoch % 86400) / 60.0
    true_solar = (minutes_utc + eq_time + 4 * longitude) % 1440
    hour_angle = math.radians(true_solar / 4 - 180)
    lat = math.radians(latitude)
    cos_zen = math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.cos(hour_angle)
    zen = math.acos(max(-1.0, min(1.0, cos_zen)))
    elevation = 90 - math.degrees(zen)
    az_den = math.cos(lat) * math.sin(zen)
    if abs(az_den) < 1e-9:
        azimuth = 180.0
    else:
        cos_az = (math.sin(lat) * math.cos(zen) - math.sin(decl)) / az_den
        az = math.degrees(math.acos(max(-1.0, min(1.0, cos_az))))
        azimuth = (az + 180) % 360 if hour_angle > 0 else (540 - az) % 360
    return SunPosition(elevation, azimuth)


@dataclass
class Irradiance:
    dni: float  # W/m² direct normal
    dhi: float  # W/m² diffuse horizontal
    ghi: float  # W/m² global horizontal


def irradiance(sun: SunPosition, cloud_pct: float) -> Irradiance:
    """Clear-sky (air-mass model) attenuated by cloud cover (Kasten-Czeplak shape)."""
    if sun.elevation_deg <= 0:
        return Irradiance(0.0, 0.0, 0.0)
    zen = math.radians(90 - sun.elevation_deg)
    air_mass = 1 / (math.cos(zen) + 0.50572 * (96.07995 - math.degrees(zen)) ** -1.6364)
    dni_clear = 1353 * 0.7 ** (air_mass**0.678)
    sin_el = math.sin(math.radians(sun.elevation_deg))
    dhi_clear = 0.1 * dni_clear * sin_el + 20 * sin_el
    c = max(0.0, min(cloud_pct, 100.0)) / 100.0
    direct_factor = 1 - c**1.2  # thick clouds block the beam almost entirely
    global_factor = 1 - 0.75 * c**3.4
    dni = dni_clear * direct_factor
    ghi = (dni_clear * sin_el + dhi_clear) * global_factor
    dhi = max(0.0, ghi - dni * sin_el)
    return Irradiance(dni, dhi, ghi)


def window_gain_w(sun: SunPosition, irr: Irradiance, orientation: str | float, area_m2: float, g_value: float) -> float:
    """Solar heat through a vertical window (before shading)."""
    if irr.ghi <= 0:
        return 0.0
    win_az = ORIENTATION_DEG.get(str(orientation).upper(), None)
    win_az = float(orientation) if win_az is None else win_az
    el = math.radians(sun.elevation_deg)
    cos_inc = math.cos(el) * math.cos(math.radians(sun.azimuth_deg - win_az))
    beam = irr.dni * max(0.0, cos_inc)
    diffuse = irr.dhi * 0.5 + irr.ghi * 0.2 * 0.5  # sky view + ground reflection
    return area_m2 * g_value * (beam + diffuse)
