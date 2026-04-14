"""MPC-based climate controller for RoomMind."""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from homeassistant.core import HomeAssistant

from ..const import (
    AC_COOLING_BOOST_TARGET,
    AC_HEATING_BOOST_TARGET,
    BANGBANG_COOL_HYSTERESIS,
    BANGBANG_HEAT_HYSTERESIS,
    CLIMATE_MODE_COOL_ONLY,
    CLIMATE_MODE_HEAT_ONLY,
    DEFAULT_OUTDOOR_COOLING_MIN,
    DEFAULT_OUTDOOR_HEATING_MAX,
    HEATING_BOOST_TARGET,
    MODE_COOLING,
    MODE_HEATING,
    MODE_IDLE,
    TargetTemps,
    make_roommind_context,
)
from ..utils.device_utils import (
    DEFAULT_IDLE_SETBACK_OFFSET,
    IDLE_ACTION_FAN_ONLY,
    IDLE_ACTION_SETBACK,
    get_ac_eids,
    get_direct_setpoint_eids,
    get_idle_action,
    get_trv_eids,
    has_reliable_hvac_modes,
)
from ..utils.temp_utils import celsius_to_ha_temp
from .mpc_optimizer import MPCOptimizer, MPCPlan
from .residual_heat import get_min_run_blocks
from .thermal_model import RoomModelManager

if TYPE_CHECKING:
    from ..managers.heat_source_orchestrator import HeatSourcePlan

_LOGGER = logging.getLogger(__name__)

_SENTINEL: object = object()  # default marker for backward-compat keyword detection

# Cache of last successfully sent command per climate entity.
# Fallback for IR devices that don't report temperature attributes.
# Persists across MPCController instances (created fresh each 30s cycle),
# resets on integration reload (module reimport).
_last_commands: dict[str, dict[str, Any]] = {}
_setpoint_override_warned: set[str] = set()


def _cache_entry(service: str, data: dict) -> dict[str, Any]:
    """Build a cache entry from a service call."""
    return {
        "service": service,
        "hvac_mode": data.get("hvac_mode"),
        "temperature": data.get("temperature"),
        "target_temp_low": data.get("target_temp_low"),
        "target_temp_high": data.get("target_temp_high"),
    }


def _should_use_cache(state: Any) -> bool:
    """Return True when the sent-command cache should be trusted.

    The cache exists for IR-controlled devices that never report state changes.
    When a device has a real HVAC state (not unavailable/unknown), the device's
    actual reported state is authoritative and the cache must not suppress
    retries — a cached "off" must not prevent re-sending when the device
    clearly reports it is still heating.
    """
    if state is None:
        return True
    return state.state in ("unavailable", "unknown")


def _snap_to_step(value: float, step: float | None) -> float:
    if step is None or step <= 0:
        return value
    return round(round(value / step) * step, 2)


def clear_command_cache() -> None:
    """Clear the sent-command cache (for tests)."""
    _last_commands.clear()
    _setpoint_override_warned.clear()


def _resolve_idle_setpoint(
    state: Any,
    fallback_setpoint: float | None,
    *,
    area_id: str = "unknown",
    entity_id: str = "unknown",
) -> float | None:
    """Pick the best setpoint to idle a device.

    Returns min_temp when available (authoritative device floor),
    otherwise fallback_setpoint. Returns None if neither works.
    """
    min_temp: float | None = None
    if state:
        raw = state.attributes.get("min_temp")
        if raw is not None:
            try:
                val = float(raw)
            except (ValueError, TypeError):
                val = -1.0
            if val > 0:
                min_temp = val
            elif fallback_setpoint is None:
                _LOGGER.warning(
                    "Area '%s': device '%s' reports min_temp=%s (<= 0), "
                    "no fallback available — cannot lower setpoint (Z2M/firmware bug?)",
                    area_id,
                    entity_id,
                    raw,
                )

    return min_temp if min_temp is not None else fallback_setpoint


async def _send_idle_setpoint(
    hass: HomeAssistant,
    entity_id: str,
    state: Any,
    setpoint: float,
    *,
    area_id: str = "unknown",
) -> None:
    """Lower a device's temperature setpoint during idle. Best-effort."""
    current = state.attributes.get("temperature")
    if current is not None and round(float(current), 1) == round(setpoint, 1):
        _setpoint_override_warned.discard(entity_id)
        return

    dev_min = state.attributes.get("min_temp")
    dev_max = state.attributes.get("max_temp")
    if dev_min is not None:
        try:
            dev_min_f = float(dev_min)
            if setpoint < dev_min_f:
                setpoint = dev_min_f
        except (ValueError, TypeError):
            pass
    if dev_max is not None:
        try:
            dev_max_f = float(dev_max)
            if setpoint > dev_max_f:
                setpoint = dev_max_f
        except (ValueError, TypeError):
            pass
    if current is not None and round(float(current), 1) == round(setpoint, 1):
        return

    cached = _last_commands.get(entity_id)
    if (
        cached
        and cached.get("service") == "set_temperature"
        and cached.get("temperature") is not None
        and round(cached["temperature"], 1) == round(setpoint, 1)
        and current is not None
    ):
        if entity_id not in _setpoint_override_warned:
            _LOGGER.warning(
                "Area '%s': device '%s' setpoint is %.1f but RoomMind previously sent %.1f — "
                "an external controller may be overriding the setpoint. "
                "Check the device's own schedule/minimum temperature settings",
                area_id,
                entity_id,
                float(current),
                setpoint,
            )
            _setpoint_override_warned.add(entity_id)

    try:
        await hass.services.async_call(
            "climate",
            "set_temperature",
            {"entity_id": entity_id, "temperature": setpoint},
            blocking=True,
            context=make_roommind_context(),
        )
        _last_commands[entity_id] = _cache_entry("set_temperature", {"temperature": setpoint})
    except Exception:  # noqa: BLE001
        _LOGGER.warning(
            "Area '%s': climate.set_temperature(%.1f) failed on '%s'",
            area_id,
            setpoint,
            entity_id,
            exc_info=True,
        )


async def async_turn_off_climate(
    hass: HomeAssistant,
    entity_id: str,
    *,
    area_id: str = "unknown",
    fallback_setpoint: float | None = None,
) -> None:
    """Turn off a climate entity, falling back to min_temp for heat-only devices.

    Some TRVs (e.g. Shelly) only support hvac_modes: ["heat"] with no "off".
    For these devices, setting the temperature to min_temp effectively closes
    the valve.  For cooling-only devices without "off", max_temp is used.
    """
    state = hass.states.get(entity_id)
    hvac_modes: list[str] = (state.attributes.get("hvac_modes") or []) if state else []

    # Normal path: "off" is supported (or modes unknown → assume supported)
    if not hvac_modes or "off" in hvac_modes:
        # Permanently-off devices (e.g. Wavin Sentio): hvac_modes only contains
        # "off", meaning there is no real mode transition.  Heating is controlled
        # purely via the temperature setpoint.  Sending set_hvac_mode("off") to
        # these devices can reset the setpoint, undoing the lowering.  Only lower
        # the setpoint for these devices, never send set_hvac_mode.
        permanently_off = bool(hvac_modes) and set(hvac_modes) == {"off"}

        effective_setpoint = _resolve_idle_setpoint(
            state,
            fallback_setpoint,
            area_id=area_id,
            entity_id=entity_id,
        )

        if state and state.state == "off":
            if permanently_off and effective_setpoint is not None:
                await _send_idle_setpoint(hass, entity_id, state, effective_setpoint, area_id=area_id)
            return  # already off

        if permanently_off:
            if state and effective_setpoint is not None:
                await _send_idle_setpoint(hass, entity_id, state, effective_setpoint, area_id=area_id)
            return

        # Cache fallback for IR devices (only when device has no reliable state)
        if _should_use_cache(state):
            cached = _last_commands.get(entity_id)
            if cached and cached.get("service") == "set_hvac_mode" and cached.get("hvac_mode") == "off":
                return
        # Defense-in-depth: lower setpoint to min_temp BEFORE sending "off".
        # Some devices (e.g. Wavin AHC9000) claim "off" support but only
        # process temperature changes when in "heat" mode.  Sending the setpoint
        # first (while the device is still active) ensures the valve closes even
        # if set_hvac_mode(off) is later ignored.
        if state and effective_setpoint is not None:
            await _send_idle_setpoint(hass, entity_id, state, effective_setpoint, area_id=area_id)

        try:
            await hass.services.async_call(
                "climate",
                "set_hvac_mode",
                {"entity_id": entity_id, "hvac_mode": "off"},
                blocking=True,
                context=make_roommind_context(),
            )
            _last_commands[entity_id] = _cache_entry("set_hvac_mode", {"hvac_mode": "off"})
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "Area '%s': climate.set_hvac_mode(off) failed on '%s'",
                area_id,
                entity_id,
                exc_info=True,
            )
        return

    # Fallback: device does not support "off" → set to min_temp / max_temp
    assert state is not None  # guaranteed: hvac_modes non-empty implies state exists
    is_cooling = "cool" in hvac_modes or "heat_cool" in hvac_modes
    fallback_temp = state.attributes.get("max_temp") if is_cooling else state.attributes.get("min_temp")

    if fallback_temp is None:
        _LOGGER.warning(
            "Area '%s': device '%s' has no 'off' mode and no %s attribute, cannot turn off reliably",
            area_id,
            entity_id,
            "max_temp" if is_cooling else "min_temp",
        )
        return

    # Same guard as defense-in-depth path above: max_temp <= 0 for cooling devices
    # is equally implausible and indicates a Z2M/firmware bug.
    if float(fallback_temp) <= 0:
        _LOGGER.warning(
            "Area '%s': device '%s' reports %s=%s (<= 0), cannot use as fallback setpoint (Z2M/firmware bug?)",
            area_id,
            entity_id,
            "max_temp" if is_cooling else "min_temp",
            fallback_temp,
        )
        return

    # Redundancy: skip if already at fallback temp
    is_range = state.attributes.get("target_temp_low") is not None
    if is_range:
        cur_check = (
            state.attributes.get("target_temp_low") if not is_cooling else state.attributes.get("target_temp_high")
        )
        if cur_check is not None and round(cur_check, 1) == round(fallback_temp, 1):
            return
        if cur_check is None and _should_use_cache(state):
            cached = _last_commands.get(entity_id)
            if cached and cached.get("service") == "set_temperature":
                c_low = cached.get("target_temp_low")
                c_high = cached.get("target_temp_high")
                if (
                    c_low is not None
                    and c_high is not None
                    and round(c_low, 1) == round(fallback_temp, 1)
                    and round(c_high, 1) == round(fallback_temp, 1)
                ):
                    return
        svc_data: dict = {"entity_id": entity_id, "target_temp_low": fallback_temp, "target_temp_high": fallback_temp}
    else:
        current_temp_setting = state.attributes.get("temperature")
        if current_temp_setting is not None and round(current_temp_setting, 1) == round(fallback_temp, 1):
            return
        if current_temp_setting is None and _should_use_cache(state):
            cached = _last_commands.get(entity_id)
            if (
                cached
                and cached.get("service") == "set_temperature"
                and cached.get("temperature") is not None
                and round(cached["temperature"], 1) == round(fallback_temp, 1)
            ):
                return
        svc_data = {"entity_id": entity_id, "temperature": fallback_temp}

    _LOGGER.debug(
        "Area '%s': device '%s' has no 'off' mode, setting temperature to %s as fallback",
        area_id,
        entity_id,
        fallback_temp,
    )
    try:
        await hass.services.async_call(
            "climate",
            "set_temperature",
            svc_data,
            blocking=True,
            context=make_roommind_context(),
        )
        _last_commands[entity_id] = _cache_entry("set_temperature", svc_data)
    except Exception:  # noqa: BLE001
        _LOGGER.warning(
            "Area '%s': climate.set_temperature(%s) fallback failed on '%s'",
            area_id,
            fallback_temp,
            entity_id,
            exc_info=True,
        )


async def async_idle_device(
    hass: HomeAssistant,
    entity_id: str,
    devices: list[dict],
    *,
    area_id: str = "unknown",
    targets: TargetTemps | None = None,
) -> None:
    """Idle a climate device per its configured idle_action.

    "off"      -> async_turn_off_climate() (existing behavior)
    "fan_only" -> hvac_mode=fan_only + set_fan_mode(idle_fan_mode)
    "setback"  -> keep current hvac_mode, shift target by offset
    Falls back to off when the configured action is not applicable.
    """
    idle_action, idle_fan_mode = get_idle_action(devices, entity_id)

    # Fallback low setpoint (in HA display units) for devices where min_temp
    # is not effective (e.g. Wavin Sentio with min_temp=0 or high min_temp).
    fallback_temp: float | None = None
    if targets is not None and targets.heat is not None:
        fallback_temp = celsius_to_ha_temp(hass, targets.heat - DEFAULT_IDLE_SETBACK_OFFSET)

    # --- SETBACK branch ---
    if idle_action == IDLE_ACTION_SETBACK:
        state = hass.states.get(entity_id)
        current_hvac = state.state if state else None

        if current_hvac not in ("heat", "cool") or targets is None:
            _LOGGER.debug(
                "Area '%s': setback not applicable for '%s' (hvac=%s, targets=%s), falling back to off",
                area_id,
                entity_id,
                current_hvac,
                targets,
            )
            await async_turn_off_climate(hass, entity_id, area_id=area_id, fallback_setpoint=fallback_temp)
            return

        # Compute setback temperature
        if current_hvac == "heat" and targets.heat is not None:
            setback_temp = targets.heat - DEFAULT_IDLE_SETBACK_OFFSET
        elif current_hvac == "cool" and targets.cool is not None:
            setback_temp = targets.cool + DEFAULT_IDLE_SETBACK_OFFSET
        else:
            await async_turn_off_climate(hass, entity_id, area_id=area_id, fallback_setpoint=fallback_temp)
            return

        # Convert to HA units FIRST, then clamp to device min/max
        # (device attributes min_temp/max_temp are in HA units, not Celsius)
        ha_t = celsius_to_ha_temp(hass, setback_temp)
        min_t = state.attributes.get("min_temp")
        max_t = state.attributes.get("max_temp")
        if min_t is not None:
            ha_t = max(ha_t, float(min_t))
        if max_t is not None:
            ha_t = min(ha_t, float(max_t))
        step = state.attributes.get("target_temp_step")
        if step is not None:
            ha_t = _snap_to_step(ha_t, float(step))
            if min_t is not None:
                ha_t = max(ha_t, float(min_t))
            if max_t is not None:
                ha_t = min(ha_t, float(max_t))

        # Redundancy check: already at setback temp
        current_temp_attr = state.attributes.get("temperature")
        if current_temp_attr is not None and abs(float(current_temp_attr) - ha_t) < 0.1:
            return

        # Cache check (only for devices without reliable state feedback)
        if _should_use_cache(state):
            cached = _last_commands.get(entity_id)
            if cached and cached.get("service") == "set_temperature" and cached.get("temperature") == ha_t:
                return

        _LOGGER.debug(
            "Area '%s': setback on '%s' — target %.1f → %.1f",
            area_id,
            entity_id,
            targets.heat if current_hvac == "heat" else targets.cool,
            ha_t,
        )
        try:
            await hass.services.async_call(
                "climate",
                "set_temperature",
                {"entity_id": entity_id, "temperature": ha_t},
                blocking=True,
                context=make_roommind_context(),
            )
            _last_commands[entity_id] = _cache_entry("set_temperature", {"temperature": ha_t})
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "Area '%s': climate.set_temperature(%.1f) failed on '%s'",
                area_id,
                ha_t,
                entity_id,
                exc_info=True,
            )
        return

    # --- OFF branch ---
    if idle_action != IDLE_ACTION_FAN_ONLY:
        await async_turn_off_climate(hass, entity_id, area_id=area_id, fallback_setpoint=fallback_temp)
        return

    state = hass.states.get(entity_id)
    hvac_modes: list[str] = (state.attributes.get("hvac_modes") or []) if state else []

    if "fan_only" not in hvac_modes:
        _LOGGER.warning(
            "Area '%s': device '%s' configured for fan_only idle but does not support it, falling back to off",
            area_id,
            entity_id,
        )
        await async_turn_off_climate(hass, entity_id, area_id=area_id, fallback_setpoint=fallback_temp)
        return

    # Redundancy check: already in fan_only with correct fan_mode
    if state and state.state == "fan_only":
        current_fan = state.attributes.get("fan_mode")
        if not idle_fan_mode or current_fan == idle_fan_mode:
            return

    # Cache fallback for IR devices (only when device has no reliable state)
    if _should_use_cache(state):
        cached = _last_commands.get(entity_id)
        if cached and cached.get("service") == "set_hvac_mode" and cached.get("hvac_mode") == "fan_only":
            if not idle_fan_mode:
                return

    try:
        await hass.services.async_call(
            "climate",
            "set_hvac_mode",
            {"entity_id": entity_id, "hvac_mode": "fan_only"},
            blocking=True,
            context=make_roommind_context(),
        )
        _last_commands[entity_id] = _cache_entry("set_hvac_mode", {"hvac_mode": "fan_only"})
    except Exception:  # noqa: BLE001
        _LOGGER.warning(
            "Area '%s': climate.set_hvac_mode(fan_only) failed on '%s'",
            area_id,
            entity_id,
            exc_info=True,
        )
        return

    if idle_fan_mode:
        fan_modes: list[str] = (state.attributes.get("fan_modes") or []) if state else []
        if idle_fan_mode in fan_modes:
            try:
                await hass.services.async_call(
                    "climate",
                    "set_fan_mode",
                    {"entity_id": entity_id, "fan_mode": idle_fan_mode},
                    blocking=True,
                    context=make_roommind_context(),
                )
            except Exception:  # noqa: BLE001
                _LOGGER.warning(
                    "Area '%s': climate.set_fan_mode('%s') failed on '%s'",
                    area_id,
                    idle_fan_mode,
                    entity_id,
                    exc_info=True,
                )
        else:
            _LOGGER.debug(
                "Area '%s': device '%s' does not support fan_mode '%s' (available: %s)",
                area_id,
                entity_id,
                idle_fan_mode,
                fan_modes,
            )


def resolve_hvac_mode(desired: str, hvac_modes: list[str]) -> str | None:
    """Pick the best available hvac_mode for the desired intent.

    Fallback: heat/cool/heat_cool -> "auto" if desired mode unavailable.
    Returns None if no compatible mode exists.
    """
    if not hvac_modes or desired in hvac_modes:
        return desired
    if desired in ("heat", "cool", "heat_cool") and "auto" in hvac_modes:
        return "auto"
    return None


# Assumed full mode set for devices whose hvac_modes attribute is unreliable.
# Deliberately excludes "heat_cool" so the cascade falls through to separate
# "heat"/"cool" branches which work for more device types.
_ASSUMED_FULL_MODES: list[str] = ["off", "heat", "cool", "fan_only"]


def _effective_ac_modes(state: Any) -> list[str]:
    """Return hvac_modes, assuming full capability when modes appear unreliable.

    When a device reports no active modes (heat/cool/heat_cool/auto),
    the integration likely hides modes or is misconfigured.  Return a
    generous assumed set so the command cascade picks the right mode.  The actual
    service call may still fail — the caller's try/except handles that safely.
    """
    if state is None:
        return []
    modes = state.attributes.get("hvac_modes") or []
    if has_reliable_hvac_modes(state):
        return modes
    return _ASSUMED_FULL_MODES


# Maximum prediction uncertainty (degC) for MPC to be used.
# Physical meaning: "use MPC when the 5-min prediction is accurate to ±0.5°C."
MPC_MAX_PREDICTION_STD = 0.5

# Planning parameters
PLAN_DT_MINUTES = 5
MIN_HORIZON_HOURS = 2
HORIZON_MULTIPLIER = 2.5
DEFAULT_OUTDOOR_TEMP_FALLBACK = 10.0
SAFETY_GUARD_MIN_BLOCKS = 6  # Minimum guard horizon (30 min floor)
GUARD_PREDICTION_MARGIN = 0.2  # °C margin for prediction-based guard bypass
HARD_OVERSHOOT_CEILING = 1.0  # °C — model-independent max overshoot before forced idle

# Minimum sample counts before MPC is allowed.
# Each EKF update covers ~3 min (EKF_UPDATE_MIN_DT), so these correspond
# to real-time requirements of ~3 h idle + ~1 h active-mode data.
MIN_IDLE_UPDATES = 60  # ~3 h of idle data at 3-min EKF intervals
MIN_ACTIVE_UPDATES = 20  # ~1 h of heating or cooling data


def check_acs_can_heat(hass: HomeAssistant, room_config: dict) -> bool:
    """Check if any AC entity in the room supports heating."""
    for eid in get_ac_eids(room_config.get("devices", [])):
        state = hass.states.get(eid)
        if state is None:
            continue
        modes = _effective_ac_modes(state)
        if "heat" in modes or "heat_cool" in modes or "auto" in modes:
            return True
    return False


def get_can_heat_cool(
    room_config: dict,
    outdoor_temp: float | None = None,
    outdoor_cooling_min: float = DEFAULT_OUTDOOR_COOLING_MIN,
    outdoor_heating_max: float = DEFAULT_OUTDOOR_HEATING_MAX,
    acs_can_heat: bool = False,
) -> tuple[bool, bool]:
    """Determine whether heating/cooling are allowed for a room.

    Accounts for climate_mode, device availability, and outdoor temperature
    gating.  This is the single source of truth — used by coordinator,
    controller, and analytics.

    When *acs_can_heat* is True, ACs that support heating (heat pumps)
    contribute to the heating capability of the room.
    """
    climate_mode = room_config.get("climate_mode", "auto")
    can_heat = climate_mode != CLIMATE_MODE_COOL_ONLY and (
        bool(get_trv_eids(room_config.get("devices", []))) or acs_can_heat
    )
    can_cool = climate_mode != CLIMATE_MODE_HEAT_ONLY and bool(get_ac_eids(room_config.get("devices", [])))

    if outdoor_temp is not None:
        if outdoor_temp > outdoor_heating_max:
            can_heat = False
        if outdoor_temp < outdoor_cooling_min:
            can_cool = False

    return can_heat, can_cool


def is_mpc_active(
    model_manager: RoomModelManager,
    area_id: str,
    can_heat: bool,
    can_cool: bool,
    current_temp: float,
    outdoor_temp: float,
) -> bool:
    """Check if MPC control is active for a room.

    Single source of truth for MPC activation — used by coordinator
    and analytics.
    """
    model = model_manager.get_model(area_id)
    Q_check = model.Q_heat if can_heat else (-model.Q_cool if can_cool else 0.0)
    pred_std = model_manager.get_prediction_std(area_id, Q_check, current_temp, outdoor_temp, PLAN_DT_MINUTES)
    if pred_std >= MPC_MAX_PREDICTION_STD:
        return False

    n_idle, n_heating, n_cooling = model_manager.get_mode_counts(area_id)
    if n_idle < MIN_IDLE_UPDATES:
        return False
    if can_heat and n_heating < MIN_ACTIVE_UPDATES:
        return False
    if can_cool and n_cooling < MIN_ACTIVE_UPDATES:
        return False
    return True


class MPCController:
    """MPC-based climate controller for a single room.

    Falls back to bang-bang with hysteresis when model confidence is low.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        room_config: dict,
        *,
        model_manager: RoomModelManager,
        outdoor_temp: float | None = None,
        outdoor_forecast: list[dict] | None = None,
        settings: dict | None = None,
        previous_mode: str = MODE_IDLE,
        has_external_sensor: bool = True,
        target_resolver: Callable[[float], TargetTemps | float] | None = None,
        q_solar: float = 0.0,
        latitude: float = 0.0,
        longitude: float = 0.0,
        cloud_series: list[float | None] | None = None,
        q_residual: float = 0.0,
        heating_system_type: str = "",
        mode_on_since: float | None = None,
        shading_factor: float = 1.0,
        q_occupancy: float = 0.0,
    ) -> None:
        self.hass = hass
        self.room_config = room_config
        self.thermostats: list[str] = get_trv_eids(room_config.get("devices", []))
        self.acs: list[str] = get_ac_eids(room_config.get("devices", []))
        self._devices: list[dict] = room_config.get("devices", [])
        self._direct_eids: set[str] = get_direct_setpoint_eids(self._devices)
        self.climate_mode: str = room_config.get("climate_mode", "auto")
        self.outdoor_temp = outdoor_temp
        self.outdoor_forecast = outdoor_forecast or []
        self.previous_mode = previous_mode
        self.has_external_sensor = has_external_sensor
        self._model_manager = model_manager
        self._area_id = room_config.get("area_id", "unknown")
        self._target_resolver = target_resolver
        self.last_plan: MPCPlan | None = None
        self.q_solar = q_solar
        self._latitude = latitude
        self._longitude = longitude
        self._cloud_series = cloud_series or []
        self.q_residual = q_residual
        self._heating_system_type = heating_system_type
        self._mode_on_since = mode_on_since
        self._shading_factor = shading_factor
        self.q_occupancy = q_occupancy
        self._idle_targets: TargetTemps | None = None

        s = settings or {}
        self.outdoor_cooling_min = s.get("outdoor_cooling_min", DEFAULT_OUTDOOR_COOLING_MIN)
        self.outdoor_heating_max = s.get("outdoor_heating_max", DEFAULT_OUTDOOR_HEATING_MAX)

        # Comfort weight from UI slider (0-100, default 70 = comfort-biased).
        # Maps to optimizer w_comfort / w_energy ratio.
        cw = s.get("comfort_weight", 70)
        self._w_comfort = max(1.0, cw / 10.0)
        self._w_energy = max(1.0, (100 - cw) / 10.0)

    async def async_evaluate(
        self,
        current_temp: float | None,
        targets: TargetTemps | float | None = None,
        *,
        target_temp: float | None | object = _SENTINEL,
    ) -> tuple[str, float]:
        """Evaluate what action to take. Returns (mode, power_fraction).

        Accepts TargetTemps for dual heat/cool targets or a single float
        for backward compatibility. ``target_temp`` keyword kept for callers
        that haven't migrated yet.
        """
        # Backward compat: accept legacy keyword
        if target_temp is not _SENTINEL:
            targets = target_temp  # type: ignore[assignment]

        # Backward compat: single float → TargetTemps(heat=val, cool=val)
        if not isinstance(targets, TargetTemps):
            t = targets
            targets = TargetTemps(heat=t, cool=t) if t is not None else TargetTemps(heat=None, cool=None)

        if not self.has_external_sensor:
            mode = self._evaluate_managed_mode(targets)
            return mode, 1.0  # managed mode: device self-regulates

        # Use the model's prediction uncertainty to decide MPC vs bang-bang.
        # Compute std for the actual operating conditions (heating power as proxy).
        model = self._model_manager.get_model(self._area_id)
        can_heat, can_cool = self._get_can_heat_cool()
        Q_check = model.Q_heat if can_heat else (-model.Q_cool if can_cool else 0.0)
        T_out = self.outdoor_temp if self.outdoor_temp is not None else DEFAULT_OUTDOOR_TEMP_FALLBACK
        pred_std = self._model_manager.get_prediction_std(
            self._area_id,
            Q_check,
            current_temp or 20.0,
            T_out,
            PLAN_DT_MINUTES,
            q_solar=self.q_solar,
            q_residual=self.q_residual,
            q_occupancy=self.q_occupancy,
        )
        if pred_std < MPC_MAX_PREDICTION_STD and self._has_enough_data(can_heat, can_cool):
            return self._evaluate_mpc(current_temp, targets)
        # Bang-bang fallback: binary control (1.0 power) for fast EKF learning
        mode = self._evaluate_bangbang(current_temp, targets)
        return mode, 1.0 if mode != MODE_IDLE else 0.0

    def _has_enough_data(self, can_heat: bool, can_cool: bool) -> bool:
        """Check if the model has enough samples for reliable MPC."""
        n_idle, n_heating, n_cooling = self._model_manager.get_mode_counts(self._area_id)
        if n_idle < MIN_IDLE_UPDATES:
            return False
        # Require active-mode data for the modes this room can actually use
        if can_heat and n_heating < MIN_ACTIVE_UPDATES:
            return False
        if can_cool and n_cooling < MIN_ACTIVE_UPDATES:
            return False
        return True

    def _within_min_run(self, mode: str) -> bool:
        """Return True if the given mode is currently active and within its minimum run window.

        Used to prevent premature shutdown of slow heating systems (e.g. underfloor)
        that need a guaranteed minimum run time before being allowed to idle.
        """
        if self.previous_mode != mode or self._mode_on_since is None:
            return False
        min_run_seconds = get_min_run_blocks(self._heating_system_type, PLAN_DT_MINUTES) * PLAN_DT_MINUTES * 60
        return (time.time() - self._mode_on_since) < min_run_seconds

    def _predict_idle_drift(self, current_temp: float, dt_minutes: float) -> float:
        """Predict room temperature assuming no active HVAC over *dt_minutes*.

        Used by the safety guard to check whether temperature will drift below
        (or above) target before suppressing optimizer recommendations.
        """
        model = self._model_manager.get_model(self._area_id)
        T_out = self.outdoor_temp if self.outdoor_temp is not None else DEFAULT_OUTDOOR_TEMP_FALLBACK
        return model.predict(
            current_temp,
            T_out,
            Q_active=0.0,
            dt_minutes=dt_minutes,
            q_solar=self.q_solar * self._shading_factor,
            q_residual=self.q_residual,
            q_occupancy=self.q_occupancy,
        )

    def _evaluate_mpc(
        self,
        current_temp: float | None,
        targets: TargetTemps,
    ) -> tuple[str, float]:
        """MPC evaluation — use optimizer to determine action and power fraction."""
        if current_temp is None or (targets.heat is None and targets.cool is None):
            return MODE_IDLE, 0.0

        model = self._model_manager.get_model(self._area_id)
        can_heat, can_cool = self._get_can_heat_cool()

        # Use heat target for horizon computation (heating is most common)
        horizon_target = targets.heat if targets.heat is not None else targets.cool
        horizon_blocks = self._compute_horizon_blocks(model, current_temp, horizon_target)

        # Build outdoor series from forecast or current temp
        outdoor_series = self._build_outdoor_series(horizon_blocks)

        # Build solar series from forecast cloud coverage
        solar_series = self._build_solar_series(horizon_blocks)

        # Build residual heat series (decaying from current q_residual)
        residual_series = self._build_residual_series(horizon_blocks)

        # Build occupancy heat series (constant over horizon)
        occupancy_series = [self.q_occupancy] * horizon_blocks

        # Build dual target series with schedule lookahead for pre-heating/pre-cooling.
        # None values (from "off" action) are replaced with current_temp so the
        # optimizer sees "no deviation needed = idle optimal".
        if self._target_resolver is not None:
            now = time.time()
            dt_seconds = PLAN_DT_MINUTES * 60
            raw_targets = [self._target_resolver(now + i * dt_seconds) for i in range(horizon_blocks)]
            # Extract separate heat and cool series from TargetTemps
            if raw_targets and isinstance(raw_targets[0], TargetTemps):
                tt_targets = cast(list[TargetTemps], raw_targets)
                heat_target_series = [t.heat if t.heat is not None else current_temp for t in tt_targets]
                cool_target_series = [t.cool if t.cool is not None else current_temp for t in tt_targets]
            else:
                # Legacy resolver returning float|None
                float_targets = cast(list[float | None], raw_targets)
                heat_target_series = [t if t is not None else current_temp for t in float_targets]
                cool_target_series = list(heat_target_series)
        else:
            fallback_h = targets.heat if targets.heat is not None else current_temp
            fallback_c = targets.cool if targets.cool is not None else current_temp
            heat_target_series = [fallback_h] * horizon_blocks
            cool_target_series = [fallback_c] * horizon_blocks

        from .residual_heat import get_min_run_blocks

        min_run = get_min_run_blocks(self._heating_system_type, PLAN_DT_MINUTES)

        optimizer = MPCOptimizer(
            model=model,
            can_heat=can_heat,
            can_cool=can_cool,
            w_comfort=self._w_comfort,
            w_energy=self._w_energy,
            outdoor_cooling_min=self.outdoor_cooling_min,
            outdoor_heating_max=self.outdoor_heating_max,
            min_run_blocks=min_run,
        )

        plan = optimizer.optimize(
            T_room=current_temp,
            T_outdoor_series=outdoor_series,
            heat_target_series=heat_target_series,
            cool_target_series=cool_target_series,
            dt_minutes=PLAN_DT_MINUTES,
            solar_series=solar_series,
            residual_series=residual_series,
            occupancy_series=occupancy_series,
        )
        self.last_plan = plan

        action = plan.get_current_action()
        power_fraction = plan.get_current_power_fraction()

        # Safety guard: don't heat above the maximum upcoming target,
        # don't cool below the minimum upcoming target, while preserving
        # pre-heating/pre-cooling when the model predicts a drift past target.
        # The guard horizon scales with heating system response time.
        guard_blocks = max(SAFETY_GUARD_MIN_BLOCKS, min_run)
        guard_horizon_minutes = guard_blocks * PLAN_DT_MINUTES
        near_heat = heat_target_series[:guard_blocks]
        near_cool = cool_target_series[:guard_blocks]

        # Hard ceiling: force idle when significantly past target, regardless
        # of model predictions or min-run window.  Prevents runaway
        # heating/cooling from a miscalibrated thermal model (#152).
        if near_heat and action == MODE_HEATING and current_temp > max(near_heat) + HARD_OVERSHOOT_CEILING:
            _LOGGER.info(
                "Hard ceiling: suppressing HEATING for %s at %.1f°C (target max %.1f°C + %.1f°C ceiling)",
                self._area_id,
                current_temp,
                max(near_heat),
                HARD_OVERSHOOT_CEILING,
            )
            action = MODE_IDLE
            power_fraction = 0.0
        elif near_cool and action == MODE_COOLING and current_temp < min(near_cool) - HARD_OVERSHOOT_CEILING:
            _LOGGER.info(
                "Hard ceiling: suppressing COOLING for %s at %.1f°C (target min %.1f°C - %.1f°C ceiling)",
                self._area_id,
                current_temp,
                min(near_cool),
                HARD_OVERSHOOT_CEILING,
            )
            action = MODE_IDLE
            power_fraction = 0.0

        # Model-based guard: suppress when model predicts temp stays past
        # target, but allow pre-heating/pre-cooling when a drift is predicted.
        elif near_heat and action == MODE_HEATING and current_temp >= max(near_heat):
            predicted = self._predict_idle_drift(current_temp, guard_horizon_minutes)
            if predicted < min(near_heat) - GUARD_PREDICTION_MARGIN:
                pass  # model predicts dip — allow optimizer's HEAT decision
            elif not self._within_min_run(MODE_HEATING):
                action = MODE_IDLE
                power_fraction = 0.0
        elif near_cool and action == MODE_COOLING and current_temp <= min(near_cool):
            predicted = self._predict_idle_drift(current_temp, guard_horizon_minutes)
            if predicted > max(near_cool) + GUARD_PREDICTION_MARGIN:
                pass  # model predicts rise — allow optimizer's COOL decision
            elif not self._within_min_run(MODE_COOLING):
                action = MODE_IDLE
                power_fraction = 0.0

        return action, power_fraction

    def _evaluate_bangbang(
        self,
        current_temp: float | None,
        targets: TargetTemps,
    ) -> str:
        """Fallback: bang-bang with hysteresis and dead-band support."""
        if current_temp is None:
            return MODE_IDLE

        can_heat, can_cool = self._get_can_heat_cool()
        heat_target = targets.heat
        cool_target = targets.cool

        # Mode stickiness
        if self.previous_mode == MODE_HEATING and can_heat and heat_target is not None:
            if current_temp < heat_target or self._within_min_run(MODE_HEATING):
                return MODE_HEATING
            return MODE_IDLE

        if self.previous_mode == MODE_COOLING and can_cool and cool_target is not None:
            if current_temp > cool_target or self._within_min_run(MODE_COOLING):
                return MODE_COOLING
            return MODE_IDLE

        # From idle: threshold to start
        if can_heat and heat_target is not None and current_temp < heat_target - BANGBANG_HEAT_HYSTERESIS:
            return MODE_HEATING

        if can_cool and cool_target is not None and current_temp > cool_target + BANGBANG_COOL_HYSTERESIS:
            return MODE_COOLING

        return MODE_IDLE

    def _evaluate_managed_mode(self, targets: TargetTemps) -> str:
        """Managed Mode: device self-regulates.

        In auto mode with both thermostats and ACs, both device types
        are activated (each with its own target temp) and self-regulate
        independently.  async_apply handles this via has_external_sensor.
        The returned mode is used for display and outdoor gating only.
        """
        if targets.heat is None and targets.cool is None:
            return MODE_IDLE

        can_heat, can_cool = self._get_can_heat_cool()

        if self.climate_mode == CLIMATE_MODE_COOL_ONLY:
            return MODE_COOLING if can_cool else MODE_IDLE

        if self.climate_mode == CLIMATE_MODE_HEAT_ONLY:
            return MODE_HEATING if can_heat else MODE_IDLE

        # Auto mode: activate all available, non-gated device types.
        # Both thermostats and ACs get their respective target temps and self-regulate.
        if can_heat and can_cool:
            # Both available — display mode based on season heuristic
            return MODE_HEATING
        if can_heat:
            return MODE_HEATING
        if can_cool:
            return MODE_COOLING
        return MODE_IDLE

    def _get_can_heat_cool(self) -> tuple[bool, bool]:
        """Determine whether heating/cooling are allowed based on climate mode."""
        return get_can_heat_cool(
            self.room_config,
            self.outdoor_temp,
            self.outdoor_cooling_min,
            self.outdoor_heating_max,
            acs_can_heat=check_acs_can_heat(self.hass, self.room_config),
        )

    def _compute_horizon_blocks(self, model: Any, current_temp: float, target_temp: float | None) -> int:
        """Compute adaptive horizon in blocks.

        target_temp can be a single value or the primary target from TargetTemps.
        """
        if target_temp is None:
            return int(MIN_HORIZON_HOURS * 60 / PLAN_DT_MINUTES)
        delta = abs(current_temp - target_temp) + 3.0  # extra margin
        Q_max = max(model.Q_heat, model.Q_cool)
        if Q_max > 0:
            rate = Q_max / (model.C * 60)  # °C/min approx
            if rate > 0:
                est_minutes = delta / rate
                horizon_minutes = max(MIN_HORIZON_HOURS * 60, est_minutes * HORIZON_MULTIPLIER)
                return max(24, int(horizon_minutes / PLAN_DT_MINUTES))
        return int(MIN_HORIZON_HOURS * 60 / PLAN_DT_MINUTES)  # default 24 blocks = 2h

    def _build_outdoor_series(self, n_blocks: int) -> list[float]:
        """Build outdoor temperature series from forecast or current value."""
        if self.outdoor_forecast:
            series = [
                f.get("temperature", self.outdoor_temp or DEFAULT_OUTDOOR_TEMP_FALLBACK) for f in self.outdoor_forecast
            ]
            while len(series) < n_blocks:
                series.append(series[-1] if series else (self.outdoor_temp or DEFAULT_OUTDOOR_TEMP_FALLBACK))
            return series[:n_blocks]
        T = self.outdoor_temp if self.outdoor_temp is not None else DEFAULT_OUTDOOR_TEMP_FALLBACK
        return [T] * n_blocks

    def _build_solar_series(self, n_blocks: int) -> list[float]:
        """Build solar irradiance series for MPC horizon from forecast cloud data."""
        from .solar import build_solar_series

        # Expand hourly cloud coverage to 5-min blocks (×12 per hour)
        cloud_per_block: list[float | None] | None = None
        if self._cloud_series:
            expanded: list[float | None] = []
            for cc in self._cloud_series:
                expanded.extend([cc] * 12)
            cloud_per_block = expanded[:n_blocks]
            while len(cloud_per_block) < n_blocks:
                cloud_per_block.append(cloud_per_block[-1] if cloud_per_block else None)

        series = build_solar_series(
            self._latitude,
            self._longitude,
            n_blocks,
            dt_minutes=PLAN_DT_MINUTES,
            cloud_series=cloud_per_block,
        )
        # MPC uses unshaded solar to avoid oscillation feedback loop:
        # covers deployed → low solar prediction → retract → high solar → deploy
        return series

    @property
    def predicted_peak_temp(self) -> float | None:
        """Return the maximum predicted temperature over the MPC lookahead horizon.

        Available after async_evaluate() has been called.
        Returns None if no MPC plan was computed (bang-bang mode or insufficient data).
        """
        plan = self.last_plan
        if plan is None or not plan.temperatures or len(plan.temperatures) < 2:
            return None
        return max(plan.temperatures[1:])  # Skip index 0 (current T)

    def _build_residual_series(self, n_blocks: int) -> list[float] | None:
        """Build decaying residual heat series for MPC horizon."""
        if self.q_residual <= 0 or not self._heating_system_type:
            return None
        from ..const import HEATING_SYSTEM_PROFILES, RESIDUAL_HEAT_CUTOFF

        profile = HEATING_SYSTEM_PROFILES.get(self._heating_system_type)
        if not profile:
            return None
        tau = profile["tau_minutes"]
        if tau <= 0:
            return None
        series: list[float] = []
        for i in range(n_blocks):
            q = self.q_residual * math.exp(-i * PLAN_DT_MINUTES / tau)
            series.append(q if q >= RESIDUAL_HEAT_CUTOFF else 0.0)
        return series

    async def async_apply(
        self,
        mode: str,
        targets: TargetTemps | float | None = None,
        power_fraction: float = 1.0,
        current_temp: float | None = None,
        exclude_eids: set[str] | None = None,
        *,
        target_temp: float | None | object = _SENTINEL,
        heating_boost_target: float | None = None,
        ac_heating_boost_target: float | None = None,
        cooling_boost_target: float | None = None,
        heat_source_plan: HeatSourcePlan | None = None,
        compressor_forced_on: set[str] | None = None,
        compressor_forced_off: set[str] | None = None,
    ) -> None:
        """Apply the determined mode with proportional valve control."""
        _forced_on = compressor_forced_on or set()
        _forced_off = compressor_forced_off or set()

        # Backward compat: accept legacy keyword
        if target_temp is not _SENTINEL:
            targets = target_temp  # type: ignore[assignment]

        # Backward compat: single float → TargetTemps
        if not isinstance(targets, TargetTemps):
            t = targets
            targets = TargetTemps(heat=t, cool=t) if t is not None else TargetTemps(heat=None, cool=None)

        # Store targets for _call delegation (setback idle_action) — must be
        # after backward-compat conversion so legacy callers get a TargetTemps.
        self._idle_targets = targets

        # Resolve effective target_temp for the current mode
        if mode == MODE_HEATING:
            target_temp = targets.heat
        elif mode == MODE_COOLING:
            target_temp = targets.cool
        else:
            target_temp = targets.heat if targets.heat is not None else targets.cool

        if mode != MODE_IDLE and target_temp is None:
            mode = MODE_IDLE

        # After the guard above, target_temp is guaranteed non-None for HEATING/COOLING.
        # We assign a typed local for downstream use.
        effective_target: float = target_temp if target_temp is not None else 0.0

        # Dynamic boost: use device-reported limits, fall back to constants
        trv_heat_boost = heating_boost_target if heating_boost_target is not None else HEATING_BOOST_TARGET
        ac_heat_boost = ac_heating_boost_target if ac_heating_boost_target is not None else AC_HEATING_BOOST_TARGET
        ac_cool_boost = cooling_boost_target if cooling_boost_target is not None else AC_COOLING_BOOST_TARGET

        can_heat, can_cool = self._get_can_heat_cool()

        _exclude = exclude_eids or set()
        thermostats = [e for e in self.thermostats if e not in _exclude]

        # Managed mode (no external sensor) with auto climate mode and
        # both device types: activate each device in its natural mode so
        # both can self-regulate against the target temperature.
        if (
            not self.has_external_sensor
            and self.climate_mode not in (CLIMATE_MODE_HEAT_ONLY, CLIMATE_MODE_COOL_ONLY)
            and mode != MODE_IDLE
        ):
            # In managed auto mode, thermostats get heat target and ACs get cool target
            ha_heat_target = celsius_to_ha_temp(self.hass, targets.heat) if targets.heat is not None else None
            ha_cool_target = celsius_to_ha_temp(self.hass, targets.cool) if targets.cool is not None else None
            for eid in thermostats:
                if eid in _forced_off:
                    await async_idle_device(self.hass, eid, self._devices, area_id=self._area_id, targets=targets)
                    continue
                if can_heat and ha_heat_target is not None:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "heat"})
                    await self._call(
                        "set_temperature", {"entity_id": eid, "temperature": ha_heat_target}, temp_intent="heat"
                    )
                else:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "off"})
            for eid in self.acs:
                if eid in _forced_off:
                    await async_idle_device(self.hass, eid, self._devices, area_id=self._area_id, targets=targets)
                    continue
                ac_state = self.hass.states.get(eid)
                ac_modes = _effective_ac_modes(ac_state)
                ac_target = ha_cool_target if ha_cool_target is not None else ha_heat_target
                ac_heat_target = ha_heat_target if ha_heat_target is not None else ha_cool_target
                if ac_target is None:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "off"})
                elif "heat_cool" in ac_modes:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "heat_cool"})
                    # Dual-setpoint: send both targets when device uses range mode
                    ac_state_now = self.hass.states.get(eid)
                    is_range = ac_state_now and ac_state_now.attributes.get("target_temp_low") is not None
                    if is_range and ha_heat_target is not None and ha_cool_target is not None:
                        low = min(ha_heat_target, ha_cool_target)
                        high = max(ha_heat_target, ha_cool_target)
                        await self._call(
                            "set_temperature", {"entity_id": eid, "target_temp_low": low, "target_temp_high": high}
                        )
                    else:
                        await self._call("set_temperature", {"entity_id": eid, "temperature": ac_target})
                elif not thermostats and can_heat and can_cool and "heat" in ac_modes and "cool" in ac_modes:
                    # AC-only room, device supports heat+cool but not heat_cool:
                    # use device's built-in temperature to pick the right mode.
                    dev_temp = ac_state.attributes.get("current_temperature") if ac_state else None
                    if dev_temp is not None and ha_cool_target is not None and dev_temp > ha_cool_target:
                        await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "cool"})
                        await self._call(
                            "set_temperature",
                            {"entity_id": eid, "temperature": ha_cool_target},
                            temp_intent="cool",
                        )
                    else:
                        ac_heat_t = ha_heat_target if ha_heat_target is not None else ha_cool_target
                        await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "heat"})
                        await self._call(
                            "set_temperature",
                            {"entity_id": eid, "temperature": ac_heat_t},
                            temp_intent="heat",
                        )
                elif can_cool and "cool" in ac_modes:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "cool"})
                    await self._call(
                        "set_temperature", {"entity_id": eid, "temperature": ac_target}, temp_intent="cool"
                    )
                elif can_heat and "heat" in ac_modes:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "heat"})
                    await self._call(
                        "set_temperature", {"entity_id": eid, "temperature": ac_heat_target}, temp_intent="heat"
                    )
                elif "auto" in ac_modes:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "auto"})
                    await self._call(
                        "set_temperature", {"entity_id": eid, "temperature": ac_heat_target}, temp_intent="heat"
                    )
                else:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "off"})
            return

        if mode == MODE_HEATING and heat_source_plan is not None:
            # Orchestrated heating: route power to specific devices per plan
            for cmd in heat_source_plan.commands:
                if cmd.entity_id in _exclude:
                    continue
                if cmd.entity_id in _forced_on and not cmd.active:
                    # Compressor protection: keep device running at target temp
                    # to prevent overshoot (defensive — currently unreachable
                    # because forced_on is only populated for IDLE mode).
                    if targets.heat is not None:
                        ha_t = celsius_to_ha_temp(self.hass, targets.heat)
                        if cmd.device_type == "thermostat":
                            await self._call(
                                "set_hvac_mode",
                                {"entity_id": cmd.entity_id, "hvac_mode": "heat"},
                            )
                            await self._call(
                                "set_temperature",
                                {"entity_id": cmd.entity_id, "temperature": ha_t},
                                temp_intent="heat",
                            )
                        else:
                            ac_state = self.hass.states.get(cmd.entity_id)
                            ac_modes = _effective_ac_modes(ac_state)
                            if "heat" in ac_modes:
                                await self._call(
                                    "set_hvac_mode",
                                    {"entity_id": cmd.entity_id, "hvac_mode": "heat"},
                                )
                            elif "heat_cool" in ac_modes:
                                await self._call(
                                    "set_hvac_mode",
                                    {"entity_id": cmd.entity_id, "hvac_mode": "heat_cool"},
                                )
                            elif "auto" in ac_modes:
                                await self._call(
                                    "set_hvac_mode",
                                    {"entity_id": cmd.entity_id, "hvac_mode": "auto"},
                                )
                            else:
                                continue
                            await self._call(
                                "set_temperature",
                                {"entity_id": cmd.entity_id, "temperature": ha_t},
                                temp_intent="heat",
                            )
                    continue
                if cmd.entity_id in _forced_off and cmd.active:
                    await async_idle_device(
                        self.hass, cmd.entity_id, self._devices, area_id=self._area_id, targets=targets
                    )
                    continue
                if cmd.active:
                    if cmd.device_type == "thermostat":
                        if self.has_external_sensor and current_temp is not None:
                            t = round(
                                current_temp + cmd.power_fraction * (trv_heat_boost - current_temp),
                                1,
                            )
                            t = max(effective_target, t)
                            t = min(trv_heat_boost, t)
                        else:
                            t = trv_heat_boost if self.has_external_sensor else effective_target
                        t_final = effective_target if cmd.entity_id in self._direct_eids else t
                        ha_t = celsius_to_ha_temp(self.hass, t_final)
                        await self._call("set_hvac_mode", {"entity_id": cmd.entity_id, "hvac_mode": "heat"})
                        await self._call(
                            "set_temperature",
                            {"entity_id": cmd.entity_id, "temperature": ha_t},
                            temp_intent="heat",
                        )
                    else:  # ac
                        if self.has_external_sensor and current_temp is not None:
                            t = round(
                                current_temp + cmd.power_fraction * (ac_heat_boost - current_temp),
                                1,
                            )
                            t = max(effective_target, t)
                            t = min(ac_heat_boost, t)
                        else:
                            t = effective_target
                        t_final = effective_target if cmd.entity_id in self._direct_eids else t
                        ha_t = celsius_to_ha_temp(self.hass, t_final)
                        ac_state = self.hass.states.get(cmd.entity_id)
                        ac_modes = _effective_ac_modes(ac_state)
                        if "heat" in ac_modes:
                            await self._call("set_hvac_mode", {"entity_id": cmd.entity_id, "hvac_mode": "heat"})
                            await self._call(
                                "set_temperature",
                                {"entity_id": cmd.entity_id, "temperature": ha_t},
                                temp_intent="heat",
                            )
                        elif "heat_cool" in ac_modes:
                            await self._call("set_hvac_mode", {"entity_id": cmd.entity_id, "hvac_mode": "heat_cool"})
                            await self._call(
                                "set_temperature",
                                {"entity_id": cmd.entity_id, "temperature": ha_t},
                                temp_intent="heat",
                            )
                        elif "auto" in ac_modes:
                            await self._call("set_hvac_mode", {"entity_id": cmd.entity_id, "hvac_mode": "auto"})
                            await self._call(
                                "set_temperature",
                                {"entity_id": cmd.entity_id, "temperature": ha_t},
                                temp_intent="heat",
                            )
                        else:
                            await self._call("set_hvac_mode", {"entity_id": cmd.entity_id, "hvac_mode": "off"})
                else:
                    # Inactive device
                    if cmd.device_type == "thermostat":
                        # Keep TRV in heat mode at current temp to keep valve closed
                        # while the preferred source handles heating.
                        # current_temp is guaranteed non-None here: the orchestrator
                        # returns None when current_temp is None (line 100).
                        assert current_temp is not None
                        ha_t = celsius_to_ha_temp(self.hass, current_temp)
                        await self._call("set_hvac_mode", {"entity_id": cmd.entity_id, "hvac_mode": "heat"})
                        await self._call(
                            "set_temperature",
                            {"entity_id": cmd.entity_id, "temperature": ha_t},
                            temp_intent="heat",
                        )
                    else:
                        # ACs can be turned off without boiler cycling concerns
                        await self._call("set_hvac_mode", {"entity_id": cmd.entity_id, "hvac_mode": "off"})
            return

        if mode == MODE_HEATING:
            # Proportional TRV setpoint for Full Control mode
            if self.has_external_sensor and current_temp is not None:
                trv_target = round(
                    current_temp + power_fraction * (trv_heat_boost - current_temp),
                    1,
                )
                # Floor: never below target (TRV must always aim to heat toward target)
                trv_target = max(effective_target, trv_target)
                # Ceiling: never above boost target
                trv_target = min(trv_heat_boost, trv_target)
            else:
                trv_target = trv_heat_boost if self.has_external_sensor else effective_target
            ha_trv = celsius_to_ha_temp(self.hass, trv_target)
            ha_trv_direct = celsius_to_ha_temp(self.hass, effective_target)
            for eid in thermostats:
                if eid in _forced_off:
                    await async_idle_device(self.hass, eid, self._devices, area_id=self._area_id, targets=targets)
                    continue
                ha_t = ha_trv_direct if eid in self._direct_eids else ha_trv
                await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "heat"})
                await self._call("set_temperature", {"entity_id": eid, "temperature": ha_t}, temp_intent="heat")
            # ACs: proportional setpoint in Full Control, actual target otherwise
            if self.has_external_sensor and current_temp is not None:
                ac_heat_target = round(
                    current_temp + power_fraction * (ac_heat_boost - current_temp),
                    1,
                )
                ac_heat_target = max(effective_target, ac_heat_target)
                ac_heat_target = min(ac_heat_boost, ac_heat_target)
            else:
                ac_heat_target = effective_target
            ha_ac_target = celsius_to_ha_temp(self.hass, ac_heat_target)
            ha_ac_direct = celsius_to_ha_temp(self.hass, effective_target)
            for eid in self.acs:
                if eid in _forced_off:
                    await async_idle_device(self.hass, eid, self._devices, area_id=self._area_id, targets=targets)
                    continue
                ha_t = ha_ac_direct if eid in self._direct_eids else ha_ac_target
                ac_state = self.hass.states.get(eid)
                ac_modes = _effective_ac_modes(ac_state)
                if "heat" in ac_modes:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "heat"})
                    await self._call("set_temperature", {"entity_id": eid, "temperature": ha_t}, temp_intent="heat")
                elif "heat_cool" in ac_modes:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "heat_cool"})
                    await self._call("set_temperature", {"entity_id": eid, "temperature": ha_t}, temp_intent="heat")
                elif "auto" in ac_modes:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "auto"})
                    await self._call("set_temperature", {"entity_id": eid, "temperature": ha_t}, temp_intent="heat")
                else:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "off"})
        elif mode == MODE_COOLING:
            if self.has_external_sensor and current_temp is not None:
                ac_cool_target = round(
                    current_temp - power_fraction * (current_temp - ac_cool_boost),
                    1,
                )
                ac_cool_target = max(ac_cool_boost, ac_cool_target)
                ac_cool_target = min(effective_target, ac_cool_target)
            else:
                ac_cool_target = effective_target
            ha_target = celsius_to_ha_temp(self.hass, ac_cool_target)
            ha_cool_direct = celsius_to_ha_temp(self.hass, effective_target)
            for eid in self.acs:
                if eid in _forced_off:
                    await async_idle_device(self.hass, eid, self._devices, area_id=self._area_id, targets=targets)
                    continue
                ha_t = ha_cool_direct if eid in self._direct_eids else ha_target
                await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "cool"})
                await self._call("set_temperature", {"entity_id": eid, "temperature": ha_t}, temp_intent="cool")
            for eid in thermostats:
                if eid in _forced_off:
                    await async_idle_device(self.hass, eid, self._devices, area_id=self._area_id, targets=targets)
                    continue
                await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "off"})
        elif mode == MODE_IDLE:
            for eid in thermostats + self.acs:
                if eid in _forced_on:
                    # Compressor min-run: set target temp so device self-regulates
                    # instead of overshooting at the old boost setpoint.
                    dev_state = self.hass.states.get(eid)
                    current_hvac = dev_state.state if dev_state else None
                    if current_hvac == "heat" and targets.heat is not None:
                        ha_t = celsius_to_ha_temp(self.hass, targets.heat)
                        await self._call(
                            "set_temperature",
                            {"entity_id": eid, "temperature": ha_t},
                            temp_intent="heat",
                        )
                    elif current_hvac == "cool" and targets.cool is not None:
                        ha_t = celsius_to_ha_temp(self.hass, targets.cool)
                        await self._call(
                            "set_temperature",
                            {"entity_id": eid, "temperature": ha_t},
                            temp_intent="cool",
                        )
                    elif current_hvac in ("heat_cool", "auto"):
                        if targets.heat is not None:
                            ha_t = celsius_to_ha_temp(self.hass, targets.heat)
                            await self._call(
                                "set_temperature",
                                {"entity_id": eid, "temperature": ha_t},
                                temp_intent="heat",
                            )
                        elif targets.cool is not None:
                            ha_t = celsius_to_ha_temp(self.hass, targets.cool)
                            await self._call(
                                "set_temperature",
                                {"entity_id": eid, "temperature": ha_t},
                                temp_intent="cool",
                            )
                    _LOGGER.debug(
                        "Area '%s': keeping '%s' active (compressor min-run protection)",
                        self._area_id,
                        eid,
                    )
                    continue
                await async_idle_device(self.hass, eid, self._devices, area_id=self._area_id, targets=targets)

    async def _call(self, service: str, data: dict, *, temp_intent: str = "") -> None:
        eid = data.get("entity_id")
        state = self.hass.states.get(eid) if eid else None

        # Delegate "turn off" to fallback-aware helper (handles heat-only TRVs)
        if service == "set_hvac_mode" and data.get("hvac_mode") == "off" and eid:
            await async_idle_device(self.hass, eid, self._devices, area_id=self._area_id, targets=self._idle_targets)
            return

        # Resolve hvac_mode to a supported mode (handles auto-only devices)
        if service == "set_hvac_mode" and state:
            hvac_modes = state.attributes.get("hvac_modes") or []
            resolved = resolve_hvac_mode(data["hvac_mode"], hvac_modes)
            if resolved is None:
                if not has_reliable_hvac_modes(state):
                    if (
                        state.state == "off"
                        and data["hvac_mode"] not in ("off", "fan_only")
                        and "fan_only" in hvac_modes
                    ):
                        resolved = "fan_only"
                        _LOGGER.debug(
                            "Area '%s': device '%s' is off with incomplete modes, pre-activating via fan_only (#135)",
                            self._area_id,
                            eid,
                        )
                    else:
                        resolved = data["hvac_mode"]
                        _LOGGER.debug(
                            "Area '%s': device '%s' has incomplete modes, sending '%s' directly",
                            self._area_id,
                            eid,
                            resolved,
                        )
                else:
                    _LOGGER.debug(
                        "Area '%s': device '%s' does not support '%s' or any fallback, skipping",
                        self._area_id,
                        eid,
                        data["hvac_mode"],
                    )
                    return
            if resolved != data["hvac_mode"]:
                _LOGGER.debug(
                    "Area '%s': device '%s' resolved '%s' -> '%s'",
                    self._area_id,
                    eid,
                    data["hvac_mode"],
                    resolved,
                )
                data = {**data, "hvac_mode": resolved}

        # Clamp temperature to device min/max range (before redundancy check
        # so that e.g. 30°C clamped to 25°C is correctly seen as redundant
        # when the device is already at 25°C)
        if service == "set_temperature" and state and "temperature" in data:
            dev_min = state.attributes.get("min_temp")
            dev_max = state.attributes.get("max_temp")
            temp = data["temperature"]
            if dev_max is not None and temp > dev_max:
                data = {**data, "temperature": dev_max}
            if dev_min is not None and temp < dev_min:
                data = {**data, "temperature": dev_min}

        # Adapt for dual-setpoint devices (e.g. Bosch BTH-RM230Z):
        # when device exposes target_temp_low/high, convert single temperature
        # to the appropriate range format based on the caller's intent.
        if (
            service == "set_temperature"
            and state
            and "temperature" in data
            and temp_intent
            and state.attributes.get("target_temp_low") is not None
        ):
            temp = data["temperature"]
            dev_max = state.attributes.get("max_temp", temp)
            dev_min = state.attributes.get("min_temp", temp)
            if temp_intent == "heat":
                cur_high = state.attributes.get("target_temp_high", dev_max)
                data = {k: v for k, v in data.items() if k != "temperature"}
                data["target_temp_low"] = temp
                data["target_temp_high"] = max(temp, cur_high)
            elif temp_intent == "cool":
                cur_low = state.attributes.get("target_temp_low", dev_min)
                data = {k: v for k, v in data.items() if k != "temperature"}
                data["target_temp_low"] = min(temp, cur_low)
                data["target_temp_high"] = temp

        # Clamp dual-setpoint data to device min/max
        if service == "set_temperature" and state and "target_temp_low" in data:
            dev_min = state.attributes.get("min_temp")
            dev_max = state.attributes.get("max_temp")
            if dev_min is not None and data["target_temp_low"] < dev_min:
                data = {**data, "target_temp_low": dev_min}
            if dev_max is not None and data["target_temp_high"] > dev_max:
                data = {**data, "target_temp_high": dev_max}

        # Snap to device's target_temp_step (e.g. 1.0 for ACs that only accept integers)
        if service == "set_temperature" and state:
            step = state.attributes.get("target_temp_step")
            if step is not None:
                step = float(step)
                dev_min = state.attributes.get("min_temp")
                dev_max = state.attributes.get("max_temp")
                if "temperature" in data:
                    t = _snap_to_step(data["temperature"], step)
                    if dev_max is not None and t > dev_max:
                        t = dev_max
                    if dev_min is not None and t < dev_min:
                        t = dev_min
                    data = {**data, "temperature": t}
                if "target_temp_low" in data:
                    lo = _snap_to_step(data["target_temp_low"], step)
                    if dev_min is not None and lo < dev_min:
                        lo = dev_min
                    data = {**data, "target_temp_low": lo}
                if "target_temp_high" in data:
                    hi = _snap_to_step(data["target_temp_high"], step)
                    if dev_max is not None and hi > dev_max:
                        hi = dev_max
                    data = {**data, "target_temp_high": hi}

        # --- Redundancy: primary (device state) then fallback (sent cache) ---
        skip = False
        if state:
            if service == "set_hvac_mode" and state.state == data.get("hvac_mode"):
                skip = True
            elif service == "set_temperature":
                if "target_temp_low" in data:
                    cur_low = state.attributes.get("target_temp_low")
                    cur_high = state.attributes.get("target_temp_high")
                    des_low = data.get("target_temp_low")
                    des_high = data.get("target_temp_high")
                    if (
                        cur_low is not None
                        and des_low is not None
                        and cur_high is not None
                        and des_high is not None
                        and round(cur_low, 1) == round(des_low, 1)
                        and round(cur_high, 1) == round(des_high, 1)
                    ):
                        skip = True
                else:
                    current = state.attributes.get("temperature")
                    desired = data.get("temperature")
                    if current is not None and desired is not None and round(current, 1) == round(desired, 1):
                        skip = True

        # Fallback: check sent-command cache (for IR devices without state feedback)
        if not skip and eid and _should_use_cache(state):
            cached = _last_commands.get(eid)
            if cached is not None and cached.get("service") == service:
                if service == "set_hvac_mode":
                    if cached.get("hvac_mode") == data.get("hvac_mode"):
                        skip = True
                elif service == "set_temperature":
                    if "target_temp_low" in data:
                        c_low = cached.get("target_temp_low")
                        c_high = cached.get("target_temp_high")
                        d_low = data.get("target_temp_low")
                        d_high = data.get("target_temp_high")
                        if (
                            c_low is not None
                            and d_low is not None
                            and c_high is not None
                            and d_high is not None
                            and round(c_low, 1) == round(d_low, 1)
                            and round(c_high, 1) == round(d_high, 1)
                        ):
                            skip = True
                    else:
                        c_temp = cached.get("temperature")
                        d_temp = data.get("temperature")
                        if c_temp is not None and d_temp is not None and round(c_temp, 1) == round(d_temp, 1):
                            skip = True

        if skip:
            return

        try:
            await self.hass.services.async_call(
                "climate",
                service,
                data,
                blocking=True,
                context=make_roommind_context(),
            )
            if eid:
                _last_commands[eid] = _cache_entry(service, data)
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "Area '%s': climate.%s failed on '%s'",
                self._area_id,
                service,
                data.get("entity_id"),
                exc_info=True,
            )
