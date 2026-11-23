/**
 * rs-analytics-chart – Chart card with ha-chart-base and series legend.
 */
import { LitElement, html, css, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, AnalyticsData, AnalyticsDataPoint } from "../../types";
import { localize, type TranslationKey } from "../../utils/localize";
import { tokens } from "../../styles/tokens";
import "../shared/rs-list-card";
import "../shared/rs-info-icon";
import {
  buildChartSeries,
  buildChartOptions,
  chartHeight,
  placeEventStrips,
  placeOnPanels,
  visiblePanels,
  type ChartBuildContext,
  type ChartColors,
  panelTitle,
  panelTops,
  priceVisualMap,
} from "../../utils/chart-builder";
import { humidityVisualMap, type HumidityColors } from "../../utils/humidity";
import { tempUnit, toDisplayDelta } from "../../utils/temperature";
import { formatNumber } from "../../utils/format";
import { timeSpans } from "../../utils/analytics-spans";

type MasterGateState = "comfort" | "eco" | "blocked" | "unavailable";

// Series drawn for another legend entry: hiding that entry hides them too
const LEGEND_OWNER: Record<string, string> = {
  target_band_base: "target_temp",
  target_band: "target_temp",
  target_band_cold_base: "target_temp",
  target_band_cold: "target_temp",
  target_band_warm_base: "target_temp",
  target_band_warm: "target_temp",
  humidity_limits: "humidity",
  humidity_band_base: "humidity",
  humidity_band: "humidity",
};
// Per-panel copies of the window band and the "now" line carry the panel in their id.
// The past model line and the future prediction are one "Prediction" entry while both are drawn.
const legendOwner = (id: string, prediction = false) =>
  id.startsWith("window_events_")
    ? "window_events"
    : prediction && id === "backtest_temp"
      ? "predicted_temp"
      : (LEGEND_OWNER[id] ?? id);
const inLegend = (id: string, prediction = false) =>
  !(id in LEGEND_OWNER) &&
  !(prediction && id === "backtest_temp") &&
  !id.startsWith("window_events_") &&
  !id.startsWith("now_marker");
const hasPrediction = (series: Array<Record<string, unknown>>) =>
  series.some((s) => s.id === "predicted_temp");

interface EChartsLike {
  on(event: string, handler: () => void): void;
  getOption(): { dataZoom?: Array<{ id?: string; start: number; end: number }> };
  dispatchAction(action: Record<string, unknown>): void;
}

@customElement("rs-analytics-chart")
export class RsAnalyticsChart extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public data: AnalyticsData | null = null;
  @property({ type: Number }) public rangeStart = 0;
  @property({ type: Number }) public rangeEnd = 0;
  @property({ type: Number }) public chartAnchor = 0;
  @property({ type: String }) public language = "en";
  @property({ type: Boolean }) public isOutdoor = false;
  /** Sides the room is judged on (auto both, heat only, cool only): shades that range. */
  @property({ attribute: false }) public targetBand: "both" | "heat" | "cool" | null = null;
  /** The room follows the price: draw the price panel. */
  @property({ type: Boolean }) public showPrice = false;

  @state() private _hiddenSeries = new Set(["device_target"]);
  @state() private _chartInfoExpanded = false;
  @state() private _zoomed = false;

  private readonly _touch = matchMedia("(pointer: coarse)").matches;
  // The ECharts instance the zoom listener sits on; ha-chart-base creates it lazily
  private _chart: EChartsLike | null = null;
  private _armRetry?: number;

  protected updated(changed: PropertyValues) {
    super.updated(changed);
    this._armZoom();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    clearTimeout(this._armRetry);
    this._chart = null;
  }

  /** Drag-to-zoom stays armed across option updates; zoom state drives touch panning. */
  private _armZoom(attempt = 0) {
    clearTimeout(this._armRetry);
    const base = this.renderRoot.querySelector("ha-chart-base") as { chart?: EChartsLike } | null;
    const chart = base?.chart;
    if (!chart) {
      if (base && attempt < 20)
        this._armRetry = window.setTimeout(() => this._armZoom(attempt + 1), 150);
      return;
    }
    if (chart !== this._chart) {
      this._chart = chart;
      chart.on("datazoom", () => {
        const zoom = chart.getOption().dataZoom?.find((z) => z.id === "dataZoom");
        this._zoomed = !!zoom && (zoom.start > 0 || zoom.end < 100);
      });
    }
    if (!this._touch) {
      chart.dispatchAction({
        type: "takeGlobalCursor",
        key: "dataZoomSelect",
        dataZoomSelectActive: true,
      });
    }
  }

  render() {
    const l = this.language;
    const points = this.data ? [...this.data.history, ...this.data.detail] : [];
    const allPoints = [...points, ...(this.data?.forecast ?? [])];

    const chartCtx: ChartBuildContext = {
      hass: this.hass,
      language: l,
      chartAnchor: this.chartAnchor,
      rangeStart: this.rangeStart,
      rangeEnd: this.rangeEnd,
      forecast: this.data?.forecast,
      isOutdoor: this.isOutdoor,
      targetBand: this.targetBand,
      priceUnit: this.data?.price_unit ?? "",
      touch: this._touch,
      zoomed: this._zoomed,
      colors: this._chartColors(),
      hidden: this._hiddenSeries,
      showPrice: this.showPrice,
    };
    const allSeries = points.length > 0 ? buildChartSeries(points, chartCtx) : [];
    const panels = visiblePanels(allSeries, this._hiddenSeries);
    chartCtx.panels = panels;

    const visibleY: number[] = [];
    // With every temperature series hidden the axis keeps the range of the room and its targets
    // (the device setpoint, hidden by default, would stretch it to the boost); else it scales to
    // the run strips' placeholder value and they fill the whole plot
    const allY: number[] = [];
    const chartSeries = placeOnPanels(allSeries, panels);
    const prediction = hasPrediction(allSeries);
    const displaySeries = chartSeries.map((s) => {
      const id = s.id as string;
      const ls = (s.lineStyle as Record<string, unknown>) || {};
      const isEvent = id.endsWith("_events");
      const onTempAxis =
        !isEvent && !id.startsWith("target_band") && id !== "now_marker" && !s.xAxisIndex;
      if (onTempAxis && id !== "device_target") {
        for (const point of s.data as Array<[number, number]>) {
          if (point && point[1] != null) allY.push(point[1]);
        }
      }
      if (this._hiddenSeries.has(legendOwner(id, prediction))) {
        const hidden: Record<string, unknown> = {
          ...s,
          lineStyle: { ...ls, width: 0, opacity: 0 },
        };
        if (s.areaStyle) {
          hidden.areaStyle = { ...(s.areaStyle as Record<string, unknown>), opacity: 0 };
        }
        return hidden;
      }
      if (onTempAxis) {
        for (const point of s.data as Array<[number, number]>) {
          if (point && point[1] != null) {
            visibleY.push(point[1]);
          }
        }
      }
      const visible: Record<string, unknown> = { ...s, lineStyle: { ...ls, opacity: 1 } };
      if (s.areaStyle) {
        const area = s.areaStyle as Record<string, unknown>;
        visible.areaStyle = { ...area, opacity: area.opacity ?? 1 };
      }
      return visible;
    });

    const options = buildChartOptions(visibleY.length > 0 ? visibleY : allY, allPoints, chartCtx);
    const mainAxis = (Array.isArray(options.yAxis) ? options.yAxis[0] : options.yAxis) as {
      min?: number;
      max?: number;
    };
    const plotted =
      mainAxis.min != null && mainAxis.max != null
        ? placeEventStrips(displaySeries, mainAxis.min, mainAxis.max)
        : displaySeries.filter((s) => !(s.id as string).endsWith("_events"));
    const visualMaps: Array<Record<string, unknown>> = [];
    const humidity = displaySeries.find((s) => s.id === "humidity");
    if (humidity) {
      visualMaps.push(
        humidityVisualMap(
          "humidity",
          humidity.data as Array<[number, number]>,
          this._humidityColors(),
        ),
      );
    }
    if (panels.includes("price")) visualMaps.push(priceVisualMap(points, this._priceColors()));
    if (visualMaps.length > 0) options.visualMap = visualMaps;
    const tops = panelTops(panels);

    return html`
      <rs-list-card unclipped .heading=${localize("analytics.history_chart", l)}>
        <rs-info-icon
          slot="header-extras"
          disclosure
          .label=${localize("analytics.chart_info_title", l)}
          .expanded=${this._chartInfoExpanded}
          @info-toggle=${() => {
            this._chartInfoExpanded = !this._chartInfoExpanded;
          }}
        ></rs-info-icon>
        ${
          this._chartInfoExpanded
            ? html`<div class="chart-info-panel">
                ${this._renderMarkdown(
                  localize("analytics.chart_info_body", l, {
                    tolerance: `${formatNumber(toDisplayDelta(0.5, this.hass), this.hass, 1)} ${tempUnit(this.hass)}`,
                  }),
                )}
              </div>`
            : nothing
        }
        ${
          points.length > 0
            ? html`
                <div class="chart-wrap">
                  <ha-chart-base
                    .hass=${this.hass}
                    .data=${plotted}
                    .options=${options}
                    .height=${`${chartHeight(panels)}px`}
                    style="height: ${chartHeight(panels)}px; --chart-max-height: ${chartHeight(panels)}px"
                  ></ha-chart-base>
                  ${(["main", ...panels] as const).map(
                    (p, i) =>
                      html`<div class="panel-title" style="top: ${tops[i] - 17}px">
                        ${panelTitle(p, l, {
                          temp: tempUnit(this.hass),
                          price: this.data?.price_unit ?? "",
                        })}
                      </div>`,
                  )}
                </div>
                ${this._renderMasterGateTimeline(points)} ${this._renderBoilerCallTimeline(points)}
                ${this._renderSeriesLegend(allSeries)}
                <div class="zoom-hint">
                  ${localize(this._touch ? "analytics.zoom_hint_touch" : "analytics.zoom_hint", l)}
                </div>
              `
            : html`<div class="chart-empty">
                <ha-icon icon="mdi:chart-line"></ha-icon>
                <span>${localize("analytics.no_data", l)}</span>
              </div>`
        }
      </rs-list-card>
    `;
  }

  private _renderMasterGateTimeline(points: AnalyticsDataPoint[]) {
    const sharedPoints = points.filter((p) => !!p.shared_system_id);
    if (sharedPoints.length === 0) return nothing;

    const states: Array<[MasterGateState, Array<[number, number]>]> = [
      [
        "comfort",
        timeSpans(
          sharedPoints,
          (p) => p.shared_system_schedule_active === true && !p.shared_system_demand_blocked,
        ),
      ],
      [
        "eco",
        timeSpans(
          sharedPoints,
          (p) => p.shared_system_schedule_active === false && !p.shared_system_demand_blocked,
        ),
      ],
      [
        "blocked",
        timeSpans(
          sharedPoints,
          (p) =>
            p.shared_system_demand_blocked === true &&
            p.shared_system_block_reason !== "master_schedule_unavailable",
        ),
      ],
      [
        "unavailable",
        timeSpans(
          sharedPoints,
          (p) =>
            p.shared_system_demand_blocked === true &&
            p.shared_system_block_reason === "master_schedule_unavailable",
        ),
      ],
    ];
    const start = this.rangeStart;
    const length = Math.max(this.rangeEnd - start, 1);
    const pct = (ms: number) => Math.min(Math.max(((ms - start) / length) * 100, 0), 100);
    const labels: Record<MasterGateState, string> = {
      comfort: localize("analytics.master_gate_comfort", this.language),
      eco: localize("analytics.master_gate_eco", this.language),
      blocked: localize("analytics.master_gate_blocked", this.language),
      unavailable: localize("analytics.master_gate_unavailable", this.language),
    };
    const colours: Record<MasterGateState, string> = {
      comfort: "var(--rs-ok)",
      eco: "var(--secondary-text-color)",
      blocked: "var(--rs-heat)",
      unavailable: "var(--rs-cool)",
    };
    const visibleStates = states.filter(([, spans]) =>
      spans.some(([a, b]) => b > start && a < this.rangeEnd),
    );

    return html`
      <div
        class="master-gate-timeline"
        aria-label=${localize("analytics.master_gate", this.language)}
      >
        <div class="master-gate-heading">${localize("analytics.master_gate", this.language)}</div>
        <div class="master-gate-track">
          ${visibleStates.flatMap(([state, spans]) =>
            spans
              .filter(([a, b]) => b > start && a < this.rangeEnd)
              .map(
                ([a, b]) =>
                  html`<i
                    title=${labels[state]}
                    style="left: ${pct(a)}%; width: ${pct(b) - pct(a)}%; background: ${colours[state]}"
                  ></i>`,
              ),
          )}
        </div>
        <div class="master-gate-key">
          ${visibleStates.map(
            ([state]) =>
              html`<span><i style="background: ${colours[state]}"></i>${labels[state]}</span>`,
          )}
        </div>
      </div>
    `;
  }

  private _renderSeriesLegend(series: Array<Record<string, unknown>>) {
    const prediction = hasPrediction(series);
    const legendSeries = series.filter((s) => inLegend(s.id as string, prediction) && s.name);
    const { good, fair, poor } = this._humidityColors();
    return html`
      <div class="series-legend">
        ${legendSeries.map((s) => {
          const id = s.id as string;
          const hidden = this._hiddenSeries.has(id);
          return html`
            <button
              type="button"
              class="legend-item ${hidden ? "legend-hidden" : ""}"
              aria-pressed=${hidden ? "false" : "true"}
              @click=${() => this._toggleSeries(id)}
            >
              <span
                class="legend-dot"
                style="background: ${
                  id === "humidity"
                    ? `linear-gradient(90deg, ${good} 0 50%, ${fair} 50% 75%, ${poor} 75%)`
                    : s.color
                }"
              ></span>
              ${s.name}
            </button>
          `;
        })}
      </div>
    `;
  }

  private _renderBoilerCallTimeline(points: AnalyticsDataPoint[]) {
    const sharedPoints = points.filter(
      (p) => p.shared_system_zone_action != null || p.shared_system_master_action != null,
    );
    if (sharedPoints.length === 0 || this.isOutdoor) return nothing;
    const start = this.rangeStart;
    const length = Math.max(this.rangeEnd - start, 1);
    const pct = (ms: number) => Math.min(Math.max(((ms - start) / length) * 100, 0), 100);
    const tracks = [
      {
        key: "analytics.zone_calling_heat" as TranslationKey,
        colour: "var(--rs-warn)",
        spans: timeSpans(sharedPoints, (p) => p.shared_system_zone_action === "heating"),
      },
      {
        key: "analytics.boiler_calling_heat" as TranslationKey,
        colour: "var(--rs-heat)",
        spans: timeSpans(sharedPoints, (p) => p.shared_system_master_action === "heating"),
      },
    ].filter(({ spans }) => spans.some(([a, b]) => b > start && a < this.rangeEnd));

    return html`
      <div
        class="master-gate-timeline boiler-call-timeline"
        aria-label=${localize("analytics.boiler_calling_heat", this.language)}
      >
        <div class="master-gate-heading">
          ${localize("analytics.boiler_calling_heat", this.language)}
        </div>
        ${tracks.map(
          ({ key, colour, spans }) => html`
            <div class="boiler-call-row">
              <span class="boiler-call-label">${localize(key, this.language)}</span>
              <div class="master-gate-track">
                ${spans
                  .filter(([a, b]) => b > start && a < this.rangeEnd)
                  .map(
                    ([a, b]) =>
                      html`<i
                        title=${localize(key, this.language)}
                        style="left: ${pct(a)}%; width: ${pct(b) - pct(a)}%; background: ${colour}"
                      ></i>`,
                  )}
              </div>
            </div>
          `,
        )}
        <div class="master-gate-key">
          ${tracks.map(
            ({ key, colour }) =>
              html`<span
                ><i style="background: ${colour}"></i>${localize(key, this.language)}</span
              >`,
          )}
        </div>
      </div>
    `;
  }

  /** Token colours for the canvas: heat and cool as everywhere on the page, the room line neutral. */
  private _chartColors(): ChartColors {
    const style = getComputedStyle(this);
    const token = (name: string, fallback: string) =>
      style.getPropertyValue(name).trim() || fallback;
    return {
      temp: token("--primary-text-color", "#212121"),
      prediction: token("--primary-color", "#03a9f4"),
      target: token("--success-color", "#4caf50"),
      heat: token("--rs-heat", "#ff8100"),
      cool: token("--rs-cool", "#2b9af9"),
      neutral: token("--secondary-text-color", "#727272"),
    };
  }

  private _priceColors() {
    const style = getComputedStyle(this);
    const token = (name: string, fallback: string) =>
      style.getPropertyValue(name).trim() || fallback;
    return {
      cheap: token("--success-color", "#4caf50"),
      normal: token("--secondary-text-color", "#8a8a8a"),
      expensive: token("--error-color", "#db4437"),
    };
  }

  private _humidityColors(): HumidityColors {
    const style = getComputedStyle(this);
    const token = (name: string, fallback: string) =>
      style.getPropertyValue(name).trim() || fallback;
    return {
      good: token("--success-color", "#4caf50"),
      fair: token("--warning-color", "#ffa600"),
      poor: token("--error-color", "#db4437"),
    };
  }

  private _renderMarkdown(text: string) {
    const paragraphs = text.split("\n\n");
    return paragraphs.map(
      (p) =>
        html`<p>
          ${p
            .split(/(\*\*.*?\*\*)/)
            .map((part) =>
              part.startsWith("**") && part.endsWith("**")
                ? html`<strong>${part.slice(2, -2)}</strong>`
                : part,
            )}
        </p>`,
    );
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

  static styles = [
    tokens,
    css`
      :host {
        display: block;
        margin-bottom: var(--rs-space-4);
      }

      .chart-wrap {
        position: relative;
      }

      /* Heading of each plot below the temperature, in the gap above it (chart-builder PANEL_GAP) */
      .panel-title {
        position: absolute;
        left: 56px;
        font-size: 11px;
        line-height: 14px;
        color: var(--secondary-text-color);
        pointer-events: none;
      }

      .chart-info-panel {
        margin: 8px 16px 4px;
        padding: 12px 14px;
        border-radius: var(--rs-radius-sm);
        background: var(--rs-fill);
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

      .zoom-hint {
        padding: 0 16px 12px;
        font-size: 12px;
        text-align: center;
        color: var(--secondary-text-color);
      }

      .master-gate-timeline {
        margin: 8px 16px 0;
        font-size: 12px;
      }

      .master-gate-heading {
        margin-bottom: 4px;
        color: var(--secondary-text-color);
      }

      .master-gate-track {
        position: relative;
        height: 10px;
        border-radius: 5px;
        background: var(--rs-fill);
        overflow: hidden;
      }

      .master-gate-track i {
        position: absolute;
        top: 0;
        bottom: 0;
        min-width: 2px;
      }

      .boiler-call-row {
        display: grid;
        grid-template-columns: minmax(110px, 0.3fr) 1fr;
        align-items: center;
        gap: 8px;
        margin-bottom: 4px;
      }

      .boiler-call-label {
        color: var(--secondary-text-color);
      }

      .master-gate-key {
        display: flex;
        flex-wrap: wrap;
        gap: 2px 10px;
        margin-top: 4px;
        color: var(--secondary-text-color);
      }

      .master-gate-key span {
        display: inline-flex;
        align-items: center;
        gap: 4px;
      }

      .master-gate-key i {
        width: 8px;
        height: 8px;
        border-radius: 2px;
      }

      .series-legend {
        display: flex;
        justify-content: center;
        gap: 6px;
        padding: 8px 16px 4px;
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
        background: var(--rs-fill);
      }

      .legend-item:focus-visible {
        outline: 2px solid var(--primary-color);
        outline-offset: 1px;
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
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-analytics-chart": RsAnalyticsChart;
  }
}
