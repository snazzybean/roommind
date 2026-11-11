/**
 * SVG paths for the small temperature curves (room card background, later the room hero).
 * Pure: no custom elements, usable by the dashboard card bundle too.
 */

/** `live.recent_temps` row: unix seconds, room temperature, target (may be null). */
export type RecentTemp = [number, number | null, number | null];

export interface SparklinePaths {
  /** Filled area under the temperature line, one closed subpath per stretch. */
  area: string;
  /** Temperature line, a new subpath after every gap. */
  line: string;
  /** Target as a step line; empty when no target is known. */
  target: string;
  /** Last temperature point (for an end dot), null without data. */
  last: { x: number; y: number } | null;
}

export interface SparklineOptions {
  width: number;
  height: number;
  /** Time window ending at the newest sample, seconds. */
  windowS?: number;
  /** Samples further apart than this split the curve, seconds. */
  maxGapS?: number;
  /** Smallest temperature span the height stands for (K); keeps sensor noise flat. */
  minSpanK?: number;
  /** Extra room above and below the data (K). */
  padK?: number;
}

export const SPARKLINE_WINDOW_S = 6 * 3600;
export const SPARKLINE_MAX_GAP_S = 15 * 60;

const f = (n: number) => (Math.round(n * 10) / 10).toString();

/** Paths for `points`, or null when there is nothing to draw. */
export function buildSparkline(
  points: readonly RecentTemp[] | null | undefined,
  opts: SparklineOptions,
): SparklinePaths | null {
  const windowS = opts.windowS ?? SPARKLINE_WINDOW_S;
  const maxGap = opts.maxGapS ?? SPARKLINE_MAX_GAP_S;
  const minSpan = opts.minSpanK ?? 2;
  const pad = opts.padK ?? 0.4;
  const { width: w, height: h } = opts;
  if (!points?.length) return null;

  const rows = [...points].filter((p) => Number.isFinite(p[0])).sort((a, b) => a[0] - b[0]);
  if (!rows.length) return null;
  const end = rows[rows.length - 1][0];
  const start = end - windowS;
  const inWindow = rows.filter((p) => p[0] >= start);
  const temps = inWindow.filter((p) => p[1] != null && Number.isFinite(p[1]));
  if (!temps.length) return null;

  const values: number[] = [];
  for (const p of inWindow) {
    if (p[1] != null && Number.isFinite(p[1])) values.push(p[1]);
    if (p[2] != null && Number.isFinite(p[2])) values.push(p[2]);
  }
  let lo = Math.min(...values) - pad;
  let hi = Math.max(...values) + pad;
  if (hi - lo < minSpan) {
    const mid = (hi + lo) / 2;
    lo = mid - minSpan / 2;
    hi = mid + minSpan / 2;
  }
  const X = (ts: number) => ((ts - start) / windowS) * w;
  const Y = (v: number) => h - ((v - lo) / (hi - lo)) * h;

  // Temperature: split into stretches at gaps.
  const stretches: RecentTemp[][] = [];
  for (const p of temps) {
    const cur = stretches[stretches.length - 1];
    if (cur && p[0] - cur[cur.length - 1][0] <= maxGap) cur.push(p);
    else stretches.push([p]);
  }
  let line = "";
  let area = "";
  for (const s of stretches) {
    const pts = s.map((p) => `${f(X(p[0]))},${f(Y(p[1] as number))}`);
    if (s.length === 1) {
      // A lone sample still shows as a short dash.
      const x = X(s[0][0]);
      const y = f(Y(s[0][1] as number));
      line += `M${f(Math.max(0, x - 2))},${y}L${f(x)},${y}`;
      continue;
    }
    line += `M${pts.join("L")}`;
    area += `M${pts[0].split(",")[0]},${h}L${pts.join("L")}L${pts[pts.length - 1].split(",")[0]},${h}Z`;
  }

  // Target: each value holds until the next sample; a null target or a gap breaks the line.
  let target = "";
  let prev: RecentTemp | null = null;
  for (const p of inWindow) {
    const t = p[2];
    const joined = prev !== null && p[0] - prev[0] <= maxGap;
    if (joined) target += `H${f(X(p[0]))}`;
    if (t == null || !Number.isFinite(t)) {
      prev = null;
      continue;
    }
    target += joined ? `V${f(Y(t))}` : `M${f(X(p[0]))},${f(Y(t))}`;
    prev = p;
  }

  const lastTemp = temps[temps.length - 1];
  return {
    area,
    line,
    target,
    last: { x: X(lastTemp[0]), y: Y(lastTemp[1] as number) },
  };
}
