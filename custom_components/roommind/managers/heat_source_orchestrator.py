"""Heat source orchestrator for rooms with multiple heating device types.

When a room has both thermostats (e.g. radiator TRVs connected to a gas boiler)
and ACs with heating capability (heat pumps), this module decides which devices
to activate based on temperature gap (delta-T) and outdoor temperature.

Roles are fixed: thermostats are always primary, ACs are always secondary.

The orchestrator sits between the MPC optimizer output (abstract mode + power_fraction)
and the device command layer (async_apply). It does NOT modify the thermal model or
optimizer. It only filters and distributes the power decision across devices.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.core import HomeAssistant

from ..const import (
    DEFAULT_HEAT_SOURCE_AC_MIN_OUTDOOR,
    DEFAULT_HEAT_SOURCE_OUTDOOR_THRESHOLD,
    DEFAULT_HEAT_SOURCE_PRIMARY_DELTA,
    HEAT_SOURCE_HYSTERESIS,
    HEAT_SOURCE_LARGE_GAP_MULTIPLIER,
    HEAT_SOURCE_SECONDARY_POWER_SCALE,
    MODE_HEATING,
)
from ..utils.device_utils import get_ac_eids, get_trv_eids

_LOGGER = logging.getLogger(__name__)


@dataclass
class DeviceCommand:
    """Command for a single climate device within a heat source plan."""

    entity_id: str
    role: str  # "primary" | "secondary"
    device_type: str  # "thermostat" | "ac"
    active: bool
    power_fraction: float  # 0.0-1.0
    reason: str


@dataclass
class HeatSourcePlan:
    """Orchestration plan describing which heating devices to activate."""

    commands: list[DeviceCommand]
    active_sources: str  # "primary" | "secondary" | "both" | "none"
    reason: str


def _is_available(hass: HomeAssistant, entity_id: str) -> bool:
    """Check if an entity is available (not unavailable/unknown)."""
    state = hass.states.get(entity_id)
    if state is None:
        return False
    return state.state not in ("unavailable", "unknown")


def _ac_can_heat(hass: HomeAssistant, entity_id: str) -> bool:
    """Check if a single AC entity supports heating and is available."""
    state = hass.states.get(entity_id)
    if state is None:
        return False
    if state.state in ("unavailable", "unknown"):
        return False
    modes = state.attributes.get("hvac_modes", [])
    return "heat" in modes or "heat_cool" in modes or "auto" in modes


def evaluate_heat_sources(
    room_config: dict,
    mode: str,
    power_fraction: float,
    current_temp: float | None,
    target_temp: float | None,
    outdoor_temp: float | None,
    previous_active_sources: str,
    hass: HomeAssistant,
) -> HeatSourcePlan | None:
    """Evaluate which heating devices to activate.

    Returns a HeatSourcePlan for MODE_HEATING, or None if orchestration
    should not apply (wrong mode, disabled, or missing data).
    """
    if mode != MODE_HEATING:
        return None

    if not room_config.get("heat_source_orchestration", False):
        return None

    thermostats = get_trv_eids(room_config.get("devices", []))
    acs = get_ac_eids(room_config.get("devices", []))
    if not thermostats or not acs:
        return None

    if current_temp is None or target_temp is None:
        return None

    primary_delta = room_config.get("heat_source_primary_delta", DEFAULT_HEAT_SOURCE_PRIMARY_DELTA)
    outdoor_threshold = room_config.get("heat_source_outdoor_threshold", DEFAULT_HEAT_SOURCE_OUTDOOR_THRESHOLD)
    ac_min_outdoor = room_config.get("heat_source_ac_min_outdoor", DEFAULT_HEAT_SOURCE_AC_MIN_OUTDOOR)

    delta_t = target_temp - current_temp

    # Fixed roles: thermostats = primary, ACs = secondary
    primary_devices: list[tuple[str, str]] = [(eid, "thermostat") for eid in thermostats]
    secondary_devices: list[tuple[str, str]] = [(eid, "ac") for eid in acs]

    # Early exit: at or above target, no heating needed
    if delta_t <= 0:
        idle_cmds: list[DeviceCommand] = []
        for eid, device_type in primary_devices:
            idle_cmds.append(
                DeviceCommand(
                    entity_id=eid,
                    role="primary",
                    device_type=device_type,
                    active=False,
                    power_fraction=0.0,
                    reason="not selected",
                )
            )
        for eid, device_type in secondary_devices:
            idle_cmds.append(
                DeviceCommand(
                    entity_id=eid,
                    role="secondary",
                    device_type=device_type,
                    active=False,
                    power_fraction=0.0,
                    reason="not selected",
                )
            )
        _LOGGER.debug(
            "Room '%s': heat source orchestration → none (delta_t=%.1f, outdoor=%s)",
            room_config.get("area_id", "?"),
            delta_t,
            outdoor_temp,
        )
        return HeatSourcePlan(commands=idle_cmds, active_sources="none", reason="delta_t <= 0")

    # Hardware protection: disable AC heating in extreme cold
    ac_disabled = outdoor_temp is not None and outdoor_temp < ac_min_outdoor
    if ac_disabled:
        # Remove ACs from both lists, they cannot heat
        primary_devices = [(eid, dt) for eid, dt in primary_devices if dt != "ac"]
        secondary_devices = [(eid, dt) for eid, dt in secondary_devices if dt != "ac"]

    # Filter ACs that don't support heating or are unavailable
    primary_devices = [(eid, dt) for eid, dt in primary_devices if dt != "ac" or _ac_can_heat(hass, eid)]
    secondary_devices = [(eid, dt) for eid, dt in secondary_devices if dt != "ac" or _ac_can_heat(hass, eid)]

    # Filter unavailable thermostats
    primary_devices = [(eid, dt) for eid, dt in primary_devices if dt != "thermostat" or _is_available(hass, eid)]
    secondary_devices = [(eid, dt) for eid, dt in secondary_devices if dt != "thermostat" or _is_available(hass, eid)]

    # Determine which source group to activate
    large_gap_threshold = primary_delta * HEAT_SOURCE_LARGE_GAP_MULTIPLIER

    # Weather-based preference with hysteresis (None when no outdoor data available)
    prefer_ac: bool | None
    if outdoor_temp is not None:
        if previous_active_sources == "secondary":
            # AC was active: keep unless outdoor drops below threshold - hysteresis
            prefer_ac = outdoor_temp > outdoor_threshold - HEAT_SOURCE_HYSTERESIS
        elif previous_active_sources == "primary":
            # Boiler was active: keep unless outdoor rises above threshold + hysteresis
            prefer_ac = outdoor_temp > outdoor_threshold + HEAT_SOURCE_HYSTERESIS
        else:
            prefer_ac = outdoor_temp > outdoor_threshold
    else:
        prefer_ac = None

    # "both" when gap is large, or hysteresis holds "both" state
    if delta_t >= large_gap_threshold + HEAT_SOURCE_HYSTERESIS:
        active = "both"
    elif previous_active_sources == "both" and delta_t > primary_delta - HEAT_SOURCE_HYSTERESIS:
        active = "both"
    elif prefer_ac is True:
        active = "secondary"
    elif prefer_ac is False:
        active = "primary"
    else:
        # No outdoor data: delta-T heuristic (backward compatible)
        active = "primary" if delta_t >= primary_delta + HEAT_SOURCE_HYSTERESIS else "secondary"

    # Edge case: if chosen group has no devices, fall back
    if active == "secondary" and not secondary_devices:
        active = "primary"
    if active == "primary" and not primary_devices:
        active = "secondary"
    if active == "both" and not primary_devices:
        active = "secondary"
    if active == "both" and not secondary_devices:
        active = "primary"
    if not primary_devices and not secondary_devices:
        active = "none"

    # Build device commands
    commands: list[DeviceCommand] = []
    reason_parts: list[str] = []

    if ac_disabled and active != "none":
        reason_parts.append(f"AC disabled (outdoor {outdoor_temp}°C < {ac_min_outdoor}°C)")

    if active == "both":
        reason_parts.append(f"large gap ({delta_t:.1f}°C)")
    elif active == "primary":
        outdoor_str = f"{outdoor_temp}°C" if outdoor_temp is not None else "n/a"
        reason_parts.append(f"boiler preferred ({delta_t:.1f}°C gap, outdoor {outdoor_str})")
    elif active == "secondary":
        outdoor_str = f"{outdoor_temp}°C" if outdoor_temp is not None else "n/a"
        reason_parts.append(f"AC preferred ({delta_t:.1f}°C gap, outdoor {outdoor_str})")

    for eid, device_type in primary_devices:
        is_active = active in ("primary", "both")
        pf = power_fraction if is_active else 0.0
        commands.append(
            DeviceCommand(
                entity_id=eid,
                role="primary",
                device_type=device_type,
                active=is_active,
                power_fraction=pf,
                reason="active" if is_active else "not selected",
            )
        )

    for eid, device_type in secondary_devices:
        is_active = active in ("secondary", "both")
        pf = power_fraction
        if active == "both":
            pf = round(power_fraction * HEAT_SOURCE_SECONDARY_POWER_SCALE, 2)
        if not is_active:
            pf = 0.0
        commands.append(
            DeviceCommand(
                entity_id=eid,
                role="secondary",
                device_type=device_type,
                active=is_active,
                power_fraction=pf,
                reason="active" if is_active else "not selected",
            )
        )

    reason = "; ".join(reason_parts) if reason_parts else active

    _LOGGER.debug(
        "Room '%s': heat source orchestration → %s (delta_t=%.1f, outdoor=%s)",
        room_config.get("area_id", "?"),
        active,
        delta_t,
        outdoor_temp,
    )

    return HeatSourcePlan(commands=commands, active_sources=active, reason=reason)
