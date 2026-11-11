/**
 * rs-analytics-rhythm – Days by hours around the selected range: when the room runs, when it
 * misses its target. The range is marked, and a day label selects that day for the whole page.
 */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { AnalyticsRhythm, HomeAssistant, RhythmDay } from "../../types";
import { localize } from "../../utils/localize";
import { formatTempLocale, tempUnit } from "../../utils/temperature";
import { formatHours, formatPercent } from "../../utils/format";
import { tokens, srOnly } from "../../styles/tokens";
import { floatingStyles } from "../../styles/floating-styles";
import "../shared/rs-list-card";
import "../shared/rs-segmented";

type RhythmView = "activity" | "comfort";

const HOURS = Array.from({ length: 24 }, (_, h) => h);
const AXIS_HOURS = [0, 6, 12, 18];
const POPUP_WIDTH = 190;
// Sticky toolbars plus the popup itself; closer to the top it opens below the cell
const POPUP_MIN_TOP = 300;

const isoDate = (ms: number) => {
  const d = new Date(ms);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};

const shade = (variable: string, share: number) =>
  `color-mix(in srgb, var(${variable}) ${Math.round(30 + 70 * Math.sqrt(share))}%, var(--rs-idle))`;

@customElement("rs-analytics-rhythm")
export class RsAnalyticsRhythm extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public rhythm: AnalyticsRhythm | null = null;
  @property({ type: Number }) public rangeStart = 0;
  @property({ type: Number }) public rangeEnd = 0;
  @property({ type: String }) public language = "en";

  @state() private _view: RhythmView = "activity";
  // Touch keeps the popup open and offers the day in it; a mouse picks the day by clicking
  @state() private _tapped = false;
  private _popupPressed = false;
  @state() private _selected: {
    row: number;
    hour: number;
    x: number;
    y: number;
    below: boolean;
  } | null = null;

  private _closeOnOutside = (e: Event) => {
    if (e.composedPath().includes(this)) return;
    this._popupPressed = false;
    this._selected = null;
  };

  connectedCallback() {
    super.connectedCallback();
    document.addEventListener("pointerdown", this._closeOnOutside);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    document.removeEventListener("pointerdown", this._closeOnOutside);
  }

  render() {
    const days = this.rhythm?.days;
    if (!days?.length) return nothing;
    const l = this.language;
    const hasComfort = days.some((d) => d.within != null);
    const view = hasComfort ? this._view : "activity";
    return html`
      <rs-list-card unclipped .heading=${localize("analytics.rhythm", l)}>
        <div class="bar">
          <span class="period"
            >${this._formatDay(days[days.length - 1].date, { day: "numeric", month: "short" })} –
            ${this._formatDay(days[0].date, { day: "numeric", month: "short" })}</span
          >
          ${
            hasComfort
              ? html`<rs-segmented
                  size="sm"
                  wrap
                  .label=${localize("analytics.rhythm_view", l)}
                  .options=${[
                    { value: "activity", label: localize("analytics.rhythm_activity", l) },
                    { value: "comfort", label: localize("analytics.rhythm_comfort", l) },
                  ]}
                  .value=${view}
                  @value-changed=${this._onView}
                ></rs-segmented>`
              : nothing
          }
        </div>
        <div class="grid-wrap">
          <div
            class="grid"
            role="group"
            tabindex="0"
            aria-label=${localize("analytics.rhythm", l)}
            @pointermove=${this._onPointer}
            @pointerdown=${this._onPointer}
            @pointerleave=${this._onPointerLeave}
            @keydown=${(e: KeyboardEvent) => this._onKey(e, days.length)}
            @blur=${() => {
              // Tapping the popup's button blurs the grid first; the popup must outlive that
              if (!this._popupPressed) this._selected = null;
            }}
          >
            <span></span>
            ${AXIS_HOURS.map(
              (h) =>
                html`<span class="hour-label" style="grid-column: ${h + 2} / span 6"
                  >${this._formatHour(h)}</span
                >`,
            )}
            <span></span>
            ${days.map((day, row) => this._renderRow(day, row, view))}
          </div>
          ${this._selected ? this._renderPopup(days) : nothing}
        </div>
        <div class="foot">
          ${this._renderLegend(view)}
          <div>${localize("analytics.rhythm_hint", l)}</div>
          <div class="sr-only" aria-live="polite">${this._selected ? this._when(days) : ""}</div>
        </div>
      </rs-list-card>
    `;
  }

  private _renderRow(day: RhythmDay, row: number, view: RhythmView) {
    const inRange = day.date >= isoDate(this.rangeStart) && day.date <= isoDate(this.rangeEnd);
    return html`
      <button
        class="day-label ${inRange ? "in-range" : ""}"
        aria-pressed=${inRange ? "true" : "false"}
        @click=${() => this._selectDay(day.date)}
      >
        ${this._formatDay(day.date, { weekday: "short", day: "numeric" })}
      </button>
      ${HOURS.map((hour) => {
        const selected = this._selected?.row === row && this._selected.hour === hour;
        const background =
          view === "activity" ? this._activityColor(day, hour) : this._comfortColor(day, hour);
        const window = view === "activity" && (day.window[hour] ?? 0) > 0;
        return html`<span
          @click=${(e: PointerEvent) => this._onCellClick(e, day.date)}
          class="cell ${selected ? "selected" : ""} ${window ? "window" : ""}"
          data-row=${row}
          data-hour=${hour}
          style=${background ? `background: ${background}` : ""}
        ></span>`;
      })}
      <span class="day-total">${this._rowTotal(day, view)}</span>
    `;
  }

  private _activityColor(day: RhythmDay, hour: number): string | null {
    const heat = day.heat[hour];
    const cool = day.cool[hour];
    if (heat == null || cool == null) return null;
    if (heat === 0 && cool === 0) return "var(--rs-idle)";
    return heat >= cool ? shade("--rs-warm", heat) : shade("--rs-cold", cool);
  }

  private _comfortColor(day: RhythmDay, hour: number): string | null {
    const below = day.below[hour];
    const above = day.above[hour];
    if (below == null || above == null) return null;
    if (below === 0 && above === 0) return "var(--rs-on-target)";
    return below >= above ? shade("--rs-cold", below) : shade("--rs-warm", above);
  }

  private _rowTotal(day: RhythmDay, view: RhythmView): string {
    if (view === "activity") {
      const sum = (values: Array<number | null>) =>
        values.reduce<number>((a, v) => a + (v ?? 0), 0);
      const hours = sum(day.heat) + sum(day.cool);
      return hours > 0 ? formatHours(hours, this.language) : "";
    }
    if (day.within == null) return "";
    // Floor: 99.6 % on target must not read as 100 %
    return formatPercent(Math.floor(day.within * 100), this.hass);
  }

  private _renderLegend(view: RhythmView) {
    const l = this.language;
    if (view === "activity") {
      return html`<div class="legend">
        <span><i class="key warm"></i>${localize("analytics.heating_period", l)}</span>
        <span><i class="key cold"></i>${localize("analytics.cooling_period", l)}</span>
        <span><i class="key window-key"></i>${localize("analytics.window_open_period", l)}</span>
      </div>`;
    }
    return html`<div class="legend">
      <span><i class="key cold"></i>${localize("analytics.comfort_below", l)}</span>
      <span><i class="key ok"></i>${localize("analytics.comfort_on_target", l)}</span>
      <span><i class="key warm"></i>${localize("analytics.comfort_above", l)}</span>
    </div>`;
  }

  private _when(days: RhythmDay[]): string {
    const { row, hour } = this._selected!;
    const day = days[row];
    if (!day) return "";
    const date = this._formatDay(day.date, { weekday: "short", day: "numeric", month: "short" });
    return `${date} · ${this._formatHour(hour)}–${this._formatHour((hour + 1) % 24)}`;
  }

  private _renderPopup(days: RhythmDay[]) {
    const l = this.language;
    const { row, hour, x, y, below } = this._selected!;
    const day = days[row];
    if (!day) return nothing;
    const unit = tempUnit(this.hass);
    const percent = (v: number) => formatPercent(v * 100, this.hass);
    const temp = (v: number) => `${formatTempLocale(v, this.hass)}\u00A0${unit}`;
    const lines: Array<[string, string]> = [];
    const add = (label: string, value: number | null, format: (v: number) => string) => {
      if (value != null) lines.push([label, format(value)]);
    };
    const share = (label: string, value: number | null) => add(label, value || null, percent);
    add(localize("analytics.temperature", l), day.temp[hour], temp);
    share(localize("analytics.comfort_below", l), day.below[hour]);
    share(localize("analytics.comfort_above", l), day.above[hour]);
    share(localize("analytics.heating_period", l), day.heat[hour]);
    share(localize("analytics.cooling_period", l), day.cool[hour]);
    share(localize("analytics.window_open_period", l), day.window[hour]);
    add(localize("analytics.humidity", l), day.humidity[hour], (v) => formatPercent(v, this.hass));
    add(localize("analytics.outdoor", l), day.outdoor[hour], temp);
    return html`
      <div
        class="popup floating-surface ${below ? "below" : ""} ${this._tapped ? "tapped" : ""}"
        role=${this._tapped ? "group" : "tooltip"}
        @pointerdown=${() => {
          this._popupPressed = true;
        }}
        style="left: ${x}px; top: ${y}px; width: ${POPUP_WIDTH}px"
      >
        <div class="popup-title">${this._when(days)}</div>
        ${
          lines.length > 0
            ? lines.map(
                ([label, value]) => html`
                  <div class="popup-line"><span>${label}</span><span>${value}</span></div>
                `,
              )
            : html`<div class="popup-line">${localize("analytics.no_data", l)}</div>`
        }
        ${
          this._tapped
            ? html`<button class="popup-action" @click=${() => this._selectDay(day.date)}>
                ${localize("analytics.rhythm_show_day", l)}
              </button>`
            : nothing
        }
      </div>
    `;
  }

  private _selectDay(date: string) {
    this._popupPressed = false;
    this._selected = null;
    this.dispatchEvent(new CustomEvent("day-selected", { detail: date }));
  }

  // A mouse sees the hour on hover, so its click picks the day; a tap opens the hour instead
  private _onCellClick(e: PointerEvent, date: string) {
    if (e.pointerType === "mouse") this._selectDay(date);
  }

  private _formatDay(date: string, options: Intl.DateTimeFormatOptions): string {
    return new Intl.DateTimeFormat(this.language, options).format(new Date(`${date}T12:00:00`));
  }

  private _formatHour(hour: number): string {
    return new Intl.DateTimeFormat(this.language, { hour: "numeric" }).format(
      new Date(2026, 0, 1, hour),
    );
  }

  private _onView(e: CustomEvent<{ value: string }>) {
    e.stopPropagation();
    this._view = e.detail.value as RhythmView;
  }

  private _onPointer(e: PointerEvent) {
    if (e.type === "pointerdown") {
      this._tapped = e.pointerType !== "mouse";
      this._popupPressed = false;
    }
    const cell = (e.target as HTMLElement).closest<HTMLElement>("[data-row]");
    if (!cell) return;
    const row = Number(cell.dataset.row);
    const hour = Number(cell.dataset.hour);
    if (this._selected?.row !== row || this._selected.hour !== hour) this._select(row, hour);
  }

  private _select(row: number, hour: number) {
    const cell = this.renderRoot.querySelector(`[data-row="${row}"][data-hour="${hour}"]`);
    const wrap = this.renderRoot.querySelector(".grid-wrap");
    if (!cell || !wrap) return;
    const cellBox = cell.getBoundingClientRect();
    const wrapBox = wrap.getBoundingClientRect();
    const margin = POPUP_WIDTH / 2 + 4;
    this._selected = {
      row,
      hour,
      x: Math.min(
        Math.max(cellBox.left + cellBox.width / 2 - wrapBox.left, margin),
        wrapBox.width - margin,
      ),
      y: (cellBox.top < POPUP_MIN_TOP ? cellBox.bottom : cellBox.top) - wrapBox.top,
      below: cellBox.top < POPUP_MIN_TOP,
    };
  }

  private _onPointerLeave(e: PointerEvent) {
    if (e.pointerType === "mouse") this._selected = null;
  }

  private _onKey(e: KeyboardEvent, rows: number) {
    const moves: Record<string, [number, number]> = {
      ArrowUp: [-1, 0],
      ArrowDown: [1, 0],
      ArrowLeft: [0, -1],
      ArrowRight: [0, 1],
    };
    if (e.key === "Escape") this._selected = null;
    if (e.key === "Enter" && this._selected) {
      const day = this.rhythm?.days[this._selected.row];
      if (day) this._selectDay(day.date);
      return;
    }
    const move = moves[e.key];
    if (!move) return;
    e.preventDefault();
    const { row, hour } = this._selected ?? { row: 0, hour: 0 };
    this._select(
      Math.min(Math.max(row + move[0], 0), rows - 1),
      Math.min(Math.max(hour + move[1], 0), 23),
    );
  }

  static styles = [
    tokens,
    srOnly,
    floatingStyles,
    css`
      :host {
        display: block;
        margin-bottom: var(--rs-space-4);
        --rs-cold: var(--rs-cool);
        --rs-warm: var(--rs-heat);
        --rs-idle: color-mix(in srgb, var(--primary-text-color) 7%, var(--card-background-color));
        --rs-on-target: color-mix(in srgb, var(--rs-ok) 35%, var(--rs-idle));
      }

      .bar {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        justify-content: space-between;
        gap: var(--rs-space-2);
        padding: 0 var(--rs-space-4);
      }

      .period {
        font-size: 13px;
        color: var(--secondary-text-color);
      }

      rs-segmented {
        flex: none;
      }

      .grid-wrap {
        position: relative;
        padding-top: var(--rs-space-2);
      }

      .grid {
        display: grid;
        grid-template-columns: max-content repeat(24, minmax(0, 1fr)) 40px;
        gap: 2px;
        align-items: center;
        padding: 0 16px;
        font-size: 11px;
        color: var(--secondary-text-color);
        font-variant-numeric: tabular-nums;
        touch-action: pan-y;
        outline: none;
      }

      .grid:focus-visible {
        outline: 2px solid var(--primary-color);
        outline-offset: 2px;
        border-radius: 4px;
      }

      .hour-label {
        white-space: nowrap;
      }

      .day-label {
        height: 100%;
        padding: 0 6px;
        border: none;
        border-radius: 4px;
        background: transparent;
        color: inherit;
        font: inherit;
        text-align: left;
        white-space: nowrap;
        cursor: pointer;
        touch-action: manipulation;
      }

      .day-label:hover {
        color: var(--primary-color);
      }

      .day-label:focus-visible {
        outline: 2px solid var(--primary-color);
      }

      .day-label.in-range {
        color: var(--primary-color);
        font-weight: 500;
        background: color-mix(in srgb, var(--primary-color) 14%, transparent);
        box-shadow: inset 2px 0 var(--primary-color);
      }

      .day-total {
        text-align: right;
        white-space: nowrap;
      }

      .cell {
        position: relative;
        height: 18px;
        border-radius: 3px;
        cursor: pointer;
      }

      .cell.selected {
        box-shadow: 0 0 0 1.5px var(--primary-text-color);
      }

      .cell.window::after {
        content: "";
        position: absolute;
        left: 50%;
        top: 50%;
        width: 4px;
        height: 4px;
        margin: -2px 0 0 -2px;
        border-radius: 50%;
        background: var(--primary-text-color);
      }

      .foot {
        display: flex;
        flex-direction: column;
        gap: 4px;
        padding: 10px 16px 14px;
        font-size: 12px;
        color: var(--secondary-text-color);
      }

      .legend {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 4px 14px;
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

      .key.warm {
        background: var(--rs-warm);
      }

      .key.cold {
        background: var(--rs-cold);
      }

      .key.window-key {
        width: 4px;
        height: 4px;
        margin: 0 3px;
        border-radius: 50%;
        background: var(--primary-text-color);
      }

      .key.ok {
        background: var(--rs-on-target);
      }

      .popup {
        position: absolute;
        z-index: 5;
        padding: 8px 12px;
        font-size: 12px;
        line-height: 1.5;
        font-variant-numeric: tabular-nums;
        transform: translate(-50%, calc(-100% - 6px));
        pointer-events: none;
      }

      .popup.below {
        transform: translate(-50%, 6px);
      }

      .popup.tapped {
        pointer-events: auto;
      }

      .popup-action {
        width: 100%;
        min-height: 44px;
        margin-top: 6px;
        border: none;
        border-radius: 6px;
        background: color-mix(in srgb, var(--primary-color) 14%, transparent);
        color: var(--primary-color);
        font: inherit;
        font-weight: 500;
        cursor: pointer;
        touch-action: manipulation;
      }

      .popup-action:focus-visible {
        outline: 2px solid var(--primary-color);
      }

      .popup-title {
        margin-bottom: 2px;
        font-weight: 500;
      }

      .popup-line {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        color: var(--secondary-text-color);
      }

      .popup-line span:last-child {
        color: var(--primary-text-color);
        white-space: nowrap;
      }

      @media (max-width: 600px) {
        .grid {
          grid-template-columns: max-content repeat(24, minmax(0, 1fr)) 34px;
          gap: 1px;
        }
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-analytics-rhythm": RsAnalyticsRhythm;
  }
}
