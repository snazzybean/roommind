"""Diagnostics support for RoomMind."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, VERSION


def _build_model_info(estimator) -> dict:
    """Build model diagnostics from a ThermalEKF estimator."""
    rc = estimator.get_model()
    return {
        "alpha": round(estimator._x[1], 6),
        "beta_h": round(estimator._x[2], 4),
        "beta_c": round(estimator._x[3], 4),
        "n_updates": estimator._n_updates,
        "n_idle": estimator._n_idle,
        "n_heating": estimator._n_heating,
        "n_cooling": estimator._n_cooling,
        "applicable_modes": sorted(estimator._applicable_modes),
        "P_diagonal": [round(estimator._P[i][i], 6) for i in range(5)],
        "prediction_std_idle": round(estimator.prediction_std(0.0, 20.0, 15.0, 5.0), 4),
        "prediction_std_heating": round(estimator.prediction_std(rc.Q_heat, 20.0, 10.0, 5.0), 4),
        "confidence": round(estimator.confidence, 4),
        "model_params": rc.to_dict(),
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = hass.data.get(DOMAIN, {})
    store = data.get("store")
    coordinator = data.get("coordinator")

    if not store:
        return {"error": "Integration not loaded"}

    settings = store.get_settings()
    rooms_config = store.get_rooms()
    live_states = coordinator.rooms if coordinator else {}

    # Build per-room diagnostics
    rooms_diag: dict[str, dict] = {}
    for area_id, config in rooms_config.items():
        live = live_states.get(area_id, {})
        room_diag: dict[str, Any] = {
            "config": dict(config),
            "live": {
                "current_temp": live.get("current_temp"),
                "current_humidity": live.get("current_humidity"),
                "target_temp": live.get("target_temp"),
                "mode": live.get("mode", "idle"),
                "window_open": live.get("window_open", False),
                "mpc_active": live.get("mpc_active", False),
                "confidence": live.get("confidence"),
                "presence_away": live.get("presence_away", False),
            },
        }

        # Model info from EKF estimator
        if coordinator:
            mgr = coordinator._model_manager
            if area_id in mgr._estimators:
                room_diag["model"] = _build_model_info(mgr._estimators[area_id])

        rooms_diag[area_id] = room_diag

    # Outdoor conditions
    outdoor: dict[str, Any] = {
        "temp": coordinator.outdoor_temp if coordinator else None,
        "humidity": coordinator.outdoor_humidity if coordinator else None,
    }
    if coordinator:
        forecast = coordinator._outdoor_forecast
        outdoor["forecast_available"] = bool(forecast)
        outdoor["forecast_points"] = len(forecast) if forecast else 0

    # Recent history (last 2 hours of detail data per room)
    recent_history: dict[str, list] = {}
    if coordinator and coordinator._history_store:
        for area_id in rooms_config:
            try:
                rows = await hass.async_add_executor_job(
                    coordinator._history_store.read_detail, area_id, 7200
                )
                recent_history[area_id] = [
                    {
                        "ts": row.get("timestamp", ""),
                        "room_temp": row.get("room_temp", ""),
                        "outdoor_temp": row.get("outdoor_temp", ""),
                        "target_temp": row.get("target_temp", ""),
                        "mode": row.get("mode", ""),
                        "predicted_temp": row.get("predicted_temp", ""),
                    }
                    for row in rows[-240:]  # Cap at ~240 points
                ]
            except Exception:  # noqa: BLE001
                recent_history[area_id] = []

    return {
        "integration": {
            "version": VERSION,
            "domain": DOMAIN,
        },
        "settings": dict(settings),
        "rooms": rooms_diag,
        "outdoor": outdoor,
        "recent_history": recent_history,
        "presence": {
            "enabled": settings.get("presence_enabled", False),
            "persons": settings.get("presence_persons", []),
            "person_states": {
                pid: (hass.states.get(pid).state if hass.states.get(pid) else "unavailable")
                for pid in settings.get("presence_persons", [])
            },
        },
    }
