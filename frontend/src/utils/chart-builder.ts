/**
 * Pure functions to build ECharts series and options for analytics charts.
 */
import type { AnalyticsDataPoint } from "../types";
import { localize } from "./localize";
import { formatTemp, tempUnit, toDisplay } from "./temperature";
import type { HomeAssistant } from "../types";

const FORECAST_MS = 3 * 3600_000;

export interface ChartBuildContext {
  hass: HomeAssistant;
  language: string;
  chartAnchor: number;
  rangeStart: number;
  rangeEnd: number;
  forecast?: AnalyticsDataPoint[];
}

export function buildChartSeries(
  points: AnalyticsDataPoint[],
  ctx: ChartBuildContext,
): Array<Record<string, unknown>> {
  const { hass, language: l, chartAnchor, forecast } = ctx;
  const d = (c: number) => toDisplay(c, hass);

  const roomData: Array<[number, number]> = [];
  const targetData: Array<[number, number]> = [];
  const predictedData: Array<[number, number]> = [];
  const outdoorData: Array<[number, number]> = [];

  for (const p of points) {
    const ts = p.ts * 1000;
    if (p.room_temp !== null) roomData.push([ts, d(p.room_temp)]);
    if (p.target_temp !== null) targetData.push([ts, d(p.target_temp)]);
    if (p.predicted_temp !== null) predictedData.push([ts, d(p.predicted_temp)]);
    if (p.outdoor_temp !== null) outdoorData.push([ts, d(p.outdoor_temp)]);
  }

  for (const p of forecast ?? []) {
    const ts = p.ts * 1000;
    if (p.target_temp !== null) targetData.push([ts, d(p.target_temp)]);
    if (p.predicted_temp !== null) predictedData.push([ts, d(p.predicted_temp)]);
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
    {
      id: "target_temp",
      type: "line",
      name: localize("analytics.target", l),
      color: "rgb(76, 175, 80)",
      data: targetData,
      showSymbol: false,
      smooth: false,
      lineStyle: { width: 2, type: "dashed" },
      yAxisIndex: 0,
    },
  ];

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
  let hasHeating = false, hasCooling = false, hasWindow = false;

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

  // Blind position line (secondary Y-axis, inverted: shows % closed)
  const blindData: Array<[number, number | null]> = [];
  let hasBlinds = false;
  for (const p of points) {
    const ts = p.ts * 1000;
    if (p.blind_position != null) {
      blindData.push([ts, 100 - p.blind_position]);
      hasBlinds = true;
    } else {
      blindData.push([ts, null]);
    }
  }

  if (hasBlinds) {
    series.push({
      id: "blind_position",
      type: "line",
      name: localize("analytics.blind_position", l),
      color: "rgba(139, 90, 43, 0.8)",
      data: blindData,
      yAxisIndex: 1,
      smooth: false,
      showSymbol: false,
      lineStyle: { width: 1.5, type: "dashed" },
      areaStyle: { color: "rgba(139, 90, 43, 0.07)", origin: "start" },
      connectNulls: false,
      z: -1,
    });
  }

  // "Now" vertical marker line
  series.push({
    id: "now_marker",
    type: "line",
    name: "",
    color: "rgba(255,255,255,0.3)",
    data: [[chartAnchor, -999], [chartAnchor, 999]],
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
  const { hass, language: l, chartAnchor, rangeStart, rangeEnd } = ctx;
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

  return {
    xAxis: {
      type: "time",
      min: rangeStart,
      max: isLive ? chartAnchor + FORECAST_MS : rangeEnd,
    },
    yAxis: [
      yAxis,
      {
        type: "value",
        min: 0,
        max: 100,
        show: false,
        splitLine: { show: false },
      },
    ],
    dataZoom: [
      {
        type: "inside",
        xAxisIndex: 0,
        filterMode: "none",
      },
    ],
    tooltip: {
      trigger: "axis",
      axisPointer: { snap: false },
      valueFormatter: (v: number) => v.toFixed(1) + "\u00A0" + unit,
      formatter: (params: Array<{ seriesName: string; color: string; value: [number, number]; seriesId: string }>) => {
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
          const isBlind = p.seriesId === "blind_position";
          const valStr = isBlind ? `${Math.round(v)}%` : `${v.toFixed(1)}\u00A0${unit}`;
          markup += `<div>${p.color ? `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${p.color};margin-right:6px"></span>` : ""}${p.seriesName}: ${valStr}</div>`;
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
              if (hp != null && hp > 0 && closest.room_temp != null) {
                const trv = Math.round((closest.room_temp + (hp / 100) * (30 - closest.room_temp)) * 10) / 10;
                parts.push(`TRV ${formatTemp(trv, hass)}\u00A0${unit}`);
              }
            } else if (closest.mode === "cooling") {
              parts.push(localize("analytics.cooling_period", l));
            }
            if (closest.window_open) parts.push(localize("analytics.window_open_period", l));
            if (parts.length > 0) {
              markup += `<div style="border-top:1px solid rgba(128,128,128,0.3);margin-top:4px;padding-top:4px;color:rgba(255,255,255,0.7)">${parts.join(" \u00B7 ")}</div>`;
            }
          }
        }
        return markup;
      },
    },
    grid: {
      top: 15,
      left: 10,
      right: 10,
      bottom: 5,
      containLabel: true,
    },
  };
}
