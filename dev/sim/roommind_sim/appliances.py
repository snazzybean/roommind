"""Room appliances beside the climate devices: exhaust fan, dehumidifier, humidifier, room fan.

Each is a ``fan.*``, ``switch.*`` or ``humidifier.*`` entity in HA; the domain comes from
the entity id, the behaviour from ``model``. ``on`` is the power state HA shows,
``running`` whether the appliance actually works (a device hygrostat idles it).

Physics conventions (see README "Appliances"):

- Exhaust fan: by default extra outdoor-air exchange through ``Gains.vent_w_k``; the zone
  turns it into heat loss and moisture exchange with the outdoor humidity ratio. With
  ``makeup_room`` the air comes from that room (door gap) at its temperature and humidity,
  and that room draws the same flow of outdoor air. The motor heat leaves with the exhaust.
- Dehumidifier (compressor): removes water at ``rated_kg_h`` at ``rated_temp_c`` /
  ``rated_rh``, proportional to the humidity ratio above its coil (``coil_temp_c``),
  zero below it. Electric power and the condensation heat end up in the room.
- Humidifier: adds ``rated_kg_h`` (tapering to 0 between 90 and 100 % RH); the water
  evaporates in the room air and takes its latent heat from it.
- Room fan (ceiling/standing): motor heat only; while running it raises the convective
  output of the room's radiators (``radiator_boost``) and the air-to-mass coupling
  (``mixing_boost``). The zone has no stratification, so there is no further effect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .devices.base import CommandResult, clamp
from .physics.psychro import AIR_DENSITY, CP_AIR, LATENT_HEAT, abs_humidity
from .physics.zone import Gains, Zone
from .scenario.model import ApplianceSpec
from .weather import Outdoor

APPLIANCE_MODELS: dict[str, tuple[str, ...]] = {
    "exhaust_fan": ("fan", "switch"),
    "dehumidifier": ("humidifier", "switch"),
    "humidifier": ("humidifier", "switch"),
    "room_fan": ("fan", "switch"),
}
HYGROSTAT_MODELS = ("dehumidifier", "humidifier")


@dataclass
class ApplianceCounters:
    starts: int = 0  # running: off -> on
    run_s: float = 0.0
    on_s: float = 0.0
    electric_j: float = 0.0
    heat_j: float = 0.0  # sensible heat to the room (negative = removed)
    moisture_kg: float = 0.0  # + added to the room, - removed
    commands: int = 0
    rejected: int = 0
    manual: int = 0


@dataclass
class SimAppliance:
    spec: ApplianceSpec
    on: bool = False
    percentage: int = 100
    target_humidity: float | None = None
    running: bool = False
    available: bool = True
    current_rh: float | None = None  # the appliance's own humidity reading
    off_since: float = -1e12
    electric_w: float = 0.0
    heat_w: float = 0.0
    moisture_kg_s: float = 0.0
    counters: ApplianceCounters = field(default_factory=ApplianceCounters)

    def __post_init__(self) -> None:
        p = self.spec.params
        self.on = bool(p.get("initial_on", False))
        self.percentage = int(p.get("initial_percentage", 100))
        target = p.get("target_humidity")
        self.target_humidity = None if target is None else float(target)

    # --- identity ---------------------------------------------------------------------

    @property
    def entity_id(self) -> str:
        return self.spec.entity_id

    @property
    def room(self) -> str:
        return self.spec.room

    @property
    def model(self) -> str:
        return self.spec.model

    @property
    def domain(self) -> str:
        return self.spec.entity_id.split(".", 1)[0]

    @property
    def speed_count(self) -> int:
        """Fan speeds HA offers (0 = on/off only); only ``fan.*`` entities have them."""
        return int(self.spec.params.get("speed_count", 0)) if self.domain == "fan" else 0

    @property
    def min_humidity(self) -> float:
        return float(self.spec.params.get("min_humidity", 30))

    @property
    def max_humidity(self) -> float:
        return float(self.spec.params.get("max_humidity", 80))

    @property
    def share(self) -> float:
        """Running share of full airflow/power (percentage on fans with speeds)."""
        return self.percentage / 100.0 if self.speed_count else 1.0

    # --- commands ---------------------------------------------------------------------

    def call(self, service: str, data: dict[str, Any], now: float) -> CommandResult:
        self.counters.commands += 1
        result = CommandResult(False, "unavailable") if not self.available else self._apply(service, data)
        if not result.ok:
            self.counters.rejected += 1
        return result

    def _apply(self, service: str, data: dict[str, Any]) -> CommandResult:
        before = (self.on, self.percentage, self.target_humidity)
        if service == "turn_on":
            pct = data.get("percentage")
            if pct is not None:
                res = self._set_percentage(pct)
                if res is not None:
                    return res
            else:
                self.on = True
        elif service == "turn_off":
            self.on = False
        elif service == "set_percentage":
            res = self._set_percentage(data.get("percentage"))
            if res is not None:
                return res
        elif service == "set_humidity":
            if self.domain != "humidifier":
                return CommandResult(False, f"unsupported_service:{service}")
            value = float(data["humidity"])
            if not self.min_humidity <= value <= self.max_humidity:
                return CommandResult(False, "out_of_range")
            self.target_humidity = value
        else:
            return CommandResult(False, f"unsupported_service:{service}")
        return CommandResult(True, changed=before != (self.on, self.percentage, self.target_humidity))

    def _set_percentage(self, pct: Any) -> CommandResult | None:
        if not self.speed_count:
            return CommandResult(False, "unsupported_service:set_percentage")
        value = round(float(pct))
        if not 0 <= value <= 100:
            return CommandResult(False, "out_of_range")
        if value == 0:
            self.on = False
        else:
            self.on, self.percentage = True, value
        return None

    def manual(self, args: dict[str, Any]) -> None:
        """Someone at the device (button, remote): no command, RoomMind sees only the state."""
        # YAML reads a bare on/off as a boolean, so both spellings arrive here
        state = args.get("state", args.get("on"))
        if state is not None:
            self.on = state is True or state == "on"
        if args.get("percentage") is not None:
            self.percentage = int(args["percentage"])
        if args.get("target_humidity") is not None:
            self.target_humidity = float(args["target_humidity"])
        self.counters.manual += 1

    # --- effects on other parts of the house ------------------------------------------------

    def radiator_factor(self) -> float:
        """Multiplier on the room's radiator output while a room fan runs."""
        if self.model != "room_fan" or not self.running:
            return 1.0
        return 1.0 + (float(self.spec.params.get("radiator_boost", 1.3)) - 1.0) * self.share

    def mixing_factor(self) -> float:
        """Multiplier on the room's air-to-mass coupling while a room fan runs."""
        if self.model != "room_fan" or not self.running:
            return 1.0
        return 1.0 + float(self.spec.params.get("mixing_boost", 0.1)) * self.share

    # --- simulation -------------------------------------------------------------------

    def _hygrostat(self, want: bool) -> bool:
        if not want or self.model not in HYGROSTAT_MODELS or self.target_humidity is None:
            return want
        rh = self.current_rh if self.current_rh is not None else 0.0
        hyst = float(self.spec.params.get("hysteresis_pct", 2.0))
        if self.model == "dehumidifier":
            if rh >= self.target_humidity + hyst:
                return True
            if rh <= self.target_humidity - hyst:
                return False
        else:
            if rh <= self.target_humidity - hyst:
                return True
            if rh >= self.target_humidity + hyst:
                return False
        return self.running

    def step(self, dt: float, zones: dict[str, Zone], outdoor: Outdoor, now: float) -> dict[str, Gains]:
        """Advance by ``dt``; returns the gains per room (an exhaust fan with ``makeup_room``
        also acts on the room its make-up air comes from)."""
        p = self.spec.params
        zone = zones[self.room]
        self.current_rh = zone.rh + float(p.get("rh_offset", 0.0))
        want = self._hygrostat(self.on and self.available)
        if want and not self.running and now - self.off_since < float(p.get("min_off_s", 0.0)):
            want = False  # compressor restart delay
        if want and not self.running:
            self.counters.starts += 1
        if self.running and not want:
            self.off_since = now
        self.running = want
        gains = Gains()
        out = {self.room: gains}
        electric = heat = moisture = 0.0
        if self.running:
            share = self.share
            electric = float(p.get("power_w", 0.0)) * share
            if self.model == "exhaust_fan":
                flow_kg_s = float(p.get("airflow_m3_h", 80.0)) * share * AIR_DENSITY / 3600.0
                w_k = flow_kg_s * CP_AIR
                source = p.get("makeup_room")
                if source:
                    # make-up air through the door gap; the source room draws outdoor air in turn
                    src = zones[source]
                    heat = w_k * (src.t_air - zone.t_air)
                    moisture = flow_kg_s * (src.x - zone.x)
                    gains.conv_w = heat
                    gains.moisture_kg_s = moisture
                    out[source] = Gains(vent_w_k=w_k)
                else:
                    # the zone applies heat and moisture exchange with outdoor air through vent_w_k
                    gains.vent_w_k = w_k
                    heat = -w_k * (zone.t_air - outdoor.temp_c)
                    moisture = -flow_kg_s * (zone.x - outdoor.x)
            elif self.model == "dehumidifier":
                x_coil = abs_humidity(float(p.get("coil_temp_c", 5.0)), 100.0)
                x_rated = abs_humidity(float(p.get("rated_temp_c", 20.0)), float(p.get("rated_rh", 60.0)))
                taper = clamp((zone.x - x_coil) / max(x_rated - x_coil, 1e-6), 0.0, float(p.get("max_factor", 1.5)))
                rate = float(p.get("rated_kg_h", 0.4)) / 3600.0 * taper
                moisture = -rate
                heat = electric + rate * LATENT_HEAT
                gains.moisture_kg_s = moisture
                gains.conv_w = heat
            elif self.model == "humidifier":
                rate = float(p.get("rated_kg_h", 0.3)) / 3600.0 * clamp((100.0 - zone.rh) / 10.0, 0.0, 1.0)
                moisture = rate
                heat = electric - rate * LATENT_HEAT
                gains.moisture_kg_s = moisture
                gains.conv_w = heat
            else:  # room_fan
                heat = electric
                gains.conv_w = heat
        self.electric_w, self.heat_w, self.moisture_kg_s = electric, heat, moisture
        c = self.counters
        if self.running:
            c.run_s += dt
        if self.on and self.available:
            c.on_s += dt
        c.electric_j += electric * dt
        c.heat_j += heat * dt
        c.moisture_kg += moisture * dt
        return out

    # --- observation / persistence ---------------------------------------------------------

    def sample(self) -> dict[str, Any]:
        rec: dict[str, Any] = {
            "on": self.on,
            "running": self.running,
            "available": self.available,
            "electric_w": round(self.electric_w),
            "heat_w": round(self.heat_w),
            "moisture_g_h": round(self.moisture_kg_s * 3.6e6),
        }
        if self.speed_count:
            rec["pct"] = self.percentage
        if self.model in HYGROSTAT_MODELS:
            rec["target_rh"] = self.target_humidity
        return rec

    def snapshot(self) -> dict[str, Any]:
        return {
            "on": self.on,
            "percentage": self.percentage,
            "target_humidity": self.target_humidity,
            "running": self.running,
            "available": self.available,
            "off_since": self.off_since,
            "counters": self.counters.__dict__.copy(),
        }

    def restore(self, data: dict[str, Any]) -> None:
        for key in ("on", "percentage", "target_humidity", "running", "available", "off_since"):
            if key in data:
                setattr(self, key, data[key])
        self.counters = ApplianceCounters(**data.get("counters", {}))
