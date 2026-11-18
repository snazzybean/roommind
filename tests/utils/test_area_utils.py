"""Tests for utils/area_utils.py helpers without a coordinator."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from custom_components.roommind.utils.area_utils import ha_floor_order

FLOOR_REGISTRY = "custom_components.roommind.utils.area_utils.fr.async_get"


def test_floor_order_follows_the_registry(hass):
    registry = MagicMock()
    registry.async_list_floors.return_value = [
        SimpleNamespace(floor_id="attic"),
        SimpleNamespace(floor_id="ground"),
        SimpleNamespace(floor_id="basement"),
    ]
    with patch(FLOOR_REGISTRY, return_value=registry):
        assert ha_floor_order(hass) == ["attic", "ground", "basement"]


def test_floor_order_is_empty_without_a_registry(hass):
    with patch(FLOOR_REGISTRY, side_effect=KeyError("floor_registry")):
        assert ha_floor_order(hass) == []
