/**
 * Store-layer limit helpers shared by the room card and the settings form.
 *
 * The consent band (per-side never-below/never-above), the max deviation
 * (swing) and the price-gap gate work on two levels: global defaults in
 * settings and optional per-room overrides; a blank (null) override means
 * "inherit the global value" — the exact semantics TouManager.make_adjuster
 * applies server-side (room.get(...) else settings.get(...) else default).
 */
import type { TouLimits, TouRoomLimits } from "../types";

const KEYS: (keyof TouLimits)[] = [
  "heat_min",
  "heat_max",
  "cool_min",
  "cool_max",
  "swing",
  "store_gap",
];

/**
 * Fallback before the backend's `tou_limits` view arrives (or a room without
 * a stored setting): mirrors DEFAULT_TOU_* in const.py, the same values the
 * manager applies.
 */
export const DEFAULT_TOU_LIMITS: TouLimits = {
  heat_min: 17.0,
  heat_max: 28.0,
  cool_min: 18.0,
  cool_max: 30.0,
  swing: 3.0,
  store_gap: 1.0,
};

/** The limits actually in force for a room: each override wins per key. */
export function effectiveLimits(global: TouLimits, room: TouRoomLimits): TouLimits {
  const out = { ...global };
  for (const key of KEYS) {
    const v = room[key];
    if (typeof v === "number" && !Number.isNaN(v)) out[key] = v;
  }
  return out;
}
