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
