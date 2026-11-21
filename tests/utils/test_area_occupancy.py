"""Tests for Area Occupancy Detection as an occupancy source."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.util import dt as dt_util

from custom_components.roommind.const import AREA_OCCUPANCY_PRIORS_TTL_SECONDS
from custom_components.roommind.utils.area_occupancy import (
    AreaOccupancySource,
    AreaPriors,
    area_ids,
    parse_area_priors,
)

ROOM = {"use_learned_schedule": True, "learned_occupancy_area_id": "bath", "learned_occupancy_threshold": None}


def _response(**area_overrides):
    """A get_time_priors response with one area, 'bath', used Monday 07:00-08:00."""
    area = {
        "area_id": "bath",
        "global_prior": 0.04,
        "slot_minutes": 60,
        "slots": {"0,7": 0.9, "0,8": 0.9},  # evidence-conditioned: must not be read
        "slots_raw": {"0,6": 0.05, "0,7": 0.3, "0,8": 0.02, "1,7": 0.25},
        "data_points": {"0,6": 4, "0,7": 4, "0,8": 4, "1,7": 0},
    }
    area.update(area_overrides)
    return {"areas": {"entry_1": area}}


def _monday(hour: int) -> float:
    return datetime(2025, 1, 6, hour, 30, tzinfo=dt_util.DEFAULT_TIME_ZONE).timestamp()


class TestParseAreaPriors:
    def test_reads_slots_raw_and_drops_unobserved_slots(self):
        priors = parse_area_priors(_response(), "bath")
        assert priors is not None
        assert priors.slots == {(0, 6): 0.05, (0, 7): 0.3, (0, 8): 0.02}
        assert priors.global_prior == 0.04
        assert priors.slot_minutes == 60

    def test_without_data_points_every_slot_counts(self):
        priors = parse_area_priors(_response(data_points=None), "bath")
        assert priors is not None
        assert (1, 7) in priors.slots

    def test_unknown_area_or_bad_response_gives_none(self):
        assert parse_area_priors(_response(), "kitchen") is None
        assert parse_area_priors(None, "bath") is None
        assert parse_area_priors("oops", "bath") is None

    def test_without_slots_raw_gives_none(self):
        assert parse_area_priors(_response(slots_raw=None), "bath") is None

    def test_nothing_observed_gives_none(self):
        assert parse_area_priors(_response(data_points={"0,6": 0, "0,7": 0, "0,8": 0, "1,7": 0}), "bath") is None

    def test_malformed_keys_and_slot_width_are_ignored(self):
        priors = parse_area_priors(
            _response(slots_raw={"x": 0.5, "0,7": 0.3}, data_points=None, slot_minutes=7), "bath"
        )
        assert priors is not None
        assert priors.slots == {(0, 7): 0.3}
        assert priors.slot_minutes == 60


class TestAreaPriors:
    def test_probability_in_local_time(self):
        priors = parse_area_priors(_response(), "bath")
        assert priors.probability_at(_monday(7)) == 0.3
        assert priors.probability_at(_monday(12)) is None

    def test_automatic_threshold_is_relative_to_the_room_use(self):
        assert AreaPriors(slots={(0, 0): 0.1}, global_prior=0.04).automatic_threshold() == pytest.approx(0.12)

    def test_automatic_threshold_has_a_floor_and_a_cap(self):
        assert AreaPriors(slots={(0, 0): 0.1}, global_prior=0.01).automatic_threshold() == 0.1
        assert AreaPriors(slots={(0, 0): 0.9}, global_prior=0.4).automatic_threshold() == 0.5

    def test_automatic_threshold_without_global_prior_uses_the_slot_mean(self):
        assert AreaPriors(slots={(0, 0): 0.1, (0, 1): 0.0}).automatic_threshold() == pytest.approx(0.15)


def test_area_ids_are_sorted_and_unique():
    response = {"areas": {"a": {"area_id": "kitchen"}, "b": {"area_id": "bath"}, "c": {"area_id": "bath"}, "d": 3}}
    assert area_ids(response) == ["bath", "kitchen"]
    assert area_ids(None) == []


def _source(response=None, available=True, raises=None):
    hass = MagicMock()
    hass.services.has_service.return_value = available
    hass.services.async_call = AsyncMock(return_value=response, side_effect=raises)
    return AreaOccupancySource(hass), hass


class TestAreaOccupancySource:
    @pytest.mark.asyncio
    async def test_off_by_default(self):
        source, hass = _source(_response())
        assert await source.async_expected_occupancy({}) is None
        assert await source.async_expected_occupancy({"use_learned_schedule": True}) is None
        hass.services.async_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_expected_occupancy_with_the_automatic_threshold(self):
        source, _ = _source(_response())
        expected = await source.async_expected_occupancy(ROOM)
        assert expected is not None
        assert expected.threshold == pytest.approx(0.12)
        assert expected.expected_at(_monday(7)) is True
        assert expected.expected_at(_monday(6)) is False
        assert expected.expected_at(_monday(12)) is None

    @pytest.mark.asyncio
    async def test_manual_threshold_wins(self):
        source, _ = _source(_response())
        expected = await source.async_expected_occupancy({**ROOM, "learned_occupancy_threshold": 0.5})
        assert expected.threshold == 0.5
        assert expected.expected_at(_monday(7)) is False

    @pytest.mark.asyncio
    async def test_without_the_integration_the_room_keeps_its_schedule(self):
        source, hass = _source(_response(), available=False)
        assert await source.async_expected_occupancy(ROOM) is None
        hass.services.async_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_one_call_serves_every_room_until_the_cache_expires(self):
        source, hass = _source(_response())
        with patch("custom_components.roommind.utils.area_occupancy.time.time", return_value=1000.0):
            await source.async_expected_occupancy(ROOM)
            await source.async_expected_occupancy(ROOM)
        assert hass.services.async_call.await_count == 1
        later = 1000.0 + AREA_OCCUPANCY_PRIORS_TTL_SECONDS
        with patch("custom_components.roommind.utils.area_occupancy.time.time", return_value=later):
            await source.async_expected_occupancy(ROOM)
        assert hass.services.async_call.await_count == 2

    @pytest.mark.asyncio
    async def test_failed_call_keeps_the_last_good_priors(self):
        source, hass = _source(_response())
        with patch("custom_components.roommind.utils.area_occupancy.time.time", return_value=1000.0):
            assert await source.async_expected_occupancy(ROOM) is not None
        hass.services.async_call.side_effect = RuntimeError("restarting")
        later = 1000.0 + AREA_OCCUPANCY_PRIORS_TTL_SECONDS
        with patch("custom_components.roommind.utils.area_occupancy.time.time", return_value=later):
            assert await source.async_expected_occupancy(ROOM) is not None

    @pytest.mark.asyncio
    async def test_failed_first_call_falls_back_to_the_schedule(self):
        source, _ = _source(raises=RuntimeError("boom"))
        assert await source.async_expected_occupancy(ROOM) is None

    @pytest.mark.asyncio
    async def test_service_gone_drops_the_cached_priors(self):
        source, hass = _source(_response())
        assert await source.async_expected_occupancy(ROOM) is not None
        hass.services.has_service.return_value = False
        assert await source.async_expected_occupancy(ROOM) is None
