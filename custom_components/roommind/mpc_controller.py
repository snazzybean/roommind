"""MPC-based climate controller for RoomMind."""

from __future__ import annotations

import logging
import math
import time
from typing import Callable

from homeassistant.core import HomeAssistant

from .const import (
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
)
from .mpc_optimizer import MPCOptimizer, MPCPlan
from .temp_utils import celsius_to_ha_temp
from .thermal_model import RoomModelManager

_LOGGER = logging.getLogger(__name__)

_SENTINEL = object()  # default marker for backward-compat keyword detection


async def async_turn_off_climate(
    hass: HomeAssistant,
    entity_id: str,
    *,
    area_id: str = "unknown",
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
        if state and state.state == "off":
            return  # already off
        try:
            await hass.services.async_call(
                "climate",
                "set_hvac_mode",
                {"entity_id": entity_id, "hvac_mode": "off"},
                blocking=True,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "Area '%s': climate.set_hvac_mode(off) failed on '%s'",
                area_id,
                entity_id,
                exc_info=True,
            )
        return

    # Fallback: device does not support "off" → set to min_temp / max_temp
    is_cooling = "cool" in hvac_modes or "heat_cool" in hvac_modes
    fallback_temp = (
        state.attributes.get("max_temp") if is_cooling else state.attributes.get("min_temp")
    )

    if fallback_temp is None:
        _LOGGER.warning(
            "Area '%s': device '%s' has no 'off' mode and no %s attribute, "
            "cannot turn off reliably",
            area_id,
            entity_id,
            "max_temp" if is_cooling else "min_temp",
        )
        return

    # Redundancy: skip if already at fallback temp
    current_temp_setting = state.attributes.get("temperature")
    if (
        current_temp_setting is not None
        and round(current_temp_setting, 1) == round(fallback_temp, 1)
    ):
        return

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
            {"entity_id": entity_id, "temperature": fallback_temp},
            blocking=True,
        )
    except Exception:  # noqa: BLE001
        _LOGGER.warning(
            "Area '%s': climate.set_temperature(%s) fallback failed on '%s'",
            area_id,
            fallback_temp,
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


# Maximum prediction uncertainty (degC) for MPC to be used.
# Physical meaning: "use MPC when the 5-min prediction is accurate to ±0.5°C."
MPC_MAX_PREDICTION_STD = 0.5

# Planning parameters
PLAN_DT_MINUTES = 5
MIN_HORIZON_HOURS = 2
HORIZON_MULTIPLIER = 2.5
DEFAULT_OUTDOOR_TEMP_FALLBACK = 10.0

# Minimum sample counts before MPC is allowed.
# Each EKF update covers ~3 min (EKF_UPDATE_MIN_DT), so these correspond
# to real-time requirements of ~3 h idle + ~1 h active-mode data.
MIN_IDLE_UPDATES = 60    # ~3 h of idle data at 3-min EKF intervals
MIN_ACTIVE_UPDATES = 20  # ~1 h of heating or cooling data


def check_acs_can_heat(hass: HomeAssistant, room_config: dict) -> bool:
    """Check if any AC entity in the room supports heating."""
    for eid in room_config.get("acs", []):
        state = hass.states.get(eid)
        if state is None:
            continue
        modes = state.attributes.get("hvac_modes", [])
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
        bool(room_config.get("thermostats")) or acs_can_heat
    )
    can_cool = climate_mode != CLIMATE_MODE_HEAT_ONLY and bool(room_config.get("acs"))

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
    pred_std = model_manager.get_prediction_std(
        area_id, Q_check, current_temp, outdoor_temp, PLAN_DT_MINUTES
    )
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
        target_resolver: "Callable[[float], float] | None" = None,
        q_solar: float = 0.0,
        latitude: float = 0.0,
        longitude: float = 0.0,
        cloud_series: list[float | None] | None = None,
        q_residual: float = 0.0,
        heating_system_type: str = "",
    ) -> None:
        self.hass = hass
        self.room_config = room_config
        self.thermostats: list[str] = room_config.get("thermostats", [])
        self.acs: list[str] = room_config.get("acs", [])
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
        target_temp: float | None = _SENTINEL,
    ) -> tuple[str, float]:
        """Evaluate what action to take. Returns (mode, power_fraction).

        Accepts TargetTemps for dual heat/cool targets or a single float
        for backward compatibility. ``target_temp`` keyword kept for callers
        that haven't migrated yet.
        """
        # Backward compat: accept legacy keyword
        if target_temp is not _SENTINEL:
            targets = target_temp

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
            self._area_id, Q_check, current_temp or 20.0, T_out, PLAN_DT_MINUTES,
            q_solar=self.q_solar,
            q_residual=self.q_residual,
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

        # Build dual target series with schedule lookahead for pre-heating/pre-cooling.
        # None values (from "off" action) are replaced with current_temp so the
        # optimizer sees "no deviation needed = idle optimal".
        if self._target_resolver is not None:
            now = time.time()
            dt_seconds = PLAN_DT_MINUTES * 60
            raw_targets = [
                self._target_resolver(now + i * dt_seconds)
                for i in range(horizon_blocks)
            ]
            # Extract separate heat and cool series from TargetTemps
            if raw_targets and isinstance(raw_targets[0], TargetTemps):
                heat_target_series = [
                    t.heat if t.heat is not None else current_temp for t in raw_targets
                ]
                cool_target_series = [
                    t.cool if t.cool is not None else current_temp for t in raw_targets
                ]
            else:
                # Legacy resolver returning float|None
                heat_target_series = [t if t is not None else current_temp for t in raw_targets]
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
        )
        self.last_plan = plan

        action = plan.get_current_action()
        power_fraction = plan.get_current_power_fraction()

        # Safety guard: don't heat above the maximum upcoming target,
        # don't cool below the minimum upcoming target.
        near_heat = heat_target_series[:6]
        near_cool = cool_target_series[:6]
        if near_heat and action == MODE_HEATING and current_temp >= max(near_heat):
            action = MODE_IDLE
            power_fraction = 0.0
        elif near_cool and action == MODE_COOLING and current_temp <= min(near_cool):
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
            if current_temp < heat_target:
                return MODE_HEATING
            return MODE_IDLE

        if self.previous_mode == MODE_COOLING and can_cool and cool_target is not None:
            if current_temp > cool_target:
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

    def _compute_horizon_blocks(self, model, current_temp, target_temp) -> int:
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
            series = [f.get("temperature", self.outdoor_temp or DEFAULT_OUTDOOR_TEMP_FALLBACK) for f in self.outdoor_forecast]
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

        return build_solar_series(
            self._latitude, self._longitude, n_blocks,
            dt_minutes=PLAN_DT_MINUTES,
            cloud_series=cloud_per_block,
        )

    def _build_residual_series(self, n_blocks: int) -> list[float] | None:
        """Build decaying residual heat series for MPC horizon."""
        if self.q_residual <= 0 or not self._heating_system_type:
            return None
        from .const import HEATING_SYSTEM_PROFILES, RESIDUAL_HEAT_CUTOFF
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
        target_temp: float | None = _SENTINEL,
    ) -> None:
        """Apply the determined mode with proportional valve control."""
        # Backward compat: accept legacy keyword
        if target_temp is not _SENTINEL:
            targets = target_temp

        # Backward compat: single float → TargetTemps
        if not isinstance(targets, TargetTemps):
            t = targets
            targets = TargetTemps(heat=t, cool=t) if t is not None else TargetTemps(heat=None, cool=None)

        # Resolve effective target_temp for the current mode
        if mode == MODE_HEATING:
            target_temp = targets.heat
        elif mode == MODE_COOLING:
            target_temp = targets.cool
        else:
            target_temp = targets.heat if targets.heat is not None else targets.cool

        if mode != MODE_IDLE and target_temp is None:
            mode = MODE_IDLE

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
                if can_heat and ha_heat_target is not None:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "heat"})
                    await self._call("set_temperature", {"entity_id": eid, "temperature": ha_heat_target})
                else:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "off"})
            for eid in self.acs:
                ac_state = self.hass.states.get(eid)
                ac_modes = (ac_state.attributes.get("hvac_modes") or []) if ac_state else []
                ac_target = ha_cool_target if ha_cool_target is not None else ha_heat_target
                if ac_target is None:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "off"})
                elif "heat_cool" in ac_modes:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "heat_cool"})
                    await self._call("set_temperature", {"entity_id": eid, "temperature": ac_target})
                elif can_cool and "cool" in ac_modes:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "cool"})
                    await self._call("set_temperature", {"entity_id": eid, "temperature": ac_target})
                elif can_heat and "heat" in ac_modes:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "heat"})
                    await self._call("set_temperature", {"entity_id": eid, "temperature": ac_target})
                elif "auto" in ac_modes:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "auto"})
                    await self._call("set_temperature", {"entity_id": eid, "temperature": ac_target})
                else:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "off"})
            return

        if mode == MODE_HEATING:
            # Proportional TRV setpoint for Full Control mode
            if self.has_external_sensor and current_temp is not None:
                trv_target = round(
                    current_temp + power_fraction * (HEATING_BOOST_TARGET - current_temp),
                    1,
                )
                # Floor: never below target (TRV must always aim to heat toward target)
                trv_target = max(target_temp, trv_target)
                # Ceiling: never above boost target
                trv_target = min(HEATING_BOOST_TARGET, trv_target)
            else:
                trv_target = HEATING_BOOST_TARGET if self.has_external_sensor else target_temp
            ha_trv = celsius_to_ha_temp(self.hass, trv_target)
            for eid in thermostats:
                await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "heat"})
                await self._call("set_temperature", {"entity_id": eid, "temperature": ha_trv})
            # ACs: heat-capable ones get actual target temp, others turn off
            ha_target = celsius_to_ha_temp(self.hass, target_temp)
            for eid in self.acs:
                ac_state = self.hass.states.get(eid)
                ac_modes = (ac_state.attributes.get("hvac_modes") or []) if ac_state else []
                if "heat" in ac_modes:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "heat"})
                    await self._call("set_temperature", {"entity_id": eid, "temperature": ha_target})
                elif "heat_cool" in ac_modes:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "heat_cool"})
                    await self._call("set_temperature", {"entity_id": eid, "temperature": ha_target})
                elif "auto" in ac_modes:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "auto"})
                    await self._call("set_temperature", {"entity_id": eid, "temperature": ha_target})
                else:
                    await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "off"})
        elif mode == MODE_COOLING:
            ha_target = celsius_to_ha_temp(self.hass, target_temp)
            for eid in self.acs:
                await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "cool"})
                await self._call("set_temperature", {"entity_id": eid, "temperature": ha_target})
            for eid in thermostats:
                await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "off"})
        elif mode == MODE_IDLE:
            for eid in thermostats + self.acs:
                await self._call("set_hvac_mode", {"entity_id": eid, "hvac_mode": "off"})

    async def _call(self, service: str, data: dict) -> None:
        eid = data.get("entity_id")
        state = self.hass.states.get(eid) if eid else None

        # Delegate "turn off" to fallback-aware helper (handles heat-only TRVs)
        if service == "set_hvac_mode" and data.get("hvac_mode") == "off" and eid:
            await async_turn_off_climate(self.hass, eid, area_id=self._area_id)
            return

        # Resolve hvac_mode to a supported mode (handles auto-only devices)
        if service == "set_hvac_mode" and state:
            hvac_modes = state.attributes.get("hvac_modes") or []
            resolved = resolve_hvac_mode(data["hvac_mode"], hvac_modes)
            if resolved is None:
                _LOGGER.debug(
                    "Area '%s': device '%s' does not support '%s' or any fallback, skipping",
                    self._area_id, eid, data["hvac_mode"],
                )
                return
            if resolved != data["hvac_mode"]:
                _LOGGER.debug(
                    "Area '%s': device '%s' resolved '%s' -> '%s'",
                    self._area_id, eid, data["hvac_mode"], resolved,
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

        # Skip redundant commands (avoids IR blaster beeping every cycle)
        if state:
            if service == "set_hvac_mode" and state.state == data.get("hvac_mode"):
                return
            if service == "set_temperature":
                current = state.attributes.get("temperature")
                desired = data.get("temperature")
                if current is not None and desired is not None and round(current, 1) == round(desired, 1):
                    return

        try:
            await self.hass.services.async_call("climate", service, data, blocking=True)
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "Area '%s': climate.%s failed on '%s'",
                self._area_id, service, data.get("entity_id"),
                exc_info=True,
            )
