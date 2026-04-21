"""Tests for fan-only and setback idle modes."""

from __future__ import annotations

from unittest.mock import ANY, MagicMock

import pytest

from custom_components.roommind.const import MODE_IDLE, TargetTemps
from custom_components.roommind.control.mpc_controller import (
    MPCController,
    _last_commands,
    async_idle_device,
    clear_command_cache,
)
from custom_components.roommind.control.thermal_model import RoomModelManager

from .conftest import build_hass, make_room

# ---------------------------------------------------------------------------
# async_idle_device — unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_idle_device_off():
    """Device with idle_action='off' delegates to async_turn_off_climate."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"]}
    hass.states.get = MagicMock(return_value=state)

    devices = [{"entity_id": "climate.ac1", "type": "ac", "role": "auto", "idle_action": "off", "idle_fan_mode": ""}]
    await async_idle_device(hass, "climate.ac1", devices, area_id="living_room")

    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.ac1", "hvac_mode": "off"},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_async_idle_device_fan_only():
    """Device with idle_action='fan_only' and supported fan_only mode sets fan_only + fan_mode."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {"hvac_modes": ["cool", "fan_only", "off"], "fan_modes": ["low", "medium", "high"]}
    hass.states.get = MagicMock(return_value=state)

    devices = [
        {"entity_id": "climate.ac1", "type": "ac", "role": "auto", "idle_action": "fan_only", "idle_fan_mode": "low"}
    ]
    await async_idle_device(hass, "climate.ac1", devices, area_id="living_room")

    calls = hass.services.async_call.call_args_list
    assert len(calls) == 2
    assert calls[0][0] == ("climate", "set_hvac_mode", {"entity_id": "climate.ac1", "hvac_mode": "fan_only"})
    assert calls[1][0] == ("climate", "set_fan_mode", {"entity_id": "climate.ac1", "fan_mode": "low"})


@pytest.mark.asyncio
async def test_async_idle_device_fan_only_unsupported():
    """Device with idle_action='fan_only' but fan_only NOT in hvac_modes falls back to off."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {"hvac_modes": ["cool", "off"], "fan_modes": ["low"]}
    hass.states.get = MagicMock(return_value=state)

    devices = [
        {"entity_id": "climate.ac1", "type": "ac", "role": "auto", "idle_action": "fan_only", "idle_fan_mode": "low"}
    ]
    await async_idle_device(hass, "climate.ac1", devices, area_id="living_room")

    # Falls back to async_turn_off_climate which calls set_hvac_mode off
    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.ac1", "hvac_mode": "off"},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_async_idle_device_fan_only_redundancy():
    """Device already in fan_only with correct fan_mode skips service calls."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "fan_only"
    state.attributes = {"hvac_modes": ["cool", "fan_only", "off"], "fan_modes": ["low", "medium"], "fan_mode": "low"}
    hass.states.get = MagicMock(return_value=state)

    devices = [
        {"entity_id": "climate.ac1", "type": "ac", "role": "auto", "idle_action": "fan_only", "idle_fan_mode": "low"}
    ]
    await async_idle_device(hass, "climate.ac1", devices, area_id="living_room")

    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_async_idle_device_fan_only_custom_fan_mode():
    """Custom idle_fan_mode='medium' calls set_fan_mode('medium')."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {"hvac_modes": ["cool", "fan_only", "off"], "fan_modes": ["low", "medium", "high"]}
    hass.states.get = MagicMock(return_value=state)

    devices = [
        {
            "entity_id": "climate.ac1",
            "type": "ac",
            "role": "auto",
            "idle_action": "fan_only",
            "idle_fan_mode": "medium",
        }
    ]
    await async_idle_device(hass, "climate.ac1", devices, area_id="living_room")

    calls = hass.services.async_call.call_args_list
    fan_mode_calls = [c for c in calls if c[0][1] == "set_fan_mode"]
    assert len(fan_mode_calls) == 1
    assert fan_mode_calls[0][0][2]["fan_mode"] == "medium"


@pytest.mark.asyncio
async def test_async_idle_device_no_device_config():
    """Entity not found in devices[] defaults to 'off' behavior."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"]}
    hass.states.get = MagicMock(return_value=state)

    # Empty devices list, entity not found
    await async_idle_device(hass, "climate.unknown", [], area_id="living_room")

    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.unknown", "hvac_mode": "off"},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_async_idle_device_fan_mode_not_in_fan_modes():
    """idle_fan_mode='turbo' not in fan_modes: hvac_mode=fan_only IS set, fan_mode call is SKIPPED."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {"hvac_modes": ["cool", "fan_only", "off"], "fan_modes": ["low", "medium", "high"]}
    hass.states.get = MagicMock(return_value=state)

    devices = [
        {
            "entity_id": "climate.ac1",
            "type": "ac",
            "role": "auto",
            "idle_action": "fan_only",
            "idle_fan_mode": "turbo",
        }
    ]
    await async_idle_device(hass, "climate.ac1", devices, area_id="living_room")

    calls = hass.services.async_call.call_args_list
    # set_hvac_mode(fan_only) should be called
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    assert len(hvac_calls) == 1
    assert hvac_calls[0][0][2]["hvac_mode"] == "fan_only"
    # set_fan_mode should NOT be called (turbo not supported)
    fan_calls = [c for c in calls if c[0][1] == "set_fan_mode"]
    assert len(fan_calls) == 0


# ---------------------------------------------------------------------------
# async_apply integration tests with fan_only idle_action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mpc_apply_idle_respects_fan_only():
    """async_apply(MODE_IDLE) with AC device that has idle_action='fan_only' uses fan_only."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {
        "hvac_modes": ["cool", "fan_only", "off"],
        "fan_modes": ["low", "medium", "high"],
        "temperature": 23.0,
    }
    hass.states.get = MagicMock(return_value=state)

    room = make_room(thermostats=[], acs=["climate.ac1"])
    # Override devices with fan_only config
    room["devices"] = [
        {
            "entity_id": "climate.ac1",
            "type": "ac",
            "role": "auto",
            "heating_system_type": "",
            "idle_action": "fan_only",
            "idle_fan_mode": "low",
        }
    ]
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("idle", 23.0)

    calls = hass.services.async_call.call_args_list
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    assert any(c[0][2].get("hvac_mode") == "fan_only" for c in hvac_calls)
    fan_calls = [c for c in calls if c[0][1] == "set_fan_mode"]
    assert any(c[0][2].get("fan_mode") == "low" for c in fan_calls)
    # No "off" calls
    off_calls = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2].get("hvac_mode") == "off"]
    assert len(off_calls) == 0


@pytest.mark.asyncio
async def test_mpc_apply_idle_forced_on_overrides_fan_only():
    """Device in compressor_forced_on during IDLE runs forced_on logic, NOT fan_only."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {
        "hvac_modes": ["cool", "fan_only", "off"],
        "fan_modes": ["low"],
        "temperature": 25.0,
    }
    hass.states.get = MagicMock(return_value=state)

    room = make_room(thermostats=[], acs=["climate.ac1"])
    room["devices"] = [
        {
            "entity_id": "climate.ac1",
            "type": "ac",
            "role": "auto",
            "heating_system_type": "",
            "idle_action": "fan_only",
            "idle_fan_mode": "low",
        }
    ]
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("idle", 23.0, compressor_forced_on={"climate.ac1"})

    calls = hass.services.async_call.call_args_list
    # forced_on sets temperature, does NOT switch to fan_only
    fan_only_calls = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2].get("hvac_mode") == "fan_only"]
    assert len(fan_only_calls) == 0
    # Verify forced_on DID call set_temperature (positive assertion)
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert len(temp_calls) >= 1


@pytest.mark.asyncio
async def test_mpc_apply_heating_forced_off_fan_only():
    """AC with idle_action='fan_only' in compressor_forced_off during HEATING uses fan_only."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {
        "hvac_modes": ["heat", "cool", "fan_only", "off"],
        "fan_modes": ["low", "medium"],
        "temperature": 20.0,
    }
    hass.states.get = MagicMock(return_value=state)

    room = make_room(thermostats=[], acs=["climate.ac1"])
    room["devices"] = [
        {
            "entity_id": "climate.ac1",
            "type": "ac",
            "role": "auto",
            "heating_system_type": "",
            "idle_action": "fan_only",
            "idle_fan_mode": "low",
        }
    ]
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0, compressor_forced_off={"climate.ac1"})

    calls = hass.services.async_call.call_args_list
    # Should use fan_only instead of off
    fan_only_calls = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2].get("hvac_mode") == "fan_only"]
    assert len(fan_only_calls) >= 1
    off_calls = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2].get("hvac_mode") == "off"]
    assert len(off_calls) == 0


@pytest.mark.asyncio
async def test_mpc_apply_call_hvac_off_uses_idle_action():
    """Verify _call('set_hvac_mode', hvac_mode='off') delegates to async_idle_device."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {
        "hvac_modes": ["cool", "fan_only", "off"],
        "fan_modes": ["low"],
        "temperature": 23.0,
    }
    hass.states.get = MagicMock(return_value=state)

    # Room with TRV + AC. During cooling, TRVs get "off" via _call.
    # If the TRV has idle_action=fan_only, it should get fan_only.
    room = make_room(thermostats=["climate.trv1"], acs=["climate.ac1"])
    room["devices"] = [
        {
            "entity_id": "climate.trv1",
            "type": "trv",
            "role": "auto",
            "heating_system_type": "",
            "idle_action": "fan_only",
            "idle_fan_mode": "low",
        },
        {
            "entity_id": "climate.ac1",
            "type": "ac",
            "role": "auto",
            "heating_system_type": "",
            "idle_action": "off",
            "idle_fan_mode": "",
        },
    ]
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    # During cooling, TRVs are set to "off" via _call -> async_idle_device
    await ctrl.async_apply("cooling", 23.0)

    calls = hass.services.async_call.call_args_list
    # TRV should get fan_only (not off) via the _call delegation to async_idle_device
    trv_fan_only = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.trv1"
        and c[0][1] == "set_hvac_mode"
        and c[0][2].get("hvac_mode") == "fan_only"
    ]
    assert len(trv_fan_only) >= 1
    trv_off = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.trv1"
        and c[0][1] == "set_hvac_mode"
        and c[0][2].get("hvac_mode") == "off"
    ]
    assert len(trv_off) == 0


# ---------------------------------------------------------------------------
# async_idle_device — "low" unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_idle_device_low_lowers_to_min_temp():
    """Device with idle_action='low' lowers setpoint to min_temp and never sends set_hvac_mode."""
    clear_command_cache()
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {
        "hvac_modes": ["heat", "off"],
        "min_temp": 5.0,
        "max_temp": 35.0,
        "temperature": 21.0,
    }
    hass.states.get = MagicMock(return_value=state)

    devices = [{"entity_id": "climate.trv1", "type": "trv", "role": "auto", "idle_action": "low", "idle_fan_mode": ""}]
    await async_idle_device(hass, "climate.trv1", devices, area_id="living_room")

    calls = hass.services.async_call.call_args_list
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert len(temp_calls) == 1
    assert temp_calls[0][0][2]["temperature"] == 5.0
    assert temp_calls[0][0][2]["entity_id"] == "climate.trv1"
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    assert len(hvac_calls) == 0


@pytest.mark.asyncio
async def test_async_idle_device_low_redundancy():
    """Device with idle_action='low' already at min_temp skips the call."""
    clear_command_cache()
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {
        "hvac_modes": ["heat", "off"],
        "min_temp": 5.0,
        "max_temp": 35.0,
        "temperature": 5.0,
    }
    hass.states.get = MagicMock(return_value=state)

    devices = [{"entity_id": "climate.trv1", "type": "trv", "role": "auto", "idle_action": "low", "idle_fan_mode": ""}]
    await async_idle_device(hass, "climate.trv1", devices, area_id="living_room")

    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_async_idle_device_low_no_state_noop():
    """Device with idle_action='low' and no state performs no service call."""
    clear_command_cache()
    hass = build_hass()
    hass.states.get = MagicMock(return_value=None)

    devices = [{"entity_id": "climate.trv1", "type": "trv", "role": "auto", "idle_action": "low", "idle_fan_mode": ""}]
    await async_idle_device(hass, "climate.trv1", devices, area_id="living_room")

    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_async_idle_device_low_falls_back_to_heat_target_when_min_temp_invalid():
    """When device reports min_temp <= 0, 'low' falls back to heat target minus setback offset."""
    clear_command_cache()
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {
        "hvac_modes": ["heat", "off"],
        "min_temp": 0.0,
        "max_temp": 35.0,
        "temperature": 21.0,
    }
    hass.states.get = MagicMock(return_value=state)

    devices = [{"entity_id": "climate.trv1", "type": "trv", "role": "auto", "idle_action": "low", "idle_fan_mode": ""}]
    targets = TargetTemps(heat=21.0, cool=None)
    await async_idle_device(hass, "climate.trv1", devices, area_id="living_room", targets=targets)

    calls = hass.services.async_call.call_args_list
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert len(temp_calls) == 1
    # heat - DEFAULT_IDLE_SETBACK_OFFSET = 21 - 2 = 19
    assert temp_calls[0][0][2]["temperature"] == 19.0
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    assert len(hvac_calls) == 0


@pytest.mark.asyncio
async def test_async_idle_device_low_window_open_targets_none():
    """Window open triggers idle with targets=None; 'low' still uses min_temp."""
    clear_command_cache()
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {
        "hvac_modes": ["heat", "off"],
        "min_temp": 5.0,
        "max_temp": 35.0,
        "temperature": 21.0,
    }
    hass.states.get = MagicMock(return_value=state)

    devices = [{"entity_id": "climate.trv1", "type": "trv", "role": "auto", "idle_action": "low", "idle_fan_mode": ""}]
    # targets=None simulates a window-open idle path in the coordinator
    await async_idle_device(hass, "climate.trv1", devices, area_id="living_room", targets=None)

    calls = hass.services.async_call.call_args_list
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert len(temp_calls) == 1
    assert temp_calls[0][0][2]["temperature"] == 5.0
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    assert len(hvac_calls) == 0


@pytest.mark.asyncio
async def test_async_idle_device_low_no_min_temp_and_no_targets_is_noop():
    """No usable min_temp and no targets: 'low' is a no-op (never falls back to off)."""
    clear_command_cache()
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {
        "hvac_modes": ["heat", "off"],
        # min_temp reported as 0.0 (Z2M/firmware bug), no fallback available
        "min_temp": 0.0,
        "max_temp": 35.0,
        "temperature": 21.0,
    }
    hass.states.get = MagicMock(return_value=state)

    devices = [{"entity_id": "climate.trv1", "type": "trv", "role": "auto", "idle_action": "low", "idle_fan_mode": ""}]
    await async_idle_device(hass, "climate.trv1", devices, area_id="living_room", targets=None)

    # No service call at all — explicitly NOT falling back to async_turn_off_climate,
    # since that would defeat the purpose of idle_action="low".
    hass.services.async_call.assert_not_called()


# ---------------------------------------------------------------------------
# MPCController integration — "low" idle_action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mpc_apply_heating_forced_off_trv_low():
    """TRV with idle_action='low' in compressor_forced_off during HEATING lowers to min_temp."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {
        "hvac_modes": ["heat", "off"],
        "min_temp": 5.0,
        "max_temp": 35.0,
        "temperature": 21.0,
    }
    hass.states.get = MagicMock(return_value=state)

    room = make_room(thermostats=["climate.trv_low"], acs=[])
    room["devices"] = [
        {
            "entity_id": "climate.trv_low",
            "type": "trv",
            "role": "auto",
            "heating_system_type": "",
            "idle_action": "low",
            "setpoint_mode": "proportional",
        }
    ]
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0, compressor_forced_off={"climate.trv_low"})

    calls = hass.services.async_call.call_args_list
    # Setpoint must be lowered to min_temp
    temp_calls = [c for c in calls if c[0][1] == "set_temperature" and c[0][2].get("entity_id") == "climate.trv_low"]
    assert len(temp_calls) >= 1
    assert temp_calls[-1][0][2]["temperature"] == 5.0
    # No set_hvac_mode("off") for this entity
    off_calls = [
        c
        for c in calls
        if c[0][1] == "set_hvac_mode"
        and c[0][2].get("entity_id") == "climate.trv_low"
        and c[0][2].get("hvac_mode") == "off"
    ]
    assert off_calls == []


@pytest.mark.asyncio
async def test_mpc_apply_call_hvac_off_delegates_low():
    """_call('set_hvac_mode', hvac_mode='off') delegates to LOW branch for idle_action='low'."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {
        "hvac_modes": ["heat", "cool", "off"],
        "min_temp": 5.0,
        "max_temp": 35.0,
        "temperature": 23.0,
    }
    hass.states.get = MagicMock(return_value=state)

    # Room with TRV (low) + AC — during cooling, TRVs get "off" via _call.
    # The TRV with idle_action="low" should get its setpoint lowered instead.
    room = make_room(thermostats=["climate.trv_low"], acs=["climate.ac1"])
    room["devices"] = [
        {
            "entity_id": "climate.trv_low",
            "type": "trv",
            "role": "auto",
            "heating_system_type": "",
            "idle_action": "low",
            "setpoint_mode": "proportional",
        },
        {
            "entity_id": "climate.ac1",
            "type": "ac",
            "role": "auto",
            "heating_system_type": "",
            "idle_action": "off",
            "setpoint_mode": "proportional",
        },
    ]
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("cooling", 23.0)

    calls = hass.services.async_call.call_args_list
    # TRV should receive min_temp setpoint, NOT set_hvac_mode(off)
    trv_temp = [c for c in calls if c[0][2].get("entity_id") == "climate.trv_low" and c[0][1] == "set_temperature"]
    assert len(trv_temp) >= 1
    assert trv_temp[-1][0][2]["temperature"] == 5.0
    trv_off = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.trv_low"
        and c[0][1] == "set_hvac_mode"
        and c[0][2].get("hvac_mode") == "off"
    ]
    assert trv_off == []


@pytest.mark.asyncio
async def test_mpc_apply_heat_source_inactive_trv_low():
    """Heat Source Orchestration: inactive TRV with idle_action='low' lowers to min_temp."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {
        "hvac_modes": ["heat", "off"],
        "min_temp": 5.0,
        "max_temp": 35.0,
        "temperature": 21.0,
    }
    ac_state = MagicMock()
    ac_state.state = "heat"
    ac_state.attributes = {
        "hvac_modes": ["heat", "cool", "off"],
        "min_temp": 16.0,
        "max_temp": 30.0,
        "temperature": 23.0,
    }

    def states_get(eid):
        if eid == "climate.ac1":
            return ac_state
        return state

    hass.states.get = MagicMock(side_effect=states_get)

    room = make_room(
        thermostats=["climate.trv_low"],
        acs=["climate.ac1"],
        heat_source_orchestration=True,
    )
    room["devices"] = [
        {
            "entity_id": "climate.trv_low",
            "type": "trv",
            "role": "auto",
            "heating_system_type": "",
            "idle_action": "low",
            "setpoint_mode": "proportional",
        },
        {
            "entity_id": "climate.ac1",
            "type": "ac",
            "role": "auto",
            "heating_system_type": "",
            "idle_action": "off",
            "setpoint_mode": "proportional",
        },
    ]

    from custom_components.roommind.managers.heat_source_orchestrator import (
        DeviceCommand,
        HeatSourcePlan,
    )

    plan = HeatSourcePlan(
        commands=[
            DeviceCommand(
                entity_id="climate.ac1",
                role="primary",
                device_type="ac",
                active=True,
                power_fraction=1.0,
                reason="primary",
            ),
            DeviceCommand(
                entity_id="climate.trv_low",
                role="secondary",
                device_type="thermostat",
                active=False,
                power_fraction=0.0,
                reason="not selected",
            ),
        ],
        active_sources="primary",
        reason="orchestrated",
    )

    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 20.0, heat_source_plan=plan)

    calls = hass.services.async_call.call_args_list
    trv_temp = [c for c in calls if c[0][2].get("entity_id") == "climate.trv_low" and c[0][1] == "set_temperature"]
    assert len(trv_temp) >= 1
    assert trv_temp[-1][0][2]["temperature"] == 5.0
    trv_off = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.trv_low"
        and c[0][1] == "set_hvac_mode"
        and c[0][2].get("hvac_mode") == "off"
    ]
    assert trv_off == []


# ---------------------------------------------------------------------------
# async_idle_device — setback unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_idle_device_setback_heating():
    """Device with idle_action='setback' in heat mode shifts target down by 2."""
    clear_command_cache()
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0, "max_temp": 35.0, "temperature": 21.0}
    hass.states.get = MagicMock(return_value=state)

    devices = [
        {"entity_id": "climate.ac1", "type": "ac", "role": "auto", "idle_action": "setback", "idle_fan_mode": ""}
    ]
    targets = TargetTemps(heat=21.0, cool=None)
    await async_idle_device(hass, "climate.ac1", devices, area_id="living_room", targets=targets)

    calls = hass.services.async_call.call_args_list
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert len(temp_calls) == 1
    assert temp_calls[0][0][2]["temperature"] == 19.0
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    assert len(hvac_calls) == 0


@pytest.mark.asyncio
async def test_async_idle_device_setback_cooling():
    """Device with idle_action='setback' in cool mode shifts target up by 2."""
    clear_command_cache()
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {"hvac_modes": ["cool", "off"], "min_temp": 5.0, "max_temp": 35.0, "temperature": 24.0}
    hass.states.get = MagicMock(return_value=state)

    devices = [
        {"entity_id": "climate.ac1", "type": "ac", "role": "auto", "idle_action": "setback", "idle_fan_mode": ""}
    ]
    targets = TargetTemps(heat=None, cool=24.0)
    await async_idle_device(hass, "climate.ac1", devices, area_id="living_room", targets=targets)

    calls = hass.services.async_call.call_args_list
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert len(temp_calls) == 1
    assert temp_calls[0][0][2]["temperature"] == 26.0
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    assert len(hvac_calls) == 0


@pytest.mark.asyncio
async def test_async_idle_device_setback_no_state():
    """Setback with no device state falls back to off."""
    clear_command_cache()
    hass = build_hass()
    hass.states.get = MagicMock(return_value=None)

    devices = [
        {"entity_id": "climate.ac1", "type": "ac", "role": "auto", "idle_action": "setback", "idle_fan_mode": ""}
    ]
    targets = TargetTemps(heat=21.0, cool=24.0)
    await async_idle_device(hass, "climate.ac1", devices, area_id="living_room", targets=targets)

    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.ac1", "hvac_mode": "off"},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_async_idle_device_setback_auto_mode_fallback():
    """Setback with device in 'auto' hvac mode falls back to off + defense-in-depth set_temperature."""
    clear_command_cache()
    hass = build_hass()
    state = MagicMock()
    state.state = "auto"
    state.attributes = {
        "hvac_modes": ["auto", "heat", "cool", "off"],
        "min_temp": 5.0,
        "max_temp": 35.0,
        "temperature": 25.0,
    }
    hass.states.get = MagicMock(return_value=state)

    devices = [
        {"entity_id": "climate.ac1", "type": "ac", "role": "auto", "idle_action": "setback", "idle_fan_mode": ""}
    ]
    targets = TargetTemps(heat=21.0, cool=24.0)
    await async_idle_device(hass, "climate.ac1", devices, area_id="living_room", targets=targets)

    assert hass.services.async_call.call_count == 2
    hass.services.async_call.assert_any_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.ac1", "hvac_mode": "off"},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_async_idle_device_setback_no_targets():
    """Setback with targets=None falls back to off."""
    clear_command_cache()
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"]}
    hass.states.get = MagicMock(return_value=state)

    devices = [
        {"entity_id": "climate.ac1", "type": "ac", "role": "auto", "idle_action": "setback", "idle_fan_mode": ""}
    ]
    await async_idle_device(hass, "climate.ac1", devices, area_id="living_room", targets=None)

    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.ac1", "hvac_mode": "off"},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_async_idle_device_setback_heat_mode_no_heat_target():
    """Setback in heat mode but targets.heat=None (cooling-only room) falls back to off + defense-in-depth."""
    clear_command_cache()
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {
        "hvac_modes": ["heat", "cool", "off"],
        "min_temp": 5.0,
        "max_temp": 35.0,
        "temperature": 25.0,
    }
    hass.states.get = MagicMock(return_value=state)

    devices = [
        {"entity_id": "climate.ac1", "type": "ac", "role": "auto", "idle_action": "setback", "idle_fan_mode": ""}
    ]
    # Device in heat mode but only cool target available
    targets = TargetTemps(heat=None, cool=24.0)
    await async_idle_device(hass, "climate.ac1", devices, area_id="living_room", targets=targets)

    assert hass.services.async_call.call_count == 2
    hass.services.async_call.assert_any_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.ac1", "hvac_mode": "off"},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_async_idle_device_setback_clamp_min():
    """Setback temp below device min_temp is clamped to min_temp."""
    clear_command_cache()
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0, "max_temp": 35.0, "temperature": 6.0}
    hass.states.get = MagicMock(return_value=state)

    devices = [
        {"entity_id": "climate.ac1", "type": "ac", "role": "auto", "idle_action": "setback", "idle_fan_mode": ""}
    ]
    # heat=6.0, setback would be 4.0, clamped to min_temp=5.0
    targets = TargetTemps(heat=6.0, cool=None)
    await async_idle_device(hass, "climate.ac1", devices, area_id="living_room", targets=targets)

    calls = hass.services.async_call.call_args_list
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert len(temp_calls) == 1
    assert temp_calls[0][0][2]["temperature"] == 5.0


@pytest.mark.asyncio
async def test_async_idle_device_setback_clamp_max():
    """Setback temp above device max_temp is clamped to max_temp."""
    clear_command_cache()
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {"hvac_modes": ["cool", "off"], "min_temp": 5.0, "max_temp": 35.0, "temperature": 34.0}
    hass.states.get = MagicMock(return_value=state)

    devices = [
        {"entity_id": "climate.ac1", "type": "ac", "role": "auto", "idle_action": "setback", "idle_fan_mode": ""}
    ]
    # cool=34.0, setback would be 36.0, clamped to max_temp=35.0
    targets = TargetTemps(heat=None, cool=34.0)
    await async_idle_device(hass, "climate.ac1", devices, area_id="living_room", targets=targets)

    calls = hass.services.async_call.call_args_list
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert len(temp_calls) == 1
    assert temp_calls[0][0][2]["temperature"] == 35.0


@pytest.mark.asyncio
async def test_async_idle_device_setback_redundancy():
    """Device already at setback temp skips service calls."""
    clear_command_cache()
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0, "max_temp": 35.0, "temperature": 19.0}
    hass.states.get = MagicMock(return_value=state)

    devices = [
        {"entity_id": "climate.ac1", "type": "ac", "role": "auto", "idle_action": "setback", "idle_fan_mode": ""}
    ]
    # heat=21.0, setback=19.0, device already at 19.0
    targets = TargetTemps(heat=21.0, cool=None)
    await async_idle_device(hass, "climate.ac1", devices, area_id="living_room", targets=targets)

    hass.services.async_call.assert_not_called()


# ---------------------------------------------------------------------------
# async_apply integration tests with setback idle_action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mpc_apply_idle_respects_setback():
    """async_apply(MODE_IDLE) with AC device that has idle_action='setback' uses setback temp."""
    clear_command_cache()
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {
        "hvac_modes": ["cool", "off"],
        "min_temp": 5.0,
        "max_temp": 35.0,
        "temperature": 24.0,
    }
    hass.states.get = MagicMock(return_value=state)

    room = make_room(thermostats=[], acs=["climate.ac1"])
    room["devices"] = [
        {
            "entity_id": "climate.ac1",
            "type": "ac",
            "role": "auto",
            "heating_system_type": "",
            "idle_action": "setback",
            "idle_fan_mode": "",
        }
    ]
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    targets = TargetTemps(heat=21.0, cool=24.0)
    await ctrl.async_apply(MODE_IDLE, targets)

    calls = hass.services.async_call.call_args_list
    # Should set temperature to 26.0 (cool setback: 24 + 2)
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert len(temp_calls) >= 1
    assert temp_calls[0][0][2]["temperature"] == 26.0
    # No off calls
    off_calls = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2].get("hvac_mode") == "off"]
    assert len(off_calls) == 0


@pytest.mark.asyncio
async def test_mpc_apply_idle_forced_on_overrides_setback():
    """Device in compressor_forced_on during IDLE runs forced_on logic, NOT setback."""
    clear_command_cache()
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {
        "hvac_modes": ["cool", "off"],
        "min_temp": 5.0,
        "max_temp": 35.0,
        "temperature": 25.0,
    }
    hass.states.get = MagicMock(return_value=state)

    room = make_room(thermostats=[], acs=["climate.ac1"])
    room["devices"] = [
        {
            "entity_id": "climate.ac1",
            "type": "ac",
            "role": "auto",
            "heating_system_type": "",
            "idle_action": "setback",
            "idle_fan_mode": "",
        }
    ]
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    targets = TargetTemps(heat=21.0, cool=24.0)
    await ctrl.async_apply(MODE_IDLE, targets, compressor_forced_on={"climate.ac1"})

    calls = hass.services.async_call.call_args_list
    # forced_on sets temperature to actual target, not setback offset
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert len(temp_calls) >= 1
    # Setback would be 26.0 (24+2), forced_on should use actual target (24.0)
    setback_calls = [c for c in temp_calls if c[0][2].get("temperature") == 26.0]
    assert len(setback_calls) == 0


@pytest.mark.asyncio
async def test_mpc_apply_call_hvac_off_delegates_setback():
    """_call('set_hvac_mode', 'off') delegates to async_idle_device which applies setback.

    Uses a TRV with setback to test the _call delegation path. In practice,
    only ACs can be configured with setback in the frontend — this test
    exercises the backend delegation mechanism which is device-type agnostic.
    """
    clear_command_cache()
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {
        "hvac_modes": ["heat", "cool", "off"],
        "min_temp": 5.0,
        "max_temp": 35.0,
        "temperature": 20.0,
    }
    hass.states.get = MagicMock(return_value=state)

    # Room with TRV + AC. During cooling, TRVs get "off" via _call.
    room = make_room(thermostats=["climate.trv1"], acs=["climate.ac1"])
    room["devices"] = [
        {
            "entity_id": "climate.trv1",
            "type": "trv",
            "role": "auto",
            "heating_system_type": "",
            "idle_action": "setback",
            "idle_fan_mode": "",
        },
        {
            "entity_id": "climate.ac1",
            "type": "ac",
            "role": "auto",
            "heating_system_type": "",
            "idle_action": "off",
            "idle_fan_mode": "",
        },
    ]
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    targets = TargetTemps(heat=21.0, cool=24.0)
    # During cooling, TRVs are set to "off" via _call -> async_idle_device
    await ctrl.async_apply("cooling", targets)

    calls = hass.services.async_call.call_args_list
    # TRV should get setback (set_temperature with 19.0 = 21 - 2), not off
    trv_temp_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.trv1" and c[0][1] == "set_temperature"]
    assert len(trv_temp_calls) >= 1
    assert trv_temp_calls[0][0][2]["temperature"] == 19.0
    trv_off = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.trv1"
        and c[0][1] == "set_hvac_mode"
        and c[0][2].get("hvac_mode") == "off"
    ]
    assert len(trv_off) == 0
