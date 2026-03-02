/**
 * rs-analytics – Analytics tab showing temperature charts and thermal model status.
 */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, RoomConfig } from "../types";
import { localize, type TranslationKey } from "../utils/localize";
import { infoIconStyles } from "../styles/info-icon-styles";
import { formatTemp, tempUnit, toDisplay, toDisplayDelta } from "../utils/temperature";
import { getSelectValue } from "../utils/events";

interface AnalyticsDataPoint {
  ts: number;
  room_temp: number | null;
  outdoor_temp: number | null;
  target_temp: number | null;
  mode: string;
  predicted_temp: number | null;
  window_open: boolean;
  heating_power: number | null;
}

interface AnalyticsData {
  detail: AnalyticsDataPoint[];
  history: AnalyticsDataPoint[];
  forecast?: AnalyticsDataPoint[];
  model: {
    confidence: number;
    model: { C: number; U: number; Q_heat: number; Q_cool: number; Q_solar: number };
    n_samples: number;
    n_observations: number;
    n_heating: number;
    n_cooling: number;
    applicable_modes: string[];
    mpc_active: boolean;
    sigma_e: number;
    prediction_std_idle: number;
    prediction_std_heating: number;
  };
}

type TimeRange = "12h" | "24h" | "2d" | "7d" | "14d" | "30d" | "90d";

const FORECAST_MS = 3 * 3600_000; // 3 hours into the future

const RANGE_MS: Record<TimeRange, number> = {
  "12h": 12 * 3600_000,
  "24h": 24 * 3600_000,
  "2d": 2 * 86400_000,
  "7d": 7 * 86400_000,
  "14d": 14 * 86400_000,
  "30d": 30 * 86400_000,
  "90d": 90 * 86400_000,
};

@customElement("rs-analytics")
export class RsAnalytics extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Object }) public rooms: Record<string, RoomConfig> = {};
  @property() public initialRoom = "";
  @property() public controlMode: "mpc" | "bangbang" = "bangbang";

  @state() private _selectedRoom = "";
  @state() private _rangeStart: number = new Date(new Date().setHours(0, 0, 0, 0)).getTime();
  @state() private _rangeEnd: number = Date.now();
  @state() private _data: AnalyticsData | null = null;
  @state() private _chartAnchor: number = Date.now();
  @state() private _loading = false;
  @state() private _hiddenSeries = new Set(["outdoor_temp"]);
  @state() private _expandedStat: string | null = null;
  @state() private _chartInfoExpanded = false;
  @state() private _openDropdown: "csv" | "diag" | null = null;
  @state() private _activeQuick: string | null = "24h";

  private _refreshInterval?: ReturnType<typeof setInterval>;
  private _boundCloseDropdowns = this._closeDropdowns.bind(this);

  connectedCallback() {
    super.connectedCallback();
    this._refreshInterval = setInterval(() => this._silentRefresh(), 60_000);
    document.addEventListener("click", this._boundCloseDropdowns);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._refreshInterval) {
      clearInterval(this._refreshInterval);
      this._refreshInterval = undefined;
    }
    document.removeEventListener("click", this._boundCloseDropdowns);
  }

  protected willUpdate(changedProps: Map<string, unknown>) {
    // Apply initial room from URL
    if (changedProps.has("initialRoom") && this.initialRoom) {
      this._selectedRoom = this.initialRoom;
    }
    // Auto-select first configured room if none selected
    let autoSelected = false;
    if (changedProps.has("rooms") && !this._selectedRoom) {
      const configured = Object.keys(this.rooms);
      if (configured.length > 0) {
        this._selectedRoom = configured[0];
        autoSelected = true;
        this.dispatchEvent(
          new CustomEvent("room-selected", {
            detail: { areaId: configured[0] },
            bubbles: true,
            composed: true,
          }),
        );
      }
    }
    // Fetch data when room or range changes (or auto-selected)
    if (autoSelected || changedProps.has("_selectedRoom") || changedProps.has("_rangeStart") || changedProps.has("_rangeEnd")) {
      if (this._selectedRoom) {
        this._fetchData();
      }
    }
  }

  protected updated(changedProps: Map<string, unknown>) {
    // ha-select doesn't sync its visual state when list items render after
    // .value was already set.  Force re-sync once rooms are available.
    if ((changedProps.has("rooms") || changedProps.has("_selectedRoom")) && this._selectedRoom) {
      this.updateComplete.then(() => {
        const select = this.renderRoot?.querySelector("ha-select") as HTMLElement & { value?: string };
        if (select && select.value !== this._selectedRoom) {
          select.value = this._selectedRoom;
        }
      });
    }
  }

  protected render() {
    const l = this.hass.language;
    const configuredRooms = this._getConfiguredRooms();

    return html`
      ${this._renderRoomSelector(configuredRooms, l)}
      ${this._selectedRoom
        ? html`
            ${this._renderRangeButtons(l)}
            ${this._loading
              ? html`<div class="loading">${localize("panel.loading", l)}</div>`
              : html`
                  ${this._renderChart(l)}
                  ${this._renderModelStatus(l)}
                `}
          `
        : html`
            <div class="no-data">
              <ha-icon icon="mdi:chart-line" style="--mdc-icon-size: 48px; opacity: 0.4"></ha-icon>
              <p>${localize("analytics.select_room", l)}</p>
            </div>
          `}
    `;
  }

  private _getConfiguredRooms(): Array<{ area_id: string; name: string }> {
    return Object.entries(this.rooms).map(([area_id, config]) => {
      const area = this.hass?.areas?.[area_id];
      return { area_id, name: config.display_name || area?.name || area_id };
    });
  }

  private _renderRoomSelector(
    rooms: Array<{ area_id: string; name: string }>,
    l: string,
  ) {
    return html`
      <div class="selector-row">
        <ha-select
          .value=${this._selectedRoom}
          .label=${localize("analytics.select_room", l)}
          .options=${rooms.map((r) => ({ value: r.area_id, label: r.name }))}
          naturalMenuWidth
          fixedMenuPosition
          @selected=${this._onRoomSelected}
          @closed=${(e: Event) => e.stopPropagation()}
        >
          ${rooms.map(
            (r) => html`
              <ha-list-item .value=${r.area_id}>${r.name}</ha-list-item>
            `,
          )}
        </ha-select>
      </div>
    `;
  }

  private _renderRangeButtons(l: string) {
    const quickRanges = [
      { key: "24h", label: localize("analytics.range_1d", l), days: 1 },
      { key: "2d", label: localize("analytics.range_2d", l), days: 2 },
      { key: "7d", label: localize("analytics.range_7d", l), days: 7 },
      { key: "30d", label: localize("analytics.range_30d", l), days: 30 },
    ];
    const hasData = this._data && (this._data.history.length > 0 || this._data.detail.length > 0);

    const fmt = (ms: number) => {
      return new Date(ms).toLocaleString(this.hass.language, {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
    };

    return html`
      <div class="range-row">
        <div class="range-controls">
          <div class="range-bar">
            ${quickRanges.map(
              (r) => html`
                <button
                  class="range-chip"
                  ?active=${this._activeQuick === r.key}
                  @click=${() => this._onQuickRange(r.key, r.days)}
                >
                  ${r.label}
                </button>
              `,
            )}
            <div class="range-chip picker-chip ${this._activeQuick === null ? "picker-active" : ""}">
              <ha-date-range-picker
                .hass=${this.hass}
                .startDate=${new Date(this._rangeStart)}
                .endDate=${new Date(this._rangeEnd)}
                .ranges=${false}
                time-picker
                auto-apply
                minimal
                @value-changed=${this._onDateRangeChanged}
              ></ha-date-range-picker>
            </div>
          </div>
          <span class="date-label ${this._activeQuick === null ? "custom-active" : ""}">${fmt(this._rangeStart)} – ${fmt(this._rangeEnd)}</span>
        </div>
        <div class="action-buttons">
          <div class="export-split">
            <button
              class="export-btn"
              ?disabled=${!hasData}
              @click=${(e: Event) => { e.stopPropagation(); this._toggleDropdown("csv"); }}
            >
              <ha-icon icon="mdi:download"></ha-icon>
              ${localize("analytics.export", l)}
              <ha-icon class="arrow-icon" icon="mdi:chevron-down"></ha-icon>
            </button>
            ${this._openDropdown === "csv"
              ? html`<div class="export-dropdown" @click=${(e: Event) => e.stopPropagation()}>
                  <button @click=${this._exportCsv}>
                    <ha-icon icon="mdi:download"></ha-icon>
                    ${localize("analytics.export_download", l)}
                  </button>
                  <button @click=${this._copyCsvToClipboard}>
                    <ha-icon icon="mdi:content-copy"></ha-icon>
                    ${localize("analytics.export_clipboard", l)}
                  </button>
                </div>`
              : nothing}
          </div>
          <div class="export-split">
            <button
              class="export-btn"
              ?disabled=${!this._selectedRoom || !this._data}
              @click=${(e: Event) => { e.stopPropagation(); this._toggleDropdown("diag"); }}
            >
              <ha-icon icon="mdi:bug-outline"></ha-icon>
              ${localize("analytics.copy_diagnostics", l)}
              <ha-icon class="arrow-icon" icon="mdi:chevron-down"></ha-icon>
            </button>
            ${this._openDropdown === "diag"
              ? html`<div class="export-dropdown" @click=${(e: Event) => e.stopPropagation()}>
                  <button @click=${this._exportDiagnostics}>
                    <ha-icon icon="mdi:download"></ha-icon>
                    ${localize("analytics.export_download", l)}
                  </button>
                  <button @click=${this._copyDiagnosticsToClipboard}>
                    <ha-icon icon="mdi:content-copy"></ha-icon>
                    ${localize("analytics.export_clipboard", l)}
                  </button>
                </div>`
              : nothing}
          </div>
        </div>
      </div>
    `;
  }

  private _renderChart(l: string) {
    const points = this._data
      ? [...this._data.history, ...this._data.detail]
      : [];
    const allPoints = [...points, ...(this._data?.forecast ?? [])];

    const allSeries = points.length > 0
      ? this._buildChartSeries(points, l)
      : [];

    // Apply hidden styling; collect visible y-values for axis bounds
    const visibleY: number[] = [];
    const displaySeries = allSeries.map((s) => {
      const id = s.id as string;
      const ls = (s.lineStyle as Record<string, unknown>) || {};
      const isEvent = id.endsWith("_events");
      if (this._hiddenSeries.has(id)) {
        const hidden: Record<string, unknown> = { ...s, lineStyle: { ...ls, width: 0, opacity: 0 } };
        // Hide areaStyle for event band series
        if (s.areaStyle) {
          hidden.areaStyle = { ...(s.areaStyle as Record<string, unknown>), opacity: 0 };
        }
        return hidden;
      }
      // Don't include event band / marker y-values in axis bounds
      if (!isEvent && id !== "now_marker") {
        for (const point of s.data as Array<[number, number]>) {
          if (point && point[1] != null) {
            visibleY.push(point[1]);
          }
        }
      }
      // Explicitly set areaStyle opacity to 1 so ECharts merge doesn't keep stale opacity: 0
      const visible: Record<string, unknown> = { ...s, lineStyle: { ...ls, opacity: 1 } };
      if (s.areaStyle) {
        visible.areaStyle = { ...(s.areaStyle as Record<string, unknown>), opacity: 1 };
      }
      return visible;
    });

    const options = this._buildChartOptions(visibleY, l, allPoints);

    return html`
      <ha-card>
        <div class="card-header">
          <span>${localize("analytics.temperature", l)}</span>
          <ha-icon
            class="info-icon chart-info-toggle ${this._chartInfoExpanded ? "info-active" : ""}"
            icon="mdi:information-outline"
            @click=${() => { this._chartInfoExpanded = !this._chartInfoExpanded; }}
          ></ha-icon>
        </div>
        ${this._chartInfoExpanded
          ? html`<div class="chart-info-panel">
              ${this._renderMarkdown(localize("analytics.chart_info_body", l))}
            </div>`
          : nothing}
        ${points.length > 0
          ? html`
              <ha-chart-base
                .hass=${this.hass}
                .data=${displaySeries}
                .options=${options}
                .height=${"300px"}
                style="height: 300px"
              ></ha-chart-base>
              ${this._renderSeriesLegend(allSeries)}
            `
          : html`<div class="chart-empty">
              <ha-icon icon="mdi:chart-line"></ha-icon>
              <span>${localize("analytics.no_data", l)}</span>
            </div>`}
      </ha-card>
    `;
  }

  /** Build ECharts series array (ha-chart-base .data property). */
  private _buildChartSeries(
    points: AnalyticsDataPoint[],
    l: string,
  ): Array<Record<string, unknown>> {
    const roomData: Array<[number, number]> = [];
    const targetData: Array<[number, number]> = [];
    const predictedData: Array<[number, number]> = [];
    const outdoorData: Array<[number, number]> = [];

    for (const p of points) {
      const ts = p.ts * 1000; // seconds → ms
      if (p.room_temp !== null) roomData.push([ts, p.room_temp]);
      if (p.target_temp !== null) targetData.push([ts, p.target_temp]);
      if (p.predicted_temp !== null) predictedData.push([ts, p.predicted_temp]);
      if (p.outdoor_temp !== null) outdoorData.push([ts, p.outdoor_temp]);
    }

    // Append forecast points (same format as history, pre-merged on 5-min grid)
    for (const p of this._data?.forecast ?? []) {
      const ts = p.ts * 1000;
      if (p.target_temp !== null) targetData.push([ts, p.target_temp]);
      if (p.predicted_temp !== null) predictedData.push([ts, p.predicted_temp]);
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

    // Event band series using areaStyle (filled areas behind temperature lines)
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

    // "Now" vertical marker line
    const anchor = this._chartAnchor;
    series.push({
      id: "now_marker",
      type: "line",
      name: "",
      color: "rgba(255,255,255,0.3)",
      data: [[anchor, -999], [anchor, 999]],
      showSymbol: false,
      lineStyle: { width: 1, type: "dashed" },
      yAxisIndex: 0,
      tooltip: { show: false },
      z: -2,
    });

    return series;
  }

  /** Build ECharts options (ha-chart-base .options property). */
  private _buildChartOptions(
    visibleY: number[],
    l: string,
    points: AnalyticsDataPoint[] = [],
  ): Record<string, unknown> {
    const yAxis: Record<string, unknown> = {
      type: "value",
      name: tempUnit(this.hass),
    };

    // Compute y-axis bounds from visible series only
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

    const anchor = this._chartAnchor;
    const rangeStart = this._rangeStart;
    const isLive = Math.abs(this._rangeEnd - Date.now()) < 3600_000;

    return {
      xAxis: {
        type: "time",
        min: rangeStart,
        max: isLive ? anchor + FORECAST_MS : this._rangeEnd,
      },
      yAxis,
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
        valueFormatter: (v: number) => toDisplay(v, this.hass).toFixed(1) + "\u00A0" + tempUnit(this.hass),
        formatter: (params: Array<{ seriesName: string; color: string; value: [number, number]; seriesId: string }>) => {
          if (!Array.isArray(params) || params.length === 0) return "";
          const date = new Date(params[0].value[0]);
          const time = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
          let markup = `<div style="font-weight:500;margin-bottom:4px">${time}</div>`;
          let roomVal: number | null = null;
          let predVal: number | null = null;
          for (const p of params) {
            // Skip event band series
            if ((p.seriesId as string)?.endsWith("_events")) continue;
            const v = p.value?.[1];
            if (v == null) continue;
            markup += `<div>${p.color ? `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${p.color};margin-right:6px"></span>` : ""}${p.seriesName}: ${toDisplay(v, this.hass).toFixed(1)}\u00A0${tempUnit(this.hass)}</div>`;
            if (p.seriesId === "room_temp") roomVal = v;
            if (p.seriesId === "predicted_temp") predVal = v;
          }
          if (roomVal !== null && predVal !== null) {
            const delta = roomVal - predVal;
            const sign = delta >= 0 ? "+" : "";
            markup += `<div style="border-top:1px solid rgba(128,128,128,0.3);margin-top:4px;padding-top:4px">Delta: ${sign}${toDisplayDelta(delta, this.hass).toFixed(2)}\u00A0${tempUnit(this.hass)}</div>`;
          }
          // Show mode and window status from closest data point
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
                // Show TRV setpoint when proportional
                if (hp != null && hp > 0 && closest.room_temp != null) {
                  const trv = Math.round((closest.room_temp + (hp / 100) * (30 - closest.room_temp)) * 10) / 10;
                  parts.push(`TRV ${formatTemp(trv, this.hass)}\u00A0${tempUnit(this.hass)}`);
                }
              } else if (closest.mode === "cooling") {
                parts.push(localize("analytics.cooling_period", l));
              }
              if (closest.window_open) parts.push(localize("analytics.window_open_period", l));
              if (parts.length > 0) {
                markup += `<div style="border-top:1px solid rgba(128,128,128,0.3);margin-top:4px;padding-top:4px;color:rgba(255,255,255,0.7)">${parts.join(" · ")}</div>`;
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

  private _renderModelStatus(l: string) {
    const hasModel = !!(this._data?.model?.model);
    const m = this._data?.model;
    const model = m?.model;
    const confidence = m?.confidence ?? 0;
    const n_samples = m?.n_samples ?? 0;
    const n_heating = m?.n_heating ?? 0;
    const n_cooling = m?.n_cooling ?? 0;
    const applicable_modes = m?.applicable_modes ?? [];
    const predStdIdle = m?.prediction_std_idle;
    const predStdHeat = m?.prediction_std_heating;

    const mpcActive = m?.mpc_active ?? false;
    const confidencePct = Math.round(confidence * 100);
    const modes = new Set(applicable_modes);
    const canHeat = modes.has("heating");
    const canCool = modes.has("cooling");
    const hasHeated = n_heating >= 10;
    const hasCooled = n_cooling >= 10;
    const hasIdleData = (n_samples - n_heating - n_cooling) >= 10;
    const n_observations = m?.n_observations ?? n_samples;
    const ph = "\u2014";

    const statItems: Array<{ id: string; labelKey: TranslationKey; infoKey: TranslationKey }> = [];
    const stat = (
      id: string,
      value: string | number,
      labelKey: TranslationKey,
      unit: string,
      infoKey: TranslationKey,
    ) => {
      statItems.push({ id, labelKey, infoKey });
      const active = this._expandedStat === id;
      return html`
        <div class="model-stat ${active ? "active" : ""}" @click=${() => this._toggleStat(id)}>
          <div class="stat-content">
            <span class="model-value ${value === ph ? "pending" : ""}">${value}</span>
            <span class="model-label">${localize(labelKey, l)}${unit ? ` (${unit})` : ""}</span>
          </div>
          <ha-icon
            class="info-icon ${active ? "info-active" : ""}"
            icon="mdi:information-outline"
          ></ha-icon>
        </div>
      `;
    };

    return html`
      <ha-card>
        <div class="card-header">
          <span>${localize("analytics.model_status", l)}</span>
        </div>
        <div class="card-content">
          <!-- Confidence hero -->
          <div class="confidence-hero">
            <div class="confidence-top">
              <div class="confidence-main">
                <span class="confidence-value">${hasModel ? confidencePct + "%" : "0%"}</span>
                <span class="confidence-label">
                  ${localize("analytics.confidence", l)}
                  <ha-icon
                    class="info-icon ${this._expandedStat === "confidence" ? "info-active" : ""}"
                    icon="mdi:information-outline"
                    @click=${() => this._toggleStat("confidence")}
                  ></ha-icon>
                </span>
              </div>
              <div class="confidence-meta">
                <span class="meta-value">${hasModel ? n_observations : 0}</span>
                <span class="meta-label">
                  ${localize("analytics.data_points", l)}
                  <ha-icon
                    class="info-icon ${this._expandedStat === "data_points" ? "info-active" : ""}"
                    icon="mdi:information-outline"
                    @click=${() => this._toggleStat("data_points")}
                  ></ha-icon>
                </span>
              </div>
            </div>
            <div class="confidence-bar">
              <div class="confidence-fill" style="width: ${hasModel ? confidencePct : 0}%"></div>
            </div>
            <div class="control-mode-badge ${mpcActive ? "mpc" : "bangbang"}">
              <ha-icon icon=${mpcActive ? "mdi:brain" : "mdi:school-outline"}></ha-icon>
              ${mpcActive
                ? localize("analytics.control_mode_mpc", l)
                : localize("analytics.control_mode_bangbang", l)}
            </div>
            ${this._expandedStat === "confidence"
              ? html`<div class="info-panel stat-info-panel">
                  <strong>${localize("analytics.confidence", l)}</strong>
                  ${localize("analytics.info.confidence", l)}
                </div>`
              : nothing}
            ${this._expandedStat === "data_points"
              ? html`<div class="info-panel stat-info-panel">
                  <strong>${localize("analytics.data_points", l)}</strong>
                  ${localize("analytics.info.data_points", l)}
                </div>`
              : nothing}
          </div>

          <!-- Stats grid -->
          <div class="model-grid">
            ${stat("time_constant", hasIdleData && model && model.U > 0 ? (1 / model.U).toFixed(1) + "h" : ph, "analytics.time_constant", "", "analytics.info.time_constant")}
            ${canHeat ? stat("heating_rate", hasHeated && model ? toDisplayDelta(model.Q_heat, this.hass).toFixed(1) + tempUnit(this.hass) + "/h" : ph, "analytics.heating_rate", "", "analytics.info.heating_rate") : nothing}
            ${canCool ? stat("cooling_rate", hasCooled && model ? toDisplayDelta(model.Q_cool, this.hass).toFixed(1) + tempUnit(this.hass) + "/h" : ph, "analytics.cooling_rate", "", "analytics.info.cooling_rate") : nothing}
            ${model && model.Q_solar > 0.1 ? stat("solar_gain", toDisplayDelta(model.Q_solar, this.hass).toFixed(1) + tempUnit(this.hass) + "/h", "analytics.solar_gain", "", "analytics.info.solar_gain") : nothing}
            ${stat("accuracy_idle", hasIdleData && predStdIdle != null ? "\u00B1" + toDisplayDelta(predStdIdle, this.hass).toFixed(2) + tempUnit(this.hass) : ph, "analytics.accuracy_idle", "", "analytics.info.accuracy_idle")}
            ${canHeat ? stat("accuracy_heating", hasHeated && predStdHeat != null ? "\u00B1" + toDisplayDelta(predStdHeat, this.hass).toFixed(2) + tempUnit(this.hass) : ph, "analytics.accuracy_heating", "", "analytics.info.accuracy_heating") : nothing}
          </div>
          ${this._expandedStat && statItems.find((s) => s.id === this._expandedStat)
            ? html`<div class="info-panel stat-info-panel">
                <strong>${localize(statItems.find((s) => s.id === this._expandedStat)!.labelKey, l)}</strong>
                ${localize(statItems.find((s) => s.id === this._expandedStat)!.infoKey, l)}
              </div>`
            : nothing}

        </div>
      </ha-card>
    `;
  }

  private _renderSeriesLegend(series: Array<Record<string, unknown>>) {
    const legendSeries = series.filter((s) => {
      const id = s.id as string;
      return id !== "now_marker";
    });
    return html`
      <div class="series-legend">
        ${legendSeries.map((s) => {
          const id = s.id as string;
          const hidden = this._hiddenSeries.has(id);
          return html`
            <button
              class="legend-item ${hidden ? "legend-hidden" : ""}"
              @click=${() => this._toggleSeries(id)}
            >
              <span class="legend-dot" style="background: ${s.color}"></span>
              ${s.name}
            </button>
          `;
        })}
      </div>
    `;
  }

  private _renderMarkdown(text: string) {
    // Simple markdown: **bold** and paragraph breaks
    const paragraphs = text.split("\n\n");
    return paragraphs.map(
      (p) =>
        html`<p>
          ${p.split(/(\*\*.*?\*\*)/).map((part) =>
            part.startsWith("**") && part.endsWith("**")
              ? html`<strong>${part.slice(2, -2)}</strong>`
              : part,
          )}
        </p>`,
    );
  }

  private _toggleStat(id: string) {
    this._expandedStat = this._expandedStat === id ? null : id;
  }

  private _toggleSeries(id: string) {
    const next = new Set(this._hiddenSeries);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    this._hiddenSeries = next;
  }


  private _onRoomSelected(e: Event) {
    const value = getSelectValue(e);
    if (value && value !== this._selectedRoom) {
      this._selectedRoom = value;
      this.dispatchEvent(
        new CustomEvent("room-selected", {
          detail: { areaId: value },
          bubbles: true,
          composed: true,
        }),
      );
    }
  }

  private _onQuickRange(key: string, days: number) {
    const now = new Date();
    const start = new Date(now);
    start.setDate(start.getDate() - (days - 1));
    start.setHours(0, 0, 0, 0);
    this._activeQuick = key;
    this._rangeEnd = now.getTime();
    this._rangeStart = start.getTime();
    this._chartAnchor = now.getTime();
  }

  private _onDateRangeChanged(e: CustomEvent) {
    const { startDate, endDate } = e.detail.value as { startDate: Date; endDate: Date };
    if (!startDate || !endDate) return;
    this._activeQuick = null;
    this._rangeStart = startDate.getTime();
    this._rangeEnd = endDate.getTime();
    this._chartAnchor = endDate.getTime();
  }

  private _buildCsvString(): string | null {
    if (!this._data) return null;
    const points = [...this._data.history, ...this._data.detail];
    if (points.length === 0) return null;

    const header = "timestamp,datetime,room_temp,outdoor_temp,target_temp,mode,predicted_temp,window_open";
    const rows = points.map((p) => {
      const dt = new Date(p.ts * 1000).toISOString();
      const rt = p.room_temp ?? "";
      const ot = p.outdoor_temp ?? "";
      const tt = p.target_temp ?? "";
      const pt = p.predicted_temp ?? "";
      return `${p.ts},${dt},${rt},${ot},${tt},${p.mode},${pt},${p.window_open}`;
    });

    return [header, ...rows].join("\n");
  }

  private _buildDiagnosticsString(): string | null {
    if (!this._selectedRoom || !this._data) return null;

    const room = this.rooms?.[this._selectedRoom];
    const points = [...(this._data.history ?? []), ...(this._data.detail ?? [])];
    const lastPoint = points.length > 0 ? points[points.length - 1] : null;

    const data = {
      version: "0.2.0",
      area_id: this._selectedRoom,
      room_config: {
        climate_mode: room?.climate_mode,
        has_thermostats: (room?.thermostats?.length || 0) > 0,
        has_acs: (room?.acs?.length || 0) > 0,
        has_temp_sensor: !!room?.temperature_sensor,
        has_window_sensors: (room?.window_sensors?.length || 0) > 0,
      },
      live: room?.live || {},
      model: this._data.model || {},
      settings: {
        control_mode: this.controlMode,
      },
      outdoor: {
        temp: lastPoint?.outdoor_temp ?? null,
      },
    };

    return JSON.stringify(data, null, 2);
  }

  private _downloadString(content: string, filename: string, mimeType: string) {
    const blob = new Blob([content], { type: `${mimeType};charset=utf-8` });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  private _exportCsv() {
    const csv = this._buildCsvString();
    if (!csv) return;
    const area = this.hass?.areas?.[this._selectedRoom];
    const roomConfig = this.rooms[this._selectedRoom];
    const name = (roomConfig?.display_name || area?.name || this._selectedRoom).replace(/\s+/g, "_").toLowerCase();
    const from = new Date(this._rangeStart).toISOString().slice(0, 10);
    const to = new Date(this._rangeEnd).toISOString().slice(0, 10);
    this._downloadString(csv, `roommind_${name}_${from}_${to}.csv`, "text/csv");
    this._openDropdown = null;
  }

  private _exportDiagnostics() {
    const json = this._buildDiagnosticsString();
    if (!json) return;
    const area = this.hass?.areas?.[this._selectedRoom];
    const roomConfig = this.rooms[this._selectedRoom];
    const name = (roomConfig?.display_name || area?.name || this._selectedRoom).replace(/\s+/g, "_").toLowerCase();
    this._downloadString(json, `roommind_diagnostics_${name}.json`, "application/json");
    this._openDropdown = null;
  }

  private _copyToClipboard(text: string): boolean {
    // Try modern API first (requires secure context / HTTPS)
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(text).catch(() => {
        this._copyToClipboardFallback(text);
      });
      return true;
    }
    // Fallback for HTTP contexts
    return this._copyToClipboardFallback(text);
  }

  private _copyToClipboardFallback(text: string): boolean {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (err) {
      console.debug("[RoomMind] clipboard fallback:", err);
    }
    document.body.removeChild(ta);
    return ok;
  }

  private _copyCsvToClipboard() {
    const csv = this._buildCsvString();
    if (!csv) return;
    this._copyToClipboard(csv);
    this._openDropdown = null;
  }

  private _copyDiagnosticsToClipboard() {
    const json = this._buildDiagnosticsString();
    if (!json) return;
    this._copyToClipboard(json);
    this._openDropdown = null;
  }

  private _toggleDropdown(id: "csv" | "diag") {
    this._openDropdown = this._openDropdown === id ? null : id;
  }

  private _closeDropdowns() {
    if (this._openDropdown) {
      this._openDropdown = null;
    }
  }

  private _buildWsParams(): Record<string, unknown> {
    return {
      type: "roommind/analytics/get",
      area_id: this._selectedRoom,
      start_ts: this._rangeStart / 1000,
      end_ts: this._rangeEnd / 1000,
    };
  }

  private async _fetchData() {
    if (!this._selectedRoom) return;
    this._loading = true;
    this._data = null;
    this._chartAnchor = this._rangeEnd;

    try {
      const result = await this.hass.callWS<AnalyticsData>(this._buildWsParams());
      this._data = result;
    } catch (err) {
      console.debug("[RoomMind] fetchData:", err);
      this._data = null;
    } finally {
      this._loading = false;
    }
  }

  private async _silentRefresh() {
    if (!this._selectedRoom || this._loading) return;
    try {
      const result = await this.hass.callWS<AnalyticsData>(this._buildWsParams());
      this._data = result;
      this._chartAnchor = Date.now();
    } catch (err) {
      console.debug("[RoomMind] silentRefresh:", err);
    }
  }

  static styles = [
    infoIconStyles,
    css`
    :host {
      display: block;
    }

    .selector-row {
      margin-bottom: 16px;
    }

    .selector-row ha-select {
      width: 100%;
    }

    .range-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 16px;
      gap: 12px;
    }

    .range-controls {
      display: flex;
      align-items: center;
      gap: 8px;
      position: relative;
    }

    .range-bar {
      display: inline-flex;
      border-radius: 12px;
      border: 1px solid var(--divider-color);
      background: var(--card-background-color);
    }

    .range-bar > :first-child {
      border-radius: 12px 0 0 12px;
    }

    .range-bar > :last-child {
      border-radius: 0 12px 12px 0;
    }

    .range-chip {
      padding: 7px 14px;
      border: none;
      border-right: 1px solid var(--divider-color);
      background: transparent;
      color: var(--secondary-text-color);
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
      transition: background 0.15s ease, color 0.15s ease;
      font-family: inherit;
      white-space: nowrap;
    }

    .range-chip:last-child {
      border-right: none;
    }

    .range-chip:hover:not([active]) {
      background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.08);
      color: var(--primary-text-color);
    }

    .range-chip[active] {
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }

    .picker-chip {
      display: flex;
      align-items: center;
      padding: 0;
      cursor: pointer;
    }

    .picker-chip ha-date-range-picker {
      --mdc-icon-size: 18px;
      --mdc-icon-button-size: 32px;
    }

    .picker-chip.picker-active {
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }

    .date-label {
      font-size: 12px;
      color: var(--secondary-text-color);
      white-space: nowrap;
    }

    .date-label.custom-active {
      color: var(--primary-color);
    }

    .action-buttons {
      display: flex;
      gap: 8px;
    }

    .export-split {
      position: relative;
      display: inline-flex;
    }

    .export-btn {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 7px 14px;
      border: 1px solid var(--divider-color);
      border-radius: 12px;
      background: var(--card-background-color);
      color: var(--secondary-text-color);
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s ease;
      font-family: inherit;
      white-space: nowrap;
      --mdc-icon-size: 14px;
    }

    .export-btn:hover {
      color: var(--primary-text-color);
      border-color: var(--primary-color);
    }

    .export-btn[disabled] {
      opacity: 0.4;
      cursor: default;
    }

    .arrow-icon {
      --mdc-icon-size: 14px;
      margin-left: 2px;
      margin-right: -4px;
    }

    .export-dropdown {
      position: absolute;
      top: 100%;
      right: 0;
      margin-top: 4px;
      min-width: 100%;
      background: var(--card-background-color);
      border: 1px solid var(--divider-color);
      border-radius: 8px;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
      z-index: 10;
      overflow: hidden;
    }

    .export-dropdown button {
      display: flex;
      align-items: center;
      gap: 8px;
      width: 100%;
      padding: 10px 14px;
      border: none;
      background: transparent;
      color: var(--primary-text-color);
      font-size: 12px;
      font-family: inherit;
      cursor: pointer;
      white-space: nowrap;
      --mdc-icon-size: 14px;
    }

    .export-dropdown button:hover {
      background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.08);
    }

    .export-dropdown button + button {
      border-top: 1px solid var(--divider-color);
    }

    @media (max-width: 600px) {
      .range-row {
        flex-wrap: wrap;
      }
      .range-controls {
        flex-wrap: wrap;
      }
      .range-chip {
        padding: 6px 10px;
        font-size: 11px;
      }
    }

    ha-card {
      margin-bottom: 16px;
    }

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16px 16px 0;
      font-size: 16px;
      font-weight: 500;
    }

    .chart-info-toggle {
      --mdc-icon-size: 20px;
    }

    .chart-info-panel {
      margin: 8px 16px 4px;
      padding: 12px 14px;
      border-radius: 8px;
      background: var(--secondary-background-color, rgba(128, 128, 128, 0.06));
      font-size: 13px;
      line-height: 1.6;
      color: var(--secondary-text-color);
    }

    .chart-info-panel p {
      margin: 0 0 8px;
    }

    .chart-info-panel p:last-child {
      margin-bottom: 0;
    }

    .chart-info-panel strong {
      color: var(--primary-text-color);
    }

    .card-content {
      padding: 16px;
    }

    .chart-container {
      padding: 16px;
      height: 300px;
    }

    .confidence-hero {
      margin-bottom: 16px;
    }

    .confidence-top {
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      margin-bottom: 8px;
    }

    .confidence-main {
      display: flex;
      align-items: baseline;
      gap: 8px;
    }

    .confidence-value {
      font-size: 28px;
      font-weight: 600;
      color: var(--primary-text-color);
    }

    .confidence-label {
      font-size: 13px;
      color: var(--secondary-text-color);
    }

    .confidence-meta {
      display: flex;
      align-items: baseline;
      gap: 6px;
    }

    .meta-value {
      font-size: 16px;
      font-weight: 500;
      color: var(--primary-text-color);
    }

    .meta-label {
      font-size: 12px;
      color: var(--secondary-text-color);
    }

    .control-mode-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      margin-top: 8px;
      padding: 4px 12px;
      border-radius: 12px;
      font-size: 12px;
      font-weight: 500;
      --mdc-icon-size: 14px;
    }

    .control-mode-badge.mpc {
      background: rgba(76, 175, 80, 0.12);
      color: var(--success-color, #4caf50);
    }

    .control-mode-badge.bangbang {
      background: rgba(158, 158, 158, 0.12);
      color: var(--secondary-text-color);
    }

    .confidence-bar {
      height: 4px;
      border-radius: 2px;
      background: var(--divider-color);
      overflow: hidden;
    }

    .confidence-fill {
      height: 100%;
      border-radius: 2px;
      background: var(--primary-color);
      transition: width 0.6s ease;
    }

    .model-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap: 12px;
    }

    .model-stat {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 12px;
      border-radius: 8px;
      border: 1px solid var(--divider-color);
      cursor: pointer;
      transition: border-color 0.2s;
    }

    .model-stat.active {
      border-color: var(--primary-color);
    }

    .stat-content {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }

    .model-value {
      font-size: 18px;
      font-weight: 500;
      color: var(--primary-text-color);
    }

    .model-value.pending {
      opacity: 0.2;
    }

    .model-label {
      font-size: 12px;
      color: var(--secondary-text-color);
    }

    .info-panel.stat-info-panel {
      margin-top: 12px;
    }

    .series-legend {
      display: flex;
      justify-content: center;
      gap: 6px;
      padding: 8px 16px 12px;
      flex-wrap: wrap;
    }

    .legend-item {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border: none;
      border-radius: 12px;
      background: transparent;
      color: var(--primary-text-color);
      font-size: 12px;
      font-family: inherit;
      cursor: pointer;
      transition: opacity 0.2s;
    }

    .legend-item:hover {
      background: var(--secondary-background-color, rgba(128, 128, 128, 0.1));
    }

    .legend-item.legend-hidden {
      opacity: 0.35;
    }

    .legend-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      flex-shrink: 0;
    }

    .chart-empty {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      height: 200px;
      gap: 8px;
      color: var(--secondary-text-color);
      opacity: 0.5;
      --mdc-icon-size: 40px;
      font-size: 13px;
    }


    .no-data {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 80px 16px;
      text-align: center;
      color: var(--secondary-text-color);
    }

    .no-data p {
      font-size: 15px;
      max-width: 400px;
      line-height: 1.5;
      margin-top: 16px;
    }

    .loading {
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 80px 16px;
      color: var(--secondary-text-color);
      font-size: 14px;
    }

    @media (max-width: 600px) {
      .model-grid {
        grid-template-columns: repeat(2, 1fr);
        gap: 8px;
      }

      .chart-container {
        padding: 8px;
        height: 240px;
      }

      .range-buttons {
        flex-wrap: wrap;
      }
    }
  `];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-analytics": RsAnalytics;
  }
}
