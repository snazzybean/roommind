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
        """No coordinator-level wake when master is already in correct mode.

        The zone still gets pre-activated via fan_only by _call() during
        normal room processing (#135), but _async_wake_member_zone should
        not fire separately (master already active → redundancy skip).
        """
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

        fan_only_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("hvac_mode") == "fan_only"
        ]
        assert len(fan_only_calls) >= 1, "Zone should be pre-activated via fan_only by _call() (#135)"
        assert fan_only_calls[0].args[2]["entity_id"] == "climate.zone_a"

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
    async def test_no_coordinator_wake_for_script_only_group(self, hass, mock_config_entry):
        """Script-only groups don't trigger _async_wake_member_zone.

        The zone still gets pre-activated via fan_only by _call() during
        normal room processing (#135). This is correct: the zone needs to
        be activated to heat, and the action_script handles master control.
        """
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

        fan_only_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("hvac_mode") == "fan_only"
        ]
        assert len(fan_only_calls) >= 1, "Zone should be pre-activated via fan_only by _call() (#135)"

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


def _room_with_trv_and_ac(area_id, trv_eid, ac_eid, **overrides):
    """Room with both TRV and AC, heat-source orchestration enabled by default."""
    room = {
        **SAMPLE_ROOM,
        "area_id": area_id,
        "thermostats": [trv_eid],
        "acs": [ac_eid],
        "devices": [
            {"entity_id": trv_eid, "type": "trv", "role": "auto", "heating_system_type": ""},
            {"entity_id": ac_eid, "type": "ac", "role": "auto", "heating_system_type": ""},
        ],
        "heat_source_orchestration": True,
    }
    room.update(overrides)
    return room


def _mock_evaluate_heat_sources(active_sources):
    """Build a patch target that returns a HeatSourcePlan with fixed active_sources.

    ``active_sources=None`` simulates the Orchestrator returning None (fallback).
    """
    from custom_components.roommind.managers.heat_source_orchestrator import (
        HeatSourcePlan,
    )

    def _fake(**kwargs):
        if active_sources is None:
            return None
        return HeatSourcePlan(commands=[], active_sources=active_sources, reason="test")

    return _fake


class TestMasterOrchestrationAware:
    """Master device control respects heat-source orchestration (#168)."""

    @pytest.mark.asyncio
    async def test_boiler_master_idle_when_orchestration_secondary(self, hass, mock_config_entry):
        """Boiler master stays idle when orchestration picks only the AC."""
        from unittest.mock import patch as _patch

        room = _room_with_trv_and_ac("living_room_abc12345", "climate.living_trv", "climate.living_ac")
        store = _make_store_mock({"living_room_abc12345": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "boiler",
                    "name": "Gas Boiler",
                    "members": ["climate.living_trv"],
                    "master_entity": "climate.boiler",
                }
            ],
        }

        master_state = _make_master_state("off")
        ac_state = MagicMock()
        ac_state.state = "off"
        ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "min_temp": 16, "max_temp": 30}
        base_get = make_mock_states_get(temp="18.0")

        def states_get(eid):
            if eid == "climate.boiler":
                return master_state
            if eid == "climate.living_ac":
                return ac_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        with _patch(
            "custom_components.roommind.coordinator.evaluate_heat_sources",
            side_effect=_mock_evaluate_heat_sources("secondary"),
        ):
            await coordinator._async_update_data()

        boiler_heat_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("entity_id") == "climate.boiler"
            and c.args[2].get("hvac_mode") == "heat"
        ]
        assert len(boiler_heat_calls) == 0, "Boiler must not receive heat when AC is selected"

    @pytest.mark.asyncio
    async def test_boiler_master_heat_when_orchestration_primary(self, hass, mock_config_entry):
        """Boiler master gets heat when orchestration picks primary (TRV)."""
        from unittest.mock import patch as _patch

        room = _room_with_trv_and_ac("living_room_abc12345", "climate.living_trv", "climate.living_ac")
        store = _make_store_mock({"living_room_abc12345": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "boiler",
                    "name": "Gas Boiler",
                    "members": ["climate.living_trv"],
                    "master_entity": "climate.boiler",
                }
            ],
        }

        master_state = _make_master_state("off")
        ac_state = MagicMock()
        ac_state.state = "off"
        ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "min_temp": 16, "max_temp": 30}
        base_get = make_mock_states_get(temp="18.0")

        def states_get(eid):
            if eid == "climate.boiler":
                return master_state
            if eid == "climate.living_ac":
                return ac_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        with _patch(
            "custom_components.roommind.coordinator.evaluate_heat_sources",
            side_effect=_mock_evaluate_heat_sources("primary"),
        ):
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
        assert boiler_calls[-1].args[2]["hvac_mode"] == "heat"

    @pytest.mark.asyncio
    async def test_boiler_master_heat_when_orchestration_both(self, hass, mock_config_entry):
        """Boiler master gets heat when orchestration picks both sources."""
        from unittest.mock import patch as _patch

        room = _room_with_trv_and_ac("living_room_abc12345", "climate.living_trv", "climate.living_ac")
        store = _make_store_mock({"living_room_abc12345": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "boiler",
                    "name": "Gas Boiler",
                    "members": ["climate.living_trv"],
                    "master_entity": "climate.boiler",
                }
            ],
        }

        master_state = _make_master_state("off")
        ac_state = MagicMock()
        ac_state.state = "off"
        ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "min_temp": 16, "max_temp": 30}
        base_get = make_mock_states_get(temp="18.0")

        def states_get(eid):
            if eid == "climate.boiler":
                return master_state
            if eid == "climate.living_ac":
                return ac_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        with _patch(
            "custom_components.roommind.coordinator.evaluate_heat_sources",
            side_effect=_mock_evaluate_heat_sources("both"),
        ):
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
        assert boiler_calls[-1].args[2]["hvac_mode"] == "heat"

    @pytest.mark.asyncio
    async def test_ac_master_idle_when_orchestration_primary(self, hass, mock_config_entry):
        """AC master stays idle when orchestration picks only the boiler."""
        from unittest.mock import patch as _patch

        room = _room_with_trv_and_ac("living_room_abc12345", "climate.living_trv", "climate.living_ac")
        store = _make_store_mock({"living_room_abc12345": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "ac",
                    "name": "AC Unit",
                    "members": ["climate.living_ac"],
                    "master_entity": "climate.ac_master",
                }
            ],
        }

        ac_master_state = _make_master_state("off")
        ac_state = MagicMock()
        ac_state.state = "off"
        ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "min_temp": 16, "max_temp": 30}
        base_get = make_mock_states_get(temp="18.0")

        def states_get(eid):
            if eid == "climate.ac_master":
                return ac_master_state
            if eid == "climate.living_ac":
                return ac_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        with _patch(
            "custom_components.roommind.coordinator.evaluate_heat_sources",
            side_effect=_mock_evaluate_heat_sources("primary"),
        ):
            await coordinator._async_update_data()

        ac_master_heat_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("entity_id") == "climate.ac_master"
            and c.args[2].get("hvac_mode") == "heat"
        ]
        assert len(ac_master_heat_calls) == 0

    @pytest.mark.asyncio
    async def test_ac_master_heat_when_orchestration_secondary(self, hass, mock_config_entry):
        """AC master gets heat when orchestration picks secondary (AC)."""
        from unittest.mock import patch as _patch

        room = _room_with_trv_and_ac("living_room_abc12345", "climate.living_trv", "climate.living_ac")
        store = _make_store_mock({"living_room_abc12345": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "ac",
                    "name": "AC Unit",
                    "members": ["climate.living_ac"],
                    "master_entity": "climate.ac_master",
                }
            ],
        }

        ac_master_state = _make_master_state("off")
        ac_state = MagicMock()
        ac_state.state = "off"
        ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "min_temp": 16, "max_temp": 30}
        base_get = make_mock_states_get(temp="18.0")

        def states_get(eid):
            if eid == "climate.ac_master":
                return ac_master_state
            if eid == "climate.living_ac":
                return ac_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        with _patch(
            "custom_components.roommind.coordinator.evaluate_heat_sources",
            side_effect=_mock_evaluate_heat_sources("secondary"),
        ):
            await coordinator._async_update_data()

        ac_master_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("entity_id") == "climate.ac_master"
        ]
        assert len(ac_master_calls) >= 1
        assert ac_master_calls[-1].args[2]["hvac_mode"] == "heat"

    @pytest.mark.asyncio
    async def test_boiler_idle_when_active_sources_none(self, hass, mock_config_entry):
        """Boiler stays idle when orchestration reports active_sources='none'."""
        from unittest.mock import patch as _patch

        room = _room_with_trv_and_ac("living_room_abc12345", "climate.living_trv", "climate.living_ac")
        store = _make_store_mock({"living_room_abc12345": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "boiler",
                    "name": "Gas Boiler",
                    "members": ["climate.living_trv"],
                    "master_entity": "climate.boiler",
                }
            ],
        }

        master_state = _make_master_state("off")
        ac_state = MagicMock()
        ac_state.state = "off"
        ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "min_temp": 16, "max_temp": 30}
        base_get = make_mock_states_get(temp="18.0")

        def states_get(eid):
            if eid == "climate.boiler":
                return master_state
            if eid == "climate.living_ac":
                return ac_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        with _patch(
            "custom_components.roommind.coordinator.evaluate_heat_sources",
            side_effect=_mock_evaluate_heat_sources("none"),
        ):
            await coordinator._async_update_data()

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
    async def test_boiler_heat_when_active_sources_missing_fallback(self, hass, mock_config_entry):
        """When orchestrator returns None (fallback), master behaves legacy."""
        from unittest.mock import patch as _patch

        room = _room_with_trv_and_ac("living_room_abc12345", "climate.living_trv", "climate.living_ac")
        store = _make_store_mock({"living_room_abc12345": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "boiler",
                    "name": "Gas Boiler",
                    "members": ["climate.living_trv"],
                    "master_entity": "climate.boiler",
                }
            ],
        }

        master_state = _make_master_state("off")
        ac_state = MagicMock()
        ac_state.state = "off"
        ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "min_temp": 16, "max_temp": 30}
        base_get = make_mock_states_get(temp="18.0")

        def states_get(eid):
            if eid == "climate.boiler":
                return master_state
            if eid == "climate.living_ac":
                return ac_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        # Orchestrator returns None -> active_heat_sources stays None -> filter
        # returns True -> master reacts to commanded_mode as before.
        with _patch(
            "custom_components.roommind.coordinator.evaluate_heat_sources",
            side_effect=_mock_evaluate_heat_sources(None),
        ):
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
        assert boiler_calls[-1].args[2]["hvac_mode"] == "heat"

    @pytest.mark.asyncio
    async def test_mixed_rooms_orchestrated_secondary_and_plain_heating(self, hass, mock_config_entry):
        """Room B without orchestration still drives the boiler even if Room A skips it."""
        from unittest.mock import patch as _patch

        room_a = _room_with_trv_and_ac("living_room_abc12345", "climate.a_trv", "climate.a_ac")
        # Room B: no orchestration, TRV only, temp_sensor for its area
        room_b = {
            **SAMPLE_ROOM,
            "area_id": "kitchen_xyz",
            "thermostats": ["climate.b_trv"],
            "acs": [],
            "devices": [
                {"entity_id": "climate.b_trv", "type": "trv", "role": "auto", "heating_system_type": ""},
            ],
            "heat_source_orchestration": False,
            "temperature_sensor": "sensor.kitchen_temp",
        }
        store = _make_store_mock({"living_room_abc12345": room_a, "kitchen_xyz": room_b})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "boiler",
                    "name": "Gas Boiler",
                    "members": ["climate.a_trv", "climate.b_trv"],
                    "master_entity": "climate.boiler",
                }
            ],
        }

        master_state = _make_master_state("off")
        ac_state = MagicMock()
        ac_state.state = "off"
        ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "min_temp": 16, "max_temp": 30}
        base_get = make_mock_states_get(temp="18.0")
        kitchen_temp = MagicMock()
        kitchen_temp.state = "18.0"
        kitchen_temp.attributes = {}

        def states_get(eid):
            if eid == "climate.boiler":
                return master_state
            if eid == "climate.a_ac":
                return ac_state
            if eid == "sensor.kitchen_temp":
                return kitchen_temp
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        with _patch(
            "custom_components.roommind.coordinator.evaluate_heat_sources",
            side_effect=_mock_evaluate_heat_sources("secondary"),
        ):
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
        assert boiler_calls[-1].args[2]["hvac_mode"] == "heat", (
            "Room B (no orchestration) must still drive the boiler master"
        )

    @pytest.mark.asyncio
    async def test_non_orchestrated_unchanged(self, hass, mock_config_entry):
        """A room without orchestration drives the boiler master as before."""
        room = _room_with_device("living_room_abc12345", "climate.living_trv")
        store = _make_store_mock({"living_room_abc12345": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "boiler",
                    "name": "Gas Boiler",
                    "members": ["climate.living_trv"],
                    "master_entity": "climate.boiler",
                }
            ],
        }

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
        assert boiler_calls[-1].args[2]["hvac_mode"] == "heat"

    @pytest.mark.asyncio
    async def test_cooling_mode_not_filtered(self, hass, mock_config_entry):
        """Cooling-mode rooms bypass the heating orchestration filter."""
        from unittest.mock import patch as _patch

        # Cool-only climate mode so the room commands MODE_COOLING
        room = _room_with_trv_and_ac(
            "living_room_abc12345",
            "climate.living_trv",
            "climate.living_ac",
            climate_mode="cool_only",
            comfort_temp=22.0,
            eco_temp=26.0,
            comfort_cool=22.0,
            eco_cool=26.0,
        )
        store = _make_store_mock({"living_room_abc12345": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "ac",
                    "name": "AC",
                    "members": ["climate.living_ac"],
                    "master_entity": "climate.ac_master",
                }
            ],
        }

        ac_master_state = _make_master_state("off")
        ac_state = MagicMock()
        ac_state.state = "off"
        ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "min_temp": 16, "max_temp": 30}
        base_get = make_mock_states_get(temp="28.0")  # hot -> cooling

        def states_get(eid):
            if eid == "climate.ac_master":
                return ac_master_state
            if eid == "climate.living_ac":
                return ac_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        # Orchestrator is short-circuited on non-heating modes anyway,
        # but explicit patch clarifies intent.
        with _patch(
            "custom_components.roommind.coordinator.evaluate_heat_sources",
            side_effect=_mock_evaluate_heat_sources(None),
        ):
            await coordinator._async_update_data()

        ac_master_calls = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("entity_id") == "climate.ac_master"
        ]
        assert len(ac_master_calls) >= 1
        assert ac_master_calls[-1].args[2]["hvac_mode"] == "cool"

    @pytest.mark.asyncio
    async def test_two_groups_per_room_filtered_independently(self, hass, mock_config_entry):
        """Room with TRV in boiler group and AC in AC group -> per-group filter."""
        from unittest.mock import patch as _patch

        room = _room_with_trv_and_ac("living_room_abc12345", "climate.living_trv", "climate.living_ac")
        store = _make_store_mock({"living_room_abc12345": room})
        store.get_settings.return_value = {
            "climate_control_active": True,
            "compressor_groups": [
                {
                    "id": "boiler",
                    "name": "Gas Boiler",
                    "members": ["climate.living_trv"],
                    "master_entity": "climate.boiler",
                },
                {
                    "id": "ac",
                    "name": "AC",
                    "members": ["climate.living_ac"],
                    "master_entity": "climate.ac_master",
                },
            ],
        }

        boiler_state = _make_master_state("off")
        ac_master_state = _make_master_state("off")
        ac_state = MagicMock()
        ac_state.state = "off"
        ac_state.attributes = {"hvac_modes": ["heat", "cool", "off"], "min_temp": 16, "max_temp": 30}
        base_get = make_mock_states_get(temp="18.0")

        def states_get(eid):
            if eid == "climate.boiler":
                return boiler_state
            if eid == "climate.ac_master":
                return ac_master_state
            if eid == "climate.living_ac":
                return ac_state
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}

        coordinator = _create_coordinator(hass, mock_config_entry)
        with _patch(
            "custom_components.roommind.coordinator.evaluate_heat_sources",
            side_effect=_mock_evaluate_heat_sources("secondary"),
        ):
            await coordinator._async_update_data()

        boiler_heat = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("entity_id") == "climate.boiler"
            and c.args[2].get("hvac_mode") == "heat"
        ]
        ac_master_heat = [
            c
            for c in hass.services.async_call.call_args_list
            if len(c.args) >= 3
            and c.args[0] == "climate"
            and c.args[1] == "set_hvac_mode"
            and c.args[2].get("entity_id") == "climate.ac_master"
            and c.args[2].get("hvac_mode") == "heat"
        ]
        assert len(boiler_heat) == 0, "Boiler must stay idle when AC is selected"
        assert len(ac_master_heat) >= 1, "AC master must activate when AC is selected"


@pytest.mark.asyncio
async def test_wake_skips_the_ac_sitting_out_of_heat_only(hass, mock_config_entry):
    """The zone woken for the master must be one that may run: not an AC sitting out heating (#476)."""
    sitting_out = {
        **_room_with_device("room_a", "climate.zone_a"),
        "climate_mode": "heat_only",
        "devices": [
            {"entity_id": "climate.trv_a", "type": "trv", "role": "auto", "heating_system_type": ""},
            {"entity_id": "climate.zone_a", "type": "ac", "role": "auto", "heating_system_type": ""},
        ],
    }
    neighbour = _room_with_device("room_b", "climate.zone_b")
    rooms = {"room_a": sitting_out, "room_b": neighbour}
    zone = _make_ac_zone_state("off")
    hass.states.get = MagicMock(return_value=zone)
    hass.services.async_call = AsyncMock()
    hass.data = {"roommind": {"store": _make_store_mock(rooms)}}
    coordinator = _create_coordinator(hass, mock_config_entry)
    coordinator._compressor_manager.load_groups(
        [
            {
                "id": "g1",
                "name": "G1",
                "members": ["climate.zone_a", "climate.zone_b"],
                "master_entity": "climate.outdoor",
            }
        ]
    )
    group = coordinator._compressor_manager.get_groups()["g1"]
    room_states = {
        "room_a": {"mode": "heating", "commanded_mode": "heating"},
        "room_b": {"mode": "heating", "commanded_mode": "heating"},
    }

    await coordinator._async_wake_member_zone(group, room_states, rooms)

    woken = [
        c.args[2]["entity_id"]
        for c in hass.services.async_call.call_args_list
        if c.args[1] == "set_hvac_mode" and c.args[2].get("hvac_mode") == "fan_only"
    ]
    assert woken == ["climate.zone_b"]


@pytest.mark.asyncio
async def test_wake_fallback_skips_the_ac_sitting_out_of_heat_only(hass, mock_config_entry):
    sitting_out = {
        **_room_with_device("room_a", "climate.zone_a"),
        "climate_mode": "heat_only",
        "devices": [
            {"entity_id": "climate.trv_a", "type": "trv", "role": "auto", "heating_system_type": ""},
            {"entity_id": "climate.zone_a", "type": "ac", "role": "auto", "heating_system_type": ""},
        ],
    }
    neighbour = _room_with_device("room_b", "climate.zone_b")
    rooms = {"room_a": sitting_out, "room_b": neighbour}
    zone_a = _make_ac_zone_state("off")
    zone_b = _make_ac_zone_state("off", hvac_modes=["off", "heat"])  # no fan_only
    states = {"climate.zone_a": zone_a, "climate.zone_b": zone_b}
    hass.states.get = MagicMock(side_effect=states.get)
    hass.services.async_call = AsyncMock()
    hass.data = {"roommind": {"store": _make_store_mock(rooms)}}
    coordinator = _create_coordinator(hass, mock_config_entry)
    coordinator._compressor_manager.load_groups(
        [
            {
                "id": "g1",
                "name": "G1",
                "members": ["climate.zone_a", "climate.zone_b"],
                "master_entity": "climate.outdoor",
            }
        ]
    )
    group = coordinator._compressor_manager.get_groups()["g1"]
    room_states = {
        "room_a": {"mode": "heating", "commanded_mode": "heating"},
        "room_b": {"mode": "heating", "commanded_mode": "heating"},
    }
    await coordinator._async_wake_member_zone(group, room_states, rooms)
    woken = [
        c.args[2]["entity_id"]
        for c in hass.services.async_call.call_args_list
        if c.args[1] == "set_hvac_mode" and c.args[2].get("hvac_mode") == "fan_only"
    ]
    assert woken == []


def _fan_only_wakes(hass):
    return [
        c.args[2]["entity_id"]
        for c in hass.services.async_call.call_args_list
        if c.args[1] == "set_hvac_mode" and c.args[2].get("hvac_mode") == "fan_only"
    ]


def _wake_coordinator(hass, mock_config_entry, rooms, states):
    hass.states.get = MagicMock(side_effect=states.get)
    hass.services.async_call = AsyncMock()
    hass.data = {"roommind": {"store": _make_store_mock(rooms)}}
    coordinator = _create_coordinator(hass, mock_config_entry)
    coordinator._compressor_manager.load_groups(
        [
            {
                "id": "g1",
                "name": "G1",
                "members": ["climate.zone_a", "climate.zone_b"],
                "master_entity": "climate.outdoor",
            }
        ]
    )
    return coordinator, coordinator._compressor_manager.get_groups()["g1"]


@pytest.mark.asyncio
@pytest.mark.parametrize("unruled", [{"climate_control_enabled": False}, {"is_outdoor": True}])
async def test_wake_fallback_leaves_a_room_alone_that_receives_no_commands(hass, mock_config_entry, unruled):
    """No cycle would switch a zone of a room without control off again (#36), so it is never woken."""
    demanding = _room_with_device("room_a", "climate.zone_a")
    unruled_room = {**_room_with_device("room_b", "climate.zone_b"), **unruled}
    rooms = {"room_a": demanding, "room_b": unruled_room}
    states = {
        "climate.zone_a": _make_ac_zone_state("off", hvac_modes=["off", "heat"]),  # no fan_only
        "climate.zone_b": _make_ac_zone_state("off"),
    }
    coordinator, group = _wake_coordinator(hass, mock_config_entry, rooms, states)
    room_states = {"room_a": {"mode": "heating", "commanded_mode": "heating"}}

    await coordinator._async_wake_member_zone(group, room_states, rooms)

    assert _fan_only_wakes(hass) == []


@pytest.mark.asyncio
async def test_wake_fallback_leaves_the_zone_of_a_resting_room_alone(hass, mock_config_entry):
    """A room whose area was deleted (#494) has no cycle that would switch its zone off again."""
    demanding = _room_with_device("room_a", "climate.zone_a")
    resting = _room_with_device("room_b", "climate.zone_b")
    states = {
        "climate.zone_a": _make_ac_zone_state("off", hvac_modes=["off", "heat"]),  # no fan_only
        "climate.zone_b": _make_ac_zone_state("off"),
    }
    # Stored, but not among the rooms the cycle runs
    coordinator, group = _wake_coordinator(hass, mock_config_entry, {"room_a": demanding, "room_b": resting}, states)
    room_states = {"room_a": {"mode": "heating", "commanded_mode": "heating"}}

    await coordinator._async_wake_member_zone(group, room_states, {"room_a": demanding})

    assert _fan_only_wakes(hass) == []


@pytest.mark.asyncio
async def test_wake_fallback_still_wakes_an_idle_room_under_control(hass, mock_config_entry):
    demanding = _room_with_device("room_a", "climate.zone_a")
    idle = _room_with_device("room_b", "climate.zone_b")
    rooms = {"room_a": demanding, "room_b": idle}
    states = {
        "climate.zone_a": _make_ac_zone_state("off", hvac_modes=["off", "heat"]),
        "climate.zone_b": _make_ac_zone_state("off"),
    }
    coordinator, group = _wake_coordinator(hass, mock_config_entry, rooms, states)
    room_states = {
        "room_a": {"mode": "heating", "commanded_mode": "heating"},
        "room_b": {"mode": "idle", "commanded_mode": "idle"},
    }

    await coordinator._async_wake_member_zone(group, room_states, rooms)

    assert _fan_only_wakes(hass) == ["climate.zone_b"]


@pytest.mark.asyncio
async def test_wake_skips_the_ac_the_orchestration_parks(hass, mock_config_entry):
    """A room heating through its TRV alone does not hand its parked AC to the master (#168)."""
    orchestrated = _room_with_trv_and_ac("room_a", "climate.trv_a", "climate.zone_a")
    neighbour = _room_with_device("room_b", "climate.zone_b")
    rooms = {"room_a": orchestrated, "room_b": neighbour}
    states = {"climate.zone_a": _make_ac_zone_state("off"), "climate.zone_b": _make_ac_zone_state("off")}
    coordinator, group = _wake_coordinator(hass, mock_config_entry, rooms, states)
    room_states = {
        "room_a": {"mode": "heating", "commanded_mode": "heating", "active_heat_sources": "primary"},
        "room_b": {"mode": "heating", "commanded_mode": "heating"},
    }

    await coordinator._async_wake_member_zone(group, room_states, rooms)

    assert _fan_only_wakes(hass) == ["climate.zone_b"]


@pytest.mark.asyncio
async def test_wake_takes_the_ac_the_orchestration_runs(hass, mock_config_entry):
    orchestrated = _room_with_trv_and_ac("room_a", "climate.trv_a", "climate.zone_a")
    rooms = {"room_a": orchestrated}
    states = {"climate.zone_a": _make_ac_zone_state("off"), "climate.zone_b": _make_ac_zone_state("off")}
    coordinator, group = _wake_coordinator(hass, mock_config_entry, rooms, states)
    room_states = {"room_a": {"mode": "heating", "commanded_mode": "heating", "active_heat_sources": "secondary"}}

    await coordinator._async_wake_member_zone(group, room_states, rooms)

    assert _fan_only_wakes(hass) == ["climate.zone_a"]


@pytest.mark.asyncio
async def test_a_woken_zone_of_no_room_does_not_count_as_running(hass, mock_config_entry):
    """No room cycle reports a zone outside every room as stopped, so marking it running
    would leave a phantom member that cancels the group's min run for good."""
    demanding = _room_with_device("room_a", "climate.zone_a")
    rooms = {"room_a": demanding}
    states = {
        "climate.zone_a": _make_ac_zone_state("off", hvac_modes=["off", "heat"]),
        "climate.zone_b": _make_ac_zone_state("off"),
    }
    coordinator, group = _wake_coordinator(hass, mock_config_entry, rooms, states)
    room_states = {"room_a": {"mode": "heating", "commanded_mode": "heating"}}

    await coordinator._async_wake_member_zone(group, room_states, rooms)

    assert _fan_only_wakes(hass) == ["climate.zone_b"]
    assert not coordinator._compressor_manager.is_compressor_running("g1")


def _woken_zone_setup(hass, mock_config_entry, master_mode="heat"):
    """Room A (no fan_only) heats, zone B belongs to no room and was woken for the master."""
    rooms = {"room_a": _room_with_device("room_a", "climate.zone_a")}
    states = {
        "climate.zone_a": _make_ac_zone_state("off", hvac_modes=["off", "heat"]),
        "climate.zone_b": _make_ac_zone_state("off"),
        "climate.outdoor": _make_master_state(master_mode),
    }
    coordinator, group = _wake_coordinator(hass, mock_config_entry, rooms, states)
    coordinator._had_valid_temp.update({"room_a", "room_b"})
    return coordinator, group, rooms, states


def _zone_offs(hass, eid="climate.zone_b"):
    return [
        c
        for c in hass.services.async_call.call_args_list
        if c.args[1] == "set_hvac_mode" and c.args[2] == {"entity_id": eid, "hvac_mode": "off"}
    ]


async def _wake_then_idle(coordinator, group, rooms, states, hass):
    await coordinator._async_wake_member_zone(group, {"room_a": {"commanded_mode": "heating"}}, rooms)
    states["climate.zone_b"] = _make_ac_zone_state("fan_only")
    hass.services.async_call.reset_mock()
    await coordinator._async_control_master_devices(
        {"room_a": {"mode": "idle", "commanded_mode": "idle"}}, rooms, {"climate_control_active": True}
    )


@pytest.mark.asyncio
async def test_a_woken_zone_of_no_room_goes_off_with_the_master(hass, mock_config_entry):
    """No room cycle sends that zone anything, so it ran fan_only for good (#135)."""
    coordinator, group, rooms, states = _woken_zone_setup(hass, mock_config_entry)

    await _wake_then_idle(coordinator, group, rooms, states, hass)

    calls = [c.args[2] for c in hass.services.async_call.call_args_list if c.args[1] == "set_hvac_mode"]
    assert calls == [
        {"entity_id": "climate.outdoor", "hvac_mode": "off"},
        {"entity_id": "climate.zone_b", "hvac_mode": "off"},
    ]
    assert coordinator._woken_zones == {}


@pytest.mark.asyncio
async def test_a_woken_zone_goes_off_when_the_master_is_already_off(hass, mock_config_entry):
    coordinator, group, rooms, states = _woken_zone_setup(hass, mock_config_entry, master_mode="off")

    await _wake_then_idle(coordinator, group, rooms, states, hass)

    assert len(_zone_offs(hass)) == 1


@pytest.mark.asyncio
async def test_a_woken_zone_stays_while_the_master_runs(hass, mock_config_entry):
    coordinator, group, rooms, states = _woken_zone_setup(hass, mock_config_entry)
    await coordinator._async_wake_member_zone(group, {"room_a": {"commanded_mode": "heating"}}, rooms)
    states["climate.zone_b"] = _make_ac_zone_state("fan_only")
    hass.services.async_call.reset_mock()

    await coordinator._async_control_master_devices(
        {"room_a": {"mode": "heating", "commanded_mode": "heating"}}, rooms, {"climate_control_active": True}
    )

    assert _zone_offs(hass) == []
    assert coordinator._woken_zones == {"g1": "climate.zone_b"}


@pytest.mark.asyncio
@pytest.mark.parametrize("zone_mode", ["cool", "off"])
async def test_a_woken_zone_someone_switched_is_left_alone(hass, mock_config_entry, zone_mode):
    coordinator, group, rooms, states = _woken_zone_setup(hass, mock_config_entry)
    await coordinator._async_wake_member_zone(group, {"room_a": {"commanded_mode": "heating"}}, rooms)
    states["climate.zone_b"] = _make_ac_zone_state(zone_mode)
    hass.services.async_call.reset_mock()

    await coordinator._async_control_master_devices(
        {"room_a": {"mode": "idle", "commanded_mode": "idle"}}, rooms, {"climate_control_active": True}
    )

    assert _zone_offs(hass) == []
    assert coordinator._woken_zones == {}


@pytest.mark.asyncio
async def test_a_woken_zone_a_room_took_over_is_left_to_that_room(hass, mock_config_entry):
    coordinator, group, rooms, states = _woken_zone_setup(hass, mock_config_entry)
    await coordinator._async_wake_member_zone(group, {"room_a": {"commanded_mode": "heating"}}, rooms)
    states["climate.zone_b"] = _make_ac_zone_state("fan_only")
    rooms["room_b"] = _room_with_device("room_b", "climate.zone_b")
    hass.services.async_call.reset_mock()

    await coordinator._async_control_master_devices(
        {"room_a": {"mode": "idle", "commanded_mode": "idle"}, "room_b": {"mode": "idle", "commanded_mode": "idle"}},
        rooms,
        {"climate_control_active": True},
    )

    assert _zone_offs(hass) == []


@pytest.mark.asyncio
async def test_a_woken_zone_gets_nothing_while_climate_control_is_off(hass, mock_config_entry):
    """#36: with climate control off RoomMind sends nothing, the zone keeps its mark."""
    coordinator, group, rooms, states = _woken_zone_setup(hass, mock_config_entry)
    await coordinator._async_wake_member_zone(group, {"room_a": {"commanded_mode": "heating"}}, rooms)
    states["climate.zone_b"] = _make_ac_zone_state("fan_only")
    hass.services.async_call.reset_mock()

    await coordinator._async_control_master_devices(
        {"room_a": {"mode": "idle", "commanded_mode": "idle"}}, rooms, {"climate_control_active": False}
    )

    assert hass.services.async_call.call_args_list == []
    assert coordinator._woken_zones == {"g1": "climate.zone_b"}


@pytest.mark.asyncio
async def test_a_failed_switch_off_of_the_woken_zone_is_retried(hass, mock_config_entry):
    coordinator, group, rooms, states = _woken_zone_setup(hass, mock_config_entry, master_mode="off")
    await coordinator._async_wake_member_zone(group, {"room_a": {"commanded_mode": "heating"}}, rooms)
    states["climate.zone_b"] = _make_ac_zone_state("fan_only")

    async def fail_zone(domain, service, data, **kwargs):
        if data.get("entity_id") == "climate.zone_b":
            raise RuntimeError("zone unreachable")

    hass.services.async_call = AsyncMock(side_effect=fail_zone)
    idle = {"room_a": {"mode": "idle", "commanded_mode": "idle"}}
    await coordinator._async_control_master_devices(idle, rooms, {"climate_control_active": True})
    assert coordinator._woken_zones == {"g1": "climate.zone_b"}

    hass.services.async_call = AsyncMock()
    await coordinator._async_control_master_devices(idle, rooms, {"climate_control_active": True})
    assert len(_zone_offs(hass)) == 1
    assert coordinator._woken_zones == {}


@pytest.mark.asyncio
async def test_a_woken_zone_of_a_room_is_not_marked(hass, mock_config_entry):
    """A zone a room drives is switched off by that room's own cycle."""
    rooms = {
        "room_a": _room_with_device("room_a", "climate.zone_a"),
        "room_b": _room_with_device("room_b", "climate.zone_b"),
    }
    states = {
        "climate.zone_a": _make_ac_zone_state("off", hvac_modes=["off", "heat"]),
        "climate.zone_b": _make_ac_zone_state("off"),
    }
    coordinator, group = _wake_coordinator(hass, mock_config_entry, rooms, states)

    await coordinator._async_wake_member_zone(group, {"room_a": {"commanded_mode": "heating"}}, rooms)

    assert _fan_only_wakes(hass) == ["climate.zone_b"]
    assert coordinator._woken_zones == {}


class TestUniformModeSetback:
    """A setback unit must not keep the opposite mode in a uniform-mode group (#533)."""

    @staticmethod
    async def _cycle_with_group_action(hass, mock_config_entry, action):
        room = {
            **SAMPLE_ROOM,
            "thermostats": [],
            "acs": ["climate.ac_living"],
            "devices": [
                {
                    "entity_id": "climate.ac_living",
                    "type": "ac",
                    "role": "auto",
                    "heating_system_type": "",
                    "idle_action": "setback",
                }
            ],
        }
        store = _make_store_mock(
            {"living_room_abc12345": room},
            settings={
                "climate_control_active": True,
                "compressor_groups": [
                    {
                        "id": "g1",
                        "name": "G1",
                        "members": ["climate.ac_living", "climate.ac_other"],
                        "enforce_uniform_mode": True,
                    }
                ],
            },
        )
        ac_attrs = {"hvac_modes": ["heat", "cool", "off"], "min_temp": 16, "max_temp": 30, "temperature": 21.0}
        # 22 °C sits between comfort heat 21 and cool 24: the room idles.
        hass.states.get = make_mock_states_get(temp="22.0", extra={"climate.ac_living": ("heat", ac_attrs)})
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}
        coordinator = _create_coordinator(hass, mock_config_entry)
        coordinator._compressor_manager.load_groups(store.get_settings()["compressor_groups"])
        coordinator._compressor_manager.set_master_action("g1", action)
        await coordinator._async_update_data()
        return [
            c.args[2]
            for c in hass.services.async_call.call_args_list
            if c.args[0] == "climate" and c.args[2].get("entity_id") == "climate.ac_living"
        ]

    @pytest.mark.asyncio
    async def test_heat_setback_switches_off_when_the_group_cools(self, hass, mock_config_entry):
        calls = await self._cycle_with_group_action(hass, mock_config_entry, "cool")
        assert {"entity_id": "climate.ac_living", "hvac_mode": "off"} in calls

    @pytest.mark.asyncio
    async def test_heat_setback_stays_while_the_group_heats(self, hass, mock_config_entry):
        calls = await self._cycle_with_group_action(hass, mock_config_entry, "heat")
        assert not any(c.get("hvac_mode") == "off" for c in calls)
        assert {"entity_id": "climate.ac_living", "temperature": 19.0} in calls

    @pytest.mark.asyncio
    @pytest.mark.parametrize("master_refuses_once", [False, True])
    async def test_units_in_the_old_mode_go_off_before_the_group_switches(
        self, hass, mock_config_entry, master_refuses_once
    ):
        """Order of a switch: the unit in heat goes off before anything runs the other way (#533)."""

        def ac(eid):
            return [
                {"entity_id": eid, "type": "ac", "role": "auto", "heating_system_type": "", "idle_action": "setback"}
            ]

        living = {**SAMPLE_ROOM, "thermostats": [], "acs": ["climate.ac_living"], "devices": ac("climate.ac_living")}
        sunroom = {
            **SAMPLE_ROOM,
            "area_id": "sunroom",
            "thermostats": [],
            "acs": ["climate.ac_sun"],
            "devices": ac("climate.ac_sun"),
            "temperature_sensor": "sensor.sun_temp",
            "humidity_sensor": "",
        }
        store = _make_store_mock(
            {"living_room_abc12345": living, "sunroom": sunroom},
            settings={
                "climate_control_active": True,
                "compressor_groups": [
                    {
                        "id": "g1",
                        "name": "G1",
                        "members": ["climate.ac_living", "climate.ac_sun"],
                        "master_entity": "climate.outdoor",
                        "action_script": "script.outdoor_mode",
                        "enforce_uniform_mode": True,
                    }
                ],
            },
        )
        ac_attrs = {"hvac_modes": ["heat", "cool", "off"], "min_temp": 16, "max_temp": 30, "temperature": 21.0}
        modes = {"climate.ac_living": "heat", "climate.ac_sun": "off", "climate.outdoor": "off"}
        base_get = make_mock_states_get(
            temp="22.0",
            outdoor_temp="20.0",
            extra={"sensor.sun_temp": ("27.0", {}), "script.outdoor_mode": ("off", {})},
        )

        def states_get(eid):
            if eid in modes:
                st = MagicMock()
                st.state = modes[eid]
                st.attributes = {"hvac_modes": ["off", "heat", "cool"]} if eid == "climate.outdoor" else ac_attrs
                return st
            return base_get(eid)

        log: list[tuple[str, str]] = []
        refusals = [master_refuses_once]

        async def call(domain, service, data, **kwargs):
            eid = data.get("entity_id", "")
            if domain == "script":
                log.append(("script", service))
                return
            if service == "set_hvac_mode":
                if eid == "climate.outdoor" and refusals[0]:
                    refusals[0] = False
                    raise RuntimeError("indoor units in different modes")
                modes[eid] = data["hvac_mode"]
                log.append((eid, data["hvac_mode"]))

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock(side_effect=call)
        hass.data = {"roommind": {"store": store}}
        coordinator = _create_coordinator(hass, mock_config_entry)

        result = await coordinator._async_update_data()
        assert result["rooms"]["sunroom"]["mode"] == MODE_IDLE  # waits for the living room unit
        assert result["rooms"]["sunroom"]["group_wanted_mode"] == "cooling"
        assert coordinator._compressor_manager.get_state("g1").desired_action == "cool"
        assert log == []

        for _ in range(3):
            await coordinator._async_update_data()

        assert modes == {"climate.ac_living": "off", "climate.ac_sun": "cool", "climate.outdoor": "cool"}
        order = [entry[0] for entry in log]
        assert order[0] == "climate.ac_living"
        assert {"climate.ac_sun", "climate.outdoor", "script"} <= set(order[1:])

    @pytest.mark.asyncio
    async def test_a_room_waits_while_its_group_turns_the_other_way(self, hass, mock_config_entry):
        """The master has not followed the switch to cool yet: a room wanting heat does not start it (#533)."""
        room = {
            **SAMPLE_ROOM,
            "thermostats": [],
            "acs": ["climate.ac_living"],
            "devices": [{"entity_id": "climate.ac_living", "type": "ac", "role": "auto", "heating_system_type": ""}],
        }
        store = _make_store_mock(
            {"living_room_abc12345": room},
            settings={
                "climate_control_active": True,
                "compressor_groups": [
                    {
                        "id": "g1",
                        "name": "G1",
                        "members": ["climate.ac_living", "climate.ac_other"],
                        "enforce_uniform_mode": True,
                    }
                ],
            },
        )
        ac_attrs = {"hvac_modes": ["heat", "cool", "off"], "min_temp": 16, "max_temp": 30, "temperature": 21.0}
        hass.states.get = make_mock_states_get(temp="18.0", extra={"climate.ac_living": ("off", ac_attrs)})
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}
        coordinator = _create_coordinator(hass, mock_config_entry)
        manager = coordinator._compressor_manager
        manager.load_groups(store.get_settings()["compressor_groups"])
        manager.set_master_action("g1", "idle")
        manager.set_desired_action("g1", "cool")

        result = await coordinator._async_update_data()

        assert result["rooms"]["living_room_abc12345"]["mode"] == MODE_IDLE
        calls = [c.args[2] for c in hass.services.async_call.call_args_list if c.args[0] == "climate"]
        assert not any(c.get("hvac_mode") == "heat" for c in calls)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("climate_active", [True, False])
    async def test_a_stale_wish_is_dropped(self, hass, mock_config_entry, climate_active):
        """Master unavailable or climate control off: the old wish no longer switches units off."""
        store = _make_store_mock(
            {"living_room_abc12345": SAMPLE_ROOM},
            settings={
                "climate_control_active": climate_active,
                "compressor_groups": [
                    {
                        "id": "g1",
                        "name": "G1",
                        "members": ["climate.living_room"],
                        "master_entity": "climate.outdoor",
                        "enforce_uniform_mode": True,
                    }
                ],
            },
        )
        hass.states.get = make_mock_states_get(temp="22.0", extra={"climate.outdoor": ("unavailable", {})})
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}
        coordinator = _create_coordinator(hass, mock_config_entry)
        manager = coordinator._compressor_manager
        manager.load_groups(store.get_settings()["compressor_groups"])
        manager.set_desired_action("g1", "cool")

        await coordinator._async_update_data()

        assert manager.get_state("g1").desired_action is None

    @staticmethod
    def _cooling_room_next_to(hass, mock_config_entry, other_mode: str, own_mode: str = "off"):
        room = {
            **SAMPLE_ROOM,
            "thermostats": [],
            "acs": ["climate.ac_living"],
            "devices": [{"entity_id": "climate.ac_living", "type": "ac", "role": "auto", "heating_system_type": ""}],
            "climate_mode": "cool_only",
        }
        store = _make_store_mock(
            {"living_room_abc12345": room},
            settings={
                "climate_control_active": True,
                "compressor_groups": [
                    {
                        "id": "g1",
                        "name": "G1",
                        "members": ["climate.ac_living", "climate.ac_other"],
                        "enforce_uniform_mode": True,
                    }
                ],
            },
        )
        ac_attrs = {"hvac_modes": ["heat", "cool", "off"], "min_temp": 16, "max_temp": 30, "temperature": 21.0}
        hass.states.get = make_mock_states_get(
            temp="27.0",
            outdoor_temp="20.0",
            extra={"climate.ac_living": (own_mode, ac_attrs), "climate.ac_other": (other_mode, ac_attrs)},
        )
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}
        return _create_coordinator(hass, mock_config_entry)

    @pytest.mark.asyncio
    async def test_a_unit_roommind_may_not_touch_blocks_the_switch_five_minutes_at_most(
        self, hass, mock_config_entry, monkeypatch
    ):
        import custom_components.roommind.managers.compressor_group_manager as mod

        now = [1000.0]
        monkeypatch.setattr(mod, "monotonic", lambda: now[0])
        coordinator = self._cooling_room_next_to(hass, mock_config_entry, "heat")

        result = await coordinator._async_update_data()
        assert result["rooms"]["living_room_abc12345"]["mode"] == MODE_IDLE

        now[0] += 301
        result = await coordinator._async_update_data()
        assert result["rooms"]["living_room_abc12345"]["mode"] == "cooling"

    @pytest.mark.asyncio
    async def test_a_free_group_starts_at_once(self, hass, mock_config_entry):
        coordinator = self._cooling_room_next_to(hass, mock_config_entry, "cool")
        result = await coordinator._async_update_data()
        assert result["rooms"]["living_room_abc12345"]["mode"] == "cooling"
        assert coordinator._compressor_manager.get_state("g1").master_action == "cool"

    @pytest.mark.asyncio
    async def test_a_unit_in_its_min_run_in_the_wanted_mode_finishes_it(self, hass, mock_config_entry):
        """The group flips to heat while this unit still cools in its min run: it cools on, not reversed."""
        coordinator = self._cooling_room_next_to(hass, mock_config_entry, "off", own_mode="cool")
        manager = coordinator._compressor_manager
        manager.load_groups(hass.data["roommind"]["store"].get_settings()["compressor_groups"])
        manager.set_master_action("g1", "cool")
        manager.set_desired_action("g1", "heat")
        manager.check_must_stay_active = MagicMock(side_effect=lambda eid: eid == "climate.ac_living")

        result = await coordinator._async_update_data()

        assert result["rooms"]["living_room_abc12345"]["mode"] == "cooling"

    @pytest.mark.asyncio
    async def test_a_unit_in_its_min_run_in_the_old_mode_is_held_there(self, hass, mock_config_entry):
        """The room now wants cool, its unit still heats in its min run: no reversal, it heats out."""
        coordinator = self._cooling_room_next_to(hass, mock_config_entry, "off", own_mode="heat")
        manager = coordinator._compressor_manager
        manager.load_groups(hass.data["roommind"]["store"].get_settings()["compressor_groups"])
        manager.set_master_action("g1", "heat")
        manager.check_must_stay_active = MagicMock(side_effect=lambda eid: eid == "climate.ac_living")

        result = await coordinator._async_update_data()

        assert result["rooms"]["living_room_abc12345"]["mode"] != "cooling"
        calls = [c.args[2] for c in hass.services.async_call.call_args_list if c.args[0] == "climate"]
        assert not any(c.get("hvac_mode") in ("cool", "off") for c in calls)

    @pytest.mark.asyncio
    async def test_a_unit_of_the_other_mode_in_its_min_run_is_waited_for(self, hass, mock_config_entry, monkeypatch):
        import custom_components.roommind.managers.compressor_group_manager as mod

        now = [1000.0]
        monkeypatch.setattr(mod, "monotonic", lambda: now[0])
        coordinator = self._cooling_room_next_to(hass, mock_config_entry, "heat")
        manager = coordinator._compressor_manager
        manager.load_groups(hass.data["roommind"]["store"].get_settings()["compressor_groups"])
        manager.check_must_stay_active = MagicMock(side_effect=lambda eid: eid == "climate.ac_other")

        await coordinator._async_update_data()
        now[0] += 301
        result = await coordinator._async_update_data()

        assert result["rooms"]["living_room_abc12345"]["mode"] == MODE_IDLE


@pytest.mark.parametrize(
    ("state", "action", "expected"),
    [
        (None, None, None),
        ("heat", None, "heat"),
        ("heat_cool", "heating", "heat"),
        ("auto", "cooling", "cool"),
        ("auto", "fan", "fan_only"),
        ("heat_cool", "idle", None),
    ],
)
def test_uniform_mode_reads_heat_cool_units_by_what_they_do(state, action, expected):
    from custom_components.roommind.coordinator import _uniform_mode

    st = None
    if state is not None:
        st = MagicMock()
        st.state = state
        st.attributes = {"hvac_action": action} if action else {}
    assert _uniform_mode(st) == expected


class TestUniformModeRound5:
    """Same-cycle starts, display, Managed rooms, untouchable units, restart (#533)."""

    @staticmethod
    def _house(hass, mock_config_entry, *, living_temp="18.0", sun_temp="27.0", modes=None, managed=False, extra=None):
        def ac(eid):
            return [{"entity_id": eid, "type": "ac", "role": "auto", "heating_system_type": ""}]

        living = {**SAMPLE_ROOM, "thermostats": [], "acs": ["climate.ac_living"], "devices": ac("climate.ac_living")}
        if managed:
            living["temperature_sensor"] = ""
        sunroom = {
            **SAMPLE_ROOM,
            "area_id": "sunroom",
            "thermostats": [],
            "acs": ["climate.ac_sun"],
            "devices": ac("climate.ac_sun"),
            "temperature_sensor": "sensor.sun_temp",
            "humidity_sensor": "",
        }
        store = _make_store_mock(
            {"living_room_abc12345": living, "sunroom": sunroom},
            settings={
                "climate_control_active": True,
                "compressor_groups": [
                    {
                        "id": "g1",
                        "name": "G1",
                        "members": ["climate.ac_living", "climate.ac_sun"],
                        "enforce_uniform_mode": True,
                        **(extra or {}),
                    }
                ],
            },
        )
        attrs = {"hvac_modes": ["heat", "cool", "fan_only", "off"], "min_temp": 16, "max_temp": 30, "temperature": 21.0}
        states = {"climate.ac_living": "off", "climate.ac_sun": "off", **(modes or {})}
        base_get = make_mock_states_get(
            temp=living_temp, outdoor_temp="19.0", extra={"sensor.sun_temp": (sun_temp, {})}
        )

        def states_get(eid):
            if eid in states:
                st = MagicMock()
                st.state = states[eid]
                st.attributes = dict(attrs)
                return st
            return base_get(eid)

        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()
        hass.data = {"roommind": {"store": store}}
        return _create_coordinator(hass, mock_config_entry)

    @staticmethod
    def _modes_sent(hass, eid):
        return [
            c.args[2]["hvac_mode"]
            for c in hass.services.async_call.call_args_list
            if c.args[0] == "climate" and c.args[1] == "set_hvac_mode" and c.args[2].get("entity_id") == eid
        ]

    @pytest.mark.asyncio
    async def test_two_rooms_never_start_opposite_ways_in_one_cycle(self, hass, mock_config_entry):
        """After a restart the states show nothing yet: only the first room starts (states do not follow here)."""
        coordinator = self._house(hass, mock_config_entry)
        result = await coordinator._async_update_data()

        started = {eid: self._modes_sent(hass, eid) for eid in ("climate.ac_living", "climate.ac_sun")}
        assert not ("heat" in started["climate.ac_living"] and "cool" in started["climate.ac_sun"])
        held = [a for a, r in result["rooms"].items() if r.get("group_wanted_mode")]
        assert len(held) == 1
        assert result["rooms"][held[0]]["compressor_protection_reason"] == "uniform_mode"
        assert result["rooms"][held[0]]["compressor_protection_active"] is True

    @pytest.mark.asyncio
    async def test_managed_room_units_follow_the_group_mode(self, hass, mock_config_entry):
        """A Managed auto room has no demand of its own: its unit takes the group's mode, not heat_cool."""
        coordinator = self._house(hass, mock_config_entry, managed=True, sun_temp="22.0")
        manager = coordinator._compressor_manager
        manager.load_groups(hass.data["roommind"]["store"].get_settings()["compressor_groups"])
        manager.set_master_action("g1", "cool")

        result = await coordinator._async_update_data()

        assert "cool" in self._modes_sent(hass, "climate.ac_living")
        assert "heat_cool" not in self._modes_sent(hass, "climate.ac_living")
        assert result["rooms"]["living_room_abc12345"].get("managed_follows_group") is True

    @pytest.mark.asyncio
    async def test_managed_room_votes_with_what_its_units_do(self, hass, mock_config_entry):
        coordinator = self._house(hass, mock_config_entry, managed=True, sun_temp="22.0")
        rooms = hass.data["roommind"]["store"].get_rooms()
        rs = {"living_room_abc12345": {"managed_follows_group": True, "commanded_mode": "heating"}}
        heating = MagicMock()
        heating.state = "heat"
        heating.attributes = {"hvac_action": "idle"}
        hass.states.get = MagicMock(return_value=heating)
        modes = coordinator._collect_member_room_modes(["climate.ac_living"], rs, rooms, {})
        assert modes == ["idle"]
        heating.attributes = {"hvac_action": "cooling"}
        assert coordinator._collect_member_room_modes(["climate.ac_living"], rs, rooms, {}) == ["cooling"]
        heating.attributes = {"hvac_action": "heating"}
        assert coordinator._collect_member_room_modes(["climate.ac_living"], rs, rooms, {}) == ["heating"]

    @pytest.mark.asyncio
    async def test_a_unit_waited_for_once_does_not_hold_the_next_switch(self, hass, mock_config_entry, monkeypatch):
        import custom_components.roommind.managers.compressor_group_manager as mod

        now = [1000.0]
        monkeypatch.setattr(mod, "monotonic", lambda: now[0])
        coordinator = self._house(hass, mock_config_entry, modes={"climate.ac_living": "fan_only"})
        manager = coordinator._compressor_manager
        manager.load_groups(hass.data["roommind"]["store"].get_settings()["compressor_groups"])
        group = manager.get_groups()["g1"]

        assert coordinator._uniform_switch_pending("g1", group, "heat", set()) is True
        now[0] += 301
        assert coordinator._uniform_switch_pending("g1", group, "heat", set()) is False
        manager.set_master_action("g1", "heat")
        manager.set_master_action("g1", "idle")
        assert coordinator._uniform_switch_pending("g1", group, "heat", set()) is False

    @pytest.mark.asyncio
    async def test_restart_reads_the_way_the_group_ran(self, hass, mock_config_entry):
        coordinator = self._house(hass, mock_config_entry, modes={"climate.ac_sun": "heat"})
        coordinator._compressor_manager.load_groups(hass.data["roommind"]["store"].get_settings()["compressor_groups"])
        coordinator._seed_uniform_modes()
        assert coordinator._compressor_manager.get_state("g1").last_mode_action == "heat"

    @pytest.mark.asyncio
    async def test_no_fan_only_wake_before_a_uniform_group_heats(self, hass, mock_config_entry):
        coordinator = self._house(
            hass,
            mock_config_entry,
            living_temp="18.0",
            sun_temp="22.0",
            modes={"climate.outdoor": "off"},
            extra={"master_entity": "climate.outdoor"},
        )
        await coordinator._async_update_data()
        assert "fan_only" not in self._modes_sent(hass, "climate.ac_living")
        assert "fan_only" not in self._modes_sent(hass, "climate.ac_sun")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("uniform", [True, False])
    async def test_an_unreadable_master_keeps_its_guard(self, hass, mock_config_entry, uniform):
        """A blip of the master keeps its applied action and timers; a uniform group stops trusting it meanwhile."""
        coordinator = self._house(
            hass,
            mock_config_entry,
            modes={"climate.outdoor": "unavailable"},
            extra={"master_entity": "climate.outdoor", "enforce_uniform_mode": uniform},
        )
        manager = coordinator._compressor_manager
        manager.load_groups(hass.data["roommind"]["store"].get_settings()["compressor_groups"])
        manager.set_master_action("g1", "heat")
        on_since = manager.get_state("g1").master_on_since

        await coordinator._async_update_data()

        state = manager.get_state("g1")
        assert state.master_action == "heat"
        assert state.master_on_since == on_since
        assert manager.check_master_can_switch("g1", "idle") is False  # min run still holds
        assert state.master_unreadable is uniform
        assert manager.get_enforced_action("climate.ac_living") is None

    @pytest.mark.asyncio
    async def test_a_readable_master_is_trusted_again(self, hass, mock_config_entry):
        coordinator = self._house(
            hass, mock_config_entry, modes={"climate.outdoor": "heat"}, extra={"master_entity": "climate.outdoor"}
        )
        manager = coordinator._compressor_manager
        manager.load_groups(hass.data["roommind"]["store"].get_settings()["compressor_groups"])
        manager.get_state("g1").master_unreadable = True
        await coordinator._async_update_data()
        assert manager.get_state("g1").master_unreadable is False

    @pytest.mark.asyncio
    async def test_managed_room_keeps_its_own_way_while_the_group_idles(self, hass, mock_config_entry):
        """An idle group with a last mode does not pin a Managed unit to it."""
        coordinator = self._house(hass, mock_config_entry, managed=True, sun_temp="22.0")
        manager = coordinator._compressor_manager
        manager.load_groups(hass.data["roommind"]["store"].get_settings()["compressor_groups"])
        manager.set_master_action("g1", "heat")
        manager.set_master_action("g1", "idle")
        assert manager.managed_mode("climate.ac_living") is None
        assert manager.managed_mode("climate.unknown") is None

    @pytest.mark.asyncio
    async def test_managed_unit_stays_off_while_its_group_turns(self, hass, mock_config_entry):
        coordinator = self._house(hass, mock_config_entry, managed=True, sun_temp="22.0")
        manager = coordinator._compressor_manager
        manager.load_groups(hass.data["roommind"]["store"].get_settings()["compressor_groups"])
        manager.set_master_action("g1", "heat")
        manager.set_desired_action("g1", "cool")
        assert manager.managed_mode("climate.ac_living") == "off"

        await coordinator._async_update_data()

        assert "cool" not in self._modes_sent(hass, "climate.ac_living")
        assert "heat" not in self._modes_sent(hass, "climate.ac_living")

    def test_managed_vote_reads_the_unit_against_the_band(self, hass, mock_config_entry):
        coordinator = self._house(hass, mock_config_entry, managed=True)
        st = MagicMock()
        st.attributes = {"hvac_action": "idle", "current_temperature": 28.0}
        assert coordinator._managed_vote(st, 21.0, 24.0) == "cooling"
        st.attributes = {"current_temperature": 18.0}
        assert coordinator._managed_vote(st, 21.0, 24.0) == "heating"
        st.attributes = {"current_temperature": 22.0}
        assert coordinator._managed_vote(st, 21.0, 24.0) == "idle"
        st.attributes = {"hvac_action": "heating"}
        assert coordinator._managed_vote(st, 21.0, 24.0) == "heating"
        st.attributes = {"hvac_action": "cooling"}
        assert coordinator._managed_vote(st, 21.0, 24.0) == "cooling"
        st.attributes = {"current_temperature": "n/a"}
        assert coordinator._managed_vote(st, 21.0, 24.0) == "idle"
        st.attributes = {}
        assert coordinator._managed_vote(st, 21.0, 24.0) == "idle"
        assert coordinator._managed_vote(None, 21.0, 24.0) == "idle"

    @pytest.mark.asyncio
    async def test_an_ignored_unit_counts_again_once_it_changes_mode(self, hass, mock_config_entry, monkeypatch):
        import custom_components.roommind.managers.compressor_group_manager as mod

        now = [1000.0]
        monkeypatch.setattr(mod, "monotonic", lambda: now[0])
        coordinator = self._house(hass, mock_config_entry, modes={"climate.ac_living": "fan_only"})
        manager = coordinator._compressor_manager
        manager.load_groups(hass.data["roommind"]["store"].get_settings()["compressor_groups"])
        group = manager.get_groups()["g1"]
        coordinator._uniform_switch_pending("g1", group, "heat", set())
        now[0] += 301
        coordinator._uniform_switch_pending("g1", group, "heat", set())
        assert manager.get_state("g1").switch_ignored == {"climate.ac_living": "fan_only"}

        manager.get_state("g1").switch_ignored["climate.ac_living"] = "dry"  # it changed meanwhile
        assert coordinator._uniform_switch_pending("g1", group, "heat", set()) is True
        assert "climate.ac_living" not in manager.get_state("g1").switch_ignored

    @pytest.mark.asyncio
    async def test_a_held_room_reads_switching_while_its_own_way_is_pending(self, hass, mock_config_entry):
        """The group already wants cool but the outdoor unit still heats: the room waits for the switch."""
        coordinator = self._house(hass, mock_config_entry, living_temp="22.0", modes={"climate.ac_living": "heat"})
        manager = coordinator._compressor_manager
        manager.load_groups(hass.data["roommind"]["store"].get_settings()["compressor_groups"])
        manager.set_master_action("g1", "heat")
        manager.set_desired_action("g1", "cool")

        result = await coordinator._async_update_data()

        sun = result["rooms"]["sunroom"]
        assert sun["compressor_protection_reason"] == "uniform_mode"
        assert sun["uniform_group_mode"] is None
