"""WebSocket API for RoomMind room CRUD operations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import math
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
from .mpc_controller import DEFAULT_OUTDOOR_TEMP_FALLBACK, check_acs_can_heat, get_can_heat_cool, is_mpc_active
from .thermal_model import RoomModelManager

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


def _safe_float(value: str) -> float | None:
    """Convert CSV string to float, or None for empty/invalid values."""
    if not value:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _csv_to_points(rows: list[dict]) -> list[dict]:
    """Convert CSV rows (string values, 'timestamp' key) to typed points ('ts' key)."""
    result = []
    for row in rows:
        ts = _safe_float(row.get("timestamp", ""))
        if ts is None:
            continue
        result.append({
            "ts": ts,
            "room_temp": _safe_float(row.get("room_temp", "")),
            "outdoor_temp": _safe_float(row.get("outdoor_temp", "")),
            "target_temp": _safe_float(row.get("target_temp", "")),
            "mode": row.get("mode", ""),
            "predicted_temp": _safe_float(row.get("predicted_temp", "")),
            "window_open": row.get("window_open", "") in ("True", "true", "1"),
            "heating_power": _safe_float(row.get("heating_power", "")),
        })
    return result


def _compute_anyone_home(hass, settings):
    """Return True if at least one tracked person is home (or fail-safe)."""
    from .presence_utils import is_presence_away
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

async def _compute_target_forecast(
    hass: HomeAssistant,
    room: dict,
    settings: dict,
    mold_prevention_delta: float = 0.0,
    hours: float = 3.0,
    interval_minutes: int = 5,
) -> list[dict]:
    """Compute target temperature forecast for the next N hours.

    Each point contains ``target_temp`` (chart display, mode-aware),
    ``heat_target`` and ``cool_target`` (for MPC simulator).
    """
    from .const import (
        CLIMATE_MODE_COOL_ONLY,
        CLIMATE_MODE_HEAT_ONLY,
        DEFAULT_COMFORT_COOL,
        DEFAULT_COMFORT_HEAT,
        DEFAULT_ECO_COOL,
        DEFAULT_ECO_HEAT,
    )
    from .presence_utils import is_presence_away
    from .schedule_utils import (
        get_active_schedule_entity,
        read_schedule_blocks,
        resolve_targets_at_time,
    )
    from .temp_utils import ha_temp_to_celsius

    comfort_heat = room.get("comfort_heat", room.get("comfort_temp", DEFAULT_COMFORT_HEAT))
    comfort_cool = room.get("comfort_cool", DEFAULT_COMFORT_COOL)
    eco_heat = room.get("eco_heat", room.get("eco_temp", DEFAULT_ECO_HEAT))
    eco_cool = room.get("eco_cool", DEFAULT_ECO_COOL)
    override_until = room.get("override_until")
    override_temp = room.get("override_temp")
    vacation_until = settings.get("vacation_until")
    vacation_temp = settings.get("vacation_temp")
    climate_mode = room.get("climate_mode", "auto")

    presence_away = is_presence_away(hass, room, settings)

    entity_id = get_active_schedule_entity(hass, room)
    schedule_blocks = await read_schedule_blocks(hass, entity_id) if entity_id else None

    _hass = hass
    converter = lambda v: ha_temp_to_celsius(_hass, v)  # noqa: E731

    # Generate forecast points
    now = time.time()
    end_ts = now + hours * 3600
    result: list[dict] = []
    ts = now
    while ts <= end_ts:
        targets = resolve_targets_at_time(
            ts, schedule_blocks,
            override_until, override_temp,
            vacation_until, vacation_temp,
            comfort_heat, comfort_cool,
            eco_heat, eco_cool,
            presence_away=presence_away,
            block_temp_converter=converter,
            presence_away_action=settings.get("presence_away_action", "eco"),
            schedule_off_action=settings.get("schedule_off_action", "eco"),
        )
        heat_target = targets.heat
        cool_target = targets.cool

        # Apply mold prevention delta to heat target only
        if heat_target is not None:
            heat_target = round(heat_target + mold_prevention_delta, 1)
        elif mold_prevention_delta > 0:
            heat_target = round(eco_heat + mold_prevention_delta, 1)

        # Chart display: mode-aware single value
        if climate_mode == CLIMATE_MODE_COOL_ONLY:
            target = cool_target
        elif climate_mode == CLIMATE_MODE_HEAT_ONLY:
            target = heat_target
        else:
            # Auto mode: show heat target (primary for chart line)
            target = heat_target

        result.append({
            "ts": round(ts, 1),
            "target_temp": target,
            "heat_target": heat_target,
            "cool_target": cool_target,
        })
        ts += interval_minutes * 60
    return result


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
    area_id = msg["area_id"]
    range_key = msg.get("range", "12h")
    custom_start = msg.get("start_ts")
    custom_end = msg.get("end_ts")
    store = hass.data[DOMAIN]["store"]
    settings = store.get_settings()
    coordinator = _get_coordinator(hass)
    history_store = getattr(coordinator, "_history_store", None)

    # Read history data — custom timestamps take precedence over range preset
    detail: list = []
    history: list = []
    if history_store:
        if custom_start is not None:
            detail = _csv_to_points(
                await hass.async_add_executor_job(
                    history_store.read_detail, area_id, None, custom_start, custom_end
                )
            )
            history = _csv_to_points(
                await hass.async_add_executor_job(
                    history_store.read_history, area_id, None, custom_start, custom_end
                )
            )
        else:
            max_age_map = {
                "12h": 43200,
                "24h": 86400,
                "2d": 172800,
                "7d": 604800,
                "14d": 1209600,
                "30d": 2592000,
                "90d": 7776000,
            }
            max_age = max_age_map.get(range_key, 43200)
            detail = _csv_to_points(
                await hass.async_add_executor_job(history_store.read_detail, area_id, max_age)
            )
            history = _csv_to_points(
                await hass.async_add_executor_job(history_store.read_history, area_id, max_age)
            )

    # Model info (only if estimator exists — avoid auto-creating for unknown rooms)
    model_info: dict = {}
    mpc_active = False
    if coordinator:
        mgr = coordinator._model_manager
        if area_id in mgr._estimators:
            est = mgr._estimators[area_id]
            rc = est.get_model()
            pred_std_idle = est.prediction_std(0.0, 20.0, 15.0, 5.0)
            pred_std_heat = est.prediction_std(rc.Q_heat, 20.0, 10.0, 5.0)
            room_config = store.get_room(area_id) or {}
            has_ext_sensor = bool(room_config.get("temperature_sensor"))
            if has_ext_sensor:
                can_heat, can_cool = get_can_heat_cool(room_config, coordinator.outdoor_temp, acs_can_heat=check_acs_can_heat(hass, room_config))
                T_out = coordinator.outdoor_temp if coordinator.outdoor_temp is not None else DEFAULT_OUTDOOR_TEMP_FALLBACK
                mpc_active = is_mpc_active(mgr, area_id, can_heat, can_cool, 20.0, T_out)
            else:
                mpc_active = False
            # EKF uncertainty: sqrt(P[0][0]) as proxy for sigma_e
            sigma_proxy = math.sqrt(max(est._P[0][0], 0.0))
            model_info = {
                "confidence": est.confidence,
                "model": rc.to_dict(),
                "n_samples": est._n_updates,
                "n_observations": est._n_updates,
                "n_heating": est._n_heating,
                "n_cooling": est._n_cooling,
                "applicable_modes": sorted(est._applicable_modes),
                "mpc_active": mpc_active,
                "sigma_e": round(sigma_proxy, 4),
                "prediction_std_idle": round(pred_std_idle, 4),
                "prediction_std_heating": round(pred_std_heat, 4),
            }

    # Build merged forecast: same format as history points, on a shared 5-min grid
    room_config = store.get_room(area_id) or {}
    mold_delta = 0.0
    if coordinator:
        live = coordinator.rooms.get(area_id, {})
        mold_delta = live.get("mold_prevention_delta", 0.0)
    try:
        target_forecast = await _compute_target_forecast(
            hass, room_config, settings, mold_prevention_delta=mold_delta,
        )
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Target forecast computation failed for '%s'", area_id)
        target_forecast = []

    # Forward-simulate temperature prediction for the forecast period.
    from .analytics_simulator import build_forecast_outdoor_series, build_forecast_solar_series, simulate_prediction

    pred_temps: list[float | None] = []
    prediction_enabled = settings.get("prediction_enabled", True)
    if prediction_enabled and target_forecast and coordinator:
        mgr = coordinator._model_manager
        if area_id in mgr._estimators:
            model = mgr.get_model(area_id)
            est = mgr._estimators[area_id]
            all_points = detail if detail else history
            current_t: float | None = None
            for p in reversed(all_points):
                if p.get("room_temp") is not None:
                    current_t = p["room_temp"]
                    break
            if current_t is not None:
                T_out_now = coordinator.outdoor_temp if coordinator.outdoor_temp is not None else DEFAULT_OUTDOOR_TEMP_FALLBACK
                outdoor_series = build_forecast_outdoor_series(
                    coordinator._outdoor_forecast, T_out_now, len(target_forecast),
                )
                solar_series = build_forecast_solar_series(
                    hass.config.latitude, hass.config.longitude,
                    coordinator._outdoor_forecast, len(target_forecast),
                )
                # Residual heat state for analytics simulation
                system_type = room_config.get("heating_system_type", "")
                sim_q_residual = 0.0
                sim_heat_dur = 0.0
                sim_last_pf = 1.0
                if system_type and area_id in getattr(coordinator, "_heating_off_since", {}):
                    import time as _time
                    off_since = coordinator._heating_off_since[area_id]
                    elapsed = (_time.time() - off_since) / 60.0
                    sim_heat_dur = (off_since - coordinator._heating_on_since.get(area_id, off_since)) / 60.0
                    sim_last_pf = coordinator._heating_off_power.get(area_id, 1.0)
                    from .residual_heat import compute_residual_heat
                    sim_q_residual = compute_residual_heat(elapsed, system_type, sim_last_pf, sim_heat_dur)

                pred_temps = simulate_prediction(
                    model=model,
                    estimator=est,
                    target_forecast=target_forecast,
                    outdoor_series=outdoor_series,
                    current_temp=current_t,
                    window_open=coordinator._window_paused.get(area_id, False),
                    mpc_active=mpc_active,
                    room_config=room_config,
                    settings=settings,
                    all_points=all_points,
                    solar_series=solar_series,
                    acs_can_heat=check_acs_can_heat(hass, room_config),
                    q_residual=sim_q_residual,
                    heating_system_type=system_type,
                    heating_duration_minutes=sim_heat_dur,
                    last_power_fraction=sim_last_pf,
                )

    # Merge into unified forecast points on shared 5-min grid
    forecast: list[dict] = []
    grid = 300  # 5 minutes
    for i, tf in enumerate(target_forecast):
        snapped = round(tf["ts"] / grid) * grid
        forecast.append({
            "ts": snapped,
            "room_temp": None,
            "outdoor_temp": None,
            "target_temp": tf["target_temp"],
            "mode": "forecast",
            "predicted_temp": pred_temps[i] if i < len(pred_temps) else None,
            "window_open": False,
        })

    connection.send_result(msg["id"], {
        "detail": detail,
        "history": history,
        "model": model_info,
        "forecast": forecast,
    })


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
        coordinator._heating_off_since.pop(area_id, None)
        coordinator._heating_off_power.pop(area_id, None)
        coordinator._heating_on_since.pop(area_id, None)

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
        coordinator._heating_off_since.clear()
        coordinator._heating_off_power.clear()
        coordinator._heating_on_since.clear()

    # Clear persisted thermal data
    await store.async_clear_all_thermal_data()

    # Clear history CSV files for all rooms
    if coordinator and coordinator._history_store:
        for area_id in room_ids:
            await hass.async_add_executor_job(coordinator._history_store.remove_room, area_id)

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
    websocket_api.async_register_command(hass, websocket_get_analytics)
    websocket_api.async_register_command(hass, websocket_thermal_reset)
    websocket_api.async_register_command(hass, websocket_thermal_reset_all)
