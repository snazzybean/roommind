"""Device model base: capabilities, commands, quirk hooks, unit handling."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from ..physics.zone import Gains, Zone
from ..scenario.model import DeviceSpec
from ..weather import Outdoor

ACTIVE_STATES = ("heat", "cool", "heat_cool", "auto", "dry")


@dataclass
class CommandResult:
    ok: bool
    reason: str = ""
    changed: bool = False

    @property
    def status(self) -> str:
        if not self.ok:
            return f"rejected:{self.reason}"
        return "accepted" if self.changed else "accepted:no_change"


@dataclass
class DeviceEnv:
    now: float
    zone: Zone
    outdoor: Outdoor
    zones: dict[str, Zone]
    supply_temp_c: float | None = None  # from a boiler master, None = own default


@dataclass
class DeviceCounters:
    heat_j: float = 0.0  # delivered to rooms (+heat, -cooling)
    electric_j: float = 0.0
    starts: int = 0
    active_s: float = 0.0
    commands: int = 0
    rejected: int = 0
    beeps: int = 0


@dataclass
class SimDevice:
    """Common state and command handling. Subclasses implement ``_physics``."""

    spec: DeviceSpec
    rng: random.Random
    hvac_mode: str = "off"
    target: float = 0.0  # device unit
    target_low: float | None = None
    target_high: float | None = None
    fan_mode: str | None = None
    available: bool = True
    active: bool = False  # compressor / burner / valve open
    hvac_action: str = "off"
    sensor_c: float | None = None  # what the device itself measures
    boot_time: float = 0.0
    counters: DeviceCounters = field(default_factory=DeviceCounters)
    last_command: tuple[str, float] | None = None
    quirks: list[Any] = field(default_factory=list)

    model = "base"

    def __post_init__(self) -> None:
        from .quirks import make_quirk

        caps = self.spec.capabilities
        self.unit = str(caps.get("unit", "C")).upper()
        self.hvac_modes: list[str] = list(caps.get("hvac_modes", ["off", "heat"]))
        self.fan_modes: list[str] = list(caps.get("fan_modes", []))
        self.min_temp = float(caps.get("min_temp", self.from_c(7)))
        self.max_temp = float(caps.get("max_temp", self.from_c(30)))
        self.step_size = float(caps.get("target_temp_step", 0.5 if self.unit == "C" else 1.0))
        self.range_setpoint = bool(caps.get("range_setpoint", False))
        p = self.spec.params
        self.hvac_mode = p.get("initial_mode", "off")
        self.target = self._snap(self.from_c(float(p.get("initial_target_c", 20.0))))
        if self.range_setpoint:
            self.target_low = self._snap(self.from_c(float(p.get("initial_low_c", 20.0))))
            self.target_high = self._snap(self.from_c(float(p.get("initial_high_c", 24.0))))
        self.fan_mode = self.fan_modes[0] if self.fan_modes else None
        self._last_on_mode = next((m for m in self.hvac_modes if m != "off"), "heat")
        self.quirks = [make_quirk(q) for q in self.spec.quirks]

    # --- identity / units ---------------------------------------------------------------

    @property
    def entity_id(self) -> str:
        return self.spec.entity_id

    @property
    def room(self) -> str:
        return self.spec.room

    def to_c(self, value: float) -> float:
        return (value - 32.0) * 5.0 / 9.0 if self.unit == "F" else value

    def from_c(self, value: float) -> float:
        return value * 9.0 / 5.0 + 32.0 if self.unit == "F" else value

    def _snap(self, value: float) -> float:
        step = self.step_size or 0.5
        return round(round(value / step) * step, 2)

    @property
    def target_c(self) -> float:
        return self.to_c(self.target)

    # --- HA view ----------------------------------------------------------------------

    def state(self, now: float) -> str:
        for q in self.quirks:
            st = q.state_override(self, now)
            if st is not None:
                return st
        return self.hvac_mode if self.available else "unavailable"

    def attributes(self, now: float) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "hvac_mode": self.hvac_mode,
            "hvac_modes": self.hvac_modes,
            "hvac_action": self.hvac_action,
            "current_temperature": None if self.sensor_c is None else round(self.from_c(self.sensor_c), 1),
            "min_temp": self.min_temp,
            "max_temp": self.max_temp,
            "target_temp_step": self.step_size,
            "unit": self.unit,
        }
        if self.range_setpoint and self.hvac_mode in ("heat_cool", "auto"):
            attrs["temperature"] = None
            attrs["target_temp_low"] = self.target_low
            attrs["target_temp_high"] = self.target_high
        else:
            attrs["temperature"] = self.target
            if self.range_setpoint:
                attrs["target_temp_low"] = None
                attrs["target_temp_high"] = None
        if self.fan_modes:
            attrs["fan_mode"] = self.fan_mode
            attrs["fan_modes"] = self.fan_modes
        for q in self.quirks:
            attrs = q.transform_attributes(self, attrs, now)
        return attrs

    # --- commands ---------------------------------------------------------------------

    def call(self, service: str, data: dict[str, Any], now: float) -> CommandResult:
        self.counters.commands += 1
        result: CommandResult | None = None
        if not self.available:
            result = CommandResult(False, "unavailable")
        for q in self.quirks:
            if result is None:
                result = q.before_command(self, service, data, now)
        if result is None:
            result = self._apply(service, data)
        for q in self.quirks:
            q.after_command(self, service, data, now, result)
        if not result.ok:
            self.counters.rejected += 1
        self.last_command = (service, now)
        return result

    def _apply(self, service: str, data: dict[str, Any]) -> CommandResult:
        before = (self.hvac_mode, self.target, self.target_low, self.target_high, self.fan_mode)
        if service == "set_hvac_mode":
            res = self._set_mode(data.get("hvac_mode"))
            if res is not None:
                return res
        elif service == "set_temperature":
            if data.get("hvac_mode"):
                res = self._set_mode(data["hvac_mode"])
                if res is not None:
                    return res
            if "temperature" in data and data["temperature"] is not None:
                self.target = self._snap(float(data["temperature"]))
            if data.get("target_temp_low") is not None:
                if not self.range_setpoint:
                    return CommandResult(False, "range_not_supported")
                self.target_low = self._snap(float(data["target_temp_low"]))
            if data.get("target_temp_high") is not None:
                if not self.range_setpoint:
                    return CommandResult(False, "range_not_supported")
                self.target_high = self._snap(float(data["target_temp_high"]))
        elif service == "set_fan_mode":
            if data.get("fan_mode") not in self.fan_modes:
                return CommandResult(False, "invalid_fan_mode")
            self.fan_mode = data["fan_mode"]
        elif service == "turn_on":
            res = self._set_mode(self._last_on_mode)
            if res is not None:
                return res
        elif service == "turn_off":
            res = self._set_mode("off")
            if res is not None:
                return res
        else:
            return CommandResult(False, f"unsupported_service:{service}")
        after = (self.hvac_mode, self.target, self.target_low, self.target_high, self.fan_mode)
        return CommandResult(True, changed=before != after)

    def _set_mode(self, mode: str | None) -> CommandResult | None:
        if mode not in self.hvac_modes:
            return CommandResult(False, "invalid_hvac_mode")
        self.hvac_mode = mode
        if mode != "off":
            self._last_on_mode = mode
        return None

    def force_mode(self, mode: str) -> None:
        """Used by quirks/manual actions to change the mode without counting a command."""
        if mode in self.hvac_modes or mode == "off":
            self.hvac_mode = mode

    # --- simulation -------------------------------------------------------------------

    def step(self, dt: float, env: DeviceEnv) -> dict[str, Gains]:
        for q in self.quirks:
            q.on_step(self, dt, env.now)
        was_active = self.active
        gains = self._physics(dt, env)
        if self.active and not was_active:
            self.counters.starts += 1
        if self.active:
            self.counters.active_s += dt
        return gains

    def _physics(self, dt: float, env: DeviceEnv) -> dict[str, Gains]:
        raise NotImplementedError

    def heat_output_w(self) -> float:
        """Last delivered heat (negative while cooling), for samples."""
        return getattr(self, "_last_heat_w", 0.0)

    def electric_w(self) -> float:
        return getattr(self, "_last_electric_w", 0.0)

    def _account(self, dt: float, heat_w: float, electric_w: float) -> None:
        self._last_heat_w = heat_w
        self._last_electric_w = electric_w
        self.counters.heat_j += heat_w * dt
        self.counters.electric_j += electric_w * dt

    def snapshot(self) -> dict[str, Any]:
        data = {
            "hvac_mode": self.hvac_mode,
            "target": self.target,
            "target_low": self.target_low,
            "target_high": self.target_high,
            "fan_mode": self.fan_mode,
            "available": self.available,
            "active": self.active,
            "sensor_c": self.sensor_c,
            "last_on_mode": self._last_on_mode,
            "counters": self.counters.__dict__.copy(),
            "model_state": self._model_state(),
            "quirks": [q.snapshot() for q in self.quirks],
        }
        return data

    def restore(self, data: dict[str, Any]) -> None:
        for key in ("hvac_mode", "target", "target_low", "target_high", "fan_mode", "available", "active", "sensor_c"):
            setattr(self, key, data[key])
        self._last_on_mode = data.get("last_on_mode", self._last_on_mode)
        self.counters = DeviceCounters(**data.get("counters", {}))
        self._restore_model_state(data.get("model_state") or {})
        for q, qs in zip(self.quirks, data.get("quirks") or [], strict=False):
            q.restore(qs)

    def _model_state(self) -> dict[str, Any]:
        return {}

    def _restore_model_state(self, data: dict[str, Any]) -> None:
        return None


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def approach(current: float, target: float, rate_per_s: float, dt: float) -> float:
    """Move ``current`` towards ``target`` by at most ``rate_per_s * dt``."""
    delta = target - current
    limit = rate_per_s * dt
    return target if abs(delta) <= limit else current + limit * (1 if delta > 0 else -1)
