"""Device models: TRV/radiator, underfloor zone, split AC, central heat pump, heater, boiler."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ..physics.psychro import LATENT_HEAT, abs_humidity
from ..physics.zone import Gains
from .base import CommandResult, DeviceEnv, SimDevice, approach, clamp

GROUND_TEMP_C = 12.0
VALVE_TRAVEL_S = 120.0
UFH_ACTUATOR_TRAVEL_S = 180.0
COIL_TEMP_C = 10.0
MAX_SUPPLY_C = 75.0
_VALVE_SERVICES = {"set_valve_opening_degree": "opening", "set_valve_closing_degree": "closing"}


def _gains(heat_w: float, radiant_fraction: float) -> Gains:
    return Gains(conv_w=heat_w * (1 - radiant_fraction), rad_w=heat_w * radiant_fraction)


def frost_rate(p: dict[str, Any], t_out: float, rh: float) -> float:
    """Share of a full frost load the outdoor coil gathers per second of heating.

    Frost needs a coil below 0 °C in humid air: none above ~6 °C outdoor, most around
    -5..+3 °C, less in dry deep cold. ``defrost_interval_s`` is the shortest cycle (worst
    conditions); 30-90 min between defrosts is the usual range. Assumed shape, not fitted."""
    interval = float(p.get("defrost_interval_s", 2700))
    if interval <= 0:
        return 0.0
    if t_out >= 6.0 or t_out <= -20.0:
        f_t = 0.0
    elif t_out > 3.0:
        f_t = (6.0 - t_out) / 3.0
    elif t_out >= -5.0:
        f_t = 1.0
    else:
        f_t = (t_out + 20.0) / 15.0
    return f_t * clamp((rh - 60.0) / 30.0, 0.0, 1.0) / interval


def advance_frost(dev: Any, dt: float, env: DeviceEnv, heating: bool) -> bool:
    """Frost and defrost bookkeeping of an air-source unit; True while it defrosts.

    A defrost reverses the cycle for ``defrost_s``: no heat reaches the room, the
    compressor keeps running. Frost thaws off a stopped coil above +2 °C outdoor."""
    p = dev.spec.params
    if heating:
        if env.now < dev.defrost_until:
            return True
        dev.frost += dt * frost_rate(p, env.outdoor.temp_c, env.outdoor.rh)
        if dev.frost >= 1.0:
            dev.frost = 0.0
            dev.defrost_until = env.now + float(p.get("defrost_s", 300))
            return True
    elif env.outdoor.temp_c > 2.0:
        dev.frost = max(0.0, dev.frost - dt / 1800.0)
    return False


def curve_supply_c(p: dict[str, Any], t_out: float, design_default: float) -> float:
    """Supply temperature of a weather-compensated heating curve (straight line from
    ``supply_foot_c`` at +20 °C outdoor to ``supply_temp_c`` at ``design_outdoor_c``).
    ``heating_curve: false`` keeps the supply fixed at ``supply_temp_c``."""
    design = float(p.get("supply_temp_c", design_default))
    if not p.get("heating_curve", True):
        return design
    foot = float(p.get("supply_foot_c", 25.0))
    design_out = float(p.get("design_outdoor_c", -12.0))
    share = (20.0 - t_out) / (20.0 - design_out)
    return clamp(foot + (design - foot) * share, foot, MAX_SUPPLY_C)


@dataclass
class Trv(SimDevice):
    """TRV on a hot-water radiator. The head measures air + bias toward the radiator and
    runs a P controller, so a proportional setpoint from RoomMind acts like real life."""

    model = "trv"

    def __post_init__(self) -> None:
        super().__post_init__()
        self.t_rad: float | None = None
        self.valve = 0.0
        self.valve_opening_deg = 100
        self.valve_closing_deg = 100
        self._next_report = 0.0

    def _apply(self, service: str, data: dict[str, Any]) -> CommandResult:
        kind = _VALVE_SERVICES.get(service)
        if kind is None:
            return super()._apply(service, data)
        if kind not in self.spec.valve_numbers():
            return CommandResult(False, f"unsupported_service:{service}")
        value = round(float(data["value"]))
        if not 0 <= value <= 100:
            return CommandResult(False, "out_of_range")
        attr = f"valve_{kind}_deg"
        changed = getattr(self, attr) != value
        setattr(self, attr, value)
        return CommandResult(True, changed=changed)

    def _valve_position(self, demand: float) -> float:
        """TRVZB semantics: open position = opening degree, closed position = 100 - closing
        degree; the P controller's demand moves the valve between both. Crossed degrees
        (open position below closed position) clamp the demand into their range instead
        of inverting it."""
        lo = 1.0 - self.valve_closing_deg / 100.0
        hi = self.valve_opening_deg / 100.0
        if hi >= lo:
            return lo + demand * (hi - lo)
        return clamp(demand, hi, lo)

    def flow_share(self) -> float:
        """Share of full water flow at the current valve position (dead zone, then position ** exponent)."""
        p = self.spec.params
        dead = float(p.get("valve_dead_zone", 0.0))
        if self.valve <= dead:
            return 0.0
        return ((self.valve - dead) / (1.0 - dead)) ** float(p.get("valve_flow_exponent", 1.0))

    def _design_dt(self) -> float:
        """Mean radiator excess over a 20 °C room at the design supply (steady state, valve open)."""
        p = self.spec.params
        ratio = float(p.get("flow_per_h", 1.5))
        supply = float(p.get("supply_temp_c", 55))
        return (ratio * supply + 20.0) / (ratio + 1.0) - 20.0

    def _size(self, env: DeviceEnv) -> float:
        """Radiator W/K at the design point: explicit, or sized to the room's heat load."""
        p = self.spec.params
        if "h_radiator_w_k" in p:
            return float(p["h_radiator_w_k"])
        ua = env.zone.params.h_air_out + env.zone.params.h_mass_out
        design_w = float(p.get("design_factor", 1.3)) * ua * (20.0 - float(p.get("design_outdoor_c", -12)))
        return design_w / self._design_dt()

    def _physics(self, dt: float, env: DeviceEnv) -> dict[str, Gains]:
        p = self.spec.params
        z = env.zone
        h_rad = self._size(env)
        if self.t_rad is None:
            self.t_rad = z.t_air
        reading = z.t_air + float(p.get("sensor_bias", 0.04)) * (self.t_rad - z.t_air)
        if env.now >= self._next_report:
            self.sensor_c = round(reading, 1)
            self._next_report = env.now + float(p.get("report_interval_s", 60))
        demand = 0.0
        if self.hvac_mode in ("heat", "auto", "heat_cool") and self.available:
            demand = clamp((self.target_c - reading) / float(p.get("p_band_k", 1.0)), 0.0, 1.0)
        self.valve = approach(self.valve, self._valve_position(demand), 1.0 / VALVE_TRAVEL_S, dt)
        supply = env.supply_temp_c if env.supply_temp_c is not None else curve_supply_c(p, env.outdoor.temp_c, 55.0)
        flow = float(p.get("flow_w_k", h_rad * float(p.get("flow_per_h", 1.5))))
        capacity_j_k = float(p.get("radiator_capacity_kj_k", h_rad * float(p.get("capacity_kj_per_h", 1.75)))) * 1000
        q_in = self.flow_share() * flow * max(0.0, supply - self.t_rad)
        # EN 442: output grows with the excess temperature to the power n (~1.3 for panels)
        dt_design = self._design_dt()
        excess = self.t_rad - z.t_air
        n = float(p.get("radiator_exponent", 1.3))
        q_out = h_rad * dt_design * math.copysign((abs(excess) / dt_design) ** n, excess)
        self.t_rad += dt * (q_in - q_out) / capacity_j_k
        self.active = self.valve > 0.05 and q_in > 1.0
        self.hvac_action = "off" if self.hvac_mode == "off" else ("heating" if self.active else "idle")
        self.water_draw_w = q_in
        self._account(dt, q_out, 0.0)
        return {self.room: _gains(q_out, float(p.get("radiant_fraction", 0.3)))}

    def _model_state(self) -> dict[str, Any]:
        return {
            "t_rad": self.t_rad,
            "valve": self.valve,
            "valve_opening_deg": self.valve_opening_deg,
            "valve_closing_deg": self.valve_closing_deg,
        }

    def _restore_model_state(self, data: dict[str, Any]) -> None:
        self.t_rad = data.get("t_rad")
        self.valve = data.get("valve", 0.0)
        self.valve_opening_deg = data.get("valve_opening_deg", 100)
        self.valve_closing_deg = data.get("valve_closing_deg", 100)


@dataclass
class Ufh(SimDevice):
    """Underfloor zone: on/off room thermostat, thermal actuator, screed slab node."""

    model = "ufh"

    def __post_init__(self) -> None:
        super().__post_init__()
        self.t_slab: float | None = None
        self.actuator = 0.0
        self.calling = False

    def _physics(self, dt: float, env: DeviceEnv) -> dict[str, Gains]:
        p = self.spec.params
        z = env.zone
        area = z.params.floor_area_m2 * float(p.get("coverage", 0.9))
        if self.t_slab is None:
            self.t_slab = z.t_air
        reading = z.t_air + float(p.get("sensor_bias_k", 0.0))
        self.sensor_c = round(reading, 1)
        hyst = float(p.get("hysteresis_k", 0.3))
        if self.hvac_mode != "heat" or not self.available:
            self.calling = False
        elif reading <= self.target_c - hyst:
            self.calling = True
        elif reading >= self.target_c + hyst:
            self.calling = False
        self.actuator = approach(self.actuator, 1.0 if self.calling else 0.0, 1.0 / UFH_ACTUATOR_TRAVEL_S, dt)
        supply = env.supply_temp_c if env.supply_temp_c is not None else curve_supply_c(p, env.outdoor.temp_c, 35.0)
        q_in = self.actuator * float(p.get("flow_w_per_m2k", 8)) * area * max(0.0, supply - self.t_slab)
        q_up = float(p.get("h_slab_air_w_per_m2k", 10.8)) * area * (self.t_slab - z.t_air)
        q_down = float(p.get("h_slab_ground_w_per_m2k", 0.5)) * area * (self.t_slab - GROUND_TEMP_C)
        cap = float(p.get("slab_capacity_kj_k_per_m2", 90)) * 1000 * area
        self.t_slab += dt * (q_in - q_up - q_down) / cap
        self.active = self.actuator > 0.5
        self.hvac_action = "off" if self.hvac_mode == "off" else ("heating" if self.active else "idle")
        self.water_draw_w = q_in
        self._account(dt, q_up, 0.0)
        return {self.room: _gains(q_up, float(p.get("radiant_fraction", 0.6)))}

    def _model_state(self) -> dict[str, Any]:
        return {"t_slab": self.t_slab, "actuator": self.actuator, "calling": self.calling}

    def _restore_model_state(self, data: dict[str, Any]) -> None:
        self.t_slab = data.get("t_slab")
        self.actuator = data.get("actuator", 0.0)
        self.calling = data.get("calling", False)


@dataclass
class SplitAc(SimDevice):
    """Inverter split AC. Controls on its return-air sensor (offset while heating),
    modulates, has its own deadband and minimum run, dehumidifies while cooling.

    The return-air offset builds up and fades with ``sensor_offset_tau_s``: warm air
    collects at the intake while the compressor runs and is still there right after
    it stops. With the compressor stopped it settles at ``sensor_offset_idle_k``
    (default 0): a wall unit under the ceiling reads the warm layer once no air
    moves past it.

    ``capacity_tau_s`` lags the delivered output behind the compressor (inverter soft
    start, refrigerant and coil pull-down; the coil also keeps working briefly after a
    stop). ``min_off_s`` is the restart delay after a stop (anti-short-cycle timer).

    Real units ramp up with a time constant of 40-76 s (DOE/AHRI cycling tests). The
    profile keeps ``capacity_tau_s`` at 0: with a 3.5 kW unit at full power the lag
    turned into short cycles and a mislearned model. The earlier explanation (air node
    2-4x faster than real rooms) rested on a throttled real unit (ECO mode) and is void.

    ``max_output`` caps the delivered share (ECO/quiet modes run the inverter well below
    its rating). In heat mode the outdoor coil frosts and defrosts (``frost_rate``)."""

    model = "ac"

    def __post_init__(self) -> None:
        super().__post_init__()
        self.running_mode: str | None = None  # "heat" | "cool" while the compressor runs
        self.on_since = 0.0
        self.modulation = 0.0
        self.output = 0.0  # delivered share of capacity, lags the compressor
        self.output_mode: str | None = None
        self.off_since = -1e12
        self.coil_water_kg = 0.0
        self.sensor_offset_k = 0.0
        self.frost = 0.0  # outdoor coil, 1.0 = defrost due
        self.defrost_until = -1e12

    def _update_sensor_offset(self, dt: float) -> None:
        p = self.spec.params
        goal = float(p.get("sensor_offset_idle_k", 0.0))
        if self.running_mode == "heat":
            goal = float(p.get("sensor_offset_heat_k", 1.5))
        elif self.running_mode == "cool":
            goal = float(p.get("sensor_offset_cool_k", 0.0))
        tau = float(p.get("sensor_offset_tau_s", 0.0))
        if tau <= 0:
            self.sensor_offset_k = goal
        else:
            self.sensor_offset_k += (goal - self.sensor_offset_k) * (1 - math.exp(-dt / tau))

    def _sensor(self, t_air: float) -> float:
        return t_air + self.sensor_offset_k

    def _wanted(self, reading: float) -> str | None:
        p = self.spec.params
        dead = float(p.get("deadband_k", 0.5))
        restart = float(p.get("restart_k", 0.5))
        mode = self.hvac_mode
        if mode in ("heat_cool", "auto"):
            low = self.to_c(self.target_low) if self.target_low is not None else self.target_c - 1
            high = self.to_c(self.target_high) if self.target_high is not None else self.target_c + 1
            if self.running_mode == "heat":
                return "heat" if reading < low + dead else None
            if self.running_mode == "cool":
                return "cool" if reading > high - dead else None
            if reading <= low - restart:
                return "heat"
            if reading >= high + restart:
                return "cool"
            return None
        sp = self.target_c
        if mode == "heat":
            if self.running_mode == "heat":
                return "heat" if reading < sp + dead else None
            return "heat" if reading <= sp - restart else None
        if mode in ("cool", "dry"):
            if self.running_mode == "cool":
                return "cool" if reading > sp - dead else None
            return "cool" if reading >= sp + restart else None
        return None

    def _physics(self, dt: float, env: DeviceEnv) -> dict[str, Gains]:
        p = self.spec.params
        z = env.zone
        t_out = env.outdoor.temp_c
        self._update_sensor_offset(dt)
        reading = self._sensor(z.t_air)
        self.sensor_c = round(reading * 2) / 2
        wanted = self._wanted(reading) if self.available and self.hvac_mode != "off" else None
        min_run = float(p.get("internal_min_run_s", 180))
        if self.running_mode and wanted != self.running_mode:
            # Mode change or "off" commanded stops at once; reaching the setpoint waits for min run.
            commanded_stop = self.hvac_mode == "off" or not self.available or (wanted is not None)
            if commanded_stop or self.hvac_mode in ("fan_only",) or env.now - self.on_since >= min_run:
                self.running_mode = None
                self.off_since = env.now
        if (
            self.running_mode is None
            and wanted is not None
            and env.now - self.off_since >= float(p.get("min_off_s", 0))
        ):
            self.running_mode = wanted
            self.on_since = env.now
        heat_w = 0.0
        electric = 0.0
        moisture = 0.0
        if self.running_mode:
            if self.running_mode == "heat":
                sp = self.to_c(self.target_low) if self.target_low is not None else self.target_c
                err = max(0.0, sp - reading)
            else:
                err = max(0.0, reading - self.target_c)
            lo = float(p.get("min_modulation", 0.3))
            top = float(p.get("max_output", 1.0))
            self.modulation = (
                0.4 if self.hvac_mode == "dry" else clamp(lo + float(p.get("kp", 0.6)) * err, min(lo, top), top)
            )
        else:
            self.modulation = 0.0
        if self.running_mode and self.output_mode not in (None, self.running_mode):
            self.output = 0.0  # reversing the cycle starts from scratch
        defrosting = advance_frost(self, dt, env, self.running_mode == "heat")
        tau = float(p.get("capacity_tau_s", 0.0))
        if defrosting:
            self.output = 0.0  # heating restarts from scratch after the defrost
        elif tau <= 0:
            self.output = self.modulation
        else:
            self.output += (self.modulation - self.output) * (1 - math.exp(-dt / tau))
        if self.running_mode:
            self.output_mode = self.running_mode
        elif self.output < 1e-3 or self.hvac_mode == "off" or not self.available:
            # with the indoor fan stopped the cold coil no longer reaches the room
            self.output, self.output_mode = 0.0, None
        out_mode = self.output_mode
        if out_mode and self.output > 0:
            if out_mode == "heat":
                cap = float(p.get("heat_capacity_w", 3500)) * max(
                    0.3, 1 - float(p.get("heat_derate_per_k", 0.02)) * max(0.0, 7 - t_out)
                )
                heat_w = cap * self.output
                a, b = p.get("cop_heat", [3.2, 0.06])
                electric = heat_w / max(1.5, a + b * t_out)
            else:
                q = float(p.get("cool_capacity_w", 3500)) * self.output
                shr = 0.5 if self.hvac_mode == "dry" else float(p.get("shr", 0.75))
                electric = q / float(p.get("eer", 3.5))
                if z.x > abs_humidity(COIL_TEMP_C, 100):
                    latent = q * (1 - shr)
                    moisture = -latent / LATENT_HEAT
                    self.coil_water_kg += -moisture * dt
                    heat_w = -q * shr
                else:
                    heat_w = -q
        if defrosting:
            electric = float(p.get("heat_capacity_w", 3500)) * 0.1
        if not self.running_mode:
            electric = 0.0  # what the coil still delivers after a stop costs no compressor power
            if self.coil_water_kg > 0:
                rate = 3e-5 if self.hvac_mode == "fan_only" else 3e-6  # kg/s re-evaporation / drain
                evap = min(self.coil_water_kg, rate * dt)
                self.coil_water_kg -= evap
                if self.hvac_mode == "fan_only":
                    moisture += evap / dt
        fan_on = self.hvac_mode != "off" and self.available
        electric += 25.0 if fan_on else 2.0
        self.active = self.running_mode is not None
        self.hvac_action = {
            # most integrations keep showing "heating" through a defrost; some report it
            "heat": str(p.get("defrost_action", "heating")) if defrosting else "heating",
            "cool": "drying" if self.hvac_mode == "dry" else "cooling",
        }.get(
            self.running_mode or "",
            "fan" if self.hvac_mode == "fan_only" else ("off" if self.hvac_mode == "off" else "idle"),
        )
        self._account(dt, heat_w, electric)
        return {self.room: Gains(conv_w=heat_w, moisture_kg_s=moisture)}

    def _model_state(self) -> dict[str, Any]:
        return {
            "running_mode": self.running_mode,
            "on_since": self.on_since,
            "off_since": self.off_since,
            "output": self.output,
            "output_mode": self.output_mode,
            "coil_water_kg": self.coil_water_kg,
            "sensor_offset_k": self.sensor_offset_k,
            "frost": self.frost,
            "defrost_until": self.defrost_until,
        }

    def _restore_model_state(self, data: dict[str, Any]) -> None:
        self.running_mode = data.get("running_mode")
        self.on_since = data.get("on_since", 0.0)
        self.off_since = data.get("off_since", -1e12)
        self.output = data.get("output", 0.0)
        self.output_mode = data.get("output_mode")
        self.coil_water_kg = data.get("coil_water_kg", 0.0)
        self.sensor_offset_k = data.get("sensor_offset_k", 0.0)
        self.frost = data.get("frost", 0.0)
        self.defrost_until = data.get("defrost_until", -1e12)


@dataclass
class HeatPump(SimDevice):
    """Central ducted heat pump behind a thermostat (Ecobee-like), range setpoint."""

    model = "heat_pump"

    def __post_init__(self) -> None:
        super().__post_init__()
        self.running_mode: str | None = None
        self.on_since = 0.0
        self.frost = 0.0
        self.defrost_until = -1e12

    def _physics(self, dt: float, env: DeviceEnv) -> dict[str, Gains]:
        p = self.spec.params
        z = env.zone
        reading = z.t_air
        self.sensor_c = reading
        h = float(p.get("hysteresis_k", 0.5))
        mode = self.hvac_mode if self.available else "off"
        low = (
            self.to_c(self.target_low)
            if mode in ("heat_cool", "auto") and self.target_low is not None
            else self.target_c
        )
        high = (
            self.to_c(self.target_high)
            if mode in ("heat_cool", "auto") and self.target_high is not None
            else self.target_c
        )
        want: str | None = None
        if mode in ("heat", "heat_cool", "auto"):
            if reading <= low - h or (self.running_mode == "heat" and reading < low + h):
                want = "heat"
        if want is None and mode in ("cool", "heat_cool", "auto"):
            if reading >= high + h or (self.running_mode == "cool" and reading > high - h):
                want = "cool"
        if self.running_mode != want:
            ran = env.now - self.on_since
            if self.running_mode is None or mode == "off" or ran >= float(p.get("min_run_s", 300)):
                self.running_mode = want
                self.on_since = env.now
        rooms = [self.room, *(p.get("serves_rooms") or [])]
        heat_w = 0.0
        electric = 0.0
        moisture = 0.0
        defrosting = advance_frost(self, dt, env, self.running_mode == "heat")
        if self.running_mode == "heat":
            heat_w = 0.0 if defrosting else float(p.get("heat_capacity_w", 8000))
            a, b = p.get("cop_heat", [2.8, 0.05])
            electric = (
                (0.1 * float(p.get("heat_capacity_w", 8000)))
                if defrosting
                else heat_w / max(1.5, a + b * env.outdoor.temp_c)
            )
        elif self.running_mode == "cool":
            q = float(p.get("cool_capacity_w", 7000))
            electric = q / float(p.get("eer", 3.2))
            shr = float(p.get("shr", 0.7))
            heat_w = -q * shr
            moisture = -q * (1 - shr) / LATENT_HEAT
        self.active = self.running_mode is not None
        heating_action = str(p.get("defrost_action", "heating")) if defrosting else "heating"
        self.hvac_action = {"heat": heating_action, "cool": "cooling"}.get(
            self.running_mode or "", "off" if mode == "off" else "idle"
        )
        self._account(dt, heat_w, electric + (40 if self.active else 3))
        share = 1 / len(rooms)
        return {r: Gains(conv_w=heat_w * share, moisture_kg_s=moisture * share) for r in rooms}

    def _model_state(self) -> dict[str, Any]:
        return {
            "running_mode": self.running_mode,
            "on_since": self.on_since,
            "frost": self.frost,
            "defrost_until": self.defrost_until,
        }

    def _restore_model_state(self, data: dict[str, Any]) -> None:
        self.running_mode = data.get("running_mode")
        self.on_since = data.get("on_since", 0.0)
        self.frost = data.get("frost", 0.0)
        self.defrost_until = data.get("defrost_until", -1e12)


@dataclass
class Heater(SimDevice):
    """Electric heater with body mass and on/off thermostat; "cool" is a fan only (Dyson)."""

    model = "heater"

    def __post_init__(self) -> None:
        super().__post_init__()
        self.t_body: float | None = None
        self.element = False

    def _physics(self, dt: float, env: DeviceEnv) -> dict[str, Gains]:
        p = self.spec.params
        z = env.zone
        if self.t_body is None:
            self.t_body = z.t_air
        power = float(p.get("power_w", 1500))
        h_body = power / 40.0
        reading = z.t_air + (float(p.get("sensor_bias_k", 0.5)) if self.element else 0.0)
        self.sensor_c = round(reading, 1)
        hyst = float(p.get("hysteresis_k", 0.4))
        if self.hvac_mode != "heat" or not self.available:
            self.element = False
        elif reading <= self.target_c - hyst:
            self.element = True
        elif reading >= self.target_c + hyst:
            self.element = False
        q_el = power if self.element else 0.0
        q_out = h_body * (self.t_body - z.t_air)
        self.t_body += dt * (q_el - q_out) / (float(p.get("capacity_kj_k", 15)) * 1000)
        self.active = self.element
        fan = 30.0 if self.hvac_mode == "cool" else 0.0
        self.hvac_action = (
            "heating"
            if self.element
            else ("cooling" if self.hvac_mode == "cool" else ("off" if self.hvac_mode == "off" else "idle"))
        )
        self._account(dt, q_out, q_el + fan)
        return {self.room: _gains(q_out, float(p.get("radiant_fraction", 0.3)))}

    def _model_state(self) -> dict[str, Any]:
        return {"t_body": self.t_body, "element": self.element}

    def _restore_model_state(self, data: dict[str, Any]) -> None:
        self.t_body = data.get("t_body")
        self.element = data.get("element", False)


@dataclass
class Boiler(SimDevice):
    """Central heat source. Supplies hot water to the TRV/UFH devices it serves; the
    burner fires while switched on and someone draws heat."""

    model = "boiler"

    def __post_init__(self) -> None:
        super().__post_init__()
        self.t_water: float | None = None
        self.load_w = 0.0  # last tick's draw from served devices (set by the world)

    def serves(self, entity_id: str) -> bool:
        serves = self.spec.params.get("serves", "all")
        return serves == "all" or entity_id in (serves or [])

    def supply_temp(self, room_temp: float) -> float:
        return self.t_water if self.t_water is not None else room_temp

    def _physics(self, dt: float, env: DeviceEnv) -> dict[str, Gains]:
        p = self.spec.params
        if self.t_water is None:
            self.t_water = env.zone.t_air
        on = self.hvac_mode == "heat" and self.available
        target = curve_supply_c(p, env.outdoor.temp_c, 60.0) if on else env.zone.t_air
        warmup = float(p.get("warmup_s", 120))
        self.t_water += (target - self.t_water) * min(1.0, dt / max(warmup, dt))
        self.sensor_c = round(self.t_water, 1)
        self.active = on and self.load_w > 50
        self.hvac_action = "heating" if self.active else ("off" if not on else "idle")
        self._account(dt, 0.0, self.load_w / float(p.get("efficiency", 0.92)) if self.active else 0.0)
        return {}

    def _model_state(self) -> dict[str, Any]:
        return {"t_water": self.t_water}

    def _restore_model_state(self, data: dict[str, Any]) -> None:
        self.t_water = data.get("t_water")


MODELS: dict[str, type[SimDevice]] = {
    "trv": Trv,
    "ufh": Ufh,
    "ac": SplitAc,
    "heat_pump": HeatPump,
    "heater": Heater,
    "boiler": Boiler,
}


def create_device(spec, rng) -> SimDevice:  # noqa: ANN001
    return MODELS[spec.model](spec=spec, rng=rng)
