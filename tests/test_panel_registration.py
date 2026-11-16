"""Sidebar panel registration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.roommind import _async_register_panel
from custom_components.roommind.const import DOMAIN, VERSION

pytestmark = pytest.mark.asyncio


async def test_the_panel_is_for_admins_only(hass):
    """The panel edits the whole setup; non-admins keep the dashboard card and the room entities."""
    hass.data[DOMAIN] = {}
    hass.http.async_register_static_paths = AsyncMock()
    with (
        patch.object(Path, "exists", return_value=True),
        patch("custom_components.roommind.async_register_built_in_panel") as register,
    ):
        await _async_register_panel(hass)

    register.assert_called_once()
    assert register.call_args.kwargs["require_admin"] is True
    assert register.call_args.kwargs["frontend_url_path"] == "roommind"


async def test_the_panel_url_carries_the_version(hass):
    """A cached panel of the previous release must not be reused after an update."""
    hass.data[DOMAIN] = {}
    hass.http.async_register_static_paths = AsyncMock()
    with (
        patch.object(Path, "exists", return_value=True),
        patch("custom_components.roommind.async_register_built_in_panel") as register,
    ):
        await _async_register_panel(hass)

    (config,) = hass.http.async_register_static_paths.await_args.args[0]
    js_url = register.call_args.kwargs["config"]["_panel_custom"]["js_url"]
    assert js_url == f"{config.url_path}?v={VERSION}"
