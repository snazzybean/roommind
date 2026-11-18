"""A device that shows "off" but keeps reporting the run gets RoomMind's off again (lost command)."""

from __future__ import annotations

import logging
from datetime import timedelta
from unittest.mock import ANY, MagicMock, patch

import pytest
from homeassistant.util import dt as dt_util

from custom_components.roommind.const import OFF_CONFIRM_SECONDS, OFF_RESEND_INTERVAL_SECONDS, OFF_RESEND_MAX
from custom_components.roommind.control.mpc_controller import (
    _off_sent,
    _remember_command,
    _reports_stop,
    async_turn_off_climate,
)

from .conftest import build_hass

EID = "climate.kitchen_trv"


class Device:
    """A TRV whose HA state the test sets; the hass mock reads it."""

    def __init__(self, hass, *, modes=("heat", "off")):
        self.state = MagicMock()
        self.state.last_changed = dt_util.utcnow()
        self.modes = list(modes)
        self.set("heat", "heating", 34.5)
        hass.states.get = MagicMock(side_effect=lambda eid: self.state if eid == EID else None)

    def set(self, mode, action, temperature, *, changed=None):
        if mode != self.state.state:
            self.state.last_changed = changed or dt_util.utcnow()
        self.state.state = mode
        self.state.attributes = {
            "hvac_modes": self.modes,
            "min_temp": 5.0,
            "max_temp": 35.0,
            "temperature": temperature,
            "hvac_action": action,
        }


@pytest.fixture
def clock():
    t = {"now": 1000.0}
    with patch("custom_components.roommind.control.mpc_controller._now", side_effect=lambda: t["now"]):
        yield t


def _sends(hass):
    return [(c[0][1], c[0][2]) for c in hass.services.async_call.call_args_list]


async def _switch_off(hass, dev, clock, *, action_after="heating"):
    """RoomMind switches the heating device off; the integration shows "off" at once."""
    await async_turn_off_climate(hass, EID)
    dev.set("off", action_after, 5.0)
    clock["now"] += 30


async def _learn_reports_stop(hass, dev, clock):
    """A normal off: the device drops its run within the next report."""
    await _switch_off(hass, dev, clock)
    dev.set("off", "idle", 5.0)
    await async_turn_off_climate(hass, EID)
    assert EID in _reports_stop
    assert EID not in _off_sent
    dev.set("heat", "heating", 34.5)
    _remember_command(EID, "set_hvac_mode", {"hvac_mode": "heat"})
    hass.services.async_call.reset_mock()


@pytest.mark.asyncio
async def test_lost_off_is_sent_again_after_the_confirm_time(clock, caplog):
    hass = build_hass()
    dev = Device(hass)
    await _learn_reports_stop(hass, dev, clock)

    await _switch_off(hass, dev, clock)
    hass.services.async_call.reset_mock()
    # The device reverts to its old setpoint and keeps heating behind the "off"
    dev.set("off", "heating", 34.5)
    await async_turn_off_climate(hass, EID)
    assert _sends(hass) == []

    clock["now"] += OFF_CONFIRM_SECONDS
    with caplog.at_level(logging.WARNING):
        await async_turn_off_climate(hass, EID)
    assert _sends(hass) == [
        ("set_temperature", {"entity_id": EID, "temperature": 5.0}),
        ("set_hvac_mode", {"entity_id": EID, "hvac_mode": "off"}),
    ]
    assert "sending the off again (1/3)" in caplog.text


@pytest.mark.asyncio
async def test_device_never_seen_dropping_its_run_gets_nothing_extra(clock):
    """An integration whose hvac_action ignores the mode (stays "heating" in off) is left alone."""
    hass = build_hass()
    dev = Device(hass)
    await _switch_off(hass, dev, clock)
    hass.services.async_call.reset_mock()
    for _ in range(10):
        clock["now"] += OFF_RESEND_INTERVAL_SECONDS
        await async_turn_off_climate(hass, EID)
    assert _sends(hass) == []


@pytest.mark.asyncio
async def test_an_off_from_idle_does_not_count_as_dropping_a_run(clock):
    hass = build_hass()
    dev = Device(hass)
    dev.set("heat", "idle", 21.0)
    await _switch_off(hass, dev, clock, action_after="idle")
    await async_turn_off_climate(hass, EID)
    assert EID not in _reports_stop


@pytest.mark.asyncio
async def test_resends_are_spaced_and_end_with_a_warning(clock, caplog):
    hass = build_hass()
    dev = Device(hass)
    await _learn_reports_stop(hass, dev, clock)
    await _switch_off(hass, dev, clock)
    hass.services.async_call.reset_mock()

    clock["now"] += OFF_CONFIRM_SECONDS
    await async_turn_off_climate(hass, EID)
    clock["now"] += OFF_RESEND_INTERVAL_SECONDS - 60
    await async_turn_off_climate(hass, EID)
    offs = [s for s in _sends(hass) if s[0] == "set_hvac_mode"]
    assert len(offs) == 1

    for _ in range(OFF_RESEND_MAX + 3):
        clock["now"] += OFF_RESEND_INTERVAL_SECONDS
        with caplog.at_level(logging.WARNING):
            await async_turn_off_climate(hass, EID)
    offs = [s for s in _sends(hass) if s[0] == "set_hvac_mode"]
    assert len(offs) == OFF_RESEND_MAX
    assert caplog.text.count("check the device") == 1


@pytest.mark.asyncio
async def test_device_that_stops_after_a_resend_ends_the_watch(clock, caplog):
    hass = build_hass()
    dev = Device(hass)
    await _learn_reports_stop(hass, dev, clock)
    await _switch_off(hass, dev, clock)
    clock["now"] += OFF_CONFIRM_SECONDS
    await async_turn_off_climate(hass, EID)
    dev.set("off", "idle", 5.0)
    hass.services.async_call.reset_mock()
    with caplog.at_level(logging.INFO):
        await async_turn_off_climate(hass, EID)
    assert EID not in _off_sent
    assert "stopped after the off was sent 1 more time(s)" in caplog.text
    clock["now"] += OFF_RESEND_INTERVAL_SECONDS
    await async_turn_off_climate(hass, EID)
    assert _sends(hass) == []


@pytest.mark.asyncio
async def test_cooling_unit_gets_only_the_off(clock):
    """min_temp would be the hardest cooling demand for a unit that is still cooling."""
    hass = build_hass()
    dev = Device(hass, modes=("cool", "off"))
    dev.set("cool", "cooling", 18.0)
    await async_turn_off_climate(hass, EID)
    dev.set("off", "off", 18.0)
    clock["now"] += 30
    await async_turn_off_climate(hass, EID)
    assert EID in _reports_stop

    dev.set("cool", "cooling", 18.0)
    await async_turn_off_climate(hass, EID)
    dev.set("off", "cooling", 18.0)
    hass.services.async_call.reset_mock()
    clock["now"] += OFF_CONFIRM_SECONDS
    await async_turn_off_climate(hass, EID)
    assert _sends(hass) == [("set_hvac_mode", {"entity_id": EID, "hvac_mode": "off"})]


@pytest.mark.asyncio
async def test_off_switched_by_someone_else_later_is_not_resent(clock):
    hass = build_hass()
    dev = Device(hass)
    await _learn_reports_stop(hass, dev, clock)
    await _switch_off(hass, dev, clock)
    # Someone switches it on and off again by hand ten minutes later
    dev.set("heat", "heating", 30.0)
    dev.set("off", "heating", 30.0, changed=dt_util.utcnow() + timedelta(minutes=10))
    hass.services.async_call.reset_mock()
    clock["now"] += OFF_CONFIRM_SECONDS
    await async_turn_off_climate(hass, EID)
    assert _sends(hass) == []
    assert EID not in _off_sent


@pytest.mark.asyncio
async def test_switching_the_device_on_ends_the_watch():
    hass = build_hass()
    dev = Device(hass)
    await async_turn_off_climate(hass, EID)
    assert EID in _off_sent
    _remember_command(EID, "set_temperature", {"temperature": 30.0, "hvac_mode": "heat"})
    assert EID not in _off_sent
    assert dev.state.state == "heat"


@pytest.mark.asyncio
async def test_failed_off_is_not_watched():
    hass = build_hass()
    Device(hass)
    hass.services.async_call.side_effect = [None, RuntimeError("zigbee")]
    await async_turn_off_climate(hass, EID)
    assert EID not in _off_sent
    hass.services.async_call.assert_any_call(
        "climate", "set_hvac_mode", {"entity_id": EID, "hvac_mode": "off"}, blocking=True, context=ANY
    )


@pytest.mark.asyncio
async def test_a_stop_long_after_the_off_proves_nothing(clock):
    """An action computed from temperatures drops hours later once the room cooled past the setpoint."""
    hass = build_hass()
    dev = Device(hass)
    await _switch_off(hass, dev, clock)
    await async_turn_off_climate(hass, EID)
    clock["now"] += OFF_CONFIRM_SECONDS
    await async_turn_off_climate(hass, EID)
    assert EID not in _off_sent
    clock["now"] += 3600
    dev.set("off", "idle", 5.0)
    await async_turn_off_climate(hass, EID)
    assert EID not in _reports_stop


@pytest.mark.asyncio
async def test_giving_up_drops_the_device_from_the_resends(clock):
    hass = build_hass()
    dev = Device(hass)
    await _learn_reports_stop(hass, dev, clock)
    await _switch_off(hass, dev, clock)
    clock["now"] += OFF_CONFIRM_SECONDS
    for _ in range(OFF_RESEND_MAX + 1):
        await async_turn_off_climate(hass, EID)
        clock["now"] += OFF_RESEND_INTERVAL_SECONDS
    assert EID not in _reports_stop

    # The next off of the device is left to the device
    dev.set("heat", "heating", 34.5)
    _remember_command(EID, "set_hvac_mode", {"hvac_mode": "heat"})
    await _switch_off(hass, dev, clock)
    hass.services.async_call.reset_mock()
    clock["now"] += OFF_RESEND_INTERVAL_SECONDS
    await async_turn_off_climate(hass, EID)
    assert _sends(hass) == []


@pytest.mark.asyncio
async def test_unit_that_can_cool_gets_no_min_temp_while_heating(clock):
    """Behind "off" it may still be in heat_cool: min_temp would turn the heating into hard cooling (#388)."""
    hass = build_hass()
    dev = Device(hass, modes=("heat_cool", "heat", "cool", "off"))
    dev.set("heat", "heating", 26.0)
    await _learn_reports_stop(hass, dev, clock)
    dev.set("heat", "heating", 26.0)
    await _switch_off(hass, dev, clock)
    dev.set("off", "heating", 26.0)
    hass.services.async_call.reset_mock()
    clock["now"] += OFF_CONFIRM_SECONDS
    await async_turn_off_climate(hass, EID)
    assert _sends(hass) == [("set_hvac_mode", {"entity_id": EID, "hvac_mode": "off"})]
