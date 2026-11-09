/**
 * rs-analytics-chart – Chart card with ha-chart-base and series legend.
 */
import { LitElement, html, css, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, AnalyticsData } from "../../types";
import { localize } from "../../utils/localize";
import { infoIconStyles } from "../../styles/info-icon-styles";
import {
  buildChartSeries,
  buildChartOptions,
  chartHeight,
  type ChartBuildContext,
} from "../../utils/chart-builder";
import { humidityVisualMap, type HumidityColors } from "../../utils/humidity";

// Series drawn for another legend entry: hiding that entry hides them too
const LEGEND_OWNER: Record<string, string> = {
  window_humidity_events: "window_events",
  target_band_base: "target_temp",
  target_band: "target_temp",
  humidity_limits: "humidity",
};
const NOT_IN_LEGEND = new Set([
  "now_marker",
  "now_humidity_marker",
  "window_humidity_events",
  "target_band_base",
  "target_band",
  "humidity_limits",
]);

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
  /** Room judged on both sides (auto): shade the band between heat and cool target. */
  @property({ type: Boolean }) public targetBand = false;

  @state() private _hiddenSeries = new Set(["outdoor_temp", "device_target"]);
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

    const humidityPanel =
      !this._hiddenSeries.has("humidity") && points.some((p) => p.humidity != null);
    const chartCtx: ChartBuildContext = {
      hass: this.hass,
      language: l,
      chartAnchor: this.chartAnchor,
      rangeStart: this.rangeStart,
      rangeEnd: this.rangeEnd,
      forecast: this.data?.forecast,
      isOutdoor: this.isOutdoor,
      humidityPanel,
      targetBand: this.targetBand,
      touch: this._touch,
      zoomed: this._zoomed,
    };
    const allSeries = points.length > 0 ? buildChartSeries(points, chartCtx) : [];

    const visibleY: number[] = [];
    const chartSeries = humidityPanel ? allSeries : allSeries.filter((s) => s.xAxisIndex !== 1);
    const displaySeries = chartSeries.map((s) => {
      const id = s.id as string;
      const ls = (s.lineStyle as Record<string, unknown>) || {};
      const isEvent = id.endsWith("_events");
      if (this._hiddenSeries.has(LEGEND_OWNER[id] ?? id)) {
        const hidden: Record<string, unknown> = {
          ...s,
          lineStyle: { ...ls, width: 0, opacity: 0 },
        };
        if (s.areaStyle) {
          hidden.areaStyle = { ...(s.areaStyle as Record<string, unknown>), opacity: 0 };
        }
        return hidden;
      }
      if (!isEvent && !id.startsWith("target_band") && id !== "now_marker" && s.yAxisIndex !== 1) {
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
    const humidity = displaySeries.find((s) => s.id === "humidity");
    if (humidityPanel && humidity) {
      options.visualMap = humidityVisualMap(
        "humidity",
        humidity.data as Array<[number, number]>,
        this._humidityColors(),
      );
    }

    return html`
      <ha-card>
        <div class="card-header">
          <span>${localize("analytics.temperature", l)}</span>
          <ha-icon
            class="info-icon chart-info-toggle ${this._chartInfoExpanded ? "info-active" : ""}"
            icon="mdi:information-outline"
            @click=${() => {
              this._chartInfoExpanded = !this._chartInfoExpanded;
            }}
          ></ha-icon>
        </div>
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
                <ha-chart-base
                  .hass=${this.hass}
                  .data=${displaySeries}
                  .options=${options}
                  .height=${`${chartHeight(humidityPanel)}px`}
                  style="height: ${chartHeight(humidityPanel)}px; --chart-max-height: ${chartHeight(humidityPanel)}px"
                ></ha-chart-base>
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
      </ha-card>
    `;
  }

  private _renderSeriesLegend(series: Array<Record<string, unknown>>) {
    const legendSeries = series.filter((s) => !NOT_IN_LEGEND.has(s.id as string));
    const { good, fair, poor } = this._humidityColors();
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
    infoIconStyles,
    css`
      :host {
        display: block;
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
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-analytics-chart": RsAnalyticsChart;
  }
}
