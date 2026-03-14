"""Tests for the MPC controller."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.roommind.const import TargetTemps
from custom_components.roommind.control.mpc_controller import (
    MODE_COOLING,
    MODE_HEATING,
    MODE_IDLE,
    MPCController,
    _last_commands,
    async_idle_device,
    async_turn_off_climate,
    check_acs_can_heat,
    resolve_hvac_mode,
)
from custom_components.roommind.control.mpc_optimizer import MPCPlan
from custom_components.roommind.control.thermal_model import RCModel, RoomModelManager


def build_hass():
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.states.get = MagicMock(return_value=None)
    return hass


def make_room(**overrides):
    room = {
        "area_id": "living_room",
        "thermostats": ["climate.living_trv"],
        "acs": [],
        "climate_mode": "auto",
        "temperature_sensor": "sensor.living_temp",
        "schedules": [],
    }
    room.update(overrides)
    # Build devices from thermostats/acs for consistency
    hst = room.get("heating_system_type", "")
    room["devices"] = [
        {"entity_id": eid, "type": "trv", "role": "auto", "heating_system_type": hst}
        for eid in room.get("thermostats", [])
    ] + [{"entity_id": eid, "type": "ac", "role": "auto", "heating_system_type": ""} for eid in room.get("acs", [])]
    return room


@pytest.mark.asyncio
async def test_mpc_evaluate_heats_when_cold():
    """Cold room triggers heating."""
    hass = build_hass()
    room = make_room()
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    mode, pf = await ctrl.async_evaluate(current_temp=17.0, target_temp=21.0)
    assert mode == "heating"
    assert 0.0 < pf <= 1.0


@pytest.mark.asyncio
async def test_mpc_evaluate_idle_at_target():
    """At target, returns idle."""
    hass = build_hass()
    room = make_room()
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    mode, pf = await ctrl.async_evaluate(current_temp=21.0, target_temp=21.0)
    assert mode == "idle"
    assert pf == 0.0


@pytest.mark.asyncio
async def test_mpc_fallback_to_bangbang():
    """Low confidence = bang-bang: 0.1°C below target, within 0.2°C hysteresis → idle."""
    hass = build_hass()
    room = make_room()
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    mode, pf = await ctrl.async_evaluate(current_temp=20.9, target_temp=21.0)
    assert mode == "idle"
    assert pf == 0.0


@pytest.mark.asyncio
async def test_mpc_apply_heating():
    """Apply heating calls climate services."""
    hass = build_hass()
    room = make_room()
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0)
    assert hass.services.async_call.called


@pytest.mark.asyncio
async def test_mpc_managed_mode():
    """Managed mode: device self-regulates, returns heating when thermostats present."""
    hass = build_hass()
    room = make_room(temperature_sensor="")
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )
    mode, pf = await ctrl.async_evaluate(current_temp=None, target_temp=21.0)
    assert mode == "heating"
    assert pf == 1.0  # managed mode: device self-regulates


@pytest.mark.asyncio
async def test_mpc_outdoor_gating():
    """Cooling blocked when outdoor below threshold."""
    hass = build_hass()
    room = make_room(thermostats=[], acs=["climate.ac"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=10.0,
        settings={"outdoor_cooling_min": 16.0},
        has_external_sensor=True,
    )
    mode, pf = await ctrl.async_evaluate(current_temp=25.0, target_temp=22.0)
    assert mode == "idle"
    assert pf == 0.0


@pytest.mark.asyncio
async def test_mpc_apply_cooling():
    """Apply cooling calls climate services on ACs."""
    hass = build_hass()
    room = make_room(thermostats=[], acs=["climate.ac"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("cooling", 23.0)
    assert hass.services.async_call.called


@pytest.mark.asyncio
async def test_mpc_apply_idle():
    """Apply idle turns off everything."""
    hass = build_hass()
    room = make_room(acs=["climate.ac"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("idle", 21.0)
    assert hass.services.async_call.called


@pytest.mark.asyncio
async def test_mpc_path_when_confident():
    """When model confidence is high, MPC optimizer is used instead of bang-bang."""
    hass = build_hass()
    room = make_room()
    model_mgr = RoomModelManager()
    # Pre-train to get a valid model
    model_mgr.update("living_room", 18.5, 5.0, "heating", 5.0)
    model_mgr.update("living_room", 19.0, 5.0, "heating", 5.0)
    # Mock prediction_std to be low (confident) + enough training data
    model_mgr.get_prediction_std = MagicMock(return_value=0.1)
    model_mgr.get_mode_counts = MagicMock(return_value=(100, 30, 0))
    # Mock a realistic trained model (2 EKF updates give alpha=_ALPHA_MIN which is
    # too low for the optimizer to distinguish heating from idle via T_eq clamping)
    model_mgr.get_model = MagicMock(return_value=RCModel(C=1.0, U=0.15, Q_heat=3.0, Q_cool=4.0))
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    mode, pf = await ctrl.async_evaluate(current_temp=17.0, target_temp=21.0)
    assert mode == "heating"
    assert 0.0 < pf <= 1.0
    model_mgr.get_prediction_std.assert_called_once()


@pytest.mark.asyncio
async def test_confidence_transition_threshold():
    """pred_std >= 0.5 -> bang-bang, pred_std < 0.5 -> MPC."""
    hass = build_hass()
    room = make_room()
    model_mgr = RoomModelManager()
    model_mgr.update("living_room", 18.5, 5.0, "heating", 5.0)
    model_mgr.update("living_room", 19.0, 5.0, "heating", 5.0)

    # Enough training data for MPC
    model_mgr.get_mode_counts = MagicMock(return_value=(100, 30, 0))
    # Mock a realistic trained model (2 EKF updates give alpha=_ALPHA_MIN which is
    # too low for the optimizer to distinguish heating from idle via T_eq clamping)
    model_mgr.get_model = MagicMock(return_value=RCModel(C=1.0, U=0.15, Q_heat=3.0, Q_cool=4.0))

    # Just above threshold — bang-bang
    model_mgr.get_prediction_std = MagicMock(return_value=0.5)
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    mode, pf = await ctrl.async_evaluate(current_temp=17.0, target_temp=21.0)
    assert mode == "heating"  # bang-bang also heats when cold
    assert pf == 1.0  # bang-bang: full power

    # Just below threshold — MPC path
    model_mgr.get_prediction_std = MagicMock(return_value=0.49)
    ctrl2 = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    mode2, pf2 = await ctrl2.async_evaluate(current_temp=17.0, target_temp=21.0)
    assert mode2 == "heating"  # MPC also heats when cold
    assert 0.0 < pf2 <= 1.0


@pytest.mark.asyncio
async def test_mpc_requires_min_updates():
    """MPC falls back to bang-bang when not enough training data per mode."""
    hass = build_hass()
    room = make_room()
    model_mgr = RoomModelManager()

    # Low pred_std (model thinks it's confident) but not enough samples
    model_mgr.get_prediction_std = MagicMock(return_value=0.1)

    # Too few idle samples → bang-bang
    model_mgr.get_mode_counts = MagicMock(return_value=(30, 25, 0))
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    mode, pf = await ctrl.async_evaluate(current_temp=20.9, target_temp=21.0)
    assert mode == "idle"  # bang-bang: within hysteresis
    assert pf == 0.0

    # Enough idle but too few heating samples → bang-bang
    model_mgr.get_mode_counts = MagicMock(return_value=(100, 10, 0))
    ctrl2 = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    mode2, pf2 = await ctrl2.async_evaluate(current_temp=20.9, target_temp=21.0)
    assert mode2 == "idle"  # still bang-bang
    assert pf2 == 0.0

    # Enough data → MPC (would heat at 20.9 because optimizer predicts drop)
    model_mgr.get_mode_counts = MagicMock(return_value=(100, 30, 0))
    ctrl3 = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    mode3, pf3 = await ctrl3.async_evaluate(current_temp=20.9, target_temp=21.0)
    assert mode3 == "heating"  # MPC: optimizer decides to heat proactively
    assert 0.0 < pf3 <= 1.0


# ---------------------------------------------------------------------------
# T4: _compute_horizon_blocks unit tests
# ---------------------------------------------------------------------------


class TestComputeHorizonBlocks:
    """Unit tests for MPCController._compute_horizon_blocks."""

    def _make_ctrl(self, **room_overrides):
        hass = build_hass()
        room = make_room(**room_overrides)
        model_mgr = RoomModelManager()
        return MPCController(
            hass,
            room,
            model_manager=model_mgr,
            outdoor_temp=5.0,
            settings={},
            has_external_sensor=True,
        )

    def test_small_delta_returns_minimum_horizon(self):
        """Small temp delta should still produce at least MIN_HORIZON_HOURS worth of blocks."""
        from custom_components.roommind.control.mpc_controller import MIN_HORIZON_HOURS, PLAN_DT_MINUTES

        ctrl = self._make_ctrl()
        model = ctrl._model_manager.get_model("living_room")
        blocks = ctrl._compute_horizon_blocks(model, 20.5, 21.0)
        min_blocks = int(MIN_HORIZON_HOURS * 60 / PLAN_DT_MINUTES)
        assert blocks >= min_blocks

    def test_large_delta_increases_horizon(self):
        """Larger delta between current and target should increase horizon blocks."""
        ctrl = self._make_ctrl()
        model = ctrl._model_manager.get_model("living_room")
        blocks_small = ctrl._compute_horizon_blocks(model, 20.0, 21.0)
        blocks_large = ctrl._compute_horizon_blocks(model, 10.0, 21.0)
        assert blocks_large >= blocks_small

    def test_returns_at_least_24_blocks(self):
        """Result should always be at least 24 blocks."""
        ctrl = self._make_ctrl()
        model = ctrl._model_manager.get_model("living_room")
        blocks = ctrl._compute_horizon_blocks(model, 21.0, 21.0)
        assert blocks >= 24

    def test_zero_Q_max_returns_default(self):
        """When Q_heat and Q_cool are both 0, fall back to default horizon."""
        from custom_components.roommind.control.mpc_controller import MIN_HORIZON_HOURS, PLAN_DT_MINUTES
        from custom_components.roommind.control.thermal_model import RCModel

        ctrl = self._make_ctrl()
        model = RCModel(C=2.0, U=50.0, Q_heat=0.0, Q_cool=0.0)
        blocks = ctrl._compute_horizon_blocks(model, 15.0, 21.0)
        assert blocks == int(MIN_HORIZON_HOURS * 60 / PLAN_DT_MINUTES)

    def test_high_power_model_shorter_horizon(self):
        """High HVAC power should yield fewer blocks (faster to reach target)."""
        from custom_components.roommind.control.thermal_model import RCModel

        ctrl = self._make_ctrl()
        model_low = RCModel(C=2.0, U=50.0, Q_heat=400.0, Q_cool=400.0)
        model_high = RCModel(C=2.0, U=50.0, Q_heat=4000.0, Q_cool=4000.0)
        blocks_low = ctrl._compute_horizon_blocks(model_low, 15.0, 21.0)
        blocks_high = ctrl._compute_horizon_blocks(model_high, 15.0, 21.0)
        assert blocks_high <= blocks_low

    def test_high_thermal_mass_longer_horizon(self):
        """High thermal capacitance should yield more blocks (slower temperature change)."""
        from custom_components.roommind.control.thermal_model import RCModel

        ctrl = self._make_ctrl()
        model_small_c = RCModel(C=1.0, U=50.0, Q_heat=800.0, Q_cool=800.0)
        model_large_c = RCModel(C=10.0, U=50.0, Q_heat=800.0, Q_cool=800.0)
        blocks_small = ctrl._compute_horizon_blocks(model_small_c, 15.0, 21.0)
        blocks_large = ctrl._compute_horizon_blocks(model_large_c, 15.0, 21.0)
        assert blocks_large >= blocks_small


# ---------------------------------------------------------------------------
# T4: _build_outdoor_series unit tests
# ---------------------------------------------------------------------------


class TestBuildOutdoorSeries:
    """Unit tests for MPCController._build_outdoor_series."""

    def test_constant_outdoor_no_forecast(self):
        """Without forecast, returns constant outdoor temp repeated n_blocks times."""
        hass = build_hass()
        room = make_room()
        model_mgr = RoomModelManager()
        ctrl = MPCController(
            hass,
            room,
            model_manager=model_mgr,
            outdoor_temp=8.0,
            settings={},
            has_external_sensor=True,
        )
        series = ctrl._build_outdoor_series(10)
        assert series == [8.0] * 10

    def test_fallback_when_outdoor_temp_none_no_forecast(self):
        """Without forecast and outdoor_temp=None, uses DEFAULT_OUTDOOR_TEMP_FALLBACK."""
        from custom_components.roommind.control.mpc_controller import DEFAULT_OUTDOOR_TEMP_FALLBACK

        hass = build_hass()
        room = make_room()
        model_mgr = RoomModelManager()
        ctrl = MPCController(
            hass,
            room,
            model_manager=model_mgr,
            outdoor_temp=None,
            settings={},
            has_external_sensor=True,
        )
        series = ctrl._build_outdoor_series(5)
        assert series == [DEFAULT_OUTDOOR_TEMP_FALLBACK] * 5

    def test_forecast_used_when_available(self):
        """With forecast data, series uses forecast temperatures."""
        hass = build_hass()
        room = make_room()
        model_mgr = RoomModelManager()
        forecast = [
            {"temperature": 5.0},
            {"temperature": 6.0},
            {"temperature": 7.0},
        ]
        ctrl = MPCController(
            hass,
            room,
            model_manager=model_mgr,
            outdoor_temp=8.0,
            outdoor_forecast=forecast,
            settings={},
            has_external_sensor=True,
        )
        series = ctrl._build_outdoor_series(3)
        assert series == [5.0, 6.0, 7.0]

    def test_forecast_padded_when_shorter_than_n_blocks(self):
        """Forecast shorter than n_blocks should be padded with last forecast value."""
        hass = build_hass()
        room = make_room()
        model_mgr = RoomModelManager()
        forecast = [
            {"temperature": 5.0},
            {"temperature": 6.0},
        ]
        ctrl = MPCController(
            hass,
            room,
            model_manager=model_mgr,
            outdoor_temp=8.0,
            outdoor_forecast=forecast,
            settings={},
            has_external_sensor=True,
        )
        series = ctrl._build_outdoor_series(5)
        assert series == [5.0, 6.0, 6.0, 6.0, 6.0]

    def test_forecast_truncated_when_longer_than_n_blocks(self):
        """Forecast longer than n_blocks should be truncated."""
        hass = build_hass()
        room = make_room()
        model_mgr = RoomModelManager()
        forecast = [
            {"temperature": 5.0},
            {"temperature": 6.0},
            {"temperature": 7.0},
            {"temperature": 8.0},
            {"temperature": 9.0},
        ]
        ctrl = MPCController(
            hass,
            room,
            model_manager=model_mgr,
            outdoor_temp=10.0,
            outdoor_forecast=forecast,
            settings={},
            has_external_sensor=True,
        )
        series = ctrl._build_outdoor_series(3)
        assert series == [5.0, 6.0, 7.0]

    def test_forecast_missing_temperature_key_uses_outdoor_temp(self):
        """Forecast entries without 'temperature' key fall back to current outdoor_temp."""
        hass = build_hass()
        room = make_room()
        model_mgr = RoomModelManager()
        forecast = [
            {"temperature": 5.0},
            {"condition": "cloudy"},  # no temperature key
            {"temperature": 7.0},
        ]
        ctrl = MPCController(
            hass,
            room,
            model_manager=model_mgr,
            outdoor_temp=8.0,
            outdoor_forecast=forecast,
            settings={},
            has_external_sensor=True,
        )
        series = ctrl._build_outdoor_series(3)
        assert series == [5.0, 8.0, 7.0]

    def test_forecast_missing_temp_key_and_outdoor_none_uses_fallback(self):
        """Forecast entry without temp + outdoor_temp=None uses DEFAULT_OUTDOOR_TEMP_FALLBACK."""
        from custom_components.roommind.control.mpc_controller import DEFAULT_OUTDOOR_TEMP_FALLBACK

        hass = build_hass()
        room = make_room()
        model_mgr = RoomModelManager()
        forecast = [
            {"condition": "cloudy"},  # no temperature key
        ]
        ctrl = MPCController(
            hass,
            room,
            model_manager=model_mgr,
            outdoor_temp=None,
            outdoor_forecast=forecast,
            settings={},
            has_external_sensor=True,
        )
        series = ctrl._build_outdoor_series(3)
        assert series[0] == DEFAULT_OUTDOOR_TEMP_FALLBACK
        # Padding should also use the fallback
        assert all(v == DEFAULT_OUTDOOR_TEMP_FALLBACK for v in series)


# ---------------------------------------------------------------------------
# Proportional control tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_proportional_power_far_from_target():
    """MPC mode, large error → power_fraction near 1.0."""
    hass = build_hass()
    room = make_room()
    model_mgr = RoomModelManager()
    model_mgr.update("living_room", 15.0, 5.0, "heating", 5.0)
    model_mgr.update("living_room", 16.0, 5.0, "heating", 5.0)
    model_mgr.get_prediction_std = MagicMock(return_value=0.1)
    model_mgr.get_mode_counts = MagicMock(return_value=(100, 30, 0))
    # Mock a realistic trained model (2 EKF updates give alpha=_ALPHA_MIN which is
    # too low for the optimizer to distinguish heating from idle via T_eq clamping)
    model_mgr.get_model = MagicMock(return_value=RCModel(C=1.0, U=0.15, Q_heat=3.0, Q_cool=4.0))
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    mode, pf = await ctrl.async_evaluate(current_temp=15.0, target_temp=21.0)
    assert mode == "heating"
    assert pf >= 0.7  # large error → high power


@pytest.mark.asyncio
async def test_proportional_power_near_target():
    """MPC mode, small error → reduced power_fraction."""
    hass = build_hass()
    room = make_room()
    model_mgr = RoomModelManager()
    # Use a known model with high Q_heat so a small 0.3°C error yields frac < 1.
    # This tests MPC proportional behavior, not EKF learning.
    model_mgr.get_model = MagicMock(return_value=RCModel(C=1.0, U=0.15, Q_heat=50.0, Q_cool=75.0))
    model_mgr.get_prediction_std = MagicMock(return_value=0.1)
    model_mgr.get_mode_counts = MagicMock(return_value=(100, 40, 0))
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    mode, pf = await ctrl.async_evaluate(current_temp=20.7, target_temp=21.0)
    if mode == "heating":
        assert pf < 1.0  # near target → less than full power


@pytest.mark.asyncio
async def test_proportional_trv_setpoint():
    """TRV setpoint is proportional between current_temp and 30°C."""
    hass = build_hass()
    room = make_room()
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    # 50% power at 20°C → TRV = 20 + 0.5*(30-20) = 25°C
    await ctrl.async_apply("heating", 21.0, power_fraction=0.5, current_temp=20.0)
    calls = hass.services.async_call.call_args_list
    set_temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert set_temp_calls
    temp_arg = set_temp_calls[0][0][2]["temperature"]
    assert temp_arg == 25.0


@pytest.mark.asyncio
async def test_bangbang_returns_full_power():
    """Bang-bang fallback → power_fraction = 1.0 for heating."""
    hass = build_hass()
    room = make_room()
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    # Large error in bang-bang mode (low confidence)
    mode, pf = await ctrl.async_evaluate(current_temp=17.0, target_temp=21.0)
    assert mode == "heating"
    assert pf == 1.0  # bang-bang: always full power


@pytest.mark.asyncio
async def test_async_apply_backward_compat():
    """Calling async_apply without power_fraction uses default 1.0 → 30°C boost."""
    from custom_components.roommind.control.mpc_controller import HEATING_BOOST_TARGET

    hass = build_hass()
    room = make_room()
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0)  # no power_fraction → default 1.0
    calls = hass.services.async_call.call_args_list
    set_temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert set_temp_calls
    # Without current_temp, falls back to HEATING_BOOST_TARGET
    temp_arg = set_temp_calls[0][0][2]["temperature"]
    assert temp_arg == HEATING_BOOST_TARGET


@pytest.mark.asyncio
async def test_mpc_apply_heating_fahrenheit():
    """set_temperature uses Fahrenheit when HA is configured for °F."""
    from homeassistant.const import UnitOfTemperature

    from custom_components.roommind.control.mpc_controller import HEATING_BOOST_TARGET

    hass = build_hass()
    hass.config.units.temperature_unit = UnitOfTemperature.FAHRENHEIT

    room = make_room()
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0)

    calls = hass.services.async_call.call_args_list
    set_temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert set_temp_calls

    # HEATING_BOOST_TARGET (30°C) → 86°F
    expected_f = HEATING_BOOST_TARGET * 9 / 5 + 32
    temp_arg = set_temp_calls[0][0][2]["temperature"]
    assert temp_arg == pytest.approx(expected_f)


@pytest.mark.asyncio
async def test_mpc_apply_cooling_fahrenheit():
    """Cooling set_temperature uses Fahrenheit when HA is configured for °F."""
    from homeassistant.const import UnitOfTemperature

    hass = build_hass()
    hass.config.units.temperature_unit = UnitOfTemperature.FAHRENHEIT

    room = make_room(thermostats=[], acs=["climate.ac"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    # Apply cooling with target 23°C
    await ctrl.async_apply("cooling", 23.0)

    calls = hass.services.async_call.call_args_list
    set_temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert set_temp_calls

    # 23°C → 73.4°F
    expected_f = 23.0 * 9 / 5 + 32
    temp_arg = set_temp_calls[0][0][2]["temperature"]
    assert temp_arg == pytest.approx(expected_f)


# ---------------------------------------------------------------------------
# get_can_heat_cool unit tests
# ---------------------------------------------------------------------------


class TestGetCanHeatCool:
    """Unit tests for get_can_heat_cool."""

    def test_auto_mode_with_both_devices(self):
        """auto mode with thermostats and ACs → (True, True)."""
        from custom_components.roommind.control.mpc_controller import get_can_heat_cool

        room = make_room(climate_mode="auto", acs=["climate.ac"])
        can_heat, can_cool = get_can_heat_cool(room)
        assert can_heat is True
        assert can_cool is True

    def test_heat_only_mode(self):
        """heat_only mode → (True, False) regardless of ACs."""
        from custom_components.roommind.control.mpc_controller import get_can_heat_cool

        room = make_room(climate_mode="heat_only", acs=["climate.ac"])
        can_heat, can_cool = get_can_heat_cool(room)
        assert can_heat is True
        assert can_cool is False

    def test_cool_only_mode(self):
        """cool_only mode → (False, True) regardless of thermostats."""
        from custom_components.roommind.control.mpc_controller import get_can_heat_cool

        room = make_room(climate_mode="cool_only", acs=["climate.ac"])
        can_heat, can_cool = get_can_heat_cool(room)
        assert can_heat is False
        assert can_cool is True

    def test_no_thermostats_heat_only(self):
        """heat_only but no thermostats → (False, False)."""
        from custom_components.roommind.control.mpc_controller import get_can_heat_cool

        room = make_room(climate_mode="heat_only", thermostats=[], acs=[])
        can_heat, can_cool = get_can_heat_cool(room)
        assert can_heat is False
        assert can_cool is False

    def test_no_acs_cool_only(self):
        """cool_only but no ACs → (False, False)."""
        from custom_components.roommind.control.mpc_controller import get_can_heat_cool

        room = make_room(climate_mode="cool_only", thermostats=[], acs=[])
        can_heat, can_cool = get_can_heat_cool(room)
        assert can_heat is False
        assert can_cool is False

    def test_outdoor_temp_none_no_gating(self):
        """outdoor_temp=None → no gating applied."""
        from custom_components.roommind.control.mpc_controller import get_can_heat_cool

        room = make_room(acs=["climate.ac"])
        can_heat, can_cool = get_can_heat_cool(room, outdoor_temp=None)
        assert can_heat is True
        assert can_cool is True

    def test_outdoor_above_heating_max_blocks_heat(self):
        """Outdoor temp above outdoor_heating_max → can_heat=False."""
        from custom_components.roommind.control.mpc_controller import get_can_heat_cool

        room = make_room(acs=["climate.ac"])
        can_heat, can_cool = get_can_heat_cool(
            room,
            outdoor_temp=25.0,
            outdoor_heating_max=22.0,
        )
        assert can_heat is False
        assert can_cool is True

    def test_outdoor_below_cooling_min_blocks_cool(self):
        """Outdoor temp below outdoor_cooling_min → can_cool=False."""
        from custom_components.roommind.control.mpc_controller import get_can_heat_cool

        room = make_room(acs=["climate.ac"])
        can_heat, can_cool = get_can_heat_cool(
            room,
            outdoor_temp=10.0,
            outdoor_cooling_min=16.0,
        )
        assert can_heat is True
        assert can_cool is False

    def test_outdoor_at_threshold_boundary(self):
        """Outdoor temp equal to heating_max → not blocked (>= not used, > is)."""
        from custom_components.roommind.control.mpc_controller import get_can_heat_cool

        room = make_room(acs=["climate.ac"])
        # At exactly outdoor_heating_max=22.0 → 22 > 22 is False, so still allowed
        can_heat, can_cool = get_can_heat_cool(
            room,
            outdoor_temp=22.0,
            outdoor_heating_max=22.0,
        )
        assert can_heat is True
        # At exactly outdoor_cooling_min=16.0 → 16 < 16 is False, so still allowed
        can_heat2, can_cool2 = get_can_heat_cool(
            room,
            outdoor_temp=16.0,
            outdoor_cooling_min=16.0,
        )
        assert can_cool2 is True

    def test_auto_no_devices_returns_false_false(self):
        """auto mode but no devices → (False, False)."""
        from custom_components.roommind.control.mpc_controller import get_can_heat_cool

        room = make_room(climate_mode="auto", thermostats=[], acs=[])
        can_heat, can_cool = get_can_heat_cool(room)
        assert can_heat is False
        assert can_cool is False


# ---------------------------------------------------------------------------
# is_mpc_active unit tests
# ---------------------------------------------------------------------------


class TestIsMpcActive:
    """Unit tests for is_mpc_active."""

    def test_area_not_in_estimators(self):
        """Returns False when area_id has no estimator."""
        from custom_components.roommind.control.mpc_controller import is_mpc_active

        model_mgr = RoomModelManager()
        result = is_mpc_active(model_mgr, "unknown_room", True, False, 20.0, 10.0)
        assert result is False

    def test_prediction_std_too_high(self):
        """Returns False when prediction_std >= MPC_MAX_PREDICTION_STD."""
        from custom_components.roommind.control.mpc_controller import is_mpc_active

        model_mgr = RoomModelManager()
        model_mgr.update("living_room", 20.0, 10.0, "idle", 5.0)
        model_mgr.get_prediction_std = MagicMock(return_value=0.6)
        model_mgr.get_mode_counts = MagicMock(return_value=(100, 30, 30))
        result = is_mpc_active(model_mgr, "living_room", True, False, 20.0, 10.0)
        assert result is False

    def test_insufficient_idle_samples(self):
        """Returns False when idle samples below MIN_IDLE_UPDATES."""
        from custom_components.roommind.control.mpc_controller import is_mpc_active

        model_mgr = RoomModelManager()
        model_mgr.update("living_room", 20.0, 10.0, "idle", 5.0)
        model_mgr.get_prediction_std = MagicMock(return_value=0.1)
        model_mgr.get_mode_counts = MagicMock(return_value=(30, 30, 30))  # idle < 60
        result = is_mpc_active(model_mgr, "living_room", True, False, 20.0, 10.0)
        assert result is False

    def test_insufficient_heating_samples(self):
        """Returns False when can_heat but heating samples below MIN_ACTIVE_UPDATES."""
        from custom_components.roommind.control.mpc_controller import is_mpc_active

        model_mgr = RoomModelManager()
        model_mgr.update("living_room", 20.0, 10.0, "idle", 5.0)
        model_mgr.get_prediction_std = MagicMock(return_value=0.1)
        model_mgr.get_mode_counts = MagicMock(return_value=(100, 10, 0))  # heating < 20
        result = is_mpc_active(model_mgr, "living_room", True, False, 20.0, 10.0)
        assert result is False

    def test_insufficient_cooling_samples(self):
        """Returns False when can_cool but cooling samples below MIN_ACTIVE_UPDATES."""
        from custom_components.roommind.control.mpc_controller import is_mpc_active

        model_mgr = RoomModelManager()
        model_mgr.update("living_room", 20.0, 10.0, "idle", 5.0)
        model_mgr.get_prediction_std = MagicMock(return_value=0.1)
        model_mgr.get_mode_counts = MagicMock(return_value=(100, 0, 10))  # cooling < 20
        result = is_mpc_active(model_mgr, "living_room", False, True, 20.0, 10.0)
        assert result is False

    def test_all_conditions_met_returns_true(self):
        """Returns True when all conditions satisfied."""
        from custom_components.roommind.control.mpc_controller import is_mpc_active

        model_mgr = RoomModelManager()
        model_mgr.update("living_room", 20.0, 10.0, "idle", 5.0)
        model_mgr.get_prediction_std = MagicMock(return_value=0.1)
        model_mgr.get_mode_counts = MagicMock(return_value=(100, 30, 0))
        result = is_mpc_active(model_mgr, "living_room", True, False, 20.0, 10.0)
        assert result is True

    def test_heat_and_cool_both_need_samples(self):
        """When both can_heat and can_cool, both need MIN_ACTIVE_UPDATES."""
        from custom_components.roommind.control.mpc_controller import is_mpc_active

        model_mgr = RoomModelManager()
        model_mgr.update("living_room", 20.0, 10.0, "idle", 5.0)
        model_mgr.get_prediction_std = MagicMock(return_value=0.1)
        # Enough heating but not enough cooling
        model_mgr.get_mode_counts = MagicMock(return_value=(100, 30, 10))
        result = is_mpc_active(model_mgr, "living_room", True, True, 20.0, 10.0)
        assert result is False

    def test_no_heat_no_cool_only_idle_needed(self):
        """When neither can_heat nor can_cool, only idle check matters."""
        from custom_components.roommind.control.mpc_controller import is_mpc_active

        model_mgr = RoomModelManager()
        model_mgr.update("living_room", 20.0, 10.0, "idle", 5.0)
        model_mgr.get_prediction_std = MagicMock(return_value=0.1)
        model_mgr.get_mode_counts = MagicMock(return_value=(100, 0, 0))
        result = is_mpc_active(model_mgr, "living_room", False, False, 20.0, 10.0)
        assert result is True

    def test_prediction_std_at_threshold(self):
        """pred_std exactly at MPC_MAX_PREDICTION_STD (0.5) → False."""
        from custom_components.roommind.control.mpc_controller import MPC_MAX_PREDICTION_STD, is_mpc_active

        model_mgr = RoomModelManager()
        model_mgr.update("living_room", 20.0, 10.0, "idle", 5.0)
        model_mgr.get_prediction_std = MagicMock(return_value=MPC_MAX_PREDICTION_STD)
        model_mgr.get_mode_counts = MagicMock(return_value=(100, 30, 0))
        result = is_mpc_active(model_mgr, "living_room", True, False, 20.0, 10.0)
        assert result is False


# ---------------------------------------------------------------------------
# Device min/max temperature clamping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_clamps_to_device_max_temp():
    """Temperature is clamped to device max_temp attribute."""
    hass = build_hass()
    mock_state = MagicMock()
    mock_state.state = "off"
    mock_state.attributes = {"min_temp": 5.0, "max_temp": 25.0, "temperature": None}
    hass.states.get = MagicMock(return_value=mock_state)

    room = make_room()
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    # Heating with full power tries to set 30°C (HEATING_BOOST_TARGET)
    await ctrl.async_apply("heating", 21.0, power_fraction=1.0, current_temp=18.0)

    set_temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert set_temp_calls
    temp_arg = set_temp_calls[0][0][2]["temperature"]
    assert temp_arg == 25.0  # clamped to device max


@pytest.mark.asyncio
async def test_apply_clamps_to_device_min_temp():
    """Temperature is clamped to device min_temp attribute."""
    hass = build_hass()
    mock_state = MagicMock()
    mock_state.state = "off"
    mock_state.attributes = {"min_temp": 10.0, "max_temp": 30.0, "temperature": None}
    hass.states.get = MagicMock(return_value=mock_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=35.0,
        settings={},
        has_external_sensor=True,
    )
    # Cooling with target below device min
    await ctrl.async_apply("cooling", 8.0)

    set_temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert set_temp_calls
    temp_arg = set_temp_calls[0][0][2]["temperature"]
    assert temp_arg == 10.0  # clamped to device min


# ---------------------------------------------------------------------------
# async_turn_off_climate — unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_off_climate_normal_device():
    """Device with 'off' in hvac_modes uses standard set_hvac_mode off."""
    from custom_components.roommind.control.mpc_controller import async_turn_off_climate

    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.trv", "hvac_mode": "off"},
        blocking=True,
    )


@pytest.mark.asyncio
async def test_turn_off_climate_heat_only_uses_min_temp():
    """Heat-only device (no 'off' mode) gets set_temperature with min_temp."""
    from custom_components.roommind.control.mpc_controller import async_turn_off_climate

    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat"], "min_temp": 5.0, "temperature": 21.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_temperature",
        {"entity_id": "climate.trv", "temperature": 5.0},
        blocking=True,
    )


@pytest.mark.asyncio
async def test_turn_off_climate_cool_only_uses_max_temp():
    """Cool-only device without 'off' uses max_temp as fallback."""
    from custom_components.roommind.control.mpc_controller import async_turn_off_climate

    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {"hvac_modes": ["cool"], "min_temp": 16.0, "max_temp": 30.0, "temperature": 20.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.ac")
    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_temperature",
        {"entity_id": "climate.ac", "temperature": 30.0},
        blocking=True,
    )


@pytest.mark.asyncio
async def test_turn_off_climate_already_off_skipped():
    """Device already in 'off' state: call is skipped."""
    from custom_components.roommind.control.mpc_controller import async_turn_off_climate

    hass = build_hass()
    state = MagicMock()
    state.state = "off"
    state.attributes = {"hvac_modes": ["heat", "off"]}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_turn_off_climate_empty_modes_uses_off():
    """Empty hvac_modes list: assume 'off' is supported (backward compat)."""
    from custom_components.roommind.control.mpc_controller import async_turn_off_climate

    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": []}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.trv", "hvac_mode": "off"},
        blocking=True,
    )


@pytest.mark.asyncio
async def test_turn_off_climate_no_modes_attr_uses_off():
    """No hvac_modes attribute at all: assume 'off' is supported (backward compat)."""
    from custom_components.roommind.control.mpc_controller import async_turn_off_climate

    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"min_temp": 5.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.trv", "hvac_mode": "off"},
        blocking=True,
    )


@pytest.mark.asyncio
async def test_turn_off_climate_heat_only_no_min_temp():
    """Heat-only device without min_temp: logs warning, no crash."""
    from custom_components.roommind.control.mpc_controller import async_turn_off_climate

    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat"]}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_turn_off_climate_heat_only_already_at_min_temp():
    """Heat-only device already at min_temp: redundant call skipped."""
    from custom_components.roommind.control.mpc_controller import async_turn_off_climate

    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat"], "min_temp": 5.0, "temperature": 5.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    hass.services.async_call.assert_not_called()


# ---------------------------------------------------------------------------
# async_apply integration tests for heat-only TRV fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_idle_heat_only_trv():
    """Idle mode on heat-only TRV sends min_temp instead of set_hvac_mode off."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat"], "min_temp": 5.0, "max_temp": 30.0, "temperature": 21.0}
    hass.states.get = MagicMock(return_value=state)

    room = make_room()
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("idle", 21.0)

    calls = hass.services.async_call.call_args_list
    off_calls = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2].get("hvac_mode") == "off"]
    assert len(off_calls) == 0
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert len(temp_calls) >= 1
    assert temp_calls[0][0][2]["temperature"] == 5.0


@pytest.mark.asyncio
async def test_managed_mode_heat_gated_heat_only_trv():
    """Managed mode: can_heat=False on heat-only TRV uses min_temp fallback."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat"], "min_temp": 5.0, "max_temp": 30.0, "temperature": 21.0}
    hass.states.get = MagicMock(return_value=state)

    room = make_room(acs=["climate.ac"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=25.0,  # above heating max → can_heat=False
        settings={"outdoor_heating_max": 22.0},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", 21.0)

    calls = hass.services.async_call.call_args_list
    off_calls = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2].get("hvac_mode") == "off"]
    assert len(off_calls) == 0
    temp_calls = [c for c in calls if c[0][1] == "set_temperature" and c[0][2]["temperature"] == 5.0]
    assert len(temp_calls) >= 1


# ---------------------------------------------------------------------------
# check_acs_can_heat unit tests
# ---------------------------------------------------------------------------


class TestCheckAcsCanHeat:
    """Unit tests for check_acs_can_heat."""

    def test_ac_with_heat_mode(self):
        """AC with 'heat' in hvac_modes → True."""
        hass = build_hass()
        state = MagicMock()
        state.attributes = {"hvac_modes": ["heat", "cool", "off"]}
        hass.states.get = MagicMock(return_value=state)
        room = make_room(thermostats=[], acs=["climate.hp"])
        assert check_acs_can_heat(hass, room) is True

    def test_ac_with_heat_cool_mode(self):
        """AC with 'heat_cool' in hvac_modes → True."""
        hass = build_hass()
        state = MagicMock()
        state.attributes = {"hvac_modes": ["heat_cool", "off"]}
        hass.states.get = MagicMock(return_value=state)
        room = make_room(thermostats=[], acs=["climate.hp"])
        assert check_acs_can_heat(hass, room) is True

    def test_ac_cool_only(self):
        """AC with only 'cool' → False."""
        hass = build_hass()
        state = MagicMock()
        state.attributes = {"hvac_modes": ["cool", "off"]}
        hass.states.get = MagicMock(return_value=state)
        room = make_room(thermostats=[], acs=["climate.ac"])
        assert check_acs_can_heat(hass, room) is False

    def test_no_acs(self):
        """No ACs → False."""
        hass = build_hass()
        room = make_room(thermostats=["climate.trv"], acs=[])
        assert check_acs_can_heat(hass, room) is False

    def test_ac_state_unavailable(self):
        """AC entity not found → False."""
        hass = build_hass()
        hass.states.get = MagicMock(return_value=None)
        room = make_room(thermostats=[], acs=["climate.hp"])
        assert check_acs_can_heat(hass, room) is False


# ---------------------------------------------------------------------------
# get_can_heat_cool with acs_can_heat
# ---------------------------------------------------------------------------


class TestGetCanHeatCoolAcsCanHeat:
    """Tests for get_can_heat_cool with acs_can_heat parameter."""

    def test_acs_can_heat_no_thermostats(self):
        """acs_can_heat=True allows heating even without thermostats."""
        from custom_components.roommind.control.mpc_controller import get_can_heat_cool

        room = make_room(thermostats=[], acs=["climate.hp"])
        can_heat, can_cool = get_can_heat_cool(room, acs_can_heat=True)
        assert can_heat is True
        assert can_cool is True

    def test_acs_can_heat_cool_only_mode(self):
        """acs_can_heat=True but cool_only mode → can_heat still False."""
        from custom_components.roommind.control.mpc_controller import get_can_heat_cool

        room = make_room(climate_mode="cool_only", thermostats=[], acs=["climate.hp"])
        can_heat, can_cool = get_can_heat_cool(room, acs_can_heat=True)
        assert can_heat is False
        assert can_cool is True

    def test_acs_can_heat_with_outdoor_gating(self):
        """acs_can_heat=True but outdoor above heating max → can_heat gated."""
        from custom_components.roommind.control.mpc_controller import get_can_heat_cool

        room = make_room(thermostats=[], acs=["climate.hp"])
        can_heat, can_cool = get_can_heat_cool(
            room,
            outdoor_temp=25.0,
            outdoor_heating_max=22.0,
            acs_can_heat=True,
        )
        assert can_heat is False

    def test_default_acs_can_heat_false(self):
        """Default acs_can_heat=False preserves old behavior."""
        from custom_components.roommind.control.mpc_controller import get_can_heat_cool

        room = make_room(thermostats=[], acs=["climate.hp"])
        can_heat, can_cool = get_can_heat_cool(room)
        assert can_heat is False
        assert can_cool is True


# ---------------------------------------------------------------------------
# async_apply: AC heating behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_heating_ac_with_heat_gets_target():
    """Heating: AC with 'heat' mode gets proportional boost target."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "temperature": 20.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.hp"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0, power_fraction=0.5, current_temp=18.0)

    calls = hass.services.async_call.call_args_list
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    # AC should get heat mode
    assert any(c[0][2].get("hvac_mode") == "heat" for c in hvac_calls)
    # AC should get proportional target: 18 + 0.5*(30-18) = 24.0
    assert any(c[0][2]["temperature"] == 24.0 for c in temp_calls)


@pytest.mark.asyncio
async def test_apply_heating_ac_heat_cool_mode():
    """Heating: AC with only 'heat_cool' (no separate 'heat') gets heat_cool."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["heat_cool", "cool", "off"], "temperature": 20.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.hp"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0, power_fraction=1.0, current_temp=18.0)

    calls = hass.services.async_call.call_args_list
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    assert any(c[0][2].get("hvac_mode") == "heat_cool" for c in hvac_calls)


@pytest.mark.asyncio
async def test_apply_heating_cool_only_ac_turned_off():
    """Heating: cool-only AC still gets turned off (no regression)."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "cool"
    ac_state.attributes = {"hvac_modes": ["cool", "off"], "temperature": 23.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(acs=["climate.ac"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0)

    calls = hass.services.async_call.call_args_list
    # AC should be turned off (via async_turn_off_climate)
    ac_off_calls = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.ac" and c[0][1] == "set_hvac_mode" and c[0][2].get("hvac_mode") == "off"
    ]
    assert len(ac_off_calls) >= 1


@pytest.mark.asyncio
async def test_apply_heating_trv_still_gets_boost():
    """Heating: TRV in thermostats[] still gets proportional 30°C boost."""
    from custom_components.roommind.control.mpc_controller import HEATING_BOOST_TARGET

    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 21.0, "min_temp": 5.0, "max_temp": 30.0}
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()  # thermostats=["climate.living_trv"]
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    # Full power: TRV should get 30°C (HEATING_BOOST_TARGET)
    await ctrl.async_apply("heating", 21.0, power_fraction=1.0, current_temp=18.0)

    calls = hass.services.async_call.call_args_list
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert temp_calls
    assert temp_calls[0][0][2]["temperature"] == HEATING_BOOST_TARGET


@pytest.mark.asyncio
async def test_managed_mode_ac_heat_cool():
    """Managed mode auto: AC with heat_cool gets heat_cool mode."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["heat_cool", "heat", "cool", "off"], "temperature": 20.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.hp"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", 21.0)

    calls = hass.services.async_call.call_args_list
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    # Should get heat_cool mode (not cool)
    assert any(c[0][2].get("hvac_mode") == "heat_cool" for c in hvac_calls)
    # Should get actual target temp
    assert any(c[0][2]["temperature"] == 21.0 for c in temp_calls)


@pytest.mark.asyncio
async def test_ac_only_room_can_heat():
    """Room with only heat-capable AC can enter heating mode."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "temperature": 20.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.hp"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    mode, pf = await ctrl.async_evaluate(current_temp=17.0, target_temp=21.0)
    assert mode == "heating"


@pytest.mark.asyncio
async def test_apply_heating_mixed_trv_and_ac():
    """Heating with TRV + heat-capable AC: TRV gets boost, AC gets proportional boost."""
    from custom_components.roommind.control.mpc_controller import HEATING_BOOST_TARGET

    hass = build_hass()

    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 21.0, "min_temp": 5.0, "max_temp": 30.0}

    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {
        "hvac_modes": ["heat", "cool", "off"],
        "temperature": 20.0,
        "min_temp": 16.0,
        "max_temp": 30.0,
    }

    def states_get(eid):
        if eid == "climate.living_trv":
            return trv_state
        if eid == "climate.hp":
            return ac_state
        return None

    hass.states.get = MagicMock(side_effect=states_get)

    room = make_room(thermostats=["climate.living_trv"], acs=["climate.hp"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0, power_fraction=1.0, current_temp=18.0)

    calls = hass.services.async_call.call_args_list
    # TRV should get boost target (30°C)
    trv_temp_calls = [
        c for c in calls if c[0][1] == "set_temperature" and c[0][2].get("entity_id") == "climate.living_trv"
    ]
    assert trv_temp_calls
    assert trv_temp_calls[0][0][2]["temperature"] == HEATING_BOOST_TARGET

    # AC should get proportional boost: 18 + 1.0*(30-18) = 30.0
    ac_temp_calls = [c for c in calls if c[0][1] == "set_temperature" and c[0][2].get("entity_id") == "climate.hp"]
    assert ac_temp_calls
    assert ac_temp_calls[0][0][2]["temperature"] == 30.0

    # AC should be in heat mode, not off
    ac_hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2].get("entity_id") == "climate.hp"]
    assert ac_hvac_calls
    assert ac_hvac_calls[0][0][2]["hvac_mode"] == "heat"


@pytest.mark.asyncio
async def test_managed_mode_auto_trv_and_heat_cool_ac():
    """Managed mode auto with TRV + heat_cool AC: TRV=heat, AC=heat_cool."""
    hass = build_hass()

    trv_state = MagicMock()
    trv_state.state = "off"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 20.0}

    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["heat_cool", "heat", "cool", "off"], "temperature": 20.0}

    def states_get(eid):
        if eid == "climate.living_trv":
            return trv_state
        if eid == "climate.hp":
            return ac_state
        return None

    hass.states.get = MagicMock(side_effect=states_get)

    room = make_room(thermostats=["climate.living_trv"], acs=["climate.hp"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", 21.0)

    calls = hass.services.async_call.call_args_list

    # TRV should be in heat mode with target temp
    trv_hvac = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2].get("entity_id") == "climate.living_trv"]
    assert trv_hvac
    assert trv_hvac[0][0][2]["hvac_mode"] == "heat"

    # AC should be in heat_cool mode (self-regulates both directions)
    ac_hvac = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2].get("entity_id") == "climate.hp"]
    assert ac_hvac
    assert ac_hvac[0][0][2]["hvac_mode"] == "heat_cool"

    # Both should get target temp 21°C
    trv_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2].get("entity_id") == "climate.living_trv"]
    ac_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2].get("entity_id") == "climate.hp"]
    assert trv_temp and trv_temp[0][0][2]["temperature"] == 21.0
    assert ac_temp and ac_temp[0][0][2]["temperature"] == 21.0


# ---------------------------------------------------------------------------
# async_turn_off_climate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_off_already_off():
    """Device already off is a no-op."""
    hass = build_hass()
    state = MagicMock()
    state.state = "off"
    state.attributes = {"hvac_modes": ["heat", "off"]}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv1", area_id="room_a")
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_turn_off_calls_set_hvac_mode_off():
    """Normal device gets set_hvac_mode(off)."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"]}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv1", area_id="room_a")
    hass.services.async_call.assert_called_once()
    call_args = hass.services.async_call.call_args[0]
    assert call_args[1] == "set_hvac_mode"
    assert call_args[2]["hvac_mode"] == "off"


@pytest.mark.asyncio
async def test_turn_off_set_hvac_mode_exception():
    """Exception in set_hvac_mode(off) is caught, doesn't raise."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"]}
    hass.states.get = MagicMock(return_value=state)
    hass.services.async_call = AsyncMock(side_effect=RuntimeError("service error"))

    # Should not raise
    await async_turn_off_climate(hass, "climate.trv1", area_id="room_a")


@pytest.mark.asyncio
async def test_turn_off_fallback_to_min_temp():
    """Heat-only device without 'off' mode uses min_temp fallback."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat"], "min_temp": 5.0, "temperature": 21.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv1", area_id="room_a")
    call_args = hass.services.async_call.call_args[0]
    assert call_args[1] == "set_temperature"
    assert call_args[2]["temperature"] == 5.0


@pytest.mark.asyncio
async def test_turn_off_fallback_redundant_skip():
    """Heat-only device already at min_temp is a no-op."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat"], "min_temp": 5.0, "temperature": 5.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv1", area_id="room_a")
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_turn_off_cooling_device_uses_max_temp():
    """Cool-only device without 'off' uses max_temp fallback."""
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {"hvac_modes": ["cool"], "max_temp": 30.0, "temperature": 24.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv1", area_id="room_a")
    call_args = hass.services.async_call.call_args[0]
    assert call_args[1] == "set_temperature"
    assert call_args[2]["temperature"] == 30.0


@pytest.mark.asyncio
async def test_turn_off_no_min_temp_attribute():
    """Heat-only device without min_temp attribute logs warning, returns."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat"]}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv1", area_id="room_a")
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_turn_off_fallback_set_temperature_exception():
    """Exception in fallback set_temperature is caught."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat"], "min_temp": 5.0, "temperature": 21.0}
    hass.states.get = MagicMock(return_value=state)
    hass.services.async_call = AsyncMock(side_effect=RuntimeError("service error"))

    # Should not raise
    await async_turn_off_climate(hass, "climate.trv1", area_id="room_a")


@pytest.mark.asyncio
async def test_turn_off_no_state():
    """Entity with no state (None) treats as modes unknown and tries off."""
    hass = build_hass()
    hass.states.get = MagicMock(return_value=None)

    await async_turn_off_climate(hass, "climate.trv1", area_id="room_a")
    hass.services.async_call.assert_called_once()


# ---------------------------------------------------------------------------
# _evaluate_bangbang hysteresis
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bangbang_heating_stickiness():
    """In heating mode, stays heating until at target."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    ctrl.previous_mode = MODE_HEATING
    mode = ctrl._evaluate_bangbang(20.0, TargetTemps(heat=21.0, cool=24.0))
    assert mode == MODE_HEATING


@pytest.mark.asyncio
async def test_bangbang_heating_reaches_target():
    """In heating mode, switches to idle at target."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    ctrl.previous_mode = MODE_HEATING
    mode = ctrl._evaluate_bangbang(21.5, TargetTemps(heat=21.0, cool=24.0))
    assert mode == MODE_IDLE


@pytest.mark.asyncio
async def test_bangbang_cooling_stickiness():
    """In cooling mode, stays cooling until at target."""
    hass = build_hass()
    room = make_room(acs=["climate.ac1"], climate_mode="cool_only")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    ctrl.previous_mode = MODE_COOLING
    mode = ctrl._evaluate_bangbang(25.0, TargetTemps(heat=21.0, cool=23.0))
    assert mode == MODE_COOLING


@pytest.mark.asyncio
async def test_bangbang_cooling_reaches_target():
    """In cooling mode, switches to idle at target."""
    hass = build_hass()
    room = make_room(acs=["climate.ac1"], climate_mode="cool_only")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    ctrl.previous_mode = MODE_COOLING
    mode = ctrl._evaluate_bangbang(22.5, TargetTemps(heat=21.0, cool=23.0))
    assert mode == MODE_IDLE


@pytest.mark.asyncio
async def test_bangbang_idle_to_heating():
    """From idle, starts heating below threshold."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    ctrl.previous_mode = MODE_IDLE
    mode = ctrl._evaluate_bangbang(20.0, TargetTemps(heat=21.0, cool=24.0))
    assert mode == MODE_HEATING


@pytest.mark.asyncio
async def test_bangbang_idle_to_cooling():
    """From idle, starts cooling above threshold."""
    hass = build_hass()
    room = make_room(acs=["climate.ac1"], climate_mode="cool_only")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    ctrl.previous_mode = MODE_IDLE
    mode = ctrl._evaluate_bangbang(24.0, TargetTemps(heat=21.0, cool=23.0))
    assert mode == MODE_COOLING


@pytest.mark.asyncio
async def test_bangbang_idle_deadband():
    """Within deadband from idle, stays idle."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    ctrl.previous_mode = MODE_IDLE
    mode = ctrl._evaluate_bangbang(20.9, TargetTemps(heat=21.0, cool=24.0))
    assert mode == MODE_IDLE


@pytest.mark.asyncio
async def test_bangbang_none_inputs():
    """None inputs return idle."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    assert ctrl._evaluate_bangbang(None, TargetTemps(heat=21.0, cool=24.0)) == MODE_IDLE
    assert ctrl._evaluate_bangbang(20.0, TargetTemps(heat=None, cool=None)) == MODE_IDLE


@pytest.mark.asyncio
async def test_bangbang_heating_min_run_holds_at_target():
    """Underfloor heating must keep running when at target but within min-run window."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
        previous_mode=MODE_HEATING,
        heating_system_type="underfloor",
        mode_on_since=time.time() - 60,  # 1 min in, window is 30 min
    )
    # current_temp equals target — without min-run this would go idle
    mode = ctrl._evaluate_bangbang(21.0, TargetTemps(heat=21.0, cool=24.0))
    assert mode == MODE_HEATING


@pytest.mark.asyncio
async def test_bangbang_heating_idles_after_min_run():
    """Underfloor heating goes idle at target once the min-run window has elapsed."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
        previous_mode=MODE_HEATING,
        heating_system_type="underfloor",
        mode_on_since=time.time() - 2000,  # 33 min ago, past 30-min window
    )
    mode = ctrl._evaluate_bangbang(21.5, TargetTemps(heat=21.0, cool=24.0))
    assert mode == MODE_IDLE


@pytest.mark.asyncio
async def test_bangbang_cooling_min_run_holds_at_target():
    """Cooling must keep running when at target but within min-run window."""
    hass = build_hass()
    room = make_room(acs=["climate.ac1"], climate_mode="cool_only")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
        previous_mode=MODE_COOLING,
        heating_system_type="underfloor",
        mode_on_since=time.time() - 60,
    )
    mode = ctrl._evaluate_bangbang(23.0, TargetTemps(heat=21.0, cool=23.0))
    assert mode == MODE_COOLING


# ---------------------------------------------------------------------------
# _evaluate_mpc edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_mpc_none_inputs():
    """None current_temp or target_temp returns idle."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    mode, pf = ctrl._evaluate_mpc(None, TargetTemps(heat=21.0, cool=24.0))
    assert mode == MODE_IDLE
    assert pf == 0.0

    mode, pf = ctrl._evaluate_mpc(20.0, TargetTemps(heat=None, cool=None))
    assert mode == MODE_IDLE
    assert pf == 0.0


# ---------------------------------------------------------------------------
# _build_outdoor_series
# ---------------------------------------------------------------------------


def test_outdoor_series_no_forecast():
    """Without forecast, returns constant series."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    series = ctrl._build_outdoor_series(10)
    assert series == [5.0] * 10


def test_outdoor_series_none_outdoor_temp():
    """Without outdoor temp and no forecast, uses fallback."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=None,
        settings={},
        has_external_sensor=True,
    )
    series = ctrl._build_outdoor_series(10)
    assert len(series) == 10
    assert all(t == series[0] for t in series)  # all the same fallback


def test_outdoor_series_with_forecast():
    """With forecast, uses forecast temps extended to fill horizon."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    ctrl.outdoor_forecast = [
        {"temperature": 6.0},
        {"temperature": 7.0},
        {"temperature": 8.0},
    ]
    series = ctrl._build_outdoor_series(5)
    assert series[0] == 6.0
    assert series[1] == 7.0
    assert series[2] == 8.0
    assert series[3] == 8.0  # extended with last
    assert series[4] == 8.0


# ---------------------------------------------------------------------------
# async_apply edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_mode_not_idle_but_target_none():
    """Non-idle mode with None target falls back to idle."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", target_temp=None)
    # Should have called set_hvac_mode off (idle) for all devices
    calls = hass.services.async_call.call_args_list
    for c in calls:
        if c[0][1] == "set_hvac_mode":
            assert c[0][2]["hvac_mode"] == "off"


@pytest.mark.asyncio
async def test_apply_cooling_turns_off_thermostats():
    """Cooling mode turns off thermostats and cools ACs."""
    hass = build_hass()
    room = make_room(
        acs=["climate.ac1"],
        climate_mode="cool_only",
    )
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )

    await ctrl.async_apply("cooling", target_temp=23.0)
    calls = hass.services.async_call.call_args_list

    # AC should be set to cool
    ac_modes = [c for c in calls if c[0][2].get("entity_id") == "climate.ac1" and c[0][1] == "set_hvac_mode"]
    assert any(c[0][2]["hvac_mode"] == "cool" for c in ac_modes)

    # TRV should be turned off
    trv_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.living_trv"]
    # "off" is delegated to async_turn_off_climate which calls set_hvac_mode
    if trv_calls:
        assert any(c[0][2].get("hvac_mode") == "off" for c in trv_calls if c[0][1] == "set_hvac_mode")


@pytest.mark.asyncio
async def test_apply_managed_mode_ac_heat_only():
    """Managed mode AC with only 'heat' mode gets heat + target temp."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["heat"], "temperature": None}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(
        thermostats=[],
        acs=["climate.ac1"],
        climate_mode="auto",
        temperature_sensor="",  # no external sensor
    )
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )

    await ctrl.async_apply("heating", target_temp=21.0)
    calls = hass.services.async_call.call_args_list

    ac_hvac = [c for c in calls if c[0][2].get("entity_id") == "climate.ac1" and c[0][1] == "set_hvac_mode"]
    assert any(c[0][2]["hvac_mode"] == "heat" for c in ac_hvac)


@pytest.mark.asyncio
async def test_apply_managed_mode_ac_no_compatible_mode_turns_off():
    """Managed mode AC with no compatible mode attempts turn-off (warning if no off/min_temp)."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "fan_only"
    ac_state.attributes = {"hvac_modes": ["fan_only"], "temperature": None}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(
        thermostats=[],
        acs=["climate.ac1"],
        climate_mode="auto",
        temperature_sensor="",
    )
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )

    await ctrl.async_apply("heating", target_temp=21.0)
    # Device has no 'off' mode and no min_temp, so async_turn_off_climate
    # logs a warning and returns without calling any service
    hass.services.async_call.assert_not_called()


# ---------------------------------------------------------------------------
# _call redundancy skip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_skips_redundant_temperature():
    """Redundant set_temperature is skipped."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 21.0, "min_temp": 5, "max_temp": 30}
    hass.states.get = MagicMock(return_value=state)

    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 21.0})
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_call_skips_redundant_hvac_mode():
    """Redundant set_hvac_mode is skipped."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"]}
    hass.states.get = MagicMock(return_value=state)

    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl._call("set_hvac_mode", {"entity_id": "climate.living_trv", "hvac_mode": "heat"})
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_call_service_exception_caught():
    """Exception in service call is caught."""
    hass = build_hass()
    state = MagicMock()
    state.state = "off"
    state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 20.0, "min_temp": 5, "max_temp": 30}
    hass.states.get = MagicMock(return_value=state)
    hass.services.async_call = AsyncMock(side_effect=RuntimeError("fail"))

    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    # Should not raise
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 25.0})


@pytest.mark.asyncio
async def test_call_clamps_to_device_max():
    """Temperature is clamped to device max_temp."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 20.0, "min_temp": 5, "max_temp": 25}
    hass.states.get = MagicMock(return_value=state)

    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 30.0})
    # Should have been clamped to 25
    call_args = hass.services.async_call.call_args[0]
    assert call_args[2]["temperature"] == 25


# ---------------------------------------------------------------------------
# _has_enough_data cooling path
# ---------------------------------------------------------------------------


def test_has_enough_data_insufficient_cooling():
    """Returns False when cooling data is insufficient."""
    hass = build_hass()
    room = make_room(acs=["climate.ac1"], climate_mode="cool_only")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    # Model has no data
    assert ctrl._has_enough_data(can_heat=False, can_cool=True) is False


def test_has_enough_data_enough_idle_but_not_cooling():
    """Returns False when idle is sufficient but cooling data not."""
    hass = build_hass()
    room = make_room(acs=["climate.ac1"], climate_mode="cool_only")
    mgr = RoomModelManager()
    # Feed enough idle data (>= 60 updates)
    for _ in range(65):
        mgr.update("living_room", 20.0, 5.0, "idle", 3.0)
    # A few cooling updates (< 20)
    for _ in range(5):
        mgr.update("living_room", 25.0, 30.0, "cooling", 3.0, can_cool=True)

    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    assert ctrl._has_enough_data(can_heat=False, can_cool=True) is False


# ---------------------------------------------------------------------------
# _evaluate_managed_mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_managed_mode_none_target():
    """Managed mode with None target returns idle."""
    hass = build_hass()
    room = make_room(temperature_sensor="")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )
    assert ctrl._evaluate_managed_mode(TargetTemps(heat=None, cool=None)) == MODE_IDLE


@pytest.mark.asyncio
async def test_managed_mode_cool_only_can_cool():
    """Cool-only mode returns cooling when cooling is allowed."""
    hass = build_hass()
    room = make_room(acs=["climate.ac1"], climate_mode="cool_only")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=False,
    )
    assert ctrl._evaluate_managed_mode(TargetTemps(heat=21.0, cool=23.0)) == MODE_COOLING


@pytest.mark.asyncio
async def test_managed_mode_cool_only_gated():
    """Cool-only mode returns idle when outdoor temp too low."""
    hass = build_hass()
    room = make_room(acs=["climate.ac1"], climate_mode="cool_only")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )
    assert ctrl._evaluate_managed_mode(TargetTemps(heat=21.0, cool=23.0)) == MODE_IDLE


@pytest.mark.asyncio
async def test_managed_mode_heat_only_can_heat():
    """Heat-only mode returns heating when heating is allowed."""
    hass = build_hass()
    room = make_room(climate_mode="heat_only")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )
    assert ctrl._evaluate_managed_mode(TargetTemps(heat=21.0, cool=24.0)) == MODE_HEATING


@pytest.mark.asyncio
async def test_managed_mode_heat_only_gated():
    """Heat-only mode returns idle when outdoor temp too high."""
    hass = build_hass()
    room = make_room(climate_mode="heat_only")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=False,
    )
    assert ctrl._evaluate_managed_mode(TargetTemps(heat=21.0, cool=24.0)) == MODE_IDLE


@pytest.mark.asyncio
async def test_managed_mode_auto_both_available():
    """Auto mode with both heat and cool returns heating (season heuristic)."""
    hass = build_hass()
    # Need both TRVs and ACs, outdoor temp in a zone where both are allowed
    room = make_room(acs=["climate.ac1"], climate_mode="auto")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=18.0,
        settings={},  # between cooling_min(16) and heating_max(22)
        has_external_sensor=False,
    )
    assert ctrl._evaluate_managed_mode(TargetTemps(heat=21.0, cool=24.0)) == MODE_HEATING


@pytest.mark.asyncio
async def test_managed_mode_auto_only_cool():
    """Auto mode with only cooling available returns cooling."""
    hass = build_hass()
    # No thermostats, only ACs
    room = make_room(thermostats=[], acs=["climate.ac1"], climate_mode="auto")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=False,
    )
    assert ctrl._evaluate_managed_mode(TargetTemps(heat=21.0, cool=23.0)) == MODE_COOLING


@pytest.mark.asyncio
async def test_managed_mode_auto_neither():
    """Auto mode with neither heat nor cool returns idle."""
    hass = build_hass()
    room = make_room(thermostats=[], acs=[], climate_mode="auto")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=False,
    )
    assert ctrl._evaluate_managed_mode(TargetTemps(heat=21.0, cool=24.0)) == MODE_IDLE


# ---------------------------------------------------------------------------
# _evaluate_mpc safety guard
# ---------------------------------------------------------------------------


def test_evaluate_mpc_safety_guard_heating_above_target(monkeypatch):
    """Safety guard overrides heating to idle when temp >= max(near_targets)."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    # Mock optimizer to return HEATING so the safety guard is actually tested
    fake_plan = MPCPlan(
        actions=[MODE_HEATING] * 6,
        temperatures=[22.0] * 7,
        power_fractions=[0.8] * 6,
    )
    monkeypatch.setattr(
        "custom_components.roommind.control.mpc_controller.MPCOptimizer.optimize",
        lambda *a, **kw: fake_plan,
    )
    # current_temp=22 >= target=21 → safety guard should override to idle
    mode, pf = ctrl._evaluate_mpc(22.0, TargetTemps(heat=21.0, cool=24.0))
    assert mode == MODE_IDLE
    assert pf == 0.0


def test_evaluate_mpc_safety_guard_cooling_below_target(monkeypatch):
    """Safety guard overrides cooling to idle when temp <= min(near_targets)."""
    hass = build_hass()
    room = make_room(acs=["climate.ac1"], thermostats=[], climate_mode="cool_only")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    # Mock optimizer to return COOLING so the safety guard is tested
    fake_plan = MPCPlan(
        actions=[MODE_COOLING] * 6,
        temperatures=[22.0] * 7,
        power_fractions=[0.8] * 6,
    )
    monkeypatch.setattr(
        "custom_components.roommind.control.mpc_controller.MPCOptimizer.optimize",
        lambda *a, **kw: fake_plan,
    )
    # current_temp=22 <= target=23 → safety guard should override to idle
    mode, pf = ctrl._evaluate_mpc(22.0, TargetTemps(heat=21.0, cool=23.0))
    assert mode == MODE_IDLE
    assert pf == 0.0


def test_evaluate_mpc_safety_guard_respects_min_run_heating(monkeypatch):
    """Safety guard must NOT override heating when within minimum run window."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
        previous_mode=MODE_HEATING,
        heating_system_type="underfloor",
        mode_on_since=time.time() - 60,  # started 1 min ago (within 30-min window)
    )
    fake_plan = MPCPlan(
        actions=[MODE_HEATING] * 6,
        temperatures=[22.0] * 7,
        power_fractions=[0.8] * 6,
    )
    monkeypatch.setattr(
        "custom_components.roommind.control.mpc_controller.MPCOptimizer.optimize",
        lambda *a, **kw: fake_plan,
    )
    # current_temp=22 >= target=21 but we're in min-run window → must keep heating
    mode, pf = ctrl._evaluate_mpc(22.0, TargetTemps(heat=21.0, cool=24.0))
    assert mode == MODE_HEATING


def test_evaluate_mpc_safety_guard_fires_after_min_run_heating(monkeypatch):
    """Safety guard must override heating when minimum run window has elapsed."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
        previous_mode=MODE_HEATING,
        heating_system_type="underfloor",
        mode_on_since=time.time() - 2000,  # started 33 min ago (past 30-min window)
    )
    fake_plan = MPCPlan(
        actions=[MODE_HEATING] * 6,
        temperatures=[22.0] * 7,
        power_fractions=[0.8] * 6,
    )
    monkeypatch.setattr(
        "custom_components.roommind.control.mpc_controller.MPCOptimizer.optimize",
        lambda *a, **kw: fake_plan,
    )
    mode, pf = ctrl._evaluate_mpc(22.0, TargetTemps(heat=21.0, cool=24.0))
    assert mode == MODE_IDLE
    assert pf == 0.0


def test_evaluate_mpc_safety_guard_fires_after_default_min_run_heating(monkeypatch):
    """Safety guard must override heating when default minimum run window has elapsed."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
        previous_mode=MODE_HEATING,
        heating_system_type="",
        mode_on_since=time.time() - 660,  # started 11 min ago (past 10-min default window)
    )
    fake_plan = MPCPlan(
        actions=[MODE_HEATING] * 6,
        temperatures=[22.0] * 7,
        power_fractions=[0.8] * 6,
    )
    monkeypatch.setattr(
        "custom_components.roommind.control.mpc_controller.MPCOptimizer.optimize",
        lambda *a, **kw: fake_plan,
    )
    mode, pf = ctrl._evaluate_mpc(22.0, TargetTemps(heat=21.0, cool=24.0))
    assert mode == MODE_IDLE
    assert pf == 0.0


# ---------------------------------------------------------------------------
# _evaluate_mpc without target_resolver
# ---------------------------------------------------------------------------


def test_evaluate_mpc_no_target_resolver():
    """Without target_resolver, uses flat target_series."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
        target_resolver=None,
    )
    # Call _evaluate_mpc — it should use [target_temp] * horizon_blocks
    mode, pf = ctrl._evaluate_mpc(17.0, TargetTemps(heat=21.0, cool=24.0))
    assert mode in (MODE_HEATING, MODE_IDLE, MODE_COOLING)
    # Should also store a last_plan
    assert ctrl.last_plan is not None


def test_evaluate_mpc_with_target_resolver():
    """With target_resolver, builds target_series from resolver calls."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
        target_resolver=lambda ts: TargetTemps(heat=21.0, cool=24.0),  # constant resolver
    )
    mode, pf = ctrl._evaluate_mpc(17.0, TargetTemps(heat=21.0, cool=24.0))
    assert mode in (MODE_HEATING, MODE_IDLE, MODE_COOLING)
    assert ctrl.last_plan is not None


# ---------------------------------------------------------------------------
# _build_solar_series with cloud_series
# ---------------------------------------------------------------------------


def test_build_solar_series_with_cloud():
    """Cloud series is expanded to 5-min blocks and passed to build_solar_series."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
        cloud_series=[50.0, 80.0],
        latitude=48.0,
        longitude=11.0,
    )
    series = ctrl._build_solar_series(30)
    assert len(series) == 30
    # All values should be non-negative floats
    assert all(isinstance(v, (int, float)) and v >= 0 for v in series)


def test_build_solar_series_short_cloud_extended():
    """Short cloud series is extended to fill n_blocks."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
        cloud_series=[50.0],  # only 1 hour = 12 blocks
        latitude=48.0,
        longitude=11.0,
    )
    series = ctrl._build_solar_series(30)
    assert len(series) == 30


# ---------------------------------------------------------------------------
# Managed mode AC with "cool" in modes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_managed_mode_ac_cool_only():
    """Managed mode AC with only 'cool' mode gets cool + target temp."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["cool"], "temperature": None}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(
        thermostats=[],
        acs=["climate.ac1"],
        climate_mode="auto",
        temperature_sensor="",
    )
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=False,
    )

    await ctrl.async_apply("cooling", target_temp=23.0)
    calls = hass.services.async_call.call_args_list
    ac_hvac = [c for c in calls if c[0][2].get("entity_id") == "climate.ac1" and c[0][1] == "set_hvac_mode"]
    assert any(c[0][2]["hvac_mode"] == "cool" for c in ac_hvac)


# ---------------------------------------------------------------------------
# resolve_hvac_mode unit tests
# ---------------------------------------------------------------------------


class TestResolveHvacMode:
    def test_desired_available(self):
        assert resolve_hvac_mode("heat", ["off", "heat"]) == "heat"

    def test_fallback_to_auto_for_heat(self):
        assert resolve_hvac_mode("heat", ["off", "auto"]) == "auto"

    def test_fallback_to_auto_for_cool(self):
        assert resolve_hvac_mode("cool", ["off", "auto"]) == "auto"

    def test_fallback_to_auto_for_heat_cool(self):
        assert resolve_hvac_mode("heat_cool", ["off", "auto"]) == "auto"

    def test_no_compatible_mode(self):
        assert resolve_hvac_mode("heat", ["off", "fan_only"]) is None

    def test_empty_modes_returns_desired(self):
        assert resolve_hvac_mode("heat", []) == "heat"

    def test_auto_desired_and_available(self):
        assert resolve_hvac_mode("auto", ["off", "auto"]) == "auto"

    def test_auto_desired_not_available(self):
        assert resolve_hvac_mode("auto", ["off", "heat"]) is None


# ---------------------------------------------------------------------------
# Auto-only device tests (issue #44)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_heating_thermostat_auto_only():
    """Full control heating: thermostat with 'off'+'auto' gets 'auto' instead of 'heat'."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "off"
    trv_state.attributes = {
        "hvac_modes": ["off", "auto"],
        "temperature": None,
        "min_temp": 5.0,
        "max_temp": 30.0,
    }
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )

    await ctrl.async_apply("heating", 21.0, current_temp=19.0)
    calls = hass.services.async_call.call_args_list
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    assert not any(c[0][2]["hvac_mode"] == "heat" for c in hvac_calls)
    assert any(c[0][2]["hvac_mode"] == "auto" for c in hvac_calls)


@pytest.mark.asyncio
async def test_apply_managed_mode_thermostat_auto_only():
    """Managed mode: thermostat with only 'off'+'auto' gets 'auto' mode."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "off"
    trv_state.attributes = {
        "hvac_modes": ["off", "auto"],
        "temperature": None,
        "min_temp": 5.0,
        "max_temp": 30.0,
    }
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room(temperature_sensor="")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )

    await ctrl.async_apply("heating", target_temp=21.0)
    calls = hass.services.async_call.call_args_list
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2].get("entity_id") == "climate.living_trv"]
    assert not any(c[0][2]["hvac_mode"] == "heat" for c in hvac_calls)
    assert any(c[0][2]["hvac_mode"] == "auto" for c in hvac_calls)


@pytest.mark.asyncio
async def test_apply_cooling_ac_auto_only():
    """AC with only 'off'+'auto' hvac_modes gets 'auto' instead of 'cool'."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["off", "auto"], "temperature": None}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac1"])
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=35.0,
        settings={},
        has_external_sensor=True,
    )

    await ctrl.async_apply("cooling", 23.0)
    calls = hass.services.async_call.call_args_list
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    assert not any(c[0][2]["hvac_mode"] == "cool" for c in hvac_calls)
    assert any(c[0][2]["hvac_mode"] == "auto" for c in hvac_calls)


@pytest.mark.asyncio
async def test_apply_managed_mode_ac_auto_only():
    """Managed mode AC with only 'off'+'auto' gets 'auto' mode via cascade."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["off", "auto"], "temperature": None}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(
        thermostats=[],
        acs=["climate.ac1"],
        climate_mode="auto",
        temperature_sensor="",
    )
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=False,
    )

    await ctrl.async_apply("cooling", target_temp=23.0)
    calls = hass.services.async_call.call_args_list
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2].get("entity_id") == "climate.ac1"]
    assert any(c[0][2]["hvac_mode"] == "auto" for c in hvac_calls)


@pytest.mark.asyncio
async def test_apply_heating_ac_auto_only():
    """MODE_HEATING: AC with only 'off'+'auto' gets 'auto' via cascade."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["off", "auto"], "temperature": None}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(acs=["climate.ac1"])
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )

    await ctrl.async_apply("heating", 21.0)
    calls = hass.services.async_call.call_args_list
    ac_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.ac1" and c[0][1] == "set_hvac_mode"]
    assert any(c[0][2]["hvac_mode"] == "auto" for c in ac_calls)


def test_acs_can_heat_auto_mode():
    """AC with only 'off'+'auto' hvac_modes is recognized as heat-capable."""
    hass = build_hass()
    state = MagicMock()
    state.attributes = {"hvac_modes": ["off", "auto"]}
    hass.states.get = MagicMock(return_value=state)
    assert (
        check_acs_can_heat(
            hass,
            {
                "acs": ["climate.ac1"],
                "devices": [{"entity_id": "climate.ac1", "type": "ac", "role": "auto", "heating_system_type": ""}],
            },
        )
        is True
    )


# ---------------------------------------------------------------------------
# Dead-band tests for bangbang with split targets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bangbang_deadband_split_targets():
    """Inside dead band (between heat and cool), bangbang returns idle."""
    hass = build_hass()
    room = make_room()
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    mode, pf = await ctrl.async_evaluate(
        current_temp=22.5,
        targets=TargetTemps(heat=21.0, cool=24.0),
    )
    assert mode == MODE_IDLE
    assert pf == 0.0


@pytest.mark.asyncio
async def test_bangbang_heats_with_split_below_heat():
    """Below heat target with split targets, bangbang heats."""
    hass = build_hass()
    room = make_room()
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    mode, pf = await ctrl.async_evaluate(
        current_temp=20.5,
        targets=TargetTemps(heat=21.0, cool=24.0),
    )
    assert mode == MODE_HEATING
    assert pf == 1.0  # bangbang: full power


@pytest.mark.asyncio
async def test_bangbang_cools_with_split_above_cool():
    """Above cool target with split targets, bangbang cools."""
    hass = build_hass()
    room = make_room(thermostats=[], acs=["climate.ac"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    mode, pf = await ctrl.async_evaluate(
        current_temp=24.5,
        targets=TargetTemps(heat=21.0, cool=24.0),
    )
    assert mode == MODE_COOLING
    assert pf == 1.0  # bangbang: full power


@pytest.mark.asyncio
async def test_bangbang_heat_only_none_cool():
    """TargetTemps(heat=21.0, cool=None) below heat target heats."""
    hass = build_hass()
    room = make_room()
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    mode, pf = await ctrl.async_evaluate(
        current_temp=20.5,
        targets=TargetTemps(heat=21.0, cool=None),
    )
    assert mode == MODE_HEATING
    assert pf == 1.0


@pytest.mark.asyncio
async def test_bangbang_cool_only_none_heat():
    """TargetTemps(heat=None, cool=24.0) above cool target cools."""
    hass = build_hass()
    room = make_room(thermostats=[], acs=["climate.ac"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    mode, pf = await ctrl.async_evaluate(
        current_temp=24.5,
        targets=TargetTemps(heat=None, cool=24.0),
    )
    assert mode == MODE_COOLING
    assert pf == 1.0


# ---------------------------------------------------------------------------
# async_evaluate with split TargetTemps (full flow)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_evaluate_split_deadband_idle():
    """Full async_evaluate: temp in dead band → IDLE."""
    hass = build_hass()
    room = make_room(acs=["climate.ac"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=20.0,
        settings={},
        has_external_sensor=True,
    )
    mode, pf = await ctrl.async_evaluate(
        current_temp=22.5,
        targets=TargetTemps(heat=21.0, cool=24.0),
    )
    assert mode == MODE_IDLE
    assert pf == 0.0


@pytest.mark.asyncio
async def test_async_evaluate_split_heats_below_heat():
    """Full async_evaluate: temp below heat target → HEATING."""
    hass = build_hass()
    room = make_room()
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    mode, pf = await ctrl.async_evaluate(
        current_temp=20.5,
        targets=TargetTemps(heat=21.0, cool=24.0),
    )
    assert mode == MODE_HEATING
    assert pf == 1.0


@pytest.mark.asyncio
async def test_async_evaluate_split_cools_above_cool():
    """Full async_evaluate: temp above cool target → COOLING."""
    hass = build_hass()
    room = make_room(thermostats=[], acs=["climate.ac"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    mode, pf = await ctrl.async_evaluate(
        current_temp=24.5,
        targets=TargetTemps(heat=21.0, cool=24.0),
    )
    assert mode == MODE_COOLING
    assert pf == 1.0


# ---------------------------------------------------------------------------
# Stickiness with split TargetTemps
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bangbang_stickiness_heating_stops_in_deadband():
    """Was HEATING at 22.0 (>heat=21, <cool=24) → should go IDLE, not COOLING."""
    hass = build_hass()
    room = make_room(acs=["climate.ac"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=20.0,
        settings={},
        has_external_sensor=True,
        previous_mode=MODE_HEATING,
    )
    mode, pf = await ctrl.async_evaluate(
        current_temp=22.0,
        targets=TargetTemps(heat=21.0, cool=24.0),
    )
    assert mode == MODE_IDLE
    assert pf == 0.0


@pytest.mark.asyncio
async def test_bangbang_stickiness_cooling_stops_in_deadband():
    """Was COOLING at 23.0 (<cool=24, >heat=21) → should go IDLE, not HEATING."""
    hass = build_hass()
    room = make_room(thermostats=[], acs=["climate.ac"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
        previous_mode=MODE_COOLING,
    )
    mode, pf = await ctrl.async_evaluate(
        current_temp=23.0,
        targets=TargetTemps(heat=21.0, cool=24.0),
    )
    assert mode == MODE_IDLE
    assert pf == 0.0


# ---------------------------------------------------------------------------
# Proportional AC boost tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_proportional_mixed_trv_ac_half_power():
    """Mixed TRV+AC room at 50% power: both get correct proportional targets."""
    hass = build_hass()

    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 21.0, "min_temp": 5.0, "max_temp": 30.0}

    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {
        "hvac_modes": ["heat", "cool", "off"],
        "temperature": 20.0,
        "min_temp": 16.0,
        "max_temp": 30.0,
    }

    def states_get(eid):
        if eid == "climate.trv":
            return trv_state
        if eid == "climate.ac":
            return ac_state
        return None

    hass.states.get = MagicMock(side_effect=states_get)

    room = make_room(thermostats=["climate.trv"], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0, power_fraction=0.5, current_temp=18.0)

    calls = hass.services.async_call.call_args_list
    # TRV: 18 + 0.5*(30-18) = 24.0
    trv_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2].get("entity_id") == "climate.trv"]
    assert trv_temp and trv_temp[0][0][2]["temperature"] == 24.0
    # AC: 18 + 0.5*(30-18) = 24.0
    ac_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2].get("entity_id") == "climate.ac"]
    assert ac_temp and ac_temp[0][0][2]["temperature"] == 24.0


@pytest.mark.asyncio
async def test_proportional_ac_heating_half_power():
    """AC heating at 50% power gets proportional boost between current and 30°C."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "temperature": 20.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0, power_fraction=0.5, current_temp=20.0)

    calls = hass.services.async_call.call_args_list
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    # 20 + 0.5*(30-20) = 25.0
    assert any(c[0][2]["temperature"] == 25.0 for c in temp_calls)


@pytest.mark.asyncio
async def test_proportional_ac_cooling_half_power():
    """AC cooling at 50% power gets proportional boost between current and 16°C."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["cool", "off"], "temperature": 23.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=35.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("cooling", 23.0, power_fraction=0.5, current_temp=26.0)

    calls = hass.services.async_call.call_args_list
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    # 26 - 0.5*(26-16) = 21.0
    assert any(c[0][2]["temperature"] == 21.0 for c in temp_calls)


@pytest.mark.asyncio
async def test_proportional_ac_heating_clamped_floor():
    """Very low power heating: AC target clamped to effective_target floor."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 20.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    # Raw: 20.5 + 0.01*(30-20.5) = 20.595 → clamped to max(21.0, 20.6) = 21.0
    await ctrl.async_apply("heating", 21.0, power_fraction=0.01, current_temp=20.5)

    calls = hass.services.async_call.call_args_list
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert any(c[0][2]["temperature"] == 21.0 for c in temp_calls)


@pytest.mark.asyncio
async def test_proportional_ac_cooling_clamped_ceiling():
    """Very low power cooling: AC target clamped to effective_target ceiling."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["cool", "off"], "temperature": 25.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=35.0,
        settings={},
        has_external_sensor=True,
    )
    # Raw: 23.5 - 0.01*(23.5-16) = 23.425 → clamped to min(23.0, 23.4) = 23.0
    await ctrl.async_apply("cooling", 23.0, power_fraction=0.01, current_temp=23.5)

    calls = hass.services.async_call.call_args_list
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert any(c[0][2]["temperature"] == 23.0 for c in temp_calls)


@pytest.mark.asyncio
async def test_proportional_ac_heating_no_current_temp():
    """AC heating without current_temp falls back to effective_target."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "temperature": 20.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0, power_fraction=0.8)

    calls = hass.services.async_call.call_args_list
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert any(c[0][2]["temperature"] == 21.0 for c in temp_calls)


@pytest.mark.asyncio
async def test_proportional_ac_cooling_no_current_temp():
    """AC cooling without current_temp falls back to effective_target."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["cool", "off"], "temperature": 25.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=35.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("cooling", 23.0, power_fraction=0.8)

    calls = hass.services.async_call.call_args_list
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert any(c[0][2]["temperature"] == 23.0 for c in temp_calls)


@pytest.mark.asyncio
async def test_proportional_ac_managed_mode_unchanged():
    """Managed mode AC gets actual target, NOT proportional boost (regression guard)."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["heat_cool", "heat", "cool", "off"], "temperature": 20.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(
        thermostats=[],
        acs=["climate.ac"],
        climate_mode="auto",
        temperature_sensor="",
    )
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", 21.0, power_fraction=0.5, current_temp=18.0)

    calls = hass.services.async_call.call_args_list
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    # Managed mode: AC should get actual target (21.0), not proportional boost
    assert any(c[0][2]["temperature"] == 21.0 for c in temp_calls)


# ---------------------------------------------------------------------------
# Dynamic boost target tests (#76)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dynamic_heating_boost_trv_full_power():
    """TRV at full power uses dynamic boost target (35) instead of default 30."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "off"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 20.0, "max_temp": 35.0}
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room(thermostats=["climate.trv"], acs=[])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0, power_fraction=1.0, current_temp=20.0, heating_boost_target=35.0)

    temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert any(c[0][2]["temperature"] == 35.0 for c in temp_calls)


@pytest.mark.asyncio
async def test_dynamic_heating_boost_none_fallback():
    """When heating_boost_target is None, falls back to HEATING_BOOST_TARGET (30)."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "off"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 20.0}
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room(thermostats=["climate.trv"], acs=[])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0, power_fraction=1.0, current_temp=20.0, heating_boost_target=None)

    temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert any(c[0][2]["temperature"] == 30.0 for c in temp_calls)


@pytest.mark.asyncio
async def test_dynamic_heating_boost_proportional():
    """TRV at 50% power with dynamic boost=35: 20 + 0.5*(35-20) = 27.5."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "off"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 20.0, "max_temp": 35.0}
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room(thermostats=["climate.trv"], acs=[])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0, power_fraction=0.5, current_temp=20.0, heating_boost_target=35.0)

    temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert any(c[0][2]["temperature"] == 27.5 for c in temp_calls)


@pytest.mark.asyncio
async def test_dynamic_cooling_boost_full_power():
    """AC at full cooling power uses dynamic boost (18) instead of default 16."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["cool", "off"], "temperature": 23.0, "min_temp": 18.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=35.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("cooling", 23.0, power_fraction=1.0, current_temp=26.0, cooling_boost_target=18.0)

    temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert any(c[0][2]["temperature"] == 18.0 for c in temp_calls)


@pytest.mark.asyncio
async def test_dynamic_cooling_boost_none_fallback():
    """When cooling_boost_target is None, falls back to AC_COOLING_BOOST_TARGET (16)."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["cool", "off"], "temperature": 23.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=35.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("cooling", 23.0, power_fraction=1.0, current_temp=26.0, cooling_boost_target=None)

    temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    # 26 - 1.0*(26-16) = 16.0
    assert any(c[0][2]["temperature"] == 16.0 for c in temp_calls)


@pytest.mark.asyncio
async def test_dynamic_ac_heating_boost():
    """AC in heating mode uses ac_heating_boost_target instead of default 30."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "temperature": 20.0, "max_temp": 28.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0, power_fraction=1.0, current_temp=20.0, ac_heating_boost_target=28.0)

    temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert any(c[0][2]["temperature"] == 28.0 for c in temp_calls)


# --- dual-setpoint support (#78) ---


@pytest.mark.asyncio
async def test_call_dual_setpoint_heat_intent():
    """TRV with target_temp_low attr + temp_intent='heat' sends dual-setpoint keys."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {
        "hvac_modes": ["heat", "off"],
        "temperature": 20.0,
        "target_temp_low": 18.0,
        "target_temp_high": 25.0,
        "min_temp": 5.0,
        "max_temp": 30.0,
    }
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0, power_fraction=1.0, current_temp=18.0)

    temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert temp_calls
    last_data = temp_calls[-1][0][2]
    assert "target_temp_low" in last_data
    assert "temperature" not in last_data


@pytest.mark.asyncio
async def test_call_dual_setpoint_cool_intent():
    """AC with dual-setpoint + temp_intent='cool' sets target_temp_high."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {
        "hvac_modes": ["cool", "off"],
        "temperature": 22.0,
        "target_temp_low": 18.0,
        "target_temp_high": 25.0,
        "min_temp": 16.0,
        "max_temp": 30.0,
    }
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=35.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("cooling", 23.0, power_fraction=1.0, current_temp=26.0)

    temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert temp_calls
    last_data = temp_calls[-1][0][2]
    assert "target_temp_high" in last_data


@pytest.mark.asyncio
async def test_call_single_setpoint_unchanged():
    """Device WITHOUT target_temp_low uses 'temperature' key (backward compat)."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {
        "hvac_modes": ["heat", "off"],
        "temperature": 20.0,
        "min_temp": 5.0,
        "max_temp": 30.0,
    }
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0, power_fraction=1.0, current_temp=18.0)

    temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert temp_calls
    last_data = temp_calls[-1][0][2]
    assert "temperature" in last_data
    assert "target_temp_low" not in last_data


@pytest.mark.asyncio
async def test_call_dual_setpoint_no_intent_unchanged():
    """Device with target_temp_low but empty temp_intent uses 'temperature' key."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {
        "hvac_modes": ["heat", "off"],
        "temperature": 20.0,
        "target_temp_low": 18.0,
        "target_temp_high": 25.0,
        "min_temp": 5.0,
        "max_temp": 30.0,
    }
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    # Call _call directly with no temp_intent (default empty string)
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 22.0})

    assert hass.services.async_call.called
    call_data = hass.services.async_call.call_args[0][2]
    assert "temperature" in call_data
    assert "target_temp_low" not in call_data


@pytest.mark.asyncio
async def test_call_dual_setpoint_redundancy_skip():
    """Current low/high match desired after transformation: no service call."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {
        "hvac_modes": ["heat", "off"],
        "target_temp_low": 22.0,
        "target_temp_high": 25.0,
        "min_temp": 5.0,
        "max_temp": 30.0,
    }
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    # heat intent: low=22.0, high=max(22,25)=25.0 — matches state exactly
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 22.0}, temp_intent="heat")

    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_call_dual_setpoint_clamping():
    """Values beyond min/max are clamped for dual-setpoint."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {
        "hvac_modes": ["heat", "off"],
        "target_temp_low": 15.0,
        "target_temp_high": 24.0,
        "min_temp": 10.0,
        "max_temp": 25.0,
    }
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    # heat intent: low=8.0 (below min 10 → clamped to 10), high=max(8,24)=24.0
    # low differs from state (15→10) so not redundant
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 8.0}, temp_intent="heat")

    assert hass.services.async_call.called
    call_data = hass.services.async_call.call_args[0][2]
    assert call_data["target_temp_low"] == 10.0


@pytest.mark.asyncio
async def test_managed_auto_heat_cool_dual_setpoint():
    """Managed Auto AC in heat_cool + dual-setpoint sends both targets."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {
        "hvac_modes": ["heat_cool", "off"],
        "target_temp_low": 18.0,
        "target_temp_high": 25.0,
        "min_temp": 16.0,
        "max_temp": 30.0,
    }
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"], climate_mode="auto")
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", TargetTemps(heat=21.0, cool=25.0), power_fraction=1.0)

    temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert temp_calls
    last_data = temp_calls[-1][0][2]
    assert "target_temp_low" in last_data
    assert "target_temp_high" in last_data


@pytest.mark.asyncio
async def test_managed_auto_heat_cool_single_setpoint():
    """Managed Auto AC in heat_cool + single-setpoint sends 'temperature'."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {
        "hvac_modes": ["heat_cool", "off"],
        "temperature": 22.0,
        "min_temp": 16.0,
        "max_temp": 30.0,
    }
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"], climate_mode="auto")
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", TargetTemps(heat=21.0, cool=25.0), power_fraction=1.0)

    temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert temp_calls
    last_data = temp_calls[-1][0][2]
    assert "temperature" in last_data
    assert "target_temp_low" not in last_data


@pytest.mark.asyncio
async def test_turn_off_dual_setpoint_heat_only():
    """Heat-only device with dual-setpoint and no 'off' mode uses both low/high = min_temp."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {
        "hvac_modes": ["heat"],
        "target_temp_low": 20.0,
        "target_temp_high": 25.0,
        "min_temp": 5.0,
        "max_temp": 30.0,
    }
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv1", area_id="test")

    assert hass.services.async_call.called
    call_data = hass.services.async_call.call_args[0][2]
    assert call_data["target_temp_low"] == 5.0
    assert call_data["target_temp_high"] == 5.0


@pytest.mark.asyncio
async def test_heating_trv_dual_setpoint_full_control():
    """Full Control heating with dual-setpoint TRV gets proportional target_temp_low."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {
        "hvac_modes": ["heat", "off"],
        "temperature": 20.0,
        "target_temp_low": 18.0,
        "target_temp_high": 25.0,
        "min_temp": 5.0,
        "max_temp": 30.0,
    }
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    # power_fraction=0.5, current=20, boost=30: sp = 20 + 0.5*(30-20) = 25.0
    await ctrl.async_apply("heating", 21.0, power_fraction=0.5, current_temp=20.0)

    temp_calls = [
        c
        for c in hass.services.async_call.call_args_list
        if c[0][1] == "set_temperature" and c[0][2].get("entity_id") == "climate.living_trv"
    ]
    assert temp_calls
    call_data = temp_calls[-1][0][2]
    assert "target_temp_low" in call_data
    assert call_data["target_temp_low"] == 25.0


# ---------------------------------------------------------------------------
# Command cache tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_cache_fallback_skips_ir_device():
    """Cache prevents duplicate commands on IR devices with no temperature feedback."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "temperature": None, "min_temp": 5.0, "max_temp": 30.0}
    hass.states.get = MagicMock(return_value=state)

    room = make_room()
    ctrl = MPCController(
        hass, room, model_manager=RoomModelManager(), outdoor_temp=5.0, settings={}, has_external_sensor=True
    )
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 21.0})
    assert hass.services.async_call.call_count == 1

    # Second identical call should be skipped by cache
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 21.0})
    assert hass.services.async_call.call_count == 1


@pytest.mark.asyncio
async def test_call_cache_allows_different_temperature():
    """Cache allows calls with different temperatures to go through."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "temperature": None, "min_temp": 5.0, "max_temp": 30.0}
    hass.states.get = MagicMock(return_value=state)

    room = make_room()
    ctrl = MPCController(
        hass, room, model_manager=RoomModelManager(), outdoor_temp=5.0, settings={}, has_external_sensor=True
    )
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 21.0})
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 22.0})
    assert hass.services.async_call.call_count == 2


@pytest.mark.asyncio
async def test_call_cache_device_state_takes_priority():
    """Device state dedup takes priority over cache when state attributes are available."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 21.0, "min_temp": 5.0, "max_temp": 30.0}
    hass.states.get = MagicMock(return_value=state)

    # Prepopulate cache with a different temperature
    _last_commands["climate.living_trv"] = {
        "service": "set_temperature",
        "hvac_mode": None,
        "temperature": 20.0,
        "target_temp_low": None,
        "target_temp_high": None,
    }

    room = make_room()
    ctrl = MPCController(
        hass, room, model_manager=RoomModelManager(), outdoor_temp=5.0, settings={}, has_external_sensor=True
    )
    # 21.0 matches device state (21.0), so skipped by primary dedup, not cache
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 21.0})
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_call_cache_not_updated_on_exception():
    """Cache is not updated when the service call raises an exception."""
    hass = build_hass()
    hass.states.get = MagicMock(return_value=None)
    hass.services.async_call = AsyncMock(side_effect=Exception("fail"))

    room = make_room()
    ctrl = MPCController(
        hass, room, model_manager=RoomModelManager(), outdoor_temp=5.0, settings={}, has_external_sensor=True
    )
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 21.0})
    assert "climate.living_trv" not in _last_commands


@pytest.mark.asyncio
async def test_call_cache_persists_across_controller_instances():
    """Module-level cache persists across MPCController instances."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "temperature": None, "min_temp": 5.0, "max_temp": 30.0}
    hass.states.get = MagicMock(return_value=state)

    room = make_room()
    ctrl1 = MPCController(
        hass, room, model_manager=RoomModelManager(), outdoor_temp=5.0, settings={}, has_external_sensor=True
    )
    await ctrl1._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 21.0})
    assert hass.services.async_call.call_count == 1

    # New controller instance, same entity and temperature
    ctrl2 = MPCController(
        hass, room, model_manager=RoomModelManager(), outdoor_temp=5.0, settings={}, has_external_sensor=True
    )
    await ctrl2._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 21.0})
    assert hass.services.async_call.call_count == 1


@pytest.mark.asyncio
async def test_call_cache_dual_setpoint_fallback():
    """Cache fallback works for dual-setpoint IR devices."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat_cool"
    state.attributes = {
        "hvac_modes": ["heat_cool", "off"],
        "target_temp_low": None,
        "target_temp_high": None,
        "min_temp": 5.0,
        "max_temp": 30.0,
    }
    hass.states.get = MagicMock(return_value=state)

    room = make_room(thermostats=[], acs=["climate.living_trv"])
    ctrl = MPCController(
        hass, room, model_manager=RoomModelManager(), outdoor_temp=5.0, settings={}, has_external_sensor=True
    )
    await ctrl._call(
        "set_temperature",
        {"entity_id": "climate.living_trv", "target_temp_low": 18.0, "target_temp_high": 22.0},
    )
    assert hass.services.async_call.call_count == 1

    # Second identical call should be skipped by cache
    await ctrl._call(
        "set_temperature",
        {"entity_id": "climate.living_trv", "target_temp_low": 18.0, "target_temp_high": 22.0},
    )
    assert hass.services.async_call.call_count == 1


@pytest.mark.asyncio
async def test_call_cache_hvac_mode_fallback_no_state():
    """Cache fallback works for set_hvac_mode when device has no state."""
    hass = build_hass()
    hass.states.get = MagicMock(return_value=None)

    room = make_room()
    ctrl = MPCController(
        hass, room, model_manager=RoomModelManager(), outdoor_temp=5.0, settings={}, has_external_sensor=True
    )
    await ctrl._call("set_hvac_mode", {"entity_id": "climate.living_trv", "hvac_mode": "heat"})
    assert hass.services.async_call.call_count == 1

    # Second call skipped by cache
    await ctrl._call("set_hvac_mode", {"entity_id": "climate.living_trv", "hvac_mode": "heat"})
    assert hass.services.async_call.call_count == 1


@pytest.mark.asyncio
async def test_turn_off_cache_fallback():
    """async_turn_off_climate skips when cache says device is already off."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"]}
    hass.states.get = MagicMock(return_value=state)

    # Prepopulate cache with off command
    _last_commands["climate.ac"] = {
        "service": "set_hvac_mode",
        "hvac_mode": "off",
        "temperature": None,
        "target_temp_low": None,
        "target_temp_high": None,
    }

    await async_turn_off_climate(hass, "climate.ac")
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_turn_off_cache_updated():
    """async_turn_off_climate updates the cache after successful call."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"]}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.ac")
    assert "climate.ac" in _last_commands
    assert _last_commands["climate.ac"]["service"] == "set_hvac_mode"
    assert _last_commands["climate.ac"]["hvac_mode"] == "off"


@pytest.mark.asyncio
async def test_call_cache_rounding():
    """Cache comparison uses rounding, so 21.04 and 21.05 both round to 21.0."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "temperature": None, "min_temp": 5.0, "max_temp": 30.0}
    hass.states.get = MagicMock(return_value=state)

    room = make_room()
    ctrl = MPCController(
        hass, room, model_manager=RoomModelManager(), outdoor_temp=5.0, settings={}, has_external_sensor=True
    )
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 21.04})
    assert hass.services.async_call.call_count == 1

    # 21.05 rounds to 21.1 (Python banker's rounding: round(21.05, 1) = 21.1, round(21.04, 1) = 21.0)
    # So use 21.049 which also rounds to 21.0
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 21.049})
    assert hass.services.async_call.call_count == 1


# ---------------------------------------------------------------------------
# Turn-off fallback path cache tests (heat-only / cool-only devices without "off")
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_off_heat_only_cache_fallback_single_setpoint():
    """Heat-only TRV without 'off': cache prevents redundant min_temp fallback."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {
        "hvac_modes": ["heat"],
        "min_temp": 5.0,
        "max_temp": 30.0,
        "temperature": None,  # IR device: no temperature feedback
    }
    hass.states.get = MagicMock(return_value=state)

    # First call goes through (sets to min_temp=5.0)
    await async_turn_off_climate(hass, "climate.trv", area_id="bedroom")
    assert hass.services.async_call.call_count == 1
    call_data = hass.services.async_call.call_args[0][2]
    assert call_data["temperature"] == 5.0

    # Second call: cache has temperature=5.0, matches fallback_temp=5.0 → skipped
    await async_turn_off_climate(hass, "climate.trv", area_id="bedroom")
    assert hass.services.async_call.call_count == 1


@pytest.mark.asyncio
async def test_turn_off_cool_only_cache_fallback_single_setpoint():
    """Cool-only device without 'off': cache prevents redundant max_temp fallback."""
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {
        "hvac_modes": ["cool"],
        "min_temp": 16.0,
        "max_temp": 30.0,
        "temperature": None,  # IR device
    }
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.ac", area_id="living")
    assert hass.services.async_call.call_count == 1
    call_data = hass.services.async_call.call_args[0][2]
    assert call_data["temperature"] == 30.0

    # Cached → skipped
    await async_turn_off_climate(hass, "climate.ac", area_id="living")
    assert hass.services.async_call.call_count == 1


@pytest.mark.asyncio
async def test_turn_off_cool_only_cache_fallback_range_device():
    """Cool-only range device without 'off': cache prevents redundant fallback.

    Range device where target_temp_low has a value (is_range=True) but
    target_temp_high is None (cur_check=None for cooling), so cache is consulted.
    """
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {
        "hvac_modes": ["cool"],
        "min_temp": 16.0,
        "max_temp": 30.0,
        "target_temp_low": 18.0,  # Has value → is_range=True
        "target_temp_high": None,  # None → cur_check=None for cooling → cache fallback
    }
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.ac", area_id="living")
    assert hass.services.async_call.call_count == 1
    call_data = hass.services.async_call.call_args[0][2]
    assert call_data["target_temp_low"] == 30.0
    assert call_data["target_temp_high"] == 30.0

    # Cached → skipped
    await async_turn_off_climate(hass, "climate.ac", area_id="living")
    assert hass.services.async_call.call_count == 1


@pytest.mark.asyncio
async def test_turn_off_fallback_cache_updated():
    """Turn-off fallback path updates the cache after successful call."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {
        "hvac_modes": ["heat"],
        "min_temp": 5.0,
        "max_temp": 30.0,
        "temperature": None,
    }
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv", area_id="bedroom")
    assert "climate.trv" in _last_commands
    assert _last_commands["climate.trv"]["service"] == "set_temperature"
    assert _last_commands["climate.trv"]["temperature"] == 5.0


@pytest.mark.asyncio
async def test_turn_off_fallback_cache_not_updated_on_exception():
    """Turn-off fallback path does not update cache when service call fails."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {
        "hvac_modes": ["heat"],
        "min_temp": 5.0,
        "max_temp": 30.0,
        "temperature": None,
    }
    hass.states.get = MagicMock(return_value=state)
    hass.services.async_call = AsyncMock(side_effect=Exception("IR timeout"))

    await async_turn_off_climate(hass, "climate.trv", area_id="bedroom")
    assert "climate.trv" not in _last_commands


@pytest.mark.asyncio
async def test_turn_off_normal_path_cache_not_updated_on_exception():
    """Normal off path does not update cache when service call fails."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"]}
    hass.states.get = MagicMock(return_value=state)
    hass.services.async_call = AsyncMock(side_effect=Exception("fail"))

    await async_turn_off_climate(hass, "climate.ac", area_id="living")
    assert "climate.ac" not in _last_commands


@pytest.mark.asyncio
async def test_call_cache_mode_change_not_blocked():
    """Changing mode (heat→cool) is not blocked by cache from previous mode."""
    hass = build_hass()
    state = MagicMock()
    state.state = "off"  # Start from off so set_hvac_mode calls go through
    state.attributes = {"hvac_modes": ["heat", "cool", "off"], "temperature": None, "min_temp": 16, "max_temp": 30}
    hass.states.get = MagicMock(return_value=state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass, room, model_manager=RoomModelManager(), outdoor_temp=5.0, settings={}, has_external_sensor=True
    )

    # Send heat mode + temperature
    await ctrl._call("set_hvac_mode", {"entity_id": "climate.ac", "hvac_mode": "heat"})
    await ctrl._call("set_temperature", {"entity_id": "climate.ac", "temperature": 25.0})
    assert hass.services.async_call.call_count == 2

    # Switch to cool: different hvac_mode → goes through (cache has "heat")
    await ctrl._call("set_hvac_mode", {"entity_id": "climate.ac", "hvac_mode": "cool"})
    assert hass.services.async_call.call_count == 3

    # Different temperature for cooling → goes through
    await ctrl._call("set_temperature", {"entity_id": "climate.ac", "temperature": 20.0})
    assert hass.services.async_call.call_count == 4

    # Same cool temperature again → blocked by cache
    await ctrl._call("set_temperature", {"entity_id": "climate.ac", "temperature": 20.0})
    assert hass.services.async_call.call_count == 4


@pytest.mark.asyncio
async def test_call_cache_different_entities_independent():
    """Cache entries are per-entity, not shared across devices."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "temperature": None, "min_temp": 5, "max_temp": 30}
    hass.states.get = MagicMock(return_value=state)

    room = make_room(thermostats=["climate.trv1", "climate.trv2"])
    ctrl = MPCController(
        hass, room, model_manager=RoomModelManager(), outdoor_temp=5.0, settings={}, has_external_sensor=True
    )

    # Same temperature to two different entities: both go through
    await ctrl._call("set_temperature", {"entity_id": "climate.trv1", "temperature": 21.0})
    await ctrl._call("set_temperature", {"entity_id": "climate.trv2", "temperature": 21.0})
    assert hass.services.async_call.call_count == 2

    # Repeat: both blocked by their own cache entries
    await ctrl._call("set_temperature", {"entity_id": "climate.trv1", "temperature": 21.0})
    await ctrl._call("set_temperature", {"entity_id": "climate.trv2", "temperature": 21.0})
    assert hass.services.async_call.call_count == 2


@pytest.mark.asyncio
async def test_turn_off_cache_invalidated_by_heat_command():
    """After turning off via cache, a heat command goes through (different service intent)."""
    hass = build_hass()
    state = MagicMock()
    state.state = "off"
    state.attributes = {"hvac_modes": ["heat", "off"], "temperature": None, "min_temp": 5, "max_temp": 30}
    hass.states.get = MagicMock(return_value=state)

    # Turn off → skipped by state check (already off), but cache gets nothing
    await async_turn_off_climate(hass, "climate.trv")
    hass.services.async_call.assert_not_called()

    # Now device comes on: state changes to "heat"
    state.state = "heat"

    room = make_room()
    ctrl = MPCController(
        hass, room, model_manager=RoomModelManager(), outdoor_temp=5.0, settings={}, has_external_sensor=True
    )
    # Heat command goes through (cache is empty or has different service)
    await ctrl._call("set_temperature", {"entity_id": "climate.trv", "temperature": 25.0})
    assert hass.services.async_call.call_count == 1

    # Turn off again → goes through (state is "heat", no cache for off)
    await async_turn_off_climate(hass, "climate.trv")
    assert hass.services.async_call.call_count == 2


@pytest.mark.asyncio
async def test_call_cache_dual_setpoint_different_values_not_blocked():
    """Cache allows dual-setpoint calls with different values."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat_cool"
    state.attributes = {
        "hvac_modes": ["heat_cool", "off"],
        "target_temp_low": None,
        "target_temp_high": None,
        "min_temp": 5.0,
        "max_temp": 30.0,
    }
    hass.states.get = MagicMock(return_value=state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass, room, model_manager=RoomModelManager(), outdoor_temp=5.0, settings={}, has_external_sensor=True
    )

    await ctrl._call(
        "set_temperature",
        {"entity_id": "climate.ac", "target_temp_low": 18.0, "target_temp_high": 22.0},
    )
    assert hass.services.async_call.call_count == 1

    # Different low → goes through
    await ctrl._call(
        "set_temperature",
        {"entity_id": "climate.ac", "target_temp_low": 19.0, "target_temp_high": 22.0},
    )
    assert hass.services.async_call.call_count == 2

    # Different high → goes through
    await ctrl._call(
        "set_temperature",
        {"entity_id": "climate.ac", "target_temp_low": 19.0, "target_temp_high": 23.0},
    )
    assert hass.services.async_call.call_count == 3

    # Same as last → blocked
    await ctrl._call(
        "set_temperature",
        {"entity_id": "climate.ac", "target_temp_low": 19.0, "target_temp_high": 23.0},
    )
    assert hass.services.async_call.call_count == 3


@pytest.mark.asyncio
async def test_heat_source_plan_excluded_trv_skipped():
    """TRV in heat source plan but also in exclude_eids gets no service calls."""
    from custom_components.roommind.managers.heat_source_orchestrator import (
        DeviceCommand,
        HeatSourcePlan,
    )

    _last_commands.clear()
    hass = build_hass()
    room = make_room(thermostats=["climate.trv1", "climate.trv2"], acs=[])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )

    plan = HeatSourcePlan(
        commands=[
            DeviceCommand(
                entity_id="climate.trv1",
                role="primary",
                device_type="thermostat",
                active=True,
                power_fraction=0.8,
                reason="primary heating",
            ),
            DeviceCommand(
                entity_id="climate.trv2",
                role="primary",
                device_type="thermostat",
                active=True,
                power_fraction=0.8,
                reason="primary heating",
            ),
        ],
        active_sources="primary",
        reason="normal heating",
    )

    # Exclude trv1 (valve protection cycling)
    await ctrl.async_apply(
        mode=MODE_HEATING,
        targets=TargetTemps(heat=21.0, cool=None),
        power_fraction=0.8,
        current_temp=18.0,
        exclude_eids={"climate.trv1"},
        heat_source_plan=plan,
    )

    # Collect all entity_ids that received service calls
    called_eids = set()
    for call in hass.services.async_call.call_args_list:
        # Positional args pattern: async_call(domain, service, data)
        if call.args and len(call.args) >= 3 and isinstance(call.args[2], dict):
            eid = call.args[2].get("entity_id")
            if eid:
                called_eids.add(eid)
        # Keyword args pattern
        if "service_data" in (call.kwargs or {}):
            eid = call.kwargs["service_data"].get("entity_id")
            if eid:
                called_eids.add(eid)

    assert "climate.trv1" not in called_eids, "Excluded TRV should receive no service calls"
    assert "climate.trv2" in called_eids, "Non-excluded TRV should receive service calls"


def _make_ac_state_for_plan(hvac_modes, current_state="heat"):
    """Create a mock AC state with given hvac_modes for heat source plan tests."""
    state = MagicMock()
    state.state = current_state
    state.attributes = {"hvac_modes": hvac_modes, "min_temp": 5.0, "max_temp": 30.0, "temperature": None}
    return state


@pytest.mark.asyncio
async def test_heat_source_plan_active_trv_inactive_ac():
    """Active TRV gets heat mode + proportional temp, inactive AC gets turned off."""
    from custom_components.roommind.managers.heat_source_orchestrator import DeviceCommand, HeatSourcePlan

    _last_commands.clear()
    hass = build_hass()
    room = make_room(thermostats=["climate.trv1"], acs=["climate.ac1"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    plan = HeatSourcePlan(
        commands=[
            DeviceCommand(
                entity_id="climate.trv1",
                role="primary",
                device_type="thermostat",
                active=True,
                power_fraction=0.6,
                reason="test",
            ),
            DeviceCommand(
                entity_id="climate.ac1",
                role="secondary",
                device_type="ac",
                active=False,
                power_fraction=0.0,
                reason="test",
            ),
        ],
        active_sources="primary",
        reason="test",
    )
    # current=20, target=21, boost=30 -> trv = 20 + 0.6*(30-20) = 26.0
    await ctrl.async_apply(
        mode=MODE_HEATING,
        targets=TargetTemps(heat=21.0, cool=None),
        power_fraction=0.6,
        current_temp=20.0,
        heat_source_plan=plan,
    )

    calls = hass.services.async_call.call_args_list

    # TRV: heat mode + proportional temp
    trv_mode = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.trv1"]
    assert len(trv_mode) == 1
    assert trv_mode[0][0][2]["hvac_mode"] == "heat"

    trv_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == "climate.trv1"]
    assert len(trv_temp) == 1
    assert trv_temp[0][0][2]["temperature"] == 26.0

    # Inactive AC: turned off
    ac_mode = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.ac1"]
    assert len(ac_mode) == 1
    assert ac_mode[0][0][2]["hvac_mode"] == "off"

    # No temperature call for inactive AC
    ac_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2].get("entity_id") == "climate.ac1"]
    assert len(ac_temp) == 0


@pytest.mark.asyncio
async def test_heat_source_plan_active_ac_inactive_trv():
    """Active AC gets heat + proportional temp, inactive TRV gets heat + current_temp (valve closed)."""
    from custom_components.roommind.managers.heat_source_orchestrator import DeviceCommand, HeatSourcePlan

    _last_commands.clear()
    hass = build_hass()
    # AC currently in "off" so setting to "heat" is not redundant
    ac_state = _make_ac_state_for_plan(["heat", "cool", "off"], current_state="off")
    trv_state = MagicMock()
    trv_state.state = "off"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0, "max_temp": 30.0, "temperature": None}

    def _states_get(eid):
        if eid == "climate.ac1":
            return ac_state
        if eid == "climate.trv1":
            return trv_state
        return None

    hass.states.get = MagicMock(side_effect=_states_get)

    room = make_room(thermostats=["climate.trv1"], acs=["climate.ac1"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    plan = HeatSourcePlan(
        commands=[
            DeviceCommand(
                entity_id="climate.trv1",
                role="primary",
                device_type="thermostat",
                active=False,
                power_fraction=0.0,
                reason="test",
            ),
            DeviceCommand(
                entity_id="climate.ac1",
                role="secondary",
                device_type="ac",
                active=True,
                power_fraction=0.8,
                reason="test",
            ),
        ],
        active_sources="secondary",
        reason="test",
    )
    # current=19, target=21, ac_boost=30 -> ac = 19 + 0.8*(30-19) = 27.8
    await ctrl.async_apply(
        mode=MODE_HEATING,
        targets=TargetTemps(heat=21.0, cool=None),
        power_fraction=0.8,
        current_temp=19.0,
        heat_source_plan=plan,
    )

    calls = hass.services.async_call.call_args_list

    # Inactive TRV: heat mode + current_temp (19.0) to keep valve closed
    trv_mode = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.trv1"]
    assert len(trv_mode) == 1
    assert trv_mode[0][0][2]["hvac_mode"] == "heat"

    trv_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == "climate.trv1"]
    assert len(trv_temp) == 1
    assert trv_temp[0][0][2]["temperature"] == 19.0

    # Active AC: heat mode + proportional temp
    ac_mode = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.ac1"]
    assert len(ac_mode) == 1
    assert ac_mode[0][0][2]["hvac_mode"] == "heat"

    ac_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == "climate.ac1"]
    assert len(ac_temp) == 1
    assert ac_temp[0][0][2]["temperature"] == 27.8


@pytest.mark.asyncio
async def test_heat_source_plan_both_active_different_fractions():
    """Both devices active with different power fractions get correct proportional temps."""
    from custom_components.roommind.managers.heat_source_orchestrator import DeviceCommand, HeatSourcePlan

    _last_commands.clear()
    hass = build_hass()
    ac_state = _make_ac_state_for_plan(["heat", "cool", "off"])
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=["climate.trv1"], acs=["climate.ac1"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    plan = HeatSourcePlan(
        commands=[
            DeviceCommand(
                entity_id="climate.trv1",
                role="primary",
                device_type="thermostat",
                active=True,
                power_fraction=1.0,
                reason="test",
            ),
            DeviceCommand(
                entity_id="climate.ac1",
                role="secondary",
                device_type="ac",
                active=True,
                power_fraction=0.5,
                reason="test",
            ),
        ],
        active_sources="both",
        reason="test",
    )
    # current=20, trv_boost=30: trv = 20 + 1.0*(30-20) = 30.0
    # current=20, ac_boost=30:  ac  = 20 + 0.5*(30-20) = 25.0
    await ctrl.async_apply(
        mode=MODE_HEATING,
        targets=TargetTemps(heat=21.0, cool=None),
        power_fraction=1.0,
        current_temp=20.0,
        heat_source_plan=plan,
    )

    calls = hass.services.async_call.call_args_list

    trv_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == "climate.trv1"]
    assert len(trv_temp) == 1
    assert trv_temp[0][0][2]["temperature"] == 30.0

    ac_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == "climate.ac1"]
    assert len(ac_temp) == 1
    assert ac_temp[0][0][2]["temperature"] == 25.0


@pytest.mark.asyncio
async def test_heat_source_plan_excluded_eid_skipped():
    """Excluded EID in plan commands is skipped entirely (no service calls)."""
    from custom_components.roommind.managers.heat_source_orchestrator import DeviceCommand, HeatSourcePlan

    _last_commands.clear()
    hass = build_hass()
    room = make_room(thermostats=["climate.trv1", "climate.trv2"], acs=[])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    plan = HeatSourcePlan(
        commands=[
            DeviceCommand(
                entity_id="climate.trv1",
                role="primary",
                device_type="thermostat",
                active=True,
                power_fraction=0.7,
                reason="test",
            ),
            DeviceCommand(
                entity_id="climate.trv2",
                role="primary",
                device_type="thermostat",
                active=True,
                power_fraction=0.7,
                reason="test",
            ),
        ],
        active_sources="primary",
        reason="test",
    )
    await ctrl.async_apply(
        mode=MODE_HEATING,
        targets=TargetTemps(heat=21.0, cool=None),
        power_fraction=0.7,
        current_temp=20.0,
        exclude_eids={"climate.trv2"},
        heat_source_plan=plan,
    )

    calls = hass.services.async_call.call_args_list
    trv1_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.trv1"]
    assert len(trv1_calls) == 2  # set_hvac_mode + set_temperature

    trv2_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.trv2"]
    assert len(trv2_calls) == 0


@pytest.mark.asyncio
async def test_heat_source_plan_ac_cool_only_gets_off():
    """AC with only 'cool' in hvac_modes gets turned off when active in heating plan."""
    from custom_components.roommind.managers.heat_source_orchestrator import DeviceCommand, HeatSourcePlan

    _last_commands.clear()
    hass = build_hass()
    ac_state = _make_ac_state_for_plan(["cool", "off"])
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac1"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    plan = HeatSourcePlan(
        commands=[
            DeviceCommand(
                entity_id="climate.ac1",
                role="secondary",
                device_type="ac",
                active=True,
                power_fraction=0.8,
                reason="test",
            ),
        ],
        active_sources="secondary",
        reason="test",
    )
    await ctrl.async_apply(
        mode=MODE_HEATING,
        targets=TargetTemps(heat=21.0, cool=None),
        power_fraction=0.8,
        current_temp=20.0,
        heat_source_plan=plan,
    )

    calls = hass.services.async_call.call_args_list
    ac_mode = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.ac1"]
    assert len(ac_mode) == 1
    assert ac_mode[0][0][2]["hvac_mode"] == "off"

    # No temperature call for AC turned off
    ac_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2].get("entity_id") == "climate.ac1"]
    assert len(ac_temp) == 0


@pytest.mark.asyncio
async def test_heat_source_plan_ac_heat_cool_mode():
    """AC with 'heat_cool' but no 'heat' uses heat_cool hvac_mode."""
    from custom_components.roommind.managers.heat_source_orchestrator import DeviceCommand, HeatSourcePlan

    _last_commands.clear()
    hass = build_hass()
    ac_state = _make_ac_state_for_plan(["heat_cool", "cool", "off"])
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac1"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    plan = HeatSourcePlan(
        commands=[
            DeviceCommand(
                entity_id="climate.ac1",
                role="secondary",
                device_type="ac",
                active=True,
                power_fraction=0.5,
                reason="test",
            ),
        ],
        active_sources="secondary",
        reason="test",
    )
    # current=20, ac_boost=30 -> 20 + 0.5*(30-20) = 25.0
    await ctrl.async_apply(
        mode=MODE_HEATING,
        targets=TargetTemps(heat=21.0, cool=None),
        power_fraction=0.5,
        current_temp=20.0,
        heat_source_plan=plan,
    )

    calls = hass.services.async_call.call_args_list
    ac_mode = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.ac1"]
    assert len(ac_mode) == 1
    assert ac_mode[0][0][2]["hvac_mode"] == "heat_cool"

    ac_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == "climate.ac1"]
    assert len(ac_temp) == 1
    assert ac_temp[0][0][2]["temperature"] == 25.0


@pytest.mark.asyncio
async def test_heat_source_plan_managed_mode_no_external_sensor():
    """Managed mode (no external sensor, heat_only): TRV and AC both get effective_target."""
    from custom_components.roommind.managers.heat_source_orchestrator import DeviceCommand, HeatSourcePlan

    _last_commands.clear()
    hass = build_hass()
    # AC currently in "off" so setting to "heat" is not redundant
    ac_state = _make_ac_state_for_plan(["heat", "cool", "off"], current_state="off")
    trv_state = MagicMock()
    trv_state.state = "off"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0, "max_temp": 30.0, "temperature": None}

    def _states_get(eid):
        if eid == "climate.ac1":
            return ac_state
        if eid == "climate.trv1":
            return trv_state
        return None

    hass.states.get = MagicMock(side_effect=_states_get)

    # Use heat_only to bypass managed auto block (which returns early for auto mode)
    room = make_room(
        thermostats=["climate.trv1"],
        acs=["climate.ac1"],
        temperature_sensor="",
        climate_mode="heat_only",
    )
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )
    plan = HeatSourcePlan(
        commands=[
            DeviceCommand(
                entity_id="climate.trv1",
                role="primary",
                device_type="thermostat",
                active=True,
                power_fraction=0.7,
                reason="test",
            ),
            DeviceCommand(
                entity_id="climate.ac1",
                role="secondary",
                device_type="ac",
                active=True,
                power_fraction=0.5,
                reason="test",
            ),
        ],
        active_sources="both",
        reason="test",
    )
    # has_external_sensor=False: TRV gets effective_target (21.0), AC gets effective_target (21.0)
    await ctrl.async_apply(
        mode=MODE_HEATING,
        targets=TargetTemps(heat=21.0, cool=None),
        power_fraction=0.7,
        current_temp=None,
        heat_source_plan=plan,
    )

    calls = hass.services.async_call.call_args_list

    # TRV: heat mode + effective_target
    trv_mode = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.trv1"]
    assert len(trv_mode) == 1
    assert trv_mode[0][0][2]["hvac_mode"] == "heat"

    trv_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == "climate.trv1"]
    assert len(trv_temp) == 1
    assert trv_temp[0][0][2]["temperature"] == 21.0

    # AC: heat mode + effective_target
    ac_mode = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.ac1"]
    assert len(ac_mode) == 1
    assert ac_mode[0][0][2]["hvac_mode"] == "heat"

    ac_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == "climate.ac1"]
    assert len(ac_temp) == 1
    assert ac_temp[0][0][2]["temperature"] == 21.0


# ---------------------------------------------------------------------------
# Managed mode: AC-only room with heat+cool (no heat_cool) — Issue #100
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_managed_mode_ac_only_heat_cool_heats_when_cold():
    """AC-only managed mode: device temp below heat target → heat mode."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {
        "hvac_modes": ["heat", "cool", "off"],
        "current_temperature": 18.0,
        "temperature": None,
    }
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac1"], climate_mode="auto", temperature_sensor="")
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=None,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", TargetTemps(heat=21.0, cool=24.0))

    calls = hass.services.async_call.call_args_list
    hvac = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.ac1"]
    temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == "climate.ac1"]
    assert any(c[0][2]["hvac_mode"] == "heat" for c in hvac)
    assert any(c[0][2]["temperature"] == 21.0 for c in temp)


@pytest.mark.asyncio
async def test_managed_mode_ac_only_heat_cool_cools_when_hot():
    """AC-only managed mode: device temp above cool target → cool mode."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {
        "hvac_modes": ["heat", "cool", "off"],
        "current_temperature": 25.0,
        "temperature": None,
    }
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac1"], climate_mode="auto", temperature_sensor="")
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=None,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", TargetTemps(heat=21.0, cool=24.0))

    calls = hass.services.async_call.call_args_list
    hvac = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.ac1"]
    temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == "climate.ac1"]
    assert any(c[0][2]["hvac_mode"] == "cool" for c in hvac)
    assert any(c[0][2]["temperature"] == 24.0 for c in temp)


@pytest.mark.asyncio
async def test_managed_mode_ac_only_heat_cool_deadband_uses_heat():
    """AC-only managed mode: device temp in deadband → heat mode (safe default)."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {
        "hvac_modes": ["heat", "cool", "off"],
        "current_temperature": 22.0,
        "temperature": None,
    }
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac1"], climate_mode="auto", temperature_sensor="")
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=None,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", TargetTemps(heat=21.0, cool=24.0))

    calls = hass.services.async_call.call_args_list
    hvac = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.ac1"]
    assert any(c[0][2]["hvac_mode"] == "heat" for c in hvac)
    assert not any(c[0][2]["hvac_mode"] == "cool" for c in hvac)


@pytest.mark.asyncio
async def test_managed_mode_ac_only_heat_cool_no_current_temp():
    """AC-only managed mode: no current_temperature → heat mode (fallback)."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {
        "hvac_modes": ["heat", "cool", "off"],
        "temperature": None,
    }
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac1"], climate_mode="auto", temperature_sensor="")
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=None,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", TargetTemps(heat=21.0, cool=24.0))

    calls = hass.services.async_call.call_args_list
    hvac = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.ac1"]
    assert any(c[0][2]["hvac_mode"] == "heat" for c in hvac)
    assert not any(c[0][2]["hvac_mode"] == "cool" for c in hvac)


@pytest.mark.asyncio
async def test_managed_mode_mixed_room_ac_still_cools():
    """Mixed room (TRV+AC): AC still gets cool mode even when device temp is cold."""
    hass = build_hass()

    def _get(eid):
        s = MagicMock()
        s.state = "off"
        if eid == "climate.trv1":
            s.attributes = {"hvac_modes": ["heat", "off"], "temperature": None}
        else:
            s.attributes = {
                "hvac_modes": ["heat", "cool", "off"],
                "current_temperature": 18.0,
                "temperature": None,
            }
        return s

    hass.states.get = MagicMock(side_effect=_get)

    room = make_room(
        thermostats=["climate.trv1"],
        acs=["climate.ac1"],
        climate_mode="auto",
        temperature_sensor="",
    )
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=None,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", TargetTemps(heat=21.0, cool=24.0))

    calls = hass.services.async_call.call_args_list
    ac_hvac = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.ac1"]
    assert any(c[0][2]["hvac_mode"] == "cool" for c in ac_hvac)
    assert not any(c[0][2]["hvac_mode"] == "heat" for c in ac_hvac)


@pytest.mark.asyncio
async def test_managed_mode_ac_only_heat_cool_correct_target():
    """AC-only managed mode heating: temperature call uses heat_target, not cool_target."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {
        "hvac_modes": ["heat", "cool", "off"],
        "current_temperature": 18.0,
        "temperature": None,
    }
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac1"], climate_mode="auto", temperature_sensor="")
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=None,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", TargetTemps(heat=21.0, cool=24.0))

    calls = hass.services.async_call.call_args_list
    temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == "climate.ac1"]
    assert len(temp) == 1
    assert temp[0][0][2]["temperature"] == 21.0


# ---------------------------------------------------------------------------
# Compressor forced_on / forced_off tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_idle_forced_on_keeps_device_active():
    """In idle mode, forced_on sets device to target temp instead of turning off."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0}
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply(
        "idle",
        TargetTemps(heat=21.0, cool=24.0),
        compressor_forced_on={"climate.living_trv"},
    )
    calls = hass.services.async_call.call_args_list
    # No turn-off call
    off_calls = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.living_trv"
        and c[0][1] == "set_hvac_mode"
        and c[0][2].get("hvac_mode") == "off"
    ]
    assert len(off_calls) == 0
    # set_temperature called with heat target
    temp_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.living_trv" and c[0][1] == "set_temperature"]
    assert len(temp_calls) == 1
    assert temp_calls[0][0][2]["temperature"] == 21.0


@pytest.mark.asyncio
async def test_apply_heating_forced_off_turns_off_trv():
    """In heating mode, forced_off turns off TRV despite heating being active."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0}
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply(
        "heating",
        TargetTemps(heat=21.0, cool=24.0),
        compressor_forced_off={"climate.living_trv"},
    )
    calls = hass.services.async_call.call_args_list
    off_calls = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.living_trv"
        and c[0][1] == "set_hvac_mode"
        and c[0][2].get("hvac_mode") == "off"
    ]
    assert len(off_calls) >= 1


@pytest.mark.asyncio
async def test_apply_cooling_forced_off_turns_off_ac():
    """In cooling mode, forced_off turns off AC despite cooling being active."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "cool"
    ac_state.attributes = {"hvac_modes": ["cool", "off"], "min_temp": 16.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply(
        "cooling",
        TargetTemps(heat=21.0, cool=24.0),
        compressor_forced_off={"climate.ac"},
    )
    calls = hass.services.async_call.call_args_list
    off_calls = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.ac" and c[0][1] == "set_hvac_mode" and c[0][2].get("hvac_mode") == "off"
    ]
    assert len(off_calls) >= 1


@pytest.mark.asyncio
async def test_apply_managed_auto_forced_off():
    """In managed auto mode (no external sensor), forced_off turns off device."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0}
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room(temperature_sensor="")
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply(
        "heating",
        TargetTemps(heat=21.0, cool=24.0),
        compressor_forced_off={"climate.living_trv"},
    )
    calls = hass.services.async_call.call_args_list
    off_calls = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.living_trv"
        and c[0][1] == "set_hvac_mode"
        and c[0][2].get("hvac_mode") == "off"
    ]
    assert len(off_calls) >= 1


@pytest.mark.asyncio
async def test_apply_orchestrated_forced_on_overrides_inactive():
    """Forced_on overrides orchestrator marking device as inactive."""
    from custom_components.roommind.managers.heat_source_orchestrator import (
        DeviceCommand,
        HeatSourcePlan,
    )

    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "off"  # device was off, forced_on should activate it
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0}
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={"heat_source_orchestration": True},
        has_external_sensor=True,
    )
    plan = HeatSourcePlan(
        commands=[
            DeviceCommand(
                entity_id="climate.living_trv",
                role="primary",
                device_type="thermostat",
                active=False,  # orchestrator says inactive
                power_fraction=0.0,
                reason="test",
            ),
        ],
        active_sources="none",
        reason="test",
    )
    await ctrl.async_apply(
        "heating",
        TargetTemps(heat=21.0, cool=24.0),
        heat_source_plan=plan,
        compressor_forced_on={"climate.living_trv"},
    )
    # forced_on should set device to heat at target temp, not turn off
    calls = hass.services.async_call.call_args_list
    off_calls = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.living_trv"
        and c[0][1] == "set_hvac_mode"
        and c[0][2].get("hvac_mode") == "off"
    ]
    assert len(off_calls) == 0
    # set_hvac_mode("heat") and set_temperature called
    heat_calls = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.living_trv"
        and c[0][1] == "set_hvac_mode"
        and c[0][2].get("hvac_mode") == "heat"
    ]
    assert len(heat_calls) == 1
    temp_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.living_trv" and c[0][1] == "set_temperature"]
    assert len(temp_calls) == 1
    assert temp_calls[0][0][2]["temperature"] == 21.0


@pytest.mark.asyncio
async def test_apply_orchestrated_forced_off_overrides_active():
    """Forced_off overrides orchestrator marking device as active."""
    from custom_components.roommind.managers.heat_source_orchestrator import (
        DeviceCommand,
        HeatSourcePlan,
    )

    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0}
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={"heat_source_orchestration": True},
        has_external_sensor=True,
    )
    plan = HeatSourcePlan(
        commands=[
            DeviceCommand(
                entity_id="climate.living_trv",
                role="primary",
                device_type="thermostat",
                active=True,  # orchestrator says active
                power_fraction=1.0,
                reason="test",
            ),
        ],
        active_sources="primary",
        reason="test",
    )
    await ctrl.async_apply(
        "heating",
        TargetTemps(heat=21.0, cool=24.0),
        heat_source_plan=plan,
        compressor_forced_off={"climate.living_trv"},
    )
    # forced_off should turn off the device despite orchestrator saying active
    calls = hass.services.async_call.call_args_list
    off_calls = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.living_trv"
        and c[0][1] == "set_hvac_mode"
        and c[0][2].get("hvac_mode") == "off"
    ]
    assert len(off_calls) >= 1


@pytest.mark.asyncio
async def test_apply_forced_on_and_off_empty_sets_no_effect():
    """Empty forced_on/forced_off sets do not alter normal behavior."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "off"  # not yet heating, so set_hvac_mode won't be skipped as redundant
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0}
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    # Normal heating with empty sets
    await ctrl.async_apply(
        "heating",
        TargetTemps(heat=21.0, cool=24.0),
        compressor_forced_on=set(),
        compressor_forced_off=set(),
    )
    calls = hass.services.async_call.call_args_list
    # TRV should receive heat mode and temperature as normal
    heat_calls = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.living_trv"
        and c[0][1] == "set_hvac_mode"
        and c[0][2].get("hvac_mode") == "heat"
    ]
    assert len(heat_calls) >= 1


@pytest.mark.asyncio
async def test_apply_idle_forced_on_cooling_ac():
    """In idle mode, forced_on AC in cool mode gets cool target."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "cool"
    ac_state.attributes = {"hvac_modes": ["cool", "heat", "off"], "min_temp": 16.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply(
        "idle",
        TargetTemps(heat=21.0, cool=24.0),
        compressor_forced_on={"climate.ac"},
    )
    calls = hass.services.async_call.call_args_list
    # set_temperature called with cool target
    temp_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.ac" and c[0][1] == "set_temperature"]
    assert len(temp_calls) == 1
    assert temp_calls[0][0][2]["temperature"] == 24.0
    # No hvac_mode change (device already in cool mode)
    mode_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.ac" and c[0][1] == "set_hvac_mode"]
    assert len(mode_calls) == 0


@pytest.mark.asyncio
async def test_apply_idle_forced_on_heat_cool_device():
    """In idle mode, forced_on device in heat_cool gets heat target via temp_intent."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "heat_cool"
    ac_state.attributes = {
        "hvac_modes": ["heat_cool", "off"],
        "min_temp": 16.0,
        "target_temp_low": 18.0,
        "target_temp_high": 26.0,
    }
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=20.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply(
        "idle",
        TargetTemps(heat=21.0, cool=24.0),
        compressor_forced_on={"climate.ac"},
    )
    calls = hass.services.async_call.call_args_list
    # set_temperature called with heat target (dual-setpoint handled by _call)
    temp_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.ac" and c[0][1] == "set_temperature"]
    assert len(temp_calls) == 1
    # _call converts to target_temp_low/high for dual-setpoint devices
    assert temp_calls[0][0][2].get("target_temp_low") == 21.0


@pytest.mark.asyncio
async def test_apply_idle_forced_on_no_target():
    """Forced_on device with no matching target does nothing (no crash)."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0}
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply(
        "idle",
        TargetTemps(heat=None, cool=None),
        compressor_forced_on={"climate.living_trv"},
    )
    calls = hass.services.async_call.call_args_list
    # No service calls for the forced_on device (no target available)
    trv_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.living_trv"]
    assert len(trv_calls) == 0


@pytest.mark.asyncio
async def test_apply_orchestrated_forced_on_ac():
    """Orchestrated forced_on AC gets heat mode + heat target."""
    from custom_components.roommind.managers.heat_source_orchestrator import (
        DeviceCommand,
        HeatSourcePlan,
    )

    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"  # device was off, forced_on should activate it
    ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "min_temp": 16.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={"heat_source_orchestration": True},
        has_external_sensor=True,
    )
    plan = HeatSourcePlan(
        commands=[
            DeviceCommand(
                entity_id="climate.ac",
                role="primary",
                device_type="ac",
                active=False,
                power_fraction=0.0,
                reason="test",
            ),
        ],
        active_sources="none",
        reason="test",
    )
    await ctrl.async_apply(
        "heating",
        TargetTemps(heat=21.0, cool=24.0),
        heat_source_plan=plan,
        compressor_forced_on={"climate.ac"},
    )
    calls = hass.services.async_call.call_args_list
    heat_calls = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.ac"
        and c[0][1] == "set_hvac_mode"
        and c[0][2].get("hvac_mode") == "heat"
    ]
    assert len(heat_calls) == 1
    temp_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.ac" and c[0][1] == "set_temperature"]
    assert len(temp_calls) == 1
    assert temp_calls[0][0][2]["temperature"] == 21.0


@pytest.mark.asyncio
async def test_apply_idle_forced_on_device_state_none():
    """Forced_on device with unavailable state (None) does nothing."""
    hass = build_hass()
    # build_hass default: hass.states.get returns None
    room = make_room()
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply(
        "idle",
        TargetTemps(heat=21.0, cool=24.0),
        compressor_forced_on={"climate.living_trv"},
    )
    calls = hass.services.async_call.call_args_list
    trv_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.living_trv"]
    assert len(trv_calls) == 0


@pytest.mark.asyncio
async def test_apply_idle_forced_on_heat_cool_no_targets():
    """Forced_on device in heat_cool with no targets does nothing."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "heat_cool"
    ac_state.attributes = {
        "hvac_modes": ["heat_cool", "off"],
        "min_temp": 16.0,
        "target_temp_low": 18.0,
        "target_temp_high": 26.0,
    }
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=20.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply(
        "idle",
        TargetTemps(heat=None, cool=None),
        compressor_forced_on={"climate.ac"},
    )
    calls = hass.services.async_call.call_args_list
    ac_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.ac"]
    assert len(ac_calls) == 0


@pytest.mark.asyncio
async def test_apply_idle_forced_on_managed_mode():
    """Forced_on in managed mode (no external sensor) sets target correctly."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0}
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room(temperature_sensor="")  # managed mode: no external sensor
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply(
        "idle",
        TargetTemps(heat=21.0, cool=24.0),
        compressor_forced_on={"climate.living_trv"},
    )
    calls = hass.services.async_call.call_args_list
    # No turn-off
    off_calls = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.living_trv"
        and c[0][1] == "set_hvac_mode"
        and c[0][2].get("hvac_mode") == "off"
    ]
    assert len(off_calls) == 0
    # set_temperature called with heat target
    temp_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.living_trv" and c[0][1] == "set_temperature"]
    assert len(temp_calls) == 1
    assert temp_calls[0][0][2]["temperature"] == 21.0


# ---------------------------------------------------------------------------
# async_idle_device — unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_idle_device_off():
    """Device with idle_action='off' delegates to async_turn_off_climate."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"]}
    hass.states.get = MagicMock(return_value=state)

    devices = [{"entity_id": "climate.ac1", "type": "ac", "role": "auto", "idle_action": "off", "idle_fan_mode": ""}]
    await async_idle_device(hass, "climate.ac1", devices, area_id="living_room")

    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.ac1", "hvac_mode": "off"},
        blocking=True,
    )


@pytest.mark.asyncio
async def test_async_idle_device_fan_only():
    """Device with idle_action='fan_only' and supported fan_only mode sets fan_only + fan_mode."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {"hvac_modes": ["cool", "fan_only", "off"], "fan_modes": ["low", "medium", "high"]}
    hass.states.get = MagicMock(return_value=state)

    devices = [
        {"entity_id": "climate.ac1", "type": "ac", "role": "auto", "idle_action": "fan_only", "idle_fan_mode": "low"}
    ]
    await async_idle_device(hass, "climate.ac1", devices, area_id="living_room")

    calls = hass.services.async_call.call_args_list
    assert len(calls) == 2
    assert calls[0][0] == ("climate", "set_hvac_mode", {"entity_id": "climate.ac1", "hvac_mode": "fan_only"})
    assert calls[1][0] == ("climate", "set_fan_mode", {"entity_id": "climate.ac1", "fan_mode": "low"})


@pytest.mark.asyncio
async def test_async_idle_device_fan_only_unsupported():
    """Device with idle_action='fan_only' but fan_only NOT in hvac_modes falls back to off."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {"hvac_modes": ["cool", "off"], "fan_modes": ["low"]}
    hass.states.get = MagicMock(return_value=state)

    devices = [
        {"entity_id": "climate.ac1", "type": "ac", "role": "auto", "idle_action": "fan_only", "idle_fan_mode": "low"}
    ]
    await async_idle_device(hass, "climate.ac1", devices, area_id="living_room")

    # Falls back to async_turn_off_climate which calls set_hvac_mode off
    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.ac1", "hvac_mode": "off"},
        blocking=True,
    )


@pytest.mark.asyncio
async def test_async_idle_device_fan_only_redundancy():
    """Device already in fan_only with correct fan_mode skips service calls."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "fan_only"
    state.attributes = {"hvac_modes": ["cool", "fan_only", "off"], "fan_modes": ["low", "medium"], "fan_mode": "low"}
    hass.states.get = MagicMock(return_value=state)

    devices = [
        {"entity_id": "climate.ac1", "type": "ac", "role": "auto", "idle_action": "fan_only", "idle_fan_mode": "low"}
    ]
    await async_idle_device(hass, "climate.ac1", devices, area_id="living_room")

    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_async_idle_device_fan_only_custom_fan_mode():
    """Custom idle_fan_mode='medium' calls set_fan_mode('medium')."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {"hvac_modes": ["cool", "fan_only", "off"], "fan_modes": ["low", "medium", "high"]}
    hass.states.get = MagicMock(return_value=state)

    devices = [
        {
            "entity_id": "climate.ac1",
            "type": "ac",
            "role": "auto",
            "idle_action": "fan_only",
            "idle_fan_mode": "medium",
        }
    ]
    await async_idle_device(hass, "climate.ac1", devices, area_id="living_room")

    calls = hass.services.async_call.call_args_list
    fan_mode_calls = [c for c in calls if c[0][1] == "set_fan_mode"]
    assert len(fan_mode_calls) == 1
    assert fan_mode_calls[0][0][2]["fan_mode"] == "medium"


@pytest.mark.asyncio
async def test_async_idle_device_no_device_config():
    """Entity not found in devices[] defaults to 'off' behavior."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"]}
    hass.states.get = MagicMock(return_value=state)

    # Empty devices list, entity not found
    await async_idle_device(hass, "climate.unknown", [], area_id="living_room")

    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.unknown", "hvac_mode": "off"},
        blocking=True,
    )


@pytest.mark.asyncio
async def test_async_idle_device_fan_mode_not_in_fan_modes():
    """idle_fan_mode='turbo' not in fan_modes: hvac_mode=fan_only IS set, fan_mode call is SKIPPED."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {"hvac_modes": ["cool", "fan_only", "off"], "fan_modes": ["low", "medium", "high"]}
    hass.states.get = MagicMock(return_value=state)

    devices = [
        {
            "entity_id": "climate.ac1",
            "type": "ac",
            "role": "auto",
            "idle_action": "fan_only",
            "idle_fan_mode": "turbo",
        }
    ]
    await async_idle_device(hass, "climate.ac1", devices, area_id="living_room")

    calls = hass.services.async_call.call_args_list
    # set_hvac_mode(fan_only) should be called
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    assert len(hvac_calls) == 1
    assert hvac_calls[0][0][2]["hvac_mode"] == "fan_only"
    # set_fan_mode should NOT be called (turbo not supported)
    fan_calls = [c for c in calls if c[0][1] == "set_fan_mode"]
    assert len(fan_calls) == 0


# ---------------------------------------------------------------------------
# async_apply integration tests with fan_only idle_action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mpc_apply_idle_respects_fan_only():
    """async_apply(MODE_IDLE) with AC device that has idle_action='fan_only' uses fan_only."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {
        "hvac_modes": ["cool", "fan_only", "off"],
        "fan_modes": ["low", "medium", "high"],
        "temperature": 23.0,
    }
    hass.states.get = MagicMock(return_value=state)

    room = make_room(thermostats=[], acs=["climate.ac1"])
    # Override devices with fan_only config
    room["devices"] = [
        {
            "entity_id": "climate.ac1",
            "type": "ac",
            "role": "auto",
            "heating_system_type": "",
            "idle_action": "fan_only",
            "idle_fan_mode": "low",
        }
    ]
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("idle", 23.0)

    calls = hass.services.async_call.call_args_list
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    assert any(c[0][2].get("hvac_mode") == "fan_only" for c in hvac_calls)
    fan_calls = [c for c in calls if c[0][1] == "set_fan_mode"]
    assert any(c[0][2].get("fan_mode") == "low" for c in fan_calls)
    # No "off" calls
    off_calls = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2].get("hvac_mode") == "off"]
    assert len(off_calls) == 0


@pytest.mark.asyncio
async def test_mpc_apply_idle_forced_on_overrides_fan_only():
    """Device in compressor_forced_on during IDLE runs forced_on logic, NOT fan_only."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {
        "hvac_modes": ["cool", "fan_only", "off"],
        "fan_modes": ["low"],
        "temperature": 25.0,
    }
    hass.states.get = MagicMock(return_value=state)

    room = make_room(thermostats=[], acs=["climate.ac1"])
    room["devices"] = [
        {
            "entity_id": "climate.ac1",
            "type": "ac",
            "role": "auto",
            "heating_system_type": "",
            "idle_action": "fan_only",
            "idle_fan_mode": "low",
        }
    ]
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("idle", 23.0, compressor_forced_on={"climate.ac1"})

    calls = hass.services.async_call.call_args_list
    # forced_on sets temperature, does NOT switch to fan_only
    fan_only_calls = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2].get("hvac_mode") == "fan_only"]
    assert len(fan_only_calls) == 0
    # Verify forced_on DID call set_temperature (positive assertion)
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert len(temp_calls) >= 1


@pytest.mark.asyncio
async def test_mpc_apply_heating_forced_off_fan_only():
    """AC with idle_action='fan_only' in compressor_forced_off during HEATING uses fan_only."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {
        "hvac_modes": ["heat", "cool", "fan_only", "off"],
        "fan_modes": ["low", "medium"],
        "temperature": 20.0,
    }
    hass.states.get = MagicMock(return_value=state)

    room = make_room(thermostats=[], acs=["climate.ac1"])
    room["devices"] = [
        {
            "entity_id": "climate.ac1",
            "type": "ac",
            "role": "auto",
            "heating_system_type": "",
            "idle_action": "fan_only",
            "idle_fan_mode": "low",
        }
    ]
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0, compressor_forced_off={"climate.ac1"})

    calls = hass.services.async_call.call_args_list
    # Should use fan_only instead of off
    fan_only_calls = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2].get("hvac_mode") == "fan_only"]
    assert len(fan_only_calls) >= 1
    off_calls = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2].get("hvac_mode") == "off"]
    assert len(off_calls) == 0


@pytest.mark.asyncio
async def test_mpc_apply_call_hvac_off_uses_idle_action():
    """Verify _call('set_hvac_mode', hvac_mode='off') delegates to async_idle_device."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {
        "hvac_modes": ["cool", "fan_only", "off"],
        "fan_modes": ["low"],
        "temperature": 23.0,
    }
    hass.states.get = MagicMock(return_value=state)

    # Room with TRV + AC. During cooling, TRVs get "off" via _call.
    # If the TRV has idle_action=fan_only, it should get fan_only.
    room = make_room(thermostats=["climate.trv1"], acs=["climate.ac1"])
    room["devices"] = [
        {
            "entity_id": "climate.trv1",
            "type": "trv",
            "role": "auto",
            "heating_system_type": "",
            "idle_action": "fan_only",
            "idle_fan_mode": "low",
        },
        {
            "entity_id": "climate.ac1",
            "type": "ac",
            "role": "auto",
            "heating_system_type": "",
            "idle_action": "off",
            "idle_fan_mode": "",
        },
    ]
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    # During cooling, TRVs are set to "off" via _call -> async_idle_device
    await ctrl.async_apply("cooling", 23.0)

    calls = hass.services.async_call.call_args_list
    # TRV should get fan_only (not off) via the _call delegation to async_idle_device
    trv_fan_only = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.trv1"
        and c[0][1] == "set_hvac_mode"
        and c[0][2].get("hvac_mode") == "fan_only"
    ]
    assert len(trv_fan_only) >= 1
    trv_off = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.trv1"
        and c[0][1] == "set_hvac_mode"
        and c[0][2].get("hvac_mode") == "off"
    ]
    assert len(trv_off) == 0
