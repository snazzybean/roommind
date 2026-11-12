"""Direct-mode devices get the target MPC pre-heats / pre-cools for, not the current one."""

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
    _active_targets,
    _last_commands,
    clear_command_cache,
)
from custom_components.roommind.control.mpc_optimizer import MPCPlan
from custom_components.roommind.control.thermal_model import RoomModelManager
from custom_components.roommind.coordinator import RoomMindCoordinator
from custom_components.roommind.managers.heat_source_orchestrator import DeviceCommand, HeatSourcePlan
from custom_components.roommind.utils.schedule_utils import make_target_resolver

from .conftest import build_hass, make_room

BLOCK_S = 300


def _state(*, hvac="heat", modes=("heat", "off"), temperature=None):
    state = MagicMock()
    state.state = hvac
    state.attributes = {
        "hvac_modes": list(modes),
        "min_temp": 5.0,
        "max_temp": 30.0,
        "target_temp_step": 0.5,
        "temperature": temperature,
    }
    return state


def _room(*, device_type="trv", mode="direct", offset=None, climate_mode="heat_only", system="underfloor"):
    thermostats = ["climate.dev"] if device_type == "trv" else []
    acs = ["climate.dev"] if device_type == "ac" else []
    room = make_room(thermostats=thermostats, acs=acs, climate_mode=climate_mode, heating_system_type=system)
    room["devices"][0]["setpoint_mode"] = mode
    if offset is not None:
        room["devices"][0]["setpoint_offset"] = offset
    return room


def _step_resolver(now_target: TargetTemps, later_target: TargetTemps, after_s: float):
    start = time.time()

    def resolve(ts: float) -> TargetTemps:
        return later_target if ts >= start + after_s else now_target

    return resolve


def _controller(room, resolver, *, system="underfloor", plan_action=MODE_HEATING, lookahead=24, monkeypatch=None):
    hass = build_hass()
    hass.states.get = MagicMock(return_value=_state(modes=("heat", "cool", "off")))
    ctrl = MPCController(
        hass,
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
        target_resolver=resolver,
        heating_system_type=system,
    )
    plan = MPCPlan(
        actions=[plan_action] * 24,
        temperatures=[19.0] * 25,
        power_fractions=[0.8] * 24,
        lookahead_blocks=lookahead,
    )
    assert monkeypatch is not None
    monkeypatch.setattr(
        "custom_components.roommind.control.mpc_controller.MPCOptimizer.optimize",
        lambda *a, **kw: plan,
    )
    return hass, ctrl


def _sent(hass, eid="climate.dev"):
    return [
        c[0][2]["temperature"]
        for c in hass.services.async_call.call_args_list
        if c[0][1] == "set_temperature" and c[0][2]["entity_id"] == eid
    ]


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_command_cache()
    _last_commands.clear()
    yield
    clear_command_cache()


@pytest.mark.asyncio
async def test_preheat_sends_upcoming_comfort_target_to_direct_device(monkeypatch):
    """Eco 19 now, comfort 21.5 in one hour: the UFH thermostat must get 21.5 while MPC pre-heats."""
    resolver = _step_resolver(TargetTemps(19.0, None), TargetTemps(21.5, None), 3600)
    hass, ctrl = _controller(_room(), resolver, monkeypatch=monkeypatch)

    mode, _ = ctrl._evaluate_mpc(19.2, TargetTemps(19.0, None))
    assert mode == MODE_HEATING
    await ctrl.async_apply(mode, TargetTemps(19.0, None), power_fraction=0.8, current_temp=19.2)

    assert _sent(hass) == [21.5]
    # The hold compares against the targets in force, not the pre-heat target
    assert _active_targets["climate.dev"] == (19.0, None)


@pytest.mark.asyncio
async def test_preheat_target_includes_setpoint_offset(monkeypatch):
    resolver = _step_resolver(TargetTemps(19.0, None), TargetTemps(21.5, None), 3600)
    hass, ctrl = _controller(_room(offset=1.0), resolver, monkeypatch=monkeypatch)

    mode, _ = ctrl._evaluate_mpc(19.2, TargetTemps(19.0, None))
    await ctrl.async_apply(mode, TargetTemps(19.0, None), power_fraction=0.8, current_temp=19.2)

    assert _sent(hass) == [22.5]


@pytest.mark.asyncio
async def test_target_beyond_the_guard_window_is_not_a_lead(monkeypatch):
    """A comfort block three hours out is outside the 2 h UFH window: the current target goes out."""
    resolver = _step_resolver(TargetTemps(19.0, None), TargetTemps(21.5, None), 3 * 3600)
    hass, ctrl = _controller(_room(), resolver, monkeypatch=monkeypatch)

    mode, _ = ctrl._evaluate_mpc(18.0, TargetTemps(19.0, None))
    await ctrl.async_apply(mode, TargetTemps(19.0, None), power_fraction=0.8, current_temp=18.0)

    assert _sent(hass) == [19.0]


@pytest.mark.asyncio
async def test_lower_upcoming_target_does_not_lower_the_setpoint(monkeypatch):
    """Comfort now, eco later: heating keeps the current target (no early setback)."""
    resolver = _step_resolver(TargetTemps(21.5, None), TargetTemps(19.0, None), 1800)
    hass, ctrl = _controller(_room(), resolver, monkeypatch=monkeypatch)

    mode, _ = ctrl._evaluate_mpc(20.0, TargetTemps(21.5, None))
    await ctrl.async_apply(mode, TargetTemps(21.5, None), power_fraction=0.8, current_temp=20.0)

    assert _sent(hass) == [21.5]


@pytest.mark.asyncio
async def test_schedule_off_blocks_are_ignored(monkeypatch):
    """Blocks without a heat target (schedule off) are filled with the room temperature for the
    optimizer; that fill must not become the direct setpoint."""
    resolver = _step_resolver(TargetTemps(19.0, None), TargetTemps(None, None), 1800)
    hass, ctrl = _controller(_room(), resolver, monkeypatch=monkeypatch)

    mode, _ = ctrl._evaluate_mpc(18.0, TargetTemps(19.0, None))
    await ctrl.async_apply(mode, TargetTemps(19.0, None), power_fraction=0.8, current_temp=18.0)

    assert _sent(hass) == [19.0]


@pytest.mark.asyncio
async def test_proportional_device_is_unchanged(monkeypatch):
    resolver = _step_resolver(TargetTemps(19.0, None), TargetTemps(21.5, None), 3600)
    hass, ctrl = _controller(_room(mode="proportional"), resolver, monkeypatch=monkeypatch)

    mode, _ = ctrl._evaluate_mpc(19.2, TargetTemps(19.0, None))
    await ctrl.async_apply(mode, TargetTemps(19.0, None), power_fraction=0.5, current_temp=19.2)

    # proportional boost from the room temperature, not the lead target
    assert _sent(hass) == [24.5]


@pytest.mark.asyncio
async def test_precool_sends_upcoming_cool_target(monkeypatch):
    """Eco cool 27 now, comfort 24 in 20 min (inside the 30 min AC window): a direct AC that pre-cools gets 24."""
    resolver = _step_resolver(TargetTemps(None, 27.0), TargetTemps(None, 24.0), 1200)
    room = _room(device_type="ac", climate_mode="cool_only", system="")
    hass, ctrl = _controller(room, resolver, system="", plan_action=MODE_COOLING, lookahead=6, monkeypatch=monkeypatch)
    ctrl.previous_mode = MODE_COOLING  # already running: no start hysteresis

    mode, _ = ctrl._evaluate_mpc(27.5, TargetTemps(None, 27.0))
    assert mode == MODE_COOLING
    await ctrl.async_apply(mode, TargetTemps(None, 27.0), power_fraction=0.8, current_temp=27.5)

    assert _sent(hass) == [24.0]


@pytest.mark.asyncio
async def test_idle_setback_keeps_the_current_target(monkeypatch):
    """The lead only applies to active commands; a setback device in IDLE keeps the current target."""
    resolver = _step_resolver(TargetTemps(19.0, None), TargetTemps(21.5, None), 3600)
    room = _room()
    room["devices"][0]["idle_action"] = "setback"
    hass, ctrl = _controller(room, resolver, monkeypatch=monkeypatch)

    ctrl._evaluate_mpc(19.2, TargetTemps(19.0, None))
    await ctrl.async_apply(MODE_IDLE, TargetTemps(19.0, None), power_fraction=0.0, current_temp=19.2)

    assert all(t < 21.5 for t in _sent(hass))


@pytest.mark.asyncio
async def test_bangbang_has_no_lead(monkeypatch):
    resolver = _step_resolver(TargetTemps(19.0, None), TargetTemps(21.5, None), 3600)
    hass, ctrl = _controller(_room(), resolver, monkeypatch=monkeypatch)
    ctrl._lead_heat = 21.5  # left over from an earlier evaluation
    ctrl._mpc_enabled = False

    mode, _ = await ctrl.async_evaluate(18.0, TargetTemps(19.0, None))
    assert mode == MODE_HEATING
    await ctrl.async_apply(mode, TargetTemps(19.0, None), power_fraction=1.0, current_temp=18.0)

    assert _sent(hass) == [19.0]


def test_direct_target_public_helper(monkeypatch):
    resolver = _step_resolver(TargetTemps(19.0, 26.0), TargetTemps(21.5, 24.0), 1800)
    _, ctrl = _controller(_room(climate_mode="auto"), resolver, monkeypatch=monkeypatch)
    assert ctrl.direct_target(MODE_HEATING, 19.0) == 19.0  # nothing evaluated yet
    ctrl._evaluate_mpc(19.2, TargetTemps(19.0, 26.0))
    assert ctrl.direct_target(MODE_HEATING, 19.0) == 21.5
    assert ctrl.direct_target(MODE_COOLING, 26.0) == 24.0
    assert ctrl.direct_target(MODE_IDLE, 19.0) == 19.0


def test_display_shows_the_lead_target():
    assert (
        RoomMindCoordinator._compute_device_setpoint(
            MODE_HEATING, 0.8, 19.2, 19.0, True, all_direct=True, direct_offset=1.0, direct_target=21.5
        )
        == 22.5
    )
    assert RoomMindCoordinator._compute_device_setpoint(MODE_HEATING, 0.8, 19.2, 19.0, True, all_direct=True) == 19.0


@pytest.mark.asyncio
async def test_legacy_float_resolver_also_leads(monkeypatch):
    start = time.time()

    def resolver(ts: float) -> float | None:
        return 21.5 if ts >= start + 3600 else 19.0

    hass, ctrl = _controller(_room(), resolver, monkeypatch=monkeypatch)
    mode, _ = ctrl._evaluate_mpc(19.2, TargetTemps(19.0, 19.0))
    await ctrl.async_apply(mode, TargetTemps(19.0, None), power_fraction=0.8, current_temp=19.2)

    assert _sent(hass) == [21.5]


def test_orchestrated_display_shows_the_lead_target():
    plan = HeatSourcePlan(
        commands=[DeviceCommand("climate.dev", "primary", "thermostat", True, 0.8, "test")],
        active_sources="primary",
        reason="test",
    )
    shown = RoomMindCoordinator._compute_device_setpoint_orchestrated(
        plan, 19.2, 19.0, 30.0, 30.0, direct_eids={"climate.dev"}, direct_target=21.5
    )
    assert shown == 21.5


@pytest.mark.asyncio
@pytest.mark.parametrize(("override_hours", "expected"), [(3.0, 17.0), (1.0, 21.5)])
async def test_eco_override_is_not_overrun_by_the_comfort_target(monkeypatch, override_hours, expected):
    """The real resolver keeps the override over the horizon: only its end inside the window is a lead."""
    room = _room()
    room.update(
        comfort_heat=21.5,
        override_heat=17.0,
        override_cool=None,
        override_type="eco",
        override_until=time.time() + override_hours * 3600,
    )
    resolver = make_target_resolver(None, room, {})
    hass, ctrl = _controller(room, resolver, monkeypatch=monkeypatch)

    mode, _ = ctrl._evaluate_mpc(16.5, TargetTemps(17.0, None))
    await ctrl.async_apply(mode, TargetTemps(17.0, None), power_fraction=0.8, current_temp=16.5)

    assert _sent(hass) == [expected]


# ─── Live display of a pre-heat (hero "heats ahead for X from HH:MM") ─────────────


def test_preheat_names_the_upcoming_target_and_its_start(monkeypatch):
    resolver = _step_resolver(TargetTemps(19.0, None), TargetTemps(21.5, None), 3600)
    _, ctrl = _controller(_room(), resolver, monkeypatch=monkeypatch)
    before = time.time()

    mode, _ = ctrl._evaluate_mpc(19.2, TargetTemps(19.0, None))

    assert mode == MODE_HEATING
    assert ctrl.preheat is not None
    assert ctrl.preheat["mode"] == MODE_HEATING
    assert ctrl.preheat["target"] == 21.5
    # the block start between two plan samples, not the next 5-min sample after it
    assert before + 3600 <= ctrl.preheat["at"] <= time.time() + 3600 + 10


def test_no_preheat_while_the_room_is_below_the_target_in_force(monkeypatch):
    """Below eco the run heats for the current target anyway; naming the comfort block would be wrong."""
    resolver = _step_resolver(TargetTemps(19.0, None), TargetTemps(21.5, None), 3600)
    _, ctrl = _controller(_room(), resolver, monkeypatch=monkeypatch)

    ctrl._evaluate_mpc(18.5, TargetTemps(19.0, None))

    assert ctrl.preheat is None


def test_no_preheat_without_a_rise_or_beyond_the_guard_window(monkeypatch):
    flat = _step_resolver(TargetTemps(19.0, None), TargetTemps(19.0, None), 3600)
    _, ctrl = _controller(_room(), flat, monkeypatch=monkeypatch)
    ctrl._evaluate_mpc(19.2, TargetTemps(19.0, None))
    assert ctrl.preheat is None

    far = _step_resolver(TargetTemps(19.0, None), TargetTemps(21.5, None), 3 * 3600)
    _, ctrl = _controller(_room(), far, monkeypatch=monkeypatch)
    ctrl._evaluate_mpc(19.2, TargetTemps(19.0, None))
    assert ctrl.preheat is None


def test_no_preheat_while_idle(monkeypatch):
    resolver = _step_resolver(TargetTemps(19.0, None), TargetTemps(21.5, None), 3600)
    _, ctrl = _controller(_room(), resolver, plan_action=MODE_IDLE, monkeypatch=monkeypatch)
    ctrl.preheat = {"mode": MODE_HEATING, "target": 21.5, "at": 0}  # left over from an earlier cycle

    mode, _ = ctrl._evaluate_mpc(21.8, TargetTemps(19.0, None))

    assert mode == MODE_IDLE
    assert ctrl.preheat is None


def test_precool_is_named_too(monkeypatch):
    resolver = _step_resolver(TargetTemps(None, 27.0), TargetTemps(None, 24.0), 1800)
    room = _room(device_type="ac", climate_mode="cool_only", system="")
    _, ctrl = _controller(room, resolver, system="", plan_action=MODE_COOLING, monkeypatch=monkeypatch)

    mode, _ = ctrl._evaluate_mpc(26.5, TargetTemps(None, 27.0))

    assert mode == MODE_COOLING
    assert ctrl.preheat is not None
    assert ctrl.preheat["mode"] == MODE_COOLING
    assert ctrl.preheat["target"] == 24.0


def test_preheat_display_rejects_a_missing_current_target():
    window = [TargetTemps(None, None), TargetTemps(21.0, None)]
    resolve = lambda ts: window[0]  # noqa: E731
    assert MPCController._preheat_display(MODE_HEATING, 19.0, window, 0.0, resolve) is None
    assert MPCController._preheat_display(MODE_HEATING, 19.0, [], 0.0, resolve) is None


def test_a_cheap_hour_is_no_preheat_even_when_the_price_ends(monkeypatch):
    """Expensive hour lowers the target now, the schedule stays flat: the end of the price stretch is no lead."""
    resolver = _step_resolver(TargetTemps(20.0, None), TargetTemps(21.0, None), 1800)
    _, ctrl = _controller(_room(), resolver, monkeypatch=monkeypatch)
    ctrl._schedule_target_resolver = lambda ts: TargetTemps(21.0, None)

    ctrl._evaluate_mpc(21.1, TargetTemps(20.0, None))

    assert ctrl.preheat is None
