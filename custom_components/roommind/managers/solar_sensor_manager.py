"""Per-room sun sensor: the solar input a room really gets (#303).

The weather model gives one irradiance for the whole house. A sensor at or in a room
measures what reaches it: orientation, a tree, the neighbour's roof, real clouds.

Scale: a calibration over the first two days with sun divides the reading by the ratio
sensor/model, so W/m² behind glass, lux and percent all end up "GHI-equivalent" and the
learned solar gain (beta_s) and the cover constants per unit GHI keep their meaning. Until
the calibration is done (it ends at night, so the input never jumps in daylight) the room
runs on the weather model exactly as without a sensor.

Forecasts keep the weather series as their shape. Each step is multiplied with a profile
learned per sun azimuth (orientation, local shade) and the current deviation from it
(clouds the forecast does not know), which fades back to the profile.

Covers: only samples with the covers open teach calibration, profile and deviation, so
RoomMind closing a cover never lowers its own sun forecast. Whether the sensor sits
behind the covers is told from shaded samples against the profile; until that is known a
shaded room uses the profile estimate times the shading factor (as without a sensor).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..const import (
    SOLAR_SENSOR_CALIBRATION_SUN_H,
    SOLAR_SENSOR_DEVIATION_FADE_H,
    SOLAR_SENSOR_DEVIATION_TAU_MIN,
    SOLAR_SENSOR_LEARN_MIN_Q,
    SOLAR_SENSOR_OPEN_SHADING,
    SOLAR_SENSOR_POSITION_MIN_SUN_H,
    SOLAR_SENSOR_PROFILE_BINS,
    SOLAR_SENSOR_PROFILE_TAU_H,
    SOLAR_SENSOR_RATIO_MAX,
    SOLAR_SENSOR_SHADED,
    SOLAR_SENSOR_STALE_S,
    SOLAR_SENSOR_USE_MIN_Q,
)
from ..control.solar import compute_q_solar_norm, solar_azimuth

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

KIND_IRRADIANCE = "irradiance"
KIND_ILLUMINANCE = "illuminance"
KIND_PERCENT = "percent"

POSITION_INSIDE = "inside"
POSITION_OUTSIDE = "outside"

# A cycle gap longer than this (restart, skipped room) counts as this much sample time
_MAX_SAMPLE_S = 120.0
# Profile bins with less sample time than this keep their prior
_MIN_BIN_H = 0.05
# Shaded samples only judge the position where the profile is learned and expects sun
_POSITION_MIN_BIN_H = 0.25
# A reading this far below the open-cover profile while shaded comes from behind the cover
_POSITION_INSIDE_BELOW = 0.85
# ... and one at least this close to the profile from in front of it; in between the call stays
_POSITION_OUTSIDE_ABOVE = 0.95
_POSITION_MIN_PROFILE = 0.2
# Old position evidence halves once there is this much, so a wrong early call can turn
_POSITION_MAX_SUN_H = 2.0
_PEAK_DAYS_KEPT = 3
# Share of the sun's path (azimuth bins with sun this season) the calibration must have seen with
# the covers open: a room shaded every afternoon would get a scale from the morning alone
_CALIBRATION_MIN_SHARE = 0.6
_CALIBRATION_MIN_BINS = 2
# Days with calibration samples: one day's cloud nowcast error would stay in the scale for good
_CALIBRATION_MIN_DAYS = 2
# A direction the sensor barely sees (diffuse light only) does not set the deviation for all others
_DEVIATION_MIN_PROFILE = 0.3


def solar_sensor_kind(state: Any) -> str | None:
    """What a sensor measures: irradiance (W/m²), illuminance (lx), percent, or None (not usable)."""
    if state is None:
        return None
    attrs = getattr(state, "attributes", {}) or {}
    device_class = attrs.get("device_class")
    unit = attrs.get("unit_of_measurement")
    if device_class == "irradiance" or unit == "W/m²":
        return KIND_IRRADIANCE
    if device_class == "illuminance" or unit == "lx":
        return KIND_ILLUMINANCE
    if unit == "%" and not device_class:
        return KIND_PERCENT
    return None


def _bin(azimuth: float) -> int:
    width = 360.0 / SOLAR_SENSOR_PROFILE_BINS
    return int((azimuth % 360.0) // width) % SOLAR_SENSOR_PROFILE_BINS


def _fade(dev: float, seconds: float) -> float:
    """Deviation from the profile, faded back towards 1 over *seconds*."""
    return 1.0 + (dev - 1.0) * math.exp(-max(0.0, seconds) / (SOLAR_SENSOR_DEVIATION_FADE_H * 3600.0))


@dataclass(frozen=True)
class RoomSolar:
    """Solar input of a room with an active sun sensor, on the weather model's scale (GHI/1000).

    ``q_now``: unshaded input now (what the room would get with open covers).
    ``q_effective``: what the room gets now, behind its covers; the thermal model learns from it.
    """

    q_now: float
    q_effective: float
    measured: bool
    latitude: float
    longitude: float
    now: float
    profile: tuple[float, ...]
    deviation: float

    def factors(self, start_ts: float, n_blocks: int, dt_minutes: float) -> list[float]:
        """Multipliers for a weather solar series starting at *start_ts* (profile x fading deviation)."""
        out: list[float] = []
        for i in range(n_blocks):
            ts = start_ts + i * dt_minutes * 60.0
            prof = self.profile[_bin(solar_azimuth(self.latitude, self.longitude, ts))]
            out.append(prof * _fade(self.deviation, ts - self.now))
        return out

    def scale(self, series: list[float], start_ts: float, dt_minutes: float) -> list[float]:
        """*series* (weather model, unshaded) as this room gets it."""
        return [q * f for q, f in zip(series, self.factors(start_ts, len(series), dt_minutes), strict=True)]


def _zeros() -> list[float]:
    return [0.0] * SOLAR_SENSOR_PROFILE_BINS


def _sun_day(now: float, lon: float) -> int:
    """Day number by local solar time: it changes at local midnight, never while the sun is up."""
    return int((now + lon / 15.0 * 3600.0) // 86400)


@dataclass
class _SensorState:
    entity_id: str
    kind: str | None
    scale: float | None = None
    cal_raw: list[float] = field(default_factory=_zeros)
    cal_model: list[float] = field(default_factory=_zeros)
    cal_hours: list[float] = field(default_factory=_zeros)
    cal_sun: list[float] = field(default_factory=_zeros)
    # [sun day (_sun_day), model sun-hours] per calibration day
    cal_days: list[list[float]] = field(default_factory=list)
    profile: list[float] = field(default_factory=lambda: [1.0] * SOLAR_SENSOR_PROFILE_BINS)
    weight: list[float] = field(default_factory=_zeros)
    position: str | None = None
    pos_sun: float = 0.0
    pos_ratio: float = 0.0
    pos_shading: float = 0.0
    peak: float = 0.0
    peak_days: list[int] = field(default_factory=list)
    deviation: float = 1.0
    deviation_ts: float | None = None
    last_ts: float | None = None
    status: str = "learning"


class SolarSensorManager:
    """Reads each room's sun sensor and turns it into the room's solar input."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._rooms: dict[str, _SensorState] = {}
        # dirty: save now (calibrated, new sensor, position); learned: save with the thermal data
        self.dirty = False
        self.learned = False

    # --- per cycle ---

    def update(
        self,
        area_id: str,
        entity_id: str,
        q_model: float,
        shading_factor: float,
        now: float,
    ) -> RoomSolar | None:
        """Solar input of the room this cycle; None while it runs on the weather model (no or new sensor)."""
        if not entity_id:
            if self._rooms.pop(area_id, None) is not None:
                self.dirty = True
            return None
        state = self.hass.states.get(entity_id)
        kind = solar_sensor_kind(state)
        st = self._rooms.get(area_id)
        if st is None or st.entity_id != entity_id or (kind is not None and st.kind not in (None, kind)):
            st = _SensorState(entity_id=entity_id, kind=kind)
            self._rooms[area_id] = st
            self.dirty = True
        elif st.kind is None and kind is not None:
            st.kind = kind
        dt_h = 0.0 if st.last_ts is None else max(0.0, min(now - st.last_ts, _MAX_SAMPLE_S)) / 3600.0
        st.last_ts = now

        raw = self._reading(state, kind, q_model, now)
        lat = self.hass.config.latitude
        lon = self.hass.config.longitude
        capped = raw is not None and self._at_cap(st, raw, _sun_day(now, lon))
        b = _bin(solar_azimuth(lat, lon, now))
        is_open = shading_factor >= SOLAR_SENSOR_OPEN_SHADING
        learn = raw is not None and not capped and is_open and q_model >= SOLAR_SENSOR_LEARN_MIN_Q

        if st.scale is None:
            # Unsupported only once the sensor shows a unit RoomMind cannot use, not while it has no state
            st.status = "unsupported" if kind is None and state is not None else "learning"
            if q_model >= SOLAR_SENSOR_LEARN_MIN_Q:
                st.cal_sun[b] += dt_h
            if learn and raw is not None:
                self.learned = True
                st.cal_raw[b] += raw * dt_h
                st.cal_model[b] += q_model * dt_h
                st.cal_hours[b] += dt_h
                day = _sun_day(now, lon)
                if st.cal_days and st.cal_days[-1][0] == day:
                    st.cal_days[-1][1] += q_model * dt_h
                else:
                    st.cal_days = [*st.cal_days, [day, q_model * dt_h]]
            if q_model < SOLAR_SENSOR_USE_MIN_Q:
                # Dusk, never full daylight: the input does not jump (and midnight sun still ends it)
                self._finish_calibration(area_id, st)
            return None

        st.status = "active" if raw is not None else "unavailable"
        # Clamped like the profile: a scale learned on diffuse light must not turn direct sun into many suns
        # Against clear sky, not the cloud forecast: sun the forecast did not expect is what the sensor is for
        m = None if raw is None else min(raw / st.scale, SOLAR_SENSOR_RATIO_MAX * compute_q_solar_norm(lat, lon, now))
        if learn and m is not None:
            self._learn(st, b, m / q_model, dt_h, now)
            self.learned = True
        elif m is not None and not capped and not is_open and q_model >= SOLAR_SENSOR_LEARN_MIN_Q:
            self._judge_position(st, b, m / q_model, shading_factor, q_model * dt_h)

        dev = _fade(st.deviation, now - st.deviation_ts) if st.deviation_ts is not None else 1.0
        fallback = q_model * st.profile[b] * dev if q_model > 0.0 else 0.0
        measured = m is not None and q_model >= SOLAR_SENSOR_USE_MIN_Q
        if q_model <= 0.0:
            # Night: whatever the sensor sees is lamp light
            q_now = q_eff = 0.0
        elif m is None or not measured:
            q_now, q_eff = fallback, fallback * shading_factor
        elif capped:
            # Saturated: the sun is at least this bright
            q_now = max(m, fallback)
            q_eff = q_now * shading_factor
        elif is_open:
            q_now = m
            q_eff = m if st.position == POSITION_INSIDE else m * shading_factor
        elif st.position == POSITION_INSIDE:
            q_now, q_eff = fallback, m
        elif st.position == POSITION_OUTSIDE:
            q_now, q_eff = m, m * shading_factor
        else:
            q_now, q_eff = fallback, fallback * shading_factor
            measured = False
        return RoomSolar(
            q_now=q_now,
            q_effective=q_eff,
            measured=measured and not capped,
            latitude=lat,
            longitude=lon,
            now=now,
            profile=tuple(st.profile),
            deviation=dev,
        )

    def _reading(self, state: Any, kind: str | None, q_model: float, now: float) -> float | None:
        """The sensor value, None when unusable: no state, unknown unit, not a number, or hanging in daylight."""
        if state is None or kind is None or state.state in ("unavailable", "unknown"):
            return None
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(value) or value < 0.0:
            return None
        reported = getattr(state, "last_reported", None) or getattr(state, "last_updated", None)
        if (
            reported is not None
            and q_model >= SOLAR_SENSOR_LEARN_MIN_Q
            and now - reported.timestamp() > SOLAR_SENSOR_STALE_S
        ):
            return None
        return value

    @staticmethod
    def _at_cap(st: _SensorState, raw: float, day: int) -> bool:
        """True when *raw* sits at the sensor's ceiling: its all-time maximum, reached on two days or more."""
        if raw <= 0.0:
            return False
        if raw > st.peak:
            st.peak = raw
            st.peak_days = [day]
            return False
        if raw == st.peak and day not in st.peak_days:
            st.peak_days = [*st.peak_days, day][-_PEAK_DAYS_KEPT:]
        return raw >= st.peak and len(st.peak_days) >= 2

    def _finish_calibration(self, area_id: str, st: _SensorState) -> None:
        """At night after enough sun: fix the scale and seed the profile from the calibration days."""
        model = sum(st.cal_model)
        raw = sum(st.cal_raw)
        # Each counted day brings a fair share of the sun, so one day's nowcast error is at most half the scale
        full_days = sum(1 for _, sun in st.cal_days if sun >= SOLAR_SENSOR_CALIBRATION_SUN_H / _CALIBRATION_MIN_DAYS)
        if model < SOLAR_SENSOR_CALIBRATION_SUN_H or raw <= 0.0 or full_days < _CALIBRATION_MIN_DAYS:
            return
        # Most of the sun's path seen: a room shaded every afternoon would get a scale from the morning alone
        seen = sum(1 for h in st.cal_hours if h >= _MIN_BIN_H)
        path = sum(1 for h in st.cal_sun if h >= _MIN_BIN_H)
        if seen < max(_CALIBRATION_MIN_BINS, math.ceil(_CALIBRATION_MIN_SHARE * path)):
            return
        st.scale = raw / model
        for b in range(SOLAR_SENSOR_PROFILE_BINS):
            if st.cal_hours[b] >= _MIN_BIN_H and st.cal_model[b] > 0.0:
                ratio = st.cal_raw[b] / st.cal_model[b] / st.scale
                st.profile[b] = max(0.0, min(SOLAR_SENSOR_RATIO_MAX, ratio))
                st.weight[b] = st.cal_hours[b]
        st.cal_raw, st.cal_model, st.cal_hours, st.cal_sun = _zeros(), _zeros(), _zeros(), _zeros()
        st.cal_days = []
        st.status = "active"
        self.dirty = True
        _LOGGER.info("Room '%s': sun sensor %s calibrated (scale %.4g)", area_id, st.entity_id, st.scale)

    @staticmethod
    def _learn(st: _SensorState, b: int, ratio: float, dt_h: float, now: float) -> None:
        """Covers open, sun up: update the profile bin and the current deviation."""
        ratio = max(0.0, min(SOLAR_SENSOR_RATIO_MAX, ratio))
        if dt_h > 0.0:
            st.weight[b] += dt_h
            # Running mean over the first hours of a bin, then an average over the last few
            st.profile[b] += (ratio - st.profile[b]) * dt_h / min(st.weight[b], SOLAR_SENSOR_PROFILE_TAU_H)
        prof = st.profile[b]
        if prof < _DEVIATION_MIN_PROFILE:
            return
        x = max(0.0, min(SOLAR_SENSOR_RATIO_MAX, ratio / prof))
        if st.deviation_ts is None:
            st.deviation = x
        else:
            prev = _fade(st.deviation, now - st.deviation_ts)
            k = 1.0 - math.exp(-max(0.0, now - st.deviation_ts) / (SOLAR_SENSOR_DEVIATION_TAU_MIN * 60.0))
            st.deviation = prev + (x - prev) * k
        st.deviation_ts = now

    def _judge_position(self, st: _SensorState, b: int, ratio: float, shading_factor: float, sun_h: float) -> None:
        """Covers down: a sensor behind them drops by about the shading factor, one outside does not."""
        if shading_factor > SOLAR_SENSOR_SHADED or sun_h <= 0.0:
            return
        if st.weight[b] < _POSITION_MIN_BIN_H or st.profile[b] < _POSITION_MIN_PROFILE:
            return
        x = min(3.0, ratio / st.profile[b])
        if st.pos_sun > _POSITION_MAX_SUN_H:
            st.pos_sun *= 0.5
            st.pos_ratio *= 0.5
            st.pos_shading *= 0.5
        st.pos_sun += sun_h
        self.learned = True
        st.pos_ratio += sun_h * x
        st.pos_shading += sun_h * shading_factor
        if st.pos_sun < SOLAR_SENSOR_POSITION_MIN_SUN_H:
            return
        mean_ratio = st.pos_ratio / st.pos_sun
        mean_shading = st.pos_shading / st.pos_sun
        # Behind the cover the reading drops; how far depends on the real cover (slats let light
        # through, the shading factor is only RoomMind's model), so any clear drop counts
        if mean_ratio < max((1.0 + mean_shading) / 2.0, _POSITION_INSIDE_BELOW):
            position = POSITION_INSIDE
        elif mean_ratio > _POSITION_OUTSIDE_ABOVE:
            position = POSITION_OUTSIDE
        else:
            return
        if position != st.position:
            st.position = position
            self.dirty = True

    # --- status, persistence ---

    def status(self, area_id: str) -> dict[str, Any] | None:
        """For the room page: what the sensor is (kind) and where it stands (learning/active/unavailable/unsupported)."""
        st = self._rooms.get(area_id)
        if st is None:
            return None
        return {"kind": st.kind, "state": st.status, "position": st.position}

    def prune(self, area_ids: set[str]) -> None:
        for area_id in [a for a in self._rooms if a not in area_ids]:
            del self._rooms[area_id]
            self.dirty = True

    def get_state(self) -> dict[str, dict[str, Any]]:
        return {
            area_id: {
                "entity_id": st.entity_id,
                "kind": st.kind,
                "scale": st.scale,
                "cal": [st.cal_raw, st.cal_model, st.cal_hours, st.cal_sun] if st.scale is None else None,
                "cal_days": st.cal_days if st.scale is None else [],
                "profile": [round(p, 4) for p in st.profile],
                "weight": [round(w, 3) for w in st.weight],
                "position": st.position,
                "pos": [st.pos_sun, st.pos_ratio, st.pos_shading],
                "peak": st.peak,
                "peak_days": st.peak_days,
            }
            for area_id, st in self._rooms.items()
        }

    def load_state(self, data: dict[str, Any]) -> None:
        self._rooms = {}
        n = SOLAR_SENSOR_PROFILE_BINS
        for area_id, d in (data or {}).items():
            try:
                st = _SensorState(entity_id=str(d["entity_id"]), kind=d.get("kind"))
                scale = d.get("scale")
                st.scale = float(scale) if scale is not None and float(scale) > 0.0 else None
                cal = d.get("cal")
                if st.scale is None and cal and len(cal) == 4 and all(len(c) == n for c in cal):
                    st.cal_raw, st.cal_model, st.cal_hours, st.cal_sun = ([float(v) for v in c] for c in cal)
                    st.cal_days = [[int(day), float(sun)] for day, sun in d.get("cal_days", [])]
                if len(d.get("profile") or []) == n and len(d.get("weight") or []) == n:
                    st.profile = [float(v) for v in d["profile"]]
                    st.weight = [float(v) for v in d["weight"]]
                st.position = d.get("position") if d.get("position") in (POSITION_INSIDE, POSITION_OUTSIDE) else None
                pos = d.get("pos") or [0.0, 0.0, 0.0]
                st.pos_sun, st.pos_ratio, st.pos_shading = (float(v) for v in pos)
                st.peak = float(d.get("peak", 0.0))
                st.peak_days = [int(v) for v in d.get("peak_days", [])]
                st.status = "active" if st.scale is not None else "learning"
            except (KeyError, TypeError, ValueError):
                _LOGGER.warning("Room '%s': stored sun sensor state unreadable, learning again", area_id)
                continue
            self._rooms[area_id] = st
        self.dirty = False
        self.learned = False
