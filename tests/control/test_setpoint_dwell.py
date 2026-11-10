"""Proportional setpoint dwell: a recomputed setpoint waits one MPC block (#317)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.const import (
    MODE_HEATING,
    MODE_IDLE,
    PROPORTIONAL_SETPOINT_DWELL_SECONDS,
    TargetTemps,
)
from custom_components.roommind.control import mpc_controller
from custom_components.roommind.control.mpc_controller import MPCController
from custom_components.roommind.control.thermal_model import RoomModelManager

from .conftest import build_hass, make_room

TRV = "climate.living_trv"
_NOW = "custom_components.roommind.control.mpc_controller._now"


def _device(hass, state="heat", setpoint=None):
    """A TRV whose reported state follows the commands it accepts."""
    dev = MagicMock()
    dev.state = state
    dev.attributes = {
        "hvac_modes": ["heat", "off"],
        "temperature": setpoint,
        "min_temp": 5.0,
        "max_temp": 30.5,
        "target_temp_step": 0.5,
    }
    hass.states.get = MagicMock(return_value=dev)

    async def _apply(domain, service, data, **kwargs):
        if "hvac_mode" in data:
            dev.state = data["hvac_mode"]
        if "temperature" in data:
            dev.attributes = {**dev.attributes, "temperature": data["temperature"]}

    hass.services.async_call = AsyncMock(side_effect=_apply)
    return dev


def _ctrl(hass, **settings):
    return MPCController(
        hass,
        make_room(),
        model_manager=RoomModelManager(),
        outdoor_temp=0.0,
        settings=settings,
        has_external_sensor=True,
    )


def _setpoints(hass):
    return [c[0][2]["temperature"] for c in hass.services.async_call.call_args_list if c[0][1] == "set_temperature"]


async def _heat(hass, ctrl, pf, current_temp=19.4, heat=19.5):
    await ctrl.async_apply(
        MODE_HEATING, TargetTemps(heat=heat, cool=None), power_fraction=pf, current_temp=current_temp
    )


@pytest.mark.asyncio
async def test_jittering_power_is_sent_once_per_block():
    """Default comfort weight (no deadband): power flipping every cycle reaches the TRV once per dwell."""
    hass = build_hass()
    _device(hass, state="off")
    ctrl = _ctrl(hass)
    clock = {"t": 1000.0}
    with patch(_NOW, side_effect=lambda: clock["t"]):
        for i in range(20):  # 10 min of 30 s cycles
            await _heat(hass, ctrl, 0.5 if i % 2 else 0.25)
            clock["t"] += 30
    # first send at t=0, the next one once the dwell has passed, and again after the next dwell
    # t=0 sends; t=300 (pf 0.25) matches the device; t=330 sends; the next dwell ends after the loop
    assert len(_setpoints(hass)) == 2


@pytest.mark.asyncio
async def test_change_goes_out_after_the_dwell():
    hass = build_hass()
    _device(hass, state="off")
    ctrl = _ctrl(hass)
    clock = {"t": 1000.0}
    with patch(_NOW, side_effect=lambda: clock["t"]):
        await _heat(hass, ctrl, 0.25)
        clock["t"] += PROPORTIONAL_SETPOINT_DWELL_SECONDS - 1
        await _heat(hass, ctrl, 1.0)
        assert len(_setpoints(hass)) == 1
        clock["t"] += 1
        await _heat(hass, ctrl, 1.0)
    assert _setpoints(hass) == [22.0, 30.0]


@pytest.mark.asyncio
async def test_unchanged_setpoint_is_still_confirmed_not_resent():
    hass = build_hass()
    _device(hass, state="off")
    ctrl = _ctrl(hass)
    clock = {"t": 1000.0}
    with patch(_NOW, side_effect=lambda: clock["t"]):
        await _heat(hass, ctrl, 0.25)
        for _ in range(30):
            clock["t"] += 30
            await _heat(hass, ctrl, 0.25)
    assert _setpoints(hass) == [22.0]


@pytest.mark.asyncio
async def test_target_change_bypasses_the_dwell():
    """Schedule step, override or eco: the new target must not wait for the dwell."""
    hass = build_hass()
    _device(hass, state="off")
    ctrl = _ctrl(hass)
    clock = {"t": 1000.0}
    with patch(_NOW, side_effect=lambda: clock["t"]):
        await _heat(hass, ctrl, 0.25, current_temp=17.0, heat=17.5)
        clock["t"] += 30
        await _heat(hass, ctrl, 1.0, current_temp=17.0, heat=21.0)
    assert len(_setpoints(hass)) == 2


@pytest.mark.asyncio
async def test_first_setpoint_after_idle_is_not_delayed():
    """An idle phase in between (off + min_temp) drops the record, so a restart is sent at once."""
    hass = build_hass()
    _device(hass, state="off")
    ctrl = _ctrl(hass)
    clock = {"t": 1000.0}
    targets = TargetTemps(heat=19.5, cool=None)
    with patch(_NOW, side_effect=lambda: clock["t"]):
        await _heat(hass, ctrl, 0.25)
        clock["t"] += 30
        await ctrl.async_apply(MODE_IDLE, targets, power_fraction=0.0, current_temp=19.6)
        clock["t"] += 30
        hass.services.async_call.reset_mock()
        await _heat(hass, ctrl, 0.5)
    assert _setpoints(hass) == [24.5]


@pytest.mark.asyncio
async def test_idle_low_setpoint_in_between_drops_the_record():
    """idle_action low keeps the TRV in heat at min_temp; the restart must not wait at 5 °C."""
    hass = build_hass()
    _device(hass, state="off")
    room = make_room()
    room["devices"][0]["idle_action"] = "low"
    ctrl = MPCController(hass, room, model_manager=RoomModelManager(), outdoor_temp=0.0, has_external_sensor=True)
    clock = {"t": 1000.0}
    with patch(_NOW, side_effect=lambda: clock["t"]):
        await _heat(hass, ctrl, 0.25)
        clock["t"] += 30
        await ctrl.async_apply(MODE_IDLE, TargetTemps(heat=19.5, cool=None), power_fraction=0.0, current_temp=19.6)
        assert hass.states.get(TRV).attributes["temperature"] == 5.0
        clock["t"] += 30
        await _heat(hass, ctrl, 0.25)
    assert _setpoints(hass) == [22.0, 5.0, 22.0]


@pytest.mark.asyncio
async def test_device_not_in_commanded_mode_is_not_delayed():
    """Switched off by hand (or a reset) within the dwell: the next cycle sends again."""
    hass = build_hass()
    dev = _device(hass, state="off")
    ctrl = _ctrl(hass)
    clock = {"t": 1000.0}
    with patch(_NOW, side_effect=lambda: clock["t"]):
        await _heat(hass, ctrl, 0.25)
        dev.state = "off"
        clock["t"] += 30
        assert (
            ctrl._proportional_dwell_active(
                TRV, "set_temperature", {"entity_id": TRV, "temperature": 25.0, "hvac_mode": "heat"}, dev, 0.0
            )
            is False
        )
        assert (
            ctrl._proportional_dwell_active(TRV, "set_temperature", {"entity_id": TRV, "temperature": 25.0}, dev, 0.0)
            is False
        )
        dev.state = "heat"
        assert (
            ctrl._proportional_dwell_active(TRV, "set_temperature", {"entity_id": TRV, "temperature": 25.0}, dev, 0.0)
            is True
        )


@pytest.mark.asyncio
async def test_non_proportional_sends_are_not_delayed():
    """Direct targets, managed mode and the hold pass no deadband and are never held back."""
    hass = build_hass()
    _device(hass, state="off")
    ctrl = _ctrl(hass)
    clock = {"t": 1000.0}
    with patch(_NOW, side_effect=lambda: clock["t"]):
        await _heat(hass, ctrl, 0.25)
        clock["t"] += 30
        result = await ctrl._call("set_temperature", {"entity_id": TRV, "temperature": 25.0, "hvac_mode": "heat"})
    assert result == mpc_controller._CALL_SENT
    assert _setpoints(hass) == [22.0, 25.0]


@pytest.mark.asyncio
async def test_dwell_skip_leaves_the_hold_reference_alone():
    hass = build_hass()
    _device(hass, state="off")
    ctrl = _ctrl(hass)
    clock = {"t": 1000.0}
    with patch(_NOW, side_effect=lambda: clock["t"]):
        await _heat(hass, ctrl, 0.25)
        assert mpc_controller._active_targets[TRV] == (19.5, None)
        mpc_controller._active_targets[TRV] = (18.0, None)
        clock["t"] += 30
        result = await ctrl._call(
            "set_temperature",
            {"entity_id": TRV, "temperature": 25.0, "hvac_mode": "heat"},
            temp_intent="heat",
            deadband=0.0,
        )
    assert result == mpc_controller._CALL_SKIPPED
    assert mpc_controller._active_targets[TRV] == (18.0, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["unknown", None])
async def test_device_without_usable_state_keeps_the_cache_path(state):
    """#416: no dwell without state feedback; the quantized cache path decides alone."""
    hass = build_hass()
    if state is None:
        hass.states.get = MagicMock(return_value=None)
    else:
        dev = MagicMock()
        dev.state = state
        dev.attributes = {"hvac_modes": ["heat", "off"], "min_temp": 5.0, "max_temp": 30.5}
        hass.states.get = MagicMock(return_value=dev)
    ctrl = _ctrl(hass)
    clock = {"t": 1000.0}
    with patch(_NOW, side_effect=lambda: clock["t"]):
        await _heat(hass, ctrl, 0.25)
        clock["t"] += 30
        await _heat(hass, ctrl, 0.5)
        clock["t"] += 30
        await _heat(hass, ctrl, 0.5)
    assert len(_setpoints(hass)) == 2


@pytest.mark.asyncio
async def test_gentle_regime_combines_deadband_and_dwell():
    hass = build_hass()
    _device(hass, state="off")
    ctrl = _ctrl(hass, comfort_weight=0)
    clock = {"t": 1000.0}
    with patch(_NOW, side_effect=lambda: clock["t"]):
        await _heat(hass, ctrl, 0.25)
        clock["t"] += 30
        await _heat(hass, ctrl, 0.5)
        assert len(_setpoints(hass)) == 1  # above the deadband, but within the dwell
        clock["t"] += PROPORTIONAL_SETPOINT_DWELL_SECONDS
        await _heat(hass, ctrl, 0.5)
    assert len(_setpoints(hass)) == 2


@pytest.mark.asyncio
async def test_backing_off_from_the_boost_waits_for_the_dwell():
    """Kept on purpose: skipping the dwell for the back-off cost commands in the sim without
    reducing overshoot (ir-ac-no-feedback 7.25 -> 8.83/h, homematic duty cycle over 20/h)."""
    hass = build_hass()
    _device(hass, state="off")
    ctrl = _ctrl(hass)
    clock = {"t": 1000.0}
    with patch(_NOW, side_effect=lambda: clock["t"]):
        await _heat(hass, ctrl, 1.0, current_temp=19.0)
        clock["t"] += 30
        await _heat(hass, ctrl, 0.15, current_temp=19.6)
    assert len(_setpoints(hass)) == 1


# --- range devices (target_temp_low/high) --------------------------------------------


def _range_device(hass, state="heat_cool"):
    """A dual-setpoint thermostat: the proportional heating setpoint lands on target_temp_low."""
    dev = MagicMock()
    dev.state = state
    dev.attributes = {
        "hvac_modes": ["heat_cool", "heat", "off"],
        "target_temp_low": 18.0,
        "target_temp_high": 24.0,
        "min_temp": 5.0,
        "max_temp": 30.5,
        "target_temp_step": 0.5,
    }
    hass.states.get = MagicMock(return_value=dev)

    async def _apply(domain, service, data, **kwargs):
        if "hvac_mode" in data:
            dev.state = data["hvac_mode"]
        for key in ("target_temp_low", "target_temp_high"):
            if key in data:
                dev.attributes = {**dev.attributes, key: data[key]}

    hass.services.async_call = AsyncMock(side_effect=_apply)
    return dev


def _range_sends(hass):
    return [
        (c[0][2]["target_temp_low"], c[0][2]["target_temp_high"])
        for c in hass.services.async_call.call_args_list
        if c[0][1] == "set_temperature"
    ]


@pytest.mark.asyncio
async def test_range_device_jittering_power_is_sent_once_per_block():
    """The low setpoint follows the proportional power like a single setpoint (#317 for
    dual-setpoint thermostats): one send per dwell instead of one per 30 s cycle."""
    hass = build_hass()
    _range_device(hass)
    ctrl = _ctrl(hass)
    clock = {"t": 1000.0}
    with patch(_NOW, side_effect=lambda: clock["t"]):
        for i in range(10):  # 5 min of 30 s cycles, all inside one dwell
            await _heat(hass, ctrl, 0.5 if i % 2 else 0.25)
            clock["t"] += 30
    assert len(_range_sends(hass)) == 1


@pytest.mark.asyncio
async def test_range_device_change_goes_out_after_the_dwell():
    hass = build_hass()
    dev = _range_device(hass)
    ctrl = _ctrl(hass)
    clock = {"t": 1000.0}
    with patch(_NOW, side_effect=lambda: clock["t"]):
        await _heat(hass, ctrl, 0.25)
        first = dev.attributes["target_temp_low"]
        clock["t"] += PROPORTIONAL_SETPOINT_DWELL_SECONDS - 1
        await _heat(hass, ctrl, 1.0)
        assert len(_range_sends(hass)) == 1
        clock["t"] += 1
        await _heat(hass, ctrl, 1.0)
    sends = _range_sends(hass)
    assert len(sends) == 2
    assert sends[1][0] > first


@pytest.mark.asyncio
async def test_range_device_target_change_skips_the_dwell():
    hass = build_hass()
    _range_device(hass)
    ctrl = _ctrl(hass)
    clock = {"t": 1000.0}
    with patch(_NOW, side_effect=lambda: clock["t"]):
        await _heat(hass, ctrl, 0.25)
        clock["t"] += 30
        await _heat(hass, ctrl, 0.5, heat=20.5)
    assert len(_range_sends(hass)) == 2


def _reverting_device(hass, revert_to=5.0, times=1):
    """A TRV that takes a setpoint and then falls back to its own one (tado X over Matter
    restores the value it had before the mode change a few seconds later)."""
    dev = _device(hass, state="off", setpoint=revert_to)
    left = {"n": times}

    async def _apply(domain, service, data, **kwargs):
        if "hvac_mode" in data:
            dev.state = data["hvac_mode"]
        if "temperature" in data:
            value = data["temperature"]
            if left["n"] > 0:
                left["n"] -= 1
                value = revert_to
            dev.attributes = {**dev.attributes, "temperature": value}

    hass.services.async_call = AsyncMock(side_effect=_apply)
    return dev


@pytest.mark.asyncio
async def test_a_setpoint_the_device_dropped_is_sent_again_within_the_dwell():
    """The device fell back to 5 °C right after the boost went out: waiting for the dwell
    left the radiator cold for five minutes of a run."""
    hass = build_hass()
    dev = _reverting_device(hass)
    ctrl = _ctrl(hass)
    clock = {"t": 1000.0}
    with patch(_NOW, side_effect=lambda: clock["t"]):
        await _heat(hass, ctrl, 1.0)
        assert dev.attributes["temperature"] == 5.0
        for _ in range(4):  # two minutes of 30 s cycles
            clock["t"] += 30
            await _heat(hass, ctrl, 1.0)
    assert _setpoints(hass) == [30.0, 30.0]
    assert dev.attributes["temperature"] == 30.0


@pytest.mark.asyncio
async def test_a_dropped_setpoint_waits_for_a_slow_state_report():
    """A device that reports a send late must not get the value twice right away."""
    hass = build_hass()
    _reverting_device(hass)
    ctrl = _ctrl(hass)
    clock = {"t": 1000.0}
    with patch(_NOW, side_effect=lambda: clock["t"]):
        await _heat(hass, ctrl, 1.0)
        clock["t"] += 30
        await _heat(hass, ctrl, 1.0)
    assert _setpoints(hass) == [30.0]


@pytest.mark.asyncio
async def test_a_device_that_keeps_refusing_is_reasserted_once_per_dwell():
    """No command every cycle for a device that never takes the value (#317 duty cycles)."""
    hass = build_hass()
    _reverting_device(hass, times=1000)
    ctrl = _ctrl(hass)
    clock = {"t": 1000.0}
    with patch(_NOW, side_effect=lambda: clock["t"]):
        for _ in range(20):  # 10 min of 30 s cycles
            await _heat(hass, ctrl, 1.0)
            clock["t"] += 30
    # switch-on at t=0, one reassert at t=60, the dwell still ends at t=300
    sends = _setpoints(hass)
    assert len(sends) == 3


@pytest.mark.asyncio
async def test_a_device_that_clamps_a_running_setpoint_waits_for_the_dwell():
    """Not switched on by the send: a device that shows another value (own limit, late
    report) keeps the plain dwell, no extra frame (#317)."""
    hass = build_hass()
    dev = _device(hass, state="heat", setpoint=20.0)

    async def _clamp(domain, service, data, **kwargs):
        if "temperature" in data:
            dev.attributes = {**dev.attributes, "temperature": min(data["temperature"], 25.0)}

    hass.services.async_call = AsyncMock(side_effect=_clamp)
    ctrl = _ctrl(hass)
    clock = {"t": 1000.0}
    with patch(_NOW, side_effect=lambda: clock["t"]):
        for _ in range(9):  # 4.5 min
            await _heat(hass, ctrl, 1.0)
            clock["t"] += 30
    assert _setpoints(hass) == [30.0]


@pytest.mark.asyncio
async def test_rounding_on_the_device_is_no_dropped_setpoint():
    hass = build_hass()
    dev = _device(hass, state="off")

    async def _round(domain, service, data, **kwargs):
        if "hvac_mode" in data:
            dev.state = data["hvac_mode"]
        if "temperature" in data:
            dev.attributes = {**dev.attributes, "temperature": round(data["temperature"])}

    hass.services.async_call = AsyncMock(side_effect=_round)
    ctrl = _ctrl(hass)
    clock = {"t": 1000.0}
    with patch(_NOW, side_effect=lambda: clock["t"]):
        await _heat(hass, ctrl, 0.25)
        for _ in range(8):
            clock["t"] += 30
            await _heat(hass, ctrl, 0.25)
    assert len(_setpoints(hass)) == 1


@pytest.mark.asyncio
async def test_a_failed_reassert_is_not_repeated_every_cycle():
    hass = build_hass()
    dev = _reverting_device(hass)
    ok = hass.services.async_call.side_effect
    ctrl = _ctrl(hass)
    clock = {"t": 1000.0}
    with patch(_NOW, side_effect=lambda: clock["t"]):
        await _heat(hass, ctrl, 1.0)
        assert dev.attributes["temperature"] == 5.0

        async def _fail(domain, service, data, **kwargs):
            raise TimeoutError

        hass.services.async_call = AsyncMock(side_effect=_fail)
        for _ in range(8):  # up to 4 min, inside the dwell
            clock["t"] += 30
            await _heat(hass, ctrl, 1.0)
    assert ok is not None  # the device worked for the switch-on itself
    assert hass.services.async_call.await_count == 1


def test_a_range_send_records_only_the_side_roommind_computed():
    data = {"target_temp_low": 30.0, "target_temp_high": 31.5}
    assert mpc_controller._controlled_setpoints(data, "heat") == {"target_temp_low": 30.0}
    assert mpc_controller._controlled_setpoints(data, "cool") == {"target_temp_high": 31.5}
    assert mpc_controller._controlled_setpoints({"temperature": 22.0}, "heat") == {"temperature": 22.0}


@pytest.mark.asyncio
async def test_a_reassert_does_not_move_the_end_of_the_dwell():
    hass = build_hass()
    _reverting_device(hass, times=1000)
    ctrl = _ctrl(hass)
    clock = {"t": 1000.0}
    sent_at = []

    with patch(_NOW, side_effect=lambda: clock["t"]):
        for _ in range(12):  # 6 min
            before = len(_setpoints(hass))
            await _heat(hass, ctrl, 1.0)
            if len(_setpoints(hass)) > before:
                sent_at.append(clock["t"] - 1000.0)
            clock["t"] += 30
    assert sent_at == [0.0, 60.0, 300.0]


@pytest.mark.asyncio
async def test_a_value_shown_at_once_is_not_checked_before_the_report_time():
    hass = build_hass()
    _reverting_device(hass)
    ctrl = _ctrl(hass)
    clock = {"t": 1000.0}
    with patch(_NOW, side_effect=lambda: clock["t"]):
        await _heat(hass, ctrl, 1.0)
        clock["t"] += mpc_controller.PROPORTIONAL_SETPOINT_REPORT_SECONDS - 1
        await _heat(hass, ctrl, 1.0)
        assert len(_setpoints(hass)) == 1
        clock["t"] += 1
        await _heat(hass, ctrl, 1.0)
    assert len(_setpoints(hass)) == 2


@pytest.mark.asyncio
async def test_a_switch_on_by_the_setpoint_call_alone_counts_too():
    """set_hvac_mode failed, the setpoint call with the mode switched the device on."""
    hass = build_hass()
    dev = _reverting_device(hass)
    revert = hass.services.async_call.side_effect

    async def _mode_fails(domain, service, data, **kwargs):
        if service == "set_hvac_mode":
            raise TimeoutError
        await revert(domain, service, data, **kwargs)

    hass.services.async_call = AsyncMock(side_effect=_mode_fails)
    ctrl = _ctrl(hass)
    clock = {"t": 1000.0}
    with patch(_NOW, side_effect=lambda: clock["t"]):
        await _heat(hass, ctrl, 1.0)
        assert dev.state == "heat" and dev.attributes["temperature"] == 5.0
        for _ in range(3):
            clock["t"] += 30
            await _heat(hass, ctrl, 1.0)
    assert _setpoints(hass) == [30.0, 30.0]
