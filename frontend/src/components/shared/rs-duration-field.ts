import { LitElement, html, css, nothing, type PropertyValues } from "lit";
import { customElement, property, query } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { tokens } from "../../styles/tokens";

/**
 * The panel's duration input, shaped like Home Assistant's own "For at least"
 * editor: `hh`, `mm`, `ss` boxes separated by colons, plus a fourth `ms` box
 * because tariff debounces legitimately settle below a second (a relay at a
 * price boundary, an inverter at standby). Stored value is total seconds,
 * may be fractional; each box is clamped to its natural range and the whole
 * row is clamped to `maxSeconds` (default the registry's 3600 s ceiling),
 * written back into the boxes so what is shown is what will be saved.
 * Commits on change (blur, Enter), not on every keystroke.
 * Fires `value-changed` (not bubbling) with `{ value }` (seconds) only when
 * the value changed.
 */
@customElement("rs-duration-field")
export class RsDurationField extends LitElement {
  @property({ attribute: false }) public hass?: HomeAssistant;
  @property({ type: String }) public label = "";
  /** Total seconds; fractional ms allowed. */
  @property({ type: Number }) public value = 0;
  @property({ type: Number }) public maxSeconds = 3600;
  @property({ type: Boolean }) public disabled = false;

  @query("#hh") private _hh?: HTMLInputElement;
  @query("#mm") private _mm?: HTMLInputElement;
  @query("#ss") private _ss?: HTMLInputElement;
  @query("#ms") private _ms?: HTMLInputElement;

  private get _inputs(): { el: HTMLInputElement | undefined; cap: number }[] {
    return [
      { el: this._hh, cap: Math.floor(this.maxSeconds / 3600) },
      { el: this._mm, cap: 59 },
      { el: this._ss, cap: 59 },
      { el: this._ms, cap: 999 },
    ];
  }

  static styles = [
    tokens,
    css`
      :host {
        display: block;
        min-width: 0;
      }

      .label {
        color: var(--mdc-theme-text-secondary-color, var(--secondary-text-color));
        font-size: var(--rs-font-sm, 0.8rem);
        margin-bottom: 4px;
      }

      .row {
        display: flex;
        align-items: center;
        gap: 6px;
        border: 1px solid var(--outline-color, #444);
        border-radius: 8px;
        padding: 6px 10px;
        background: var(--card-background-color);
      }

      .cell {
        flex: 1;
        display: flex;
        flex-direction: column;
        align-items: center;
        min-width: 0;
      }

      .cell small {
        color: var(--secondary-text-color);
        font-size: 0.65rem;
      }

      .cell input {
        width: 100%;
        background: none;
        border: none;
        color: var(--primary-text-color);
        font: inherit;
        font-variant-numeric: tabular-nums;
        text-align: center;
        padding: 2px 0;
      }

      .cell input:focus {
        outline: none;
      }

      .cell input:disabled {
        color: var(--disabled-text-color);
      }

      .colon {
        color: var(--secondary-text-color);
      }
    `,
  ];

  private _total(parts: number[]): number {
    const [hh, mm, ss, ms] = parts.map((v) => (Number.isFinite(v) ? v : 0));
    return Math.max(0, Math.min(this.maxSeconds, hh * 3600 + mm * 60 + ss + ms / 1000));
  }

  private _parts(seconds: number): number[] {
    const clamped = Math.max(0, Math.min(this.maxSeconds, seconds || 0));
    return [
      Math.floor(clamped / 3600),
      Math.floor((clamped % 3600) / 60),
      Math.floor(clamped % 60),
      Math.round((clamped * 1000) % 1000),
    ];
  }

  /** Zero-pad the two natural-width boxes so 05 is distinguishable from 5 while typing. */
  private _text(index: number): string {
    const p = this._parts(this.value ?? 0);
    const raw = String(p[index]);
    if (index === 1 || index === 2) return raw.padStart(2, "0");
    return raw;
  }

  protected updated(changed: PropertyValues<this>): void {
    if (this._lastCommitted === null) this._lastCommitted = this.value ?? 0;
    if (changed.has("value") && !this._typing) {
      this._syncBoxes();
    }
    if (changed.has("maxSeconds")) this._syncBoxes();
  }

  private _typing = false;

  private _syncBoxes(): void {
    const boxes = [this._hh, this._mm, this._ss, this._ms];
    const active = document.activeElement;
    boxes.forEach((el, i) => {
      if (el && el !== active) el.value = this._text(i);
    });
  }

  render() {
    const cells = [
      { id: "hh", caption: "hh" },
      { id: "mm", caption: "mm" },
      { id: "ss", caption: "ss" },
      { id: "ms", caption: "ms" },
    ];
    return html`${this.label ? html`<div class="label">${this.label}</div>` : nothing}
      <div class="row">
        ${cells.map(
          (c, i) =>
            html`${i > 0 ? html`<span class="colon">:</span>` : nothing}
              <span class="cell">
                <small>${c.caption}</small>
                <input
                  id=${c.id}
                  type="number"
                  min="0"
                  .max=${String(this._inputs[i].cap)}
                  .value=${this._text(i)}
                  .disabled=${this.disabled}
                  @focus=${() => (this._typing = true)}
                  @blur=${() => {
                    this._typing = false;
                    this._commit();
                  }}
                  @keydown=${(e: KeyboardEvent) => e.key === "Enter" && this._commit()}
                />
              </span>`,
        )}
      </div>`;
  }

  private _read(): number[] {
    return [this._hh, this._mm, this._ss, this._ms].map((el) => {
      const n = Number(el?.value ?? 0);
      return Number.isFinite(n) ? Math.max(0, n) : 0;
    });
  }

  private _commit(): void {
    const total = this._total(this._read());
    this.value = total;
    this._syncBoxes();
    if (total !== Number(this._lastCommitted)) {
      this._lastCommitted = total;
      this.dispatchEvent(new CustomEvent("value-changed", { detail: { value: total } }));
    }
  }

  private _lastCommitted: number | null = null;
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-duration-field": RsDurationField;
  }
}
