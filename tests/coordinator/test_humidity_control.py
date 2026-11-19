"""Humidity limits in the coordinator cycle: ventilation, dehumidifier, humidifier (#518, #526)."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.roommind.const import DOMAIN

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get

AREA = "living_room_abc12345"
HUM_SENSOR = "sensor.living_room_humidity"
FAN = "fan.bath"
DEHUM = "switch.dehumidifier"
HUMIDIFIER = "humidifier.bedroom"
CO2 = "sensor.living_room_co2"
OUT_HUM = "sensor.outdoor_humidity"
WINDOW = "binary_sensor.window"


def _setup(hass, mock_config_entry, room, settings=None, humidity="75", window="off", **states):
    store = _make_store_mock({AREA: room}, settings)
    hass.data = {DOMAIN: {"store": store}}
    base = make_mock_states_get(temp="21.0", humidity=humidity, window_sensors={WINDOW: window})
    extra = {FAN: "off", DEHUM: "off", HUMIDIFIER: "off", CO2: None, OUT_HUM: None, **states}

    def get(eid):
        if eid in extra:
            return None if extra[eid] is None else SimpleNamespace(state=extra[eid], attributes={})
        return base(eid)

    hass.states.get = get
    calls = []

    async def _call(domain, service, data, **_kw):
        eid = data.get("entity_id")
        calls.append((domain, service, eid))
        if eid in extra and service in ("turn_on", "turn_off"):
            extra[eid] = "on" if service == "turn_on" else "off"

    hass.services.async_call = AsyncMock(side_effect=_call)
    coordinator = _create_coordinator(hass, mock_config_entry)
    return coordinator, store, extra, calls


def _switch_calls(calls, *eids):
    return [c for c in calls if c[2] in eids and c[1] in ("turn_on", "turn_off")]


BATH = {**SAMPLE_ROOM, "ventilation_entity": FAN, "humidity_max": 60}


async def _cycle(coordinator):
    return (await coordinator._async_update_data())["rooms"][AREA]


@pytest.mark.asyncio
async def test_without_limits_nothing_changes(hass, mock_config_entry):
    """A room with a fan and a humidity sensor but no limit: as before, the fan is not touched."""
    room_cfg = {**SAMPLE_ROOM, "ventilation_entity": FAN, "dehumidifier_entity": DEHUM, "humidifier_entity": HUMIDIFIER}
    coordinator, store, _, calls = _setup(hass, mock_config_entry, room_cfg, humidity="95")
    room = await _cycle(coordinator)
    assert room["humidity_high"] is False and room["humidity_low"] is False
    assert room["ventilation_active"] is False and room["dehumidifier_active"] is False
    assert _switch_calls(calls, FAN, DEHUM, HUMIDIFIER) == []
    saved = [c.args[0] for c in store.async_save_settings.await_args_list]
    assert not any("humidity_device_state" in s or "ventilation_state" in s for s in saved)


@pytest.mark.asyncio
async def test_humid_bathroom_runs_the_fan_until_the_hysteresis(hass, mock_config_entry):
    coordinator, store, extra, calls = _setup(hass, mock_config_entry, BATH)
    room = await _cycle(coordinator)
    assert room["humidity_high"] is True and room["humidity_ventilate"] is True
    assert room["ventilation_active"] is True
    assert room["air_quality_bad"] is False
    assert _switch_calls(calls, FAN) == [("fan", "turn_on", FAN)]
    store.async_save_settings.assert_any_await(
        {"ventilation_state": {FAN: pytest.approx(coordinator._ventilation.get_state()[FAN])}}
    )
    # Back inside the band: still too humid, keeps running
    hass.states.get = _with(hass.states.get, HUM_SENSOR, "57")
    assert (await _cycle(coordinator))["humidity_high"] is True
    # Below the release, min run over: off
    hass.states.get = _with(hass.states.get, HUM_SENSOR, "54")
    coordinator._ventilation._owned[FAN] = time.time() - 3600
    room = await _cycle(coordinator)
    assert room["humidity_high"] is False and room["ventilation_active"] is False
    assert _switch_calls(calls, FAN)[-1] == ("fan", "turn_off", FAN)


def _with(get, eid, state):
    def wrapped(e):
        if e == eid:
            return SimpleNamespace(state=state, attributes={"unit_of_measurement": "%"})
        return get(e)

    return wrapped


@pytest.mark.asyncio
async def test_wetter_outdoor_air_keeps_the_fan_off_but_not_the_dehumidifier(hass, mock_config_entry):
    room_cfg = {**BATH, "dehumidifier_entity": DEHUM}
    coordinator, store, _, calls = _setup(
        hass,
        mock_config_entry,
        room_cfg,
        settings={"outdoor_humidity_sensor": OUT_HUM},
        humidity="65",
        **{OUT_HUM: "95", "sensor.outdoor_temp": "25.0"},
    )
    room = await _cycle(coordinator)
    assert room["humidity_high"] is True
    assert room["humidity_ventilate"] is False and room["humidity_vent_blocked"] is True
    assert room["dehumidifier_active"] is True
    assert _switch_calls(calls, FAN, DEHUM) == [("switch", "turn_on", DEHUM)]
    store.async_save_settings.assert_any_await(
        {"humidity_device_state": {DEHUM: pytest.approx(coordinator._humidity_devices.get_state()[DEHUM])}}
    )


@pytest.mark.asyncio
async def test_dry_winter_air_outside_lets_the_fan_run(hass, mock_config_entry):
    coordinator, _, _, calls = _setup(
        hass,
        mock_config_entry,
        BATH,
        settings={"outdoor_humidity_sensor": OUT_HUM},
        **{OUT_HUM: "90"},  # 5 °C outdoor from the default mock
    )
    room = await _cycle(coordinator)
    assert room["humidity_ventilate"] is True
    assert _switch_calls(calls, FAN) == [("fan", "turn_on", FAN)]


@pytest.mark.asyncio
async def test_dry_room_runs_the_humidifier_and_never_the_dehumidifier(hass, mock_config_entry):
    room_cfg = {
        **SAMPLE_ROOM,
        "humidity_max": 60,
        "humidity_min": 40,
        "dehumidifier_entity": DEHUM,
        "humidifier_entity": HUMIDIFIER,
    }
    coordinator, _, _, calls = _setup(hass, mock_config_entry, room_cfg, humidity="35")
    room = await _cycle(coordinator)
    assert room["humidity_low"] is True and room["humidifier_active"] is True
    assert room["dehumidifier_active"] is False
    assert _switch_calls(calls, DEHUM, HUMIDIFIER) == [("humidifier", "turn_on", HUMIDIFIER)]


@pytest.mark.asyncio
async def test_window_open_switches_the_dehumidifier_off_at_once_but_not_the_fan(hass, mock_config_entry):
    room_cfg = {**BATH, "dehumidifier_entity": DEHUM, "window_sensors": [WINDOW]}
    coordinator, _, extra, calls = _setup(hass, mock_config_entry, room_cfg)
    await _cycle(coordinator)
    assert _switch_calls(calls, FAN, DEHUM) == [("fan", "turn_on", FAN), ("switch", "turn_on", DEHUM)]
    hass.states.get = _with(hass.states.get, WINDOW, "on")
    room = await _cycle(coordinator)
    assert room["window_open"] is True
    assert room["dehumidifier_active"] is False and room["ventilation_active"] is True
    assert _switch_calls(calls, FAN, DEHUM)[-1] == ("switch", "turn_off", DEHUM)


@pytest.mark.asyncio
async def test_climate_control_off_switches_nothing_on(hass, mock_config_entry):
    room_cfg = {**BATH, "dehumidifier_entity": DEHUM, "climate_control_enabled": False}
    coordinator, _, _, calls = _setup(hass, mock_config_entry, room_cfg)
    room = await _cycle(coordinator)
    assert room["humidity_high"] is True  # still measured: hint
    assert room["humidity_ventilate"] is False and room["humidity_vent_blocked"] is False
    assert _switch_calls(calls, FAN, DEHUM) == []


@pytest.mark.asyncio
async def test_global_control_off_switches_owned_devices_off_once(hass, mock_config_entry):
    room_cfg = {**BATH, "dehumidifier_entity": DEHUM}
    coordinator, store, _, calls = _setup(hass, mock_config_entry, room_cfg)
    await _cycle(coordinator)
    store.get_settings.return_value = {**store.get_settings.return_value, "climate_control_active": False}
    await _cycle(coordinator)
    room = await _cycle(coordinator)
    assert room["humidity_ventilate"] is False and room["humidity_vent_blocked"] is False
    assert _switch_calls(calls, FAN, DEHUM) == [
        ("fan", "turn_on", FAN),
        ("switch", "turn_on", DEHUM),
        ("fan", "turn_off", FAN),
        ("switch", "turn_off", DEHUM),
    ]


@pytest.mark.asyncio
async def test_co2_and_humidity_share_one_fan(hass, mock_config_entry):
    """CO2 good again while the room is still too humid: the fan stays on, and the other way round."""
    room_cfg = {**BATH, "co2_sensor": CO2}
    coordinator, _, extra, calls = _setup(hass, mock_config_entry, room_cfg, **{CO2: "1200"})
    room = await _cycle(coordinator)
    assert room["air_quality_bad"] is True and room["humidity_high"] is True
    coordinator._ventilation._owned[FAN] = time.time() - 3600
    extra[CO2] = "600"
    room = await _cycle(coordinator)
    assert room["ventilation_active"] is True
    extra[CO2] = "1200"
    hass.states.get = _with(hass.states.get, HUM_SENSOR, "50")
    room = await _cycle(coordinator)
    assert room["humidity_high"] is False and room["ventilation_active"] is True
    assert _switch_calls(calls, FAN) == [("fan", "turn_on", FAN)]


@pytest.mark.asyncio
async def test_a_dehumidifier_run_from_before_the_restart_goes_on(hass, mock_config_entry):
    room_cfg = {**SAMPLE_ROOM, "humidity_max": 60, "dehumidifier_entity": DEHUM}
    coordinator, _, _, calls = _setup(
        hass,
        mock_config_entry,
        room_cfg,
        settings={"humidity_device_state": {DEHUM: time.time() - 3600}},
        humidity="57",
        **{DEHUM: "on"},
    )
    room = await _cycle(coordinator)
    assert room["humidity_high"] is True and room["dehumidifier_active"] is True
    assert _switch_calls(calls, DEHUM) == []


@pytest.mark.asyncio
async def test_a_humidifier_run_from_before_the_restart_goes_on(hass, mock_config_entry):
    room_cfg = {**SAMPLE_ROOM, "humidity_min": 40, "humidifier_entity": HUMIDIFIER}
    coordinator, _, _, calls = _setup(
        hass,
        mock_config_entry,
        room_cfg,
        settings={"humidity_device_state": {HUMIDIFIER: time.time() - 3600}},
        humidity="43",
        **{HUMIDIFIER: "on"},
    )
    room = await _cycle(coordinator)
    assert room["humidity_low"] is True and room["humidifier_active"] is True
    assert _switch_calls(calls, HUMIDIFIER) == []


@pytest.mark.asyncio
async def test_limit_removed_switches_the_owned_dehumidifier_off(hass, mock_config_entry):
    room_cfg = {**SAMPLE_ROOM, "humidity_max": 60, "dehumidifier_entity": DEHUM}
    coordinator, store, _, calls = _setup(hass, mock_config_entry, room_cfg)
    await _cycle(coordinator)
    store.get_rooms.return_value = {AREA: {**room_cfg, "humidity_max": None}}
    room = await _cycle(coordinator)
    assert room["humidity_high"] is False and room["dehumidifier_active"] is False
    assert _switch_calls(calls, DEHUM) == [("switch", "turn_on", DEHUM), ("switch", "turn_off", DEHUM)]


@pytest.mark.asyncio
async def test_outdoor_room_has_no_humidity_control(hass, mock_config_entry):
    room_cfg = {**BATH, "is_outdoor": True, "dehumidifier_entity": DEHUM}
    coordinator, _, _, calls = _setup(hass, mock_config_entry, room_cfg)
    room = await _cycle(coordinator)
    assert room["humidity_high"] is False and room["dehumidifier_active"] is False
    assert _switch_calls(calls, FAN, DEHUM) == []


@pytest.mark.asyncio
async def test_failing_humidity_reconcile_does_not_break_the_cycle(hass, mock_config_entry):
    room_cfg = {**SAMPLE_ROOM, "humidity_max": 60, "dehumidifier_entity": DEHUM}
    coordinator, _, _, _ = _setup(hass, mock_config_entry, room_cfg)
    coordinator._humidity_devices.async_reconcile = AsyncMock(side_effect=RuntimeError("boom"))
    room = await _cycle(coordinator)
    assert room["humidity_high"] is True and room["dehumidifier_active"] is False


@pytest.mark.asyncio
async def test_forget_room_drops_the_humidity_judgement(hass, mock_config_entry):
    room_cfg = {**SAMPLE_ROOM, "humidity_max": 60}
    coordinator, _, _, _ = _setup(hass, mock_config_entry, room_cfg)
    await _cycle(coordinator)
    assert coordinator._humidity.is_too_humid(AREA)
    from unittest.mock import MagicMock, patch

    reg = MagicMock()
    reg.entities.values.return_value = []
    with patch("homeassistant.helpers.entity_registry.async_get", return_value=reg):
        coordinator._forget_room(AREA)
    assert not coordinator._humidity.is_too_humid(AREA)


@pytest.mark.asyncio
async def test_a_fan_run_for_co2_does_not_count_as_too_humid(hass, mock_config_entry):
    """Limit switched on (or a restart) while the fan runs for CO2, humidity inside the band: not too humid."""
    room_cfg = {
        **SAMPLE_ROOM,
        "co2_sensor": CO2,
        "ventilation_entity": FAN,
        "humidity_max": 60,
        "dehumidifier_entity": DEHUM,
    }
    coordinator, _, _, calls = _setup(
        hass,
        mock_config_entry,
        room_cfg,
        settings={"ventilation_state": {FAN: time.time() - 60}},
        humidity="57",
        **{CO2: "1200", FAN: "on"},
    )
    room = await _cycle(coordinator)
    assert room["humidity_high"] is False and room["dehumidifier_active"] is False
    assert _switch_calls(calls, DEHUM) == []


@pytest.mark.asyncio
async def test_a_fan_run_for_humidity_goes_on_across_a_restart(hass, mock_config_entry):
    coordinator, store, _, calls = _setup(
        hass,
        mock_config_entry,
        BATH,
        settings={"ventilation_state": {FAN: time.time() - 3600}, "humidity_vent_rooms": [AREA]},
        humidity="57",
        **{FAN: "on"},
    )
    room = await _cycle(coordinator)
    assert room["humidity_high"] is True and room["ventilation_active"] is True
    assert _switch_calls(calls, FAN) == []
    saved = [c.args[0] for c in store.async_save_settings.await_args_list]
    assert not any("humidity_vent_rooms" in s for s in saved)  # unchanged, nothing written


@pytest.mark.asyncio
async def test_rooms_venting_for_humidity_are_persisted(hass, mock_config_entry):
    coordinator, store, _, _ = _setup(hass, mock_config_entry, BATH)
    await _cycle(coordinator)
    store.async_save_settings.assert_any_await({"humidity_vent_rooms": [AREA]})
    hass.states.get = _with(hass.states.get, HUM_SENSOR, "50")
    coordinator._ventilation._owned[FAN] = time.time() - 3600
    await _cycle(coordinator)
    store.async_save_settings.assert_any_await({"humidity_vent_rooms": []})


@pytest.mark.asyncio
async def test_a_fan_run_for_humidity_does_not_seed_bad_air_after_a_restart(hass, mock_config_entry):
    """The fan ran for humidity, CO2 sits under its threshold: after the restart the air is not bad."""
    coordinator, _, _, calls = _setup(
        hass,
        mock_config_entry,
        {**BATH, "co2_sensor": CO2},
        settings={"ventilation_state": {FAN: time.time() - 3600}, "humidity_vent_rooms": [AREA]},
        humidity="50",
        **{CO2: "850", FAN: "on"},
    )
    room = await _cycle(coordinator)
    assert room["air_quality_bad"] is False and room["humidity_high"] is False
    assert _switch_calls(calls, FAN) == [("fan", "turn_off", FAN)]
