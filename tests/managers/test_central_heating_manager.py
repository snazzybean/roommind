"""Central heating: switched from the number of rooms demanding heat."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.managers import central_heating_manager as chm
from custom_components.roommind.managers.central_heating_manager import (
    CentralHeatingConfig,
    CentralHeatingManager,
    room_counts_for_central_heating,
)

TRV = {"entity_id": "climate.trv", "type": "trv"}
AC = {"entity_id": "climate.ac", "type": "ac"}


def _settings(**overrides):
    config = {"enabled": True, "entity_id": "switch.boiler", "min_rooms": 2, "start_delay_s": 60, "stop_delay_s": 300}
    config.update(overrides)
    return {"central_heating": config}


ROOMS = {
    "bad": {"devices": [TRV]},
    "buero": {"devices": [TRV]},
    "kueche": {"devices": [TRV]},
    "wohnzimmer_ac": {"devices": [AC]},
}


def _states(*heating: str) -> dict:
    return {area: {"commanded_mode": "heating" if area in heating else "idle"} for area in ROOMS}


class Env:
    def __init__(self, monkeypatch, entity_state="off", attributes=None):
        self.now = [1000.0]
        monkeypatch.setattr(chm.time, "monotonic", lambda: self.now[0])
        self.hass = MagicMock()
        self.target = MagicMock()
        self.target.state = entity_state
        self.target.attributes = attributes or {}
        self.hass.states.get.side_effect = lambda eid: (
            self.target if eid in ("switch.boiler", "climate.boiler") else None
        )
        self.hass.services.async_call = AsyncMock(side_effect=self._apply)
        self.timers: list = []

        def call_later(_hass, delay, action):
            cancel = MagicMock()
            self.timers.append((delay, action, cancel))
            return cancel

        patch.object(chm, "async_call_later", side_effect=call_later).start()
        self.manager = CentralHeatingManager(self.hass)

    async def _apply(self, domain, service, data, **_kw):
        if service in ("turn_on", "turn_off"):
            self.target.state = "on" if service == "turn_on" else "off"
        elif service == "set_hvac_mode":
            self.target.state = data["hvac_mode"]
        elif service == "set_temperature":
            self.target.attributes = {**self.target.attributes, "temperature": data["temperature"]}
            if "hvac_mode" in data:
                self.target.state = data["hvac_mode"]

    async def cycle(self, *heating: str, settings=None):
        await self.manager.async_update(_settings() if settings is None else settings, ROOMS, _states(*heating))

    def calls(self):
        return [
            (c.args[0], c.args[1], {k: v for k, v in c.args[2].items() if k != "entity_id"})
            for c in self.hass.services.async_call.call_args_list
        ]


@pytest.fixture
def env(monkeypatch):
    environment = Env(monkeypatch)
    yield environment
    patch.stopall()


# ─── Configuration ─────────────────────────────────────────────────


def test_config_from_settings():
    assert CentralHeatingConfig.from_settings({}) is None
    assert CentralHeatingConfig.from_settings({"central_heating": {"enabled": False, "entity_id": "switch.x"}}) is None
    assert CentralHeatingConfig.from_settings({"central_heating": {"enabled": True, "entity_id": "light.x"}}) is None
    config = CentralHeatingConfig.from_settings(_settings(min_rooms=0))
    assert config is not None and config.min_rooms == 1 and config.domain == "switch"


def test_room_participation():
    assert room_counts_for_central_heating({"devices": [TRV]})
    assert not room_counts_for_central_heating({"devices": [AC]})
    assert room_counts_for_central_heating({"devices": [AC], "central_heating": True})
    assert not room_counts_for_central_heating({"devices": [TRV], "central_heating": False})
    assert not room_counts_for_central_heating({"devices": [TRV], "is_outdoor": True})


# ─── Switching ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_disabled_does_nothing(env):
    await env.cycle("bad", "buero", settings={})
    assert env.calls() == []
    assert env.manager.state() == {"enabled": False}


@pytest.mark.asyncio
async def test_starts_after_the_delay_once_enough_rooms_demand(env):
    await env.cycle("bad")
    assert env.manager.state()["pending"] is None  # one room is not enough
    await env.cycle("bad", "buero")
    state = env.manager.state()
    assert state["pending"] == "start" and state["pending_seconds"] == 60
    assert env.calls() == []
    # the timer ends the delay to the second
    delay, tick, _ = env.timers[-1]
    assert delay == pytest.approx(60.1)
    env.now[0] += 60.1
    await tick(None)
    assert env.calls() == [("switch", "turn_on", {})]
    assert env.manager.state()["on"] is True


@pytest.mark.asyncio
async def test_demand_dropping_inside_the_start_delay_cancels_it(env):
    await env.cycle("bad", "buero")
    env.now[0] += 30
    await env.cycle("bad")
    env.now[0] += 60
    await env.cycle("bad")
    assert env.calls() == []


@pytest.mark.asyncio
async def test_runs_on_for_the_stop_delay(env):
    await env.cycle("bad", "buero", settings=_settings(start_delay_s=0))
    assert env.calls() == [("switch", "turn_on", {})]
    env.now[0] += 30
    await env.cycle("bad", settings=_settings(start_delay_s=0))
    assert env.manager.state()["pending"] == "stop"
    env.now[0] += 200
    await env.cycle("bad", "kueche", settings=_settings(start_delay_s=0))  # demand back: run-on cancelled
    assert env.manager.state()["pending"] is None
    await env.cycle(settings=_settings(start_delay_s=0))
    env.now[0] += 299
    await env.cycle(settings=_settings(start_delay_s=0))
    assert env.target.state == "on"
    env.now[0] += 2
    await env.cycle(settings=_settings(start_delay_s=0))
    assert env.calls()[-1] == ("switch", "turn_off", {})
    assert env.manager.state()["on"] is False


@pytest.mark.asyncio
async def test_only_rooms_that_count_are_counted(env):
    rooms = {**ROOMS, "bad": {"devices": [TRV], "central_heating": False}}
    await env.manager.async_update(_settings(start_delay_s=0), rooms, _states("bad", "buero", "wohnzimmer_ac"))
    assert env.manager.demanding_rooms == ["buero"]
    assert env.calls() == []


@pytest.mark.asyncio
async def test_rooms_with_control_off_and_global_off_do_not_count(env):
    rooms = {**ROOMS, "bad": {"devices": [TRV], "climate_control_enabled": False}}
    await env.manager.async_update(_settings(start_delay_s=0), rooms, _states("bad", "buero"))
    assert env.manager.demanding_rooms == ["buero"]
    await env.manager.async_update(
        {**_settings(start_delay_s=0), "climate_control_active": False}, ROOMS, _states("bad", "buero")
    )
    assert env.manager.demanding_rooms == []


@pytest.mark.asyncio
async def test_takes_over_the_target_state_after_a_restart(monkeypatch):
    env = Env(monkeypatch, entity_state="on")
    try:
        await env.cycle("bad", "buero")
        assert env.calls() == []  # already on, demand present: nothing to send
        assert env.manager.state()["on"] is True
    finally:
        patch.stopall()


@pytest.mark.asyncio
async def test_re_sends_when_switched_elsewhere(env):
    await env.cycle("bad", "buero", settings=_settings(start_delay_s=0))
    env.target.state = "off"  # someone switched the boiler off
    await env.cycle("bad", "buero", settings=_settings(start_delay_s=0))
    assert env.calls() == [("switch", "turn_on", {}), ("switch", "turn_on", {})]


@pytest.mark.asyncio
async def test_unavailable_target_is_left_alone(env):
    env.target.state = "unavailable"
    await env.cycle("bad", "buero", settings=_settings(start_delay_s=0))
    assert env.calls() == []


@pytest.mark.asyncio
async def test_failed_command_is_retried(env):
    env.hass.services.async_call.side_effect = Exception("down")
    await env.cycle("bad", "buero", settings=_settings(start_delay_s=0))
    assert env.manager.state()["on"] is False
    env.hass.services.async_call.side_effect = env._apply
    await env.cycle("bad", "buero", settings=_settings(start_delay_s=0))
    assert env.manager.state()["on"] is True


@pytest.mark.asyncio
async def test_new_target_is_read_again_and_timer_stopped(env):
    await env.cycle("bad", "buero")
    _, _, cancel = env.timers[-1]
    await env.cycle("bad", "buero", settings=_settings(entity_id="climate.boiler", on_temperature=60))
    cancel.assert_called()
    env.manager.async_stop()


# ─── Thermostat target ─────────────────────────────────────────────


def _climate(**overrides):
    return _settings(entity_id="climate.boiler", start_delay_s=0, stop_delay_s=0, **overrides)


@pytest.mark.asyncio
async def test_thermostat_on_and_off_temperature(monkeypatch):
    env = Env(monkeypatch, entity_state="heat", attributes={"temperature": 10.0})
    try:
        settings = _climate(on_temperature=60.0, off_temperature=10.0)
        await env.cycle("bad", "buero", settings=settings)
        assert env.calls() == [("climate", "set_temperature", {"temperature": 60.0, "hvac_mode": "heat"})]
        await env.cycle(settings=settings)
        assert env.calls()[-1] == ("climate", "set_temperature", {"temperature": 10.0})
        assert env.target.state == "heat"  # stays in heat mode
        assert env.manager.state()["on"] is False
    finally:
        patch.stopall()


@pytest.mark.asyncio
async def test_thermostat_off_mode_switches_it_off(monkeypatch):
    env = Env(monkeypatch, entity_state="off", attributes={"temperature": 10.0})
    try:
        settings = _climate(on_temperature=60.0, off_temperature=10.0, climate_off_mode="off")
        await env.cycle("bad", "buero", settings=settings)
        await env.cycle(settings=settings)
        assert env.calls()[-2:] == [
            ("climate", "set_temperature", {"temperature": 10.0}),
            ("climate", "set_hvac_mode", {"hvac_mode": "off"}),
        ]
    finally:
        patch.stopall()


@pytest.mark.asyncio
async def test_thermostat_without_temperatures_only_switches_mode(monkeypatch):
    env = Env(monkeypatch, entity_state="off")
    try:
        await env.cycle("bad", "buero", settings=_climate())
        await env.cycle(settings=_climate())
        assert env.calls() == [
            ("climate", "set_hvac_mode", {"hvac_mode": "heat"}),
            ("climate", "set_hvac_mode", {"hvac_mode": "off"}),
        ]
    finally:
        patch.stopall()
