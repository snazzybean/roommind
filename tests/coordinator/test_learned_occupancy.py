"""Coordinator tests for the predictive learned-occupancy schedule (opt-in)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.roommind.const import TargetTemps

from .conftest import (
    SAMPLE_ROOM,
    _create_coordinator,
    _make_store_mock,
    make_mock_states_get,
)


def _all_slots(value: float) -> dict[str, float]:
    return {f"{d},{s}": value for d in range(7) for s in range(24)}


def _priors_response(area_id: str, value: float) -> dict:
    return {
        "slot_minutes": 60,
        "areas": {"Area": {"area_id": area_id, "slot_minutes": 60, "slots": _all_slots(value)}},
    }


class TestLearnedPriorFetch:
    """_get_learned_priors / _get_learned_prior_matrix."""

    @pytest.mark.asyncio
    async def test_matrix_parsed_from_service(self, hass, mock_config_entry):
        hass.services.has_service = MagicMock(return_value=True)
        hass.services.async_call = AsyncMock(
            return_value={"areas": {"A": {"area_id": "soggiorno", "slots": {"0,8": 0.7}}}}
        )
        coordinator = _create_coordinator(hass, mock_config_entry)

        matrix, slot_minutes = await coordinator._get_learned_prior_matrix("soggiorno")
        assert matrix == {(0, 8): 0.7}
        assert slot_minutes == 60

    @pytest.mark.asyncio
    async def test_absent_service_returns_none(self, hass, mock_config_entry):
        hass.services.has_service = MagicMock(return_value=False)
        coordinator = _create_coordinator(hass, mock_config_entry)

        assert await coordinator._get_learned_priors() is None
        matrix, slot_minutes = await coordinator._get_learned_prior_matrix("soggiorno")
        assert matrix is None
        assert slot_minutes == 60

    @pytest.mark.asyncio
    async def test_service_error_falls_back(self, hass, mock_config_entry):
        hass.services.has_service = MagicMock(return_value=True)
        hass.services.async_call = AsyncMock(side_effect=RuntimeError("boom"))
        coordinator = _create_coordinator(hass, mock_config_entry)

        assert await coordinator._get_learned_priors() is None

    @pytest.mark.asyncio
    async def test_response_is_cached_within_ttl(self, hass, mock_config_entry):
        call = AsyncMock(return_value={"areas": {}})
        hass.services.has_service = MagicMock(return_value=True)
        hass.services.async_call = call
        coordinator = _create_coordinator(hass, mock_config_entry)

        await coordinator._get_learned_priors()
        await coordinator._get_learned_priors()
        assert call.call_count == 1  # second call served from cache


class TestLearnedTargetResolution:
    """_resolve_target_temps learned-window branch + full cycle."""

    def test_resolve_target_temps_learned_comfort(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        matrix = {(d, s): 0.9 for d in range(7) for s in range(24)}  # always occupied
        result = coordinator._resolve_target_temps(
            SAMPLE_ROOM, {}, prior_matrix=matrix, prior_threshold=0.5, prior_slot_minutes=60
        )
        assert result == TargetTemps(21.0, 24.0)

    def test_resolve_target_temps_learned_eco(self, hass, mock_config_entry):
        coordinator = _create_coordinator(hass, mock_config_entry)
        matrix = {(d, s): 0.1 for d in range(7) for s in range(24)}  # never occupied
        result = coordinator._resolve_target_temps(
            SAMPLE_ROOM, {}, prior_matrix=matrix, prior_threshold=0.5, prior_slot_minutes=60
        )
        assert result == TargetTemps(17.0, 27.0)

    @pytest.mark.asyncio
    async def test_full_cycle_uses_learned_schedule(self, hass, mock_config_entry):
        room = {
            **SAMPLE_ROOM,
            "schedules": [],  # no manual schedule; learned drives the window
            "use_learned_schedule": True,
            "learned_occupancy_area_id": "soggiorno",
        }
        store = _make_store_mock({"living_room_abc12345": room})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=make_mock_states_get())
        hass.services.has_service = MagicMock(return_value=True)

        async def _call(domain, service, *args, **kwargs):
            if domain == "area_occupancy" and service == "get_time_priors":
                return _priors_response("soggiorno", 0.9)  # always occupied → comfort
            return {}

        hass.services.async_call = AsyncMock(side_effect=_call)

        coordinator = _create_coordinator(hass, mock_config_entry)
        data = await coordinator._async_update_data()

        room_state = data["rooms"]["living_room_abc12345"]
        assert room_state["target_temp"] == 21.0  # comfort from learned occupancy
