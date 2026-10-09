"""Tests for TRV setpoints, AC control, managed vs full control, device max/min, proportional boost, Fahrenheit conversion."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from .conftest import (
    MANAGED_ROOM,
    SAMPLE_ROOM,
    _create_coordinator,
    _make_store_mock,
    make_mock_states_get,
)


class TestComputeDeviceSetpoint:
    """Tests for _compute_device_setpoint static method."""

    def test_idle_returns_none(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        result = coordinator._compute_device_setpoint("idle", 0.5, 20.0, 21.0, True)
        assert result is None

    def test_no_external_sensor_returns_none(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        result = coordinator._compute_device_setpoint("heating", 0.5, 20.0, 21.0, False)
        assert result is None

    def test_none_current_temp_returns_none(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        result = coordinator._compute_device_setpoint("heating", 0.5, None, 21.0, True)
        assert result is None

    def test_heating_computes_setpoint(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        # power_fraction=0.5, current=20, target=21, boost=30
        # sp = 20 + 0.5 * (30 - 20) = 25.0
        result = coordinator._compute_device_setpoint("heating", 0.5, 20.0, 21.0, True)
        assert result == 25.0

    def test_heating_floor_at_target(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        # power_fraction=0.01, current=20, target=21
        # sp = 20 + 0.01 * (30 - 20) = 20.1 -> clamped to target 21.0
        result = coordinator._compute_device_setpoint("heating", 0.01, 20.0, 21.0, True)
        assert result == 21.0

    def test_clamped_to_device_max_temp(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        # device_max_temp=25 is now used AS the boost target
        # power_fraction=0.5, current=20, boost=25 -> sp = 20 + 0.5*(25-20) = 22.5
        result = coordinator._compute_device_setpoint("heating", 0.5, 20.0, 21.0, True, device_max_temp=25.0)
        assert result == 22.5
        # power_fraction=1.0, current=20, boost=25 -> sp = 25.0
        result = coordinator._compute_device_setpoint("heating", 1.0, 20.0, 21.0, True, device_max_temp=25.0)
        assert result == 25.0

    def test_device_max_temp_none_no_clamping(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        # Without device_max_temp, should reach 30 (HEATING_BOOST_TARGET)
        result = coordinator._compute_device_setpoint("heating", 1.0, 20.0, 21.0, True, device_max_temp=None)
        assert result == 30.0

    def test_cooling_computes_setpoint(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        # power_fraction=0.5, current=26, AC_COOLING_BOOST_TARGET=16
        # sp = 26 - 0.5 * (26 - 16) = 21.0
        result = coordinator._compute_device_setpoint("cooling", 0.5, 26.0, 23.0, True, has_acs=True)
        assert result == 21.0

    def test_cooling_without_acs_returns_none(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        result = coordinator._compute_device_setpoint("cooling", 0.5, 26.0, 23.0, True, has_acs=False)
        assert result is None

    def test_heating_ac_only_room(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        # AC heating: AC_HEATING_BOOST_TARGET=30
        # sp = 20 + 0.5 * (30 - 20) = 25.0
        result = coordinator._compute_device_setpoint(
            "heating",
            0.5,
            20.0,
            21.0,
            True,
            has_thermostats=False,
            has_acs=True,
        )
        assert result == 25.0

    def test_cooling_clamped_to_device_min(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        # power_fraction=1.0, current=26, AC_COOLING_BOOST_TARGET=16
        # raw = 26 - 1.0 * (26 - 16) = 16.0, device_min_temp=18 -> clamped to 18.0
        result = coordinator._compute_device_setpoint(
            "cooling",
            1.0,
            26.0,
            23.0,
            True,
            device_min_temp=18.0,
            has_acs=True,
        )
        assert result == 18.0

    def test_dynamic_cooling_boost_proportional(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        # device_min_temp=18, pf=0.5: 26 - 0.5*(26-18) = 22.0
        result = coordinator._compute_device_setpoint(
            "cooling",
            0.5,
            26.0,
            23.0,
            True,
            device_min_temp=18.0,
            has_acs=True,
        )
        assert result == 22.0

    def test_all_direct_returns_target(self, hass, mock_config_entry):
        """When all devices are direct, return target_temp directly."""
        coordinator = _create_coordinator(hass, mock_config_entry)
        result = coordinator._compute_device_setpoint(
            "heating",
            1.0,
            20.0,
            21.0,
            True,
            all_direct=True,
        )
        assert result == 21.0

    def test_all_direct_cooling_returns_target(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        result = coordinator._compute_device_setpoint(
            "cooling",
            1.0,
            26.0,
            23.0,
            True,
            has_acs=True,
            all_direct=True,
        )
        assert result == 23.0

    def test_all_direct_no_sensor_still_none(self, hass, mock_config_entry):
        """all_direct with no external sensor still returns None."""
        coordinator = _create_coordinator(hass, mock_config_entry)
        result = coordinator._compute_device_setpoint(
            "heating",
            1.0,
            20.0,
            21.0,
            False,
            all_direct=True,
        )
        assert result is None

    def test_all_direct_adds_offset(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        result = coordinator._compute_device_setpoint(
            "heating",
            1.0,
            20.0,
            21.0,
            True,
            all_direct=True,
            direct_offset=1.5,
        )
        assert result == 22.5


class TestComputeDeviceSetpointOrchestrated:
    """Tests for _compute_device_setpoint_orchestrated with direct_eids."""

    def test_direct_device_returns_target(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        cmd = MagicMock()
        cmd.active = True
        cmd.entity_id = "climate.heater"
        cmd.device_type = "thermostat"
        cmd.power_fraction = 1.0
        plan = MagicMock()
        plan.commands = [cmd]
        result = coordinator._compute_device_setpoint_orchestrated(
            plan,
            20.0,
            21.0,
            30.0,
            28.0,
            direct_eids={"climate.heater"},
        )
        assert result == 21.0

    def test_proportional_device_computes_boost(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        cmd = MagicMock()
        cmd.active = True
        cmd.entity_id = "climate.trv1"
        cmd.device_type = "thermostat"
        cmd.power_fraction = 0.5
        plan = MagicMock()
        plan.commands = [cmd]
        result = coordinator._compute_device_setpoint_orchestrated(
            plan,
            20.0,
            21.0,
            30.0,
            28.0,
            direct_eids=set(),
        )
        # 20 + 0.5 * (30 - 20) = 25.0
        assert result == 25.0

    def test_no_direct_eids_defaults_to_proportional(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        cmd = MagicMock()
        cmd.active = True
        cmd.entity_id = "climate.trv1"
        cmd.device_type = "thermostat"
        cmd.power_fraction = 1.0
        plan = MagicMock()
        plan.commands = [cmd]
        result = coordinator._compute_device_setpoint_orchestrated(
            plan,
            20.0,
            21.0,
            30.0,
            28.0,
        )
        assert result == 30.0

    def test_direct_device_adds_offset(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        cmd = MagicMock()
        cmd.active = True
        cmd.entity_id = "climate.heater"
        cmd.device_type = "thermostat"
        cmd.power_fraction = 1.0
        plan = MagicMock()
        plan.commands = [cmd]
        result = coordinator._compute_device_setpoint_orchestrated(
            plan,
            20.0,
            21.0,
            30.0,
            28.0,
            direct_eids={"climate.heater"},
            direct_offsets={"climate.heater": -1.0},
        )
        assert result == 20.0


class TestReadDeviceTemp:
    """Tests for _read_device_temp."""

    def test_reads_from_thermostat(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        state = MagicMock()
        state.attributes = {"current_temperature": 21.5}
        hass.states.get = MagicMock(return_value=state)

        room = {
            "thermostats": ["climate.trv1"],
            "acs": [],
            "devices": [{"entity_id": "climate.trv1", "type": "trv", "role": "auto", "heating_system_type": ""}],
        }
        assert coordinator._read_device_temp(room) == 21.5

    def test_reads_from_ac_when_no_thermostat(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        state = MagicMock()
        state.attributes = {"current_temperature": 25.0}
        hass.states.get = MagicMock(return_value=state)

        room = {
            "thermostats": [],
            "acs": ["climate.ac1"],
            "devices": [{"entity_id": "climate.ac1", "type": "ac", "role": "auto", "heating_system_type": ""}],
        }
        assert coordinator._read_device_temp(room) == 25.0

    def test_no_devices(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        room = {"thermostats": [], "acs": [], "devices": []}
        assert coordinator._read_device_temp(room) is None

    def test_state_is_none(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        hass.states.get = MagicMock(return_value=None)
        room = {
            "thermostats": ["climate.trv1"],
            "acs": [],
            "devices": [{"entity_id": "climate.trv1", "type": "trv", "role": "auto", "heating_system_type": ""}],
        }
        assert coordinator._read_device_temp(room) is None

    def test_invalid_temperature_value(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        state = MagicMock()
        state.attributes = {"current_temperature": "unknown"}
        hass.states.get = MagicMock(return_value=state)

        room = {
            "thermostats": ["climate.trv1"],
            "acs": [],
            "devices": [{"entity_id": "climate.trv1", "type": "trv", "role": "auto", "heating_system_type": ""}],
        }
        assert coordinator._read_device_temp(room) is None

    def test_no_current_temp_attribute(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        state = MagicMock()
        state.attributes = {"temperature": 21.0}  # different key
        hass.states.get = MagicMock(return_value=state)

        room = {
            "thermostats": ["climate.trv1"],
            "acs": [],
            "devices": [{"entity_id": "climate.trv1", "type": "trv", "role": "auto", "heating_system_type": ""}],
        }
        assert coordinator._read_device_temp(room) is None


class TestFahrenheitConversion:
    """Tests for Fahrenheit temperature conversion at system boundaries."""

    @pytest.mark.asyncio
    async def test_fahrenheit_sensor_converted_to_celsius(self, hass, mock_config_entry):
        """When HA is in Fahrenheit, sensor temps are converted to Celsius internally."""
        from homeassistant.const import UnitOfTemperature

        hass.config.units.temperature_unit = UnitOfTemperature.FAHRENHEIT

        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}

        # Sensor reports 64.4degF (= 18degC), outdoor 50degF (= 10degC)
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                temp="64.4",
                humidity="55.0",
                outdoor_temp="50",
                temp_unit="°F",
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        # Internal current_temp should be Celsius (~18degC)
        assert room["current_temp"] == pytest.approx(18.0, abs=0.1)
        # Target temp should remain in Celsius (comfort_temp=21degC stored in Celsius)
        assert room["target_temp"] == pytest.approx(21.0, abs=0.1)
        # Mode should be heating (18degC < 21degC target)
        assert room["mode"] == "heating"

    @pytest.mark.asyncio
    async def test_valve_protection_set_temperature_in_fahrenheit(self, hass, mock_config_entry):
        """Valve protection set_temperature uses Fahrenheit when HA is in degF mode."""
        from homeassistant.const import UnitOfTemperature

        from custom_components.roommind.const import HEATING_BOOST_TARGET

        hass.config.units.temperature_unit = UnitOfTemperature.FAHRENHEIT

        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        store.get_settings.return_value = {
            "valve_protection_enabled": True,
            "valve_protection_interval_days": 7,
        }
        store.async_save_settings = AsyncMock()
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(temp="69.8", temp_unit="°F"),  # 69.8degF ~ 21degC
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._valve_manager._last_actuation["climate.living_room"] = time.time() - 8 * 86400
        coordinator._valve_manager._check_count = 119
        await coordinator._async_update_data()

        assert "climate.living_room" in coordinator._valve_manager._cycling

        # Find set_temperature calls for the cycling valve
        set_temp_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if c[0][0] == "climate"
            and c[0][1] == "set_temperature"
            and c[0][2].get("entity_id") == "climate.living_room"
        ]
        assert set_temp_calls
        # HEATING_BOOST_TARGET is 30degC -> 86degF
        expected_f = HEATING_BOOST_TARGET * 9 / 5 + 32  # 86degF
        temp_arg = set_temp_calls[0][0][2]["temperature"]
        assert temp_arg == pytest.approx(expected_f)

    @pytest.mark.asyncio
    async def test_fahrenheit_device_max_temp_converted_for_boost(self, hass, mock_config_entry):
        """Device max_temp in Fahrenheit is converted to Celsius for boost target (#117)."""
        from homeassistant.const import UnitOfTemperature

        hass.config.units.temperature_unit = UnitOfTemperature.FAHRENHEIT

        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}

        # TRV reports max_temp=95degF (= 35degC). Bug: treated as 95degC.
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                temp="64.4",
                humidity="55.0",
                outdoor_temp="50",
                temp_unit="°F",
                extra={
                    "climate.living_room": (
                        "heat",
                        {
                            "current_temperature": 64.4,
                            "temperature": 69.8,
                            "max_temp": 95.0,
                            "min_temp": 44.6,
                            "hvac_modes": ["off", "heat"],
                            "hvac_action": "heating",
                        },
                    ),
                },
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        # device_setpoint is in Celsius. With the bug it would be ~95.
        # After fix: boost = 35degC (converted from 95degF), so setpoint <= 35.
        assert room["device_setpoint"] is not None
        assert room["device_setpoint"] <= 35.0

    @pytest.mark.asyncio
    async def test_fahrenheit_set_temperature_uses_converted_boost(self, hass, mock_config_entry):
        """set_temperature call must not exceed device max in Fahrenheit (#117)."""
        from homeassistant.const import UnitOfTemperature

        hass.config.units.temperature_unit = UnitOfTemperature.FAHRENHEIT

        store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
        hass.data = {"roommind": {"store": store}}

        # TRV reports max_temp=95degF (= 35degC)
        hass.states.get = MagicMock(
            side_effect=make_mock_states_get(
                temp="64.4",
                humidity="55.0",
                outdoor_temp="50",
                temp_unit="°F",
                extra={
                    "climate.living_room": (
                        "heat",
                        {
                            "current_temperature": 64.4,
                            "temperature": 69.8,
                            "max_temp": 95.0,
                            "min_temp": 44.6,
                            "hvac_modes": ["off", "heat"],
                            "hvac_action": "heating",
                        },
                    ),
                },
            ),
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        # Find set_temperature calls for the TRV
        set_temp_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if c[0][0] == "climate"
            and c[0][1] == "set_temperature"
            and c[0][2].get("entity_id") == "climate.living_room"
        ]
        assert set_temp_calls
        # Temperature must be <= 95degF (device max). With the bug it would be 203degF.
        temp_arg = set_temp_calls[0][0][2].get("temperature")
        if temp_arg is not None:
            assert temp_arg <= 95.0, f"set_temperature sent {temp_arg}degF, exceeds device max 95degF"


class TestManagedModeDisplay:
    """Tests for Managed Mode display and EKF training fixes (#69)."""

    @pytest.mark.asyncio
    async def test_managed_mode_display_idle_at_setpoint(self, hass, mock_config_entry):
        """Managed Mode: device at setpoint without hvac_action -> display idle (#69)."""
        store = _make_store_mock({"living_room_abc12345": MANAGED_ROOM})
        hass.data = {"roommind": {"store": store}}

        # Device in heat mode, current_temp (21) >= setpoint (21) -> inferred idle
        device_state = MagicMock()
        device_state.state = "heat"
        device_state.attributes = {
            "current_temperature": 21.0,
            "temperature": 21.0,
            "hvac_modes": ["off", "heat"],
        }
        base_mock = make_mock_states_get(temp=None, humidity="55.0")

        def custom_get(eid):
            if eid == "climate.living_room":
                return device_state
            return base_mock(eid)

        hass.states.get = MagicMock(side_effect=custom_get)
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mode"] == "idle", "Managed Mode should show idle when device is at setpoint"
        assert room["heating_power"] == 0

    @pytest.mark.asyncio
    async def test_managed_mode_display_heating_below_setpoint(self, hass, mock_config_entry):
        """Managed Mode: device below setpoint without hvac_action -> display heating (#69)."""
        store = _make_store_mock({"living_room_abc12345": MANAGED_ROOM})
        hass.data = {"roommind": {"store": store}}

        # Device in heat mode, current_temp (18) < setpoint (21) -> inferred heating
        device_state = MagicMock()
        device_state.state = "heat"
        device_state.attributes = {
            "current_temperature": 18.0,
            "temperature": 21.0,
            "hvac_modes": ["off", "heat"],
        }
        base_mock = make_mock_states_get(temp=None, humidity="55.0")

        def custom_get(eid):
            if eid == "climate.living_room":
                return device_state
            return base_mock(eid)

        hass.states.get = MagicMock(side_effect=custom_get)
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mode"] == "heating", "Managed Mode should show heating when device is below setpoint"
        assert room["heating_power"] == 100

    @pytest.mark.asyncio
    async def test_managed_mode_display_uses_hvac_action(self, hass, mock_config_entry):
        """Managed Mode: device with hvac_action=idle -> display idle (#69)."""
        store = _make_store_mock({"living_room_abc12345": MANAGED_ROOM})
        hass.data = {"roommind": {"store": store}}

        device_state = MagicMock()
        device_state.state = "heat"
        device_state.attributes = {
            "hvac_action": "idle",
            "current_temperature": 21.0,
            "temperature": 21.0,
            "hvac_modes": ["off", "heat"],
        }
        base_mock = make_mock_states_get(temp=None, humidity="55.0")

        def custom_get(eid):
            if eid == "climate.living_room":
                return device_state
            return base_mock(eid)

        hass.states.get = MagicMock(side_effect=custom_get)
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mode"] == "idle", "Managed Mode should use hvac_action when available"

    @pytest.mark.asyncio
    async def test_managed_mode_ekf_trains_inferred_idle(self, hass, mock_config_entry):
        """Managed Mode: EKF should train with inferred idle, not always heating (#69)."""
        store = _make_store_mock({"living_room_abc12345": MANAGED_ROOM})
        hass.data = {"roommind": {"store": store}}

        # Device at setpoint -> inferred idle. EKF should see idle, not heating.
        device_state = MagicMock()
        device_state.state = "heat"
        device_state.attributes = {
            "current_temperature": 21.0,
            "temperature": 21.0,
            "hvac_modes": ["off", "heat"],
        }
        base_mock = make_mock_states_get(temp=None, humidity="55.0")

        def custom_get(eid):
            if eid == "climate.living_room":
                return device_state
            return base_mock(eid)

        hass.states.get = MagicMock(side_effect=custom_get)
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        for _ in range(13):
            await coordinator._async_update_data()

        n_idle, n_heating, n_cooling = coordinator._model_manager.get_mode_counts(
            "living_room_abc12345",
        )
        assert n_idle > 0, "EKF should have idle training samples in Managed Mode at setpoint"
        assert n_heating == 0, "EKF should NOT train as heating when device is at setpoint"

    @pytest.mark.asyncio
    async def test_managed_mode_display_cooling_idle_at_setpoint(self, hass, mock_config_entry):
        """Managed Mode cooling: AC at setpoint without hvac_action -> display idle (#69)."""
        managed_cool_room = {
            **MANAGED_ROOM,
            "thermostats": [],
            "acs": ["climate.living_room"],
            "devices": [{"entity_id": "climate.living_room", "type": "ac", "role": "auto", "heating_system_type": ""}],
            "climate_mode": "cool_only",
        }
        store = _make_store_mock({"living_room_abc12345": managed_cool_room})
        hass.data = {"roommind": {"store": store}}

        # AC in cool mode, current_temp (21) <= setpoint (22) -> inferred idle
        device_state = MagicMock()
        device_state.state = "cool"
        device_state.attributes = {
            "current_temperature": 21.0,
            "temperature": 22.0,
            "hvac_modes": ["off", "cool"],
        }
        base_mock = make_mock_states_get(temp=None, humidity="55.0")

        def custom_get(eid):
            if eid == "climate.living_room":
                return device_state
            return base_mock(eid)

        hass.states.get = MagicMock(side_effect=custom_get)
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room_abc12345"]
        assert room["mode"] == "idle", "Managed Mode should show idle when AC is at setpoint"
