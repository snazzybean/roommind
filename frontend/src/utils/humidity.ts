/**
 * Indoor humidity levels and how the analytics chart shows them.
 */
import type { AnalyticsDataPoint } from "../types";

// Indoor relative humidity: 40-60 % is the usual comfort range
export const HUMIDITY_LEVELS = { veryDry: 30, dry: 40, humid: 60, veryHumid: 70 };
// Fixed scale so the limits stay in view and days compare; it only widens for readings outside
const AXIS_MIN = 20;
const AXIS_MAX = 80;

export type HumidityLevel = "very_dry" | "dry" | "good" | "humid" | "very_humid";

export interface HumidityColors {
  good: string;
  fair: string;
  poor: string;
}

export function humidityLevel(rh: number): HumidityLevel {
  if (rh < HUMIDITY_LEVELS.veryDry) return "very_dry";
  if (rh < HUMIDITY_LEVELS.dry) return "dry";
  if (rh <= HUMIDITY_LEVELS.humid) return "good";
  if (rh <= HUMIDITY_LEVELS.veryHumid) return "humid";
  return "very_humid";
}

function humidityColor(rh: number, colors: HumidityColors): string {
  const level = humidityLevel(rh);
  if (level === "good") return colors.good;
  return level === "dry" || level === "humid" ? colors.fair : colors.poor;
}

/**
 * Colours the humidity line and the area under it by level. Pieces run along time, not value:
 * by value the area below a line at 50 % would show the 30-40 % strip as "dry". Bounds stay
 * finite, ECharts fails on infinite ones on a time axis.
 */
export function humidityVisualMap(
  seriesId: string,
  data: Array<[number, number]>,
  colors: HumidityColors,
) {
  const pieces: Array<Record<string, number | string>> = [];
  let start = data.length > 0 ? data[0][0] : 0;
  let current: string | null = null;
  for (const [ts, rh] of data) {
    const color = humidityColor(rh, colors);
    if (color === current) continue;
    if (current !== null) pieces.push({ gte: start, lt: ts, color: current });
    start = ts;
    current = color;
  }
  if (current !== null) pieces.push({ gte: start, lte: data[data.length - 1][0], color: current });
  // By id: ECharts keeps the series order of earlier renders, an index can point elsewhere
  return { type: "piecewise", show: false, seriesId, dimension: 0, pieces };
}

export function humidityAxis(
  points: AnalyticsDataPoint[],
  gridIndex: number,
): Record<string, unknown> {
  let min = AXIS_MIN;
  let max = AXIS_MAX;
  for (const p of points) {
    if (p.humidity == null) continue;
    min = Math.min(min, p.humidity);
    max = Math.max(max, p.humidity);
  }
  return {
    type: "value",
    gridIndex,
    min: Math.max(Math.floor(min / 20) * 20, 0),
    max: Math.min(Math.ceil(max / 20) * 20, 100),
    interval: 20,
    axisLabel: { formatter: "{value} %" },
  };
}
