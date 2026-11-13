"""Air quality (CO2/VOC) in the coordinator cycle and the ventilation it runs (#267)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.const import DOMAIN

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get

AREA = "living_room_abc12345"
CO2 = "sensor.living_room_co2"
VOC = "sensor.living_room_voc"
FAN = "fan.living_room"
AQ_ROOM = {**SAMPLE_ROOM, "co2_sensor": CO2, "ventilation_entity": FAN}


def _states(co2="1200", voc=None, fan="off"):
    base = make_mock_states_get(temp="21.0", humidity="50")
    extra = {CO2: co2, VOC: voc, FAN: fan}

    def get(eid):
        if eid in extra:
            return None if extra[eid] is None else SimpleNamespace(state=extra[eid], attributes={})
        return base(eid)

    return get, extra


def _setup(hass, mock_config_entry, room, settings=None, **states):
    store = _make_store_mock({AREA: room}, settings)
    hass.data = {DOMAIN: {"store": store}}
    get, extra = _states(**states)
    hass.states.get = get
    calls = []

    async def _call(domain, service, data, **_kw):
        calls.append((domain, service, data.get("entity_id")))
        if data.get("entity_id") in extra and service in ("turn_on", "turn_off"):
            extra[data["entity_id"]] = "on" if service == "turn_on" else "off"

    hass.services.async_call = AsyncMock(side_effect=_call)
    coordinator = _create_coordinator(hass, mock_config_entry)
    return coordinator, store, extra, calls


def _fan_calls(calls):
    return [c for c in calls if c[2] == FAN]


@pytest.mark.asyncio
async def test_co2_above_threshold_is_bad_and_switches_the_fan_on(hass, mock_config_entry):
    coordinator, store, extra, calls = _setup(hass, mock_config_entry, AQ_ROOM)
    data = await coordinator._async_update_data()
    room = data["rooms"][AREA]
    assert room["co2"] == 1200.0
    assert room["air_quality_bad"] is True
    assert room["air_quality_reason"] == "co2"
    assert room["ventilation_active"] is True
    assert _fan_calls(calls) == [("fan", "turn_on", FAN)]
    store.async_save_settings.assert_any_await(
        {"ventilation_state": {FAN: pytest.approx(coordinator._ventilation.get_state()[FAN])}}
    )


@pytest.mark.asyncio
async def test_custom_threshold_and_hysteresis_across_cycles(hass, mock_config_entry):
    room_cfg = {**AQ_ROOM, "co2_threshold": 1500}
    coordinator, _, extra, calls = _setup(hass, mock_config_entry, room_cfg, co2="1400")
    assert (await coordinator._async_update_data())["rooms"][AREA]["air_quality_bad"] is False
    extra[CO2] = "1500"
    assert (await coordinator._async_update_data())["rooms"][AREA]["air_quality_bad"] is True
    extra[CO2] = "1250"  # above 80 % of 1500: still bad
    assert (await coordinator._async_update_data())["rooms"][AREA]["air_quality_bad"] is True
    extra[CO2] = "1150"
    assert (await coordinator._async_update_data())["rooms"][AREA]["air_quality_bad"] is False


@pytest.mark.asyncio
async def test_voc_without_threshold_is_shown_not_judged(hass, mock_config_entry):
    room_cfg = {**SAMPLE_ROOM, "voc_sensor": VOC}
    coordinator, _, _, _ = _setup(hass, mock_config_entry, room_cfg, voc="450")
    room = (await coordinator._async_update_data())["rooms"][AREA]
    assert room["voc"] == 450.0
    assert room["air_quality_bad"] is False


@pytest.mark.asyncio
async def test_voc_with_threshold_in_the_sensor_unit(hass, mock_config_entry):
    room_cfg = {**SAMPLE_ROOM, "voc_sensor": VOC, "voc_threshold": 250}
    coordinator, _, _, _ = _setup(hass, mock_config_entry, room_cfg, voc="300")
    room = (await coordinator._async_update_data())["rooms"][AREA]
    assert room["air_quality_bad"] is True
    assert room["air_quality_reason"] == "voc"


@pytest.mark.asyncio
async def test_room_without_air_quality_sensor_is_untouched(hass, mock_config_entry):
    coordinator, _, _, calls = _setup(hass, mock_config_entry, {**SAMPLE_ROOM, "ventilation_entity": FAN})
    room = (await coordinator._async_update_data())["rooms"][AREA]
    assert room["co2"] is None and room["air_quality_bad"] is False
    assert _fan_calls(calls) == []


@pytest.mark.asyncio
async def test_climate_control_off_switches_nothing_on(hass, mock_config_entry):
    coordinator, _, _, calls = _setup(hass, mock_config_entry, {**AQ_ROOM, "climate_control_enabled": False})
    room = (await coordinator._async_update_data())["rooms"][AREA]
    assert room["air_quality_bad"] is True  # still measured: binary sensor and hint
    assert _fan_calls(calls) == []


@pytest.mark.asyncio
async def test_global_control_off_switches_an_owned_fan_off_once(hass, mock_config_entry):
    coordinator, store, extra, calls = _setup(hass, mock_config_entry, AQ_ROOM)
    await coordinator._async_update_data()
    store.get_settings.return_value = {**store.get_settings.return_value, "climate_control_active": False}
    await coordinator._async_update_data()
    await coordinator._async_update_data()
    assert _fan_calls(calls) == [("fan", "turn_on", FAN), ("fan", "turn_off", FAN)]


@pytest.mark.asyncio
async def test_a_fan_someone_switched_on_stays_on(hass, mock_config_entry):
    coordinator, _, extra, calls = _setup(hass, mock_config_entry, AQ_ROOM, co2="600", fan="on")
    for co2 in ("1200", "600"):
        extra[CO2] = co2
        room = (await coordinator._async_update_data())["rooms"][AREA]
        assert room["ventilation_active"] is False
    assert _fan_calls(calls) == []


@pytest.mark.asyncio
async def test_fan_removed_from_the_room_goes_off(hass, mock_config_entry):
    coordinator, store, _, calls = _setup(hass, mock_config_entry, AQ_ROOM)
    await coordinator._async_update_data()
    store.get_rooms.return_value = {AREA: {**AQ_ROOM, "ventilation_entity": ""}}
    await coordinator._async_update_data()
    assert _fan_calls(calls)[-1] == ("fan", "turn_off", FAN)


@pytest.mark.asyncio
async def test_one_fan_for_two_rooms_runs_while_either_needs_it(hass, mock_config_entry):
    coordinator, store, extra, calls = _setup(hass, mock_config_entry, AQ_ROOM)
    other = {**AQ_ROOM, "area_id": "office", "co2_sensor": "sensor.office_co2"}
    store.get_rooms.return_value = {AREA: AQ_ROOM, "office": other}
    extra["sensor.office_co2"] = "600"
    await coordinator._async_update_data()
    assert _fan_calls(calls) == [("fan", "turn_on", FAN)]


@pytest.mark.asyncio
async def test_outdoor_room_has_no_air_quality(hass, mock_config_entry):
    coordinator, _, _, calls = _setup(hass, mock_config_entry, {**AQ_ROOM, "is_outdoor": True})
    room = (await coordinator._async_update_data())["rooms"][AREA]
    assert room["air_quality_bad"] is False and room["co2"] is None
    assert _fan_calls(calls) == []


@pytest.mark.asyncio
async def test_ventilation_state_loaded_once(hass, mock_config_entry):
    coordinator, store, extra, calls = _setup(
        hass, mock_config_entry, AQ_ROOM, settings={"ventilation_state": {FAN: 0.0}}, co2="600", fan="on"
    )
    await coordinator._async_update_data()
    # Owned since the epoch, min run long over, air good: RoomMind switches its fan off
    assert _fan_calls(calls) == [("fan", "turn_off", FAN)]


@pytest.mark.asyncio
async def test_failing_reconcile_does_not_break_the_cycle(hass, mock_config_entry):
    coordinator, _, _, _ = _setup(hass, mock_config_entry, AQ_ROOM)
    coordinator._ventilation.async_reconcile = AsyncMock(side_effect=RuntimeError("boom"))
    data = await coordinator._async_update_data()
    assert data["rooms"][AREA]["ventilation_active"] is False


def _registry(entries):
    reg = MagicMock()
    reg.entities.values.return_value = entries
    return reg


def _entry(uid, eid):
    e = MagicMock()
    e.platform = DOMAIN
    e.unique_id = uid
    e.entity_id = eid
    return e


def test_cleanup_keeps_the_air_quality_entity_only_with_a_sensor(hass, mock_config_entry):
    coordinator = _create_coordinator(hass, mock_config_entry)
    store = MagicMock()
    store.get_rooms.return_value = {
        "bed": {"co2_sensor": CO2},
        "hall": {},
        "garden": {"co2_sensor": CO2, "is_outdoor": True},
    }
    hass.data = {DOMAIN: {"store": store}}
    reg = _registry(
        [
            _entry(f"{DOMAIN}_{a}_air_quality", f"binary_sensor.roommind_{a}_air_quality")
            for a in ("bed", "hall", "garden")
        ]
    )
    with patch("homeassistant.helpers.entity_registry.async_get", return_value=reg):
        coordinator.cleanup_orphaned_entities()
    removed = [c.args[0] for c in reg.async_remove.call_args_list]
    assert removed == ["binary_sensor.roommind_hall_air_quality", "binary_sensor.roommind_garden_air_quality"]


@pytest.mark.asyncio
async def test_room_added_creates_the_air_quality_entity_next_to_the_cover_one(hass, mock_config_entry):
    coordinator = _create_coordinator(hass, mock_config_entry)
    store = MagicMock()
    store.get_room.return_value = {}
    hass.data = {DOMAIN: {"store": store}}
    coordinator.async_request_refresh = AsyncMock()
    coordinator.async_add_binary_sensor_entities = MagicMock()
    coordinator._binary_sensor_entity_areas.add("bed")  # cover sensor already there
    with patch("custom_components.roommind.binary_sensor._get_area_name", return_value="Bed"):
        await coordinator.async_room_added({"area_id": "bed", "covers": ["cover.x"], "co2_sensor": CO2})
        await coordinator.async_room_added({"area_id": "bed", "covers": ["cover.x"], "co2_sensor": CO2})
    added = [e for c in coordinator.async_add_binary_sensor_entities.call_args_list for e in c.args[0]]
    assert [e.unique_id for e in added] == [f"{DOMAIN}_bed_air_quality"]
    with patch("homeassistant.helpers.entity_registry.async_get", return_value=_registry([])):
        coordinator._forget_room("bed")
    assert "bed" not in coordinator._air_quality_entity_areas
