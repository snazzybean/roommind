import { LitElement, html, css, type PropertyValues } from "lit";
import { customElement, property, query } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { inputStyles } from "../../styles/input-styles";
import { tokens } from "../../styles/tokens";
import {
  tempUnit,
  toCelsius,
  toCelsiusDelta,
  toDisplay,
  toDisplayDelta,
  usesFahrenheit,
} from "../../utils/temperature";
import "./rs-field";

/** What the value means: a plain number, a temperature or a temperature difference (°C stored). */
export type NumberKind = "number" | "temperature" | "temperature-delta";

/**
 * The panel's number input. Commits on change (blur, Enter), not on every keystroke, so a
 * half-typed value never reaches the auto-save. The value is clamped to `min`/`max`, rounded
 * to `step` and written back into the field, so what the field shows is what was saved; an
 * empty (unless `allow-empty`) or unreadable entry goes back to the last value. Temperatures are stored in °C and shown
 * in the user's unit (`kind`, needs `hass`): `value`, `min`, `max` stay in °C, `step` defaults to
 * 0.5 °C / 1 °F. Floating label inside the field, `info` icon beside it, `hint` below (rs-field).
 * Shown and typed in the user's language: German shows "1,5" and accepts "1,5" and "1.5".
 * Fires `value-changed` (not bubbling, listen on the field) with `{ value }` (°C for
 * temperatures) only when the value changed.
 */
@customElement("rs-number-field")
export class RsNumberField extends LitElement {
  @property({ attribute: false }) public hass?: HomeAssistant;
  @property({ type: String }) public kind: NumberKind = "number";
  @property({ type: String }) public label = "";
  @property({ type: String }) public info = "";
  @property({ type: String }) public hint = "";
  /** Unit after the number; temperatures default to °C/°F. */
  @property({ type: String }) public suffix = "";
  @property({ type: Number }) public value: number | null = null;
  @property({ type: Number }) public min: number | undefined;
  @property({ type: Number }) public max: number | undefined;
  /** In display units; default 1, temperatures 0.5 °C / 1 °F. */
  @property({ type: Number }) public step: number | undefined;
  @property({ type: Boolean }) public disabled = false;
  /** An emptied field commits `null` (an optional value, e.g. "no threshold") instead of going back. */
  @property({ type: Boolean, attribute: "allow-empty" }) public allowEmpty = false;

  @query("ha-textfield") private _field?: HTMLElement & { value: string };

  static styles = [
    tokens,
    inputStyles,
    css`
      :host {
        display: block;
        min-width: 0;
      }

      ha-textfield {
        width: 100%;
      }
    `,
  ];

  private get _isTemp(): boolean {
    return this.kind !== "number" && !!this.hass;
  }

  private _toShown(v: number): number {
    if (!this._isTemp) return v;
    return this.kind === "temperature" ? toDisplay(v, this.hass!) : toDisplayDelta(v, this.hass!);
  }

  private _fromShown(v: number): number {
    if (!this._isTemp) return v;
    return this.kind === "temperature" ? toCelsius(v, this.hass!) : toCelsiusDelta(v, this.hass!);
  }

  private get _step(): number {
    if (this.step !== undefined) return this.step;
    if (this._isTemp) return usesFahrenheit(this.hass!) ? 1 : 0.5;
    return 1;
  }

  /** Display bounds; temperature limits round inwards so a converted bound stays valid. */
  private get _bounds(): { min: number; max: number } {
    const step = this._step;
    const min = this.min === undefined ? -Infinity : this._toShown(this.min);
    const max = this.max === undefined ? Infinity : this._toShown(this.max);
    return {
      min: Number.isFinite(min) ? Math.ceil(min / step - 1e-9) * step : min,
      max: Number.isFinite(max) ? Math.floor(max / step + 1e-9) * step : max,
    };
  }

  private _decimals(): number {
    const s = String(this._step);
    return s.includes(".") ? s.split(".")[1].length : 0;
  }

  /** Number in the user's language (decimal comma in German), no grouping. */
  private _format(shown: number): string {
    return new Intl.NumberFormat(this.hass?.language, {
      maximumFractionDigits: this._isTemp ? Math.max(1, this._decimals()) : 6,
      useGrouping: false,
    }).format(shown);
  }

  private _shownText(): string {
    if (this.value === null || this.value === undefined || Number.isNaN(this.value)) return "";
    return this._format(this._toShown(this.value));
  }

  protected updated(changed: PropertyValues<this>): void {
    // A value equal to the old one does not re-render; keep the field in step anyway
    if (changed.has("value") && this._field && this._field.value !== this._shownText()) {
      this._field.value = this._shownText();
    }
  }

  render() {
    const { min } = this._bounds;
    const suffix = this.suffix || (this._isTemp ? tempUnit(this.hass!) : "");
    return html`<rs-field .info=${this.info} .hint=${this.hint}>
      <ha-textfield
        type="text"
        .inputMode=${min >= 0 ? (Number.isInteger(this._step) ? "numeric" : "decimal") : "text"}
        .label=${this.label}
        .suffix=${suffix}
        .value=${this._shownText()}
        .disabled=${this.disabled}
        @change=${this._onChange}
      ></ha-textfield>
    </rs-field>`;
  }

  private _onChange(e: Event) {
    e.stopPropagation();
    const field = e.target as HTMLElement & { value: string };
    if (this.allowEmpty && String(field.value).trim() === "") {
      field.value = "";
      if (this.value != null) {
        this.dispatchEvent(new CustomEvent("value-changed", { detail: { value: null } }));
      }
      return;
    }
    // type=number would follow the browser's locale, not the panel's; accept comma and dot
    const raw = parseFloat(
      String(field.value).replace(/\s/g, "").replace("\u2212", "-").replace(",", "."),
    );
    if (!Number.isFinite(raw)) {
      field.value = this._shownText();
      return;
    }
    const step = this._step;
    const { min, max } = this._bounds;
    const rounded = Number((Math.round(raw / step) * step).toFixed(this._decimals()));
    const shown = Math.min(max, Math.max(min, rounded));
    field.value = this._format(shown);
    const value = this._fromShown(shown);
    const current = this.value ?? NaN;
    if (Math.abs(value - current) < 1e-6) return;
    // Not bubbling: entity pickers use the same event name around it
    this.dispatchEvent(new CustomEvent("value-changed", { detail: { value } }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-number-field": RsNumberField;
  }
}
