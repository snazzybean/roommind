"""Device models: TRV/radiator, underfloor zone, split AC, central heat pump, heater, boiler."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..physics.psychro import LATENT_HEAT, abs_humidity
from ..physics.zone import Gains
from .base import DeviceEnv, SimDevice, approach, clamp

GROUND_TEMP_C = 12.0
VALVE_TRAVEL_S = 120.0
UFH_ACTUATOR_TRAVEL_S = 180.0
COIL_TEMP_C = 10.0


def _gains(heat_w: float, radiant_fraction: float) -> Gains:
    return Gains(conv_w=heat_w * (1 - radiant_fraction), rad_w=heat_w * radiant_fraction)


@dataclass
class Trv(SimDevice):
    """TRV on a hot-water radiator. The head measures air + bias toward the radiator and
    runs a P controller, so a proportional setpoint from RoomMind acts like real life."""

    model = "trv"

    def __post_init__(self) -> None:
        super().__post_init__()
        self.t_rad: float | None = None
        self.valve = 0.0
        self._next_report = 0.0

    def _physics(self, dt: float, env: DeviceEnv) -> dict[str, Gains]:
        p = self.spec.params
        z = env.zone
        if self.t_rad is None:
            self.t_rad = z.t_air
        reading = z.t_air + float(p.get("sensor_bias", 0.04)) * (self.t_rad - z.t_air)
        if env.now >= self._next_report:
            self.sensor_c = round(reading, 1)
            self._next_report = env.now + float(p.get("report_interval_s", 60))
        demand = 0.0
        if self.hvac_mode in ("heat", "auto", "heat_cool") and self.available:
            demand = clamp((self.target_c - reading) / float(p.get("p_band_k", 1.0)), 0.0, 1.0)
        self.valve = approach(self.valve, demand, 1.0 / VALVE_TRAVEL_S, dt)
        supply = env.supply_temp_c if env.supply_temp_c is not None else float(p.get("supply_temp_c", 55))
        q_in = self.valve * float(p.get("flow_w_k", 200)) * max(0.0, supply - self.t_rad)
        q_out = float(p.get("h_radiator_w_k", 40)) * (self.t_rad - z.t_air)
        self.t_rad += dt * (q_in - q_out) / (float(p.get("radiator_capacity_kj_k", 30)) * 1000)
        self.active = self.valve > 0.05 and q_in > 1.0
        self.hvac_action = "off" if self.hvac_mode == "off" else ("heating" if self.active else "idle")
        self.water_draw_w = q_in
        self._account(dt, q_out, 0.0)
        return {self.room: _gains(q_out, float(p.get("radiant_fraction", 0.3)))}

    def _model_state(self) -> dict[str, Any]:
        return {"t_rad": self.t_rad, "valve": self.valve}

    def _restore_model_state(self, data: dict[str, Any]) -> None:
        self.t_rad = data.get("t_rad")
        self.valve = data.get("valve", 0.0)


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
        supply = env.supply_temp_c if env.supply_temp_c is not None else float(p.get("supply_temp_c", 35))
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
    modulates, has its own deadband and minimum run, dehumidifies while cooling."""

    model = "ac"

    def __post_init__(self) -> None:
        super().__post_init__()
        self.running_mode: str | None = None  # "heat" | "cool" while the compressor runs
        self.on_since = 0.0
        self.modulation = 0.0
        self.coil_water_kg = 0.0

    def _sensor(self, t_air: float) -> float:
        p = self.spec.params
        if self.running_mode == "heat":
            return t_air + float(p.get("sensor_offset_heat_k", 1.5))
        if self.running_mode == "cool":
            return t_air + float(p.get("sensor_offset_cool_k", 0.0))
        return t_air

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
        reading = self._sensor(z.t_air)
        self.sensor_c = round(reading * 2) / 2
        wanted = self._wanted(reading) if self.available and self.hvac_mode != "off" else None
        min_run = float(p.get("internal_min_run_s", 180))
        if self.running_mode and wanted != self.running_mode:
            # Mode change or "off" commanded stops at once; reaching the setpoint waits for min run.
            commanded_stop = self.hvac_mode == "off" or not self.available or (wanted is not None)
            if commanded_stop or self.hvac_mode in ("fan_only",) or env.now - self.on_since >= min_run:
                self.running_mode = None
        if self.running_mode is None and wanted is not None:
            self.running_mode = wanted
            self.on_since = env.now
        heat_w = 0.0
        electric = 0.0
        moisture = 0.0
        if self.running_mode:
            err = abs(
                (
                    self.to_c(self.target_low)
                    if self.running_mode == "heat" and self.target_low is not None
                    else self.target_c
                )
                - reading
            )
            lo = float(p.get("min_modulation", 0.3))
            self.modulation = 0.4 if self.hvac_mode == "dry" else clamp(lo + float(p.get("kp", 0.6)) * err, lo, 1.0)
            if self.running_mode == "heat":
                cap = float(p.get("heat_capacity_w", 3500)) * max(
                    0.3, 1 - float(p.get("heat_derate_per_k", 0.02)) * max(0.0, 7 - t_out)
                )
                heat_w = cap * self.modulation
                a, b = p.get("cop_heat", [3.2, 0.06])
                electric = heat_w / max(1.5, a + b * t_out)
            else:
                q = float(p.get("cool_capacity_w", 3500)) * self.modulation
                shr = 0.5 if self.hvac_mode == "dry" else float(p.get("shr", 0.75))
                electric = q / float(p.get("eer", 3.5))
                if z.x > abs_humidity(COIL_TEMP_C, 100):
                    latent = q * (1 - shr)
                    moisture = -latent / LATENT_HEAT
                    self.coil_water_kg += -moisture * dt
                    heat_w = -q * shr
                else:
                    heat_w = -q
        else:
            self.modulation = 0.0
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
            "heat": "heating",
            "cool": "drying" if self.hvac_mode == "dry" else "cooling",
        }.get(
            self.running_mode or "",
            "fan" if self.hvac_mode == "fan_only" else ("off" if self.hvac_mode == "off" else "idle"),
        )
        self._account(dt, heat_w, electric)
        return {self.room: Gains(conv_w=heat_w, moisture_kg_s=moisture)}

    def _model_state(self) -> dict[str, Any]:
        return {"running_mode": self.running_mode, "on_since": self.on_since, "coil_water_kg": self.coil_water_kg}

    def _restore_model_state(self, data: dict[str, Any]) -> None:
        self.running_mode = data.get("running_mode")
        self.on_since = data.get("on_since", 0.0)
        self.coil_water_kg = data.get("coil_water_kg", 0.0)


@dataclass
class HeatPump(SimDevice):
    """Central ducted heat pump behind a thermostat (Ecobee-like), range setpoint."""

    model = "heat_pump"

    def __post_init__(self) -> None:
        super().__post_init__()
        self.running_mode: str | None = None
        self.on_since = 0.0

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
        if self.running_mode == "heat":
            heat_w = float(p.get("heat_capacity_w", 8000))
            a, b = p.get("cop_heat", [2.8, 0.05])
            electric = heat_w / max(1.5, a + b * env.outdoor.temp_c)
        elif self.running_mode == "cool":
            q = float(p.get("cool_capacity_w", 7000))
            electric = q / float(p.get("eer", 3.2))
            shr = float(p.get("shr", 0.7))
            heat_w = -q * shr
            moisture = -q * (1 - shr) / LATENT_HEAT
        self.active = self.running_mode is not None
        self.hvac_action = {"heat": "heating", "cool": "cooling"}.get(
            self.running_mode or "", "off" if mode == "off" else "idle"
        )
        self._account(dt, heat_w, electric + (40 if self.active else 3))
        share = 1 / len(rooms)
        return {r: Gains(conv_w=heat_w * share, moisture_kg_s=moisture * share) for r in rooms}

    def _model_state(self) -> dict[str, Any]:
        return {"running_mode": self.running_mode, "on_since": self.on_since}

    def _restore_model_state(self, data: dict[str, Any]) -> None:
        self.running_mode = data.get("running_mode")
        self.on_since = data.get("on_since", 0.0)


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
        target = float(p.get("supply_temp_c", 60)) if on else env.zone.t_air
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
