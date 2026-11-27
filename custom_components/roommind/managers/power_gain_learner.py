"""Heat of the devices on a room's power sensors, learned per sensor outside the thermal model.

A power reading does not say how much of it ends up as heat in the room: a PC or a server
turns all of it into room heat, a dishwasher sends most of it down the drain, an oven gives
it off much later. So each sensor gets its own gain [degC/h per kW], and a sensor only
counts once it measurably improves the room's prediction; otherwise it shows "no effect"
and is ignored.

The gain is learned from each sensor's deviation from its usual load (a slow average),
from the model's own prediction errors over idle windows: for each window the residual of
the model without the devices is regressed on the deviations of all sensors at once
(recursive least squares, with a constant term for what the model misses anyway), so two
plugs switching together do not take each other's heat. A constant load such as a fridge
sits on its usual load, never excites the learner and is never used: it stays in the
thermal model as without a sensor, so it cannot keep the heating rate from learning.

A sensor in use adds its full heat, gain x power, to the model as a known input, so the
model no longer books its device's heat on the room's own parameters.

Rooms without power sensors have no state here, and nothing about the devices is stored
with the room's thermal model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from ..const import MODE_IDLE
from ..control.thermal_model import RCModel

# Length of a learning window and the usual-load average
POWER_LEARN_WINDOW_MINUTES = 30.0
POWER_BASELINE_TAU_H = 48.0
# A sensor is excited in a window only this far off its usual load
POWER_MIN_DEVIATION_KW = 0.05
# Gain prior and residual noise of a window
_GAIN_INIT_VAR = 4.0  # (degC/h per kW)^2
_BIAS_INIT_VAR = 1.0  # (degC/h)^2
_WINDOW_NOISE_VAR = 0.01  # (0.1 K)^2
# RLS forgetting per window and decay of the scores
_FORGET = 0.999
_SCORE_DECAY = 0.98
# A sensor is used once enough excited windows show a clear positive gain that cuts the error
POWER_ACTIVE_MIN_WINDOWS = 40
POWER_ACTIVE_MIN_Z = 3.0
POWER_ACTIVE_MIN_IMPROVEMENT = 0.10
POWER_DROP_IMPROVEMENT = 0.03
# Without that after this many windows, or never off its usual load for a week: no effect
POWER_NO_EFFECT_WINDOWS = 80
POWER_CONSTANT_DAYS = 7.0

STATUS_LEARNING = "learning"
# Key of the constant term while the terms are matched to the configured sensors
_BIAS = "\0bias"
STATUS_ACTIVE = "active"
STATUS_NO_EFFECT = "no_effect"


@dataclass
class _Sensor:
    """What is known about one power sensor of a room."""

    baseline_kw: float | None = None
    n: int = 0
    sse_with: float = 0.0
    sse_without: float = 0.0
    active: bool = False
    # Time-weighted mean square deviation from the usual load, and the hours seen
    dev_sq: float = 0.0
    hours: float = 0.0

    def improvement(self) -> float:
        """Share of the prediction error this sensor's gain removes (scored before learning)."""
        if self.sse_without <= 0:
            return 0.0
        return 1.0 - self.sse_with / self.sse_without

    def constant(self) -> bool:
        return self.hours >= POWER_CONSTANT_DAYS * 24 and math.sqrt(self.dev_sq) < POWER_MIN_DEVIATION_KW


@dataclass
class _Window:
    """Idle stretch being accumulated for one learning step."""

    T_start: float
    minutes: float = 0.0
    t_out: float = 0.0
    q_solar: float = 0.0
    q_occupancy: float = 0.0
    q_residual: float = 0.0
    deviation: list[float] = field(default_factory=list)


@dataclass
class _Room:
    sensors: list[str] = field(default_factory=list)
    # One gain per sensor, then the constant term [degC/h]; P covers both
    gain: list[float] = field(default_factory=lambda: [0.0])
    P: list[list[float]] = field(default_factory=lambda: [[_BIAS_INIT_VAR]])
    state: dict[str, _Sensor] = field(default_factory=dict)
    # Reading and deviation from the usual load of each sensor this cycle [kW], None without a reading
    reading: dict[str, float | None] = field(default_factory=dict)
    now: dict[str, float | None] = field(default_factory=dict)
    window: _Window | None = None


class PowerGainLearner:
    """Learns per sensor how much a room's metered devices warm it, and whether that helps."""

    def __init__(self) -> None:
        self._rooms: dict[str, _Room] = {}

    # --- per cycle ---------------------------------------------------------------------

    def begin_cycle(self, area_id: str, sensors: list[str], readings: dict[str, float], dt_minutes: float) -> float:
        """Update the usual loads and return the devices' heat now [degC/h] (active sensors only).

        *readings* holds the sensors with a reading [kW]. A room without sensors has no state.
        """
        if not sensors:
            self._rooms.pop(area_id, None)
            return 0.0
        room = self._sync(area_id, sensors)
        k = 1.0 - math.exp(-max(dt_minutes, 0.0) / 60.0 / POWER_BASELINE_TAU_H)
        room.now = {}
        room.reading = {}
        for eid in room.sensors:
            st = room.state[eid]
            reading = readings.get(eid)
            room.reading[eid] = reading
            if reading is None:
                room.now[eid] = None
                continue
            if st.baseline_kw is None:
                st.baseline_kw = reading
            x = reading - st.baseline_kw
            st.baseline_kw += (reading - st.baseline_kw) * k
            h = dt_minutes / 60.0
            st.dev_sq = (st.dev_sq * st.hours + x * x * h) / (st.hours + h) if st.hours + h > 0 else 0.0
            st.hours = min(st.hours + h, 10 * POWER_CONSTANT_DAYS * 24)
            room.now[eid] = x
        return self.device_heat(area_id)

    def device_heat(self, area_id: str) -> float:
        """Heat the sensors in use add to the room this cycle [degC/h]: gain x power."""
        room = self._rooms.get(area_id)
        if room is None:
            return 0.0
        total = 0.0
        for i, eid in enumerate(room.sensors):
            reading = room.reading.get(eid)
            if reading is not None and room.state[eid].active:
                total += max(room.gain[i], 0.0) * reading
        return total

    def observe(
        self,
        area_id: str,
        *,
        model: RCModel,
        mode: str | None,
        disturbed: bool,
        current_temp: float | None,
        T_outdoor: float | None,
        dt_minutes: float,
        q_solar: float = 0.0,
        q_occupancy: float = 0.0,
        q_residual: float = 0.0,
    ) -> None:
        """Feed one cycle; an idle window of POWER_LEARN_WINDOW_MINUTES teaches the gains.

        Only idle, undisturbed cycles with a reading of every sensor count: heating
        windows are dominated by how far the emitter's output differs from the model.
        """
        room = self._rooms.get(area_id)
        if room is None:
            return
        usable = (
            mode == MODE_IDLE
            and not disturbed
            and current_temp is not None
            and T_outdoor is not None
            and dt_minutes > 0
            and all(room.now.get(eid) is not None for eid in room.sensors)
        )
        if not usable or current_temp is None or T_outdoor is None:
            room.window = None
            return
        win = room.window
        if win is None:
            room.window = _Window(T_start=current_temp, deviation=[0.0] * len(room.sensors))
            return
        w = dt_minutes
        total = win.minutes + w
        win.t_out = (win.t_out * win.minutes + T_outdoor * w) / total
        win.q_solar = (win.q_solar * win.minutes + q_solar * w) / total
        win.q_occupancy = (win.q_occupancy * win.minutes + q_occupancy * w) / total
        win.q_residual = (win.q_residual * win.minutes + q_residual * w) / total
        win.deviation = [
            (d * win.minutes + (room.now[eid] or 0.0) * w) / total
            for d, eid in zip(win.deviation, room.sensors, strict=True)
        ]
        win.minutes = total
        if win.minutes >= POWER_LEARN_WINDOW_MINUTES:
            self._learn(room, win, model, current_temp)
            room.window = _Window(T_start=current_temp, deviation=[0.0] * len(room.sensors))

    def interrupt(self, area_id: str) -> None:
        """A cycle the model does not learn from (paused learning, device hold): the window starts over."""
        room = self._rooms.get(area_id)
        if room is not None:
            room.window = None

    # --- learning ----------------------------------------------------------------------

    def _learn(self, room: _Room, win: _Window, model: RCModel, T_end: float) -> None:
        inputs = {"q_solar": win.q_solar, "q_occupancy": win.q_occupancy, "q_residual": win.q_residual}
        base = model.predict(win.T_start, win.t_out, 0.0, win.minutes, **inputs)
        per_unit = model.predict(win.T_start, win.t_out, 0.0, win.minutes, u_device=1.0, **inputs) - base
        residual = T_end - base
        excited = [abs(d) >= POWER_MIN_DEVIATION_KW for d in win.deviation]
        if not any(excited) or per_unit <= 0:
            return
        # Regressors: each sensor's deviation, then the constant term
        z = [d * per_unit for d in win.deviation] + [per_unit]
        n = len(z)
        predicted = sum(room.gain[i] * z[i] for i in range(n))
        # Score before learning: the window with every term, and without each sensor's own
        for i, eid in enumerate(room.sensors):
            if not excited[i]:
                continue
            st = room.state[eid]
            st.sse_with = st.sse_with * _SCORE_DECAY + (residual - predicted) ** 2
            st.sse_without = st.sse_without * _SCORE_DECAY + (residual - predicted + room.gain[i] * z[i]) ** 2
            st.n += 1
        # Recursive least squares over all sensors at once
        Pz = [sum(room.P[i][j] * z[j] for j in range(n)) for i in range(n)]
        s = _WINDOW_NOISE_VAR + sum(z[i] * Pz[i] for i in range(n))
        gain_k = [p / s for p in Pz]
        err = residual - predicted
        room.gain = [room.gain[i] + gain_k[i] * err for i in range(n)]
        room.P = [[(room.P[i][j] - gain_k[i] * Pz[j]) / _FORGET for j in range(n)] for i in range(n)]
        for i, eid in enumerate(room.sensors):
            self._update_status(room, i, room.state[eid])

    def _update_status(self, room: _Room, i: int, st: _Sensor) -> None:
        gain = room.gain[i]
        std = math.sqrt(max(room.P[i][i], 1e-12))
        if st.active:
            if st.improvement() < POWER_DROP_IMPROVEMENT or gain <= 0:
                st.active = False
        elif (
            st.n >= POWER_ACTIVE_MIN_WINDOWS
            and gain > 0
            and gain / std >= POWER_ACTIVE_MIN_Z
            and st.improvement() >= POWER_ACTIVE_MIN_IMPROVEMENT
            and not st.constant()
        ):
            st.active = True

    def _sync(self, area_id: str, sensors: list[str]) -> _Room:
        """Keep the room's state to its configured sensors (a removed one is forgotten)."""
        room = self._rooms.setdefault(area_id, _Room())
        if room.sensors == sensors:
            return room
        bias = len(room.sensors)
        keep: dict[str, int] = {eid: i for i, eid in enumerate(room.sensors)}
        keep[_BIAS] = bias
        order = list(dict.fromkeys(sensors))
        terms = [*order, _BIAS]
        init = {_BIAS: _BIAS_INIT_VAR}
        gain: list[float] = []
        P: list[list[float]] = []
        for a in terms:
            gain.append(room.gain[keep[a]] if a in keep else 0.0)
            row = []
            for b in terms:
                if a in keep and b in keep:
                    row.append(room.P[keep[a]][keep[b]])
                else:
                    row.append(init.get(a, _GAIN_INIT_VAR) if a == b else 0.0)
            P.append(row)
        room.sensors, room.gain, room.P = order, gain, P
        room.state = {eid: room.state.get(eid) or _Sensor() for eid in order}
        room.window = None
        return room

    # --- state -------------------------------------------------------------------------

    def status(self, area_id: str, entity_id: str) -> str:
        room = self._rooms.get(area_id)
        st = room.state.get(entity_id) if room else None
        if st is None:
            return STATUS_LEARNING
        if st.active:
            return STATUS_ACTIVE
        if st.constant() or st.n >= POWER_NO_EFFECT_WINDOWS:
            return STATUS_NO_EFFECT
        return STATUS_LEARNING

    def info(self, area_id: str) -> list[dict[str, Any]]:
        """Per sensor: status, gain, its uncertainty, error it removes, windows, usual load, heat now."""
        room = self._rooms.get(area_id)
        if room is None:
            return []
        out = []
        for i, eid in enumerate(room.sensors):
            st = room.state[eid]
            reading = room.reading.get(eid)
            active = st.active
            out.append(
                {
                    "entity_id": eid,
                    "status": self.status(area_id, eid),
                    "gain": round(room.gain[i], 3),
                    "gain_std": round(math.sqrt(max(room.P[i][i], 0.0)), 3),
                    "improvement": round(st.improvement(), 3),
                    "windows": st.n,
                    "windows_needed": POWER_ACTIVE_MIN_WINDOWS,
                    "baseline_kw": round(st.baseline_kw, 3) if st.baseline_kw is not None else None,
                    "power_kw": round(reading, 3) if reading is not None else None,
                    "heat_now": round(max(room.gain[i], 0.0) * reading, 3) if active and reading is not None else 0.0,
                }
            )
        return out

    def reset(self, area_id: str) -> None:
        """Forget what was learned for a room (its thermal model was reset)."""
        self._rooms.pop(area_id, None)

    def remove_room(self, area_id: str) -> None:
        self._rooms.pop(area_id, None)

    def to_dict(self) -> dict[str, Any]:
        """Persisted state, only for rooms with power sensors."""
        return {
            area_id: {
                "sensors": list(room.sensors),
                "gain": list(room.gain),
                "P": [list(row) for row in room.P],
                "state": {
                    eid: {
                        "baseline_kw": st.baseline_kw,
                        "n": st.n,
                        "sse_with": st.sse_with,
                        "sse_without": st.sse_without,
                        "active": st.active,
                        "dev_sq": st.dev_sq,
                        "hours": st.hours,
                    }
                    for eid, st in room.state.items()
                },
            }
            for area_id, room in self._rooms.items()
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PowerGainLearner:
        """Restore; a malformed room starts over instead of failing the load."""
        learner = cls()
        if not isinstance(data, dict):
            return learner
        for area_id, raw in data.items():
            try:
                sensors = [str(e) for e in raw["sensors"]]
                n = len(sensors) + 1  # the gains and the constant term
                gain = [float(g) for g in raw["gain"]]
                P = [[float(v) for v in row] for row in raw["P"]]
                if len(gain) != n or len(P) != n or any(len(row) != n for row in P):
                    continue
                state = {}
                for eid in sensors:
                    s = raw["state"][eid]
                    state[eid] = _Sensor(
                        baseline_kw=None if s.get("baseline_kw") is None else float(s["baseline_kw"]),
                        n=int(s.get("n", 0)),
                        sse_with=float(s.get("sse_with", 0.0)),
                        sse_without=float(s.get("sse_without", 0.0)),
                        active=bool(s.get("active", False)),
                        dev_sq=float(s.get("dev_sq", 0.0)),
                        hours=float(s.get("hours", 0.0)),
                    )
            except (KeyError, TypeError, ValueError, AttributeError):
                continue
            learner._rooms[area_id] = _Room(sensors=sensors, gain=gain, P=P, state=state)
        return learner
