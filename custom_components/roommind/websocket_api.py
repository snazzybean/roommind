"""WebSocket API for RoomMind room CRUD operations."""

from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import (
    CLIMATE_MODES,
    CONFLICT_RESOLUTIONS,
    CONTROL_MODE_BANGBANG,
    CONTROL_MODE_MPC,
    DEFAULT_COMPRESSOR_MIN_OFF_MINUTES,
    DEFAULT_COMPRESSOR_MIN_RUN_MINUTES,
    DEFAULT_CONFLICT_RESOLUTION,
    DEFAULT_CONTROL_MODE,
    DEFAULT_TOU_COOL_MAX,
    DEFAULT_TOU_COOL_MIN,
    DEFAULT_TOU_HEAT_MAX,
    DEFAULT_TOU_HEAT_MIN,
    DEFAULT_TOU_STORE_GAP,
    DEFAULT_TOU_SWING,
    DOMAIN,
    MAX_CO2_THRESHOLD,
    MAX_PRICE_SHIFT_K,
    MIN_CO2_THRESHOLD,
    MIN_OCCUPANCY_ECO_DELAY_MINUTES,
    OVERRIDE_CUSTOM,
    OVERRIDE_TYPES,
    TOU_EDGES,
    TOU_LOOKAHEADS,
    TOU_PHASES,
    TOU_ROW_ACTIONS,
    TOU_ROW_UNTILS,
    TOU_SCHEDULE_MINUTES_MAX,
    TOU_SCHEDULE_MINUTES_MIN,
    TOU_SCHEDULE_SHIFT_MAX,
    TOU_SCHEDULE_SHIFT_MIN,
    TOU_SCHEDULE_TEMP_MAX,
    TOU_SCHEDULE_TEMP_MIN,
    TOU_SHIFT_DIRECTIONS,
    TOU_SIDES,
    TOU_TIER_SOURCES,
    TOU_TIERS,
    TOU_UNTILS,
    TOU_VALUE_MODES,
    TOU_WEEKDAYS,
    VENTILATION_DOMAINS,
    build_override_live,
    is_override_suppressed,
)
from .control.direct_valve import async_release_valve
from .services.analytics_service import (
    _compute_target_forecast,  # noqa: F401 - re-exported for tests
    _csv_to_points,  # noqa: F401 - re-exported for tests
    _safe_float,  # noqa: F401 - re-exported for tests
    build_analytics_data,
)
from .utils.area_utils import REST_SWITCHED_OFF, rooms_with_area, rooms_without_area
from .utils.device_utils import (
    COIL_DRY_INHERIT,
    COIL_DRY_MODE_FAN_ONLY,
    COIL_DRY_MODES,
    COIL_DRY_ON,
    COIL_DRY_OVERRIDES,
    DEFAULT_COIL_DRY_DRAIN_MINUTES,
    DEFAULT_COIL_DRY_FAN_MODE,
    DEFAULT_COIL_DRY_MIN_COOLING_MINUTES,
    DEFAULT_COIL_DRY_MINUTES,
    SETPOINT_OFFSET_MAX,
    SETPOINT_OFFSET_MIN,
    VALVE_CLOSING_MODES,
    ValveEntities,
    get_valve_entities,
)
from .utils.schedule_utils import mask_override_band, next_schedule_change, override_preset_band

_LOGGER = logging.getLogger(__name__)


def _validate_device_idle_action(device: dict) -> dict:
    """Enforce type-specific idle_action constraints.

    idle_action="low" lowers the setpoint to min_temp while keeping the
    device in its active hvac_mode. For ACs this would cool continuously
    toward the minimum, which is never the intent. Restrict "low" to TRVs.
    """
    if device.get("type") == "ac" and device.get("idle_action") == "low":
        raise vol.Invalid("idle_action='low' is only supported for TRVs (type='trv')")
    return device


def _validate_device_coil_dry(device: dict) -> dict:
    """Enforce that coil dry is only enabled on ACs.

    A TRV has no evaporator coil, so "on" is meaningless there. "inherit" and
    "off" stay allowed for both types so a uniform device dict is always valid.
    """
    if device.get("type") == "trv" and device.get("coil_dry") == COIL_DRY_ON:
        raise vol.Invalid("coil_dry='on' is only supported for ACs (type='ac')")
    return device


def _number_entity_or_empty(value: object) -> str:
    """A ``number.*`` entity id, or "" for none."""
    if value is None or value == "":
        return ""
    if not isinstance(value, str) or not value.startswith("number."):
        raise vol.Invalid("must be a number entity")
    return value


def _validate_device_valve(device: dict) -> dict:
    """Direct valve control (#413) is for TRVs; it takes effect once both degree entities are set."""
    opening, closing = device.get("valve_opening_entity"), device.get("valve_closing_entity")
    if (opening or closing) and device.get("type") != "trv":
        raise vol.Invalid("direct valve control is only supported for TRVs (type='trv')")
    if device.get("valve_closing_entity") and device.get("valve_closing_entity") == device.get("valve_opening_entity"):
        raise vol.Invalid("valve_opening_entity and valve_closing_entity must differ")
    return device


if TYPE_CHECKING:
    from homeassistant.components.websocket_api import ActiveConnection

    from .coordinator import RoomMindCoordinator
    from .store import RoomMindStore


def _get_coordinator(hass: HomeAssistant) -> RoomMindCoordinator | None:
    """Return the RoomMindCoordinator from hass.data, or None."""
    coordinator: RoomMindCoordinator | None = hass.data.get(DOMAIN, {}).get("coordinator")
    return coordinator


_ROOM_SAVE_FIELDS = (
    "thermostats",
    "acs",
    "devices",
    "temperature_sensor",
    "humidity_sensor",
    "occupancy_sensors",
    "occupancy_eco_enabled",
    "occupancy_eco_delay",
    "preheat_enabled",
    "price_shift",
    "tou_store_enabled",
    "tou_heat_min",
    "tou_heat_max",
    "tou_cool_min",
    "tou_cool_max",
    "tou_swing",
    "tou_store_gap",
    "tou_overrides",
    "tou_schedule_enabled",
    "follow_device_setpoint",
    "climate_mode",
    "schedules",
    "schedule_selector_entity",
    "window_sensors",
    "window_open_delay",
    "window_close_delay",
    "comfort_temp",
    "eco_temp",
    "comfort_heat",
    "comfort_cool",
    "eco_heat",
    "eco_cool",
    "presence_persons",
    "display_name",
    "heating_system_type",
    "covers",
    "covers_auto_enabled",
    "covers_deploy_threshold",
    "covers_min_position",
    "covers_outdoor_min_temp",
    "covers_override_minutes",
    "cover_schedules",
    "cover_schedule_selector_entity",
    "cover_orientations",
    "covers_night_close",
    "covers_night_close_elevation",
    "covers_night_close_offset_minutes",
    "covers_night_position",
    "covers_snap_deploy",
    "covers_window_hold",
    "cover_min_positions",
    "ignore_presence",
    "is_outdoor",
    "heat_source_orchestration",
    "heat_source_primary_delta",
    "heat_source_outdoor_threshold",
    "heat_source_ac_min_outdoor",
    "heat_source_price_aware",
    "valve_protection_exclude",
    "climate_control_enabled",
    "co2_sensor",
    "co2_threshold",
    "voc_sensor",
    "voc_threshold",
    "ventilation_entity",
)

_SETTINGS_SAVE_FIELDS = (
    "outdoor_temp_sensor",
    "outdoor_humidity_sensor",
    "outdoor_cooling_min",
    "outdoor_heating_max",
    "control_mode",
    "comfort_weight",
    "weather_entity",
    "outdoor_unavailable_notify",
    "climate_control_active",
    "learning_disabled_rooms",
    "hidden_rooms",
    "vacation_temp",
    "vacation_until",
    "prediction_enabled",
    "presence_enabled",
    "presence_persons",
    "presence_away_action",
    "presence_clears_override",
    "schedule_off_action",
    "valve_protection_enabled",
    "valve_protection_interval_days",
    "coil_dry_enabled",
    "coil_dry_minutes",
    "coil_dry_mode",
    "coil_dry_fan_mode",
    "coil_dry_min_cooling_minutes",
    "coil_dry_drain_minutes",
    "mold_detection_enabled",
    "mold_humidity_threshold",
    "mold_f_rsi",
    "mold_sustained_minutes",
    "mold_notification_cooldown",
    "mold_notifications_enabled",
    "mold_notification_targets",
    "mold_prevention_enabled",
    "mold_prevention_intensity",
    "mold_prevention_notify_enabled",
    "mold_prevention_notify_targets",
    "room_order",
    "group_by_floor",
    "compressor_groups",
    "tou_enabled",
    "tou_tier_source",
    "tou_lookahead",
    "tou_rate_entity",
    "tou_period_entity",
    "tou_next_change_entity",
    "tou_next_rate_entity",
    "tou_next_period_entity",
    "tou_next_change_tier",
    "tou_calendar_entities",
    "tou_rate_windows",
    "tou_flag_entities",
    "tou_price_weighting",
    "tou_peak_threshold",
    "tou_mid_threshold",
    "tou_ultra_threshold",
    "tou_heat_min",
    "tou_heat_max",
    "tou_cool_min",
    "tou_cool_max",
    "tou_swing",
    "tou_store_gap",
    "tou_period_aliases",
    "tou_coast_max_minutes",
    "tou_schedules",
    "tou_rules",
)


# _safe_float, _csv_to_points and _compute_target_forecast are imported from
# .services.analytics_service (see imports above) and re-exported so that
# existing callers (incl. tests) keep working.


def _compute_anyone_home(hass: HomeAssistant, settings: dict) -> bool:
    """Return True if at least one tracked person is home (or fail-safe)."""
    from .utils.presence_utils import is_presence_away

    return not is_presence_away(hass, {}, settings)  # all away


def _validate_no_own_entities(config: dict, own_prefix: str) -> str | None:
    """Check that no RoomMind-owned entities are assigned. Returns error message or None."""
    for field in ("thermostats", "acs", "window_sensors", "covers", "occupancy_sensors"):
        for eid in config.get(field, []):
            if eid.split(".", 1)[-1].startswith(own_prefix):
                return f"Cannot assign RoomMind's own entity '{eid}' to a room"
    for device in config.get("devices", []):
        eid = device.get("entity_id", "")
        if eid.split(".", 1)[-1].startswith(own_prefix):
            return f"Cannot assign RoomMind's own entity '{eid}' to a room"
    for field in ("temperature_sensor", "humidity_sensor", "co2_sensor", "voc_sensor", "ventilation_entity"):
        eid = config.get(field, "")
        if eid and eid.split(".", 1)[-1].startswith(own_prefix):
            return f"Cannot assign RoomMind's own entity '{eid}' to a room"
    return None


def _hhmm_ok(text: str) -> bool:
    """True when text parses as HH:MM (0-23, 0-59)."""
    parts = text.split(":")
    if len(parts) < 2 or not (parts[0].isdigit() and parts[1].isdigit()):
        return False
    return 0 <= int(parts[0]) <= 23 and 0 <= int(parts[1]) <= 59


# Shared tariff rule definition fields (settings["tou_rules"] entries, and the
# optional `definition` a card row carries while the rule is being created or
# edited). heat/cool hold a °C target for set/arrive and a Δ for raise/lower;
# a blank side skips that mode. See TouManager.row_records for compilation.
_TOU_RULE_DEF_FIELDS = {
    vol.Required("name"): str,
    # Tier relaxed to str: the static schema cannot know the extra-tier
    # registry's ids; _tou_rule_def_error validates against them.
    vol.Optional("tier", default="any"): str,
    vol.Optional("edge", default="start"): vol.In(TOU_EDGES),
    vol.Required("action"): vol.In(TOU_ROW_ACTIONS),
    vol.Optional("heat"): vol.Any(None, "comfort", "eco", vol.Coerce(float)),
    vol.Optional("cool"): vol.Any(None, "comfort", "eco", vol.Coerce(float)),
    vol.Optional("until", default="tier_window"): vol.In(TOU_ROW_UNTILS),
    vol.Optional("minutes", default=0): vol.Coerce(int),
    vol.Optional("clock", default=""): str,
    vol.Optional("days", default=[]): vol.All([vol.In(TOU_WEEKDAYS)], vol.Length(max=7)),
    vol.Optional("between", default=None): vol.Any(
        None,
        {vol.Required("from"): str, vol.Required("to"): str},
    ),
}


def _tou_rule_def_error(defn: dict, allowed_tiers: tuple[str, ...] = ()) -> str | None:
    """Validate one tariff rule definition; return an error message or None.

    ``allowed_tiers`` carries the extra-tier registry ids: a rule may anchor
    on a generator or a solar window just as on a grid period, and only the
    handler (not the static schema) can know those user-created labels.
    """
    name = str(defn.get("name") or "").strip()
    if not name:
        return "Tariff rules need a name"
    action = str(defn.get("action") or "")
    if action not in TOU_ROW_ACTIONS:
        return f"Unknown action '{action}'"
    tier = str(defn.get("tier") or "any")
    if tier != "any" and tier not in TOU_TIERS and tier not in allowed_tiers:
        return f"Unknown tariff period '{tier}'"
    sides = [v for v in (defn.get("heat"), defn.get("cool")) if v is not None]
    if not sides:
        return "Tariff rules need a heating or a cooling value"
    named = [v for v in sides if isinstance(v, str)]
    numbers = [v for v in sides if not isinstance(v, str)]
    if action in ("set", "arrive"):
        # Named values (Comfort/Eco) aim at the room's own targets: no
        # numeric range to check, only the plain temperatures.
        if not all(TOU_SCHEDULE_TEMP_MIN <= float(v) <= TOU_SCHEDULE_TEMP_MAX for v in numbers):
            return f"'{action}' needs temperatures {TOU_SCHEDULE_TEMP_MIN:g}-{TOU_SCHEDULE_TEMP_MAX:g} °C"
    elif named:
        # raise/lower are deltas; a named value cannot express one.
        return f"'{action}' needs numeric deltas, not a named temperature"
    if action in ("raise", "lower") and not all(
        TOU_SCHEDULE_SHIFT_MIN <= abs(float(v)) <= TOU_SCHEDULE_SHIFT_MAX for v in sides
    ):
        return f"'{action}' needs deltas {TOU_SCHEDULE_SHIFT_MIN:g}-{TOU_SCHEDULE_SHIFT_MAX:g} °C"
    until = str(defn.get("until") or "tier_window")
    if until not in TOU_ROW_UNTILS:
        return f"Unknown end '{until}'"
    if action == "arrive":
        # Arrival modes (see TouManager._rule_records): an arrival clock means
        # "reach by HH:MM" (the edge must be parseable); no clock means the
        # room coasts through the anchored period to its end. Any-tier arrivals
        # would fire on every boundary, and fixed minutes end nothing.
        if str(defn.get("tier") or "any") == "any":
            return "'arrive' needs a tariff period to anchor on"
        if until == "minutes":
            return "'arrive' cannot end after a fixed duration"
        clock = str(defn.get("clock") or "")
        if clock:
            if not _hhmm_ok(clock):
                return "'arrive' needs 'HH:MM' or no clock to coast through the period"
        elif until == "clock":
            return "'clock' end needs 'HH:MM'"
    elif until == "clock" and not _hhmm_ok(str(defn.get("clock") or "")):
        return "'clock' end needs 'HH:MM'"
    if until == "minutes" and not (
        TOU_SCHEDULE_MINUTES_MIN <= int(defn.get("minutes") or 0) <= TOU_SCHEDULE_MINUTES_MAX
    ):
        return f"Minute ends need {TOU_SCHEDULE_MINUTES_MIN}-{TOU_SCHEDULE_MINUTES_MAX} minutes"
    between = defn.get("between")
    if between and not (_hhmm_ok(str(between.get("from") or "")) and _hhmm_ok(str(between.get("to") or ""))):
        return "'between' needs 'HH:MM' values"
    return None


async def _async_upsert_tou_rules(hass: HomeAssistant, rows: list[dict]) -> None:
    """Apply card row definitions to the shared rule library.

    The rule's name is its identity: same name means the same rule in every
    room. Unchanged name → propagate the edit to every room referencing it.
    New name → fork a derivative, this room alone repoints. Name that already
    belongs to another rule → merge: the incoming definition overwrites the
    canonical entry and every reference to the old id repoints to it, so the
    rename onto an existing name applies to all rooms sharing it.
    """
    store = hass.data[DOMAIN]["store"]
    library = [r for r in (store.get_settings().get("tou_rules") or []) if isinstance(r, dict)]
    by_id = {str(r.get("id", "")): r for r in library}
    by_name = {str(r.get("name", "")).strip(): r for r in library}
    remaps: dict[str, str] = {}  # old rule id -> canonical id (merge)
    changed = False
    for row in rows:
        defn = row.get("definition")
        if not isinstance(defn, dict):
            continue
        # The card may echo the id it knows; ids are library-owned, never
        # client-carried (a merge would otherwise rewrite the canonical id).
        defn = {k: v for k, v in defn.items() if k != "id"}
        name = str(defn.get("name") or "").strip()
        rid = str(row.get("rule_id") or "")
        existing = by_id.get(rid)
        same_name = by_name.get(name)
        if same_name is not None and same_name is not existing:
            canonical_id = str(same_name["id"])
            same_name.clear()
            same_name.update({"id": canonical_id, **defn, "name": name})
            if existing is not None:
                # merged away: every room pointing at the old id follows
                library.remove(existing)
                by_id.pop(rid, None)
                remaps[rid] = canonical_id
                by_name.pop(str(existing.get("name", "")).strip(), None)
            by_name[name] = same_name
            row["rule_id"] = canonical_id
            changed = True
        elif existing is not None and str(existing.get("name", "")).strip() == name:
            existing.clear()
            existing.update({"id": rid, **defn, "name": name})
            changed = True
        else:
            # fork (renamed away from a still-shared rule) or brand-new rule
            new_id = uuid.uuid4().hex if (existing is not None or not rid) else rid
            entry: dict = {"id": new_id, **defn, "name": name}
            library.append(entry)
            by_id[new_id] = entry
            by_name[name] = entry
            row["rule_id"] = new_id
            changed = True

    if not changed and not remaps:
        return
    await store.async_save_settings({"tou_rules": library})
    # Merge repoints other rooms' rows too (same name, same rule everywhere).
    if remaps:
        for area_id, room in store.get_rooms().items():
            room_rows = room.get("tou_overrides") or []
            if any(str(r.get("rule_id") or "") in remaps for r in room_rows if isinstance(r, dict)):
                updated = [
                    {**r, "rule_id": remaps.get(str(r.get("rule_id") or ""), str(r.get("rule_id") or ""))}
                    if isinstance(r, dict)
                    else r
                    for r in room_rows
                ]
                await store.async_update_room(area_id, {"tou_overrides": updated})


async def _async_prune_tou_rules(hass: HomeAssistant) -> None:
    """Drop shared rules no room row references anymore.

    Reference counting is state-blind: a room whose schedule or Time-of-Use
    is switched off still holds its rows, and through them the rules — a
    temporary measure never loses data. Only removing the row or the room
    drops the count.
    """
    store = hass.data[DOMAIN]["store"]
    library = store.get_settings().get("tou_rules") or []
    if not isinstance(library, list) or not library:
        return
    referenced = {
        str(row.get("rule_id") or "")
        for room in store.get_rooms().values()
        for row in (room.get("tou_overrides") or [])
        if isinstance(row, dict)
    }
    kept = [e for e in library if isinstance(e, dict) and str(e.get("id")) in referenced]
    if len(kept) != len(library):
        await store.async_save_settings({"tou_rules": kept})


def _validate_no_duplicate_devices(config: dict) -> str | None:
    """Check for duplicate entity_ids in devices[]. Returns error message or None."""
    device_eids = [d["entity_id"] for d in config.get("devices", [])]
    if len(device_eids) != len(set(device_eids)):
        return "devices[] contains duplicate entity_ids"
    return None


# ---------------------------------------------------------------------------
# List rooms
# ---------------------------------------------------------------------------


@websocket_api.websocket_command({vol.Required("type"): "roommind/rooms/list"})
@websocket_api.async_response
async def websocket_list_rooms(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict,
) -> None:
    """Return all rooms with current state."""
    store = hass.data[DOMAIN]["store"]
    stored = store.get_rooms()
    rooms = rooms_with_area(hass, stored)

    # Merge live state from coordinator
    coordinator = _get_coordinator(hass)
    # If coordinator has no data yet but rooms exist, trigger an immediate refresh
    if coordinator and rooms and not coordinator.rooms:
        await coordinator.async_request_refresh()
    live_states = coordinator.rooms if coordinator else {}

    # Outdoor temperature availability gates EKF training (#301).  Surface the
    # paused state per room so the frontend can show an explanatory badge.
    outdoor_available = coordinator is not None and coordinator.outdoor_temp_effective is not None
    settings = store.get_settings()
    learning_disabled = set(settings.get("learning_disabled_rooms", []))
    boost_anchors = settings.get("boost_applied_at", {})

    # Build response: config + live state per room
    # Override fields are computed from the store (always up-to-date) rather
    # than from the coordinator (which refreshes on a 10s cycle).
    result = {}
    for area_id, room_config in rooms.items():
        room_data = dict(room_config)
        live = live_states.get(area_id, {})
        # Managed Mode rooms train too (on the device reading), only outdoor areas never do.
        if not outdoor_available and area_id not in learning_disabled and not room_config.get("is_outdoor", False):
            learning_paused_reason: str | None = "outdoor_unavailable"
        else:
            learning_paused_reason = None

        room_data["live"] = {
            "current_temp": live.get("current_temp"),
            "current_humidity": live.get("current_humidity"),
            "target_temp": live.get("target_temp"),
            "heat_target": live.get("heat_target"),
            "cool_target": live.get("cool_target"),
            "mode": live.get("mode", "idle"),
            "heating_power": live.get("heating_power", 0),
            "device_setpoint": live.get("device_setpoint"),
            "window_open": live.get("window_open", False),
            **build_override_live(
                room_config,
                suppressed=is_override_suppressed(room_config, settings, live.get("presence_away", False)),
            ),
            "active_schedule_index": live.get("active_schedule_index", -1),
            "confidence": live.get("confidence"),
            "mpc_active": live.get("mpc_active", False),
            "presence_away": live.get("presence_away", False),
            "occupancy_vacant": live.get("occupancy_vacant", False),
            "co2": live.get("co2"),
            "voc": live.get("voc"),
            "air_quality_bad": live.get("air_quality_bad", False),
            "air_quality_reason": live.get("air_quality_reason"),
            "ventilation_active": live.get("ventilation_active", False),
            "mold_risk_level": live.get("mold_risk_level", "ok"),
            "mold_surface_rh": live.get("mold_surface_rh"),
            "mold_surface_temp": live.get("mold_surface_temp"),
            "mold_prevention_active": live.get("mold_prevention_active", False),
            "mold_prevention_delta": live.get("mold_prevention_delta", 0),
            "n_observations": live.get("n_observations", 0),
            # A paused room does not fade the boost, so no countdown for it
            "boost_applied_at": None if area_id in learning_disabled else boost_anchors.get(area_id),
            "blind_position": live.get("blind_position"),
            "cover_auto_paused": live.get("cover_auto_paused", False),
            "cover_override_until": live.get("cover_override_until"),
            "cover_forced_reason": live.get("cover_forced_reason", ""),
            "cover_reason": live.get("cover_reason", ""),
            "active_cover_schedule_index": live.get("active_cover_schedule_index", -1),
            "active_heat_sources": live.get("active_heat_sources"),
            "learning_paused_reason": learning_paused_reason,
            "compressor_protection_active": live.get("compressor_protection_active", False),
            "compressor_protection_reason": live.get("compressor_protection_reason"),
            "compressor_protection_until": live.get("compressor_protection_until"),
            "coil_dry_active": live.get("coil_dry_active", False),
            "coil_dry_phase": live.get("coil_dry_phase"),
            "coil_dry_until": live.get("coil_dry_until"),
            "coil_dry_entities": live.get("coil_dry_entities", []),
            "schedule_temp_warnings": live.get("schedule_temp_warnings", []),
            "price_level": live.get("price_level"),
            "preheat": live.get("preheat"),
            "setback": live.get("setback"),
            "price_shift_heat": live.get("price_shift_heat", 0.0),
            "price_shift_cool": live.get("price_shift_cool", 0.0),
            "recent_temps": coordinator.recent_temps.get(area_id) if coordinator else [],
        }
        result[area_id] = room_data

    # Vacation state from settings
    vacation_until = settings.get("vacation_until")
    vacation_active = bool(vacation_until and time.time() < vacation_until)

    # TOU tariff snapshot from the last cycle (absent while Time-of-Use is off,
    # so the payload is byte-identical to the pre-TOU base when disabled).
    coordinator_data = getattr(coordinator, "data", None) if coordinator else None
    tou_snapshot = coordinator_data.get("tou") if isinstance(coordinator_data, dict) else None
    tou_tier_info = None
    if tou_snapshot:
        manager = getattr(coordinator, "_tou_manager", None)
        info = manager.tier_info(settings) if manager is not None else None
        tou_tier_info = info if isinstance(info, dict) else None

    connection.send_result(
        msg["id"],
        {
            "rooms": result,
            "rooms_without_area": [
                {"area_id": area_id, "display_name": room.get("display_name", "")}
                for area_id, room in rooms_without_area(hass, stored).items()
            ],
            # Countdowns in the browser compare against this, not against the device's own clock
            "server_time": time.time(),
            "outdoor_temp": coordinator.outdoor_temp_effective if coordinator else None,
            "outdoor_humidity": coordinator.outdoor_humidity if coordinator else None,
            "vacation_active": vacation_active,
            "vacation_temp": settings.get("vacation_temp") if vacation_active else None,
            "vacation_until": vacation_until if vacation_active else None,
            "hidden_rooms": settings.get("hidden_rooms", []),
            "room_order": settings.get("room_order", []),
            "group_by_floor": settings.get("group_by_floor", False),
            "control_mode": settings.get("control_mode", DEFAULT_CONTROL_MODE),
            "climate_control_active": settings.get("climate_control_active", True),
            "presence_enabled": settings.get("presence_enabled", False),
            "presence_persons": settings.get("presence_persons", []),
            "presence_away_action": settings.get("presence_away_action", "eco"),
            "presence_clears_override": settings.get("presence_clears_override", False),
            "schedule_off_action": settings.get("schedule_off_action", "eco"),
            "anyone_home": _compute_anyone_home(hass, settings),
            "valve_protection_enabled": settings.get("valve_protection_enabled", False),
            "coil_dry_enabled": settings.get("coil_dry_enabled", False),
            "coil_dry_minutes": settings.get("coil_dry_minutes", DEFAULT_COIL_DRY_MINUTES),
            "coil_dry_mode": settings.get("coil_dry_mode", COIL_DRY_MODE_FAN_ONLY),
            "coil_dry_fan_mode": settings.get("coil_dry_fan_mode", DEFAULT_COIL_DRY_FAN_MODE),
            "coil_dry_min_cooling_minutes": settings.get(
                "coil_dry_min_cooling_minutes", DEFAULT_COIL_DRY_MIN_COOLING_MINUTES
            ),
            "coil_dry_drain_minutes": settings.get("coil_dry_drain_minutes", DEFAULT_COIL_DRY_DRAIN_MINUTES),
            "compressor_groups": settings.get("compressor_groups", []),
            # Shared tariff rule library: cards resolve row rule_id -> definition.
            "tou_rules": settings.get("tou_rules", []),
            # Effective store limits, so room cards can state what an empty
            # per-room override inherits (managers/tou_manager.py make_adjuster).
            "tou_limits": {
                "heat_min": settings.get("tou_heat_min", DEFAULT_TOU_HEAT_MIN),
                "heat_max": settings.get("tou_heat_max", DEFAULT_TOU_HEAT_MAX),
                "cool_min": settings.get("tou_cool_min", DEFAULT_TOU_COOL_MIN),
                "cool_max": settings.get("tou_cool_max", DEFAULT_TOU_COOL_MAX),
                "swing": settings.get("tou_swing", DEFAULT_TOU_SWING),
                "store_gap": settings.get("tou_store_gap", DEFAULT_TOU_STORE_GAP),
            },
            # The global master switch gates the room cards' energy-price box (D8).
            "tou_enabled": bool(settings.get("tou_enabled", False)),
            **({"tou": tou_snapshot} if tou_snapshot else {}),
            # Tier dictionary: what the bound sources actually feed (prices,
            # vocabulary, unmapped strings) for the settings panel.
            **({"tou_tier_info": tou_tier_info} if tou_tier_info else {}),
        },
    )


# ---------------------------------------------------------------------------
# Save room (upsert: create or update)
# ---------------------------------------------------------------------------


@websocket_api.websocket_command(
    {
        vol.Required("type"): "roommind/rooms/save",
        vol.Required("area_id"): str,
        vol.Optional("thermostats"): [str],
        vol.Optional("acs"): [str],
        vol.Optional("devices"): [
            vol.All(
                {
                    vol.Required("entity_id"): str,
                    vol.Required("type"): vol.In(["trv", "ac"]),
                    vol.Optional("role", default="auto"): vol.In(["primary", "secondary", "auto"]),
                    vol.Optional("heating_system_type", default=""): vol.In(["", "radiator", "underfloor"]),
                    vol.Optional("idle_action", default="off"): vol.In(["off", "fan_only", "setback", "low"]),
                    vol.Optional("idle_fan_mode", default="low"): str,
                    # No default: devices without it keep their stored form (#255)
                    vol.Optional("setback_auto_off"): bool,
                    vol.Optional("setpoint_mode", default="proportional"): vol.In(["proportional", "direct"]),
                    vol.Optional("setpoint_offset", default=0.0): vol.All(
                        vol.Coerce(float), vol.Range(min=SETPOINT_OFFSET_MIN, max=SETPOINT_OFFSET_MAX)
                    ),
                    vol.Optional("coil_dry", default=COIL_DRY_INHERIT): vol.In(COIL_DRY_OVERRIDES),
                    vol.Optional("coil_dry_minutes", default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=60)),
                    vol.Optional("coil_dry_mode", default=""): vol.In(["", *COIL_DRY_MODES]),
                    vol.Optional("coil_dry_fan_mode", default=""): str,
                    vol.Optional("valve_opening_entity"): _number_entity_or_empty,
                    vol.Optional("valve_closing_entity"): _number_entity_or_empty,
                    # No default: devices without it keep their stored form (#482)
                    vol.Optional("valve_closing_mode"): vol.In(VALVE_CLOSING_MODES),
                },
                _validate_device_idle_action,
                _validate_device_coil_dry,
                _validate_device_valve,
            )
        ],
        vol.Optional("temperature_sensor"): str,
        vol.Optional("humidity_sensor"): str,
        vol.Optional("occupancy_sensors"): [str],
        vol.Optional("occupancy_eco_enabled"): bool,
        vol.Optional("occupancy_eco_delay"): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_OCCUPANCY_ECO_DELAY_MINUTES, max=240)
        ),
        vol.Optional("preheat_enabled"): bool,
        vol.Optional("price_shift"): vol.All(vol.Coerce(float), vol.Range(min=0, max=MAX_PRICE_SHIFT_K)),
        # Time-of-Use store layer: per-room participation and consent limits
        # (blank/None = inherit the global limits from settings).
        vol.Optional("tou_store_enabled"): bool,
        vol.Optional("tou_heat_min"): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=5, max=35))),
        vol.Optional("tou_heat_max"): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=5, max=40))),
        vol.Optional("tou_cool_min"): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=5, max=35))),
        vol.Optional("tou_cool_max"): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=5, max=40))),
        vol.Optional("tou_swing"): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=0, max=10))),
        vol.Optional("tou_store_gap"): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=1, max=10))),
        # Tariff schedule rows edited on the device card: thin references into
        # the shared rule library (settings["tou_rules"]) with a per-row
        # enabled toggle. `definition` rides along only while the card creates
        # or edits the rule; _async_upsert_tou_rules applies it (propagate /
        # fork on rename / merge onto a same-named rule) and it is never
        # stored on the room. The optional `id` is tolerated because the card
        # echoes the library entry's id while editing (upsert strips it).
        # Rows in the ignored pre-release inline format (no rule_id) are
        # dropped by the next save.
        vol.Optional("tou_schedule_enabled"): bool,
        vol.Optional("tou_overrides"): [
            {
                vol.Required("id"): str,
                vol.Required("rule_id"): str,
                vol.Optional("enabled", default=True): bool,
                vol.Optional("definition"): {
                    **_TOU_RULE_DEF_FIELDS,
                    vol.Optional("id"): str,
                },
            }
        ],
        vol.Optional("follow_device_setpoint"): bool,
        vol.Optional("climate_mode"): vol.In(CLIMATE_MODES),
        vol.Optional("schedules"): [{vol.Required("entity_id"): str}],
        vol.Optional("schedule_selector_entity"): str,
        vol.Optional("window_sensors"): [str],
        vol.Optional("window_open_delay"): vol.Coerce(int),
        vol.Optional("window_close_delay"): vol.Coerce(int),
        vol.Optional("comfort_temp"): vol.Coerce(float),
        vol.Optional("eco_temp"): vol.Coerce(float),
        vol.Optional("comfort_heat"): vol.Coerce(float),
        vol.Optional("comfort_cool"): vol.Coerce(float),
        vol.Optional("eco_heat"): vol.Coerce(float),
        vol.Optional("eco_cool"): vol.Coerce(float),
        vol.Optional("presence_persons"): [str],
        vol.Optional("display_name"): str,
        vol.Optional("heating_system_type"): vol.In(["", "radiator", "underfloor"]),
        vol.Optional("covers"): [str],
        vol.Optional("covers_auto_enabled"): bool,
        vol.Optional("covers_deploy_threshold"): vol.All(vol.Coerce(float), vol.Range(min=0)),
        vol.Optional("covers_min_position"): vol.All(vol.Coerce(int), vol.Range(min=0, max=99)),
        vol.Optional("covers_outdoor_min_temp"): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=0, max=35))),
        vol.Optional("covers_override_minutes"): vol.All(vol.Coerce(int), vol.Range(min=0, max=480)),
        vol.Optional("cover_schedules"): [
            {
                vol.Required("entity_id"): str,
                vol.Optional("mode", default="force"): vol.In(["force", "gate"]),
            }
        ],
        vol.Optional("cover_schedule_selector_entity"): str,
        vol.Optional("cover_orientations"): {str: vol.All(vol.Coerce(int), vol.Range(min=0, max=359))},
        vol.Optional("covers_night_close"): bool,
        vol.Optional("covers_night_close_elevation"): vol.All(vol.Coerce(float), vol.Range(min=-18, max=10)),
        vol.Optional("covers_night_close_offset_minutes"): vol.All(vol.Coerce(int), vol.Range(min=-120, max=120)),
        vol.Optional("covers_night_position"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
        vol.Optional("covers_snap_deploy"): bool,
        vol.Optional("covers_window_hold"): bool,
        vol.Optional("cover_min_positions"): {str: vol.All(vol.Coerce(int), vol.Range(min=0, max=99))},
        vol.Optional("ignore_presence"): bool,
        vol.Optional("is_outdoor"): bool,
        vol.Optional("valve_protection_exclude"): [str],
        vol.Optional("heat_source_orchestration"): bool,
        vol.Optional("heat_source_primary_delta"): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=5.0)),
        vol.Optional("heat_source_outdoor_threshold"): vol.All(vol.Coerce(float), vol.Range(min=-20, max=25)),
        vol.Optional("heat_source_ac_min_outdoor"): vol.All(vol.Coerce(float), vol.Range(min=-30, max=5)),
        vol.Optional("heat_source_price_aware"): bool,
        vol.Optional("climate_control_enabled"): bool,
        vol.Optional("co2_sensor"): str,
        vol.Optional("co2_threshold"): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_CO2_THRESHOLD, max=MAX_CO2_THRESHOLD)
        ),
        vol.Optional("voc_sensor"): str,
        # In the sensor's own unit (index, ppb, µg/m³); None = the reading is shown, not judged
        vol.Optional("voc_threshold"): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=0.001, max=1e6))),
        vol.Optional("ventilation_entity"): vol.Any(
            "", vol.All(str, vol.Match(rf"^({'|'.join(VENTILATION_DOMAINS)})\.[a-z0-9_]+$"))
        ),
    }
)
@websocket_api.async_response
async def websocket_save_room(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict,
) -> None:
    """Create or update a room configuration."""
    store = hass.data[DOMAIN]["store"]
    area_id = msg["area_id"]

    # Build config dict from optional fields present in the message
    config: dict = {}
    for key in _ROOM_SAVE_FIELDS:
        if key in msg:
            config[key] = msg[key]

    # Reject RoomMind's own entities to prevent self-assignment (#86)
    own_prefix = f"{DOMAIN}_"
    err = _validate_no_own_entities(config, own_prefix)
    if err:
        connection.send_error(msg["id"], "invalid_entity", err)
        return
    # Reject duplicate entity_ids in devices[]
    err = _validate_no_duplicate_devices(config)
    if err:
        connection.send_error(msg["id"], "duplicate_entity", err)
        return

    # Tariff schedule rows (device card): rows are references into the shared
    # library; an attached definition is validated, upserted, and then stripped
    # so only the thin reference is stored on the room.
    overrides = config.get("tou_overrides")
    if overrides:
        row_ids = [str(r.get("id", "")) for r in overrides]
        if len(row_ids) != len(set(row_ids)):
            connection.send_error(msg["id"], "duplicate_tou_override_id", "Tariff schedule IDs must be unique")
            return
        for r in overrides:
            defn = r.get("definition")
            if defn is not None:
                err = _tou_rule_def_error(defn)
                if err:
                    connection.send_error(msg["id"], "invalid_tou_override", err)
                    return
            elif not str(r.get("rule_id") or ""):
                connection.send_error(
                    msg["id"],
                    "invalid_tou_override",
                    "A schedule row must reference a rule or carry its definition",
                )
                return
        # Upsert now (before the room write): the merge remap loop repoints
        # other rooms' rows, and this room's rows were already mutated to the
        # canonical ids, so the save below stores the final references.
        await _async_upsert_tou_rules(hass, overrides)
        # Definitions are library state, never room state: store thin
        # references. An empty list passes through as-is (it clears the rows).
        config["tou_overrides"] = [{k: v for k, v in r.items() if k != "definition"} for r in overrides]

    if ("thermostats" in config or "acs" in config) and "devices" not in config:
        _LOGGER.warning(
            "Room save for '%s' uses legacy thermostats/acs fields without devices. "
            "This is deprecated and will be removed in a future version.",
            area_id,
        )

    old_valves = get_valve_entities((store.get_room(area_id) or {}).get("devices", []))
    room = await store.async_save_room(area_id, config)
    new_valves = get_valve_entities(room.get("devices", []))
    await _async_release_dropped_valves(hass, area_id, old_valves, new_valves)
    if overrides is not None:
        # Rows the card just removed were the last references: drop those
        # rules from the shared library (state-blind counting).
        await _async_prune_tou_rules(hass)

    # Notify coordinator to create/update sensor entities for the room
    coordinator = _get_coordinator(hass)
    if coordinator:
        await coordinator.async_room_added(room)

    connection.send_result(msg["id"], {"room": room})


async def _async_release_dropped_valves(
    hass: HomeAssistant,
    area_id: str,
    old: dict[str, ValveEntities],
    new: dict[str, ValveEntities],
    *,
    hand_back: bool = True,
) -> None:
    """Hand valves RoomMind no longer controls back to their TRVs (#413).

    Nobody else would: without the config RoomMind does not know these number
    entities any more, and the valve would stay pinned where it was last set. A changed
    closing mode alone is left to the next cycle (#482): a release in the old mode would
    open a TRV-ZBT fully while it idles.
    """
    for climate_eid, valve in old.items():
        kept = new.get(climate_eid)
        if kept is not None and kept[:2] == valve[:2]:
            continue
        try:
            await async_release_valve(
                hass,
                climate_eid,
                valve.opening,
                valve.closing,
                area_id=area_id,
                hand_back=hand_back,
                idle_opening=valve.idle_opening,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Room '%s': releasing the valve of '%s' failed", area_id, climate_eid, exc_info=True)


# ---------------------------------------------------------------------------
# Delete room
# ---------------------------------------------------------------------------


@websocket_api.websocket_command(
    {
        vol.Required("type"): "roommind/rooms/delete",
        vol.Required("area_id"): str,
    }
)
@websocket_api.async_response
async def websocket_delete_room(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict,
) -> None:
    """Delete a room."""
    area_id = msg["area_id"]
    if not await async_remove_room(hass, area_id):
        connection.send_error(msg["id"], "not_found", f"Room '{area_id}' not found")
        return
    connection.send_result(msg["id"], {"success": True})


async def _async_drop_boost_anchors(store: RoomMindStore, area_ids: list[str] | None = None) -> None:
    """Forget the boost anchor with the model it counted on (None = every room)."""
    anchors = store.get_settings().get("boost_applied_at", {})
    if not anchors:
        return
    kept = {} if area_ids is None else {a: n for a, n in anchors.items() if a not in area_ids}
    if kept != anchors:
        await store.async_save_settings({"boost_applied_at": kept})


async def _async_forget_in_room_lists(store: RoomMindStore, area_id: str) -> None:
    """Drop a deleted room from the settings lists, else a new room in the same area inherits them."""
    settings = store.get_settings()
    changes = {
        key: [a for a in settings[key] if a != area_id]
        for key in ("hidden_rooms", "room_order", "learning_disabled_rooms")
        if area_id in (settings.get(key) or [])
    }
    if changes:
        await store.async_save_settings(changes)


async def async_remove_room(hass: HomeAssistant, area_id: str) -> bool:
    """Delete a room with its entities, valves, model and history; False if it is not stored."""
    store = hass.data[DOMAIN]["store"]
    room = store.get_room(area_id)
    if room is None:
        return False
    coordinator = _get_coordinator(hass)
    switched_off = bool(coordinator and coordinator.note_room_deleted(area_id, room))
    await store.async_delete_room(area_id)

    # The room target as setpoint would let a TRV that is switched off next cycle heat on by itself
    await _async_release_dropped_valves(
        hass, area_id, get_valve_entities(room.get("devices", [])), {}, hand_back=not switched_off
    )
    await _async_forget_in_room_lists(store, area_id)
    # The deleted room's rows were the last references: prune the library.
    await _async_prune_tou_rules(hass)

    if coordinator:
        await coordinator.async_room_removed(area_id)
    # Stored right away, after the in-memory model is gone: else it only went with the next thermal save
    await store.async_clear_thermal_data_room(area_id)
    await _async_drop_boost_anchors(store, [area_id])
    return True


async def async_pause_room(hass: HomeAssistant, area_id: str) -> None:
    """Stop running a room whose area was deleted, keeping what is stored for it (#494)."""
    coordinator = _get_coordinator(hass)
    if hass.data[DOMAIN]["store"].get_room(area_id) is not None and coordinator:
        await coordinator.async_room_paused(area_id)


async def async_resume_room(hass: HomeAssistant, area_id: str) -> None:
    """Run a resting room again once an area with its id exists (#494)."""
    store = hass.data[DOMAIN]["store"]
    if store.get_room(area_id) is None:
        return
    await store.async_update_room(area_id, {REST_SWITCHED_OFF: False})
    coordinator = _get_coordinator(hass)
    if coordinator:
        await coordinator.async_room_added(store.get_room(area_id))


# ---------------------------------------------------------------------------
# Set override
# ---------------------------------------------------------------------------


@websocket_api.websocket_command(
    {
        vol.Required("type"): "roommind/override/set",
        vol.Required("area_id"): str,
        vol.Required("override_type"): vol.In(OVERRIDE_TYPES),
        vol.Optional("heat"): vol.Coerce(float),
        vol.Optional("cool"): vol.Coerce(float),
        vol.Optional("duration"): vol.Coerce(float),  # hours (omit or 0 for permanent)
        # Until the active schedule's next block boundary; `duration` is the fallback without one
        vol.Optional("until_schedule_change", default=False): bool,
    }
)
@websocket_api.async_response
async def websocket_override_set(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict,
) -> None:
    """Set a temporary override for a room."""
    store = hass.data[DOMAIN]["store"]
    area_id = msg["area_id"]
    override_type = msg["override_type"]
    duration_hours = msg.get("duration")

    room = store.get_room(area_id)
    if room is None:
        connection.send_error(msg["id"], "not_found", f"Room '{area_id}' not found")
        return

    if override_type == OVERRIDE_CUSTOM:
        heat = msg.get("heat")
        cool = msg.get("cool")
        if heat is None and cool is None:
            connection.send_error(msg["id"], "invalid", "Custom override requires heat and/or cool")
            return
    else:
        heat, cool = override_preset_band(room, override_type)

    heat, cool = mask_override_band(heat, cool, room.get("climate_mode", "auto"))

    if heat is not None and cool is not None and cool < heat:
        connection.send_error(msg["id"], "invalid", "Cooling target must be >= heating target")
        return

    override_until = (time.time() + duration_hours * 3600) if duration_hours else None
    if msg.get("until_schedule_change"):
        next_change = next_schedule_change(hass, room)
        if next_change is not None and next_change > time.time():
            override_until = next_change

    await store.async_update_room(
        area_id,
        {
            "override_heat": heat,
            "override_cool": cool,
            "override_until": override_until,
            "override_type": override_type,
        },
    )

    coordinator = _get_coordinator(hass)
    if coordinator:
        coordinator.clear_override_seed(area_id)
        await coordinator.async_request_refresh()

    connection.send_result(msg["id"], {"success": True})


# ---------------------------------------------------------------------------
# Clear override
# ---------------------------------------------------------------------------


@websocket_api.websocket_command(
    {
        vol.Required("type"): "roommind/override/clear",
        vol.Required("area_id"): str,
    }
)
@websocket_api.async_response
async def websocket_override_clear(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict,
) -> None:
    """Clear an active override for a room."""
    store = hass.data[DOMAIN]["store"]
    area_id = msg["area_id"]

    room = store.get_room(area_id)
    if room is None:
        connection.send_error(msg["id"], "not_found", f"Room '{area_id}' not found")
        return

    await store.async_update_room(
        area_id,
        {
            "override_heat": None,
            "override_cool": None,
            "override_until": None,
            "override_type": None,
        },
    )

    coordinator = _get_coordinator(hass)
    if coordinator:
        coordinator.clear_override_seed(area_id)
        await coordinator.async_request_refresh()

    connection.send_result(msg["id"], {"success": True})


# ---------------------------------------------------------------------------
# Get settings
# ---------------------------------------------------------------------------


@websocket_api.websocket_command({vol.Required("type"): "roommind/settings/get"})
@websocket_api.async_response
async def websocket_get_settings(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict,
) -> None:
    """Return global settings."""
    store = hass.data[DOMAIN]["store"]
    connection.send_result(msg["id"], {"settings": store.get_settings()})


# ---------------------------------------------------------------------------
# Save settings
# ---------------------------------------------------------------------------


@websocket_api.websocket_command(
    {
        vol.Required("type"): "roommind/settings/save",
        vol.Optional("outdoor_temp_sensor"): str,
        vol.Optional("outdoor_humidity_sensor"): str,
        vol.Optional("outdoor_cooling_min"): vol.Coerce(float),
        vol.Optional("outdoor_heating_max"): vol.Coerce(float),
        vol.Optional("control_mode"): vol.In([CONTROL_MODE_MPC, CONTROL_MODE_BANGBANG]),
        vol.Optional("comfort_weight"): vol.Coerce(float),
        vol.Optional("weather_entity"): str,
        vol.Optional("outdoor_unavailable_notify"): bool,
        vol.Optional("climate_control_active"): bool,
        vol.Optional("learning_disabled_rooms"): [str],
        vol.Optional("hidden_rooms"): [str],
        vol.Optional("prediction_enabled"): bool,
        vol.Optional("vacation_temp"): vol.Coerce(float),
        vol.Optional("vacation_until"): vol.Any(vol.Coerce(float), None),
        vol.Optional("presence_enabled"): bool,
        vol.Optional("presence_persons"): [str],
        vol.Optional("presence_away_action"): vol.In(["eco", "off"]),
        vol.Optional("presence_clears_override"): bool,
        vol.Optional("schedule_off_action"): vol.In(["eco", "off"]),
        vol.Optional("valve_protection_enabled"): bool,
        vol.Optional("valve_protection_interval_days"): vol.All(vol.Coerce(int), vol.Range(min=1, max=90)),
        vol.Optional("coil_dry_enabled"): bool,
        vol.Optional("coil_dry_minutes"): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
        vol.Optional("coil_dry_mode"): vol.In(COIL_DRY_MODES),
        vol.Optional("coil_dry_fan_mode"): str,
        vol.Optional("coil_dry_min_cooling_minutes"): vol.All(vol.Coerce(int), vol.Range(min=1, max=240)),
        vol.Optional("coil_dry_drain_minutes"): vol.All(vol.Coerce(int), vol.Range(min=0, max=15)),
        vol.Optional("mold_detection_enabled"): bool,
        vol.Optional("mold_humidity_threshold"): vol.All(vol.Coerce(float), vol.Range(min=50, max=90)),
        vol.Optional("mold_f_rsi"): vol.All(vol.Coerce(float), vol.Range(min=0.6, max=0.95)),
        vol.Optional("mold_sustained_minutes"): vol.All(vol.Coerce(int), vol.Range(min=5, max=120)),
        vol.Optional("mold_notification_cooldown"): vol.All(vol.Coerce(int), vol.Range(min=10, max=1440)),
        vol.Optional("mold_notifications_enabled"): bool,
        vol.Optional("mold_notification_targets"): [
            {
                vol.Required("entity_id"): str,
                vol.Optional("person_entity", default=""): str,
                vol.Optional("notify_when", default="always"): vol.In(["always", "home_only"]),
            }
        ],
        vol.Optional("mold_prevention_enabled"): bool,
        vol.Optional("mold_prevention_intensity"): vol.In(["light", "medium", "strong"]),
        vol.Optional("mold_prevention_notify_enabled"): bool,
        vol.Optional("mold_prevention_notify_targets"): [
            {
                vol.Required("entity_id"): str,
                vol.Optional("person_entity", default=""): str,
                vol.Optional("notify_when", default="always"): vol.In(["always", "home_only"]),
            }
        ],
        vol.Optional("room_order"): [str],
        vol.Optional("group_by_floor"): bool,
        vol.Optional("compressor_groups"): [
            {
                vol.Required("id"): str,
                vol.Required("name"): str,
                vol.Required("members"): vol.All([str], vol.Length(min=1)),
                vol.Optional("min_run_minutes", default=DEFAULT_COMPRESSOR_MIN_RUN_MINUTES): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=60)
                ),
                vol.Optional("min_off_minutes", default=DEFAULT_COMPRESSOR_MIN_OFF_MINUTES): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=30)
                ),
                vol.Optional("master_entity", default=""): str,
                vol.Optional("conflict_resolution", default=DEFAULT_CONFLICT_RESOLUTION): vol.In(CONFLICT_RESOLUTIONS),
                vol.Optional("action_script", default=""): str,
                vol.Optional("enforce_uniform_mode", default=False): bool,
            }
        ],
        # Time-of-Use tariff sources (the TOU manager reads them each cycle;
        # the settings panel is a follow-up PR, so these are API-only today).
        vol.Optional("tou_enabled"): bool,
        vol.Optional("tou_tier_source"): vol.In(TOU_TIER_SOURCES),
        vol.Optional("tou_lookahead"): vol.In(TOU_LOOKAHEADS),
        vol.Optional("tou_rate_entity"): str,
        vol.Optional("tou_period_entity"): str,
        vol.Optional("tou_next_change_entity"): str,
        vol.Optional("tou_next_rate_entity"): str,
        vol.Optional("tou_next_period_entity"): str,
        vol.Optional("tou_next_change_tier"): vol.Any("", vol.In(TOU_TIERS)),
        vol.Optional("tou_calendar_entities"): vol.All(
            [
                {
                    vol.Required("entity_id"): str,
                    vol.Required("tier"): vol.In(TOU_TIERS),
                }
            ],
            vol.Length(max=4),
        ),
        vol.Optional("tou_rate_windows"): [
            {
                vol.Required("id"): str,
                vol.Required("rate"): vol.Coerce(float),
                vol.Required("start"): str,
                vol.Required("end"): str,
                vol.Optional("days", default=[]): [str],
            }
        ],
        vol.Optional("tou_flag_entities"): {vol.In(TOU_TIERS): str},
        # User-assigned period vocabulary: raw state (lower-cased) -> tier.
        # Consulted by TouManager._normalize_period before word recognition.
        vol.Optional("tou_period_aliases"): {
            vol.All(str, vol.Length(min=1, max=64)): vol.In(TOU_TIERS),
        },
        vol.Optional("tou_price_weighting"): bool,
        vol.Optional("tou_peak_threshold"): vol.Any(None, vol.Coerce(float)),
        vol.Optional("tou_mid_threshold"): vol.Any(None, vol.Coerce(float)),
        vol.Optional("tou_ultra_threshold"): vol.Any(None, vol.Coerce(float)),
        vol.Optional("tou_heat_min"): vol.All(vol.Coerce(float), vol.Range(min=5, max=35)),
        vol.Optional("tou_heat_max"): vol.All(vol.Coerce(float), vol.Range(min=5, max=40)),
        vol.Optional("tou_cool_min"): vol.All(vol.Coerce(float), vol.Range(min=5, max=35)),
        vol.Optional("tou_cool_max"): vol.All(vol.Coerce(float), vol.Range(min=5, max=40)),
        vol.Optional("tou_swing"): vol.All(vol.Coerce(float), vol.Range(min=0, max=10)),
        vol.Optional("tou_store_gap"): vol.All(vol.Coerce(float), vol.Range(min=1, max=10)),
        vol.Optional("tou_coast_max_minutes"): vol.All(vol.Coerce(int), vol.Range(min=30, max=1440)),
        # Tariff schedules (unified chain): edge-anchored adjustments in the
        # engine's native record format. guard is internal (legacy semantics).
        vol.Optional("tou_schedules"): [
            {
                vol.Required("id"): str,
                vol.Required("name"): str,
                vol.Optional("enabled", default=True): bool,
                vol.Required("rooms"): vol.All([str], vol.Length(min=1)),
                vol.Required("side"): vol.In(TOU_SIDES),
                vol.Optional("tier", default="any"): vol.In([*TOU_TIERS, "any"]),
                vol.Optional("from_tier", default=""): vol.Any("", vol.In(TOU_TIERS)),
                vol.Optional("edge", default="start"): vol.In(TOU_EDGES),
                vol.Optional("phase", default="after"): vol.In(TOU_PHASES),
                vol.Optional("minutes", default=0): vol.Coerce(int),
                vol.Optional("until", default="window"): vol.In(TOU_UNTILS),
                vol.Optional("until_tier", default=""): vol.Any("", vol.In(TOU_TIERS)),
                vol.Optional("clock", default=""): str,
                vol.Optional("between", default=None): vol.Any(
                    None,
                    {vol.Required("from"): str, vol.Required("to"): str},
                ),
                vol.Optional("days", default=[]): vol.All([vol.In(TOU_WEEKDAYS)], vol.Length(max=7)),
                vol.Optional("guard", default=False): bool,
                vol.Required("value"): {
                    vol.Required("mode"): vol.In(TOU_VALUE_MODES),
                    vol.Optional("temp"): vol.Coerce(float),
                    vol.Optional("direction"): vol.In(TOU_SHIFT_DIRECTIONS),
                    vol.Optional("delta"): vol.Coerce(float),
                },
            }
        ],
        # Shared tariff rule library (settings["tou_rules"]): the single source
        # of truth card rows reference by rule_id. Advanced direct edits are
        # validated here; the normal authoring path is the device card's
        # embedded `definition` upsert in websocket_save_room.
        vol.Optional("tou_rules"): [
            {
                vol.Required("id"): str,
                **_TOU_RULE_DEF_FIELDS,
            }
        ],
    }
)
@websocket_api.async_response
async def websocket_save_settings(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict,
) -> None:
    """Save global settings (partial merge)."""
    store = hass.data[DOMAIN]["store"]
    changes: dict = {}
    for key in _SETTINGS_SAVE_FIELDS:
        if key in msg:
            changes[key] = msg[key]

    # Validate compressor groups
    groups = changes.get("compressor_groups")
    if groups:
        group_ids = [g.get("id", "") for g in groups]
        if len(group_ids) != len(set(group_ids)):
            connection.send_error(
                msg["id"],
                "duplicate_group_id",
                "Compressor group IDs must be unique",
            )
            return
        all_members: list[str] = []
        for g in groups:
            for eid in g.get("members", []):
                if not eid.startswith("climate."):
                    connection.send_error(
                        msg["id"],
                        "invalid_member",
                        f"Compressor group member '{eid}' is not a climate entity",
                    )
                    return
            all_members.extend(g.get("members", []))
        if len(all_members) != len(set(all_members)):
            connection.send_error(
                msg["id"],
                "duplicate_member",
                "A climate entity cannot be in multiple compressor groups",
            )
            return

        # Validate master_entity and action_script fields
        all_masters: list[str] = []
        for g in groups:
            master = g.get("master_entity", "")
            if master:
                if not master.startswith("climate."):
                    connection.send_error(
                        msg["id"],
                        "invalid_master_entity",
                        f"Master entity '{master}' must be a climate entity",
                    )
                    return
                if master in g.get("members", []):
                    connection.send_error(
                        msg["id"],
                        "master_in_members",
                        f"Master entity '{master}' cannot also be a group member",
                    )
                    return
                if master in all_members:
                    connection.send_error(
                        msg["id"],
                        "master_is_other_member",
                        f"Master entity '{master}' is a member of another group",
                    )
                    return
                all_masters.append(master)
            script = g.get("action_script", "")
            if script and not script.startswith("script."):
                connection.send_error(
                    msg["id"],
                    "invalid_action_script",
                    f"Action script '{script}' must be a script entity",
                )
                return
        if len(all_masters) != len(set(all_masters)):
            connection.send_error(
                msg["id"],
                "duplicate_master",
                "A master entity cannot be assigned to multiple groups",
            )
            return

    # Tariff window rows: wall-clock format and weekday names. Rates map to
    # tiers through the cost thresholds inside the engine; rows that cannot
    # classify stay inert rather than guessing, so only shape is validated.
    windows = changes.get("tou_rate_windows")
    if windows:
        for w in windows:
            for key in ("start", "end"):
                raw = str(w.get(key) or "")
                if not raw:
                    continue
                parts = raw.split(":")
                ok = (
                    len(parts) >= 2
                    and parts[0].isdigit()
                    and parts[1].isdigit()
                    and 0 <= int(parts[0]) <= 23
                    and 0 <= int(parts[1]) <= 59
                )
                if not ok:
                    connection.send_error(
                        msg["id"],
                        "invalid_tou_window_time",
                        f"Tariff windows need '{key}' as 'HH:MM'",
                    )
                    return
            bad = [d for d in (w.get("days") or []) if d not in TOU_WEEKDAYS]
            if bad:
                connection.send_error(
                    msg["id"],
                    "invalid_tou_window_days",
                    f"Tariff window days must be weekday names, not {bad}",
                )
                return

    # Shared tariff rule library direct edit: unique ids and names, coherent
    # definitions. Pruning stays on the room channels, so rules pre-seeded
    # through this path survive until the first card save claims (or drops) them.
    rules = changes.get("tou_rules")
    if rules is not None:
        rule_ids = [str(r.get("id", "")) for r in rules]
        if len(rule_ids) != len(set(rule_ids)):
            connection.send_error(msg["id"], "duplicate_tou_rule_id", "Tariff rule IDs must be unique")
            return
        rule_names = [str(r.get("name", "")).strip() for r in rules]
        if len(rule_names) != len(set(rule_names)):
            connection.send_error(msg["id"], "duplicate_tou_rule_name", "Tariff rule names must be unique")
            return
        for r in rules:
            err = _tou_rule_def_error(r)
            if err:
                connection.send_error(msg["id"], "invalid_tou_rule", err)
                return

    # Tariff schedules: value/lead/clock/until/between checks.
    schedules = changes.get("tou_schedules")
    if schedules is not None:
        sched_ids = [s.get("id", "") for s in schedules]
        if len(sched_ids) != len(set(sched_ids)):
            connection.send_error(msg["id"], "duplicate_tou_schedule_id", "Schedule IDs must be unique")
            return
        for s in schedules:
            phase, until = s.get("phase", "after"), s.get("until", "window")
            minutes = int(s.get("minutes") or 0)
            if (phase == "before" or until == "minutes") and not (
                TOU_SCHEDULE_MINUTES_MIN <= minutes <= TOU_SCHEDULE_MINUTES_MAX
            ):
                connection.send_error(
                    msg["id"],
                    "invalid_tou_schedule",
                    f"Schedule lead/duration needs {TOU_SCHEDULE_MINUTES_MIN}-{TOU_SCHEDULE_MINUTES_MAX} minutes",
                )
                return
            if until == "clock" and not _hhmm_ok(str(s.get("clock") or "")):
                connection.send_error(msg["id"], "invalid_tou_schedule", "Clock schedules need 'HH:MM'")
                return
            if until == "next_tier_change" and s.get("until_tier") not in TOU_TIERS:
                connection.send_error(msg["id"], "invalid_tou_schedule", "next_tier_change needs a known tier")
                return
            between = s.get("between")
            if between and not (_hhmm_ok(str(between.get("from") or "")) and _hhmm_ok(str(between.get("to") or ""))):
                connection.send_error(msg["id"], "invalid_tou_schedule", "'between' needs 'HH:MM' values")
                return
            value = s.get("value") or {}
            mode = value.get("mode")
            if mode in ("set", "arrive"):
                temp = value.get("temp")
                if not isinstance(temp, (int, float)) or not (
                    TOU_SCHEDULE_TEMP_MIN <= float(temp) <= TOU_SCHEDULE_TEMP_MAX
                ):
                    connection.send_error(
                        msg["id"],
                        "invalid_tou_schedule",
                        f"'{mode}' needs a temp {TOU_SCHEDULE_TEMP_MIN:g}-{TOU_SCHEDULE_TEMP_MAX:g}",
                    )
                    return
            elif mode in ("comfort", "eco"):
                # Named targets (PR-06 / S7): no payload of their own — they
                # resolve against each room's configured values at apply
                # time, exactly like the card-authored rule sides do.
                pass
            else:
                delta = value.get("delta")
                if (
                    not isinstance(delta, (int, float))
                    or not (TOU_SCHEDULE_SHIFT_MIN <= abs(float(delta)) <= TOU_SCHEDULE_SHIFT_MAX)
                    or value.get("direction") not in TOU_SHIFT_DIRECTIONS
                ):
                    connection.send_error(
                        msg["id"], "invalid_tou_schedule", "'shift' needs direction and a delta 0.5-8"
                    )
                    return

    settings = await store.async_save_settings(changes)
    connection.send_result(msg["id"], {"settings": settings})
    coordinator = _get_coordinator(hass)
    if "climate_control_active" in changes and coordinator:
        # Stop or resume control now, which also updates switch.roommind_climate_control (#291).
        await coordinator.async_request_refresh()


# ---------------------------------------------------------------------------
# Tariff schedule preview (rule editor: tier bands, windows, fire counts)
# ---------------------------------------------------------------------------


@websocket_api.websocket_command(
    {
        vol.Required("type"): "roommind/tou/preview",
        vol.Optional("area_id"): str,
    }
)
@websocket_api.async_response
async def websocket_tou_preview(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict,
) -> None:
    """Return compiled tariff windows + tier segments for the rule editor."""
    store = hass.data[DOMAIN]["store"]
    coordinator = _get_coordinator(hass)
    manager = getattr(coordinator, "_tou_manager", None) if coordinator else None
    preview = (
        manager.preview(store.get_settings(), msg.get("area_id"), store.get_rooms()) if manager is not None else None
    )
    connection.send_result(msg["id"], {"preview": preview or {"segments": [], "areas": {}, "records": {}}})


# ---------------------------------------------------------------------------
# Target temperature forecast (for analytics chart)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Get analytics data
# ---------------------------------------------------------------------------


@websocket_api.websocket_command(
    {
        vol.Required("type"): "roommind/analytics/get",
        vol.Required("area_id"): str,
        vol.Optional("range"): vol.In(["12h", "24h", "2d", "7d", "14d", "30d", "90d"]),
        vol.Optional("start_ts"): vol.Coerce(float),
        vol.Optional("end_ts"): vol.Coerce(float),
    }
)
@websocket_api.async_response
async def websocket_get_analytics(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict,
) -> None:
    """Return analytics data for a room."""
    store = hass.data[DOMAIN]["store"]
    coordinator = _get_coordinator(hass)
    result = await build_analytics_data(
        hass,
        msg["area_id"],
        msg.get("range", "12h"),
        store,
        coordinator,
        custom_start=msg.get("start_ts"),
        custom_end=msg.get("end_ts"),
    )
    connection.send_result(msg["id"], result)


# ---------------------------------------------------------------------------
# Reset thermal model (per room)
# ---------------------------------------------------------------------------


@websocket_api.websocket_command(
    {
        vol.Required("type"): "roommind/thermal/reset",
        vol.Required("area_id"): str,
    }
)
@websocket_api.async_response
async def websocket_thermal_reset(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict,
) -> None:
    """Reset thermal model and history for a single room."""
    store = hass.data[DOMAIN]["store"]
    area_id = msg["area_id"]
    coordinator = _get_coordinator(hass)

    # Clear learned model and residual heat tracking
    if coordinator:
        coordinator.reset_thermal_room(area_id)

    # Clear persisted thermal data
    await store.async_clear_thermal_data_room(area_id)
    await _async_drop_boost_anchors(store, [area_id])

    # Clear history CSV files
    if coordinator and coordinator.history_store:
        await hass.async_add_executor_job(coordinator.history_store.remove_room, area_id)

    connection.send_result(msg["id"], {"success": True})


# ---------------------------------------------------------------------------
# Reset thermal model (all rooms)
# ---------------------------------------------------------------------------


@websocket_api.websocket_command({vol.Required("type"): "roommind/thermal/reset_all"})
@websocket_api.async_response
async def websocket_thermal_reset_all(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict,
) -> None:
    """Reset thermal model and history for all rooms."""
    store = hass.data[DOMAIN]["store"]
    coordinator = _get_coordinator(hass)

    # Clear all learned models — replace entire manager for clean state
    room_ids: list[str] = []
    if coordinator:
        room_ids = coordinator.reset_thermal_all()

    # Clear persisted thermal data
    await store.async_clear_all_thermal_data()
    await _async_drop_boost_anchors(store)

    # Clear history CSV files for all rooms, also those without a model (outdoor areas)
    if coordinator and coordinator.history_store:
        for area_id in sorted(set(room_ids) | set(store.get_rooms())):
            await hass.async_add_executor_job(coordinator.history_store.remove_room, area_id)

    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "roommind/model/boost_learning",
        vol.Required("area_id"): str,
    }
)
@websocket_api.async_response
async def websocket_boost_learning(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict,
) -> None:
    """Boost EKF covariance for a room to accelerate re-learning."""
    store = hass.data[DOMAIN]["store"]
    coordinator = _get_coordinator(hass)
    area_id = msg["area_id"]

    if not coordinator:
        connection.send_error(msg["id"], "no_coordinator", "Coordinator not ready")
        return

    n_obs = coordinator.boost_learning(area_id)
    if n_obs is None:
        connection.send_error(msg["id"], "no_model", "Room has no learned model yet")
        return

    # The frontend counts the fade from this anchor
    settings = store.get_settings()
    boost_applied = dict(settings.get("boost_applied_at", {}))
    boost_applied[area_id] = n_obs
    await store.async_save_settings({"boost_applied_at": boost_applied})

    connection.send_result(msg["id"], {"success": True, "n_observations": n_obs})


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


@websocket_api.websocket_command({vol.Required("type"): "roommind/diagnostics/get"})
@websocket_api.async_response
async def websocket_get_diagnostics(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Return full integration diagnostics via WebSocket."""
    from .diagnostics import async_get_config_entry_diagnostics

    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        connection.send_error(msg["id"], "not_found", "No config entry found")
        return
    result = await async_get_config_entry_diagnostics(hass, entries[0])
    connection.send_result(msg["id"], result)


# ---------------------------------------------------------------------------
# Clear cover user override
# ---------------------------------------------------------------------------


@websocket_api.websocket_command(
    {
        vol.Required("type"): "roommind/covers/clear_override",
        vol.Required("area_id"): str,
    }
)
@websocket_api.async_response
async def websocket_covers_clear_override(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict,
) -> None:
    """Clear a user cover override so automatic cover control resumes."""
    store = hass.data[DOMAIN]["store"]
    area_id = msg["area_id"]
    if store.get_room(area_id) is None:
        connection.send_error(msg["id"], "not_found", f"Room '{area_id}' not found")
        return

    coordinator = _get_coordinator(hass)
    if coordinator:
        coordinator.clear_cover_override(area_id)
        await coordinator.async_request_refresh()

    connection.send_result(msg["id"], {"success": True})


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


@callback
def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register all RoomMind WebSocket commands."""
    websocket_api.async_register_command(hass, websocket_list_rooms)
    websocket_api.async_register_command(hass, websocket_save_room)
    websocket_api.async_register_command(hass, websocket_delete_room)
    websocket_api.async_register_command(hass, websocket_override_set)
    websocket_api.async_register_command(hass, websocket_override_clear)
    websocket_api.async_register_command(hass, websocket_get_settings)
    websocket_api.async_register_command(hass, websocket_save_settings)
    websocket_api.async_register_command(hass, websocket_tou_preview)
    websocket_api.async_register_command(hass, websocket_get_analytics)
    websocket_api.async_register_command(hass, websocket_thermal_reset)
    websocket_api.async_register_command(hass, websocket_thermal_reset_all)
    websocket_api.async_register_command(hass, websocket_boost_learning)
    websocket_api.async_register_command(hass, websocket_get_diagnostics)
    websocket_api.async_register_command(hass, websocket_covers_clear_override)
