"""Integration: window/door sensor pause with delays and state transitions."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from .conftest import ROOM_LIVING, make_hass_states, setup_room

ROOM_WITH_WINDOW = {
    **ROOM_LIVING,
    "window_sensors": ["binary_sensor.window_living"],
    "window_open_delay": 0,
    "window_close_delay": 0,
}


class TestWindowPause:
    @pytest.mark.asyncio
    async def test_window_open_pauses_heating(self, coordinator, real_store):
        await setup_room(real_store, ROOM_WITH_WINDOW)
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                extra={"binary_sensor.window_living": "on"},
            )
        )

        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room"]
        assert room["window_open"] is True
        assert room["mode"] == "idle"

    @pytest.mark.asyncio
    async def test_window_close_resumes_heating(self, coordinator, real_store):
        await setup_room(real_store, ROOM_WITH_WINDOW)

        # First cycle: window open
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                extra={"binary_sensor.window_living": "on"},
            )
        )
        data1 = await coordinator._async_update_data()
        assert data1["rooms"]["living_room"]["mode"] == "idle"

        # Second cycle: window closed
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                extra={"binary_sensor.window_living": "off"},
            )
        )
        data2 = await coordinator._async_update_data()
        assert data2["rooms"]["living_room"]["mode"] in ("heating", "idle")
        assert data2["rooms"]["living_room"]["window_open"] is False

    @pytest.mark.asyncio
    async def test_window_open_delay_keeps_heating(self, coordinator, real_store):
        """With a 60s open delay, window opens but heating continues on first cycle."""
        room = {**ROOM_WITH_WINDOW, "window_open_delay": 60}
        await setup_room(real_store, room)
        # Mark room as already known (simulates prior cycle with window closed)
        coordinator._window_manager._seen.add("living_room")
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                extra={"binary_sensor.window_living": "on"},
            )
        )

        data = await coordinator._async_update_data()

        # Window physically open but delay not elapsed - should NOT be paused yet
        assert data["rooms"]["living_room"]["window_open"] is False
        assert data["rooms"]["living_room"]["mode"] in ("heating", "idle")

    @pytest.mark.asyncio
    async def test_window_target_temp_unchanged_during_pause(self, coordinator, real_store):
        """Window pause should idle the mode but NOT change the target temp."""
        await setup_room(real_store, ROOM_WITH_WINDOW)

        # Cycle without window open
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                extra={"binary_sensor.window_living": "off"},
            )
        )
        data_normal = await coordinator._async_update_data()
        normal_target = data_normal["rooms"]["living_room"]["target_temp"]

        # Cycle with window open
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                extra={"binary_sensor.window_living": "on"},
            )
        )
        data_paused = await coordinator._async_update_data()
        paused_target = data_paused["rooms"]["living_room"]["target_temp"]

        assert normal_target == paused_target == 21.0
