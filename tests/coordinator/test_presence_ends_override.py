"""presence_ends_override: everyone leaving ends the override after a delay, arriving never does."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.const import PRESENCE_OVERRIDE_END_DELAY_S

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, _presence_states_get

AREA = "living_room_abc12345"
END = {"presence_enabled": True, "presence_persons": ["person.anna"], "presence_ends_override": True}


def _override_room(**extra):
    return {
        **SAMPLE_ROOM,
        "override_heat": 25.0,
        "override_cool": 26.0,
        "override_until": time.time() + 6 * 3600,
        "override_type": "boost",
        **extra,
    }


@pytest.fixture
def setup(hass, mock_config_entry):
    store = _make_store_mock({AREA: _override_room()})
    store.async_update_room = AsyncMock()
    hass.data = {"roommind": {"store": store}}
    tasks: list = []
    hass.async_create_task = MagicMock(side_effect=tasks.append)
    coordinator = _create_coordinator(hass, mock_config_entry)

    def run(room, settings, *home, now=None):
        """One cycle for *room* as the store holds it, background writes run right after."""
        store.get_room.return_value = room
        hass.states.get = MagicMock(side_effect=_presence_states_get(*home))
        with patch("custom_components.roommind.coordinator.time.time", return_value=now or 1_000_000.0):
            result = coordinator._end_override_when_everyone_left(room, settings)
        while tasks:
            _drain(tasks.pop(0))
        return result

    return coordinator, store, run


def _drain(coro):
    """Run a background write on its own loop; asyncio.run would unset the test's current loop."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(coro)
    finally:
        loop.close()


def _writes(store):
    return [call.args[1] for call in store.async_update_room.call_args_list]


def test_someone_home_arms_the_override(setup):
    _, store, run = setup
    room = run(_override_room(), END, "person.anna")
    assert room["override_home_seen"] is True
    assert room["override_heat"] == 25.0
    assert _writes(store) == [{"override_home_seen": True}]


def test_already_armed_writes_nothing_while_home(setup):
    _, store, run = setup
    run(_override_room(override_home_seen=True), END, "person.anna")
    assert _writes(store) == []


def test_leaving_ends_it_after_the_delay(setup):
    _, store, run = setup
    room = _override_room(override_home_seen=True)
    t0 = 1_000_000.0
    assert run(room, END, now=t0)["override_heat"] == 25.0
    assert run(room, END, now=t0 + PRESENCE_OVERRIDE_END_DELAY_S - 1)["override_heat"] == 25.0
    ended = run(room, END, now=t0 + PRESENCE_OVERRIDE_END_DELAY_S)
    assert ended["override_heat"] is None and ended["override_cool"] is None
    assert ended["override_until"] is None and ended["override_type"] is None
    assert _writes(store) == [
        {"override_heat": None, "override_cool": None, "override_until": None, "override_type": None}
    ]


def test_flapping_restarts_the_wait(setup):
    _, store, run = setup
    room = _override_room(override_home_seen=True)
    t0 = 1_000_000.0
    run(room, END, now=t0)
    run(room, END, "person.anna", now=t0 + 300)
    assert run(room, END, now=t0 + 400)["override_heat"] == 25.0
    assert run(room, END, now=t0 + 400 + PRESENCE_OVERRIDE_END_DELAY_S - 1)["override_heat"] == 25.0
    assert _writes(store) == []


def test_set_while_away_survives_the_empty_house(setup):
    _, store, run = setup
    room = _override_room(override_home_seen=False)
    assert run(room, END, now=1_000_000.0)["override_heat"] == 25.0
    assert run(room, END, now=1_000_000.0 + 10 * PRESENCE_OVERRIDE_END_DELAY_S)["override_heat"] == 25.0
    assert _writes(store) == []


def test_arriving_never_ends_it(setup):
    _, store, run = setup
    room = run(_override_room(override_home_seen=False), END, "person.anna")
    assert room["override_heat"] == 25.0
    assert _writes(store) == [{"override_home_seen": True}]


def test_unknown_presence_neither_arms_nor_ends(setup):
    coordinator, store, run = setup
    room = _override_room(override_home_seen=True)
    coordinator.hass.states.get = MagicMock(return_value=MagicMock(state="unavailable"))
    with patch("custom_components.roommind.coordinator.time.time", return_value=1_000_000.0):
        coordinator._end_override_when_everyone_left(room, END)
    assert AREA not in coordinator._override_away_since
    unarmed = _override_room(override_home_seen=False)
    with patch("custom_components.roommind.coordinator.time.time", return_value=1_000_000.0):
        assert coordinator._end_override_when_everyone_left(unarmed, END) is unarmed
    assert _writes(store) == []


@pytest.mark.parametrize(
    "settings",
    [
        {"presence_enabled": True, "presence_persons": ["person.anna"]},
        {"presence_enabled": True, "presence_persons": ["person.anna"], "presence_clears_override": True},
    ],
)
def test_keep_and_pause_never_end_it(setup, settings):
    _, store, run = setup
    room = _override_room(override_home_seen=True)
    assert run(room, settings, now=1_000_000.0)["override_heat"] == 25.0
    assert run(room, settings, now=1_000_000.0 + 10 * PRESENCE_OVERRIDE_END_DELAY_S)["override_heat"] == 25.0
    assert _writes(store) == []


def test_room_ignoring_presence_keeps_it(setup):
    _, store, run = setup
    room = _override_room(override_home_seen=True, ignore_presence=True)
    run(room, END, now=1_000_000.0)
    assert run(room, END, now=1_000_000.0 + 2 * PRESENCE_OVERRIDE_END_DELAY_S)["override_heat"] == 25.0
    assert _writes(store) == []


def test_no_override_drops_the_wait(setup):
    coordinator, _, run = setup
    run(_override_room(override_home_seen=True), END, now=1_000_000.0)
    assert AREA in coordinator._override_away_since
    run({**SAMPLE_ROOM}, END, now=1_000_001.0)
    assert AREA not in coordinator._override_away_since


def test_restart_counts_from_the_first_cycle_and_ends_an_armed_override(setup):
    """Leaving while HA was off: the persisted flag arms it, the wait starts with the new coordinator."""
    coordinator, store, run = setup
    coordinator._override_away_since.clear()
    room = _override_room(override_home_seen=True)
    assert run(room, END, now=2_000_000.0)["override_heat"] == 25.0
    assert run(room, END, now=2_000_000.0 + PRESENCE_OVERRIDE_END_DELAY_S)["override_heat"] is None
    assert len(_writes(store)) == 1


def test_an_override_set_meanwhile_is_not_cleared(setup):
    """The cycle read the old override; one set from away before the clear runs stays."""
    coordinator, store, _ = setup
    held = _override_room(override_home_seen=True)
    coordinator._override_away_since[AREA] = 1_000_000.0 - PRESENCE_OVERRIDE_END_DELAY_S
    store.get_room.return_value = _override_room(override_heat=22.0, override_home_seen=False)
    coordinator.hass.states.get = MagicMock(side_effect=_presence_states_get())
    tasks: list = []
    coordinator.hass.async_create_task = MagicMock(side_effect=tasks.append)
    with patch("custom_components.roommind.coordinator.time.time", return_value=1_000_000.0):
        assert coordinator._end_override_when_everyone_left(held, END)["override_heat"] is None
    _drain(tasks.pop())
    assert _writes(store) == []
    store.get_room.return_value = None
    with patch("custom_components.roommind.coordinator.time.time", return_value=1_000_000.0):
        coordinator._override_away_since[AREA] = 0.0
        coordinator._end_override_when_everyone_left(held, END)
    _drain(tasks.pop())
    assert _writes(store) == []


@pytest.mark.asyncio
async def test_cycle_ends_the_override_and_follows_presence_away(hass, mock_config_entry):
    room = _override_room(override_home_seen=True)
    store = _make_store_mock({AREA: room}, settings=END)
    store.async_update_room = AsyncMock()
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(side_effect=_presence_states_get())
    hass.services.async_call = AsyncMock()
    hass.async_create_task = MagicMock(side_effect=lambda coro: coro.close())
    coordinator = _create_coordinator(hass, mock_config_entry)
    coordinator._override_away_since[AREA] = time.time() - PRESENCE_OVERRIDE_END_DELAY_S
    data = await coordinator._async_update_data()
    live = data["rooms"][AREA]
    assert live["override_active"] is False
    assert live["target_temp"] == 17.0  # eco while away
