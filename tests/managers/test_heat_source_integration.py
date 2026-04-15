"""Multi-cycle integration tests for heat source orchestration.

These tests simulate realistic scenarios over multiple coordinator cycles
to verify the heat source orchestrator correctly routes heating commands
to TRVs and/or ACs based on temperature gap, outdoor temperature, and
hysteresis rules.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.coordinator import RoomMindCoordinator
from custom_components.roommind.managers.heat_source_orchestrator import (
    DeviceCommand,
    HeatSourcePlan,
)
from custom_components.roommind.store import RoomMindStore

# ---------------------------------------------------------------------------
# Room template with both TRV and AC for heat source orchestration
# ---------------------------------------------------------------------------
ROOM_WITH_TRV_AND_AC = {
    "area_id": "living_room",
    "thermostats": ["climate.trv_living"],
    "acs": ["climate.ac_living"],
    "devices": [
        {"entity_id": "climate.trv_living", "type": "trv", "role": "auto", "heating_system_type": ""},
        {"entity_id": "climate.ac_living", "type": "ac", "role": "auto", "heating_system_type": ""},
    ],
    "temperature_sensor": "sensor.living_room_temp",
    "humidity_sensor": "sensor.living_room_humidity",
    "climate_mode": "auto",
    "schedules": [{"entity_id": "schedule.living_room"}],
    "schedule_selector_entity": "",
    "comfort_temp": 21.0,
    "eco_temp": 17.0,
    "window_sensors": [],
    "window_open_delay": 0,
    "window_close_delay": 0,
    "heating_system_type": "",
    "presence_persons": [],
    "heat_source_orchestration": True,
}

DEFAULT_SETTINGS = {"outdoor_temp_sensor": "sensor.outdoor_temp"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hass_states(
    temp="18.0",
    humidity="55.0",
    schedule_state="on",
    outdoor_temp="10.0",
    ac_hvac_modes=None,
    trv_hvac_modes=None,
    extra=None,
):
    """Build a ``hass.states.get`` side_effect with TRV + AC entities."""
    if ac_hvac_modes is None:
        ac_hvac_modes = ["off", "heat", "cool", "heat_cool"]
    if trv_hvac_modes is None:
        trv_hvac_modes = ["off", "heat"]
    if extra is None:
        extra = {}

    def _get(entity_id):
        entities = {
            "sensor.living_room_temp": ("state", temp, {}),
            "sensor.living_room_humidity": ("state", humidity, {}),
            "schedule.living_room": ("state", schedule_state, {}),
            "sensor.outdoor_temp": ("state", outdoor_temp, {}),
            "climate.trv_living": (
                "state",
                "idle",
                {"hvac_modes": trv_hvac_modes, "hvac_action": "idle"},
            ),
            "climate.ac_living": (
                "state",
                "idle",
                {"hvac_modes": ac_hvac_modes, "hvac_action": "idle"},
            ),
        }
        if entity_id in extra:
            val = extra[entity_id]
            s = MagicMock()
            if isinstance(val, tuple):
                s.state = val[0]
                s.attributes = val[1] if len(val) > 1 else {}
            else:
                s.state = val
                s.attributes = {}
            return s
        if entity_id in entities:
            _, state, attrs = entities[entity_id]
            s = MagicMock()
            s.state = state
            s.attributes = attrs
            return s
        return None

    return _get


async def _setup_store(store, room=None, settings=None):
    """Load store, save room and settings."""
    await store.async_load()
    r = room or ROOM_WITH_TRV_AND_AC
    await store.async_save_room(r["area_id"], r)
    await store.async_save_settings(settings or DEFAULT_SETTINGS)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def real_store(hass):
    s = RoomMindStore(hass)
    s._store = AsyncMock()
    s._store.async_load = AsyncMock(return_value=None)
    s._store.async_save = AsyncMock()
    return s


@pytest.fixture
def coordinator(hass, mock_config_entry, real_store):
    hass.data = {"roommind": {"store": real_store}}
    hass.services.async_call = AsyncMock()
    hass.states.get = MagicMock(side_effect=_make_hass_states())
    hass.config.latitude = 50.0
    hass.config.longitude = 10.0
    hass.config.units = MagicMock()
    hass.config.units.temperature_unit = "°C"
    with patch("homeassistant.helpers.frame.report_usage"):
        c = RoomMindCoordinator(hass, mock_config_entry)
    return c


def _service_calls(hass, domain="climate"):
    """Return list of (service, entity_id) from hass.services.async_call."""
    result = []
    for c in hass.services.async_call.call_args_list:
        args = c[0] if c[0] else ()
        kwargs = c[1] if c[1] else {}
        if len(args) >= 2 and args[0] == domain:
            svc = args[1]
            svc_data = args[2] if len(args) >= 3 else kwargs.get("service_data", {})
            eid = svc_data.get("entity_id", "?")
            result.append((svc, eid, svc_data))
    return result


def _calls_for_entity(hass, entity_id):
    """Filter service calls for a specific entity_id."""
    return [(svc, data) for svc, eid, data in _service_calls(hass) if eid == entity_id]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHeatSourceIntegration:
    """Multi-cycle integration tests for heat source orchestration."""

    @pytest.mark.asyncio
    async def test_small_gap_only_ac_receives_commands(self, coordinator, real_store, hass):
        """Small gap (0.5C): only secondary (AC) should actively heat.

        Inactive TRV is idled via async_idle_device (default idle_action=off),
        not kept in heat mode. (#168)
        """
        await _setup_store(real_store)

        # Gap = 21.0 - 20.5 = 0.5C, well below primary_delta (1.5C)
        hass.states.get = MagicMock(side_effect=_make_hass_states(temp="20.5", outdoor_temp="10.0"))

        await coordinator._async_update_data()

        trv_calls = _calls_for_entity(hass, "climate.trv_living")
        ac_calls = _calls_for_entity(hass, "climate.ac_living")

        # Inactive TRV: idled to off (not kept in heat mode).
        trv_mode_data = [d for svc, d in trv_calls if svc == "set_hvac_mode"]
        assert len(trv_mode_data) == 1, "TRV should be turned off"
        assert trv_mode_data[0]["hvac_mode"] == "off"

        # AC: should receive active heat commands
        ac_modes = [d for svc, d in ac_calls if svc == "set_hvac_mode"]
        assert len(ac_modes) > 0, "AC should receive hvac_mode command"
        assert ac_modes[0]["hvac_mode"] in ("heat", "heat_cool")

        # Orchestrator state should be "secondary"
        assert coordinator._heat_source_states.get("living_room") == "secondary"

    @pytest.mark.asyncio
    async def test_large_gap_both_devices_receive_commands(self, coordinator, real_store, hass):
        """Large gap (4C): both primary (TRV) and secondary (AC) should heat."""
        await _setup_store(real_store)

        # Gap = 21.0 - 17.0 = 4.0C, above large_gap threshold (1.5 * 2.0 = 3.0)
        hass.states.get = MagicMock(side_effect=_make_hass_states(temp="17.0", outdoor_temp="10.0"))

        await coordinator._async_update_data()

        trv_calls = _calls_for_entity(hass, "climate.trv_living")
        ac_calls = _calls_for_entity(hass, "climate.ac_living")

        # Both devices should get heat commands
        trv_modes = [d for svc, d in trv_calls if svc == "set_hvac_mode"]
        assert len(trv_modes) > 0
        assert trv_modes[0]["hvac_mode"] == "heat"

        ac_modes = [d for svc, d in ac_calls if svc == "set_hvac_mode"]
        assert len(ac_modes) > 0
        assert ac_modes[0]["hvac_mode"] in ("heat", "heat_cool")

        # TRV should get a proportional setpoint (NOT just effective_target)
        trv_temps = [d for svc, d in trv_calls if svc == "set_temperature"]
        assert len(trv_temps) > 0
        # With large gap in "both" mode, TRV should be actively heating
        # so setpoint should be above effective_target (21.0)
        assert trv_temps[0]["temperature"] >= 21.0

        # Orchestrator state should be "both"
        # Need gap > large_gap_threshold + hysteresis = 3.0 + 0.3 = 3.3C from "none"
        # Gap is 4.0C, so should be "both"
        assert coordinator._heat_source_states.get("living_room") == "both"

    @pytest.mark.asyncio
    async def test_gap_shrinks_transitions_from_both_to_secondary_with_hysteresis(self, coordinator, real_store, hass):
        """Hysteresis test: gap shrinks from 'both' and stays until below threshold."""
        await _setup_store(real_store)

        # --- Cycle 1: large gap -> both ---
        hass.states.get = MagicMock(side_effect=_make_hass_states(temp="17.0", outdoor_temp="10.0"))
        await coordinator._async_update_data()
        assert coordinator._heat_source_states.get("living_room") == "both"

        # --- Cycle 2: gap narrows to 1.3C ---
        # primary_delta - hysteresis = 1.5 - 0.3 = 1.2
        # Gap 1.3C > 1.2, so hysteresis keeps us on "both"
        hass.services.async_call.reset_mock()
        # Backdate mode_on_since to bypass any min-run window
        coordinator._mode_on_since["living_room"] = coordinator._mode_on_since.get("living_room", 0) - 4000
        hass.states.get = MagicMock(side_effect=_make_hass_states(temp="19.7", outdoor_temp="10.0"))
        await coordinator._async_update_data()
        assert coordinator._heat_source_states.get("living_room") == "both", (
            "Should stay on 'both' due to hysteresis (gap 1.3 > 1.2)"
        )

        # --- Cycle 3: gap narrows to 0.8C ---
        # 0.8 < primary_delta - hysteresis = 1.2, so should switch to "secondary"
        hass.services.async_call.reset_mock()
        coordinator._mode_on_since["living_room"] = coordinator._mode_on_since.get("living_room", 0) - 4000
        hass.states.get = MagicMock(side_effect=_make_hass_states(temp="20.2", outdoor_temp="10.0"))
        await coordinator._async_update_data()
        assert coordinator._heat_source_states.get("living_room") == "secondary", (
            "Should switch to 'secondary' when gap drops below hysteresis band"
        )

    @pytest.mark.asyncio
    async def test_extreme_cold_disables_ac_only_trv_heats(self, coordinator, real_store, hass):
        """Outdoor below ac_min_outdoor (-15C): AC disabled, only TRV heats."""
        await _setup_store(real_store)

        # Gap = 3C, outdoor = -20C (below -15C default ac_min_outdoor)
        hass.states.get = MagicMock(side_effect=_make_hass_states(temp="18.0", outdoor_temp="-20.0"))

        await coordinator._async_update_data()

        trv_calls = _calls_for_entity(hass, "climate.trv_living")
        ac_calls = _calls_for_entity(hass, "climate.ac_living")

        # TRV should be actively heating
        trv_modes = [d for svc, d in trv_calls if svc == "set_hvac_mode"]
        assert len(trv_modes) > 0
        assert trv_modes[0]["hvac_mode"] == "heat"

        # AC should NOT get heat/heat_cool mode. It may be turned off.
        ac_heat_modes = [
            d for svc, d in ac_calls if svc == "set_hvac_mode" and d["hvac_mode"] in ("heat", "heat_cool", "auto")
        ]
        assert len(ac_heat_modes) == 0, (
            "AC should NOT receive heating commands when outdoor temp is below ac_min_outdoor"
        )

    @pytest.mark.asyncio
    async def test_ekf_training_uses_adjusted_power_fraction(self, coordinator, real_store, hass):
        """When orchestration is active, EKF should receive adjusted power_fraction.

        The adjusted pf is the mean of per-device power_fractions from the plan,
        reflecting that not all devices are equally active.
        """
        await _setup_store(real_store)

        # Create a controlled plan: AC active at 0.8, TRV inactive at 0.0
        controlled_plan = HeatSourcePlan(
            commands=[
                DeviceCommand(
                    entity_id="climate.trv_living",
                    role="primary",
                    device_type="thermostat",
                    active=False,
                    power_fraction=0.0,
                    reason="not selected",
                ),
                DeviceCommand(
                    entity_id="climate.ac_living",
                    role="secondary",
                    device_type="ac",
                    active=True,
                    power_fraction=0.8,
                    reason="active",
                ),
            ],
            active_sources="secondary",
            reason="small gap",
        )

        # Expected mean pf = (0.0 + 0.8) / 2 = 0.4
        expected_ekf_pf = 0.4

        hass.states.get = MagicMock(side_effect=_make_hass_states(temp="20.5", outdoor_temp="10.0"))

        with patch(
            "custom_components.roommind.coordinator.evaluate_heat_sources",
            return_value=controlled_plan,
        ):
            await coordinator._async_update_data()

        # Verify the EKF training manager received the adjusted pf
        # Access the training manager's last call
        ekf_mgr = coordinator._ekf_training
        # The process method should have been called with adjusted pf
        # We check coordinator's ekf training by inspecting what was passed
        # Since _ekf_training.process is not mocked, we patch it to capture args
        calls_received = []
        original_process = ekf_mgr.process

        def capture_process(**kwargs):
            calls_received.append(kwargs)
            return original_process(**kwargs)

        # Run again with the capture
        hass.services.async_call.reset_mock()
        with (
            patch(
                "custom_components.roommind.coordinator.evaluate_heat_sources",
                return_value=controlled_plan,
            ),
            patch.object(ekf_mgr, "process", side_effect=capture_process),
        ):
            await coordinator._async_update_data()

        assert len(calls_received) > 0, "EKF training should have been called"
        ekf_call = calls_received[0]
        assert abs(ekf_call["ekf_pf"] - expected_ekf_pf) < 0.01, (
            f"EKF pf should be {expected_ekf_pf} (mean of device pfs), got {ekf_call['ekf_pf']}"
        )

    @pytest.mark.asyncio
    async def test_orchestration_disabled_mid_session_cleans_state(self, coordinator, real_store, hass):
        """Disabling orchestration mid-session should clean up _heat_source_states."""
        await _setup_store(real_store)

        # Cycle 1: orchestration ON, large gap -> state populated
        hass.states.get = MagicMock(side_effect=_make_hass_states(temp="17.0", outdoor_temp="10.0"))
        await coordinator._async_update_data()
        assert "living_room" in coordinator._heat_source_states

        # Disable orchestration
        rooms = real_store.get_rooms()
        rooms["living_room"]["heat_source_orchestration"] = False
        # Persist the change
        await real_store.async_update_room("living_room", {"heat_source_orchestration": False})

        # Cycle 2: orchestration OFF -> state should be cleaned up
        hass.services.async_call.reset_mock()
        coordinator._mode_on_since["living_room"] = coordinator._mode_on_since.get("living_room", 0) - 4000
        hass.states.get = MagicMock(side_effect=_make_hass_states(temp="17.0", outdoor_temp="10.0"))
        await coordinator._async_update_data()

        assert "living_room" not in coordinator._heat_source_states, (
            "Heat source state should be removed when orchestration is disabled"
        )

        # Both devices should get normal heating commands (non-orchestrated)
        trv_calls = _calls_for_entity(hass, "climate.trv_living")
        ac_calls = _calls_for_entity(hass, "climate.ac_living")

        trv_modes = [d for svc, d in trv_calls if svc == "set_hvac_mode"]
        ac_modes = [d for svc, d in ac_calls if svc == "set_hvac_mode"]

        assert len(trv_modes) > 0, "TRV should get commands with orchestration off"
        assert trv_modes[0]["hvac_mode"] == "heat"
        assert len(ac_modes) > 0, "AC should get commands with orchestration off"
        assert ac_modes[0]["hvac_mode"] in ("heat", "heat_cool")

    @pytest.mark.asyncio
    async def test_weather_preference_switches_with_outdoor_temp_change(self, coordinator, real_store, hass):
        """Outdoor temp change affects whether primary or secondary is preferred.

        Medium gap with mild weather -> secondary (AC preferred).
        Medium gap with cold weather -> primary (boiler/TRV preferred).
        """
        await _setup_store(real_store)

        # Medium gap: 2.0C. This is above primary_delta + hysteresis (1.5 + 0.3 = 1.8)
        # from "none" state, so weather decides.
        # Outdoor = 12C (above outdoor_threshold=5C) -> secondary preferred
        hass.states.get = MagicMock(side_effect=_make_hass_states(temp="19.0", outdoor_temp="12.0"))
        await coordinator._async_update_data()

        assert coordinator._heat_source_states.get("living_room") == "secondary", (
            "Mild weather (12C > 5C threshold) should prefer secondary (AC)"
        )

        # Verify AC got active commands, TRV got low setpoint
        ac_calls_c1 = _calls_for_entity(hass, "climate.ac_living")
        ac_heat_c1 = [d for svc, d in ac_calls_c1 if svc == "set_hvac_mode" and d["hvac_mode"] in ("heat", "heat_cool")]
        assert len(ac_heat_c1) > 0, "AC should be actively heating in mild weather"

        # --- Cycle 2: cold weather ---
        # From "secondary", need delta >= primary_delta + hysteresis = 1.8 to switch
        # to "primary". Keep gap at 2.0 (still >= 1.8).
        # But the hysteresis logic: from secondary, delta_t < primary_delta - hysteresis
        # = 1.2 would go to secondary. delta_t >= 1.2 stays secondary.
        # Actually re-reading the code: from "secondary" (else branch), it re-evaluates:
        #   large_gap >= 3.3 -> both
        #   >= 1.8 -> weather decides (cold -> primary)
        #   else -> secondary
        # So gap=2.0 >= 1.8 and outdoor=-5 < 5 -> primary
        hass.services.async_call.reset_mock()
        coordinator._mode_on_since["living_room"] = coordinator._mode_on_since.get("living_room", 0) - 4000
        # Reset _heat_source_states to "none" to avoid secondary->secondary hysteresis
        # In real use, after several cycles in secondary, dropping outdoor temp would
        # mean the "else" branch re-evaluates, but previous_active_sources="secondary"
        # falls into the else branch (not "both" or "primary").
        hass.states.get = MagicMock(side_effect=_make_hass_states(temp="19.0", outdoor_temp="-5.0"))
        await coordinator._async_update_data()

        assert coordinator._heat_source_states.get("living_room") == "primary", (
            "Cold weather (-5C < 5C threshold) should prefer primary (TRV/boiler)"
        )

        # Verify TRV gets active heating
        trv_calls_c2 = _calls_for_entity(hass, "climate.trv_living")
        trv_modes_c2 = [d for svc, d in trv_calls_c2 if svc == "set_hvac_mode"]
        assert len(trv_modes_c2) > 0
        assert trv_modes_c2[0]["hvac_mode"] == "heat"

        # TRV should have a setpoint above effective_target since it's actively heating
        trv_temps_c2 = [d for svc, d in trv_calls_c2 if svc == "set_temperature"]
        assert len(trv_temps_c2) > 0
        assert trv_temps_c2[0]["temperature"] >= 21.0

    @pytest.mark.asyncio
    async def test_sensor_dropout_clears_stale_orchestration_state(self, coordinator, real_store, hass):
        """Stale _heat_source_states must be cleared when the orchestrator
        returns None (e.g. sensor dropout).  Otherwise the master-demand
        filter would act on the previous decision while the non-orchestrated
        fallback path is already commanding all devices.
        """
        await _setup_store(real_store)

        # Cycle 1: normal conditions -> orchestrator sets state to "secondary".
        hass.states.get = MagicMock(side_effect=_make_hass_states(temp="20.5", outdoor_temp="10.0"))
        await coordinator._async_update_data()
        assert coordinator._heat_source_states.get("living_room") == "secondary"

        # Cycle 2: temperature sensor goes unavailable -> coordinator's
        # current_temp becomes None -> orchestrator returns None.
        # Drive the coordinator through this state explicitly via the
        # evaluate_heat_sources patch to avoid relying on other fallbacks.
        hass.services.async_call.reset_mock()
        coordinator._mode_on_since["living_room"] = coordinator._mode_on_since.get("living_room", 0) - 4000
        hass.states.get = MagicMock(side_effect=_make_hass_states(temp="20.5", outdoor_temp="10.0"))
        with patch(
            "custom_components.roommind.coordinator.evaluate_heat_sources",
            return_value=None,
        ):
            await coordinator._async_update_data()

        assert "living_room" not in coordinator._heat_source_states, (
            "Stale orchestration state must be cleared when the orchestrator "
            "returns None so the master-demand filter doesn't act on it"
        )
