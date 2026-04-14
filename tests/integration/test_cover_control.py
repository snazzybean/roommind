"""Integration: cover/blind control feature with coordinator cycles."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.const import HISTORY_WRITE_CYCLES
from custom_components.roommind.managers.cover_manager import compute_shading_factor

from .conftest import ROOM_LIVING, make_hass_states, setup_room

ROOM_WITH_COVERS = {
    **ROOM_LIVING,
    "covers": ["cover.lr_blind"],
    "covers_auto_enabled": False,
    "covers_deploy_threshold": 1.5,
    "covers_min_position": 0,
}

ROOM_WITH_COVERS_AUTO = {
    **ROOM_WITH_COVERS,
    "covers_auto_enabled": True,
}


class TestCoverIntegration:
    @pytest.mark.asyncio
    async def test_room_without_covers_unaffected(self, coordinator, real_store):
        """Room with no covers configured behaves exactly as before."""
        await setup_room(real_store)

        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room"]
        assert room["blind_position"] is None
        assert room["cover_auto_paused"] is False
        assert room["target_temp"] == 21.0
        assert room["mode"] in ("heating", "idle")
        # No cover service calls
        for call in coordinator.hass.services.async_call.call_args_list:
            assert call[0][0] != "cover", f"Unexpected cover call: {call}"

    @pytest.mark.asyncio
    async def test_covers_read_position_from_ha_state(self, coordinator, real_store):
        """Cover position is read from HA entity state into room_state."""
        await setup_room(real_store, ROOM_WITH_COVERS)
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                extra={
                    "cover.lr_blind": ("open", {"current_position": 60, "supported_features": 4}),
                },
            )
        )

        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room"]
        assert room["blind_position"] == 60
        assert room["cover_auto_paused"] is False
        # Auto disabled -> no cover service calls
        for call in coordinator.hass.services.async_call.call_args_list:
            assert call[0][0] != "cover", f"Unexpected cover call: {call}"

    @pytest.mark.asyncio
    async def test_covers_auto_disabled_no_service_calls(self, coordinator, real_store):
        """Auto disabled means no cover service calls even with hot temps."""
        await setup_room(real_store, ROOM_WITH_COVERS)
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                temp="28.0",
                outdoor_temp="35.0",
                extra={
                    "cover.lr_blind": ("open", {"current_position": 100, "supported_features": 4}),
                },
            )
        )

        await coordinator._async_update_data()

        for call in coordinator.hass.services.async_call.call_args_list:
            assert call[0][0] != "cover", f"Unexpected cover call: {call}"

    @pytest.mark.asyncio
    async def test_shading_factor_computed_from_cover_positions(self, coordinator, real_store):
        """Shading factor and average blind_position computed from multiple covers."""
        room = {
            **ROOM_LIVING,
            "covers": ["cover.blind1", "cover.blind2"],
            "covers_auto_enabled": False,
            "covers_deploy_threshold": 1.5,
            "covers_min_position": 0,
            "covers_outdoor_min_temp": 10.0,
        }
        await setup_room(real_store, room)
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                extra={
                    "cover.blind1": ("closed", {"current_position": 0, "supported_features": 4}),
                    "cover.blind2": ("open", {"current_position": 100, "supported_features": 4}),
                },
            )
        )

        # Verify the pure function
        factor = compute_shading_factor([0, 100])
        assert abs(factor - 0.575) < 0.01

        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room"]
        assert room_state["blind_position"] == 50  # average of 0 and 100

    @pytest.mark.asyncio
    async def test_cover_auto_paused_when_user_override_active(self, coordinator, real_store):
        """User manually opening cover triggers auto pause."""
        await setup_room(real_store, ROOM_WITH_COVERS_AUTO)

        # First cycle: cover at position 30 (as if auto commanded)
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                extra={
                    "cover.lr_blind": ("open", {"current_position": 30, "supported_features": 4}),
                },
            )
        )
        await coordinator._async_update_data()

        # Simulate auto having commanded position 30 (both state fields must match)
        coordinator._cover_manager._states["living_room"].last_commanded_position = 30
        coordinator._cover_manager._states["living_room"].current_position = 30
        coordinator._cover_manager._states["living_room"].last_command_ts = 0.0  # settle window past

        # Second cycle: user opened cover to 100 (simulating manual override)
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                extra={
                    "cover.lr_blind": ("open", {"current_position": 100, "supported_features": 4}),
                },
            )
        )
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room"]
        assert room["cover_auto_paused"] is True

    @pytest.mark.asyncio
    async def test_room_removed_cleans_up_cover_state(self, coordinator, real_store):
        """Removing a room cleans up cover manager state."""
        await setup_room(real_store, ROOM_WITH_COVERS)
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                extra={
                    "cover.lr_blind": ("open", {"current_position": 50, "supported_features": 4}),
                },
            )
        )

        await coordinator._async_update_data()

        # Verify state exists
        assert "living_room" in coordinator._cover_manager._states

        # Remove room
        mock_registry = MagicMock()
        mock_registry.entities = MagicMock()
        mock_registry.entities.values.return_value = []
        with (
            patch(
                "homeassistant.helpers.entity_registry.async_get",
                return_value=mock_registry,
            ),
            patch.object(coordinator, "async_request_refresh", new_callable=AsyncMock),
        ):
            await coordinator.async_room_removed("living_room")

        assert "living_room" not in coordinator._cover_manager._states

    @pytest.mark.asyncio
    async def test_blind_position_recorded_in_history(self, coordinator, real_store):
        """History record includes blind_position after enough cycles."""
        await setup_room(real_store, ROOM_WITH_COVERS)
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                extra={
                    "cover.lr_blind": ("open", {"current_position": 75, "supported_features": 4}),
                },
            )
        )

        # Mock the history store
        mock_history = MagicMock()
        mock_history.record = MagicMock()
        mock_history.rotate = MagicMock()
        coordinator._history_store = mock_history

        # Run enough cycles to trigger history write
        for _ in range(HISTORY_WRITE_CYCLES + 1):
            await coordinator._async_update_data()

        # Verify record was called with blind_position
        assert mock_history.record.called
        record_call = mock_history.record.call_args
        record_data = record_call[0][1]
        assert "blind_position" in record_data
        assert record_data["blind_position"] == 75

    @pytest.mark.asyncio
    async def test_cover_position_none_for_unavailable_entity(self, coordinator, real_store):
        """Unavailable cover entity gracefully degrades — no crash, default position."""
        await setup_room(real_store, ROOM_WITH_COVERS)
        # cover.lr_blind returns None from hass.states.get (unavailable)
        coordinator.hass.states.get = MagicMock(side_effect=make_hass_states())

        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room"]
        # Entity unavailable means no position read from HA; CoverManager returns
        # its default (100 = fully open). The key point: no crash on unavailable entity.
        assert room["blind_position"] is not None
        # No cover service calls despite entity being unavailable
        for call in coordinator.hass.services.async_call.call_args_list:
            assert call[0][0] != "cover", f"Unexpected cover call: {call}"

    @pytest.mark.asyncio
    async def test_cover_binary_only_entity_reads_state(self, coordinator, real_store):
        """Cover without current_position attribute falls back to state-based position."""
        room = {
            **ROOM_LIVING,
            "covers": ["cover.simple"],
            "covers_auto_enabled": False,
            "covers_deploy_threshold": 1.5,
            "covers_min_position": 0,
            "covers_outdoor_min_temp": 10.0,
        }
        await setup_room(real_store, room)
        # Entity has no current_position, just state "closed"
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                extra={
                    "cover.simple": ("closed", {"supported_features": 0}),
                },
            )
        )

        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room"]
        assert room_state["blind_position"] == 0

    @pytest.mark.asyncio
    async def test_cover_multi_schedule_resolution(self, coordinator, real_store):
        """Cover forced position resolved from multi-schedule with selector."""
        room = {
            **ROOM_WITH_COVERS_AUTO,
            "cover_schedules": [
                {"entity_id": "schedule.cover_night"},
                {"entity_id": "schedule.cover_privacy"},
            ],
            "cover_schedule_selector_entity": "input_boolean.cover_mode",
        }
        await setup_room(real_store, room)
        # Selector OFF → schedule #1 (index 0), schedule entity is "on" → forced
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                extra={
                    "cover.lr_blind": ("open", {"current_position": 100, "supported_features": 4}),
                    "schedule.cover_night": ("on", {"position": 0}),
                    "schedule.cover_privacy": ("off", {}),
                    "input_boolean.cover_mode": ("off", {}),
                },
            )
        )

        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room"]
        assert room_state["cover_forced_reason"] == "schedule_active"
        assert room_state["active_cover_schedule_index"] == 0

    @pytest.mark.asyncio
    async def test_cover_multi_schedule_selector_switches(self, coordinator, real_store):
        """Selector ON switches to schedule #2."""
        room = {
            **ROOM_WITH_COVERS_AUTO,
            "cover_schedules": [
                {"entity_id": "schedule.cover_night"},
                {"entity_id": "schedule.cover_privacy"},
            ],
            "cover_schedule_selector_entity": "input_boolean.cover_mode",
        }
        await setup_room(real_store, room)
        # Selector ON → schedule #2 (index 1), schedule entity is "on" → forced
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                extra={
                    "cover.lr_blind": ("open", {"current_position": 100, "supported_features": 4}),
                    "schedule.cover_night": ("off", {}),
                    "schedule.cover_privacy": ("on", {"position": 30}),
                    "input_boolean.cover_mode": ("on", {}),
                },
            )
        )

        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room"]
        assert room_state["cover_forced_reason"] == "schedule_active"
        assert room_state["active_cover_schedule_index"] == 1

    @pytest.mark.asyncio
    async def test_covers_deploy_without_mpc_via_solar_prediction(self, coordinator, real_store):
        """Covers deploy via simple solar prediction even without MPC active."""
        await setup_room(real_store, ROOM_WITH_COVERS_AUTO)
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                temp="24.0",
                outdoor_temp="30.0",
                extra={
                    "cover.lr_blind": ("open", {"current_position": 100, "supported_features": 4}),
                },
            )
        )

        # Mock solar computation to return a known positive value (time-independent)
        with patch(
            "custom_components.roommind.coordinator.compute_q_solar_norm",
            return_value=0.8,
        ):
            await coordinator._async_update_data()

        # With temp=24, q_solar=0.8, linear fallback: 24 + 3.0*0.8*1.0 = 26.4
        # excess = 26.4 - 21.0 = 5.4 > threshold 1.5 → deploy
        cover_calls = [c for c in coordinator.hass.services.async_call.call_args_list if c[0][0] == "cover"]
        assert len(cover_calls) > 0, "Expected cover deploy via solar prediction"

    @pytest.mark.asyncio
    async def test_binary_cover_open_state_contributes_position(self, coordinator, real_store):
        """Binary cover in 'open' state should contribute position 100."""
        room = {
            **ROOM_LIVING,
            "covers": ["cover.position_blind", "cover.binary_blind"],
            "covers_auto_enabled": False,
            "covers_deploy_threshold": 1.5,
            "covers_min_position": 0,
            "covers_outdoor_min_temp": 10.0,
        }
        await setup_room(real_store, room)
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                extra={
                    # Position cover at 0 (closed), binary cover "open" (no current_position)
                    "cover.position_blind": ("closed", {"current_position": 0, "supported_features": 4}),
                    "cover.binary_blind": ("open", {"supported_features": 0}),
                },
            )
        )

        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room"]
        # Average of [0, 100] = 50
        assert room_state["blind_position"] == 50

    @pytest.mark.asyncio
    async def test_override_gate_suppresses_cover_control(self, coordinator, real_store):
        """Active climate override prevents cover auto-control (override gate)."""
        import time as _time

        await setup_room(real_store, ROOM_WITH_COVERS_AUTO)
        # Set override via async_update_room (like the WS override/set endpoint does)
        await real_store.async_update_room(
            "living_room",
            {
                "override_temp": 25.0,
                "override_until": _time.time() + 3600,
                "override_type": "boost",
            },
        )
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                temp="24.0",
                outdoor_temp="30.0",
                extra={
                    "cover.lr_blind": ("open", {"current_position": 100, "supported_features": 4}),
                },
            )
        )

        with patch(
            "custom_components.roommind.coordinator.compute_q_solar_norm",
            return_value=0.8,
        ):
            await coordinator._async_update_data()

        # With override active, covers should NOT be deployed despite solar
        cover_calls = [c for c in coordinator.hass.services.async_call.call_args_list if c[0][0] == "cover"]
        assert len(cover_calls) == 0, "No cover calls expected when override is active"

    @pytest.mark.asyncio
    async def test_solar_overheating_deploys_in_cold_weather(self, coordinator, real_store):
        """Covers deploy when solar overheats room, even if outdoor temp is 5C (cold-weather gate removed)."""
        await setup_room(real_store, ROOM_WITH_COVERS_AUTO)
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                temp="23.0",
                outdoor_temp="5.0",
                extra={
                    "cover.lr_blind": ("open", {"current_position": 100, "supported_features": 4}),
                },
            )
        )

        # High solar irradiance causing overheating despite cold outdoor temp
        with patch(
            "custom_components.roommind.coordinator.compute_q_solar_norm",
            return_value=0.9,
        ):
            await coordinator._async_update_data()

        # Linear fallback: 23 + 3.0*0.9*1.0 = 25.7
        # excess = 25.7 - 21.0 = 4.7 > threshold 1.5 → deploy
        # Old behavior would have blocked this (outdoor 5 < gate 10)
        cover_calls = [c for c in coordinator.hass.services.async_call.call_args_list if c[0][0] == "cover"]
        assert len(cover_calls) > 0, "Covers should deploy despite cold outdoor temp when solar causes overheating"

    @pytest.mark.asyncio
    async def test_sunrise_holds_covers_when_peak_predicted(self, coordinator, real_store):
        """At sunrise (low q_solar), covers stay closed if forecast predicts overheating."""
        room = {
            **ROOM_WITH_COVERS_AUTO,
            "covers_night_close": True,
            "covers_night_position": 0,
        }
        await setup_room(real_store, room)

        # Cycle 1: Night — elevation <= 0, forced night_close to position 0
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                temp="21.0",
                outdoor_temp="4.0",
                extra={
                    "cover.lr_blind": ("closed", {"current_position": 0, "supported_features": 4}),
                },
            )
        )
        with (
            patch(
                "custom_components.roommind.coordinator.compute_q_solar_norm",
                return_value=0.0,
            ),
            patch(
                "custom_components.roommind.managers.cover_orchestrator.solar_elevation",
                return_value=-5.0,
            ),
        ):
            await coordinator._async_update_data()

        coordinator.hass.services.async_call.reset_mock()

        # Cycle 2: Sunrise — elevation > 0 (night_close ends), q_solar still very low
        # Predicted peak via linear fallback: 21 + 3.0*0.05*1.0 = 21.15 (below threshold)
        # BUT with higher solar, MPC/RC would predict higher peak.
        # We mock q_solar=0.05 (below COVER_SOLAR_MIN=0.15) and use a high solar for
        # the linear fallback by mocking _estimate_solar_peak_temp to return a hot peak.
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                temp="21.0",
                outdoor_temp="4.0",
                extra={
                    "cover.lr_blind": ("closed", {"current_position": 0, "supported_features": 4}),
                },
            )
        )
        with (
            patch(
                "custom_components.roommind.coordinator.compute_q_solar_norm",
                return_value=0.05,
            ),
            patch(
                "custom_components.roommind.managers.cover_orchestrator.solar_elevation",
                return_value=3.0,
            ),
            patch.object(
                coordinator._cover_orchestrator,
                "_estimate_solar_peak_temp",
                return_value=26.0,
            ),
        ):
            await coordinator._async_update_data()

        # Covers should NOT open — solar_threat detected (peak 26 > target+1.5 AND > current 21)
        cover_calls = [c for c in coordinator.hass.services.async_call.call_args_list if c[0][0] == "cover"]
        assert len(cover_calls) == 0, (
            "Covers should stay closed at sunrise when forecast predicts overheating, "
            f"but got cover calls: {cover_calls}"
        )
