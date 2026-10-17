"""MPC-based climate controller for RoomMind."""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant

from ..const import (
    AC_BOOST_DELTA_MAX,
    AC_BOOST_DELTA_MIN,
    AC_COOLING_BOOST_TARGET,
    AC_HEATING_BOOST_TARGET,
    APPROACH_RATE_MIN,
    BANGBANG_COOL_HYSTERESIS,
    BANGBANG_HEAT_HYSTERESIS,
    BOOST_CAP_FALLBACK_STEP,
    CLIMATE_MODE_COOL_ONLY,
    CLIMATE_MODE_HEAT_ONLY,
    COMMAND_CACHE_REASSERT_SECONDS,
    COMPRESSOR_HOLD_RETARGET_TOLERANCE,
    CONTROL_MODE_BANGBANG,
    DEFAULT_COMFORT_WEIGHT,
    DEFAULT_CONTROL_MODE,
    DEFAULT_OUTDOOR_COOLING_MIN,
    DEFAULT_OUTDOOR_HEATING_MAX,
    HEATING_BOOST_TARGET,
    HOLD_OVERSHOOT_MARGIN,
    MIN_POWER_FRACTION,
    MODE_COOLING,
    MODE_HEATING,
    MODE_IDLE,
    PROPORTIONAL_DEADBAND_C,
    PROPORTIONAL_DEADBAND_NEAR_TARGET_C,
    PROPORTIONAL_SETPOINT_DWELL_SECONDS,
    TargetTemps,
    is_override_active,
    make_roommind_context,
)
from ..managers.heat_source_orchestrator import evaluate_heat_sources
from ..utils.device_utils import (
    DEFAULT_IDLE_SETBACK_OFFSET,
    HOLD_BAND_K,
    IDLE_ACTION_FAN_ONLY,
    IDLE_ACTION_HOLD,
    IDLE_ACTION_LOW,
    IDLE_ACTION_OFF,
    IDLE_ACTION_SETBACK,
    get_ac_eids,
    get_all_entity_ids,
    get_direct_setpoint_eids,
    get_idle_action,
    get_setpoint_offset,
    get_setpoint_offsets,
    get_trv_eids,
    has_reliable_hvac_modes,
)
from ..utils.temp_utils import celsius_delta_to_ha, celsius_to_ha_temp
from .mpc_optimizer import MPCOptimizer, MPCPlan, preheat_max_blocks, slow_start_penalty
from .residual_heat import get_min_run_blocks, mean_rebound
from .thermal_model import RoomModelManager

if TYPE_CHECKING:
    from ..managers.head_offset_tracker import HeadOffsetTracker
    from ..managers.heat_source_orchestrator import HeatSourcePlan

_LOGGER = logging.getLogger(__name__)

_SENTINEL: object = object()  # default marker for backward-compat keyword detection

# Cache of last successfully sent command per climate entity.
# Fallback for IR devices that don't report temperature attributes.
# Persists across MPCController instances (created fresh each 30s cycle),
# resets on integration reload (module reimport).
_last_commands: dict[str, dict[str, Any]] = {}
# Last successful command per (entity, service).  _last_commands keeps only the
# newest command per entity, so set_hvac_mode and set_temperature would evict
# each other and the IR fallback could never recognise a repeated pair (#416).
_last_by_service: dict[tuple[str, str], dict[str, Any]] = {}
# When each (entity, service) entry was last sent or confirmed.  Kept apart from the
# entries because those are exposed in diagnostics.
_sent_at: dict[tuple[str, str], float] = {}
_setpoint_override_warned: set[str] = set()
# Resolved (heat, cool) targets at each device's last active command, so the compressor
# hold can tell a deliberate target change from a room that merely reached its target.
_active_targets: dict[str, tuple[float | None, float | None]] = {}
# Devices whose overshoot target the hold already passed on; one send per hold, so a device
# that does not take the value is not commanded every cycle until the min-run ends.
_overshoot_sent: set[str] = set()
# Devices the hold already throttled to minimum (room past its target), one send per hold (#416).
_hold_modulated: set[str] = set()
# Last proportional setpoint send per device: (monotonic send time, (heat, cool) targets it was
# computed for). Any other command to the device drops the entry (#317).
_proportional_sent: dict[str, tuple[float, tuple[float | None, float | None]]] = {}
# hvac states in which a lower setpoint means more cooling, not less output
# Outcome of MPCController._call
_CALL_SENT = "sent"  # a command went to the device
_CALL_CONFIRMED = "confirmed"  # nothing sent: the device state or the sent-command cache already holds the value
_CALL_SKIPPED = "skipped"  # nothing sent: deadband, unsupported mode or handled elsewhere
_CALL_FAILED = "failed"  # the service call raised
_COOLING_SIDE_STATES = ("cool", "dry")
# states that cool only on devices which offer "cool" (a TRV in them is a heating device)
_COOLING_CAPABLE_STATES = ("heat_cool", "auto")


def _now() -> float:
    return time.monotonic()


def _cache_entry(service: str, data: dict) -> dict[str, Any]:
    """Build a cache entry from a service call."""
    return {
        "service": service,
        "hvac_mode": data.get("hvac_mode"),
        "temperature": data.get("temperature"),
        "target_temp_low": data.get("target_temp_low"),
        "target_temp_high": data.get("target_temp_high"),
        "fan_mode": data.get("fan_mode"),
    }


def _note_applied(entity_id: str, service: str, data: dict) -> None:
    """Record that the device is known to be in the state *data* describes."""
    entry = _cache_entry(service, data)
    if service == "set_hvac_mode":
        previous = _last_by_service.get((entity_id, service))
        if previous is None or previous.get("hvac_mode") != entry["hvac_mode"]:
            # A mode change can reset the device's setpoint, so it must be sent again
            _last_by_service.pop((entity_id, "set_temperature"), None)
            _sent_at.pop((entity_id, "set_temperature"), None)
    _last_by_service[(entity_id, service)] = entry
    _sent_at[(entity_id, service)] = _now()


def _remember_command(entity_id: str, service: str, data: dict) -> None:
    """Record a successfully sent command in both caches."""
    if entity_id not in _last_commands:
        for key in [k for k in _last_by_service if k[0] == entity_id]:
            del _last_by_service[key]
            _sent_at.pop(key, None)
    _proportional_sent.pop(entity_id, None)
    _last_commands[entity_id] = _cache_entry(service, data)
    _note_applied(entity_id, service, data)


def _cached_command(entity_id: str, service: str) -> dict[str, Any] | None:
    """Last command of *service* sent to the entity, if still believed to be in effect."""
    latest = _last_commands.get(entity_id)
    if latest is not None and latest.get("service") == service:
        return latest
    return _last_by_service.get((entity_id, service)) if latest is not None else None


def _cache_expired(entity_id: str, service: str) -> bool:
    """True when the cached command is old enough to be sent once more.

    Without state feedback the cache is all we know, so it can never notice a
    lost IR frame, a change on the remote or a restarted device.  Re-asserting
    now and then heals that; the interval is far above the 30 s cycle, so the
    beep-every-cycle behaviour of #416 does not return.
    """
    sent = _sent_at.get((entity_id, service))
    return sent is not None and _now() - sent >= COMMAND_CACHE_REASSERT_SECONDS


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


def match_fan_mode(state: Any, desired: str) -> str | None:
    """The device's own name for fan mode *desired*, or None if it has none.

    The configured value is matched against the advertised ``fan_modes``
    ignoring case and separators, because integrations spell the same speed
    differently ("Low", "low"; "Medium Low", "medium_low") and the panel's
    default ("low") is not taken from the device.
    """
    raw = (state.attributes.get("fan_modes") or []) if state else []
    if not isinstance(raw, (list, tuple)):
        return None
    modes: list[str] = list(raw)
    if desired in modes:
        return desired

    def fold(value: Any) -> str:
        return str(value).casefold()

    def norm(value: Any) -> str:
        return "".join(ch for ch in fold(value) if ch.isalnum())

    # Case first, so "High" wins over "High+" for "high"; separators only after that
    for key in (fold, norm):
        wanted = key(desired)
        match = next((mode for mode in modes if key(mode) == wanted), None)
        if match is not None:
            return match
    return None


def _target_moved(previous: float | None, current: float | None) -> bool:
    if previous is None or current is None:
        return previous is not current
    return abs(previous - current) > COMPRESSOR_HOLD_RETARGET_TOLERANCE


def _demand_lowered(previous: float | None, current: float | None, *, heating: bool) -> bool:
    """True when the target moved so that the unit has less to do (heat target down, cool target up)."""
    if previous is None:
        return False
    if current is None:
        return True
    return (previous - current if heating else current - previous) > COMPRESSOR_HOLD_RETARGET_TOLERANCE


def _carries_setpoint(data: dict) -> bool:
    """A set_temperature payload with a single setpoint or a low/high range."""
    return "temperature" in data or "target_temp_low" in data


def _snap_to_step(value: float, step: float | None) -> float:
    if step is None or step <= 0:
        return value
    return round(round(value / step) * step, 2)


def _resolve_step(hass: HomeAssistant, attributes: Any) -> float | None:
    """Setpoint step of a device: its ``target_temp_step`` or a °F whole-degree fallback.

    HA reports °F setpoints in whole degrees unless an entity overrides its
    precision, and entities without ``target_temp_step`` give no other hint.
    An unsnapped 75.9 then never equals the displayed 76 and is resent every
    cycle (#416).  The fallback applies only while the device shows a whole
    number, so entities that report tenths keep their resolution.
    """
    step = attributes.get("target_temp_step")
    if step is not None:
        return float(step)
    if hass.config.units.temperature_unit != UnitOfTemperature.FAHRENHEIT:
        return None
    try:
        return 1.0 if float(attributes.get("temperature")).is_integer() else None
    except (TypeError, ValueError):
        return None


def _learned_setback_step(hass: HomeAssistant, attributes: Any) -> float:
    """Snap step for a setback carrying a learned AC sensor offset, on a device without a step.

    Without a snap the setback can land between the values a device can show: one that
    shows whole degrees reads 27.5 back as 28 and gets it again every cycle.
    """
    try:
        if float(attributes.get("temperature")).is_integer():
            return 1.0
    except (TypeError, ValueError):
        pass
    return 1.0 if hass.config.units.temperature_unit == UnitOfTemperature.FAHRENHEIT else 0.5


def clear_command_cache() -> None:
    """Clear the sent-command cache (for tests)."""
    _last_commands.clear()
    _last_by_service.clear()
    _sent_at.clear()
    _proportional_sent.clear()
    _setpoint_override_warned.clear()
    _active_targets.clear()
    _overshoot_sent.clear()
    _hold_modulated.clear()


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
        _remember_command(entity_id, "set_temperature", {"temperature": setpoint})
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
        # if set_hvac_mode(off) is later ignored.  Skipped while the device is on
        # the cooling side: min_temp there is the hardest cooling demand, so the
        # unit would ramp up for the seconds before "off" arrives (#388). "heat_cool" and
        # "auto" count when the device can cool; a TRV in them (own schedule) keeps the frame.
        on_cooling_side = state is not None and (
            state.state in _COOLING_SIDE_STATES or (state.state in _COOLING_CAPABLE_STATES and "cool" in hvac_modes)
        )
        if state and effective_setpoint is not None and not on_cooling_side:
            await _send_idle_setpoint(hass, entity_id, state, effective_setpoint, area_id=area_id)

        try:
            await hass.services.async_call(
                "climate",
                "set_hvac_mode",
                {"entity_id": entity_id, "hvac_mode": "off"},
                blocking=True,
                context=make_roommind_context(),
            )
            _remember_command(entity_id, "set_hvac_mode", {"hvac_mode": "off"})
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
        _remember_command(entity_id, "set_temperature", svc_data)
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
    force_off: bool = False,
    use_setpoint_offset: bool = True,
    release_setback: frozenset[str] = frozenset(),
    head_offset: float = 0.0,
) -> None:
    """Idle a climate device per its configured idle_action.

    "off"      -> async_turn_off_climate() (existing behavior)
    "fan_only" -> hvac_mode=fan_only + set_fan_mode(idle_fan_mode)
    "setback"  -> keep current hvac_mode, shift target by offset
    "low"      -> lower setpoint to device min_temp, never send set_hvac_mode(off)
    Falls back to off when the configured action is not applicable.

    ``use_setpoint_offset`` lets the setback keep a direct device's sensor
    offset (#369); the controller turns it off in Managed mode.

    ``release_setback`` lists the hvac modes (``"heat"``/``"cool"``) the MPC plan
    expects no run of for ``SETBACK_RELEASE_BLOCKS``; a setback device in one of
    them is turned off instead of being held at the setback target (#255).

    ``head_offset`` is the learned offset of an AC's own sensor from the room
    while it is stopped. It moves the setback into the device's frame, so a unit
    whose sensor reads the warm layer under the ceiling does not restart while
    the room is still inside the setback.

    ``force_off`` marks an explicit user request to shut the room down
    (schedule_off_action / presence_away_action = "off").  It outranks the
    per-device idle_action, which only expresses "no heat/cool demand right
    now" — e.g. fan_only would keep an AC circulating air after the schedule
    ended (#368).  IDLE_ACTION_LOW is exempt: it exists because some battery
    Zigbee TRVs enter deep sleep in hvac_mode=off and lose later wake-up
    commands (#183), and lowering to min_temp already stops all heat output.
    """
    idle_action, idle_fan_mode = get_idle_action(devices, entity_id)
    if force_off and idle_action != IDLE_ACTION_LOW:
        idle_action = IDLE_ACTION_OFF
    if idle_action == IDLE_ACTION_HOLD:
        # Past the hold band, or for a device the controller does not hold
        idle_action = IDLE_ACTION_SETBACK

    # Fallback low setpoint (in HA display units) for devices where min_temp
    # is not effective (e.g. Wavin Sentio with min_temp=0 or high min_temp).
    fallback_temp: float | None = None
    if targets is not None and targets.heat is not None:
        fallback_temp = celsius_to_ha_temp(hass, targets.heat - DEFAULT_IDLE_SETBACK_OFFSET)

    # --- LOW branch ---
    # Some TRVs (e.g. battery Zigbee valves) enter deep-sleep hibernation after
    # extended time in hvac_mode=off, causing later wake-up commands to be lost.
    # "low" keeps the device out of off-mode by only lowering the setpoint.
    if idle_action == IDLE_ACTION_LOW:
        state = hass.states.get(entity_id)
        if state is None:
            return
        effective_setpoint = _resolve_idle_setpoint(
            state,
            fallback_temp,
            area_id=area_id,
            entity_id=entity_id,
        )
        if effective_setpoint is not None:
            await _send_idle_setpoint(hass, entity_id, state, effective_setpoint, area_id=area_id)
        return

    # --- SETBACK branch ---
    if idle_action == IDLE_ACTION_SETBACK:
        state = hass.states.get(entity_id)
        current_hvac = state.state if state else None

        if current_hvac in release_setback:
            _LOGGER.debug(
                "Area '%s': no %s run planned for '%s' within the hour, setback ends in off",
                area_id,
                current_hvac,
                entity_id,
            )
            await async_turn_off_climate(hass, entity_id, area_id=area_id, fallback_setpoint=fallback_temp)
            return

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

        # Direct devices keep their sensor offset (#369), but only where the active
        # path applies it too (Full Control).
        sensor_offset = get_setpoint_offset(devices, entity_id) if use_setpoint_offset else 0.0
        if current_hvac == "heat" and targets.heat is not None:
            setback_temp = targets.heat + sensor_offset + head_offset - DEFAULT_IDLE_SETBACK_OFFSET
        elif current_hvac == "cool" and targets.cool is not None:
            setback_temp = targets.cool + sensor_offset + head_offset + DEFAULT_IDLE_SETBACK_OFFSET
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
        step = _resolve_step(hass, state.attributes)
        if step is None and head_offset:
            step = _learned_setback_step(hass, state.attributes)
        if step is not None:
            ha_t = _snap_to_step(ha_t, step)
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
            _remember_command(entity_id, "set_temperature", {"temperature": ha_t})
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

    # A fan mode the device does not have is left alone, like an empty idle_fan_mode:
    # waiting for the device to report it would resend fan_only every cycle.
    fan_mode = match_fan_mode(state, idle_fan_mode) if idle_fan_mode else None
    if idle_fan_mode and fan_mode is None:
        _LOGGER.debug(
            "Area '%s': device '%s' does not support fan_mode '%s' (available: %s)",
            area_id,
            entity_id,
            idle_fan_mode,
            (state.attributes.get("fan_modes") or []) if state else [],
        )

    # Redundancy check: already in fan_only with correct fan_mode
    if state and state.state == "fan_only":
        current_fan = state.attributes.get("fan_mode")
        if fan_mode is None or current_fan == fan_mode:
            return

    # Cache fallback for IR devices (only when device has no reliable state)
    if _should_use_cache(state):
        cached = _last_commands.get(entity_id)
        if cached and cached.get("service") == "set_hvac_mode" and cached.get("hvac_mode") == "fan_only":
            cached_fan = _last_by_service.get((entity_id, "set_fan_mode"))
            if fan_mode is None or (cached_fan is not None and cached_fan.get("fan_mode") == fan_mode):
                return

    try:
        await hass.services.async_call(
            "climate",
            "set_hvac_mode",
            {"entity_id": entity_id, "hvac_mode": "fan_only"},
            blocking=True,
            context=make_roommind_context(),
        )
        _remember_command(entity_id, "set_hvac_mode", {"hvac_mode": "fan_only"})
        # The device may have come back to fan_only on another speed than last time
        _last_by_service.pop((entity_id, "set_fan_mode"), None)
        _sent_at.pop((entity_id, "set_fan_mode"), None)
    except Exception:  # noqa: BLE001
        _LOGGER.warning(
            "Area '%s': climate.set_hvac_mode(fan_only) failed on '%s'",
            area_id,
            entity_id,
            exc_info=True,
        )
        return

    if fan_mode is not None:
        try:
            await hass.services.async_call(
                "climate",
                "set_fan_mode",
                {"entity_id": entity_id, "fan_mode": fan_mode},
                blocking=True,
                context=make_roommind_context(),
            )
            _note_applied(entity_id, "set_fan_mode", {"fan_mode": fan_mode})
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "Area '%s': climate.set_fan_mode('%s') failed on '%s'",
                area_id,
                fan_mode,
                entity_id,
                exc_info=True,
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
MAX_HORIZON_HOURS = 12
HORIZON_MULTIPLIER = 2.5
DEFAULT_OUTDOOR_TEMP_FALLBACK = 10.0
SAFETY_GUARD_MIN_BLOCKS = 6  # Minimum guard horizon (30 min floor)
# Setback bridges short pauses (#87). After SETBACK_HOLD_MINUTES of idle a setback device
# is switched off if the plan has no run of its kind for SETBACK_RELEASE_BLOCKS (#255).
# The plan alone is no gate: after an AC heating run it saw an hour of idle where the
# room called for heat again after 15-30 min (sim multisplit-setback-release).
SETBACK_HOLD_MINUTES = 60
SETBACK_RELEASE_BLOCKS = 12
GUARD_PREDICTION_MARGIN = 0.2  # °C margin for prediction-based guard bypass
HARD_OVERSHOOT_CEILING = 1.0  # °C — model-independent max overshoot before forced idle
# A fast system only starts once the room is this far past the target: the optimizer
# alone switched at the target itself, every other cycle. One sensor step for TRVs and
# for cooling; an AC heating the air node sees it drop back 0.2-0.3 K right after a
# stop, so heating that an AC takes part in (also TRV + heat pump rooms, orchestrated
# or not) uses the bang-bang hysteresis. Cooling with 0.2 K let a sunny room sit above
# the cool target almost three times as long for ~7 % fewer starts (sim ekf-summer-ac).
MPC_START_HYSTERESIS = 0.1
_TEMP_EPSILON = 1e-6  # sensor floats like 20.899999999999 still read 20.9

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
    *,
    override_active: bool = False,
) -> tuple[bool, bool]:
    """Determine whether heating/cooling are allowed for a room.

    Accounts for climate_mode, device availability, and outdoor temperature
    gating.  This is the single source of truth — used by coordinator,
    controller, and analytics.

    When *acs_can_heat* is True, ACs that support heating (heat pumps)
    contribute to the heating capability of the room.

    When *override_active* is True, outdoor temperature gating is bypassed
    because the user has explicitly requested a specific target temperature.
    """
    climate_mode = room_config.get("climate_mode", "auto")
    can_heat = climate_mode != CLIMATE_MODE_COOL_ONLY and (
        bool(get_trv_eids(room_config.get("devices", []))) or acs_can_heat
    )
    can_cool = climate_mode != CLIMATE_MODE_HEAT_ONLY and bool(get_ac_eids(room_config.get("devices", [])))

    if outdoor_temp is not None and not override_active:
        if outdoor_temp > outdoor_heating_max:
            can_heat = False
        if outdoor_temp < outdoor_cooling_min:
            can_cool = False

    return can_heat, can_cool


def outdoor_gate_limits(outdoor_known: bool, cooling_min: float, heating_max: float) -> tuple[float, float]:
    """Optimizer outdoor gate as (cooling_min, heating_max), open when the outdoor temperature is unknown.

    Without a reading or forecast the horizon is DEFAULT_OUTDOOR_TEMP_FALLBACK, a placeholder
    below the cooling minimum; gating on it barred the room from cooling (#464).
    get_can_heat_cool() does not gate on a missing reading either.
    """
    if outdoor_known:
        return cooling_min, heating_max
    return float("-inf"), float("inf")


def fill_missing_targets(heat: float | None, cool: float | None, fallback: float) -> tuple[float, float]:
    """Give the optimizer a numeric (heat, cool) pair for a possibly one-sided target.

    ``None`` means "no demand on that side". With both sides missing the room is
    held where it is (``fallback``). A missing heat target must not be filled with
    a room temperature above the cool target: the optimizer raises the cool target
    to at least the heat target, so a cooling-only override (``heat=None``) would
    otherwise be lifted to the current room temperature and never cool (#388).
    """
    if cool is None:
        return (fallback, fallback) if heat is None else (heat, fallback)
    if heat is None:
        return min(fallback, cool), cool
    return heat, cool


def heat_start_hysteresis(ac_heats: bool, has_trvs: bool) -> float:
    """Distance below the heat target a fast heating run starts at (see MPC_START_HYSTERESIS)."""
    return BANGBANG_HEAT_HYSTERESIS if ac_heats or not has_trvs else MPC_START_HYSTERESIS


def is_slow_heat(min_run_blocks: int) -> bool:
    """A heating system with a longer min run than an AC (UFH) must start before the drift."""
    return min_run_blocks > get_min_run_blocks("", PLAN_DT_MINUTES)


def compute_horizon_blocks(model: Any, current_temp: float, target_temp: float | None) -> int:
    """Adaptive MPC horizon in blocks: long enough to reach the target, at least MIN_HORIZON_HOURS."""
    if target_temp is None:
        return int(MIN_HORIZON_HOURS * 60 / PLAN_DT_MINUTES)
    delta = abs(current_temp - target_temp) + 3.0  # extra margin
    # The slower direction sets the horizon: a heat-only room keeps the untrained default
    # cooling rate, and taking the faster one cut a slow room's pre-heat window to 2 h.
    # Q_fast: the air pull-down of an AC room is part of how fast it reaches the target.
    rates = [q for q in (model.Q_heat, model.Q_cool + model.Q_fast) if q > 0]
    if rates:
        rate = min(rates) / (model.C * 60)  # °C/min approx
        if rate > 0:
            est_minutes = delta / rate
            horizon_minutes = min(MAX_HORIZON_HOURS * 60, max(MIN_HORIZON_HOURS * 60, est_minutes * HORIZON_MULTIPLIER))
            return max(24, int(horizon_minutes / PLAN_DT_MINUTES))
    return int(MIN_HORIZON_HOURS * 60 / PLAN_DT_MINUTES)  # default 24 blocks = 2h


def gentle_power(
    optimizer: MPCOptimizer,
    mode: str,
    current_temp: float,
    outdoor_temp: float,
    target: float,
    *,
    q_solar: float,
    q_residual: float,
    q_occupancy: float,
    rebound_charge: float | None = None,
) -> float:
    """Closed-form power for a min-run continuation of *mode*, at least MIN_POWER_FRACTION."""
    pf, pf_mode = optimizer.compute_optimal_power(
        current_temp,
        outdoor_temp,
        target,
        PLAN_DT_MINUTES,
        q_solar=q_solar,
        q_residual=q_residual,
        q_occupancy=q_occupancy,
        rebound_charge=rebound_charge,
    )
    return max(pf, MIN_POWER_FRACTION) if pf_mode == mode else MIN_POWER_FRACTION


def decide_mpc_action(
    action: str,
    power_fraction: float,
    current_temp: float,
    heat_target_series: list[float],
    cool_target_series: list[float],
    *,
    guard_blocks: int,
    slow_heat: bool,
    previous_mode: str,
    heat_in_min_run: bool,
    cool_in_min_run: bool,
    can_heat: bool,
    can_cool: bool,
    heat_hysteresis: float,
    idle_drift: Callable[[float], float],
    continuation_power: Callable[[str, float], float],
    area_id: str | None = None,
) -> tuple[str, float]:
    """Apply the controller's rules to the optimizer's first block.

    Shared by ``MPCController._evaluate_mpc`` and the analytics prediction, so the
    prediction line follows what RoomMind actually does. Pure apart from the two
    callbacks: ``idle_drift(minutes)`` predicts the room without HVAC,
    ``continuation_power(mode, target)`` gives the power of a min-run continuation.
    ``area_id`` enables the hard-ceiling log lines (the prediction passes None).

    Order: hard ceiling, model guard, then the switching hysteresis.
    """
    near_heat = heat_target_series[:guard_blocks]
    near_cool = cool_target_series[:guard_blocks]

    # Hard ceiling: force idle when significantly past target, regardless
    # of model predictions or min-run window.  Prevents runaway
    # heating/cooling from a miscalibrated thermal model (#152).
    if near_heat and action == MODE_HEATING and current_temp > max(near_heat) + HARD_OVERSHOOT_CEILING:
        if area_id is not None:
            _LOGGER.info(
                "Hard ceiling: suppressing HEATING for %s at %.1f°C (target max %.1f°C + %.1f°C ceiling)",
                area_id,
                current_temp,
                max(near_heat),
                HARD_OVERSHOOT_CEILING,
            )
        action = MODE_IDLE
        power_fraction = 0.0
    elif near_cool and action == MODE_COOLING and current_temp < min(near_cool) - HARD_OVERSHOOT_CEILING:
        if area_id is not None:
            _LOGGER.info(
                "Hard ceiling: suppressing COOLING for %s at %.1f°C (target min %.1f°C - %.1f°C ceiling)",
                area_id,
                current_temp,
                min(near_cool),
                HARD_OVERSHOOT_CEILING,
            )
        action = MODE_IDLE
        power_fraction = 0.0

    # Model-based guard: suppress when model predicts temp stays past
    # target, but allow pre-heating when a drift is predicted. Only a slow
    # heating system may start early: a fast one catches the drift once it
    # happens, and an AC's fast air node makes the 1-node model predict steep
    # drifts that would restart it right after every stop.
    elif near_heat and action == MODE_HEATING and current_temp >= max(near_heat):
        if slow_heat and idle_drift(guard_blocks * PLAN_DT_MINUTES) < min(near_heat) - GUARD_PREDICTION_MARGIN:
            pass  # model predicts dip — allow optimizer's HEAT decision
        elif not heat_in_min_run:
            action = MODE_IDLE
            power_fraction = 0.0
    elif near_cool and action == MODE_COOLING and current_temp <= min(near_cool):
        if not cool_in_min_run:
            action = MODE_IDLE
            power_fraction = 0.0

    # Switching hysteresis. The optimizer has no memory: it started the moment the
    # room read below the target and stopped the moment it read above, so a sensor
    # resolution step (or an AC's air node relaxing right after a stop) switched the
    # device every 30 s cycle. A run only starts past the start hysteresis, unless a
    # stricter target is coming up (pre-heating/pre-cooling stays the optimizer's
    # call), and a run the optimizer wants to end stays on until its minimum run time
    # is over, at gentle power. A slow heating system (UFH) keeps the optimizer's
    # heating decisions as they are. The hard ceiling still ends a run at once (it set
    # IDLE above, and the room is then beyond ``target + ceiling``, where nothing here
    # re-enables it).
    heat_now = heat_target_series[0]
    cool_now = cool_target_series[0]
    heat_rising = max(near_heat) > heat_now
    cool_falling = min(near_cool) < cool_now

    if action == MODE_HEATING:
        if not slow_heat and previous_mode != MODE_HEATING and not heat_rising:
            if current_temp > heat_now - heat_hysteresis - _TEMP_EPSILON:
                return MODE_IDLE, 0.0
    elif action == MODE_COOLING:
        if previous_mode != MODE_COOLING and not cool_falling:
            if current_temp < cool_now + MPC_START_HYSTERESIS + _TEMP_EPSILON:
                return MODE_IDLE, 0.0
    elif (
        not slow_heat
        and previous_mode == MODE_HEATING
        and can_heat
        and current_temp < max(near_heat) + HARD_OVERSHOOT_CEILING
        and heat_in_min_run
    ):
        return MODE_HEATING, continuation_power(MODE_HEATING, heat_now)
    elif (
        previous_mode == MODE_COOLING
        and can_cool
        and current_temp > min(near_cool) - HARD_OVERSHOOT_CEILING
        and cool_in_min_run
    ):
        return MODE_COOLING, continuation_power(MODE_COOLING, cool_now)
    return action, power_fraction


def infer_running_mode(hass: HomeAssistant, room_config: dict, before: float | None = None) -> str | None:
    """Mode the room's devices run in right now, to seed the controller after a start.

    The previous mode lives in memory only: after a reload or restart a run inside the
    start hysteresis band (20.9 at a 21 target) would read as "idle" and be switched off
    once. A device counts when it reports ``hvac_action`` heating/cooling, unless the last
    command RoomMind sent it (kept across an integration reload) switched it off, which
    marks a manual switch-on; ``before`` (monotonic) limits that to commands sent before
    the start, not the ones of the first cycles. Devices disagreeing on the direction
    seed nothing. None while a device has no usable state yet (Zigbee TRVs are
    unavailable for a while after a restart): the caller asks again in the next cycle.
    """
    heating = cooling = False
    for eid in get_all_entity_ids(room_config.get("devices", [])):
        state = hass.states.get(eid)
        if state is None:
            continue
        if state.state in ("unavailable", "unknown"):
            return None
        last = _last_commands.get(eid)
        sent = _sent_at.get((eid, "set_hvac_mode"))
        if last is not None and last.get("hvac_mode") == "off" and (before is None or (sent or 0.0) < before):
            continue
        action = state.attributes.get("hvac_action")
        if action in ("heating", "preheating"):
            heating = True
        elif action == "cooling":
            cooling = True
    if heating and not cooling:
        return MODE_HEATING
    if cooling and not heating:
        return MODE_COOLING
    return MODE_IDLE


def is_mpc_enabled(settings: dict | None) -> bool:
    """Return False when the user picked simple on/off control (``control_mode``)."""
    return bool((settings or {}).get("control_mode", DEFAULT_CONTROL_MODE) != CONTROL_MODE_BANGBANG)


def is_mpc_active(
    model_manager: RoomModelManager,
    area_id: str,
    can_heat: bool,
    can_cool: bool,
    current_temp: float,
    outdoor_temp: float,
    *,
    settings: dict | None = None,
) -> bool:
    """Check if MPC control is active for a room.

    Single source of truth for MPC activation — used by coordinator
    and analytics.
    """
    if not is_mpc_enabled(settings):
        return False
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
        idle_since: float | None = None,
        shading_factor: float = 1.0,
        q_occupancy: float = 0.0,
        q_rebound: float | None = None,
        previous_heat_sources: str = "none",
        head_offsets: HeadOffsetTracker | None = None,
    ) -> None:
        self.hass = hass
        self.room_config = room_config
        self.thermostats: list[str] = get_trv_eids(room_config.get("devices", []))
        self.acs: list[str] = get_ac_eids(room_config.get("devices", []))
        self._devices: list[dict] = room_config.get("devices", [])
        self._direct_eids: set[str] = get_direct_setpoint_eids(self._devices)
        self._direct_offsets: dict[str, float] = get_setpoint_offsets(self._devices)
        self.climate_mode: str = room_config.get("climate_mode", "auto")
        self.outdoor_temp = outdoor_temp
        self.outdoor_forecast = outdoor_forecast or []
        self.previous_mode = previous_mode
        self.has_external_sensor = has_external_sensor
        self._model_manager = model_manager
        self._area_id = room_config.get("area_id", "unknown")
        self._target_resolver = target_resolver
        self.last_plan: MPCPlan | None = None
        self._peak_temps_unoccupied: list[float] | None = None
        self.q_solar = q_solar
        self._latitude = latitude
        self._longitude = longitude
        self._cloud_series = cloud_series or []
        self.q_residual = q_residual
        self._heating_system_type = heating_system_type
        # Heating system whose run rules apply this cycle (see _resolve_run_system)
        self._run_system = heating_system_type
        self._previous_heat_sources = previous_heat_sources
        self._mode_on_since = mode_on_since
        self._idle_since = idle_since
        self._shading_factor = shading_factor
        self.q_occupancy = q_occupancy
        # AC rebound charge now (residual_heat); None leaves the air/mass term out
        self.q_rebound = q_rebound
        # Learned AC sensor offsets (device reading - room sensor); None leaves setpoints in the room frame
        self._head_offsets = head_offsets
        self._idle_targets: TargetTemps | None = None
        self._force_off = False
        # Strictest heat / cool target within the MPC guard window (set by _evaluate_mpc)
        self._lead_heat: float | None = None
        self._lead_cool: float | None = None
        # hvac modes whose setback devices may switch off (set by _evaluate_mpc)
        self._setback_release: frozenset[str] = frozenset()
        # ACs the idle action "hold" kept running at the target this cycle
        self.held_at_target: set[str] = set()

        s = settings or {}
        self._mpc_enabled = is_mpc_enabled(s)
        self.outdoor_cooling_min = s.get("outdoor_cooling_min", DEFAULT_OUTDOOR_COOLING_MIN)
        self.outdoor_heating_max = s.get("outdoor_heating_max", DEFAULT_OUTDOOR_HEATING_MAX)

        # Comfort weight from UI slider (0-100, default 70 = comfort-biased).
        # Maps to optimizer w_comfort / w_energy ratio.
        cw = s.get("comfort_weight", 70)
        self._w_comfort = max(1.0, cw / 10.0)
        self._w_energy = max(1.0, (100 - cw) / 10.0)
        self._preheat_max_blocks = preheat_max_blocks(cw, PLAN_DT_MINUTES)
        self._approach_rate = min(1.0, APPROACH_RATE_MIN + (1.0 - APPROACH_RATE_MIN) * cw / DEFAULT_COMFORT_WEIGHT)
        self._ac_boost_delta = min(
            AC_BOOST_DELTA_MAX,
            AC_BOOST_DELTA_MIN + (AC_BOOST_DELTA_MAX - AC_BOOST_DELTA_MIN) * cw / DEFAULT_COMFORT_WEIGHT,
        )

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

        self._lead_heat = self._lead_cool = None
        self._setback_release = frozenset()
        if not self.has_external_sensor:
            mode = self._evaluate_managed_mode(targets)
            return mode, 1.0  # managed mode: device self-regulates

        if not self._mpc_enabled:
            mode = self._evaluate_bangbang(current_temp, targets)
            return mode, 1.0 if mode != MODE_IDLE else 0.0

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
        # Cooling always runs on an AC; the UFH profile of a hybrid room is not its run time.
        system = self._run_system if mode == MODE_HEATING else ""
        min_run_seconds = get_min_run_blocks(system, PLAN_DT_MINUTES) * PLAN_DT_MINUTES * 60
        return (time.time() - self._mode_on_since) < min_run_seconds

    def _setback_hold_over(self) -> bool:
        """Whether the room has been idle long enough for a setback device to switch off."""
        if self.previous_mode != MODE_IDLE or self._idle_since is None:
            return False
        return time.time() - self._idle_since >= SETBACK_HOLD_MINUTES * 60

    def _resolve_run_system(self, current_temp: float | None, heat_target: float | None) -> str:
        """Heating system whose run rules (min run, drift pre-heat, no start hysteresis) apply.

        Heat source orchestration closes a small gap with the AC alone; the UFH rules of
        the room would then hold that AC for 30 min and let it pre-heat on a predicted
        drift. Asks the orchestrator which sources a heating run would use now (with its
        hysteresis on the sources of the running run) and falls back to the running
        sources when it has no answer (room at the target).
        """
        system = self._heating_system_type
        if (
            system
            and self.room_config.get("heat_source_orchestration", False)
            and self.has_external_sensor
            and self.thermostats
            and self.acs
        ):
            plan = evaluate_heat_sources(
                room_config=self.room_config,
                mode=MODE_HEATING,
                power_fraction=1.0,
                current_temp=current_temp,
                target_temp=heat_target,
                outdoor_temp=self.outdoor_temp,
                previous_active_sources=self._previous_heat_sources,
                hass=self.hass,
            )
            sources = (
                plan.active_sources
                if plan is not None and plan.active_sources != "none"
                else self._previous_heat_sources
            )
            if sources == "secondary":
                system = ""
        self._run_system = system
        return system

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
            q_rebound=None if self.q_rebound is None else mean_rebound(self.q_rebound, False, dt_minutes),
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
        # The unfilled series keep None, so the lead target for direct devices never
        # becomes the room temperature a "no target" block was filled with.
        raw_heat: list[float | None] = []
        raw_cool: list[float | None] = []
        if self._target_resolver is not None:
            now = time.time()
            dt_seconds = PLAN_DT_MINUTES * 60
            raw_targets = [self._target_resolver(now + i * dt_seconds) for i in range(horizon_blocks)]
            # Extract separate heat and cool series from TargetTemps
            if raw_targets and isinstance(raw_targets[0], TargetTemps):
                pairs = cast(list[TargetTemps], raw_targets)
                raw_heat = [t.heat for t in pairs]
                raw_cool = [t.cool for t in pairs]
                filled = [fill_missing_targets(t.heat, t.cool, current_temp) for t in pairs]
                heat_target_series = [h for h, _ in filled]
                cool_target_series = [c for _, c in filled]
            else:
                # Legacy resolver returning float|None
                float_targets = cast(list[float | None], raw_targets)
                raw_heat = list(float_targets)
                raw_cool = list(float_targets)
                heat_target_series = [t if t is not None else current_temp for t in float_targets]
                cool_target_series = list(heat_target_series)
        else:
            fallback_h, fallback_c = fill_missing_targets(targets.heat, targets.cool, current_temp)
            heat_target_series = [fallback_h] * horizon_blocks
            cool_target_series = [fallback_c] * horizon_blocks

        run_system = self._resolve_run_system(current_temp, targets.heat)
        min_run = get_min_run_blocks(run_system, PLAN_DT_MINUTES)

        cooling_min, heating_max = outdoor_gate_limits(
            self.outdoor_temp is not None or bool(self.outdoor_forecast),
            self.outdoor_cooling_min,
            self.outdoor_heating_max,
        )

        optimizer = MPCOptimizer(
            model=model,
            can_heat=can_heat,
            can_cool=can_cool,
            w_comfort=self._w_comfort,
            w_energy=self._w_energy,
            outdoor_cooling_min=cooling_min,
            outdoor_heating_max=heating_max,
            min_run_blocks=min_run,
            cool_min_run_blocks=get_min_run_blocks("", PLAN_DT_MINUTES),
            override_active=is_override_active(self.room_config),
            heating_system_type=run_system,
            approach_rate=self._approach_rate,
            start_penalty=slow_start_penalty(min_run, PLAN_DT_MINUTES),
            fast_heater_shares_model=check_acs_can_heat(self.hass, self.room_config),
            preheat_max_blocks=self._preheat_max_blocks,
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
            initial_mode=self.previous_mode,
            rebound_charge=self.q_rebound,
        )
        self.last_plan = plan
        # Shading can attenuate solar gain, never the body heat of whoever just
        # walked in, so the cover logic reads a peak computed without it (#418).
        # Replaying the plan keeps the control decision itself untouched.
        _unoccupied = (
            optimizer.simulate_plan(
                plan,
                current_temp,
                outdoor_series,
                PLAN_DT_MINUTES,
                solar_series=solar_series,
                residual_series=residual_series,
                occupancy_series=None,
                rebound_charge=self.q_rebound,
            )
            if self.q_occupancy > 0
            else None
        )
        self._peak_temps_unoccupied = _unoccupied if _unoccupied and len(_unoccupied) > 1 else None

        # The guard horizon scales with heating system response time and
        # matches the optimizer's per-system lookahead (read from the plan) so
        # mild-weather UFH pre-heat decisions don't get suppressed by a short
        # drift check.
        guard_blocks = max(SAFETY_GUARD_MIN_BLOCKS, min_run, plan.lookahead_blocks, plan.preheat_blocks + 1)
        lead_heat = [h for h in raw_heat[:guard_blocks] if h is not None]
        lead_cool = [c for c in raw_cool[:guard_blocks] if c is not None]
        self._lead_heat = max(lead_heat) if lead_heat else None
        self._lead_cool = min(lead_cool) if lead_cool else None
        outdoor_now = outdoor_series[0]
        action = decide_mpc_action(
            plan.get_current_action(),
            plan.get_current_power_fraction(),
            current_temp,
            heat_target_series,
            cool_target_series,
            guard_blocks=guard_blocks,
            slow_heat=is_slow_heat(min_run),
            previous_mode=self.previous_mode,
            heat_in_min_run=self._within_min_run(MODE_HEATING),
            cool_in_min_run=self._within_min_run(MODE_COOLING),
            can_heat=can_heat,
            can_cool=can_cool,
            heat_hysteresis=heat_start_hysteresis(
                check_acs_can_heat(self.hass, self.room_config), bool(self.thermostats)
            ),
            idle_drift=lambda minutes: self._predict_idle_drift(current_temp, minutes),
            continuation_power=lambda mode, target: self._gentle_power(
                optimizer, mode, current_temp, outdoor_now, target
            ),
            area_id=self._area_id,
        )
        if action[0] == MODE_IDLE and self._setback_hold_over() and len(plan.actions) >= SETBACK_RELEASE_BLOCKS:
            ahead = plan.actions[:SETBACK_RELEASE_BLOCKS]
            self._setback_release = frozenset(
                hvac for hvac, run in (("heat", MODE_HEATING), ("cool", MODE_COOLING)) if run not in ahead
            )
        return action

    def _gentle_power(
        self, optimizer: MPCOptimizer, mode: str, current_temp: float, outdoor_temp: float, target: float
    ) -> float:
        """Closed-form power for *mode*, at least MIN_POWER_FRACTION."""
        return gentle_power(
            optimizer,
            mode,
            current_temp,
            outdoor_temp,
            target,
            q_solar=self.q_solar * self._shading_factor,
            q_residual=self.q_residual,
            q_occupancy=self.q_occupancy,
            rebound_charge=self.q_rebound,
        )

    def _evaluate_bangbang(
        self,
        current_temp: float | None,
        targets: TargetTemps,
    ) -> str:
        """Fallback: bang-bang with hysteresis and dead-band support."""
        if current_temp is None:
            return MODE_IDLE

        self._resolve_run_system(current_temp, targets.heat)
        can_heat, can_cool = self._get_can_heat_cool()
        heat_target = targets.heat
        cool_target = targets.cool

        # Mode stickiness. While the model learns, the min run keeps a run going past the
        # target only up to the hard ceiling: a strong AC in a small room otherwise ran its
        # min run at full boost and overheated by 4-8 K. Power stays binary (an AC does not
        # deliver a throttled fraction, the EKF learned a 3x heating rate from one). Simple
        # mode and slow heating systems keep the plain rule (UFH + split: the shorter
        # learning runs left the screed idle for hours on one seed).
        capped = self._mpc_enabled and not is_slow_heat(get_min_run_blocks(self._run_system, PLAN_DT_MINUTES))
        ceiling = HARD_OVERSHOOT_CEILING if capped else math.inf
        if self.previous_mode == MODE_HEATING and can_heat and heat_target is not None:
            if current_temp < heat_target or (
                self._within_min_run(MODE_HEATING) and current_temp < heat_target + ceiling
            ):
                return MODE_HEATING
            return MODE_IDLE

        if self.previous_mode == MODE_COOLING and can_cool and cool_target is not None:
            if current_temp > cool_target or (
                self._within_min_run(MODE_COOLING) and current_temp > cool_target - ceiling
            ):
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
        _override = is_override_active(self.room_config)
        can_heat, can_cool = get_can_heat_cool(
            self.room_config,
            self.outdoor_temp,
            self.outdoor_cooling_min,
            self.outdoor_heating_max,
            acs_can_heat=check_acs_can_heat(self.hass, self.room_config),
            override_active=_override,
        )

        if self.outdoor_temp is not None:
            if _override and (
                self.outdoor_temp < self.outdoor_cooling_min or self.outdoor_temp > self.outdoor_heating_max
            ):
                _LOGGER.debug(
                    "%s: override active, outdoor gate bypassed (outdoor=%.1f, cooling_min=%.1f, heating_max=%.1f)",
                    self._area_id,
                    self.outdoor_temp,
                    self.outdoor_cooling_min,
                    self.outdoor_heating_max,
                )
            elif not _override:
                if self.outdoor_temp < self.outdoor_cooling_min:
                    _LOGGER.debug(
                        "%s: outdoor gate blocking cooling (outdoor=%.1f < cooling_min=%.1f)",
                        self._area_id,
                        self.outdoor_temp,
                        self.outdoor_cooling_min,
                    )
                if self.outdoor_temp > self.outdoor_heating_max:
                    _LOGGER.debug(
                        "%s: outdoor gate blocking heating (outdoor=%.1f > heating_max=%.1f)",
                        self._area_id,
                        self.outdoor_temp,
                        self.outdoor_heating_max,
                    )

        return can_heat, can_cool

    def _compute_horizon_blocks(self, model: Any, current_temp: float, target_temp: float | None) -> int:
        """Compute adaptive horizon in blocks (see ``compute_horizon_blocks``)."""
        return compute_horizon_blocks(model, current_temp, target_temp)

    def _build_outdoor_series(self, n_blocks: int) -> list[float]:
        """Build outdoor temperature series for the MPC horizon.

        Block 0 uses the real-time outdoor sensor reading (most accurate for
        "now"). Subsequent blocks expand each hourly forecast entry to
        ``60 // PLAN_DT_MINUTES`` blocks. The series is padded with the last
        forecast value when the horizon exceeds the available forecast length.
        """
        if not self.outdoor_forecast:
            T = self.outdoor_temp if self.outdoor_temp is not None else DEFAULT_OUTDOOR_TEMP_FALLBACK
            return [T] * n_blocks

        blocks_per_hour = 60 // PLAN_DT_MINUTES
        fallback = self.outdoor_temp if self.outdoor_temp is not None else DEFAULT_OUTDOOR_TEMP_FALLBACK

        series: list[float] = []
        for f in self.outdoor_forecast:
            temp = f.get("temperature", fallback)
            series.extend([temp] * blocks_per_hour)
            if len(series) >= n_blocks:
                break

        if self.outdoor_temp is not None:
            series[0] = self.outdoor_temp

        while len(series) < n_blocks:
            series.append(series[-1])

        return series[:n_blocks]

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

        Excludes occupancy heat: this value drives shading decisions, and covers
        cannot counteract metabolic gain (#418).

        Available after async_evaluate() has been called.
        Returns None if no MPC plan was computed (bang-bang mode or insufficient data).
        """
        plan = self.last_plan
        if plan is None or not plan.temperatures or len(plan.temperatures) < 2:
            return None
        temperatures = self._peak_temps_unoccupied or plan.temperatures
        return max(temperatures[1:])  # Skip index 0 (current T)

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
        force_off: bool = False,
    ) -> None:
        """Apply the determined mode with proportional valve control.

        ``force_off`` signals that the room was shut down on purpose
        (schedule_off_action / presence_away_action = "off") rather than merely
        having no demand, so per-device idle_action must not keep devices
        running (#368).
        """
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
        self._force_off = force_off
        for eid in self.thermostats + self.acs:
            if eid not in _forced_on:
                _overshoot_sent.discard(eid)
                _hold_modulated.discard(eid)

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
        # Only the active branches use it: the hold and the setback keep the current target.
        direct_target = self.direct_target(mode, effective_target)

        # Dynamic boost: use device-reported limits, fall back to constants
        trv_heat_boost = heating_boost_target if heating_boost_target is not None else HEATING_BOOST_TARGET
        ac_heat_boost = ac_heating_boost_target if ac_heating_boost_target is not None else AC_HEATING_BOOST_TARGET
        ac_cool_boost = cooling_boost_target if cooling_boost_target is not None else AC_COOLING_BOOST_TARGET

        can_heat, can_cool = self._get_can_heat_cool()

        _exclude = exclude_eids or set()
        thermostats = [e for e in self.thermostats if e not in _exclude]
        # ACs were previously never filtered because exclude_eids only ever
        # carried TRVs (valve protection is TRV-only).  Coil dry excludes ACs.
        acs = [e for e in self.acs if e not in _exclude]

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
                    await async_idle_device(
                        self.hass,
                        eid,
                        self._devices,
                        area_id=self._area_id,
                        targets=targets,
                        use_setpoint_offset=self.has_external_sensor,
                        head_offset=self._head_offset(eid, "idle"),
                    )
                    continue
                if can_heat and ha_heat_target is not None:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "heat"})
                    await self._call(
                        "set_temperature",
                        {"entity_id": eid, "temperature": ha_heat_target, "hvac_mode": "heat"},
                        temp_intent="heat",
                    )
                else:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "off"})
            for eid in acs:
                if eid in _forced_off:
                    await async_idle_device(
                        self.hass,
                        eid,
                        self._devices,
                        area_id=self._area_id,
                        targets=targets,
                        use_setpoint_offset=self.has_external_sensor,
                        head_offset=self._head_offset(eid, "idle"),
                    )
                    continue
                ac_state = self.hass.states.get(eid)
                ac_modes = _effective_ac_modes(ac_state)
                # A command must never carry the opposite side's target. Single
                # setpoint heat_cool regulates from both sides onto the one value
                # it gets, so a band with only a heating target would make the
                # device cool down to it; the directed branches below have the
                # same problem and now require their own target. Only a range
                # device can express a one-sided band, by parking the unused side
                # on its own limit.
                ac_target = ha_cool_target if ha_cool_target is not None else ha_heat_target
                ac_heat_target = ha_heat_target if ha_heat_target is not None else ha_cool_target
                _both_targets = ha_heat_target is not None and ha_cool_target is not None
                _known_range = bool(ac_state and ac_state.attributes.get("target_temp_low") is not None)
                if ac_target is None:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "off"})
                elif "heat_cool" in ac_modes and (_both_targets or _known_range):
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "heat_cool"})
                    # Dual-setpoint: send both targets when device uses range mode
                    ac_state_now = self.hass.states.get(eid)
                    is_range = ac_state_now and ac_state_now.attributes.get("target_temp_low") is not None
                    if is_range:
                        _attrs = ac_state_now.attributes if ac_state_now else {}
                        low = ha_heat_target if ha_heat_target is not None else _attrs.get("min_temp")
                        high = ha_cool_target if ha_cool_target is not None else _attrs.get("max_temp")
                    else:
                        low = high = None
                    if low is not None and high is not None:
                        await self._call(
                            "set_temperature",
                            {
                                "entity_id": eid,
                                "target_temp_low": min(low, high),
                                "target_temp_high": max(low, high),
                                "hvac_mode": "heat_cool",
                            },
                        )
                    else:
                        await self._call(
                            "set_temperature",
                            {"entity_id": eid, "temperature": ac_target, "hvac_mode": "heat_cool"},
                        )
                elif not thermostats and can_heat and can_cool and "heat" in ac_modes and "cool" in ac_modes:
                    # AC-only room, device supports heat+cool but not heat_cool:
                    # use device's built-in temperature to pick the right mode.
                    dev_temp = ac_state.attributes.get("current_temperature") if ac_state else None
                    if dev_temp is not None and ha_cool_target is not None and dev_temp > ha_cool_target:
                        await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "cool"})
                        await self._call(
                            "set_temperature",
                            {"entity_id": eid, "temperature": ha_cool_target, "hvac_mode": "cool"},
                            temp_intent="cool",
                        )
                    else:
                        await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "heat"})
                        await self._call(
                            "set_temperature",
                            {"entity_id": eid, "temperature": ac_heat_target, "hvac_mode": "heat"},
                            temp_intent="heat",
                        )
                elif can_cool and ha_cool_target is not None and "cool" in ac_modes:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "cool"})
                    await self._call(
                        "set_temperature",
                        {"entity_id": eid, "temperature": ha_cool_target, "hvac_mode": "cool"},
                        temp_intent="cool",
                    )
                elif can_heat and ha_heat_target is not None and "heat" in ac_modes:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "heat"})
                    await self._call(
                        "set_temperature",
                        {"entity_id": eid, "temperature": ha_heat_target, "hvac_mode": "heat"},
                        temp_intent="heat",
                    )
                elif "auto" in ac_modes:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "auto"})
                    await self._call(
                        "set_temperature",
                        {"entity_id": eid, "temperature": ac_heat_target, "hvac_mode": "auto"},
                        temp_intent="heat",
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
                    # Compressor min-run: the plan parked a device that must keep
                    # running. Same rule as the idle hold: the device keeps its last
                    # setpoint unless the target changed on purpose (#436). A device
                    # that reports off (state lag or switched off by hand) is not
                    # switched on again.
                    _LOGGER.debug(
                        "Area '%s': keeping '%s' active (compressor min-run protection)",
                        self._area_id,
                        cmd.entity_id,
                    )
                    await self._async_hold_retarget(cmd.entity_id, targets, current_temp)
                    continue
                if cmd.entity_id in _forced_off and cmd.active:
                    await async_idle_device(
                        self.hass,
                        cmd.entity_id,
                        self._devices,
                        area_id=self._area_id,
                        targets=targets,
                        use_setpoint_offset=self.has_external_sensor,
                        head_offset=self._head_offset(cmd.entity_id, "idle"),
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
                        ha_t = self._heating_setpoint_ha(cmd.entity_id, t, effective_target, direct_target)
                        await self._call("set_hvac_mode", {"entity_id": cmd.entity_id, "hvac_mode": "heat"})
                        await self._call(
                            "set_temperature",
                            {"entity_id": cmd.entity_id, "temperature": ha_t, "hvac_mode": "heat"},
                            temp_intent="heat",
                            deadband=self._proportional_deadband(cmd.entity_id, current_temp, effective_target),
                        )
                    else:  # ac
                        if self.has_external_sensor and current_temp is not None:
                            t = round(
                                current_temp + cmd.power_fraction * (ac_heat_boost - current_temp),
                                1,
                            )
                            t = max(effective_target, t)
                            t = min(ac_heat_boost, effective_target + self._ac_boost_delta, t)
                        else:
                            t = effective_target
                        shift = self._head_offset(cmd.entity_id, "heat")
                        ha_t = self._heating_setpoint_ha(
                            cmd.entity_id, t + shift, effective_target + shift, direct_target
                        )
                        ac_state = self.hass.states.get(cmd.entity_id)
                        ac_modes = _effective_ac_modes(ac_state)
                        if "heat" in ac_modes:
                            ac_mode = "heat"
                        elif "heat_cool" in ac_modes:
                            ac_mode = "heat_cool"
                        elif "auto" in ac_modes:
                            ac_mode = "auto"
                        else:
                            ac_mode = ""
                        if ac_mode:
                            await self._call("set_hvac_mode", {"entity_id": cmd.entity_id, "hvac_mode": ac_mode})
                            await self._call(
                                "set_temperature",
                                {"entity_id": cmd.entity_id, "temperature": ha_t, "hvac_mode": ac_mode},
                                temp_intent="heat",
                                deadband=self._proportional_deadband(cmd.entity_id, current_temp, effective_target),
                            )
                        else:
                            await self._call("set_hvac_mode", {"entity_id": cmd.entity_id, "hvac_mode": "off"})
                else:
                    # Inactive device
                    if cmd.device_type == "thermostat":
                        # Idle inactive TRVs via the configured idle_action
                        # (default "off").  Previously the TRV was kept in
                        # heat+setpoint=current_temp, but step snapping
                        # (e.g. 19.3 -> 19.5) could nudge the valve open on
                        # sensor fluctuation, causing a mechanical twitch
                        # and unnecessary heat demand. (#168)
                        await async_idle_device(
                            self.hass,
                            cmd.entity_id,
                            self._devices,
                            area_id=self._area_id,
                            targets=targets,
                            use_setpoint_offset=self.has_external_sensor,
                            head_offset=self._head_offset(cmd.entity_id, "idle"),
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
            for eid in thermostats:
                if eid in _forced_off:
                    await async_idle_device(
                        self.hass,
                        eid,
                        self._devices,
                        area_id=self._area_id,
                        targets=targets,
                        use_setpoint_offset=self.has_external_sensor,
                        head_offset=self._head_offset(eid, "idle"),
                    )
                    continue
                ha_t = self._heating_setpoint_ha(eid, trv_target, effective_target, direct_target)
                await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "heat"})
                await self._call(
                    "set_temperature",
                    {"entity_id": eid, "temperature": ha_t, "hvac_mode": "heat"},
                    temp_intent="heat",
                    deadband=self._proportional_deadband(eid, current_temp, effective_target),
                )
            # ACs: proportional setpoint in Full Control, actual target otherwise
            if self.has_external_sensor and current_temp is not None:
                ac_heat_target = round(
                    current_temp + power_fraction * (ac_heat_boost - current_temp),
                    1,
                )
                ac_heat_target = max(effective_target, ac_heat_target)
                ac_heat_target = min(ac_heat_boost, effective_target + self._ac_boost_delta, ac_heat_target)
            else:
                ac_heat_target = effective_target
            for eid in acs:
                if eid in _forced_off:
                    await async_idle_device(
                        self.hass,
                        eid,
                        self._devices,
                        area_id=self._area_id,
                        targets=targets,
                        use_setpoint_offset=self.has_external_sensor,
                        head_offset=self._head_offset(eid, "idle"),
                    )
                    continue
                shift = self._head_offset(eid, "heat")
                ha_t = self._heating_setpoint_ha(eid, ac_heat_target + shift, effective_target + shift, direct_target)
                ac_state = self.hass.states.get(eid)
                ac_modes = _effective_ac_modes(ac_state)
                if "heat" in ac_modes:
                    ac_mode = "heat"
                elif "heat_cool" in ac_modes:
                    ac_mode = "heat_cool"
                elif "auto" in ac_modes:
                    ac_mode = "auto"
                else:
                    ac_mode = ""
                if ac_mode:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": ac_mode})
                    await self._call(
                        "set_temperature",
                        {"entity_id": eid, "temperature": ha_t, "hvac_mode": ac_mode},
                        temp_intent="heat",
                        deadband=self._proportional_deadband(eid, current_temp, effective_target),
                    )
                else:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "off"})
        elif mode == MODE_COOLING:
            if self.has_external_sensor and current_temp is not None:
                ac_cool_target = round(
                    current_temp - power_fraction * (current_temp - ac_cool_boost),
                    1,
                )
                ac_cool_target = max(ac_cool_boost, effective_target - self._ac_boost_delta, ac_cool_target)
                ac_cool_target = min(effective_target, ac_cool_target)
            else:
                ac_cool_target = effective_target
            for eid in acs:
                if eid in _forced_off:
                    await async_idle_device(
                        self.hass,
                        eid,
                        self._devices,
                        area_id=self._area_id,
                        targets=targets,
                        use_setpoint_offset=self.has_external_sensor,
                        head_offset=self._head_offset(eid, "idle"),
                    )
                    continue
                direct_t = self._direct_setpoint_ha(eid, direct_target)
                ha_t = direct_t if direct_t is not None else self._cooling_setpoint_ha(eid, ac_cool_target)
                await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "cool"})
                await self._call(
                    "set_temperature",
                    {"entity_id": eid, "temperature": ha_t, "hvac_mode": "cool"},
                    temp_intent="cool",
                    deadband=self._proportional_deadband(eid, current_temp, effective_target),
                )
            for eid in thermostats:
                if eid in _forced_off:
                    await async_idle_device(
                        self.hass,
                        eid,
                        self._devices,
                        area_id=self._area_id,
                        targets=targets,
                        use_setpoint_offset=self.has_external_sensor,
                        head_offset=self._head_offset(eid, "idle"),
                    )
                    continue
                await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "off"})
        elif mode == MODE_IDLE:
            for eid in thermostats + acs:
                if eid in _forced_on:
                    # Compressor min-run: keep the device running. Its last active
                    # setpoint does that; falling back to the room target at once
                    # would stop units whose own sensor reads the room as already
                    # warm/cold enough (#436). Only a target that changed on purpose
                    # (eco override, vacation, schedule off) is passed on.
                    _LOGGER.debug(
                        "Area '%s': keeping '%s' active (compressor min-run protection)",
                        self._area_id,
                        eid,
                    )
                    await self._async_hold_retarget(eid, targets, current_temp)
                    continue
                if not force_off and await self._async_hold_at_target(eid, targets, current_temp):
                    continue
                await async_idle_device(
                    self.hass,
                    eid,
                    self._devices,
                    area_id=self._area_id,
                    targets=targets,
                    use_setpoint_offset=self.has_external_sensor,
                    head_offset=self._head_offset(eid, "idle"),
                    force_off=force_off,
                    release_setback=self._setback_release,
                )

    async def _call_and_record(
        self, eid: str, record: tuple[float | None, float | None], *args: Any, **kwargs: Any
    ) -> str:
        """``_call`` for the hold: a delivered change, or one the device already shows, is used up."""
        result = await self._call(*args, **kwargs)
        if result == _CALL_CONFIRMED:
            _active_targets[eid] = record
        return result

    def _hold_setpoint_ha(self, eid: str, target: float, intent: str) -> float:
        """HA-unit setpoint for a held device: direct target (+offset) or the room target in the device's frame."""
        direct = self._direct_setpoint_ha(eid, target)
        return direct if direct is not None else celsius_to_ha_temp(self.hass, target + self._head_offset(eid, intent))

    async def _async_hold_at_target(self, eid: str, targets: TargetTemps, current_temp: float | None) -> bool:
        """Idle action "hold": keep an AC in its mode at the room target in its own frame.

        A modulating unit given the target (plus its learned running offset) throttles
        down to the output that balances the room instead of stopping, so a short idle
        between MPC runs costs no compressor start and no full-power restart. Only
        within ``HOLD_BAND_K`` of the target and while a run of this mode is still
        expected (the setback release, #255); otherwise the device falls through to
        setback/off. Returns True if the device was held.
        """
        if (
            eid not in self.acs
            or not self.has_external_sensor
            or current_temp is None
            or get_idle_action(self._devices, eid)[0] != IDLE_ACTION_HOLD
        ):
            return False
        state = self.hass.states.get(eid)
        hvac = state.state if state else None
        if hvac not in ("heat", "cool") or hvac in self._setback_release:
            return False
        target = targets.heat if hvac == "heat" else targets.cool
        if target is None:
            return False
        past = target - current_temp if hvac == "cool" else current_temp - target
        if past > HOLD_BAND_K:
            return False
        # The frame follows the unit: while it runs, its running offset holds the room at
        # the target; once it has stopped on its own, the idle offset makes it restart
        # only when the room is past the target again, not when its sensor reads the
        # stagnant layer under the ceiling.
        frame = "idle" if state.attributes.get("hvac_action") == "idle" else hvac
        await self._call(
            "set_temperature",
            {"entity_id": eid, "temperature": self._hold_setpoint_ha(eid, target, frame), "hvac_mode": hvac},
            temp_intent=hvac,
        )
        self.held_at_target.add(eid)
        return True

    async def _async_hold_retarget(self, eid: str, targets: TargetTemps, current_temp: float | None) -> None:
        """Pass a deliberately changed target on to a device held by the compressor min-run.

        The hold sends nothing while the resolved target is the one of the last
        active command: the room has only reached it and the unit keeps running on
        its last setpoint (#436). A target that moved since then (eco override,
        vacation, schedule off with eco, presence) would otherwise reach the unit
        only after the min-run, up to an hour of heating against a target several
        degrees too high.  Only the side the device regulates on counts, so
        editing the cooling target does not drop a heating unit.  Mold prevention
        raises the heating target in steps and with hysteresis, so it counts as
        any other change.  The device stays in its mode; one that is off, or has
        no state, is left alone.

        A room that has run past the far side of its band (heating unit, room at or
        above the cooling target) is handled as before the hold: the target goes
        out and the unit stops heating, so the boost cannot flip it to cooling.
        This applies to units in plain ``heat`` or ``cool`` only. "Past" means
        beyond the far target and at least ``HOLD_OVERSHOOT_MARGIN`` from the near
        one, so a single-point target (heat == cool) does not end the hold the
        moment the room reaches it.
        """
        state = self.hass.states.get(eid)
        hvac = state.state if state else None
        if state is None or hvac not in ("heat", "cool", "heat_cool", "auto"):
            return
        previous = _active_targets.get(eid)
        if previous is None:
            # Nothing remembered (reload in the middle of the hold): the current targets become the
            # reference, so that a later reduction is passed on
            _active_targets[eid] = (targets.heat, targets.cool)
        # Only a change that lowers the demand matters: a raised heating target while the unit
        # already heats at full tilt needs no command, and sending the bare target when the room
        # arrives would stop the unit at once (#436).
        heat_moved = (
            previous is not None and hvac != "cool" and _demand_lowered(previous[0], targets.heat, heating=True)
        )
        cool_moved = (
            previous is not None and hvac != "heat" and _demand_lowered(previous[1], targets.cool, heating=False)
        )
        # Past the far side of the band the boost would carry the room over it and
        # flip the unit to the other mode right after the min-run. Only a room that
        # can switch sides cares; heat-only rooms never cool. A heat_cool/auto unit
        # picks its side itself and is left to the rule below.
        heat_overshoot = False
        if hvac == "heat" and self.climate_mode != CLIMATE_MODE_HEAT_ONLY and targets.cool is not None:
            limit = targets.cool if targets.heat is None else max(targets.cool, targets.heat + HOLD_OVERSHOOT_MARGIN)
            heat_overshoot = current_temp is not None and current_temp >= limit
        cool_overshoot = False
        if hvac == "cool" and self.climate_mode != CLIMATE_MODE_COOL_ONLY and targets.heat is not None:
            limit = targets.heat if targets.cool is None else min(targets.heat, targets.cool - HOLD_OVERSHOOT_MARGIN)
            cool_overshoot = current_temp is not None and current_temp <= limit
        overshoot = (heat_overshoot or cool_overshoot) and eid not in _overshoot_sent
        if not (heat_moved or cool_moved or overshoot):
            await self._async_hold_modulate(eid, state, targets, current_temp)
            return
        # Recorded only once something was passed on, so a change that could not be
        # sent yet (single setpoint inside the band) is still pending next cycle.
        new_record = (targets.heat, targets.cool)

        if hvac in ("heat", "cool"):
            target = targets.heat if hvac == "heat" else targets.cool
            if target is not None:
                result = await self._call_and_record(
                    eid,
                    new_record,
                    "set_temperature",
                    {"entity_id": eid, "temperature": self._hold_setpoint_ha(eid, target, hvac)},
                    temp_intent=hvac,
                )
                if result != _CALL_FAILED:
                    # The plain target is below any throttle level: no throttle on top of it this hold
                    _hold_modulated.add(eid)
                    if overshoot:
                        _overshoot_sent.add(eid)
            return

        # heat_cool/auto regulate from both sides onto what they get, so a single
        # side's value would make the device chase it the wrong way (heating target
        # 17 °C under an eco override cools a 21 °C room, #284).
        heat_ha = celsius_to_ha_temp(self.hass, targets.heat) if targets.heat is not None else None
        cool_ha = celsius_to_ha_temp(self.hass, targets.cool) if targets.cool is not None else None
        if state.attributes.get("target_temp_low") is not None:
            try:
                low = heat_ha if heat_ha is not None else float(state.attributes["min_temp"])
                high = cool_ha if cool_ha is not None else float(state.attributes["max_temp"])
            except (KeyError, TypeError, ValueError):
                return
            await self._call_and_record(
                eid,
                new_record,
                "set_temperature",
                {"entity_id": eid, "target_temp_low": min(low, high), "target_temp_high": max(low, high)},
            )
        elif current_temp is not None:
            # Single setpoint: only a side the room is already past is safe to send.
            if targets.heat is not None and current_temp <= targets.heat:
                await self._call_and_record(
                    eid,
                    new_record,
                    "set_temperature",
                    {"entity_id": eid, "temperature": self._hold_setpoint_ha(eid, targets.heat, "heat")},
                    temp_intent="heat",
                )
            elif targets.cool is not None and current_temp >= targets.cool:
                await self._call_and_record(
                    eid,
                    new_record,
                    "set_temperature",
                    {"entity_id": eid, "temperature": self._hold_setpoint_ha(eid, targets.cool, "cool")},
                    temp_intent="cool",
                )

    async def _async_hold_modulate(
        self, eid: str, state: Any, targets: TargetTemps, current_temp: float | None
    ) -> None:
        """Throttle a held unit to minimum once the room is ``HOLD_OVERSHOOT_MARGIN`` past its target.

        The hold keeps the last active setpoint so the unit does not stop (#436). In a
        room without a far side (heat_only / cool_only, or no target on the other side)
        the band rule never ends the boost before the min-run is over, and a strong
        unit carries the room several degrees past the target. Rooms with both sides
        keep the band rule. The unit gets the value its own sensor
        reads, rounded up (heating) or down (cooling) to its step: an inverter there
        modulates to minimum and keeps running, where the plain room target would stop
        a unit whose sensor reads warm. Never past the room target (+ direct offset),
        only ever lowering (raising for cooling) the held value, and once per hold, so
        the setpoint does not follow the room up and down (#416).
        """
        hvac = state.state
        if current_temp is None or eid in _hold_modulated or hvac not in ("heat", "cool"):
            return
        heating = hvac == "heat"
        target = targets.heat if heating else targets.cool
        far_side = targets.cool if heating else targets.heat
        one_sided = self.climate_mode == (CLIMATE_MODE_HEAT_ONLY if heating else CLIMATE_MODE_COOL_ONLY)
        if target is None or (far_side is not None and not one_sided):
            return
        past = (
            current_temp >= target + HOLD_OVERSHOOT_MARGIN
            if heating
            else current_temp <= target - HOLD_OVERSHOOT_MARGIN
        )
        if not past:
            return
        attrs = state.attributes
        held = attrs.get("temperature")
        if held is None:
            cached = _cached_command(eid, "set_temperature")
            held = cached.get("temperature") if cached else None
        reading = attrs.get("current_temperature")
        try:
            held_f = float(held) if held is not None else None
            reading_f = float(reading) if reading is not None else celsius_to_ha_temp(self.hass, current_temp)
        except (TypeError, ValueError):
            return
        if held_f is None:
            return
        step = _resolve_step(self.hass, attrs) or celsius_delta_to_ha(self.hass, BOOST_CAP_FALLBACK_STEP)
        bound = self._hold_setpoint_ha(eid, target, hvac)
        tolerance = celsius_delta_to_ha(self.hass, COMPRESSOR_HOLD_RETARGET_TOLERANCE)
        if heating:
            level = max(bound, math.ceil(reading_f / step - 1e-6) * step)
            if level >= held_f - tolerance:
                return
        else:
            level = min(bound, math.floor(reading_f / step + 1e-6) * step)
            if level <= held_f + tolerance:
                return
        _LOGGER.debug(
            "Area '%s': throttling held '%s' from %s to %s (room %.1f, target %.1f)",
            self._area_id,
            eid,
            held_f,
            level,
            current_temp,
            target,
        )
        result = await self._call(
            "set_temperature", {"entity_id": eid, "temperature": round(level, 2)}, temp_intent=hvac
        )
        if result != _CALL_FAILED:
            _hold_modulated.add(eid)

    def direct_target(self, mode: str, target: float) -> float:
        """Room target (°C, without offset) a direct-mode device gets while *mode* is active.

        A direct device regulates on the value it gets, so while MPC heats ahead of a
        stricter upcoming target it needs that target, not the current one; otherwise
        pre-heating only starts when the block begins. Pre-cooling mirrored. Outside
        MPC (bang-bang, managed mode) there is no lead and the target is returned as is.
        """
        if mode == MODE_HEATING and self._lead_heat is not None:
            return max(target, self._lead_heat)
        if mode == MODE_COOLING and self._lead_cool is not None:
            return min(target, self._lead_cool)
        return target

    def _direct_setpoint_ha(self, eid: str, effective_target: float) -> float | None:
        """HA-unit setpoint for a direct-mode device: room target plus its offset, None if not direct.

        The offset only makes sense against an external reference sensor, so
        managed mode (the device's own reading drives control) ignores it.
        """
        if eid not in self._direct_eids:
            return None
        offset = self._direct_offsets.get(eid, 0.0) if self.has_external_sensor else 0.0
        return celsius_to_ha_temp(self.hass, effective_target + offset)

    def _head_offset(self, eid: str, intent: str) -> float:
        """Learned offset (K) of an AC's own sensor from the room sensor in state *intent*.

        *intent* is "heat" or "cool" (compressor running that way) or "idle" (stopped).
        A proportional, held or setback setpoint is meant in the room's frame, but the
        unit compares it with its own reading. Adding the offset makes the unit stop and
        restart where the room, not its sensor, is at the setpoint. Only for ACs in
        proportional mode with an external room sensor: a direct device carries the
        user's own offset, and without a room sensor there is nothing to compare with.
        """
        if (
            self._head_offsets is None
            or not self.has_external_sensor
            or eid not in self.acs
            or eid in self._direct_eids
        ):
            return 0.0
        return self._head_offsets.offset(eid, intent)

    def _cooling_setpoint_ha(self, eid: str, celsius: float) -> float:
        """HA-unit proportional AC cooling setpoint in the device's frame, within its range."""
        ha_t = celsius_to_ha_temp(self.hass, celsius + self._head_offset(eid, "cool"))
        state = self.hass.states.get(eid)
        if state is None:
            return ha_t
        try:
            low = float(state.attributes["min_temp"])
            high = float(state.attributes["max_temp"])
        except (KeyError, TypeError, ValueError):
            return ha_t
        return min(max(ha_t, low), high)

    def _heating_setpoint_ha(
        self, eid: str, proportional_celsius: float, effective_target: float, direct_target: float | None = None
    ) -> float:
        """HA-unit heating setpoint: direct target (+offset) or the capped proportional boost."""
        direct = self._direct_setpoint_ha(eid, effective_target if direct_target is None else direct_target)
        if direct is not None:
            return direct
        return self._boost_setpoint_ha(eid, proportional_celsius, effective_target)

    def _boost_setpoint_ha(self, eid: str, celsius: float, effective_target: float) -> float:
        """HA-unit proportional heating setpoint, kept one step below the device's max_temp.

        Some integrations validate the upper bound exclusively or after a
        unit round trip, so exactly max_temp can be rejected (#396). The cap
        only trims the top step of the boost and never goes below the room
        target. Without ``target_temp_step`` a device that shows whole degrees
        gets a whole-degree ceiling, so what it reads back equals what was
        sent; devices showing tenths keep the 0.5 K margin.
        """
        ha_t = celsius_to_ha_temp(self.hass, celsius)
        state = self.hass.states.get(eid)
        raw_max = state.attributes.get("max_temp") if state else None
        if raw_max is None:
            return ha_t
        try:
            max_t = float(raw_max)
            step = float(state.attributes.get("target_temp_step") or 0.0)
        except (TypeError, ValueError):
            return ha_t
        whole_ceiling = False
        if step <= 0:
            # In HA units so that a whole-degree snap on °F devices (no step reported) still lands below max_temp
            step = celsius_delta_to_ha(self.hass, BOOST_CAP_FALLBACK_STEP)
            try:
                whole_ceiling = float(state.attributes.get("temperature")).is_integer()
            except (TypeError, ValueError):
                pass
        cap = max_t - step
        if whole_ceiling:
            # The device shows whole degrees: 29.5 would read back as 30 and be resent every cycle
            cap = math.floor(cap)
        ceiling = max(cap, celsius_to_ha_temp(self.hass, effective_target))
        return min(ha_t, ceiling)

    def _proportional_deadband(self, eid: str, current_temp: float | None, effective_target: float) -> float | None:
        """Deadband for a proportional setpoint send; None marks a send that is not proportional.

        Direct-mode devices and managed mode get None. A proportional send gets
        0.0 (exact comparison) in the comfort regime (approach_rate >= 1.0) and a
        threshold in the gentle regime, finer near target so the final approach
        stays regulated. ``_call`` also applies the setpoint dwell to every
        proportional send.
        """
        if eid in self._direct_eids or not self.has_external_sensor or current_temp is None:
            return None
        if self._approach_rate >= 1.0:
            return 0.0
        if abs(current_temp - effective_target) <= 1.0:
            return PROPORTIONAL_DEADBAND_NEAR_TARGET_C
        return PROPORTIONAL_DEADBAND_C

    def _current_target_pair(self) -> tuple[float | None, float | None]:
        targets = self._idle_targets
        return (targets.heat, targets.cool) if targets is not None else (None, None)

    def _proportional_dwell_active(
        self, eid: str, service: str, data: dict, state: Any, deadband: float | None
    ) -> bool:
        """True when a recomputed proportional setpoint has to wait for the dwell to end.

        The proportional power follows a 5-min deadbeat law, so one 0.1 K sensor
        step moves the setpoint by 2 K or more. Resent every 30 s cycle that
        exhausts radio duty cycles (#317) while a radiator cannot follow anyway.
        The dwell keeps the last value for one MPC block. Never delayed: the
        first setpoint after any other command that was actually sent (mode
        change, idle), a changed room target, a device that is not running in
        the commanded mode, and devices without usable state, whose
        sent-command cache (#416) stays as it is. A compressor hold that sends
        nothing keeps the record; it only matters if the hold ends within the
        dwell, since a hold lasts the group's minimum run. Dual-setpoint devices
        get the proportional value on ``target_temp_low``/``high`` and dwell the same way.
        """
        if service != "set_temperature" or deadband is None or not _carries_setpoint(data):
            return False
        if state is None or _should_use_cache(state):
            return False
        record = _proportional_sent.get(eid)
        if record is None or _now() - record[0] >= PROPORTIONAL_SETPOINT_DWELL_SECONDS:
            return False
        sent_heat, sent_cool = record[1]
        heat, cool = self._current_target_pair()
        if _target_moved(sent_heat, heat) or _target_moved(sent_cool, cool):
            return False
        desired_mode = data.get("hvac_mode")
        if desired_mode is not None:
            return bool(state.state == desired_mode)
        return bool(state.state != "off")

    async def _call(self, service: str, data: dict, *, temp_intent: str = "", deadband: float | None = None) -> str:
        """Send a climate service call unless the device already holds the value.

        Returns ``_CALL_SENT``, ``_CALL_CONFIRMED``, ``_CALL_SKIPPED`` or ``_CALL_FAILED``.
        A sent command also remembers the targets it was computed for, which is what
        the compressor hold compares against (``_active_targets``).
        """
        eid = data.get("entity_id")
        state = self.hass.states.get(eid) if eid else None

        # Delegate "turn off" to fallback-aware helper (handles heat-only TRVs)
        if service == "set_hvac_mode" and data.get("hvac_mode") == "off" and eid:
            await async_idle_device(
                self.hass,
                eid,
                self._devices,
                area_id=self._area_id,
                targets=self._idle_targets,
                use_setpoint_offset=self.has_external_sensor,
                head_offset=self._head_offset(eid, "idle"),
                force_off=self._force_off,
            )
            return _CALL_SKIPPED

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
                    return _CALL_SKIPPED
            if resolved != data["hvac_mode"]:
                _LOGGER.debug(
                    "Area '%s': device '%s' resolved '%s' -> '%s'",
                    self._area_id,
                    eid,
                    data["hvac_mode"],
                    resolved,
                )
                data = {**data, "hvac_mode": resolved}

        # Resolve hvac_mode bundled with set_temperature (#337).  Sending the
        # mode atomically with the temperature prevents integrations that
        # build device commands from a stale power cache (e.g. midea_ac_lan)
        # from turning the device back off right after set_hvac_mode.  When
        # the device reports modes that exclude the desired one with no
        # fallback (e.g. ["off", "fan_only"], #100/#135) the key is dropped
        # and the previous two-call behavior is kept.  An empty hvac_modes
        # list keeps the raw mode, mirroring the set_hvac_mode direct-send
        # path for devices with unreliable mode reporting.
        if service == "set_temperature" and "hvac_mode" in data and state:
            hvac_modes = state.attributes.get("hvac_modes") or []
            resolved = resolve_hvac_mode(data["hvac_mode"], hvac_modes)
            if resolved is None:
                data = {k: v for k, v in data.items() if k != "hvac_mode"}
            elif resolved != data["hvac_mode"]:
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
            step = _resolve_step(self.hass, state.attributes)
            if step is not None:
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

        # Unusable state and no step to snap to: the sent-command cache only recognises
        # identical values, so a proportional setpoint that drifts with the room
        # temperature would go out every cycle or two. Quantize it to the unit the
        # device can show anyway (#416). Direct targets and Managed Mode, which send the
        # plain room target, keep their exact value.
        if (
            service == "set_temperature"
            and "temperature" in data
            and eid not in self._direct_eids
            and self.has_external_sensor
            and state
            and _should_use_cache(state)
            and _resolve_step(self.hass, state.attributes) is None
        ):
            unit_step = 1.0 if self.hass.config.units.temperature_unit == UnitOfTemperature.FAHRENHEIT else 0.5
            t = _snap_to_step(data["temperature"], unit_step)
            dev_min = state.attributes.get("min_temp")
            dev_max = state.attributes.get("max_temp")
            if dev_max is not None and t > dev_max:
                t = dev_max
            if dev_min is not None and t < dev_min:
                t = dev_min
            data = {**data, "temperature": t}

        # --- Redundancy: primary (device state) then fallback (sent cache) ---
        skip = False
        cache_checked = False
        # True when the skip proves the device already holds exactly this value
        # (not merely within the proportional deadband)
        confirmed = False
        if state:
            if service == "set_hvac_mode" and state.state == data.get("hvac_mode"):
                skip = confirmed = True
            elif service == "set_temperature":
                # Dual-setpoint (range) devices: proportional deadband is intentionally
                # NOT applied here — it only governs single-setpoint gentle-regime sends.
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
                        skip = confirmed = True
                else:
                    current = state.attributes.get("temperature")
                    desired = data.get("temperature")
                    if current is not None and desired is not None:
                        if deadband is not None and deadband > 0.0:
                            ha_deadband = celsius_delta_to_ha(self.hass, deadband)
                            if abs(float(current) - float(desired)) < ha_deadband:
                                skip = True
                        elif round(current, 1) == round(desired, 1):
                            skip = confirmed = True

        # Fallback: check sent-command cache (for IR devices without state feedback).
        # Proportional deadband is intentionally NOT applied here — it is anchored to
        # live device state, while this branch handles IR/no-state devices via the cache.
        if not skip and eid and _should_use_cache(state):
            cache_checked = True
            cached = _cached_command(eid, service)
            if cached is not None and not _cache_expired(eid, service):
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

        if not skip and eid and self._proportional_dwell_active(eid, service, data, state, deadband):
            _LOGGER.debug(
                "Area '%s': keeping proportional setpoint on '%s' (changed less than %ds ago)",
                self._area_id,
                eid,
                PROPORTIONAL_SETPOINT_DWELL_SECONDS,
            )
            return _CALL_SKIPPED

        if skip:
            if confirmed and eid:
                _note_applied(eid, service, data)
            if service == "set_temperature" and eid and self._idle_targets is not None:
                # After a reload nothing has been sent yet although the unit already runs: start the
                # hold reference here, but never replace a remembered one (that is what a send does)
                _active_targets.setdefault(eid, (self._idle_targets.heat, self._idle_targets.cool))
            return _CALL_CONFIRMED if confirmed or cache_checked else _CALL_SKIPPED

        try:
            await self.hass.services.async_call(
                "climate",
                service,
                data,
                blocking=True,
                context=make_roommind_context(),
            )
            if eid:
                _remember_command(eid, service, data)
                if self._idle_targets is not None:
                    _active_targets[eid] = (self._idle_targets.heat, self._idle_targets.cool)
                if deadband is not None and service == "set_temperature" and _carries_setpoint(data):
                    _proportional_sent[eid] = (_now(), self._current_target_pair())
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "Area '%s': climate.%s failed on '%s'",
                self._area_id,
                service,
                data.get("entity_id"),
                exc_info=True,
            )
            return _CALL_FAILED
        return _CALL_SENT
