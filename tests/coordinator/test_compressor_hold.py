"""Coordinator-level tests for the compressor min-run hold (#436, #416)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.const import MODE_HEATING, MODE_IDLE

from .conftest import (
    SAMPLE_ROOM,
    _create_coordinator,
    _make_store_mock,
    make_mock_states_get,
)

AC = "climate.living_room_ac"
AC2 = "climate.bedroom_ac"
AREA = "living_room_abc12345"

AC_ROOM = {
    **SAMPLE_ROOM,
    "thermostats": [],
    "acs": [AC],
    "devices": [{"entity_id": AC, "type": "ac", "role": "auto", "heating_system_type": ""}],
    "climate_mode": "heat_only",
}

GROUP = {
    "id": "group1",
    "name": "Outdoor Unit",
    "members": [AC],
    "min_run_minutes": 15,
    "min_off_minutes": 5,
}


def _ac_state(state: str, setpoint: float | None = None):
    s = MagicMock()
    s.state = state
    s.attributes = {
        "hvac_modes": ["heat", "cool", "off"],
        "min_temp": 16.0,
        "max_temp": 30.0,
        "temperature": setpoint,
    }
    return s


def _wire_states(hass, ac_holder: dict, *, temp: str):
    base = make_mock_states_get(temp=temp)

    def _get(eid):
        if eid == AC:
            return ac_holder["state"]
        return base(eid)

    hass.states.get = MagicMock(side_effect=_get)


def _age_mode(coordinator):
    """Pretend the current mode started long ago so the room-level min-run window is over."""
    if AREA in coordinator._mode_on_since:
        coordinator._mode_on_since[AREA] -= 3600


def _calls(hass, service: str):
    return [c for c in hass.services.async_call.call_args_list if c[0][1] == service and c[0][2]["entity_id"] == AC]


async def _setup(hass, mock_config_entry, room=AC_ROOM, groups=(GROUP,)):
    store = _make_store_mock({AREA: room}, settings={"compressor_groups": list(groups)})
    hass.data = {"roommind": {"store": store}}
    hass.services.async_call = AsyncMock()
    return _create_coordinator(hass, mock_config_entry)


class TestHoldKeepsSetpoint:
    @pytest.mark.asyncio
    async def test_idle_during_min_run_sends_no_setpoint(self, hass, mock_config_entry):
        """Room reaches target during min-run: device keeps its boost setpoint (#436)."""
        coordinator = await _setup(hass, mock_config_entry)
        ac = {"state": _ac_state("off", 16.0)}

        # Tick 1: cold room -> heating, boost setpoint goes out
        _wire_states(hass, ac, temp="18.0")
        data = await coordinator._async_update_data()
        assert data["rooms"][AREA]["mode"] == MODE_HEATING
        boost = _calls(hass, "set_temperature")[-1][0][2]["temperature"]
        assert boost > 21.0

        # Device now reports heat at the boost setpoint, room is above target
        ac["state"] = _ac_state("heat", boost)
        hass.services.async_call.reset_mock()
        _wire_states(hass, ac, temp="22.5")
        _age_mode(coordinator)
        data = await coordinator._async_update_data()

        assert data["rooms"][AREA]["mode"] == MODE_IDLE
        assert data["rooms"][AREA]["compressor_protection_reason"] == "min_run"
        assert _calls(hass, "set_temperature") == []
        assert _calls(hass, "set_hvac_mode") == []

    @pytest.mark.asyncio
    async def test_setpoint_does_not_pendulum_between_heating_and_hold(self, hass, mock_config_entry):
        """Heating -> idle -> heating around the target must not alternate setpoints (#416)."""
        coordinator = await _setup(hass, mock_config_entry)
        ac = {"state": _ac_state("off", 16.0)}
        sent: list[float] = []

        def _track():
            for c in _calls(hass, "set_temperature"):
                sent.append(c[0][2]["temperature"])
                ac["state"] = _ac_state("heat", c[0][2]["temperature"])
            hass.services.async_call.reset_mock()

        modes = []
        for temp in ("18.0", "22.5", "20.5", "22.5", "20.5"):
            _wire_states(hass, ac, temp=temp)
            _age_mode(coordinator)
            data = await coordinator._async_update_data()
            modes.append(data["rooms"][AREA]["mode"])
            _track()

        assert modes == [MODE_HEATING, MODE_IDLE, MODE_HEATING, MODE_IDLE, MODE_HEATING]
        assert len(sent) == 1, f"setpoint pendulums: {sent}"


class TestHoldSurvivesStateLag:
    @pytest.mark.asyncio
    async def test_device_still_reporting_off_right_after_start(self, hass, mock_config_entry):
        """A device whose state lags behind the command must not lose the hold (#436)."""
        coordinator = await _setup(hass, mock_config_entry)
        ac = {"state": _ac_state("off", 16.0)}

        _wire_states(hass, ac, temp="18.0")
        await coordinator._async_update_data()
        assert coordinator._compressor_manager.is_compressor_running("group1")

        # Room reaches target, but the integration has not polled the new state yet
        hass.services.async_call.reset_mock()
        _wire_states(hass, ac, temp="22.5")
        _age_mode(coordinator)
        await coordinator._async_update_data()
        await coordinator._async_update_data()

        assert coordinator._compressor_manager.is_compressor_running("group1")
        assert [c for c in _calls(hass, "set_hvac_mode") if c[0][2]["hvac_mode"] == "off"] == []

    @pytest.mark.asyncio
    async def test_manual_off_is_respected_after_grace(self, hass, mock_config_entry):
        """A device that stays off well past the grace window counts as switched off by the user."""
        coordinator = await _setup(hass, mock_config_entry)
        ac = {"state": _ac_state("off", 16.0)}

        _wire_states(hass, ac, temp="18.0")
        await coordinator._async_update_data()

        _wire_states(hass, ac, temp="22.5")
        _age_mode(coordinator)
        with patch("custom_components.roommind.managers.compressor_group_manager.monotonic") as mono:
            mono.return_value = coordinator._compressor_manager.get_state("group1").compressor_on_since + 300
            await coordinator._async_update_data()

        # min-run (15 min) is still open, but the device has been off for longer than the grace window
        assert not coordinator._compressor_manager.is_compressor_running("group1")


class TestOrchestratedParkedAc:
    @pytest.mark.asyncio
    async def test_parked_ac_is_not_tracked_as_running(self, hass, mock_config_entry):
        """An AC the heat-source plan parks must not count as an active compressor member."""
        from custom_components.roommind.managers.heat_source_orchestrator import DeviceCommand, HeatSourcePlan

        room = {
            **AC_ROOM,
            "thermostats": ["climate.living_room"],
            "devices": [
                {"entity_id": "climate.living_room", "type": "trv", "role": "auto", "heating_system_type": ""},
                {"entity_id": AC, "type": "ac", "role": "auto", "heating_system_type": ""},
            ],
            "heat_source_orchestration": True,
        }
        coordinator = await _setup(hass, mock_config_entry, room=room)
        ac = {"state": _ac_state("off", 16.0)}
        _wire_states(hass, ac, temp="18.0")
        plan = HeatSourcePlan(
            commands=[
                DeviceCommand("climate.living_room", "primary", "thermostat", True, 1.0, "t"),
                DeviceCommand(AC, "secondary", "ac", False, 0.0, "t"),
            ],
            active_sources="primary",
            reason="t",
        )
        with patch("custom_components.roommind.coordinator.evaluate_heat_sources", return_value=plan):
            data = await coordinator._async_update_data()

        assert data["rooms"][AREA]["mode"] == MODE_HEATING
        assert not coordinator._compressor_manager.is_compressor_running("group1")

    @pytest.mark.asyncio
    async def test_ac_parked_by_plan_keeps_running_during_min_run(self, hass, mock_config_entry):
        """The plan switching the AC off mid-run must wait for min-run like any other stop."""
        from custom_components.roommind.managers.heat_source_orchestrator import DeviceCommand, HeatSourcePlan

        room = {
            **AC_ROOM,
            "thermostats": ["climate.living_room"],
            "devices": [
                {"entity_id": "climate.living_room", "type": "trv", "role": "auto", "heating_system_type": ""},
                {"entity_id": AC, "type": "ac", "role": "auto", "heating_system_type": ""},
            ],
            "heat_source_orchestration": True,
        }
        coordinator = await _setup(hass, mock_config_entry, room=room)
        ac = {"state": _ac_state("off", 16.0)}
        _wire_states(hass, ac, temp="18.0")
        both = HeatSourcePlan(
            commands=[
                DeviceCommand("climate.living_room", "primary", "thermostat", True, 1.0, "t"),
                DeviceCommand(AC, "secondary", "ac", True, 1.0, "t"),
            ],
            active_sources="both",
            reason="t",
        )
        trv_only = HeatSourcePlan(
            commands=[
                DeviceCommand("climate.living_room", "primary", "thermostat", True, 1.0, "t"),
                DeviceCommand(AC, "secondary", "ac", False, 0.0, "t"),
            ],
            active_sources="primary",
            reason="t",
        )
        with patch("custom_components.roommind.coordinator.evaluate_heat_sources", side_effect=[both, trv_only]):
            await coordinator._async_update_data()
            ac["state"] = _ac_state("heat", 24.0)
            hass.services.async_call.reset_mock()
            await coordinator._async_update_data()

        assert [c for c in _calls(hass, "set_hvac_mode") if c[0][2]["hvac_mode"] == "off"] == []
        assert coordinator._compressor_manager.is_compressor_running("group1")
