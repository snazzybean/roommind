"""Tests for master device control in compressor groups."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.roommind.const import MODE_IDLE

from .conftest import (
    MANAGED_ROOM,
    SAMPLE_ROOM,
    _create_coordinator,
    _make_store_mock,
    make_mock_states_get,
)


def _make_master_state(hvac_mode="off", hvac_modes=None):
    """Create a mock state for a master entity."""
    if hvac_modes is None:
        hvac_modes = ["off", "heat", "cool", "auto"]
    state = MagicMock()
    state.state = hvac_mode
    state.attributes = {"hvac_modes": hvac_modes}
    return state


def _room_with_device(area_id, entity_id, **overrides):
    """Create a room dict with one device."""
    room = {
        **SAMPLE_ROOM,
        "area_id": area_id,
        "thermostats": [entity_id],
        "acs": [],
        "devices": [
            {
                "entity_id": entity_id,
                "type": "trv",
                "role": "auto",
                "heating_system_type": "",
            }
        ],
    }
    room.update(overrides)
    return room


class TestMasterDeviceControl:
    """Tests for master device control wiring in the coordinator."""

    @pytest.mark.asyncio
    async def test_master_turns_on_heat_when_room_heating(self, hass, mock_config_entry):
        """Master entity should be set to 'heat' when a room is heating."""
        room = _room_with_device("living_room_abc12345", "climate.living_trv")
        store = _make_store_mock({"living_room_abc12345": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.living_trv"],
                    "master_entity": "climate.boiler",
                }
            ],
        }

        master_state = _make_master_state("off")

        # temp=18.0 with comfort_temp=21.0 -> room will be heating
        base_get = make_mock_states_get(temp="18.0")

        def states_get(eid):
            if eid == "climate.boiler":
                return master_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        # Check that set_hvac_mode was called on the master with "heat"
        calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("entity_id") == "climate.boiler"
        ]
        assert len(calls) >= 1
        assert calls[-1].args[2]["hvac_mode"] == "heat"

    @pytest.mark.asyncio
    async def test_master_turns_off_when_all_idle(self, hass, mock_config_entry):
        """Master entity should be set to 'off' when all rooms are idle."""
        room = _room_with_device(
            "living_room_abc12345",
            "climate.living_trv",
            comfort_temp=20.0,
            eco_temp=17.0,
        )
        store = _make_store_mock({"living_room_abc12345": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.living_trv"],
                    "master_entity": "climate.boiler",
                }
            ],
        }

        # Master currently on
        master_state = _make_master_state("heat")

        # temp=22.0 above comfort target -> room should be idle
        base_get = make_mock_states_get(temp="22.0")

        def states_get(eid):
            if eid == "climate.boiler":
                return master_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("entity_id") == "climate.boiler"
        ]
        assert len(calls) >= 1
        assert calls[-1].args[2]["hvac_mode"] == "off"

    @pytest.mark.asyncio
    async def test_group_without_master_no_commands(self, hass, mock_config_entry):
        """Group without master_entity should not generate any master commands."""
        room = _room_with_device("living_room_abc12345", "climate.living_trv")
        store = _make_store_mock({"living_room_abc12345": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.living_trv"],
                    # no master_entity
                }
            ],
        }

        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="18.0"))
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        # No calls to any entity other than the room's TRV
        master_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("entity_id") not in ("climate.living_trv",)
        ]
        assert len(master_calls) == 0

    @pytest.mark.asyncio
    async def test_master_no_redundant_calls(self, hass, mock_config_entry):
        """Master should not be called when already in the correct mode."""
        room = _room_with_device("living_room_abc12345", "climate.living_trv")
        store = _make_store_mock({"living_room_abc12345": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.living_trv"],
                    "master_entity": "climate.boiler",
                }
            ],
        }

        # Master already in "heat" mode, room is heating (temp below target)
        master_state = _make_master_state("heat")
        base_get = make_mock_states_get(temp="18.0")

        def states_get(eid):
            if eid == "climate.boiler":
                return master_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        # No set_hvac_mode call to boiler (already correct)
        boiler_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("entity_id") == "climate.boiler"
        ]
        assert len(boiler_calls) == 0

    @pytest.mark.asyncio
    async def test_master_unavailable_skipped(self, hass, mock_config_entry):
        """Unavailable master entity should be skipped without crashing."""
        room = _room_with_device("living_room_abc12345", "climate.living_trv")
        store = _make_store_mock({"living_room_abc12345": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.living_trv"],
                    "master_entity": "climate.boiler",
                }
            ],
        }

        unavailable = MagicMock()
        unavailable.state = "unavailable"
        unavailable.attributes = {}

        base_get = make_mock_states_get(temp="18.0")

        def states_get(eid):
            if eid == "climate.boiler":
                return unavailable
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        # Should not raise
        await coordinator._async_update_data()

        # No master commands
        boiler_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3 and c.args[2].get("entity_id") == "climate.boiler"
        ]
        assert len(boiler_calls) == 0

    @pytest.mark.asyncio
    async def test_master_mode_fallback_to_auto(self, hass, mock_config_entry):
        """Master that only supports 'auto' should get 'auto' when heating is needed."""
        room = _room_with_device("living_room_abc12345", "climate.living_trv")
        store = _make_store_mock({"living_room_abc12345": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.living_trv"],
                    "master_entity": "climate.boiler",
                }
            ],
        }

        # Master only supports auto and off
        master_state = _make_master_state("off", hvac_modes=["auto", "off"])
        base_get = make_mock_states_get(temp="18.0")

        def states_get(eid):
            if eid == "climate.boiler":
                return master_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        boiler_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("entity_id") == "climate.boiler"
        ]
        assert len(boiler_calls) >= 1
        assert boiler_calls[-1].args[2]["hvac_mode"] == "auto"

    @pytest.mark.asyncio
    async def test_master_action_script_called(self, hass, mock_config_entry):
        """Action script should be called with correct variables on transition."""
        room = _room_with_device("living_room_abc12345", "climate.living_trv")
        store = _make_store_mock({"living_room_abc12345": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.living_trv"],
                    "master_entity": "climate.boiler",
                    "action_script": "script.boiler_hook",
                }
            ],
        }

        master_state = _make_master_state("off")
        script_state = MagicMock()
        script_state.state = "off"

        base_get = make_mock_states_get(temp="18.0")

        def states_get(eid):
            if eid == "climate.boiler":
                return master_state
            if eid == "script.boiler_hook":
                return script_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        script_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3 and c.args[0] == "script" and c.args[1] == "turn_on"
        ]
        assert len(script_calls) >= 1
        call_data = script_calls[-1].args[2]
        assert call_data["entity_id"] == "script.boiler_hook"
        assert call_data["variables"]["action"] == "heat"
        assert call_data["variables"]["master_entity"] == "climate.boiler"
        assert call_data["variables"]["members"] == ["climate.living_trv"]

    @pytest.mark.asyncio
    async def test_master_not_controlled_when_climate_globally_disabled(self, hass, mock_config_entry):
        """Master entity must not be touched when climate_control_active is False.

        The user may manually operate the master device. RoomMind must not
        override that by forcing it off every 30 seconds.
        """
        room = _room_with_device("living_room_abc12345", "climate.living_trv")
        store = _make_store_mock({"living_room_abc12345": room})
        store.get_settings.return_value = {
            "climate_control_active": False,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.living_trv"],
                    "master_entity": "climate.boiler",
                }
            ],
        }

        # Master currently heating - user turned it on manually
        master_state = _make_master_state("heat")
        base_get = make_mock_states_get(temp="18.0")

        def states_get(eid):
            if eid == "climate.boiler":
                return master_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        # RoomMind must not send any command to the master entity
        boiler_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("entity_id") == "climate.boiler"
        ]
        assert len(boiler_calls) == 0

    @pytest.mark.asyncio
    async def test_master_missing_entity_returns_none(self, hass, mock_config_entry):
        """Master entity that does not exist in HA should be skipped."""
        room = _room_with_device("living_room_abc12345", "climate.living_trv")
        store = _make_store_mock({"living_room_abc12345": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.living_trv"],
                    "master_entity": "climate.nonexistent_boiler",
                }
            ],
        }

        # states.get returns None for the master entity (not registered)
        base_get = make_mock_states_get(temp="18.0")

        def states_get(eid):
            if eid == "climate.nonexistent_boiler":
                return None
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        # Should not raise
        await coordinator._async_update_data()

        # No master commands sent
        boiler_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3 and c.args[2].get("entity_id") == "climate.nonexistent_boiler"
        ]
        assert len(boiler_calls) == 0

    @pytest.mark.asyncio
    async def test_master_multi_room_mixed_modes(self, hass, mock_config_entry):
        """Master with multiple rooms. Heating priority resolves to 'heat'."""
        room_a = _room_with_device("room_a", "climate.trv_a")
        room_b = {
            **_room_with_device("room_b", "climate.ac_b"),
            "thermostats": [],
            "acs": ["climate.ac_b"],
            "devices": [
                {
                    "entity_id": "climate.ac_b",
                    "type": "ac",
                    "role": "auto",
                    "heating_system_type": "",
                }
            ],
            "climate_mode": "cool_only",
            "temperature_sensor": "sensor.room_b_temp",
            "humidity_sensor": "sensor.room_b_humidity",
            "schedules": [{"entity_id": "schedule.room_b_heating"}],
        }
        store = _make_store_mock({"room_a": room_a, "room_b": room_b})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.trv_a", "climate.ac_b"],
                    "master_entity": "climate.boiler",
                    # default conflict_resolution = heating_priority
                }
            ],
        }

        master_state = _make_master_state("off")

        # room_a: temp=18 (below 21 comfort) -> heating
        # room_b: temp=28 (above 24 comfort_cool for cool_only) -> cooling
        base_get = make_mock_states_get(temp="18.0")

        ac_b_state = MagicMock()
        ac_b_state.state = "off"
        ac_b_state.attributes = {
            "hvac_modes": ["cool", "off"],
            "min_temp": 16,
            "max_temp": 30,
        }

        room_b_temp = MagicMock()
        room_b_temp.state = "28.0"
        room_b_temp.attributes = {}

        room_b_humidity = MagicMock()
        room_b_humidity.state = "55.0"
        room_b_humidity.attributes = {}

        room_b_schedule = MagicMock()
        room_b_schedule.state = "on"
        room_b_schedule.attributes = {}

        def states_get(eid):
            if eid == "climate.boiler":
                return master_state
            if eid == "climate.ac_b":
                return ac_b_state
            if eid == "sensor.room_b_temp":
                return room_b_temp
            if eid == "sensor.room_b_humidity":
                return room_b_humidity
            if eid == "schedule.room_b_heating":
                return room_b_schedule
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        boiler_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("entity_id") == "climate.boiler"
        ]
        # With heating_priority (default), should resolve to "heat"
        assert len(boiler_calls) >= 1
        assert boiler_calls[-1].args[2]["hvac_mode"] == "heat"

    @pytest.mark.asyncio
    async def test_master_min_run_prevents_early_shutoff(self, hass, mock_config_entry):
        """Master must stay active for min_run_minutes before switching to idle."""
        room = _room_with_device(
            "living_room_abc12345",
            "climate.living_trv",
            comfort_temp=20.0,
        )
        store = _make_store_mock({"living_room_abc12345": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.living_trv"],
                    "master_entity": "climate.boiler",
                    "min_run_minutes": 15,
                    "min_off_minutes": 5,
                }
            ],
        }

        # Master is currently heating
        master_state = _make_master_state("heat")
        # Room is at target → would want idle, but min-run should block
        base_get = make_mock_states_get(temp="22.0")

        def states_get(eid):
            if eid == "climate.boiler":
                return master_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)

        # Load groups first so state tracking works, then simulate recent heat start
        coordinator._compressor_manager.load_groups(store.get_settings.return_value["compressor_groups"])
        coordinator._compressor_manager.set_master_action("g1", "heat")

        await coordinator._async_update_data()

        # Master should NOT have received an "off" command (min-run blocks it)
        boiler_off_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("entity_id") == "climate.boiler"
            and c.args[2].get("hvac_mode") == "off"
        ]
        assert len(boiler_off_calls) == 0

    @pytest.mark.asyncio
    async def test_master_min_off_prevents_early_restart(self, hass, mock_config_entry):
        """Master must stay off for min_off_minutes before restarting."""
        room = _room_with_device("living_room_abc12345", "climate.living_trv")
        store = _make_store_mock({"living_room_abc12345": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.living_trv"],
                    "master_entity": "climate.boiler",
                    "min_run_minutes": 15,
                    "min_off_minutes": 5,
                }
            ],
        }

        # Master is currently off, room wants heating
        master_state = _make_master_state("off")
        base_get = make_mock_states_get(temp="18.0")

        def states_get(eid):
            if eid == "climate.boiler":
                return master_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)

        # Load groups first, then simulate recent off transition
        coordinator._compressor_manager.load_groups(store.get_settings.return_value["compressor_groups"])
        coordinator._compressor_manager.set_master_action("g1", "heat")
        coordinator._compressor_manager.set_master_action("g1", "idle")

        await coordinator._async_update_data()

        # Master should NOT have received a "heat" command (min-off blocks it)
        boiler_heat_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("entity_id") == "climate.boiler"
            and c.args[2].get("hvac_mode") == "heat"
        ]
        assert len(boiler_heat_calls) == 0

    @pytest.mark.asyncio
    async def test_master_no_state_update_when_mode_unsupported(self, hass, mock_config_entry):
        """When resolved_mode is None, state should NOT be updated (K3 fix)."""
        room = _room_with_device("living_room_abc12345", "climate.living_trv")
        store = _make_store_mock({"living_room_abc12345": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.living_trv"],
                    "master_entity": "climate.boiler",
                }
            ],
        }

        # Master only supports "heat" and "off" — no "cool", "auto", or "heat_cool"
        master_state = _make_master_state("off", hvac_modes=["off", "heat"])

        # Set up room to want cooling (but master can't cool)
        room_ac = {
            **_room_with_device("living_room_abc12345", "climate.living_trv"),
            "thermostats": [],
            "acs": ["climate.living_trv"],
            "devices": [
                {
                    "entity_id": "climate.living_trv",
                    "type": "ac",
                    "role": "auto",
                    "heating_system_type": "",
                }
            ],
            "climate_mode": "cool_only",
        }
        store = _make_store_mock({"living_room_abc12345": room_ac})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.living_trv"],
                    "master_entity": "climate.boiler",
                }
            ],
        }

        ac_state = MagicMock()
        ac_state.state = "off"
        ac_state.attributes = {"hvac_modes": ["cool", "off"], "min_temp": 16, "max_temp": 30}

        base_get = make_mock_states_get(temp="30.0")

        def states_get(eid):
            if eid == "climate.boiler":
                return master_state
            if eid == "climate.living_trv":
                return ac_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        # No command should have been sent to the master
        boiler_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("entity_id") == "climate.boiler"
        ]
        assert len(boiler_calls) == 0

        # State should NOT have been updated to "cool"
        state = coordinator._compressor_manager.get_state("g1")
        assert state.master_action != "cool"

    @pytest.mark.asyncio
    async def test_script_only_mode_no_master_entity(self, hass, mock_config_entry):
        """When only action_script is set (no master_entity), only the script fires."""
        room = _room_with_device("living", "climate.living_trv")
        store = _make_store_mock(rooms={"living": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.living_trv"],
                    "action_script": "script.boiler_hook",
                },
            ],
        }

        script_state = MagicMock()
        script_state.state = "off"
        base_get = make_mock_states_get(temp="18.0")

        def states_get(eid):
            if eid == "script.boiler_hook":
                return script_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        # No climate commands to any master entity
        climate_hvac_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("entity_id") not in ["climate.living_trv"]
        ]
        assert len(climate_hvac_calls) == 0

        # Script was called
        script_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3 and c.args[0] == "script" and c.args[1] == "turn_on"
        ]
        assert len(script_calls) >= 1
        assert script_calls[-1].args[2]["entity_id"] == "script.boiler_hook"
        assert script_calls[-1].args[2]["variables"]["action"] == "heat"
        assert script_calls[-1].args[2]["variables"]["master_entity"] == ""

    @pytest.mark.asyncio
    async def test_script_only_no_redundant_calls(self, hass, mock_config_entry):
        """Script-only mode should not call script when action hasn't changed."""
        room = _room_with_device("living", "climate.living_trv")
        store = _make_store_mock(rooms={"living": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.living_trv"],
                    "action_script": "script.boiler_hook",
                },
            ],
        }

        script_state = MagicMock()
        script_state.state = "off"
        base_get = make_mock_states_get(temp="18.0")

        def states_get(eid):
            if eid == "script.boiler_hook":
                return script_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)

        # First cycle: script fires (None -> heat)
        await coordinator._async_update_data()
        script_calls_1 = [
            c for c in hass.services.async_call.call_args_list if len(c.args) >= 3 and c.args[0] == "script"
        ]
        assert len(script_calls_1) >= 1

        # Second cycle: same action, script should NOT fire
        hass.services.async_call.reset_mock()
        await coordinator._async_update_data()
        script_calls_2 = [
            c for c in hass.services.async_call.call_args_list if len(c.args) >= 3 and c.args[0] == "script"
        ]
        assert len(script_calls_2) == 0


class TestEnforceUniformMode:
    """Tests for enforce_uniform_mode on compressor groups."""

    @pytest.mark.asyncio
    async def test_enforce_forces_conflicting_room_idle(self, hass, mock_config_entry):
        """Room with conflicting mode is forced to idle on second cycle."""
        room_a = _room_with_device("room_a", "climate.trv_a")
        room_b = {
            **_room_with_device("room_b", "climate.ac_b"),
            "thermostats": [],
            "acs": ["climate.ac_b"],
            "devices": [
                {
                    "entity_id": "climate.ac_b",
                    "type": "ac",
                    "role": "auto",
                    "heating_system_type": "",
                }
            ],
            "climate_mode": "cool_only",
            "temperature_sensor": "sensor.room_b_temp",
            "humidity_sensor": "sensor.room_b_humidity",
            "schedules": [{"entity_id": "schedule.room_b_heating"}],
        }
        store = _make_store_mock({"room_a": room_a, "room_b": room_b})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.trv_a", "climate.ac_b"],
                    "enforce_uniform_mode": True,
                    # no master_entity — enforce-only mode
                }
            ],
        }

        # room_a: temp=18 (below 21 comfort) -> heating
        # room_b: temp=28 (above 24 comfort_cool for cool_only) -> cooling
        base_get = make_mock_states_get(temp="18.0")

        ac_b_state = MagicMock()
        ac_b_state.state = "off"
        ac_b_state.attributes = {
            "hvac_modes": ["cool", "off"],
            "min_temp": 16,
            "max_temp": 30,
        }

        room_b_temp = MagicMock()
        room_b_temp.state = "28.0"
        room_b_temp.attributes = {}

        room_b_humidity = MagicMock()
        room_b_humidity.state = "55.0"
        room_b_humidity.attributes = {}

        room_b_schedule = MagicMock()
        room_b_schedule.state = "on"
        room_b_schedule.attributes = {}

        def states_get(eid):
            if eid == "climate.ac_b":
                return ac_b_state
            if eid == "sensor.room_b_temp":
                return room_b_temp
            if eid == "sensor.room_b_humidity":
                return room_b_humidity
            if eid == "schedule.room_b_heating":
                return room_b_schedule
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)

        # Cycle 1: conflict resolution runs, stores "heat" (heating_priority default)
        await coordinator._async_update_data()
        state = coordinator._compressor_manager.get_state("g1")
        assert state.master_action == "heat"

        # Cycle 2: room_b (cooling) should be forced idle by enforcement
        hass.services.async_call.reset_mock()
        result = await coordinator._async_update_data()

        # room_b should now be idle due to enforcement
        room_b_mode = result["rooms"].get("room_b", {}).get("mode")
        assert room_b_mode == MODE_IDLE

        # No master climate commands should be sent (no master_entity)
        master_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("entity_id") not in ("climate.trv_a", "climate.ac_b")
        ]
        assert len(master_calls) == 0

    @pytest.mark.asyncio
    async def test_enforce_no_override_when_rooms_agree(self, hass, mock_config_entry):
        """All rooms heating -> no enforcement override."""
        room_a = _room_with_device("room_a", "climate.trv_a")
        room_b = _room_with_device(
            "room_b",
            "climate.trv_b",
            temperature_sensor="sensor.room_b_temp",
            humidity_sensor="sensor.room_b_humidity",
            schedules=[{"entity_id": "schedule.room_b_heating"}],
        )
        store = _make_store_mock({"room_a": room_a, "room_b": room_b})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.trv_a", "climate.trv_b"],
                    "enforce_uniform_mode": True,
                }
            ],
        }

        # Both rooms cold -> both heating
        base_get = make_mock_states_get(temp="18.0")

        room_b_temp = MagicMock()
        room_b_temp.state = "18.0"
        room_b_temp.attributes = {}

        room_b_humidity = MagicMock()
        room_b_humidity.state = "50.0"
        room_b_humidity.attributes = {}

        room_b_schedule = MagicMock()
        room_b_schedule.state = "on"
        room_b_schedule.attributes = {}

        trv_b_state = MagicMock()
        trv_b_state.state = "heat"
        trv_b_state.attributes = {
            "hvac_modes": ["heat", "off"],
            "min_temp": 5,
            "max_temp": 30,
        }

        def states_get(eid):
            if eid == "climate.trv_b":
                return trv_b_state
            if eid == "sensor.room_b_temp":
                return room_b_temp
            if eid == "sensor.room_b_humidity":
                return room_b_humidity
            if eid == "schedule.room_b_heating":
                return room_b_schedule
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)

        # Cycle 1: both heating, no conflict
        await coordinator._async_update_data()
        state = coordinator._compressor_manager.get_state("g1")
        assert state.master_action == "heat"

        # Cycle 2: both still heating, no override
        result = await coordinator._async_update_data()
        room_a_mode = result["rooms"].get("room_a", {}).get("mode")
        room_b_mode = result["rooms"].get("room_b", {}).get("mode")
        assert room_a_mode == "heating"
        assert room_b_mode == "heating"

    @pytest.mark.asyncio
    async def test_no_enforce_backwards_compat(self, hass, mock_config_entry):
        """Group without enforce_uniform_mode does NOT run conflict resolution."""
        room = _room_with_device("living_room_abc12345", "climate.living_trv")
        store = _make_store_mock({"living_room_abc12345": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.living_trv"],
                    # no master_entity, no action_script, no enforce_uniform_mode
                }
            ],
        }

        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="18.0"))
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        # master_action should NOT be set (group skipped in _async_control_master_devices)
        state = coordinator._compressor_manager.get_state("g1")
        assert state.master_action is None

    @pytest.mark.asyncio
    async def test_enforce_conflict_resolution_runs_without_master(self, hass, mock_config_entry):
        """enforce_uniform_mode group without master_entity still resolves and stores action."""
        room = _room_with_device("living_room_abc12345", "climate.living_trv")
        store = _make_store_mock({"living_room_abc12345": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.living_trv"],
                    "enforce_uniform_mode": True,
                    # no master_entity
                }
            ],
        }

        hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="18.0"))
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        # Conflict resolution should have run and stored action
        state = coordinator._compressor_manager.get_state("g1")
        assert state.master_action == "heat"

        # No master climate commands
        master_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("entity_id") not in ("climate.living_trv",)
        ]
        assert len(master_calls) == 0


# ---------------------------------------------------------------------------
# Helpers for ducted multi-zone (AirTouch) wake tests
# ---------------------------------------------------------------------------


def _make_ac_zone_state(hvac_mode="off", hvac_modes=None, current_temperature=20.0):
    """Mock state for a ducted AC zone with limited modes."""
    if hvac_modes is None:
        hvac_modes = ["off", "fan_only"]
    state = MagicMock()
    state.state = hvac_mode
    state.attributes = {
        "hvac_modes": hvac_modes,
        "min_temp": 16,
        "max_temp": 30,
        "temperature": 22.0,
        "current_temperature": current_temperature,
    }
    return state


def _ac_room(area_id, entity_id, **overrides):
    """Create an AC-only room dict for ducted zone testing.

    Keeps SAMPLE_ROOM's sensor names so make_mock_states_get works.
    """
    room = {
        **SAMPLE_ROOM,
        "area_id": area_id,
        "thermostats": [],
        "acs": [entity_id],
        "devices": [
            {
                "entity_id": entity_id,
                "type": "ac",
                "role": "auto",
                "heating_system_type": "",
            }
        ],
    }
    room.update(overrides)
    return room


class TestMasterZoneWake:
    """Tests for ducted multi-zone pre-activation (zone wake) logic."""

    @pytest.mark.asyncio
    async def test_wake_zone_when_all_off_heating(self, hass, mock_config_entry):
        """fan_only sent to a zone before master heat when all zones are off."""
        room = _ac_room("room_a", "climate.zone_a")
        store = _make_store_mock({"room_a": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.zone_a"],
                    "master_entity": "climate.outdoor",
                }
            ],
        }

        master_state = _make_master_state("off")
        zone_state = _make_ac_zone_state("off")

        base_get = make_mock_states_get(temp="18.0")

        def states_get(eid):
            if eid == "climate.outdoor":
                return master_state
            if eid == "climate.zone_a":
                return zone_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        calls = hass.services.async_call.call_args_list
        fan_only_calls = [
            c
            for c in calls
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("hvac_mode") == "fan_only"
            and c.args[2].get("entity_id") == "climate.zone_a"
        ]
        master_heat_calls = [
            c
            for c in calls
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("entity_id") == "climate.outdoor"
            and c.args[2].get("hvac_mode") == "heat"
        ]
        assert len(fan_only_calls) >= 1, "Zone should be woken with fan_only"
        assert len(master_heat_calls) >= 1, "Master should be set to heat"

        fan_idx = calls.index(fan_only_calls[0])
        master_idx = calls.index(master_heat_calls[0])
        assert fan_idx < master_idx, "fan_only must come before master heat"

    @pytest.mark.asyncio
    async def test_wake_zone_when_all_off_cooling(self, hass, mock_config_entry):
        """fan_only sent to zone before master cool when all zones off."""
        room = _ac_room("room_a", "climate.zone_a", climate_mode="cool_only", comfort_cool=24.0, eco_cool=27.0)
        store = _make_store_mock({"room_a": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.zone_a"],
                    "master_entity": "climate.outdoor",
                }
            ],
        }

        master_state = _make_master_state("off")
        zone_state = _make_ac_zone_state("off")

        base_get = make_mock_states_get(temp="28.0")

        def states_get(eid):
            if eid == "climate.outdoor":
                return master_state
            if eid == "climate.zone_a":
                return zone_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        calls = hass.services.async_call.call_args_list
        fan_only_calls = [
            c
            for c in calls
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("hvac_mode") == "fan_only"
            and c.args[2].get("entity_id") == "climate.zone_a"
        ]
        master_cool_calls = [
            c
            for c in calls
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("entity_id") == "climate.outdoor"
            and c.args[2].get("hvac_mode") == "cool"
        ]
        assert len(fan_only_calls) >= 1
        assert len(master_cool_calls) >= 1

    @pytest.mark.asyncio
    async def test_no_wake_when_zone_already_active(self, hass, mock_config_entry):
        """No wake when one zone is already in fan_only."""
        room = _ac_room("room_a", "climate.zone_a")
        store = _make_store_mock({"room_a": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.zone_a"],
                    "master_entity": "climate.outdoor",
                }
            ],
        }

        master_state = _make_master_state("off")
        zone_state = _make_ac_zone_state("fan_only", hvac_modes=["off", "fan_only"])

        base_get = make_mock_states_get(temp="18.0")

        def states_get(eid):
            if eid == "climate.outdoor":
                return master_state
            if eid == "climate.zone_a":
                return zone_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        wake_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("hvac_mode") == "fan_only"
            and c.args[2].get("entity_id") == "climate.zone_a"
        ]
        assert len(wake_calls) == 0, "No wake expected when zone already active"

    @pytest.mark.asyncio
    async def test_no_wake_when_master_already_correct(self, hass, mock_config_entry):
        """No wake when master is already in correct mode (redundancy)."""
        room = _ac_room("room_a", "climate.zone_a")
        store = _make_store_mock({"room_a": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.zone_a"],
                    "master_entity": "climate.outdoor",
                }
            ],
        }

        master_state = _make_master_state("heat")
        zone_state = _make_ac_zone_state("off")

        base_get = make_mock_states_get(temp="18.0")

        def states_get(eid):
            if eid == "climate.outdoor":
                return master_state
            if eid == "climate.zone_a":
                return zone_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        wake_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("hvac_mode") == "fan_only"
        ]
        assert len(wake_calls) == 0, "No wake when master is already in correct mode"

    @pytest.mark.asyncio
    async def test_no_wake_on_heat_to_cool_transition(self, hass, mock_config_entry):
        """No wake on heat->cool switch (zones already active)."""
        room = _ac_room("room_a", "climate.zone_a", climate_mode="cool_only", comfort_cool=24.0, eco_cool=27.0)
        store = _make_store_mock({"room_a": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.zone_a"],
                    "master_entity": "climate.outdoor",
                }
            ],
        }

        master_state = _make_master_state("heat")
        zone_state = _make_ac_zone_state("heat", hvac_modes=["off", "heat", "cool", "fan_only"])

        base_get = make_mock_states_get(temp="28.0")

        def states_get(eid):
            if eid == "climate.outdoor":
                return master_state
            if eid == "climate.zone_a":
                return zone_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._compressor_manager.load_groups(store.get_settings.return_value["compressor_groups"])
        coordinator._compressor_manager.set_master_action("g1", "heat")

        await coordinator._async_update_data()

        wake_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("hvac_mode") == "fan_only"
        ]
        assert len(wake_calls) == 0, "No wake on heat->cool (zones already active)"

    @pytest.mark.asyncio
    async def test_no_wake_on_idle_transition(self, hass, mock_config_entry):
        """No wake when transitioning to idle."""
        room = _ac_room("room_a", "climate.zone_a", comfort_temp=18.0, comfort_heat=18.0, eco_temp=15.0)
        store = _make_store_mock({"room_a": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.zone_a"],
                    "master_entity": "climate.outdoor",
                }
            ],
        }

        master_state = _make_master_state("heat")
        zone_state = _make_ac_zone_state("heat", hvac_modes=["off", "heat", "cool", "fan_only"])

        base_get = make_mock_states_get(temp="21.0")

        def states_get(eid):
            if eid == "climate.outdoor":
                return master_state
            if eid == "climate.zone_a":
                return zone_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._compressor_manager.load_groups(store.get_settings.return_value["compressor_groups"])
        coordinator._compressor_manager.set_master_action("g1", "heat")

        await coordinator._async_update_data()

        wake_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("hvac_mode") == "fan_only"
        ]
        assert len(wake_calls) == 0, "No wake on idle transition"

    @pytest.mark.asyncio
    async def test_wake_prefers_zone_with_demand(self, hass, mock_config_entry):
        """Wake selects zone from a room with heating demand."""
        room_a = _ac_room("room_a", "climate.zone_a")
        room_b = _ac_room("room_b", "climate.zone_b", comfort_temp=15.0, comfort_heat=15.0, eco_temp=12.0)
        store = _make_store_mock({"room_a": room_a, "room_b": room_b})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.zone_a", "climate.zone_b"],
                    "master_entity": "climate.outdoor",
                }
            ],
        }

        master_state = _make_master_state("off")
        zone_a_state = _make_ac_zone_state("off")
        zone_b_state = _make_ac_zone_state("off")

        base_get = make_mock_states_get(temp="18.0")

        def states_get(eid):
            if eid == "climate.outdoor":
                return master_state
            if eid == "climate.zone_a":
                return zone_a_state
            if eid == "climate.zone_b":
                return zone_b_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        wake_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("hvac_mode") == "fan_only"
        ]
        assert len(wake_calls) >= 1
        assert wake_calls[0].args[2]["entity_id"] == "climate.zone_a", (
            "Should pick zone_a (room has demand) not zone_b (room is idle at target)"
        )

    @pytest.mark.asyncio
    async def test_no_wake_when_no_fan_only(self, hass, mock_config_entry):
        """No wake when no zone supports fan_only; master command still sent."""
        room = _ac_room("room_a", "climate.zone_a")
        store = _make_store_mock({"room_a": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.zone_a"],
                    "master_entity": "climate.outdoor",
                }
            ],
        }

        master_state = _make_master_state("off")
        zone_state = _make_ac_zone_state("off", hvac_modes=["off"])

        base_get = make_mock_states_get(temp="18.0")

        def states_get(eid):
            if eid == "climate.outdoor":
                return master_state
            if eid == "climate.zone_a":
                return zone_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        wake_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("hvac_mode") == "fan_only"
        ]
        assert len(wake_calls) == 0, "No fan_only available"

        master_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("entity_id") == "climate.outdoor"
            and c.args[2].get("hvac_mode") == "heat"
        ]
        assert len(master_calls) >= 1, "Master command still attempted"

    @pytest.mark.asyncio
    async def test_wake_failure_does_not_block_master(self, hass, mock_config_entry):
        """Master command proceeds even when wake raises an exception."""
        room = _ac_room("room_a", "climate.zone_a")
        store = _make_store_mock({"room_a": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.zone_a"],
                    "master_entity": "climate.outdoor",
                }
            ],
        }

        master_state = _make_master_state("off")
        zone_state = _make_ac_zone_state("off")

        base_get = make_mock_states_get(temp="18.0")

        def states_get(eid):
            if eid == "climate.outdoor":
                return master_state
            if eid == "climate.zone_a":
                return zone_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)

        original_calls = []

        async def selective_fail(*args, **kwargs):
            original_calls.append((args, kwargs))
            if (
                len(args) >= 3
                and args[0] == "climate"
                and args[1] == "set_hvac_mode"
                and args[2].get("hvac_mode") == "fan_only"
            ):
                raise RuntimeError("AirTouch rejected fan_only")

        hass.services.async_call = AsyncMock(side_effect=selective_fail)
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        master_calls = [
            (a, k)
            for a, k in original_calls
            if len(a) >= 3
            and a[0] == "climate"
            and a[1] == "set_hvac_mode"
            and a[2].get("entity_id") == "climate.outdoor"
            and a[2].get("hvac_mode") == "heat"
        ]
        assert len(master_calls) >= 1, "Master heat command should still be sent"

    @pytest.mark.asyncio
    async def test_wake_updates_compressor_state(self, hass, mock_config_entry):
        """Wake updates compressor manager active_members."""
        room = _ac_room("room_a", "climate.zone_a")
        store = _make_store_mock({"room_a": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.zone_a"],
                    "master_entity": "climate.outdoor",
                }
            ],
        }

        master_state = _make_master_state("off")
        zone_state = _make_ac_zone_state("off")

        base_get = make_mock_states_get(temp="18.0")

        def states_get(eid):
            if eid == "climate.outdoor":
                return master_state
            if eid == "climate.zone_a":
                return zone_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        state = coordinator._compressor_manager.get_state("g1")
        assert "climate.zone_a" in state.active_members

    @pytest.mark.asyncio
    async def test_no_wake_for_script_only_group(self, hass, mock_config_entry):
        """No wake for groups with action_script but no master_entity."""
        room = _ac_room("room_a", "climate.zone_a")
        store = _make_store_mock({"room_a": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.zone_a"],
                    "action_script": "script.ac_control",
                }
            ],
        }

        zone_state = _make_ac_zone_state("off")
        base_get = make_mock_states_get(temp="18.0")

        def states_get(eid):
            if eid == "climate.zone_a":
                return zone_state
            if eid == "script.ac_control":
                s = MagicMock()
                s.state = "off"
                return s
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        wake_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("hvac_mode") == "fan_only"
        ]
        assert len(wake_calls) == 0

    @pytest.mark.asyncio
    async def test_commanded_mode_drives_master_in_managed_mode(self, hass, mock_config_entry):
        """In Managed Mode, commanded_mode (not display mode) drives master demand."""
        room = {
            **MANAGED_ROOM,
            "area_id": "room_a",
            "thermostats": [],
            "acs": ["climate.zone_a"],
            "devices": [
                {
                    "entity_id": "climate.zone_a",
                    "type": "ac",
                    "role": "auto",
                    "heating_system_type": "",
                }
            ],
            "temperature_sensor": "",
            "humidity_sensor": "",
            "schedules": [{"entity_id": "schedule.room_a_heating"}],
        }
        store = _make_store_mock({"room_a": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "g1",
                    "name": "G1",
                    "members": ["climate.zone_a"],
                    "master_entity": "climate.outdoor",
                }
            ],
        }

        master_state = _make_master_state("off")
        zone_state = _make_ac_zone_state("off")

        base_get = make_mock_states_get(temp="18.0")

        def states_get(eid):
            if eid == "climate.outdoor":
                return master_state
            if eid == "climate.zone_a":
                return zone_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        master_heat_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("entity_id") == "climate.outdoor"
            and c.args[2].get("hvac_mode") == "heat"
        ]
        assert len(master_heat_calls) >= 1, (
            "Master must receive heat even though device shows idle (commanded_mode=heating)"
        )
