import type { HomeAssistant } from "../types";
import { localize } from "./localize";
import { serverNow } from "./server-clock";

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

const NBSP = "\u00a0";

function count(value: number, language: string, maxDecimals = 0): string {
  return new Intl.NumberFormat(language, { maximumFractionDigits: maxDecimals }).format(value);
}

// Intl's unit names differ per locale ("Std.", "hr", "m") and Intl.DurationFormat is too
// new, so the number comes from Intl and the unit from the locale keys.
function joined(text: string): string {
  return text.replace(/ /g, NBSP);
}

/** Whole minutes as "45 min", "2 h" or "1 h 59 min" in the user's language. */
export function formatMinutes(minutes: number, language: string): string {
  const total = Math.max(0, Math.round(minutes));
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (h === 0) return joined(localize("duration.minutes", language, { n: count(m, language) }));
  if (m === 0) return joined(localize("duration.hours", language, { n: count(h, language) }));
  return joined(
    localize("duration.hours_minutes", language, {
      h: count(h, language),
      m: count(m, language),
    }),
  );
}

/** Hours with at most one decimal ("1,9 h"), below an hour in minutes ("45 min"). */
export function formatHours(hours: number, language: string): string {
  if (hours > 0 && hours < 1) return formatMinutes(hours * 60, language);
  return joined(localize("duration.hours", language, { n: count(hours, language, 1) }));
}

/** Time left until `until` (Unix seconds), rounded up to whole minutes; "" once it passed. */
export function formatRemaining(until: number, language: string, now = serverNow() / 1000): string {
  const left = until - now;
  return left > 0 ? formatMinutes(Math.ceil(left / 60), language) : "";
}

/** How long ago `ts` (Unix seconds) was: "vor 3 Minuten", "2 hours ago"; at least a minute. */
export function formatAgo(ts: number, language: string, now = serverNow() / 1000): string {
  const minutes = Math.max(1, Math.floor((now - ts) / 60));
  const rtf = new Intl.RelativeTimeFormat(language, { numeric: "always" });
  if (minutes < 60) return rtf.format(-minutes, "minute");
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return rtf.format(-hours, "hour");
  return rtf.format(-Math.floor(hours / 24), "day");
}
