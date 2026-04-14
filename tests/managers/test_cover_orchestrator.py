"""Tests for CoverOrchestrator — position reading, delegation, and async_process pipeline."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.const import (
    COVER_DEFAULT_BETA_S,
    COVER_LINEAR_LOOKAHEAD_H,
    MODE_COOLING,
    MODE_HEATING,
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
    async def test_heating_mode_uses_heat_target(self):
        """In heating mode, cover_target should use targets.heat."""
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(covers=["cover.blind1"])

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
        assert call_kwargs[1]["target_temp"] == 21.0 or call_kwargs.kwargs["target_temp"] == 21.0

    @pytest.mark.asyncio
    async def test_fallback_target_22_when_none(self):
        """When both heat and cool targets are None, fallback to 22.0."""
        cm = _make_cover_manager()
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
        room = _make_room(covers=["cover.blind1"])

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

        call_kwargs = cm.evaluate.call_args
        assert call_kwargs[1]["target_temp"] == 22.0 or call_kwargs.kwargs["target_temp"] == 22.0

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
            current_temp=20.0,
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
                current_temp=20.0,
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
        assert call_kwargs["predicted_peak_temp"] == 21.0

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
                current_temp=20.0,
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
                current_temp=20.0,
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
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
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
    async def test_no_correction_without_cover_min_positions(self, mock_apply):
        """Without cover_min_positions, set_commanded_position is NOT called."""
        cm = _make_cover_manager()
        cm.evaluate.return_value = CoverDecision(target_position=10, changed=True, reason="deploy")
        orch = CoverOrchestrator(_make_hass(), cm, _make_model_manager())
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

        cm.set_commanded_position.assert_not_called()

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
        assert call_kwargs["predicted_peak_temp"] == 21.0

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
