"""Snapshot tests for coordinator._async_process_room return dict.

These tests call _async_process_room directly and verify the return dict
to catch regressions during future coordinator decomposition.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from .conftest import (
    MANAGED_ROOM,
    SAMPLE_ROOM,
    _create_coordinator,
    _make_store_mock,
    make_mock_states_get,
)


def _setup_coordinator(hass, mock_config_entry, rooms, settings=None):
    """Wire up hass, store, and create coordinator."""
    store = _make_store_mock(rooms)
    if settings:
        store.get_settings.return_value = settings
    hass.data = {"roommind": {"store": store}}
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    return coordinator, store


# Keys that every normal (non-outdoor) room return dict must contain.
NORMAL_ROOM_KEYS = {
    "area_id",
    "current_temp",
    "current_temp_raw",
    "current_humidity",
    "target_temp",
    "heat_target",
    "cool_target",
    "mode",
    "commanded_mode",
    "heating_power",
    "device_setpoint",
    "window_open",
    "override_active",
    "override_type",
    "override_temp",
    "override_until",
    "active_schedule_index",
    "confidence",
    "mpc_active",
    "presence_away",
    "force_off",
    "mold_risk_level",
    "mold_surface_rh",
    "mold_prevention_active",
    "mold_prevention_delta",
    "shading_factor",
    "q_occupancy",
    "n_observations",
    "blind_position",
    "cover_auto_paused",
    "cover_forced_reason",
    "cover_reason",
    "active_cover_schedule_index",
    "active_heat_sources",
}

OUTDOOR_ROOM_KEYS = {
    "area_id",
    "current_temp",
    "current_temp_raw",
    "current_humidity",
    "target_temp",
    "heat_target",
    "cool_target",
    "mode",
    "heating_power",
    "device_setpoint",
    "window_open",
    "override_active",
    "override_type",
    "override_temp",
    "override_until",
    "active_schedule_index",
    "confidence",
    "mpc_active",
    "presence_away",
    "force_off",
    "mold_risk_level",
    "mold_surface_rh",
    "mold_prevention_active",
    "mold_prevention_delta",
    "shading_factor",
    "n_observations",
    "blind_position",
    "cover_auto_paused",
    "cover_forced_reason",
    "active_cover_schedule_index",
    "q_occupancy",
    "active_heat_sources",
}


class TestProcessRoomSnapshot:
    """Snapshot tests for _async_process_room return dict."""

    @pytest.mark.asyncio
    async def test_normal_heating(self, hass, mock_config_entry):
        """temp=18, schedule=on: should heat toward comfort_temp=21."""
        coordinator, store = _setup_coordinator(
            hass,
            mock_config_entry,
            {"living_room_abc12345": SAMPLE_ROOM},
        )
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(temp="18.0", humidity="55.0"),
        )

        settings = store.get_settings()
        result = await coordinator._async_process_room(SAMPLE_ROOM, settings, [])

        # All expected keys present
        assert set(result.keys()) == NORMAL_ROOM_KEYS

        assert result["area_id"] == "living_room_abc12345"
        assert result["current_temp"] == 18.0
        assert result["target_temp"] == pytest.approx(21.0)
        assert result["heat_target"] == pytest.approx(21.0)
        assert result["mode"] == "heating"
        assert result["heating_power"] > 0
        assert result["window_open"] is False
        assert result["override_active"] is False
        assert result["presence_away"] is False
        assert result["force_off"] is False
        assert result["mold_risk_level"] == "ok"
        assert result["mold_prevention_active"] is False
        assert result["mold_prevention_delta"] == 0
        assert result["q_occupancy"] == 0.0

    @pytest.mark.asyncio
    async def test_idle_at_target(self, hass, mock_config_entry):
        """temp=21 (at comfort_temp), schedule=on: target_temp=21, mode idle."""
        coordinator, store = _setup_coordinator(
            hass,
            mock_config_entry,
            {"living_room_abc12345": SAMPLE_ROOM},
        )
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(temp="21.0", humidity="55.0"),
        )

        settings = store.get_settings()
        result = await coordinator._async_process_room(SAMPLE_ROOM, settings, [])

        assert result["area_id"] == "living_room_abc12345"
        assert result["current_temp"] == 21.0
        assert result["target_temp"] == pytest.approx(21.0)
        assert result["heat_target"] == pytest.approx(21.0)
        # At target, bang-bang controller should be idle
        assert result["mode"] == "idle"
        assert result["heating_power"] == 0

    @pytest.mark.asyncio
    async def test_window_open(self, hass, mock_config_entry):
        """Window sensor on: window_open=True, mode=idle."""
        room = {
            **SAMPLE_ROOM,
            "window_sensors": ["binary_sensor.w1"],
        }
        coordinator, store = _setup_coordinator(
            hass,
            mock_config_entry,
            {"living_room_abc12345": room},
        )
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                temp="18.0",
                humidity="55.0",
                window_sensors={"binary_sensor.w1": "on"},
            ),
        )

        settings = store.get_settings()
        result = await coordinator._async_process_room(room, settings, [])

        assert result["window_open"] is True
        assert result["mode"] == "idle"
        assert result["heating_power"] == 0

    @pytest.mark.asyncio
    async def test_outdoor_room(self, hass, mock_config_entry):
        """is_outdoor=True: returns reduced key set, mode=idle, force_off=False."""
        room = {
            **SAMPLE_ROOM,
            "is_outdoor": True,
        }
        coordinator, store = _setup_coordinator(
            hass,
            mock_config_entry,
            {"living_room_abc12345": room},
        )
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(temp="18.0", humidity="55.0"),
        )

        settings = store.get_settings()
        result = await coordinator._async_process_room(room, settings, [])

        assert set(result.keys()) == OUTDOOR_ROOM_KEYS
        assert result["mode"] == "idle"
        assert result["force_off"] is False  # NOT True!
        assert result["target_temp"] is None
        assert result["override_active"] is False
        # Outdoor rooms now include q_occupancy and active_heat_sources for consistency
        assert result["q_occupancy"] == 0.0
        assert result["active_heat_sources"] is None

    @pytest.mark.asyncio
    async def test_climate_control_disabled(self, hass, mock_config_entry):
        """climate_control_enabled=False: mode=idle, heating_power=0."""
        room = {**SAMPLE_ROOM, "climate_control_enabled": False}
        coordinator, store = _setup_coordinator(
            hass,
            mock_config_entry,
            {"living_room_abc12345": room},
        )
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(temp="18.0", humidity="55.0"),
        )

        settings = store.get_settings()
        result = await coordinator._async_process_room(room, settings, [])

        assert result["mode"] == "idle"
        assert result["heating_power"] == 0
        # All normal keys should still be present
        assert set(result.keys()) == NORMAL_ROOM_KEYS

    @pytest.mark.asyncio
    async def test_managed_mode(self, hass, mock_config_entry):
        """MANAGED_ROOM with device temp: target_temp is not None."""
        coordinator, store = _setup_coordinator(
            hass,
            mock_config_entry,
            {"living_room_abc12345": MANAGED_ROOM},
        )
        # Provide device temperature via climate entity's current_temperature
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                temp=None,  # No external sensor
                humidity="55.0",
                extra={
                    "climate.living_room": (
                        "heat",
                        {
                            "current_temperature": 19.0,
                            "temperature": 21.0,
                            "hvac_modes": ["off", "heat"],
                            "max_temp": 30,
                            "min_temp": 5,
                        },
                    ),
                },
            ),
        )

        settings = store.get_settings()
        result = await coordinator._async_process_room(MANAGED_ROOM, settings, [])

        assert result["target_temp"] is not None
        # Managed mode should still return all normal keys
        assert set(result.keys()) == NORMAL_ROOM_KEYS
