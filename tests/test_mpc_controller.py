"""Tests for the MPC controller."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock

from custom_components.roommind.const import TargetTemps
from custom_components.roommind.mpc_controller import (
    MPCController,
    async_turn_off_climate,
    check_acs_can_heat,
    resolve_hvac_mode,
    MODE_COOLING,
    MODE_HEATING,
    MODE_IDLE,
)
from custom_components.roommind.mpc_optimizer import MPCPlan
from custom_components.roommind.thermal_model import RoomModelManager, RCModel


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
    return room


@pytest.mark.asyncio
async def test_mpc_evaluate_heats_when_cold():
    """Cold room triggers heating."""
    hass = build_hass()
    room = make_room()
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=False,
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=10.0, settings={"outdoor_cooling_min": 16.0},
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=30.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
    )
    mode, pf = await ctrl.async_evaluate(current_temp=17.0, target_temp=21.0)
    assert mode == "heating"  # bang-bang also heats when cold
    assert pf == 1.0  # bang-bang: full power

    # Just below threshold — MPC path
    model_mgr.get_prediction_std = MagicMock(return_value=0.49)
    ctrl2 = MPCController(
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
    )
    mode, pf = await ctrl.async_evaluate(current_temp=20.9, target_temp=21.0)
    assert mode == "idle"  # bang-bang: within hysteresis
    assert pf == 0.0

    # Enough idle but too few heating samples → bang-bang
    model_mgr.get_mode_counts = MagicMock(return_value=(100, 10, 0))
    ctrl2 = MPCController(
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
    )
    mode2, pf2 = await ctrl2.async_evaluate(current_temp=20.9, target_temp=21.0)
    assert mode2 == "idle"  # still bang-bang
    assert pf2 == 0.0

    # Enough data → MPC (would heat at 20.9 because optimizer predicts drop)
    model_mgr.get_mode_counts = MagicMock(return_value=(100, 30, 0))
    ctrl3 = MPCController(
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
            hass, room, model_manager=model_mgr,
            outdoor_temp=5.0, settings={}, has_external_sensor=True,
        )

    def test_small_delta_returns_minimum_horizon(self):
        """Small temp delta should still produce at least MIN_HORIZON_HOURS worth of blocks."""
        from custom_components.roommind.mpc_controller import MIN_HORIZON_HOURS, PLAN_DT_MINUTES
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
        from custom_components.roommind.mpc_controller import MIN_HORIZON_HOURS, PLAN_DT_MINUTES
        from custom_components.roommind.thermal_model import RCModel
        ctrl = self._make_ctrl()
        model = RCModel(C=2.0, U=50.0, Q_heat=0.0, Q_cool=0.0)
        blocks = ctrl._compute_horizon_blocks(model, 15.0, 21.0)
        assert blocks == int(MIN_HORIZON_HOURS * 60 / PLAN_DT_MINUTES)

    def test_high_power_model_shorter_horizon(self):
        """High HVAC power should yield fewer blocks (faster to reach target)."""
        from custom_components.roommind.thermal_model import RCModel
        ctrl = self._make_ctrl()
        model_low = RCModel(C=2.0, U=50.0, Q_heat=400.0, Q_cool=400.0)
        model_high = RCModel(C=2.0, U=50.0, Q_heat=4000.0, Q_cool=4000.0)
        blocks_low = ctrl._compute_horizon_blocks(model_low, 15.0, 21.0)
        blocks_high = ctrl._compute_horizon_blocks(model_high, 15.0, 21.0)
        assert blocks_high <= blocks_low

    def test_high_thermal_mass_longer_horizon(self):
        """High thermal capacitance should yield more blocks (slower temperature change)."""
        from custom_components.roommind.thermal_model import RCModel
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
            hass, room, model_manager=model_mgr,
            outdoor_temp=8.0, settings={}, has_external_sensor=True,
        )
        series = ctrl._build_outdoor_series(10)
        assert series == [8.0] * 10

    def test_fallback_when_outdoor_temp_none_no_forecast(self):
        """Without forecast and outdoor_temp=None, uses DEFAULT_OUTDOOR_TEMP_FALLBACK."""
        from custom_components.roommind.mpc_controller import DEFAULT_OUTDOOR_TEMP_FALLBACK
        hass = build_hass()
        room = make_room()
        model_mgr = RoomModelManager()
        ctrl = MPCController(
            hass, room, model_manager=model_mgr,
            outdoor_temp=None, settings={}, has_external_sensor=True,
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
            hass, room, model_manager=model_mgr,
            outdoor_temp=8.0, outdoor_forecast=forecast,
            settings={}, has_external_sensor=True,
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
            hass, room, model_manager=model_mgr,
            outdoor_temp=8.0, outdoor_forecast=forecast,
            settings={}, has_external_sensor=True,
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
            hass, room, model_manager=model_mgr,
            outdoor_temp=10.0, outdoor_forecast=forecast,
            settings={}, has_external_sensor=True,
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
            hass, room, model_manager=model_mgr,
            outdoor_temp=8.0, outdoor_forecast=forecast,
            settings={}, has_external_sensor=True,
        )
        series = ctrl._build_outdoor_series(3)
        assert series == [5.0, 8.0, 7.0]

    def test_forecast_missing_temp_key_and_outdoor_none_uses_fallback(self):
        """Forecast entry without temp + outdoor_temp=None uses DEFAULT_OUTDOOR_TEMP_FALLBACK."""
        from custom_components.roommind.mpc_controller import DEFAULT_OUTDOOR_TEMP_FALLBACK
        hass = build_hass()
        room = make_room()
        model_mgr = RoomModelManager()
        forecast = [
            {"condition": "cloudy"},  # no temperature key
        ]
        ctrl = MPCController(
            hass, room, model_manager=model_mgr,
            outdoor_temp=None, outdoor_forecast=forecast,
            settings={}, has_external_sensor=True,
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
    )
    mode, pf = await ctrl.async_evaluate(current_temp=20.7, target_temp=21.0)
    if mode == "heating":
        assert pf < 1.0  # near target → less than full power


@pytest.mark.asyncio
async def test_proportional_trv_setpoint():
    """TRV setpoint is proportional between current_temp and 30°C."""
    from custom_components.roommind.mpc_controller import HEATING_BOOST_TARGET
    hass = build_hass()
    room = make_room()
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
    )
    # Large error in bang-bang mode (low confidence)
    mode, pf = await ctrl.async_evaluate(current_temp=17.0, target_temp=21.0)
    assert mode == "heating"
    assert pf == 1.0  # bang-bang: always full power


@pytest.mark.asyncio
async def test_async_apply_backward_compat():
    """Calling async_apply without power_fraction uses default 1.0 → 30°C boost."""
    from custom_components.roommind.mpc_controller import HEATING_BOOST_TARGET
    hass = build_hass()
    room = make_room()
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
    from custom_components.roommind.mpc_controller import HEATING_BOOST_TARGET

    hass = build_hass()
    hass.config.units.temperature_unit = UnitOfTemperature.FAHRENHEIT

    room = make_room()
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=30.0, settings={}, has_external_sensor=True,
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
        from custom_components.roommind.mpc_controller import get_can_heat_cool
        room = make_room(climate_mode="auto", acs=["climate.ac"])
        can_heat, can_cool = get_can_heat_cool(room)
        assert can_heat is True
        assert can_cool is True

    def test_heat_only_mode(self):
        """heat_only mode → (True, False) regardless of ACs."""
        from custom_components.roommind.mpc_controller import get_can_heat_cool
        room = make_room(climate_mode="heat_only", acs=["climate.ac"])
        can_heat, can_cool = get_can_heat_cool(room)
        assert can_heat is True
        assert can_cool is False

    def test_cool_only_mode(self):
        """cool_only mode → (False, True) regardless of thermostats."""
        from custom_components.roommind.mpc_controller import get_can_heat_cool
        room = make_room(climate_mode="cool_only", acs=["climate.ac"])
        can_heat, can_cool = get_can_heat_cool(room)
        assert can_heat is False
        assert can_cool is True

    def test_no_thermostats_heat_only(self):
        """heat_only but no thermostats → (False, False)."""
        from custom_components.roommind.mpc_controller import get_can_heat_cool
        room = make_room(climate_mode="heat_only", thermostats=[], acs=[])
        can_heat, can_cool = get_can_heat_cool(room)
        assert can_heat is False
        assert can_cool is False

    def test_no_acs_cool_only(self):
        """cool_only but no ACs → (False, False)."""
        from custom_components.roommind.mpc_controller import get_can_heat_cool
        room = make_room(climate_mode="cool_only", thermostats=[], acs=[])
        can_heat, can_cool = get_can_heat_cool(room)
        assert can_heat is False
        assert can_cool is False

    def test_outdoor_temp_none_no_gating(self):
        """outdoor_temp=None → no gating applied."""
        from custom_components.roommind.mpc_controller import get_can_heat_cool
        room = make_room(acs=["climate.ac"])
        can_heat, can_cool = get_can_heat_cool(room, outdoor_temp=None)
        assert can_heat is True
        assert can_cool is True

    def test_outdoor_above_heating_max_blocks_heat(self):
        """Outdoor temp above outdoor_heating_max → can_heat=False."""
        from custom_components.roommind.mpc_controller import get_can_heat_cool
        room = make_room(acs=["climate.ac"])
        can_heat, can_cool = get_can_heat_cool(
            room, outdoor_temp=25.0, outdoor_heating_max=22.0,
        )
        assert can_heat is False
        assert can_cool is True

    def test_outdoor_below_cooling_min_blocks_cool(self):
        """Outdoor temp below outdoor_cooling_min → can_cool=False."""
        from custom_components.roommind.mpc_controller import get_can_heat_cool
        room = make_room(acs=["climate.ac"])
        can_heat, can_cool = get_can_heat_cool(
            room, outdoor_temp=10.0, outdoor_cooling_min=16.0,
        )
        assert can_heat is True
        assert can_cool is False

    def test_outdoor_at_threshold_boundary(self):
        """Outdoor temp equal to heating_max → not blocked (>= not used, > is)."""
        from custom_components.roommind.mpc_controller import get_can_heat_cool
        room = make_room(acs=["climate.ac"])
        # At exactly outdoor_heating_max=22.0 → 22 > 22 is False, so still allowed
        can_heat, can_cool = get_can_heat_cool(
            room, outdoor_temp=22.0, outdoor_heating_max=22.0,
        )
        assert can_heat is True
        # At exactly outdoor_cooling_min=16.0 → 16 < 16 is False, so still allowed
        can_heat2, can_cool2 = get_can_heat_cool(
            room, outdoor_temp=16.0, outdoor_cooling_min=16.0,
        )
        assert can_cool2 is True

    def test_auto_no_devices_returns_false_false(self):
        """auto mode but no devices → (False, False)."""
        from custom_components.roommind.mpc_controller import get_can_heat_cool
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
        from custom_components.roommind.mpc_controller import is_mpc_active
        model_mgr = RoomModelManager()
        result = is_mpc_active(model_mgr, "unknown_room", True, False, 20.0, 10.0)
        assert result is False

    def test_prediction_std_too_high(self):
        """Returns False when prediction_std >= MPC_MAX_PREDICTION_STD."""
        from custom_components.roommind.mpc_controller import is_mpc_active
        model_mgr = RoomModelManager()
        model_mgr.update("living_room", 20.0, 10.0, "idle", 5.0)
        model_mgr.get_prediction_std = MagicMock(return_value=0.6)
        model_mgr.get_mode_counts = MagicMock(return_value=(100, 30, 30))
        result = is_mpc_active(model_mgr, "living_room", True, False, 20.0, 10.0)
        assert result is False

    def test_insufficient_idle_samples(self):
        """Returns False when idle samples below MIN_IDLE_UPDATES."""
        from custom_components.roommind.mpc_controller import is_mpc_active
        model_mgr = RoomModelManager()
        model_mgr.update("living_room", 20.0, 10.0, "idle", 5.0)
        model_mgr.get_prediction_std = MagicMock(return_value=0.1)
        model_mgr.get_mode_counts = MagicMock(return_value=(30, 30, 30))  # idle < 60
        result = is_mpc_active(model_mgr, "living_room", True, False, 20.0, 10.0)
        assert result is False

    def test_insufficient_heating_samples(self):
        """Returns False when can_heat but heating samples below MIN_ACTIVE_UPDATES."""
        from custom_components.roommind.mpc_controller import is_mpc_active
        model_mgr = RoomModelManager()
        model_mgr.update("living_room", 20.0, 10.0, "idle", 5.0)
        model_mgr.get_prediction_std = MagicMock(return_value=0.1)
        model_mgr.get_mode_counts = MagicMock(return_value=(100, 10, 0))  # heating < 20
        result = is_mpc_active(model_mgr, "living_room", True, False, 20.0, 10.0)
        assert result is False

    def test_insufficient_cooling_samples(self):
        """Returns False when can_cool but cooling samples below MIN_ACTIVE_UPDATES."""
        from custom_components.roommind.mpc_controller import is_mpc_active
        model_mgr = RoomModelManager()
        model_mgr.update("living_room", 20.0, 10.0, "idle", 5.0)
        model_mgr.get_prediction_std = MagicMock(return_value=0.1)
        model_mgr.get_mode_counts = MagicMock(return_value=(100, 0, 10))  # cooling < 20
        result = is_mpc_active(model_mgr, "living_room", False, True, 20.0, 10.0)
        assert result is False

    def test_all_conditions_met_returns_true(self):
        """Returns True when all conditions satisfied."""
        from custom_components.roommind.mpc_controller import is_mpc_active
        model_mgr = RoomModelManager()
        model_mgr.update("living_room", 20.0, 10.0, "idle", 5.0)
        model_mgr.get_prediction_std = MagicMock(return_value=0.1)
        model_mgr.get_mode_counts = MagicMock(return_value=(100, 30, 0))
        result = is_mpc_active(model_mgr, "living_room", True, False, 20.0, 10.0)
        assert result is True

    def test_heat_and_cool_both_need_samples(self):
        """When both can_heat and can_cool, both need MIN_ACTIVE_UPDATES."""
        from custom_components.roommind.mpc_controller import is_mpc_active
        model_mgr = RoomModelManager()
        model_mgr.update("living_room", 20.0, 10.0, "idle", 5.0)
        model_mgr.get_prediction_std = MagicMock(return_value=0.1)
        # Enough heating but not enough cooling
        model_mgr.get_mode_counts = MagicMock(return_value=(100, 30, 10))
        result = is_mpc_active(model_mgr, "living_room", True, True, 20.0, 10.0)
        assert result is False

    def test_no_heat_no_cool_only_idle_needed(self):
        """When neither can_heat nor can_cool, only idle check matters."""
        from custom_components.roommind.mpc_controller import is_mpc_active
        model_mgr = RoomModelManager()
        model_mgr.update("living_room", 20.0, 10.0, "idle", 5.0)
        model_mgr.get_prediction_std = MagicMock(return_value=0.1)
        model_mgr.get_mode_counts = MagicMock(return_value=(100, 0, 0))
        result = is_mpc_active(model_mgr, "living_room", False, False, 20.0, 10.0)
        assert result is True

    def test_prediction_std_at_threshold(self):
        """pred_std exactly at MPC_MAX_PREDICTION_STD (0.5) → False."""
        from custom_components.roommind.mpc_controller import is_mpc_active, MPC_MAX_PREDICTION_STD
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
    )
    # Heating with full power tries to set 30°C (HEATING_BOOST_TARGET)
    await ctrl.async_apply("heating", 21.0, power_fraction=1.0, current_temp=18.0)

    set_temp_calls = [
        c for c in hass.services.async_call.call_args_list
        if c[0][1] == "set_temperature"
    ]
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=35.0, settings={}, has_external_sensor=True,
    )
    # Cooling with target below device min
    await ctrl.async_apply("cooling", 8.0)

    set_temp_calls = [
        c for c in hass.services.async_call.call_args_list
        if c[0][1] == "set_temperature"
    ]
    assert set_temp_calls
    temp_arg = set_temp_calls[0][0][2]["temperature"]
    assert temp_arg == 10.0  # clamped to device min


# ---------------------------------------------------------------------------
# async_turn_off_climate — unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_off_climate_normal_device():
    """Device with 'off' in hvac_modes uses standard set_hvac_mode off."""
    from custom_components.roommind.mpc_controller import async_turn_off_climate

    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    hass.services.async_call.assert_called_once_with(
        "climate", "set_hvac_mode",
        {"entity_id": "climate.trv", "hvac_mode": "off"},
        blocking=True,
    )


@pytest.mark.asyncio
async def test_turn_off_climate_heat_only_uses_min_temp():
    """Heat-only device (no 'off' mode) gets set_temperature with min_temp."""
    from custom_components.roommind.mpc_controller import async_turn_off_climate

    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat"], "min_temp": 5.0, "temperature": 21.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    hass.services.async_call.assert_called_once_with(
        "climate", "set_temperature",
        {"entity_id": "climate.trv", "temperature": 5.0},
        blocking=True,
    )


@pytest.mark.asyncio
async def test_turn_off_climate_cool_only_uses_max_temp():
    """Cool-only device without 'off' uses max_temp as fallback."""
    from custom_components.roommind.mpc_controller import async_turn_off_climate

    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {"hvac_modes": ["cool"], "min_temp": 16.0, "max_temp": 30.0, "temperature": 20.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.ac")
    hass.services.async_call.assert_called_once_with(
        "climate", "set_temperature",
        {"entity_id": "climate.ac", "temperature": 30.0},
        blocking=True,
    )


@pytest.mark.asyncio
async def test_turn_off_climate_already_off_skipped():
    """Device already in 'off' state: call is skipped."""
    from custom_components.roommind.mpc_controller import async_turn_off_climate

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
    from custom_components.roommind.mpc_controller import async_turn_off_climate

    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": []}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    hass.services.async_call.assert_called_once_with(
        "climate", "set_hvac_mode",
        {"entity_id": "climate.trv", "hvac_mode": "off"},
        blocking=True,
    )


@pytest.mark.asyncio
async def test_turn_off_climate_no_modes_attr_uses_off():
    """No hvac_modes attribute at all: assume 'off' is supported (backward compat)."""
    from custom_components.roommind.mpc_controller import async_turn_off_climate

    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"min_temp": 5.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    hass.services.async_call.assert_called_once_with(
        "climate", "set_hvac_mode",
        {"entity_id": "climate.trv", "hvac_mode": "off"},
        blocking=True,
    )


@pytest.mark.asyncio
async def test_turn_off_climate_heat_only_no_min_temp():
    """Heat-only device without min_temp: logs warning, no crash."""
    from custom_components.roommind.mpc_controller import async_turn_off_climate

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
    from custom_components.roommind.mpc_controller import async_turn_off_climate

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
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=model_mgr,
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
        from custom_components.roommind.mpc_controller import get_can_heat_cool
        room = make_room(thermostats=[], acs=["climate.hp"])
        can_heat, can_cool = get_can_heat_cool(room, acs_can_heat=True)
        assert can_heat is True
        assert can_cool is True

    def test_acs_can_heat_cool_only_mode(self):
        """acs_can_heat=True but cool_only mode → can_heat still False."""
        from custom_components.roommind.mpc_controller import get_can_heat_cool
        room = make_room(climate_mode="cool_only", thermostats=[], acs=["climate.hp"])
        can_heat, can_cool = get_can_heat_cool(room, acs_can_heat=True)
        assert can_heat is False
        assert can_cool is True

    def test_acs_can_heat_with_outdoor_gating(self):
        """acs_can_heat=True but outdoor above heating max → can_heat gated."""
        from custom_components.roommind.mpc_controller import get_can_heat_cool
        room = make_room(thermostats=[], acs=["climate.hp"])
        can_heat, can_cool = get_can_heat_cool(
            room, outdoor_temp=25.0, outdoor_heating_max=22.0, acs_can_heat=True,
        )
        assert can_heat is False

    def test_default_acs_can_heat_false(self):
        """Default acs_can_heat=False preserves old behavior."""
        from custom_components.roommind.mpc_controller import get_can_heat_cool
        room = make_room(thermostats=[], acs=["climate.hp"])
        can_heat, can_cool = get_can_heat_cool(room)
        assert can_heat is False
        assert can_cool is True


# ---------------------------------------------------------------------------
# async_apply: AC heating behavior
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_apply_heating_ac_with_heat_gets_target():
    """Heating: AC with 'heat' mode gets actual target, not 30°C boost."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "temperature": 20.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.hp"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0, power_fraction=0.5, current_temp=18.0)

    calls = hass.services.async_call.call_args_list
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    # AC should get heat mode
    assert any(c[0][2].get("hvac_mode") == "heat" for c in hvac_calls)
    # AC should get actual target (21°C), not 30°C
    assert any(c[0][2]["temperature"] == 21.0 for c in temp_calls)


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
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0)

    calls = hass.services.async_call.call_args_list
    # AC should be turned off (via async_turn_off_climate)
    ac_off_calls = [
        c for c in calls
        if c[0][2].get("entity_id") == "climate.ac"
        and c[0][1] == "set_hvac_mode"
        and c[0][2].get("hvac_mode") == "off"
    ]
    assert len(ac_off_calls) >= 1


@pytest.mark.asyncio
async def test_apply_heating_trv_still_gets_boost():
    """Heating: TRV in thermostats[] still gets proportional 30°C boost."""
    from custom_components.roommind.mpc_controller import HEATING_BOOST_TARGET
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 21.0, "min_temp": 5.0, "max_temp": 30.0}
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()  # thermostats=["climate.living_trv"]
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=False,
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
    )
    mode, pf = await ctrl.async_evaluate(current_temp=17.0, target_temp=21.0)
    assert mode == "heating"


@pytest.mark.asyncio
async def test_apply_heating_mixed_trv_and_heat_pump():
    """Heating with TRV + heat-capable AC: TRV gets boost, AC gets actual target."""
    from custom_components.roommind.mpc_controller import HEATING_BOOST_TARGET
    hass = build_hass()

    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 21.0, "min_temp": 5.0, "max_temp": 30.0}

    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "temperature": 20.0, "min_temp": 16.0, "max_temp": 30.0}

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
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0, power_fraction=1.0, current_temp=18.0)

    calls = hass.services.async_call.call_args_list
    # TRV should get boost target (30°C)
    trv_temp_calls = [
        c for c in calls
        if c[0][1] == "set_temperature" and c[0][2].get("entity_id") == "climate.living_trv"
    ]
    assert trv_temp_calls
    assert trv_temp_calls[0][0][2]["temperature"] == HEATING_BOOST_TARGET

    # AC should get actual target (21°C)
    ac_temp_calls = [
        c for c in calls
        if c[0][1] == "set_temperature" and c[0][2].get("entity_id") == "climate.hp"
    ]
    assert ac_temp_calls
    assert ac_temp_calls[0][0][2]["temperature"] == 21.0

    # AC should be in heat mode, not off
    ac_hvac_calls = [
        c for c in calls
        if c[0][1] == "set_hvac_mode" and c[0][2].get("entity_id") == "climate.hp"
    ]
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=False,
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
        hass, room, model_manager=mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=mgr,
        outdoor_temp=30.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=mgr,
        outdoor_temp=30.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=mgr,
        outdoor_temp=30.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
    )
    assert ctrl._evaluate_bangbang(None, TargetTemps(heat=21.0, cool=24.0)) == MODE_IDLE
    assert ctrl._evaluate_bangbang(20.0, TargetTemps(heat=None, cool=None)) == MODE_IDLE


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
        hass, room, model_manager=mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
    )
    series = ctrl._build_outdoor_series(10)
    assert series == [5.0] * 10


def test_outdoor_series_none_outdoor_temp():
    """Without outdoor temp and no forecast, uses fallback."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass, room, model_manager=mgr,
        outdoor_temp=None, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=mgr,
        outdoor_temp=30.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=False,
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
        hass, room, model_manager=mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=False,
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
        hass, room, model_manager=mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=mgr,
        outdoor_temp=30.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=mgr,
        outdoor_temp=30.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=False,
    )
    assert ctrl._evaluate_managed_mode(TargetTemps(heat=None, cool=None)) == MODE_IDLE


@pytest.mark.asyncio
async def test_managed_mode_cool_only_can_cool():
    """Cool-only mode returns cooling when cooling is allowed."""
    hass = build_hass()
    room = make_room(acs=["climate.ac1"], climate_mode="cool_only")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass, room, model_manager=mgr,
        outdoor_temp=30.0, settings={}, has_external_sensor=False,
    )
    assert ctrl._evaluate_managed_mode(TargetTemps(heat=21.0, cool=23.0)) == MODE_COOLING


@pytest.mark.asyncio
async def test_managed_mode_cool_only_gated():
    """Cool-only mode returns idle when outdoor temp too low."""
    hass = build_hass()
    room = make_room(acs=["climate.ac1"], climate_mode="cool_only")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass, room, model_manager=mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=False,
    )
    assert ctrl._evaluate_managed_mode(TargetTemps(heat=21.0, cool=23.0)) == MODE_IDLE


@pytest.mark.asyncio
async def test_managed_mode_heat_only_can_heat():
    """Heat-only mode returns heating when heating is allowed."""
    hass = build_hass()
    room = make_room(climate_mode="heat_only")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass, room, model_manager=mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=False,
    )
    assert ctrl._evaluate_managed_mode(TargetTemps(heat=21.0, cool=24.0)) == MODE_HEATING


@pytest.mark.asyncio
async def test_managed_mode_heat_only_gated():
    """Heat-only mode returns idle when outdoor temp too high."""
    hass = build_hass()
    room = make_room(climate_mode="heat_only")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass, room, model_manager=mgr,
        outdoor_temp=30.0, settings={}, has_external_sensor=False,
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
        hass, room, model_manager=mgr,
        outdoor_temp=18.0, settings={},  # between cooling_min(16) and heating_max(22)
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
        hass, room, model_manager=mgr,
        outdoor_temp=30.0, settings={}, has_external_sensor=False,
    )
    assert ctrl._evaluate_managed_mode(TargetTemps(heat=21.0, cool=23.0)) == MODE_COOLING


@pytest.mark.asyncio
async def test_managed_mode_auto_neither():
    """Auto mode with neither heat nor cool returns idle."""
    hass = build_hass()
    room = make_room(thermostats=[], acs=[], climate_mode="auto")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass, room, model_manager=mgr,
        outdoor_temp=30.0, settings={}, has_external_sensor=False,
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
        hass, room, model_manager=mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
    )
    # Mock optimizer to return HEATING so the safety guard is actually tested
    fake_plan = MPCPlan(
        actions=[MODE_HEATING] * 6,
        temperatures=[22.0] * 7,
        power_fractions=[0.8] * 6,
    )
    monkeypatch.setattr(
        "custom_components.roommind.mpc_controller.MPCOptimizer.optimize",
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
        hass, room, model_manager=mgr,
        outdoor_temp=30.0, settings={}, has_external_sensor=True,
    )
    # Mock optimizer to return COOLING so the safety guard is tested
    fake_plan = MPCPlan(
        actions=[MODE_COOLING] * 6,
        temperatures=[22.0] * 7,
        power_fractions=[0.8] * 6,
    )
    monkeypatch.setattr(
        "custom_components.roommind.mpc_controller.MPCOptimizer.optimize",
        lambda *a, **kw: fake_plan,
    )
    # current_temp=22 <= target=23 → safety guard should override to idle
    mode, pf = ctrl._evaluate_mpc(22.0, TargetTemps(heat=21.0, cool=23.0))
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
        hass, room, model_manager=mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
        cloud_series=[50.0, 80.0],
        latitude=48.0, longitude=11.0,
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
        hass, room, model_manager=mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
        cloud_series=[50.0],  # only 1 hour = 12 blocks
        latitude=48.0, longitude=11.0,
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
        hass, room, model_manager=mgr,
        outdoor_temp=30.0, settings={}, has_external_sensor=False,
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
        "hvac_modes": ["off", "auto"], "temperature": None,
        "min_temp": 5.0, "max_temp": 30.0,
    }
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass, room, model_manager=mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        "hvac_modes": ["off", "auto"], "temperature": None,
        "min_temp": 5.0, "max_temp": 30.0,
    }
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room(temperature_sensor="")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass, room, model_manager=mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=False,
    )

    await ctrl.async_apply("heating", target_temp=21.0)
    calls = hass.services.async_call.call_args_list
    hvac_calls = [
        c for c in calls
        if c[0][1] == "set_hvac_mode" and c[0][2].get("entity_id") == "climate.living_trv"
    ]
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
        hass, room, model_manager=mgr,
        outdoor_temp=35.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=mgr,
        outdoor_temp=30.0, settings={}, has_external_sensor=False,
    )

    await ctrl.async_apply("cooling", target_temp=23.0)
    calls = hass.services.async_call.call_args_list
    hvac_calls = [
        c for c in calls
        if c[0][1] == "set_hvac_mode" and c[0][2].get("entity_id") == "climate.ac1"
    ]
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
        hass, room, model_manager=mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
    )

    await ctrl.async_apply("heating", 21.0)
    calls = hass.services.async_call.call_args_list
    ac_calls = [
        c for c in calls
        if c[0][2].get("entity_id") == "climate.ac1" and c[0][1] == "set_hvac_mode"
    ]
    assert any(c[0][2]["hvac_mode"] == "auto" for c in ac_calls)


def test_acs_can_heat_auto_mode():
    """AC with only 'off'+'auto' hvac_modes is recognized as heat-capable."""
    hass = build_hass()
    state = MagicMock()
    state.attributes = {"hvac_modes": ["off", "auto"]}
    hass.states.get = MagicMock(return_value=state)
    assert check_acs_can_heat(hass, {"acs": ["climate.ac1"]}) is True


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
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=30.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=30.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=20.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=30.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=20.0, settings={}, has_external_sensor=True,
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
        hass, room, model_manager=model_mgr,
        outdoor_temp=30.0, settings={}, has_external_sensor=True,
        previous_mode=MODE_COOLING,
    )
    mode, pf = await ctrl.async_evaluate(
        current_temp=23.0,
        targets=TargetTemps(heat=21.0, cool=24.0),
    )
    assert mode == MODE_IDLE
    assert pf == 0.0
