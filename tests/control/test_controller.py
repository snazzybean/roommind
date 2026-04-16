"""Tests for MPC controller main flow, orchestration, data gates, min_updates, outdoor gating."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.roommind.control.mpc_controller import (
    MPCController,
)
from custom_components.roommind.control.thermal_model import RCModel, RoomModelManager

from .conftest import build_hass, make_room


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
async def test_mpc_outdoor_gating_bypassed_by_override():
    """Override active → outdoor cooling gate bypassed, cooling proceeds."""
    hass = build_hass()
    room = make_room(thermostats=[], acs=["climate.ac"], override_temp=22.0, override_until=None)
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
    assert mode == "cooling"


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
