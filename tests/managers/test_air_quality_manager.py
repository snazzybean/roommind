"""Tests for air_quality_manager.py: CO2/VOC hysteresis and the ventilation RoomMind runs (#267)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import CoreState

from custom_components.roommind.const import MAX_SENSOR_STALENESS
from custom_components.roommind.managers.air_quality_manager import (
    VENTILATION_MIN_RUN_S,
    VENTILATION_REPORT_GRACE_S,
    AirQualityTracker,
    VentilationController,
    next_air_bad,
)

FAN = "fan.bedroom"


@pytest.mark.parametrize(
    ("previous", "value", "expected"),
    [
        (False, 999, False),
        (False, 1000, True),
        (True, 900, True),  # between release and threshold: stays as it was
        (False, 900, False),
        (True, 801, True),
        (True, 799, False),
        (True, None, True),  # no reading: no new information
        (False, None, False),
    ],
)
def test_co2_hysteresis(previous, value, expected):
    assert next_air_bad(previous, value, 1000) is expected


def test_no_threshold_never_judges():
    assert next_air_bad(True, 5000, None) is False
    assert next_air_bad(True, 5000, 0) is False


def test_tracker_keeps_bad_through_a_short_dropout_and_drops_it_when_stale():
    t = AirQualityTracker()
    assert t.evaluate("bed", "co2", 1200, 1000, 0) is True
    assert t.evaluate("bed", "co2", None, 1000, MAX_SENSOR_STALENESS) is True
    assert t.evaluate("bed", "co2", None, 1000, MAX_SENSOR_STALENESS + 1) is False
    # Back with a value between release and threshold: good, the bad state was dropped
    assert t.evaluate("bed", "co2", 900, 1000, MAX_SENSOR_STALENESS + 2) is False


def test_tracker_kinds_and_rooms_are_separate():
    t = AirQualityTracker()
    assert t.evaluate("bed", "co2", 1200, 1000, 0) is True
    assert t.evaluate("bed", "voc", 900, 1000, 0) is False
    assert t.evaluate("office", "co2", 900, 1000, 0) is False
    t.remove_room("bed")
    assert t.evaluate("bed", "co2", 900, 1000, 1) is False


def test_tracker_without_any_reading_is_good():
    assert AirQualityTracker().evaluate("bed", "co2", None, 1000, 0) is False


class _Hass:
    """Entity states plus a service mock that applies on/off to them."""

    def __init__(self, states: dict[str, str]) -> None:
        self.state_map = dict(states)
        self.states = MagicMock()
        self.states.get = lambda eid: SimpleNamespace(state=self.state_map[eid]) if eid in self.state_map else None
        self.calls: list[tuple[str, str, str]] = []
        self.fail = False
        self.state = CoreState.running

        async def _call(domain, service, data, **_kw):
            if self.fail:
                raise RuntimeError("boom")
            eid = data["entity_id"]
            self.calls.append((domain, service, eid))
            self.state_map[eid] = "on" if service == "turn_on" else "off"

        self.services = SimpleNamespace(async_call=AsyncMock(side_effect=_call))


@pytest.mark.asyncio
async def test_switches_on_for_bad_air_and_off_after_the_min_run():
    hass = _Hass({FAN: "off"})
    v = VentilationController(hass)
    await v.async_reconcile({FAN: True}, 0)
    assert hass.calls == [("fan", "turn_on", FAN)]
    assert v.is_running(FAN) and v.dirty
    # Good again before the min run is over: keeps running
    await v.async_reconcile({FAN: False}, VENTILATION_MIN_RUN_S - 1)
    assert len(hass.calls) == 1
    await v.async_reconcile({FAN: False}, VENTILATION_MIN_RUN_S)
    assert hass.calls[-1] == ("fan", "turn_off", FAN)
    assert not v.is_running(FAN)


@pytest.mark.asyncio
async def test_a_unit_already_running_is_never_switched_off():
    hass = _Hass({"switch.kwl_boost": "on"})
    v = VentilationController(hass)
    await v.async_reconcile({"switch.kwl_boost": True}, 0)
    await v.async_reconcile({"switch.kwl_boost": False}, VENTILATION_MIN_RUN_S * 2)
    await v.async_reconcile({}, VENTILATION_MIN_RUN_S * 3)
    assert hass.calls == []


@pytest.mark.asyncio
async def test_switched_off_by_someone_stays_off_until_the_air_was_good():
    hass = _Hass({FAN: "off"})
    v = VentilationController(hass)
    await v.async_reconcile({FAN: True}, 0)
    hass.state_map[FAN] = "off"  # someone switched it off
    await v.async_reconcile({FAN: True}, VENTILATION_REPORT_GRACE_S)
    assert not v.is_running(FAN)
    await v.async_reconcile({FAN: True}, VENTILATION_REPORT_GRACE_S + 30)
    assert hass.calls == [("fan", "turn_on", FAN)]
    # Good air ends the spell; the next bad spell switches it on again
    await v.async_reconcile({FAN: False}, 2000)
    await v.async_reconcile({FAN: True}, 3000)
    assert hass.calls[-1] == ("fan", "turn_on", FAN)


@pytest.mark.asyncio
async def test_off_just_after_the_command_is_report_lag_not_a_manual_off():
    hass = _Hass({FAN: "off"})
    v = VentilationController(hass)
    await v.async_reconcile({FAN: True}, 0)
    hass.state_map[FAN] = "off"  # not reported yet
    await v.async_reconcile({FAN: True}, VENTILATION_REPORT_GRACE_S - 1)
    assert v.is_running(FAN)


@pytest.mark.asyncio
async def test_an_owned_unit_nobody_uses_any_more_goes_off_at_once():
    """Room deleted, entity removed from the room or climate control off: not in ``wanted``."""
    hass = _Hass({FAN: "off"})
    v = VentilationController(hass)
    await v.async_reconcile({FAN: True}, 0)
    await v.async_reconcile({}, 10)
    assert hass.calls[-1] == ("fan", "turn_off", FAN)
    assert not v.is_running(FAN)


@pytest.mark.asyncio
async def test_an_owned_unit_already_off_is_only_released():
    hass = _Hass({FAN: "off"})
    v = VentilationController(hass)
    await v.async_reconcile({FAN: True}, 0)
    hass.state_map[FAN] = "off"
    await v.async_reconcile({}, 10)
    assert hass.calls == [("fan", "turn_on", FAN)]
    assert not v.is_running(FAN)


@pytest.mark.asyncio
async def test_unavailable_unit_gets_no_command_and_stays_owned():
    hass = _Hass({FAN: "off"})
    v = VentilationController(hass)
    await v.async_reconcile({FAN: True}, 0)
    hass.state_map[FAN] = "unavailable"
    await v.async_reconcile({FAN: False}, VENTILATION_MIN_RUN_S * 2)
    assert v.is_running(FAN)
    assert len(hass.calls) == 1


@pytest.mark.asyncio
async def test_failed_command_is_retried_next_cycle():
    hass = _Hass({FAN: "off"})
    v = VentilationController(hass)
    hass.fail = True
    await v.async_reconcile({FAN: True}, 0)
    assert not v.is_running(FAN)
    hass.fail = False
    await v.async_reconcile({FAN: True}, 30)
    assert v.is_running(FAN)
    hass.fail = True
    await v.async_reconcile({}, 60)
    assert v.is_running(FAN)


@pytest.mark.asyncio
async def test_ownership_survives_a_restart():
    hass = _Hass({"input_boolean.luefter": "off"})
    v = VentilationController(hass)
    await v.async_reconcile({"input_boolean.luefter": True}, 0)
    restarted = VentilationController(hass)
    restarted.load_state(v.get_state())
    await restarted.async_reconcile({"input_boolean.luefter": False}, VENTILATION_MIN_RUN_S)
    assert hass.calls[-1] == ("input_boolean", "turn_off", "input_boolean.luefter")


def test_load_state_ignores_garbage():
    v = VentilationController(MagicMock())
    v.load_state({"fan.a": 12.0, "fan.b": "x"})
    assert v.get_state() == {"fan.a": 12.0}
    v.load_state(None)  # type: ignore[arg-type]
    assert v.get_state() == {}


def test_tracker_seeded_bad_continues_a_run_across_a_restart():
    t = AirQualityTracker()
    # Between release and threshold: the run started before the restart goes on
    assert t.evaluate("bed", "co2", 900, 1000, 0, assume_bad=True) is True
    # Seeded only once: below the release it is good, and stays good
    assert t.evaluate("bed", "co2", 790, 1000, 30, assume_bad=True) is False
    assert t.evaluate("bed", "co2", 900, 1000, 60, assume_bad=True) is False


def test_tracker_seeded_bad_holds_a_silent_sensor_until_stale():
    t = AirQualityTracker()
    assert t.evaluate("bed", "co2", None, 1000, 0, assume_bad=True) is True
    assert t.evaluate("bed", "co2", None, 1000, MAX_SENSOR_STALENESS + 1, assume_bad=True) is False


@pytest.mark.asyncio
async def test_hand_on_then_hand_off_during_a_bad_spell_stays_off():
    """Switched on by hand while the air was good, off by hand while it is bad: not switched on again (M2)."""
    hass = _Hass({FAN: "on"})
    v = VentilationController(hass)
    await v.async_reconcile({FAN: True}, 0)
    assert not v.is_running(FAN)
    hass.state_map[FAN] = "off"
    await v.async_reconcile({FAN: True}, 30)
    await v.async_reconcile({FAN: True}, 60)
    assert hass.calls == []
    # The next bad spell is RoomMind's again
    await v.async_reconcile({FAN: False}, 90)
    await v.async_reconcile({FAN: True}, 120)
    assert hass.calls == [("fan", "turn_on", FAN)]


@pytest.mark.asyncio
async def test_own_switch_off_is_no_hand_on_it():
    """RoomMind ended its run; the air turning bad again right after switches it on again."""
    hass = _Hass({FAN: "off"})
    v = VentilationController(hass)
    await v.async_reconcile({FAN: True}, 0)
    await v.async_reconcile({FAN: False}, VENTILATION_MIN_RUN_S)
    await v.async_reconcile({FAN: True}, VENTILATION_MIN_RUN_S + 30)
    assert [c[1] for c in hass.calls] == ["turn_on", "turn_off", "turn_on"]


@pytest.mark.asyncio
async def test_owned_unit_unavailable_when_the_room_drops_it_goes_off_once_back():
    """Ownership is kept while the unit is unavailable, else it ran on for good (Mi1)."""
    hass = _Hass({FAN: "off"})
    v = VentilationController(hass)
    await v.async_reconcile({FAN: True}, 0)
    hass.state_map[FAN] = "unavailable"
    await v.async_reconcile({}, 100)
    assert v.is_running(FAN)
    hass.state_map[FAN] = "on"
    await v.async_reconcile({}, 200)
    assert hass.calls[-1] == ("fan", "turn_off", FAN)
    assert not v.is_running(FAN)


@pytest.mark.asyncio
async def test_off_after_a_dropout_is_no_hand_on_it():
    """Power cut or Zigbee rejoin: the unit comes back off while the air is still bad (Mi3)."""
    hass = _Hass({FAN: "off"})
    v = VentilationController(hass)
    await v.async_reconcile({FAN: True}, 0)
    hass.state_map[FAN] = "unavailable"
    await v.async_reconcile({FAN: True}, 300)
    hass.state_map[FAN] = "off"
    await v.async_reconcile({FAN: True}, 330)
    assert hass.calls == [("fan", "turn_on", FAN), ("fan", "turn_on", FAN)]
    assert v.is_running(FAN)
    # Air good meanwhile: the unit is only released
    hass.state_map[FAN] = "unknown"
    await v.async_reconcile({FAN: False}, 400)
    hass.state_map[FAN] = "off"
    await v.async_reconcile({FAN: False}, 430)
    assert not v.is_running(FAN)
    assert len(hass.calls) == 2


@pytest.mark.asyncio
async def test_first_reading_after_a_restart_off_is_switched_on_again():
    hass = _Hass({FAN: "off"})
    v = VentilationController(hass)
    v.load_state({FAN: 0.0})
    await v.async_reconcile({FAN: True}, 100)
    assert hass.calls == [("fan", "turn_on", FAN)]


@pytest.mark.asyncio
@pytest.mark.parametrize("wanted", [{FAN: True}, {}])
async def test_unit_deleted_in_ha_is_released(monkeypatch, wanted):
    """No state and no registry entry once HA runs (Mi6); still loading or registered: kept."""
    from custom_components.roommind.managers import air_quality_manager

    registry = SimpleNamespace(async_get=lambda eid: None)
    monkeypatch.setattr(air_quality_manager.er, "async_get", lambda _hass: registry)
    hass = _Hass({FAN: "off"})
    v = VentilationController(hass)
    await v.async_reconcile({FAN: True}, 0)
    del hass.state_map[FAN]
    hass.state = CoreState.starting
    await v.async_reconcile(wanted, 10)
    assert v.is_running(FAN)
    registry.async_get = lambda eid: object()
    hass.state = CoreState.running
    await v.async_reconcile(wanted, 20)
    assert v.is_running(FAN)
    registry.async_get = lambda eid: None
    await v.async_reconcile(wanted, 30)
    assert not v.is_running(FAN)
