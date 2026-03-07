"""Tests for presence_utils.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.roommind.utils.presence_utils import is_presence_away


def _make_state(entity_id: str, state: str) -> MagicMock:
    s = MagicMock()
    s.entity_id = entity_id
    s.state = state
    return s


def test_presence_enabled_but_no_persons_returns_false():
    """When presence_enabled but presence_persons is empty, return False."""
    hass = MagicMock()
    settings = {"presence_enabled": True, "presence_persons": []}
    assert is_presence_away(hass, {}, settings) is False


def test_binary_sensor_off_counts_as_away():
    """binary_sensor 'off' means not home → if all away, returns True."""
    hass = MagicMock()
    hass.states.get = MagicMock(
        return_value=_make_state("binary_sensor.motion", "off")
    )
    settings = {"presence_enabled": True, "presence_persons": ["binary_sensor.motion"]}
    assert is_presence_away(hass, {}, settings) is True


def test_binary_sensor_on_counts_as_home():
    """binary_sensor 'on' means home → returns False."""
    hass = MagicMock()
    hass.states.get = MagicMock(
        return_value=_make_state("binary_sensor.motion", "on")
    )
    settings = {"presence_enabled": True, "presence_persons": ["binary_sensor.motion"]}
    assert is_presence_away(hass, {}, settings) is False
