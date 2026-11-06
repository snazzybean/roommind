/**
 * rs-analytics-rhythm – Days by hours: when the room runs, and when it misses its target.
 */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { AnalyticsRhythm, HomeAssistant, RhythmDay } from "../../types";
import { localize } from "../../utils/localize";
import { tempUnit, toDisplayDelta } from "../../utils/temperature";
import "../shared/rs-chip-group";

type RhythmView = "activity" | "comfort";

const HOURS = Array.from({ length: 24 }, (_, h) => h);
const AXIS_HOURS = [0, 6, 12, 18];
// Darkest colour at this distance from the target; a cell inside the dead zone reads as on target
const DEVIATION_FULL_K = 2;
const DEVIATION_DEAD_ZONE_K = 0.25;

const shade = (variable: string, share: number) =>
  `color-mix(in srgb, var(${variable}) ${Math.round(30 + 70 * Math.sqrt(share))}%, var(--rs-idle))`;

@customElement("rs-analytics-rhythm")
export class RsAnalyticsRhythm extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public rhythm: AnalyticsRhythm | null = null;
  @property({ type: String }) public language = "en";

  @state() private _view: RhythmView = "activity";
  @state() private _selected: { row: number; hour: number } | null = null;

  render() {
    const days = this.rhythm?.days;
    if (!days?.length) return nothing;
    const l = this.language;
    const hasComfort = days.some((d) => d.deviation.some((v) => v != null));
    const view = hasComfort ? this._view : "activity";
    return html`
      <ha-card>
        <div class="header">
          <div>
            <div class="title">${localize("analytics.rhythm", l)}</div>
            <div class="subtitle">
              ${localize("analytics.rhythm_days", l, { count: days.length })}
            </div>
          </div>
          ${
            hasComfort
              ? html`<rs-chip-group
                  .chips=${[
                    {
                      id: "activity",
                      label: localize("analytics.rhythm_activity", l),
                      active: view === "activity",
                    },
                    {
                      id: "comfort",
                      label: localize("analytics.rhythm_comfort", l),
                      active: view === "comfort",
                    },
                  ]}
                  @chip-clicked=${this._onChip}
                ></rs-chip-group>`
              : nothing
          }
        </div>
        <div
          class="grid"
          role="group"
          tabindex="0"
          aria-label=${localize("analytics.rhythm", l)}
          aria-describedby="readout"
          @pointermove=${this._onPointer}
          @pointerdown=${this._onPointer}
          @pointerleave=${this._onPointerLeave}
          @keydown=${(e: KeyboardEvent) => this._onKey(e, days.length)}
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
        <div class="foot">
          ${this._renderLegend(view)}
          <div class="readout" id="readout" aria-live="polite">
            ${this._selected ? this._readout(days, view) : localize("analytics.rhythm_hint", l)}
          </div>
        </div>
      </ha-card>
    `;
  }

  private _renderRow(day: RhythmDay, row: number, view: RhythmView) {
    return html`
      <span class="day-label"
        >${this._formatDay(day.date, { weekday: "short", day: "numeric" })}</span
      >
      ${HOURS.map((hour) => {
        const selected = this._selected?.row === row && this._selected.hour === hour;
        const background =
          view === "activity" ? this._activityColor(day, hour) : this._comfortColor(day, hour);
        const window = view === "activity" && (day.window[hour] ?? 0) > 0;
        return html`<span
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
    const value = day.deviation[hour];
    if (value == null) return null;
    if (Math.abs(value) < DEVIATION_DEAD_ZONE_K) return "var(--rs-idle)";
    return shade(
      value < 0 ? "--rs-cold" : "--rs-warm",
      Math.min(Math.abs(value) / DEVIATION_FULL_K, 1),
    );
  }

  private _rowTotal(day: RhythmDay, view: RhythmView): string {
    const l = this.language;
    const number = (v: number) => new Intl.NumberFormat(l, { maximumFractionDigits: 1 }).format(v);
    if (view === "activity") {
      const sum = (values: Array<number | null>) =>
        values.reduce<number>((a, v) => a + (v ?? 0), 0);
      const hours = sum(day.heat) + sum(day.cool);
      return hours > 0 ? `${number(hours)} h` : "";
    }
    const known = day.deviation.filter((v): v is number => v != null);
    if (known.length === 0) return "";
    const mean = known.reduce((a, v) => a + Math.abs(v), 0) / known.length;
    return mean >= 0.05 ? `±${number(toDisplayDelta(mean, this.hass))}` : "";
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
      <span>${localize("analytics.comfort_below", l)}</span>
      <i class="scale"></i>
      <span>${localize("analytics.comfort_above", l)}</span>
    </div>`;
  }

  private _readout(days: RhythmDay[], view: RhythmView): string {
    const l = this.language;
    const { row, hour } = this._selected!;
    const day = days[row];
    if (!day) return "";
    const when = `${this._formatDay(day.date, { weekday: "short", day: "numeric", month: "short" })}, ${this._formatHour(hour)}–${this._formatHour((hour + 1) % 24)}`;
    const percent = (v: number) =>
      new Intl.NumberFormat(l, { style: "percent", maximumFractionDigits: 0 }).format(v);
    const parts = [when];
    if (day.heat[hour] == null) {
      parts.push(localize("analytics.no_data", l));
    } else if (view === "activity") {
      if (day.heat[hour]! > 0) {
        parts.push(`${localize("analytics.heating_period", l)} ${percent(day.heat[hour]!)}`);
      }
      if (day.cool[hour]! > 0) {
        parts.push(`${localize("analytics.cooling_period", l)} ${percent(day.cool[hour]!)}`);
      }
      if (day.window[hour]! > 0) {
        parts.push(`${localize("analytics.window_open_period", l)} ${percent(day.window[hour]!)}`);
      }
      if (parts.length === 1) parts.push(localize("analytics.rhythm_idle", l));
    } else {
      const value = day.deviation[hour];
      if (value == null) {
        parts.push(localize("analytics.no_data", l));
      } else {
        const delta = new Intl.NumberFormat(l, {
          signDisplay: "exceptZero",
          maximumFractionDigits: 1,
        }).format(toDisplayDelta(value, this.hass));
        parts.push(`${delta} ${tempUnit(this.hass)}`);
      }
    }
    return parts.join(" · ");
  }

  private _formatDay(date: string, options: Intl.DateTimeFormatOptions): string {
    return new Intl.DateTimeFormat(this.language, options).format(new Date(`${date}T12:00:00`));
  }

  private _formatHour(hour: number): string {
    return new Intl.DateTimeFormat(this.language, { hour: "numeric" }).format(
      new Date(2026, 0, 1, hour),
    );
  }

  private _onChip(e: CustomEvent<string>) {
    this._view = e.detail as RhythmView;
  }

  private _onPointer(e: PointerEvent) {
    const cell = (e.target as HTMLElement).closest<HTMLElement>("[data-row]");
    if (!cell) return;
    const row = Number(cell.dataset.row);
    const hour = Number(cell.dataset.hour);
    if (this._selected?.row !== row || this._selected.hour !== hour) {
      this._selected = { row, hour };
    }
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
    const move = moves[e.key];
    if (!move) return;
    e.preventDefault();
    const { row, hour } = this._selected ?? { row: 0, hour: 0 };
    this._selected = {
      row: Math.min(Math.max(row + move[0], 0), rows - 1),
      hour: Math.min(Math.max(hour + move[1], 0), 23),
    };
  }

  static styles = css`
    :host {
      display: block;
      --rs-cold: var(--state-climate-cool-color, #2b9af9);
      --rs-warm: var(--state-climate-heat-color, #ff8100);
      --rs-idle: color-mix(in srgb, var(--primary-text-color) 7%, var(--card-background-color));
    }

    ha-card {
      margin-bottom: 16px;
    }

    .header {
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding: 16px 16px 8px;
    }

    .title {
      font-size: 16px;
      font-weight: 500;
    }

    .subtitle {
      font-size: 12px;
      color: var(--secondary-text-color);
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
      padding-right: 6px;
      white-space: nowrap;
    }

    .day-total {
      text-align: right;
      white-space: nowrap;
    }

    .cell {
      position: relative;
      height: 16px;
      border-radius: 3px;
      cursor: crosshair;
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

    .scale {
      width: 96px;
      height: 8px;
      border-radius: 4px;
      background: linear-gradient(90deg, var(--rs-cold), var(--rs-idle), var(--rs-warm));
    }

    .readout {
      min-height: 18px;
      color: var(--primary-text-color);
      font-variant-numeric: tabular-nums;
    }

    @media (max-width: 600px) {
      .cell {
        height: 14px;
      }

      .grid {
        grid-template-columns: max-content repeat(24, minmax(0, 1fr)) 34px;
        gap: 1px;
      }
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-analytics-rhythm": RsAnalyticsRhythm;
  }
}
