/**
 * rs-confidence-chart – The model's confidence per day (backend `confidence_history`), the
 * days MPC controlled shaded, the data points as bars. Plain SVG drawn at the measured width.
 * Each day is a button over its point with the shared tooltip; one tab stop, arrow keys move.
 */
import { LitElement, html, css, nothing, svg } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";
import { formatPercent } from "../../utils/format";
import { tokens } from "../../styles/tokens";
import "../shared/rs-tooltip";

export type ConfidenceDay = [string, number, number, boolean];

const HEIGHT = 160;
const LEFT = 40;
const RIGHT = 8;
const TOP = 10;
const BOTTOM = 22;
const BAR_MAX = 26;
const DAY_MS = 86_400_000;
const HIT = 28;

// Local noon: a bare date would be parsed as UTC midnight and land on the day before
const dayMs = (date: string) => new Date(`${date}T12:00:00`).getTime();

@customElement("rs-confidence-chart")
export class RsConfidenceChart extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public history: ConfidenceDay[] = [];
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

  render() {
    const l = this.language;
    const days = this.history;
    const fmtDay = new Intl.DateTimeFormat(l, { day: "numeric", month: "short" });
    if (days.length === 0) {
      return html`<p class="note">${localize("analytics.confidence_history_empty", l)}</p>`;
    }
    const first = days[0];
    const last = days[days.length - 1];
    const label = localize("analytics.confidence_history_label", l, {
      from: fmtDay.format(dayMs(first[0])),
      to: fmtDay.format(dayMs(last[0])),
      start: formatPercent(first[1] * 100, this.hass),
      end: formatPercent(last[1] * 100, this.hass),
    });
    const hasMpc = days.some((d) => d[3]);
    return html`
      <div class="plot" role="group" aria-label=${label}>
        ${this._width > 0 ? this._svg(days, fmtDay) : nothing}
        ${this._width > 0 ? this._hits(days, fmtDay) : nothing}
      </div>
      <div class="legend">
        <span><i class="key line"></i>${localize("analytics.confidence", l)}</span>
        <span><i class="key bars"></i>${localize("analytics.data_points", l)}</span>
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
              ${localize("analytics.confidence_history_start", l, {
                date: fmtDay.format(dayMs(first[0])),
              })}
            </p>`
          : nothing
      }
    `;
  }

  private _geometry(days: ConfidenceDay[]) {
    const right = this._width - RIGHT;
    const bottom = HEIGHT - BOTTOM;
    const start = dayMs(days[0][0]);
    const span = Math.max(Math.round((dayMs(days[days.length - 1][0]) - start) / DAY_MS), 1);
    // One day's width; a single day sits in the middle of the plot
    const dayW = (right - LEFT) / (days.length === 1 ? 1 : span + 1);
    const x = (date: string) =>
      days.length === 1
        ? (LEFT + right) / 2
        : LEFT +
          dayW / 2 +
          (Math.round((dayMs(date) - start) / DAY_MS) / span) * (right - LEFT - dayW);
    const y = (confidence: number) => bottom - confidence * (bottom - TOP);
    return { right, bottom, dayW, x, y };
  }

  private _dayText(d: ConfidenceDay, fmtDay: Intl.DateTimeFormat): string {
    return `${fmtDay.format(dayMs(d[0]))}: ${formatPercent(d[1] * 100, this.hass)}`;
  }

  private _hits(days: ConfidenceDay[], fmtDay: Intl.DateTimeFormat) {
    const { dayW, x, y } = this._geometry(days);
    // Never wider than a day, so neighbouring boxes do not overlap
    const w = Math.min(HIT, dayW);
    const focusIdx = this._focusIdx ?? days.length - 1;
    return html`<div class="hits" @keydown=${this._onKey}>
      ${days.map((d, i) => {
        const text = this._dayText(d, fmtDay);
        return html`<rs-tooltip
          class="hit"
          style="left:${x(d[0]) - w / 2}px;top:${y(d[1]) - HIT / 2}px"
          .text=${text}
          @tooltip-toggle=${(e: CustomEvent<{ open: boolean }>) => {
            if (e.detail.open) this._activeIdx = i;
            else if (this._activeIdx === i) this._activeIdx = null;
          }}
        >
          <button
            type="button"
            style="width:${w}px"
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

  private _svg(days: ConfidenceDay[], fmtDay: Intl.DateTimeFormat) {
    const width = this._width;
    const { right, bottom, dayW, x, y } = this._geometry(days);
    const maxN = Math.max(...days.map((d) => d[2]), 1);
    const line = days.map((d, i) => `${i ? "L" : "M"}${x(d[0])},${y(d[1])}`).join("");
    const area = `${line}L${x(days[days.length - 1][0])},${bottom}L${x(days[0][0])},${bottom}Z`;
    const ticks = days.length === 1 ? [days[0]] : this._tickDays(days);
    return svg`<svg width=${width} height=${HEIGHT} viewBox="0 0 ${width} ${HEIGHT}" aria-hidden="true">
      <defs>
        <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="var(--primary-color)" stop-opacity="0.28" />
          <stop offset="1" stop-color="var(--primary-color)" stop-opacity="0" />
        </linearGradient>
      </defs>
      ${days
        .filter((d) => d[3])
        .map(
          (d) =>
            svg`<rect class="mpc" x=${x(d[0]) - dayW / 2} y=${TOP} width=${dayW} height=${bottom - TOP} />`,
        )}
      ${[0, 0.5, 1].map(
        (t) => svg`<line class="grid" x1=${LEFT} x2=${right} y1=${y(t)} y2=${y(t)} />
          <text class="axis" x=${LEFT - 6} y=${y(t) + 4} text-anchor="end">${formatPercent(t * 100, this.hass)}</text>`,
      )}
      ${days.map((d) => {
        const h = (d[2] / maxN) * BAR_MAX;
        const w = Math.min(Math.max(dayW * 0.4, 2), 8);
        return svg`<rect class="bar" x=${x(d[0]) - w / 2} y=${bottom - h} width=${w} height=${h} rx="1" />`;
      })}
      ${days.length > 1 ? svg`<path class="area" d=${area} /><path class="line" d=${line} />` : nothing}
      ${days.map(
        (d, i) =>
          svg`<circle class="dot" cx=${x(d[0])} cy=${y(d[1])} r=${i === days.length - 1 || i === this._activeIdx ? 4.5 : days.length <= 14 ? 2.5 : 0} />`,
      )}
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
          ticks.length === 1 ? x(d[0]) : i === 0 ? LEFT : i === ticks.length - 1 ? right : x(d[0]);
        return svg`<text class="axis" x=${tx} y=${HEIGHT - 4} text-anchor=${anchor}>${fmtDay.format(dayMs(d[0]))}</text>`;
      })}
    </svg>`;
  }

  /** First and last day, plus one in the middle when the plot is wide enough for three. */
  private _tickDays(days: ConfidenceDay[]): ConfidenceDay[] {
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

      .plot {
        position: relative;
        height: ${HEIGHT}px;
      }

      rs-tooltip.hit {
        position: absolute;
      }

      .hit button {
        height: ${HIT}px;
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
        fill: var(--secondary-text-color);
        opacity: 0.25;
      }

      .area {
        fill: url(#fill);
      }

      .line {
        fill: none;
        stroke: var(--primary-color);
        stroke-width: 2.2;
        stroke-linejoin: round;
      }

      .dot {
        fill: var(--primary-color);
        stroke: var(--rs-surface);
        stroke-width: 2;
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

      .key.line {
        height: 3px;
        border-radius: 2px;
        background: var(--primary-color);
      }

      .key.bars {
        background: color-mix(in srgb, var(--secondary-text-color) 35%, transparent);
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
    "rs-confidence-chart": RsConfidenceChart;
  }
}
