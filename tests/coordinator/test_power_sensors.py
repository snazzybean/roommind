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
    # The reading itself is no model input: only a learned effect is (none yet)
    assert controller_cls.call_args.kwargs["u_device"] == 0.0
    assert process.call_args.kwargs["u_device"] == 0.0


@pytest.mark.asyncio
async def test_room_without_power_sensors(hass, mock_config_entry):
    coordinator = _setup(hass, mock_config_entry, SAMPLE_ROOM, {})
    with patch("custom_components.roommind.coordinator.room_device_ids") as device_ids:
        data = await coordinator._async_update_data()
    device_ids.assert_not_called()
    assert data["rooms"][AREA]["power_kw"] is None
    assert data["rooms"][AREA]["device_heat"] is None
    # nothing is learned or stored for a room without power sensors
    assert coordinator._power_gains.to_dict() == {}


@pytest.mark.asyncio
async def test_power_sensors_without_reading(hass, mock_config_entry):
    room = {**SAMPLE_ROOM, "power_sensors": ["sensor.pc_power"]}
    coordinator = _setup(hass, mock_config_entry, room, {"sensor.pc_power": ("unavailable", {})})
    with patch("custom_components.roommind.coordinator.room_device_ids", return_value=set()):
        data = await coordinator._async_update_data()
    assert data["rooms"][AREA]["power_kw"] is None


@pytest.mark.asyncio
async def test_an_active_sensor_heats_the_plan_and_the_training(hass, mock_config_entry):
    room = {**SAMPLE_ROOM, "power_sensors": ["sensor.pc_power"]}
    extra = {"sensor.pc_power": ("400", {"unit_of_measurement": "W"})}
    coordinator = _setup(hass, mock_config_entry, room, extra)
    # Stored: the PC is known to warm the room by 1.5 degC/h per kW above its usual 100 W
    hass.data["roommind"]["store"].get_power_gains.return_value = {
        AREA: {
            "sensors": ["sensor.pc_power"],
            "gain": [1.5],
            "P": [[0.01]],
            "state": {"sensor.pc_power": {"baseline_kw": 0.1, "active": True, "n": 50}},
        }
    }
    learner = coordinator._power_gains
    with (
        patch("custom_components.roommind.coordinator.room_device_ids", return_value=set()),
        patch("custom_components.roommind.coordinator.MPCController") as controller_cls,
        patch.object(coordinator._ekf_training, "process") as process,
        patch(
            "custom_components.roommind.managers.power_gain_learner.PowerGainLearner.observe", autospec=True
        ) as observe,
    ):
        controller = controller_cls.return_value
        controller.async_evaluate = AsyncMock(return_value=("idle", 0.0))
        controller.last_plan = None
        controller.direct_target.return_value = None
        controller.predicted_peak_temp = None
        data = await coordinator._async_update_data()
    # 400 W against a usual 100 W: 0.3 kW x 1.5 degC/h per kW
    assert controller_cls.call_args.kwargs["u_device"] == pytest.approx(0.45, rel=0.01)
    assert process.call_args.kwargs["u_device"] == pytest.approx(0.45, rel=0.01)
    assert data["rooms"][AREA]["device_heat"] == pytest.approx(0.45, rel=0.01)
    assert observe.call_args.kwargs["mode"] is not None
    assert learner is not coordinator._power_gains  # replaced by the stored state


@pytest.mark.asyncio
async def test_power_gains_are_loaded_saved_and_reset(hass, mock_config_entry):
    room = {**SAMPLE_ROOM, "power_sensors": ["sensor.pc_power"]}
    coordinator = _setup(hass, mock_config_entry, room, {"sensor.pc_power": ("400", {"unit_of_measurement": "W"})})
    store = hass.data["roommind"]["store"]
    saved = {AREA: {"sensors": ["sensor.pc_power"], "gain": [1.1], "P": [[0.2]], "state": {"sensor.pc_power": {}}}}
    store.get_power_gains.return_value = saved
    with patch("custom_components.roommind.coordinator.room_device_ids", return_value=set()):
        await coordinator._async_update_data()
    assert coordinator._power_gains.info(AREA)[0]["gain"] == 1.1
    coordinator._thermal_save_count = 10**6
    with patch("custom_components.roommind.coordinator.room_device_ids", return_value=set()):
        await coordinator._async_update_data()
    assert AREA in store.set_power_gains.call_args.args[0]
    coordinator.reset_thermal_room(AREA)
    assert coordinator._power_gains.info(AREA) == []
    coordinator._power_gains.begin_cycle(AREA, ["sensor.pc_power"], {}, 0.5)
    coordinator.reset_thermal_all()
    assert coordinator._power_gains.to_dict() == {}
