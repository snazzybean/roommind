"""Tests for proportional TRV setpoints, power calculations, AC proportional control, dynamic boost."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.roommind.control.mpc_controller import (
    MPCController,
)
from custom_components.roommind.control.thermal_model import RCModel, RoomModelManager

from .conftest import build_hass, make_room


@pytest.mark.asyncio
async def test_proportional_power_far_from_target():
    """MPC mode, large error → power_fraction near 1.0."""
    hass = build_hass()
    room = make_room()
    model_mgr = RoomModelManager()
    model_mgr.update("living_room", 15.0, 5.0, "heating", 5.0)
    model_mgr.update("living_room", 16.0, 5.0, "heating", 5.0)
    model_mgr.get_prediction_std = MagicMock(return_value=0.1)
    model_mgr.get_mode_counts = MagicMock(return_value=(100, 30, 0))
    # Mock a realistic trained model (2 EKF updates give alpha=_ALPHA_MIN which is
    # too low for the optimizer to distinguish heating from idle via T_eq clamping)
    model_mgr.get_model = MagicMock(return_value=RCModel(C=1.0, U=0.15, Q_heat=3.0, Q_cool=4.0))
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    mode, pf = await ctrl.async_evaluate(current_temp=15.0, target_temp=21.0)
    assert mode == "heating"
    assert pf >= 0.7  # large error → high power


@pytest.mark.asyncio
async def test_proportional_power_near_target():
    """MPC mode, small error → reduced power_fraction."""
    hass = build_hass()
    room = make_room()
    model_mgr = RoomModelManager()
    # Use a known model with moderate Q_heat so a small 0.3°C error yields frac < 1.
    # This tests MPC proportional behavior, not EKF learning.
    model_mgr.get_model = MagicMock(return_value=RCModel(C=1.0, U=0.15, Q_heat=8.0, Q_cool=10.0))
    model_mgr.get_prediction_std = MagicMock(return_value=0.1)
    model_mgr.get_mode_counts = MagicMock(return_value=(100, 40, 0))
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    mode, pf = await ctrl.async_evaluate(current_temp=20.7, target_temp=21.0)
    assert mode is not None
    assert mode == "heating"
    assert pf < 1.0  # near target → less than full power


@pytest.mark.asyncio
async def test_proportional_trv_setpoint():
    """TRV setpoint is proportional between current_temp and 30°C."""
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
    # 50% power at 20°C → TRV = 20 + 0.5*(30-20) = 25°C
    await ctrl.async_apply("heating", 21.0, power_fraction=0.5, current_temp=20.0)
    calls = hass.services.async_call.call_args_list
    set_temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert set_temp_calls
    temp_arg = set_temp_calls[0][0][2]["temperature"]
    assert temp_arg == 25.0


@pytest.mark.asyncio
async def test_proportional_mixed_trv_ac_half_power():
    """Mixed TRV+AC room at 50% power: both get correct proportional targets."""
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
        if eid == "climate.trv":
            return trv_state
        if eid == "climate.ac":
            return ac_state
        return None

    hass.states.get = MagicMock(side_effect=states_get)

    room = make_room(thermostats=["climate.trv"], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0, power_fraction=0.5, current_temp=18.0)

    calls = hass.services.async_call.call_args_list
    # TRV: 18 + 0.5*(30-18) = 24.0
    trv_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2].get("entity_id") == "climate.trv"]
    assert trv_temp and trv_temp[0][0][2]["temperature"] == 24.0
    # AC: 18 + 0.5*(30-18) = 24.0
    ac_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2].get("entity_id") == "climate.ac"]
    assert ac_temp and ac_temp[0][0][2]["temperature"] == 24.0


@pytest.mark.asyncio
async def test_proportional_ac_heating_half_power():
    """AC heating at 50% power gets proportional boost between current and 30°C."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "temperature": 20.0}
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
    await ctrl.async_apply("heating", 21.0, power_fraction=0.5, current_temp=20.0)

    calls = hass.services.async_call.call_args_list
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    # 20 + 0.5*(30-20) = 25.0
    assert any(c[0][2]["temperature"] == 25.0 for c in temp_calls)


@pytest.mark.asyncio
async def test_proportional_ac_cooling_half_power():
    """AC cooling at 50% power gets proportional boost between current and 16°C."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["cool", "off"], "temperature": 23.0}
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
    await ctrl.async_apply("cooling", 23.0, power_fraction=0.5, current_temp=26.0)

    calls = hass.services.async_call.call_args_list
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    # 26 - 0.5*(26-16) = 21.0
    assert any(c[0][2]["temperature"] == 21.0 for c in temp_calls)


@pytest.mark.asyncio
async def test_proportional_ac_heating_clamped_floor():
    """Very low power heating: AC target clamped to effective_target floor."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 20.0}
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
    # Raw: 20.5 + 0.01*(30-20.5) = 20.595 → clamped to max(21.0, 20.6) = 21.0
    await ctrl.async_apply("heating", 21.0, power_fraction=0.01, current_temp=20.5)

    calls = hass.services.async_call.call_args_list
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert any(c[0][2]["temperature"] == 21.0 for c in temp_calls)


@pytest.mark.asyncio
async def test_proportional_ac_cooling_clamped_ceiling():
    """Very low power cooling: AC target clamped to effective_target ceiling."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["cool", "off"], "temperature": 25.0}
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
    # Raw: 23.5 - 0.01*(23.5-16) = 23.425 → clamped to min(23.0, 23.4) = 23.0
    await ctrl.async_apply("cooling", 23.0, power_fraction=0.01, current_temp=23.5)

    calls = hass.services.async_call.call_args_list
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert any(c[0][2]["temperature"] == 23.0 for c in temp_calls)


@pytest.mark.asyncio
async def test_proportional_ac_heating_no_current_temp():
    """AC heating without current_temp falls back to effective_target."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "temperature": 20.0}
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
    await ctrl.async_apply("heating", 21.0, power_fraction=0.8)

    calls = hass.services.async_call.call_args_list
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert any(c[0][2]["temperature"] == 21.0 for c in temp_calls)


@pytest.mark.asyncio
async def test_proportional_ac_cooling_no_current_temp():
    """AC cooling without current_temp falls back to effective_target."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["cool", "off"], "temperature": 25.0}
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
    await ctrl.async_apply("cooling", 23.0, power_fraction=0.8)

    calls = hass.services.async_call.call_args_list
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert any(c[0][2]["temperature"] == 23.0 for c in temp_calls)


@pytest.mark.asyncio
async def test_proportional_ac_managed_mode_unchanged():
    """Managed mode AC gets actual target, NOT proportional boost (regression guard)."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["heat_cool", "heat", "cool", "off"], "temperature": 20.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(
        thermostats=[],
        acs=["climate.ac"],
        climate_mode="auto",
        temperature_sensor="",
    )
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )
    await ctrl.async_apply("heating", 21.0, power_fraction=0.5, current_temp=18.0)

    calls = hass.services.async_call.call_args_list
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    # Managed mode: AC should get actual target (21.0), not proportional boost
    assert any(c[0][2]["temperature"] == 21.0 for c in temp_calls)


# ---------------------------------------------------------------------------
# Dynamic boost target tests (#76)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dynamic_heating_boost_trv_full_power():
    """TRV at full power uses dynamic boost target (35) instead of default 30."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "off"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 20.0, "max_temp": 35.0}
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room(thermostats=["climate.trv"], acs=[])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0, power_fraction=1.0, current_temp=20.0, heating_boost_target=35.0)

    temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert any(c[0][2]["temperature"] == 35.0 for c in temp_calls)


@pytest.mark.asyncio
async def test_dynamic_heating_boost_none_fallback():
    """When heating_boost_target is None, falls back to HEATING_BOOST_TARGET (30)."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "off"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 20.0}
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room(thermostats=["climate.trv"], acs=[])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0, power_fraction=1.0, current_temp=20.0, heating_boost_target=None)

    temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert any(c[0][2]["temperature"] == 30.0 for c in temp_calls)


@pytest.mark.asyncio
async def test_dynamic_heating_boost_proportional():
    """TRV at 50% power with dynamic boost=35: 20 + 0.5*(35-20) = 27.5."""
    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "off"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 20.0, "max_temp": 35.0}
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room(thermostats=["climate.trv"], acs=[])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0, power_fraction=0.5, current_temp=20.0, heating_boost_target=35.0)

    temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert any(c[0][2]["temperature"] == 27.5 for c in temp_calls)


@pytest.mark.asyncio
async def test_dynamic_cooling_boost_full_power():
    """AC at full cooling power uses dynamic boost (18) instead of default 16."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["cool", "off"], "temperature": 23.0, "min_temp": 18.0}
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
    await ctrl.async_apply("cooling", 23.0, power_fraction=1.0, current_temp=26.0, cooling_boost_target=18.0)

    temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert any(c[0][2]["temperature"] == 18.0 for c in temp_calls)


@pytest.mark.asyncio
async def test_dynamic_cooling_boost_none_fallback():
    """When cooling_boost_target is None, falls back to AC_COOLING_BOOST_TARGET (16)."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["cool", "off"], "temperature": 23.0}
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
    await ctrl.async_apply("cooling", 23.0, power_fraction=1.0, current_temp=26.0, cooling_boost_target=None)

    temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    # 26 - 1.0*(26-16) = 16.0
    assert any(c[0][2]["temperature"] == 16.0 for c in temp_calls)


@pytest.mark.asyncio
async def test_dynamic_ac_heating_boost():
    """AC in heating mode uses ac_heating_boost_target instead of default 30."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"
    ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "temperature": 20.0, "max_temp": 28.0}
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
    await ctrl.async_apply("heating", 21.0, power_fraction=1.0, current_temp=20.0, ac_heating_boost_target=28.0)

    temp_calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert any(c[0][2]["temperature"] == 28.0 for c in temp_calls)
