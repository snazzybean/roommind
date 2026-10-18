"""EKF training accumulation and batching for RoomMind."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..const import EKF_UPDATE_MIN_DT

if TYPE_CHECKING:
    from ..control.thermal_model import RoomModelManager

_LOGGER = logging.getLogger(__name__)


class EkfTrainingManager:
    """Manages EKF training accumulation and batched updates per room."""

    def __init__(self, model_manager: RoomModelManager) -> None:
        self._model_manager = model_manager
        self._accumulated_dt: dict[str, float] = {}
        self._accumulated_mode: dict[str, str] = {}
        self._accumulated_pf: dict[str, float] = {}
        # dt-weighted mean AC rebound charge of the batch: it decays within minutes,
        # so the value at flush time would understate the batch.
        self._accumulated_rebound: dict[str, float] = {}
        # Rooms whose model temperature follows the measurement. After a restart or
        # skipped cycles it is stale, and learning the jump to the current reading as
        # one cycle's change dragged the model off (#478).
        self._synced: set[str] = set()
        # Rooms whose model temperature is current right now (no skipped cycle since the
        # last observation); k_window may only learn from those.
        self._current: set[str] = set()
        # dt-weighted mean power of the metered devices (kW): it changes from tick to tick
        self._accumulated_power: dict[str, float] = {}
        self.last_temps: dict[str, float] = {}

    def set_model_manager(self, model_manager: RoomModelManager) -> None:
        """Update the model manager reference (used after full thermal reset)."""
        self._model_manager = model_manager

    def flush(
        self,
        area_id: str,
        current_temp: float,
        T_outdoor: float,
        can_heat: bool,
        can_cool: bool,
        q_solar: float,
        q_residual: float = 0.0,
        shading_factor: float = 1.0,
        q_occupancy: float = 0.0,
    ) -> None:
        """Flush accumulated EKF update (on mode change or window open)."""
        accumulated = self._accumulated_dt.pop(area_id, 0.0)
        prev_mode = self._accumulated_mode.pop(area_id, None)
        pf = self._accumulated_pf.pop(area_id, 1.0)
        q_rebound = self._accumulated_rebound.pop(area_id, None)
        q_power = self._accumulated_power.pop(area_id, 0.0)
        if accumulated > 0 and prev_mode is not None:
            self._model_manager.update(
                area_id,
                current_temp,
                T_outdoor,
                prev_mode,
                accumulated,
                can_heat=can_heat,
                can_cool=can_cool,
                power_fraction=pf,
                q_solar=q_solar * shading_factor,
                q_residual=q_residual,
                q_occupancy=q_occupancy,
                q_rebound=q_rebound,
                q_power=q_power,
            )

    def process(
        self,
        area_id: str,
        current_temp: float,
        T_outdoor: float,
        ekf_mode: str | None,
        ekf_pf: float,
        window_open: bool,
        raw_open: bool,
        q_residual: float,
        shading_factor: float,
        q_solar: float,
        can_heat: bool,
        can_cool: bool,
        dt_minutes: float,
        q_occupancy: float = 0.0,
        q_rebound: float | None = None,
        q_power: float = 0.0,
    ) -> None:
        """Process an EKF training step for a room.

        Contains the full training decision tree: window open, raw open
        (within delay), unobservable mode, or normal accumulation.
        """
        if window_open or raw_open:
            was_current = area_id in self._current
            self.flush(
                area_id,
                current_temp,
                T_outdoor,
                can_heat,
                can_cool,
                q_solar,
                q_residual=q_residual,
                shading_factor=shading_factor,
                q_occupancy=q_occupancy,
            )
            self.clear(area_id)
            # Always track temperature state to prevent stale _x[0]
            # when normal learning resumes.  Only learn k_window when
            # the signal is clean (no residual heat) and _x[0] is current.
            self._model_manager.update_window_open(
                area_id,
                current_temp,
                T_outdoor,
                dt_minutes,
                learn_k_window=(window_open and q_residual == 0.0 and was_current),
            )
            self._synced.add(area_id)
            self._current.add(area_id)
        elif ekf_mode is None:
            self.flush(
                area_id,
                current_temp,
                T_outdoor,
                can_heat,
                can_cool,
                q_solar,
                q_residual=q_residual,
                shading_factor=shading_factor,
                q_occupancy=q_occupancy,
            )
            self.clear(area_id)
        elif area_id not in self._synced:
            self._model_manager.sync_temperature(area_id, current_temp)
            self._synced.add(area_id)
            self._current.add(area_id)
        else:
            self._current.add(area_id)
            prev_mode = self._accumulated_mode.get(area_id)
            if prev_mode is not None and prev_mode != ekf_mode:
                self.flush(
                    area_id,
                    current_temp,
                    T_outdoor,
                    can_heat,
                    can_cool,
                    q_solar,
                    q_residual=q_residual,
                    shading_factor=shading_factor,
                    q_occupancy=q_occupancy,
                )

            old_dt = self._accumulated_dt.get(area_id, 0.0)
            new_dt = old_dt + dt_minutes
            if new_dt > 0:
                old_pf = self._accumulated_pf.get(area_id, 1.0)
                self._accumulated_pf[area_id] = (old_pf * old_dt + ekf_pf * dt_minutes) / new_dt
                if q_rebound is None:
                    self._accumulated_rebound.pop(area_id, None)
                else:
                    old_rebound = self._accumulated_rebound.get(area_id, q_rebound)
                    self._accumulated_rebound[area_id] = (old_rebound * old_dt + q_rebound * dt_minutes) / new_dt
                old_power = self._accumulated_power.get(area_id, q_power)
                self._accumulated_power[area_id] = (old_power * old_dt + q_power * dt_minutes) / new_dt
            self._accumulated_dt[area_id] = new_dt
            self._accumulated_mode[area_id] = ekf_mode

            if self._accumulated_dt[area_id] >= EKF_UPDATE_MIN_DT:
                pf = self._accumulated_pf.pop(area_id, 1.0)
                batch_rebound = self._accumulated_rebound.pop(area_id, None)
                batch_power = self._accumulated_power.pop(area_id, 0.0)
                self._model_manager.update(
                    area_id,
                    current_temp,
                    T_outdoor,
                    ekf_mode,
                    self._accumulated_dt[area_id],
                    can_heat=can_heat,
                    can_cool=can_cool,
                    power_fraction=pf,
                    q_solar=q_solar * shading_factor,
                    q_residual=q_residual,
                    q_occupancy=q_occupancy,
                    q_rebound=batch_rebound,
                    q_power=batch_power,
                )
                self._accumulated_dt[area_id] = 0.0

        self.last_temps[area_id] = current_temp

    def clear(self, area_id: str, *, resync: bool = True) -> None:
        """Clear accumulated EKF state for a room.

        ``resync`` re-reads the model temperature from the next measurement before
        learning resumes. Off, the first batch afterwards learns the whole change since
        the last observation (kept for the compressor hold and coil dry, see coordinator).
        """
        self._current.discard(area_id)
        if resync:
            self._synced.discard(area_id)
        self._accumulated_dt.pop(area_id, None)
        self._accumulated_mode.pop(area_id, None)
        self._accumulated_pf.pop(area_id, None)
        self._accumulated_rebound.pop(area_id, None)
        self._accumulated_power.pop(area_id, None)

    def remove_room(self, area_id: str) -> None:
        """Clean up all state for a removed room."""
        self.clear(area_id)
        self.last_temps.pop(area_id, None)
