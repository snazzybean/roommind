"""WebSocket API for RoomMind room CRUD operations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import time

_LOGGER = logging.getLogger(__name__)

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import (
    CLIMATE_MODES,
    DEFAULT_COMFORT_COOL,
    DEFAULT_COMFORT_HEAT,
    DEFAULT_ECO_COOL,
    DEFAULT_ECO_HEAT,
    DOMAIN,
    OVERRIDE_TYPES,
    build_override_live,
)
from .services.analytics_service import (
    _csv_to_points,
    _safe_float,
    build_analytics_data,
    _compute_target_forecast,
)
from .control.thermal_model import RoomModelManager

if TYPE_CHECKING:
    from homeassistant.components.websocket_api import ActiveConnection
    from .coordinator import RoomMindCoordinator


def _get_coordinator(hass: HomeAssistant) -> RoomMindCoordinator | None:
    """Return the RoomMindCoordinator from hass.data, or None."""
    return hass.data.get(DOMAIN, {}).get("coordinator")


_ROOM_SAVE_FIELDS = (
    "thermostats", "acs", "temperature_sensor", "humidity_sensor",
    "climate_mode", "schedules", "schedule_selector_entity",
    "window_sensors", "window_open_delay", "window_close_delay",
    "comfort_temp", "eco_temp",
    "comfort_heat", "comfort_cool", "eco_heat", "eco_cool",
    "presence_persons", "display_name",
    "heating_system_type",
    "covers", "covers_auto_enabled", "covers_deploy_threshold",
    "covers_min_position", "covers_outdoor_min_temp", "covers_override_minutes",
    "cover_schedules", "cover_schedule_selector_entity",
    "covers_night_close", "covers_night_position",
)

_SETTINGS_SAVE_FIELDS = (
    "outdoor_temp_sensor", "outdoor_humidity_sensor",
    "outdoor_cooling_min", "outdoor_heating_max",
    "control_mode", "comfort_weight", "weather_entity",
    "climate_control_active", "learning_disabled_rooms", "hidden_rooms",
    "vacation_temp", "vacation_until", "prediction_enabled",
    "presence_enabled", "presence_persons", "presence_away_action",
    "schedule_off_action",
    "valve_protection_enabled", "valve_protection_interval_days",
    "mold_detection_enabled", "mold_humidity_threshold",
    "mold_sustained_minutes", "mold_notification_cooldown",
    "mold_notifications_enabled", "mold_notification_targets",
    "mold_prevention_enabled", "mold_prevention_intensity",
    "mold_prevention_notify_enabled", "mold_prevention_notify_targets",
    "room_order", "group_by_floor",
)



# _safe_float, _csv_to_points and _compute_target_forecast are imported from
# .services.analytics_service (see imports above) and re-exported so that
# existing callers (incl. tests) keep working.


def _compute_anyone_home(hass, settings):
    """Return True if at least one tracked person is home (or fail-safe)."""
    from .utils.presence_utils import is_presence_away
    return not is_presence_away(hass, {}, settings)  # all away


# ---------------------------------------------------------------------------
# List rooms
# ---------------------------------------------------------------------------

@websocket_api.websocket_command(
    {vol.Required("type"): "roommind/rooms/list"}
)
@websocket_api.async_response
async def websocket_list_rooms(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict,
) -> None:
    """Return all rooms with current state."""
    store = hass.data[DOMAIN]["store"]
    rooms = store.get_rooms()

    # Merge live state from coordinator
    coordinator = _get_coordinator(hass)
    # If coordinator has no data yet but rooms exist, trigger an immediate refresh
    if coordinator and rooms and not coordinator.rooms:
        await coordinator.async_request_refresh()
    live_states = coordinator.rooms if coordinator else {}

    # Build response: config + live state per room
    # Override fields are computed from the store (always up-to-date) rather
    # than from the coordinator (which refreshes on a 10s cycle).
    result = {}
    for area_id, room_config in rooms.items():
        room_data = dict(room_config)
        live = live_states.get(area_id, {})

        room_data["live"] = {
            "current_temp": live.get("current_temp"),
            "current_humidity": live.get("current_humidity"),
            "target_temp": live.get("target_temp"),
            "heat_target": live.get("heat_target"),
            "cool_target": live.get("cool_target"),
            "mode": live.get("mode", "idle"),
            "heating_power": live.get("heating_power", 0),
            "trv_setpoint": live.get("trv_setpoint"),
            "window_open": live.get("window_open", False),
            **build_override_live(room_config),
            "active_schedule_index": live.get("active_schedule_index", -1),
            "confidence": live.get("confidence"),
            "mpc_active": live.get("mpc_active", False),
            "presence_away": live.get("presence_away", False),
            "mold_risk_level": live.get("mold_risk_level", "ok"),
            "mold_surface_rh": live.get("mold_surface_rh"),
            "mold_prevention_active": live.get("mold_prevention_active", False),
            "mold_prevention_delta": live.get("mold_prevention_delta", 0),
            "n_observations": live.get("n_observations", 0),
            "blind_position": live.get("blind_position"),
            "cover_auto_paused": live.get("cover_auto_paused", False),
            "cover_forced_reason": live.get("cover_forced_reason", ""),
            "active_cover_schedule_index": live.get("active_cover_schedule_index", -1),
        }
        result[area_id] = room_data

    # Vacation state from settings
    settings = store.get_settings()
    vacation_until = settings.get("vacation_until")
    vacation_active = bool(vacation_until and time.time() < vacation_until)

    connection.send_result(msg["id"], {
        "rooms": result,
        "outdoor_temp": coordinator.outdoor_temp if coordinator else None,
        "outdoor_humidity": coordinator.outdoor_humidity if coordinator else None,
        "vacation_active": vacation_active,
        "vacation_temp": settings.get("vacation_temp") if vacation_active else None,
        "vacation_until": vacation_until if vacation_active else None,
        "hidden_rooms": settings.get("hidden_rooms", []),
        "room_order": settings.get("room_order", []),
        "group_by_floor": settings.get("group_by_floor", False),
        "control_mode": settings.get("control_mode", "bangbang"),
        "climate_control_active": settings.get("climate_control_active", True),
        "presence_enabled": settings.get("presence_enabled", False),
        "presence_persons": settings.get("presence_persons", []),
        "presence_away_action": settings.get("presence_away_action", "eco"),
        "schedule_off_action": settings.get("schedule_off_action", "eco"),
        "anyone_home": _compute_anyone_home(hass, settings),
    })


# ---------------------------------------------------------------------------
# Save room (upsert: create or update)
# ---------------------------------------------------------------------------

@websocket_api.websocket_command(
    {
        vol.Required("type"): "roommind/rooms/save",
        vol.Required("area_id"): str,
        vol.Optional("thermostats"): [str],
        vol.Optional("acs"): [str],
        vol.Optional("temperature_sensor"): str,
        vol.Optional("humidity_sensor"): str,
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
        vol.Optional("heating_system_type"): vol.In(
            ["", "radiator", "underfloor"]
        ),
        vol.Optional("covers"): [str],
        vol.Optional("covers_auto_enabled"): bool,
        vol.Optional("covers_deploy_threshold"): vol.All(vol.Coerce(float), vol.Range(min=0)),
        vol.Optional("covers_min_position"): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=99)
        ),
        vol.Optional("covers_outdoor_min_temp"): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0, max=35))
        ),
        vol.Optional("covers_override_minutes"): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=480)
        ),
        vol.Optional("cover_schedules"): [
            {
                vol.Required("entity_id"): str,
            }
        ],
        vol.Optional("cover_schedule_selector_entity"): str,
        vol.Optional("covers_night_close"): bool,
        vol.Optional("covers_night_position"): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=100)
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

    room = await store.async_save_room(area_id, config)

    # Notify coordinator to create/update sensor entities for the room
    coordinator = _get_coordinator(hass)
    if coordinator:
        await coordinator.async_room_added(room)

    connection.send_result(msg["id"], {"room": room})


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
    store = hass.data[DOMAIN]["store"]
    area_id = msg["area_id"]

    try:
        await store.async_delete_room(area_id)
    except KeyError:
        connection.send_error(
            msg["id"], "not_found", f"Room '{area_id}' not found"
        )
        return

    # Notify coordinator to remove sensor entities for the deleted room
    coordinator = _get_coordinator(hass)
    if coordinator:
        await coordinator.async_room_removed(area_id)

    connection.send_result(msg["id"], {"success": True})


# ---------------------------------------------------------------------------
# Set override
# ---------------------------------------------------------------------------

@websocket_api.websocket_command(
    {
        vol.Required("type"): "roommind/override/set",
        vol.Required("area_id"): str,
        vol.Required("override_type"): vol.In(OVERRIDE_TYPES),
        vol.Optional("temperature"): vol.Coerce(float),
        vol.Required("duration"): vol.Coerce(float),  # hours
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
    duration_hours = msg["duration"]

    room = store.get_room(area_id)
    if room is None:
        connection.send_error(msg["id"], "not_found", f"Room '{area_id}' not found")
        return

    # Resolve override temperature
    if override_type == "boost":
        climate_mode = room.get("climate_mode", "auto")
        if climate_mode == "cool_only":
            override_temp = room.get("comfort_cool", DEFAULT_COMFORT_COOL)
        else:
            override_temp = room.get("comfort_heat", room.get("comfort_temp", DEFAULT_COMFORT_HEAT))
    elif override_type == "eco":
        climate_mode = room.get("climate_mode", "auto")
        if climate_mode == "cool_only":
            override_temp = room.get("eco_cool", DEFAULT_ECO_COOL)
        else:
            override_temp = room.get("eco_heat", room.get("eco_temp", DEFAULT_ECO_HEAT))
    else:  # custom
        override_temp = msg.get("temperature")
        if override_temp is None:
            connection.send_error(msg["id"], "invalid", "Custom override requires temperature")
            return

    override_until = time.time() + duration_hours * 3600

    await store.async_update_room(area_id, {
        "override_temp": override_temp,
        "override_until": override_until,
        "override_type": override_type,
    })

    coordinator = _get_coordinator(hass)
    if coordinator:
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

    await store.async_update_room(area_id, {
        "override_temp": None,
        "override_until": None,
        "override_type": None,
    })

    coordinator = _get_coordinator(hass)
    if coordinator:
        await coordinator.async_request_refresh()

    connection.send_result(msg["id"], {"success": True})


# ---------------------------------------------------------------------------
# Get settings
# ---------------------------------------------------------------------------

@websocket_api.websocket_command(
    {vol.Required("type"): "roommind/settings/get"}
)
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
        vol.Optional("control_mode"): vol.In(["mpc", "bangbang"]),
        vol.Optional("comfort_weight"): vol.Coerce(float),
        vol.Optional("weather_entity"): str,
        vol.Optional("climate_control_active"): bool,
        vol.Optional("learning_disabled_rooms"): [str],
        vol.Optional("hidden_rooms"): [str],
        vol.Optional("prediction_enabled"): bool,
        vol.Optional("vacation_temp"): vol.Coerce(float),
        vol.Optional("vacation_until"): vol.Any(vol.Coerce(float), None),
        vol.Optional("presence_enabled"): bool,
        vol.Optional("presence_persons"): [str],
        vol.Optional("presence_away_action"): vol.In(["eco", "off"]),
        vol.Optional("schedule_off_action"): vol.In(["eco", "off"]),
        vol.Optional("valve_protection_enabled"): bool,
        vol.Optional("valve_protection_interval_days"): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=90)
        ),
        vol.Optional("mold_detection_enabled"): bool,
        vol.Optional("mold_humidity_threshold"): vol.All(
            vol.Coerce(float), vol.Range(min=50, max=90)
        ),
        vol.Optional("mold_sustained_minutes"): vol.All(
            vol.Coerce(int), vol.Range(min=5, max=120)
        ),
        vol.Optional("mold_notification_cooldown"): vol.All(
            vol.Coerce(int), vol.Range(min=10, max=1440)
        ),
        vol.Optional("mold_notifications_enabled"): bool,
        vol.Optional("mold_notification_targets"): [
            {
                vol.Required("entity_id"): str,
                vol.Optional("person_entity", default=""): str,
                vol.Optional("notify_when", default="always"): vol.In(
                    ["always", "home_only"]
                ),
            }
        ],
        vol.Optional("mold_prevention_enabled"): bool,
        vol.Optional("mold_prevention_intensity"): vol.In(
            ["light", "medium", "strong"]
        ),
        vol.Optional("mold_prevention_notify_enabled"): bool,
        vol.Optional("mold_prevention_notify_targets"): [
            {
                vol.Required("entity_id"): str,
                vol.Optional("person_entity", default=""): str,
                vol.Optional("notify_when", default="always"): vol.In(
                    ["always", "home_only"]
                ),
            }
        ],
        vol.Optional("room_order"): [str],
        vol.Optional("group_by_floor"): bool,
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
    settings = await store.async_save_settings(changes)
    connection.send_result(msg["id"], {"settings": settings})


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
        hass, msg["area_id"], msg.get("range", "12h"),
        store, coordinator,
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
        coordinator._model_manager.remove_room(area_id)
        coordinator._last_temps.pop(area_id, None)
        coordinator._residual_tracker.clear_room(area_id)

    # Clear persisted thermal data
    await store.async_clear_thermal_data_room(area_id)

    # Clear history CSV files
    if coordinator and coordinator._history_store:
        await hass.async_add_executor_job(coordinator._history_store.remove_room, area_id)

    connection.send_result(msg["id"], {"success": True})


# ---------------------------------------------------------------------------
# Reset thermal model (all rooms)
# ---------------------------------------------------------------------------

@websocket_api.websocket_command(
    {vol.Required("type"): "roommind/thermal/reset_all"}
)
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
        room_ids = list(coordinator._model_manager._estimators.keys())
        coordinator._model_manager = RoomModelManager()
        coordinator._last_temps.clear()
        coordinator._residual_tracker.clear_all()

    # Clear persisted thermal data
    await store.async_clear_all_thermal_data()

    # Clear history CSV files for all rooms
    if coordinator and coordinator._history_store:
        for area_id in room_ids:
            await hass.async_add_executor_job(coordinator._history_store.remove_room, area_id)

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

    n_obs = coordinator._model_manager.boost_learning(area_id)

    # Persist cooldown anchor in settings
    settings = store.get_settings()
    boost_applied = dict(settings.get("boost_applied_at", {}))
    boost_applied[area_id] = n_obs
    await store.async_save_settings({"boost_applied_at": boost_applied})

    connection.send_result(msg["id"], {"success": True, "n_observations": n_obs})


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
    websocket_api.async_register_command(hass, websocket_get_analytics)
    websocket_api.async_register_command(hass, websocket_thermal_reset)
    websocket_api.async_register_command(hass, websocket_thermal_reset_all)
    websocket_api.async_register_command(hass, websocket_boost_learning)
