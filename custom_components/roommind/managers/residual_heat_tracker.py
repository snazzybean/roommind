"""Residual heat transition tracking for RoomMind."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..const import (
    MODE_COOLING,
    MODE_HEATING,
    MODE_IDLE,
    RESIDUAL_LEARN_MIN_EXPECTED_K,
    RESIDUAL_LEARN_MIN_MINUTES,
    RESIDUAL_LEARN_WINDOW_MINUTES,
    RESIDUAL_TAU_GRID,
    RESIDUAL_TAU_MIN_RISE_K,
)
from ..control.residual_heat import advance_rebound, compute_residual_heat
from ..control.thermal_model import RCModel


class ResidualHeatTracker:
    """Tracks heating on/off transitions and computes residual heat."""

    def __init__(self) -> None:
        self._off_since: dict[str, float] = {}
        self._off_power: dict[str, float] = {}
        self._on_since: dict[str, float] = {}

    def get_q_residual(
        self,
        area_id: str,
        system_type: str,
        previous_mode: str,
        scale: float = 1.0,
        tau_minutes: float | None = None,
    ) -> float:
        """Compute residual heat from previous cycle state."""
        if not system_type or area_id not in self._off_since or previous_mode == MODE_HEATING:
            return 0.0
        elapsed = (time.time() - self._off_since[area_id]) / 60.0
        heat_dur = self.last_run_minutes(area_id)
        last_pf = self._off_power.get(area_id, 1.0)
        return compute_residual_heat(elapsed, system_type, last_pf, heat_dur, scale, tau_minutes)

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
    system_type: str
    run_minutes: float
    run_power: float
    measured_excess: float = 0.0  # K the room rose beyond the model's idle drift
    # Per step: (minutes after the stop at its middle, K one unit of residual heat adds
    # over the step, K measured beyond the idle drift). The model is linear in the
    # residual heat, so any decay time's expected rise follows from these.
    steps: list[tuple[float, float, float]] = field(default_factory=list)

    def expected(self, tau: float | None) -> list[float]:
        """Cumulative rise (K) the afterglow at scale 1 and decay time *tau* predicts per step."""
        total, out = 0.0, []
        for mid, gain, _ in self.steps:
            total += gain * compute_residual_heat(mid, self.system_type, self.run_power, self.run_minutes, 1.0, tau)
            out.append(total)
        return out

    def fit_tau(self) -> float | None:
        """Decay time whose afterglow shape best matches the measured rise, None without a clear signal.

        The cumulative measured rise is fitted with each candidate's cumulative rise
        (least squares over the scale); the candidate with the smallest residual wins.
        """
        if self.measured_excess < RESIDUAL_TAU_MIN_RISE_K or len(self.steps) < 4:
            return None
        measured, total = [], 0.0
        for _, _, excess in self.steps:
            total += excess
            measured.append(total)
        best: tuple[float, float] | None = None
        for tau in RESIDUAL_TAU_GRID:
            unit = self.expected(tau)
            denom = sum(u * u for u in unit)
            if denom <= 0:
                continue
            scale = sum(m * u for m, u in zip(measured, unit, strict=True)) / denom
            if scale <= 0:
                continue
            sse = sum((m - scale * u) ** 2 for m, u in zip(measured, unit, strict=True))
            if best is None or sse < best[1]:
                best = (tau, sse)
        return best[0] if best is not None else None


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

    The scale sample is measured against the room's current decay time (``tau_minutes``,
    the profile's while none is learned). A full window also fits the decay time that
    best matches the shape of the rise; ``take_tau_sample`` hands it to the caller.
    """

    def __init__(self) -> None:
        self._obs: dict[str, _Observation] = {}
        self._tau_samples: dict[str, float] = {}

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
        tau_minutes: float | None = None,
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
                return self._sample(obs, tau_minutes)
            return None
        if mode != MODE_IDLE or minutes_since_stop > RESIDUAL_LEARN_WINDOW_MINUTES + dt_minutes:
            self._obs.pop(area_id, None)
            return None
        if obs is None:
            # Only start right after the stop; a later start would miss the bulk of the heat
            if minutes_since_stop <= 2 * dt_minutes:
                self._obs[area_id] = _Observation(
                    T_prev=current_temp, system_type=system_type, run_minutes=run_minutes, run_power=run_power
                )
            return None

        mid = max(0.0, minutes_since_stop - dt_minutes / 2)
        base = model.predict(obs.T_prev, T_outdoor, 0.0, dt_minutes, q_solar=q_solar, q_occupancy=q_occupancy)
        with_unit = model.predict(
            obs.T_prev, T_outdoor, 0.0, dt_minutes, q_solar=q_solar, q_occupancy=q_occupancy, q_residual=1.0
        )
        excess = current_temp - base
        obs.measured_excess += excess
        obs.steps.append((mid, with_unit - base, excess))
        obs.T_prev = current_temp
        if minutes_since_stop >= RESIDUAL_LEARN_WINDOW_MINUTES:
            self._obs.pop(area_id, None)
            sample = self._sample(obs, tau_minutes)
            # The shape only counts where the size does: a short run's rise is mostly not its own heat
            tau = obs.fit_tau() if sample is not None else None
            if tau is not None:
                self._tau_samples[area_id] = tau
            return sample
        return None

    def take_tau_sample(self, area_id: str) -> float | None:
        """The decay time the last full window fitted for *area_id*, once (None without one)."""
        return self._tau_samples.pop(area_id, None)

    @staticmethod
    def _sample(obs: _Observation, tau_minutes: float | None) -> float | None:
        expected = obs.expected(tau_minutes)
        if not expected or expected[-1] < RESIDUAL_LEARN_MIN_EXPECTED_K:
            return None
        return obs.measured_excess / expected[-1]

    def remove_room(self, area_id: str) -> None:
        """Drop the observation of a removed or reset room."""
        self._obs.pop(area_id, None)
        self._tau_samples.pop(area_id, None)

    def clear_all(self) -> None:
        """Drop all observations."""
        self._obs.clear()
        self._tau_samples.clear()


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
