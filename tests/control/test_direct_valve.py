"""Direct valve control through number entities (#413)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.roommind.const import VALVE_DWELL_SECONDS, TargetTemps
from custom_components.roommind.control import direct_valve
from custom_components.roommind.control.direct_valve import async_release_valve, async_set_valve
from custom_components.roommind.control.mpc_controller import MODE_COOLING, MODE_HEATING, MODE_IDLE, MPCController
from custom_components.roommind.control.thermal_model import RoomModelManager
from custom_components.roommind.managers.heat_source_orchestrator import DeviceCommand, HeatSourcePlan

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

    await direct_valve.async_release_orphaned_valves(hass, {"climate.b": ("number.b", "number.bc")})

    assert _number_calls(hass) == [(OPEN, 100.0), (CLOSE, 100.0)]
    assert direct_valve.held_opening(TRV) is None
    assert direct_valve.held_opening("climate.b") == 0.3


@pytest.mark.asyncio
async def test_release_of_a_released_valve_sends_nothing():
    hass = _hass({OPEN: _number(100), CLOSE: _number(100)})

    await async_release_valve(hass, TRV, OPEN, CLOSE, area_id="a")

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

    await direct_valve.async_release_all_valves(hass, {TRV: (OPEN, CLOSE)})
    assert ("number.o", 100.0) in _number_calls(hass) and (OPEN, 100.0) in _number_calls(hass)

    hass.services.async_call.reset_mock()
    await async_set_valve(hass, TRV, OPEN, CLOSE, 30, area_id="a")
    assert _number_calls(hass) == []

    direct_valve.clear_valve_cache()
    await async_set_valve(hass, TRV, OPEN, CLOSE, 40, area_id="a")
    assert (OPEN, 40.0) in _number_calls(hass)

    with patch.object(direct_valve, "async_release_valve", side_effect=RuntimeError("boom")):
        await direct_valve.async_release_all_valves(hass, {TRV: (OPEN, CLOSE)})
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
