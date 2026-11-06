"""Tests for CoverOrchestrator — position reading, delegation, and async_process pipeline."""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.const import (
    COVER_COOLING_LINEAR_H,
    COVER_COOLING_LOOKAHEAD_H,
    COVER_DEFAULT_BETA_S,
    COVER_DIRECT_SUN_ANGLE_DEG,
    COVER_LINEAR_LOOKAHEAD_H,
    COVER_MIN_IDLE_FOR_LEARNED,
    COVER_PREDICTION_DT_MINUTES,
    COVER_SMOOTHING_MINUTES,
    COVER_SMOOTHING_RISE_MINUTES,
    MODE_COOLING,
    MODE_HEATING,
    MODE_IDLE,
    TargetTemps,
)
from custom_components.roommind.managers.cover_manager import CoverDecision
from custom_components.roommind.managers.cover_orchestrator import (
    CoverOrchestrator,
    CoverResult,
)

_BUILD_SOLAR_SERIES = "custom_components.roommind.managers.cover_orchestrator.build_solar_series"

# ── Helpers ───────────────────────────────────────────────────────────


def _make_hass() -> MagicMock:
    hass = MagicMock()
    hass.config.latitude = 48.2
    hass.config.longitude = 16.3
    hass.states.get = MagicMock(return_value=None)
    return hass


def _make_cover_manager() -> MagicMock:
    cm = MagicMock()
    cm.evaluate = MagicMock(return_value=CoverDecision(target_position=100, changed=False, reason="disabled"))
    cm.update_position = MagicMock()
    cm.get_current_position = MagicMock(return_value=50)
    cm.is_user_override_active = MagicMock(return_value=False)
    cm.remove_room = MagicMock()
    return cm


def _make_model_manager() -> MagicMock:
    mm = MagicMock()
    mm.get_mode_counts = MagicMock(return_value=(0, 0, 0))
    mm.get_prediction_std = MagicMock(return_value=1.0)
    mm.get_model = MagicMock()
    return mm


def _make_room(**overrides) -> dict:
    room = {
        "area_id": "living_room",
        "temperature_sensor": "",
        "covers": [],
        "covers_auto_enabled": True,
        "covers_deploy_threshold": 1.5,
        "covers_min_position": 0,
        "covers_outdoor_min_temp": None,
        "covers_override_minutes": 60,
        "cover_schedules": [],
        "cover_schedule_selector_entity": "",
        "covers_night_close": False,
        "covers_night_close_elevation": 0,
        "covers_night_close_offset_minutes": 0,
        "covers_night_position": 0,
        "covers_snap_deploy": False,
        "cover_min_positions": {},
    }
    room.update(overrides)
    return room


def _make_cover_state(position: int | None = None, state: str = "open") -> MagicMock:
    s = MagicMock()
    s.state = state
    s.attributes = {"current_position": position} if position is not None else {}
    return s


# ── TestSetCloudSeries ────────────────────────────────────────────────


class TestSetCloudSeries:
    def test_stores_cloud_series(self):
        orch = CoverOrchestrator(_make_hass(), _make_cover_manager(), _make_model_manager())
        series = [0.1, 0.2, 0.3]
        orch.set_cloud_series(series)
        assert orch._cloud_series is series

    def test_clears_cloud_series(self):
        orch = CoverOrchestrator(_make_hass(), _make_cover_manager(), _make_model_manager())
        orch.set_cloud_series([0.5])
        orch.set_cloud_series(None)
        assert orch._cloud_series is None

    def test_initial_cloud_series_is_none(self):
        orch = CoverOrchestrator(_make_hass(), _make_cover_manager(), _make_model_manager())
        assert orch._cloud_series is None


# ── TestReadPositions ─────────────────────────────────────────────────


class TestReadPositions:
    def test_single_cover_reads_position(self):
        hass = _make_hass()
        cm = _make_cover_manager()
        orch = CoverOrchestrator(hass, cm, _make_model_manager())

        hass.states.get = MagicMock(return_value=_make_cover_state(position=75))
        room = _make_room(covers=["cover.blind1"])

        result = orch.read_positions("living_room", room)

        assert result.positions == [75]
        cm.update_position.assert_called_once_with("living_room", 75, override_minutes=60)

    def test_multiple_covers_average(self):
        hass = _make_hass()
        cm = _make_cover_manager()
        orch = CoverOrchestrator(hass, cm, _make_model_manager())

        states = {"cover.blind1": _make_cover_state(position=60), "cover.blind2": _make_cover_state(position=40)}
        hass.states.get = MagicMock(side_effect=states.get)
        room = _make_room(covers=["cover.blind1", "cover.blind2"])

        result = orch.read_positions("living_room", room)

        assert result.positions == [60, 40]
        # Average is 50
        cm.update_position.assert_called_once_with("living_room", 50, override_minutes=60)

    def test_no_covers_returns_shading_factor_1(self):
        orch = CoverOrchestrator(_make_hass(), _make_cover_manager(), _make_model_manager())
        room = _make_room(covers=[])

        result = orch.read_positions("living_room", room)

        assert result.shading_factor == 1.0
        assert result.positions == []

    def test_unavailable_cover_skipped(self):
        hass = _make_hass()
        cm = _make_cover_manager()
        orch = CoverOrchestrator(hass, cm, _make_model_manager())

        # First cover returns None (unavailable), second has position
        states = {"cover.blind1": None, "cover.blind2": _make_cover_state(position=80)}
        hass.states.get = MagicMock(side_effect=states.get)
        room = _make_room(covers=["cover.blind1", "cover.blind2"])

        result = orch.read_positions("living_room", room)

        assert result.positions == [80]
        cm.update_position.assert_called_once_with("living_room", 80, override_minutes=60)

    def test_closed_state_fallback(self):
        hass = _make_hass()
        cm = _make_cover_manager()
        orch = CoverOrchestrator(hass, cm, _make_model_manager())

        hass.states.get = MagicMock(return_value=_make_cover_state(position=None, state="closed"))
        room = _make_room(covers=["cover.blind1"])

        result = orch.read_positions("living_room", room)

        assert result.positions == [0]
        cm.update_position.assert_called_once_with("living_room", 0, override_minutes=60)

    def test_open_state_fallback(self):
        hass = _make_hass()
        cm = _make_cover_manager()
        orch = CoverOrchestrator(hass, cm, _make_model_manager())

        hass.states.get = MagicMock(return_value=_make_cover_state(position=None, state="open"))
        room = _make_room(covers=["cover.blind1"])

        result = orch.read_positions("living_room", room)

        assert result.positions == [100]
        cm.update_position.assert_called_once_with("living_room", 100, override_minutes=60)

    def test_custom_override_minutes(self):
        hass = _make_hass()
        cm = _make_cover_manager()
        orch = CoverOrchestrator(hass, cm, _make_model_manager())

        hass.states.get = MagicMock(return_value=_make_cover_state(position=50))
        room = _make_room(covers=["cover.blind1"], covers_override_minutes=120)

        orch.read_positions("living_room", room)

        cm.update_position.assert_called_once_with("living_room", 50, override_minutes=120)

    def test_no_positions_skips_update(self):
        """When all covers are unavailable, update_position is not called."""
        hass = _make_hass()
        cm = _make_cover_manager()
        orch = CoverOrchestrator(hass, cm, _make_model_manager())

        hass.states.get = MagicMock(return_value=None)
        room = _make_room(covers=["cover.blind1"])

        result = orch.read_positions("living_room", room)

        assert result.positions == []
        assert result.shading_factor == 1.0
        cm.update_position.assert_not_called()


# ── TestDelegation ────────────────────────────────────────────────────


class TestDelegation:
    def test_get_current_position_delegates(self):
        cm = _make_cover_manager()
        cm.get_current_position.return_value = 42
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())

        assert orch.get_current_position("bedroom") == 42
        cm.get_current_position.assert_called_once_with("bedroom")

    def test_is_user_override_active_delegates(self):
        cm = _make_cover_manager()
        cm.is_user_override_active.return_value = True
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())

        assert orch.is_user_override_active("bedroom") is True
        cm.is_user_override_active.assert_called_once_with("bedroom")

    def test_remove_room_delegates(self):
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())

        orch.remove_room("bedroom")
        cm.remove_room.assert_called_once_with("bedroom")


# ── TestAsyncProcess ──────────────────────────────────────────────────


class TestAsyncProcess:
    @pytest.mark.asyncio
    async def test_no_covers_returns_result(self):
        """Room with no covers still returns a valid CoverResult."""
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(covers=[])

        result = await orch.async_process(
            area_id="living_room",
            room=room,
            targets=TargetTemps(heat=21.0, cool=24.0),
            mode=MODE_HEATING,
            current_temp=20.0,
            outdoor_temp=15.0,
            q_solar=0.3,
            predicted_peak_temp=None,
            has_override=False,
        )

        assert isinstance(result, CoverResult)
        assert isinstance(result.decision, CoverDecision)
        cm.evaluate.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_disabled_returns_unchanged(self):
        """When covers_auto_enabled=False, process returns no-op without calling evaluate."""
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(covers=["cover.blind1"], covers_auto_enabled=False)

        result = await orch.async_process(
            area_id="living_room",
            room=room,
            targets=TargetTemps(heat=21.0, cool=24.0),
            mode=MODE_HEATING,
            current_temp=20.0,
            outdoor_temp=15.0,
            q_solar=0.3,
            predicted_peak_temp=22.0,
            has_override=False,
        )

        assert result.decision.changed is False
        assert result.decision.reason == "disabled"
        assert result.forced_reason == ""
        cm.evaluate.assert_not_called()

    @pytest.mark.asyncio
    async def test_managed_mode_no_external_sensor(self):
        """No external sensor (Managed Mode) still returns valid CoverResult."""
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(temperature_sensor="", covers=["cover.blind1"])

        result = await orch.async_process(
            area_id="living_room",
            room=room,
            targets=TargetTemps(heat=21.0, cool=24.0),
            mode=MODE_HEATING,
            current_temp=20.0,
            outdoor_temp=15.0,
            q_solar=0.0,
            predicted_peak_temp=21.0,
            has_override=False,
        )

        assert isinstance(result, CoverResult)

    @pytest.mark.asyncio
    async def test_snap_deploy_passed_to_evaluate(self):
        """covers_snap_deploy=True on room is forwarded to CoverManager.evaluate()."""
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(covers=["cover.blind1"], covers_snap_deploy=True)

        await orch.async_process(
            area_id="living_room",
            room=room,
            targets=TargetTemps(heat=21.0, cool=24.0),
            mode=MODE_HEATING,
            current_temp=20.0,
            outdoor_temp=15.0,
            q_solar=0.3,
            predicted_peak_temp=22.0,
            has_override=False,
        )

        cm.evaluate.assert_called_once()
        call_kwargs = cm.evaluate.call_args[1]
        assert call_kwargs["covers_snap_deploy"] is True

    @pytest.mark.asyncio
    async def test_cooling_mode_uses_cool_target(self):
        """In cooling mode, cover_target should use targets.cool."""
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(covers=["cover.blind1"])

        await orch.async_process(
            area_id="living_room",
            room=room,
            targets=TargetTemps(heat=21.0, cool=24.0),
            mode=MODE_COOLING,
            current_temp=25.0,
            outdoor_temp=30.0,
            q_solar=0.5,
            predicted_peak_temp=26.0,
            has_override=False,
        )

        # Verify evaluate was called with target_temp=24.0 (the cool target)
        call_kwargs = cm.evaluate.call_args
        assert call_kwargs[1]["target_temp"] == 24.0 or call_kwargs.kwargs["target_temp"] == 24.0

    @pytest.mark.asyncio
    async def test_non_cooling_uses_comfort_cool_not_heat_target(self):
        """Not cooling: shading protects the comfort ceiling, not the heating setpoint (#418)."""
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(covers=["cover.blind1"])  # comfort_cool defaults to 24.0

        await orch.async_process(
            area_id="living_room",
            room=room,
            targets=TargetTemps(heat=21.0, cool=24.0),
            mode=MODE_HEATING,
            current_temp=20.0,
            outdoor_temp=15.0,
            q_solar=0.3,
            predicted_peak_temp=22.0,
            has_override=False,
        )

        assert cm.evaluate.call_args[1]["target_temp"] == 24.0

    @pytest.mark.asyncio
    async def test_heat_only_single_point_block_uses_comfort_cool(self):
        """The reported case: heat_only room, schedule block collapses both targets to 22 (#418).

        MODE_COOLING is unreachable in heat_only, so the old code compared the
        predicted peak against the heating setpoint and deployed ~3 C too early.
        """
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(covers=["cover.blind1"], comfort_cool=24.0)

        await orch.async_process(
            area_id="living_room",
            room=room,
            targets=TargetTemps(heat=22.0, cool=22.0),
            mode=MODE_HEATING,
            current_temp=23.2,
            outdoor_temp=15.8,
            q_solar=0.3,
            predicted_peak_temp=23.6,
            has_override=False,
        )

        assert cm.evaluate.call_args[1]["target_temp"] == 24.0

    @pytest.mark.asyncio
    async def test_cooling_keeps_low_cool_target(self):
        """Actively cooling to 22 must still shade against 22, not the comfort ceiling."""
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(covers=["cover.blind1"], comfort_cool=24.0)

        await orch.async_process(
            area_id="living_room",
            room=room,
            targets=TargetTemps(heat=22.0, cool=22.0),
            mode=MODE_COOLING,
            current_temp=23.0,
            outdoor_temp=28.0,
            q_solar=0.6,
            predicted_peak_temp=25.0,
            has_override=False,
        )

        assert cm.evaluate.call_args[1]["target_temp"] == 22.0

    @pytest.mark.asyncio
    async def test_eco_branch_uses_eco_cool_above_comfort_cool(self):
        """Eco widens the band: shading must not pull back to the comfort ceiling."""
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(covers=["cover.blind1"], comfort_cool=24.0)

        await orch.async_process(
            area_id="living_room",
            room=room,
            targets=TargetTemps(heat=17.0, cool=27.0),
            mode=MODE_IDLE,
            current_temp=22.0,
            outdoor_temp=20.0,
            q_solar=0.4,
            predicted_peak_temp=25.0,
            has_override=False,
        )

        assert cm.evaluate.call_args[1]["target_temp"] == 27.0

    @pytest.mark.asyncio
    async def test_cool_only_override_without_heat_target(self):
        """cool_only override sets heat=None; the cool target must win over comfort_cool."""
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(covers=["cover.blind1"], comfort_cool=24.0)

        await orch.async_process(
            area_id="living_room",
            room=room,
            targets=TargetTemps(heat=None, cool=26.0),
            mode=MODE_IDLE,
            current_temp=24.5,
            outdoor_temp=28.0,
            q_solar=0.5,
            predicted_peak_temp=26.5,
            has_override=True,
        )

        assert cm.evaluate.call_args[1]["target_temp"] == 26.0

    @pytest.mark.asyncio
    async def test_heat_target_above_comfort_cool_is_the_floor(self):
        """comfort_cool below the heating setpoint must not shade more aggressively than before."""
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(covers=["cover.blind1"], comfort_cool=22.0)

        await orch.async_process(
            area_id="living_room",
            room=room,
            targets=TargetTemps(heat=23.0, cool=None),
            mode=MODE_HEATING,
            current_temp=22.0,
            outdoor_temp=10.0,
            q_solar=0.3,
            predicted_peak_temp=24.0,
            has_override=False,
        )

        assert cm.evaluate.call_args[1]["target_temp"] == 23.0

    @pytest.mark.asyncio
    async def test_cooling_without_cool_target_falls_back(self):
        """MPC can report MODE_COOLING with cool=None; the non-cooling branch must catch it."""
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(covers=["cover.blind1"], comfort_cool=24.0)

        await orch.async_process(
            area_id="living_room",
            room=room,
            targets=TargetTemps(heat=21.0, cool=None),
            mode=MODE_COOLING,
            current_temp=25.0,
            outdoor_temp=30.0,
            q_solar=0.5,
            predicted_peak_temp=26.0,
            has_override=False,
        )

        assert cm.evaluate.call_args[1]["target_temp"] == 24.0

    @pytest.mark.asyncio
    async def test_no_targets_falls_back_to_comfort_cool(self):
        """Both targets None (force_off): comfort_cool replaces the old hardcoded 22.0."""
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(covers=["cover.blind1"], comfort_cool=24.0)

        await orch.async_process(
            area_id="living_room",
            room=room,
            targets=TargetTemps(heat=None, cool=None),
            mode=MODE_HEATING,
            current_temp=20.0,
            outdoor_temp=15.0,
            q_solar=0.3,
            predicted_peak_temp=22.0,
            has_override=False,
        )

        assert cm.evaluate.call_args[1]["target_temp"] == 24.0

    @pytest.mark.asyncio
    @patch("custom_components.roommind.managers.cover_orchestrator.CoverManager.async_apply", new_callable=AsyncMock)
    async def test_changed_decision_calls_apply(self, mock_apply):
        """When decision.changed=True, async_apply is called on covers."""
        cm = _make_cover_manager()
        cm.evaluate.return_value = CoverDecision(target_position=30, changed=True, reason="solar_shade")
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(covers=["cover.blind1", "cover.blind2"])

        with patch.object(CoverOrchestrator, "_estimate_solar_peak_temp", return_value=23.0):
            result = await orch.async_process(
                area_id="living_room",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=20.0,
                outdoor_temp=15.0,
                q_solar=0.5,
                predicted_peak_temp=None,
                has_override=False,
            )

        assert result.decision.changed is True
        mock_apply.assert_awaited_once_with(
            orch.hass,
            ["cover.blind1", "cover.blind2"],
            30,
            cover_min_positions=None,
        )

    @pytest.mark.asyncio
    async def test_unchanged_decision_skips_apply(self):
        """When decision.changed=False, async_apply is NOT called."""
        cm = _make_cover_manager()
        cm.evaluate.return_value = CoverDecision(target_position=100, changed=False, reason="no_change")
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(covers=["cover.blind1"])

        with patch.object(CoverOrchestrator, "_estimate_solar_peak_temp", return_value=22.0):
            await orch.async_process(
                area_id="living_room",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=20.0,
                outdoor_temp=15.0,
                q_solar=0.3,
                predicted_peak_temp=None,
                has_override=False,
            )

        # CoverManager.async_apply should not have been called

    @pytest.mark.asyncio
    async def test_predicted_peak_passed_through(self):
        """When predicted_peak_temp is provided, it goes directly to evaluate."""
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(covers=["cover.blind1"])

        await orch.async_process(
            area_id="living_room",
            room=room,
            targets=TargetTemps(heat=21.0, cool=24.0),
            mode=MODE_HEATING,
            current_temp=22.0,  # above heat target: no heating gate
            outdoor_temp=15.0,
            q_solar=0.3,
            predicted_peak_temp=25.5,
            has_override=False,
        )

        call_kwargs = cm.evaluate.call_args
        assert call_kwargs[1]["predicted_peak_temp"] == 25.5 or call_kwargs.kwargs["predicted_peak_temp"] == 25.5

    @pytest.mark.asyncio
    async def test_no_predicted_peak_uses_fallback(self):
        """When predicted_peak_temp is None, _estimate_solar_peak_temp is used."""
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(covers=["cover.blind1"])

        with patch.object(CoverOrchestrator, "_estimate_solar_peak_temp", return_value=23.5) as mock_est:
            await orch.async_process(
                area_id="living_room",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=22.0,  # above heat target: no heating gate
                outdoor_temp=15.0,
                q_solar=0.3,
                predicted_peak_temp=None,
                has_override=False,
            )

            mock_est.assert_called_once()
            call_kwargs = cm.evaluate.call_args
            assert call_kwargs[1]["predicted_peak_temp"] == 23.5 or call_kwargs.kwargs["predicted_peak_temp"] == 23.5

    @pytest.mark.asyncio
    async def test_schedule_forced_position(self):
        """Active cover schedule forces position and sets forced_reason."""
        hass = _make_hass()
        cm = _make_cover_manager()
        orch = CoverOrchestrator(hass, cm, _make_model_manager())

        sched_state = MagicMock()
        sched_state.state = "on"
        sched_state.attributes = {"position": 25}
        hass.states.get = MagicMock(return_value=sched_state)

        room = _make_room(
            covers=["cover.blind1"],
            cover_schedules=[{"entity_id": "schedule.cover_morning"}],
        )

        with patch(
            "custom_components.roommind.managers.cover_orchestrator.resolve_schedule_index",
            return_value=0,
        ):
            result = await orch.async_process(
                area_id="living_room",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=20.0,
                outdoor_temp=15.0,
                q_solar=0.3,
                predicted_peak_temp=22.0,
                has_override=False,
            )

        assert result.forced_reason == "schedule_active"
        # evaluate should have been called with forced_position=25
        call_kwargs = cm.evaluate.call_args
        assert call_kwargs[1]["forced_position"] == 25 or call_kwargs.kwargs["forced_position"] == 25

    @pytest.mark.asyncio
    async def test_night_close_forced(self):
        """Night close forces position when solar elevation <= 0."""
        hass = _make_hass()
        cm = _make_cover_manager()
        orch = CoverOrchestrator(hass, cm, _make_model_manager())

        room = _make_room(covers=["cover.blind1"], covers_night_close=True, covers_night_position=10)

        with patch(
            "custom_components.roommind.managers.cover_orchestrator.solar_elevation",
            return_value=-5.0,
        ):
            result = await orch.async_process(
                area_id="living_room",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=20.0,
                outdoor_temp=15.0,
                q_solar=0.0,
                predicted_peak_temp=20.0,
                has_override=False,
            )

        assert result.forced_reason == "night_close"
        call_kwargs = cm.evaluate.call_args
        assert call_kwargs[1]["forced_position"] == 10 or call_kwargs.kwargs["forced_position"] == 10

    @pytest.mark.asyncio
    async def test_auto_disabled_no_action_regardless_of_night_close(self):
        """When auto is disabled, covers are not moved even if night just ended."""
        hass = _make_hass()
        cm = _make_cover_manager()
        orch = CoverOrchestrator(hass, cm, _make_model_manager())

        room = _make_room(
            covers=["cover.blind1"],
            covers_night_close=True,
            covers_auto_enabled=False,
        )

        with patch(
            "custom_components.roommind.managers.cover_orchestrator.solar_elevation",
            return_value=10.0,  # Sun is up
        ):
            result = await orch.async_process(
                area_id="living_room",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=20.0,
                outdoor_temp=15.0,
                q_solar=0.3,
                predicted_peak_temp=21.0,
                has_override=False,
            )

        assert result.decision.changed is False
        assert result.decision.reason == "disabled"
        assert result.forced_reason == ""
        cm.evaluate.assert_not_called()

    @pytest.mark.asyncio
    async def test_schedule_ignored_when_auto_disabled(self):
        """Active schedule does not control covers when covers_auto_enabled=False."""
        hass = _make_hass()
        cm = _make_cover_manager()
        orch = CoverOrchestrator(hass, cm, _make_model_manager())

        sched_state = MagicMock()
        sched_state.state = "on"
        sched_state.attributes = {"position": 25}
        hass.states.get = MagicMock(return_value=sched_state)

        room = _make_room(
            covers=["cover.blind1"],
            covers_auto_enabled=False,
            cover_schedules=[{"entity_id": "schedule.blind_plan"}],
        )

        with patch(
            "custom_components.roommind.managers.cover_orchestrator.resolve_schedule_index",
            return_value=0,
        ):
            result = await orch.async_process(
                area_id="living_room",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=20.0,
                outdoor_temp=15.0,
                q_solar=0.3,
                predicted_peak_temp=22.0,
                has_override=False,
            )

        assert result.decision.changed is False
        assert result.decision.reason == "disabled"
        assert result.forced_reason == ""
        cm.evaluate.assert_not_called()

    @pytest.mark.asyncio
    async def test_active_cover_schedule_index_returned(self):
        """The active_cover_schedule_index is included in CoverResult."""
        hass = _make_hass()
        cm = _make_cover_manager()
        orch = CoverOrchestrator(hass, cm, _make_model_manager())

        # Schedule entity exists but is off
        sched_state = MagicMock()
        sched_state.state = "off"
        hass.states.get = MagicMock(return_value=sched_state)

        room = _make_room(
            covers=["cover.blind1"],
            cover_schedules=[{"entity_id": "schedule.cover1"}, {"entity_id": "schedule.cover2"}],
        )

        with patch(
            "custom_components.roommind.managers.cover_orchestrator.resolve_schedule_index",
            return_value=1,
        ):
            result = await orch.async_process(
                area_id="living_room",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=20.0,
                outdoor_temp=15.0,
                q_solar=0.0,
                predicted_peak_temp=21.0,
                has_override=False,
            )

        assert result.active_cover_schedule_index == 1

    @pytest.mark.asyncio
    async def test_no_cover_schedules_index_minus_one(self):
        """Without cover_schedules, active_cover_schedule_index is -1."""
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(covers=["cover.blind1"], cover_schedules=[])

        result = await orch.async_process(
            area_id="living_room",
            room=room,
            targets=TargetTemps(heat=21.0, cool=24.0),
            mode=MODE_HEATING,
            current_temp=20.0,
            outdoor_temp=15.0,
            q_solar=0.0,
            predicted_peak_temp=21.0,
            has_override=False,
        )

        assert result.active_cover_schedule_index == -1


# ── TestEstimateSolarPeakTemp ─────────────────────────────────────────


class TestEstimateSolarPeakTemp:
    @patch(_BUILD_SOLAR_SERIES, return_value=[0.5])
    def test_tier2_linear_fallback(self, _mock_solar):
        """With no idle samples, falls back to linear: base + beta_s * daily_peak * lookahead."""
        mm = _make_model_manager()
        mm.get_mode_counts.return_value = (0, 0, 0)  # No idle samples
        orch = CoverOrchestrator(_make_hass(), _make_cover_manager(), mm)

        result = orch._estimate_solar_peak_temp("living_room", 20.0, 21.0, 0.5, 15.0)

        expected = 20.0 + COVER_DEFAULT_BETA_S * 0.5 * COVER_LINEAR_LOOKAHEAD_H
        assert result == pytest.approx(expected)

    @patch(_BUILD_SOLAR_SERIES, return_value=[0.5])
    def test_tier2_with_none_current_temp(self, _mock_solar):
        """When current_temp is None, base_temp falls back to target_temp."""
        mm = _make_model_manager()
        mm.get_mode_counts.return_value = (0, 0, 0)
        orch = CoverOrchestrator(_make_hass(), _make_cover_manager(), mm)

        result = orch._estimate_solar_peak_temp("living_room", None, 22.0, 0.5, 15.0)

        expected = 22.0 + COVER_DEFAULT_BETA_S * 0.5 * COVER_LINEAR_LOOKAHEAD_H
        assert result == pytest.approx(expected)

    @patch(_BUILD_SOLAR_SERIES, return_value=[0.0])
    def test_tier2_with_zero_solar(self, _mock_solar):
        """When daily solar peak is zero, peak equals base temp."""
        mm = _make_model_manager()
        mm.get_mode_counts.return_value = (0, 0, 0)
        orch = CoverOrchestrator(_make_hass(), _make_cover_manager(), mm)

        result = orch._estimate_solar_peak_temp("living_room", 20.0, 21.0, 0.0, 15.0)

        assert result == pytest.approx(20.0)

    @patch(_BUILD_SOLAR_SERIES, return_value=[0.5])
    def test_model_exception_falls_back_to_linear(self, _mock_solar):
        """If model_manager raises, falls back to linear using daily peak."""
        mm = _make_model_manager()
        mm.get_mode_counts.side_effect = Exception("no model")
        orch = CoverOrchestrator(_make_hass(), _make_cover_manager(), mm)

        result = orch._estimate_solar_peak_temp("living_room", 20.0, 21.0, 0.5, 15.0)

        expected = 20.0 + COVER_DEFAULT_BETA_S * 0.5 * COVER_LINEAR_LOOKAHEAD_H
        assert result == pytest.approx(expected)

    @patch(_BUILD_SOLAR_SERIES, return_value=[0.2, 0.5, 0.9, 0.8, 0.6])
    def test_tier2_uses_daily_peak_not_current_q_solar(self, _mock_solar):
        """Tier 2 uses max of daily solar series (0.9), not the current q_solar argument (0.2)."""
        mm = _make_model_manager()
        mm.get_mode_counts.return_value = (0, 0, 0)
        orch = CoverOrchestrator(_make_hass(), _make_cover_manager(), mm)

        result = orch._estimate_solar_peak_temp("living_room", 20.0, 21.0, 0.2, 15.0)

        expected = 20.0 + COVER_DEFAULT_BETA_S * 0.9 * COVER_LINEAR_LOOKAHEAD_H
        assert result == pytest.approx(expected)

    def test_tier2_cloud_series_passed_to_build_solar_series(self):
        """Tier 2 passes the orchestrator's cloud_series to build_solar_series."""
        mm = _make_model_manager()
        mm.get_mode_counts.return_value = (0, 0, 0)
        orch = CoverOrchestrator(_make_hass(), _make_cover_manager(), mm)
        orch.set_cloud_series([50.0, 60.0])

        with patch(_BUILD_SOLAR_SERIES, return_value=[0.4]) as mock_bs:
            orch._estimate_solar_peak_temp("living_room", 20.0, 21.0, 0.5, 15.0)

        _call_kwargs = mock_bs.call_args
        assert _call_kwargs.kwargs.get("cloud_series") == [50.0, 60.0]

    @patch(_BUILD_SOLAR_SERIES, return_value=[])
    def test_tier2_fallback_when_daily_series_empty(self, _mock_solar):
        """When build_solar_series returns empty list, falls back to current q_solar argument."""
        mm = _make_model_manager()
        mm.get_mode_counts.return_value = (0, 0, 0)
        orch = CoverOrchestrator(_make_hass(), _make_cover_manager(), mm)

        result = orch._estimate_solar_peak_temp("living_room", 20.0, 21.0, 0.7, 15.0)

        expected = 20.0 + COVER_DEFAULT_BETA_S * 0.7 * COVER_LINEAR_LOOKAHEAD_H
        assert result == pytest.approx(expected)


# ── TestScheduleGateMode ─────────────────────────────────────────────


class TestScheduleGateMode:
    @pytest.mark.asyncio
    async def test_gate_mode_on_enables_thermal(self):
        """Gate mode schedule 'on' → evaluate called with solar_gated=True, no forced_position."""
        hass = _make_hass()
        cm = _make_cover_manager()
        orch = CoverOrchestrator(hass, cm, _make_model_manager())

        sched_state = MagicMock()
        sched_state.state = "on"
        sched_state.attributes = {}
        hass.states.get = MagicMock(return_value=sched_state)

        room = _make_room(
            covers=["cover.blind1"],
            cover_schedules=[{"entity_id": "schedule.cover_time", "mode": "gate"}],
        )

        with patch(
            "custom_components.roommind.managers.cover_orchestrator.resolve_schedule_index",
            return_value=0,
        ):
            await orch.async_process(
                area_id="living_room",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=20.0,
                outdoor_temp=15.0,
                q_solar=0.3,
                predicted_peak_temp=22.0,
                has_override=False,
            )

        call_kwargs = cm.evaluate.call_args
        assert call_kwargs[1].get("forced_position") is None or call_kwargs.kwargs.get("forced_position") is None
        assert call_kwargs[1].get("solar_gated") is True or call_kwargs.kwargs.get("solar_gated") is True

    @pytest.mark.asyncio
    async def test_gate_mode_off_passes_solar_gated_false(self):
        """Gate mode schedule 'off' → evaluate called with solar_gated=False."""
        hass = _make_hass()
        cm = _make_cover_manager()
        orch = CoverOrchestrator(hass, cm, _make_model_manager())

        sched_state = MagicMock()
        sched_state.state = "off"
        sched_state.attributes = {}
        hass.states.get = MagicMock(return_value=sched_state)

        room = _make_room(
            covers=["cover.blind1"],
            cover_schedules=[{"entity_id": "schedule.cover_time", "mode": "gate"}],
        )

        with patch(
            "custom_components.roommind.managers.cover_orchestrator.resolve_schedule_index",
            return_value=0,
        ):
            await orch.async_process(
                area_id="living_room",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=20.0,
                outdoor_temp=15.0,
                q_solar=0.3,
                predicted_peak_temp=22.0,
                has_override=False,
            )

        call_kwargs = cm.evaluate.call_args
        assert call_kwargs[1].get("solar_gated") is False or call_kwargs.kwargs.get("solar_gated") is False

    @pytest.mark.asyncio
    async def test_force_mode_unchanged(self):
        """Force mode schedule 'on' → forced_position set as before, solar_gated=True (default)."""
        hass = _make_hass()
        cm = _make_cover_manager()
        orch = CoverOrchestrator(hass, cm, _make_model_manager())

        sched_state = MagicMock()
        sched_state.state = "on"
        sched_state.attributes = {"position": 30}
        hass.states.get = MagicMock(return_value=sched_state)

        room = _make_room(
            covers=["cover.blind1"],
            cover_schedules=[{"entity_id": "schedule.cover_blind", "mode": "force"}],
        )

        with patch(
            "custom_components.roommind.managers.cover_orchestrator.resolve_schedule_index",
            return_value=0,
        ):
            result = await orch.async_process(
                area_id="living_room",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=20.0,
                outdoor_temp=15.0,
                q_solar=0.3,
                predicted_peak_temp=22.0,
                has_override=False,
            )

        assert result.forced_reason == "schedule_active"
        call_kwargs = cm.evaluate.call_args
        assert call_kwargs[1].get("forced_position") == 30 or call_kwargs.kwargs.get("forced_position") == 30
        assert call_kwargs[1].get("solar_gated") is True or call_kwargs.kwargs.get("solar_gated", True) is True

    @pytest.mark.asyncio
    async def test_gate_mode_night_close_not_affected(self):
        """Gate schedule 'off' does not prevent night close forced_position from Gate 1."""
        hass = _make_hass()
        cm = _make_cover_manager()
        orch = CoverOrchestrator(hass, cm, _make_model_manager())

        # Gate schedule is OFF
        sched_state = MagicMock()
        sched_state.state = "off"
        sched_state.attributes = {}
        hass.states.get = MagicMock(return_value=sched_state)

        room = _make_room(
            covers=["cover.blind1"],
            cover_schedules=[{"entity_id": "schedule.cover_time", "mode": "gate"}],
            covers_night_close=True,
            covers_night_position=0,
        )

        with (
            patch(
                "custom_components.roommind.managers.cover_orchestrator.resolve_schedule_index",
                return_value=0,
            ),
            patch(
                "custom_components.roommind.managers.cover_orchestrator.solar_elevation",
                return_value=-5.0,  # nighttime
            ),
        ):
            result = await orch.async_process(
                area_id="living_room",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=20.0,
                outdoor_temp=15.0,
                q_solar=0.0,
                predicted_peak_temp=20.0,
                has_override=False,
            )

        # Night close must still fire (Gate 1, before Gate 2.5)
        assert result.forced_reason == "night_close"
        call_kwargs = cm.evaluate.call_args
        assert call_kwargs[1].get("forced_position") == 0 or call_kwargs.kwargs.get("forced_position") == 0

    @pytest.mark.asyncio
    async def test_gate_entity_unavailable_keeps_solar_protection(self):
        """Gate schedule entity unavailable → solar_gated stays True (fail-safe)."""
        hass = _make_hass()
        cm = _make_cover_manager()
        orch = CoverOrchestrator(hass, cm, _make_model_manager())

        hass.states.get = MagicMock(return_value=None)

        room = _make_room(
            covers=["cover.blind1"],
            cover_schedules=[{"entity_id": "schedule.cover_time", "mode": "gate"}],
        )

        with patch(
            "custom_components.roommind.managers.cover_orchestrator.resolve_schedule_index",
            return_value=0,
        ):
            await orch.async_process(
                area_id="living_room",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=20.0,
                outdoor_temp=15.0,
                q_solar=0.3,
                predicted_peak_temp=22.0,
                has_override=False,
            )

        call_kwargs = cm.evaluate.call_args
        solar_gated = call_kwargs.kwargs.get("solar_gated", call_kwargs[1].get("solar_gated"))
        assert solar_gated is True


# ── Orientation ─────────────────────────────────────────────────────────

_BUILD_ORIENTED = "custom_components.roommind.managers.cover_orchestrator.build_oriented_solar_series"


class TestCoverOrientation:
    """Per-cover orientation: cover_orientations dict scales solar series."""

    @pytest.mark.asyncio
    @patch(_BUILD_SOLAR_SERIES, return_value=[0.5])
    async def test_orientation_empty_dict_no_scaling(self, mock_bss):
        """No cover_orientations → plain build_solar_series used."""
        hass = _make_hass()
        cm = _make_cover_manager()
        orch = CoverOrchestrator(hass, cm, _make_model_manager())

        room = _make_room(covers=["cover.blind1"])  # no cover_orientations key

        with patch(_BUILD_ORIENTED) as mock_oriented:
            await orch.async_process(
                area_id="living_room",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=20.0,
                outdoor_temp=None,
                q_solar=0.5,
                predicted_peak_temp=None,
                has_override=False,
            )

        mock_oriented.assert_not_called()

    @pytest.mark.asyncio
    async def test_orientation_with_azimuths_calls_oriented_series(self):
        """cover_orientations → build_oriented_solar_series used in Tier 2."""
        hass = _make_hass()
        cm = _make_cover_manager()
        orch = CoverOrchestrator(hass, cm, _make_model_manager())

        room = _make_room(
            covers=["cover.blind1"],
            cover_orientations={"cover.blind1": 180},
        )

        with patch(_BUILD_ORIENTED, return_value=[0.8]) as mock_oriented:
            await orch.async_process(
                area_id="living_room",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=20.0,
                outdoor_temp=None,
                q_solar=0.5,
                predicted_peak_temp=None,
                has_override=False,
            )

        mock_oriented.assert_called_once()
        # build_oriented_solar_series(lat, lon, n_blocks, surface_azimuths, …)
        # surface_azimuths is the 4th positional arg
        positional = mock_oriented.call_args[0]
        assert len(positional) >= 4 and positional[3] == [180.0]

    @pytest.mark.asyncio
    async def test_orientation_partial_mapping_uses_only_configured(self):
        """Only covers with an orientation entry contribute to _surface_azimuths."""
        hass = _make_hass()
        cm = _make_cover_manager()
        orch = CoverOrchestrator(hass, cm, _make_model_manager())

        room = _make_room(
            covers=["cover.blind1", "cover.blind2"],
            # Only blind1 has an orientation; blind2 is omitted
            cover_orientations={"cover.blind1": 90},
        )

        with patch(_BUILD_ORIENTED, return_value=[0.4]) as mock_oriented:
            await orch.async_process(
                area_id="living_room",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=20.0,
                outdoor_temp=None,
                q_solar=0.5,
                predicted_peak_temp=None,
                has_override=False,
            )

        mock_oriented.assert_called_once()

    @pytest.mark.asyncio
    @patch(_BUILD_SOLAR_SERIES, return_value=[0.5])
    async def test_orientation_all_covers_unmapped_no_oriented_call(self, mock_bss):
        """cover_orientations present but no covers match → plain series used."""
        hass = _make_hass()
        cm = _make_cover_manager()
        orch = CoverOrchestrator(hass, cm, _make_model_manager())

        room = _make_room(
            covers=["cover.blind1"],
            # Orientation key doesn't match any cover entity
            cover_orientations={"cover.other": 180},
        )

        with patch(_BUILD_ORIENTED) as mock_oriented:
            await orch.async_process(
                area_id="living_room",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=20.0,
                outdoor_temp=None,
                q_solar=0.5,
                predicted_peak_temp=None,
                has_override=False,
            )

        mock_oriented.assert_not_called()


# ── Outdoor min temp gate tests ──────────────────────────────────────


class TestOutdoorMinTempGate:
    @pytest.mark.asyncio
    async def test_outdoor_below_threshold_suppresses_solar(self):
        """When outdoor temp < covers_outdoor_min_temp, predicted peak is clamped to target."""
        cm = _make_cover_manager()
        cm.evaluate.return_value = CoverDecision(target_position=100, changed=False, reason="test")
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(covers=["cover.b"], covers_outdoor_min_temp=10.0)

        with patch.object(CoverOrchestrator, "_estimate_solar_peak_temp", return_value=26.0):
            await orch.async_process(
                area_id="lr",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=20.0,
                outdoor_temp=5.0,
                q_solar=0.8,
                predicted_peak_temp=None,
                has_override=False,
            )

        call_kwargs = cm.evaluate.call_args[1]
        # Gate neutralises by making peak == target, so excess == 0.
        # Assert the invariant, not the literal: cover_target moved with #418.
        assert call_kwargs["predicted_peak_temp"] == call_kwargs["target_temp"]

    @pytest.mark.asyncio
    async def test_outdoor_above_threshold_passes_through(self):
        """When outdoor temp >= threshold, prediction is unchanged."""
        cm = _make_cover_manager()
        cm.evaluate.return_value = CoverDecision(target_position=100, changed=False, reason="test")
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(covers=["cover.b"], covers_outdoor_min_temp=10.0)

        with patch.object(CoverOrchestrator, "_estimate_solar_peak_temp", return_value=26.0):
            await orch.async_process(
                area_id="lr",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=22.0,  # above heat target: no heating gate
                outdoor_temp=15.0,
                q_solar=0.8,
                predicted_peak_temp=None,
                has_override=False,
            )

        call_kwargs = cm.evaluate.call_args[1]
        assert call_kwargs["predicted_peak_temp"] == 26.0

    @pytest.mark.asyncio
    async def test_outdoor_min_temp_none_disables_gate(self):
        """covers_outdoor_min_temp=None means the gate is disabled."""
        cm = _make_cover_manager()
        cm.evaluate.return_value = CoverDecision(target_position=100, changed=False, reason="test")
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(covers=["cover.b"], covers_outdoor_min_temp=None)

        with patch.object(CoverOrchestrator, "_estimate_solar_peak_temp", return_value=26.0):
            await orch.async_process(
                area_id="lr",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=22.0,  # above heat target: no heating gate
                outdoor_temp=5.0,
                q_solar=0.8,
                predicted_peak_temp=None,
                has_override=False,
            )

        call_kwargs = cm.evaluate.call_args[1]
        assert call_kwargs["predicted_peak_temp"] == 26.0


# ── Night close elevation + offset tests ─────────────────────────────


class TestNightCloseElevationOffset:
    @pytest.mark.asyncio
    async def test_night_close_custom_elevation_not_reached(self):
        """Custom elevation threshold -6: at -3 degrees, night close NOT triggered."""
        cm = _make_cover_manager()
        cm.evaluate.return_value = CoverDecision(target_position=100, changed=False, reason="test")
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(
            covers=["cover.b"],
            covers_night_close=True,
            covers_night_close_elevation=-6,
            covers_night_position=0,
        )

        with patch("custom_components.roommind.managers.cover_orchestrator.solar_elevation", return_value=-3.0):
            await orch.async_process(
                area_id="lr",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=20.0,
                outdoor_temp=15.0,
                q_solar=0.0,
                predicted_peak_temp=None,
                has_override=False,
            )

        call_kwargs = cm.evaluate.call_args[1]
        assert call_kwargs["forced_position"] is None

    @pytest.mark.asyncio
    async def test_night_close_custom_elevation_reached(self):
        """Custom elevation threshold -6: at -7, night close triggered."""
        cm = _make_cover_manager()
        cm.evaluate.return_value = CoverDecision(target_position=0, changed=True, reason="forced")
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(
            covers=["cover.b"],
            covers_night_close=True,
            covers_night_close_elevation=-6,
            covers_night_position=5,
        )

        with patch("custom_components.roommind.managers.cover_orchestrator.solar_elevation", return_value=-7.0):
            await orch.async_process(
                area_id="lr",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=20.0,
                outdoor_temp=15.0,
                q_solar=0.0,
                predicted_peak_temp=None,
                has_override=False,
            )

        call_kwargs = cm.evaluate.call_args[1]
        assert call_kwargs["forced_position"] == 5
        assert call_kwargs["forced_reason"] == "night_close"

    @pytest.mark.asyncio
    async def test_night_close_offset_shifts_check_timestamp(self):
        """Positive offset checks elevation at an earlier timestamp."""
        cm = _make_cover_manager()
        cm.evaluate.return_value = CoverDecision(target_position=100, changed=False, reason="test")
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(
            covers=["cover.b"],
            covers_night_close=True,
            covers_night_close_offset_minutes=30,
            covers_night_position=0,
        )

        with (
            patch("custom_components.roommind.managers.cover_orchestrator.solar_elevation") as mock_elev,
            patch("custom_components.roommind.managers.cover_orchestrator.time") as mock_time,
        ):
            mock_time.time.return_value = 1000.0
            mock_elev.return_value = 2.0
            await orch.async_process(
                area_id="lr",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=20.0,
                outdoor_temp=15.0,
                q_solar=0.0,
                predicted_peak_temp=None,
                has_override=False,
            )

            call_ts = mock_elev.call_args[0][2]
            assert call_ts == 1000.0 - 30 * 60


# ── Per-cover min position correction tests ──────────────────────────


class TestPerCoverMinPositionCorrection:
    @pytest.mark.asyncio
    @patch("custom_components.roommind.managers.cover_orchestrator.CoverManager.async_apply", new_callable=AsyncMock)
    async def test_commanded_position_corrected_with_cover_min_positions(self, mock_apply):
        """When cover_min_positions is set and decision changes, commanded position is corrected."""
        cm = _make_cover_manager()
        cm.evaluate.return_value = CoverDecision(target_position=10, changed=True, reason="deploy")
        hass = _make_hass()
        positional_state = MagicMock()
        positional_state.attributes = {"supported_features": 15}
        hass.states.get = MagicMock(return_value=positional_state)
        orch = CoverOrchestrator(hass, cm, _make_model_manager())
        room = _make_room(
            covers=["cover.a", "cover.b"],
            cover_min_positions={"cover.a": 40},
        )

        with patch.object(CoverOrchestrator, "_estimate_solar_peak_temp", return_value=25.0):
            await orch.async_process(
                area_id="lr",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=20.0,
                outdoor_temp=15.0,
                q_solar=0.8,
                predicted_peak_temp=None,
                has_override=False,
            )

        # cover.a clamped to max(40, 10)=40, cover.b stays at 10 → avg=25
        assert cm.set_commanded_position.call_args[0] == ("lr", 25)

    @pytest.mark.asyncio
    @patch("custom_components.roommind.managers.cover_orchestrator.CoverManager.async_apply", new_callable=AsyncMock)
    async def test_correction_without_min_positions_uses_target(self, mock_apply):
        """Without cover_min_positions, expected position falls back to the decision's target."""
        cm = _make_cover_manager()
        cm.evaluate.return_value = CoverDecision(target_position=10, changed=True, reason="deploy")
        hass = _make_hass()
        positional_state = MagicMock()
        positional_state.attributes = {"supported_features": 15}
        hass.states.get = MagicMock(return_value=positional_state)
        orch = CoverOrchestrator(hass, cm, _make_model_manager())
        room = _make_room(covers=["cover.a"])

        with patch.object(CoverOrchestrator, "_estimate_solar_peak_temp", return_value=25.0):
            await orch.async_process(
                area_id="lr",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=20.0,
                outdoor_temp=15.0,
                q_solar=0.8,
                predicted_peak_temp=None,
                has_override=False,
            )

        cm.set_commanded_position.assert_called_once_with("lr", 10)

    @pytest.mark.asyncio
    async def test_night_close_negative_offset_closes_before_sunset(self):
        """Negative offset = close before sunset (check elevation in the future)."""
        cm = _make_cover_manager()
        cm.evaluate.return_value = CoverDecision(target_position=0, changed=True, reason="forced")
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(
            covers=["cover.b"],
            covers_night_close=True,
            covers_night_close_offset_minutes=-30,
            covers_night_position=0,
        )

        with (
            patch("custom_components.roommind.managers.cover_orchestrator.solar_elevation") as mock_elev,
            patch("custom_components.roommind.managers.cover_orchestrator.time") as mock_time,
        ):
            mock_time.time.return_value = 1000.0
            mock_elev.return_value = -2.0
            await orch.async_process(
                area_id="lr",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=20.0,
                outdoor_temp=15.0,
                q_solar=0.0,
                predicted_peak_temp=None,
                has_override=False,
            )

            call_ts = mock_elev.call_args[0][2]
            assert call_ts == 1000.0 + 30 * 60

        call_kwargs = cm.evaluate.call_args[1]
        assert call_kwargs["forced_position"] == 0
        assert call_kwargs["forced_reason"] == "night_close"

    @pytest.mark.asyncio
    async def test_night_close_positive_elevation_threshold(self):
        """Positive threshold (e.g. 5°): close before sunset while sun is still above horizon."""
        cm = _make_cover_manager()
        cm.evaluate.return_value = CoverDecision(target_position=0, changed=True, reason="forced")
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(
            covers=["cover.b"],
            covers_night_close=True,
            covers_night_close_elevation=5,
            covers_night_position=0,
        )

        with patch("custom_components.roommind.managers.cover_orchestrator.solar_elevation", return_value=3.0):
            await orch.async_process(
                area_id="lr",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=20.0,
                outdoor_temp=15.0,
                q_solar=0.0,
                predicted_peak_temp=None,
                has_override=False,
            )

        call_kwargs = cm.evaluate.call_args[1]
        assert call_kwargs["forced_position"] == 0
        assert call_kwargs["forced_reason"] == "night_close"


class TestBinaryCoverExpectedPosition:
    @pytest.mark.asyncio
    @patch("custom_components.roommind.managers.cover_orchestrator.CoverManager.async_apply", new_callable=AsyncMock)
    async def test_binary_cover_expected_zero_when_closing(self, mock_apply):
        """Binary cover (no SET_POSITION) commanded below 100 → expected reported 0."""
        hass = _make_hass()
        cm = _make_cover_manager()
        cm.evaluate.return_value = CoverDecision(target_position=39, changed=True, reason="deploy")
        binary_state = MagicMock()
        binary_state.attributes = {"supported_features": 3}
        hass.states.get = MagicMock(return_value=binary_state)
        orch = CoverOrchestrator(hass, cm, _make_model_manager())
        room = _make_room(covers=["cover.binary"], covers_auto_enabled=True)
        with patch.object(CoverOrchestrator, "_estimate_solar_peak_temp", return_value=25.0):
            await orch.async_process(
                area_id="lr",
                room=room,
                targets=TargetTemps(heat=21.0, cool=None),
                mode=MODE_HEATING,
                current_temp=22.0,
                outdoor_temp=20.0,
                q_solar=0.5,
                predicted_peak_temp=25.0,
                has_override=False,
            )
        cm.set_commanded_position.assert_called_once_with("lr", 0)

    @pytest.mark.asyncio
    @patch("custom_components.roommind.managers.cover_orchestrator.CoverManager.async_apply", new_callable=AsyncMock)
    async def test_mixed_room_expected_average(self, mock_apply):
        """Positional (39) + binary (0) → expected average 19."""
        hass = _make_hass()
        cm = _make_cover_manager()
        cm.evaluate.return_value = CoverDecision(target_position=39, changed=True, reason="deploy")
        positional = MagicMock()
        positional.attributes = {"supported_features": 15}
        binary = MagicMock()
        binary.attributes = {"supported_features": 3}
        hass.states.get = MagicMock(side_effect=lambda eid: positional if eid == "cover.pos" else binary)
        orch = CoverOrchestrator(hass, cm, _make_model_manager())
        room = _make_room(covers=["cover.pos", "cover.binary"], covers_auto_enabled=True)
        with patch.object(CoverOrchestrator, "_estimate_solar_peak_temp", return_value=25.0):
            await orch.async_process(
                area_id="lr",
                room=room,
                targets=TargetTemps(heat=21.0, cool=None),
                mode=MODE_HEATING,
                current_temp=22.0,
                outdoor_temp=20.0,
                q_solar=0.5,
                predicted_peak_temp=25.0,
                has_override=False,
            )
        cm.set_commanded_position.assert_called_once_with("lr", 19)

    @pytest.mark.asyncio
    async def test_unavailable_covers_skipped_no_correction(self):
        hass = _make_hass()
        cm = _make_cover_manager()
        cm.evaluate.return_value = CoverDecision(target_position=39, changed=True, reason="deploy")
        hass.states.get = MagicMock(return_value=None)
        orch = CoverOrchestrator(hass, cm, _make_model_manager())
        room = _make_room(covers=["cover.gone"], covers_auto_enabled=True)
        with patch.object(CoverOrchestrator, "_estimate_solar_peak_temp", return_value=25.0):
            await orch.async_process(
                area_id="lr",
                room=room,
                targets=TargetTemps(heat=21.0, cool=None),
                mode=MODE_HEATING,
                current_temp=22.0,
                outdoor_temp=20.0,
                q_solar=0.5,
                predicted_peak_temp=25.0,
                has_override=False,
            )
        cm.set_commanded_position.assert_not_called()

    @pytest.mark.asyncio
    @patch("custom_components.roommind.managers.cover_orchestrator.CoverManager.async_apply", new_callable=AsyncMock)
    async def test_binary_cover_expected_hundred_when_opening(self, mock_apply):
        """Binary cover (no SET_POSITION) commanded to 100 → expected reported 100."""
        hass = _make_hass()
        cm = _make_cover_manager()
        cm.evaluate.return_value = CoverDecision(target_position=100, changed=True, reason="low_solar")
        binary_state = MagicMock()
        binary_state.attributes = {"supported_features": 3}
        hass.states.get = MagicMock(return_value=binary_state)
        orch = CoverOrchestrator(hass, cm, _make_model_manager())
        room = _make_room(covers=["cover.binary"], covers_auto_enabled=True)
        with patch.object(CoverOrchestrator, "_estimate_solar_peak_temp", return_value=25.0):
            await orch.async_process(
                area_id="lr",
                room=room,
                targets=TargetTemps(heat=21.0, cool=None),
                mode=MODE_HEATING,
                current_temp=22.0,
                outdoor_temp=20.0,
                q_solar=0.5,
                predicted_peak_temp=25.0,
                has_override=False,
            )
        cm.set_commanded_position.assert_called_once_with("lr", 100)


# ── Orientation gate tests ───────────────────────────────────────────


class TestOrientationGate:
    @pytest.mark.asyncio
    async def test_sun_not_on_cover_side_suppresses_deployment(self):
        """When oriented q_solar < COVER_SOLAR_MIN, predicted peak is clamped to target."""
        cm = _make_cover_manager()
        cm.evaluate.return_value = CoverDecision(target_position=100, changed=False, reason="test")
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(
            covers=["cover.b"],
            cover_orientations={"cover.b": 135},  # SE
        )

        with (
            patch("custom_components.roommind.managers.cover_orchestrator.solar_azimuth", return_value=250.0),
            patch("custom_components.roommind.managers.cover_orchestrator.solar_elevation", return_value=20.0),
            patch("custom_components.roommind.managers.cover_orchestrator.surface_irradiance_factor", return_value=0.0),
            patch.object(CoverOrchestrator, "_estimate_solar_peak_temp", return_value=26.0),
        ):
            await orch.async_process(
                area_id="lr",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=22.0,
                outdoor_temp=20.0,
                q_solar=0.5,
                predicted_peak_temp=25.0,
                has_override=False,
            )

        call_kwargs = cm.evaluate.call_args[1]
        # Gate neutralises by making peak == target, so excess == 0.
        # Assert the invariant, not the literal: cover_target moved with #418.
        assert call_kwargs["predicted_peak_temp"] == call_kwargs["target_temp"]

    @pytest.mark.asyncio
    async def test_sun_on_cover_side_allows_deployment(self):
        """When oriented q_solar >= COVER_SOLAR_MIN, prediction passes through."""
        cm = _make_cover_manager()
        cm.evaluate.return_value = CoverDecision(target_position=100, changed=False, reason="test")
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(
            covers=["cover.b"],
            cover_orientations={"cover.b": 180},  # S
        )

        with (
            patch("custom_components.roommind.managers.cover_orchestrator.solar_azimuth", return_value=180.0),
            patch("custom_components.roommind.managers.cover_orchestrator.solar_elevation", return_value=45.0),
            patch("custom_components.roommind.managers.cover_orchestrator.surface_irradiance_factor", return_value=0.7),
            patch.object(CoverOrchestrator, "_estimate_solar_peak_temp", return_value=26.0),
        ):
            await orch.async_process(
                area_id="lr",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=22.0,
                outdoor_temp=20.0,
                q_solar=0.5,
                predicted_peak_temp=25.0,
                has_override=False,
            )

        call_kwargs = cm.evaluate.call_args[1]
        assert call_kwargs["predicted_peak_temp"] == 25.0

    @pytest.mark.asyncio
    async def test_no_orientation_no_gate(self):
        """Without orientation configured, the gate does not apply."""
        cm = _make_cover_manager()
        cm.evaluate.return_value = CoverDecision(target_position=100, changed=False, reason="test")
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(covers=["cover.b"])

        with patch.object(CoverOrchestrator, "_estimate_solar_peak_temp", return_value=26.0):
            await orch.async_process(
                area_id="lr",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_HEATING,
                current_temp=22.0,
                outdoor_temp=20.0,
                q_solar=0.5,
                predicted_peak_temp=25.0,
                has_override=False,
            )

        call_kwargs = cm.evaluate.call_args[1]
        assert call_kwargs["predicted_peak_temp"] == 25.0


# ── Shade first, cool the rest (rooms that can cool) ──────────────────

_TIME = "custom_components.roommind.managers.cover_orchestrator.time"
_AC_DEVICES = [{"entity_id": "climate.ac", "type": "ac", "role": "auto"}]


def _ac_room(**overrides) -> dict:
    return _make_room(covers=["cover.b"], devices=_AC_DEVICES, comfort_cool=24.5, **overrides)


async def _process(orch: CoverOrchestrator, room: dict, **overrides) -> None:
    kwargs = dict(
        area_id="lr",
        room=room,
        targets=TargetTemps(heat=21.0, cool=24.5),
        mode=MODE_IDLE,
        current_temp=24.3,
        outdoor_temp=28.0,
        q_solar=0.6,
        predicted_peak_temp=None,
        has_override=False,
    )
    kwargs.update(overrides)
    await orch.async_process(**kwargs)


class TestShadeBeforeCooling:
    @pytest.mark.asyncio
    async def test_idle_ac_room_aims_at_cool_target(self):
        """The cover target no longer follows the compressor: idle uses targets.cool too."""
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        with patch.object(CoverOrchestrator, "_estimate_solar_load_peak", return_value=24.0):
            await _process(orch, _ac_room(), targets=TargetTemps(heat=21.0, cool=23.0))
        assert cm.evaluate.call_args[1]["target_temp"] == 23.0

    @pytest.mark.asyncio
    async def test_heat_only_room_with_ac_keeps_comfort_ceiling(self):
        """An AC used only for heating cannot cool: #418 target and the old estimate stay."""
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        with (
            patch.object(CoverOrchestrator, "_estimate_solar_peak_temp", return_value=23.0) as old,
            patch.object(CoverOrchestrator, "_estimate_solar_load_peak") as new,
        ):
            await _process(orch, _ac_room(climate_mode="heat_only"), targets=TargetTemps(heat=22.0, cool=22.0))
        assert cm.evaluate.call_args[1]["target_temp"] == 24.5
        assert cm.evaluate.call_args[1]["predicted_peak_temp"] == 23.0
        old.assert_called_once()
        new.assert_not_called()

    @pytest.mark.asyncio
    async def test_solar_load_shades_although_plan_holds_the_room(self):
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        with patch.object(CoverOrchestrator, "_estimate_solar_load_peak", return_value=27.0):
            await _process(orch, _ac_room(), predicted_peak_temp=24.5)
        assert cm.evaluate.call_args[1]["predicted_peak_temp"] == pytest.approx(27.0)

    @pytest.mark.asyncio
    async def test_plan_peak_still_counts_for_a_weak_unit(self):
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        with patch.object(CoverOrchestrator, "_estimate_solar_load_peak", return_value=25.0):
            await _process(orch, _ac_room(), predicted_peak_temp=26.5)
        assert cm.evaluate.call_args[1]["predicted_peak_temp"] == pytest.approx(26.5)

    @pytest.mark.asyncio
    async def test_simple_mode_uses_the_same_estimate(self):
        """No plan (bang-bang): the solar-load estimate decides alone."""
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        with patch.object(CoverOrchestrator, "_estimate_solar_load_peak", return_value=26.0) as est:
            await _process(orch, _ac_room(), predicted_peak_temp=None)
        est.assert_called_once()
        assert cm.evaluate.call_args[1]["predicted_peak_temp"] == pytest.approx(26.0)

    @pytest.mark.asyncio
    async def test_heating_demand_suppresses_shading(self):
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        with patch.object(CoverOrchestrator, "_estimate_solar_load_peak", return_value=28.0):
            await _process(orch, _ac_room(), current_temp=20.5)
        assert cm.evaluate.call_args[1]["predicted_peak_temp"] == 24.5

    @pytest.mark.asyncio
    async def test_cool_only_room_shades_below_its_band_floor(self):
        """A cool_only room's heat side is a band floor, not heating demand (legacy heat == cool)."""
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        with patch.object(CoverOrchestrator, "_estimate_solar_load_peak", return_value=28.0):
            await _process(
                orch,
                _ac_room(climate_mode="cool_only"),
                current_temp=23.0,
                targets=TargetTemps(heat=24.5, cool=24.5),
            )
        assert cm.evaluate.call_args[1]["predicted_peak_temp"] > 24.5

    @pytest.mark.asyncio
    async def test_excess_rises_fast_and_falls_slowly(self):
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _ac_room()
        with patch(_TIME) as mock_t, patch.object(CoverOrchestrator, "_estimate_solar_load_peak") as est:
            mock_t.time.return_value = 1000.0
            est.return_value = 25.5  # excess 1.0
            await _process(orch, room)
            assert cm.evaluate.call_args[1]["predicted_peak_temp"] == pytest.approx(25.5)

            mock_t.time.return_value = 1000.0 + COVER_SMOOTHING_RISE_MINUTES * 60
            est.return_value = 27.5  # excess 3.0
            await _process(orch, room)
            rise = 1.0 + 2.0 * (1 - math.exp(-1))
            assert cm.evaluate.call_args[1]["predicted_peak_temp"] == pytest.approx(24.5 + rise)

            mock_t.time.return_value += COVER_SMOOTHING_MINUTES * 60
            est.return_value = 24.5  # excess 0.0
            await _process(orch, room)
            fall = rise * math.exp(-1)
            assert cm.evaluate.call_args[1]["predicted_peak_temp"] == pytest.approx(24.5 + fall)

    @pytest.mark.asyncio
    async def test_compressor_cycle_barely_moves_the_base_temperature(self):
        """A 0.6 K swing of the room temperature over one 10-minute cycle stays below 0.1 K."""
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _ac_room()
        with (
            patch(_TIME) as mock_t,
            patch.object(CoverOrchestrator, "_estimate_solar_load_peak", return_value=25.0) as est,
        ):
            for i, temp in enumerate([24.3, 23.7, 24.3]):
                mock_t.time.return_value = 1000.0 + i * 300
                await _process(orch, room, current_temp=temp)
            bases = [c.args[1] for c in est.call_args_list]
        assert max(bases) - min(bases) < 0.1

    @pytest.mark.asyncio
    async def test_remove_room_drops_smoothing_state(self):
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        with patch.object(CoverOrchestrator, "_estimate_solar_load_peak", return_value=26.0):
            await _process(orch, _ac_room())
        assert "lr" in orch._smoothed_temp and "lr" in orch._smoothed_excess
        orch.remove_room("lr")
        assert "lr" not in orch._smoothed_temp and "lr" not in orch._smoothed_excess

    @pytest.mark.asyncio
    async def test_missing_temperature_drops_smoothed_temp(self):
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        with patch.object(CoverOrchestrator, "_estimate_solar_load_peak", return_value=26.0) as est:
            await _process(orch, _ac_room())
            await _process(orch, _ac_room(), current_temp=None)
        assert "lr" not in orch._smoothed_temp
        assert est.call_args.args[1] is None

    def test_smooth_ignores_time_going_backwards(self):
        store: dict[str, tuple[float, float]] = {}
        assert CoverOrchestrator._smooth(store, "lr", 1.0, 100.0) == 1.0
        assert CoverOrchestrator._smooth(store, "lr", 5.0, 50.0) == 1.0


_AZIMUTH = "custom_components.roommind.managers.cover_orchestrator.solar_azimuth"
_N_COOL = int(COVER_COOLING_LOOKAHEAD_H * 60 / COVER_PREDICTION_DT_MINUTES)


def _input_h(series: list[float]) -> float:
    return sum(series) * COVER_PREDICTION_DT_MINUTES / 60.0


class TestEstimateSolarLoadPeak:
    def _orch(self, n_idle: int = 0, confident: bool = False) -> CoverOrchestrator:
        mm = _make_model_manager()
        mm.get_mode_counts.return_value = (n_idle, 10, 10)
        mm.get_prediction_std.return_value = 0.1 if confident else 1.0
        return CoverOrchestrator(_make_hass(), _make_cover_manager(), mm)

    def test_linear_counts_solar_input_over_the_near_horizon_from_the_capped_base(self):
        series = [0.6] * _N_COOL
        orch = self._orch()
        with patch(_BUILD_SOLAR_SERIES, return_value=series) as bs:
            result = orch._estimate_solar_load_peak("lr", 25.3, 24.5, 0.2, 30.0)
        assert bs.call_args.args[2] == _N_COOL
        assert result == pytest.approx(24.5 + COVER_DEFAULT_BETA_S * 0.6 * COVER_COOLING_LINEAR_H)

    def test_morning_sun_far_ahead_does_not_count(self):
        """Only the next hours count: a rising morning series gives a small estimate."""
        series = [0.05 * i / _N_COOL for i in range(_N_COOL)]
        orch = self._orch()
        with patch(_BUILD_SOLAR_SERIES, return_value=series):
            result = orch._estimate_solar_load_peak("lr", 24.5, 24.5, 0.05, 20.0)
        assert result - 24.5 < 0.2

    @patch(_BUILD_SOLAR_SERIES, return_value=[0.5] * _N_COOL)
    def test_linear_below_target_starts_at_room_temperature(self, _mock_solar):
        orch = self._orch()
        result = orch._estimate_solar_load_peak("lr", 22.0, 24.5, 0.5, 20.0)
        assert result == pytest.approx(22.0 + COVER_DEFAULT_BETA_S * 0.5 * COVER_COOLING_LINEAR_H)

    @patch(_BUILD_SOLAR_SERIES, return_value=[0.5] * _N_COOL)
    def test_no_room_temperature_starts_at_target(self, _mock_solar):
        orch = self._orch()
        result = orch._estimate_solar_load_peak("lr", None, 24.5, 0.5, 20.0)
        assert result == pytest.approx(24.5 + COVER_DEFAULT_BETA_S * 0.5 * COVER_COOLING_LINEAR_H)

    @patch(_BUILD_SOLAR_SERIES, return_value=[])
    def test_empty_series_falls_back_to_current_q_solar(self, _mock_solar):
        orch = self._orch()
        result = orch._estimate_solar_load_peak("lr", 24.5, 24.5, 0.4, 20.0)
        assert result == pytest.approx(24.5 + COVER_DEFAULT_BETA_S * 0.4 * COVER_COOLING_LINEAR_H)

    @patch(_BUILD_SOLAR_SERIES, return_value=[0.0, 0.0])
    def test_model_ignores_heat_from_outdoors(self, _mock_solar):
        """Above the target only the sun's share counts: shading cannot stop a hot outdoor temperature."""
        orch = self._orch(n_idle=COVER_MIN_IDLE_FOR_LEARNED, confident=True)
        model = MagicMock()
        model.predict_trajectory.side_effect = [[24.5, 26.0, 28.0], [24.5, 25.5, 27.0]]
        orch._model_manager.get_model.return_value = model
        result = orch._estimate_solar_load_peak("lr", 24.5, 24.5, 0.0, 32.0)
        # pointwise 24.5, 26.0 - 1.0, 28.0 - 2.5
        assert result == pytest.approx(25.5)
        assert "q_solar_series" not in model.predict_trajectory.call_args_list[1].kwargs

    @patch(_BUILD_SOLAR_SERIES, return_value=[0.0, 0.0])
    def test_model_below_target_counts_the_whole_rise(self, _mock_solar):
        orch = self._orch(n_idle=COVER_MIN_IDLE_FOR_LEARNED, confident=True)
        model = MagicMock()
        model.predict_trajectory.side_effect = [[23.0, 25.0, 27.0], [23.0, 23.2, 23.4]]
        orch._model_manager.get_model.return_value = model
        assert orch._estimate_solar_load_peak("lr", 23.0, 24.5, 0.0, 25.0) == pytest.approx(27.0)

    @patch(_BUILD_SOLAR_SERIES, return_value=[0.8] * _N_COOL)
    def test_linear_is_the_floor_for_a_model_still_learning_its_solar_gain(self, _mock_solar):
        orch = self._orch(n_idle=COVER_MIN_IDLE_FOR_LEARNED, confident=True)
        model = MagicMock()
        model.predict_trajectory.side_effect = [[24.5, 24.6, 24.7], [24.5, 24.6, 24.7]]
        orch._model_manager.get_model.return_value = model
        result = orch._estimate_solar_load_peak("lr", 24.5, 24.5, 0.8, 30.0)
        assert result == pytest.approx(24.5 + COVER_DEFAULT_BETA_S * 0.8 * COVER_COOLING_LINEAR_H)

    @patch(_BUILD_SOLAR_SERIES, return_value=[0.1] * _N_COOL)
    def test_model_raises_the_estimate_over_its_longer_horizon(self, _mock_solar):
        orch = self._orch(n_idle=COVER_MIN_IDLE_FOR_LEARNED, confident=True)
        model = MagicMock()
        model.predict_trajectory.side_effect = [[24.5, 25.5, 27.0], [24.5, 24.5, 24.5]]
        orch._model_manager.get_model.return_value = model
        assert orch._estimate_solar_load_peak("lr", 24.5, 24.5, 0.1, 30.0) == pytest.approx(27.0)

    @patch(_BUILD_SOLAR_SERIES, return_value=[0.5] * _N_COOL)
    def test_model_error_falls_back_to_linear(self, _mock_solar):
        orch = self._orch(n_idle=COVER_MIN_IDLE_FOR_LEARNED, confident=True)
        orch._model_manager.get_model.side_effect = RuntimeError("no model")
        result = orch._estimate_solar_load_peak("lr", 24.5, 24.5, 0.5, 30.0)
        assert result == pytest.approx(24.5 + COVER_DEFAULT_BETA_S * 0.5 * COVER_COOLING_LINEAR_H)

    def test_orientation_keeps_ghi_strength_while_the_sun_faces_the_window(self):
        orch = self._orch()
        series = [0.6] * _N_COOL
        with patch(_BUILD_SOLAR_SERIES, return_value=series), patch(_AZIMUTH, return_value=180.0):
            facing = orch._estimate_solar_load_peak("lr", 24.5, 24.5, 0.6, 30.0, [180.0])
        with patch(_BUILD_SOLAR_SERIES, return_value=series):
            unoriented = orch._estimate_solar_load_peak("lr", 24.5, 24.5, 0.6, 30.0)
        assert facing == pytest.approx(unoriented)

    def test_orientation_drops_sun_behind_the_facade(self):
        orch = self._orch()
        with patch(_BUILD_SOLAR_SERIES, return_value=[0.6] * _N_COOL), patch(_AZIMUTH, return_value=180.0):
            result = orch._estimate_solar_load_peak("lr", 24.5, 24.5, 0.6, 30.0, [0.0])
        assert result == pytest.approx(24.5)

    def test_orientation_follows_the_sun_through_the_horizon(self):
        """Sun reaches the facade half way through the horizon: half the input counts."""
        orch = self._orch()
        azimuths = [90.0] * (_N_COOL // 2) + [180.0] * (_N_COOL - _N_COOL // 2)
        with (
            patch(_BUILD_SOLAR_SERIES, return_value=[0.6] * _N_COOL),
            patch(_AZIMUTH, side_effect=azimuths) as az,
        ):
            result = orch._estimate_solar_load_peak("lr", 24.5, 24.5, 0.6, 30.0, [180.0])
        assert az.call_count == _N_COOL
        n_linear = int(COVER_COOLING_LINEAR_H * 60 / COVER_PREDICTION_DT_MINUTES)
        expected = COVER_DEFAULT_BETA_S * _input_h([0.6] * max(0, n_linear - _N_COOL // 2))
        assert result == pytest.approx(24.5 + expected)


class TestSunlitWeight:
    @pytest.mark.parametrize(
        ("sun", "facade", "weight"),
        [
            (180.0, 180.0, 1.0),
            (180.0 + COVER_DIRECT_SUN_ANGLE_DEG, 180.0, 1.0),
            (90.0, 180.0, 0.0),
            (0.0, 180.0, 0.0),
            (350.0, 0.0, 1.0),
        ],
    )
    def test_weight(self, sun, facade, weight):
        assert CoverOrchestrator._sunlit_weight(sun, [facade]) == pytest.approx(weight, abs=1e-9)

    def test_partial_between_full_angle_and_parallel(self):
        w = CoverOrchestrator._sunlit_weight(180.0 + 75.0, [180.0])
        assert 0.0 < w < 1.0

    def test_corner_room_averages_the_covers(self):
        assert CoverOrchestrator._sunlit_weight(180.0, [180.0, 0.0]) == pytest.approx(0.5)


class TestShadeByNeedWiring:
    @pytest.mark.asyncio
    async def test_room_that_cools_shades_by_need(self):
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        with patch.object(CoverOrchestrator, "_estimate_solar_load_peak", return_value=26.0):
            await _process(orch, _ac_room())
        assert cm.evaluate.call_args[1]["shade_by_need"] is True

    @pytest.mark.asyncio
    async def test_room_without_cooling_keeps_the_old_mapping(self):
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        with patch.object(CoverOrchestrator, "_estimate_solar_peak_temp", return_value=26.0):
            await _process(orch, _make_room(covers=["cover.b"]))
        assert cm.evaluate.call_args[1]["shade_by_need"] is False

    @pytest.mark.asyncio
    async def test_sun_not_on_the_facade_now_keeps_the_cover_open(self):
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _ac_room(cover_orientations={"cover.b": 0})
        with (
            patch.object(CoverOrchestrator, "_estimate_solar_load_peak", return_value=28.0),
            patch(_AZIMUTH, return_value=180.0),
        ):
            await _process(orch, room, q_solar=0.8)
        assert cm.evaluate.call_args[1]["predicted_peak_temp"] == 24.5

    @pytest.mark.asyncio
    async def test_sun_on_the_facade_uses_full_ghi_for_the_gate(self):
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _ac_room(cover_orientations={"cover.b": 180})
        with (
            patch.object(CoverOrchestrator, "_estimate_solar_load_peak", return_value=28.0),
            patch(_AZIMUTH, return_value=200.0),
        ):
            await _process(orch, room, q_solar=0.2)
        assert cm.evaluate.call_args[1]["predicted_peak_temp"] == pytest.approx(28.0)


# ── TestWindowHold (#268) ─────────────────────────────────────────────

_SET_POSITION = 4


def _position_cover(position: int) -> MagicMock:
    s = MagicMock()
    s.state = "open" if position > 0 else "closed"
    s.attributes = {"current_position": position, "supported_features": _SET_POSITION}
    return s


def _binary_cover(state: str) -> MagicMock:
    s = MagicMock()
    s.state = state
    s.attributes = {"supported_features": 3}
    return s


async def _process_night(orch: CoverOrchestrator, room: dict, *, window_open: bool, elevation: float = -5.0):
    with patch(
        "custom_components.roommind.managers.cover_orchestrator.solar_elevation",
        return_value=elevation,
    ):
        return await orch.async_process(
            area_id="living_room",
            room=room,
            targets=TargetTemps(heat=21.0, cool=24.0),
            mode=MODE_IDLE,
            current_temp=21.0,
            outdoor_temp=15.0,
            q_solar=0.0,
            predicted_peak_temp=21.0,
            has_override=False,
            window_open=window_open,
        )


class TestWindowHold:
    """An open window keeps RoomMind from lowering the room's covers (#268/#370)."""

    def _setup(self, states: dict, **room_kw):
        from custom_components.roommind.managers.cover_manager import CoverManager

        hass = _make_hass()
        hass.states.get = MagicMock(side_effect=states.get)
        hass.services.async_call = AsyncMock()
        orch = CoverOrchestrator(hass, CoverManager(), _make_model_manager())
        room = _make_room(
            **{
                "covers": list(states),
                "covers_night_close": True,
                "covers_night_position": 0,
                "covers_window_hold": True,
                **room_kw,
            }
        )
        orch.read_positions("living_room", room)
        return hass, orch, room

    @pytest.mark.asyncio
    async def test_night_close_waits_while_window_open(self):
        hass, orch, room = self._setup({"cover.blind1": _position_cover(100)})

        result = await _process_night(orch, room, window_open=True)

        hass.services.async_call.assert_not_called()
        assert result.decision.changed is False
        assert result.decision.reason == "window_hold"
        # The night close hint must not claim the cover is closing
        assert result.forced_reason == ""

    @pytest.mark.asyncio
    async def test_night_close_follows_once_window_closed(self):
        hass, orch, room = self._setup({"cover.blind1": _position_cover(100)})
        await _process_night(orch, room, window_open=True)

        result = await _process_night(orch, room, window_open=False)

        assert result.decision.changed is True
        assert result.decision.target_position == 0
        assert result.forced_reason == "night_close"
        hass.services.async_call.assert_awaited_once()
        assert hass.services.async_call.await_args.args[1] == "set_cover_position"

    @pytest.mark.asyncio
    async def test_hold_leaves_cover_state_untouched(self):
        """A held move must not count as RoomMind's own position or arm a user override."""
        hass, orch, room = self._setup({"cover.blind1": _position_cover(100)})
        cm = orch._cover_manager
        before = cm._get_state("living_room")
        snapshot = (before.last_commanded_position, before.owned, before.last_was_forced, before.current_position)

        await _process_night(orch, room, window_open=True)
        orch.read_positions("living_room", room)

        after = cm._get_state("living_room")
        assert (
            after.last_commanded_position,
            after.owned,
            after.last_was_forced,
            after.current_position,
        ) == snapshot
        assert cm.is_user_override_active("living_room") is False

    @pytest.mark.asyncio
    async def test_opening_is_not_held(self):
        """Raising a cover cannot hit the window; daylight retract goes out with the window open."""
        hass, orch, room = self._setup({"cover.blind1": _position_cover(100)})
        await _process_night(orch, room, window_open=False)  # closes to 0
        hass.states.get = MagicMock(side_effect={"cover.blind1": _position_cover(0)}.get)
        orch.read_positions("living_room", room)
        hass.services.async_call.reset_mock()

        result = await _process_night(orch, room, window_open=True, elevation=10.0)

        assert result.decision.changed is True
        assert result.decision.target_position == 100

    @pytest.mark.asyncio
    async def test_one_cover_going_down_holds_the_room(self):
        """The average can rise while a single cover would still be lowered."""
        states = {"cover.a": _position_cover(100), "cover.b": _position_cover(0)}
        hass, orch, room = self._setup(states, covers_night_position=60)

        result = await _process_night(orch, room, window_open=True)

        assert result.decision.reason == "window_hold"
        hass.services.async_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_per_cover_minimum_counts(self):
        """A cover whose own minimum keeps it where it is does not move down."""
        states = {"cover.a": _position_cover(50)}
        hass, orch, room = self._setup(states, covers_night_position=0, cover_min_positions={"cover.a": 50})

        result = await _process_night(orch, room, window_open=True)

        assert result.decision.reason != "window_hold"

    @pytest.mark.asyncio
    async def test_binary_cover_close_is_held(self):
        hass, orch, room = self._setup({"cover.a": _binary_cover("open")})

        result = await _process_night(orch, room, window_open=True)

        assert result.decision.reason == "window_hold"
        hass.services.async_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_cover_without_known_position_is_held(self):
        s = MagicMock()
        s.state = "unknown"
        s.attributes = {"supported_features": _SET_POSITION}
        hass, orch, room = self._setup({"cover.a": s})

        result = await _process_night(orch, room, window_open=True)

        assert result.decision.reason == "window_hold"

    @pytest.mark.asyncio
    async def test_switch_off_keeps_old_behaviour(self):
        hass, orch, room = self._setup({"cover.blind1": _position_cover(100)})
        room["covers_window_hold"] = False

        result = await _process_night(orch, room, window_open=True)

        assert result.decision.changed is True
        assert result.decision.target_position == 0

    @pytest.mark.asyncio
    async def test_missing_field_keeps_old_behaviour(self):
        hass, orch, room = self._setup({"cover.blind1": _position_cover(100)})
        del room["covers_window_hold"]

        result = await _process_night(orch, room, window_open=True)

        assert result.decision.changed is True

    @pytest.mark.asyncio
    async def test_solar_deploy_is_held(self):
        hass, orch, room = self._setup({"cover.blind1": _position_cover(100)}, covers_night_close=False)

        with patch.object(CoverOrchestrator, "_estimate_solar_peak_temp", return_value=27.0):
            result = await orch.async_process(
                area_id="living_room",
                room=room,
                targets=TargetTemps(heat=21.0, cool=24.0),
                mode=MODE_IDLE,
                current_temp=23.0,
                outdoor_temp=25.0,
                q_solar=0.8,
                predicted_peak_temp=None,
                has_override=False,
                window_open=True,
            )

        assert result.decision.reason == "window_hold"
        hass.services.async_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_raising_with_an_unknown_cover_is_not_held(self):
        """A cover without a reading must not block sending everything fully open."""
        unknown = MagicMock()
        unknown.state = "unavailable"
        unknown.attributes = {"supported_features": _SET_POSITION}
        states = {"cover.a": _position_cover(100), "cover.b": unknown}
        hass, orch, room = self._setup(states)
        await _process_night(orch, room, window_open=False)  # closes to 0
        states["cover.a"] = _position_cover(0)
        orch.read_positions("living_room", room)

        result = await _process_night(orch, room, window_open=True, elevation=10.0)

        assert result.decision.changed is True
        assert result.decision.target_position == 100

    @pytest.mark.asyncio
    async def test_binary_cover_opening_is_not_held(self):
        states = {"cover.a": _binary_cover("open")}
        hass, orch, room = self._setup(states)
        await _process_night(orch, room, window_open=False)  # close_cover
        states["cover.a"] = _binary_cover("closed")
        orch.read_positions("living_room", room)

        result = await _process_night(orch, room, window_open=True, elevation=10.0)

        assert result.decision.changed is True
        assert hass.services.async_call.await_args.args[1] == "open_cover"

    def test_cover_without_state_is_skipped(self):
        hass, orch, room = self._setup({"cover.a": _position_cover(100)})
        hass.states.get = MagicMock(return_value=None)
        assert orch._lowers_any(["cover.a"], 0, {}) is False

    @pytest.mark.asyncio
    async def test_held_solar_deploy_follows_once_window_closed(self):
        hass, orch, room = self._setup({"cover.blind1": _position_cover(100)}, covers_night_close=False)

        async def solar(window_open: bool):
            with patch.object(CoverOrchestrator, "_estimate_solar_peak_temp", return_value=27.0):
                return await orch.async_process(
                    area_id="living_room",
                    room=room,
                    targets=TargetTemps(heat=21.0, cool=24.0),
                    mode=MODE_IDLE,
                    current_temp=23.0,
                    outdoor_temp=25.0,
                    q_solar=0.8,
                    predicted_peak_temp=None,
                    has_override=False,
                    window_open=window_open,
                )

        held = await solar(True)
        state = orch._cover_manager._get_state("living_room")
        assert held.decision.reason == "window_hold"
        assert state.baseline_position is None and state.owned is False

        result = await solar(False)

        assert result.decision.changed is True
        assert result.decision.target_position < 100
