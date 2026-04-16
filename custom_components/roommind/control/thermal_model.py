"""First-order RC thermal model with EKF parameter learning for RoomMind.

Physics: dT/dt = (Q_active - U * (T_room - T_outdoor)) / C

Reparametrized for identifiability (C=1 normalization):
  alpha = U/C   [1/h]  heat loss rate
  beta_h = Q_heat/C  [degC/h]  heating rate
  beta_c = Q_cool/C  [degC/h]  cooling rate
  beta_s = Q_solar/C [degC/h per kW/m²]  solar gain rate
  beta_o = Q_occupancy/C [degC/h]  occupancy heat gain rate

RCModel solves the ODE analytically (exact for constant inputs over a time step).
ThermalEKF learns alpha, beta_h, beta_c, beta_s, beta_o online from temperature
measurements using an Extended Kalman Filter with augmented state
[T, alpha, beta_h, beta_c, beta_s, beta_o].
RoomModelManager provides per-room model access for the coordinator.
"""

from __future__ import annotations

import logging
import math

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RCModel -- deterministic first-order RC thermal model
# ---------------------------------------------------------------------------


class RCModel:
    """First-order RC thermal model with analytical solution.

    Models a room as a single thermal mass (capacitance C) losing heat to the
    outdoors through an effective conductance U, with optional active power Q.

    The ODE  dT/dt = (Q - U*(T - T_out)) / C  has the closed-form solution:

        T_eq = T_out + Q / U
        T(t) = T_eq + (T_0 - T_eq) * exp(-U * dt / C)

    where dt is in hours (matching Wh units for C).
    """

    DEFAULT_C: float = 2.0  # Wh/degC  -- thermal capacitance
    DEFAULT_U: float = 50.0  # W/degC   -- heat loss coefficient
    DEFAULT_Q_HEAT: float = 800.0  # W      -- heating power
    DEFAULT_Q_COOL: float = 1200.0  # W      -- cooling power
    DEFAULT_Q_SOLAR: float = 0.0  # degC/h per kW/m² GHI -- solar gain
    DEFAULT_Q_OCCUPANCY: float = 0.0  # degC/h -- occupancy heat gain

    def __init__(
        self,
        C: float = DEFAULT_C,
        U: float = DEFAULT_U,
        Q_heat: float = DEFAULT_Q_HEAT,
        Q_cool: float = DEFAULT_Q_COOL,
        Q_solar: float = DEFAULT_Q_SOLAR,
        Q_occupancy: float = DEFAULT_Q_OCCUPANCY,
    ) -> None:
        self.C = C
        self.U = U
        self.Q_heat = Q_heat
        self.Q_cool = Q_cool
        self.Q_solar = Q_solar
        self.Q_occupancy = Q_occupancy

    def predict(
        self,
        T_room: float,
        T_outdoor: float,
        Q_active: float,
        dt_minutes: float,
        *,
        q_solar: float = 0.0,
        q_residual: float = 0.0,
        q_occupancy: float = 0.0,
    ) -> float:
        """Predict room temperature after *dt_minutes* using the analytical solution.

        Args:
            T_room: current room temperature [degC].
            T_outdoor: outdoor temperature [degC].
            Q_active: active power [W] (positive = heating, negative = cooling).
            dt_minutes: time step in minutes.
            q_solar: normalized solar irradiance (GHI/1000, 0–1).
            q_residual: residual heat fraction from thermal mass (0–1).
            q_occupancy: occupancy signal (0 = unoccupied, 1 = occupied).

        Returns:
            Predicted room temperature [degC], clamped to [0, 50].
        """
        if dt_minutes <= 0:
            return T_room
        dt_hours = dt_minutes / 60.0
        # Residual heat: only contributes when HVAC is off (no double-counting)
        Q_residual = self.Q_heat * q_residual if Q_active == 0.0 and q_residual > 0 else 0.0
        # Total thermal input including solar gain, occupancy heat, and residual heat
        Q_total = Q_active + self.Q_solar * q_solar + self.Q_occupancy * q_occupancy + Q_residual
        # Equilibrium temperature: T_out + Q/U
        T_eq = T_outdoor + Q_total / self.U
        # Decay constant  (U/C has unit 1/h)
        decay = math.exp(-self.U * dt_hours / self.C)
        result = T_eq + (T_room - T_eq) * decay
        # Hard output clamp for safety
        return max(0.0, min(50.0, result))

    def predict_window_open(
        self,
        T_room: float,
        T_outdoor: float,
        k_window: float,
        dt_minutes: float,
    ) -> float:
        """Predict temperature with window open (amplified heat exchange, Q=0).

        Uses U * k_window instead of U.  Works bidirectionally:
        winter (T_outdoor < T_room) gives cooling,
        summer (T_outdoor > T_room) gives warming.
        """
        if dt_minutes <= 0:
            return T_room
        dt_hours = dt_minutes / 60.0
        U_eff = self.U * k_window
        # Q=0 during window-open, so T_eq = T_outdoor
        T_eq = max(0.0, min(50.0, T_outdoor))
        decay = math.exp(-U_eff * dt_hours / self.C)
        result = T_eq + (T_room - T_eq) * decay
        return max(0.0, min(50.0, result))

    def predict_trajectory(
        self,
        T_room: float,
        T_outdoor_series: list[float],
        Q_active_series: list[float],
        dt_minutes: float,
        *,
        q_solar_series: list[float] | None = None,
        q_residual_series: list[float] | None = None,
        q_occupancy_series: list[float] | None = None,
    ) -> list[float]:
        """Predict a temperature trajectory over multiple time steps.

        Each entry in *T_outdoor_series* / *Q_active_series* represents the
        constant value over that step (zero-order hold).

        Args:
            T_room: initial room temperature [degC].
            T_outdoor_series: outdoor temps per step [degC].
            Q_active_series: active power per step [W].
            dt_minutes: duration of each step in minutes.
            q_solar_series: normalized solar irradiance per step (GHI/1000).
            q_residual_series: residual heat fraction per step (0–1).
            q_occupancy_series: occupancy signal per step (0 or 1).

        Returns:
            List of len(series) + 1 temperatures (including the initial value).
        """
        if len(T_outdoor_series) != len(Q_active_series):
            raise ValueError("T_outdoor_series and Q_active_series must have the same length")
        solar = q_solar_series or [0.0] * len(T_outdoor_series)
        residual = q_residual_series or [0.0] * len(T_outdoor_series)
        occupancy = q_occupancy_series or [0.0] * len(T_outdoor_series)
        trajectory = [T_room]
        T = T_room
        for i, (T_out, Q) in enumerate(zip(T_outdoor_series, Q_active_series, strict=False)):
            qs = solar[i] if i < len(solar) else 0.0
            qr = residual[i] if i < len(residual) else 0.0
            qo = occupancy[i] if i < len(occupancy) else 0.0
            T = self.predict(T, T_out, Q, dt_minutes, q_solar=qs, q_residual=qr, q_occupancy=qo)
            trajectory.append(T)
        return trajectory

    def to_dict(self) -> dict:
        """Serialize model parameters."""
        return {
            "C": self.C,
            "U": self.U,
            "Q_heat": self.Q_heat,
            "Q_cool": self.Q_cool,
            "Q_solar": self.Q_solar,
            "Q_occupancy": self.Q_occupancy,
        }

    @classmethod
    def from_dict(cls, data: dict) -> RCModel:
        """Restore model from a dict."""
        return cls(
            C=max(0.1, data.get("C", cls.DEFAULT_C)),
            U=max(0.1, data.get("U", cls.DEFAULT_U)),
            Q_heat=max(0.0, data.get("Q_heat", cls.DEFAULT_Q_HEAT)),
            Q_cool=max(0.0, data.get("Q_cool", cls.DEFAULT_Q_COOL)),
            Q_solar=max(0.0, data.get("Q_solar", cls.DEFAULT_Q_SOLAR)),
            Q_occupancy=max(0.0, data.get("Q_occupancy", cls.DEFAULT_Q_OCCUPANCY)),
        )

    def __repr__(self) -> str:
        return (
            f"RCModel(C={self.C:.2f}, U={self.U:.2f}, "
            f"Q_heat={self.Q_heat:.0f}, Q_cool={self.Q_cool:.0f}, "
            f"Q_solar={self.Q_solar:.1f}, Q_occupancy={self.Q_occupancy:.1f})"
        )


# ---------------------------------------------------------------------------
# ThermalEKF -- Extended Kalman Filter for online RC parameter learning
# ---------------------------------------------------------------------------


class ThermalEKF:
    """Extended Kalman Filter for 1R1C thermal model.

    Augmented state vector x = [T, alpha, beta_h, beta_c, beta_s, beta_o] where:
      T       = room temperature [degC]  (directly measured)
      alpha   = U/C  heat loss rate [1/h]
      beta_h  = Q_heat/C  heating rate [degC/h]
      beta_c  = Q_cool/C  cooling rate [degC/h]
      beta_s  = Q_solar/C  solar gain rate [degC/h per kW/m²]
      beta_o  = Q_occupancy/C  occupancy heat gain rate [degC/h]

    The EKF uses the analytical 1R1C solution for the predict step and
    a standard Kalman measurement update.  Parameters are modeled as
    random walks (constant + process noise), so they adapt slowly to
    changing building conditions.

    Mode-awareness is built into the Jacobian:
      - During idle, F[0][2]=F[0][3]=0 → heating/cooling params NOT updated
      - During heating, F[0][2]>0 → beta_h IS updated from heating data
      - During cooling, F[0][3]<0 → beta_c IS updated from cooling data

    References:
      - Bacher & Madsen (2011): RC model selection for buildings
      - Radecki & Hencey (2016): Online model estimation (arXiv:1601.02947)
      - Zamani et al. (2025): UKF for RC model estimation (PMC 11798724)
    """

    # Threshold below which we use the linearized model to avoid 1/alpha
    _ALPHA_SMALL: float = 0.01

    # Innovation outlier threshold (in standard deviations)
    _ANOMALY_SIGMA: float = 4.0
    # Factor to inflate R when an outlier is detected (soft reject)
    _ANOMALY_R_INFLATE: float = 100.0

    # Parameter bounds (C=1 normalization: alpha=U/C, beta=Q/C)
    _ALPHA_MIN: float = 0.005  # time constant up to 200 h (very heavy building)
    _ALPHA_MAX: float = 5.0  # time constant down to 12 min (lightweight space)
    _BETA_H_MIN: float = 0.1  # very weak heater relative to thermal mass
    _BETA_H_MAX: float = 200.0  # powerful heater in lightweight room
    _BETA_C_MIN: float = 0.1
    _BETA_C_MAX: float = 300.0
    _BETA_S_MIN: float = 0.0  # interior rooms / north-facing → 0
    _BETA_S_MAX: float = 50.0  # large south-facing sunroom
    _BETA_O_MIN: float = 0.0  # no occupancy gain
    _BETA_O_MAX: float = 20.0  # large occupancy gain (many people / small room)

    # Default initial parameter values (C=1 normalization)
    _DEFAULT_ALPHA: float = 0.15  # ~7 h time constant (moderate residential room)
    _DEFAULT_BETA_H: float = 3.0  # moderate heater: T_eq = T_out + 20°C
    _DEFAULT_BETA_C: float = 4.0  # moderate AC
    _DEFAULT_BETA_S: float = 0.5  # small initial solar gain; learns from data
    _DEFAULT_BETA_O: float = 0.3  # ~100W body heat, C=1 normalized

    # Process noise (diagonal of Q_noise matrix)
    # Higher values keep the filter adaptive; lower values freeze parameters.
    # Note: beta_h/beta_c/beta_s noise is mode-gated in _predict_step —
    # only applied when the parameter is observable (Jacobian F[0][i] ≠ 0).
    _Q_T: float = 0.01  # unmodeled disturbances (~0.1 degC/step)
    _Q_ALPHA: float = 0.0005  # building property drift (slow: seasonal, insulation)
    _Q_BETA_H: float = 0.005  # HVAC power drift (5x previous)
    _Q_BETA_C: float = 0.005  # HVAC power drift (5x previous)
    _Q_BETA_S: float = 0.002  # solar gain drift
    _Q_BETA_O: float = 0.002  # occupancy gain drift

    # Measurement noise
    _R: float = 0.04  # sensor noise variance (0.2 degC std)

    # Initial covariance diagonal — sized to prevent first-update overshoot.
    # Rule: K = F*P_init / (F^2*P_init + R) should stay below ~1.0.
    _P_INIT_T: float = 0.5
    _P_INIT_ALPHA: float = 0.5  # σ≈0.7 around default 0.15
    _P_INIT_BETA: float = 50.0  # σ≈7 around default 3.0
    _P_INIT_BETA_S: float = 25.0  # σ≈5 around default 0.5
    _P_INIT_BETA_O: float = 10.0  # moderate initial uncertainty for occupancy

    # Window-open heat exchange multiplier
    _K_WINDOW_DEFAULT: float = 5.0  # initial: 5x faster than closed
    _K_WINDOW_MIN: float = 1.5  # must be at least somewhat faster
    _K_WINDOW_MAX: float = 50.0  # physical upper bound
    _K_WINDOW_EMA_ALPHA: float = 0.05  # EMA smoothing factor
    _K_WINDOW_MIN_DT: float = 0.25  # min dt (minutes) for learning
    _K_WINDOW_MIN_DELTA_T: float = 0.1  # min |T_outdoor - T_room| for learning

    # Number of state dimensions
    _N: int = 6

    def __init__(self, T_init: float = 20.0) -> None:
        self._x: list[float] = [
            T_init,
            self._DEFAULT_ALPHA,
            self._DEFAULT_BETA_H,
            self._DEFAULT_BETA_C,
            self._DEFAULT_BETA_S,
            self._DEFAULT_BETA_O,
        ]
        self._P: list[list[float]] = [
            [self._P_INIT_T, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, self._P_INIT_ALPHA, 0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, self._P_INIT_BETA, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, self._P_INIT_BETA, 0.0, 0.0],
            [0.0, 0.0, 0.0, 0.0, self._P_INIT_BETA_S, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0, self._P_INIT_BETA_O],
        ]
        self._n_updates: int = 0
        self._n_heating: int = 0
        self._n_cooling: int = 0
        self._n_idle: int = 0
        self._applicable_modes: set[str] = {"heating", "cooling", "idle"}
        self._last_mode: str | None = None
        self._initialized: bool = False
        self._k_window: float = self._K_WINDOW_DEFAULT
        self._k_window_n: int = 0

    # -- public API ----------------------------------------------------------

    @property
    def confidence(self) -> float:
        """Model reliability, 0.0 to 1.0.

        Multi-factor confidence that reflects actual model readiness:
        1. Data factor: how close to MPC-ready sample counts
        2. Accuracy factor: prediction std mapped relative to MPC threshold

        Combined as: 0.3 * data_factor + 0.7 * data_factor * accuracy_factor
        Data alone gives up to 30% (we have samples, model is learning).
        Accuracy multiplied by data adds the remaining 70%.

        This produces a meaningful 0-100% range:
        - 0%: no data
        - ~10-30%: learning (some data, covariance still wide)
        - ~40-60%: improving (enough idle data, active data growing)
        - ~80-100%: MPC-ready (enough data + accurate predictions)
        """
        if self._n_updates < 3:
            return 0.0

        # --- Data factor (0..1) ---
        # Mirrors MPC data gates: MIN_IDLE_UPDATES=60, MIN_ACTIVE_UPDATES=20.
        # Each update covers ~3 min (EKF_UPDATE_MIN_DT), so thresholds
        # correspond to ~3 h idle + ~1 h active real time.
        idle_frac = min(self._n_idle / 60.0, 1.0)

        # Active data: average across modes that this room can use
        active_fracs: list[float] = []
        if self._n_heating >= 2:
            active_fracs.append(min(self._n_heating / 20.0, 1.0))
        if self._n_cooling >= 2:
            active_fracs.append(min(self._n_cooling / 20.0, 1.0))
        if active_fracs:
            active_frac = sum(active_fracs) / len(active_fracs)
        else:
            # No active mode data yet — cap active contribution at 0
            active_frac = 0.0

        data_factor = 0.5 * idle_frac + 0.5 * active_frac

        # --- Accuracy factor (0..1) ---
        # Map weighted prediction std from [noise_floor, mpc_threshold] to [1.0, 0.0]
        # Realistic noise floor: the minimum achievable prediction std
        # accounts for process noise (Q_T), sensor noise (R → P[0][0]),
        # and parameter cross-coupling.  Simulations show ~0.20-0.21°C
        # as the converged minimum at standard operating points.
        noise_floor = 0.20
        mpc_threshold = 0.5  # MPC activation threshold

        # Frequency-weighted prediction std: each mode's contribution is
        # proportional to its sample count.  This prevents a rarely-used mode
        # (e.g. cooling in a heating-dominant climate) from capping the entire
        # accuracy metric via an unlearned parameter with wide covariance.
        std_weights: list[tuple[int, float]] = [
            (max(self._n_idle, 1), self.prediction_std(0.0, 20.0, 15.0, 5.0)),
        ]
        if self._n_heating >= 2:
            std_weights.append((self._n_heating, self.prediction_std(self._x[2], 20.0, 10.0, 5.0)))
        if self._n_cooling >= 2:
            std_weights.append((self._n_cooling, self.prediction_std(-self._x[3], 20.0, 25.0, 5.0)))
        total_w = sum(w for w, _ in std_weights)
        weighted_std = sum(w / total_w * s for w, s in std_weights)

        if weighted_std <= noise_floor:
            accuracy_factor = 1.0
        elif weighted_std >= mpc_threshold:
            accuracy_factor = 0.0
        else:
            accuracy_factor = 1.0 - (weighted_std - noise_floor) / (mpc_threshold - noise_floor)

        # Data alone contributes up to 30%, accuracy adds remaining 70%
        return data_factor * (0.3 + 0.7 * accuracy_factor)

    def prediction_std(
        self,
        Q_active: float,
        T_room: float,
        T_outdoor: float,
        dt_minutes: float,
        *,
        q_solar: float = 0.0,
        q_residual: float = 0.0,
        q_occupancy: float = 0.0,
    ) -> float:
        """Prediction uncertainty in degC for a given operating point.

        Propagates the covariance matrix through the Jacobian to compute
        the temperature prediction variance at dt_minutes ahead.
        """
        if dt_minutes <= 0:
            return math.sqrt(max(self._P[0][0], 0.0))

        mode = "idle"
        if Q_active > 0:
            mode = "heating"
        elif Q_active < 0:
            mode = "cooling"

        dt_h = dt_minutes / 60.0
        alpha = self._x[1]
        u = self._mode_to_u(mode)
        F = self._compute_jacobian(
            T_room,
            alpha,
            u,
            T_outdoor,
            dt_h,
            mode,
            q_solar=q_solar,
            q_residual=q_residual,
            q_occupancy=q_occupancy,
        )

        # P_pred = F @ P @ F^T + Q_noise (only need element [0][0])
        # Compute F[0,:] @ P
        FP_row = [sum(F[0][k] * self._P[k][j] for k in range(self._N)) for j in range(self._N)]
        # Compute FP_row @ F[0,:]^T = F[0,:] @ P @ F[0,:]^T
        var = sum(FP_row[j] * F[0][j] for j in range(self._N))
        var += self._Q_T  # add process noise
        return math.sqrt(max(var, 0.0))

    @property
    def k_window(self) -> float:
        """Learned window heat-exchange multiplier."""
        return self._k_window

    def update_window_open(
        self,
        T_measured: float,
        T_outdoor: float,
        dt_minutes: float,
        *,
        learn_k_window: bool = True,
    ) -> None:
        """Track temperature state and optionally learn k_window during window-open.

        Always updates _x[0] so the EKF resumes with current temperature.
        When *learn_k_window* is True, also computes the observed heat loss
        rate and updates the k_window multiplier.
        """
        if dt_minutes < self._K_WINDOW_MIN_DT:
            return
        if not self._initialized:
            self._x[0] = T_measured
            self._initialized = True
            return

        T_prev = self._x[0]
        delta_T = T_prev - T_outdoor

        if not learn_k_window or abs(delta_T) < self._K_WINDOW_MIN_DELTA_T:
            self._x[0] = T_measured
            return

        # From analytical 1R1C solution with Q=0:
        # T_new = T_outdoor + (T_prev - T_outdoor) * exp(-alpha_obs * dt_h)
        # => ratio = (T_measured - T_outdoor) / (T_prev - T_outdoor) = exp(-alpha_obs * dt_h)
        dt_h = dt_minutes / 60.0
        ratio = (T_measured - T_outdoor) / delta_T

        # ratio must be in (0, 1) for a valid observation
        if ratio <= 0.01 or ratio >= 1.0:
            self._x[0] = T_measured
            return

        alpha_obs = -math.log(ratio) / dt_h
        alpha_normal = max(self._x[1], self._ALPHA_SMALL)

        k_obs = alpha_obs / alpha_normal
        k_obs = max(self._K_WINDOW_MIN, min(self._K_WINDOW_MAX, k_obs))

        if self._k_window_n == 0:
            self._k_window = k_obs
        else:
            ema = self._K_WINDOW_EMA_ALPHA
            self._k_window = ema * k_obs + (1.0 - ema) * self._k_window

        self._k_window_n += 1
        self._k_window = max(self._K_WINDOW_MIN, min(self._K_WINDOW_MAX, self._k_window))

        # Track temperature without updating EKF parameters
        self._x[0] = T_measured

    def set_applicable_modes(self, can_heat: bool, can_cool: bool) -> None:
        """Update which modes this room supports."""
        modes = {"idle"}
        if can_heat:
            modes.add("heating")
        if can_cool:
            modes.add("cooling")
        self._applicable_modes = modes

    def update(
        self,
        T_measured: float,
        T_outdoor: float,
        mode: str,
        dt_minutes: float,
        *,
        power_fraction: float = 1.0,
        q_solar: float = 0.0,
        q_residual: float = 0.0,
        q_occupancy: float = 0.0,
    ) -> None:
        """Run one full EKF cycle: predict then update with measurement.

        Args:
            T_measured: current room temperature measurement [degC].
            T_outdoor: outdoor temperature [degC].
            mode: mode active during the interval ('heating', 'cooling', 'idle').
            dt_minutes: time since last call [min].
            power_fraction: fraction of max heating/cooling power applied (0-1).
            q_solar: normalized solar irradiance (GHI/1000, 0–1).
            q_residual: residual heat fraction from thermal mass (0–1).
            q_occupancy: occupancy signal (0 = unoccupied, 1 = occupied).
        """
        if dt_minutes <= 0:
            return

        # On first call, initialize temperature state from measurement
        if not self._initialized:
            self._x[0] = T_measured
            self._initialized = True
            self._last_mode = mode
            return

        # Use the mode that was active during this time interval
        predict_mode = self._last_mode or mode
        dt_h = dt_minutes / 60.0

        # --- Predict step ---
        self._predict_step(
            T_outdoor,
            predict_mode,
            dt_h,
            power_fraction=power_fraction,
            q_solar=q_solar,
            q_residual=q_residual,
            q_occupancy=q_occupancy,
        )

        # --- Update step ---
        self._update_step(T_measured)

        # --- Enforce parameter bounds ---
        self._clamp_parameters()

        # --- Ensure P stays symmetric and PSD ---
        self._enforce_psd()

        # Update bookkeeping
        self._last_mode = mode
        self._n_updates += 1
        if predict_mode == "heating":
            self._n_heating += 1
        elif predict_mode == "cooling":
            self._n_cooling += 1
        else:
            self._n_idle += 1

    def get_model(self) -> RCModel:
        """Extract an RCModel (C=1 normalization) for the MPC optimizer.

        Since only ratios alpha=U/C, beta=Q/C are identifiable, we set C=1
        and map: U=alpha, Q_heat=beta_h, Q_cool=beta_c, Q_solar=beta_s.
        The resulting RCModel gives identical predictions.
        """
        return RCModel(
            C=1.0,
            U=max(self._x[1], self._ALPHA_MIN),
            Q_heat=max(self._x[2], 0.0),
            Q_cool=max(self._x[3], 0.0),
            Q_solar=max(self._x[4], 0.0),
            Q_occupancy=max(self._x[5], 0.0),
        )

    # -- EKF internals -------------------------------------------------------

    def _mode_to_u(self, mode: str) -> float:
        """Return the thermal input u from EKF state for the given mode."""
        if mode == "heating":
            return self._x[2]  # beta_h
        if mode == "cooling":
            return -self._x[3]  # -beta_c
        return 0.0

    def _state_transition(self, T: float, alpha: float, u: float, T_out: float, dt_h: float) -> float:
        """Compute predicted temperature using the analytical 1R1C solution.

        Uses linearized (Euler) form when alpha is very small to avoid
        division-by-zero in T_eq = T_out + u/alpha.
        """
        if abs(alpha) < self._ALPHA_SMALL:
            return T + dt_h * (u - alpha * (T - T_out))
        T_eq = T_out + u / alpha
        decay = math.exp(-alpha * dt_h)
        return T_eq + (T - T_eq) * decay

    def _compute_jacobian(
        self,
        T: float,
        alpha: float,
        u: float,
        T_out: float,
        dt_h: float,
        mode: str,
        *,
        power_fraction: float = 1.0,
        q_solar: float = 0.0,
        q_residual: float = 0.0,
        q_occupancy: float = 0.0,
    ) -> list[list[float]]:
        """Compute the 6x6 Jacobian of the state transition.

        F[0][0] = dT_new/dT
        F[0][1] = dT_new/d_alpha
        F[0][2] = dT_new/d_beta_h  (nonzero during heating, or idle with residual)
        F[0][3] = dT_new/d_beta_c  (nonzero only during cooling)
        F[0][4] = dT_new/d_beta_s  (nonzero only when q_solar > 0)
        F[0][5] = dT_new/d_beta_o  (nonzero only when q_occupancy > 0)
        F[1..5][1..5] = I           (parameters are random walk)
        """
        N = self._N
        F: list[list[float]] = [[0.0] * N for _ in range(N)]
        # Identity for parameter rows
        F[1][1] = 1.0
        F[2][2] = 1.0
        F[3][3] = 1.0
        F[4][4] = 1.0
        F[5][5] = 1.0

        if abs(alpha) < self._ALPHA_SMALL:
            # Linearized (Euler) Jacobian
            F[0][0] = 1.0 - alpha * dt_h
            F[0][1] = -(T - T_out) * dt_h
            if mode == "heating":
                F[0][2] = power_fraction * dt_h
            elif mode == "cooling":
                F[0][3] = -power_fraction * dt_h
            elif mode == "idle" and q_residual > 0:
                F[0][2] = q_residual * dt_h
            # Solar: dT_new/d_beta_s = q_solar * dt_h
            F[0][4] = q_solar * dt_h
            # Occupancy: dT_new/d_beta_o = q_occupancy * dt_h
            F[0][5] = q_occupancy * dt_h
        else:
            decay = math.exp(-alpha * dt_h)
            one_minus_decay = 1.0 - decay
            F[0][0] = decay
            # dT_new/d_alpha (derived analytically, see plan for derivation)
            F[0][1] = -(u / (alpha * alpha)) * one_minus_decay - (T - T_out - u / alpha) * dt_h * decay
            if mode == "heating":
                F[0][2] = power_fraction * (1.0 / alpha) * one_minus_decay
            elif mode == "cooling":
                F[0][3] = -power_fraction * (1.0 / alpha) * one_minus_decay
            elif mode == "idle" and q_residual > 0:
                F[0][2] = q_residual * (1.0 / alpha) * one_minus_decay
            # Solar: dT_new/d_beta_s = q_solar * (1/alpha) * (1 - exp(-alpha*dt))
            F[0][4] = q_solar * (1.0 / alpha) * one_minus_decay
            # Occupancy: dT_new/d_beta_o = q_occupancy * (1/alpha) * (1 - exp(-alpha*dt))
            F[0][5] = q_occupancy * (1.0 / alpha) * one_minus_decay
        return F

    def _predict_step(
        self,
        T_outdoor: float,
        mode: str,
        dt_h: float,
        *,
        power_fraction: float = 1.0,
        q_solar: float = 0.0,
        q_residual: float = 0.0,
        q_occupancy: float = 0.0,
    ) -> None:
        """EKF predict: propagate state and covariance forward."""
        T, alpha, beta_h, beta_c, beta_s, beta_o = self._x
        u_hvac = self._mode_to_u(mode) * power_fraction
        # Residual heat: during idle, thermal mass continues releasing stored energy
        u_residual = beta_h * q_residual if mode == "idle" and q_residual > 0 else 0.0
        # Occupancy heat: always additive (not mode-gated)
        u = u_hvac + beta_s * q_solar + beta_o * q_occupancy + u_residual

        # State prediction (analytical or linearized)
        T_new = self._state_transition(T, alpha, u, T_outdoor, dt_h)
        self._x = [T_new, alpha, beta_h, beta_c, beta_s, beta_o]

        # Jacobian at current state
        F = self._compute_jacobian(
            T,
            alpha,
            u,
            T_outdoor,
            dt_h,
            mode,
            power_fraction=power_fraction,
            q_solar=q_solar,
            q_residual=q_residual,
            q_occupancy=q_occupancy,
        )

        # Covariance prediction: P = F @ P @ F^T + Q_noise
        N = self._N
        P = self._P
        # Mode-gated process noise: only add drift to parameters that are
        # currently observable (Jacobian F[0][i] ≠ 0).  Unobservable params
        # keep their variance frozen — inflating it without any measurement
        # to reduce it again just degrades confidence and destabilises the
        # correlated parameters (alpha ↔ beta_h coupling → time-constant
        # oscillation).
        alpha_ratio = max(alpha, self._ALPHA_MIN) / self._DEFAULT_ALPHA
        q_alpha = self._Q_ALPHA * min(1.0, alpha_ratio * alpha_ratio)
        Q = [
            self._Q_T,
            q_alpha,
            self._Q_BETA_H if (mode == "heating" or (mode == "idle" and q_residual > 0)) else 0.0,
            self._Q_BETA_C if mode == "cooling" else 0.0,
            self._Q_BETA_S if q_solar > 0 else 0.0,
            self._Q_BETA_O if q_occupancy > 0 else 0.0,
        ]

        # FP = F @ P
        FP = [[sum(F[i][k] * P[k][j] for k in range(N)) for j in range(N)] for i in range(N)]

        # P_new = FP @ F^T + diag(Q)
        P_new = [[0.0] * N for _ in range(N)]
        for i in range(N):
            for j in range(N):
                P_new[i][j] = sum(FP[i][k] * F[j][k] for k in range(N))
                if i == j:
                    P_new[i][j] += Q[i]

        self._P = P_new

    def _update_step(self, T_measured: float) -> None:
        """EKF update: correct state with measurement.

        Measurement model: H = [1, 0, 0, 0, 0, 0], so y = T_measured.
        """
        N = self._N
        P = self._P

        # Innovation
        y_pred = self._x[0]
        innovation = T_measured - y_pred

        # Innovation covariance: S = P[0][0] + R
        S = P[0][0] + self._R

        # Outlier detection via normalized innovation
        R_eff = self._R
        if S > 0:
            norm_innov = abs(innovation) / math.sqrt(S)
            if norm_innov > self._ANOMALY_SIGMA:
                _LOGGER.debug(
                    "EKF: outlier detected (innovation=%.2f, %.1f sigma), softening update",
                    innovation,
                    norm_innov,
                )
                R_eff = self._R * self._ANOMALY_R_INFLATE
                S = P[0][0] + R_eff

        if S < 1e-12:
            return  # Numerical safety

        # Kalman gain: K = P[:, 0] / S
        K = [P[i][0] / S for i in range(N)]

        # State update: x = x + K * innovation
        for i in range(N):
            self._x[i] += K[i] * innovation

        # Covariance update: P = (I - K @ H) @ P
        # Since H = [1, 0, 0, 0, 0, 0]:  P_new[i][j] = P[i][j] - K[i] * P[0][j]
        P_new = [[P[i][j] - K[i] * P[0][j] for j in range(N)] for i in range(N)]

        # Add K * R_eff * K^T for numerical stability (Joseph-form correction)
        for i in range(N):
            for j in range(N):
                P_new[i][j] += K[i] * R_eff * K[j]

        self._P = P_new

    def _clamp_parameters(self) -> None:
        """Enforce physical bounds on parameters."""
        self._x[1] = max(self._ALPHA_MIN, min(self._ALPHA_MAX, self._x[1]))
        self._x[2] = max(self._BETA_H_MIN, min(self._BETA_H_MAX, self._x[2]))
        self._x[3] = max(self._BETA_C_MIN, min(self._BETA_C_MAX, self._x[3]))
        self._x[4] = max(self._BETA_S_MIN, min(self._BETA_S_MAX, self._x[4]))
        self._x[5] = max(self._BETA_O_MIN, min(self._BETA_O_MAX, self._x[5]))

    def _enforce_psd(self) -> None:
        """Enforce symmetry and positive semi-definiteness of P."""
        N = self._N
        P = self._P
        # Enforce symmetry
        for i in range(N):
            for j in range(i + 1, N):
                avg = (P[i][j] + P[j][i]) / 2.0
                P[i][j] = avg
                P[j][i] = avg
        # Enforce positive diagonal
        for i in range(N):
            if P[i][i] < 1e-10:
                P[i][i] = 1e-10

    # -- serialization -------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize EKF state for persistence."""
        return {
            "ekf_version": 4,
            "x": list(self._x),
            "P": [list(row) for row in self._P],
            "n_updates": self._n_updates,
            "n_heating": self._n_heating,
            "n_cooling": self._n_cooling,
            "n_idle": self._n_idle,
            "applicable_modes": sorted(self._applicable_modes),
            "last_mode": self._last_mode,
            "initialized": self._initialized,
            "k_window": self._k_window,
            "k_window_n": self._k_window_n,
        }

    def boost_covariance(self, factor: float = 2.5, floor_frac: float = 0.3) -> None:
        """Multiply covariance P by *factor*, floored at *floor_frac* of P_initial.

        Used to accelerate re-learning after room physics change (e.g. new
        radiator, insulation, furniture).  The floor prevents repeated clicks
        from destroying the matrix.
        """
        p_init_diag = [
            self._P_INIT_T,
            self._P_INIT_ALPHA,
            self._P_INIT_BETA,
            self._P_INIT_BETA,
            self._P_INIT_BETA_S,
            self._P_INIT_BETA_O,
        ]
        for i in range(self._N):
            for j in range(self._N):
                boosted = self._P[i][j] * factor
                if i == j:
                    floor = p_init_diag[i] * floor_frac
                    boosted = max(boosted, floor)
                self._P[i][j] = boosted
        self._enforce_psd()

    @classmethod
    def from_dict(cls, data: dict) -> ThermalEKF:
        """Restore EKF from persisted data."""
        ekf = cls()

        if "x" in data:
            if len(data["x"]) == 6:
                ekf._x = list(data["x"])
            elif len(data["x"]) == 5:
                ekf._x = list(data["x"]) + [cls._DEFAULT_BETA_O]
        if "P" in data:
            if len(data["P"]) == 6:
                ekf._P = [list(row) for row in data["P"]]
            elif len(data["P"]) == 5:
                ekf._P = [list(row) + [0.0] for row in data["P"]]
                ekf._P.append([0.0] * 5 + [cls._P_INIT_BETA_O])

        ekf._n_updates = data.get("n_updates", 0)
        ekf._n_heating = data.get("n_heating", 0)
        ekf._n_cooling = data.get("n_cooling", 0)
        ekf._n_idle = data.get("n_idle", 0)
        if "applicable_modes" in data:
            ekf._applicable_modes = set(data["applicable_modes"])
        ekf._last_mode = data.get("last_mode")
        ekf._initialized = data.get("initialized", ekf._n_updates > 0)
        ekf._k_window = data.get("k_window", cls._K_WINDOW_DEFAULT)
        ekf._k_window_n = data.get("k_window_n", 0)
        # Apply bounds in case stored data is out of range
        ekf._clamp_parameters()
        return ekf

    def __repr__(self) -> str:
        return (
            f"ThermalEKF(T={self._x[0]:.1f}, alpha={self._x[1]:.2f}, "
            f"beta_h={self._x[2]:.1f}, beta_c={self._x[3]:.1f}, "
            f"beta_s={self._x[4]:.1f}, beta_o={self._x[5]:.1f}, "
            f"confidence={self.confidence:.2f}, n={self._n_updates})"
        )


# ---------------------------------------------------------------------------
# RoomModelManager -- per-room model management
# ---------------------------------------------------------------------------


class RoomModelManager:
    """Manages per-room ThermalEKF instances.

    Provides a simple facade so the coordinator can update observations and
    request predictions without worrying about per-room bookkeeping.
    """

    def __init__(self) -> None:
        self._estimators: dict[str, ThermalEKF] = {}

    def get_room_ids(self) -> list[str]:
        """Return list of room IDs with learned models."""
        return list(self._estimators.keys())

    def get_estimator(self, area_id: str) -> ThermalEKF:
        """Return the estimator for *area_id*, creating one if needed."""
        if area_id not in self._estimators:
            self._estimators[area_id] = ThermalEKF()
        return self._estimators[area_id]

    def update(
        self,
        area_id: str,
        T_new: float,
        T_outdoor: float,
        mode: str,
        dt_minutes: float,
        *,
        can_heat: bool = True,
        can_cool: bool = True,
        power_fraction: float = 1.0,
        q_solar: float = 0.0,
        q_residual: float = 0.0,
        q_occupancy: float = 0.0,
    ) -> None:
        """Feed an observed transition to the room's estimator."""
        est = self.get_estimator(area_id)
        est.set_applicable_modes(can_heat, can_cool)
        est.update(
            T_new,
            T_outdoor,
            mode,
            dt_minutes,
            power_fraction=power_fraction,
            q_solar=q_solar,
            q_residual=q_residual,
            q_occupancy=q_occupancy,
        )

    def predict(
        self,
        area_id: str,
        T_room: float,
        T_outdoor: float,
        Q_active: float,
        dt_minutes: float,
    ) -> float:
        """Predict future temperature for *area_id*."""
        return self.get_estimator(area_id).get_model().predict(T_room, T_outdoor, Q_active, dt_minutes)

    def get_model(self, area_id: str) -> RCModel:
        """Return the learned RCModel for *area_id* (C=1 normalization)."""
        return self.get_estimator(area_id).get_model()

    def get_confidence(self, area_id: str) -> float:
        """Return model confidence for *area_id* (0.0 if never seen)."""
        if area_id not in self._estimators:
            return 0.0
        return self._estimators[area_id].confidence

    def get_prediction_std(
        self,
        area_id: str,
        Q_active: float,
        T_room: float,
        T_outdoor: float,
        dt_minutes: float,
        *,
        q_solar: float = 0.0,
        q_residual: float = 0.0,
        q_occupancy: float = 0.0,
    ) -> float:
        """Return prediction uncertainty in degC for *area_id* at given conditions."""
        if area_id not in self._estimators:
            return float("inf")
        return self._estimators[area_id].prediction_std(
            Q_active,
            T_room,
            T_outdoor,
            dt_minutes,
            q_solar=q_solar,
            q_residual=q_residual,
            q_occupancy=q_occupancy,
        )

    def get_mode_counts(self, area_id: str) -> tuple[int, int, int]:
        """Return (n_idle, n_heating, n_cooling) for *area_id*."""
        if area_id not in self._estimators:
            return (0, 0, 0)
        est = self._estimators[area_id]
        return (est._n_idle, est._n_heating, est._n_cooling)

    def get_n_observations(self, area_id: str) -> int:
        """Return total number of EKF updates for *area_id*."""
        est = self._estimators.get(area_id)
        return est._n_updates if est else 0

    def update_window_open(
        self,
        area_id: str,
        T_new: float,
        T_outdoor: float,
        dt_minutes: float,
        *,
        learn_k_window: bool = True,
    ) -> None:
        """Track temperature state and optionally learn k_window during window-open."""
        est = self.get_estimator(area_id)
        est.update_window_open(T_new, T_outdoor, dt_minutes, learn_k_window=learn_k_window)

    def predict_window_open(
        self,
        area_id: str,
        T_room: float,
        T_outdoor: float,
        dt_minutes: float,
    ) -> float:
        """Predict temperature during window-open using learned k_window."""
        est = self.get_estimator(area_id)
        return est.get_model().predict_window_open(T_room, T_outdoor, est.k_window, dt_minutes)

    def get_k_window(self, area_id: str) -> float:
        """Return the learned window multiplier for *area_id*."""
        if area_id not in self._estimators:
            return ThermalEKF._K_WINDOW_DEFAULT
        return self._estimators[area_id].k_window

    def boost_learning(self, area_id: str) -> int:
        """Boost covariance for *area_id* to accelerate re-learning.

        Returns the current ``n_updates`` (used as cooldown anchor).
        """
        est = self._estimators.get(area_id)
        if est is None:
            return 0
        est.boost_covariance()
        return est._n_updates

    def remove_room(self, area_id: str) -> None:
        """Discard learned data for *area_id*."""
        self._estimators.pop(area_id, None)

    def to_dict(self) -> dict:
        """Serialize all room estimators."""
        return {area_id: est.to_dict() for area_id, est in self._estimators.items()}

    @classmethod
    def from_dict(cls, data: dict) -> RoomModelManager:
        """Restore all room estimators from persisted data."""
        mgr = cls()
        for area_id, est_data in data.items():
            mgr._estimators[area_id] = ThermalEKF.from_dict(est_data)
        return mgr

    def __repr__(self) -> str:
        rooms = ", ".join(f"{aid}({e.confidence:.0%})" for aid, e in self._estimators.items())
        return f"RoomModelManager([{rooms}])"
