"""Dashboard card registration (#346)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.roommind import CARD_URL, _async_register_card
from custom_components.roommind.const import DOMAIN, VERSION

pytestmark = pytest.mark.asyncio


@pytest.fixture
def card_hass(hass):
    hass.data[DOMAIN] = {}
    hass.http.async_register_static_paths = AsyncMock()
    return hass


async def test_the_card_loads_on_every_page_with_a_version_query(card_hass):
    with (
        patch.object(Path, "exists", return_value=True),
        patch("custom_components.roommind.add_extra_js_url") as add_url,
    ):
        await _async_register_card(card_hass)

    card_hass.http.async_register_static_paths.assert_awaited_once()
    (config,) = card_hass.http.async_register_static_paths.await_args.args[0]
    assert config.url_path == CARD_URL
    add_url.assert_called_once_with(card_hass, f"{CARD_URL}?v={VERSION}")


async def test_a_reload_registers_the_card_only_once(card_hass):
    with (
        patch.object(Path, "exists", return_value=True),
        patch("custom_components.roommind.add_extra_js_url") as add_url,
    ):
        await _async_register_card(card_hass)
        await _async_register_card(card_hass)

    assert add_url.call_count == 1
    card_hass.http.async_register_static_paths.assert_awaited_once()


async def test_an_already_served_path_still_adds_the_card(card_hass):
    card_hass.http.async_register_static_paths.side_effect = RuntimeError("already registered")
    with (
        patch.object(Path, "exists", return_value=True),
        patch("custom_components.roommind.add_extra_js_url") as add_url,
    ):
        await _async_register_card(card_hass)

    add_url.assert_called_once()


async def test_without_a_built_card_nothing_is_registered(card_hass):
    with (
        patch.object(Path, "exists", return_value=False),
        patch("custom_components.roommind.add_extra_js_url") as add_url,
    ):
        await _async_register_card(card_hass)

    add_url.assert_not_called()
    card_hass.http.async_register_static_paths.assert_not_awaited()
    assert "card_registered" not in card_hass.data[DOMAIN]
