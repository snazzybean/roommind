"""Tests for the unmanaged heat source pause (stove, fireplace) in the coordinator."""

from __future__ import annotations

import time
from unittest.mock import ANY, AsyncMock, MagicMock, call, patch

import pytest

from .conftest import (
    SAMPLE_ROOM,
    _create_coordinator,
    _make_store_mock,
    make_mock_states_get,
)

AREA = "living_room_abc12345"
STOVE_TEMP = "sensor.stove_temp"
MANAGER_TIME = "custom_components.roommind.managers.external_heat_manager.time"

STOVE_ROOM = {**SAMPLE_ROOM, "external_heat_sensors": [STOVE_TEMP]}


def states_with_stove(stove_value: str, room_temp: str = "18.0", **kwargs):
    """Return a mock ``hass.states.get`` with the stove sensor at ``stove_value`` degrees C.

    Args:
        stove_value: state string of the temperature sensor next to the stove.
        room_temp: state string of the room temperature sensor.
        **kwargs: forwarded to :func:`make_mock_states_get` (extra entities are merged).
    """
    extra = dict(kwargs.pop("extra", {}))
    extra[STOVE_TEMP] = (stove_value, {"unit_of_measurement": "°C", "device_class": "temperature"})
    return make_mock_states_get(temp=room_temp, extra=extra, **kwargs)


def setup(hass, mock_config_entry, room: dict, states_get):
    """Wire a single-room store, the given states and a fresh coordinator.

    Args:
        hass: the test Home Assistant instance.
        mock_config_entry: the integration config entry fixture.
        room: the room config stored under ``AREA``.
        states_get: the ``hass.states.get`` side effect.
    """
    store = _make_store_mock({AREA: room})
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(side_effect=states_get)
    hass.services.async_call = AsyncMock()
    return _create_coordinator(hass, mock_config_entry)


class TestExternalHeatPause:
    @pytest.mark.asyncio
    async def test_hot_stove_pauses_the_room(self, hass, mock_config_entry):
        """A stove sensor well above the room forces idle and turns the devices off."""
        coordinator = setup(hass, mock_config_entry, STOVE_ROOM, states_with_stove("26.0"))
        data = await coordinator._async_update_data()

        room_state = data["rooms"][AREA]
        assert room_state["mode"] == "idle"
        assert room_state["external_heat_active"] is True
        assert room_state["external_heat_until"] is None
        assert (
            call(
                "climate",
                "set_hvac_mode",
                {"entity_id": "climate.living_room", "hvac_mode": "off"},
                blocking=True,
                context=ANY,
            )
            in hass.services.async_call.call_args_list
        )

    @pytest.mark.asyncio
    async def test_cold_stove_lets_the_room_heat(self, hass, mock_config_entry):
        """A stove sensor at room temperature changes nothing."""
        coordinator = setup(hass, mock_config_entry, STOVE_ROOM, states_with_stove("18.5"))
        data = await coordinator._async_update_data()

        room_state = data["rooms"][AREA]
        assert room_state["mode"] == "heating"
        assert room_state["external_heat_active"] is False

    @pytest.mark.asyncio
    async def test_room_without_sources_is_unchanged(self, hass, mock_config_entry):
        """A room without external heat sensors heats as before and reports inactive."""
        coordinator = setup(hass, mock_config_entry, SAMPLE_ROOM, make_mock_states_get())
        data = await coordinator._async_update_data()

        room_state = data["rooms"][AREA]
        assert room_state["mode"] == "heating"
        assert room_state["external_heat_active"] is False
        assert room_state["external_heat_until"] is None

    @pytest.mark.asyncio
    async def test_stove_beats_manual_override(self, hass, mock_config_entry):
        """Like an open window, a burning stove wins over a boost override."""
        room = {
            **STOVE_ROOM,
            "override_heat": 25.0,
            "override_cool": 25.0,
            "override_until": time.time() + 3600,
            "override_type": "boost",
        }
        coordinator = setup(hass, mock_config_entry, room, states_with_stove("26.0"))
        data = await coordinator._async_update_data()

        room_state = data["rooms"][AREA]
        assert room_state["override_active"] is True
        assert room_state["mode"] == "idle"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("stove_value", "expected_mode", "expected_active"),
        [
            ("26.5", "cooling", False),  # control: without the stove this room cools
            ("32.0", "idle", True),
        ],
    )
    async def test_stove_also_stops_cooling(self, hass, mock_config_entry, stove_value, expected_mode, expected_active):
        """A stove overheating a cool_only room must not start the AC."""
        room = {
            **SAMPLE_ROOM,
            "thermostats": [],
            "acs": ["climate.living_room_ac"],
            "devices": [
                {"entity_id": "climate.living_room_ac", "type": "ac", "role": "auto", "heating_system_type": ""}
            ],
            "climate_mode": "cool_only",
            "external_heat_sensors": [STOVE_TEMP],
        }
        coordinator = setup(
            hass, mock_config_entry, room, states_with_stove(stove_value, room_temp="26.0", outdoor_temp="30.0")
        )
        data = await coordinator._async_update_data()

        room_state = data["rooms"][AREA]
        assert room_state["external_heat_active"] is expected_active
        assert room_state["mode"] == expected_mode

    @pytest.mark.asyncio
    async def test_cooldown_keeps_the_pause_and_reports_its_end(self, hass, mock_config_entry):
        """After the stove cools down the room stays paused until the cooldown ends."""
        room = {**STOVE_ROOM, "external_heat_cooldown": 60}
        coordinator = setup(hass, mock_config_entry, room, states_with_stove("26.0"))
        with patch(MANAGER_TIME) as mock_time:
            mock_time.time.return_value = 1000.0
            await coordinator._async_update_data()

            hass.states.get = MagicMock(side_effect=states_with_stove("18.5"))
            mock_time.time.return_value = 2000.0
            data = await coordinator._async_update_data()
            room_state = data["rooms"][AREA]
            assert room_state["mode"] == "idle"
            assert room_state["external_heat_active"] is True
            assert room_state["external_heat_until"] == pytest.approx(2000.0 + 3600)

            mock_time.time.return_value = 2000.0 + 3600
            data = await coordinator._async_update_data()
            room_state = data["rooms"][AREA]
            assert room_state["external_heat_active"] is False
            assert room_state["mode"] == "heating"

    @pytest.mark.asyncio
    async def test_training_is_told_about_the_source(self, hass, mock_config_entry):
        """The EKF training step receives external_heat=True while the stove burns."""
        coordinator = setup(hass, mock_config_entry, STOVE_ROOM, states_with_stove("26.0"))
        training = MagicMock()
        coordinator._ekf_training.process = training
        await coordinator._async_update_data()

        training.assert_called()
        assert training.call_args.kwargs["external_heat"] is True

    @pytest.mark.asyncio
    async def test_training_without_source_gets_false(self, hass, mock_config_entry):
        """Without a burning stove the EKF training step gets external_heat=False."""
        coordinator = setup(hass, mock_config_entry, STOVE_ROOM, states_with_stove("18.5"))
        training = MagicMock()
        coordinator._ekf_training.process = training
        await coordinator._async_update_data()

        assert training.call_args.kwargs["external_heat"] is False


class TestExternalHeatSources:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("entity_id", "state", "attrs", "expected"),
        [
            ("sensor.stove_power", "800", {"unit_of_measurement": "W", "device_class": "power"}, True),
            ("sensor.stove_power", "3", {"unit_of_measurement": "W", "device_class": "power"}, False),
            ("binary_sensor.stove", "on", {}, True),
            ("input_boolean.stove_lit", "off", {}, False),
        ],
    )
    async def test_power_and_on_off_entities(self, hass, mock_config_entry, entity_id, state, attrs, expected):
        """A power plug and an on/off helper pause the room as well as a temperature sensor."""
        room = {**SAMPLE_ROOM, "external_heat_sensors": [entity_id]}
        coordinator = setup(hass, mock_config_entry, room, make_mock_states_get(extra={entity_id: (state, attrs)}))
        room_state = (await coordinator._async_update_data())["rooms"][AREA]
        assert room_state["external_heat_active"] is expected
        assert room_state["mode"] == ("idle" if expected else "heating")

    @pytest.mark.asyncio
    async def test_stove_and_open_window_both_reported(self, hass, mock_config_entry):
        """A window opened next to a burning stove: both flags, the room stays idle."""
        room = {**STOVE_ROOM, "window_sensors": ["binary_sensor.living_room_window"]}
        coordinator = setup(
            hass,
            mock_config_entry,
            room,
            states_with_stove("26.0", window_sensors={"binary_sensor.living_room_window": "on"}),
        )
        room_state = (await coordinator._async_update_data())["rooms"][AREA]
        assert room_state["window_open"] is True
        assert room_state["external_heat_active"] is True
        assert room_state["mode"] == "idle"


class TestExternalHeatLearning:
    @pytest.mark.asyncio
    async def test_afterglow_learner_sees_the_stove_as_disturbance(self, hass, mock_config_entry):
        """The radiator afterglow is not measured while a stove heats the room."""
        coordinator = setup(hass, mock_config_entry, STOVE_ROOM, states_with_stove("26.0"))
        with patch.object(coordinator._residual_learner, "step", return_value=None) as step:
            await coordinator._async_update_data()
        assert step.call_args.kwargs["disturbed"] is True

    @pytest.mark.asyncio
    async def test_learn_only_mode_still_pauses_training(self, hass, mock_config_entry):
        """With climate control off RoomMind sends nothing, but the model still does not learn the stove."""
        store = _make_store_mock({AREA: STOVE_ROOM}, settings={"climate_control_active": False})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=states_with_stove("26.0"))
        hass.services.async_call = AsyncMock()
        coordinator = _create_coordinator(hass, mock_config_entry)
        training = MagicMock()
        coordinator._ekf_training.process = training
        room_state = (await coordinator._async_update_data())["rooms"][AREA]
        assert room_state["external_heat_active"] is True
        assert training.call_args.kwargs["external_heat"] is True
        assert [c for c in hass.services.async_call.call_args_list if c[0][0] == "climate"] == []

    @pytest.mark.asyncio
    async def test_history_records_the_pause(self, hass, mock_config_entry):
        """The analytics history gets an external_heat column for the chart band."""
        from custom_components.roommind.const import HISTORY_WRITE_CYCLES

        coordinator = setup(hass, mock_config_entry, STOVE_ROOM, states_with_stove("26.0"))
        history = MagicMock()
        coordinator._history_store = history
        coordinator._history_write_count = HISTORY_WRITE_CYCLES - 1
        await coordinator._async_update_data()
        records = [c for c in hass.async_add_executor_job.call_args_list if c[0] and c[0][0] is history.record]
        assert records[0][0][2]["external_heat"] is True

    @pytest.mark.asyncio
    async def test_removed_room_forgets_the_stove(self, hass, mock_config_entry):
        """Deleting the room drops the heat source state with the rest of its run state."""
        coordinator = setup(hass, mock_config_entry, STOVE_ROOM, states_with_stove("26.0"))
        await coordinator._async_update_data()
        assert coordinator._external_heat_manager.is_active(AREA) is True
        registry = MagicMock()
        registry.entities.values.return_value = []
        with patch("homeassistant.helpers.entity_registry.async_get", return_value=registry):
            coordinator._forget_room(AREA)
        assert coordinator._external_heat_manager.is_active(AREA) is False
