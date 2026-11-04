"""Residual heat transition tracking for RoomMind."""

from __future__ import annotations

import time
from dataclasses import dataclass

from ..const import (
    MODE_COOLING,
    MODE_HEATING,
    MODE_IDLE,
    RESIDUAL_LEARN_MIN_EXPECTED_K,
    RESIDUAL_LEARN_MIN_MINUTES,
    RESIDUAL_LEARN_WINDOW_MINUTES,
)
from ..control.residual_heat import advance_rebound, compute_residual_heat
from ..control.thermal_model import RCModel


class ResidualHeatTracker:
    """Tracks heating on/off transitions and computes residual heat."""

    def __init__(self) -> None:
        self._off_since: dict[str, float] = {}
        self._off_power: dict[str, float] = {}
        self._on_since: dict[str, float] = {}

    def get_q_residual(self, area_id: str, system_type: str, previous_mode: str, scale: float = 1.0) -> float:
        """Compute residual heat from previous cycle state."""
        if not system_type or area_id not in self._off_since or previous_mode == MODE_HEATING:
            return 0.0
        elapsed = (time.time() - self._off_since[area_id]) / 60.0
        heat_dur = self.last_run_minutes(area_id)
        last_pf = self._off_power.get(area_id, 1.0)
        return compute_residual_heat(elapsed, system_type, last_pf, heat_dur, scale)

    def get_run_state(self, area_id: str, previous_mode: str) -> tuple[float, float] | None:
        """(minutes heated, power fraction) of the heating run in progress, None when not heating.

        What the controller needs to know which residual heat stopping now would leave.
        """
        if previous_mode != MODE_HEATING or area_id not in self._on_since:
            return None
        return (time.time() - self._on_since[area_id]) / 60.0, self._off_power.get(area_id, 1.0)

    def last_run_minutes(self, area_id: str) -> float:
        """Duration of the last finished heating run (0.0 when unknown)."""
        if area_id not in self._off_since:
            return 0.0
        return (self._off_since[area_id] - self._on_since.get(area_id, self._off_since[area_id])) / 60.0

    def last_run_power(self, area_id: str) -> float:
        """Power fraction of the last heating run."""
        return self._off_power.get(area_id, 1.0)

    def minutes_since_stop(self, area_id: str) -> float | None:
        """Minutes since the last heating run stopped, None while heating or without one."""
        if area_id not in self._off_since:
            return None
        return (time.time() - self._off_since[area_id]) / 60.0

    def update(
        self, area_id: str, mode: str, power_fraction: float, previous_mode: str, q_residual: float = 0.0
    ) -> None:
        """Update heating transition state based on current mode."""
        if mode == MODE_HEATING:
            self._off_since.pop(area_id, None)
            self._off_power[area_id] = power_fraction
            if previous_mode != MODE_HEATING:
                self._on_since[area_id] = time.time()
        elif previous_mode == MODE_HEATING:
            self._off_since[area_id] = time.time()
        elif (
            q_residual == 0.0
            and area_id in self._off_since
            and time.time() - self._off_since[area_id] >= RESIDUAL_LEARN_WINDOW_MINUTES * 60
        ):
            # Kept for the learning window even after the afterglow fell below the
            # cutoff: the ResidualHeatLearner still needs the run that caused it.
            self._off_since.pop(area_id, None)
            self._off_power.pop(area_id, None)
            self._on_since.pop(area_id, None)

    def remove_room(self, area_id: str) -> None:
        """Clean up state for a removed room."""
        self._off_since.pop(area_id, None)
        self._off_power.pop(area_id, None)
        self._on_since.pop(area_id, None)

    def clear_room(self, area_id: str) -> None:
        """Clear state for a room (thermal reset)."""
        self.remove_room(area_id)

    def clear_all(self) -> None:
        """Clear state for all rooms."""
        self._off_since.clear()
        self._off_power.clear()
        self._on_since.clear()


@dataclass
class _Observation:
    """One afterglow under observation (see ResidualHeatLearner)."""

    T_prev: float
    measured_excess: float = 0.0  # K the room rose beyond the model's idle drift
    expected_unit: float = 0.0  # K the profile (scale 1) predicts for the same steps


class ResidualHeatLearner:
    """Learns how much residual heat a room's heating system really releases.

    The heating system profiles are a fixed guess per system type, while a radiator's
    stored heat depends on its size, water temperature and how fast its TRV closes.
    After each heating run the room is watched: every cycle, the measured change is
    compared with the learned model's idle prediction without residual heat (outdoor,
    sun and occupancy included), and with the change the profile at scale 1 predicts.
    At the end of the window the ratio of the two sums is one sample of the room's
    residual scale. Summing per-step differences telescopes the measurements to
    ``T_end - T_start``, so sensor resolution only enters at the two ends.

    A window that opens, a heating run that restarts early, a cooling run or a missing
    reading ends the observation; a run that restarts after ``RESIDUAL_LEARN_MIN_MINUTES``
    still gives a sample.
    """

    def __init__(self) -> None:
        self._obs: dict[str, _Observation] = {}

    def step(
        self,
        area_id: str,
        *,
        model: RCModel,
        system_type: str,
        mode: str,
        current_temp: float | None,
        T_outdoor: float | None,
        dt_minutes: float,
        minutes_since_stop: float | None,
        run_minutes: float,
        run_power: float,
        q_solar: float,
        q_occupancy: float,
        disturbed: bool,
    ) -> float | None:
        """Advance one cycle. Returns a residual scale sample when an observation completes."""
        obs = self._obs.get(area_id)
        if (
            not system_type
            or minutes_since_stop is None
            or current_temp is None
            or T_outdoor is None
            or disturbed
            or mode == MODE_COOLING
        ):
            self._obs.pop(area_id, None)
            return None
        if mode == MODE_HEATING:
            # Restarted: what was seen so far still counts if it was long enough
            self._obs.pop(area_id, None)
            if obs is not None and minutes_since_stop >= RESIDUAL_LEARN_MIN_MINUTES:
                return self._sample(obs)
            return None
        if mode != MODE_IDLE or minutes_since_stop > RESIDUAL_LEARN_WINDOW_MINUTES + dt_minutes:
            self._obs.pop(area_id, None)
            return None
        if obs is None:
            # Only start right after the stop; a later start would miss the bulk of the heat
            if minutes_since_stop <= 2 * dt_minutes:
                self._obs[area_id] = _Observation(T_prev=current_temp)
            return None

        mid = max(0.0, minutes_since_stop - dt_minutes / 2)
        q_unit = compute_residual_heat(mid, system_type, run_power, run_minutes)
        base = model.predict(obs.T_prev, T_outdoor, 0.0, dt_minutes, q_solar=q_solar, q_occupancy=q_occupancy)
        with_unit = model.predict(
            obs.T_prev, T_outdoor, 0.0, dt_minutes, q_solar=q_solar, q_occupancy=q_occupancy, q_residual=q_unit
        )
        obs.measured_excess += current_temp - base
        obs.expected_unit += with_unit - base
        obs.T_prev = current_temp
        if minutes_since_stop >= RESIDUAL_LEARN_WINDOW_MINUTES:
            self._obs.pop(area_id, None)
            return self._sample(obs)
        return None

    @staticmethod
    def _sample(obs: _Observation) -> float | None:
        if obs.expected_unit < RESIDUAL_LEARN_MIN_EXPECTED_K:
            return None
        return obs.measured_excess / obs.expected_unit

    def remove_room(self, area_id: str) -> None:
        """Drop the observation of a removed or reset room."""
        self._obs.pop(area_id, None)

    def clear_all(self) -> None:
        """Drop all observations."""
        self._obs.clear()


class AcReboundTracker:
    """Tracks the AC rebound charge per room (air pulled below the building mass).

    Driven by the mode the EKF trains with, so the charge always matches the
    labels the model learns from.
    """

    def __init__(self) -> None:
        self._charge: dict[str, float] = {}
        self._cooling: dict[str, bool] = {}
        self._at: dict[str, float] = {}

    def get_charge(self, area_id: str) -> float:
        """Current charge, advanced to now with the last recorded mode."""
        if area_id not in self._at:
            return 0.0
        elapsed = (time.time() - self._at[area_id]) / 60.0
        return advance_rebound(self._charge[area_id], 1.0 if self._cooling[area_id] else 0.0, elapsed)

    def update(self, area_id: str, mode: str | None) -> None:
        """Record the mode from now on (None: unknown, treated as not cooling)."""
        charge = self.get_charge(area_id)
        cooling = mode == MODE_COOLING
        if charge <= 0.0 and not cooling:
            self.remove_room(area_id)
            return
        self._charge[area_id] = charge
        self._cooling[area_id] = cooling
        self._at[area_id] = time.time()

    def seed_running(self, area_id: str) -> None:
        """Start fully charged: a cooling run already in progress (after a restart)."""
        self._charge[area_id] = 1.0
        self._cooling[area_id] = True
        self._at[area_id] = time.time()

    def remove_room(self, area_id: str) -> None:
        """Clean up state for a removed room."""
        self._charge.pop(area_id, None)
        self._cooling.pop(area_id, None)
        self._at.pop(area_id, None)

    def clear_all(self) -> None:
        """Clear state for all rooms."""
        self._charge.clear()
        self._cooling.clear()
        self._at.clear()
