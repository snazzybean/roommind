/**
 * Days and times on the analytics page in Home Assistant's time zone, the zone the backend
 * cuts its days in (rhythm rows, "today"). One day format for the whole page.
 */
import type { HomeAssistant } from "../types";

const DAY_MS = 86_400_000;

/** HA's time zone when the browser knows it, else undefined (the browser's own). */
export function haTimeZone(hass: Pick<HomeAssistant, "config"> | undefined): string | undefined {
  const zone = hass?.config?.time_zone;
  if (!zone) return undefined;
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: zone });
    return zone;
  } catch {
    return undefined;
  }
}

function parts(ms: number, timeZone: string | undefined) {
  const out: Record<string, number> = {};
  for (const p of new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(ms)) {
    if (p.type !== "literal") out[p.type] = Number(p.value);
  }
  return out;
}

/** Offset of the zone from UTC at `ms`, in ms. */
function zoneOffset(ms: number, timeZone: string | undefined): number {
  const p = parts(ms, timeZone);
  const asUtc = Date.UTC(p.year, p.month - 1, p.day, p.hour % 24, p.minute, p.second);
  return asUtc - Math.floor(ms / 1000) * 1000;
}

/** "2026-11-11" for the day `ms` falls on in the zone. */
export function isoDateInZone(ms: number, timeZone: string | undefined): string {
  const p = parts(ms, timeZone);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${p.year}-${pad(p.month)}-${pad(p.day)}`;
}

/** Midnight of an ISO date in the zone, as epoch ms. */
export function startOfDayInZone(isoDate: string, timeZone: string | undefined): number {
  const [y, m, d] = isoDate.split("-").map(Number);
  const guess = Date.UTC(y, m - 1, d);
  const first = guess - zoneOffset(guess, timeZone);
  // Second pass: the offset at midnight itself (a DST switch between guess and midnight)
  return guess - zoneOffset(first, timeZone);
}

/** The last `days` days up to now: midnight `days - 1` days ago until now. */
export function quickRange(
  days: number,
  timeZone: string | undefined,
  now = Date.now(),
): { start: number; end: number } {
  const today = isoDateInZone(now, timeZone);
  // Noon of today minus whole days lands on the right date across DST switches
  const startDay = isoDateInZone(
    startOfDayInZone(today, timeZone) + DAY_MS / 2 - (days - 1) * DAY_MS,
    timeZone,
  );
  return { start: startOfDayInZone(startDay, timeZone), end: now };
}

/** True when both instants fall on the same day in the zone. */
export function sameDayInZone(a: number, b: number, timeZone: string | undefined): boolean {
  return isoDateInZone(a, timeZone) === isoDateInZone(b, timeZone);
}

/** "11. Nov." – the one day format of the analytics page. */
export function formatDay(ms: number, language: string, timeZone: string | undefined): string {
  return new Intl.DateTimeFormat(language, { day: "numeric", month: "short", timeZone }).format(ms);
}

/** "14:20" */
export function formatClock(ms: number, language: string, timeZone: string | undefined): string {
  return new Intl.DateTimeFormat(language, { hour: "2-digit", minute: "2-digit", timeZone }).format(
    ms,
  );
}

/** "11. Nov., 14:20" */
export function formatDayTime(ms: number, language: string, timeZone: string | undefined): string {
  return new Intl.DateTimeFormat(language, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone,
  }).format(ms);
}

/** A calendar date ("2026-11-11") in the user's language, independent of any zone. */
export function formatIsoDay(
  isoDate: string,
  language: string,
  options: Intl.DateTimeFormatOptions = { day: "numeric", month: "short" },
): string {
  const [y, m, d] = isoDate.split("-").map(Number);
  return new Intl.DateTimeFormat(language, { ...options, timeZone: "UTC" }).format(
    Date.UTC(y, m - 1, d, 12),
  );
}

/** Days of each quick range of the toolbar ("24h" is today since midnight). */
export const QUICK_RANGE_DAYS: Record<string, number> = { "24h": 1, "2d": 2, "7d": 7, "30d": 30 };
