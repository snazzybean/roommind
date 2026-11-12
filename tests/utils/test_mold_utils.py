"""Tests for mold_utils.py — mold risk calculation utilities."""

import pytest

from custom_components.roommind.utils.mold_utils import (
    calculate_mold_risk,
    dew_point,
    estimate_surface_temp,
    mold_prevention_delta,
    surface_rh,
)

# --- dew_point ---


def test_dew_point_standard_conditions():
    """21°C / 60% RH → dew point ≈ 12.9°C."""
    dp = dew_point(21.0, 60.0)
    assert dp == pytest.approx(12.97, abs=0.1)


def test_dew_point_high_humidity():
    """At 100% RH, dew point equals air temperature."""
    dp = dew_point(20.0, 100.0)
    assert dp == pytest.approx(20.0, abs=0.1)


def test_dew_point_low_humidity():
    """Very low humidity → very low dew point."""
    dp = dew_point(20.0, 20.0)
    assert dp < 0.0


def test_dew_point_cold_conditions():
    """Cold air with moderate humidity."""
    dp = dew_point(5.0, 80.0)
    assert 1.0 < dp < 4.0


# --- surface_rh ---


def test_surface_rh_at_dew_point():
    """Surface at dew point → ~100% RH."""
    t_dew = dew_point(20.0, 50.0)
    srh = surface_rh(t_dew, t_dew)
    assert srh == pytest.approx(100.0, abs=0.5)


def test_surface_rh_above_dew_point():
    """Surface above dew point → RH < 100%."""
    t_dew = dew_point(20.0, 50.0)
    srh = surface_rh(t_dew, t_dew + 5.0)
    assert 50.0 < srh < 100.0


def test_surface_rh_well_above_dew_point():
    """Surface well above dew point → low RH."""
    t_dew = dew_point(20.0, 40.0)
    srh = surface_rh(t_dew, 20.0)
    # Surface at room temp → surface RH == room RH
    assert srh == pytest.approx(40.0, abs=1.0)


def test_surface_rh_clamped_to_100():
    """Cannot exceed 100%."""
    srh = surface_rh(20.0, 10.0)  # dew point far above surface
    assert srh == 100.0


# --- estimate_surface_temp ---


def test_estimate_surface_temp_standard():
    """20°C inside, -5°C outside, f_Rsi=0.70 → 12.5°C surface."""
    t_surface = estimate_surface_temp(20.0, -5.0, f_rsi=0.70)
    assert t_surface == pytest.approx(12.5, abs=0.01)


def test_estimate_surface_temp_perfect_insulation():
    """f_Rsi=1.0 → surface = indoor temp."""
    t_surface = estimate_surface_temp(20.0, 0.0, f_rsi=1.0)
    assert t_surface == pytest.approx(20.0, abs=0.01)


def test_estimate_surface_temp_no_insulation():
    """f_Rsi=0.0 → surface = outdoor temp."""
    t_surface = estimate_surface_temp(20.0, 0.0, f_rsi=0.0)
    assert t_surface == pytest.approx(0.0, abs=0.01)


def test_estimate_surface_temp_warm_outside():
    """When outdoor is warm, surface stays between indoor and outdoor."""
    t_surface = estimate_surface_temp(22.0, 30.0, f_rsi=0.70)
    assert 22.0 <= t_surface <= 30.0


# --- calculate_mold_risk ---


def test_calculate_mold_risk_ok():
    """Normal conditions: 20°C, 45% RH, 10°C outside → ok."""
    level, srh, _t = calculate_mold_risk(20.0, 45.0, 10.0)
    assert level == "ok"
    assert srh < 65.0


def test_calculate_mold_risk_warning():
    """Higher humidity with cool outside → warning (surface RH 70-80%)."""
    # 20°C, 60% RH, 5°C outside → surface 16.25°C (f_Rsi=0.75), surface RH ~76%
    level, srh, _t = calculate_mold_risk(20.0, 60.0, 5.0)
    assert level == "warning"
    assert 70.0 <= srh < 80.0


def test_calculate_mold_risk_critical():
    """High humidity with very cold outside → critical."""
    level, srh, _t = calculate_mold_risk(18.0, 75.0, -5.0)
    assert level == "critical"
    assert srh >= 80.0


def test_calculate_mold_risk_no_outdoor_temp():
    """Fallback: no outdoor temp → uses room RH + 10% offset."""
    level, srh, _t = calculate_mold_risk(20.0, 45.0, None)
    assert level == "ok"
    assert srh == pytest.approx(55.0, abs=0.1)

    # High room RH → warning in fallback mode
    level2, srh2, _t2 = calculate_mold_risk(20.0, 60.0, None)
    assert level2 == "warning"

    # Very high room RH → critical in fallback mode
    level3, srh3, _t3 = calculate_mold_risk(20.0, 72.0, None)
    assert level3 == "critical"


def test_calculate_mold_risk_warm_conditions_ok():
    """Warm outside, moderate humidity → always ok."""
    level, srh, _t = calculate_mold_risk(22.0, 55.0, 20.0)
    assert level == "ok"


def test_calculate_mold_risk_respects_custom_f_rsi():
    """A lower f_Rsi (worse insulation) must produce a colder surface and
    therefore a higher surface RH for the same room/outdoor conditions.
    """
    # 20°C inside, 0°C outside, 60% RH → warning with default f_Rsi=0.80
    # surface = 0 + 0.80 * 20 = 16°C; surface RH ≈ 77% (warning)
    level_default, srh_default, _ = calculate_mold_risk(20.0, 60.0, 0.0)
    assert level_default == "warning"

    # Worse insulation (f_Rsi=0.60) → colder wall → higher surface RH
    level_poor, srh_poor, _ = calculate_mold_risk(20.0, 60.0, 0.0, f_rsi=0.60)
    assert srh_poor > srh_default

    # Better insulation (f_Rsi=1.0) → wall equals indoor → surface RH ≈ room RH
    level_good, srh_good, _ = calculate_mold_risk(20.0, 60.0, 0.0, f_rsi=1.0)
    assert srh_good < srh_default
    assert srh_good == pytest.approx(60.0, abs=1.0)


def test_calculate_mold_risk_f_rsi_can_change_risk_level():
    """A sufficiently high f_Rsi can demote a borderline critical case to
    warning or below — and a low f_Rsi can promote a borderline case.
    """
    # 20°C inside, 70% RH, -5°C outside → critical with default f_Rsi=0.80
    # surface = -5 + 0.80 * 25 = 15°C; surface RH > 95% (critical)
    _, srh_default, _ = calculate_mold_risk(20.0, 70.0, -5.0)
    level_default, _, _ = calculate_mold_risk(20.0, 70.0, -5.0)
    assert level_default == "critical"

    # Better insulation reduces the risk level
    level_better, srh_better, _ = calculate_mold_risk(20.0, 70.0, -5.0, f_rsi=0.95)
    assert srh_better < srh_default
    assert level_better in ("warning", "ok")

    # Poor insulation promotes a borderline warning: 20°C, 60% RH, 0°C → warning at 0.80
    assert calculate_mold_risk(20.0, 60.0, 0.0)[0] == "warning"
    assert calculate_mold_risk(20.0, 60.0, 0.0, f_rsi=0.65)[0] == "critical"


def test_calculate_mold_risk_returns_surface_temp():
    """calculate_mold_risk returns the estimated wall surface temperature
    alongside the risk level and surface RH.  It must be a number between
    outdoor and indoor temperature, and None when no outdoor temp is
    available.
    """
    level, srh, t_surface = calculate_mold_risk(20.0, 60.0, 0.0)
    assert level == "warning"
    assert srh >= 70.0
    # f_Rsi=0.80: surface = 0 + 0.80 * (20 - 0) = 16.0
    assert t_surface == pytest.approx(16.0, abs=0.1)

    # Custom f_Rsi is reflected in surface_temp as well
    _, _, t_surface_better = calculate_mold_risk(20.0, 60.0, 0.0, f_rsi=1.0)
    assert t_surface_better == pytest.approx(20.0, abs=0.1)

    # No outdoor → surface_temp is None
    _, _, t_surface_none = calculate_mold_risk(20.0, 60.0, None)
    assert t_surface_none is None


def test_calculate_mold_risk_cold_surface_still_reports_the_risk():
    """A wall below 5 °C is where condensate forms first: no "ok" with surface RH 0."""
    # Room 10°C, outside -20°C, f_Rsi=0.80 → surface = -20 + 0.80*30 = 4°C, dew point ~8.5°C
    level, srh, t_surface = calculate_mold_risk(10.0, 90.0, -20.0)
    assert level == "critical"
    assert srh == 100.0
    assert t_surface == pytest.approx(4.0, abs=0.1)


def test_calculate_mold_risk_cold_dry_surface_is_ok():
    # Same cold wall, dry air (dew point ~-10°C): no risk, and the real surface RH is reported
    level, srh, t_surface = calculate_mold_risk(10.0, 25.0, -20.0)
    assert level == "ok"
    assert 0.0 < srh < 70.0
    assert t_surface == pytest.approx(4.0, abs=0.1)


# --- mold_prevention_delta ---


def test_mold_prevention_delta_light():
    assert mold_prevention_delta("light") == 1.0


def test_mold_prevention_delta_medium():
    assert mold_prevention_delta("medium") == 2.0


def test_mold_prevention_delta_strong():
    assert mold_prevention_delta("strong") == 3.0


def test_mold_prevention_delta_unknown_falls_back():
    """Unknown intensity → defaults to medium (2.0)."""
    assert mold_prevention_delta("unknown") == 2.0


# --- boundary value tests ---


@pytest.mark.parametrize(
    "rh_room, t_outdoor, expected_level",
    [
        # Just below warning threshold (surface RH < 70%) → ok
        (50.0, 10.0, "ok"),
        # Just at/above critical (surface RH >= 80%) → critical
        (75.0, -5.0, "critical"),
    ],
)
def test_calculate_mold_risk_boundary_levels(rh_room, t_outdoor, expected_level):
    """Verify risk level at critical boundary values."""
    level, _srh, _st = calculate_mold_risk(20.0, rh_room, t_outdoor)
    assert level == expected_level


def test_calculate_mold_risk_fallback_at_threshold():
    """Fallback mode: room RH 60% + 10% offset = 70% → exactly at warning."""
    level, srh, _t = calculate_mold_risk(20.0, 60.0, None)
    assert srh == pytest.approx(70.0, abs=0.1)
    assert level == "warning"


def test_calculate_mold_risk_fallback_below_warning():
    """Fallback mode: room RH 59% + 10% = 69% → ok."""
    level, srh, _t = calculate_mold_risk(20.0, 59.0, None)
    assert srh == pytest.approx(69.0, abs=0.1)
    assert level == "ok"


def test_surface_rh_thresholds_exact():
    """Verify the risk function returns correct levels at exact thresholds."""
    from custom_components.roommind.utils.mold_utils import _risk_from_surface_rh

    assert _risk_from_surface_rh(69.9) == "ok"
    assert _risk_from_surface_rh(70.0) == "warning"
    assert _risk_from_surface_rh(79.9) == "warning"
    assert _risk_from_surface_rh(80.0) == "critical"
