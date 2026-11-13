"""Tests for mold delta, hysteresis, surface RH, prevention intensity, notifications."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.const import MOLD_PREVENTION_RELEASE_MINUTES

from .conftest import (
    SAMPLE_ROOM,
    _create_coordinator,
    _make_store_mock,
    make_mock_states_get,
)


class TestMoldRiskDetection:
    """Tests for mold risk detection and prevention in the coordinator."""

    @pytest.mark.asyncio
    async def test_mold_detection_disabled_by_default(self, hass, mock_config_entry):
        """When mold detection is not enabled, mold_risk_level should be 'ok'."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(humidity="80.0"),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_risk_level"] == "ok"
        assert room["mold_prevention_active"] is False

    @pytest.mark.asyncio
    async def test_mold_risk_computed_when_detection_enabled(
        self,
        hass,
        mock_config_entry,
    ):
        """When detection is enabled, mold risk should be calculated."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_detection_enabled": True,
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        # 18degC, 75% RH, 0degC outside -> should be critical
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity="75.0",
                outdoor_temp="0.0",
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_risk_level"] == "critical"
        assert room["mold_surface_rh"] is not None
        assert room["mold_surface_rh"] > 80.0

    @pytest.mark.asyncio
    async def test_mold_prevention_raises_target_temp(
        self,
        hass,
        mock_config_entry,
    ):
        """When prevention is enabled and risk is high, target temp is raised."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_prevention_enabled": True,
            "mold_prevention_intensity": "medium",
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        # High mold risk conditions
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity="75.0",
                outdoor_temp="0.0",
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_prevention_active"] is True
        assert room["mold_prevention_delta"] == 2.0
        # Target temp should be comfort (21) + delta (2) = 23
        assert room["target_temp"] == 23.0

    @pytest.mark.asyncio
    async def test_mold_prevention_intensity_light(
        self,
        hass,
        mock_config_entry,
    ):
        """Light intensity raises target by 1degC."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_prevention_enabled": True,
            "mold_prevention_intensity": "light",
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity="75.0",
                outdoor_temp="0.0",
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_prevention_delta"] == 1.0
        assert room["target_temp"] == 22.0

    @pytest.mark.asyncio
    async def test_mold_no_humidity_sensor_skipped(
        self,
        hass,
        mock_config_entry,
    ):
        """Rooms without humidity data should not trigger mold logic."""
        room_no_humidity = {**SAMPLE_ROOM, "humidity_sensor": ""}
        store = _make_store_mock({"living_room_abc12345": room_no_humidity})
        store.get_settings.return_value = {
            "mold_detection_enabled": True,
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity=None,
                outdoor_temp="0.0",
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_risk_level"] == "ok"
        assert room["mold_surface_rh"] is None

    @pytest.mark.asyncio
    async def test_mold_risk_fields_in_room_state(
        self,
        hass,
        mock_config_entry,
    ):
        """Mold risk fields should always be present in room state."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get())
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert "mold_risk_level" in room
        assert "mold_surface_rh" in room
        assert "mold_surface_temp" in room
        assert "mold_prevention_active" in room
        assert "mold_prevention_delta" in room

    @pytest.mark.asyncio
    async def test_mold_prevention_intensity_strong(
        self,
        hass,
        mock_config_entry,
    ):
        """Strong intensity raises target by 3degC."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_prevention_enabled": True,
            "mold_prevention_intensity": "strong",
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity="75.0",
                outdoor_temp="0.0",
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_prevention_delta"] == 3.0
        assert room["target_temp"] == 24.0

    @pytest.mark.asyncio
    async def test_mold_sustained_timer_no_notification_before_threshold(
        self,
        hass,
        mock_config_entry,
    ):
        """Notification should NOT be sent before sustained_minutes elapsed."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_detection_enabled": True,
            "mold_notifications_enabled": True,
            "mold_sustained_minutes": 30,
            "mold_notification_targets": [
                {"entity_id": "notify.mobile", "person_entity": "", "notify_when": "always"},
            ],
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity="75.0",
                outdoor_temp="0.0",
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)

        # First cycle: risk starts, sustained timer begins
        await coordinator._async_update_data()

        # No notification service call should have been made for mold
        # (only climate control calls may have been made)
        mold_calls = [c for c in hass.services.async_call.call_args_list if c[0][0] == "notify"]
        assert len(mold_calls) == 0

    @pytest.mark.asyncio
    async def test_mold_sustained_timer_notification_after_threshold(
        self,
        hass,
        mock_config_entry,
    ):
        """Notification should be sent after sustained_minutes have elapsed."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_detection_enabled": True,
            "mold_notifications_enabled": True,
            "mold_sustained_minutes": 0,  # immediate notification
            "mold_notification_cooldown": 60,
            "mold_notification_targets": [
                {"entity_id": "notify.mobile", "person_entity": "", "notify_when": "always"},
            ],
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity="75.0",
                outdoor_temp="0.0",
            ),
        )
        hass.services.async_call = AsyncMock()
        # The notification is delivered in a background task (#502)
        tasks: list[asyncio.Task] = []
        hass.async_create_background_task = MagicMock(
            side_effect=lambda coro, name: tasks.append(asyncio.ensure_future(coro)) or tasks[-1]
        )

        coordinator = _create_coordinator(hass, mock_config_entry)
        with patch(
            "custom_components.roommind.coordinator._get_area_name",
            return_value="Living Room",
        ):
            await coordinator._async_update_data()
        await asyncio.gather(*tasks)

        mold_calls = [c for c in hass.services.async_call.call_args_list if c[0][0] == "notify"]
        assert len(mold_calls) >= 1

    @pytest.mark.asyncio
    async def test_mold_hysteresis_clearing(
        self,
        hass,
        mock_config_entry,
    ):
        """Prevention should deactivate only when surface RH drops below hysteresis threshold."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_prevention_enabled": True,
            "mold_prevention_intensity": "medium",
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)

        # Cycle 1: High risk -> prevention activates
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity="75.0",
                outdoor_temp="0.0",
            ),
        )
        data = await coordinator._async_update_data()
        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_prevention_active"] is True

        # Cycle 2: Conditions improve (warm outside) -> risk ok, surface RH well below threshold;
        # the boost holds MOLD_PREVENTION_RELEASE_MINUTES before it ends
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity="40.0",
                outdoor_temp="15.0",
            ),
        )
        data = await coordinator._async_update_data()
        assert data["rooms"]["living_room_abc12345"]["mold_prevention_active"] is True

        later = time.time() + MOLD_PREVENTION_RELEASE_MINUTES * 60 + 1
        with patch("custom_components.roommind.managers.mold_manager.time.time", return_value=later):
            data = await coordinator._async_update_data()
        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_prevention_active"] is False
        assert room["mold_prevention_delta"] == 0.0

    @pytest.mark.asyncio
    async def test_mold_warning_triggers_prevention(
        self,
        hass,
        mock_config_entry,
    ):
        """WARNING-level surface RH should trigger prevention (not just CRITICAL)."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_prevention_enabled": True,
            "mold_prevention_intensity": "medium",
            "outdoor_temp_sensor": "sensor.outdoor_temp",
        }
        hass.data = {"roommind": {"store": store}}
        # Conditions that produce WARNING (surface RH 70-80%) but room humidity below threshold
        # 20degC, 60% RH, 5degC outside -> surface ~16degC, surface RH ~76% (WARNING)
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                temp="20.0",
                humidity="60.0",
                outdoor_temp="5.0",
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_risk_level"] == "warning"
        assert room["mold_prevention_active"] is True
        assert room["mold_prevention_delta"] == 2.0

    @pytest.mark.asyncio
    async def test_mold_no_outdoor_sensor_fallback(
        self,
        hass,
        mock_config_entry,
    ):
        """Without outdoor temp sensor, conservative fallback should be used."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_detection_enabled": True,
            # No outdoor_temp_sensor
        }
        hass.data = {"roommind": {"store": store}}
        # 70% room humidity -> fallback = 80% surface RH -> critical
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(humidity="70.0"),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mold_risk_level"] == "critical"
        assert room["mold_surface_rh"] == pytest.approx(80.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_mold_prevention_force_off_override(self, hass, mock_config_entry):
        """Mold prevention overrides force_off to prevent structural damage."""
        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "mold_prevention_enabled": True,
            "mold_prevention_intensity": "medium",
            "outdoor_temp_sensor": "sensor.outdoor_temp",
            "presence_enabled": True,
            "presence_persons": ["person.kevin"],
            "presence_away_action": "off",
        }
        hass.data = {"roommind": {"store": store}}
        # Nobody home + mold risk conditions
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                humidity="75.0",
                outdoor_temp="0.0",
                person_states={"person.kevin": "not_home"},
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        # Mold prevention should override force_off
        assert room["mold_prevention_active"] is True
        assert room["force_off"] is False


class TestMoldPreventionNeedsHeating:
    """Prevention raises the target only where something can heat; the risk counts everywhere."""

    _SETTINGS = {
        "mold_detection_enabled": True,
        "mold_prevention_enabled": True,
        "mold_prevention_intensity": "medium",
        "outdoor_temp_sensor": "sensor.outdoor_temp",
    }

    async def _run(self, hass, mock_config_entry, room, extra=None):
        store = _make_store_mock({"living_room_abc12345": room})
        store.get_settings.return_value = dict(self._SETTINGS)
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(humidity="75.0", outdoor_temp="0.0", extra=extra),
        )
        hass.services.async_call = AsyncMock()
        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()
        return data["rooms"]["living_room_abc12345"]

    @pytest.mark.asyncio
    async def test_room_without_devices_gets_no_prevention(self, hass, mock_config_entry):
        room = {**SAMPLE_ROOM, "devices": [], "thermostats": [], "acs": []}
        state = await self._run(hass, mock_config_entry, room)
        assert state["mold_risk_level"] == "critical"
        assert state["mold_prevention_active"] is False
        assert state["mold_prevention_delta"] == 0.0

    @pytest.mark.asyncio
    async def test_cool_only_room_gets_no_prevention(self, hass, mock_config_entry):
        room = {
            **SAMPLE_ROOM,
            "climate_mode": "cool_only",
            "devices": [{"entity_id": "climate.living_ac", "type": "ac", "role": "auto", "heating_system_type": ""}],
            "thermostats": [],
            "acs": ["climate.living_ac"],
        }
        extra = {"climate.living_ac": ("off", {"hvac_modes": ["off", "cool", "heat"]})}
        state = await self._run(hass, mock_config_entry, room, extra)
        assert state["mold_risk_level"] == "critical"
        assert state["mold_prevention_active"] is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("modes", "expected"),
        [(["off", "cool", "heat"], True), (["off", "cool"], False)],
        ids=["heat_pump", "cooling_only_unit"],
    )
    async def test_ac_room_gets_prevention_only_when_the_ac_heats(self, hass, mock_config_entry, modes, expected):
        room = {
            **SAMPLE_ROOM,
            "devices": [{"entity_id": "climate.living_ac", "type": "ac", "role": "auto", "heating_system_type": ""}],
            "thermostats": [],
            "acs": ["climate.living_ac"],
        }
        extra = {"climate.living_ac": ("off", {"hvac_modes": modes})}
        state = await self._run(hass, mock_config_entry, room, extra)
        assert state["mold_risk_level"] == "critical"
        assert state["mold_prevention_active"] is expected
