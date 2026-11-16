import { LitElement, html, css } from "lit";
import { customElement, property } from "lit/decorators.js";
import { tokens, srOnly } from "../../styles/tokens";
import { localize, uiLanguage } from "../../utils/localize";

/**
 * Number stepper: minus, value, plus. Native buttons with 44 px targets, the value is announced
 * politely. `display` is the formatted value (unit included). Fires `value-changed` with
 * `{ value }`. Buttons clamp to min/max and move to the next point of the step grid.
 * Editable steppers accept exact in-range decimals on Enter/blur; Escape resets a changed entry.
 */
@customElement("rs-stepper")
export class RsStepper extends LitElement {
  /** Opt-in exact decimal entry; other steppers retain their output-only behavior. */
  @property({ type: Boolean }) public editable = false;
  @property({ type: String }) public unit = "";
  @property({ type: Number }) public value = 0;
  @property({ type: Number }) public min = -Infinity;
  @property({ type: Number }) public max = Infinity;
  @property({ type: Number }) public step = 1;
  /** Accessible name of the group (e.g. "Heizen unter"). */
  @property({ type: String }) public label = "";
  @property({ type: String }) public display = "";
  @property({ type: Boolean, reflect: true }) public disabled = false;
  /** HA profile language for the button names (components without `hass` pass it down). */
  @property({ type: String }) public language = "";

  static styles = [
    tokens,
    srOnly,
    css`
      :host {
        display: inline-flex;
      }

      .stepper {
        display: inline-flex;
        align-items: center;
        border: 1px solid var(--rs-border);
        border-radius: calc(var(--rs-touch) / 2);
      }

      button {
        width: var(--rs-touch);
        height: var(--rs-touch);
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border: none;
        border-radius: 50%;
        background: none;
        color: var(--primary-text-color);
        cursor: pointer;
        touch-action: manipulation;
        --mdc-icon-size: 20px;
      }

      button:hover:not(:disabled):not([aria-disabled="true"]) {
        background: var(--rs-fill);
      }

      .entry {
        display: inline-flex;
        align-items: baseline;
        justify-content: center;
        gap: 2px;
        min-width: 76px;
        font-size: var(--rs-font-md);
      }

      /* 16 px keeps iOS Safari from zooming in on focus. */
      input {
        width: 5ch;
        min-height: var(--rs-touch);
        padding: 0;
        border: none;
        background: transparent;
        color: var(--primary-text-color);
        font-family: inherit;
        font-size: 16px;
        font-variant-numeric: tabular-nums;
        text-align: end;
      }

      input:disabled {
        opacity: 0.35;
      }

      input:focus-visible,
      button:focus-visible {
        outline: 2px solid var(--primary-color);
        outline-offset: -2px;
      }

      button:disabled,
      button[aria-disabled="true"] {
        opacity: 0.35;
        cursor: default;
      }

      output {
        min-width: 64px;
        text-align: center;
        font-size: var(--rs-font-md);
        font-variant-numeric: tabular-nums;
        white-space: nowrap;
      }
    `,
  ];

  private get _atMin(): boolean {
    return this.editable ? this.value <= this.min : this.value - this.step < this.min - 1e-9;
  }

  private get _atMax(): boolean {
    return this.editable ? this.value >= this.max : this.value + this.step > this.max + 1e-9;
  }

  /**
   * At a limit the button is only aria-disabled: a really disabled button would drop the
   * focus of a keyboard user who just pressed it.
   */
  render() {
    const l = this.language || uiLanguage();
    return html`<div class="stepper" role="group" aria-label=${this.label}>
      <button
        type="button"
        aria-label=${localize("common.decrease", l)}
        aria-disabled=${this._atMin ? "true" : "false"}
        ?disabled=${this.disabled}
        @click=${() => this._step(-1)}
      >
        <ha-icon icon="mdi:minus" aria-hidden="true"></ha-icon>
      </button>
      ${
        this.editable
          ? html`<label class="entry"
                ><input
                  type="text"
                  inputmode="decimal"
                  enterkeyhint="done"
                  autocomplete="off"
                  aria-label=${`${this.label} (${this.unit})`}
                  .value=${this._formattedValue()}
                  ?disabled=${this.disabled}
                  @focus=${this._selectAll}
                  @blur=${this._commit}
                  @keydown=${this._onKeydown}
                /><span aria-hidden="true">${this.unit}</span></label
              ><span class="sr-only" aria-live="polite" aria-atomic="true"
                >${this._formattedValue()} ${this.unit}</span
              >`
          : html`<output aria-live="polite">${this.display || String(this.value)}</output>`
      }
      <button
        type="button"
        aria-label=${localize("common.increase", l)}
        aria-disabled=${this._atMax ? "true" : "false"}
        ?disabled=${this.disabled}
        @click=${() => this._step(1)}
      >
        <ha-icon icon="mdi:plus" aria-hidden="true"></ha-icon>
      </button>
    </div>`;
  }

  private _formattedValue(): string {
    return new Intl.NumberFormat(this.language || uiLanguage(), {
      useGrouping: false,
      maximumFractionDigits: 2,
    }).format(this.value);
  }

  private _selectAll(e: FocusEvent) {
    const input = e.target as HTMLInputElement;
    // Safari drops a selection made on focus when the tap or click ends; select once it has.
    requestAnimationFrame(() => input.setSelectionRange(0, input.value.length));
  }

  private _commit(e: Event) {
    const input = e.target as HTMLInputElement;
    const text = input.value.trim().replace(",", ".");
    const value = /^[-+]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(text) ? Number(text) : NaN;
    // Reject rather than clamp mistyped targets; restore the saved value without emitting.
    if (
      !this.disabled &&
      Number.isFinite(value) &&
      value >= this.min &&
      value <= this.max &&
      input.value !== this._formattedValue() &&
      value !== this.value
    ) {
      this.dispatchEvent(new CustomEvent("value-changed", { detail: { value }, bubbles: true }));
    }
    input.value = this._formattedValue();
  }

  private _onKeydown(e: KeyboardEvent) {
    if (e.key === "Enter") {
      e.preventDefault();
      this._commit(e);
      (e.target as HTMLInputElement).blur();
    } else if (e.key === "Escape") {
      const input = e.target as HTMLInputElement;
      // An unchanged field lets Escape close the dialog; a changed one is only reset first.
      if (input.value === this._formattedValue()) return;
      e.preventDefault();
      e.stopPropagation();
      input.value = this._formattedValue();
      input.select();
    }
  }

  private _step(direction: 1 | -1) {
    if (this.disabled || (direction < 0 ? this._atMin : this._atMax)) return;
    const raw = this.value + direction * this.step;
    // An exact value off the grid moves to the next grid point, as on the dashboard card.
    const grid = this.value / this.step;
    const index = direction > 0 ? Math.floor(grid + 1e-6) + 1 : Math.ceil(grid - 1e-6) - 1;
    const rounded = this.editable
      ? Number((index * this.step).toFixed(10))
      : Number((Math.round(raw / this.step) * this.step).toFixed(2));
    const value = Math.min(this.max, Math.max(this.min, rounded));
    if (value === this.value) return;
    this.dispatchEvent(new CustomEvent("value-changed", { detail: { value }, bubbles: true }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-stepper": RsStepper;
  }
}
