/**
 * Mold prevention intensities and their target raise, same values as the backend
 * MOLD_PREVENTION_DELTAS in const.py.
 */
import type { HomeAssistant } from "../types";
import { formatNumber } from "./format";
import { localize } from "./localize";
import { tempUnit, toDisplayDelta } from "./temperature";

export const MOLD_INTENSITIES = ["light", "medium", "strong"] as const;
export type MoldIntensity = (typeof MOLD_INTENSITIES)[number];

const MOLD_PREVENTION_DELTAS: Record<MoldIntensity, number> = { light: 1, medium: 2, strong: 3 };

/** Target raise in °C; unknown values fall back to medium like the backend. */
export function moldPreventionDelta(intensity: string): number {
  return MOLD_PREVENTION_DELTAS[intensity as MoldIntensity] ?? MOLD_PREVENTION_DELTAS.medium;
}

/** The raise in the user's unit, e.g. "2" or "3.6". */
export function moldDeltaText(intensity: string, hass: HomeAssistant): string {
  return formatNumber(toDisplayDelta(moldPreventionDelta(intensity), hass), hass, 0, 1);
}

/** "Medium (+2 °C)". */
export function moldIntensityLabel(intensity: string, hass: HomeAssistant, lang: string): string {
  const key = (MOLD_INTENSITIES as readonly string[]).includes(intensity) ? intensity : "medium";
  return localize(`mold.intensity_${key as MoldIntensity}`, lang, {
    delta: moldDeltaText(intensity, hass),
    unit: tempUnit(hass),
  });
}
