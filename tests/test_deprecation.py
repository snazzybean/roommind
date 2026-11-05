"""Tests for the deprecation of the per-room entities (#238)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState

from custom_components.roommind import deprecation
from custom_components.roommind.const import DOMAIN


def _entry(unique_id, entity_id, platform=DOMAIN, disabled=False):
    entry = MagicMock()
    entry.platform = platform
    entry.unique_id = unique_id
    entry.entity_id = entity_id
    entry.disabled = disabled
    return entry


@pytest.fixture
def hass():
    hass = MagicMock()
    store = MagicMock()
    store.get_rooms.return_value = {"living_room": {}, "x_mode": {}}
    hass.data = {DOMAIN: {"store": store}}
    return hass


def _run(hass, entries, automations=None, scripts=None, replacement="climate.roommind_living_room"):
    automations = automations or {}
    scripts = scripts or {}
    registry = MagicMock()
    registry.entities.values.return_value = entries
    registry.async_get_entity_id.return_value = replacement
    with (
        patch("homeassistant.helpers.entity_registry.async_get", return_value=registry),
        patch(
            "homeassistant.components.automation.automations_with_entity",
            side_effect=lambda _h, eid: automations.get(eid, []),
        ),
        patch("homeassistant.components.script.scripts_with_entity", side_effect=lambda _h, eid: scripts.get(eid, [])),
        patch("homeassistant.helpers.issue_registry.async_create_issue") as create,
        patch("homeassistant.helpers.issue_registry.async_delete_issue") as delete,
    ):
        deprecation.async_check_deprecated_entities(hass)
    return create, delete


def test_issue_lists_used_deprecated_entities(hass):
    entries = [
        _entry("roommind_living_room_override", "climate.roommind_living_room_override"),
        _entry("roommind_living_room_climate_control", "switch.roommind_living_room_climate_control"),
        _entry("roommind_living_room_mode", "sensor.roommind_living_room_mode"),
        _entry("roommind_living_room_climate", "climate.roommind_living_room"),
    ]
    create, delete = _run(
        hass,
        entries,
        automations={
            "climate.roommind_living_room_override": ["automation.wall_dial"],
            "climate.roommind_living_room": ["automation.new_style"],
        },
        scripts={
            "switch.roommind_living_room_climate_control": ["script.leave_home"],
            "sensor.roommind_living_room_mode": ["script.show_mode"],
        },
    )
    delete.assert_not_called()
    create.assert_called_once()
    kwargs = create.call_args.kwargs
    assert create.call_args.args[1:] == (DOMAIN, deprecation.DEPRECATED_ENTITIES_ISSUE)
    assert kwargs["is_fixable"] is False
    assert kwargs["translation_placeholders"]["entities"] == (
        "- `climate.roommind_living_room_override` → `climate.roommind_living_room` (automation.wall_dial)\n"
        "- `sensor.roommind_living_room_mode` → `climate.roommind_living_room` (script.show_mode)"
    )


def test_no_issue_while_nothing_uses_them(hass):
    entries = [
        _entry("roommind_living_room_override", "climate.roommind_living_room_override"),
        _entry("roommind_living_room_target_temp", "sensor.roommind_living_room_target_temp", disabled=True),
        _entry("roommind_vacation", "switch.roommind_vacation"),
        _entry("roommind_climate_control", "switch.roommind_climate_control"),
        _entry("roommind_x_mode_climate", "climate.roommind_x_mode"),
        _entry("roommind_other_override", "climate.roommind_other_override", platform="template"),
        _entry(42, "sensor.weird"),
    ]
    create, delete = _run(
        hass,
        entries,
        automations={
            "sensor.roommind_living_room_target_temp": ["automation.disabled_entity"],
            "switch.roommind_vacation": ["automation.vacation"],
            "switch.roommind_climate_control": ["automation.summer"],
            "climate.roommind_x_mode": ["automation.room_named_mode"],
        },
    )
    create.assert_not_called()
    delete.assert_called_once()


def test_replacement_falls_back_to_default_entity_id(hass):
    entries = [_entry("roommind_living_room_target_temp", "sensor.roommind_living_room_target_temp")]
    create, _ = _run(
        hass, entries, automations={"sensor.roommind_living_room_target_temp": ["automation.a"]}, replacement=None
    )
    assert "→ `climate.roommind_living_room`" in create.call_args.kwargs["translation_placeholders"]["entities"]


def test_check_without_store_does_nothing():
    hass = MagicMock()
    hass.data = {}
    create, delete = _run(hass, [])
    create.assert_not_called()
    delete.assert_not_called()


def test_schedule_runs_now_when_ha_is_running(hass):
    hass.state = CoreState.running
    with patch.object(deprecation, "async_check_deprecated_entities") as check:
        deprecation.async_schedule_deprecation_check(hass)
    check.assert_called_once_with(hass)
    hass.bus.async_listen_once.assert_not_called()


def test_schedule_waits_for_startup(hass):
    hass.state = CoreState.starting
    with patch.object(deprecation, "async_check_deprecated_entities") as check:
        deprecation.async_schedule_deprecation_check(hass)
        check.assert_not_called()
        event, listener = hass.bus.async_listen_once.call_args.args
        assert event == EVENT_HOMEASSISTANT_STARTED
        listener(MagicMock())
    check.assert_called_once_with(hass)


def test_deprecated_use_is_logged_once_per_entity(caplog):
    deprecation._warned.discard("sensor.roommind_kitchen_mode")
    deprecation.warn_deprecated_use("sensor.roommind_kitchen_mode", "kitchen")
    deprecation.warn_deprecated_use("sensor.roommind_kitchen_mode", "kitchen")
    messages = [r.getMessage() for r in caplog.records if "deprecated" in r.getMessage()]
    assert messages == [
        "sensor.roommind_kitchen_mode is deprecated and will be removed in a future release, "
        "use climate.roommind_kitchen instead"
    ]
