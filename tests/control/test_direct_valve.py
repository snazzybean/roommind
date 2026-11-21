"""Direct valve control through number entities (#413)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.roommind.const import VALVE_DWELL_SECONDS, VALVE_SINGLE_RESEND_SECONDS, TargetTemps
from custom_components.roommind.control import direct_valve
from custom_components.roommind.control.direct_valve import async_release_valve, async_set_valve
from custom_components.roommind.control.mpc_controller import MODE_COOLING, MODE_HEATING, MODE_IDLE, MPCController
from custom_components.roommind.control.thermal_model import RoomModelManager
from custom_components.roommind.managers.heat_source_orchestrator import DeviceCommand, HeatSourcePlan
from custom_components.roommind.utils.device_utils import (
    ValveEntities,
    get_direct_setpoint_eids,
    get_valve_entities,
    has_direct_valve,
)

from .conftest import build_hass, make_room

OPEN = "number.trv_valve_opening_degree"
CLOSE = "number.trv_valve_closing_degree"
TRV = "climate.living_trv"


def _number(value=100.0, *, lo=0, hi=100, step=1, state=None):
    s = MagicMock()
    s.state = state if state is not None else str(value)
    s.attributes = {"min": lo, "max": hi, "step": step}
    return s


def _trv(hvac="heat"):
    s = MagicMock()
    s.state = hvac
    s.attributes = {"hvac_modes": ["off", "heat"], "min_temp": 5.0, "max_temp": 30.0, "target_temp_step": 0.5}
    return s


def _hass(states: dict):
    hass = build_hass()
    hass.states.get = MagicMock(side_effect=states.get)
    return hass


def _number_calls(hass):
    return [
        (c[0][2]["entity_id"], c[0][2]["value"])
        for c in hass.services.async_call.call_args_list
        if c[0][0] == "number" and c[0][1] == "set_value"
    ]


def _climate_calls(hass, service):
    return [c[0][2] for c in hass.services.async_call.call_args_list if c[0][0] == "climate" and c[0][1] == service]


def _valve_room(closing=True, **overrides):
    room = make_room(**overrides)
    for d in room["devices"]:
        if d["type"] == "trv":
            d["valve_opening_entity"] = OPEN
            if closing:
                d["valve_closing_entity"] = CLOSE
    return room


def _controller(hass, room, *, has_external_sensor=True):
    return MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=has_external_sensor,
    )


# --- async_set_valve / async_release_valve ---------------------------------------------


@pytest.mark.asyncio
async def test_pins_opening_and_complementary_closing():
    hass = _hass({OPEN: _number(), CLOSE: _number()})

    await async_set_valve(hass, TRV, OPEN, CLOSE, 30.4, area_id="a")

    assert _number_calls(hass) == [(OPEN, 30.0), (CLOSE, 70.0)]


@pytest.mark.asyncio
async def test_scales_to_the_entity_range():
    """Some valves run 0-99: 100 % is their maximum."""
    hass = _hass({OPEN: _number(50, hi=99), CLOSE: _number(50, hi=99)})

    await async_set_valve(hass, TRV, OPEN, CLOSE, 100, area_id="a")

    assert _number_calls(hass) == [(OPEN, 99.0), (CLOSE, 0.0)]


@pytest.mark.asyncio
async def test_value_the_entity_already_holds_is_not_sent():
    hass = _hass({OPEN: _number(30), CLOSE: _number(70)})

    await async_set_valve(hass, TRV, OPEN, CLOSE, 30, area_id="a")

    assert _number_calls(hass) == []
    assert direct_valve._valve_sent[TRV][1] == 30


@pytest.mark.asyncio
async def test_changes_wait_for_the_dwell_unless_the_target_moves():
    """A 0.2 K sensor step moves the demand by 20 %: only a new target skips the dwell."""
    states = {OPEN: _number(), CLOSE: _number()}
    hass = _hass(states)
    with patch.object(direct_valve, "_now", return_value=1000.0):
        await async_set_valve(hass, TRV, OPEN, CLOSE, 30, area_id="a", target=21.0)
    states[OPEN], states[CLOSE] = _number(30), _number(70)
    hass.services.async_call.reset_mock()

    with patch.object(direct_valve, "_now", return_value=1060.0):
        await async_set_valve(hass, TRV, OPEN, CLOSE, 33, area_id="a", target=21.0)  # deadband
        await async_set_valve(hass, TRV, OPEN, CLOSE, 60, area_id="a", target=21.0)  # dwell
    assert _number_calls(hass) == []

    with patch.object(direct_valve, "_now", return_value=1060.0):
        await async_set_valve(hass, TRV, OPEN, CLOSE, 60, area_id="a", target=22.0)
    assert _number_calls(hass) == [(OPEN, 60.0), (CLOSE, 40.0)]

    states[OPEN], states[CLOSE] = _number(60), _number(40)
    hass.services.async_call.reset_mock()
    with patch.object(direct_valve, "_now", return_value=1060.0 + VALVE_DWELL_SECONDS):
        await async_set_valve(hass, TRV, OPEN, CLOSE, 45, area_id="a", target=22.0)
    assert _number_calls(hass) == [(OPEN, 45.0), (CLOSE, 55.0)]
    assert direct_valve.held_opening(TRV) == 0.45


@pytest.mark.asyncio
async def test_other_entities_are_sent_at_once():
    hass = _hass({OPEN: _number(), CLOSE: _number(), "number.other": _number()})
    with patch.object(direct_valve, "_now", return_value=1000.0):
        await async_set_valve(hass, TRV, OPEN, CLOSE, 30, area_id="a")
        hass.services.async_call.reset_mock()
        await async_set_valve(hass, TRV, "number.other", CLOSE, 40, area_id="a")
    assert ("number.other", 40.0) in _number_calls(hass)


@pytest.mark.asyncio
async def test_unavailable_entity_is_retried_next_cycle():
    states = {OPEN: _number(state="unavailable"), CLOSE: _number()}
    hass = _hass(states)

    await async_set_valve(hass, TRV, OPEN, CLOSE, 30, area_id="a")
    assert TRV not in direct_valve._valve_sent

    states[OPEN] = _number(100)
    hass.services.async_call.reset_mock()
    await async_set_valve(hass, TRV, OPEN, CLOSE, 32, area_id="a")
    assert (OPEN, 32.0) in _number_calls(hass)


@pytest.mark.asyncio
async def test_failed_call_is_not_remembered():
    hass = _hass({OPEN: _number(), CLOSE: _number()})
    hass.services.async_call.side_effect = RuntimeError("zigbee timeout")

    await async_set_valve(hass, TRV, OPEN, CLOSE, 30, area_id="a")

    assert TRV not in direct_valve._valve_sent


@pytest.mark.asyncio
async def test_unusable_number_state_counts_as_unavailable():
    broken = _number()
    broken.attributes = {"min": "x"}
    flat = _number(lo=50, hi=50)
    hass = _hass({OPEN: broken, CLOSE: flat})

    await async_set_valve(hass, TRV, OPEN, CLOSE, 30, area_id="a")

    assert _number_calls(hass) == []


@pytest.mark.asyncio
async def test_non_numeric_state_is_sent():
    hass = _hass({OPEN: _number(state="idle"), CLOSE: _number(70)})

    await async_set_valve(hass, TRV, OPEN, CLOSE, 30, area_id="a")

    assert _number_calls(hass) == [(OPEN, 30.0)]


@pytest.mark.asyncio
async def test_release_sets_both_to_their_maximum_and_forgets_the_position():
    hass = _hass({OPEN: _number(30), CLOSE: _number(70)})
    direct_valve._valve_sent[TRV] = direct_valve._Held(0.0, 30, None, OPEN, CLOSE)

    await async_release_valve(hass, TRV, OPEN, CLOSE, area_id="a")

    assert _number_calls(hass) == [(OPEN, 100.0), (CLOSE, 100.0)]
    assert TRV not in direct_valve._valve_sent


@pytest.mark.asyncio
async def test_release_of_an_unavailable_valve_stays_on_record():
    hass = _hass({OPEN: _number(state="unavailable"), CLOSE: _number(70)})
    direct_valve._valve_sent[TRV] = direct_valve._Held(0.0, 30, 21.0, OPEN, CLOSE)

    await async_release_valve(hass, TRV, OPEN, CLOSE, area_id="a")

    assert direct_valve.held_opening(TRV) == 0.3


@pytest.mark.asyncio
async def test_orphaned_valves_are_released():
    hass = _hass({OPEN: _number(30), CLOSE: _number(70), "number.b": _number(30)})
    direct_valve._valve_sent[TRV] = direct_valve._Held(0.0, 30, 21.0, OPEN, CLOSE)
    direct_valve._valve_sent["climate.b"] = direct_valve._Held(0.0, 30, 21.0, "number.b", "number.bc")

    await direct_valve.async_release_orphaned_valves(hass, {"climate.b": ValveEntities("number.b", "number.bc")})

    assert _number_calls(hass) == [(OPEN, 100.0), (CLOSE, 100.0)]
    assert direct_valve.held_opening(TRV) is None
    assert direct_valve.held_opening("climate.b") == 0.3


@pytest.mark.asyncio
async def test_release_of_a_released_valve_sends_nothing():
    hass = _hass({OPEN: _number(100), CLOSE: _number(100)})

    await async_release_valve(hass, TRV, OPEN, CLOSE, area_id="a")

    assert _number_calls(hass) == []


@pytest.mark.asyncio
async def test_idle_opening_holds_both_positions_at_the_opening():
    """SONOFF TRV-ZBT: the second entity is the opening while the TRV does not heat (#482)."""
    hass = _hass({OPEN: _number(), CLOSE: _number(0)})

    await async_set_valve(hass, TRV, OPEN, CLOSE, 30.4, area_id="a", idle_opening=True)

    assert _number_calls(hass) == [(OPEN, 30.0), (CLOSE, 30.0)]


@pytest.mark.asyncio
async def test_idle_opening_release_closes_the_valve_while_idle():
    """Handed back as a normal TRV: open while it heats, closed while it does not (#482)."""
    hass = _hass({OPEN: _number(30), CLOSE: _number(30)})
    direct_valve._valve_sent[TRV] = direct_valve._Held(0.0, 30, None, OPEN, CLOSE, True)

    await async_release_valve(hass, TRV, OPEN, CLOSE, area_id="a", idle_opening=True)

    assert _number_calls(hass) == [(OPEN, 100.0), (CLOSE, 0.0)]
    assert TRV not in direct_valve._valve_sent


@pytest.mark.asyncio
async def test_a_changed_closing_mode_goes_out_within_the_dwell():
    states = {OPEN: _number(), CLOSE: _number()}
    hass = _hass(states)
    with patch.object(direct_valve, "_now", return_value=1000.0):
        await async_set_valve(hass, TRV, OPEN, CLOSE, 30, area_id="a", target=21.0)
    states[OPEN], states[CLOSE] = _number(30), _number(70)
    hass.services.async_call.reset_mock()

    with patch.object(direct_valve, "_now", return_value=1060.0):
        await async_set_valve(hass, TRV, OPEN, CLOSE, 30, area_id="a", target=21.0, idle_opening=True)

    assert _number_calls(hass) == [(CLOSE, 30.0)]


@pytest.mark.asyncio
async def test_a_valve_checked_in_one_closing_mode_is_checked_again_in_the_other():
    """A gen2 user switching to idle opening after the start check must get the idle position closed."""
    states = {OPEN: _number(100), CLOSE: _number(100)}
    hass = _hass(states)
    await async_release_valve(hass, TRV, OPEN, CLOSE, area_id="a")
    assert _number_calls(hass) == []

    await async_release_valve(hass, TRV, OPEN, CLOSE, area_id="a", idle_opening=True)
    assert _number_calls(hass) == [(CLOSE, 0.0)]

    states[CLOSE] = _number(0)
    hass.services.async_call.reset_mock()
    await async_release_valve(hass, TRV, OPEN, CLOSE, area_id="a", idle_opening=True)
    assert _number_calls(hass) == []


@pytest.mark.asyncio
async def test_a_changed_closing_mode_is_no_orphan():
    """Same entities, other mode: the next cycle rewrites the valve, no hand-back in between."""
    hass = _hass({OPEN: _number(30), CLOSE: _number(70)})
    direct_valve._valve_sent[TRV] = direct_valve._Held(0.0, 30, 21.0, OPEN, CLOSE)

    await direct_valve.async_release_orphaned_valves(hass, {TRV: ValveEntities(OPEN, CLOSE, True)})

    assert hass.services.async_call.call_count == 0
    assert direct_valve.held_opening(TRV) == 0.3


@pytest.mark.asyncio
async def test_unload_releases_each_valve_in_its_closing_mode():
    hass = _hass({OPEN: _number(30), CLOSE: _number(30), "number.b": _number(30), "number.bc": _number(70)})
    direct_valve._valve_sent["climate.b"] = direct_valve._Held(0.0, 30, None, "number.b", "number.bc")

    await direct_valve.async_release_all_valves(hass, {TRV: ValveEntities(OPEN, CLOSE, True)})

    assert sorted(_number_calls(hass)) == sorted(
        [(OPEN, 100.0), (CLOSE, 0.0), ("number.b", 100.0), ("number.bc", 100.0)]
    )


@pytest.mark.asyncio
async def test_an_orphan_is_released_in_its_own_closing_mode():
    hass = _hass({OPEN: _number(30), CLOSE: _number(30)})
    direct_valve._valve_sent[TRV] = direct_valve._Held(0.0, 30, 21.0, OPEN, CLOSE, True)

    await direct_valve.async_release_orphaned_valves(hass, {})

    assert _number_calls(hass) == [(OPEN, 100.0), (CLOSE, 0.0)]


@pytest.mark.asyncio
async def test_other_entities_of_a_checked_valve_are_left_alone_as_before():
    """Swapped entities in the same mode keep the once-per-start check of v1.8.0."""
    hass = _hass({OPEN: _number(100), CLOSE: _number(100), "number.other": _number(80)})
    await async_release_valve(hass, TRV, OPEN, CLOSE, area_id="a")

    await async_release_valve(hass, TRV, OPEN, "number.other", area_id="a")

    assert _number_calls(hass) == []


# --- controller ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_heating_drives_the_valve_instead_of_a_boosted_setpoint():
    hass = _hass({TRV: _trv("off"), OPEN: _number(), CLOSE: _number()})
    ctrl = _controller(hass, _valve_room())

    await ctrl.async_apply(
        MODE_HEATING,
        TargetTemps(heat=21.0, cool=24.0),
        power_fraction=0.35,
        current_temp=20.6,
        heating_boost_target=30.0,
    )

    assert _number_calls(hass) == [(OPEN, 35.0), (CLOSE, 65.0)]
    # The proportional setpoint as on main: a later release without command leaves no boost behind
    [setpoint] = [c["temperature"] for c in _climate_calls(hass, "set_temperature")]
    assert 21.0 <= setpoint < 29.5
    assert [c["hvac_mode"] for c in _climate_calls(hass, "set_hvac_mode")] == ["heat"]


@pytest.mark.asyncio
async def test_idle_opening_trv_holds_both_positions_and_releases_closed():
    room = _valve_room()
    room["devices"][0]["valve_closing_mode"] = "idle_opening"
    states = {TRV: _trv("off"), OPEN: _number(), CLOSE: _number(0)}
    hass = _hass(states)
    ctrl = _controller(hass, room)

    await ctrl.async_apply(
        MODE_HEATING,
        TargetTemps(heat=21.0, cool=24.0),
        power_fraction=0.35,
        current_temp=20.6,
        heating_boost_target=30.0,
    )
    assert _number_calls(hass) == [(OPEN, 35.0), (CLOSE, 35.0)]

    states[OPEN], states[CLOSE] = _number(35), _number(35)
    hass.services.async_call.reset_mock()
    await ctrl.async_apply(MODE_IDLE, TargetTemps(heat=21.0, cool=24.0), power_fraction=0.0, current_temp=21.3)
    assert _number_calls(hass) == [(OPEN, 100.0), (CLOSE, 0.0)]


@pytest.mark.asyncio
async def test_opening_degree_alone_is_no_valve_control():
    """Without the closing degree the TRV's own controller still closes the valve: setpoint path."""
    hass = _hass({TRV: _trv(), OPEN: _number()})
    ctrl = _controller(hass, _valve_room(closing=False))

    await ctrl.async_apply(
        MODE_HEATING,
        TargetTemps(heat=21.0, cool=24.0),
        power_fraction=0.35,
        current_temp=20.6,
        heating_boost_target=30.0,
    )

    assert _number_calls(hass) == []
    assert len(_climate_calls(hass, "set_temperature")) == 1


@pytest.mark.asyncio
async def test_valve_trv_ignores_the_direct_setpoint_mode():
    room = _valve_room()
    room["devices"][0]["setpoint_mode"] = "direct"
    hass = _hass({TRV: _trv(), OPEN: _number(), CLOSE: _number()})
    ctrl = _controller(hass, room)

    await ctrl.async_apply(
        MODE_HEATING,
        TargetTemps(heat=21.0, cool=24.0),
        power_fraction=0.35,
        current_temp=20.6,
        heating_boost_target=30.0,
    )

    [setpoint] = [c["temperature"] for c in _climate_calls(hass, "set_temperature")]
    assert setpoint > 21.0  # proportional, not the direct target


@pytest.mark.asyncio
async def test_idle_hands_the_valve_back():
    hass = _hass({TRV: _trv(), OPEN: _number(35), CLOSE: _number(65)})
    ctrl = _controller(hass, _valve_room())

    await ctrl.async_apply(MODE_IDLE, TargetTemps(heat=21.0, cool=24.0), power_fraction=0.0, current_temp=21.3)

    assert _number_calls(hass) == [(OPEN, 100.0), (CLOSE, 100.0)]
    assert [c["hvac_mode"] for c in _climate_calls(hass, "set_hvac_mode")] == ["off"]


@pytest.mark.asyncio
async def test_cooling_hands_the_valve_back():
    hass = _hass({TRV: _trv(), OPEN: _number(35), CLOSE: _number(65)})
    ctrl = _controller(hass, _valve_room())

    await ctrl.async_apply(MODE_COOLING, TargetTemps(heat=21.0, cool=24.0), power_fraction=0.5, current_temp=25.0)

    assert _number_calls(hass) == [(OPEN, 100.0), (CLOSE, 100.0)]


@pytest.mark.asyncio
async def test_managed_mode_uses_the_setpoint_and_releases_the_valve():
    hass = _hass({TRV: _trv(), OPEN: _number(35), CLOSE: _number(65)})
    ctrl = _controller(hass, _valve_room(climate_mode="heat_only"), has_external_sensor=False)

    await ctrl.async_apply(MODE_HEATING, TargetTemps(heat=21.0, cool=None), power_fraction=1.0, current_temp=None)

    assert _number_calls(hass) == [(OPEN, 100.0), (CLOSE, 100.0)]
    assert [c["temperature"] for c in _climate_calls(hass, "set_temperature")] == [21.0]


@pytest.mark.asyncio
async def test_managed_auto_mode_releases_the_valve():
    hass = _hass({TRV: _trv(), OPEN: _number(35), CLOSE: _number(65)})
    ctrl = _controller(hass, _valve_room(), has_external_sensor=False)

    await ctrl.async_apply(MODE_HEATING, TargetTemps(heat=21.0, cool=24.0), power_fraction=1.0, current_temp=None)

    assert _number_calls(hass) == [(OPEN, 100.0), (CLOSE, 100.0)]


@pytest.mark.asyncio
async def test_compressor_forced_off_trv_is_idled_and_released():
    hass = _hass({TRV: _trv(), OPEN: _number(35), CLOSE: _number(65)})
    ctrl = _controller(hass, _valve_room())

    await ctrl.async_apply(
        MODE_HEATING,
        TargetTemps(heat=21.0, cool=24.0),
        power_fraction=0.5,
        current_temp=20.0,
        compressor_forced_off={TRV},
    )

    assert _number_calls(hass) == [(OPEN, 100.0), (CLOSE, 100.0)]


@pytest.mark.asyncio
async def test_compressor_forced_off_while_cooling_releases():
    hass = _hass({TRV: _trv(), OPEN: _number(35), CLOSE: _number(65)})
    ctrl = _controller(hass, _valve_room())

    await ctrl.async_apply(
        MODE_COOLING,
        TargetTemps(heat=21.0, cool=24.0),
        power_fraction=0.5,
        current_temp=25.0,
        compressor_forced_off={TRV},
    )

    assert _number_calls(hass) == [(OPEN, 100.0), (CLOSE, 100.0)]


def _plan(active: bool, pf: float = 0.4) -> HeatSourcePlan:
    return HeatSourcePlan(
        commands=[
            DeviceCommand(
                entity_id=TRV, role="primary", device_type="thermostat", active=active, power_fraction=pf, reason="t"
            )
        ],
        active_sources="primary" if active else "none",
        reason="test",
    )


@pytest.mark.asyncio
async def test_orchestrated_active_trv_drives_the_valve():
    hass = _hass({TRV: _trv(), OPEN: _number(), CLOSE: _number()})
    ctrl = _controller(hass, _valve_room())

    await ctrl.async_apply(
        MODE_HEATING, TargetTemps(heat=21.0, cool=24.0), current_temp=20.5, heat_source_plan=_plan(True, 0.4)
    )

    assert _number_calls(hass) == [(OPEN, 40.0), (CLOSE, 60.0)]
    assert len(_climate_calls(hass, "set_temperature")) == 1


@pytest.mark.asyncio
async def test_orchestrated_parked_trv_is_released():
    hass = _hass({TRV: _trv(), OPEN: _number(40), CLOSE: _number(60)})
    ctrl = _controller(hass, _valve_room())

    await ctrl.async_apply(
        MODE_HEATING, TargetTemps(heat=21.0, cool=24.0), current_temp=20.5, heat_source_plan=_plan(False)
    )

    assert _number_calls(hass) == [(OPEN, 100.0), (CLOSE, 100.0)]


@pytest.mark.asyncio
async def test_orchestrated_forced_off_trv_is_released():
    hass = _hass({TRV: _trv(), OPEN: _number(40), CLOSE: _number(60)})
    ctrl = _controller(hass, _valve_room())

    await ctrl.async_apply(
        MODE_HEATING,
        TargetTemps(heat=21.0, cool=24.0),
        current_temp=20.5,
        heat_source_plan=_plan(True),
        compressor_forced_off={TRV},
    )

    assert _number_calls(hass) == [(OPEN, 100.0), (CLOSE, 100.0)]


@pytest.mark.asyncio
async def test_trv_without_valve_entities_is_unchanged():
    hass = _hass({TRV: _trv()})
    ctrl = _controller(hass, make_room())

    await ctrl.async_apply(
        MODE_HEATING,
        TargetTemps(heat=21.0, cool=24.0),
        power_fraction=0.35,
        current_temp=20.6,
        heating_boost_target=30.0,
    )

    assert _number_calls(hass) == []
    assert len(_climate_calls(hass, "set_temperature")) == 1


@pytest.mark.asyncio
async def test_compressor_hold_runs_the_valve_at_the_minimum():
    hass = _hass({TRV: _trv(), OPEN: _number(60), CLOSE: _number(40)})
    ctrl = _controller(hass, _valve_room())

    await ctrl.async_apply(
        MODE_IDLE,
        TargetTemps(heat=21.0, cool=24.0),
        power_fraction=0.0,
        current_temp=21.3,
        compressor_forced_on={TRV},
    )

    assert _number_calls(hass) == [(OPEN, 15.0), (CLOSE, 85.0)]
    assert _climate_calls(hass, "set_temperature") == []


@pytest.mark.asyncio
async def test_compressor_hold_of_an_idle_opening_trv_pins_both_at_the_minimum():
    room = _valve_room()
    room["devices"][0]["valve_closing_mode"] = "idle_opening"
    hass = _hass({TRV: _trv(), OPEN: _number(60), CLOSE: _number(60)})
    ctrl = _controller(hass, room)

    await ctrl.async_apply(
        MODE_IDLE,
        TargetTemps(heat=21.0, cool=24.0),
        power_fraction=0.0,
        current_temp=21.3,
        compressor_forced_on={TRV},
    )

    assert _number_calls(hass) == [(OPEN, 15.0), (CLOSE, 15.0)]


@pytest.mark.asyncio
async def test_orchestrated_parked_trv_in_a_hold_runs_at_the_minimum():
    hass = _hass({TRV: _trv(), OPEN: _number(60), CLOSE: _number(40)})
    ctrl = _controller(hass, _valve_room())

    await ctrl.async_apply(
        MODE_HEATING,
        TargetTemps(heat=21.0, cool=24.0),
        current_temp=20.5,
        heat_source_plan=_plan(False),
        compressor_forced_on={TRV},
    )

    assert _number_calls(hass) == [(OPEN, 15.0), (CLOSE, 85.0)]


@pytest.mark.asyncio
async def test_hold_of_a_setpoint_trv_is_unchanged():
    hass = _hass({TRV: _trv()})
    ctrl = _controller(hass, make_room())

    await ctrl.async_apply(
        MODE_IDLE,
        TargetTemps(heat=21.0, cool=24.0),
        power_fraction=0.0,
        current_temp=21.3,
        compressor_forced_on={TRV},
    )

    assert _number_calls(hass) == []


@pytest.mark.asyncio
async def test_a_held_valve_is_released_even_if_its_state_lags():
    """Z2M reports the new degrees only with the device's echo: the state may still say 100."""
    hass = _hass({OPEN: _number(100), CLOSE: _number(100)})
    direct_valve._valve_sent[TRV] = direct_valve._Held(0.0, 30, 21.0, OPEN, CLOSE)

    await async_release_valve(hass, TRV, OPEN, CLOSE, area_id="a")

    assert _number_calls(hass) == [(OPEN, 100.0), (CLOSE, 100.0)]


@pytest.mark.asyncio
async def test_a_valve_not_held_is_checked_once_and_then_left_alone():
    """Degrees set by hand while RoomMind does not control the TRV stay."""
    states = {OPEN: _number(30), CLOSE: _number(70)}
    hass = _hass(states)
    await async_release_valve(hass, TRV, OPEN, CLOSE, area_id="a")
    assert _number_calls(hass) == [(OPEN, 100.0), (CLOSE, 100.0)]

    states[OPEN] = _number(60)
    hass.services.async_call.reset_mock()
    await async_release_valve(hass, TRV, OPEN, CLOSE, area_id="a")
    assert _number_calls(hass) == []


@pytest.mark.asyncio
async def test_hand_back_sets_the_room_target_on_the_trv():
    hass = _hass({OPEN: _number(30), CLOSE: _number(70)})
    hass.config.units.temperature_unit = "°C"
    direct_valve._valve_sent[TRV] = direct_valve._Held(0.0, 30, 21.0, OPEN, CLOSE)

    await async_release_valve(hass, TRV, OPEN, CLOSE, area_id="a", hand_back=True)

    assert [c["temperature"] for c in _climate_calls(hass, "set_temperature")] == [21.0]


@pytest.mark.asyncio
async def test_hand_back_without_a_held_valve_sends_no_setpoint():
    hass = _hass({OPEN: _number(30), CLOSE: _number(70)})

    await async_release_valve(hass, TRV, OPEN, CLOSE, area_id="a", hand_back=True)

    assert _climate_calls(hass, "set_temperature") == []


@pytest.mark.asyncio
async def test_hand_back_failure_is_logged(caplog):
    hass = _hass({OPEN: _number(30), CLOSE: _number(70)})
    hass.config.units.temperature_unit = "°C"
    direct_valve._valve_sent[TRV] = direct_valve._Held(0.0, 30, 21.0, OPEN, CLOSE)

    async def fail_climate(domain, service, data, **kwargs):
        if domain == "climate":
            raise RuntimeError("boom")

    hass.services.async_call.side_effect = fail_climate
    await async_release_valve(hass, TRV, OPEN, CLOSE, area_id="a", hand_back=True)

    assert "handing the setpoint back" in caplog.text


@pytest.mark.asyncio
async def test_after_unload_nothing_is_pinned_until_the_next_setup(caplog):
    hass = _hass({OPEN: _number(30), CLOSE: _number(70), "number.o": _number(30), "number.c": _number(70)})
    hass.config.units.temperature_unit = "°C"
    direct_valve._valve_sent["climate.orphan"] = direct_valve._Held(0.0, 30, 21.0, "number.o", "number.c")

    await direct_valve.async_release_all_valves(hass, {TRV: ValveEntities(OPEN, CLOSE)})
    assert ("number.o", 100.0) in _number_calls(hass) and (OPEN, 100.0) in _number_calls(hass)

    hass.services.async_call.reset_mock()
    await async_set_valve(hass, TRV, OPEN, CLOSE, 30, area_id="a")
    assert _number_calls(hass) == []

    direct_valve.clear_valve_cache()
    await async_set_valve(hass, TRV, OPEN, CLOSE, 40, area_id="a")
    assert (OPEN, 40.0) in _number_calls(hass)

    with patch.object(direct_valve, "async_release_valve", side_effect=RuntimeError("boom")):
        await direct_valve.async_release_all_valves(hass, {TRV: ValveEntities(OPEN, CLOSE)})
    assert "on unload failed" in caplog.text


@pytest.mark.asyncio
async def test_urgent_changes_skip_the_dwell():
    states = {OPEN: _number(), CLOSE: _number()}
    hass = _hass(states)
    with patch.object(direct_valve, "_now", return_value=1000.0):
        await async_set_valve(hass, TRV, OPEN, CLOSE, 80, area_id="a", target=21.0)
        hass.services.async_call.reset_mock()
        await async_set_valve(hass, TRV, OPEN, CLOSE, 15, area_id="a", target=21.0, urgent=True)
    assert _number_calls(hass) == [(OPEN, 15.0), (CLOSE, 85.0)]


@pytest.mark.asyncio
async def test_a_half_applied_position_after_the_idle_check_is_released():
    """Checked while idle, then one degree went out and the other failed: still released."""
    states = {OPEN: _number(100), CLOSE: _number(100)}
    hass = _hass(states)
    await async_release_valve(hass, TRV, OPEN, CLOSE, area_id="a")  # idle check at start

    states[CLOSE] = _number(state="unavailable")
    await async_set_valve(hass, TRV, OPEN, CLOSE, 30, area_id="a")
    states[OPEN], states[CLOSE] = _number(30), _number(100)
    hass.services.async_call.reset_mock()

    await async_release_valve(hass, TRV, OPEN, CLOSE, area_id="a")

    assert (OPEN, 100.0) in _number_calls(hass)


@pytest.mark.asyncio
async def test_the_held_target_follows_a_change_the_position_does_not_need():
    hass = _hass({OPEN: _number(), CLOSE: _number()})
    hass.config.units.temperature_unit = "°C"
    with patch.object(direct_valve, "_now", return_value=1000.0):
        await async_set_valve(hass, TRV, OPEN, CLOSE, 15, area_id="a", target=21.0)
        await async_set_valve(hass, TRV, OPEN, CLOSE, 15, area_id="a", target=17.0)
    hass.services.async_call.reset_mock()

    await async_release_valve(hass, TRV, OPEN, CLOSE, area_id="a", hand_back=True)

    assert [c["temperature"] for c in _climate_calls(hass, "set_temperature")] == [17.0]


# --- single valve position entity (#537) ------------------------------------------------

PI = "number.trv_pi_heating_demand"


def _single_room(**overrides):
    room = _valve_room(closing=False, **overrides)
    for d in room["devices"]:
        if d["type"] == "trv":
            d["valve_opening_entity"] = PI
            d["valve_closing_mode"] = "single"
    return room


@pytest.mark.asyncio
async def test_single_entity_gets_the_opening_only():
    hass = _hass({PI: _number(0)})

    await async_set_valve(hass, TRV, PI, "", 30.4, area_id="a")

    assert _number_calls(hass) == [(PI, 30.0)]
    assert direct_valve.held_opening(TRV) == 0.3


@pytest.mark.asyncio
async def test_single_entity_position_is_sent_again_before_the_trv_takes_over():
    """A Bosch BTH-RA moves the valve itself 15 minutes after a write: the position goes out again, unchanged."""
    states = {PI: _number(0)}
    hass = _hass(states)
    with patch.object(direct_valve, "_now", return_value=1000.0):
        await async_set_valve(hass, TRV, PI, "", 30, area_id="a", target=21.0)
    states[PI] = _number(30)
    hass.services.async_call.reset_mock()

    with patch.object(direct_valve, "_now", return_value=1000.0 + VALVE_SINGLE_RESEND_SECONDS - 1):
        await async_set_valve(hass, TRV, PI, "", 30, area_id="a", target=21.0)
    assert _number_calls(hass) == []

    with patch.object(direct_valve, "_now", return_value=1000.0 + VALVE_SINGLE_RESEND_SECONDS):
        await async_set_valve(hass, TRV, PI, "", 30, area_id="a", target=21.0)
    # Sent although the state still shows 30
    assert _number_calls(hass) == [(PI, 30.0)]

    hass.services.async_call.reset_mock()
    with patch.object(direct_valve, "_now", return_value=1000.0 + VALVE_SINGLE_RESEND_SECONDS + 30):
        await async_set_valve(hass, TRV, PI, "", 30, area_id="a", target=21.0)
    assert _number_calls(hass) == []


@pytest.mark.asyncio
async def test_single_entity_resend_keeps_the_position_within_the_deadband():
    """The resend holds the valve where it is: a demand 3 % off does not move the motor."""
    states = {PI: _number(0)}
    hass = _hass(states)
    with patch.object(direct_valve, "_now", return_value=1000.0):
        await async_set_valve(hass, TRV, PI, "", 30, area_id="a", target=21.0)
    states[PI] = _number(30)
    hass.services.async_call.reset_mock()

    with patch.object(direct_valve, "_now", return_value=1000.0 + VALVE_SINGLE_RESEND_SECONDS):
        await async_set_valve(hass, TRV, PI, "", 33, area_id="a", target=21.0)

    assert _number_calls(hass) == [(PI, 30.0)]
    assert direct_valve.held_opening(TRV) == 0.3


@pytest.mark.asyncio
async def test_two_entity_valve_is_not_sent_again():
    states = {OPEN: _number(), CLOSE: _number()}
    hass = _hass(states)
    with patch.object(direct_valve, "_now", return_value=1000.0):
        await async_set_valve(hass, TRV, OPEN, CLOSE, 30, area_id="a", target=21.0)
    states[OPEN], states[CLOSE] = _number(30), _number(70)
    hass.services.async_call.reset_mock()

    with patch.object(direct_valve, "_now", return_value=1000.0 + 10 * VALVE_SINGLE_RESEND_SECONDS):
        await async_set_valve(hass, TRV, OPEN, CLOSE, 30, area_id="a", target=21.0)

    assert _number_calls(hass) == []


@pytest.mark.asyncio
async def test_single_entity_release_closes_the_valve():
    """100 % is no device default here, it is a fully open valve."""
    hass = _hass({PI: _number(30)})
    direct_valve._valve_sent[TRV] = direct_valve._Held(0.0, 30, None, PI, "")

    await async_release_valve(hass, TRV, PI, "", area_id="a")

    assert _number_calls(hass) == [(PI, 0.0)]
    assert direct_valve.held_opening(TRV) is None


@pytest.mark.asyncio
async def test_single_entity_left_open_before_a_restart_is_closed_once():
    """A written position survives a restart and the TRV being off: the first release closes it."""
    states = {PI: _number(30)}
    hass = _hass(states)

    await async_release_valve(hass, TRV, PI, "", area_id="a")
    assert _number_calls(hass) == [(PI, 0.0)]

    # Checked once: what the TRV does with its valve afterwards is its own
    states[PI] = _number(45)
    hass.services.async_call.reset_mock()
    await async_release_valve(hass, TRV, PI, "", area_id="a")
    assert _number_calls(hass) == []


@pytest.mark.asyncio
async def test_single_entity_found_closed_after_a_start_is_not_written():
    hass = _hass({PI: _number(0)})

    await async_release_valve(hass, TRV, PI, "", area_id="a")

    assert _number_calls(hass) == []


@pytest.mark.asyncio
async def test_single_entity_check_after_a_start_waits_for_the_entity():
    states = {PI: _number(state="unavailable")}
    hass = _hass(states)

    await async_release_valve(hass, TRV, PI, "", area_id="a")
    assert _number_calls(hass) == []

    states[PI] = _number(30)
    await async_release_valve(hass, TRV, PI, "", area_id="a")
    assert _number_calls(hass) == [(PI, 0.0)]


@pytest.mark.asyncio
async def test_single_entity_hand_back_sets_the_room_target():
    hass = _hass({PI: _number(30), TRV: _trv()})
    direct_valve._valve_sent[TRV] = direct_valve._Held(0.0, 30, 21.0, PI, "")

    await async_release_valve(hass, TRV, PI, "", area_id="a", hand_back=True)

    assert _number_calls(hass) == [(PI, 0.0)]
    assert [c["temperature"] for c in _climate_calls(hass, "set_temperature")] == [21.0]


@pytest.mark.asyncio
async def test_single_entity_trv_heats_through_the_valve():
    hass = _hass({TRV: _trv("off"), PI: _number(0)})
    ctrl = _controller(hass, _single_room())

    await ctrl.async_apply(
        MODE_HEATING,
        TargetTemps(heat=21.0, cool=24.0),
        power_fraction=0.35,
        current_temp=20.6,
        heating_boost_target=30.0,
    )

    assert _number_calls(hass) == [(PI, 35.0)]
    assert [c["hvac_mode"] for c in _climate_calls(hass, "set_hvac_mode")] == ["heat"]


@pytest.mark.asyncio
async def test_single_entity_trv_idle_closes_the_valve():
    hass = _hass({TRV: _trv(), PI: _number(35)})
    direct_valve._valve_sent[TRV] = direct_valve._Held(0.0, 35, 21.0, PI, "")
    ctrl = _controller(hass, _single_room())

    await ctrl.async_apply(MODE_IDLE, TargetTemps(heat=21.0, cool=24.0), power_fraction=0.0, current_temp=21.3)

    assert _number_calls(hass) == [(PI, 0.0)]
    assert [c["hvac_mode"] for c in _climate_calls(hass, "set_hvac_mode")] == ["off"]


def test_single_mode_needs_the_opening_entity_only():
    trv = {"entity_id": TRV, "type": "trv", "valve_opening_entity": PI, "valve_closing_mode": "single"}

    assert get_valve_entities([trv]) == {TRV: ValveEntities(PI, "")}
    # A second entity left over from another mode is ignored
    assert get_valve_entities([{**trv, "valve_closing_entity": CLOSE}]) == {TRV: ValveEntities(PI, "")}
    assert get_valve_entities([{**trv, "valve_closing_mode": "closing_degree"}]) == {}
    assert get_valve_entities([{**trv, "type": "ac"}]) == {}


@pytest.mark.asyncio
async def test_single_entity_is_written_even_if_the_state_shows_the_value():
    """After a restart the state may be the TRV's own position: only a write starts the hold."""
    hass = _hass({PI: _number(30)})

    await async_set_valve(hass, TRV, PI, "", 30, area_id="a")

    assert _number_calls(hass) == [(PI, 30.0)]
    assert direct_valve.held_opening(TRV) == 0.3


@pytest.mark.asyncio
async def test_single_entity_is_sent_again_after_a_failed_write():
    """A failed write drops the hold; the next cycle writes although the state shows the value."""
    states = {PI: _number(0)}
    hass = _hass(states)
    with patch.object(direct_valve, "_now", return_value=1000.0):
        await async_set_valve(hass, TRV, PI, "", 30, area_id="a", target=21.0)
    states[PI] = _number(state="unavailable")
    with patch.object(direct_valve, "_now", return_value=1000.0 + VALVE_SINGLE_RESEND_SECONDS):
        await async_set_valve(hass, TRV, PI, "", 30, area_id="a", target=21.0)
    assert direct_valve.held_opening(TRV) is None
    states[PI] = _number(30)
    hass.services.async_call.reset_mock()

    with patch.object(direct_valve, "_now", return_value=1000.0 + VALVE_SINGLE_RESEND_SECONDS + 30):
        await async_set_valve(hass, TRV, PI, "", 30, area_id="a", target=21.0)

    assert _number_calls(hass) == [(PI, 30.0)]


@pytest.mark.asyncio
async def test_single_entity_is_closed_after_a_failed_write():
    """The hold is forgotten after a failed write, the valve still sits where it was put."""
    states = {PI: _number(0)}
    hass = _hass(states)
    await async_set_valve(hass, TRV, PI, "", 30, area_id="a", target=21.0)
    states[PI] = _number(state="unavailable")
    await async_set_valve(hass, TRV, PI, "", 60, area_id="a", target=22.0)
    assert direct_valve.held_opening(TRV) is None
    states[PI] = _number(30)
    hass.services.async_call.reset_mock()

    await async_release_valve(hass, TRV, PI, "", area_id="a")
    assert _number_calls(hass) == [(PI, 0.0)]

    # Released once: the valve is the TRV's own again
    states[PI] = _number(45)
    hass.services.async_call.reset_mock()
    await async_release_valve(hass, TRV, PI, "", area_id="a")
    assert _number_calls(hass) == []


@pytest.mark.asyncio
async def test_single_entity_release_is_retried_while_the_entity_is_unavailable():
    states = {PI: _number(state="unavailable")}
    hass = _hass(states)
    direct_valve._valve_sent[TRV] = direct_valve._Held(0.0, 30, None, PI, "")

    await async_release_valve(hass, TRV, PI, "", area_id="a")
    assert direct_valve.held_opening(TRV) == 0.3

    states[PI] = _number(30)
    await async_release_valve(hass, TRV, PI, "", area_id="a")
    assert _number_calls(hass) == [(PI, 0.0)]
    assert direct_valve.held_opening(TRV) is None


@pytest.mark.asyncio
async def test_single_entity_orphan_is_closed():
    hass = _hass({PI: _number(30)})
    direct_valve._valve_sent[TRV] = direct_valve._Held(0.0, 30, 21.0, PI, "")

    await direct_valve.async_release_orphaned_valves(hass, {})

    assert _number_calls(hass) == [(PI, 0.0)]
    assert direct_valve.held_opening(TRV) is None


@pytest.mark.asyncio
async def test_unload_closes_a_held_single_entity_and_leaves_checked_ones_alone():
    hass = _hass({PI: _number(30), "number.other_pi": _number(45)})
    direct_valve._valve_sent[TRV] = direct_valve._Held(0.0, 30, None, PI, "")
    direct_valve._checked["climate.other"] = False  # checked after the start, the TRV's own since

    await direct_valve.async_release_all_valves(
        hass, {TRV: ValveEntities(PI, ""), "climate.other": ValveEntities("number.other_pi", "")}
    )

    assert _number_calls(hass) == [(PI, 0.0)]


@pytest.mark.asyncio
async def test_unload_releases_a_held_pair_through_its_own_entities():
    """Config already says single on the same opening entity: the pair that was written goes back."""
    hass = _hass({OPEN: _number(30), CLOSE: _number(70)})
    direct_valve._valve_sent[TRV] = direct_valve._Held(0.0, 30, None, OPEN, CLOSE)

    await direct_valve.async_release_all_valves(hass, {TRV: ValveEntities(OPEN, "")})

    assert _number_calls(hass) == [(OPEN, 100.0), (CLOSE, 100.0)]


@pytest.mark.asyncio
async def test_single_entity_trv_in_managed_mode_is_checked_once():
    """Without the room sensor the TRV regulates by itself; only the check after a start writes."""
    states = {TRV: _trv(), PI: _number(45)}
    hass = _hass(states)
    ctrl = _controller(hass, _single_room(), has_external_sensor=False)

    await ctrl.async_apply(MODE_HEATING, TargetTemps(heat=21.0, cool=24.0), power_fraction=1.0, current_temp=20.0)
    assert _number_calls(hass) == [(PI, 0.0)]

    states[PI] = _number(45)
    hass.services.async_call.reset_mock()
    await ctrl.async_apply(MODE_HEATING, TargetTemps(heat=21.0, cool=24.0), power_fraction=1.0, current_temp=20.0)
    assert _number_calls(hass) == []


def test_single_valve_trv_ignores_the_direct_setpoint_mode():
    trv = {"entity_id": TRV, "type": "trv", "setpoint_mode": "direct"}
    single = {**trv, "valve_opening_entity": PI, "valve_closing_mode": "single"}

    assert get_direct_setpoint_eids([trv]) == {TRV}
    assert get_direct_setpoint_eids([single]) == set()
    assert has_direct_valve(single)
    assert not has_direct_valve(trv)
    assert not has_direct_valve({**single, "valve_opening_entity": ""})
