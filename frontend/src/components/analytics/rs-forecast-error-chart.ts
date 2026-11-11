/**
 * rs-forecast-error-chart – How far the model's ~3-min forecast was off per day (backend
 * `daily_history`, mean absolute error), one bar per day, the days MPC controlled shaded.
 * Plain SVG drawn at the measured width. Each day is a button over its column with the shared
 * tooltip; one tab stop, arrow keys move.
 */
import { LitElement, html, css, nothing, svg } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, ModelDay } from "../../types";
import { localize } from "../../utils/localize";
import { formatNumber } from "../../utils/format";
import { tempUnit, toDisplayDelta } from "../../utils/temperature";
import { tokens } from "../../styles/tokens";
import "../shared/rs-tooltip";
import "../shared/rs-info-icon";

const HEIGHT = 150;
const LEFT = 52;
const RIGHT = 8;
const TOP = 10;
const BOTTOM = 22;
const BAR_MAX_W = 18;
const DAY_MS = 86_400_000;
const HIT = 28;
// Axis tops in the display unit; the smallest one above the largest day wins
const NICE_MAX = [0.1, 0.2, 0.3, 0.5, 1, 2, 3, 5, 10];

// Local noon: a bare date would be parsed as UTC midnight and land on the day before
const dayMs = (date: string) => new Date(`${date}T12:00:00`).getTime();

@customElement("rs-forecast-error-chart")
export class RsForecastErrorChart extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public days: ModelDay[] = [];
  @property({ type: String }) public language = "en";

  @state() private _width = 0;
  /** Day that has the tab stop (null = the newest) and the one whose tooltip is open. */
  @state() private _focusIdx: number | null = null;
  @state() private _activeIdx: number | null = null;
  private _resize?: ResizeObserver;

  connectedCallback() {
    super.connectedCallback();
    this._resize = new ResizeObserver((entries) => {
      const width = Math.floor(entries[0]?.contentRect.width ?? 0);
      if (width !== this._width) this._width = width;
    });
    this._resize.observe(this);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    this._resize?.disconnect();
  }

  protected willUpdate(changed: Map<string, unknown>): void {
    if (changed.has("days")) {
      this._focusIdx = null;
      this._activeIdx = null;
    }
  }

  render() {
    const l = this.language;
    const days = this.days;
    const fmtDay = new Intl.DateTimeFormat(l, { day: "numeric", month: "short" });
    const heading = html`<div class="heading">
      <span>${localize("analytics.forecast_error_title", l, { unit: tempUnit(this.hass) })}</span>
      <rs-info-icon .text=${localize("analytics.info.forecast_error", l)}></rs-info-icon>
    </div>`;
    const measured = days.filter((d) => d.error != null);
    if (measured.length === 0) {
      return html`${heading}
        <p class="note">${localize("analytics.forecast_error_empty", l)}</p>`;
    }
    const last = measured[measured.length - 1];
    const label = localize("analytics.forecast_error_label", l, {
      from: fmtDay.format(dayMs(days[0].date)),
      to: fmtDay.format(dayMs(days[days.length - 1].date)),
      end: this._value(last.error ?? 0),
    });
    const hasMpc = days.some((d) => d.mpc_active);
    return html`
      ${heading}
      <div class="plot" role="group" aria-label=${label}>
        ${this._width > 0 ? this._svg(days, fmtDay) : nothing}
        ${this._width > 0 ? this._hits(days, fmtDay) : nothing}
      </div>
      <div class="legend">
        <span><i class="key bar"></i>${localize("analytics.forecast_error_legend", l)}</span>
        ${
          hasMpc
            ? html`<span
                ><i class="key mpc"></i>${localize("analytics.confidence_mpc_days", l)}</span
              >`
            : nothing
        }
      </div>
      ${
        days.length < 2
          ? html`<p class="note">
              ${localize("analytics.forecast_error_start", l, {
                date: fmtDay.format(dayMs(days[0].date)),
              })}
            </p>`
          : nothing
      }
    `;
  }

  private _value(kelvin: number): string {
    return `${formatNumber(toDisplayDelta(kelvin, this.hass), this.hass, 2)} ${tempUnit(this.hass)}`;
  }

  private _geometry(days: ModelDay[]) {
    const right = this._width - RIGHT;
    const bottom = HEIGHT - BOTTOM;
    const start = dayMs(days[0].date);
    const span = Math.max(Math.round((dayMs(days[days.length - 1].date) - start) / DAY_MS), 1);
    // One day's width; a single day sits in the middle of the plot
    const dayW = (right - LEFT) / (days.length === 1 ? 1 : span + 1);
    const x = (date: string) =>
      days.length === 1
        ? (LEFT + right) / 2
        : LEFT +
          dayW / 2 +
          (Math.round((dayMs(date) - start) / DAY_MS) / span) * (right - LEFT - dayW);
    const largest = Math.max(...days.map((d) => toDisplayDelta(d.error ?? 0, this.hass)));
    const top = NICE_MAX.find((v) => v >= largest * 1.1) ?? Math.ceil(largest * 1.1);
    const y = (display: number) => bottom - (Math.min(display, top) / top) * (bottom - TOP);
    return { right, bottom, dayW, x, y, top };
  }

  private _dayText(d: ModelDay, fmtDay: Intl.DateTimeFormat): string {
    const l = this.language;
    const date = fmtDay.format(dayMs(d.date));
    if (d.error == null) return localize("analytics.forecast_error_day_none", l, { date });
    const text = localize("analytics.forecast_error_day", l, {
      date,
      value: this._value(d.error),
      steps: formatNumber(d.error_steps, this.hass),
    });
    return d.mpc_active ? `${text} · ${localize("analytics.confidence_mpc_days", l)}` : text;
  }

  private _hits(days: ModelDay[], fmtDay: Intl.DateTimeFormat) {
    const { dayW, x, bottom } = this._geometry(days);
    // Never wider than a day, so neighbouring boxes do not overlap
    const w = Math.min(HIT, dayW);
    const focusIdx = this._focusIdx ?? days.length - 1;
    return html`<div class="hits" @keydown=${this._onKey}>
      ${days.map((d, i) => {
        const text = this._dayText(d, fmtDay);
        return html`<rs-tooltip
          class="hit"
          style="left:${x(d.date) - w / 2}px;top:${TOP}px"
          .text=${text}
          @tooltip-toggle=${(e: CustomEvent<{ open: boolean }>) => {
            if (e.detail.open) this._activeIdx = i;
            else if (this._activeIdx === i) this._activeIdx = null;
          }}
        >
          <button
            type="button"
            style="width:${w}px;height:${bottom - TOP}px"
            aria-label=${text}
            tabindex=${i === focusIdx ? "0" : "-1"}
            @focus=${() => (this._focusIdx = i)}
          ></button>
        </rs-tooltip>`;
      })}
    </div>`;
  }

  private _onKey(e: KeyboardEvent) {
    const keys = ["ArrowLeft", "ArrowRight", "Home", "End"];
    if (!keys.includes(e.key)) return;
    const buttons = [...this.renderRoot.querySelectorAll<HTMLButtonElement>(".hits button")];
    const idx = buttons.indexOf(e.composedPath()[0] as HTMLButtonElement);
    if (idx < 0) return;
    e.preventDefault();
    const rtl = getComputedStyle(this).direction === "rtl";
    let next = idx;
    if (e.key === "Home") next = 0;
    else if (e.key === "End") next = buttons.length - 1;
    else next = idx + ((e.key === "ArrowRight") !== rtl ? 1 : -1);
    next = Math.max(0, Math.min(next, buttons.length - 1));
    buttons[next].focus();
  }

  private _svg(days: ModelDay[], fmtDay: Intl.DateTimeFormat) {
    const width = this._width;
    const { right, bottom, dayW, x, y, top } = this._geometry(days);
    const barW = Math.min(Math.max(dayW * 0.6, 3), BAR_MAX_W);
    const ticks = days.length === 1 ? [days[0]] : this._tickDays(days);
    const decimals = top < 1 ? 2 : 1;
    return svg`<svg width=${width} height=${HEIGHT} viewBox="0 0 ${width} ${HEIGHT}" aria-hidden="true">
      ${days
        .filter((d) => d.mpc_active)
        .map(
          (d) =>
            svg`<rect class="mpc" x=${x(d.date) - dayW / 2} y=${TOP} width=${dayW} height=${bottom - TOP} />`,
        )}
      ${[0, 0.5, 1].map(
        (t) => svg`<line class="grid" x1=${LEFT} x2=${right} y1=${y(t * top)} y2=${y(t * top)} />
          <text class="axis" x=${LEFT - 6} y=${y(t * top) + 4} text-anchor="end">${formatNumber(t * top, this.hass, 0, decimals)} ${tempUnit(this.hass)}</text>`,
      )}
      ${days.map((d, i) => {
        if (d.error == null) {
          return svg`<line class="gap" x1=${x(d.date) - barW / 2} x2=${x(d.date) + barW / 2} y1=${bottom - 1} y2=${bottom - 1} />`;
        }
        const yTop = y(toDisplayDelta(d.error, this.hass));
        const h = Math.max(bottom - yTop, 1.5);
        return svg`<rect class="bar ${i === this._activeIdx ? "active" : ""}" x=${x(d.date) - barW / 2} y=${bottom - h} width=${barW} height=${h} rx="2" />`;
      })}
      ${ticks.map((d, i) => {
        const anchor =
          ticks.length === 1
            ? "middle"
            : i === 0
              ? "start"
              : i === ticks.length - 1
                ? "end"
                : "middle";
        const tx =
          ticks.length === 1
            ? x(d.date)
            : i === 0
              ? LEFT
              : i === ticks.length - 1
                ? right
                : x(d.date);
        return svg`<text class="axis" x=${tx} y=${HEIGHT - 4} text-anchor=${anchor}>${fmtDay.format(dayMs(d.date))}</text>`;
      })}
    </svg>`;
  }

  /** First and last day, plus one in the middle when the plot is wide enough for three. */
  private _tickDays(days: ModelDay[]): ModelDay[] {
    const ends = [days[0], days[days.length - 1]];
    if (days.length < 3 || this._width < 320) return ends;
    return [days[0], days[Math.floor((days.length - 1) / 2)], days[days.length - 1]];
  }

  static styles = [
    tokens,
    css`
      :host {
        display: block;
        min-width: 0;
      }

      .heading {
        display: flex;
        align-items: center;
        gap: 2px;
        margin-bottom: var(--rs-space-1);
        font-size: var(--rs-font-md);
        color: var(--secondary-text-color);
      }

      .plot {
        position: relative;
        height: ${HEIGHT}px;
      }

      rs-tooltip.hit {
        position: absolute;
      }

      .hit button {
        padding: 0;
        border: none;
        border-radius: var(--rs-radius-sm);
        background: none;
        cursor: pointer;
      }

      .hit button:focus-visible {
        outline: 2px solid var(--primary-color);
        outline-offset: -2px;
      }

      svg {
        display: block;
        overflow: visible;
      }

      .grid {
        stroke: var(--rs-border);
      }

      .axis {
        font-size: var(--rs-font-xs);
        fill: var(--secondary-text-color);
        font-variant-numeric: tabular-nums;
      }

      .mpc {
        fill: var(--rs-ok);
        opacity: 0.12;
      }

      .bar {
        fill: var(--primary-color);
        opacity: 0.75;
      }

      .bar.active {
        opacity: 1;
      }

      .gap {
        stroke: var(--secondary-text-color);
        stroke-width: 2;
        opacity: 0.35;
      }

      .legend {
        display: flex;
        flex-wrap: wrap;
        gap: 4px 14px;
        padding-top: 6px;
        font-size: var(--rs-font-sm);
        color: var(--secondary-text-color);
      }

      .legend span {
        display: inline-flex;
        align-items: center;
        gap: 6px;
      }

      .key {
        width: 10px;
        height: 10px;
        border-radius: 3px;
      }

      .key.bar {
        background: var(--primary-color);
        opacity: 0.75;
      }

      .key.mpc {
        background: var(--rs-ok);
        opacity: 0.35;
      }

      .note {
        margin: var(--rs-space-2) 0 0;
        font-size: var(--rs-font-sm);
        line-height: 1.5;
        color: var(--secondary-text-color);
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-forecast-error-chart": RsForecastErrorChart;
  }
}
