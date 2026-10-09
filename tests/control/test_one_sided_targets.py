"""One-sided targets (cool-only / heat-only overrides) must still drive the MPC (#388, #408, #377)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.roommind.const import TargetTemps
from custom_components.roommind.control.analytics_simulator import _simulate_mpc
from custom_components.roommind.control.mpc_controller import (
    MODE_COOLING,
    MODE_HEATING,
    MODE_IDLE,
    MPCController,
    fill_missing_targets,
)
from custom_components.roommind.control.thermal_model import RCModel

from .conftest import build_hass, make_room

AC_DEVICE = {"entity_id": "climate.living_room_ac", "type": "ac", "role": "auto"}


def _trained_manager(model: RCModel) -> MagicMock:
    mgr = MagicMock()
    mgr.get_model.return_value = model
    mgr.get_mode_counts.return_value = (1500, 5, 243)
    mgr.get_prediction_std.return_value = 0.3
    return mgr


def _cool_only_controller(resolver=None, **room_overrides) -> MPCController:
    room = make_room(
        climate_mode="cool_only",
        thermostats=[],
        acs=["climate.living_room_ac"],
        override_heat=None,
        override_cool=24.0,
        override_until=None,
        **room_overrides,
    )
    return MPCController(
        build_hass(),
        room,
        model_manager=_trained_manager(RCModel(C=1.0, U=0.0139, Q_heat=9.1, Q_cool=3.64)),
        outdoor_temp=28.0,
        settings={},
        has_external_sensor=True,
        target_resolver=resolver,
    )


class TestFillMissingTargets:
    @pytest.mark.parametrize(
        ("heat", "cool", "fallback", "expected"),
        [
            (21.0, 24.0, 26.0, (21.0, 24.0)),
            (None, None, 26.0, (26.0, 26.0)),
            (None, 24.0, 26.0, (24.0, 24.0)),
            (None, 24.0, 22.0, (22.0, 24.0)),
            (21.0, None, 26.0, (21.0, 26.0)),
            (21.0, None, 18.0, (21.0, 18.0)),
        ],
    )
    def test_fill(self, heat, cool, fallback, expected):
        assert fill_missing_targets(heat, cool, fallback) == expected


class TestCoolingOnlyOverride:
    """A cool-only room stores ``heat=None``; the room above its target must cool."""

    @pytest.mark.parametrize("current", [24.5, 25.5, 26.0, 27.0, 29.0])
    @pytest.mark.asyncio
    async def test_cools_with_resolver(self, current):
        targets = TargetTemps(heat=None, cool=24.0)
        ctrl = _cool_only_controller(resolver=lambda _ts: targets)
        mode, pf = await ctrl.async_evaluate(current, targets)
        assert mode == MODE_COOLING
        assert pf > 0.0

    @pytest.mark.parametrize("current", [24.5, 26.0, 29.0])
    @pytest.mark.asyncio
    async def test_cools_without_resolver(self, current):
        ctrl = _cool_only_controller(resolver=None)
        mode, _ = await ctrl.async_evaluate(current, TargetTemps(heat=None, cool=24.0))
        assert mode == MODE_COOLING

    @pytest.mark.asyncio
    async def test_idle_when_below_target(self):
        targets = TargetTemps(heat=None, cool=24.0)
        ctrl = _cool_only_controller(resolver=lambda _ts: targets)
        mode, _ = await ctrl.async_evaluate(22.0, targets)
        assert mode == MODE_IDLE


class TestHeatingOnlyOverrideUnchanged:
    """``cool=None`` keeps its single-point behaviour (no overshoot allowed)."""

    def _controller(self, targets: TargetTemps) -> MPCController:
        room = make_room(climate_mode="heat_only", override_heat=21.0, override_cool=None, override_until=None)
        return MPCController(
            build_hass(),
            room,
            model_manager=_trained_manager(RCModel(C=1.0, U=0.15, Q_heat=3.0, Q_cool=4.0)),
            outdoor_temp=5.0,
            settings={},
            has_external_sensor=True,
            target_resolver=lambda _ts: targets,
        )

    @pytest.mark.asyncio
    async def test_heats_when_cold(self):
        targets = TargetTemps(heat=21.0, cool=None)
        mode, _ = await self._controller(targets).async_evaluate(17.0, targets)
        assert mode == MODE_HEATING

    @pytest.mark.asyncio
    async def test_idle_when_warm(self):
        targets = TargetTemps(heat=21.0, cool=None)
        mode, _ = await self._controller(targets).async_evaluate(23.0, targets)
        assert mode == MODE_IDLE


class TestSimulatorOneSidedTargets:
    def test_prediction_cools_toward_cool_only_target(self):
        model = RCModel(C=1.0, U=0.0139, Q_heat=9.1, Q_cool=3.64, Q_solar=0.0)
        forecast = [{"target_temp": 24.0, "heat_target": None, "cool_target": 24.0}] * 12
        room_config = {
            "thermostats": [],
            "acs": ["climate.living_room_ac"],
            "devices": [AC_DEVICE],
            "climate_mode": "cool_only",
        }
        result = _simulate_mpc(
            model,
            forecast,
            [28.0] * 12,
            current_temp=27.0,
            room_config=room_config,
            settings={"comfort_weight": 70},
        )
        assert result[-1] < 27.0
