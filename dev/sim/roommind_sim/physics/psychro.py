"""Moist-air helpers (Magnus formula, sea-level pressure)."""

from __future__ import annotations

import math

PRESSURE_PA = 101325.0
AIR_DENSITY = 1.2  # kg/m³
CP_AIR = 1005.0  # J/kgK
LATENT_HEAT = 2.45e6  # J/kg


def p_sat(temp_c: float) -> float:
    """Saturation vapour pressure over water in Pa."""
    return 611.2 * math.exp(17.62 * temp_c / (243.12 + temp_c))


def abs_humidity(temp_c: float, rh: float) -> float:
    """Humidity ratio x (kg water / kg dry air) from temperature and RH (0..100)."""
    pv = max(0.0, min(rh, 100.0)) / 100.0 * p_sat(temp_c)
    return 0.622 * pv / (PRESSURE_PA - pv)


def rel_humidity(temp_c: float, x: float) -> float:
    """RH (0..100) from temperature and humidity ratio; capped at 100."""
    pv = x * PRESSURE_PA / (0.622 + x)
    return max(0.0, min(100.0, 100.0 * pv / p_sat(temp_c)))


def dew_point(temp_c: float, rh: float) -> float:
    rh = max(rh, 0.1)
    gamma = math.log(rh / 100.0) + 17.62 * temp_c / (243.12 + temp_c)
    return 243.12 * gamma / (17.62 - gamma)
