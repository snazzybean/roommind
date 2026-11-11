import { LitElement, html, css, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";
import { tokens } from "../../styles/tokens";
import { formatNumber } from "../../utils/format";
import {
  MAX_TARGET_TEMP_C,
  MIN_TARGET_TEMP_C,
  tempUnit,
  toDisplay,
  usesFahrenheit,
} from "../../utils/temperature";
import {
  DAY_MINUTES,
  SNAP_MINUTES,
  blockTemps,
  hm,
  roundToStep,
  usesComfort,
  type ScheduleBlock,
} from "../../utils/schedule-week";
import "../shared/rs-segmented";
import "../shared/rs-stepper";

export interface BlockTempChange {
  heat?: number;
  cool?: number;
}

/**
 * Form for one schedule block (desktop popover, phone sheet): from/to, comfort or own
 * temperature, delete. Applies every valid change at once (no save button):
 * `block-times` `{ start, end }`, `block-split` `{ start, endNextDay }` for a range past
 * midnight, `block-temps` `{ temps }` (null = comfort), `block-delete`, `block-done`.
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

  @state() private _start = 0;
  @state() private _end = 60;
  @state() private _own = false;
  @state() private _heat = 21;
  @state() private _cool = 24;

  static styles = [
    tokens,
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
        background-color: var(--card-background-color, var(--primary-background-color));
        color: var(--primary-text-color);
        font: inherit;
        font-size: 16px;
        font-variant-numeric: tabular-nums;
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
        color: var(--rs-err);
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

      .temp-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: var(--rs-space-3);
        margin-top: var(--rs-space-3);
        font-size: var(--rs-font-md);
      }

      .temp-row span {
        display: inline-flex;
        align-items: center;
        gap: var(--rs-space-2);
      }

      .temp-row ha-icon {
        --mdc-icon-size: 18px;
      }

      .heat ha-icon {
        color: var(--rs-heat);
      }

      .cool ha-icon {
        color: var(--rs-cool);
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
            aria-invalid=${error ? "true" : "false"}
            @change=${(e: Event) => this._onTime("start", e)}
          >
            ${this._options(0, DAY_MINUTES - SNAP_MINUTES, this._start)}
          </select>
        </label>
        <label>
          ${localize("schedule_editor.to", l)}
          <select
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
      <div class="section">
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
      </div>
      <div class="footer">
        <ha-button variant="danger" appearance="plain" @click=${this._onDelete}>
          <ha-icon slot="start" icon="mdi:delete-outline"></ha-icon>
          ${localize("schedule_editor.delete_block", l)}
        </ha-button>
        <ha-button @click=${this._onDone}>${localize("schedule.done", l)}</ha-button>
      </div>
    `;
  }

  private _renderOwn() {
    const l = this.hass.language;
    const step = usesFahrenheit(this.hass) ? 1 : 0.5;
    const min = Math.ceil(toDisplay(MIN_TARGET_TEMP_C, this.hass));
    const max = Math.floor(toDisplay(MAX_TARGET_TEMP_C, this.hass));
    const fmt = (v: number) => `${formatNumber(v, this.hass, 0, 1)} ${tempUnit(this.hass)}`;
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
    this._emitTemps();
  }

  private _onTemp(side: "heat" | "cool", value: number) {
    const step = usesFahrenheit(this.hass) ? 1 : 0.5;
    const v = roundToStep(value, step);
    if (side === "heat") {
      this._heat = v;
      // A band never inverts: cooling above stays at or over heating below.
      if (this.sides.cool && this._cool < v) this._cool = v;
    } else {
      this._cool = v;
      if (this.sides.heat && this._heat > v) this._heat = v;
    }
    this._emitTemps();
  }

  private _emitTemps() {
    const temps: BlockTempChange | null = this._own
      ? {
          ...(this.sides.heat ? { heat: this._heat } : {}),
          ...(this.sides.cool ? { cool: this._cool } : {}),
        }
      : null;
    this._fire("block-temps", { temps });
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
