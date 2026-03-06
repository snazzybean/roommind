"""RoomMind – Holistic room climate management for Home Assistant."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from homeassistant.components.frontend import (
    async_register_built_in_panel,
    async_remove_panel,
)
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, issue_registry as ir
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, PLATFORMS, VERSION
from .coordinator import RoomMindCoordinator
from .store import RoomMindStore
from .websocket_api import async_register_websocket_commands

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the RoomMind integration (YAML, runs once)."""
    hass.data.setdefault(DOMAIN, {})
    async_register_websocket_commands(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up RoomMind from a config entry."""
    # Ensure the store is created and loaded (once across all entries)
    store = hass.data[DOMAIN].get("store")
    if not store:
        await _async_migrate_storage(hass)
        store = RoomMindStore(hass)
        await store.async_load()
        hass.data[DOMAIN]["store"] = store

    coordinator = RoomMindCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator
    hass.data[DOMAIN]["coordinator"] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await _async_register_panel(hass)
    await _async_check_version_mismatch(hass)

    return True


async def _async_migrate_storage(hass: HomeAssistant) -> None:
    """Migrate storage from old 'roomsense' name if present."""
    storage_dir = Path(hass.config.path(".storage"))
    await hass.async_add_executor_job(_migrate_storage_sync, storage_dir)


def _migrate_storage_sync(storage_dir: Path) -> None:
    """Blocking portion of storage migration — must run in an executor."""
    # Rename main storage file
    old_path = storage_dir / "roomsense"
    new_path = storage_dir / "roommind"
    if old_path.exists() and not new_path.exists():
        old_path.rename(new_path)
        _LOGGER.info("Migrated storage file from 'roomsense' to 'roommind'")
    # Update the internal storage key so HA's Store recognises the data
    if new_path.exists():
        try:
            data = json.loads(new_path.read_text())
            if data.get("key") == "roomsense":
                data["key"] = "roommind"
                new_path.write_text(json.dumps(data, indent=2))
                _LOGGER.info("Migrated storage key from 'roomsense' to 'roommind'")
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Failed to migrate storage key")
    # Migrate history CSV directory
    import shutil

    old_history = storage_dir / "roomsense_history"
    new_history = storage_dir / "roommind_history"
    if old_history.exists():
        if not new_history.exists():
            old_history.rename(new_history)
            _LOGGER.info("Migrated history directory to 'roommind_history'")
        else:
            # Both exist — merge old CSVs into new (append old data before new)
            for old_csv in old_history.iterdir():
                new_csv = new_history / old_csv.name
                if new_csv.exists():
                    old_lines = old_csv.read_text().splitlines()
                    new_lines = new_csv.read_text().splitlines()
                    # old_lines[0] is header, old_lines[1:] is data
                    # new_lines[0] is header, new_lines[1:] is new data
                    merged = old_lines + new_lines[1:]
                    new_csv.write_text("\n".join(merged) + "\n")
                else:
                    old_csv.rename(new_csv)
            shutil.rmtree(old_history)
            _LOGGER.info("Merged old history into 'roommind_history'")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a RoomMind config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        hass.data[DOMAIN].pop("coordinator", None)

    # Remove panel if no entries remain
    if not hass.data[DOMAIN]:
        async_remove_panel(hass, "roommind")

    return unload_ok


async def _async_check_version_mismatch(hass: HomeAssistant) -> None:
    """Compare in-memory VERSION (from boot) with manifest.json on disk."""
    manifest_path = Path(__file__).parent / "manifest.json"
    try:
        disk_version: str = (
            await hass.async_add_executor_job(
                lambda: json.loads(manifest_path.read_text())["version"]
            )
        )
    except Exception:  # noqa: BLE001
        return

    if disk_version != VERSION:
        ir.async_create_issue(
            hass,
            DOMAIN,
            "restart_required",
            is_fixable=True,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="restart_required",
            translation_placeholders={"version": disk_version},
        )
        _LOGGER.warning(
            "RoomMind on disk is %s but running %s – restart required",
            disk_version,
            VERSION,
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, "restart_required")


async def _async_register_panel(hass: HomeAssistant) -> None:
    """Register the RoomMind custom panel in the sidebar."""
    if hass.data[DOMAIN].get("panel_registered"):
        return

    panel_js = Path(__file__).parent / "frontend" / "roommind-panel.js"
    if not panel_js.exists():
        _LOGGER.warning(
            "RoomMind panel JS not found at %s – sidebar panel not registered",
            panel_js,
        )
        return

    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig("/roommind/roommind-panel.js", str(panel_js), False)]
        )
    except RuntimeError:
        _LOGGER.debug("RoomMind static path already registered")

    try:
        async_register_built_in_panel(
            hass,
            component_name="custom",
            sidebar_title="RoomMind",
            sidebar_icon="mdi:home-thermometer",
            frontend_url_path="roommind",
            config={
                "_panel_custom": {
                    "name": "roommind-panel",
                    "embed_iframe": False,
                    "trust_external": False,
                    "js_url": "/roommind/roommind-panel.js",
                }
            },
        )
    except ValueError:
        _LOGGER.debug("RoomMind panel already registered")

    hass.data[DOMAIN]["panel_registered"] = True
    _LOGGER.info("RoomMind panel registered in sidebar")
