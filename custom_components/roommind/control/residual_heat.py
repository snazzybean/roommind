"""Residual heat modeling for thermal mass (underfloor heating, radiators).

After heating stops, the thermal mass (floor screed, radiator body) continues
releasing stored energy into the room.  This module provides functions to
compute the decaying residual heat fraction so that the EKF and MPC can
account for it instead of mis-attributing the continued warming to solar
gain or insulation effects.

The AC counterpart is the rebound charge: an AC cools the air, which drops
below the building mass and warms back up after the run (see thermal_model).
"""

from __future__ import annotations

import math

from ..const import AC_REBOUND_CUTOFF, AC_REBOUND_TAU_MINUTES, HEATING_SYSTEM_PROFILES, RESIDUAL_HEAT_CUTOFF


def compute_residual_heat(
    elapsed_minutes: float,
    system_type: str,
    last_power_fraction: float = 1.0,
    heating_duration_minutes: float = 0.0,
    scale: float = 1.0,
) -> float:
    """Compute normalised residual heat fraction after heating stopped.

    The result is in [0, initial_fraction] and represents the fraction of
    ``beta_h`` (learned heating rate) still being delivered by thermal mass.

    The *charge_fraction* accounts for how long heating was active before
    it stopped — a brief 10-minute run barely warms the screed, whereas
    a 4-hour run fully charges it.

    Args:
        elapsed_minutes: Time since heating stopped (must be >= 0).
        system_type: Key into ``HEATING_SYSTEM_PROFILES`` (e.g. "underfloor").
        last_power_fraction: Power fraction that was active before stopping.
        heating_duration_minutes: How long heating was active before stopping.
        scale: Learned per-room multiplier on the profile's ``initial_fraction``
            (see ``ResidualHeatLearner``); 1.0 is the profile as is.

    Returns:
        Residual heat fraction in [0, initial_fraction * scale].  Returns 0.0 for unknown or empty
        system types (backwards-compatible default).
    """
    profile = HEATING_SYSTEM_PROFILES.get(system_type)
    if not profile or elapsed_minutes < 0:
        return 0.0

    tau = profile["tau_minutes"]
    initial = profile["initial_fraction"]
    tau_charge = profile.get("tau_charge_minutes", tau)

    if tau <= 0:
        return 0.0

    # Charge fraction: how much energy the thermal mass absorbed
    if heating_duration_minutes > 0 and tau_charge > 0:
        charge_fraction = 1.0 - math.exp(-heating_duration_minutes / tau_charge)
    else:
        charge_fraction = 1.0  # assume fully charged if duration unknown

    q = initial * scale * charge_fraction * math.exp(-elapsed_minutes / tau) * last_power_fraction
    return q if q >= RESIDUAL_HEAT_CUTOFF else 0.0


def build_residual_series(
    elapsed_minutes: float,
    system_type: str,
    n_blocks: int,
    dt_minutes: float = 5.0,
    last_power_fraction: float = 1.0,
    heating_duration_minutes: float = 0.0,
    scale: float = 1.0,
) -> list[float]:
    """Build a decaying residual heat series for MPC lookahead.

    Each entry represents the q_residual at the start of the corresponding
    time block, evenly spaced by *dt_minutes*.

    Returns:
        List of length *n_blocks* with decaying residual fractions.
    """
    return [
        compute_residual_heat(
            elapsed_minutes + i * dt_minutes,
            system_type,
            last_power_fraction,
            heating_duration_minutes,
            scale,
        )
        for i in range(n_blocks)
    ]


def get_min_run_blocks(system_type: str, dt_minutes: float = 5.0) -> int:
    """Return the minimum number of MPC blocks for a given heating system.

    Falls back to 2 blocks (the existing default) when the system type is
    unknown or empty.
    """
    profile = HEATING_SYSTEM_PROFILES.get(system_type)
    if not profile or dt_minutes <= 0:
        return 2  # existing default
    return max(2, math.ceil(profile["min_run_minutes"] / dt_minutes))


def advance_rebound(charge: float, drive: float, dt_minutes: float) -> float:
    """AC rebound charge after *dt_minutes*.

    The charge (0..1) is the air's offset below the building mass relative to a
    long run. It relaxes towards *drive* (1 while the AC cools, 0 otherwise) with
    ``AC_REBOUND_TAU_MINUTES``. On/off, not the power fraction: a unit runs near
    full power until its own sensor is satisfied, a low proportional setpoint
    does not change that.
    """
    if dt_minutes <= 0:
        return charge
    result = drive + (charge - drive) * math.exp(-dt_minutes / AC_REBOUND_TAU_MINUTES)
    return result if result >= AC_REBOUND_CUTOFF else 0.0


def mean_rebound(charge: float, drive: float, dt_minutes: float) -> float:
    """Mean charge over *dt_minutes* starting at *charge* (the ``q_rebound`` of that step)."""
    if dt_minutes <= 0:
        return charge
    tau = AC_REBOUND_TAU_MINUTES
    return drive + (charge - drive) * tau / dt_minutes * (1.0 - math.exp(-dt_minutes / tau))
