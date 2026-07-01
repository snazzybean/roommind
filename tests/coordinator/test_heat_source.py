"""Tests for heat source orchestration, routing, compressor integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.const import MODE_IDLE

from .conftest import (
    SAMPLE_ROOM,
    _create_coordinator,
    _make_store_mock,
    make_mock_states_get,
)


class TestHeatSourceOrchestration:
    """Tests for heat source orchestration wiring in the coordinator."""

    ROOM_WITH_BOTH = {
        "area_id": "living_room_abc12345",
        "thermostats": ["climate.living_room"],
        "acs": ["climate.living_room_ac"],
        "devices": [
            {"entity_id": "climate.living_room", "type": "trv", "role": "auto", "heating_system_type": ""},
            {"entity_id": "climate.living_room_ac", "type": "ac", "role": "auto", "heating_system_type": ""},
        ],
        "temperature_sensor": "sensor.living_room_temp",
        "humidity_sensor": "sensor.living_room_humidity",
        "climate_mode": "auto",
        "schedules": [{"entity_id": "schedule.living_room_heating"}],
        "schedule_selector_entity": "",
        "comfort_temp": 21.0,
        "eco_temp": 17.0,
        "heat_source_orchestration": True,
    }

    @pytest.mark.asyncio
    async def test_orchestration_wiring_calls_evaluate_and_passes_plan(self, hass, mock_config_entry):
        """Room with both thermostats and ACs, orchestration enabled, MODE_HEATING.

        Verify evaluate_heat_sources is called and the plan is forwarded to async_apply.
        """
        from custom_components.roommind.managers.heat_source_orchestrator import (
            HeatSourcePlan,
        )

        store = _make_store_mock({"living_room_abc12345": self.ROOM_WITH_BOTH})
        hass.data = {"roommind": {"store": store}}

        # AC entity needs hvac_modes with 'heat' so it's detected as heat-capable
        ac_state = MagicMock()
        ac_state.state = "off"
        ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "min_temp": 16, "max_temp": 30}

        base_mock = make_mock_states_get(temp="18.0")

        def custom_get(eid):
            if eid == "climate.living_room_ac":
                return ac_state
            return base_mock(eid)

        hass.states.get = MagicMock(side_effect=custom_get)
        hass.services.async_call = AsyncMock()

        fake_plan = HeatSourcePlan(commands=[], active_sources="primary", reason="test")

        with patch(
            "custom_components.roommind.coordinator.evaluate_heat_sources",
            return_value=fake_plan,
        ) as mock_evaluate:
            coordinator = _create_coordinator(hass, mock_config_entry)
            data = await coordinator._async_update_data()

            # evaluate_heat_sources must have been called
            mock_evaluate.assert_called_once()
            call_kwargs = mock_evaluate.call_args
            assert call_kwargs.kwargs["room_config"]["area_id"] == "living_room_abc12345"
            assert call_kwargs.kwargs["mode"] == "heating"

        # The plan's active_sources should be stored in _heat_source_states
        assert coordinator._heat_source_states.get("living_room_abc12345") == "primary"

        # async_apply was called with the plan (no exception = wiring works)
        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["mode"] == "heating"

    @pytest.mark.asyncio
    async def test_orchestration_disabled_plan_is_none(self, hass, mock_config_entry):
        """Room with heat_source_orchestration=False. Plan should be None (normal path)."""
        room = {**self.ROOM_WITH_BOTH, "heat_source_orchestration": False}
        store = _make_store_mock({"living_room_abc12345": room})
        hass.data = {"roommind": {"store": store}}

        ac_state = MagicMock()
        ac_state.state = "off"
        ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "min_temp": 16, "max_temp": 30}

        base_mock = make_mock_states_get(temp="18.0")

        def custom_get(eid):
            if eid == "climate.living_room_ac":
                return ac_state
            return base_mock(eid)

        hass.states.get = MagicMock(side_effect=custom_get)
        hass.services.async_call = AsyncMock()

        with patch(
            "custom_components.roommind.coordinator.evaluate_heat_sources",
        ) as mock_evaluate:
            coordinator = _create_coordinator(hass, mock_config_entry)
            await coordinator._async_update_data()

            # evaluate_heat_sources must NOT have been called
            mock_evaluate.assert_not_called()

        # No state stored
        assert "living_room_abc12345" not in coordinator._heat_source_states

    @pytest.mark.asyncio
    async def test_state_cleanup_on_disable(self, hass, mock_config_entry):
        """Disabling orchestration removes the stale state entry."""
        from custom_components.roommind.managers.heat_source_orchestrator import (
            HeatSourcePlan,
        )

        # First cycle: orchestration ON
        store = _make_store_mock({"living_room_abc12345": self.ROOM_WITH_BOTH})
        hass.data = {"roommind": {"store": store}}

        ac_state = MagicMock()
        ac_state.state = "off"
        ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "min_temp": 16, "max_temp": 30}

        base_mock = make_mock_states_get(temp="18.0")

        def custom_get(eid):
            if eid == "climate.living_room_ac":
                return ac_state
            return base_mock(eid)

        hass.states.get = MagicMock(side_effect=custom_get)
        hass.services.async_call = AsyncMock()

        fake_plan = HeatSourcePlan(commands=[], active_sources="both", reason="test")

        with patch(
            "custom_components.roommind.coordinator.evaluate_heat_sources",
            return_value=fake_plan,
        ):
            coordinator = _create_coordinator(hass, mock_config_entry)
            await coordinator._async_update_data()

        assert coordinator._heat_source_states.get("living_room_abc12345") == "both"

        # Second cycle: orchestration OFF
        room_disabled = {**self.ROOM_WITH_BOTH, "heat_source_orchestration": False}
        store.get_rooms.return_value = {"living_room_abc12345": room_disabled}

        with patch(
            "custom_components.roommind.coordinator.evaluate_heat_sources",
        ) as mock_evaluate:
            await coordinator._async_update_data()
            mock_evaluate.assert_not_called()

        # State entry must be removed
        assert "living_room_abc12345" not in coordinator._heat_source_states

    @pytest.mark.asyncio
    async def test_state_cleanup_on_room_deletion(self, hass, mock_config_entry):
        """async_room_removed cleans up _heat_source_states for the deleted room."""
        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator.async_request_refresh = AsyncMock()

        # Seed some state
        coordinator._heat_source_states["test_room_123"] = "primary"
        coordinator._heat_source_states["other_room_456"] = "secondary"

        mock_registry = MagicMock()
        mock_registry.entities = MagicMock()
        mock_registry.entities.values.return_value = []

        with patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=mock_registry,
        ):
            await coordinator.async_room_removed("test_room_123")

        assert "test_room_123" not in coordinator._heat_source_states
        # Other rooms are not affected
        assert coordinator._heat_source_states["other_room_456"] == "secondary"

    @pytest.mark.asyncio
    async def test_active_heat_sources_in_live_data(self, hass, mock_config_entry):
        """_build_live_data includes active_heat_sources from _heat_source_states."""
        from custom_components.roommind.managers.heat_source_orchestrator import (
            HeatSourcePlan,
        )

        store = _make_store_mock({"living_room_abc12345": self.ROOM_WITH_BOTH})
        hass.data = {"roommind": {"store": store}}

        ac_state = MagicMock()
        ac_state.state = "off"
        ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "min_temp": 16, "max_temp": 30}

        base_mock = make_mock_states_get(temp="18.0")

        def custom_get(eid):
            if eid == "climate.living_room_ac":
                return ac_state
            return base_mock(eid)

        hass.states.get = MagicMock(side_effect=custom_get)
        hass.services.async_call = AsyncMock()

        fake_plan = HeatSourcePlan(commands=[], active_sources="both", reason="test")

        with patch(
            "custom_components.roommind.coordinator.evaluate_heat_sources",
            return_value=fake_plan,
        ):
            coordinator = _create_coordinator(hass, mock_config_entry)
            data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["active_heat_sources"] == "both"

    @pytest.mark.asyncio
    async def test_active_heat_sources_none_when_not_orchestrated(self, hass, mock_config_entry):
        """active_heat_sources is None for rooms without orchestration."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}

        hass.states.get = MagicMock(side_effect=make_mock_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["active_heat_sources"] is None

    # -------------------------------------------------------------------
    # Compressor group protection integration tests
    # -------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_compressor_min_off_blocks_ac_start(self, hass, mock_config_entry):
        """AC should NOT be turned on when compressor min-off hasn't expired."""
        ac_room = {
            **SAMPLE_ROOM,
            "thermostats": [],
            "acs": ["climate.living_room_ac"],
            "devices": [
                {"entity_id": "climate.living_room_ac", "type": "ac", "role": "auto", "heating_system_type": ""},
            ],
            "climate_mode": "cool_only",
        }
        store = _make_store_mock({"living_room_abc12345": ac_room})
        # Settings include a compressor group with this AC
        store.get_settings.return_value = {
            "compressor_groups": [
                {
                    "id": "group1",
                    "name": "Outdoor Unit",
                    "members": ["climate.living_room_ac"],
                    "min_run_minutes": 5,
                    "min_off_minutes": 5,
                }
            ],
        }
        hass.data = {"roommind": {"store": store}}

        # Room is warm so coordinator wants to cool (temp=28, comfort=21)
        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="28.0"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)

        # Simulate: compressor was recently turned off (min-off not expired)
        coordinator._compressor_manager.load_groups(store.get_settings()["compressor_groups"])
        # Mark the AC as recently deactivated
        coordinator._compressor_manager.update_member("climate.living_room_ac", True)
        coordinator._compressor_manager.update_member("climate.living_room_ac", False)
        # compressor_off_since is now ~time.time(), so min-off (5 min) not expired

        data = await coordinator._async_update_data()
        room_state = data["rooms"]["living_room_abc12345"]

        # Mode should be idle because the only device is blocked by min-off
        assert room_state["mode"] == MODE_IDLE

    @pytest.mark.asyncio
    async def test_compressor_min_run_keeps_ac_on(self, hass, mock_config_entry):
        """AC should stay on (forced_on) when min-run hasn't expired."""
        ac_room = {
            **SAMPLE_ROOM,
            "thermostats": [],
            "acs": ["climate.living_room_ac"],
            "devices": [
                {"entity_id": "climate.living_room_ac", "type": "ac", "role": "auto", "heating_system_type": ""},
            ],
            "climate_mode": "cool_only",
        }
        store = _make_store_mock({"living_room_abc12345": ac_room})
        store.get_settings.return_value = {
            "compressor_groups": [
                {
                    "id": "group1",
                    "name": "Outdoor Unit",
                    "members": ["climate.living_room_ac"],
                    "min_run_minutes": 15,
                    "min_off_minutes": 5,
                }
            ],
        }
        hass.data = {"roommind": {"store": store}}

        # Room is at target so coordinator wants idle (temp=21, comfort=21)
        # AC must have an active HA state so forced_on tracking recognises it as running
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                temp="21.0",
                extra={"climate.living_room_ac": ("cool", {"hvac_modes": ["cool", "off"]})},
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)

        # Pre-load groups and mark AC as actively running (min-run not expired)
        coordinator._compressor_manager.load_groups(store.get_settings()["compressor_groups"])
        coordinator._compressor_manager.update_member("climate.living_room_ac", True)
        # compressor_on_since is now ~monotonic(), so min-run (15 min) not expired

        await coordinator._async_update_data()

        # The compressor manager should have forced the AC to stay on
        # Verify the AC was NOT turned off (check_must_stay_active returns True)
        assert coordinator._compressor_manager.check_must_stay_active("climate.living_room_ac") is True

    @pytest.mark.asyncio
    async def test_compressor_window_open_overrides_min_run(self, hass, mock_config_entry):
        """Window-open should override compressor min-run protection."""
        ac_room = {
            **SAMPLE_ROOM,
            "thermostats": [],
            "acs": ["climate.living_room_ac"],
            "devices": [
                {"entity_id": "climate.living_room_ac", "type": "ac", "role": "auto", "heating_system_type": ""},
            ],
            "climate_mode": "cool_only",
            "window_sensors": ["binary_sensor.living_room_window"],
        }
        store = _make_store_mock({"living_room_abc12345": ac_room})
        store.get_settings.return_value = {
            "compressor_groups": [
                {
                    "id": "group1",
                    "name": "Outdoor Unit",
                    "members": ["climate.living_room_ac"],
                    "min_run_minutes": 15,
                    "min_off_minutes": 5,
                }
            ],
        }
        hass.data = {"roommind": {"store": store}}

        # Window open, room warm
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                temp="28.0",
                window_sensors={"binary_sensor.living_room_window": "on"},
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)

        # Pre-load groups and mark AC as running (min-run active)
        coordinator._compressor_manager.load_groups(store.get_settings()["compressor_groups"])
        coordinator._compressor_manager.update_member("climate.living_room_ac", True)

        data = await coordinator._async_update_data()
        room_state = data["rooms"]["living_room_abc12345"]

        # Window open forces idle regardless of compressor protection
        assert room_state["mode"] == MODE_IDLE
        assert room_state["window_open"] is True

    @pytest.mark.asyncio
    async def test_compressor_cross_room(self, hass, mock_config_entry):
        """Compressor group correctly tracks shared state across two rooms."""
        room_a = {
            **SAMPLE_ROOM,
            "area_id": "room_a",
            "thermostats": [],
            "acs": ["climate.ac_a"],
            "devices": [
                {"entity_id": "climate.ac_a", "type": "ac", "role": "auto", "heating_system_type": ""},
            ],
            "climate_mode": "cool_only",
        }
        room_b = {
            **SAMPLE_ROOM,
            "area_id": "room_b",
            "thermostats": [],
            "acs": ["climate.ac_b"],
            "devices": [
                {"entity_id": "climate.ac_b", "type": "ac", "role": "auto", "heating_system_type": ""},
            ],
            "climate_mode": "cool_only",
            "temperature_sensor": "sensor.room_b_temp",
            "humidity_sensor": "sensor.room_b_humidity",
            "schedules": [{"entity_id": "schedule.room_b_heating"}],
        }
        store = _make_store_mock({"room_a": room_a, "room_b": room_b})
        store.get_settings.return_value = {
            "compressor_groups": [
                {
                    "id": "shared_outdoor",
                    "name": "Shared Outdoor",
                    "members": ["climate.ac_a", "climate.ac_b"],
                    "min_run_minutes": 5,
                    "min_off_minutes": 5,
                }
            ],
        }
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._compressor_manager.load_groups(store.get_settings()["compressor_groups"])

        # Both ACs share the same group
        assert (
            coordinator._compressor_manager.get_group_for_entity("climate.ac_a")
            == coordinator._compressor_manager.get_group_for_entity("climate.ac_b")
            == "shared_outdoor"
        )

        # Activate one AC
        coordinator._compressor_manager.update_member("climate.ac_a", True)
        assert coordinator._compressor_manager.is_compressor_running("shared_outdoor") is True

        # The other AC can join (compressor already running)
        assert coordinator._compressor_manager.check_can_activate("climate.ac_b") is True

        # Deactivate ac_a, ac_b still keeps compressor running
        coordinator._compressor_manager.update_member("climate.ac_b", True)
        coordinator._compressor_manager.update_member("climate.ac_a", False)
        assert coordinator._compressor_manager.is_compressor_running("shared_outdoor") is True

        # Deactivate last member, compressor stops
        coordinator._compressor_manager.update_member("climate.ac_b", False)
        assert coordinator._compressor_manager.is_compressor_running("shared_outdoor") is False

    @pytest.mark.asyncio
    async def test_compressor_min_off_blocks_ac_in_cool_only_room_with_trv(self, hass, mock_config_entry):
        """Compressor protection sets mode to IDLE in a cool_only room that also has a TRV.

        Regression test: before the fix, the TRV's presence in all_device_eids caused
        the 'all grouped devices blocked' check to never trigger, leaving mode as
        'cooling' even though the only cooling-capable device was protected.
        """
        mixed_room = {
            **SAMPLE_ROOM,
            "thermostats": ["climate.living_room_trv"],
            "acs": ["climate.living_room_ac"],
            "devices": [
                {
                    "entity_id": "climate.living_room_trv",
                    "type": "trv",
                    "role": "auto",
                    "heating_system_type": "radiator",
                },
                {
                    "entity_id": "climate.living_room_ac",
                    "type": "ac",
                    "role": "auto",
                    "heating_system_type": "",
                    "idle_action": "fan_only",
                },
            ],
            "climate_mode": "cool_only",
        }
        store = _make_store_mock({"living_room_abc12345": mixed_room})
        store.get_settings.return_value = {
            "compressor_groups": [
                {
                    "id": "group1",
                    "name": "Outdoor Unit",
                    "members": ["climate.living_room_ac"],
                    "min_run_minutes": 5,
                    "min_off_minutes": 5,
                }
            ],
        }
        hass.data = {"roommind": {"store": store}}

        # Room is warm so coordinator wants to cool (temp=28, comfort_cool=24)
        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="28.0"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)

        # Simulate AC recently deactivated — min-off not yet expired
        coordinator._compressor_manager.load_groups(store.get_settings()["compressor_groups"])
        coordinator._compressor_manager.update_member("climate.living_room_ac", True)
        coordinator._compressor_manager.update_member("climate.living_room_ac", False)

        data = await coordinator._async_update_data()
        room_state = data["rooms"]["living_room_abc12345"]

        # The AC is the only cooling-capable device and it is blocked: mode must be IDLE.
        # A TRV in the room must not prevent this transition (TRVs cannot cool).
        assert room_state["mode"] == MODE_IDLE, (
            "cool_only room with blocked AC should be IDLE even when a TRV is present"
        )
