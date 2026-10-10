"""Write a Home Assistant config directory for a simulation instance."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import yaml

from .scenario import Scenario, ScenarioError

# Explicit list instead of default_config: no discovery (zeroconf/ssdp/dhcp/bluetooth),
# no cloud, nothing that could find or talk to real devices on the LAN.
COMPONENTS = ["frontend", "config", "api", "sun", "system_log", "diagnostics", "simhome"]

DAY_GROUPS = {
    "daily": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
    "weekdays": ["monday", "tuesday", "wednesday", "thursday", "friday"],
    "weekend": ["saturday", "sunday"],
}
DAYS = DAY_GROUPS["daily"]
_BLOCK_RE = re.compile(r"^(\d{1,2}:\d{2})-(\d{1,2}:\d{2})(?:@(.+))?$")


def write_ha_config(
    config_dir: Path,
    scenario: Scenario,
    *,
    instance: str,
    port: int,
    roommind_src: Path,
    simhome_src: Path,
    trusted_cidrs: list[str],
    recorder: bool = False,
    log_level: str = "warning",
) -> None:
    """Create/refresh ``config_dir``. Existing ``.storage`` content (state) is kept."""
    config_dir.mkdir(parents=True, exist_ok=True)
    storage = config_dir / ".storage"
    storage.mkdir(exist_ok=True)
    (config_dir / "configuration.yaml").write_text(
        yaml.safe_dump(build_configuration(scenario, instance, trusted_cidrs, recorder, log_level), sort_keys=False)
    )
    _write_storage(storage / "http", "http", 2, 2, _http_data(port))
    if not (storage / "onboarding").exists():
        _write_storage(
            storage / "onboarding",
            "onboarding",
            4,
            1,
            {"done": ["user", "core_config", "analytics", "integration"]},
        )
    cc = config_dir / "custom_components"
    cc.mkdir(exist_ok=True)
    _symlink(cc / "roommind", roommind_src)
    _symlink(cc / "simhome", simhome_src)


def build_configuration(
    scenario: Scenario, instance: str, trusted_cidrs: list[str], recorder: bool, log_level: str
) -> dict[str, Any]:
    loc = scenario.location
    conf: dict[str, Any] = {
        "homeassistant": {
            "name": f"RoomMind Sim ({instance})",
            "latitude": loc.latitude,
            "longitude": loc.longitude,
            "elevation": loc.elevation,
            "unit_system": loc.unit_system,
            "time_zone": loc.time_zone,
            "country": loc.country,
            "currency": "EUR",
            "auth_providers": [
                {
                    "type": "trusted_networks",
                    "trusted_networks": trusted_cidrs,
                    "allow_bypass_login": True,
                },
                {"type": "homeassistant"},
            ],
        },
    }
    for comp in COMPONENTS:
        conf[comp] = {}
    if recorder:
        conf["recorder"] = {"purge_keep_days": 3, "commit_interval": 30}
        conf["history"] = {}
        conf["logbook"] = {}
    if scenario.people:
        conf["person"] = [{"id": p.id, "name": p.id, "device_trackers": [p.tracker]} for p in scenario.people]
    helpers = scenario.helpers
    if helpers.get("schedule"):
        conf["schedule"] = {
            _object_id(key, "schedule"): build_schedule(key, spec) for key, spec in helpers["schedule"].items()
        }
    for domain in ("input_boolean", "input_number", "input_select"):
        if helpers.get(domain):
            conf[domain] = {_object_id(k, domain): (v or {}) for k, v in helpers[domain].items()}
    conf["logger"] = {
        "default": log_level,
        "logs": {
            "custom_components.roommind": "info",
            "custom_components.simhome": "info",
            # Every integration without a unique version nags once per start.
            "homeassistant.loader": "error",
            "homeassistant.components.camera.img_util": "critical",
            "aiohttp_fast_zlib": "error",
        },
    }
    return conf


def build_schedule(key: str, spec: dict[str, Any]) -> dict[str, Any]:
    """Expand ``weekdays``/``weekend``/``daily`` shorthand and ``"06:00-22:00@21.5"`` blocks."""
    where = f"helpers.schedule.{key}"
    out: dict[str, Any] = {"name": spec.get("name", _object_id(key, "schedule").replace("_", " ").title())}
    days: dict[str, list[dict[str, Any]]] = {}
    for group, value in spec.items():
        if group in ("name", "icon"):
            if group == "icon":
                out["icon"] = value
            continue
        targets = DAY_GROUPS.get(group, [group] if group in DAYS else None)
        if targets is None:
            raise ScenarioError(f"unknown day key {group!r}", where)
        blocks = [_block(b, f"{where}.{group}") for b in value or []]
        for day in targets:
            days[day] = blocks
    for day in DAYS:
        if day in days:
            out[day] = days[day]
    return out


def _block(value: str | dict[str, Any], where: str) -> dict[str, Any]:
    if isinstance(value, dict):
        block = {"from": _hms(str(value["from"])), "to": _hms(str(value["to"]))}
        data = {k: v for k, v in value.items() if k not in ("from", "to")}
        data = data.pop("data", data) if "data" in data else data
        if data:
            block["data"] = data
        return block
    match = _BLOCK_RE.match(str(value).replace(" ", ""))
    if not match:
        raise ScenarioError(f"invalid block {value!r} (use 06:00-22:00 or 06:00-22:00@21.5)", where)
    block = {"from": _hms(match.group(1)), "to": _hms(match.group(2))}
    if match.group(3):
        temp = match.group(3)
        if "/" in temp:
            heat, cool = temp.split("/", 1)
            block["data"] = {"heat_temperature": float(heat), "cool_temperature": float(cool)}
        else:
            block["data"] = {"temperature": float(temp)}
    return block


def _hms(value: str) -> str:
    parts = value.split(":")
    return ":".join(p.zfill(2) for p in (parts + ["00"] * (3 - len(parts)))[:3])


def _object_id(key: str, domain: str) -> str:
    return key.split(".", 1)[1] if key.startswith(f"{domain}.") else key


def _http_data(port: int) -> dict[str, Any]:
    stable = {
        "server_port": port,
        "cors_allowed_origins": ["https://cast.home-assistant.io"],
        "login_attempts_threshold": -1,
        "ip_ban_enabled": False,
        "ssl_profile": "modern",
        "use_x_frame_options": True,
        "created_at": "2026-01-01T00:00:00+00:00",
        "error": None,
        "error_message": None,
    }
    # HA 2026.10 migrates YAML http config to a "pending" slot and restarts after 5 min
    # without confirmation, so the port lives in the stable slot and YAML has no http:.
    return {"stable": stable, "pending": None, "yaml_migration_done": True}


def _write_storage(path: Path, key: str, version: int, minor: int, data: dict[str, Any]) -> None:
    payload = {"version": version, "minor_version": minor, "key": key, "data": data}
    path.write_text(json.dumps(payload, indent=2))


def _symlink(link: Path, target: Path) -> None:
    if link.is_symlink() or link.exists():
        if link.is_symlink() and Path(os.readlink(link)) == target:
            return
        link.unlink()
    link.symlink_to(target, target_is_directory=True)
