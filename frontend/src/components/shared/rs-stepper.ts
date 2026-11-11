import { LitElement, html, css } from "lit";
import { customElement, property } from "lit/decorators.js";
import { tokens } from "../../styles/tokens";
import { localize, uiLanguage } from "../../utils/localize";

/**
 * Number stepper: minus, value, plus. Native buttons with 44 px targets, the value is announced
 * politely. `display` is the formatted value (unit included). Fires `value-changed` with
 * `{ value }`, already clamped to min/max and rounded to the step.
 */
@customElement("rs-stepper")
export class RsStepper extends LitElement {
  @property({ type: Number }) public value = 0;
  @property({ type: Number }) public min = -Infinity;
  @property({ type: Number }) public max = Infinity;
  @property({ type: Number }) public step = 1;
  /** Accessible name of the group (e.g. "Heizen unter"). */
  @property({ type: String }) public label = "";
  @property({ type: String }) public display = "";
  @property({ type: Boolean, reflect: true }) public disabled = false;

  static styles = [
    tokens,
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

      button:hover:not(:disabled) {
        background: var(--rs-fill);
      }

      button:focus-visible {
        outline: 2px solid var(--primary-color);
        outline-offset: -2px;
      }

      button:disabled {
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

  render() {
    const l = uiLanguage();
    return html`<div class="stepper" role="group" aria-label=${this.label}>
      <button
        type="button"
        aria-label=${localize("common.decrease", l)}
        ?disabled=${this.disabled || this.value - this.step < this.min - 1e-9}
        @click=${() => this._step(-1)}
      >
        <ha-icon icon="mdi:minus" aria-hidden="true"></ha-icon>
      </button>
      <output aria-live="polite">${this.display || String(this.value)}</output>
      <button
        type="button"
        aria-label=${localize("common.increase", l)}
        ?disabled=${this.disabled || this.value + this.step > this.max + 1e-9}
        @click=${() => this._step(1)}
      >
        <ha-icon icon="mdi:plus" aria-hidden="true"></ha-icon>
      </button>
    </div>`;
  }

  private _step(direction: 1 | -1) {
    const raw = this.value + direction * this.step;
    const rounded = Number((Math.round(raw / this.step) * this.step).toFixed(2));
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
