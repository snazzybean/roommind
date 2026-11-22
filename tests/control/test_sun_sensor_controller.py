"""The controller and the analytics forecast with a room's sun sensor (#303)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from custom_components.roommind.control.analytics_simulator import build_forecast_solar_series
from custom_components.roommind.control.mpc_controller import MPCController
from custom_components.roommind.control.thermal_model import RoomModelManager
from custom_components.roommind.managers.solar_sensor_manager import RoomSolar

from .conftest import build_hass, make_room

SUN = RoomSolar(
    q_now=0.6,
    q_effective=0.1,
    measured=True,
    latitude=48.0,
    longitude=11.0,
    now=0.0,
    profile=(0.5,) * 24,
    deviation=1.0,
)


def _controller(room_solar: RoomSolar | None, q_solar: float = 0.6, shading: float = 0.4) -> MPCController:
    return MPCController(
        build_hass(),
        make_room(),
        model_manager=RoomModelManager(),
        outdoor_temp=10.0,
        settings={},
        has_external_sensor=True,
        q_solar=q_solar,
        room_solar=room_solar,
        shading_factor=shading,
        latitude=48.0,
        longitude=11.0,
    )


def test_without_a_sensor_the_weather_model_is_shaded_by_the_covers():
    ctrl = _controller(None)
    assert ctrl._q_solar_shaded == 0.6 * 0.4


def test_the_sensor_input_is_taken_as_the_room_gets_it():
    ctrl = _controller(SUN)
    assert ctrl._q_solar_shaded == 0.1
    with patch.object(ctrl._model_manager, "get_model") as get_model:
        ctrl._predict_idle_drift(20.0, 5.0)
    assert get_model.return_value.predict.call_args.kwargs["q_solar"] == 0.1


@patch("custom_components.roommind.control.solar.build_solar_series", return_value=[0.8] * 12)
def test_the_plan_series_follows_the_sensor_profile(_bss):
    assert _controller(None)._build_solar_series(12) == [0.8] * 12
    assert _controller(SUN)._build_solar_series(12) == pytest.approx([0.4] * 12)


def test_the_analytics_forecast_follows_the_sensor_profile():
    plain = build_forecast_solar_series(48.0, 11.0, [], 24, shading_factor=0.5)
    scaled = build_forecast_solar_series(48.0, 11.0, [], 24, shading_factor=0.5, room_solar=SUN)
    assert plain is not None and scaled is not None
    assert scaled == pytest.approx([q * 0.5 for q in plain])
