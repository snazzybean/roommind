import type { RoomConfig } from "../types";

/** Minutes one model update covers; mirrors EKF_UPDATE_MIN_DT (const.py). */
export const EKF_UPDATE_MINUTES = 3;

/**
 * Updates after which "learn faster" counts as faded. Measured on a settled radiator room:
 * the boost multiplies the covariance by 2.5; the heat-loss figure is back after ~6 h, the
 * heating power ~1.3x after ~12 h (needs heating runs), so 250 updates (~12.5 h of learning).
 */
export const BOOST_FADE_UPDATES = 250;

/** Confidence from which the model counts as ready (the MPC gate passes around 80 %). */
export const MODEL_READY_CONFIDENCE = 0.8;

export type LearningState =
  "not_learning" | "paused" | "waiting" | "no_data" | "learning" | "ready";

/** Rooms that never train: no own temperature sensor (Managed) or an outdoor area. */
export function roomLearns(config: RoomConfig): boolean {
  return !!config.temperature_sensor && !config.is_outdoor;
}

export function learningState(config: RoomConfig, paused: boolean): LearningState {
  if (!roomLearns(config)) return "not_learning";
  if (paused) return "paused";
  const live = config.live;
  if (live?.learning_paused_reason) return "waiting";
  if (!live?.n_observations) return "no_data";
  if (live.mpc_active || (live.confidence ?? 0) >= MODEL_READY_CONFIDENCE) return "ready";
  return "learning";
}

/**
 * Whole hours until "learn faster" has faded, null when it is not running. The counter only
 * moves while the room learns (window closed, outdoor temperature known), so it is an estimate.
 * An anchor above the current count means the model was reset since: no boost.
 */
export function boostHoursLeft(
  appliedAt: number | null | undefined,
  observations: number | null | undefined,
): number | null {
  if (appliedAt == null || observations == null || observations < appliedAt) return null;
  const left = BOOST_FADE_UPDATES - (observations - appliedAt);
  if (left <= 0) return null;
  return Math.max(1, Math.ceil((left * EKF_UPDATE_MINUTES) / 60));
}
