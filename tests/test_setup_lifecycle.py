"""Component lifecycle tests: cold boot must always stash the store.

Regression guard for the 2.0.4-beta.2 defect: the store stash slid inside the
one-time "energy price replaced" repair-issue branch, so a fresh boot without
that flag left ``hass.data[DOMAIN]["store"]`` unset. The coordinator's hard
read during its first refresh (coordinator.py) then failed the whole config
entry with ``KeyError: 'store'`` — every integration test passed because none
booted ``async_setup_entry`` itself, they seeded ``hass.data`` by hand.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind import async_setup_entry
from custom_components.roommind.const import DOMAIN


def _mock_coordinator_class() -> MagicMock:
    """Coordinator class whose first refresh performs the real store read.

    ``RoomMindCoordinator._async_update_data`` dereferences
    ``hass.data[DOMAIN]["store"]`` during refresh; the mock mirrors that
    contract so a missing stash fails setup the same way production does.
    """
    coord_cls = MagicMock()
    coord = coord_cls.return_value

    async def _first_refresh(*args: object, **kwargs: object) -> None:
        raise NotImplementedError("configured per test")

    coord.async_config_entry_first_refresh = _first_refresh
    return coord_cls


def _wiring() -> dict[str, object]:
    """Patch the heavy side of setup; everything here except the stash logic."""
    return {
        "_async_migrate_storage": AsyncMock(),
        "RoomMindCoordinator": None,  # set by caller
        "_async_register_panel": AsyncMock(),
        "_async_register_card": AsyncMock(),
        "_async_check_version_mismatch": AsyncMock(),
        "async_schedule_deprecation_check": MagicMock(),
    }


@pytest.mark.asyncio
async def test_cold_setup_stashes_store_without_migration_flag(hass, mock_config_entry, store) -> None:
    """A fresh boot with no price-source migration must still expose the store."""
    hass.data[DOMAIN] = {}
    store.migrated_price_source = ""  # the ordinary case: nothing was superseded

    coord_cls = _mock_coordinator_class()
    read_ok = False

    async def _first_refresh(*args: object, **kwargs: object) -> None:
        nonlocal read_ok
        read_ok = hass.data[DOMAIN]["store"] is store  # hard read, like the real coordinator

    coord_cls.return_value.async_config_entry_first_refresh = _first_refresh

    wiring = _wiring()
    wiring["RoomMindCoordinator"] = coord_cls
    with (
        patch("custom_components.roommind.RoomMindStore", return_value=store),
        patch("custom_components.roommind.ir.async_create_issue") as create_issue,
        patch.multiple("custom_components.roommind", **{k: v for k, v in wiring.items() if v is not None}),
    ):
        result = await async_setup_entry(hass, mock_config_entry)

    assert result is True
    assert read_ok, "first refresh could not resolve the store"
    assert hass.data[DOMAIN]["store"] is store
    create_issue.assert_not_called()


@pytest.mark.asyncio
async def test_cold_setup_stashes_store_with_migration_flag(hass, mock_config_entry, store) -> None:
    """The one-time supersession notice also implies the store is stashed."""
    hass.data[DOMAIN] = {}
    store.migrated_price_source = "sensor.old_electricity_price"

    coord_cls = _mock_coordinator_class()

    async def _first_refresh(*args: object, **kwargs: object) -> None:
        assert hass.data[DOMAIN]["store"] is store

    coord_cls.return_value.async_config_entry_first_refresh = _first_refresh

    wiring = _wiring()
    wiring["RoomMindCoordinator"] = coord_cls
    with (
        patch("custom_components.roommind.RoomMindStore", return_value=store),
        patch("custom_components.roommind.ir.async_create_issue") as create_issue,
        patch.multiple("custom_components.roommind", **{k: v for k, v in wiring.items() if v is not None}),
    ):
        result = await async_setup_entry(hass, mock_config_entry)

    assert result is True
    assert hass.data[DOMAIN]["store"] is store
    assert create_issue.call_args[0][2] == "energy_price_replaced"


@pytest.mark.asyncio
async def test_second_entry_reuses_stored_store(hass, mock_config_entry, store) -> None:
    """Store is created once across all entries — a later boot must not rebuild it."""
    hass.data[DOMAIN] = {"store": store}

    coord_cls = _mock_coordinator_class()

    async def _first_refresh(*args: object, **kwargs: object) -> None:
        assert hass.data[DOMAIN]["store"] is store

    coord_cls.return_value.async_config_entry_first_refresh = _first_refresh

    wiring = _wiring()
    wiring["RoomMindCoordinator"] = coord_cls
    with (
        patch("custom_components.roommind.RoomMindStore") as store_cls,
        patch("custom_components.roommind.ir.async_create_issue"),
        patch.multiple("custom_components.roommind", **{k: v for k, v in wiring.items() if v is not None}),
    ):
        result = await async_setup_entry(hass, mock_config_entry)

    assert result is True
    store_cls.assert_not_called()
