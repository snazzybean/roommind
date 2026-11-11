import type { RoomConfig } from "../types";

/** Minutes one model update covers; mirrors EKF_UPDATE_MIN_DT (const.py). */
export const EKF_UPDATE_MINUTES = 3;

/**
 * Updates after which "learn faster" counts as faded (sim ekf-room-change): the heat-loss
 * variance is back within 1.2x after 20-31 updates, the heating power's after 45-120 in rooms
 * that heat daily (it waits for heating runs), so 120 updates (~6 h of learning).
 */
export const BOOST_FADE_UPDATES = 120;

export type LearningState =
  "outdoor" | "paused" | "waiting" | "no_data" | "learning" | "ready" | "managed" | "simple";

/** Only outdoor areas never train; Managed rooms learn on the device reading. */
export function roomLearns(config: RoomConfig): boolean {
  return !config.is_outdoor;
}

/** Area ids of the rooms that learn; stale ids of deleted rooms are not among them. */
export function learningRoomIds(rooms: Record<string, RoomConfig>): string[] {
  return Object.entries(rooms)
    .filter(([, config]) => roomLearns(config))
    .map(([id]) => id);
}

/**
 * "ready" is the backend's MPC gate (`mpc_active`: 5-min forecast within 0.5 °C plus enough
 * idle and heating/cooling updates), not a confidence threshold: confidence is a separate
 * figure and the controller can run MPC well below 80 %. Managed rooms and simple on/off
 * control learn without ever controlling by the model.
 */
export function learningState(
  config: RoomConfig,
  paused: boolean,
  controlMode: "mpc" | "bangbang" = "mpc",
): LearningState {
  if (!roomLearns(config)) return "outdoor";
  if (paused) return "paused";
  const live = config.live;
  if (live?.learning_paused_reason) return "waiting";
  if (!live?.n_observations) return "no_data";
  if (!config.temperature_sensor) return "managed";
  if (live.mpc_active) return "ready";
  if (controlMode === "bangbang") return "simple";
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
