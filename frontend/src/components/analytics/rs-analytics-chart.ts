/**
 * rs-analytics-chart – Chart card with ha-chart-base and series legend.
 */
import { LitElement, html, css, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, AnalyticsData } from "../../types";
import { localize } from "../../utils/localize";
import { tokens } from "../../styles/tokens";
import "../shared/rs-list-card";
import "../shared/rs-info-icon";
import {
  buildChartSeries,
  buildChartOptions,
  chartHeight,
  placeOnPanels,
  visiblePanels,
  type ChartBuildContext,
  panelTitle,
  panelTops,
  priceVisualMap,
} from "../../utils/chart-builder";
import { humidityVisualMap, type HumidityColors } from "../../utils/humidity";
import { tempUnit } from "../../utils/temperature";

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
// Per-panel copies of the window band and the "now" line carry the panel in their id
const legendOwner = (id: string) =>
  id.startsWith("window_events_") ? "window_events" : (LEGEND_OWNER[id] ?? id);
const inLegend = (id: string) =>
  !(id in LEGEND_OWNER) && !id.startsWith("window_events_") && !id.startsWith("now_marker");

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
    };
    const allSeries = points.length > 0 ? buildChartSeries(points, chartCtx) : [];
    const panels = visiblePanels(allSeries, this._hiddenSeries);
    chartCtx.panels = panels;

    const visibleY: number[] = [];
    const chartSeries = placeOnPanels(allSeries, panels);
    const displaySeries = chartSeries.map((s) => {
      const id = s.id as string;
      const ls = (s.lineStyle as Record<string, unknown>) || {};
      const isEvent = id.endsWith("_events");
      if (this._hiddenSeries.has(legendOwner(id))) {
        const hidden: Record<string, unknown> = {
          ...s,
          lineStyle: { ...ls, width: 0, opacity: 0 },
        };
        if (s.areaStyle) {
          hidden.areaStyle = { ...(s.areaStyle as Record<string, unknown>), opacity: 0 };
        }
        return hidden;
      }
      if (!isEvent && !id.startsWith("target_band") && id !== "now_marker" && !s.xAxisIndex) {
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

    const options = buildChartOptions(visibleY, allPoints, chartCtx);
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
                ${this._renderMarkdown(localize("analytics.chart_info_body", l))}
              </div>`
            : nothing
        }
        ${
          points.length > 0
            ? html`
                <div class="chart-wrap">
                  <ha-chart-base
                    .hass=${this.hass}
                    .data=${displaySeries}
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

  private _renderSeriesLegend(series: Array<Record<string, unknown>>) {
    const legendSeries = series.filter((s) => inLegend(s.id as string) && s.name);
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
