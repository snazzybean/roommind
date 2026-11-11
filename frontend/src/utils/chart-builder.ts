/**
 * Pure functions to build ECharts series and options for analytics charts.
 */
import type { AnalyticsDataPoint } from "../types";
import { localize, type TranslationKey } from "./localize";
import { formatTemp, tempUnit, toDisplay, toDisplayDelta } from "./temperature";
import type { HomeAssistant } from "../types";
import { HUMIDITY_LEVELS, humidityAxis, humidityLevel } from "./humidity";
import { REASON_LABELS, TARGET_REASON_GROUPS, targetReasons } from "./target-reason";
import { MAX_SAMPLE_GAP_MS } from "./analytics-spans";

const FORECAST_MS = 3 * 3600_000;
const HUMIDITY_COLOR = "rgb(233, 30, 99)";
const CHART_HEIGHT = 300;
const MAIN_PLOT_HEIGHT = 252;
const MAIN_TOP = 22;
const PANEL_GAP = 24;
const PANEL_BOTTOM = 24;

/**
 * Plots below the temperature on the same time axis, each with its own scale (a second y axis
 * on the temperature would be ambiguous, an outdoor line on it squashes the room). A panel
 * shows while its series has data and is not hidden in the legend. A new panel = an entry
 * here plus its series tagged with `panel` in buildChartSeries.
 */
export type SubPanel = "outdoor" | "humidity" | "price";
export const SUB_PANELS: Record<SubPanel, { height: number; series: string }> = {
  outdoor: { height: 68, series: "outdoor_temp" },
  humidity: { height: 84, series: "humidity" },
  price: { height: 68, series: "price" },
};
export const SUB_PANEL_ORDER: readonly SubPanel[] = ["outdoor", "humidity", "price"];
// Neutral: the line and area take the level colours (priceVisualMap), gold is the price target
const PRICE_COLOR = "rgb(128, 128, 128)";
/** Mirrors COMFORT_TOLERANCE_K (analytics_stats): the summary counts this far outside as on target. */
const COMFORT_TOLERANCE_K = 0.5;
// Far past any axis: a one-sided band runs off the plot (series are clipped to the grid)
const BAND_OPEN_K = 100;
// The panels share an x axis, so both plots start at a fixed left edge instead of containLabel
const PANEL_LEFT = 56;
// Visible on light and dark cards alike
const NOW_MARKER_COLOR = "rgba(128, 128, 128, 0.6)";

export interface ChartBuildContext {
  hass: HomeAssistant;
  language: string;
  chartAnchor: number;
  rangeStart: number;
  rangeEnd: number;
  forecast?: AnalyticsDataPoint[];
  isOutdoor?: boolean;
  /** Panels shown below the temperature, top to bottom (see SUB_PANELS). */
  panels?: SubPanel[];
  /**
   * Shade the range the summary counts as on target: between heat and cool target (auto),
   * from the heat target up (heat only) or from the cool target down (cool only), widened by
   * the comfort tolerance. None: no band.
   */
  targetBand?: "both" | "heat" | "cool" | null;
  /** Unit of the price source (ct/kWh, EUR/kWh, ...), empty when unknown or a switch. */
  priceUnit?: string;
  /** Touch screen: pinch zooms, one finger pans only once zoomed so the page still scrolls. */
  touch?: boolean;
  zoomed?: boolean;
}

/**
 * Zoom like HA's own history charts, on both panels at once: drag a range (the toolbox select,
 * armed by the chart component), Ctrl + wheel or a trackpad pinch zooms, Shift + wheel pans.
 * A plain wheel keeps scrolling the page. Own config, so it is the same on every HA version.
 */
function zoomOptions(axes: number[], touch: boolean, zoomed: boolean): Record<string, unknown> {
  return {
    dataZoom: [
      {
        // HA's zoom handler (reset button, zoom state) reads the component with this id and
        // resets every zoom to 100 % when it is missing
        id: "dataZoom",
        type: "inside",
        xAxisIndex: axes,
        filterMode: "none",
        zoomOnMouseWheel: touch ? true : "ctrl",
        moveOnMouseWheel: touch ? false : "shift",
        moveOnMouseMove: touch && zoomed,
        preventDefaultMouseMove: touch && zoomed,
      },
    ],
    toolbox: {
      show: !touch,
      top: Number.MAX_SAFE_INTEGER,
      left: Number.MAX_SAFE_INTEGER,
      feature: {
        dataZoom: {
          show: true,
          xAxisIndex: axes,
          yAxisIndex: false,
          filterMode: "none",
          showTitle: false,
        },
      },
      iconStyle: { opacity: 0 },
    },
  };
}

const PANEL_TITLE_KEYS: Record<SubPanel | "main", TranslationKey> = {
  main: "analytics.temperature",
  outdoor: "analytics.panel_outdoor",
  humidity: "analytics.humidity",
  price: "analytics.price",
};

/** Heading of a plot, all alike with the unit in brackets. */
export function panelTitle(
  panel: SubPanel | "main",
  language: string,
  units: { temp: string; price: string },
): string {
  const title = localize(PANEL_TITLE_KEYS[panel], language);
  const unit = panel === "humidity" ? "%" : panel === "price" ? units.price : units.temp;
  return unit ? `${title} (${unit})` : title;
}

/** Distance from the chart top to the top of each plot: the temperature first, then the panels. */
export function panelTops(panels: readonly SubPanel[]): number[] {
  const total = chartHeight(panels);
  return [
    MAIN_TOP,
    ...panels.map(
      (p, i) => total - PANEL_BOTTOM - panelsHeight(panels.slice(i + 1)) - SUB_PANELS[p].height,
    ),
  ];
}

/**
 * Colours the price line and the area under it by the level RoomMind saw (cheap, normal,
 * expensive), along time like the humidity. Bounds stay finite (see humidityVisualMap).
 */
export function priceVisualMap(
  points: AnalyticsDataPoint[],
  colors: { cheap: string; normal: string; expensive: string },
) {
  const pieces: Array<Record<string, number | string>> = [];
  const priced = points.filter((p) => p.price != null);
  let start = priced.length > 0 ? priced[0].ts * 1000 : 0;
  let current: string | null = null;
  for (const p of priced) {
    const level =
      p.price_level === "cheap" || p.price_level === "expensive" ? p.price_level : "normal";
    const color = colors[level];
    if (color === current) continue;
    if (current !== null) pieces.push({ gte: start, lt: p.ts * 1000, color: current });
    start = p.ts * 1000;
    current = color;
  }
  if (current !== null) {
    pieces.push({ gte: start, lte: priced[priced.length - 1].ts * 1000, color: current });
  }
  return { type: "piecewise", show: false, seriesId: "price", dimension: 0, pieces };
}

export function chartHeight(panels: readonly SubPanel[]): number {
  if (panels.length === 0) return CHART_HEIGHT;
  return MAIN_TOP + MAIN_PLOT_HEIGHT + panelsHeight(panels) + PANEL_BOTTOM;
}

function panelsHeight(panels: readonly SubPanel[]): number {
  return panels.reduce((sum, p) => sum + SUB_PANELS[p].height + PANEL_GAP, 0);
}

/** Panels whose series has data and is not hidden. */
export function visiblePanels(
  series: Array<Record<string, unknown>>,
  hidden: ReadonlySet<string>,
): SubPanel[] {
  return SUB_PANEL_ORDER.filter((p) => {
    const id = SUB_PANELS[p].series;
    return !hidden.has(id) && series.some((s) => s.id === id);
  });
}

/**
 * Put series tagged with a `panel` on that panel's axes and drop those of panels not shown.
 * The legend keeps working off the untouched list.
 */
export function placeOnPanels(
  series: Array<Record<string, unknown>>,
  panels: readonly SubPanel[],
): Array<Record<string, unknown>> {
  return series.flatMap((s) => {
    const { panel, ...rest } = s;
    if (panel == null) return [rest];
    const index = panels.indexOf(panel as SubPanel) + 1;
    return index > 0 ? [{ ...rest, xAxisIndex: index, yAxisIndex: index }] : [];
  });
}

/**
 * One value per sample, held until the next sample (at most MAX_SAMPLE_GAP_MS) and null where
 * `value` gives null. A sample stands for that time, so a run of a single sample keeps its width.
 */
function stretch(
  points: AnalyticsDataPoint[],
  value: (p: AnalyticsDataPoint) => number | null,
): Array<[number, number | null]> {
  const out: Array<[number, number | null]> = [];
  points.forEach((p, i) => {
    const ts = p.ts * 1000;
    const v = value(p);
    if (v == null) {
      out.push([ts, null]);
      return;
    }
    const next = points[i + 1];
    const nextTs = next ? next.ts * 1000 : ts;
    const end = Math.min(nextTs, ts + MAX_SAMPLE_GAP_MS);
    out.push([ts, v]);
    if (end > ts && (end < nextTs || value(next) !== v)) out.push([end, v], [end, null]);
  });
  return out;
}

const hasValue = (data: Array<[number, number | null]>) => data.some(([, v]) => v != null);

/** Stacked pair: an invisible base, the second series fills from it by its height. */
function bandPair(
  id: string,
  base: Array<[number, number | null]>,
  data: Array<[number, number | null]>,
  style: Record<string, unknown>,
): Array<Record<string, unknown>> {
  const common = {
    stack: id,
    showSymbol: false,
    lineStyle: { width: 0 },
    tooltip: { show: false },
    yAxisIndex: 0,
    z: -1,
    connectNulls: false,
    silent: true,
  };
  return [
    { ...common, id: `${id}_base`, type: "line", name: "", data: base },
    { ...common, id, type: "line", ...style, data },
  ];
}

export function buildChartSeries(
  points: AnalyticsDataPoint[],
  ctx: ChartBuildContext,
): Array<Record<string, unknown>> {
  const { hass, language: l, chartAnchor, forecast, isOutdoor, targetBand } = ctx;
  const d = (c: number) => toDisplay(c, hass);

  const roomData: Array<[number, number]> = [];
  const targetData: Array<[number, number]> = [];
  const predictedData: Array<[number, number]> = [];
  const outdoorData: Array<[number, number]> = [];
  const deviceTargetData: Array<[number, number]> = [];
  const humidityData: Array<[number, number]> = [];
  const bandBaseData: Array<[number, number | null]> = [];
  const bandData: Array<[number, number | null]> = [];
  // Outside the judged sides: too cold below the heat side, too warm above the cool side
  const coldBaseData: Array<[number, number | null]> = [];
  const coldData: Array<[number, number | null]> = [];
  const warmBaseData: Array<[number, number | null]> = [];
  const warmData: Array<[number, number | null]> = [];
  const tol = toDisplayDelta(COMFORT_TOLERANCE_K, hass);
  const open = toDisplayDelta(BAND_OPEN_K, hass);
  const pushBand = (p: AnalyticsDataPoint) => {
    const ts = p.ts * 1000;
    const heat = targetBand !== "cool" && p.heat_target != null ? d(p.heat_target) - tol : null;
    const cool = targetBand !== "heat" && p.cool_target != null ? d(p.cool_target) + tol : null;
    const low = targetBand === "cool" ? (cool != null ? cool - open : null) : heat;
    const high = targetBand === "heat" ? (heat != null ? heat + open : null) : cool;
    if (low != null && high != null && high >= low) {
      bandBaseData.push([ts, low]);
      bandData.push([ts, high - low]);
    } else {
      bandBaseData.push([ts, null]);
      bandData.push([ts, null]);
    }
    coldBaseData.push([ts, heat != null ? heat - open : null]);
    coldData.push([ts, heat != null ? open : null]);
    warmBaseData.push([ts, cool]);
    warmData.push([ts, cool != null ? open : null]);
  };

  for (const p of points) {
    const ts = p.ts * 1000;
    if (p.room_temp !== null) roomData.push([ts, d(p.room_temp)]);
    if (!isOutdoor && p.target_temp !== null) targetData.push([ts, d(p.target_temp)]);
    if (!isOutdoor && p.predicted_temp !== null) predictedData.push([ts, d(p.predicted_temp)]);
    if (p.outdoor_temp !== null) outdoorData.push([ts, d(p.outdoor_temp)]);
    if (!isOutdoor && p.device_setpoint != null) deviceTargetData.push([ts, d(p.device_setpoint)]);
    if (p.humidity != null) humidityData.push([ts, p.humidity]);
    if (targetBand && !isOutdoor) pushBand(p);
  }

  for (const p of forecast ?? []) {
    const ts = p.ts * 1000;
    if (!isOutdoor && p.target_temp !== null) targetData.push([ts, d(p.target_temp)]);
    if (!isOutdoor && p.predicted_temp !== null) predictedData.push([ts, d(p.predicted_temp)]);
    if (targetBand && !isOutdoor) pushBand(p);
  }

  const series: Array<Record<string, unknown>> = [
    {
      id: "room_temp",
      type: "line",
      name: localize("analytics.temperature", l),
      color: "rgb(255, 152, 0)",
      data: roomData,
      showSymbol: false,
      smooth: true,
      lineStyle: { width: 2 },
      yAxisIndex: 0,
    },
  ];

  if (!isOutdoor) {
    series.push({
      id: "target_temp",
      type: "line",
      name: localize("analytics.target", l),
      color: "rgb(76, 175, 80)",
      data: targetData,
      showSymbol: false,
      smooth: false,
      lineStyle: { width: 2, type: "dashed" },
      yAxisIndex: 0,
    });
    // The target line in the colour of what set it, where that was not the schedule
    for (const group of TARGET_REASON_GROUPS) {
      const data = stretch(points, (p) =>
        p.target_temp != null && targetReasons(p).some((r) => group.reasons.includes(r))
          ? d(p.target_temp)
          : null,
      );
      if (!hasValue(data)) continue;
      series.push({
        id: `target_reason_${group.id}`,
        type: "line",
        name: localize(group.label, l),
        color: group.color,
        data,
        showSymbol: false,
        lineStyle: { width: 3 },
        yAxisIndex: 0,
        connectNulls: false,
      });
    }
  }

  if (hasValue(bandData)) {
    series.push(
      ...bandPair("target_band", bandBaseData, bandData, {
        name: localize("analytics.target_band", l),
        color: "rgb(76, 175, 80)",
        areaStyle: { color: "rgba(76, 175, 80, 0.1)" },
      }),
    );
  }

  for (const [side, base, data, color] of [
    ["cold", coldBaseData, coldData, "rgba(33, 150, 243, 0.08)"],
    ["warm", warmBaseData, warmData, "rgba(244, 67, 54, 0.06)"],
  ] as const) {
    if (!hasValue(data)) continue;
    series.push(
      ...bandPair(`target_band_${side}`, base, data, {
        name: "",
        areaStyle: { color },
      }),
    );
  }

  if (predictedData.length > 0) {
    series.push({
      id: "predicted_temp",
      type: "line",
      name: localize("analytics.prediction", l),
      color: "rgb(33, 150, 243)",
      data: predictedData,
      showSymbol: false,
      smooth: true,
      lineStyle: { width: 2, type: "dotted" },
      yAxisIndex: 0,
    });
  }

  if (deviceTargetData.length > 0) {
    series.push({
      id: "device_target",
      type: "line",
      name: "TRV / AC",
      color: "rgb(156, 39, 176)",
      data: deviceTargetData,
      showSymbol: false,
      smooth: false,
      step: "end",
      lineStyle: { width: 1, type: "dashed" },
      yAxisIndex: 0,
    });
  }

  if (outdoorData.length > 0) {
    series.push({
      id: "outdoor_temp",
      type: "line",
      name: localize("analytics.outdoor", l),
      color: "rgb(158, 158, 158)",
      data: outdoorData,
      showSymbol: false,
      smooth: true,
      lineStyle: { width: 1.5 },
      panel: "outdoor",
    });
  }

  const band = (on: (p: AnalyticsDataPoint) => boolean) =>
    stretch(points, (p) => (on(p) ? 999 : null));
  const heatingBandData = band((p) => p.mode === "heating");
  const coolingBandData = band((p) => p.mode === "cooling");
  const windowBandData = band((p) => p.window_open);
  const hasHeating = hasValue(heatingBandData);
  const hasCooling = hasValue(coolingBandData);
  const hasWindow = hasValue(windowBandData);

  if (hasHeating) {
    series.push({
      id: "heating_events",
      type: "line",
      name: localize("analytics.heating_period", l),
      color: "rgb(244, 67, 54)",
      data: heatingBandData,
      showSymbol: false,
      lineStyle: { width: 0 },
      areaStyle: { color: "rgba(244, 67, 54, 0.08)", origin: "start" },
      tooltip: { show: false },
      yAxisIndex: 0,
      z: -1,
      connectNulls: false,
    });
  }

  if (hasCooling) {
    series.push({
      id: "cooling_events",
      type: "line",
      name: localize("analytics.cooling_period", l),
      color: "rgb(63, 81, 181)",
      data: coolingBandData,
      showSymbol: false,
      lineStyle: { width: 0 },
      areaStyle: { color: "rgba(63, 81, 181, 0.08)", origin: "start" },
      tooltip: { show: false },
      yAxisIndex: 0,
      z: -1,
      connectNulls: false,
    });
  }

  if (hasWindow) {
    series.push({
      id: "window_events",
      type: "line",
      name: localize("analytics.window_open_period", l),
      color: "rgb(0, 150, 136)",
      data: windowBandData,
      showSymbol: false,
      lineStyle: { width: 0 },
      areaStyle: { color: "rgba(0, 150, 136, 0.1)", origin: "start" },
      tooltip: { show: false },
      yAxisIndex: 0,
      z: -1,
      connectNulls: false,
    });
  }

  if (humidityData.length > 0) {
    series.push({
      id: "humidity",
      type: "line",
      name: localize("analytics.humidity", l),
      color: HUMIDITY_COLOR,
      data: humidityData,
      showSymbol: false,
      smooth: true,
      lineStyle: { width: 2 },
      panel: "humidity",
    });
    const x0 = ctx.rangeStart;
    const x1 = chartAnchor + FORECAST_MS;
    // The good range as a fixed band, like the target range on the temperature: whether the
    // line is inside reads at a glance, an area under the curve said nothing about it
    const goodSpan = HUMIDITY_LEVELS.humid - HUMIDITY_LEVELS.dry;
    series.push(
      {
        id: "humidity_band_base",
        type: "line",
        name: "",
        data: [
          [x0, HUMIDITY_LEVELS.dry],
          [x1, HUMIDITY_LEVELS.dry],
        ],
        stack: "humidity_band",
        showSymbol: false,
        lineStyle: { width: 0 },
        tooltip: { show: false },
        silent: true,
        z: -1,
        panel: "humidity",
      },
      {
        id: "humidity_band",
        type: "line",
        name: "",
        data: [
          [x0, goodSpan],
          [x1, goodSpan],
        ],
        stack: "humidity_band",
        showSymbol: false,
        lineStyle: { width: 0 },
        areaStyle: { color: "rgba(76, 175, 80, 0.12)" },
        tooltip: { show: false },
        silent: true,
        z: -1,
        panel: "humidity",
      },
    );
    series.push({
      id: "humidity_limits",
      type: "line",
      name: "",
      color: "rgba(128, 128, 128, 0.6)",
      data: [
        [x0, HUMIDITY_LEVELS.dry],
        [x1, HUMIDITY_LEVELS.dry],
        [x1, null],
        [x0, HUMIDITY_LEVELS.humid],
        [x1, HUMIDITY_LEVELS.humid],
      ],
      showSymbol: false,
      lineStyle: { width: 1, type: "dashed" },
      panel: "humidity",
      tooltip: { show: false },
      silent: true,
      connectNulls: false,
      z: -1,
    });
  }

  const priceData = points.flatMap((p): Array<[number, number]> =>
    p.price != null ? [[p.ts * 1000, p.price]] : [],
  );
  if (priceData.length > 0) {
    series.push({
      id: "price",
      type: "line",
      name: localize("analytics.price", l),
      color: PRICE_COLOR,
      data: priceData,
      showSymbol: false,
      step: "end",
      lineStyle: { width: 2 },
      // No colour: line and area take the level colours of priceVisualMap
      areaStyle: { opacity: 0.15, origin: "start" },
      panel: "price",
    });
  }

  const nowMarker = {
    type: "line",
    name: "",
    color: NOW_MARKER_COLOR,
    data: [
      [chartAnchor, -999],
      [chartAnchor, 999],
    ],
    showSymbol: false,
    lineStyle: { width: 1, type: "dashed" },
    tooltip: { show: false },
    z: -2,
  };
  // Open windows and "now" run through every panel; placeOnPanels drops those not shown
  for (const panel of SUB_PANEL_ORDER) {
    if (!series.some((s) => s.panel === panel)) continue;
    if (hasWindow) {
      series.push({
        ...series.find((s) => s.id === "window_events"),
        id: `window_events_${panel}`,
        panel,
      });
    }
    series.push({ ...nowMarker, id: `now_marker_${panel}`, panel });
  }

  series.push({ ...nowMarker, id: "now_marker", yAxisIndex: 0 });

  return series;
}

export function buildChartOptions(
  visibleY: number[],
  points: AnalyticsDataPoint[],
  ctx: ChartBuildContext,
): Record<string, unknown> {
  const { hass, language: l, chartAnchor, rangeStart, rangeEnd } = ctx;
  const panels = ctx.panels ?? [];
  const unit = tempUnit(hass);

  const yAxis: Record<string, unknown> = { type: "value", axisLabel: unitLabel(unit, hass) };

  if (visibleY.length > 0) {
    let minVal = Infinity;
    let maxVal = -Infinity;
    for (const v of visibleY) {
      if (v < minVal) minVal = v;
      if (v > maxVal) maxVal = v;
    }
    const range = maxVal - minVal;
    const pad = Math.max(range * 0.1, 0.5);
    // Whole degrees: half-degree bounds put "24.5" right on top of the "24" tick
    yAxis.min = Math.floor(minVal - pad);
    yAxis.max = Math.ceil(maxVal + pad);
  }

  const isLive = Math.abs(rangeEnd - Date.now()) < 3600_000;

  const timeAxis = {
    type: "time",
    min: rangeStart,
    max: isLive ? chartAnchor + FORECAST_MS : rangeEnd,
  };

  return {
    ...(panels.length > 0
      ? {
          xAxis: [
            { ...timeAxis, axisLabel: { show: false }, axisTick: { show: false } },
            ...panels.map((_, i) => ({
              ...timeAxis,
              gridIndex: i + 1,
              ...(i < panels.length - 1
                ? { axisLabel: { show: false }, axisTick: { show: false } }
                : {}),
            })),
          ],
          yAxis: [
            yAxis,
            ...panels.map((p, i) => panelAxis(p, points, i + 1, hass, ctx.priceUnit ?? "")),
          ],
          axisPointer: { link: [{ xAxisIndex: "all" }] },
          grid: [
            {
              top: MAIN_TOP,
              left: PANEL_LEFT,
              right: 10,
              bottom: PANEL_BOTTOM + panelsHeight(panels),
            },
            ...panels.map((p, i) => ({
              left: PANEL_LEFT,
              right: 10,
              bottom: PANEL_BOTTOM + panelsHeight(panels.slice(i + 1)),
              height: SUB_PANELS[p].height,
            })),
          ],
        }
      : {
          xAxis: timeAxis,
          yAxis,
          grid: { top: MAIN_TOP, left: 10, right: 10, bottom: 5, containLabel: true },
        }),
    ...zoomOptions(panels.map((_, i) => i + 1).concat(0), ctx.touch ?? false, ctx.zoomed ?? false),
    tooltip: {
      trigger: "axis",
      axisPointer: { snap: false },
      valueFormatter: (v: number | null) => (v == null ? "" : v.toFixed(1) + "\u00A0" + unit),
      formatter: (
        params: Array<{
          seriesName: string;
          color: string;
          value: [number, number];
          seriesId: string;
        }>,
      ) => {
        if (!Array.isArray(params) || params.length === 0) return "";
        const date = new Date(params[0].value[0]);
        const time = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        let markup = `<div style="font-weight:500;margin-bottom:4px">${time}</div>`;
        // Rows per panel, each panel under its own heading, so a value reads with its plot
        const groups = new Map<SubPanel | "main", string[]>();
        const panelOf = (sid: string): SubPanel | "main" =>
          SUB_PANEL_ORDER.find((p) => SUB_PANELS[p].series === sid) ?? "main";
        let roomVal: number | null = null;
        let predVal: number | null = null;
        const hoverTs = params[0].value[0] / 1000;
        let closest: AnalyticsDataPoint | null = null;
        let minDist = Infinity;
        for (const pt of points) {
          const dist = Math.abs(pt.ts - hoverTs);
          if (dist < minDist) {
            minDist = dist;
            closest = pt;
          }
        }
        for (const p of params) {
          const sid = (p.seriesId as string) ?? "";
          if (
            sid.endsWith("_events") ||
            sid.startsWith("target_band") ||
            sid.startsWith("target_reason_") ||
            sid.startsWith("humidity_band") ||
            sid === "humidity_limits"
          ) {
            continue;
          }
          const v = p.value?.[1];
          if (v == null) continue;
          let value = `${v.toFixed(1)}\u00A0${unit}`;
          if (sid === "humidity") {
            const level = humidityLevel(v);
            value = `${Math.round(v)}\u00A0%`;
            if (level !== "good") value += ` (${localize(`analytics.humidity_${level}`, l)})`;
          }
          if (sid === "price") {
            value = new Intl.NumberFormat(l, { maximumSignificantDigits: 4 }).format(v);
            if (ctx.priceUnit) value += `\u00A0${ctx.priceUnit}`;
            const level = closest?.price_level;
            if (level === "cheap" || level === "normal" || level === "expensive") {
              value += ` (${localize(`settings.price_level_${level}`, l)})`;
            }
          }
          if (sid === "target_temp" && closest) {
            const reasons = targetReasons(closest).map((r) => localize(REASON_LABELS[r], l));
            if (reasons.length > 0) value += ` (${reasons.join(", ")})`;
          }
          const group = panelOf(sid);
          const rows = groups.get(group) ?? [];
          rows.push(
            `<div>${p.color ? `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${p.color};margin-right:6px"></span>` : ""}${p.seriesName}: ${value}</div>`,
          );
          groups.set(group, rows);
          if (p.seriesId === "room_temp") roomVal = v;
          if (p.seriesId === "predicted_temp") predVal = v;
        }
        markup += (groups.get("main") ?? []).join("");
        if (roomVal !== null && predVal !== null) {
          const delta = roomVal - predVal;
          const sign = delta >= 0 ? "+" : "";
          markup += `<div style="border-top:1px solid rgba(128,128,128,0.3);margin-top:4px;padding-top:4px">${localize("analytics.prediction_delta", l)}: ${sign}${delta.toFixed(2)}\u00A0${unit}</div>`;
        }
        for (const panel of SUB_PANEL_ORDER) {
          const rows = groups.get(panel);
          if (!rows) continue;
          markup += `<div style="border-top:1px solid rgba(128,128,128,0.3);margin-top:4px;padding-top:4px">${rows.join("")}</div>`;
        }
        if (closest) {
          const parts: string[] = [];
          if (closest.mode === "heating") {
            const hp = closest.heating_power;
            if (hp != null && hp > 0 && hp < 100) {
              parts.push(`${localize("analytics.heating_period", l)} ${hp}%`);
            } else {
              parts.push(localize("analytics.heating_period", l));
            }
            if (closest.device_setpoint != null) {
              parts.push(`TRV ${formatTemp(closest.device_setpoint, hass)}\u00A0${unit}`);
            }
          } else if (closest.mode === "cooling") {
            parts.push(localize("analytics.cooling_period", l));
            if (closest.device_setpoint != null) {
              parts.push(`AC ${formatTemp(closest.device_setpoint, hass)}\u00A0${unit}`);
            }
          }
          if (closest.window_open) parts.push(localize("analytics.window_open_period", l));
          if (parts.length > 0) {
            markup += `<div style="border-top:1px solid rgba(128,128,128,0.3);margin-top:4px;padding-top:4px;opacity:0.75">${parts.join(" \u00B7 ")}</div>`;
          }
          if (closest.blind_position != null) {
            markup += `<div style="opacity:0.75">${localize("analytics.blind_position", l)} ${100 - closest.blind_position}%</div>`;
          }
        }
        // HA 2026.6's ha-chart-base pipes the tooltip formatter result through
        // Lit's render() (wrapLitTooltipFormatter). A returned string is
        // rendered as escaped text — the raw HTML shows up as code. Returning
        // an HTMLElement renders correctly there and is also a valid return
        // value for ECharts' html tooltip on older HA, so both paths work.
        const tooltipEl = document.createElement("div");
        tooltipEl.innerHTML = markup;
        return tooltipEl;
      },
    },
  };
}

/** Axis numbers with their unit, in the user's number format. */
function unitLabel(unit: string, hass: HomeAssistant, digits: Intl.NumberFormatOptions = {}) {
  const fmt = new Intl.NumberFormat(hass.language, { maximumFractionDigits: 1, ...digits });
  return {
    formatter: (v: number) => (unit ? `${fmt.format(v)}\u00A0${unit}` : fmt.format(v)),
  };
}

function outdoorAxis(
  points: AnalyticsDataPoint[],
  gridIndex: number,
  hass: HomeAssistant,
): Record<string, unknown> {
  const temps = points
    .map((p) => p.outdoor_temp)
    .filter((t): t is number => t != null)
    .map((t) => toDisplay(t, hass));
  const min = temps.length > 0 ? temps.reduce((a, b) => Math.min(a, b)) : 0;
  const max = temps.length > 0 ? temps.reduce((a, b) => Math.max(a, b)) : 10;
  return {
    type: "value",
    gridIndex,
    min: Math.floor(min - 1),
    max: Math.ceil(max + 1),
    splitNumber: 2,
    axisLabel: unitLabel(tempUnit(hass), hass),
  };
}

function panelAxis(
  panel: SubPanel,
  points: AnalyticsDataPoint[],
  gridIndex: number,
  hass: HomeAssistant,
  priceUnit: string,
): Record<string, unknown> {
  if (panel === "humidity")
    return { ...humidityAxis(points, gridIndex), axisLabel: unitLabel("%", hass) };
  if (panel === "outdoor") return outdoorAxis(points, gridIndex, hass);
  // Price: whatever unit the source uses; bounds from the prices, the level bands reach far above
  const prices = points.map((p) => p.price).filter((v): v is number => v != null);
  const low = prices.length > 0 ? prices.reduce((a, b) => Math.min(a, b)) : 0;
  const high = prices.length > 0 ? prices.reduce((a, b) => Math.max(a, b)) : 1;
  // Round bounds to the magnitude of the span: 20-38 ct reads 20 / 30 / 40, not 19.2 / 39.9
  const span = Math.max(high - low, Math.abs(high) * 0.1, 1e-6);
  const step = 10 ** Math.floor(Math.log10(span));
  return {
    type: "value",
    gridIndex,
    min: Math.floor(low / step) * step,
    max: Math.ceil(high / step) * step,
    splitNumber: 2,
    // "ct/kWh" reads "38 ct" on the axis, the heading carries the whole unit
    axisLabel: unitLabel(priceUnit.split("/")[0].trim(), hass, {
      maximumFractionDigits: undefined,
      maximumSignificantDigits: 3,
    }),
  };
}
