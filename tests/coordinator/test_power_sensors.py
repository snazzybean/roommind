"""Power sensors of a room: read each cycle, shown live, fed to the MPC and the EKF."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get

AREA = "living_room_abc12345"


def _setup(hass, mock_config_entry, room: dict, extra: dict):
    hass.data = {"roommind": {"store": _make_store_mock({AREA: room})}}
    hass.states.get = MagicMock(side_effect=make_mock_states_get(extra=extra))
    hass.services.async_call = AsyncMock()
    return _create_coordinator(hass, mock_config_entry)


@pytest.mark.asyncio
async def test_power_sensors_reach_live_state_controller_and_training(hass, mock_config_entry):
    room = {**SAMPLE_ROOM, "power_sensors": ["sensor.pc_power", "sensor.monitor_power"]}
    extra = {
        "sensor.pc_power": ("250", {"unit_of_measurement": "W"}),
        "sensor.monitor_power": ("0.05", {"unit_of_measurement": "kW"}),
    }
    coordinator = _setup(hass, mock_config_entry, room, extra)
    with (
        patch("custom_components.roommind.coordinator.room_device_ids", return_value=set()) as device_ids,
        patch("custom_components.roommind.coordinator.MPCController") as controller_cls,
        patch.object(coordinator._ekf_training, "process") as process,
    ):
        controller = controller_cls.return_value
        controller.async_evaluate = AsyncMock(return_value=("idle", 0.0))
        controller.last_plan = None
        controller.direct_target.return_value = None
        controller.predicted_peak_temp = None
        data = await coordinator._async_update_data()
    device_ids.assert_called_once_with(hass, room["devices"])
    assert data["rooms"][AREA]["power_kw"] == pytest.approx(0.3)
    assert controller_cls.call_args.kwargs["q_power"] == pytest.approx(0.3)
    assert process.call_args.kwargs["q_power"] == pytest.approx(0.3)


@pytest.mark.asyncio
async def test_room_without_power_sensors(hass, mock_config_entry):
    coordinator = _setup(hass, mock_config_entry, SAMPLE_ROOM, {})
    with patch("custom_components.roommind.coordinator.room_device_ids") as device_ids:
        data = await coordinator._async_update_data()
    device_ids.assert_not_called()
    assert data["rooms"][AREA]["power_kw"] is None


@pytest.mark.asyncio
async def test_power_sensors_without_reading(hass, mock_config_entry):
    room = {**SAMPLE_ROOM, "power_sensors": ["sensor.pc_power"]}
    coordinator = _setup(hass, mock_config_entry, room, {"sensor.pc_power": ("unavailable", {})})
    with patch("custom_components.roommind.coordinator.room_device_ids", return_value=set()):
        data = await coordinator._async_update_data()
    assert data["rooms"][AREA]["power_kw"] is None
