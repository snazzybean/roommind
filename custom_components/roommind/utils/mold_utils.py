"""Mold risk detection utilities.

Calculates mold risk based on indoor temperature, humidity, and outdoor
temperature using building-physics methods (DIN 4108-2, ISO 13788).

The core approach: estimate the coldest wall surface temperature using the
temperature factor f_Rsi (default 0.80 for standard existing buildings), then compute
the relative humidity at that surface from the dew point.  Mold growth becomes
likely when surface RH exceeds ~80 %.
"""

from __future__ import annotations

import math

from ..const import (
    DEFAULT_MOLD_F_RSI,
    MOLD_PREVENTION_DELTAS,
    MOLD_RISK_CRITICAL,
    MOLD_RISK_OK,
    MOLD_RISK_WARNING,
    MOLD_SURFACE_RH_CRITICAL,
    MOLD_SURFACE_RH_WARNING,
)

# Magnus formula constants (Alduchov & Eskridge 1996, widely used approximation)
_A = 17.271
_B = 237.7  # °C


def dew_point(temp: float, rh: float) -> float:
    """Calculate dew point temperature using the Magnus formula.

    Args:
        temp: Air temperature in °C.
        rh: Relative humidity in % (0-100).

    Returns:
        Dew point temperature in °C.
    """
    rh_clamped = max(1.0, min(rh, 100.0))
    gamma = (_A * temp) / (_B + temp) + math.log(rh_clamped / 100.0)
    return (_B * gamma) / (_A - gamma)


def surface_rh(t_dew: float, t_surface: float) -> float:
    """Calculate relative humidity at a surface.

    Args:
        t_dew: Dew point temperature in °C.
        t_surface: Surface temperature in °C.

    Returns:
        Estimated surface relative humidity in % (clamped to 0-100).
    """
    e_dew = math.exp((_A * t_dew) / (_B + t_dew))
    e_surface = math.exp((_A * t_surface) / (_B + t_surface))
    return min(100.0, max(0.0, 100.0 * e_dew / e_surface))


def estimate_surface_temp(
    t_room: float,
    t_outdoor: float,
    f_rsi: float = DEFAULT_MOLD_F_RSI,
) -> float:
    """Estimate coldest wall surface temperature using temperature factor.

    Based on DIN 4108-2.  f_Rsi = 0.80 is a realistic value for standard
    existing buildings (DIN minimum is 0.70, modern buildings 0.85+).

    Args:
        t_room: Indoor air temperature in °C.
        t_outdoor: Outdoor temperature in °C.
        f_rsi: Temperature factor (0-1).  Higher = better insulated.

    Returns:
        Estimated surface temperature in °C.
    """
    return t_outdoor + f_rsi * (t_room - t_outdoor)


def calculate_mold_risk(
    t_room: float,
    rh_room: float,
    t_outdoor: float | None,
    f_rsi: float = DEFAULT_MOLD_F_RSI,
) -> tuple[str, float, float | None]:
    """Calculate mold risk level, estimated surface RH, and surface temperature.

    Uses the full dew-point / surface-temperature method when *t_outdoor* is
    available, otherwise falls back to a conservative room-air-RH assessment.

    Args:
        t_room: Indoor air temperature in °C.
        rh_room: Indoor relative humidity in % (0-100).
        t_outdoor: Outdoor temperature in °C, or None if unavailable.
        f_rsi: Temperature factor per DIN 4108-2 (0-1). Higher = better insulated.

    Returns:
        Tuple of (risk_level, surface_rh_percent, surface_temp_celsius).
        risk_level is one of MOLD_RISK_OK / MOLD_RISK_WARNING / MOLD_RISK_CRITICAL.
        surface_temp is None when t_outdoor is unavailable.
    """
    if t_outdoor is not None:
        # No lower temperature cut-off: a wall below 5 °C grows mold slowly, but it is
        # where condensate forms first, and the mold grows once the wall warms up again
        t_surface = estimate_surface_temp(t_room, t_outdoor, f_rsi=f_rsi)
        t_dew = dew_point(t_room, rh_room)
        srh = surface_rh(t_dew, t_surface)
    else:
        # Fallback: no outdoor temp → use room air RH with conservative offsets.
        # Typical wall surface is 3-5 °C colder → surface RH is ~10-15 % higher
        # than room air RH.  We approximate by shifting thresholds down.
        srh = rh_room + 10.0  # conservative estimate
        t_surface = None

    return _risk_from_surface_rh(srh), round(srh, 1), (round(t_surface, 1) if t_surface is not None else None)


def _risk_from_surface_rh(srh: float) -> str:
    """Map surface RH to risk level."""
    if srh >= MOLD_SURFACE_RH_CRITICAL:
        return MOLD_RISK_CRITICAL
    if srh >= MOLD_SURFACE_RH_WARNING:
        return MOLD_RISK_WARNING
    return MOLD_RISK_OK


def mold_prevention_delta(intensity: str) -> float:
    """Return temperature-raise delta for a prevention intensity level.

    Args:
        intensity: One of "light", "medium", "strong".

    Returns:
        Temperature increase in °C.
    """
    return MOLD_PREVENTION_DELTAS.get(intensity, 2.0)
