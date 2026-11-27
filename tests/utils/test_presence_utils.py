"""Tests for presence_utils.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.roommind.utils.presence_utils import is_presence_away, presence_state


def _make_hass(**kwargs) -> MagicMock:
    """hass mock that is past startup (is_running=True) unless told otherwise."""
    hass = MagicMock(**kwargs)
    hass.is_running = True
    return hass


def _make_state(entity_id: str, state: str) -> MagicMock:
    s = MagicMock()
    s.entity_id = entity_id
    s.state = state
    return s


@pytest.fixture(autouse=True)
def _default_registry(monkeypatch):
    """Make every entity look registered and enabled unless a test says otherwise.

    Without this, an unpatched MagicMock registry answers every lookup with a
    truthy mock, which silently means "gone" — the opposite of the fail-safe
    default a forgetful test should get.
    """
    _patch_registry(monkeypatch, _AlwaysRegistered())


class _AlwaysRegistered(dict):
    def get(self, _key, _default=None):
        return _registry_entry()


def _patch_registry(monkeypatch, known) -> None:
    """Patch the entity registry lookup used by _is_entity_gone.

    *known* maps entity_id → registry entry (None = not registered).
    """
    registry = MagicMock()
    registry.async_get = MagicMock(side_effect=known.get)
    monkeypatch.setattr(
        "custom_components.roommind.utils.presence_utils.er.async_get",
        lambda _hass: registry,
    )


def _registry_entry(disabled_by: object | None = None) -> MagicMock:
    entry = MagicMock()
    entry.disabled_by = disabled_by
    return entry


def test_presence_enabled_but_no_persons_returns_false():
    """When presence_enabled but presence_persons is empty, return False."""
    hass = _make_hass()
    settings = {"presence_enabled": True, "presence_persons": []}
    assert is_presence_away(hass, {}, settings) is False


def test_binary_sensor_off_counts_as_away():
    """binary_sensor 'off' means not home → if all away, returns True."""
    hass = _make_hass()
    hass.states.get = MagicMock(return_value=_make_state("binary_sensor.motion", "off"))
    settings = {"presence_enabled": True, "presence_persons": ["binary_sensor.motion"]}
    assert is_presence_away(hass, {}, settings) is True


def test_binary_sensor_on_counts_as_home():
    """binary_sensor 'on' means home → returns False."""
    hass = _make_hass()
    hass.states.get = MagicMock(return_value=_make_state("binary_sensor.motion", "on"))
    settings = {"presence_enabled": True, "presence_persons": ["binary_sensor.motion"]}
    assert is_presence_away(hass, {}, settings) is False


def test_presence_disabled_returns_false():
    """When presence_enabled is False, always return False regardless of person states."""
    hass = _make_hass()
    hass.states.get = MagicMock(return_value=_make_state("person.kevin", "not_home"))
    settings = {"presence_enabled": False, "presence_persons": ["person.kevin"]}
    assert is_presence_away(hass, {}, settings) is False


def test_person_domain_home():
    """person.kevin with state 'home' means not away."""
    hass = _make_hass()
    hass.states.get = MagicMock(return_value=_make_state("person.kevin", "home"))
    settings = {"presence_enabled": True, "presence_persons": ["person.kevin"]}
    assert is_presence_away(hass, {}, settings) is False


def test_person_domain_not_home():
    """person.kevin with state 'not_home' means away."""
    hass = _make_hass()
    hass.states.get = MagicMock(return_value=_make_state("person.kevin", "not_home"))
    settings = {"presence_enabled": True, "presence_persons": ["person.kevin"]}
    assert is_presence_away(hass, {}, settings) is True


def test_device_tracker_home():
    """device_tracker.phone with state 'home' means not away."""
    hass = _make_hass()
    hass.states.get = MagicMock(return_value=_make_state("device_tracker.phone", "home"))
    settings = {"presence_enabled": True, "presence_persons": ["device_tracker.phone"]}
    assert is_presence_away(hass, {}, settings) is False


def test_device_tracker_away():
    """device_tracker.phone with state 'not_home' means away."""
    hass = _make_hass()
    hass.states.get = MagicMock(return_value=_make_state("device_tracker.phone", "not_home"))
    settings = {"presence_enabled": True, "presence_persons": ["device_tracker.phone"]}
    assert is_presence_away(hass, {}, settings) is True


def test_input_boolean_on_is_home():
    """input_boolean.guest with state 'on' means home (not away)."""
    hass = _make_hass()
    hass.states.get = MagicMock(return_value=_make_state("input_boolean.guest", "on"))
    settings = {"presence_enabled": True, "presence_persons": ["input_boolean.guest"]}
    assert is_presence_away(hass, {}, settings) is False


def test_input_boolean_off_is_away():
    """input_boolean.guest with state 'off' means away."""
    hass = _make_hass()
    hass.states.get = MagicMock(return_value=_make_state("input_boolean.guest", "off"))
    settings = {"presence_enabled": True, "presence_persons": ["input_boolean.guest"]}
    assert is_presence_away(hass, {}, settings) is True


def test_multiple_persons_one_home():
    """Two persons, one home one away. Someone is home so not away."""
    hass = _make_hass()
    states = {
        "person.kevin": _make_state("person.kevin", "home"),
        "person.lisa": _make_state("person.lisa", "not_home"),
    }
    hass.states.get = MagicMock(side_effect=states.get)
    settings = {"presence_enabled": True, "presence_persons": ["person.kevin", "person.lisa"]}
    assert is_presence_away(hass, {}, settings) is False


def test_multiple_persons_all_away():
    """Two persons, both away. Everyone is away."""
    hass = _make_hass()
    states = {
        "person.kevin": _make_state("person.kevin", "not_home"),
        "person.lisa": _make_state("person.lisa", "not_home"),
    }
    hass.states.get = MagicMock(side_effect=states.get)
    settings = {"presence_enabled": True, "presence_persons": ["person.kevin", "person.lisa"]}
    assert is_presence_away(hass, {}, settings) is True


def test_person_unavailable_treated_as_home():
    """Unavailable state is fail-safe treated as home (returns False)."""
    hass = _make_hass()
    hass.states.get = MagicMock(return_value=_make_state("person.kevin", "unavailable"))
    settings = {"presence_enabled": True, "presence_persons": ["person.kevin"]}
    assert is_presence_away(hass, {}, settings) is False


def test_person_unknown_treated_as_home():
    """Unknown state is fail-safe treated as home (returns False)."""
    hass = _make_hass()
    hass.states.get = MagicMock(return_value=_make_state("person.kevin", "unknown"))
    settings = {"presence_enabled": True, "presence_persons": ["person.kevin"]}
    assert is_presence_away(hass, {}, settings) is False


def test_person_entity_missing_treated_as_home(monkeypatch):
    """A registered entity without a state is fail-safe treated as home."""
    hass = _make_hass()
    hass.states.get = MagicMock(return_value=None)
    _patch_registry(monkeypatch, {"person.kevin": _registry_entry()})
    settings = {"presence_enabled": True, "presence_persons": ["person.kevin"]}
    assert is_presence_away(hass, {}, settings) is False


def test_room_persons_override_global():
    """Per-room presence_persons take precedence over global."""
    hass = _make_hass()
    states = {
        "person.kevin": _make_state("person.kevin", "home"),
        "person.lisa": _make_state("person.lisa", "not_home"),
    }
    hass.states.get = MagicMock(side_effect=states.get)
    settings = {"presence_enabled": True, "presence_persons": ["person.kevin"]}
    room = {"presence_persons": ["person.lisa"]}
    # Room overrides global. Only lisa checked, she is away.
    assert is_presence_away(hass, room, settings) is True


def test_room_persons_empty_falls_back_to_global():
    """Empty room presence_persons falls back to global."""
    hass = _make_hass()
    hass.states.get = MagicMock(return_value=_make_state("person.kevin", "not_home"))
    settings = {"presence_enabled": True, "presence_persons": ["person.kevin"]}
    room = {"presence_persons": []}
    assert is_presence_away(hass, room, settings) is True


def test_presence_enabled_missing_defaults_false():
    """When presence_enabled key is missing from settings, defaults to False."""
    hass = _make_hass()
    settings = {"presence_persons": ["person.kevin"]}
    assert is_presence_away(hass, {}, settings) is False


def test_deleted_entity_does_not_block_remaining_persons(monkeypatch):
    """A deleted entity is skipped; the surviving person decides (#397)."""
    hass = _make_hass()
    states = {"person.kevin": _make_state("person.kevin", "not_home")}
    hass.states.get = MagicMock(side_effect=states.get)
    _patch_registry(monkeypatch, {"person.kevin": _registry_entry()})
    settings = {"presence_enabled": True, "presence_persons": ["person.kevin"]}
    room = {"presence_persons": ["device_tracker.gone", "person.kevin"]}
    assert is_presence_away(hass, room, settings) is True


def test_deleted_entity_skipped_but_home_person_still_wins(monkeypatch):
    """Skipping a deleted entity must not make a present person invisible."""
    hass = _make_hass()
    states = {"person.kevin": _make_state("person.kevin", "home")}
    hass.states.get = MagicMock(side_effect=states.get)
    _patch_registry(monkeypatch, {"person.kevin": _registry_entry()})
    settings = {"presence_enabled": True, "presence_persons": ["person.kevin"]}
    room = {"presence_persons": ["device_tracker.gone", "person.kevin"]}
    assert is_presence_away(hass, room, settings) is False


def test_all_entities_deleted_stays_fail_safe(monkeypatch):
    """With no evaluable entity left there is no information → treat as home."""
    hass = _make_hass()
    hass.states.get = MagicMock(return_value=None)
    _patch_registry(monkeypatch, {})
    settings = {"presence_enabled": True, "presence_persons": ["device_tracker.gone"]}
    assert is_presence_away(hass, {}, settings) is False


def test_registered_entity_without_state_stays_fail_safe(monkeypatch):
    """An entity that is registered but not yet in the state machine (startup)."""
    hass = _make_hass()
    states = {"person.kevin": _make_state("person.kevin", "not_home")}
    hass.states.get = MagicMock(side_effect=states.get)
    _patch_registry(
        monkeypatch,
        {"person.kevin": _registry_entry(), "device_tracker.booting": _registry_entry()},
    )
    settings = {"presence_enabled": True, "presence_persons": ["person.kevin"]}
    room = {"presence_persons": ["person.kevin", "device_tracker.booting"]}
    assert is_presence_away(hass, room, settings) is False


def test_disabled_entity_is_treated_as_gone(monkeypatch):
    """A disabled entity never gets a state, so it must not block the room."""
    hass = _make_hass()
    states = {"person.kevin": _make_state("person.kevin", "not_home")}
    hass.states.get = MagicMock(side_effect=states.get)
    _patch_registry(
        monkeypatch,
        {
            "person.kevin": _registry_entry(),
            "device_tracker.disabled": _registry_entry(disabled_by="user"),
        },
    )
    settings = {"presence_enabled": True, "presence_persons": ["person.kevin"]}
    room = {"presence_persons": ["device_tracker.disabled", "person.kevin"]}
    assert is_presence_away(hass, room, settings) is True


def test_unregistered_entity_during_startup_stays_fail_safe(monkeypatch):
    """Entities without a unique_id never get a registry entry, so before HA has
    started a live one must not be mistaken for a deleted one."""
    hass = _make_hass()
    hass.is_running = False
    states = {"person.kevin": _make_state("person.kevin", "not_home")}
    hass.states.get = MagicMock(side_effect=states.get)
    _patch_registry(monkeypatch, {})
    settings = {"presence_enabled": True, "presence_persons": ["person.kevin"]}
    room = {"presence_persons": ["binary_sensor.yaml_template", "person.kevin"]}
    assert is_presence_away(hass, room, settings) is False


def test_deleted_entity_at_end_of_list_is_skipped(monkeypatch):
    """The skip must work regardless of position, not just as a short-circuit."""
    hass = _make_hass()
    states = {"person.kevin": _make_state("person.kevin", "not_home")}
    hass.states.get = MagicMock(side_effect=states.get)
    _patch_registry(monkeypatch, {"person.kevin": _registry_entry()})
    settings = {"presence_enabled": True, "presence_persons": ["person.kevin"]}
    room = {"presence_persons": ["person.kevin", "device_tracker.gone"]}
    assert is_presence_away(hass, room, settings) is True


def test_disabled_entity_as_sole_entry_stays_fail_safe(monkeypatch):
    """A single disabled entity leaves nothing to evaluate."""
    hass = _make_hass()
    hass.states.get = MagicMock(return_value=None)
    _patch_registry(monkeypatch, {"device_tracker.disabled": _registry_entry(disabled_by="user")})
    settings = {"presence_enabled": True, "presence_persons": ["device_tracker.disabled"]}
    assert is_presence_away(hass, {}, settings) is False


def test_unavailable_entity_still_wins_over_a_deleted_one(monkeypatch):
    """Skipping a deleted entity must not skip the fail-safe for an unavailable one."""
    hass = _make_hass()
    states = {"person.kevin": _make_state("person.kevin", "unavailable")}
    hass.states.get = MagicMock(side_effect=states.get)
    _patch_registry(monkeypatch, {"person.kevin": _registry_entry()})
    settings = {"presence_enabled": True, "presence_persons": ["person.kevin"]}
    room = {"presence_persons": ["device_tracker.gone", "person.kevin"]}
    assert is_presence_away(hass, room, settings) is False


@pytest.mark.parametrize(
    ("states", "expected"),
    [
        ({"person.anna": "home", "person.ben": "unavailable"}, "home"),
        ({"person.anna": "unavailable", "person.ben": "home"}, "home"),
        ({"person.anna": "not_home", "person.ben": "unknown"}, "unknown"),
        ({"person.anna": "not_home", "person.ben": "not_home"}, "away"),
    ],
)
def test_presence_state_tells_home_away_and_unknown(states, expected):
    """A tracker outage is unknown, not home: it must not arm presence_ends_override."""
    hass = _make_hass()
    hass.states.get = MagicMock(side_effect=lambda eid: _make_state(eid, states[eid]))
    settings = {"presence_enabled": True, "presence_persons": list(states)}
    assert presence_state(hass, {}, settings) == expected


def test_presence_state_unknown_without_presence_detection():
    hass = _make_hass()
    assert presence_state(hass, {}, {"presence_enabled": False, "presence_persons": ["person.anna"]}) == "unknown"
    assert presence_state(hass, {}, {"presence_enabled": True, "presence_persons": []}) == "unknown"


def test_presence_state_unknown_while_an_entity_has_no_state_yet(monkeypatch):
    hass = _make_hass()
    hass.is_running = False
    hass.states.get = MagicMock(return_value=None)
    assert presence_state(hass, {}, {"presence_enabled": True, "presence_persons": ["person.anna"]}) == "unknown"
