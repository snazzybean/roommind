"""Tests for the residual heat utility module."""

from __future__ import annotations

import math

import pytest

from custom_components.roommind.control.residual_heat import (
    build_residual_series,
    compute_residual_heat,
    get_min_run_blocks,
)


# ---------------------------------------------------------------------------
# compute_residual_heat
# ---------------------------------------------------------------------------


def test_unknown_system_type_returns_zero():
    """Unknown or empty system type always returns 0."""
    assert compute_residual_heat(10, "", 1.0, 60.0) == 0.0
    assert compute_residual_heat(10, "unknown_type", 1.0, 60.0) == 0.0


def test_negative_elapsed_returns_zero():
    assert compute_residual_heat(-5, "underfloor", 1.0, 60.0) == 0.0


def test_underfloor_initial_value():
    """At t=0 with full charge, should return initial_fraction * power."""
    q = compute_residual_heat(0.0, "underfloor", 1.0, 9999.0)
    assert abs(q - 0.85) < 0.01


def test_radiator_initial_value():
    """At t=0 with full charge, should return initial_fraction * power."""
    q = compute_residual_heat(0.0, "radiator", 1.0, 9999.0)
    assert abs(q - 0.3) < 0.01


def test_underfloor_decays_over_time():
    """Residual heat should decay exponentially."""
    q0 = compute_residual_heat(0.0, "underfloor", 1.0, 9999.0)
    q30 = compute_residual_heat(30.0, "underfloor", 1.0, 9999.0)
    q90 = compute_residual_heat(90.0, "underfloor", 1.0, 9999.0)
    assert q0 > q30 > q90 > 0


def test_radiator_decays_faster_than_underfloor():
    """Radiator tau=10 vs underfloor tau=90; radiator should decay faster."""
    q_rad = compute_residual_heat(20.0, "radiator", 1.0, 9999.0)
    q_uf = compute_residual_heat(20.0, "underfloor", 1.0, 9999.0)
    assert q_uf > q_rad


def test_cutoff():
    """After very long time, residual should be exactly 0 (below cutoff)."""
    q = compute_residual_heat(1000.0, "underfloor", 1.0, 9999.0)
    assert q == 0.0


def test_power_fraction_scaling():
    """Half power should give half residual."""
    q_full = compute_residual_heat(10.0, "underfloor", 1.0, 9999.0)
    q_half = compute_residual_heat(10.0, "underfloor", 0.5, 9999.0)
    assert abs(q_half - q_full * 0.5) < 0.001


def test_charge_fraction_short_duration():
    """Short heating duration means less residual than long duration."""
    q_short = compute_residual_heat(0.0, "underfloor", 1.0, 10.0)
    q_long = compute_residual_heat(0.0, "underfloor", 1.0, 240.0)
    assert q_long > q_short


def test_charge_fraction_unknown_duration():
    """With 0 duration, charge_fraction should default to 1.0 (fully charged)."""
    q = compute_residual_heat(0.0, "underfloor", 1.0, 0.0)
    assert abs(q - 0.85) < 0.01


def test_charge_fraction_scales_correctly():
    """Verify charge_fraction formula: 1 - exp(-dur/tau_charge)."""
    # underfloor tau_charge = 60min, duration = 60min -> charge = 1 - exp(-1) ≈ 0.632
    q = compute_residual_heat(0.0, "underfloor", 1.0, 60.0)
    expected_charge = 1.0 - math.exp(-60.0 / 60.0)
    expected = 0.85 * expected_charge
    assert abs(q - expected) < 0.01


# ---------------------------------------------------------------------------
# build_residual_series
# ---------------------------------------------------------------------------


def test_series_length():
    """Series should have exactly n_blocks entries."""
    series = build_residual_series(0.0, "underfloor", 12, 5.0, 1.0, 120.0)
    assert len(series) == 12


def test_series_decays():
    """Each entry should be <= the previous one."""
    series = build_residual_series(0.0, "underfloor", 12, 5.0, 1.0, 120.0)
    for i in range(1, len(series)):
        assert series[i] <= series[i - 1]


def test_series_empty_system():
    """Unknown type yields all zeros."""
    series = build_residual_series(0.0, "", 6, 5.0, 1.0, 60.0)
    assert all(q == 0.0 for q in series)


def test_series_starts_from_elapsed():
    """Series starting at 30 min elapsed should match point-wise computation."""
    series = build_residual_series(30.0, "underfloor", 4, 5.0, 1.0, 120.0)
    for i, q in enumerate(series):
        expected = compute_residual_heat(30.0 + i * 5.0, "underfloor", 1.0, 120.0)
        assert abs(q - expected) < 1e-9


# ---------------------------------------------------------------------------
# get_min_run_blocks
# ---------------------------------------------------------------------------


def test_min_run_blocks_underfloor():
    """Underfloor min_run_minutes=30, dt=5 -> 6 blocks."""
    assert get_min_run_blocks("underfloor", 5.0) == 6


def test_min_run_blocks_radiator():
    """Radiator min_run_minutes=10, dt=5 -> 2 blocks."""
    assert get_min_run_blocks("radiator", 5.0) == 2


def test_min_run_blocks_unknown():
    """Unknown type falls back to 2."""
    assert get_min_run_blocks("", 5.0) == 2
    assert get_min_run_blocks("unknown", 5.0) == 2


def test_min_run_blocks_never_below_two():
    """Even with very small min_run_minutes, at least 2 blocks."""
    assert get_min_run_blocks("radiator", 60.0) == 2


def test_min_run_blocks_zero_dt():
    """Zero dt returns fallback."""
    assert get_min_run_blocks("underfloor", 0.0) == 2


def test_tau_zero_returns_zero():
    """A profile with tau=0 should return 0.0 to avoid division by zero."""
    from unittest.mock import patch
    from custom_components.roommind.control import residual_heat as rh

    fake_profiles = {"zero_tau": {"tau_minutes": 0, "initial_fraction": 0.5}}
    with patch.object(rh, "HEATING_SYSTEM_PROFILES", fake_profiles):
        result = rh.compute_residual_heat(5.0, "zero_tau", 1.0, 60.0)
    assert result == 0.0
