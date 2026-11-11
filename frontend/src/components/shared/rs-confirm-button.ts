import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { tokens } from "../../styles/tokens";
import "./rs-confirm-dialog";

/**
 * Button for a destructive action in a settings row. With `confirmMessage` it asks first in
 * rs-confirm-dialog (`confirmHeading`, `confirmLabel`, both default to `label`); fires
 * `confirmed` (bubbles, composed) once the action is confirmed.
 */
@customElement("rs-confirm-button")
export class RsConfirmButton extends LitElement {
  @property({ type: String }) public label = "";
  @property({ type: String }) public icon = "";
  @property({ type: String }) public confirmMessage = "";
  @property({ type: String }) public confirmHeading = "";
  @property({ type: String }) public confirmLabel = "";
  @property({ type: Boolean }) public disabled = false;
  @property({ type: Boolean }) public destructive = false;
  /** Screen-reader name when several buttons share the visible label. */
  @property({ type: String }) public accessibleLabel = "";

  @state() private _asking = false;

  static styles = [
    tokens,
    css`
      :host {
        display: block;
      }

      .confirm-btn {
        display: inline-flex;
        align-items: center;
        gap: var(--rs-space-2);
        min-height: var(--rs-touch);
        background: transparent;
        border: 1px solid var(--rs-border);
        border-radius: var(--rs-radius-sm);
        padding: var(--rs-space-2) var(--rs-space-4);
        font-size: var(--rs-font-md);
        font-family: inherit;
        cursor: pointer;
        color: var(--primary-text-color);
        transition:
          background-color 0.2s,
          color 0.2s;
        --mdc-icon-size: 18px;
      }

      .confirm-btn:hover:not([disabled]) {
        background: var(--rs-fill);
      }

      .confirm-btn:focus-visible {
        outline: 2px solid var(--primary-color);
        outline-offset: 2px;
      }

      .confirm-btn.destructive {
        border-color: var(--rs-err);
        color: var(--rs-err);
      }

      .confirm-btn.destructive:hover:not([disabled]) {
        background: color-mix(in srgb, var(--rs-err) 12%, transparent);
      }

      .confirm-btn[disabled] {
        opacity: 0.5;
        cursor: not-allowed;
      }

      @media (prefers-reduced-motion: reduce) {
        .confirm-btn {
          transition: none;
        }
      }
    `,
  ];

  render() {
    return html`
      <button
        type="button"
        class="confirm-btn ${this.destructive ? "destructive" : ""}"
        ?disabled=${this.disabled}
        aria-label=${this.accessibleLabel || nothing}
        @click=${this._onClick}
      >
        ${this.icon ? html`<ha-icon .icon=${this.icon} aria-hidden="true"></ha-icon>` : nothing}
        ${this.label}
      </button>
      <rs-confirm-dialog
        .open=${this._asking}
        .heading=${this.confirmHeading || this.label}
        .icon=${this.icon || "mdi:alert-outline"}
        .message=${this.confirmMessage}
        .confirmLabel=${this.confirmLabel || this.label}
        .destructive=${this.destructive}
        @cancel=${() => (this._asking = false)}
        @confirm=${this._onConfirm}
      ></rs-confirm-dialog>
    `;
  }

  private _onClick() {
    if (this.disabled) return;
    if (this.confirmMessage) this._asking = true;
    else this._fire();
  }

  private _onConfirm() {
    this._asking = false;
    this._fire();
  }

  private _fire() {
    this.dispatchEvent(new CustomEvent("confirmed", { bubbles: true, composed: true }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-confirm-button": RsConfirmButton;
  }
}
