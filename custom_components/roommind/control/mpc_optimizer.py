"""MPC Optimizer using Dynamic Programming for RoomMind."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..const import (
    DEFAULT_COMFORT_WEIGHT,
    HEATING_SYSTEM_PROFILES,
    HEATING_SYSTEM_RADIATOR,
    MIN_POWER_FRACTION,
    MODE_COOLING,
    MODE_HEATING,
    MODE_IDLE,
    SLOW_SYSTEM_START_PENALTY,
)
from .residual_heat import advance_rebound, compute_residual_heat, get_min_run_blocks, mean_rebound
from .thermal_model import RCModel

# Base lookahead for per-block decision cost evaluation. Radiator / unknown
# systems stay at this value; systems with long thermal time constants scale up.
LOOKAHEAD_BASE_BLOCKS = 6
# How many tau time-constants to include in the lookahead beyond min_run. Set to
# 1.0 so UFH lookahead (24 blocks = 120 min) matches the outer horizon minimum,
# avoiding silent clamping. See issue #131.
LOOKAHEAD_HORIZON_SCALE = 1.0
# A pre-heat must reach a rising heat target within this margin at the block it starts.
PREHEAT_DEADLINE_MARGIN = 0.1
# A running pre-heat continues while waiting this long (1 h) would miss the target.
PREHEAT_CONTINUE_BLOCKS = 12
# Pre-heat lead at the default comfort weight; the slider scales it down to 0 at full efficiency.
PREHEAT_MAX_LEAD_HOURS = 12.0
# Predictions are clamped to [temp_min, temp_max], but never closer than this to where the
# room starts: a room already past a bound must still see which action moves it back.
CLAMP_HEADROOM_K = 5.0


def preheat_max_blocks(comfort_weight: float, dt_minutes: float = 5.0, *, enabled: bool = True) -> int | None:
    """Pre-heat lead the comfort/efficiency slider allows: the default and above
    plan up to the horizon, towards efficiency the lead shrinks to none.
    ``enabled`` is the room's pre-heat switch; off means no lead at all."""
    if not enabled:
        return 0
    if comfort_weight >= DEFAULT_COMFORT_WEIGHT:
        return None
    hours = PREHEAT_MAX_LEAD_HOURS * max(0.0, comfort_weight) / DEFAULT_COMFORT_WEIGHT
    return int(hours * 60 / dt_minutes)


def slow_start_penalty(min_run_blocks: int, dt_minutes: float = 5.0) -> float:
    """``MPCOptimizer.start_penalty`` for a run of *min_run_blocks*: only slow systems pay for starts.

    A minimum run longer than the default marks a slow heating system (UFH). Fast
    systems get a start hysteresis in the controller instead (#429).
    """
    return SLOW_SYSTEM_START_PENALTY if min_run_blocks > get_min_run_blocks("", dt_minutes) else 0.0


@dataclass
class MPCPlan:
    """Result of MPC optimization — a planned sequence of actions."""

    actions: list[str]
    temperatures: list[float]  # len = len(actions) + 1 (includes initial)
    dt_minutes: float = 5.0
    power_fractions: list[float] = field(default_factory=list)
    # Per-system decision lookahead used when building this plan. Exposed so
    # the controller's safety guard can align its horizon with the optimizer's.
    lookahead_blocks: int = LOOKAHEAD_BASE_BLOCKS
    # Blocks to the rising heat target the first block pre-heats for (0: none), so the
    # controller's guard looks that far ahead instead of overruling the pre-heat.
    preheat_blocks: int = 0

    def get_current_action(self) -> str:
        """Return the action for the current (first) time block."""
        if not self.actions:
            return MODE_IDLE
        return self.actions[0]

    def get_current_power_fraction(self) -> float:
        """Power fraction for the current block. Backward-compatible."""
        if not self.power_fractions:
            return 1.0 if self.actions and self.actions[0] != MODE_IDLE else 0.0
        return self.power_fractions[0]


def _rebound_step(charge: float | None, Q: float, dt_minutes: float) -> tuple[float | None, float | None]:
    """(q_rebound for this block, charge after it), like residual heat.

    The charge only decays: a planned run neither recharges it nor pulls the
    air down (the plan cannot represent the unit's own on/off cycling within a
    block). The rebound counts in idle blocks only; None stays None.
    """
    if charge is None:
        return None, None
    q_rebound = mean_rebound(charge, 0.0, dt_minutes) if Q == 0.0 else None
    return q_rebound, advance_rebound(charge, 0.0, dt_minutes)


@dataclass
class MPCOptimizer:
    """Dynamic Programming optimizer for heating/cooling control.

    Plans the optimal on/off schedule over a prediction horizon
    to minimize a weighted sum of temperature deviation and energy use.
    """

    model: RCModel
    can_heat: bool = True
    can_cool: bool = True
    w_comfort: float = 10.0
    w_energy: float = 1.0
    min_run_blocks: int = 2  # minimum 2 blocks (10 min) per run
    # Cooling always runs on an AC; None = same as min_run_blocks (heating profile)
    cool_min_run_blocks: int | None = None
    outdoor_cooling_min: float = 16.0
    outdoor_heating_max: float = 22.0
    temp_min: float = 5.0  # frost protection
    temp_max: float = 30.0  # overheat protection
    override_active: bool = False
    heating_system_type: str = ""  # key into HEATING_SYSTEM_PROFILES; "" = unknown
    approach_rate: float = 1.0  # fraction of remaining gap closed per block; 1.0 = legacy deadbeat
    # A heat-capable AC heats the room too, so the learned heating rate is not the screed's
    fast_heater_shares_model: bool = False
    start_penalty: float = 0.0  # comfort-weighted cost of starting a heating/cooling run (#429)
    # Longest pre-heat lead the deadline may plan (blocks); None = up to the horizon.
    preheat_max_blocks: int | None = None
    # Learned multiplier on the heating system's residual heat profile (ResidualHeatLearner)
    residual_scale: float = 1.0

    def __post_init__(self) -> None:
        # Set before optimize() runs so callers / patched optimize() still expose
        # a sensible default. optimize() refreshes this from dt_minutes per call.
        self._lookahead_blocks = LOOKAHEAD_BASE_BLOCKS

    def optimize(
        self,
        T_room: float,
        T_outdoor_series: list[float],
        heat_target_series: list[float],
        cool_target_series: list[float] | None = None,
        dt_minutes: float = 5.0,
        *,
        solar_series: list[float] | None = None,
        residual_series: list[float] | None = None,
        occupancy_series: list[float] | None = None,
        initial_mode: str = MODE_IDLE,
        rebound_charge: float | None = None,
        heat_run: tuple[float, float] | None = None,
    ) -> MPCPlan:
        """Find optimal action sequence over the planning horizon.

        Uses forward simulation with greedy optimization per block,
        considering minimum run time constraints.

        Accepts dual target series (heat_target_series + cool_target_series)
        for dead-band-aware optimization. If cool_target_series is None,
        it defaults to heat_target_series (single-target behavior).

        With ``start_penalty`` set, choosing an active mode the previous block did
        not run costs ``w_comfort * start_penalty``; ``initial_mode`` is the mode
        running when the plan is built, so continuing it in block 0 is free.

        ``rebound_charge`` is the AC rebound charge now (residual_heat); it
        decays over the plan and warms idle blocks, like ``residual_series``.
        None leaves the air/mass term out.

        ``heat_run`` is the heating run in progress as (minutes heated, power
        fraction), radiators only (``HEATING_SYSTEM_RADIATOR``). Stopping it leaves its stored heat in the radiators, so every
        hypothesis that ends heating sees that afterglow, and a run that can coast
        to the target on it stops early instead of overshooting. The plan tracks
        its own runs the same way: idle blocks after a planned run see that run's
        afterglow instead of ``residual_series`` (the real room's).
        """
        if cool_target_series is None:
            cool_target_series = list(heat_target_series)

        # Clamp inverted targets: cool must be >= heat
        cool_target_series = [max(h, c) for h, c in zip(heat_target_series, cool_target_series, strict=False)]

        # Per-system decision lookahead. UFH (tau=90min) scales up so the cost
        # function can see post-heating residual afterglow; radiator / "" stay
        # at LOOKAHEAD_BASE_BLOCKS for byte-identical behaviour. Hybrid UFH+AC
        # rooms (can_cool=True) also keep the base lookahead: extending the
        # horizon without a matching cooling-side synthesis would shift the
        # energy/comfort ratio for COOLING and cause more aggressive AC use.
        profile = HEATING_SYSTEM_PROFILES.get(self.heating_system_type) if self.heating_system_type else None
        if profile and dt_minutes > 0 and not self.can_cool:
            tau_blocks = math.ceil(profile["tau_minutes"] / dt_minutes)
            self._lookahead_blocks = max(
                LOOKAHEAD_BASE_BLOCKS,
                self.min_run_blocks + math.ceil(LOOKAHEAD_HORIZON_SCALE * tau_blocks),
            )
        else:
            self._lookahead_blocks = LOOKAHEAD_BASE_BLOCKS

        n_blocks = min(len(T_outdoor_series), len(heat_target_series), len(cool_target_series))
        if n_blocks == 0 or not math.isfinite(T_room):
            return MPCPlan(actions=[], temperatures=[T_room], dt_minutes=dt_minutes)

        q_solar = solar_series or [0.0] * n_blocks
        q_residual = residual_series or [0.0] * n_blocks
        q_occupancy = occupancy_series or [0.0] * n_blocks

        actions: list[str] = []
        temp_lo, temp_hi = self._temp_bounds(T_room)
        temperatures: list[float] = [T_room]
        power_fractions: list[float] = []
        current_temp = T_room
        current_mode = MODE_IDLE
        blocks_in_mode = 0
        last_action = initial_mode
        charge = rebound_charge
        preheat_blocks = 0
        # Heating run in progress in the plan (minutes, pf), and the last one it stopped (radiators)
        run = heat_run if initial_mode == MODE_HEATING and self._radiator else None
        glow: tuple[float, float] | None = None
        glow_elapsed = 0.0
        # UFH keeps its own pre-heat (longer lookahead with synthesized afterglow): heating
        # a screed until the air reaches the target overshot by the stored heat.
        slow_heat = self.min_run_blocks > get_min_run_blocks("", dt_minutes)

        for i in range(n_blocks):
            T_out = T_outdoor_series[i]
            heat_tgt = heat_target_series[i]
            cool_tgt = cool_target_series[i]
            qs = q_solar[i] if i < len(q_solar) else 0.0
            qr = q_residual[i] if i < len(q_residual) else 0.0
            if glow is not None:
                qr = self._afterglow(glow_elapsed, glow)
            qo = q_occupancy[i] if i < len(q_occupancy) else 0.0

            # Determine available actions this block
            available = [MODE_IDLE]
            if self.can_heat and not self._is_outdoor_gated(MODE_HEATING, T_out):
                available.append(MODE_HEATING)
            if self.can_cool and not self._is_outdoor_gated(MODE_COOLING, T_out):
                available.append(MODE_COOLING)

            # If in a run and below min_run_blocks, must continue
            forced = current_mode != MODE_IDLE and blocks_in_mode < self._min_run_for(current_mode)
            if forced:
                if current_mode in available:
                    best_action = current_mode
                else:
                    best_action = MODE_IDLE  # forced off by constraint
            else:
                # Evaluate each action: look ahead to find best
                best_action = MODE_IDLE
                best_cost = float("inf")
                future_solar = q_solar[i:] if q_solar else None
                future_residual = q_residual[i:] if q_residual else None
                if glow is not None:
                    # A run the plan stopped earlier: its afterglow replaces the real room's
                    future_residual = [
                        self._afterglow(glow_elapsed + j * dt_minutes, glow) for j in range(self._lookahead_blocks)
                    ]
                future_occupancy = q_occupancy[i:] if q_occupancy else None
                for action in available:
                    cost = self._evaluate_action(
                        action,
                        current_temp,
                        T_out,
                        heat_tgt,
                        cool_tgt,
                        T_outdoor_series[i:],
                        heat_target_series[i:],
                        cool_target_series[i:],
                        dt_minutes,
                        future_solar=future_solar,
                        future_residual=future_residual,
                        future_occupancy=future_occupancy,
                        rebound_charge=charge,
                        heat_run=run,
                    )
                    if self.start_penalty and action == MODE_HEATING and last_action != MODE_HEATING:
                        cost += self.w_comfort * self.start_penalty
                    if cost < best_cost:
                        best_cost = cost
                        best_action = action

            deadline = 0
            if best_action != MODE_HEATING and MODE_HEATING in available and not slow_heat:
                deadline = self._preheat_deadline(
                    i,
                    current_temp,
                    T_outdoor_series,
                    heat_target_series,
                    dt_minutes,
                    q_solar=q_solar,
                    q_occupancy=q_occupancy,
                    continuing=last_action == MODE_HEATING,
                )
                if deadline:
                    best_action = MODE_HEATING
                    if i == 0:
                        preheat_blocks = deadline

            # Compute proportional power fraction for this block
            # Use heat target for heating power, cool target for cooling power
            pf_target = heat_tgt if best_action == MODE_HEATING else cool_tgt
            pf, pf_mode = self.compute_optimal_power(
                current_temp,
                T_out,
                pf_target,
                dt_minutes,
                q_solar=qs,
                q_residual=qr,
                q_occupancy=qo,
                rebound_charge=charge,
            )
            if best_action == MODE_IDLE:
                pf = 0.0
            elif deadline:
                pf = 1.0
            elif forced and (pf_mode != best_action or pf == 0.0):
                # Past the target inside the min run: the controller continues at gentle
                # power, so the plan must not show a full-power run (a phantom 1-3 K
                # overshoot that the cover logic and the prediction line read).
                horizon = slice(i, i + self._lookahead_blocks)
                strict = (
                    max(heat_target_series[horizon])
                    if best_action == MODE_HEATING
                    else min(cool_target_series[horizon])
                )
                pf, pf_mode = self.compute_optimal_power(
                    current_temp,
                    T_out,
                    strict,
                    dt_minutes,
                    q_solar=qs,
                    q_residual=qr,
                    q_occupancy=qo,
                    rebound_charge=charge,
                )
                pf = max(pf, MIN_POWER_FRACTION) if pf_mode == best_action else MIN_POWER_FRACTION
            elif pf_mode != best_action:
                # compute_optimal_power found no demand in this block's direction: the
                # deviation is smaller than the energy bias, or the room needs this
                # direction only later (look-ahead). Its fraction is then 0.0 or belongs to
                # the other direction, so it is not used. Heating runs at full power, which
                # pre-heating slow systems relies on. Cooling aims at the strictest target
                # ahead (pre-cooling), else runs at the minimum, because full power would
                # drive an AC to its lowest setpoint.
                if best_action == MODE_HEATING:
                    pf = 1.0
                else:
                    pf, pf_mode = self.compute_optimal_power(
                        current_temp,
                        T_out,
                        min(cool_target_series[i : i + self._lookahead_blocks]),
                        dt_minutes,
                        q_solar=qs,
                        q_residual=qr,
                        q_occupancy=qo,
                        rebound_charge=charge,
                    )
                    pf = max(pf, MIN_POWER_FRACTION) if pf_mode == MODE_COOLING else MIN_POWER_FRACTION

            # Apply action with proportional Q for accurate forward prediction
            if best_action == MODE_HEATING:
                Q = pf * self.model.Q_heat
            elif best_action == MODE_COOLING:
                Q = -(pf * self.model.Q_cool)
            else:
                Q = 0.0
            if best_action == MODE_HEATING:
                if self._radiator:
                    # At full power like the tracker's runs (the stored heat follows the run length)
                    run = ((run[0] if run else 0.0) + dt_minutes, 1.0)
                    # A restart at low power cannot cool the radiator faster than its afterglow
                    Q = max(Q, self.model.Q_heat * qr)
                glow = None
            else:
                if run is not None:
                    glow, glow_elapsed, run = run, 0.0, None
                if glow is not None:
                    qr = self._afterglow(glow_elapsed, glow)
                    glow_elapsed += dt_minutes
            qb, charge = _rebound_step(charge, Q, dt_minutes)
            next_temp = self.model.predict(
                current_temp,
                T_out,
                Q,
                dt_minutes,
                q_solar=qs,
                q_residual=qr if Q == 0.0 else 0.0,
                q_occupancy=qo,
                q_rebound=qb,
            )
            next_temp = max(temp_lo, min(next_temp, temp_hi))

            last_action = best_action
            actions.append(best_action)
            temperatures.append(round(next_temp, 2))
            power_fractions.append(round(pf, 3))

            # Track run length
            if best_action == current_mode:
                blocks_in_mode += 1
            else:
                current_mode = best_action
                blocks_in_mode = 1

            current_temp = next_temp

        return MPCPlan(
            actions=actions,
            temperatures=temperatures,
            dt_minutes=dt_minutes,
            power_fractions=power_fractions,
            lookahead_blocks=self._lookahead_blocks,
            preheat_blocks=preheat_blocks,
        )

    def _preheat_deadline(
        self,
        i: int,
        T_room: float,
        T_outdoor_series: list[float],
        heat_target_series: list[float],
        dt_minutes: float,
        *,
        q_solar: list[float],
        q_occupancy: list[float],
        continuing: bool = False,
    ) -> int:
        """Blocks from *i* to the rising heat target that waiting would miss.

        The greedy decision only looks ``_lookahead_blocks`` ahead, so a schedule block
        further away stayed invisible until shortly before it and a room with a radiator
        sized to its heat load started too late. Waits one block, then heats at full
        power: if that misses a later, higher heat target, the pre-heat starts now
        (as late as possible). A run already heating keeps going while waiting
        ``PREHEAT_CONTINUE_BLOCKS`` (at least the min run) would miss: re-checking a
        single block switched it off and on at the edge, and a plain "heat until the
        coming target" turned every eco-holding run into a pre-heat hours early.
        0 when no such target exists.
        """
        n = len(heat_target_series)
        now = heat_target_series[i]
        if self.preheat_max_blocks is not None:
            n = min(n, i + self.preheat_max_blocks + 1)
        rise = next((j for j in range(i + 1, n) if heat_target_series[j] > max(now, T_room)), None)
        if rise is None:
            return 0
        wait = max(PREHEAT_CONTINUE_BLOCKS, self.min_run_blocks) if continuing else 1
        T = T_room
        for j in range(i, n - 1):
            Q = 0.0 if j < i + wait else self.model.Q_heat
            T = self.model.predict(
                T,
                T_outdoor_series[j],
                Q,
                dt_minutes,
                q_solar=q_solar[j] if j < len(q_solar) else 0.0,
                q_occupancy=q_occupancy[j] if j < len(q_occupancy) else 0.0,
            )
            target = heat_target_series[j + 1]
            if target > now and T < target - PREHEAT_DEADLINE_MARGIN:
                return j + 1 - i
        return 0

    def simulate_plan(
        self,
        plan: MPCPlan,
        T_room: float,
        T_outdoor_series: list[float],
        dt_minutes: float,
        *,
        solar_series: list[float] | None = None,
        residual_series: list[float] | None = None,
        occupancy_series: list[float] | None = None,
        rebound_charge: float | None = None,
    ) -> list[float]:
        """Replay a plan's actions under different disturbance series.

        Answers "what would this plan have produced without X" without
        re-optimizing, so a caller interested in one disturbance (the cover
        logic, which only cares about solar overheating) can read a temperature
        trajectory that excludes the others. Mirrors the forward step of
        :meth:`optimize` exactly, including the residual-heat suppression while
        active power flows and the physical clamp.
        """
        n_blocks = min(len(plan.actions), len(T_outdoor_series))
        q_solar = solar_series or [0.0] * n_blocks
        q_residual = residual_series or [0.0] * n_blocks
        q_occupancy = occupancy_series or [0.0] * n_blocks

        temp_lo, temp_hi = self._temp_bounds(T_room)
        temperatures: list[float] = [T_room]
        current_temp = T_room
        charge = rebound_charge
        for i in range(n_blocks):
            pf = plan.power_fractions[i] if i < len(plan.power_fractions) else 0.0
            action = plan.actions[i]
            if action == MODE_HEATING:
                Q = pf * self.model.Q_heat
            elif action == MODE_COOLING:
                Q = -(pf * self.model.Q_cool)
            else:
                Q = 0.0
            qs = q_solar[i] if i < len(q_solar) else 0.0
            qr = q_residual[i] if i < len(q_residual) else 0.0
            qo = q_occupancy[i] if i < len(q_occupancy) else 0.0
            qb, charge = _rebound_step(charge, Q, dt_minutes)
            next_temp = self.model.predict(
                current_temp,
                T_outdoor_series[i],
                Q,
                dt_minutes,
                q_solar=qs,
                q_residual=qr if Q == 0.0 else 0.0,
                q_occupancy=qo,
                q_rebound=qb,
            )
            next_temp = max(temp_lo, min(next_temp, temp_hi))
            temperatures.append(round(next_temp, 2))
            current_temp = next_temp
        return temperatures

    def _evaluate_action(
        self,
        action: str,
        T_room: float,
        T_outdoor: float,
        heat_target: float,
        cool_target: float,
        future_T_outdoor: list[float],
        future_heat_targets: list[float],
        future_cool_targets: list[float],
        dt_minutes: float,
        *,
        future_solar: list[float] | None = None,
        future_residual: list[float] | None = None,
        future_occupancy: list[float] | None = None,
        rebound_charge: float | None = None,
        heat_run: tuple[float, float] | None = None,
    ) -> float:
        """Evaluate the cost of taking an action, looking a few steps ahead.

        Per-system lookahead (self._lookahead_blocks) extends the window for
        slow heating systems. For UFH, the HEATING hypothesis synthesizes its
        own post-heating residual afterglow so the cost function values the
        sustained-comfort benefit of pre-heating. Radiator / "" lookahead stays
        at LOOKAHEAD_BASE_BLOCKS.

        Radiators only: with a heating run in progress (``heat_run``, see
        :meth:`optimize`), the hypotheses that stop it see its afterglow. A HEATING
        hypothesis sees the afterglow of its own run after the min run, so
        a radiator run is judged by where its stored heat takes the room.
        """
        lookahead = min(self._lookahead_blocks, len(future_T_outdoor))
        Q = self._action_to_Q(action)
        total_cost = 0.0
        T = T_room
        temp_lo, temp_hi = self._temp_bounds(T_room)
        solar = future_solar or []
        residual = future_residual or []
        occupancy = future_occupancy or []
        synthesis_enabled = (
            action == MODE_HEATING
            and self._lookahead_blocks > LOOKAHEAD_BASE_BLOCKS
            and self.min_run_blocks > 0
            and bool(self.heating_system_type)
        )
        heating_duration_minutes = self.min_run_blocks * dt_minutes
        run_blocks = self._min_run_for(action)
        stop_glow = heat_run if action != MODE_HEATING and self._radiator else None
        if action != MODE_IDLE and not synthesis_enabled:
            Q *= self._hypothesis_power_fraction(
                action,
                T_room,
                T_outdoor,
                heat_target if action == MODE_HEATING else cool_target,
                dt_minutes,
                q_solar=solar[0] if solar else 0.0,
                q_residual=residual[0] if residual else 0.0,
                q_occupancy=occupancy[0] if occupancy else 0.0,
                rebound_charge=rebound_charge,
            )

        charge = rebound_charge
        synth_pf_sum = 0.0
        for j in range(lookahead):
            qs = solar[j] if j < len(solar) else 0.0
            qo = occupancy[j] if j < len(occupancy) else 0.0
            # Simulate HVAC for the mode's min run (not just 1 block) to correctly
            # value sustained heating/cooling over the lookahead horizon.
            block_Q = Q if j < run_blocks else 0.0
            if synthesis_enabled and self.fast_heater_shares_model and j < run_blocks:
                # The learned heating rate is shared with a fast split (beta_h ~10 K/h):
                # at full power for the whole UFH min run plus afterglow that looked like
                # a 4 K overshoot, idle won and the room sat 2 K below target for hours.
                # Judge the run at the proportional power the controller recomputes every
                # cycle instead. Pure UFH rooms keep the full-power run (on/off actuators,
                # a rate learned from the screed alone).
                h_j = future_heat_targets[j] if j < len(future_heat_targets) else heat_target
                pf_j, pf_mode = self.compute_optimal_power(
                    T,
                    future_T_outdoor[j],
                    h_j,
                    dt_minutes,
                    q_solar=qs,
                    q_occupancy=qo,
                    rebound_charge=charge,
                )
                pf_j = max(pf_j, MIN_POWER_FRACTION) if pf_mode == MODE_HEATING else MIN_POWER_FRACTION
                block_Q = Q * pf_j
                synth_pf_sum += pf_j
            # Residual for the idle / post-run blocks. For the HEATING
            # hypothesis on a gated slow system, synthesize the afterglow this
            # hypothetical run would generate; otherwise fall back to the
            # controller-provided current-state decay.
            if synthesis_enabled and j >= self.min_run_blocks:
                elapsed = (j - self.min_run_blocks) * dt_minutes
                qr = compute_residual_heat(
                    elapsed,
                    self.heating_system_type,
                    last_power_fraction=(synth_pf_sum / max(run_blocks, 1) if self.fast_heater_shares_model else 1.0),
                    heating_duration_minutes=heating_duration_minutes,
                )
            elif stop_glow is not None:
                qr = self._afterglow(j * dt_minutes, stop_glow)
            elif action == MODE_HEATING and self._radiator and j >= run_blocks:
                own_run = ((heat_run[0] if heat_run else 0.0) + run_blocks * dt_minutes, 1.0)
                qr = max(
                    self._afterglow((j - run_blocks) * dt_minutes, own_run),
                    residual[j] if j < len(residual) else 0.0,
                )
            else:
                qr = residual[j] if j < len(residual) else 0.0
            if action == MODE_HEATING and block_Q > 0.0 and self._radiator:
                # A low-power run still delivers at least the afterglow (see optimize)
                block_Q = max(block_Q, self.model.Q_heat * qr)
            qb, charge = _rebound_step(charge, block_Q, dt_minutes)
            T = self.model.predict(
                T,
                future_T_outdoor[j],
                block_Q,
                dt_minutes,
                q_solar=qs,
                q_residual=qr if block_Q == 0.0 else 0.0,
                q_occupancy=qo,
                q_rebound=qb,
            )
            # Clamp temperature in lookahead to prevent cost explosion
            # from implausible model predictions
            T = max(temp_lo, min(temp_hi, T))
            h_tgt = future_heat_targets[j] if j < len(future_heat_targets) else heat_target
            c_tgt = future_cool_targets[j] if j < len(future_cool_targets) else cool_target
            # Dead-band-aware comfort cost: zero inside the band
            if T < h_tgt:
                total_cost += self.w_comfort * (T - h_tgt) ** 2
            elif T > c_tgt:
                total_cost += self.w_comfort * (T - c_tgt) ** 2
            # else: inside dead band, no comfort cost
            # Energy cost: proportional to HVAC power for min_run blocks
            if j < run_blocks and action != MODE_IDLE:
                total_cost += self.w_energy * abs(Q) / 1000.0

        return total_cost

    def _hypothesis_power_fraction(
        self,
        action: str,
        T_room: float,
        T_outdoor: float,
        target: float,
        dt_minutes: float,
        *,
        q_solar: float,
        q_residual: float,
        q_occupancy: float,
        rebound_charge: float | None = None,
    ) -> float:
        """Power fraction a HEATING/COOLING decision would actually be applied with.

        ``optimize`` applies the closed-form proportional power, so the candidate is
        judged at that power. Judging it at full power made a strong device (large
        learned Q, e.g. an AC heating the air node) look like it always overshoots, so
        idle won and the room sat below target. Without a proportional answer for
        this block (already at target, pre-heating for a later target) the candidate
        keeps full power as before.
        """
        pf, mode = self.compute_optimal_power(
            T_room,
            T_outdoor,
            target,
            dt_minutes,
            q_solar=q_solar,
            q_residual=q_residual,
            q_occupancy=q_occupancy,
            rebound_charge=rebound_charge,
        )
        return pf if mode == action and pf > 0.0 else 1.0

    def _temp_bounds(self, T_start: float) -> tuple[float, float]:
        """Clamp range for predictions that start at *T_start*.

        A fixed 30 °C ceiling made a room above it invisible to the cost: every
        hypothesis that could not bring it below 30 within the lookahead clamped to
        the same value at every block, idle won the tie, and a weak AC stayed off
        while the room heated further.
        """
        return min(self.temp_min, T_start - CLAMP_HEADROOM_K), max(self.temp_max, T_start + CLAMP_HEADROOM_K)

    @property
    def _radiator(self) -> bool:
        """Learned residual heat and the early stop apply to radiator rooms only."""
        return self.heating_system_type == HEATING_SYSTEM_RADIATOR

    def _afterglow(self, elapsed_minutes: float, run: tuple[float, float]) -> float:
        """Residual heat fraction *elapsed_minutes* after a run of (minutes, power fraction) stopped."""
        minutes, pf = run
        return compute_residual_heat(elapsed_minutes, self.heating_system_type, pf, minutes, self.residual_scale)

    def _min_run_for(self, mode: str) -> int:
        """Minimum run in blocks for *mode*."""
        if mode == MODE_COOLING and self.cool_min_run_blocks is not None:
            return self.cool_min_run_blocks
        return self.min_run_blocks

    def _action_to_Q(self, action: str) -> float:
        if action == MODE_HEATING:
            return self.model.Q_heat
        if action == MODE_COOLING:
            return -self.model.Q_cool
        return 0.0

    def _is_outdoor_gated(self, mode: str, T_outdoor: float) -> bool:
        if self.override_active:
            return False
        if mode == MODE_COOLING and T_outdoor < self.outdoor_cooling_min:
            return True
        if mode == MODE_HEATING and T_outdoor > self.outdoor_heating_max:
            return True
        return False

    def compute_optimal_power(
        self,
        T_room: float,
        T_outdoor: float,
        target: float,
        dt_minutes: float,
        *,
        q_solar: float = 0.0,
        q_residual: float = 0.0,
        q_occupancy: float = 0.0,
        rebound_charge: float | None = None,
    ) -> tuple[float, str]:
        """Analytical closed-form optimal heating/cooling power.

        With ``rebound_charge`` the drift includes the AC rebound (residual_heat).

        Returns (power_fraction in [0,1], mode).
        """
        if not math.isfinite(T_room) or not math.isfinite(target):
            return 0.0, MODE_IDLE

        dt_h = dt_minutes / 60.0
        alpha = self.model.U
        if alpha < 0.01:
            beta = alpha * dt_h  # Euler approx for tiny alpha
        else:
            beta = 1.0 - math.exp(-alpha * dt_h)

        if beta < 1e-9:
            return 0.0, MODE_IDLE

        # Drift temperature: where the room would go with no HVAC
        T_drift = T_room + beta * (T_outdoor - T_room)
        # Add predicted solar gain to drift
        if alpha > 0.01:
            T_drift += beta * self.model.Q_solar * q_solar / alpha
        else:
            T_drift += self.model.Q_solar * q_solar * dt_h
        # Add residual heat from thermal mass to drift
        if q_residual > 0:
            if alpha > 0.01:
                T_drift += beta * self.model.Q_heat * q_residual / alpha
            else:
                T_drift += self.model.Q_heat * q_residual * dt_h
        # Add predicted occupancy gain to drift
        if q_occupancy > 0:
            if alpha > 0.01:
                T_drift += beta * self.model.Q_occupancy * q_occupancy / alpha
            else:
                T_drift += self.model.Q_occupancy * q_occupancy * dt_h
        # AC rebound: the air still warming back towards the building mass
        if rebound_charge is not None and rebound_charge > 0:
            fast = self.model.Q_fast * mean_rebound(rebound_charge, 0.0, dt_minutes)
            T_drift += beta * fast / alpha if alpha > 0.01 else fast * dt_h
        # Reference sub-target: close `approach_rate` of the remaining gap this block
        # instead of the whole gap (deadbeat). approach_rate=1.0 => T_ref == target =>
        # identical to the legacy formula. Smaller values widen the proportional band.
        # Holding power is preserved: at steady state (T_room == target) T_ref == target
        # for any approach_rate, so Q_required reduces to the holding power.
        T_ref = T_room + self.approach_rate * (target - T_room)
        Q_required = (T_ref - T_drift) * alpha / beta

        # Energy penalty: bias toward less power based on comfort/energy weights
        energy_bias = (self.w_energy / max(self.w_comfort, 0.01)) * alpha / beta * 0.1
        if Q_required > 0:
            Q_required = max(0.0, Q_required - energy_bias)
        elif Q_required < 0:
            Q_required = min(0.0, Q_required + energy_bias)

        if Q_required > 0 and self.can_heat and not self._is_outdoor_gated(MODE_HEATING, T_outdoor):
            frac = min(Q_required / max(self.model.Q_heat, 0.01), 1.0)
            return max(frac, MIN_POWER_FRACTION), MODE_HEATING
        elif Q_required < 0 and self.can_cool and not self._is_outdoor_gated(MODE_COOLING, T_outdoor):
            frac = min(abs(Q_required) / max(self.model.Q_cool, 0.01), 1.0)
            return max(frac, MIN_POWER_FRACTION), MODE_COOLING
        else:
            return 0.0, MODE_IDLE
