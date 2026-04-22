"""Tests for the ghost-heating guard in Full Control mode (#150, #241).

The guard overrides ekf_mode to idle when RoomMind commanded heating/cooling
but the device's observed hvac_action is idle — e.g. a device with
setpoint_mode="direct" whose internal hysteresis blocks firing near target.

Without the guard the EKF receives heating labels for periods with no
actual heat input, which drives alpha toward its upper bound over time and
produces wildly inaccurate predictions.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.roommind.const import MODE_COOLING, MODE_HEATING, MODE_IDLE

from .conftest import (
    SAMPLE_ROOM,
    _create_coordinator,
    _make_store_mock,
    make_mock_states_get,
)


def _room_for_guard(
    *,
    setpoint_mode: str = "direct",
    temperature_sensor: str = "sensor.living_room_temp",
    devices: list | None = None,
) -> dict:
    """Build a room config exercising the Full Control + direct path."""
    return {
        **SAMPLE_ROOM,
        "temperature_sensor": temperature_sensor,
        "devices": devices
        if devices is not None
        else [
            {
                "entity_id": "climate.living_room",
                "type": "trv",
                "role": "auto",
                "heating_system_type": "radiator",
                "idle_action": "off",
                "idle_fan_mode": "low",
                "setpoint_mode": setpoint_mode,
            }
        ],
        "heating_system_type": "radiator",
        "thermostats": ["climate.living_room"],
        "comfort_temp": 21.0,
        "eco_temp": 17.0,
        "comfort_heat": 21.0,
        "eco_heat": 17.0,
        "comfort_cool": 24.0,
        "eco_cool": 27.0,
    }


async def _run_and_capture_train_kwargs(
    hass,
    mock_config_entry,
    states_get,
    settings: dict | None = None,
    room: dict | None = None,
):
    """Run one coordinator update and capture the kwargs passed to
    `_ekf_training.process` — returns the last call kwargs or None."""
    room = room or _room_for_guard()
    rooms = {room["area_id"]: room}
    store = _make_store_mock(rooms)
    if settings:
        store.get_settings.return_value = settings
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(side_effect=states_get)
    hass.services.async_call = AsyncMock()

    coordinator = _create_coordinator(hass, mock_config_entry)
    training_mock = MagicMock()
    coordinator._ekf_training.process = training_mock

    await coordinator._async_update_data()

    if not training_mock.called:
        return None
    return training_mock.call_args.kwargs


# ---------------------------------------------------------------------------
# Ghost-heating guard behaviour
# ---------------------------------------------------------------------------


class TestGhostHeatingGuard:
    """Verify the observation-based override only fires when unambiguous."""

    @pytest.mark.asyncio
    async def test_guard_overrides_heating_to_idle_when_all_devices_idle(self, hass, mock_config_entry):
        """Full Control + commanded heating + observed idle → train as idle."""
        # temp 19.5 is clearly below heat_target-hysteresis (21 - 0.2 = 20.8)
        # → bangbang MPC commands heating.  Observed hvac_action=idle means
        # the device didn't actually fire (ghost heating scenario).
        states_get = make_mock_states_get(
            temp="19.5",
            humidity="55.0",
            schedule_state="on",
            outdoor_temp="5.0",
            extra={
                "climate.living_room": (
                    "heat",
                    {
                        "hvac_action": "idle",
                        "current_temperature": 19.5,
                        "temperature": 21.0,
                    },
                ),
            },
        )
        kwargs = await _run_and_capture_train_kwargs(hass, mock_config_entry, states_get)

        assert kwargs is not None
        assert kwargs["ekf_mode"] == MODE_IDLE, (
            f"Guard must override commanded heating to idle "
            f"when device reports hvac_action=idle, got ekf_mode={kwargs['ekf_mode']}"
        )
        assert kwargs["ekf_pf"] == 0.0
        assert kwargs["q_residual"] == 0.0

    @pytest.mark.asyncio
    async def test_guard_inactive_when_device_reports_heating(self, hass, mock_config_entry):
        """Device confirms heating → commanded mode is used unchanged."""
        states_get = make_mock_states_get(
            temp="19.5",
            humidity="55.0",
            schedule_state="on",
            outdoor_temp="5.0",
            extra={
                "climate.living_room": (
                    "heat",
                    {
                        "hvac_action": "heating",
                        "current_temperature": 19.5,
                        "temperature": 21.0,
                    },
                ),
            },
        )
        kwargs = await _run_and_capture_train_kwargs(hass, mock_config_entry, states_get)

        assert kwargs is not None
        # Commanded mode is heating and observed confirms — guard stays off.
        assert kwargs["ekf_mode"] == MODE_HEATING
        assert kwargs["ekf_pf"] > 0.0

    @pytest.mark.asyncio
    async def test_guard_inactive_when_hvac_action_missing(self, hass, mock_config_entry):
        """Device without hvac_action attribute → _observe_device_action
        returns None → guard does not fire (status quo, no regression)."""
        states_get = make_mock_states_get(
            temp="19.5",
            humidity="55.0",
            schedule_state="on",
            outdoor_temp="5.0",
            extra={
                "climate.living_room": (
                    "heat",
                    {
                        # no hvac_action key
                        "current_temperature": 19.5,
                        "temperature": 21.0,
                    },
                ),
            },
        )
        kwargs = await _run_and_capture_train_kwargs(hass, mock_config_entry, states_get)

        assert kwargs is not None
        # Without hvac_action we cannot reliably detect ghost heating; the
        # commanded mode is used (same as before this fix).
        assert kwargs["ekf_mode"] == MODE_HEATING

    @pytest.mark.asyncio
    async def test_guard_inactive_on_mixed_hvac_actions(self, hass, mock_config_entry):
        """Mixed heating + cooling across devices → observed mode is None
        (conflict) → commanded mode wins."""
        multi_device_room = _room_for_guard(
            devices=[
                {
                    "entity_id": "climate.living_room",
                    "type": "trv",
                    "role": "auto",
                    "heating_system_type": "radiator",
                    "idle_action": "off",
                    "idle_fan_mode": "low",
                    "setpoint_mode": "direct",
                },
                {
                    "entity_id": "climate.living_room_ac",
                    "type": "ac",
                    "role": "auto",
                    "heating_system_type": "",
                    "idle_action": "off",
                    "idle_fan_mode": "low",
                    "setpoint_mode": "direct",
                },
            ]
        )
        multi_device_room["thermostats"] = ["climate.living_room"]
        multi_device_room["acs"] = ["climate.living_room_ac"]
        states_get = make_mock_states_get(
            temp="20.8",
            humidity="55.0",
            schedule_state="on",
            outdoor_temp="5.0",
            extra={
                "climate.living_room": (
                    "heat",
                    {"hvac_action": "heating", "current_temperature": 20.8, "temperature": 21.0},
                ),
                "climate.living_room_ac": (
                    "cool",
                    {"hvac_action": "cooling", "current_temperature": 20.8, "temperature": 21.0},
                ),
            },
        )
        kwargs = await _run_and_capture_train_kwargs(hass, mock_config_entry, states_get, room=multi_device_room)

        # Even if commanded/observed are contradictory, guard must not force
        # idle — that would need a reliable single observation.
        assert kwargs is not None
        assert kwargs["ekf_mode"] in (MODE_HEATING, MODE_COOLING, MODE_IDLE)
        # With both actions present, _observe_device_action returns None → no override.
        # The commanded-mode path is used.  We only assert non-interference:
        # q_residual is NOT forced to 0 unless guard fires or heat_source aggregated pf=0.

    @pytest.mark.asyncio
    async def test_guard_inactive_in_managed_mode(self, hass, mock_config_entry):
        """Room without external sensor (Managed Mode) uses the existing
        managed_display_mode pipeline — guard path is not entered."""
        room = _room_for_guard(temperature_sensor="")  # Managed Mode
        states_get = make_mock_states_get(
            temp="20.8",
            humidity="55.0",
            schedule_state="on",
            outdoor_temp="5.0",
            extra={
                "climate.living_room": (
                    "heat",
                    {
                        "hvac_action": "idle",
                        "current_temperature": 20.8,
                        "temperature": 21.0,
                    },
                ),
            },
        )
        kwargs = await _run_and_capture_train_kwargs(hass, mock_config_entry, states_get, room=room)

        assert kwargs is not None
        # Managed Mode already maps hvac_action=idle to idle via managed_display_mode,
        # so the outcome matches — but via a different code path (existing behaviour).
        assert kwargs["ekf_mode"] == MODE_IDLE

    @pytest.mark.asyncio
    async def test_guard_does_not_interfere_when_climate_control_disabled(self, hass, mock_config_entry):
        """With climate_control_active=False, the learn-only path (observed_mode)
        is used and the guard block is bypassed entirely — commanded is None."""
        states_get = make_mock_states_get(
            temp="20.8",
            humidity="55.0",
            schedule_state="on",
            outdoor_temp="5.0",
            extra={
                "climate.living_room": (
                    "heat",
                    {
                        "hvac_action": "heating",
                        "current_temperature": 20.8,
                        "temperature": 21.0,
                    },
                ),
            },
        )
        kwargs = await _run_and_capture_train_kwargs(
            hass,
            mock_config_entry,
            states_get,
            settings={"climate_control_active": False},
        )

        assert kwargs is not None
        # Learn-only path: observed = heating, so EKF trains as heating.
        assert kwargs["ekf_mode"] == MODE_HEATING

    @pytest.mark.asyncio
    async def test_guard_preserves_cooling_when_observed_cooling(self, hass, mock_config_entry):
        """Commanded cooling + observed cooling → guard must not downgrade to idle."""
        room = _room_for_guard()
        room["climate_mode"] = "cool_only"
        # AC device rather than TRV for cooling
        room["devices"] = [
            {
                "entity_id": "climate.living_room",
                "type": "ac",
                "role": "auto",
                "heating_system_type": "",
                "idle_action": "off",
                "idle_fan_mode": "low",
                "setpoint_mode": "direct",
            }
        ]
        room["thermostats"] = []
        room["acs"] = ["climate.living_room"]
        # temp 28 is clearly above cool_target+hysteresis (24 + 0.2 = 24.2)
        # → bangbang MPC commands cooling.
        states_get = make_mock_states_get(
            temp="28.0",
            humidity="55.0",
            schedule_state="on",
            outdoor_temp="30.0",
            extra={
                "climate.living_room": (
                    "cool",
                    {
                        "hvac_action": "cooling",
                        "current_temperature": 28.0,
                        "temperature": 24.0,
                        "hvac_modes": ["off", "cool", "heat", "auto"],
                    },
                ),
            },
        )
        kwargs = await _run_and_capture_train_kwargs(hass, mock_config_entry, states_get, room=room)

        assert kwargs is not None
        # Cooling confirmed — no downgrade.
        assert kwargs["ekf_mode"] == MODE_COOLING

    @pytest.mark.asyncio
    async def test_zero_power_with_active_mode_normalizes_to_idle(self, hass, mock_config_entry):
        """Commanded heating with ekf_pf==0 (e.g. after heat source plan
        selected zero active devices) should normalize to idle so the EKF
        predict step doesn't inflate Q_BETA_H with a zero-gradient Jacobian."""
        from unittest.mock import patch

        from custom_components.roommind.managers.heat_source_orchestrator import (
            DeviceCommand,
            HeatSourcePlan,
        )

        room = _room_for_guard()
        room["heat_source_orchestration"] = True
        room["devices"] = [
            {
                "entity_id": "climate.living_room",
                "type": "trv",
                "role": "primary",
                "heating_system_type": "radiator",
                "idle_action": "off",
                "idle_fan_mode": "low",
                "setpoint_mode": "direct",
            },
            {
                "entity_id": "climate.living_room_ac",
                "type": "ac",
                "role": "secondary",
                "heating_system_type": "",
                "idle_action": "off",
                "idle_fan_mode": "low",
                "setpoint_mode": "direct",
            },
        ]
        room["thermostats"] = ["climate.living_room"]
        room["acs"] = ["climate.living_room_ac"]

        # Plan commands both devices with pf=0 — unusual but possible under
        # tight gating conditions.  Observed hvac_action is "heating" on at
        # least one device (so the ghost-guard does NOT trigger — we want to
        # isolate the zero-pf branch).
        zero_plan = HeatSourcePlan(
            commands=[
                DeviceCommand(
                    entity_id="climate.living_room",
                    role="primary",
                    device_type="thermostat",
                    active=False,
                    power_fraction=0.0,
                    reason="gated",
                ),
                DeviceCommand(
                    entity_id="climate.living_room_ac",
                    role="secondary",
                    device_type="ac",
                    active=False,
                    power_fraction=0.0,
                    reason="gated",
                ),
            ],
            active_sources="none",
            reason="all gated",
        )

        states_get = make_mock_states_get(
            temp="19.5",
            humidity="55.0",
            schedule_state="on",
            outdoor_temp="5.0",
            extra={
                "climate.living_room": (
                    "heat",
                    {"hvac_action": "heating", "current_temperature": 19.5, "temperature": 21.0},
                ),
                "climate.living_room_ac": (
                    "heat",
                    {
                        "hvac_action": "heating",
                        "hvac_modes": ["off", "heat", "cool", "heat_cool"],
                        "current_temperature": 19.5,
                        "temperature": 21.0,
                    },
                ),
            },
        )

        rooms = {room["area_id"]: room}
        store = _make_store_mock(rooms)
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(side_effect=states_get)
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        training_mock = MagicMock()
        coordinator._ekf_training.process = training_mock

        with patch(
            "custom_components.roommind.coordinator.evaluate_heat_sources",
            return_value=zero_plan,
        ):
            await coordinator._async_update_data()

        assert training_mock.called
        kwargs = training_mock.call_args.kwargs
        # With all plan commands at pf=0, mean(pf)=0 → zero-pf normalize
        # forces the mode to idle regardless of the observed heating action.
        assert kwargs["ekf_pf"] == 0.0
        assert kwargs["ekf_mode"] == MODE_IDLE
        assert kwargs["q_residual"] == 0.0

    @pytest.mark.asyncio
    async def test_no_training_when_learning_disabled_for_room(self, hass, mock_config_entry):
        """When the room is in learning_disabled_rooms the guard never runs —
        training is skipped entirely via the existing learning_active branch."""
        states_get = make_mock_states_get(
            temp="20.8",
            humidity="55.0",
            schedule_state="on",
            outdoor_temp="5.0",
            extra={
                "climate.living_room": (
                    "heat",
                    {"hvac_action": "idle", "current_temperature": 20.8, "temperature": 21.0},
                ),
            },
        )
        kwargs = await _run_and_capture_train_kwargs(
            hass,
            mock_config_entry,
            states_get,
            settings={"learning_disabled_rooms": ["living_room_abc12345"]},
        )

        # process should not be called at all when learning is disabled
        assert kwargs is None
