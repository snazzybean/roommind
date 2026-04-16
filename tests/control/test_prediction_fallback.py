"""Tests for bang-bang logic, stickiness, deadband, min_run, split targets, managed mode capability gating."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from custom_components.roommind.const import TargetTemps
from custom_components.roommind.control.mpc_controller import (
    MODE_COOLING,
    MODE_HEATING,
    MODE_IDLE,
    MPCController,
    check_acs_can_heat,
    get_can_heat_cool,
)
from custom_components.roommind.control.thermal_model import RoomModelManager

from .conftest import build_hass, make_room


@pytest.mark.asyncio
async def test_mpc_fallback_to_bangbang():
    """Low confidence = bang-bang: 0.1°C below target, within 0.2°C hysteresis → idle."""
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
    mode, pf = await ctrl.async_evaluate(current_temp=20.9, target_temp=21.0)
    assert mode == "idle"
    assert pf == 0.0


@pytest.mark.asyncio
async def test_bangbang_returns_full_power():
    """Bang-bang fallback → power_fraction = 1.0 for heating."""
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
    # Large error in bang-bang mode (low confidence)
    mode, pf = await ctrl.async_evaluate(current_temp=17.0, target_temp=21.0)
    assert mode == "heating"
    assert pf == 1.0  # bang-bang: always full power


# ---------------------------------------------------------------------------
# get_can_heat_cool unit tests
# ---------------------------------------------------------------------------


class TestGetCanHeatCool:
    """Unit tests for get_can_heat_cool."""

    def test_auto_mode_with_both_devices(self):
        """auto mode with thermostats and ACs → (True, True)."""
        room = make_room(climate_mode="auto", acs=["climate.ac"])
        can_heat, can_cool = get_can_heat_cool(room)
        assert can_heat is True
        assert can_cool is True

    def test_heat_only_mode(self):
        """heat_only mode → (True, False) regardless of ACs."""
        room = make_room(climate_mode="heat_only", acs=["climate.ac"])
        can_heat, can_cool = get_can_heat_cool(room)
        assert can_heat is True
        assert can_cool is False

    def test_cool_only_mode(self):
        """cool_only mode → (False, True) regardless of thermostats."""
        room = make_room(climate_mode="cool_only", acs=["climate.ac"])
        can_heat, can_cool = get_can_heat_cool(room)
        assert can_heat is False
        assert can_cool is True

    def test_no_thermostats_heat_only(self):
        """heat_only but no thermostats → (False, False)."""
        room = make_room(climate_mode="heat_only", thermostats=[], acs=[])
        can_heat, can_cool = get_can_heat_cool(room)
        assert can_heat is False
        assert can_cool is False

    def test_no_acs_cool_only(self):
        """cool_only but no ACs → (False, False)."""
        room = make_room(climate_mode="cool_only", thermostats=[], acs=[])
        can_heat, can_cool = get_can_heat_cool(room)
        assert can_heat is False
        assert can_cool is False

    def test_outdoor_temp_none_no_gating(self):
        """outdoor_temp=None → no gating applied."""
        room = make_room(acs=["climate.ac"])
        can_heat, can_cool = get_can_heat_cool(room, outdoor_temp=None)
        assert can_heat is True
        assert can_cool is True

    def test_outdoor_above_heating_max_blocks_heat(self):
        """Outdoor temp above outdoor_heating_max → can_heat=False."""
        room = make_room(acs=["climate.ac"])
        can_heat, can_cool = get_can_heat_cool(
            room,
            outdoor_temp=25.0,
            outdoor_heating_max=22.0,
        )
        assert can_heat is False
        assert can_cool is True

    def test_outdoor_below_cooling_min_blocks_cool(self):
        """Outdoor temp below outdoor_cooling_min → can_cool=False."""
        room = make_room(acs=["climate.ac"])
        can_heat, can_cool = get_can_heat_cool(
            room,
            outdoor_temp=10.0,
            outdoor_cooling_min=16.0,
        )
        assert can_heat is True
        assert can_cool is False

    def test_outdoor_at_threshold_boundary(self):
        """Outdoor temp equal to heating_max → not blocked (>= not used, > is)."""
        room = make_room(acs=["climate.ac"])
        # At exactly outdoor_heating_max=22.0 → 22 > 22 is False, so still allowed
        can_heat, can_cool = get_can_heat_cool(
            room,
            outdoor_temp=22.0,
            outdoor_heating_max=22.0,
        )
        assert can_heat is True
        # At exactly outdoor_cooling_min=16.0 → 16 < 16 is False, so still allowed
        can_heat2, can_cool2 = get_can_heat_cool(
            room,
            outdoor_temp=16.0,
            outdoor_cooling_min=16.0,
        )
        assert can_cool2 is True

    def test_auto_no_devices_returns_false_false(self):
        """auto mode but no devices → (False, False)."""
        room = make_room(climate_mode="auto", thermostats=[], acs=[])
        can_heat, can_cool = get_can_heat_cool(room)
        assert can_heat is False
        assert can_cool is False

    def test_override_bypasses_cooling_gate(self):
        """Override active → outdoor cooling gate bypassed."""
        room = make_room(acs=["climate.ac"])
        can_heat, can_cool = get_can_heat_cool(
            room,
            outdoor_temp=10.0,
            outdoor_cooling_min=16.0,
            override_active=True,
        )
        assert can_cool is True

    def test_override_bypasses_heating_gate(self):
        """Override active → outdoor heating gate bypassed."""
        room = make_room(acs=["climate.ac"])
        can_heat, can_cool = get_can_heat_cool(
            room,
            outdoor_temp=25.0,
            outdoor_heating_max=22.0,
            override_active=True,
        )
        assert can_heat is True

    def test_override_false_still_gates(self):
        """Override not active → outdoor gate still applies."""
        room = make_room(acs=["climate.ac"])
        can_heat, can_cool = get_can_heat_cool(
            room,
            outdoor_temp=10.0,
            outdoor_cooling_min=16.0,
            override_active=False,
        )
        assert can_cool is False


# ---------------------------------------------------------------------------
# check_acs_can_heat unit tests
# ---------------------------------------------------------------------------


class TestCheckAcsCanHeat:
    """Unit tests for check_acs_can_heat."""

    def test_ac_with_heat_mode(self):
        """AC with 'heat' in hvac_modes → True."""
        hass = build_hass()
        state = MagicMock()
        state.attributes = {"hvac_modes": ["heat", "cool", "off"]}
        hass.states.get = MagicMock(return_value=state)
        room = make_room(thermostats=[], acs=["climate.hp"])
        assert check_acs_can_heat(hass, room) is True

    def test_ac_with_heat_cool_mode(self):
        """AC with 'heat_cool' in hvac_modes → True."""
        hass = build_hass()
        state = MagicMock()
        state.attributes = {"hvac_modes": ["heat_cool", "off"]}
        hass.states.get = MagicMock(return_value=state)
        room = make_room(thermostats=[], acs=["climate.hp"])
        assert check_acs_can_heat(hass, room) is True

    def test_ac_cool_only(self):
        """AC with only 'cool' → False."""
        hass = build_hass()
        state = MagicMock()
        state.attributes = {"hvac_modes": ["cool", "off"]}
        hass.states.get = MagicMock(return_value=state)
        room = make_room(thermostats=[], acs=["climate.ac"])
        assert check_acs_can_heat(hass, room) is False

    def test_no_acs(self):
        """No ACs → False."""
        hass = build_hass()
        room = make_room(thermostats=["climate.trv"], acs=[])
        assert check_acs_can_heat(hass, room) is False

    def test_ac_state_unavailable(self):
        """AC entity not found → False."""
        hass = build_hass()
        hass.states.get = MagicMock(return_value=None)
        room = make_room(thermostats=[], acs=["climate.hp"])
        assert check_acs_can_heat(hass, room) is False

    def test_ac_off_unreliable_modes(self):
        """AC off with only 'off'+'fan_only' → True (unreliable modes, #100)."""
        hass = build_hass()
        state = MagicMock()
        state.state = "off"
        state.attributes = {"hvac_modes": ["off", "fan_only"]}
        hass.states.get = MagicMock(return_value=state)
        room = make_room(thermostats=[], acs=["climate.ac"])
        assert check_acs_can_heat(hass, room) is True

    def test_ac_off_reliable_no_heat(self):
        """AC off with reliable modes (cool only) → False."""
        hass = build_hass()
        state = MagicMock()
        state.state = "off"
        state.attributes = {"hvac_modes": ["off", "cool"]}
        hass.states.get = MagicMock(return_value=state)
        room = make_room(thermostats=[], acs=["climate.ac"])
        assert check_acs_can_heat(hass, room) is False

    def test_ac_fan_only_unreliable_modes(self):
        """AC in fan_only with no active modes uses assumed modes (#100)."""
        hass = build_hass()
        state = MagicMock()
        state.state = "fan_only"
        state.attributes = {"hvac_modes": ["off", "fan_only"]}
        hass.states.get = MagicMock(return_value=state)
        room = make_room(thermostats=[], acs=["climate.ac"])
        assert check_acs_can_heat(hass, room) is True


# ---------------------------------------------------------------------------
# get_can_heat_cool with acs_can_heat
# ---------------------------------------------------------------------------


class TestGetCanHeatCoolAcsCanHeat:
    """Tests for get_can_heat_cool with acs_can_heat parameter."""

    def test_acs_can_heat_no_thermostats(self):
        """acs_can_heat=True allows heating even without thermostats."""
        room = make_room(thermostats=[], acs=["climate.hp"])
        can_heat, can_cool = get_can_heat_cool(room, acs_can_heat=True)
        assert can_heat is True
        assert can_cool is True

    def test_acs_can_heat_cool_only_mode(self):
        """acs_can_heat=True but cool_only mode → can_heat still False."""
        room = make_room(climate_mode="cool_only", thermostats=[], acs=["climate.hp"])
        can_heat, can_cool = get_can_heat_cool(room, acs_can_heat=True)
        assert can_heat is False
        assert can_cool is True

    def test_acs_can_heat_with_outdoor_gating(self):
        """acs_can_heat=True but outdoor above heating max → can_heat gated."""
        room = make_room(thermostats=[], acs=["climate.hp"])
        can_heat, can_cool = get_can_heat_cool(
            room,
            outdoor_temp=25.0,
            outdoor_heating_max=22.0,
            acs_can_heat=True,
        )
        assert can_heat is False

    def test_default_acs_can_heat_false(self):
        """Default acs_can_heat=False preserves old behavior."""
        room = make_room(thermostats=[], acs=["climate.hp"])
        can_heat, can_cool = get_can_heat_cool(room)
        assert can_heat is False
        assert can_cool is True


def test_acs_can_heat_auto_mode():
    """AC with only 'off'+'auto' hvac_modes is recognized as heat-capable."""
    hass = build_hass()
    state = MagicMock()
    state.attributes = {"hvac_modes": ["off", "auto"]}
    hass.states.get = MagicMock(return_value=state)
    assert (
        check_acs_can_heat(
            hass,
            {
                "acs": ["climate.ac1"],
                "devices": [{"entity_id": "climate.ac1", "type": "ac", "role": "auto", "heating_system_type": ""}],
            },
        )
        is True
    )


# ---------------------------------------------------------------------------
# _evaluate_bangbang hysteresis
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bangbang_heating_stickiness():
    """In heating mode, stays heating until at target."""
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
    ctrl.previous_mode = MODE_HEATING
    mode = ctrl._evaluate_bangbang(20.0, TargetTemps(heat=21.0, cool=24.0))
    assert mode == MODE_HEATING


@pytest.mark.asyncio
async def test_bangbang_heating_reaches_target():
    """In heating mode, switches to idle at target."""
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
    ctrl.previous_mode = MODE_HEATING
    mode = ctrl._evaluate_bangbang(21.5, TargetTemps(heat=21.0, cool=24.0))
    assert mode == MODE_IDLE


@pytest.mark.asyncio
async def test_bangbang_cooling_stickiness():
    """In cooling mode, stays cooling until at target."""
    hass = build_hass()
    room = make_room(acs=["climate.ac1"], climate_mode="cool_only")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    ctrl.previous_mode = MODE_COOLING
    mode = ctrl._evaluate_bangbang(25.0, TargetTemps(heat=21.0, cool=23.0))
    assert mode == MODE_COOLING


@pytest.mark.asyncio
async def test_bangbang_cooling_reaches_target():
    """In cooling mode, switches to idle at target."""
    hass = build_hass()
    room = make_room(acs=["climate.ac1"], climate_mode="cool_only")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    ctrl.previous_mode = MODE_COOLING
    mode = ctrl._evaluate_bangbang(22.5, TargetTemps(heat=21.0, cool=23.0))
    assert mode == MODE_IDLE


@pytest.mark.asyncio
async def test_bangbang_idle_to_heating():
    """From idle, starts heating below threshold."""
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
    ctrl.previous_mode = MODE_IDLE
    mode = ctrl._evaluate_bangbang(20.0, TargetTemps(heat=21.0, cool=24.0))
    assert mode == MODE_HEATING


@pytest.mark.asyncio
async def test_bangbang_idle_to_cooling():
    """From idle, starts cooling above threshold."""
    hass = build_hass()
    room = make_room(acs=["climate.ac1"], climate_mode="cool_only")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    ctrl.previous_mode = MODE_IDLE
    mode = ctrl._evaluate_bangbang(24.0, TargetTemps(heat=21.0, cool=23.0))
    assert mode == MODE_COOLING


@pytest.mark.asyncio
async def test_bangbang_idle_deadband():
    """Within deadband from idle, stays idle."""
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
    ctrl.previous_mode = MODE_IDLE
    mode = ctrl._evaluate_bangbang(20.9, TargetTemps(heat=21.0, cool=24.0))
    assert mode == MODE_IDLE


@pytest.mark.asyncio
async def test_bangbang_none_inputs():
    """None inputs return idle."""
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
    assert ctrl._evaluate_bangbang(None, TargetTemps(heat=21.0, cool=24.0)) == MODE_IDLE
    assert ctrl._evaluate_bangbang(20.0, TargetTemps(heat=None, cool=None)) == MODE_IDLE


@pytest.mark.asyncio
async def test_bangbang_heating_min_run_holds_at_target():
    """Underfloor heating must keep running when at target but within min-run window."""
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
        previous_mode=MODE_HEATING,
        heating_system_type="underfloor",
        mode_on_since=time.time() - 60,  # 1 min in, window is 30 min
    )
    # current_temp equals target — without min-run this would go idle
    mode = ctrl._evaluate_bangbang(21.0, TargetTemps(heat=21.0, cool=24.0))
    assert mode == MODE_HEATING


@pytest.mark.asyncio
async def test_bangbang_heating_idles_after_min_run():
    """Underfloor heating goes idle at target once the min-run window has elapsed."""
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
        previous_mode=MODE_HEATING,
        heating_system_type="underfloor",
        mode_on_since=time.time() - 2000,  # 33 min ago, past 30-min window
    )
    mode = ctrl._evaluate_bangbang(21.5, TargetTemps(heat=21.0, cool=24.0))
    assert mode == MODE_IDLE


@pytest.mark.asyncio
async def test_bangbang_cooling_min_run_holds_at_target():
    """Cooling must keep running when at target but within min-run window."""
    hass = build_hass()
    room = make_room(acs=["climate.ac1"], climate_mode="cool_only")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
        previous_mode=MODE_COOLING,
        heating_system_type="underfloor",
        mode_on_since=time.time() - 60,
    )
    mode = ctrl._evaluate_bangbang(23.0, TargetTemps(heat=21.0, cool=23.0))
    assert mode == MODE_COOLING


# ---------------------------------------------------------------------------
# Dead-band tests for bangbang with split targets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bangbang_deadband_split_targets():
    """Inside dead band (between heat and cool), bangbang returns idle."""
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
    mode, pf = await ctrl.async_evaluate(
        current_temp=22.5,
        targets=TargetTemps(heat=21.0, cool=24.0),
    )
    assert mode == MODE_IDLE
    assert pf == 0.0


@pytest.mark.asyncio
async def test_bangbang_heats_with_split_below_heat():
    """Below heat target with split targets, bangbang heats."""
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
    mode, pf = await ctrl.async_evaluate(
        current_temp=20.5,
        targets=TargetTemps(heat=21.0, cool=24.0),
    )
    assert mode == MODE_HEATING
    assert pf == 1.0  # bangbang: full power


@pytest.mark.asyncio
async def test_bangbang_cools_with_split_above_cool():
    """Above cool target with split targets, bangbang cools."""
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
    mode, pf = await ctrl.async_evaluate(
        current_temp=24.5,
        targets=TargetTemps(heat=21.0, cool=24.0),
    )
    assert mode == MODE_COOLING
    assert pf == 1.0  # bangbang: full power


@pytest.mark.asyncio
async def test_bangbang_heat_only_none_cool():
    """TargetTemps(heat=21.0, cool=None) below heat target heats."""
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
    mode, pf = await ctrl.async_evaluate(
        current_temp=20.5,
        targets=TargetTemps(heat=21.0, cool=None),
    )
    assert mode == MODE_HEATING
    assert pf == 1.0


@pytest.mark.asyncio
async def test_bangbang_cool_only_none_heat():
    """TargetTemps(heat=None, cool=24.0) above cool target cools."""
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
    mode, pf = await ctrl.async_evaluate(
        current_temp=24.5,
        targets=TargetTemps(heat=None, cool=24.0),
    )
    assert mode == MODE_COOLING
    assert pf == 1.0


# ---------------------------------------------------------------------------
# async_evaluate with split TargetTemps (full flow)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_evaluate_split_deadband_idle():
    """Full async_evaluate: temp in dead band → IDLE."""
    hass = build_hass()
    room = make_room(acs=["climate.ac"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=20.0,
        settings={},
        has_external_sensor=True,
    )
    mode, pf = await ctrl.async_evaluate(
        current_temp=22.5,
        targets=TargetTemps(heat=21.0, cool=24.0),
    )
    assert mode == MODE_IDLE
    assert pf == 0.0


@pytest.mark.asyncio
async def test_async_evaluate_split_heats_below_heat():
    """Full async_evaluate: temp below heat target → HEATING."""
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
    mode, pf = await ctrl.async_evaluate(
        current_temp=20.5,
        targets=TargetTemps(heat=21.0, cool=24.0),
    )
    assert mode == MODE_HEATING
    assert pf == 1.0


@pytest.mark.asyncio
async def test_async_evaluate_split_cools_above_cool():
    """Full async_evaluate: temp above cool target → COOLING."""
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
    mode, pf = await ctrl.async_evaluate(
        current_temp=24.5,
        targets=TargetTemps(heat=21.0, cool=24.0),
    )
    assert mode == MODE_COOLING
    assert pf == 1.0


# ---------------------------------------------------------------------------
# Stickiness with split TargetTemps
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bangbang_stickiness_heating_stops_in_deadband():
    """Was HEATING at 22.0 (>heat=21, <cool=24) → should go IDLE, not COOLING."""
    hass = build_hass()
    room = make_room(acs=["climate.ac"])
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=20.0,
        settings={},
        has_external_sensor=True,
        previous_mode=MODE_HEATING,
    )
    mode, pf = await ctrl.async_evaluate(
        current_temp=22.0,
        targets=TargetTemps(heat=21.0, cool=24.0),
    )
    assert mode == MODE_IDLE
    assert pf == 0.0


@pytest.mark.asyncio
async def test_bangbang_stickiness_cooling_stops_in_deadband():
    """Was COOLING at 23.0 (<cool=24, >heat=21) → should go IDLE, not HEATING."""
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
        previous_mode=MODE_COOLING,
    )
    mode, pf = await ctrl.async_evaluate(
        current_temp=23.0,
        targets=TargetTemps(heat=21.0, cool=24.0),
    )
    assert mode == MODE_IDLE
    assert pf == 0.0


# ---------------------------------------------------------------------------
# _evaluate_managed_mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_managed_mode_none_target():
    """Managed mode with None target returns idle."""
    hass = build_hass()
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
    assert ctrl._evaluate_managed_mode(TargetTemps(heat=None, cool=None)) == MODE_IDLE


@pytest.mark.asyncio
async def test_managed_mode_cool_only_can_cool():
    """Cool-only mode returns cooling when cooling is allowed."""
    hass = build_hass()
    room = make_room(acs=["climate.ac1"], climate_mode="cool_only")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=False,
    )
    assert ctrl._evaluate_managed_mode(TargetTemps(heat=21.0, cool=23.0)) == MODE_COOLING


@pytest.mark.asyncio
async def test_managed_mode_cool_only_gated():
    """Cool-only mode returns idle when outdoor temp too low."""
    hass = build_hass()
    room = make_room(acs=["climate.ac1"], climate_mode="cool_only")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )
    assert ctrl._evaluate_managed_mode(TargetTemps(heat=21.0, cool=23.0)) == MODE_IDLE


@pytest.mark.asyncio
async def test_managed_mode_heat_only_can_heat():
    """Heat-only mode returns heating when heating is allowed."""
    hass = build_hass()
    room = make_room(climate_mode="heat_only")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=False,
    )
    assert ctrl._evaluate_managed_mode(TargetTemps(heat=21.0, cool=24.0)) == MODE_HEATING


@pytest.mark.asyncio
async def test_managed_mode_heat_only_gated():
    """Heat-only mode returns idle when outdoor temp too high."""
    hass = build_hass()
    room = make_room(climate_mode="heat_only")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=False,
    )
    assert ctrl._evaluate_managed_mode(TargetTemps(heat=21.0, cool=24.0)) == MODE_IDLE


@pytest.mark.asyncio
async def test_managed_mode_auto_both_available():
    """Auto mode with both heat and cool returns heating (season heuristic)."""
    hass = build_hass()
    # Need both TRVs and ACs, outdoor temp in a zone where both are allowed
    room = make_room(acs=["climate.ac1"], climate_mode="auto")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=18.0,
        settings={},  # between cooling_min(16) and heating_max(22)
        has_external_sensor=False,
    )
    assert ctrl._evaluate_managed_mode(TargetTemps(heat=21.0, cool=24.0)) == MODE_HEATING


@pytest.mark.asyncio
async def test_managed_mode_auto_only_cool():
    """Auto mode with only cooling available returns cooling."""
    hass = build_hass()
    # No thermostats, only ACs
    room = make_room(thermostats=[], acs=["climate.ac1"], climate_mode="auto")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=False,
    )
    assert ctrl._evaluate_managed_mode(TargetTemps(heat=21.0, cool=23.0)) == MODE_COOLING


@pytest.mark.asyncio
async def test_managed_mode_auto_neither():
    """Auto mode with neither heat nor cool returns idle."""
    hass = build_hass()
    room = make_room(thermostats=[], acs=[], climate_mode="auto")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=False,
    )
    assert ctrl._evaluate_managed_mode(TargetTemps(heat=21.0, cool=24.0)) == MODE_IDLE
