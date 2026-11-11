import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import { tokens } from "../../styles/tokens";

export interface RsSegmentOption {
  value: string;
  label: string;
  icon?: string;
  disabled?: boolean;
}

/**
 * Segmented choice (radio group). Arrow keys move the focus; Space/Enter (or a click) picks.
 * Manual activation on purpose: options often trigger a request, an arrow key must not send
 * one per step. `value` may be null (nothing picked). Fires `value-changed` with `{ value }`.
 */
@customElement("rs-segmented")
export class RsSegmented extends LitElement {
  @property({ attribute: false }) public options: RsSegmentOption[] = [];
  @property({ attribute: false }) public value: string | null = null;
  /** Accessible name of the group. */
  @property({ type: String }) public label = "";
  @property({ type: String, reflect: true }) public size: "sm" | "md" = "md";
  @property({ type: Boolean, reflect: true }) public disabled = false;

  static styles = [
    tokens,
    css`
      :host {
        display: block;
        min-width: 0;
      }

      .seg {
        display: flex;
        gap: 3px;
        padding: 3px;
        border-radius: 10px;
        background: var(--rs-fill);
      }

      button {
        flex: 1 1 0;
        min-width: 0;
        height: 34px;
        padding: 0 6px;
        border: none;
        border-radius: 8px;
        background: none;
        color: var(--secondary-text-color);
        font: inherit;
        font-size: 13px;
        font-weight: 500;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 5px;
        cursor: pointer;
        white-space: nowrap;
        --mdc-icon-size: 16px;
        transition:
          background-color 0.15s ease,
          color 0.15s ease;
      }

      @media (pointer: coarse) {
        :host([size="md"]) button {
          height: 38px;
        }
      }

      :host([size="sm"]) button {
        height: 28px;
        padding: 0 10px;
        font-size: 12px;
      }

      button span {
        overflow: hidden;
        text-overflow: ellipsis;
      }

      button:hover:not(:disabled):not([aria-checked="true"]) {
        color: var(--primary-text-color);
        background: var(--rs-fill);
      }

      button[aria-checked="true"] {
        background: var(--card-background-color, var(--primary-background-color));
        color: var(--primary-text-color);
        box-shadow: 0 1px 2px rgb(0 0 0 / 18%);
      }

      button:focus-visible {
        outline: 2px solid var(--primary-color);
        outline-offset: 1px;
      }

      button:disabled {
        opacity: 0.4;
        cursor: default;
      }

      ha-icon {
        flex: none;
      }

      @media (prefers-reduced-motion: reduce) {
        button {
          transition: none;
        }
      }
    `,
  ];

  render() {
    const enabled = this.options.filter((o) => !o.disabled && !this.disabled);
    const focusValue = enabled.some((o) => o.value === this.value)
      ? this.value
      : (enabled[0]?.value ?? null);
    return html`
      <div class="seg" role="radiogroup" aria-label=${this.label} @keydown=${this._onKey}>
        ${this.options.map((o) => {
          const checked = o.value === this.value;
          return html`<button
            type="button"
            role="radio"
            data-value=${o.value}
            aria-checked=${checked ? "true" : "false"}
            tabindex=${o.value === focusValue ? "0" : "-1"}
            ?disabled=${this.disabled || o.disabled}
            @click=${() => this._pick(o)}
          >
            ${o.icon ? html`<ha-icon .icon=${o.icon}></ha-icon>` : nothing}
            <span>${o.label}</span>
          </button>`;
        })}
      </div>
    `;
  }

  private _pick(o: RsSegmentOption) {
    if (this.disabled || o.disabled || o.value === this.value) return;
    this.dispatchEvent(
      new CustomEvent("value-changed", {
        detail: { value: o.value },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onKey(e: KeyboardEvent) {
    const keys = ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"];
    if (!keys.includes(e.key)) return;
    const buttons = [
      ...this.renderRoot.querySelectorAll<HTMLButtonElement>("button:not(:disabled)"),
    ];
    if (!buttons.length) return;
    e.preventDefault();
    const idx = buttons.indexOf(e.composedPath()[0] as HTMLButtonElement);
    const rtl = getComputedStyle(this).direction === "rtl";
    let next: number;
    if (e.key === "Home") next = 0;
    else if (e.key === "End") next = buttons.length - 1;
    else {
      let forward: boolean;
      if (e.key === "ArrowDown") forward = true;
      else if (e.key === "ArrowUp") forward = false;
      else forward = (e.key === "ArrowRight") !== rtl;
      next = (idx + (forward ? 1 : -1) + buttons.length) % buttons.length;
    }
    buttons.forEach((b, i) => (b.tabIndex = i === next ? 0 : -1));
    buttons[next].focus();
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-segmented": RsSegmented;
  }
}
