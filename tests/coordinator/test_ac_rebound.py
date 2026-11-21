"""Coordinator wiring of the AC rebound charge (tracker, EKF training, controller)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind import coordinator as coordinator_module
from custom_components.roommind.const import MODE_COOLING

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get


def _ac_room() -> dict:
    return {
        **SAMPLE_ROOM,
        "climate_mode": "cool_only",
        "devices": [
            {
                "entity_id": "climate.living_room",
                "type": "ac",
                "role": "auto",
                "heating_system_type": "",
                "idle_action": "off",
                "idle_fan_mode": "low",
                "setpoint_mode": "direct",
            }
        ],
        "thermostats": [],
        "acs": ["climate.living_room"],
        "heating_system_type": "",
        "comfort_cool": 24.0,
        "eco_cool": 27.0,
    }


def _states(action: str):
    return make_mock_states_get(
        temp="28.0",
        humidity="55.0",
        schedule_state="on",
        outdoor_temp="30.0",
        extra={
            "climate.living_room": (
                "cool",
                {
                    "hvac_action": action,
                    "current_temperature": 28.0,
                    "temperature": 24.0,
                    "hvac_modes": ["off", "cool", "heat", "auto"],
                },
            ),
        },
    )


@pytest.mark.asyncio
async def test_cooling_charges_the_tracker_and_reaches_training_and_controller(hass, mock_config_entry):
    room = _ac_room()
    store = _make_store_mock({room["area_id"]: room})
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(side_effect=_states("cooling"))
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    training = MagicMock()
    coordinator._ekf_training.process = training

    await coordinator._async_update_data()
    area = room["area_id"]
    assert training.call_args.kwargs["ekf_mode"] == MODE_COOLING
    # the unit was already cooling at startup: the adopted run starts fully charged
    assert training.call_args.kwargs["q_rebound"] == pytest.approx(1.0)
    assert coordinator._rebound_tracker._cooling[area] is True

    coordinator._rebound_tracker._at[area] -= 600
    seen: dict = {}
    real_controller = coordinator_module.MPCController

    def _capture(*args, **kwargs):
        seen.update(kwargs)
        return real_controller(*args, **kwargs)

    with patch("custom_components.roommind.coordinator.MPCController", side_effect=_capture):
        await coordinator._async_update_data()
    assert seen["q_rebound"] > 0.5
    assert training.call_args.kwargs["q_rebound"] == pytest.approx(seen["q_rebound"])


@pytest.mark.asyncio
async def test_ghost_cooling_does_not_charge(hass, mock_config_entry):
    """Commanded cooling but the unit reports idle: trained as idle, so no charge either."""
    room = _ac_room()
    store = _make_store_mock({room["area_id"]: room})
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(side_effect=_states("idle"))
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    coordinator._ekf_training.process = MagicMock()

    await coordinator._async_update_data()
    assert room["area_id"] not in coordinator._rebound_tracker._at


@pytest.mark.asyncio
@pytest.mark.parametrize(("hold", "trained"), [(True, False), (False, True)])
async def test_compressor_hold_with_running_unit_skips_training_and_keeps_charging(
    hass, mock_config_entry, hold, trained
):
    """Min-run hold (#436): room IDLE, unit still cooling. No idle label, charge follows the unit."""
    room = _ac_room()
    store = _make_store_mock({room["area_id"]: room})
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(side_effect=_states("cooling"))
    coordinator = _create_coordinator(hass, mock_config_entry)
    training = MagicMock()
    coordinator._ekf_training.process = training
    coordinator._ekf_training.clear = MagicMock()
    coordinator.outdoor_temp_effective = 30.0

    await coordinator._observe_and_train(
        area_id=room["area_id"],
        room=room,
        settings={},
        current_temp_raw=24.0,
        mode="idle",
        power_fraction=0.0,
        window_open=False,
        raw_open=False,
        external_heat=False,
        q_residual=0.0,
        shading_factor=None,
        q_occupancy=0.0,
        has_external_sensor=True,
        heat_source_plan=None,
        climate_active=True,
        compressor_held={"climate.living_room"} if hold else None,
    )
    assert training.called is trained
    assert (coordinator._rebound_tracker._cooling.get(room["area_id"]) is True) is hold
    if hold:
        # a hold resumes without a resync, as before #478 (keeps #436's sim calibration)
        assert coordinator._ekf_training.clear.call_args.kwargs["resync"] is False
