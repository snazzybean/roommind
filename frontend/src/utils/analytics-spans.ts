import type { AnalyticsDataPoint } from "../types";

/** Same cap as MAX_SAMPLE_GAP_S in analytics_stats.py: a sample counts until the next one. */
export const MAX_SAMPLE_GAP_MS = 900_000;

/**
 * Time spans (ms) where `on` holds, each sample held until the next one (at most
 * MAX_SAMPLE_GAP_MS), the rule the chart's event bands follow. Points may come unsorted
 * (history plus detail).
 */
export function timeSpans(
  points: readonly AnalyticsDataPoint[],
  on: (p: AnalyticsDataPoint) => boolean,
): Array<[number, number]> {
  const sorted = [...points].sort((a, b) => a.ts - b.ts);
  const spans: Array<[number, number]> = [];
  sorted.forEach((p, i) => {
    if (!on(p)) return;
    const start = p.ts * 1000;
    const next = sorted[i + 1];
    const end = next ? Math.min(next.ts * 1000, start + MAX_SAMPLE_GAP_MS) : start;
    const last = spans[spans.length - 1];
    if (last && start <= last[1]) last[1] = Math.max(last[1], end);
    else spans.push([start, end]);
  });
  return spans;
}
