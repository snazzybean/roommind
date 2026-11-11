/**
 * rs-analytics-summary – What happened in the selected time range, read from the history:
 * time on target as a ring, runs and window time as tiles with a strip over the range.
 */
import { LitElement, html, css, nothing, svg } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { AnalyticsDataPoint, AnalyticsStats, HomeAssistant, RunOvershoot } from "../../types";
import { localize } from "../../utils/localize";
import { formatHours, formatNumber, formatPercent } from "../../utils/format";
import { tempUnit, toDisplayDelta } from "../../utils/temperature";
import { timeSpans } from "../../utils/analytics-spans";
import { formatClock, formatDay, haTimeZone, sameDayInZone } from "../../utils/analytics-time";
import { tokens } from "../../styles/tokens";
import "../shared/rs-list-card";
import "../shared/rs-stat-tile";

type BandSides = "both" | "heat" | "cool";
type PriceLevel = "cheap" | "normal" | "expensive";

const PRICE_LEVELS: readonly PriceLevel[] = ["cheap", "normal", "expensive"];
const RING_SIZE = 132;
const RING_STROKE = 12;
/** Mirrors COMFORT_TOLERANCE_K (analytics_stats). */
const COMFORT_TOLERANCE_K = 0.5;

@customElement("rs-analytics-summary")
export class RsAnalyticsSummary extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public stats: AnalyticsStats | null = null;
  /** Loaded history and detail points; the strips are drawn from them. */
  @property({ attribute: false }) public points: AnalyticsDataPoint[] = [];
  @property({ type: Number }) public rangeStart = 0;
  @property({ type: Number }) public rangeEnd = 0;
  /** Sides the room is judged on: one-sided rooms can only miss on their own side. */
  @property({ type: String }) public bandSides: BandSides = "both";
  @property({ type: Boolean }) public canHeat = true;
  @property({ type: Boolean }) public canCool = false;
  @property({ type: Boolean }) public hasWindowSensor = false;
  /** The room follows the price (price shift or price-aware heat source): show the price tiles. */
  @property({ type: Boolean }) public showPrice = false;
  @property({ type: String }) public language = "en";

  render() {
    const s = this.stats;
    if (!s || s.hours <= 0) return nothing;
    const l = this.language;
    return html`
      <rs-list-card
        .heading=${localize("analytics.summary", l)}
        .info=${localize("analytics.info.summary", l, { tolerance: this._delta(COMFORT_TOLERANCE_K) })}
      >
        <div class="wrap">
          <div class="body">
            ${this._renderComfort(s)}
            <div class="tiles">
              ${
                this.canHeat || s.heating_hours > 0
                  ? this._runTile("heat", s.heating_hours, s.heating_starts, s.heat_overshoot)
                  : nothing
              }
              ${
                this.canCool || s.cooling_hours > 0
                  ? this._runTile("cool", s.cooling_hours, s.cooling_starts, s.cool_overshoot)
                  : nothing
              }
              ${this.hasWindowSensor || s.window_hours > 0 ? this._windowTile(s) : nothing}
              ${s.price && this.showPrice ? this._priceTiles(s.price) : nothing}
            </div>
          </div>
        </div>
      </rs-list-card>
    `;
  }

  private _renderComfort(s: AnalyticsStats) {
    const l = this.language;
    const c = s.comfort;
    if (!c) {
      return html`<div class="comfort">
        ${this._ring([])}
        <p class="pending">${localize("analytics.comfort_pending", l)}</p>
      </div>`;
    }
    // 99.6 % must not read as 100 % next to "too cold 1 %"
    const within = Math.floor(c.within_pct);
    const showCold = this.bandSides !== "cool";
    const showWarm = this.bandSides !== "heat";
    const rows: Array<[string, string, number]> = [
      ["within", localize("analytics.comfort_on_target", l), within],
    ];
    if (showCold) rows.push(["cold", localize("analytics.comfort_below", l), c.below_pct]);
    if (showWarm) rows.push(["warm", localize("analytics.comfort_above", l), c.above_pct]);
    const arcs: Array<[string, number]> = [];
    if (showCold) arcs.push(["var(--rs-cool)", c.below_pct]);
    arcs.push(["var(--rs-ok)", c.within_pct]);
    if (showWarm) arcs.push(["var(--rs-heat)", c.above_pct]);
    return html`<div class="comfort">
      ${this._ring(arcs, within)}
      <div class="legend">
        ${rows.map(
          ([kind, label, value]) =>
            html`<div class="legend-row">
              <i class="key ${kind}"></i><span>${label}</span
              ><b>${formatPercent(kind === "within" ? value : Math.round(value), this.hass)}</b>
            </div>`,
        )}
        ${
          c.miss_deviation != null
            ? html`<div class="miss">
                ${localize("analytics.miss_deviation", l, { value: this._delta(c.miss_deviation) })}
              </div>`
            : nothing
        }
      </div>
    </div>`;
  }

  /** Donut of the shares in order; empty `arcs` draws the bare track. */
  private _ring(arcs: Array<[string, number]>, within?: number) {
    const r = RING_SIZE / 2 - RING_STROKE / 2 - 2;
    const circumference = 2 * Math.PI * r;
    const visible = arcs.filter(([, v]) => v > 0);
    const gap = visible.length > 1 ? 2.5 : 0;
    let offset = 0;
    const segments = visible.map(([color, value]) => {
      const share = (value / 100) * circumference;
      const length = Math.max(share - gap, 2);
      const seg = svg`<circle
        cx=${RING_SIZE / 2}
        cy=${RING_SIZE / 2}
        r=${r}
        fill="none"
        stroke=${color}
        stroke-width=${RING_STROKE}
        stroke-dasharray="${length} ${circumference}"
        stroke-dashoffset=${-offset}
        transform="rotate(-90 ${RING_SIZE / 2} ${RING_SIZE / 2})"
      />`;
      offset += share;
      return seg;
    });
    return html`<div class="ring" aria-hidden="true">
      <svg width=${RING_SIZE} height=${RING_SIZE} viewBox="0 0 ${RING_SIZE} ${RING_SIZE}">
        <circle
          cx=${RING_SIZE / 2}
          cy=${RING_SIZE / 2}
          r=${r}
          fill="none"
          stroke="var(--rs-fill-strong)"
          stroke-width=${RING_STROKE}
        />
        ${segments}
      </svg>
      ${
        within != null
          ? html`<div class="ring-center">
              <span class="ring-value">${formatPercent(within, this.hass)}</span>
              <span class="ring-label">${localize("analytics.comfort_within", this.language)}</span>
            </div>`
          : nothing
      }
    </div>`;
  }

  private _runTile(
    kind: "heat" | "cool",
    hours: number,
    starts: number,
    overshoot: RunOvershoot | null | undefined,
  ) {
    const l = this.language;
    // A run going since before the range is not counted; "0 runs" next to hours of it reads wrong
    const parts =
      starts > 0 || hours <= 0
        ? [
            localize(starts === 1 ? "analytics.run" : "analytics.runs", l, {
              count: formatNumber(starts, this.hass),
            }),
          ]
        : [];
    if (overshoot) {
      parts.push(
        localize(kind === "cool" ? "analytics.overshoot_cool" : "analytics.overshoot_heat", l, {
          value: this._delta(overshoot.mean),
          max: this._delta(overshoot.max),
        }),
      );
    }
    const mode = kind === "heat" ? "heating" : "cooling";
    return html`<rs-stat-tile
      .icon=${kind === "heat" ? "mdi:fire" : "mdi:snowflake"}
      tone=${kind}
      .label=${localize(kind === "heat" ? "analytics.heating_period" : "analytics.cooling_period", l)}
      .value=${formatHours(hours, this.language)}
      .sub=${parts.join(" · ")}
    >
      ${this._strip(
        timeSpans(this.points, (p) => p.mode === mode),
        kind === "heat" ? "var(--rs-heat)" : "var(--rs-cool)",
      )}
    </rs-stat-tile>`;
  }

  private _windowTile(s: AnalyticsStats) {
    return html`<rs-stat-tile
      icon="mdi:window-open-variant"
      .label=${localize("analytics.window_open_period", this.language)}
      .value=${formatHours(s.window_hours, this.language)}
    >
      ${this._strip(
        timeSpans(this.points, (p) => p.window_open),
        "var(--secondary-text-color)",
      )}
    </rs-stat-tile>`;
  }

  /** One tile per mode that ran with a price source; the shift goes with the first one. */
  private _priceTiles(price: NonNullable<AnalyticsStats["price"]>) {
    const l = this.language;
    const shifted =
      price.shifted_hours > 0
        ? localize("analytics.price_shifted", l, {
            value: formatHours(price.shifted_hours, this.language),
          })
        : "";
    const modes = (
      [
        ["heating", price.heating_hours],
        ["cooling", price.cooling_hours],
      ] as const
    ).filter(([, hours]) => PRICE_LEVELS.some((lv) => (hours[lv] ?? 0) > 0));
    if (modes.length === 0) {
      return shifted
        ? html`<rs-stat-tile
            icon="mdi:cash-clock"
            .label=${localize("analytics.price", l)}
            .value=${formatHours(price.shifted_hours, this.language)}
            .sub=${localize("analytics.price_shifted_short", l)}
          ></rs-stat-tile>`
        : nothing;
    }
    return modes.map(([mode, hours], i) => {
      const total = PRICE_LEVELS.reduce((sum, lv) => sum + (hours[lv] ?? 0), 0);
      // Shares of the run time: "3 min cheap" read as if the room had hardly heated
      const share = (lv: PriceLevel) =>
        `${formatPercent((100 * (hours[lv] ?? 0)) / total, this.hass)} ${localize(`settings.price_level_${lv}`, l)}`;
      const present = PRICE_LEVELS.filter((lv) => (hours[lv] ?? 0) > 0);
      const others = present.filter((lv) => lv !== "cheap").map(share);
      if (i === 0 && shifted) others.push(shifted);
      return html`<rs-stat-tile
        icon="mdi:cash-clock"
        .label=${localize(mode === "heating" ? "analytics.price_heating" : "analytics.price_cooling", l)}
        .value=${share("cheap")}
        .sub=${others.join(" · ")}
      >
        <div slot="visual">
          <div class="split">
            ${present.map(
              (lv) => html`<i class="level-${lv}" style="flex: ${hours[lv] ?? 0}"></i>`,
            )}
          </div>
          <div class="levels">
            ${present.map(
              (lv) =>
                html`<span
                  ><i class="key level-${lv}"></i>${localize(`settings.price_level_${lv}`, l)}</span
                >`,
            )}
          </div>
        </div>
      </rs-stat-tile>`;
    });
  }

  /** Spans over the range as bars on a track, start and end of the range under it. */
  private _strip(spans: Array<[number, number]>, color: string) {
    const start = this.rangeStart;
    const length = Math.max(this.rangeEnd - start, 1);
    const pct = (ms: number) => Math.min(Math.max(((ms - start) / length) * 100, 0), 100);
    const zone = haTimeZone(this.hass);
    const format = sameDayInZone(start, this.rangeEnd, zone) ? formatClock : formatDay;
    return html`<div slot="visual" aria-hidden="true">
      <div class="strip">
        ${spans
          .filter(([a, b]) => b > start && a < this.rangeEnd)
          .map(
            ([a, b]) =>
              html`<i
                style="left: ${pct(a)}%; width: ${pct(b) - pct(a)}%; background: ${color}"
              ></i>`,
          )}
      </div>
      <div class="axis">
        <span>${format(start, this.language, zone)}</span
        ><span>${format(this.rangeEnd, this.language, zone)}</span>
      </div>
    </div>`;
  }

  private _delta(kelvin: number): string {
    return `${formatNumber(toDisplayDelta(kelvin, this.hass), this.hass, 1)} ${tempUnit(this.hass)}`;
  }

  static styles = [
    tokens,
    css`
      :host {
        display: block;
        margin-bottom: var(--rs-space-4);
      }

      .wrap {
        container-type: inline-size;
        padding: var(--rs-space-2) var(--rs-space-4) var(--rs-space-2);
      }

      .comfort {
        display: flex;
        align-items: center;
        gap: 18px;
        min-width: 0;
      }

      .ring {
        position: relative;
        flex: none;
        width: ${RING_SIZE}px;
        height: ${RING_SIZE}px;
      }

      .ring svg {
        display: block;
      }

      .ring-center {
        position: absolute;
        inset: 0;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        text-align: center;
      }

      .ring-value {
        font-size: 28px;
        font-weight: 300;
        line-height: 1.1;
        font-variant-numeric: tabular-nums;
      }

      .ring-label {
        font-size: var(--rs-font-sm);
        color: var(--secondary-text-color);
      }

      .pending {
        margin: 0;
        font-size: 13px;
        line-height: 1.5;
        color: var(--secondary-text-color);
      }

      .legend {
        display: flex;
        flex-direction: column;
        gap: 6px;
        min-width: 0;
        flex: 1;
        font-size: 13px;
      }

      .legend-row {
        display: flex;
        align-items: center;
        gap: var(--rs-space-2);
      }

      .legend-row b {
        margin-left: auto;
        padding-left: 10px;
        font-weight: 500;
        font-variant-numeric: tabular-nums;
      }

      .miss {
        font-size: var(--rs-font-sm);
        line-height: 1.4;
        color: var(--secondary-text-color);
      }

      .key {
        width: 10px;
        height: 10px;
        border-radius: 3px;
        flex: none;
      }

      .key.within {
        background: var(--rs-ok);
      }
      .key.cold {
        background: var(--rs-cool);
      }
      .key.warm {
        background: var(--rs-heat);
      }

      .tiles {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(165px, 1fr));
        gap: 10px;
        margin-top: var(--rs-space-4);
      }

      @container (min-width: 860px) {
        .body {
          display: grid;
          grid-template-columns: minmax(280px, 330px) minmax(0, 1fr);
          gap: var(--rs-space-4);
          align-items: center;
        }

        .tiles {
          margin-top: 0;
        }
      }

      @container (max-width: 400px) {
        .tiles {
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }

        .comfort {
          gap: var(--rs-space-3);
        }
      }

      .strip {
        position: relative;
        height: 10px;
        border-radius: 5px;
        background: var(--rs-fill);
        overflow: hidden;
      }

      .strip i {
        position: absolute;
        top: 0;
        bottom: 0;
        min-width: 2px;
        border-radius: 2px;
      }

      .axis {
        display: flex;
        justify-content: space-between;
        gap: var(--rs-space-2);
        margin-top: 3px;
        font-size: 10px;
        color: var(--secondary-text-color);
        font-variant-numeric: tabular-nums;
        white-space: nowrap;
      }

      .levels {
        display: flex;
        flex-wrap: wrap;
        gap: 2px 10px;
        margin-top: 3px;
        font-size: 10px;
        color: var(--secondary-text-color);
      }

      .levels span {
        display: inline-flex;
        align-items: center;
        gap: 4px;
      }

      .levels .key {
        width: 8px;
        height: 8px;
        border-radius: 2px;
      }

      .split {
        display: flex;
        gap: 2px;
        height: 10px;
        border-radius: 5px;
        overflow: hidden;
      }

      .split i {
        min-width: 3px;
      }

      .level-cheap {
        background: var(--rs-ok);
      }
      .level-normal {
        background: color-mix(in srgb, var(--secondary-text-color) 50%, transparent);
      }
      .level-expensive {
        background: var(--rs-err);
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-analytics-summary": RsAnalyticsSummary;
  }
}
