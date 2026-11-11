import type { HomeAssistant } from "../types";

/** Number in the user's language (decimal comma in German). */
export function formatNumber(
  value: number,
  hass: Pick<HomeAssistant, "language">,
  minDecimals = 0,
  maxDecimals = minDecimals,
): string {
  return new Intl.NumberFormat(hass.language, {
    minimumFractionDigits: minDecimals,
    maximumFractionDigits: maxDecimals,
  }).format(value);
}

/** 0-100 as a percentage in the user's language ("48 %" in German, "48%" in English). */
export function formatPercent(value: number, hass: Pick<HomeAssistant, "language">): string {
  return new Intl.NumberFormat(hass.language, {
    style: "percent",
    maximumFractionDigits: 0,
  }).format(value / 100);
}

/** Duration in the user's language: minutes below an hour, else hours with at most one decimal. */
export function formatHours(hours: number, hass: Pick<HomeAssistant, "language">): string {
  const minutes = hours > 0 && hours < 1;
  const text = new Intl.NumberFormat(hass.language, {
    style: "unit",
    unit: minutes ? "minute" : "hour",
    unitDisplay: "short",
    maximumFractionDigits: minutes ? 0 : 1,
  }).format(minutes ? Math.round(hours * 60) : hours);
  // Some locales put a plain space between number and unit ("1,4 Std."); keep them on one line
  return text.replace(/ /g, "\u00a0");
}
