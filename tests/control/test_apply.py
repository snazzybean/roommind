"""Tests for async_apply behavior, device control, Fahrenheit conversion, turn_off logic, forced_on/forced_off, dual setpoint, cache/redundancy."""

from __future__ import annotations

from unittest.mock import ANY, AsyncMock, MagicMock

import pytest

from custom_components.roommind.const import TargetTemps
from custom_components.roommind.control.mpc_controller import (
    MPCController,
    _last_commands,
    _resolve_idle_setpoint,
    _send_idle_setpoint,
    _snap_to_step,
    async_idle_device,
    async_turn_off_climate,
    clear_command_cache,
    resolve_hvac_mode,
)
from custom_components.roommind.control.thermal_model import RoomModelManager

from .conftest import build_hass, make_room


@pytest.mark.asyncio
async def test_mpc_apply_heating():
    """Apply heating calls climate services."""
    hass = build_hass()
    room = make_room()
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0)
    assert hass.services.async_call.called
    # Verify climate domain calls target the correct entity
    calls = hass.services.async_call.call_args_list
    climate_calls = [c for c in calls if c[0][0] == "climate"]
    assert len(climate_calls) >= 1
    assert climate_calls[0][0][0] == "climate"
    assert climate_calls[0][0][2]["entity_id"] == "climate.living_trv"


@pytest.mark.asyncio
async def test_mpc_apply_cooling():
    """Apply cooling calls climate services on ACs."""
    hass = build_hass()
    room = make_room(thermostats=[], acs=["climate.ac"])
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
    assert hass.services.async_call.called
    # Verify climate domain calls target the AC entity
    calls = hass.services.async_call.call_args_list
    climate_calls = [c for c in calls if c[0][0] == "climate"]
    assert len(climate_calls) >= 1
    assert climate_calls[0][0][0] == "climate"
    assert climate_calls[0][0][2]["entity_id"] == "climate.ac"


@pytest.mark.asyncio
async def test_mpc_apply_idle():
    """Apply idle turns off everything."""
    hass = build_hass()
    room = make_room(acs=["climate.ac"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("idle", 21.0)
    assert hass.services.async_call.called
    # Verify calls target both TRV and AC entities
    calls = hass.services.async_call.call_args_list
    climate_calls = [c for c in calls if c[0][0] == "climate"]
    entity_ids = [c[0][2]["entity_id"] for c in climate_calls]
    assert "climate.living_trv" in entity_ids
    assert "climate.ac" in entity_ids


@pytest.mark.asyncio
async def test_async_apply_backward_compat():
    """Calling async_apply without power_fraction uses default 1.0 → 30°C boost."""
    from custom_components.roommind.control.mpc_controller import HEATING_BOOST_TARGET

    hass = build_hass()
    room = make_room()
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0)  # no power_fraction → default 1.0
    calls = hass.services.async_call.call_args_list
    set_temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert set_temp_calls
    # Without current_temp, falls back to HEATING_BOOST_TARGET
    temp_arg = set_temp_calls[0][0][2]["temperature"]
    assert temp_arg == HEATING_BOOST_TARGET


@pytest.mark.asyncio
async def test_mpc_apply_heating_fahrenheit():
    """set_temperature uses Fahrenheit when HA is configured for °F."""
    from homeassistant.const import UnitOfTemperature

    from custom_components.roommind.control.mpc_controller import HEATING_BOOST_TARGET

    hass = build_hass()
    hass.config.units.temperature_unit = UnitOfTemperature.FAHRENHEIT

    room = make_room()
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0)

    calls = hass.services.async_call.call_args_list
    set_temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert set_temp_calls

    # HEATING_BOOST_TARGET (30°C) → 86°F
    expected_f = HEATING_BOOST_TARGET * 9 / 5 + 32
    temp_arg = set_temp_calls[0][0][2]["temperature"]
    assert temp_arg == pytest.approx(expected_f)


@pytest.mark.asyncio
async def test_mpc_apply_cooling_fahrenheit():
    """Cooling set_temperature uses Fahrenheit when HA is configured for °F."""
    from homeassistant.const import UnitOfTemperature

    hass = build_hass()
    hass.config.units.temperature_unit = UnitOfTemperature.FAHRENHEIT

    room = make_room(thermostats=[], acs=["climate.ac"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    # Apply cooling with target 23°C
    await ctrl.async_apply("cooling", 23.0)

    calls = hass.services.async_call.call_args_list
    set_temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert set_temp_calls

    # 23°C → 73.4°F
    expected_f = 23.0 * 9 / 5 + 32
    temp_arg = set_temp_calls[0][0][2]["temperature"]
    assert temp_arg == pytest.approx(expected_f)


# ---------------------------------------------------------------------------
# Device min/max temperature clamping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_clamps_to_device_max_temp():
    """Temperature is clamped to device max_temp attribute."""
    hass = build_hass()
    mock_state = MagicMock()
    mock_state.state = "off"
    mock_state.attributes = {"min_temp": 5.0, "max_temp": 25.0, "temperature": None}
    hass.states.get = MagicMock(return_value=mock_state)

    room = make_room()
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    # Heating with full power tries to set 30°C (HEATING_BOOST_TARGET)
    await ctrl.async_apply("heating", 21.0, power_fraction=1.0, current_temp=18.0)

    set_temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert set_temp_calls
    temp_arg = set_temp_calls[0][0][2]["temperature"]
    assert temp_arg == 25.0  # clamped to device max


@pytest.mark.asyncio
async def test_apply_clamps_to_device_min_temp():
    """Temperature is clamped to device min_temp attribute."""
    hass = build_hass()
    mock_state = MagicMock()
    mock_state.state = "off"
    mock_state.attributes = {"min_temp": 10.0, "max_temp": 30.0, "temperature": None}
    hass.states.get = MagicMock(return_value=mock_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=35.0,
        settings={},
        has_external_sensor=True,
    )
    # Cooling with target below device min
    await ctrl.async_apply("cooling", 8.0)

    set_temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert set_temp_calls
    temp_arg = set_temp_calls[0][0][2]["temperature"]
    assert temp_arg == 10.0  # clamped to device min


# ---------------------------------------------------------------------------
# async_turn_off_climate — unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_off_climate_normal_device():
    """Device with 'off' in hvac_modes uses set_hvac_mode off + defense-in-depth set_temperature(min_temp)."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0, "temperature": 30.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    assert hass.services.async_call.call_count == 2
    hass.services.async_call.assert_any_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.trv", "hvac_mode": "off"},
        blocking=True,
        context=ANY,
    )
    hass.services.async_call.assert_any_call(
        "climate",
        "set_temperature",
        {"entity_id": "climate.trv", "temperature": 5.0},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_turn_off_climate_heat_only_uses_min_temp():
    """Heat-only device (no 'off' mode) gets set_temperature with min_temp."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat"], "min_temp": 5.0, "temperature": 21.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_temperature",
        {"entity_id": "climate.trv", "temperature": 5.0},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_turn_off_climate_cool_only_uses_max_temp():
    """Cool-only device without 'off' uses max_temp as fallback."""
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {"hvac_modes": ["cool"], "min_temp": 16.0, "max_temp": 30.0, "temperature": 20.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.ac")
    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_temperature",
        {"entity_id": "climate.ac", "temperature": 30.0},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_turn_off_climate_already_off_skipped():
    """Device already in 'off' state: call is skipped."""
    hass = build_hass()
    state = MagicMock()
    state.state = "off"
    state.attributes = {"hvac_modes": ["heat", "off"]}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_turn_off_already_off_high_setpoint_lowers_to_min_temp():
    """Device permanently 'off' (e.g. Wavin Sentio) with high setpoint: lower to min_temp."""
    hass = build_hass()
    state = MagicMock()
    state.state = "off"
    state.attributes = {"hvac_modes": ["off"], "temperature": 22.5, "min_temp": 5.0, "max_temp": 30.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_temperature",
        {"entity_id": "climate.trv", "temperature": 5.0},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_turn_off_already_off_setpoint_at_min_temp_no_command():
    """Device 'off' with setpoint already at min_temp: no redundant command."""
    hass = build_hass()
    state = MagicMock()
    state.state = "off"
    state.attributes = {"hvac_modes": ["off"], "temperature": 5.0, "min_temp": 5.0, "max_temp": 30.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_turn_off_already_off_no_min_temp_attribute_no_command():
    """Device 'off' without min_temp attribute: no command (safe guard)."""
    hass = build_hass()
    state = MagicMock()
    state.state = "off"
    state.attributes = {"hvac_modes": ["off"], "temperature": 22.5}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_turn_off_already_off_min_temp_zero_no_command():
    """Device 'off' with min_temp=0 (Z2M/firmware bug): no command."""
    hass = build_hass()
    state = MagicMock()
    state.state = "off"
    state.attributes = {"hvac_modes": ["off"], "temperature": 22.5, "min_temp": 0, "max_temp": 30.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_turn_off_already_off_setpoint_none_sends_min_temp():
    """Device 'off' with unknown setpoint (None): send min_temp as safety net."""
    hass = build_hass()
    state = MagicMock()
    state.state = "off"
    state.attributes = {"hvac_modes": ["off"], "temperature": None, "min_temp": 5.0, "max_temp": 30.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_temperature",
        {"entity_id": "climate.trv", "temperature": 5.0},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_turn_off_already_off_wavin_sentio_realistic():
    """Realistic Wavin Sentio: hvac_modes=['off'], state='off', setpoint at comfort_temp."""
    hass = build_hass()
    state = MagicMock()
    state.state = "off"
    state.attributes = {"hvac_modes": ["off"], "temperature": 22.5, "min_temp": 12.0, "max_temp": 30.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_temperature",
        {"entity_id": "climate.trv", "temperature": 12.0},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_turn_off_climate_empty_modes_uses_off():
    """Empty hvac_modes list: assume 'off' is supported (backward compat)."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": []}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.trv", "hvac_mode": "off"},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_turn_off_climate_no_modes_attr_uses_off():
    """No hvac_modes attribute at all: assume 'off' is supported + defense-in-depth set_temperature."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"min_temp": 5.0, "temperature": 25.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    assert hass.services.async_call.call_count == 2
    hass.services.async_call.assert_any_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.trv", "hvac_mode": "off"},
        blocking=True,
        context=ANY,
    )
    hass.services.async_call.assert_any_call(
        "climate",
        "set_temperature",
        {"entity_id": "climate.trv", "temperature": 5.0},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_turn_off_climate_heat_only_no_min_temp():
    """Heat-only device without min_temp: logs warning, no crash."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat"]}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_turn_off_climate_heat_only_already_at_min_temp():
    """Heat-only device already at min_temp: redundant call skipped."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat"], "min_temp": 5.0, "temperature": 5.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_turn_off_climate_zero_min_temp_skips_defense_in_depth():
    """min_temp=0: only set_hvac_mode(off) is sent, no set_temperature (defense-in-depth skipped)."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 0, "temperature": 20.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    assert hass.services.async_call.call_count == 1
    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.trv", "hvac_mode": "off"},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_turn_off_climate_negative_min_temp_skips_defense_in_depth():
    """min_temp<0: only set_hvac_mode(off) is sent, no set_temperature."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": -5.0, "temperature": 20.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    assert hass.services.async_call.call_count == 1


@pytest.mark.asyncio
async def test_turn_off_climate_min_temp_4_defense_in_depth_fires():
    """min_temp=4.0 (TRVZB valid minimum): both set_hvac_mode(off) and set_temperature(4.0) sent."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 4.0, "temperature": 20.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    assert hass.services.async_call.call_count == 2
    hass.services.async_call.assert_any_call(
        "climate",
        "set_temperature",
        {"entity_id": "climate.trv", "temperature": 4.0},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_turn_off_climate_heat_only_zero_min_temp_no_call():
    """Heat-only device (no 'off') with min_temp=0: no service call, fallback guard prevents invalid setpoint."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat"], "min_temp": 0, "temperature": 20.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_turn_off_climate_fahrenheit_32_fires_defense_in_depth():
    """min_temp=32 (=0°C in Fahrenheit): guard allows it (32 > 0), set_temperature(32) sent."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 32.0, "temperature": 80.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    assert hass.services.async_call.call_count == 2
    hass.services.async_call.assert_any_call(
        "climate",
        "set_temperature",
        {"entity_id": "climate.trv", "temperature": 32.0},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_turn_off_climate_current_setpoint_zero_with_valid_min_temp():
    """current_setpoint=0 and min_temp=4.0: guard passes (4.0 > 0), set_temperature(4.0) still fires."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 4.0, "temperature": 0.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    assert hass.services.async_call.call_count == 2
    hass.services.async_call.assert_any_call(
        "climate",
        "set_temperature",
        {"entity_id": "climate.trv", "temperature": 4.0},
        blocking=True,
        context=ANY,
    )


# ---------------------------------------------------------------------------
# async_apply integration tests for heat-only TRV fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_idle_heat_only_trv():
    """Idle mode on heat-only TRV sends min_temp instead of set_hvac_mode off."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat"], "min_temp": 5.0, "max_temp": 30.0, "temperature": 21.0}
    hass.states.get = MagicMock(return_value=state)

    room = make_room()
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("idle", 21.0)

    calls = hass.services.async_call.call_args_list
    off_calls = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2].get("hvac_mode") == "off"]
    assert len(off_calls) == 0
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert len(temp_calls) >= 1
    assert temp_calls[0][0][2]["temperature"] == 5.0


@pytest.mark.asyncio
async def test_managed_mode_heat_gated_heat_only_trv():
    """Managed mode: can_heat=False on heat-only TRV uses min_temp fallback."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat"], "min_temp": 5.0, "max_temp": 30.0, "temperature": 21.0}
    hass.states.get = MagicMock(return_value=state)

    room = make_room(acs=["climate.ac"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=25.0,  # above heating max → can_heat=False
        settings={"outdoor_heating_max": 22.0},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", 21.0)

    calls = hass.services.async_call.call_args_list
    off_calls = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2].get("hvac_mode") == "off"]
    assert len(off_calls) == 0
    temp_calls = [c for c in calls if c[0][1] == "set_temperature" and c[0][2]["temperature"] == 5.0]
    assert len(temp_calls) >= 1


# ---------------------------------------------------------------------------
# async_apply: AC heating behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_heating_ac_with_heat_gets_target():
    """Heating: AC with 'heat' mode gets proportional boost target."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "temperature": 20.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.hp"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0, power_fraction=0.5, current_temp=18.0)

    calls = hass.services.async_call.call_args_list
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    # AC should get heat mode
    assert any(c[0][2].get("hvac_mode") == "heat" for c in hvac_calls)
    # AC should get proportional target: 18 + 0.5*(30-18) = 24.0
    assert any(c[0][2]["temperature"] == 24.0 for c in temp_calls)


@pytest.mark.asyncio
async def test_apply_heating_ac_heat_cool_mode():
    """Heating: AC with only 'heat_cool' (no separate 'heat') gets heat_cool."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["heat_cool", "cool", "off"], "temperature": 20.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.hp"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0, power_fraction=1.0, current_temp=18.0)

    calls = hass.services.async_call.call_args_list
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    assert any(c[0][2].get("hvac_mode") == "heat_cool" for c in hvac_calls)


@pytest.mark.asyncio
async def test_apply_heating_cool_only_ac_turned_off():
    """Heating: cool-only AC still gets turned off (no regression)."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "cool"
    ac_state.attributes = {"hvac_modes": ["cool", "off"], "temperature": 23.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(acs=["climate.ac"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0)

    calls = hass.services.async_call.call_args_list
    # AC should be turned off (via async_turn_off_climate)
    ac_off_calls = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.ac" and c[0][1] == "set_hvac_mode" and c[0][2].get("hvac_mode") == "off"
    ]
    assert len(ac_off_calls) >= 1


@pytest.mark.asyncio
async def test_apply_heating_trv_still_gets_boost():
    """Heating: TRV in thermostats[] still gets proportional 30°C boost."""
    from custom_components.roommind.control.mpc_controller import HEATING_BOOST_TARGET

    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 21.0, "min_temp": 5.0, "max_temp": 30.0}
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()  # thermostats=["climate.living_trv"]
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    # Full power: TRV should get 30°C (HEATING_BOOST_TARGET)
    await ctrl.async_apply("heating", 21.0, power_fraction=1.0, current_temp=18.0)

    calls = hass.services.async_call.call_args_list
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert temp_calls
    assert temp_calls[0][0][2]["temperature"] == HEATING_BOOST_TARGET


@pytest.mark.asyncio
async def test_managed_mode_ac_heat_cool():
    """Managed mode auto: AC with heat_cool gets heat_cool mode."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["heat_cool", "heat", "cool", "off"], "temperature": 20.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.hp"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", 21.0)

    calls = hass.services.async_call.call_args_list
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    # Should get heat_cool mode (not cool)
    assert any(c[0][2].get("hvac_mode") == "heat_cool" for c in hvac_calls)
    # Should get actual target temp
    assert any(c[0][2]["temperature"] == 21.0 for c in temp_calls)


@pytest.mark.asyncio
async def test_ac_only_room_can_heat():
    """Room with only heat-capable AC can enter heating mode."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "temperature": 20.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.hp"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    mode, pf = await ctrl.async_evaluate(current_temp=17.0, target_temp=21.0)
    assert mode == "heating"


@pytest.mark.asyncio
async def test_apply_heating_mixed_trv_and_ac():
    """Heating with TRV + heat-capable AC: TRV gets boost, AC gets proportional boost."""
    from custom_components.roommind.control.mpc_controller import HEATING_BOOST_TARGET

    hass = build_hass()

    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 21.0, "min_temp": 5.0, "max_temp": 30.0}

    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {
        "hvac_modes": ["heat", "cool", "off"],
        "temperature": 20.0,
        "min_temp": 16.0,
        "max_temp": 30.0,
    }

    def states_get(eid):
        if eid == "climate.living_trv":
            return trv_state
        if eid == "climate.hp":
            return ac_state
        return None

    hass.states.get = MagicMock(side_effect=states_get)

    room = make_room(thermostats=["climate.living_trv"], acs=["climate.hp"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0, power_fraction=1.0, current_temp=18.0)

    calls = hass.services.async_call.call_args_list
    # TRV should get boost target (30°C)
    trv_temp_calls = [
        c for c in calls if c[0][1] == "set_temperature" and c[0][2].get("entity_id") == "climate.living_trv"
    ]
    assert trv_temp_calls
    assert trv_temp_calls[0][0][2]["temperature"] == HEATING_BOOST_TARGET

    # AC should get proportional boost: 18 + 1.0*(30-18) = 30.0
    ac_temp_calls = [c for c in calls if c[0][1] == "set_temperature" and c[0][2].get("entity_id") == "climate.hp"]
    assert ac_temp_calls
    assert ac_temp_calls[0][0][2]["temperature"] == 30.0

    # AC should be in heat mode, not off
    ac_hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2].get("entity_id") == "climate.hp"]
    assert ac_hvac_calls
    assert ac_hvac_calls[0][0][2]["hvac_mode"] == "heat"


@pytest.mark.asyncio
async def test_managed_mode_auto_trv_and_heat_cool_ac():
    """Managed mode auto with TRV + heat_cool AC: TRV=heat, AC=heat_cool."""
    hass = build_hass()

    trv_state = MagicMock()
    trv_state.state = "off"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 20.0}

    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["heat_cool", "heat", "cool", "off"], "temperature": 20.0}

    def states_get(eid):
        if eid == "climate.living_trv":
            return trv_state
        if eid == "climate.hp":
            return ac_state
        return None

    hass.states.get = MagicMock(side_effect=states_get)

    room = make_room(thermostats=["climate.living_trv"], acs=["climate.hp"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", 21.0)

    calls = hass.services.async_call.call_args_list

    # TRV should be in heat mode with target temp
    trv_hvac = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2].get("entity_id") == "climate.living_trv"]
    assert trv_hvac
    assert trv_hvac[0][0][2]["hvac_mode"] == "heat"

    # AC should be in heat_cool mode (self-regulates both directions)
    ac_hvac = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2].get("entity_id") == "climate.hp"]
    assert ac_hvac
    assert ac_hvac[0][0][2]["hvac_mode"] == "heat_cool"

    # Both should get target temp 21°C
    trv_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2].get("entity_id") == "climate.living_trv"]
    ac_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2].get("entity_id") == "climate.hp"]
    assert trv_temp and trv_temp[0][0][2]["temperature"] == 21.0
    assert ac_temp and ac_temp[0][0][2]["temperature"] == 21.0


# ---------------------------------------------------------------------------
# async_turn_off_climate (additional tests)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_off_set_hvac_mode_exception():
    """Exception in set_hvac_mode(off) is caught, doesn't raise."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"]}
    hass.states.get = MagicMock(return_value=state)
    hass.services.async_call = AsyncMock(side_effect=RuntimeError("service error"))

    # Should not raise
    await async_turn_off_climate(hass, "climate.trv1", area_id="room_a")


@pytest.mark.asyncio
async def test_turn_off_defense_in_depth_set_temperature_exception():
    """Exception in defense-in-depth set_temperature is silently caught; set_hvac_mode(off) still sent."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0, "temperature": 25.0}
    hass.states.get = MagicMock(return_value=state)

    # Only set_temperature raises; set_hvac_mode should still go through
    async def selective_raise(domain, service, data, **kwargs):
        if service == "set_temperature":
            raise RuntimeError("device busy")

    hass.services.async_call = AsyncMock(side_effect=selective_raise)

    # Should not raise; set_hvac_mode(off) should still be called
    await async_turn_off_climate(hass, "climate.trv1", area_id="room_a")
    calls = [c[0][1] for c in hass.services.async_call.call_args_list]
    assert "set_hvac_mode" in calls


@pytest.mark.asyncio
async def test_turn_off_fallback_set_temperature_exception():
    """Exception in fallback set_temperature is caught."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat"], "min_temp": 5.0, "temperature": 21.0}
    hass.states.get = MagicMock(return_value=state)
    hass.services.async_call = AsyncMock(side_effect=RuntimeError("service error"))

    # Should not raise
    await async_turn_off_climate(hass, "climate.trv1", area_id="room_a")


@pytest.mark.asyncio
async def test_turn_off_no_state():
    """Entity with no state (None) treats as modes unknown and tries off."""
    hass = build_hass()
    hass.states.get = MagicMock(return_value=None)

    await async_turn_off_climate(hass, "climate.trv1", area_id="room_a")
    hass.services.async_call.assert_called_once()


# ---------------------------------------------------------------------------
# async_apply edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_mode_not_idle_but_target_none():
    """Non-idle mode with None target falls back to idle."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", target_temp=None)
    # Should have called set_hvac_mode off (idle) for all devices
    calls = hass.services.async_call.call_args_list
    for c in calls:
        if c[0][1] == "set_hvac_mode":
            assert c[0][2]["hvac_mode"] == "off"


@pytest.mark.asyncio
async def test_apply_cooling_turns_off_thermostats():
    """Cooling mode turns off thermostats and cools ACs."""
    hass = build_hass()
    room = make_room(
        acs=["climate.ac1"],
        climate_mode="cool_only",
    )
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )

    await ctrl.async_apply("cooling", target_temp=23.0)
    calls = hass.services.async_call.call_args_list

    # AC should be set to cool
    ac_modes = [c for c in calls if c[0][2].get("entity_id") == "climate.ac1" and c[0][1] == "set_hvac_mode"]
    assert any(c[0][2]["hvac_mode"] == "cool" for c in ac_modes)

    # TRV should be turned off
    trv_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.living_trv"]
    # "off" is delegated to async_turn_off_climate which calls set_hvac_mode
    if trv_calls:
        assert any(c[0][2].get("hvac_mode") == "off" for c in trv_calls if c[0][1] == "set_hvac_mode")


@pytest.mark.asyncio
async def test_apply_managed_mode_ac_heat_only():
    """Managed mode AC with only 'heat' mode gets heat + target temp."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["heat"], "temperature": None}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(
        thermostats=[],
        acs=["climate.ac1"],
        climate_mode="auto",
        temperature_sensor="",  # no external sensor
    )
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )

    await ctrl.async_apply("heating", target_temp=21.0)
    calls = hass.services.async_call.call_args_list

    ac_hvac = [c for c in calls if c[0][2].get("entity_id") == "climate.ac1" and c[0][1] == "set_hvac_mode"]
    assert any(c[0][2]["hvac_mode"] == "heat" for c in ac_hvac)


@pytest.mark.asyncio
async def test_apply_managed_mode_ac_unreliable_fan_only_sends_heat():
    """Managed mode AC in fan_only with no active modes: unreliable → sends heat directly (#100)."""
    _last_commands.clear()
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "fan_only"
    ac_state.attributes = {"hvac_modes": ["fan_only"], "temperature": None}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(
        thermostats=[],
        acs=["climate.ac1"],
        climate_mode="auto",
        temperature_sensor="",
    )
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )

    await ctrl.async_apply("heating", target_temp=21.0)
    # Device has unreliable modes (no active modes in list) → assumed full modes
    # → heat command sent directly (may fail on device, caught by try/except)
    calls = hass.services.async_call.call_args_list
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    assert len(hvac_calls) >= 1
    assert hvac_calls[0][0][2]["hvac_mode"] == "heat"


@pytest.mark.asyncio
async def test_apply_managed_mode_ac_cool_only():
    """Managed mode AC with only 'cool' mode gets cool + target temp."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["cool"], "temperature": None}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(
        thermostats=[],
        acs=["climate.ac1"],
        climate_mode="auto",
        temperature_sensor="",
    )
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=False,
    )

    await ctrl.async_apply("cooling", target_temp=23.0)
    calls = hass.services.async_call.call_args_list
    ac_hvac = [c for c in calls if c[0][2].get("entity_id") == "climate.ac1" and c[0][1] == "set_hvac_mode"]
    assert any(c[0][2]["hvac_mode"] == "cool" for c in ac_hvac)


# ---------------------------------------------------------------------------
# _call redundancy skip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_skips_redundant_temperature():
    """Redundant set_temperature is skipped."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 21.0, "min_temp": 5, "max_temp": 30}
    hass.states.get = MagicMock(return_value=state)

    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 21.0})
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_call_skips_redundant_hvac_mode():
    """Redundant set_hvac_mode is skipped."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"]}
    hass.states.get = MagicMock(return_value=state)

    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl._call("set_hvac_mode", {"entity_id": "climate.living_trv", "hvac_mode": "heat"})
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_call_service_exception_caught():
    """Exception in service call is caught."""
    hass = build_hass()
    state = MagicMock()
    state.state = "off"
    state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 20.0, "min_temp": 5, "max_temp": 30}
    hass.states.get = MagicMock(return_value=state)
    hass.services.async_call = AsyncMock(side_effect=RuntimeError("fail"))

    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    # Should not raise
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 25.0})


@pytest.mark.asyncio
async def test_call_clamps_to_device_max():
    """Temperature is clamped to device max_temp."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 20.0, "min_temp": 5, "max_temp": 25}
    hass.states.get = MagicMock(return_value=state)

    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 30.0})
    # Should have been clamped to 25
    call_args = hass.services.async_call.call_args[0]
    assert call_args[2]["temperature"] == 25


# ---------------------------------------------------------------------------
# resolve_hvac_mode unit tests
# ---------------------------------------------------------------------------


class TestResolveHvacMode:
    def test_desired_available(self):
        assert resolve_hvac_mode("heat", ["off", "heat"]) == "heat"

    def test_fallback_to_auto_for_heat(self):
        assert resolve_hvac_mode("heat", ["off", "auto"]) == "auto"

    def test_fallback_to_auto_for_cool(self):
        assert resolve_hvac_mode("cool", ["off", "auto"]) == "auto"

    def test_fallback_to_auto_for_heat_cool(self):
        assert resolve_hvac_mode("heat_cool", ["off", "auto"]) == "auto"

    def test_no_compatible_mode(self):
        assert resolve_hvac_mode("heat", ["off", "fan_only"]) is None

    def test_empty_modes_returns_desired(self):
        assert resolve_hvac_mode("heat", []) == "heat"

    def test_auto_desired_and_available(self):
        assert resolve_hvac_mode("auto", ["off", "auto"]) == "auto"

    def test_auto_desired_not_available(self):
        assert resolve_hvac_mode("auto", ["off", "heat"]) is None


# ---------------------------------------------------------------------------
# Auto-only device tests (issue #44)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_heating_thermostat_auto_only():
    """Full control heating: thermostat with 'off'+'auto' gets 'auto' instead of 'heat'."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "off"
    trv_state.attributes = {
        "hvac_modes": ["off", "auto"],
        "temperature": None,
        "min_temp": 5.0,
        "max_temp": 30.0,
    }
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )

    await ctrl.async_apply("heating", 21.0, current_temp=19.0)
    calls = hass.services.async_call.call_args_list
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    assert not any(c[0][2]["hvac_mode"] == "heat" for c in hvac_calls)
    assert any(c[0][2]["hvac_mode"] == "auto" for c in hvac_calls)


@pytest.mark.asyncio
async def test_apply_managed_mode_thermostat_auto_only():
    """Managed mode: thermostat with only 'off'+'auto' gets 'auto' mode."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "off"
    trv_state.attributes = {
        "hvac_modes": ["off", "auto"],
        "temperature": None,
        "min_temp": 5.0,
        "max_temp": 30.0,
    }
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room(temperature_sensor="")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )

    await ctrl.async_apply("heating", target_temp=21.0)
    calls = hass.services.async_call.call_args_list
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2].get("entity_id") == "climate.living_trv"]
    assert not any(c[0][2]["hvac_mode"] == "heat" for c in hvac_calls)
    assert any(c[0][2]["hvac_mode"] == "auto" for c in hvac_calls)


@pytest.mark.asyncio
async def test_apply_cooling_ac_auto_only():
    """AC with only 'off'+'auto' hvac_modes gets 'auto' instead of 'cool'."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["off", "auto"], "temperature": None}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac1"])
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=35.0,
        settings={},
        has_external_sensor=True,
    )

    await ctrl.async_apply("cooling", 23.0)
    calls = hass.services.async_call.call_args_list
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    assert not any(c[0][2]["hvac_mode"] == "cool" for c in hvac_calls)
    assert any(c[0][2]["hvac_mode"] == "auto" for c in hvac_calls)


@pytest.mark.asyncio
async def test_apply_managed_mode_ac_auto_only():
    """Managed mode AC with only 'off'+'auto' gets 'auto' mode via cascade."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["off", "auto"], "temperature": None}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(
        thermostats=[],
        acs=["climate.ac1"],
        climate_mode="auto",
        temperature_sensor="",
    )
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=False,
    )

    await ctrl.async_apply("cooling", target_temp=23.0)
    calls = hass.services.async_call.call_args_list
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2].get("entity_id") == "climate.ac1"]
    assert any(c[0][2]["hvac_mode"] == "auto" for c in hvac_calls)


@pytest.mark.asyncio
async def test_apply_heating_ac_auto_only():
    """MODE_HEATING: AC with only 'off'+'auto' gets 'auto' via cascade."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["off", "auto"], "temperature": None}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(acs=["climate.ac1"])
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )

    await ctrl.async_apply("heating", 21.0)
    calls = hass.services.async_call.call_args_list
    ac_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.ac1" and c[0][1] == "set_hvac_mode"]
    assert any(c[0][2]["hvac_mode"] == "auto" for c in ac_calls)


# --- dual-setpoint support (#78) ---


@pytest.mark.asyncio
async def test_call_dual_setpoint_heat_intent():
    """TRV with target_temp_low attr + temp_intent='heat' sends dual-setpoint keys."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {
        "hvac_modes": ["heat", "off"],
        "temperature": 20.0,
        "target_temp_low": 18.0,
        "target_temp_high": 25.0,
        "min_temp": 5.0,
        "max_temp": 30.0,
    }
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0, power_fraction=1.0, current_temp=18.0)

    temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert temp_calls
    last_data = temp_calls[-1][0][2]
    assert "target_temp_low" in last_data
    assert "temperature" not in last_data


@pytest.mark.asyncio
async def test_call_dual_setpoint_cool_intent():
    """AC with dual-setpoint + temp_intent='cool' sets target_temp_high."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {
        "hvac_modes": ["cool", "off"],
        "temperature": 22.0,
        "target_temp_low": 18.0,
        "target_temp_high": 25.0,
        "min_temp": 16.0,
        "max_temp": 30.0,
    }
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=35.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("cooling", 23.0, power_fraction=1.0, current_temp=26.0)

    temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert temp_calls
    last_data = temp_calls[-1][0][2]
    assert "target_temp_high" in last_data


@pytest.mark.asyncio
async def test_call_single_setpoint_unchanged():
    """Device WITHOUT target_temp_low uses 'temperature' key (backward compat)."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {
        "hvac_modes": ["heat", "off"],
        "temperature": 20.0,
        "min_temp": 5.0,
        "max_temp": 30.0,
    }
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0, power_fraction=1.0, current_temp=18.0)

    temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert temp_calls
    last_data = temp_calls[-1][0][2]
    assert "temperature" in last_data
    assert "target_temp_low" not in last_data


@pytest.mark.asyncio
async def test_call_dual_setpoint_no_intent_unchanged():
    """Device with target_temp_low but empty temp_intent uses 'temperature' key."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {
        "hvac_modes": ["heat", "off"],
        "temperature": 20.0,
        "target_temp_low": 18.0,
        "target_temp_high": 25.0,
        "min_temp": 5.0,
        "max_temp": 30.0,
    }
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    # Call _call directly with no temp_intent (default empty string)
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 22.0})

    assert hass.services.async_call.called
    call_data = hass.services.async_call.call_args[0][2]
    assert "temperature" in call_data
    assert "target_temp_low" not in call_data


@pytest.mark.asyncio
async def test_call_dual_setpoint_redundancy_skip():
    """Current low/high match desired after transformation: no service call."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {
        "hvac_modes": ["heat", "off"],
        "target_temp_low": 22.0,
        "target_temp_high": 25.0,
        "min_temp": 5.0,
        "max_temp": 30.0,
    }
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    # heat intent: low=22.0, high=max(22,25)=25.0 — matches state exactly
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 22.0}, temp_intent="heat")

    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_call_dual_setpoint_clamping():
    """Values beyond min/max are clamped for dual-setpoint."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {
        "hvac_modes": ["heat", "off"],
        "target_temp_low": 15.0,
        "target_temp_high": 24.0,
        "min_temp": 10.0,
        "max_temp": 25.0,
    }
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    # heat intent: low=8.0 (below min 10 → clamped to 10), high=max(8,24)=24.0
    # low differs from state (15→10) so not redundant
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 8.0}, temp_intent="heat")

    assert hass.services.async_call.called
    call_data = hass.services.async_call.call_args[0][2]
    assert call_data["target_temp_low"] == 10.0


@pytest.mark.asyncio
async def test_managed_auto_heat_cool_dual_setpoint():
    """Managed Auto AC in heat_cool + dual-setpoint sends both targets."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {
        "hvac_modes": ["heat_cool", "off"],
        "target_temp_low": 18.0,
        "target_temp_high": 25.0,
        "min_temp": 16.0,
        "max_temp": 30.0,
    }
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"], climate_mode="auto")
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", TargetTemps(heat=21.0, cool=25.0), power_fraction=1.0)

    temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert temp_calls
    last_data = temp_calls[-1][0][2]
    assert "target_temp_low" in last_data
    assert "target_temp_high" in last_data


@pytest.mark.asyncio
async def test_managed_auto_heat_cool_single_setpoint():
    """Managed Auto AC in heat_cool + single-setpoint sends 'temperature'."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {
        "hvac_modes": ["heat_cool", "off"],
        "temperature": 22.0,
        "min_temp": 16.0,
        "max_temp": 30.0,
    }
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"], climate_mode="auto")
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", TargetTemps(heat=21.0, cool=25.0), power_fraction=1.0)

    temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert temp_calls
    last_data = temp_calls[-1][0][2]
    assert "temperature" in last_data
    assert "target_temp_low" not in last_data


@pytest.mark.asyncio
async def test_turn_off_dual_setpoint_heat_only():
    """Heat-only device with dual-setpoint and no 'off' mode uses both low/high = min_temp."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {
        "hvac_modes": ["heat"],
        "target_temp_low": 20.0,
        "target_temp_high": 25.0,
        "min_temp": 5.0,
        "max_temp": 30.0,
    }
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv1", area_id="test")

    assert hass.services.async_call.called
    call_data = hass.services.async_call.call_args[0][2]
    assert call_data["target_temp_low"] == 5.0
    assert call_data["target_temp_high"] == 5.0


@pytest.mark.asyncio
async def test_heating_trv_dual_setpoint_full_control():
    """Full Control heating with dual-setpoint TRV gets proportional target_temp_low."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {
        "hvac_modes": ["heat", "off"],
        "temperature": 20.0,
        "target_temp_low": 18.0,
        "target_temp_high": 25.0,
        "min_temp": 5.0,
        "max_temp": 30.0,
    }
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    # power_fraction=0.5, current=20, boost=30: sp = 20 + 0.5*(30-20) = 25.0
    await ctrl.async_apply("heating", 21.0, power_fraction=0.5, current_temp=20.0)

    temp_calls = [
        c
        for c in hass.services.async_call.call_args_list
        if c[0][1] == "set_temperature" and c[0][2].get("entity_id") == "climate.living_trv"
    ]
    assert temp_calls
    call_data = temp_calls[-1][0][2]
    assert "target_temp_low" in call_data
    assert call_data["target_temp_low"] == 25.0


# ---------------------------------------------------------------------------
# Command cache tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_cache_fallback_skips_ir_device():
    """Cache prevents duplicate commands on IR devices with no temperature feedback."""
    hass = build_hass()
    state = MagicMock()
    state.state = "unavailable"
    state.attributes = {"hvac_modes": ["heat", "off"], "temperature": None, "min_temp": 5.0, "max_temp": 30.0}
    hass.states.get = MagicMock(return_value=state)

    room = make_room()
    ctrl = MPCController(
        hass, room, model_manager=RoomModelManager(), outdoor_temp=5.0, settings={}, has_external_sensor=True
    )
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 21.0})
    assert hass.services.async_call.call_count == 1

    # Second identical call should be skipped by cache
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 21.0})
    assert hass.services.async_call.call_count == 1


@pytest.mark.asyncio
async def test_call_cache_allows_different_temperature():
    """Cache allows calls with different temperatures to go through."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "temperature": None, "min_temp": 5.0, "max_temp": 30.0}
    hass.states.get = MagicMock(return_value=state)

    room = make_room()
    ctrl = MPCController(
        hass, room, model_manager=RoomModelManager(), outdoor_temp=5.0, settings={}, has_external_sensor=True
    )
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 21.0})
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 22.0})
    assert hass.services.async_call.call_count == 2


@pytest.mark.asyncio
async def test_call_cache_device_state_takes_priority():
    """Device state dedup takes priority over cache when state attributes are available."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 21.0, "min_temp": 5.0, "max_temp": 30.0}
    hass.states.get = MagicMock(return_value=state)

    # Prepopulate cache with a different temperature
    _last_commands["climate.living_trv"] = {
        "service": "set_temperature",
        "hvac_mode": None,
        "temperature": 20.0,
        "target_temp_low": None,
        "target_temp_high": None,
    }

    room = make_room()
    ctrl = MPCController(
        hass, room, model_manager=RoomModelManager(), outdoor_temp=5.0, settings={}, has_external_sensor=True
    )
    # 21.0 matches device state (21.0), so skipped by primary dedup, not cache
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 21.0})
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_call_cache_not_updated_on_exception():
    """Cache is not updated when the service call raises an exception."""
    hass = build_hass()
    hass.states.get = MagicMock(return_value=None)
    hass.services.async_call = AsyncMock(side_effect=Exception("fail"))

    room = make_room()
    ctrl = MPCController(
        hass, room, model_manager=RoomModelManager(), outdoor_temp=5.0, settings={}, has_external_sensor=True
    )
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 21.0})
    assert "climate.living_trv" not in _last_commands


@pytest.mark.asyncio
async def test_call_cache_persists_across_controller_instances():
    """Module-level cache persists across MPCController instances."""
    hass = build_hass()
    state = MagicMock()
    state.state = "unavailable"
    state.attributes = {"hvac_modes": ["heat", "off"], "temperature": None, "min_temp": 5.0, "max_temp": 30.0}
    hass.states.get = MagicMock(return_value=state)

    room = make_room()
    ctrl1 = MPCController(
        hass, room, model_manager=RoomModelManager(), outdoor_temp=5.0, settings={}, has_external_sensor=True
    )
    await ctrl1._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 21.0})
    assert hass.services.async_call.call_count == 1

    # New controller instance, same entity and temperature
    ctrl2 = MPCController(
        hass, room, model_manager=RoomModelManager(), outdoor_temp=5.0, settings={}, has_external_sensor=True
    )
    await ctrl2._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 21.0})
    assert hass.services.async_call.call_count == 1


@pytest.mark.asyncio
async def test_call_cache_dual_setpoint_fallback():
    """Cache fallback works for dual-setpoint IR devices."""
    hass = build_hass()
    state = MagicMock()
    state.state = "unavailable"
    state.attributes = {
        "hvac_modes": ["heat_cool", "off"],
        "target_temp_low": None,
        "target_temp_high": None,
        "min_temp": 5.0,
        "max_temp": 30.0,
    }
    hass.states.get = MagicMock(return_value=state)

    room = make_room(thermostats=[], acs=["climate.living_trv"])
    ctrl = MPCController(
        hass, room, model_manager=RoomModelManager(), outdoor_temp=5.0, settings={}, has_external_sensor=True
    )
    await ctrl._call(
        "set_temperature",
        {"entity_id": "climate.living_trv", "target_temp_low": 18.0, "target_temp_high": 22.0},
    )
    assert hass.services.async_call.call_count == 1

    # Second identical call should be skipped by cache
    await ctrl._call(
        "set_temperature",
        {"entity_id": "climate.living_trv", "target_temp_low": 18.0, "target_temp_high": 22.0},
    )
    assert hass.services.async_call.call_count == 1


@pytest.mark.asyncio
async def test_call_cache_hvac_mode_fallback_no_state():
    """Cache fallback works for set_hvac_mode when device has no state."""
    hass = build_hass()
    hass.states.get = MagicMock(return_value=None)

    room = make_room()
    ctrl = MPCController(
        hass, room, model_manager=RoomModelManager(), outdoor_temp=5.0, settings={}, has_external_sensor=True
    )
    await ctrl._call("set_hvac_mode", {"entity_id": "climate.living_trv", "hvac_mode": "heat"})
    assert hass.services.async_call.call_count == 1

    # Second call skipped by cache
    await ctrl._call("set_hvac_mode", {"entity_id": "climate.living_trv", "hvac_mode": "heat"})
    assert hass.services.async_call.call_count == 1


@pytest.mark.asyncio
async def test_turn_off_cache_fallback():
    """async_turn_off_climate skips when cache says device is already off (IR device)."""
    hass = build_hass()
    state = MagicMock()
    state.state = "unavailable"
    state.attributes = {"hvac_modes": ["heat", "off"]}
    hass.states.get = MagicMock(return_value=state)

    # Prepopulate cache with off command
    _last_commands["climate.ac"] = {
        "service": "set_hvac_mode",
        "hvac_mode": "off",
        "temperature": None,
        "target_temp_low": None,
        "target_temp_high": None,
    }

    await async_turn_off_climate(hass, "climate.ac")
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_turn_off_cache_updated():
    """Final cache entry after async_turn_off_climate is set_hvac_mode(off).

    With the reordering fix, set_temperature(min_temp) is sent first (device is
    still in heat mode and processes it), then set_hvac_mode(off) becomes the
    final cache entry — which is exactly what the IR-device early-return check
    looks for (service="set_hvac_mode", hvac_mode="off").
    """
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0, "temperature": 25.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.ac")
    assert "climate.ac" in _last_commands
    assert hass.services.async_call.call_count == 2
    # Final cache entry is set_hvac_mode(off) — enables IR-device early-return on subsequent calls
    assert _last_commands["climate.ac"]["service"] == "set_hvac_mode"
    assert _last_commands["climate.ac"]["hvac_mode"] == "off"


@pytest.mark.asyncio
async def test_turn_off_call_order_set_temperature_before_set_hvac_mode():
    """set_temperature(min_temp) must be the FIRST call, set_hvac_mode(off) the SECOND.

    This ordering is required for Wavin AHC9000 and similar devices that only
    process temperature changes while still in heat mode.  Sending set_temperature
    first (while the device is active) ensures the valve closes even if
    set_hvac_mode(off) is later ignored by the firmware.  This test pins the
    invariant introduced in PR #160 so that any future refactor accidentally
    reversing the order is caught immediately.
    """
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0, "temperature": 25.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")

    calls = hass.services.async_call.call_args_list
    assert len(calls) == 2
    assert calls[0][0][1] == "set_temperature", (
        "First service call must be set_temperature — device must receive setpoint while still in heat mode"
    )
    assert calls[1][0][1] == "set_hvac_mode", "Second service call must be set_hvac_mode(off)"


@pytest.mark.asyncio
async def test_turn_off_ir_device_second_call_skipped_via_cache():
    """IR device: after first call, cache has set_hvac_mode(off) → second call skipped.

    Verifies that the reordered cache state (set_hvac_mode as final entry) correctly
    enables the IR-device early-return check on subsequent calls.  With the old
    order the final cache entry was set_temperature, so the early-return was never
    triggered and both commands were re-sent on every coordinator cycle.
    """
    hass = build_hass()
    state = MagicMock()
    state.state = "unavailable"
    state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0, "temperature": None}
    hass.states.get = MagicMock(return_value=state)

    # First call: both set_temperature(5.0) and set_hvac_mode(off) are sent
    await async_turn_off_climate(hass, "climate.ir_ac")
    assert hass.services.async_call.call_count == 2
    assert _last_commands["climate.ir_ac"]["service"] == "set_hvac_mode"
    assert _last_commands["climate.ir_ac"]["hvac_mode"] == "off"

    # Second call: cache says set_hvac_mode(off) → early return, no new calls
    await async_turn_off_climate(hass, "climate.ir_ac")
    assert hass.services.async_call.call_count == 2  # unchanged


@pytest.mark.asyncio
async def test_call_cache_rounding():
    """Cache comparison uses rounding, so 21.04 and 21.05 both round to 21.0."""
    hass = build_hass()
    state = MagicMock()
    state.state = "unavailable"
    state.attributes = {"hvac_modes": ["heat", "off"], "temperature": None, "min_temp": 5.0, "max_temp": 30.0}
    hass.states.get = MagicMock(return_value=state)

    room = make_room()
    ctrl = MPCController(
        hass, room, model_manager=RoomModelManager(), outdoor_temp=5.0, settings={}, has_external_sensor=True
    )
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 21.04})
    assert hass.services.async_call.call_count == 1

    # 21.05 rounds to 21.1 (Python banker's rounding: round(21.05, 1) = 21.1, round(21.04, 1) = 21.0)
    # So use 21.049 which also rounds to 21.0
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 21.049})
    assert hass.services.async_call.call_count == 1


# ---------------------------------------------------------------------------
# Turn-off fallback path cache tests (heat-only / cool-only devices without "off")
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_off_heat_only_cache_fallback_single_setpoint():
    """Heat-only TRV without 'off': cache prevents redundant min_temp fallback (IR device)."""
    hass = build_hass()
    state = MagicMock()
    state.state = "unavailable"
    state.attributes = {
        "hvac_modes": ["heat"],
        "min_temp": 5.0,
        "max_temp": 30.0,
        "temperature": None,  # IR device: no temperature feedback
    }
    hass.states.get = MagicMock(return_value=state)

    # First call goes through (sets to min_temp=5.0)
    await async_turn_off_climate(hass, "climate.trv", area_id="bedroom")
    assert hass.services.async_call.call_count == 1
    call_data = hass.services.async_call.call_args[0][2]
    assert call_data["temperature"] == 5.0

    # Second call: cache has temperature=5.0, matches fallback_temp=5.0 → skipped
    await async_turn_off_climate(hass, "climate.trv", area_id="bedroom")
    assert hass.services.async_call.call_count == 1


@pytest.mark.asyncio
async def test_turn_off_cool_only_cache_fallback_single_setpoint():
    """Cool-only device without 'off': cache prevents redundant max_temp fallback (IR device)."""
    hass = build_hass()
    state = MagicMock()
    state.state = "unavailable"
    state.attributes = {
        "hvac_modes": ["cool"],
        "min_temp": 16.0,
        "max_temp": 30.0,
        "temperature": None,  # IR device
    }
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.ac", area_id="living")
    assert hass.services.async_call.call_count == 1
    call_data = hass.services.async_call.call_args[0][2]
    assert call_data["temperature"] == 30.0

    # Cached → skipped
    await async_turn_off_climate(hass, "climate.ac", area_id="living")
    assert hass.services.async_call.call_count == 1


@pytest.mark.asyncio
async def test_turn_off_cool_only_cache_fallback_range_device():
    """Cool-only range device without 'off': cache prevents redundant fallback (IR device).

    Range device where target_temp_low has a value (is_range=True) but
    target_temp_high is None (cur_check=None for cooling), so cache is consulted.
    """
    hass = build_hass()
    state = MagicMock()
    state.state = "unavailable"
    state.attributes = {
        "hvac_modes": ["cool"],
        "min_temp": 16.0,
        "max_temp": 30.0,
        "target_temp_low": 18.0,  # Has value → is_range=True
        "target_temp_high": None,  # None → cur_check=None for cooling → cache fallback
    }
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.ac", area_id="living")
    assert hass.services.async_call.call_count == 1
    call_data = hass.services.async_call.call_args[0][2]
    assert call_data["target_temp_low"] == 30.0
    assert call_data["target_temp_high"] == 30.0

    # Cached → skipped
    await async_turn_off_climate(hass, "climate.ac", area_id="living")
    assert hass.services.async_call.call_count == 1


@pytest.mark.asyncio
async def test_turn_off_fallback_cache_updated():
    """Turn-off fallback path updates the cache after successful call."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {
        "hvac_modes": ["heat"],
        "min_temp": 5.0,
        "max_temp": 30.0,
        "temperature": None,
    }
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv", area_id="bedroom")
    assert "climate.trv" in _last_commands
    assert _last_commands["climate.trv"]["service"] == "set_temperature"
    assert _last_commands["climate.trv"]["temperature"] == 5.0


@pytest.mark.asyncio
async def test_turn_off_fallback_cache_not_updated_on_exception():
    """Turn-off fallback path does not update cache when service call fails."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {
        "hvac_modes": ["heat"],
        "min_temp": 5.0,
        "max_temp": 30.0,
        "temperature": None,
    }
    hass.states.get = MagicMock(return_value=state)
    hass.services.async_call = AsyncMock(side_effect=Exception("IR timeout"))

    await async_turn_off_climate(hass, "climate.trv", area_id="bedroom")
    assert "climate.trv" not in _last_commands


@pytest.mark.asyncio
async def test_turn_off_normal_path_cache_not_updated_on_exception():
    """Normal off path does not update cache when service call fails."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"]}
    hass.states.get = MagicMock(return_value=state)
    hass.services.async_call = AsyncMock(side_effect=Exception("fail"))

    await async_turn_off_climate(hass, "climate.ac", area_id="living")
    assert "climate.ac" not in _last_commands


@pytest.mark.asyncio
async def test_turn_off_partial_failure_set_hvac_mode_exception_cache_reflects_set_temperature():
    """set_temperature succeeds but set_hvac_mode(off) raises: cache stays at set_temperature.

    If set_hvac_mode fails (e.g. transient network error), the cache must NOT
    show set_hvac_mode(off).  On the next coordinator cycle the IR-device early-
    return check does not fire (cache service != "set_hvac_mode"), so the turn-off
    sequence is retried — which is the desired behaviour.
    """
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0, "temperature": 25.0}
    hass.states.get = MagicMock(return_value=state)

    async def fail_hvac_mode(*args, **kwargs):
        if args[1] == "set_hvac_mode":
            raise Exception("connection lost")

    hass.services.async_call = AsyncMock(side_effect=fail_hvac_mode)

    await async_turn_off_climate(hass, "climate.trv", area_id="living")

    # Both service calls were attempted
    assert hass.services.async_call.call_count == 2
    # Cache reflects the successful set_temperature call — NOT set_hvac_mode(off)
    assert "climate.trv" in _last_commands
    assert _last_commands["climate.trv"]["service"] == "set_temperature"
    assert _last_commands["climate.trv"]["temperature"] == 5.0


@pytest.mark.asyncio
async def test_call_cache_mode_change_not_blocked():
    """Changing mode (heat→cool) is not blocked by cache from previous mode."""
    hass = build_hass()
    state = MagicMock()
    state.state = "unavailable"  # IR device: cache is used for redundancy
    state.attributes = {"hvac_modes": ["heat", "cool", "off"], "temperature": None, "min_temp": 16, "max_temp": 30}
    hass.states.get = MagicMock(return_value=state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass, room, model_manager=RoomModelManager(), outdoor_temp=5.0, settings={}, has_external_sensor=True
    )

    # Send heat mode + temperature
    await ctrl._call("set_hvac_mode", {"entity_id": "climate.ac", "hvac_mode": "heat"})
    await ctrl._call("set_temperature", {"entity_id": "climate.ac", "temperature": 25.0})
    assert hass.services.async_call.call_count == 2

    # Switch to cool: different hvac_mode → goes through (cache has "heat")
    await ctrl._call("set_hvac_mode", {"entity_id": "climate.ac", "hvac_mode": "cool"})
    assert hass.services.async_call.call_count == 3

    # Different temperature for cooling → goes through
    await ctrl._call("set_temperature", {"entity_id": "climate.ac", "temperature": 20.0})
    assert hass.services.async_call.call_count == 4

    # Same cool temperature again → blocked by cache
    await ctrl._call("set_temperature", {"entity_id": "climate.ac", "temperature": 20.0})
    assert hass.services.async_call.call_count == 4


@pytest.mark.asyncio
async def test_call_cache_different_entities_independent():
    """Cache entries are per-entity, not shared across devices."""
    hass = build_hass()
    state = MagicMock()
    state.state = "unavailable"
    state.attributes = {"hvac_modes": ["heat", "off"], "temperature": None, "min_temp": 5, "max_temp": 30}
    hass.states.get = MagicMock(return_value=state)

    room = make_room(thermostats=["climate.trv1", "climate.trv2"])
    ctrl = MPCController(
        hass, room, model_manager=RoomModelManager(), outdoor_temp=5.0, settings={}, has_external_sensor=True
    )

    # Same temperature to two different entities: both go through
    await ctrl._call("set_temperature", {"entity_id": "climate.trv1", "temperature": 21.0})
    await ctrl._call("set_temperature", {"entity_id": "climate.trv2", "temperature": 21.0})
    assert hass.services.async_call.call_count == 2

    # Repeat: both blocked by their own cache entries
    await ctrl._call("set_temperature", {"entity_id": "climate.trv1", "temperature": 21.0})
    await ctrl._call("set_temperature", {"entity_id": "climate.trv2", "temperature": 21.0})
    assert hass.services.async_call.call_count == 2


@pytest.mark.asyncio
async def test_turn_off_cache_invalidated_by_heat_command():
    """After turning off via cache, a heat command goes through (different service intent)."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 22.0, "min_temp": 5, "max_temp": 30}
    hass.states.get = MagicMock(return_value=state)

    # Turn off from "heat" → defense-in-depth set_temperature(5.0) + set_hvac_mode("off")
    await async_turn_off_climate(hass, "climate.trv")
    assert hass.services.async_call.call_count == 2

    # Now device comes on: state changes to "heat"
    state.state = "heat"
    state.attributes["temperature"] = 22.0

    room = make_room()
    ctrl = MPCController(
        hass, room, model_manager=RoomModelManager(), outdoor_temp=5.0, settings={}, has_external_sensor=True
    )
    # Heat command goes through (cache has set_hvac_mode(off), not set_temperature at 25)
    await ctrl._call("set_temperature", {"entity_id": "climate.trv", "temperature": 25.0})
    assert hass.services.async_call.call_count == 3

    # Turn off again → goes through (state is "heat", no cache for off)
    # Sends set_hvac_mode(off) + defense-in-depth set_temperature(min_temp)
    await async_turn_off_climate(hass, "climate.trv")
    assert hass.services.async_call.call_count == 5


@pytest.mark.asyncio
async def test_call_cache_dual_setpoint_different_values_not_blocked():
    """Cache allows dual-setpoint calls with different values."""
    hass = build_hass()
    state = MagicMock()
    state.state = "unavailable"
    state.attributes = {
        "hvac_modes": ["heat_cool", "off"],
        "target_temp_low": None,
        "target_temp_high": None,
        "min_temp": 5.0,
        "max_temp": 30.0,
    }
    hass.states.get = MagicMock(return_value=state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass, room, model_manager=RoomModelManager(), outdoor_temp=5.0, settings={}, has_external_sensor=True
    )

    await ctrl._call(
        "set_temperature",
        {"entity_id": "climate.ac", "target_temp_low": 18.0, "target_temp_high": 22.0},
    )
    assert hass.services.async_call.call_count == 1

    # Different low → goes through
    await ctrl._call(
        "set_temperature",
        {"entity_id": "climate.ac", "target_temp_low": 19.0, "target_temp_high": 22.0},
    )
    assert hass.services.async_call.call_count == 2

    # Different high → goes through
    await ctrl._call(
        "set_temperature",
        {"entity_id": "climate.ac", "target_temp_low": 19.0, "target_temp_high": 23.0},
    )
    assert hass.services.async_call.call_count == 3

    # Same as last → blocked
    await ctrl._call(
        "set_temperature",
        {"entity_id": "climate.ac", "target_temp_low": 19.0, "target_temp_high": 23.0},
    )
    assert hass.services.async_call.call_count == 3


# ---------------------------------------------------------------------------
# Cache bypass for devices with reliable state — Issue #134
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_off_retries_when_device_still_active():
    """Device reports state='heat' but cache says 'off' → command re-sent (#134).

    This is the exact bug: a TRV stays at 30-40°C because the cache prevents
    re-sending the 'off' command when the device didn't respond to it.
    """
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0, "temperature": 35.0}
    hass.states.get = MagicMock(return_value=state)

    # Prepopulate cache with off command (simulating a previous failed delivery)
    _last_commands["climate.trv"] = {
        "service": "set_hvac_mode",
        "hvac_mode": "off",
        "temperature": None,
        "target_temp_low": None,
        "target_temp_high": None,
    }

    await async_turn_off_climate(hass, "climate.trv")
    # Command MUST be re-sent because device is clearly still in "heat"
    # Both off + defense-in-depth set_temperature(min_temp)
    assert hass.services.async_call.call_count == 2


@pytest.mark.asyncio
async def test_turn_off_cache_works_for_unavailable_device():
    """Device state='unavailable' (IR device) → cache trusted, no re-send."""
    hass = build_hass()
    state = MagicMock()
    state.state = "unavailable"
    state.attributes = {"hvac_modes": ["heat", "cool", "off"]}
    hass.states.get = MagicMock(return_value=state)

    _last_commands["climate.ir_ac"] = {
        "service": "set_hvac_mode",
        "hvac_mode": "off",
        "temperature": None,
        "target_temp_low": None,
        "target_temp_high": None,
    }

    await async_turn_off_climate(hass, "climate.ir_ac")
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_turn_off_cache_works_for_unknown_device():
    """Device state='unknown' → cache trusted, no re-send."""
    hass = build_hass()
    state = MagicMock()
    state.state = "unknown"
    state.attributes = {"hvac_modes": ["heat", "cool", "off"]}
    hass.states.get = MagicMock(return_value=state)

    _last_commands["climate.ir_ac"] = {
        "service": "set_hvac_mode",
        "hvac_mode": "off",
        "temperature": None,
        "target_temp_low": None,
        "target_temp_high": None,
    }

    await async_turn_off_climate(hass, "climate.ir_ac")
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_turn_off_cache_works_for_none_state():
    """Device state=None (entity removed) → cache trusted, no re-send."""
    hass = build_hass()
    hass.states.get = MagicMock(return_value=None)

    _last_commands["climate.gone"] = {
        "service": "set_hvac_mode",
        "hvac_mode": "off",
        "temperature": None,
        "target_temp_low": None,
        "target_temp_high": None,
    }

    await async_turn_off_climate(hass, "climate.gone")
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_turn_off_fallback_retries_when_device_still_active():
    """Heat-only TRV with state='heat', temp=None, cache has min_temp → re-sent (#134)."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {
        "hvac_modes": ["heat"],
        "min_temp": 5.0,
        "max_temp": 30.0,
        "temperature": None,
    }
    hass.states.get = MagicMock(return_value=state)

    # First call goes through
    await async_turn_off_climate(hass, "climate.trv", area_id="bedroom")
    assert hass.services.async_call.call_count == 1

    # Second call: device still in "heat" → cache bypassed, command re-sent
    await async_turn_off_climate(hass, "climate.trv", area_id="bedroom")
    assert hass.services.async_call.call_count == 2


@pytest.mark.asyncio
async def test_call_cache_retries_when_device_contradicts():
    """_call() with state='heat', temp=None, cache has same temp → re-sent (#134)."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "temperature": None, "min_temp": 5.0, "max_temp": 30.0}
    hass.states.get = MagicMock(return_value=state)

    room = make_room()
    ctrl = MPCController(
        hass, room, model_manager=RoomModelManager(), outdoor_temp=5.0, settings={}, has_external_sensor=True
    )
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 21.0})
    assert hass.services.async_call.call_count == 1

    # Same command again: device reports state (not unavailable), so cache is NOT consulted
    await ctrl._call("set_temperature", {"entity_id": "climate.living_trv", "temperature": 21.0})
    assert hass.services.async_call.call_count == 2


# ---------------------------------------------------------------------------
# Defense-in-depth setpoint reset — Issue #134 follow-up
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_off_skips_temperature_when_no_min_temp():
    """Device with 'off' but no min_temp attribute: only set_hvac_mode, no set_temperature."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"]}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.trv", "hvac_mode": "off"},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_turn_off_skips_temperature_when_already_at_min():
    """Device already at min_temp: only set_hvac_mode, skip redundant set_temperature."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0, "temperature": 5.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.trv", "hvac_mode": "off"},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_turn_off_sends_temperature_when_device_ignores_off():
    """Permanently-off device (Wavin Sentio): only set_temperature, no set_hvac_mode.

    Devices with hvac_modes=["off"] are controlled purely via setpoint.
    Sending set_hvac_mode("off") can reset the setpoint on these devices.
    """
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["off"], "min_temp": 5.0, "max_temp": 40.0, "temperature": 40.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.wavin", area_id="bathroom")
    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_temperature",
        {"entity_id": "climate.wavin", "temperature": 5.0},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_permanently_off_device_already_off_lowers_setpoint():
    """Permanently-off device already in 'off' state: lower setpoint, no set_hvac_mode."""
    hass = build_hass()
    state = MagicMock()
    state.state = "off"
    state.attributes = {"hvac_modes": ["off"], "min_temp": 5.0, "max_temp": 30.0, "temperature": 22.5}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.wavin")
    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_temperature",
        {"entity_id": "climate.wavin", "temperature": 5.0},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_permanently_off_uses_fallback_when_min_temp_zero():
    """Permanently-off device with min_temp=0: uses fallback_setpoint instead."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["off"], "min_temp": 0, "max_temp": 30.0, "temperature": 22.5}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.wavin", fallback_setpoint=19.0)
    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_temperature",
        {"entity_id": "climate.wavin", "temperature": 19.0},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_permanently_off_uses_fallback_when_no_min_temp():
    """Permanently-off device without min_temp attr: uses fallback_setpoint."""
    hass = build_hass()
    state = MagicMock()
    state.state = "off"
    state.attributes = {"hvac_modes": ["off"], "temperature": 22.5}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.wavin", fallback_setpoint=19.0)
    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_temperature",
        {"entity_id": "climate.wavin", "temperature": 19.0},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_permanently_off_min_of_min_temp_and_fallback():
    """When both min_temp and fallback available, uses min_temp (device floor)."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["off"], "min_temp": 12.0, "max_temp": 30.0, "temperature": 22.5}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.wavin", fallback_setpoint=19.0)
    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_temperature",
        {"entity_id": "climate.wavin", "temperature": 12.0},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_permanently_off_no_min_temp_no_fallback_no_command():
    """Permanently-off device with no min_temp and no fallback: no command."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["off"], "temperature": 22.5}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.wavin")
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_normal_device_with_heat_off_still_sends_hvac_mode():
    """Device with hvac_modes=["heat", "off"] is NOT permanently-off: sends set_hvac_mode."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0, "max_temp": 30.0, "temperature": 22.5}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv")
    calls = hass.services.async_call.call_args_list
    assert len(calls) == 2
    assert calls[0][0] == ("climate", "set_temperature", {"entity_id": "climate.trv", "temperature": 5.0})
    assert calls[1][0] == ("climate", "set_hvac_mode", {"entity_id": "climate.trv", "hvac_mode": "off"})


@pytest.mark.asyncio
async def test_fallback_setpoint_used_for_defense_in_depth():
    """Normal device with min_temp=0: fallback used for defense-in-depth + set_hvac_mode still sent."""
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 0, "max_temp": 30.0, "temperature": 22.5}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.trv", fallback_setpoint=19.0)
    calls = hass.services.async_call.call_args_list
    assert len(calls) == 2
    assert calls[0][0] == ("climate", "set_temperature", {"entity_id": "climate.trv", "temperature": 19.0})
    assert calls[1][0] == ("climate", "set_hvac_mode", {"entity_id": "climate.trv", "hvac_mode": "off"})


class TestResolveIdleSetpoint:
    """Unit tests for _resolve_idle_setpoint."""

    def test_both_available_returns_min(self):
        state = MagicMock()
        state.attributes = {"min_temp": 5.0}
        assert _resolve_idle_setpoint(state, 19.0) == 5.0

    def test_min_temp_wins_over_lower_fallback(self):
        """min_temp is authoritative device floor, always used when available."""
        state = MagicMock()
        state.attributes = {"min_temp": 20.0}
        assert _resolve_idle_setpoint(state, 17.0) == 20.0

    def test_only_min_temp(self):
        state = MagicMock()
        state.attributes = {"min_temp": 7.0}
        assert _resolve_idle_setpoint(state, None) == 7.0

    def test_only_fallback(self):
        state = MagicMock()
        state.attributes = {}
        assert _resolve_idle_setpoint(state, 19.0) == 19.0

    def test_neither_available(self):
        state = MagicMock()
        state.attributes = {}
        assert _resolve_idle_setpoint(state, None) is None

    def test_min_temp_zero_uses_fallback(self):
        state = MagicMock()
        state.attributes = {"min_temp": 0}
        assert _resolve_idle_setpoint(state, 19.0) == 19.0

    def test_min_temp_negative_uses_fallback(self):
        state = MagicMock()
        state.attributes = {"min_temp": -5.0}
        assert _resolve_idle_setpoint(state, 19.0) == 19.0

    def test_min_temp_non_numeric_uses_fallback(self):
        state = MagicMock()
        state.attributes = {"min_temp": "unavailable"}
        assert _resolve_idle_setpoint(state, 19.0) == 19.0

    def test_state_none(self):
        assert _resolve_idle_setpoint(None, 19.0) == 19.0

    def test_state_none_no_fallback(self):
        assert _resolve_idle_setpoint(None, None) is None

    def test_min_temp_always_wins_over_lower_fallback(self):
        """Bug #188: fallback below min_temp must not be returned."""
        state = MagicMock()
        state.attributes = {"min_temp": 7.0}
        assert _resolve_idle_setpoint(state, 3.0) == 7.0


@pytest.mark.asyncio
async def test_turn_off_already_off_normal_device_with_min_temp_skips_setpoint():
    """Non-permanently-off device already off: no setpoint command (#188)."""
    hass = build_hass()
    state = MagicMock()
    state.state = "off"
    state.attributes = {"hvac_modes": ["heat", "cool", "off"], "min_temp": 7.0, "max_temp": 35.0, "temperature": 22.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.ac", fallback_setpoint=15.0)
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_turn_off_already_off_ac_with_fallback_only_skips_setpoint():
    """AC already off, no min_temp, with fallback: skip setpoint (#188)."""
    hass = build_hass()
    state = MagicMock()
    state.state = "off"
    state.attributes = {"hvac_modes": ["cool", "off"], "temperature": 22.0}
    hass.states.get = MagicMock(return_value=state)

    await async_turn_off_climate(hass, "climate.ac", fallback_setpoint=15.0)
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_send_idle_setpoint_clamps_below_min_temp():
    """Setpoint below device min_temp is clamped up (#188)."""
    hass = build_hass()
    state = MagicMock()
    state.attributes = {"temperature": 22.0, "min_temp": 7.0, "max_temp": 35.0}
    clear_command_cache()

    await _send_idle_setpoint(hass, "climate.ac", state, 3.0, area_id="hallway")
    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_temperature",
        {"entity_id": "climate.ac", "temperature": 7.0},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_send_idle_setpoint_clamps_above_max_temp():
    """Setpoint above device max_temp is clamped down."""
    hass = build_hass()
    state = MagicMock()
    state.attributes = {"temperature": 22.0, "min_temp": 7.0, "max_temp": 35.0}
    clear_command_cache()

    await _send_idle_setpoint(hass, "climate.ac", state, 40.0, area_id="test")
    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_temperature",
        {"entity_id": "climate.ac", "temperature": 35.0},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_send_idle_setpoint_clamp_makes_redundant():
    """Clamping to min_temp that matches current temp → no service call."""
    hass = build_hass()
    state = MagicMock()
    state.attributes = {"temperature": 7.0, "min_temp": 7.0, "max_temp": 35.0}
    clear_command_cache()

    await _send_idle_setpoint(hass, "climate.ac", state, 3.0, area_id="hallway")
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_permanently_off_entity_not_found():
    """Entity not found (state=None): sends set_hvac_mode("off") as best-effort, no crash."""
    hass = build_hass()
    hass.states.get = MagicMock(return_value=None)

    await async_turn_off_climate(hass, "climate.gone", fallback_setpoint=19.0)
    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.gone", "hvac_mode": "off"},
        blocking=True,
        context=ANY,
    )


@pytest.mark.asyncio
async def test_turn_off_wavin_ahc9000_realistic_hvac_modes():
    """Wavin AHC9000 realistic scenario: hvac_modes=['heat', 'off'], device in heat mode.

    The Wavin AHC9000 reports both 'heat' and 'off' in hvac_modes but ignores
    set_temperature commands when already in standby/off mode.  Sending
    set_temperature(min_temp) while still in 'heat' mode (before set_hvac_mode)
    ensures the valve physically closes.  This test uses the actual Wavin device
    attributes (not the simplified ['off']-only variant) to prevent regression
    against the real device profile.
    """
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

    await async_turn_off_climate(hass, "climate.wavin_ahc9000", area_id="bathroom")

    calls = hass.services.async_call.call_args_list
    assert len(calls) == 2
    # Setpoint lowered first — while device is still in heat mode (Wavin fix)
    assert calls[0][0][1] == "set_temperature"
    assert calls[0][0][2]["temperature"] == 5.0
    # Mode changed to off second
    assert calls[1][0][1] == "set_hvac_mode"
    assert calls[1][0][2]["hvac_mode"] == "off"


# ---------------------------------------------------------------------------
# Managed mode: AC-only room with heat+cool (no heat_cool) — Issue #100
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_managed_mode_ac_only_heat_cool_heats_when_cold():
    """AC-only managed mode: device temp below heat target → heat mode."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {
        "hvac_modes": ["heat", "cool", "off"],
        "current_temperature": 18.0,
        "temperature": None,
    }
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac1"], climate_mode="auto", temperature_sensor="")
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=None,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", TargetTemps(heat=21.0, cool=24.0))

    calls = hass.services.async_call.call_args_list
    hvac = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.ac1"]
    temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == "climate.ac1"]
    assert any(c[0][2]["hvac_mode"] == "heat" for c in hvac)
    assert any(c[0][2]["temperature"] == 21.0 for c in temp)


@pytest.mark.asyncio
async def test_managed_mode_ac_only_heat_cool_cools_when_hot():
    """AC-only managed mode: device temp above cool target → cool mode."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {
        "hvac_modes": ["heat", "cool", "off"],
        "current_temperature": 25.0,
        "temperature": None,
    }
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac1"], climate_mode="auto", temperature_sensor="")
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=None,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", TargetTemps(heat=21.0, cool=24.0))

    calls = hass.services.async_call.call_args_list
    hvac = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.ac1"]
    temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == "climate.ac1"]
    assert any(c[0][2]["hvac_mode"] == "cool" for c in hvac)
    assert any(c[0][2]["temperature"] == 24.0 for c in temp)


@pytest.mark.asyncio
async def test_managed_mode_ac_only_heat_cool_deadband_uses_heat():
    """AC-only managed mode: device temp in deadband → heat mode (safe default)."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {
        "hvac_modes": ["heat", "cool", "off"],
        "current_temperature": 22.0,
        "temperature": None,
    }
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac1"], climate_mode="auto", temperature_sensor="")
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=None,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", TargetTemps(heat=21.0, cool=24.0))

    calls = hass.services.async_call.call_args_list
    hvac = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.ac1"]
    assert any(c[0][2]["hvac_mode"] == "heat" for c in hvac)
    assert not any(c[0][2]["hvac_mode"] == "cool" for c in hvac)


@pytest.mark.asyncio
async def test_managed_mode_ac_only_heat_cool_no_current_temp():
    """AC-only managed mode: no current_temperature → heat mode (fallback)."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {
        "hvac_modes": ["heat", "cool", "off"],
        "temperature": None,
    }
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac1"], climate_mode="auto", temperature_sensor="")
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=None,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", TargetTemps(heat=21.0, cool=24.0))

    calls = hass.services.async_call.call_args_list
    hvac = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.ac1"]
    assert any(c[0][2]["hvac_mode"] == "heat" for c in hvac)
    assert not any(c[0][2]["hvac_mode"] == "cool" for c in hvac)


@pytest.mark.asyncio
async def test_managed_mode_mixed_room_ac_still_cools():
    """Mixed room (TRV+AC): AC still gets cool mode even when device temp is cold."""
    hass = build_hass()

    def _get(eid):
        s = MagicMock()
        s.state = "off"
        if eid == "climate.trv1":
            s.attributes = {"hvac_modes": ["heat", "off"], "temperature": None}
        else:
            s.attributes = {
                "hvac_modes": ["heat", "cool", "off"],
                "current_temperature": 18.0,
                "temperature": None,
            }
        return s

    hass.states.get = MagicMock(side_effect=_get)

    room = make_room(
        thermostats=["climate.trv1"],
        acs=["climate.ac1"],
        climate_mode="auto",
        temperature_sensor="",
    )
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=None,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", TargetTemps(heat=21.0, cool=24.0))

    calls = hass.services.async_call.call_args_list
    ac_hvac = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.ac1"]
    assert any(c[0][2]["hvac_mode"] == "cool" for c in ac_hvac)
    assert not any(c[0][2]["hvac_mode"] == "heat" for c in ac_hvac)


@pytest.mark.asyncio
async def test_managed_mode_ac_only_heat_cool_correct_target():
    """AC-only managed mode heating: temperature call uses heat_target, not cool_target."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {
        "hvac_modes": ["heat", "cool", "off"],
        "current_temperature": 18.0,
        "temperature": None,
    }
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac1"], climate_mode="auto", temperature_sensor="")
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=None,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", TargetTemps(heat=21.0, cool=24.0))

    calls = hass.services.async_call.call_args_list
    temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == "climate.ac1"]
    assert len(temp) == 1
    assert temp[0][0][2]["temperature"] == 21.0


@pytest.mark.asyncio
async def test_managed_mode_ac_only_outdoor_gated_heats_with_correct_target():
    """AC-only managed mode with outdoor gating (outdoor < cooling_min).

    Reproduces #100: user in Australia with HVAC supporting [off, cool, fan_only, heat]
    (no heat_cool), outdoor temp 10°C → can_cool=False due to outdoor_cooling_min=16.
    The smart AC-only branch (line 955) requires can_cool=True and is skipped.
    Verify the fallthrough still sets heat mode with the HEAT target, not cool target.
    """
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {
        "hvac_modes": ["off", "cool", "fan_only", "heat"],
        "current_temperature": 18.0,
        "temperature": None,
    }
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac1"], climate_mode="auto", temperature_sensor="")
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=10.0,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", TargetTemps(heat=21.0, cool=24.0))

    calls = hass.services.async_call.call_args_list
    hvac = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.ac1"]
    temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == "climate.ac1"]
    assert any(c[0][2]["hvac_mode"] == "heat" for c in hvac), f"Expected heat mode, got: {hvac}"
    assert len(temp) == 1
    assert temp[0][0][2]["temperature"] == 21.0, (
        f"Expected heat_target 21.0, got {temp[0][0][2]['temperature']} (cool_target leak)"
    )


@pytest.mark.asyncio
async def test_managed_mode_ac_only_outdoor_gated_unreliable_modes_preactivates():
    """AC-only managed mode: device off with unreliable modes + outdoor gating.

    Reproduces #100 variant: device is off and only reports ["off", "fan_only"],
    hiding heat/cool capabilities. Combined with outdoor_temp=10 (can_cool=False).
    Off zones with unreliable modes get pre-activated via fan_only (#135).
    """
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {
        "hvac_modes": ["off", "fan_only"],
        "current_temperature": 18.0,
        "temperature": None,
    }
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac1"], climate_mode="auto", temperature_sensor="")
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=10.0,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", TargetTemps(heat=21.0, cool=24.0))

    calls = hass.services.async_call.call_args_list
    hvac = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.ac1"]
    assert any(c[0][2]["hvac_mode"] == "fan_only" for c in hvac), f"Expected fan_only pre-activation, got: {hvac}"


@pytest.mark.asyncio
async def test_managed_mode_ac_only_outdoor_gated_cools_with_correct_target():
    """AC-only managed mode: outdoor > heating_max → can_heat=False, should cool with cool_target."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {
        "hvac_modes": ["off", "cool", "heat"],
        "current_temperature": 26.0,
        "temperature": None,
    }
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac1"], climate_mode="auto", temperature_sensor="")
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=25.0,
        settings={"outdoor_heating_max": 22.0},
        has_external_sensor=False,
    )
    await ctrl.async_apply("cooling", TargetTemps(heat=21.0, cool=24.0))

    calls = hass.services.async_call.call_args_list
    hvac = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.ac1"]
    temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == "climate.ac1"]
    assert any(c[0][2]["hvac_mode"] == "cool" for c in hvac)
    assert len(temp) == 1
    assert temp[0][0][2]["temperature"] == 24.0


@pytest.mark.asyncio
async def test_managed_mode_ac_only_auto_fallback_uses_heat_target():
    """AC-only managed mode: only 'auto' in modes, outdoor gating blocks cooling → heat_target used."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {
        "hvac_modes": ["off", "auto"],
        "current_temperature": 18.0,
        "temperature": None,
    }
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac1"], climate_mode="auto", temperature_sensor="")
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=10.0,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", TargetTemps(heat=21.0, cool=24.0))

    calls = hass.services.async_call.call_args_list
    hvac = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.ac1"]
    temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == "climate.ac1"]
    assert any(c[0][2]["hvac_mode"] == "auto" for c in hvac)
    assert len(temp) == 1
    assert temp[0][0][2]["temperature"] == 21.0, (
        f"Expected heat_target 21.0, got {temp[0][0][2]['temperature']} (cool_target leak)"
    )


@pytest.mark.asyncio
async def test_managed_mode_mixed_room_outdoor_gated_ac_heats_correct_target():
    """Mixed room: TRV+AC, outdoor=5 → can_cool=False, AC falls through to heat with heat_target."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0, "temperature": None}
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {
        "hvac_modes": ["off", "cool", "heat"],
        "current_temperature": 18.0,
        "temperature": None,
    }

    def state_get(eid):
        if eid == "climate.living_trv":
            return trv_state
        if eid == "climate.ac1":
            return ac_state
        return None

    hass.states.get = MagicMock(side_effect=state_get)

    room = make_room(
        thermostats=["climate.living_trv"], acs=["climate.ac1"], climate_mode="auto", temperature_sensor=""
    )
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", TargetTemps(heat=21.0, cool=24.0))

    calls = hass.services.async_call.call_args_list
    ac_hvac = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.ac1"]
    ac_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == "climate.ac1"]
    assert any(c[0][2]["hvac_mode"] == "heat" for c in ac_hvac)
    assert len(ac_temp) == 1
    assert ac_temp[0][0][2]["temperature"] == 21.0

    trv_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == "climate.living_trv"]
    assert len(trv_temp) == 1
    assert trv_temp[0][0][2]["temperature"] == 21.0


# ---------------------------------------------------------------------------
# Compressor forced_on / forced_off tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_idle_forced_on_keeps_device_active():
    """In idle mode, forced_on sets device to target temp instead of turning off."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0}
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply(
        "idle",
        TargetTemps(heat=21.0, cool=24.0),
        compressor_forced_on={"climate.living_trv"},
    )
    calls = hass.services.async_call.call_args_list
    # No turn-off call
    off_calls = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.living_trv"
        and c[0][1] == "set_hvac_mode"
        and c[0][2].get("hvac_mode") == "off"
    ]
    assert len(off_calls) == 0
    # set_temperature called with heat target
    temp_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.living_trv" and c[0][1] == "set_temperature"]
    assert len(temp_calls) == 1
    assert temp_calls[0][0][2]["temperature"] == 21.0


@pytest.mark.asyncio
async def test_apply_heating_forced_off_turns_off_trv():
    """In heating mode, forced_off turns off TRV despite heating being active."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0}
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply(
        "heating",
        TargetTemps(heat=21.0, cool=24.0),
        compressor_forced_off={"climate.living_trv"},
    )
    calls = hass.services.async_call.call_args_list
    off_calls = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.living_trv"
        and c[0][1] == "set_hvac_mode"
        and c[0][2].get("hvac_mode") == "off"
    ]
    assert len(off_calls) >= 1


@pytest.mark.asyncio
async def test_apply_cooling_forced_off_turns_off_ac():
    """In cooling mode, forced_off turns off AC despite cooling being active."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "cool"
    ac_state.attributes = {"hvac_modes": ["cool", "off"], "min_temp": 16.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply(
        "cooling",
        TargetTemps(heat=21.0, cool=24.0),
        compressor_forced_off={"climate.ac"},
    )
    calls = hass.services.async_call.call_args_list
    off_calls = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.ac" and c[0][1] == "set_hvac_mode" and c[0][2].get("hvac_mode") == "off"
    ]
    assert len(off_calls) >= 1


@pytest.mark.asyncio
async def test_apply_managed_auto_forced_off():
    """In managed auto mode (no external sensor), forced_off turns off device."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0}
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room(temperature_sensor="")
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply(
        "heating",
        TargetTemps(heat=21.0, cool=24.0),
        compressor_forced_off={"climate.living_trv"},
    )
    calls = hass.services.async_call.call_args_list
    off_calls = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.living_trv"
        and c[0][1] == "set_hvac_mode"
        and c[0][2].get("hvac_mode") == "off"
    ]
    assert len(off_calls) >= 1


@pytest.mark.asyncio
async def test_apply_forced_on_and_off_empty_sets_no_effect():
    """Empty forced_on/forced_off sets do not alter normal behavior."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "off"  # not yet heating, so set_hvac_mode won't be skipped as redundant
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0}
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    # Normal heating with empty sets
    await ctrl.async_apply(
        "heating",
        TargetTemps(heat=21.0, cool=24.0),
        compressor_forced_on=set(),
        compressor_forced_off=set(),
    )
    calls = hass.services.async_call.call_args_list
    # TRV should receive heat mode and temperature as normal
    heat_calls = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.living_trv"
        and c[0][1] == "set_hvac_mode"
        and c[0][2].get("hvac_mode") == "heat"
    ]
    assert len(heat_calls) >= 1


@pytest.mark.asyncio
async def test_apply_idle_forced_on_cooling_ac():
    """In idle mode, forced_on AC in cool mode gets cool target."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "cool"
    ac_state.attributes = {"hvac_modes": ["cool", "heat", "off"], "min_temp": 16.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply(
        "idle",
        TargetTemps(heat=21.0, cool=24.0),
        compressor_forced_on={"climate.ac"},
    )
    calls = hass.services.async_call.call_args_list
    # set_temperature called with cool target
    temp_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.ac" and c[0][1] == "set_temperature"]
    assert len(temp_calls) == 1
    assert temp_calls[0][0][2]["temperature"] == 24.0
    # No hvac_mode change (device already in cool mode)
    mode_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.ac" and c[0][1] == "set_hvac_mode"]
    assert len(mode_calls) == 0


@pytest.mark.asyncio
async def test_apply_idle_forced_on_heat_cool_device():
    """In idle mode, forced_on device in heat_cool gets heat target via temp_intent."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "heat_cool"
    ac_state.attributes = {
        "hvac_modes": ["heat_cool", "off"],
        "min_temp": 16.0,
        "target_temp_low": 18.0,
        "target_temp_high": 26.0,
    }
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=20.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply(
        "idle",
        TargetTemps(heat=21.0, cool=24.0),
        compressor_forced_on={"climate.ac"},
    )
    calls = hass.services.async_call.call_args_list
    # set_temperature called with heat target (dual-setpoint handled by _call)
    temp_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.ac" and c[0][1] == "set_temperature"]
    assert len(temp_calls) == 1
    # _call converts to target_temp_low/high for dual-setpoint devices
    assert temp_calls[0][0][2].get("target_temp_low") == 21.0


@pytest.mark.asyncio
async def test_apply_idle_forced_on_no_target():
    """Forced_on device with no matching target does nothing (no crash)."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0}
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply(
        "idle",
        TargetTemps(heat=None, cool=None),
        compressor_forced_on={"climate.living_trv"},
    )
    calls = hass.services.async_call.call_args_list
    # No service calls for the forced_on device (no target available)
    trv_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.living_trv"]
    assert len(trv_calls) == 0


@pytest.mark.asyncio
async def test_apply_idle_forced_on_device_state_none():
    """Forced_on device with unavailable state (None) does nothing."""
    hass = build_hass()
    # build_hass default: hass.states.get returns None
    room = make_room()
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply(
        "idle",
        TargetTemps(heat=21.0, cool=24.0),
        compressor_forced_on={"climate.living_trv"},
    )
    calls = hass.services.async_call.call_args_list
    trv_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.living_trv"]
    assert len(trv_calls) == 0


@pytest.mark.asyncio
async def test_apply_idle_forced_on_heat_cool_no_targets():
    """Forced_on device in heat_cool with no targets does nothing."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "heat_cool"
    ac_state.attributes = {
        "hvac_modes": ["heat_cool", "off"],
        "min_temp": 16.0,
        "target_temp_low": 18.0,
        "target_temp_high": 26.0,
    }
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=20.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply(
        "idle",
        TargetTemps(heat=None, cool=None),
        compressor_forced_on={"climate.ac"},
    )
    calls = hass.services.async_call.call_args_list
    ac_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.ac"]
    assert len(ac_calls) == 0


@pytest.mark.asyncio
async def test_apply_idle_forced_on_managed_mode():
    """Forced_on in managed mode (no external sensor) sets target correctly."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0}
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room(temperature_sensor="")  # managed mode: no external sensor
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply(
        "idle",
        TargetTemps(heat=21.0, cool=24.0),
        compressor_forced_on={"climate.living_trv"},
    )
    calls = hass.services.async_call.call_args_list
    # No turn-off
    off_calls = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.living_trv"
        and c[0][1] == "set_hvac_mode"
        and c[0][2].get("hvac_mode") == "off"
    ]
    assert len(off_calls) == 0
    # set_temperature called with heat target
    temp_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.living_trv" and c[0][1] == "set_temperature"]
    assert len(temp_calls) == 1
    assert temp_calls[0][0][2]["temperature"] == 21.0


# ---------------------------------------------------------------------------
# Unreliable hvac_modes (#100): devices off with incomplete modes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_heating_ac_unreliable_modes_preactivates_fan_only():
    """AC off with only off+fan_only pre-activates via fan_only (#135)."""
    _last_commands.clear()
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["off", "fan_only"], "temperature": 16.0, "min_temp": 5, "max_temp": 35}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0)

    calls = hass.services.async_call.call_args_list
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    assert len(hvac_calls) >= 1
    assert hvac_calls[0][0][2]["hvac_mode"] == "fan_only"


@pytest.mark.asyncio
async def test_apply_heating_ac_unreliable_fan_only_zone_sends_heat():
    """AC in fan_only (not off) with unreliable modes sends heat directly (#135).

    When a zone is already active (fan_only), it can accept heat mode directly.
    The pre-activation only triggers for zones that are "off".
    """
    _last_commands.clear()
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "fan_only"
    ac_state.attributes = {"hvac_modes": ["off", "fan_only"], "temperature": 16.0, "min_temp": 5, "max_temp": 35}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0)

    calls = hass.services.async_call.call_args_list
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    assert len(hvac_calls) >= 1
    assert hvac_calls[0][0][2]["hvac_mode"] == "heat"


@pytest.mark.asyncio
async def test_apply_cooling_ac_unreliable_modes_preactivates_fan_only():
    """AC off with unreliable modes pre-activates via fan_only for cooling (#135)."""
    _last_commands.clear()
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["off", "fan_only"], "temperature": 28.0, "min_temp": 16, "max_temp": 30}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("cooling", 24.0)

    calls = hass.services.async_call.call_args_list
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    assert len(hvac_calls) >= 1
    assert hvac_calls[0][0][2]["hvac_mode"] == "fan_only"


@pytest.mark.asyncio
async def test_apply_heating_ac_unreliable_no_fan_only_sends_directly():
    """AC off with unreliable modes but no fan_only sends heat directly (#135).

    If the device doesn't support fan_only (e.g. modes=["off"]), we fall back
    to sending the desired mode directly as before.
    """
    _last_commands.clear()
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["off"], "temperature": 16.0, "min_temp": 5, "max_temp": 35}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0)

    calls = hass.services.async_call.call_args_list
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    assert len(hvac_calls) >= 1
    assert hvac_calls[0][0][2]["hvac_mode"] == "heat"


@pytest.mark.asyncio
async def test_apply_heating_ac_reliable_no_heat_turns_off():
    """AC off with reliable modes (cool only) should be turned off when heating."""
    _last_commands.clear()
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["off", "cool"], "temperature": 23.0, "min_temp": 16, "max_temp": 30}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0)

    calls = hass.services.async_call.call_args_list
    # Cool-only AC cannot heat — should be turned off (or no heat command sent)
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    heat_calls = [c for c in hvac_calls if c[0][2].get("hvac_mode") == "heat"]
    assert len(heat_calls) == 0


@pytest.mark.asyncio
async def test_apply_managed_mode_ac_unreliable_modes_preactivates():
    """Managed mode: AC off with unreliable modes pre-activates via fan_only (#135)."""
    _last_commands.clear()
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {
        "hvac_modes": ["off", "fan_only"],
        "current_temperature": 18.0,
        "temperature": 16.0,
        "min_temp": 5,
        "max_temp": 35,
    }
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"], temperature_sensor="")
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", TargetTemps(heat=21.0, cool=24.0))

    calls = hass.services.async_call.call_args_list
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    assert len(hvac_calls) >= 1
    assert hvac_calls[0][0][2]["hvac_mode"] == "fan_only"


# ---------------------------------------------------------------------------
# target_temp_step snapping (#122)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, step, expected",
    [
        (22.3, 1.0, 22.0),
        (22.7, 1.0, 23.0),
        (22.5, 1.0, 22.0),  # banker's rounding: .5 rounds to even
        (23.5, 1.0, 24.0),  # .5 rounds to even
        (22.3, 0.5, 22.5),
        (22.1, 0.5, 22.0),
        (22.0, 0.5, 22.0),
        (22.3, 0.1, 22.3),
        (22.34, 0.1, 22.3),
        (22.0, None, 22.0),
        (22.3, 0.0, 22.3),
        (22.3, -1.0, 22.3),
    ],
)
def test_snap_to_step(value, step, expected):
    assert _snap_to_step(value, step) == expected


@pytest.mark.asyncio
async def test_call_snaps_temperature_to_step():
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {
        "hvac_modes": ["heat", "off"],
        "min_temp": 5.0,
        "max_temp": 30.0,
        "target_temp_step": 1.0,
        "temperature": None,
    }
    hass.states.get = MagicMock(return_value=state)

    room = make_room(acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    _last_commands.clear()
    await ctrl.async_apply("heating", 21.0, power_fraction=0.15, current_temp=20.0)

    temp_calls = [
        c
        for c in hass.services.async_call.call_args_list
        if c[0][1] == "set_temperature" and c[0][2].get("entity_id") == "climate.ac"
    ]
    for call in temp_calls:
        temp = call[0][2].get("temperature")
        if temp is not None:
            assert temp == round(temp), f"temperature {temp} not snapped to step 1"


@pytest.mark.asyncio
async def test_call_snaps_dual_setpoint_to_step():
    hass = build_hass()
    state = MagicMock()
    state.state = "heat_cool"
    state.attributes = {
        "hvac_modes": ["heat_cool", "off"],
        "min_temp": 5.0,
        "max_temp": 30.0,
        "target_temp_step": 1.0,
        "target_temp_low": 20.0,
        "target_temp_high": 25.0,
        "temperature": None,
    }
    hass.states.get = MagicMock(return_value=state)

    room = make_room(thermostats=[], acs=["climate.ac"], temperature_sensor="")
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )
    _last_commands.clear()
    await ctrl.async_apply("heating", TargetTemps(heat=21.3, cool=24.7))

    temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    for call in temp_calls:
        d = call[0][2]
        if "target_temp_low" in d:
            assert d["target_temp_low"] == round(d["target_temp_low"]), (
                f"target_temp_low {d['target_temp_low']} not snapped"
            )
            assert d["target_temp_high"] == round(d["target_temp_high"]), (
                f"target_temp_high {d['target_temp_high']} not snapped"
            )


@pytest.mark.asyncio
async def test_call_no_snap_without_step():
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {
        "hvac_modes": ["heat", "off"],
        "min_temp": 5.0,
        "max_temp": 30.0,
        "temperature": None,
    }
    hass.states.get = MagicMock(return_value=state)

    room = make_room()
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    _last_commands.clear()
    await ctrl.async_apply("heating", 21.0, power_fraction=0.15, current_temp=20.0)

    temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    for call in temp_calls:
        temp = call[0][2].get("temperature")
        if temp is not None:
            assert isinstance(temp, float)


@pytest.mark.asyncio
async def test_idle_setback_snaps_to_step():
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {
        "hvac_modes": ["heat", "off"],
        "min_temp": 5.0,
        "max_temp": 30.0,
        "target_temp_step": 1.0,
        "temperature": None,
    }
    hass.states.get = MagicMock(return_value=state)

    devices = [
        {"entity_id": "climate.ac", "type": "ac", "role": "auto", "idle_action": "setback", "idle_fan_mode": "low"}
    ]
    _last_commands.clear()
    await async_idle_device(
        hass,
        "climate.ac",
        devices,
        area_id="test",
        targets=TargetTemps(heat=21.3, cool=None),
    )
    temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert len(temp_calls) == 1
    temp = temp_calls[0][0][2]["temperature"]
    assert temp == round(temp), f"setback temp {temp} not snapped to step 1"


@pytest.mark.asyncio
async def test_snap_reclamps_to_max():
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {
        "hvac_modes": ["heat", "off"],
        "min_temp": 16.0,
        "max_temp": 29.5,
        "target_temp_step": 1.0,
        "temperature": None,
    }
    hass.states.get = MagicMock(return_value=state)

    room = make_room()
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    _last_commands.clear()
    await ctrl.async_apply("heating", 29.0, power_fraction=0.9, current_temp=28.0)

    temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    for call in temp_calls:
        temp = call[0][2].get("temperature")
        if temp is not None:
            assert temp <= 29.5, f"temperature {temp} exceeds max_temp 29.5"


# ── Direct setpoint mode tests ───────────────────────────────────────


@pytest.mark.asyncio
async def test_direct_setpoint_trv_heating():
    """TRV with setpoint_mode='direct' receives effective_target, not boost."""
    hass = build_hass()
    room = make_room()
    # Override device to direct mode
    room["devices"] = [
        {
            "entity_id": "climate.living_trv",
            "type": "trv",
            "role": "auto",
            "heating_system_type": "",
            "setpoint_mode": "direct",
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
    _last_commands.clear()
    await ctrl.async_apply("heating", 21.0, power_fraction=1.0, current_temp=19.0)

    calls = hass.services.async_call.call_args_list
    set_temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert set_temp_calls
    # Direct mode: device receives target (21.0), NOT boost (30.0)
    temp_arg = set_temp_calls[0][0][2]["temperature"]
    assert temp_arg == 21.0


@pytest.mark.asyncio
async def test_direct_setpoint_ac_cooling():
    """AC with setpoint_mode='direct' in cooling receives effective_target."""
    hass = build_hass()
    room = make_room(thermostats=[], acs=["climate.ac"])
    room["devices"] = [
        {"entity_id": "climate.ac", "type": "ac", "role": "auto", "heating_system_type": "", "setpoint_mode": "direct"}
    ]
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=35.0,
        settings={},
        has_external_sensor=True,
    )
    _last_commands.clear()
    await ctrl.async_apply("cooling", 24.0, power_fraction=1.0, current_temp=28.0)

    calls = hass.services.async_call.call_args_list
    set_temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert set_temp_calls
    # Direct mode: device receives target (24.0), NOT cool boost (16.0)
    temp_arg = set_temp_calls[0][0][2]["temperature"]
    assert temp_arg == 24.0


@pytest.mark.asyncio
async def test_mixed_setpoint_modes():
    """Room with one proportional TRV and one direct TRV: each gets own setpoint."""
    hass = build_hass()
    room = make_room(thermostats=["climate.trv_prop", "climate.trv_direct"])
    room["devices"] = [
        {
            "entity_id": "climate.trv_prop",
            "type": "trv",
            "role": "auto",
            "heating_system_type": "",
            "setpoint_mode": "proportional",
        },
        {
            "entity_id": "climate.trv_direct",
            "type": "trv",
            "role": "auto",
            "heating_system_type": "",
            "setpoint_mode": "direct",
        },
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
    _last_commands.clear()
    target = 21.0
    current = 19.0
    await ctrl.async_apply("heating", target, power_fraction=0.5, current_temp=current)

    calls = hass.services.async_call.call_args_list
    set_temp_calls = {c[0][2]["entity_id"]: c[0][2]["temperature"] for c in calls if c[0][1] == "set_temperature"}
    # Proportional TRV: 19 + 0.5 * (30 - 19) = 24.5
    assert set_temp_calls["climate.trv_prop"] == 24.5
    # Direct TRV: 21.0 (effective_target)
    assert set_temp_calls["climate.trv_direct"] == target


@pytest.mark.asyncio
async def test_proportional_setpoint_unchanged_default():
    """Regression: default proportional TRV still gets boost, not target."""
    hass = build_hass()
    room = make_room()
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    _last_commands.clear()
    target = 21.0
    current = 19.0
    await ctrl.async_apply("heating", target, power_fraction=1.0, current_temp=current)

    calls = hass.services.async_call.call_args_list
    set_temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert set_temp_calls
    # Default proportional: 19 + 1.0 * (30 - 19) = 30.0 (boost)
    temp_arg = set_temp_calls[0][0][2]["temperature"]
    from custom_components.roommind.control.mpc_controller import HEATING_BOOST_TARGET

    assert temp_arg == HEATING_BOOST_TARGET
