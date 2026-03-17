"""Tests for valve cycling, actuation tracking, protection interval."""

from __future__ import annotations

import time
from unittest.mock import ANY, AsyncMock, MagicMock, call

import pytest

from .conftest import (
    SAMPLE_ROOM,
    _create_coordinator,
    _make_store_mock,
    make_mock_states_get,
)


class TestValveProtection:
    """Tests for valve protection (anti-seize) cycling."""

    @pytest.mark.asyncio
    async def test_valve_protection_disabled_by_default(self, hass, mock_config_entry):
        """No cycling occurs without explicit enable."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {}
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="21.0"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        # Force the check counter to trigger
        coordinator._valve_manager._check_count = 119
        await coordinator._async_update_data()

        # No valve cycling should have started
        assert len(coordinator._valve_manager._cycling) == 0

    @pytest.mark.asyncio
    async def test_valve_protection_cycles_stale_valve(self, hass, mock_config_entry):
        """TRV idle for 8 days gets cycled when protection is enabled."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "valve_protection_enabled": True,
            "valve_protection_interval_days": 7,
        }
        store.async_save_settings = AsyncMock()
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="21.0"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        # TRV was last used 8 days ago
        coordinator._valve_manager._last_actuation["climate.living_room"] = time.time() - 8 * 86400
        # Trigger check
        coordinator._valve_manager._check_count = 119
        await coordinator._async_update_data()

        # Valve should be cycling
        assert "climate.living_room" in coordinator._valve_manager._cycling

        # Verify heat + temperature service calls for the cycling valve
        climate_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if c[0][0] == "climate" and c[0][2].get("entity_id") == "climate.living_room"
        ]
        hvac_heat_calls = [c for c in climate_calls if c[0][1] == "set_hvac_mode" and c[0][2]["hvac_mode"] == "heat"]
        set_temp_calls = [c for c in climate_calls if c[0][1] == "set_temperature"]
        assert len(hvac_heat_calls) >= 1
        assert len(set_temp_calls) >= 1

    @pytest.mark.asyncio
    async def test_valve_protection_finishes_after_duration(self, hass, mock_config_entry):
        """After 15s duration, valve gets turned off and timestamp updated."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {"valve_protection_enabled": True}
        store.async_save_settings = AsyncMock()
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="21.0"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        # Simulate: valve has been cycling for 20 seconds (exceeds 15s)
        coordinator._valve_manager._cycling["climate.living_room"] = time.time() - 20
        old_actuation = coordinator._valve_manager._last_actuation.get("climate.living_room", 0)

        await coordinator._async_update_data()

        # Valve should no longer be cycling
        assert "climate.living_room" not in coordinator._valve_manager._cycling
        # Actuation timestamp should be updated
        assert coordinator._valve_manager._last_actuation["climate.living_room"] > old_actuation
        assert coordinator._valve_manager._actuation_dirty is True

        # Verify off command was sent
        off_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if c
            == call(
                "climate",
                "set_hvac_mode",
                {"entity_id": "climate.living_room", "hvac_mode": "off"},
                blocking=True,
                context=ANY,
            )
        ]
        assert len(off_calls) >= 1

    @pytest.mark.asyncio
    async def test_valve_protection_skips_recent_valve(self, hass, mock_config_entry):
        """TRV idle for only 2 days is not cycled (default interval = 7 days)."""
        recent_ts = time.time() - 2 * 86400
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "valve_protection_enabled": True,
            "valve_protection_interval_days": 7,
            "valve_last_actuation": {"climate.living_room": recent_ts},
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="21.0"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._valve_manager._check_count = 119
        await coordinator._async_update_data()

        assert "climate.living_room" not in coordinator._valve_manager._cycling

    @pytest.mark.asyncio
    async def test_valve_protection_excludes_cycling_from_apply(self, hass, mock_config_entry):
        """Cycling TRV is not turned off by normal idle control."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {"valve_protection_enabled": True}
        store.async_save_settings = AsyncMock()
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="21.0"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        # Valve is currently being cycled (started 5 seconds ago, still within 15s)
        coordinator._valve_manager._cycling["climate.living_room"] = time.time() - 5

        await coordinator._async_update_data()

        # The room is at target (21degC) so mode=idle, but the cycling valve
        # should NOT receive an "off" command from normal control.
        # Only the valve protection finish logic should close it (but not yet -- only 5s elapsed).
        climate_off_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if c
            == call(
                "climate",
                "set_hvac_mode",
                {"entity_id": "climate.living_room", "hvac_mode": "off"},
                blocking=True,
                context=ANY,
            )
        ]
        assert len(climate_off_calls) == 0
        # Valve should still be cycling
        assert "climate.living_room" in coordinator._valve_manager._cycling

    @pytest.mark.asyncio
    async def test_valve_protection_runs_when_climate_off(self, hass, mock_config_entry):
        """Valve protection works even when climate_control_active is False."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "climate_control_active": False,
            "valve_protection_enabled": True,
            "valve_protection_interval_days": 7,
        }
        store.async_save_settings = AsyncMock()
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="21.0"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._valve_manager._last_actuation["climate.living_room"] = time.time() - 8 * 86400
        coordinator._valve_manager._check_count = 119
        await coordinator._async_update_data()

        assert "climate.living_room" in coordinator._valve_manager._cycling

    @pytest.mark.asyncio
    async def test_valve_protection_only_trvs(self, hass, mock_config_entry):
        """Only thermostats are cycled, not ACs."""
        room_with_ac = {
            **SAMPLE_ROOM,
            "acs": ["climate.living_room_ac"],
            "devices": [
                {"entity_id": "climate.living_room", "type": "trv", "role": "auto", "heating_system_type": ""},
                {"entity_id": "climate.living_room_ac", "type": "ac", "role": "auto", "heating_system_type": ""},
            ],
        }
        store = _make_store_mock({"living_room_abc12345": room_with_ac})
        store.get_settings.return_value = {
            "valve_protection_enabled": True,
            "valve_protection_interval_days": 7,
        }
        store.async_save_settings = AsyncMock()
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="21.0"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        # Both TRV and AC idle for 8 days
        coordinator._valve_manager._last_actuation["climate.living_room"] = time.time() - 8 * 86400
        coordinator._valve_manager._last_actuation["climate.living_room_ac"] = time.time() - 8 * 86400
        coordinator._valve_manager._check_count = 119
        await coordinator._async_update_data()

        # Only TRV should be cycled, not AC
        assert "climate.living_room" in coordinator._valve_manager._cycling
        assert "climate.living_room_ac" not in coordinator._valve_manager._cycling

    @pytest.mark.asyncio
    async def test_valve_actuation_updated_on_heating(self, hass, mock_config_entry):
        """Normal heating updates valve actuation timestamps."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {}
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="18.0"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        assert "climate.living_room" not in coordinator._valve_manager._last_actuation

        await coordinator._async_update_data()

        # Room heats (18degC < 21degC target), so actuation should be tracked
        assert "climate.living_room" in coordinator._valve_manager._last_actuation
        assert coordinator._valve_manager._actuation_dirty is True

    @pytest.mark.asyncio
    async def test_valve_protection_custom_interval(self, hass, mock_config_entry):
        """Custom 3-day interval: TRV idle for 4 days gets cycled."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "valve_protection_enabled": True,
            "valve_protection_interval_days": 3,
        }
        store.async_save_settings = AsyncMock()
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="21.0"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._valve_manager._last_actuation["climate.living_room"] = time.time() - 4 * 86400
        coordinator._valve_manager._check_count = 119
        await coordinator._async_update_data()

        assert "climate.living_room" in coordinator._valve_manager._cycling

    @pytest.mark.asyncio
    async def test_valve_protection_cleanup_stale_entities(self, hass, mock_config_entry):
        """Entities no longer configured in any room are cleaned up."""
        now = time.time()
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "valve_protection_enabled": True,
            "valve_protection_interval_days": 7,
            "valve_last_actuation": {
                "climate.living_room": now,
                "climate.old_thermostat": now - 30 * 86400,
            },
        }
        store.async_save_settings = AsyncMock()
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="21.0"))
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._valve_manager._check_count = 119
        await coordinator._async_update_data()

        assert "climate.old_thermostat" not in coordinator._valve_manager._last_actuation
        assert "climate.living_room" in coordinator._valve_manager._last_actuation

    @pytest.mark.asyncio
    async def test_valve_protection_auto_only_thermostat(self, hass, mock_config_entry):
        """TRV with only 'off'+'auto' gets 'auto' mode during valve cycling."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "valve_protection_enabled": True,
            "valve_protection_interval_days": 7,
        }
        store.async_save_settings = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        trv_state = MagicMock()
        trv_state.state = "off"
        trv_state.attributes = {
            "hvac_modes": ["off", "auto"],
            "temperature": None,
            "min_temp": 5.0,
            "max_temp": 25.0,
            "current_temperature": 21.0,
        }
        base_get = make_mock_states_get(temp="21.0")

        def custom_get(eid):
            if eid == "climate.living_room":
                return trv_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=custom_get)
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._valve_manager._last_actuation["climate.living_room"] = time.time() - 8 * 86400
        coordinator._valve_manager._check_count = 119
        await coordinator._async_update_data()

        assert "climate.living_room" in coordinator._valve_manager._cycling
        climate_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if c[0][0] == "climate" and c[0][2].get("entity_id") == "climate.living_room"
        ]
        hvac_calls = [c for c in climate_calls if c[0][1] == "set_hvac_mode"]
        assert any(c[0][2]["hvac_mode"] == "auto" for c in hvac_calls)
        assert not any(c[0][2]["hvac_mode"] == "heat" for c in hvac_calls)


class TestValveProtectionFinish:
    """Tests for _async_valve_protection_finish."""

    @pytest.mark.asyncio
    async def test_no_cycling_is_noop(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        # No cycling entries -> should return immediately
        await coordinator._valve_manager.async_finish_cycles()
        hass.services.async_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_finishes_expired_cycle(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        hass.services.async_call = AsyncMock()
        # Valve has been cycling for longer than VALVE_PROTECTION_CYCLE_DURATION
        coordinator._valve_manager._cycling["climate.trv1"] = time.time() - 120

        await coordinator._valve_manager.async_finish_cycles()

        assert "climate.trv1" not in coordinator._valve_manager._cycling
        assert "climate.trv1" in coordinator._valve_manager._last_actuation
        assert coordinator._valve_manager._actuation_dirty is True

    @pytest.mark.asyncio
    async def test_finish_exception_still_cleans_up(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        hass.services.async_call = AsyncMock(side_effect=RuntimeError("fail"))
        coordinator._valve_manager._cycling["climate.trv1"] = time.time() - 120

        await coordinator._valve_manager.async_finish_cycles()

        # Still cleaned up despite exception
        assert "climate.trv1" not in coordinator._valve_manager._cycling
        assert "climate.trv1" in coordinator._valve_manager._last_actuation


class TestValveProtectionCheck:
    """Tests for _async_valve_protection_check."""

    @pytest.mark.asyncio
    async def test_disabled_clears_active_cycles(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        hass.services.async_call = AsyncMock()
        coordinator._valve_manager._cycling["climate.trv1"] = time.time()

        settings = {"valve_protection_enabled": False}
        await coordinator._valve_manager.async_check_and_cycle({}, settings)

        assert len(coordinator._valve_manager._cycling) == 0

    @pytest.mark.asyncio
    async def test_starts_cycling_stale_valve(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        hass.services.async_call = AsyncMock()
        eid_state = MagicMock()
        eid_state.attributes = {"max_temp": 30}
        hass.states.get = MagicMock(return_value=eid_state)

        rooms = {
            "room_a": {
                "thermostats": ["climate.trv1"],
                "devices": [{"entity_id": "climate.trv1", "type": "trv", "role": "auto", "heating_system_type": ""}],
            }
        }
        settings = {"valve_protection_enabled": True, "valve_protection_interval_days": 7}

        # Valve was last actuated > 7 days ago
        coordinator._valve_manager._last_actuation["climate.trv1"] = time.time() - 8 * 86400

        await coordinator._valve_manager.async_check_and_cycle(rooms, settings)

        assert "climate.trv1" in coordinator._valve_manager._cycling
        assert hass.services.async_call.call_count >= 1

    @pytest.mark.asyncio
    async def test_skips_already_cycling(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        hass.services.async_call = AsyncMock()

        rooms = {
            "room_a": {
                "thermostats": ["climate.trv1"],
                "devices": [{"entity_id": "climate.trv1", "type": "trv", "role": "auto", "heating_system_type": ""}],
            }
        }
        settings = {"valve_protection_enabled": True, "valve_protection_interval_days": 7}

        # Already cycling
        coordinator._valve_manager._cycling["climate.trv1"] = time.time()
        coordinator._valve_manager._last_actuation["climate.trv1"] = time.time() - 8 * 86400

        await coordinator._valve_manager.async_check_and_cycle(rooms, settings)

        # Should not call any service (already cycling)
        hass.services.async_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleans_up_stale_entries(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        hass.services.async_call = AsyncMock()

        # Entity in actuation dict but not in any room
        coordinator._valve_manager._last_actuation["climate.old_trv"] = time.time()
        rooms = {
            "room_a": {
                "thermostats": ["climate.trv1"],
                "devices": [{"entity_id": "climate.trv1", "type": "trv", "role": "auto", "heating_system_type": ""}],
            }
        }
        settings = {"valve_protection_enabled": True, "valve_protection_interval_days": 7}

        await coordinator._valve_manager.async_check_and_cycle(rooms, settings)

        assert "climate.old_trv" not in coordinator._valve_manager._last_actuation
        assert coordinator._valve_manager._actuation_dirty is True
