"""Rooms that opted in move their schedule target with the electricity price."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.roommind.const import TargetTemps
from custom_components.roommind.utils.price_utils import PriceSignal, PriceSlot
from custom_components.roommind.utils.schedule_utils import make_target_resolver, price_shifted

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get

AREA = "living_room_abc12345"
OVERRIDE = {"override_heat": 23.0, "override_cool": 25.0, "override_until": None, "override_type": "custom"}


async def _cycle(hass, entry, room, price=("38", None), settings=None):
    store = _make_store_mock({AREA: room})
    store.get_settings.return_value = {"price_entity": "binary_sensor.cheap", **(settings or {})}
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(
        side_effect=make_mock_states_get(schedule_state="on", extra={"binary_sensor.cheap": price})
    )
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, entry)
    data = await coordinator._async_update_data()
    return coordinator, data["rooms"][AREA]


@pytest.mark.asyncio
async def test_cheap_switch_lifts_the_schedule_target(hass, mock_config_entry):
    _, state = await _cycle(hass, mock_config_entry, {**SAMPLE_ROOM, "price_shift": 1.0}, ("on", None))
    assert state["heat_target"] == 22.0
    assert state["cool_target"] == 23.0
    assert state["price_shift_heat"] == 1.0
    assert state["price_shift_cool"] == -1.0
    assert state["price_level"] == "cheap"


@pytest.mark.asyncio
async def test_room_without_opt_in_is_untouched(hass, mock_config_entry):
    _, state = await _cycle(hass, mock_config_entry, SAMPLE_ROOM, ("on", None))
    assert state["heat_target"] == 21.0
    assert state["price_shift_heat"] == 0.0


@pytest.mark.asyncio
async def test_override_is_not_shifted(hass, mock_config_entry):
    _, state = await _cycle(hass, mock_config_entry, {**SAMPLE_ROOM, **OVERRIDE, "price_shift": 1.0}, ("on", None))
    assert state["heat_target"] == 23.0
    assert state["price_shift_heat"] == 0.0


@pytest.mark.asyncio
async def test_status_and_orchestration_level(hass, mock_config_entry):
    coordinator, _ = await _cycle(hass, mock_config_entry, SAMPLE_ROOM, ("on", None))
    assert coordinator.price_status()["kind"] == "switch"
    assert coordinator.price_signal.current_level == "cheap"
    assert coordinator._price_level_for({"heat_source_price_aware": True}) == "cheap"
    assert coordinator._price_level_for({}) is None


@pytest.mark.asyncio
async def test_price_history_is_read_from_the_recorded_rows(hass, mock_config_entry):
    coordinator, _ = await _cycle(hass, mock_config_entry, SAMPLE_ROOM, ("on", None))
    coordinator._history_store = MagicMock()
    coordinator._history_store.read_detail.return_value = [
        {"timestamp": "100", "price": "20.5"},
        {"timestamp": "200", "price": ""},
    ]
    coordinator._history_store.read_history.return_value = [{"timestamp": "50", "price": "19"}]
    hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *a: fn(*a))
    assert await coordinator._async_load_price_history() == [(100.0, 20.5), (50.0, 19.0)]
    coordinator._history_store = None
    assert await coordinator._async_load_price_history() == []


def _signal(now, levels):
    """Hourly signal: price 10 cheap, 20 normal, 30 expensive from ``now`` on."""
    prices = {"cheap": 10.0, "normal": 20.0, "expensive": 30.0}
    hour = 3600 * int(now // 3600)
    slots = [PriceSlot(hour + i * 3600, hour + (i + 1) * 3600, prices[lv]) for i, lv in enumerate(levels)]
    return PriceSignal(slots=slots, thresholds=(10.0, 30.0), now=now)


def test_resolver_shifts_the_horizon_like_the_current_cycle():
    now = time.time()
    signal = _signal(now, ["cheap", "expensive", "normal"])
    room = {**SAMPLE_ROOM, "schedules": [], "price_shift": 0.5}
    resolver = make_target_resolver(None, room, {}, price_signal=signal)
    hour = 3600 * int(now // 3600)
    assert resolver(hour + 600) == TargetTemps(21.5, 23.5)
    assert resolver(hour + 3600 + 600) == TargetTemps(20.5, 24.5)
    assert resolver(hour + 7200 + 600) == TargetTemps(21.0, 24.0)


def test_resolver_leaves_away_vacant_vacation_and_timed_override_alone():
    now = time.time()
    signal = _signal(now, ["expensive"] * 4)
    room = {**SAMPLE_ROOM, "schedules": [], "price_shift": 1.0}
    hour = 3600 * int(now // 3600)
    ts = hour + 600
    for kwargs in ({"presence_away": True}, {"room_vacant": True}):
        assert make_target_resolver(None, room, {}, price_signal=signal, **kwargs)(ts).heat != 20.0
    vacation = {"vacation_until": now + 86400, "vacation_temp": 15.0}
    assert make_target_resolver(None, room, vacation, price_signal=signal)(ts) == TargetTemps(15.0, 27.0)
    timed = {**room, **OVERRIDE, "override_until": hour + 7200}
    resolver = make_target_resolver(None, timed, {}, price_signal=signal)
    assert resolver(ts).heat == 23.0
    assert resolver(hour + 7200 + 600).heat == 20.0


def test_price_shifted_without_signal_or_outdoor_room():
    targets = TargetTemps(21.0, 24.0)
    args = {"presence_away": False, "room_vacant": False}
    assert price_shifted(targets, 0.0, {"price_shift": 1.0}, {}, None, **args) == (targets, (0.0, 0.0))
    signal = _signal(time.time(), ["cheap", "expensive"])
    outdoor = {"price_shift": 1.0, "is_outdoor": True}
    assert price_shifted(targets, time.time(), outdoor, {}, signal, **args) == (targets, (0.0, 0.0))


def test_band_in_force_takes_the_price_shift_off_again():
    from custom_components.roommind.utils.schedule_utils import band_in_force

    live = {
        "heat_target": 24.0,
        "cool_target": 23.0,
        "price_shift_heat": 1.0,
        "price_shift_cool": -1.0,
        "mold_prevention_active": True,
        "mold_prevention_delta": 2.0,
    }
    assert band_in_force({}, live) == (21.0, 24.0)


@pytest.mark.asyncio
@pytest.mark.parametrize(("shift", "expect_schedule"), [(1.0, True), (0.0, False)])
async def test_controller_gets_the_unshifted_schedule_only_for_price_rooms(
    hass, mock_config_entry, monkeypatch, shift, expect_schedule
):
    from custom_components.roommind.control import mpc_controller

    seen: list = []
    real_init = mpc_controller.MPCController.__init__

    def spy(self, *args, **kwargs):
        seen.append(kwargs.get("schedule_target_resolver"))
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(mpc_controller.MPCController, "__init__", spy)
    await _cycle(hass, mock_config_entry, {**SAMPLE_ROOM, "price_shift": shift}, ("on", None))
    assert seen
    resolver = seen[0]
    if not expect_schedule:
        assert resolver is None
        return
    # Cheap switch: the room's target is charged to 22, the schedule stays at 21
    assert resolver(time.time()).heat == 21.0
