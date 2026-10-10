"""Two-node room model: air (+ furniture) and building mass, plus moisture balance.

    C_air  dTa/dt = H_ao (To - Ta) + H_vent (To - Ta) + H_am (Tm - Ta) + Q_conv + Σ H_ij (Tj - Ta)
    C_mass dTm/dt = H_mo (To - Tm) + H_am (Ta - Tm) + Q_rad

Emitter nodes (radiator water, screed slab) belong to the devices and hand their
convective/radiant shares to this model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .psychro import AIR_DENSITY, CP_AIR, abs_humidity, rel_humidity

INFILTRATION_W_PER_M3_ACH = AIR_DENSITY * CP_AIR / 3600.0  # ≈ 0.335 W/K per m³ at 1 ach
MAX_SUBSTEP_S = 10.0


@dataclass
class ZoneParams:
    floor_area_m2: float
    volume_m3: float
    c_air: float  # J/K
    c_mass: float  # J/K
    h_air_mass: float  # W/K
    h_air_out: float  # W/K windows + infiltration (closed)
    h_mass_out: float  # W/K opaque envelope through the mass
    window_open_w_k_per_m2: float
    window_area_m2: float
    base_internal_w: float
    moisture_buffer: float  # effective moisture capacity as a multiple of the air mass
    infiltration_kg_s: float
    base_moisture_kg_s: float = 0.0  # background moisture load (cooking, plants, drying laundry)

    @classmethod
    def from_thermal(cls, thermal: dict[str, Any], window_area_m2: float) -> ZoneParams:
        area = float(thermal.get("floor_area_m2", 20.0))
        height = float(thermal.get("height_m", 2.5))
        volume = area * height
        ach = float(thermal.get("ach_infiltration", 0.5))
        wall = float(thermal.get("exterior_wall_m2", 12.0))
        return cls(
            floor_area_m2=area,
            volume_m3=volume,
            c_air=volume * AIR_DENSITY * CP_AIR * float(thermal.get("air_capacity_factor", 4.0)),
            c_mass=float(thermal.get("mass_kj_per_m2", 165.0)) * 1000.0 * area,
            h_air_mass=float(thermal.get("h_air_mass_w_per_m2", 25.0)) * area,
            h_air_out=float(thermal.get("u_window", 1.3)) * window_area_m2 + ach * volume * INFILTRATION_W_PER_M3_ACH,
            h_mass_out=float(thermal.get("u_wall", 0.6)) * max(0.0, wall - window_area_m2),
            window_open_w_k_per_m2=float(thermal.get("window_open_w_k_per_m2", 50.0)),
            window_area_m2=window_area_m2,
            base_internal_w=float(thermal.get("base_internal_w_per_m2", 2.0)) * area,
            moisture_buffer=float(thermal.get("moisture_buffer", 4.0)),
            infiltration_kg_s=ach * volume * AIR_DENSITY / 3600.0,
            base_moisture_kg_s=float(thermal.get("base_moisture_g_h_per_m2", 3.0)) * area / 3.6e6,
        )

    def equivalent_first_order(self) -> dict[str, float]:
        """Lumped one-node view (what a first-order RC model should converge to).

        ``alpha_per_h`` = total UA / total capacity in 1/h; ``tau_h`` its inverse.
        """
        ua = self.h_air_out + self.h_mass_out
        cap = self.c_air + self.c_mass
        alpha = ua / cap * 3600.0
        return {"ua_w_k": ua, "capacity_j_k": cap, "alpha_per_h": alpha, "tau_h": 1 / alpha if alpha else 0.0}


@dataclass
class Gains:
    conv_w: float = 0.0  # to the air node
    rad_w: float = 0.0  # to the mass node
    moisture_kg_s: float = 0.0  # + adds water vapour, - removes (condensate)
    vent_w_k: float = 0.0  # extra air exchange (open windows), W/K

    def add(self, other: Gains) -> None:
        self.conv_w += other.conv_w
        self.rad_w += other.rad_w
        self.moisture_kg_s += other.moisture_kg_s
        self.vent_w_k += other.vent_w_k


@dataclass
class Zone:
    area_id: str
    params: ZoneParams
    t_air: float = 20.0
    t_mass: float = 20.0
    x: float = 0.007  # humidity ratio kg/kg
    last_gains: Gains = field(default_factory=Gains)

    @property
    def rh(self) -> float:
        return rel_humidity(self.t_air, self.x)

    def set_initial(self, temp_c: float, rh: float = 50.0, mass_temp_c: float | None = None) -> None:
        self.t_air = temp_c
        self.t_mass = temp_c if mass_temp_c is None else mass_temp_c
        self.x = abs_humidity(temp_c, rh)

    def step(self, dt: float, t_out: float, x_out: float, gains: Gains, neighbor_w: float = 0.0) -> None:
        """Advance by ``dt`` seconds. ``neighbor_w`` is the net heat flow from adjacent rooms."""
        p = self.params
        self.last_gains = gains
        n = max(1, int(dt / MAX_SUBSTEP_S + 0.999))
        h = dt / n
        vent_kg_s = gains.vent_w_k / CP_AIR
        air_kg = p.volume_m3 * AIR_DENSITY * p.moisture_buffer
        internal_conv = p.base_internal_w * 0.6
        internal_rad = p.base_internal_w * 0.4
        for _ in range(n):
            q_air = (
                (p.h_air_out + gains.vent_w_k) * (t_out - self.t_air)
                + p.h_air_mass * (self.t_mass - self.t_air)
                + gains.conv_w
                + internal_conv
                + neighbor_w
            )
            q_mass = (
                p.h_mass_out * (t_out - self.t_mass)
                + p.h_air_mass * (self.t_air - self.t_mass)
                + gains.rad_w
                + internal_rad
            )
            self.t_air += h * q_air / p.c_air
            self.t_mass += h * q_mass / p.c_mass
            dx = (
                (p.infiltration_kg_s + vent_kg_s) * (x_out - self.x) + gains.moisture_kg_s + p.base_moisture_kg_s
            ) / air_kg
            self.x = max(0.0, self.x + h * dx)

    def snapshot(self) -> dict[str, float]:
        return {"t_air": self.t_air, "t_mass": self.t_mass, "x": self.x}

    def restore(self, data: dict[str, float]) -> None:
        self.t_air = data["t_air"]
        self.t_mass = data["t_mass"]
        self.x = data["x"]
