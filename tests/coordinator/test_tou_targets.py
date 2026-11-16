"""Tests for Time-of-Use integration in the coordinator update cycle."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.roommind.const import TOU_TIER_PEAK, TOU_TIER_ULTRA_LOW
from tests.conftest import make_mock_states_get

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock


def _states_with(mapping: dict[str, str]):
    """Standard states, overridden by *mapping* (state string per entity_id)."""
    base = make_mock_states_get()
    extra: dict[str, MagicMock] = {}
    for eid, state in mapping.items():
        mock = MagicMock()
        mock.state = state
        mock.attributes = {"unit_of_measurement": "CAD/kWh"}
        extra[eid] = mock

    def _get(entity_id: str):
        # A configured schedule is always reachable but empty: the coordinator
        # then resolves the comfort/eco fallbacks, which is what these tests check.
        if entity_id.startswith("schedule."):
            s = MagicMock()
            s.state = "on"
            s.attributes = {}
            return s
        if entity_id in extra:
            return extra[entity_id]
        return base(entity_id)

    return _get


async def _run_cycle(hass, mock_config_entry, *, room, settings, states):
    store = _make_store_mock({room["area_id"]: room}, settings)
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(side_effect=_states_with(states))
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    data = await coordinator._async_update_data()
    return data, coordinator


@pytest.mark.asyncio
async def test_store_relaxes_peak_target(hass, mock_config_entry) -> None:
    """A storing room on PEAK resolves its heat target to the relaxation floor."""
    room = {**SAMPLE_ROOM, "tou_store_enabled": True}
    data, _ = await _run_cycle(
        hass,
        mock_config_entry,
        room=room,
        settings={"tou_enabled": True, "tou_period_entity": "sensor.tou_period"},
        states={"sensor.tou_period": "ulo_on_peak"},
    )
    state = data["rooms"][room["area_id"]]
    assert state["heat_target"] == 18.0  # comfort 21 - swing 3, above eco 17
    assert state["cool_target"] == 27.0  # drifts to the eco cooling ceiling
    snap = data["tou"]
    assert snap["enabled"] is True
    assert snap["tier"] == TOU_TIER_PEAK


@pytest.mark.asyncio
async def test_tou_off_leaves_target_untouched(hass, mock_config_entry) -> None:
    """Without tou_enabled the cycle ignores period entities entirely."""
    room = {**SAMPLE_ROOM, "tou_store_enabled": True}
    data, _ = await _run_cycle(
        hass,
        mock_config_entry,
        room=room,
        settings={"tou_period_entity": "sensor.tou_period"},
        states={"sensor.tou_period": "ulo_on_peak"},
    )
    state = data["rooms"][room["area_id"]]
    assert state["heat_target"] == SAMPLE_ROOM["comfort_heat"]
    assert "tou" not in data


@pytest.mark.asyncio
async def test_unopted_room_ignores_active_peak(hass, mock_config_entry) -> None:
    """Rooms without the store toggle keep their schedule during PEAK."""
    room = dict(SAMPLE_ROOM)
    data, _ = await _run_cycle(
        hass,
        mock_config_entry,
        room=room,
        settings={"tou_enabled": True, "tou_period_entity": "sensor.tou_period"},
        states={"sensor.tou_period": "ulo_on_peak"},
    )
    assert data["rooms"][room["area_id"]]["heat_target"] == SAMPLE_ROOM["comfort_heat"]


@pytest.mark.asyncio
async def test_ultra_low_without_future_view_does_not_raise(hass, mock_config_entry) -> None:
    """A cheap tier with no timeline ahead relaxes nothing and raises nothing."""
    room = {**SAMPLE_ROOM, "tou_store_enabled": True}
    data, _ = await _run_cycle(
        hass,
        mock_config_entry,
        room=room,
        settings={"tou_enabled": True, "tou_period_entity": "sensor.tou_period"},
        states={"sensor.tou_period": "ulo_overnight"},
    )
    state = data["rooms"][room["area_id"]]
    assert state["heat_target"] == 21.0  # comfort stands: the pre-charge needs a run to aim at
    assert data["tou"]["tier"] == TOU_TIER_ULTRA_LOW


@pytest.mark.asyncio
async def test_override_outranks_peak_setback(hass, mock_config_entry) -> None:
    """A manual boost is never shaved by the tariff."""
    room = {
        **SAMPLE_ROOM,
        "tou_store_enabled": True,
        "override_heat": 24.0,
        "override_cool": None,
        "override_until": None,
        "override_type": "boost",
    }
    data, _ = await _run_cycle(
        hass,
        mock_config_entry,
        room=room,
        settings={"tou_enabled": True, "tou_period_entity": "sensor.tou_period"},
        states={"sensor.tou_period": "ulo_on_peak"},
    )
    assert data["rooms"][room["area_id"]]["heat_target"] == 24.0
