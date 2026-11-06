/**
 * Pure functions to build ECharts series and options for analytics charts.
 */
import type { AnalyticsDataPoint } from "../types";
import { localize } from "./localize";
import { formatTemp, tempUnit, toDisplay } from "./temperature";
import type { HomeAssistant } from "../types";

const FORECAST_MS = 3 * 3600_000;
const HUMIDITY_COLOR = "rgb(233, 30, 99)";
const CHART_HEIGHT = 300;
const PANEL_CHART_HEIGHT = 385;
const HUMIDITY_PLOT_HEIGHT = 70;
const PANEL_GAP = 24;
const PANEL_BOTTOM = 24;
// The panels share an x axis, so both plots start at a fixed left edge instead of containLabel
const PANEL_LEFT = 46;

export interface ChartBuildContext {
  hass: HomeAssistant;
  language: string;
  chartAnchor: number;
  rangeStart: number;
  rangeEnd: number;
  forecast?: AnalyticsDataPoint[];
  isOutdoor?: boolean;
  /** Draw humidity as a second plot below the temperature, on the same time axis. */
  humidityPanel?: boolean;
}

export function chartHeight(humidityPanel: boolean): number {
  return humidityPanel ? PANEL_CHART_HEIGHT : CHART_HEIGHT;
}

export function buildChartSeries(
  points: AnalyticsDataPoint[],
  ctx: ChartBuildContext,
): Array<Record<string, unknown>> {
  const { hass, language: l, chartAnchor, forecast, isOutdoor } = ctx;
  const d = (c: number) => toDisplay(c, hass);

  const roomData: Array<[number, number]> = [];
  const targetData: Array<[number, number]> = [];
  const predictedData: Array<[number, number]> = [];
  const outdoorData: Array<[number, number]> = [];
  const deviceTargetData: Array<[number, number]> = [];
  const humidityData: Array<[number, number]> = [];

  for (const p of points) {
    const ts = p.ts * 1000;
    if (p.room_temp !== null) roomData.push([ts, d(p.room_temp)]);
    if (!isOutdoor && p.target_temp !== null) targetData.push([ts, d(p.target_temp)]);
    if (!isOutdoor && p.predicted_temp !== null) predictedData.push([ts, d(p.predicted_temp)]);
    if (p.outdoor_temp !== null) outdoorData.push([ts, d(p.outdoor_temp)]);
    if (!isOutdoor && p.device_setpoint != null) deviceTargetData.push([ts, d(p.device_setpoint)]);
    if (p.humidity != null) humidityData.push([ts, p.humidity]);
  }

  for (const p of forecast ?? []) {
    const ts = p.ts * 1000;
    if (!isOutdoor && p.target_temp !== null) targetData.push([ts, d(p.target_temp)]);
    if (!isOutdoor && p.predicted_temp !== null) predictedData.push([ts, d(p.predicted_temp)]);
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
      lineStyle: { width: 1 },
      yAxisIndex: 0,
    });
  }

  // Event band series
  const heatingBandData: Array<[number, number | null]> = [];
  const coolingBandData: Array<[number, number | null]> = [];
  const windowBandData: Array<[number, number | null]> = [];
  let hasHeating = false,
    hasCooling = false,
    hasWindow = false;

  for (const p of points) {
    const ts = p.ts * 1000;
    if (p.mode === "heating") {
      heatingBandData.push([ts, 999]);
      hasHeating = true;
    } else {
      heatingBandData.push([ts, null]);
    }
    if (p.mode === "cooling") {
      coolingBandData.push([ts, 999]);
      hasCooling = true;
    } else {
      coolingBandData.push([ts, null]);
    }
    if (p.window_open) {
      windowBandData.push([ts, 999]);
      hasWindow = true;
    } else {
      windowBandData.push([ts, null]);
    }
  }

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
      areaStyle: { color: "rgba(233, 30, 99, 0.1)", origin: "start" },
      xAxisIndex: 1,
      yAxisIndex: 1,
    });
    if (hasWindow) {
      series.push({
        ...series.find((s) => s.id === "window_events"),
        id: "window_humidity_events",
        xAxisIndex: 1,
        yAxisIndex: 1,
      });
    }
    series.push({
      id: "now_humidity_marker",
      type: "line",
      name: "",
      color: "rgba(255,255,255,0.3)",
      data: [
        [chartAnchor, -999],
        [chartAnchor, 999],
      ],
      showSymbol: false,
      lineStyle: { width: 1, type: "dashed" },
      xAxisIndex: 1,
      yAxisIndex: 1,
      tooltip: { show: false },
      z: -2,
    });
  }

  // "Now" vertical marker line
  series.push({
    id: "now_marker",
    type: "line",
    name: "",
    color: "rgba(255,255,255,0.3)",
    data: [
      [chartAnchor, -999],
      [chartAnchor, 999],
    ],
    showSymbol: false,
    lineStyle: { width: 1, type: "dashed" },
    yAxisIndex: 0,
    tooltip: { show: false },
    z: -2,
  });

  return series;
}

export function buildChartOptions(
  visibleY: number[],
  points: AnalyticsDataPoint[],
  ctx: ChartBuildContext,
): Record<string, unknown> {
  const { hass, language: l, chartAnchor, rangeStart, rangeEnd, humidityPanel } = ctx;
  const unit = tempUnit(hass);

  const yAxis: Record<string, unknown> = {
    type: "value",
    name: unit,
  };

  if (visibleY.length > 0) {
    let minVal = Infinity;
    let maxVal = -Infinity;
    for (const v of visibleY) {
      if (v < minVal) minVal = v;
      if (v > maxVal) maxVal = v;
    }
    const range = maxVal - minVal;
    const pad = Math.max(range * 0.1, 0.5);
    yAxis.min = Math.floor((minVal - pad) * 2) / 2;
    yAxis.max = Math.ceil((maxVal + pad) * 2) / 2;
  }

  const isLive = Math.abs(rangeEnd - Date.now()) < 3600_000;

  const timeAxis = {
    type: "time",
    min: rangeStart,
    max: isLive ? chartAnchor + FORECAST_MS : rangeEnd,
  };

  return {
    ...(humidityPanel
      ? {
          xAxis: [
            { ...timeAxis, axisLabel: { show: false }, axisTick: { show: false } },
            { ...timeAxis, gridIndex: 1 },
          ],
          yAxis: [yAxis, humidityAxis(points)],
          axisPointer: { link: [{ xAxisIndex: "all" }] },
          grid: [
            {
              top: 15,
              left: PANEL_LEFT,
              right: 10,
              bottom: PANEL_BOTTOM + HUMIDITY_PLOT_HEIGHT + PANEL_GAP,
            },
            { left: PANEL_LEFT, right: 10, bottom: PANEL_BOTTOM, height: HUMIDITY_PLOT_HEIGHT },
          ],
        }
      : {
          xAxis: timeAxis,
          yAxis,
          grid: { top: 15, left: 10, right: 10, bottom: 5, containLabel: true },
        }),
    dataZoom: [
      {
        type: "inside",
        xAxisIndex: humidityPanel ? [0, 1] : 0,
        filterMode: "none",
      },
    ],
    tooltip: {
      trigger: "axis",
      axisPointer: { snap: false },
      valueFormatter: (v: number) => v.toFixed(1) + "\u00A0" + unit,
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
        let roomVal: number | null = null;
        let predVal: number | null = null;
        for (const p of params) {
          if ((p.seriesId as string)?.endsWith("_events")) continue;
          const v = p.value?.[1];
          if (v == null) continue;
          const value =
            p.seriesId === "humidity" ? `${Math.round(v)}\u00A0%` : `${v.toFixed(1)}\u00A0${unit}`;
          markup += `<div>${p.color ? `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${p.color};margin-right:6px"></span>` : ""}${p.seriesName}: ${value}</div>`;
          if (p.seriesId === "room_temp") roomVal = v;
          if (p.seriesId === "predicted_temp") predVal = v;
        }
        if (roomVal !== null && predVal !== null) {
          const delta = roomVal - predVal;
          const sign = delta >= 0 ? "+" : "";
          markup += `<div style="border-top:1px solid rgba(128,128,128,0.3);margin-top:4px;padding-top:4px">Delta: ${sign}${delta.toFixed(2)}\u00A0${unit}</div>`;
        }
        if (points.length > 0) {
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
              markup += `<div style="border-top:1px solid rgba(128,128,128,0.3);margin-top:4px;padding-top:4px;color:rgba(255,255,255,0.7)">${parts.join(" \u00B7 ")}</div>`;
            }
            if (closest.blind_position != null) {
              markup += `<div style="color:rgba(255,255,255,0.7)">${localize("analytics.blind_position", l)} ${100 - closest.blind_position}%</div>`;
            }
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

function humidityAxis(points: AnalyticsDataPoint[]): Record<string, unknown> {
  let min = Infinity;
  let max = -Infinity;
  for (const p of points) {
    if (p.humidity == null) continue;
    if (p.humidity < min) min = p.humidity;
    if (p.humidity > max) max = p.humidity;
  }
  return {
    type: "value",
    gridIndex: 1,
    min: Math.max(Math.floor((min - 2) / 10) * 10, 0),
    max: Math.min(Math.ceil((max + 2) / 10) * 10, 100),
    interval: 10,
    axisLabel: { formatter: "{value} %" },
  };
}
