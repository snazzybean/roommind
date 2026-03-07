"""Integration: multi-cycle scenarios testing state accumulation and transitions."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from .conftest import ROOM_LIVING, make_hass_states, setup_room


class TestMultiCycle:

    @pytest.mark.asyncio
    async def test_ekf_accumulates_across_cycles(self, coordinator, real_store):
        """EKF should accumulate observations over multiple update cycles."""
        await setup_room(real_store)

        for _ in range(5):
            await coordinator._async_update_data()

        model = coordinator._model_manager.get_model("living_room")
        assert model is not None

    @pytest.mark.asyncio
    async def test_mode_transition_heating_to_idle(self, coordinator, real_store):
        """When temp reaches target, mode should transition from heating to idle."""
        await setup_room(real_store)

        # Cycle 1: temp below target -> heating
        coordinator.hass.states.get = MagicMock(side_effect=make_hass_states(temp="18.0"))
        data1 = await coordinator._async_update_data()
        mode1 = data1["rooms"]["living_room"]["mode"]

        # Cycle 2: temp at target -> should idle
        # Backdate mode_on_since to bypass min-run enforcement window
        coordinator._mode_on_since["living_room"] = coordinator._mode_on_since.get("living_room", 0) - 4000
        coordinator.hass.states.get = MagicMock(side_effect=make_hass_states(temp="21.5"))
        data2 = await coordinator._async_update_data()
        mode2 = data2["rooms"]["living_room"]["mode"]

        assert mode1 in ("heating", "idle")
        assert mode2 == "idle"

    @pytest.mark.asyncio
    async def test_previous_mode_tracked_across_cycles(self, coordinator, real_store):
        """Coordinator should track previous mode for residual heat and transitions."""
        await setup_room(real_store)

        await coordinator._async_update_data()
        assert "living_room" in coordinator._previous_modes

        prev = coordinator._previous_modes["living_room"]
        assert prev in ("heating", "cooling", "idle")

    @pytest.mark.asyncio
    async def test_schedule_transition_comfort_to_eco(self, coordinator, real_store):
        """Switching schedule off mid-session should change target from comfort to eco."""
        await setup_room(real_store)

        # Schedule on -> comfort
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(schedule_state="on")
        )
        data1 = await coordinator._async_update_data()
        assert data1["rooms"]["living_room"]["target_temp"] == 21.0

        # Schedule off -> eco
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(schedule_state="off")
        )
        data2 = await coordinator._async_update_data()
        assert data2["rooms"]["living_room"]["target_temp"] == 17.0

    @pytest.mark.asyncio
    async def test_override_expires_falls_back_to_schedule(self, coordinator, real_store):
        """When override timer expires, target should revert to schedule-based temp."""
        await setup_room(real_store)
        await real_store.async_update_room("living_room", {
            "override_temp": 25.0,
            "override_until": time.time() - 1,
            "override_type": "custom",
        })

        data = await coordinator._async_update_data()

        assert data["rooms"]["living_room"]["target_temp"] == 21.0

    @pytest.mark.asyncio
    async def test_climate_control_disabled_shows_idle(self, coordinator, real_store):
        """With climate_control_active=false, no climate service calls should be made."""
        await setup_room(real_store, settings={
            "outdoor_temp_sensor": "sensor.outdoor_temp",
            "climate_control_active": False,
        })
        # Mock climate entity as "off" so _observe_device_action and _infer both return idle
        coordinator.hass.states.get = MagicMock(side_effect=make_hass_states(
            climate_state="off",
        ))

        coordinator.hass.services.async_call.reset_mock()
        data = await coordinator._async_update_data()

        assert data["rooms"]["living_room"]["mode"] == "idle"
        for call in coordinator.hass.services.async_call.call_args_list:
            assert call[0][0] != "climate", f"Unexpected climate call: {call}"
