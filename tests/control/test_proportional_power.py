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
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 20.5, "max_temp": 35.0}
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
    assert any(c[0][2]["temperature"] == 34.5 for c in temp_calls)


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
    ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "temperature": 20.5, "max_temp": 28.0}
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
    assert any(c[0][2]["temperature"] == 27.5 for c in temp_calls)


def _ctrl_with_cw(cw):
    hass = build_hass()
    room = make_room()
    settings = {} if cw is None else {"comfort_weight": cw}
    return MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings=settings,
        has_external_sensor=True,
    )


def test_slider_default_and_comfort_keep_approach_rate_one():
    assert _ctrl_with_cw(None)._approach_rate == 1.0  # default cw=70
    assert _ctrl_with_cw(70)._approach_rate == 1.0
    assert _ctrl_with_cw(100)._approach_rate == 1.0


def test_slider_efficiency_lowers_approach_rate():
    assert _ctrl_with_cw(0)._approach_rate == pytest.approx(0.2)
    assert _ctrl_with_cw(35)._approach_rate == pytest.approx(0.6)


def test_slider_default_and_comfort_keep_ac_cap_unbounded():
    assert _ctrl_with_cw(None)._ac_boost_delta == 50.0
    assert _ctrl_with_cw(70)._ac_boost_delta == 50.0
    assert _ctrl_with_cw(100)._ac_boost_delta == 50.0


def test_slider_efficiency_tightens_ac_cap():
    assert _ctrl_with_cw(0)._ac_boost_delta == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_ac_boost_cap_limits_setpoint_at_efficiency():
    """At full efficiency the AC heating setpoint is capped at target + 3°C."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "heat"
    ac_state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 21.0, "min_temp": 16.0, "max_temp": 30.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={"comfort_weight": 0},
        has_external_sensor=True,
    )
    # pf=1.0 would map to boost 30°C; cap must clamp to target(21) + 3 = 24°C
    await ctrl.async_apply("heating", 21.0, power_fraction=1.0, current_temp=18.0)
    set_temp = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert set_temp
    assert set_temp[-1][0][2]["temperature"] == 24.0


@pytest.mark.asyncio
async def test_ac_boost_cap_does_not_apply_at_comfort():
    """At comfort/default the efficiency cap does not bind; the boost is only trimmed one step below max_temp (#396)."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "heat"
    ac_state.attributes = {"hvac_modes": ["heat", "off"], "temperature": 21.5, "min_temp": 16.0, "max_temp": 30.0}
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
    await ctrl.async_apply("heating", 21.0, power_fraction=1.0, current_temp=18.0)
    set_temp = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert set_temp
    assert set_temp[-1][0][2]["temperature"] == 29.5


@pytest.mark.asyncio
async def test_ac_cooling_boost_cap_floors_setpoint_at_efficiency():
    """At full efficiency the AC cooling setpoint is floored at target - 3°C."""
    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "cool"
    ac_state.attributes = {"hvac_modes": ["cool", "off"], "temperature": 23.0, "min_temp": 16.0, "max_temp": 30.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=30.0,
        settings={"comfort_weight": 0},
        has_external_sensor=True,
    )
    # pf=1.0 would map to cool boost 16°C; cap must floor at target(23) - 3 = 20°C
    await ctrl.async_apply("cooling", 23.0, power_fraction=1.0, current_temp=26.0)
    set_temp = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert set_temp
    assert set_temp[-1][0][2]["temperature"] == 20.0


def settings_for(cw):
    return {} if cw is None else {"comfort_weight": cw}


def _make_controller(cw):
    hass = build_hass()
    room = make_room()
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings=settings_for(cw),
        has_external_sensor=True,
    )
    return hass, ctrl


def _mock_device(hass, setpoint):
    dev = MagicMock()
    dev.state = "heat"
    dev.attributes = {"hvac_modes": ["heat", "off"], "temperature": setpoint, "min_temp": 16.0, "max_temp": 30.0}
    hass.states.get = MagicMock(return_value=dev)
    return dev


def test_proportional_deadband_helper_disabled_at_comfort():
    _, ctrl = _make_controller(None)  # cw=70 default
    assert ctrl._proportional_deadband("climate.x", 18.0, 22.0) is None


def test_proportional_deadband_helper_values_at_efficiency():
    from custom_components.roommind.const import (
        PROPORTIONAL_DEADBAND_C,
        PROPORTIONAL_DEADBAND_NEAR_TARGET_C,
    )

    _, ctrl = _make_controller(0)  # full efficiency
    assert ctrl._proportional_deadband("climate.x", 18.0, 22.0) == PROPORTIONAL_DEADBAND_C
    assert ctrl._proportional_deadband("climate.x", 21.5, 22.0) == PROPORTIONAL_DEADBAND_NEAR_TARGET_C


def test_proportional_deadband_helper_none_for_direct_device():
    _, ctrl = _make_controller(0)
    ctrl._direct_eids = {"climate.direct"}
    assert ctrl._proportional_deadband("climate.direct", 18.0, 22.0) is None


def test_proportional_deadband_helper_none_when_current_temp_unknown():
    _, ctrl = _make_controller(0)  # full efficiency
    assert ctrl._proportional_deadband("climate.x", None, 22.0) is None


@pytest.mark.asyncio
async def test_call_deadband_suppresses_subthreshold_change():
    hass, ctrl = _make_controller(0)
    _mock_device(hass, setpoint=22.0)
    await ctrl._call(
        "set_temperature", {"entity_id": "climate.x", "temperature": 22.3}, temp_intent="heat", deadband=0.5
    )
    set_temp = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert set_temp == []  # 0.3 < 0.5 → suppressed


@pytest.mark.asyncio
async def test_call_deadband_sends_suprathreshold_change():
    hass, ctrl = _make_controller(0)
    _mock_device(hass, setpoint=22.0)
    await ctrl._call(
        "set_temperature", {"entity_id": "climate.x", "temperature": 22.6}, temp_intent="heat", deadband=0.5
    )
    set_temp = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert len(set_temp) == 1  # 0.6 >= 0.5 → sent


@pytest.mark.asyncio
async def test_call_without_deadband_preserves_exact_behavior():
    hass, ctrl = _make_controller(None)
    _mock_device(hass, setpoint=22.0)
    await ctrl._call("set_temperature", {"entity_id": "climate.x", "temperature": 22.3}, temp_intent="heat")
    set_temp = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert len(set_temp) == 1  # no deadband → today's behavior: round(22.0,1) != round(22.3,1) → sent


@pytest.mark.asyncio
async def test_call_without_deadband_skips_when_rounds_equal():
    hass, ctrl = _make_controller(None)
    _mock_device(hass, setpoint=22.0)
    await ctrl._call("set_temperature", {"entity_id": "climate.x", "temperature": 22.04}, temp_intent="heat")
    set_temp = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert set_temp == []  # round(22.04,1)==round(22.0,1) → skipped, exactly as before


@pytest.mark.asyncio
async def test_call_deadband_near_target_finer_band():
    hass, ctrl = _make_controller(0)
    _mock_device(hass, setpoint=22.0)
    # 0.3°C change with the finer 0.2 near-target deadband → sent (0.3 >= 0.2)
    await ctrl._call(
        "set_temperature", {"entity_id": "climate.x", "temperature": 22.3}, temp_intent="heat", deadband=0.2
    )
    sent = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert len(sent) == 1
    # 0.15°C change with the 0.2 deadband → suppressed
    hass.services.async_call.reset_mock()
    _mock_device(hass, setpoint=22.0)
    await ctrl._call(
        "set_temperature", {"entity_id": "climate.x", "temperature": 22.15}, temp_intent="heat", deadband=0.2
    )
    sent = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert sent == []


@pytest.mark.asyncio
async def test_call_deadband_converts_to_fahrenheit_units():
    from homeassistant.const import UnitOfTemperature

    hass, ctrl = _make_controller(0)
    hass.config.units.temperature_unit = UnitOfTemperature.FAHRENHEIT
    dev = MagicMock()
    dev.state = "heat"
    dev.attributes = {"hvac_modes": ["heat", "off"], "temperature": 72.0, "min_temp": 60.0, "max_temp": 86.0}
    hass.states.get = MagicMock(return_value=dev)
    # deadband 0.5°C = 0.9°F → a 0.5°F change must be suppressed
    await ctrl._call(
        "set_temperature", {"entity_id": "climate.x", "temperature": 72.5}, temp_intent="heat", deadband=0.5
    )
    sent = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert sent == []
    # a 1.0°F change (>= 0.9°F) must be sent
    hass.services.async_call.reset_mock()
    dev.attributes["temperature"] = 72.0
    await ctrl._call(
        "set_temperature", {"entity_id": "climate.x", "temperature": 73.0}, temp_intent="heat", deadband=0.5
    )
    sent = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]
    assert len(sent) == 1
