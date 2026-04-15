"""Tests for heat source plan application in MPC context."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.roommind.const import TargetTemps
from custom_components.roommind.control.mpc_controller import (
    MODE_HEATING,
    MPCController,
    _last_commands,
)
from custom_components.roommind.control.thermal_model import RoomModelManager

from .conftest import _make_ac_state_for_plan, build_hass, make_room


@pytest.mark.asyncio
async def test_heat_source_plan_excluded_trv_skipped():
    """TRV in heat source plan but also in exclude_eids gets no service calls."""
    from custom_components.roommind.managers.heat_source_orchestrator import (
        DeviceCommand,
        HeatSourcePlan,
    )

    _last_commands.clear()
    hass = build_hass()
    room = make_room(thermostats=["climate.trv1", "climate.trv2"], acs=[])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )

    plan = HeatSourcePlan(
        commands=[
            DeviceCommand(
                entity_id="climate.trv1",
                role="primary",
                device_type="thermostat",
                active=True,
                power_fraction=0.8,
                reason="primary heating",
            ),
            DeviceCommand(
                entity_id="climate.trv2",
                role="primary",
                device_type="thermostat",
                active=True,
                power_fraction=0.8,
                reason="primary heating",
            ),
        ],
        active_sources="primary",
        reason="normal heating",
    )

    # Exclude trv1 (valve protection cycling)
    await ctrl.async_apply(
        mode=MODE_HEATING,
        targets=TargetTemps(heat=21.0, cool=None),
        power_fraction=0.8,
        current_temp=18.0,
        exclude_eids={"climate.trv1"},
        heat_source_plan=plan,
    )

    # Collect all entity_ids that received service calls
    called_eids = set()
    for call in hass.services.async_call.call_args_list:
        # Positional args pattern: async_call(domain, service, data)
        if call.args and len(call.args) >= 3 and isinstance(call.args[2], dict):
            eid = call.args[2].get("entity_id")
            if eid:
                called_eids.add(eid)
        # Keyword args pattern
        if "service_data" in (call.kwargs or {}):
            eid = call.kwargs["service_data"].get("entity_id")
            if eid:
                called_eids.add(eid)

    assert "climate.trv1" not in called_eids, "Excluded TRV should receive no service calls"
    assert "climate.trv2" in called_eids, "Non-excluded TRV should receive service calls"


@pytest.mark.asyncio
async def test_heat_source_plan_active_trv_inactive_ac():
    """Active TRV gets heat mode + proportional temp, inactive AC gets turned off."""
    from custom_components.roommind.managers.heat_source_orchestrator import DeviceCommand, HeatSourcePlan

    _last_commands.clear()
    hass = build_hass()
    room = make_room(thermostats=["climate.trv1"], acs=["climate.ac1"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    plan = HeatSourcePlan(
        commands=[
            DeviceCommand(
                entity_id="climate.trv1",
                role="primary",
                device_type="thermostat",
                active=True,
                power_fraction=0.6,
                reason="test",
            ),
            DeviceCommand(
                entity_id="climate.ac1",
                role="secondary",
                device_type="ac",
                active=False,
                power_fraction=0.0,
                reason="test",
            ),
        ],
        active_sources="primary",
        reason="test",
    )
    # current=20, target=21, boost=30 -> trv = 20 + 0.6*(30-20) = 26.0
    await ctrl.async_apply(
        mode=MODE_HEATING,
        targets=TargetTemps(heat=21.0, cool=None),
        power_fraction=0.6,
        current_temp=20.0,
        heat_source_plan=plan,
    )

    calls = hass.services.async_call.call_args_list

    # TRV: heat mode + proportional temp
    trv_mode = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.trv1"]
    assert len(trv_mode) == 1
    assert trv_mode[0][0][2]["hvac_mode"] == "heat"

    trv_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == "climate.trv1"]
    assert len(trv_temp) == 1
    assert trv_temp[0][0][2]["temperature"] == 26.0

    # Inactive AC: turned off
    ac_mode = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.ac1"]
    assert len(ac_mode) == 1
    assert ac_mode[0][0][2]["hvac_mode"] == "off"

    # No temperature call for inactive AC
    ac_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2].get("entity_id") == "climate.ac1"]
    assert len(ac_temp) == 0


@pytest.mark.asyncio
async def test_heat_source_plan_active_ac_inactive_trv():
    """Active AC gets heat + proportional temp, inactive TRV is idled via async_idle_device (#168)."""
    from custom_components.roommind.managers.heat_source_orchestrator import DeviceCommand, HeatSourcePlan

    _last_commands.clear()
    hass = build_hass()
    # AC currently in "off" so setting to "heat" is not redundant
    ac_state = _make_ac_state_for_plan(["heat", "cool", "off"], current_state="off")
    trv_state = MagicMock()
    # Previous cycle left the TRV heating -> idle action must turn it off
    trv_state.state = "heat"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0, "max_temp": 30.0, "temperature": None}

    def _states_get(eid):
        if eid == "climate.ac1":
            return ac_state
        if eid == "climate.trv1":
            return trv_state
        return None

    hass.states.get = MagicMock(side_effect=_states_get)

    room = make_room(thermostats=["climate.trv1"], acs=["climate.ac1"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    plan = HeatSourcePlan(
        commands=[
            DeviceCommand(
                entity_id="climate.trv1",
                role="primary",
                device_type="thermostat",
                active=False,
                power_fraction=0.0,
                reason="test",
            ),
            DeviceCommand(
                entity_id="climate.ac1",
                role="secondary",
                device_type="ac",
                active=True,
                power_fraction=0.8,
                reason="test",
            ),
        ],
        active_sources="secondary",
        reason="test",
    )
    # current=19, target=21, ac_boost=30 -> ac = 19 + 0.8*(30-19) = 27.8
    await ctrl.async_apply(
        mode=MODE_HEATING,
        targets=TargetTemps(heat=21.0, cool=None),
        power_fraction=0.8,
        current_temp=19.0,
        heat_source_plan=plan,
    )

    calls = hass.services.async_call.call_args_list

    # Inactive TRV: idled via async_idle_device (default idle_action=off).
    # With min_temp=5.0 exposed, async_turn_off_climate lowers the setpoint
    # defense-in-depth BEFORE sending set_hvac_mode(off).
    trv_mode = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.trv1"]
    assert len(trv_mode) == 1
    assert trv_mode[0][0][2]["hvac_mode"] == "off"

    trv_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2].get("entity_id") == "climate.trv1"]
    assert len(trv_temp) == 1
    assert trv_temp[0][0][2]["temperature"] == 5.0  # min_temp, not current_temp

    # Active AC: heat mode + proportional temp
    ac_mode = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.ac1"]
    assert len(ac_mode) == 1
    assert ac_mode[0][0][2]["hvac_mode"] == "heat"

    ac_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == "climate.ac1"]
    assert len(ac_temp) == 1
    assert ac_temp[0][0][2]["temperature"] == 27.8


@pytest.mark.asyncio
async def test_heat_source_plan_inactive_trv_already_off_is_noop():
    """When the TRV is already off, no service calls are issued (redundancy check)."""
    from custom_components.roommind.managers.heat_source_orchestrator import DeviceCommand, HeatSourcePlan

    _last_commands.clear()
    hass = build_hass()
    ac_state = _make_ac_state_for_plan(["heat", "cool", "off"], current_state="off")
    trv_state = MagicMock()
    trv_state.state = "off"  # already idled
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0, "max_temp": 30.0, "temperature": 5.0}

    def _states_get(eid):
        if eid == "climate.ac1":
            return ac_state
        if eid == "climate.trv1":
            return trv_state
        return None

    hass.states.get = MagicMock(side_effect=_states_get)

    room = make_room(thermostats=["climate.trv1"], acs=["climate.ac1"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    plan = HeatSourcePlan(
        commands=[
            DeviceCommand(
                entity_id="climate.trv1",
                role="primary",
                device_type="thermostat",
                active=False,
                power_fraction=0.0,
                reason="test",
            ),
            DeviceCommand(
                entity_id="climate.ac1",
                role="secondary",
                device_type="ac",
                active=True,
                power_fraction=0.8,
                reason="test",
            ),
        ],
        active_sources="secondary",
        reason="test",
    )
    await ctrl.async_apply(
        mode=MODE_HEATING,
        targets=TargetTemps(heat=21.0, cool=None),
        power_fraction=0.8,
        current_temp=19.0,
        heat_source_plan=plan,
    )

    calls = hass.services.async_call.call_args_list
    trv_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.trv1"]
    # TRV already in "off" -> async_turn_off_climate short-circuits.
    assert len(trv_calls) == 0


@pytest.mark.asyncio
async def test_heat_source_plan_inactive_trv_with_setback():
    """When idle_action=setback, inactive TRV stays in heat with reduced setpoint."""
    from custom_components.roommind.managers.heat_source_orchestrator import DeviceCommand, HeatSourcePlan

    _last_commands.clear()
    hass = build_hass()
    ac_state = _make_ac_state_for_plan(["heat", "cool", "off"], current_state="off")
    trv_state = MagicMock()
    trv_state.state = "heat"
    trv_state.attributes = {
        "hvac_modes": ["heat", "off"],
        "min_temp": 5.0,
        "max_temp": 30.0,
        "temperature": 21.0,
    }

    def _states_get(eid):
        if eid == "climate.ac1":
            return ac_state
        if eid == "climate.trv1":
            return trv_state
        return None

    hass.states.get = MagicMock(side_effect=_states_get)

    room = make_room(thermostats=["climate.trv1"], acs=["climate.ac1"])
    # Override TRV device to use setback idle action
    for d in room["devices"]:
        if d["entity_id"] == "climate.trv1":
            d["idle_action"] = "setback"

    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    plan = HeatSourcePlan(
        commands=[
            DeviceCommand(
                entity_id="climate.trv1",
                role="primary",
                device_type="thermostat",
                active=False,
                power_fraction=0.0,
                reason="test",
            ),
            DeviceCommand(
                entity_id="climate.ac1",
                role="secondary",
                device_type="ac",
                active=True,
                power_fraction=0.8,
                reason="test",
            ),
        ],
        active_sources="secondary",
        reason="test",
    )
    await ctrl.async_apply(
        mode=MODE_HEATING,
        targets=TargetTemps(heat=21.0, cool=None),
        power_fraction=0.8,
        current_temp=19.0,
        heat_source_plan=plan,
    )

    calls = hass.services.async_call.call_args_list

    # Setback branch: keeps hvac_mode=heat, shifts setpoint by DEFAULT_IDLE_SETBACK_OFFSET (2.0)
    trv_mode = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.trv1"]
    assert len(trv_mode) == 0  # no hvac_mode change in setback

    trv_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2].get("entity_id") == "climate.trv1"]
    assert len(trv_temp) == 1
    assert trv_temp[0][0][2]["temperature"] == 19.0  # 21.0 - 2.0


@pytest.mark.asyncio
async def test_heat_source_plan_both_active_different_fractions():
    """Both devices active with different power fractions get correct proportional temps."""
    from custom_components.roommind.managers.heat_source_orchestrator import DeviceCommand, HeatSourcePlan

    _last_commands.clear()
    hass = build_hass()
    ac_state = _make_ac_state_for_plan(["heat", "cool", "off"])
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=["climate.trv1"], acs=["climate.ac1"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    plan = HeatSourcePlan(
        commands=[
            DeviceCommand(
                entity_id="climate.trv1",
                role="primary",
                device_type="thermostat",
                active=True,
                power_fraction=1.0,
                reason="test",
            ),
            DeviceCommand(
                entity_id="climate.ac1",
                role="secondary",
                device_type="ac",
                active=True,
                power_fraction=0.5,
                reason="test",
            ),
        ],
        active_sources="both",
        reason="test",
    )
    # current=20, trv_boost=30: trv = 20 + 1.0*(30-20) = 30.0
    # current=20, ac_boost=30:  ac  = 20 + 0.5*(30-20) = 25.0
    await ctrl.async_apply(
        mode=MODE_HEATING,
        targets=TargetTemps(heat=21.0, cool=None),
        power_fraction=1.0,
        current_temp=20.0,
        heat_source_plan=plan,
    )

    calls = hass.services.async_call.call_args_list

    trv_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == "climate.trv1"]
    assert len(trv_temp) == 1
    assert trv_temp[0][0][2]["temperature"] == 30.0

    ac_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == "climate.ac1"]
    assert len(ac_temp) == 1
    assert ac_temp[0][0][2]["temperature"] == 25.0


@pytest.mark.asyncio
async def test_heat_source_plan_excluded_eid_skipped():
    """Excluded EID in plan commands is skipped entirely (no service calls)."""
    from custom_components.roommind.managers.heat_source_orchestrator import DeviceCommand, HeatSourcePlan

    _last_commands.clear()
    hass = build_hass()
    room = make_room(thermostats=["climate.trv1", "climate.trv2"], acs=[])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    plan = HeatSourcePlan(
        commands=[
            DeviceCommand(
                entity_id="climate.trv1",
                role="primary",
                device_type="thermostat",
                active=True,
                power_fraction=0.7,
                reason="test",
            ),
            DeviceCommand(
                entity_id="climate.trv2",
                role="primary",
                device_type="thermostat",
                active=True,
                power_fraction=0.7,
                reason="test",
            ),
        ],
        active_sources="primary",
        reason="test",
    )
    await ctrl.async_apply(
        mode=MODE_HEATING,
        targets=TargetTemps(heat=21.0, cool=None),
        power_fraction=0.7,
        current_temp=20.0,
        exclude_eids={"climate.trv2"},
        heat_source_plan=plan,
    )

    calls = hass.services.async_call.call_args_list
    trv1_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.trv1"]
    assert len(trv1_calls) == 2  # set_hvac_mode + set_temperature

    trv2_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.trv2"]
    assert len(trv2_calls) == 0


@pytest.mark.asyncio
async def test_heat_source_plan_ac_cool_only_gets_off():
    """AC with only 'cool' in hvac_modes gets turned off when active in heating plan."""
    from custom_components.roommind.managers.heat_source_orchestrator import DeviceCommand, HeatSourcePlan

    _last_commands.clear()
    hass = build_hass()
    ac_state = _make_ac_state_for_plan(["cool", "off"])
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac1"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    plan = HeatSourcePlan(
        commands=[
            DeviceCommand(
                entity_id="climate.ac1",
                role="secondary",
                device_type="ac",
                active=True,
                power_fraction=0.8,
                reason="test",
            ),
        ],
        active_sources="secondary",
        reason="test",
    )
    await ctrl.async_apply(
        mode=MODE_HEATING,
        targets=TargetTemps(heat=21.0, cool=None),
        power_fraction=0.8,
        current_temp=20.0,
        heat_source_plan=plan,
    )

    calls = hass.services.async_call.call_args_list
    ac_mode = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.ac1"]
    assert len(ac_mode) == 1
    assert ac_mode[0][0][2]["hvac_mode"] == "off"

    # Defense-in-depth: AC also gets set_temperature(min_temp) when turned off
    ac_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2].get("entity_id") == "climate.ac1"]
    assert len(ac_temp) == 1
    assert ac_temp[0][0][2]["temperature"] == 5.0


@pytest.mark.asyncio
async def test_heat_source_plan_ac_heat_cool_mode():
    """AC with 'heat_cool' but no 'heat' uses heat_cool hvac_mode."""
    from custom_components.roommind.managers.heat_source_orchestrator import DeviceCommand, HeatSourcePlan

    _last_commands.clear()
    hass = build_hass()
    ac_state = _make_ac_state_for_plan(["heat_cool", "cool", "off"])
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac1"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    plan = HeatSourcePlan(
        commands=[
            DeviceCommand(
                entity_id="climate.ac1",
                role="secondary",
                device_type="ac",
                active=True,
                power_fraction=0.5,
                reason="test",
            ),
        ],
        active_sources="secondary",
        reason="test",
    )
    # current=20, ac_boost=30 -> 20 + 0.5*(30-20) = 25.0
    await ctrl.async_apply(
        mode=MODE_HEATING,
        targets=TargetTemps(heat=21.0, cool=None),
        power_fraction=0.5,
        current_temp=20.0,
        heat_source_plan=plan,
    )

    calls = hass.services.async_call.call_args_list
    ac_mode = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.ac1"]
    assert len(ac_mode) == 1
    assert ac_mode[0][0][2]["hvac_mode"] == "heat_cool"

    ac_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == "climate.ac1"]
    assert len(ac_temp) == 1
    assert ac_temp[0][0][2]["temperature"] == 25.0


@pytest.mark.asyncio
async def test_heat_source_plan_managed_mode_no_external_sensor():
    """Managed mode (no external sensor, heat_only): TRV and AC both get effective_target."""
    from custom_components.roommind.managers.heat_source_orchestrator import DeviceCommand, HeatSourcePlan

    _last_commands.clear()
    hass = build_hass()
    # AC currently in "off" so setting to "heat" is not redundant
    ac_state = _make_ac_state_for_plan(["heat", "cool", "off"], current_state="off")
    trv_state = MagicMock()
    trv_state.state = "off"
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0, "max_temp": 30.0, "temperature": None}

    def _states_get(eid):
        if eid == "climate.ac1":
            return ac_state
        if eid == "climate.trv1":
            return trv_state
        return None

    hass.states.get = MagicMock(side_effect=_states_get)

    # Use heat_only to bypass managed auto block (which returns early for auto mode)
    room = make_room(
        thermostats=["climate.trv1"],
        acs=["climate.ac1"],
        temperature_sensor="",
        climate_mode="heat_only",
    )
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )
    plan = HeatSourcePlan(
        commands=[
            DeviceCommand(
                entity_id="climate.trv1",
                role="primary",
                device_type="thermostat",
                active=True,
                power_fraction=0.7,
                reason="test",
            ),
            DeviceCommand(
                entity_id="climate.ac1",
                role="secondary",
                device_type="ac",
                active=True,
                power_fraction=0.5,
                reason="test",
            ),
        ],
        active_sources="both",
        reason="test",
    )
    # has_external_sensor=False: TRV gets effective_target (21.0), AC gets effective_target (21.0)
    await ctrl.async_apply(
        mode=MODE_HEATING,
        targets=TargetTemps(heat=21.0, cool=None),
        power_fraction=0.7,
        current_temp=None,
        heat_source_plan=plan,
    )

    calls = hass.services.async_call.call_args_list

    # TRV: heat mode + effective_target
    trv_mode = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.trv1"]
    assert len(trv_mode) == 1
    assert trv_mode[0][0][2]["hvac_mode"] == "heat"

    trv_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == "climate.trv1"]
    assert len(trv_temp) == 1
    assert trv_temp[0][0][2]["temperature"] == 21.0

    # AC: heat mode + effective_target
    ac_mode = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2]["entity_id"] == "climate.ac1"]
    assert len(ac_mode) == 1
    assert ac_mode[0][0][2]["hvac_mode"] == "heat"

    ac_temp = [c for c in calls if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == "climate.ac1"]
    assert len(ac_temp) == 1
    assert ac_temp[0][0][2]["temperature"] == 21.0


# ---------------------------------------------------------------------------
# Orchestrated forced_on / forced_off with heat source plan
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_orchestrated_forced_on_overrides_inactive():
    """Forced_on overrides orchestrator marking device as inactive."""
    from custom_components.roommind.managers.heat_source_orchestrator import (
        DeviceCommand,
        HeatSourcePlan,
    )

    hass = build_hass()
    trv_state = MagicMock()
    trv_state.state = "off"  # device was off, forced_on should activate it
    trv_state.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0}
    hass.states.get = MagicMock(return_value=trv_state)

    room = make_room()
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={"heat_source_orchestration": True},
        has_external_sensor=True,
    )
    plan = HeatSourcePlan(
        commands=[
            DeviceCommand(
                entity_id="climate.living_trv",
                role="primary",
                device_type="thermostat",
                active=False,  # orchestrator says inactive
                power_fraction=0.0,
                reason="test",
            ),
        ],
        active_sources="none",
        reason="test",
    )
    await ctrl.async_apply(
        "heating",
        TargetTemps(heat=21.0, cool=24.0),
        heat_source_plan=plan,
        compressor_forced_on={"climate.living_trv"},
    )
    # forced_on should set device to heat at target temp, not turn off
    calls = hass.services.async_call.call_args_list
    off_calls = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.living_trv"
        and c[0][1] == "set_hvac_mode"
        and c[0][2].get("hvac_mode") == "off"
    ]
    assert len(off_calls) == 0
    # set_hvac_mode("heat") and set_temperature called
    heat_calls = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.living_trv"
        and c[0][1] == "set_hvac_mode"
        and c[0][2].get("hvac_mode") == "heat"
    ]
    assert len(heat_calls) == 1
    temp_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.living_trv" and c[0][1] == "set_temperature"]
    assert len(temp_calls) == 1
    assert temp_calls[0][0][2]["temperature"] == 21.0


@pytest.mark.asyncio
async def test_apply_orchestrated_forced_off_overrides_active():
    """Forced_off overrides orchestrator marking device as active."""
    from custom_components.roommind.managers.heat_source_orchestrator import (
        DeviceCommand,
        HeatSourcePlan,
    )

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
        settings={"heat_source_orchestration": True},
        has_external_sensor=True,
    )
    plan = HeatSourcePlan(
        commands=[
            DeviceCommand(
                entity_id="climate.living_trv",
                role="primary",
                device_type="thermostat",
                active=True,  # orchestrator says active
                power_fraction=1.0,
                reason="test",
            ),
        ],
        active_sources="primary",
        reason="test",
    )
    await ctrl.async_apply(
        "heating",
        TargetTemps(heat=21.0, cool=24.0),
        heat_source_plan=plan,
        compressor_forced_off={"climate.living_trv"},
    )
    # forced_off should turn off the device despite orchestrator saying active
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
async def test_apply_orchestrated_forced_on_ac():
    """Orchestrated forced_on AC gets heat mode + heat target."""
    from custom_components.roommind.managers.heat_source_orchestrator import (
        DeviceCommand,
        HeatSourcePlan,
    )

    hass = build_hass()
    ac_state = MagicMock()
    ac_state.state = "off"  # device was off, forced_on should activate it
    ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "min_temp": 16.0}
    hass.states.get = MagicMock(return_value=ac_state)

    room = make_room(thermostats=[], acs=["climate.ac"])
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={"heat_source_orchestration": True},
        has_external_sensor=True,
    )
    plan = HeatSourcePlan(
        commands=[
            DeviceCommand(
                entity_id="climate.ac",
                role="primary",
                device_type="ac",
                active=False,
                power_fraction=0.0,
                reason="test",
            ),
        ],
        active_sources="none",
        reason="test",
    )
    await ctrl.async_apply(
        "heating",
        TargetTemps(heat=21.0, cool=24.0),
        heat_source_plan=plan,
        compressor_forced_on={"climate.ac"},
    )
    calls = hass.services.async_call.call_args_list
    heat_calls = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.ac"
        and c[0][1] == "set_hvac_mode"
        and c[0][2].get("hvac_mode") == "heat"
    ]
    assert len(heat_calls) == 1
    temp_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.ac" and c[0][1] == "set_temperature"]
    assert len(temp_calls) == 1
    assert temp_calls[0][0][2]["temperature"] == 21.0


@pytest.mark.asyncio
async def test_hso_direct_setpoint_trv():
    """Active TRV with setpoint_mode='direct' in HSO receives target, not boost."""
    from custom_components.roommind.managers.heat_source_orchestrator import (
        DeviceCommand,
        HeatSourcePlan,
    )

    _last_commands.clear()
    hass = build_hass()
    room = make_room(thermostats=["climate.trv_direct"], acs=[])
    room["devices"] = [
        {
            "entity_id": "climate.trv_direct",
            "type": "trv",
            "role": "auto",
            "heating_system_type": "",
            "setpoint_mode": "direct",
        },
    ]
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )

    plan = HeatSourcePlan(
        commands=[
            DeviceCommand(
                entity_id="climate.trv_direct",
                role="primary",
                device_type="thermostat",
                active=True,
                power_fraction=1.0,
                reason="primary heating",
            ),
        ],
        active_sources="primary",
        reason="normal heating",
    )

    await ctrl.async_apply(
        mode=MODE_HEATING,
        targets=TargetTemps(heat=21.0, cool=None),
        power_fraction=1.0,
        current_temp=18.0,
        heat_source_plan=plan,
    )

    calls = hass.services.async_call.call_args_list
    temp_calls = [c for c in calls if c[0][2].get("entity_id") == "climate.trv_direct" and c[0][1] == "set_temperature"]
    assert len(temp_calls) == 1
    # Direct mode: receives target 21.0, NOT proportional boost (18 + 1.0*(30-18)=30)
    assert temp_calls[0][0][2]["temperature"] == 21.0
