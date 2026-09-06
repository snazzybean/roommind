import { HomeAssistant } from "../types";

export function usesFahrenheit(hass: HomeAssistant): boolean {
  return hass.config?.unit_system?.temperature === "°F";
}

export function tempUnit(hass: HomeAssistant): string {
  return usesFahrenheit(hass) ? "°F" : "°C";
}

export function toDisplay(celsius: number, hass: HomeAssistant): number {
  return usesFahrenheit(hass) ? (celsius * 9) / 5 + 32 : celsius;
}

export function toCelsius(display: number, hass: HomeAssistant): number {
  return usesFahrenheit(hass) ? ((display - 32) * 5) / 9 : display;
}

export function toDisplayDelta(celsiusDelta: number, hass: HomeAssistant): number {
  return usesFahrenheit(hass) ? (celsiusDelta * 9) / 5 : celsiusDelta;
}

export function formatTemp(celsius: number, hass: HomeAssistant, decimals = 1): string {
  return toDisplay(celsius, hass).toFixed(decimals);
}

export function tempStep(hass: HomeAssistant): string {
  return usesFahrenheit(hass) ? "1" : "0.5";
}

export function tempRange(
  minC: number,
  maxC: number,
  hass: HomeAssistant,
): { min: string; max: string } {
  return {
    min: String(Math.round(toDisplay(minC, hass))),
    max: String(Math.round(toDisplay(maxC, hass))),
  };
}

/**
 * Plausibility bounds for room target temperatures (°C).
 * Mirrors MIN_TARGET_TEMP/MAX_TARGET_TEMP in the backend's const.py — schedule
 * block temps outside this range are ignored there (#395), so the panel must
 * not present them as the active target either.
 */
export const MIN_TARGET_TEMP_C = 5;
export const MAX_TARGET_TEMP_C = 35;

/** True when a schedule block temperature (in HA display units) is usable. */
export function isPlausibleTargetTemp(displayValue: unknown, hass: HomeAssistant): boolean {
  const num = Number(displayValue);
  if (!Number.isFinite(num)) return false;
  const celsius = toCelsius(num, hass);
  return celsius >= MIN_TARGET_TEMP_C && celsius <= MAX_TARGET_TEMP_C;
}
