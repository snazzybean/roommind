"""Integration: MPC controller behavior including preheating and proportional control."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.util import dt as dt_util

from custom_components.roommind.control.thermal_model import RoomModelManager

from .conftest import make_hass_states, setup_room


def _train_model_manager(model_manager: RoomModelManager, area_id: str) -> None:
    """Feed the model manager enough data so MPC activates.

    Simulates alternating idle and heating cycles so both mode counts
    exceed the minimum thresholds (60 idle, 20 heating).
    """
    T_outdoor = 5.0
    dt = 3.0  # minutes

    # Idle observations: temp slowly drifting down
    temp = 20.0
    for _ in range(70):
        model_manager.update(area_id, temp, T_outdoor, "idle", dt)
        temp -= 0.02  # slow drift

    # Heating observations: temp rising
    temp = 18.0
    for _ in range(30):
        model_manager.update(area_id, temp, T_outdoor, "heating", dt)
        temp += 0.1


def _make_schedule_service_mock(schedule_blocks: dict | None = None):
    """Create an async_call mock that returns schedule blocks for schedule.get_schedule.

    Other service calls (climate.*) pass through to a plain AsyncMock.
    """
    base_mock = AsyncMock()

    async def _async_call(domain, service, data=None, **kwargs):
        if domain == "schedule" and service == "get_schedule":
            entity_id = (data or {}).get("entity_id", "")
            if schedule_blocks is not None:
                return {entity_id: schedule_blocks}
            return None
        return await base_mock(domain, service, data, **kwargs)

    mock = AsyncMock(side_effect=_async_call)
    mock._base = base_mock  # keep reference for assertions
    return mock


def _make_schedule_blocks_at(hour: int, minute: int, duration_hours: int, day_name: str):
    """Create schedule blocks dict for a specific time on a given weekday."""
    end_hour = hour + duration_hours
    return {
        day_name: [
            {
                "from": f"{hour:02d}:{minute:02d}:00",
                "to": f"{end_hour:02d}:{minute:02d}:00",
            }
        ]
    }


@pytest.fixture
def frozen_ts():
    """Epoch for Monday 2026-03-09 10:00:00 in HA's configured timezone.

    Built at test time from ``dt_util.DEFAULT_TIME_ZONE`` (set per-test by the
    autouse ``_ha_default_timezone`` fixture) rather than as a naive module-level
    constant. Schedule blocks are authored in HA-local wall-clock time, so the
    frozen instant must map to 10:00 Monday in the *same* timezone the resolver
    uses — otherwise the schedule-window assertions only hold when host TZ == HA
    TZ. See #318.
    """
    return datetime(2026, 3, 9, 10, 0, 0, tzinfo=dt_util.DEFAULT_TIME_ZONE).timestamp()


# Schedule block that covers 06:00-22:00 on Monday (frozen time is inside it)
ACTIVE_SCHEDULE = _make_schedule_blocks_at(6, 0, 16, "monday")

# Schedule block that starts at 10:10 on Monday (10 min after frozen time)
# Within the 6-block (30 min) MPC lookahead so the optimizer sees it coming
UPCOMING_SCHEDULE = _make_schedule_blocks_at(10, 10, 8, "monday")


class TestMPCActivation:
    @pytest.mark.asyncio
    async def test_mpc_activates_after_training(self, coordinator, real_store, frozen_ts):
        """After enough EKF observations, coordinator should use MPC (not bang-bang)."""
        await setup_room(real_store)
        _train_model_manager(coordinator._model_manager, "living_room")

        coordinator.hass.states.get = MagicMock(side_effect=make_hass_states(temp="18.0"))
        coordinator.hass.services.async_call = _make_schedule_service_mock(ACTIVE_SCHEDULE)

        with patch("time.time", return_value=frozen_ts):
            data = await coordinator._async_update_data()

        room = data["rooms"]["living_room"]
        assert room["mode"] == "heating"
        assert "heating_power" in room
        assert 0 <= room["heating_power"] <= 100

    @pytest.mark.asyncio
    async def test_mpc_proportional_power_varies_with_distance(self, coordinator, real_store, frozen_ts):
        """MPC power fraction should be higher when further from target."""
        await setup_room(real_store)
        _train_model_manager(coordinator._model_manager, "living_room")

        # Far from target (15C vs 21C target)
        coordinator.hass.states.get = MagicMock(side_effect=make_hass_states(temp="15.0"))
        coordinator.hass.services.async_call = _make_schedule_service_mock(ACTIVE_SCHEDULE)

        with patch("time.time", return_value=frozen_ts):
            data_far = await coordinator._async_update_data()
        hp_far = data_far["rooms"]["living_room"]["heating_power"]

        # Close to target (20.5C vs 21C target)
        coordinator.hass.states.get = MagicMock(side_effect=make_hass_states(temp="20.5"))
        coordinator.hass.services.async_call = _make_schedule_service_mock(ACTIVE_SCHEDULE)

        with patch("time.time", return_value=frozen_ts):
            data_close = await coordinator._async_update_data()
        hp_close = data_close["rooms"]["living_room"]["heating_power"]

        # Power should be higher when far from target
        assert hp_far >= hp_close

    @pytest.mark.asyncio
    async def test_mpc_idles_at_target(self, coordinator, real_store, frozen_ts):
        """When current temp is at or above target, MPC should idle."""
        await setup_room(real_store)
        _train_model_manager(coordinator._model_manager, "living_room")

        coordinator.hass.states.get = MagicMock(side_effect=make_hass_states(temp="21.5"))
        coordinator.hass.services.async_call = _make_schedule_service_mock(ACTIVE_SCHEDULE)

        with patch("time.time", return_value=frozen_ts):
            data = await coordinator._async_update_data()

        assert data["rooms"]["living_room"]["mode"] == "idle"


class TestMPCPreheating:
    @pytest.mark.asyncio
    async def test_preheating_before_schedule_on(self, coordinator, real_store, frozen_ts):
        """MPC should start heating before schedule turns on if it sees the transition.

        Scenario: it's 10:00 (schedule off -> eco 17C), schedule starts at 10:10
        (comfort 21C). Room is at 17C. MPC should pre-heat.
        """
        await setup_room(real_store)
        _train_model_manager(coordinator._model_manager, "living_room")

        # Schedule state "off" -> current target is eco (17C)
        coordinator.hass.states.get = MagicMock(side_effect=make_hass_states(temp="17.0", schedule_state="off"))
        # But read_schedule_blocks returns blocks showing comfort starts at 10:30
        coordinator.hass.services.async_call = _make_schedule_service_mock(UPCOMING_SCHEDULE)

        with patch("time.time", return_value=frozen_ts):
            data = await coordinator._async_update_data()

        room = data["rooms"]["living_room"]
        # MPC should decide to pre-heat: 17C -> 21C needed in 30 min
        assert room["mode"] == "heating"

    @pytest.mark.asyncio
    async def test_no_preheating_at_target(self, coordinator, real_store, frozen_ts):
        """When already at comfort temp, no preheating needed before schedule."""
        await setup_room(real_store)
        _train_model_manager(coordinator._model_manager, "living_room")

        # Already at comfort temp, schedule off
        coordinator.hass.states.get = MagicMock(side_effect=make_hass_states(temp="21.0", schedule_state="off"))
        coordinator.hass.services.async_call = _make_schedule_service_mock(UPCOMING_SCHEDULE)

        with patch("time.time", return_value=frozen_ts):
            data = await coordinator._async_update_data()

        assert data["rooms"]["living_room"]["mode"] == "idle"

    @pytest.mark.asyncio
    async def test_no_preheating_without_upcoming_blocks(self, coordinator, real_store, frozen_ts):
        """Without upcoming schedule blocks, MPC sees constant eco target - no preheating."""
        await setup_room(real_store)
        _train_model_manager(coordinator._model_manager, "living_room")

        # At eco temp, schedule off. Schedule data has no blocks for today.
        coordinator.hass.states.get = MagicMock(side_effect=make_hass_states(temp="17.0", schedule_state="off"))
        # Empty schedule for today (Monday) - no upcoming comfort period
        empty_schedule = {"monday": []}
        coordinator.hass.services.async_call = _make_schedule_service_mock(empty_schedule)

        with patch("time.time", return_value=frozen_ts):
            data = await coordinator._async_update_data()

        # MPC sees constant eco (17C) across entire horizon, room at 17C -> idle
        assert data["rooms"]["living_room"]["mode"] == "idle"


class TestMPCFallback:
    @pytest.mark.asyncio
    async def test_bangbang_before_training(self, coordinator, real_store):
        """Before enough training data, coordinator should use bang-bang fallback."""
        await setup_room(real_store)

        # No training - model has no data
        coordinator.hass.states.get = MagicMock(side_effect=make_hass_states(temp="18.0"))
        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room"]
        # Bang-bang: should heat (18 < 21 - hysteresis)
        assert room["mode"] == "heating"
        # Bang-bang always uses full power
        assert room["heating_power"] == 100

    @pytest.mark.asyncio
    async def test_bangbang_hysteresis_prevents_cycling(self, coordinator, real_store):
        """Bang-bang should not oscillate near target due to hysteresis."""
        await setup_room(real_store)

        # Just barely below target - within hysteresis band
        coordinator.hass.states.get = MagicMock(side_effect=make_hass_states(temp="20.8"))
        data = await coordinator._async_update_data()

        # 20.8 is within 0.5C hysteresis of 21.0 -> should NOT start heating from idle
        assert data["rooms"]["living_room"]["mode"] == "idle"
