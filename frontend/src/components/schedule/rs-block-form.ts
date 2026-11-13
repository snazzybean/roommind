import { LitElement, html, css, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";
import { tokens } from "../../styles/tokens";
import { tempRowStyles } from "../../styles/temp-row-styles";
import { formatNumber } from "../../utils/format";
import {
  MAX_TARGET_TEMP_C,
  MIN_TARGET_TEMP_C,
  tempUnit,
  toDisplay,
  usesFahrenheit,
} from "../../utils/temperature";
import {
  COVER_CLOSED,
  COVER_OPEN,
  DAY_MINUTES,
  SNAP_MINUTES,
  blockPosition,
  blockTemps,
  hm,
  roundToStep,
  usesComfort,
  type ScheduleBlock,
} from "../../utils/schedule-week";
import "../shared/rs-segmented";
import "../shared/rs-stepper";
import "../shared/rs-number-field";

export interface BlockTempChange {
  heat?: number;
  cool?: number;
}

/**
 * Form for one schedule block (desktop popover, phone sheet): from/to, comfort or own
 * temperature, delete. Applies every valid change at once (no save button):
 * `block-times` `{ start, end }`, `block-split` `{ start, endNextDay }` for a range past
 * midnight, `block-temps` `{ temps }` (null = comfort, else only the sides that changed),
 * `block-delete`, `block-done`. A cover schedule's block (`cover`) has a position instead of a
 * temperature: `block-position` `{ position }`.
 * Events bubble but are not composed: the editor listens on the form itself.
 */
@customElement("rs-block-form")
export class RsBlockForm extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public block!: ScheduleBlock;
  /** The other blocks of the day, to name the one a new range would run into. */
  @property({ attribute: false }) public others: ScheduleBlock[] = [];
  /** Which own-temperature keys the rooms using this schedule need. */
  @property({ attribute: false }) public sides = { heat: true, cool: true };
  /** Own temperature preset when switching from comfort (HA unit system). */
  @property({ attribute: false }) public defaults = { heat: 21, cool: 24 };
  /** "Wohnzimmer 21–24 °C, Bad 22 °C" for the comfort hint. */
  @property({ type: String }) public comfortText = "";
  @property({ type: String }) public nextDayName = "";
  /** Changes when another block is opened: the draft starts over. */
  @property({ type: String }) public blockKey = "";
  /** Block of a cover schedule: position instead of temperature. */
  @property({ type: Boolean }) public cover = false;
  /** Every room uses the cover schedule only to allow shading: the position does not count. */
  @property({ type: Boolean }) public gateOnly = false;

  @state() private _start = 0;
  @state() private _end = 60;
  @state() private _own = false;
  @state() private _heat = 21;
  @state() private _cool = 24;
  @state() private _position: number = COVER_CLOSED;

  static styles = [
    tokens,
    tempRowStyles,
    css`
      :host {
        display: block;
      }

      .times {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: var(--rs-space-3);
      }

      label {
        display: flex;
        flex-direction: column;
        gap: var(--rs-space-1);
        font-size: var(--rs-font-sm);
        color: var(--secondary-text-color);
      }

      select {
        height: var(--rs-touch);
        padding: 0 var(--rs-space-2);
        border: 1px solid var(--rs-border);
        border-radius: var(--rs-radius-sm);
        background-color: var(--rs-surface);
        color: var(--primary-text-color);
        font: inherit;
        font-size: 16px;
        font-variant-numeric: tabular-nums;
      }

      /* the open list is drawn by the browser; without its own colours it stays light in dark mode */
      select option {
        background-color: var(--rs-surface);
        color: var(--primary-text-color);
      }

      select:focus-visible {
        outline: 2px solid var(--primary-color);
        outline-offset: 1px;
      }

      select[aria-invalid="true"] {
        border-color: var(--rs-err);
      }

      .error {
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        gap: var(--rs-space-2);
        margin-top: var(--rs-space-2);
        font-size: var(--rs-font-sm);
        line-height: 1.4;
        color: var(--rs-err-text);
      }

      .section {
        margin-top: var(--rs-space-4);
      }

      .section-title {
        margin: 0 0 var(--rs-space-2);
        font-size: var(--rs-font-sm);
        color: var(--secondary-text-color);
      }

      .hint {
        margin: var(--rs-space-2) 0 0;
        font-size: var(--rs-font-sm);
        line-height: 1.4;
        color: var(--secondary-text-color);
      }

      .footer {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: var(--rs-space-2);
        margin-top: var(--rs-space-4);
        padding-top: var(--rs-space-3);
        border-top: 1px solid var(--rs-border);
      }
    `,
  ];

  protected willUpdate(changed: PropertyValues<this>): void {
    if (changed.has("blockKey") || (changed.has("block") && !changed.get("block"))) {
      this._reset();
    } else if (changed.has("block") && this.block) {
      // Applied from outside (drag, keyboard) while the form is open.
      this._start = this.block.start;
      this._end = this.block.end;
    }
  }

  private _reset() {
    if (!this.block) return;
    this._start = this.block.start;
    this._end = this.block.end;
    const t = blockTemps(this.block);
    this._own = !usesComfort(this.block);
    this._heat = t.heat ?? t.single ?? this.defaults.heat;
    this._cool = t.cool ?? t.single ?? this.defaults.cool;
    this._position = blockPosition(this.block) ?? COVER_CLOSED;
  }

  render() {
    if (!this.block) return nothing;
    const l = this.hass.language;
    const error = this._timeError();
    return html`
      <div class="times">
        <label>
          ${localize("schedule_editor.from", l)}
          <select
            style=${`color-scheme: ${this.hass.themes?.darkMode ? "dark" : "light"}`}
            aria-invalid=${error ? "true" : "false"}
            @change=${(e: Event) => this._onTime("start", e)}
          >
            ${this._options(0, DAY_MINUTES - SNAP_MINUTES, this._start)}
          </select>
        </label>
        <label>
          ${localize("schedule_editor.to", l)}
          <select
            style=${`color-scheme: ${this.hass.themes?.darkMode ? "dark" : "light"}`}
            aria-invalid=${error ? "true" : "false"}
            aria-describedby="time-error"
            @change=${(e: Event) => this._onTime("end", e)}
          >
            ${this._options(SNAP_MINUTES, DAY_MINUTES, this._end)}
          </select>
        </label>
      </div>
      ${
        error
          ? html`<div class="error" id="time-error" role="alert">
              <span>${error}</span>
              ${
                this._end < this._start
                  ? html`<ha-button appearance="outlined" @click=${this._onSplit}
                      >${localize("schedule_editor.split", l)}</ha-button
                    >`
                  : nothing
              }
            </div>`
          : nothing
      }
      ${this.cover ? this._renderPosition() : this._renderTemperature()}
      <div class="footer">
        <ha-button variant="danger" appearance="plain" @click=${this._onDelete}>
          <ha-icon slot="start" icon="mdi:delete-outline"></ha-icon>
          ${localize("schedule_editor.delete_block", l)}
        </ha-button>
        <ha-button @click=${this._onDone}>${localize("schedule.done", l)}</ha-button>
      </div>
    `;
  }

  private _renderTemperature() {
    const l = this.hass.language;
    return html`<div class="section">
      <p class="section-title" id="temp-title">${localize("schedule_editor.temperature", l)}</p>
      <rs-segmented
        .label=${localize("schedule_editor.temperature", l)}
        .options=${[
          { value: "comfort", label: localize("override.comfort", l), icon: "mdi:sofa" },
          { value: "own", label: localize("schedule_editor.own", l), icon: "mdi:thermometer" },
        ]}
        .value=${this._own ? "own" : "comfort"}
        @value-changed=${this._onKind}
      ></rs-segmented>
      ${this._own ? this._renderOwn() : html`<p class="hint">${this._comfortHint()}</p>`}
    </div>`;
  }

  private _renderPosition() {
    const l = this.hass.language;
    return html`<div class="section">
      <rs-number-field
        .label=${localize("schedule_editor.cover_position", l)}
        suffix="%"
        .min=${COVER_CLOSED}
        .max=${COVER_OPEN}
        .step=${1}
        .value=${this._position}
        .hint=${localize(
          this.gateOnly
            ? "schedule_editor.cover_position_gate"
            : "schedule_editor.cover_position_hint",
          l,
        )}
        @value-changed=${this._onPosition}
      ></rs-number-field>
    </div>`;
  }

  private _renderOwn() {
    const l = this.hass.language;
    const step = usesFahrenheit(this.hass) ? 1 : 0.5;
    const min = Math.ceil(toDisplay(MIN_TARGET_TEMP_C, this.hass));
    const max = Math.floor(toDisplay(MAX_TARGET_TEMP_C, this.hass));
    const fmt = (v: number) => `${formatNumber(v, this.hass, 0, 1)}\u00a0${tempUnit(this.hass)}`;
    const both = this.sides.heat && this.sides.cool;
    return html`
      ${
        this.sides.heat
          ? html`<div class="temp-row heat">
              <span
                ><ha-icon icon="mdi:fire" aria-hidden="true"></ha-icon>${localize(
                  both ? "schedule_editor.heat_below" : "schedule_editor.target",
                  l,
                )}</span
              >
              <rs-stepper
                .language=${l}
                .label=${localize(both ? "schedule_editor.heat_below" : "schedule_editor.target", l)}
                .value=${this._heat}
                .min=${min}
                .max=${max}
                .step=${step}
                .display=${fmt(this._heat)}
                @value-changed=${(e: CustomEvent<{ value: number }>) =>
                  this._onTemp("heat", e.detail.value)}
              ></rs-stepper>
            </div>`
          : nothing
      }
      ${
        this.sides.cool
          ? html`<div class="temp-row cool">
              <span
                ><ha-icon icon="mdi:snowflake" aria-hidden="true"></ha-icon>${localize(
                  both ? "schedule_editor.cool_above" : "schedule_editor.target",
                  l,
                )}</span
              >
              <rs-stepper
                .language=${l}
                .label=${localize(both ? "schedule_editor.cool_above" : "schedule_editor.target", l)}
                .value=${this._cool}
                .min=${min}
                .max=${max}
                .step=${step}
                .display=${fmt(this._cool)}
                @value-changed=${(e: CustomEvent<{ value: number }>) =>
                  this._onTemp("cool", e.detail.value)}
              ></rs-stepper>
            </div>`
          : nothing
      }
    `;
  }

  private _comfortHint() {
    const l = this.hass.language;
    return this.comfortText
      ? localize("schedule_editor.comfort_hint", l, { rooms: this.comfortText })
      : localize("schedule_editor.comfort_hint_plain", l);
  }

  /** Quarter hours plus the current value when it is off the grid (made elsewhere). */
  private _options(from: number, to: number, current: number) {
    const values: number[] = [];
    for (let m = from; m <= to; m += SNAP_MINUTES) values.push(m);
    if (!values.includes(current)) values.push(current);
    values.sort((a, b) => a - b);
    return values.map(
      (m) => html`<option value=${String(m)} ?selected=${m === current}>${hm(m)}</option>`,
    );
  }

  private _timeError(): string {
    const l = this.hass.language;
    if (this._end < this._start) {
      return localize("schedule_editor.error_before_start_midnight", l, {
        day: this.nextDayName,
      });
    }
    if (this._end === this._start) return localize("schedule_editor.error_empty", l);
    const clash = this.others.find((b) => b.start < this._end && this._start < b.end);
    if (clash) {
      return localize("schedule_editor.error_overlap", l, {
        range: `${hm(clash.start)}–${hm(clash.end)}`,
      });
    }
    return "";
  }

  private _onTime(edge: "start" | "end", e: Event) {
    const value = Number((e.target as HTMLSelectElement).value);
    if (edge === "start") this._start = value;
    else this._end = value;
    if (!this._timeError()) this._fire("block-times", { start: this._start, end: this._end });
  }

  private _onSplit() {
    this._fire("block-split", { start: this._start, endNextDay: this._end });
  }

  private _onKind(e: CustomEvent<{ value: string }>) {
    this._own = e.detail.value === "own";
    // Switching to own writes every side the rooms need, with the values the steppers show.
    this._fire("block-temps", {
      temps: this._own
        ? {
            ...(this.sides.heat ? { heat: this._heat } : {}),
            ...(this.sides.cool ? { cool: this._cool } : {}),
          }
        : null,
    });
  }

  private _onTemp(side: "heat" | "cool", value: number) {
    const step = usesFahrenheit(this.hass) ? 1 : 0.5;
    const v = roundToStep(value, step);
    const temps: BlockTempChange = {};
    if (side === "heat") {
      this._heat = temps.heat = v;
      // A band never inverts: cooling above stays at or over heating below.
      if (this.sides.cool && this._cool < v) this._cool = temps.cool = v;
    } else {
      this._cool = temps.cool = v;
      if (this.sides.heat && this._heat > v) this._heat = temps.heat = v;
    }
    // Only the sides that moved: the other keeps its stored value or keeps following comfort.
    this._fire("block-temps", { temps });
  }

  private _onPosition(e: CustomEvent<{ value: number | null }>) {
    if (e.detail.value == null) return;
    this._position = e.detail.value;
    this._fire("block-position", { position: this._position });
  }

  private _onDelete() {
    this._fire("block-delete", {});
  }

  private _onDone() {
    this._fire("block-done", {});
  }

  private _fire(name: string, detail: unknown) {
    this.dispatchEvent(new CustomEvent(name, { detail, bubbles: true }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-block-form": RsBlockForm;
  }
}
