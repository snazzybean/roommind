import { LitElement, html, css } from "lit";
import { customElement, property } from "lit/decorators.js";
import { ifDefined } from "lit/directives/if-defined.js";
import { tokens } from "../../styles/tokens";
import "./rs-tooltip";

/**
 * Round icon button named by the shared tooltip instead of `title`. The label is also the
 * accessible name. Clicks bubble from the host like from a native button.
 */
@customElement("rs-icon-button")
export class RsIconButton extends LitElement {
  @property({ type: String }) public icon = "";
  @property({ type: String }) public label = "";
  @property({ type: Boolean, reflect: true }) public disabled = false;
  /** Toggle buttons: sets `aria-pressed`. */
  @property({ attribute: false }) public pressed: boolean | undefined = undefined;
  @property({ type: String }) public haspopup: "" | "menu" = "";
  @property({ type: Boolean }) public expanded = false;
  /** `sm` = 40 px (44 px on touch), `md` = 48 px like HA's toolbar buttons. */
  @property({ type: String, reflect: true }) public size: "sm" | "md" = "md";

  static styles = [
    tokens,
    css`
      :host {
        display: inline-flex;
        flex: none;
      }

      button {
        width: 48px;
        height: 48px;
        border-radius: 50%;
        border: none;
        padding: 0;
        margin: 0;
        display: grid;
        place-items: center;
        background: var(--rs-icon-button-background, none);
        color: var(--rs-icon-button-color, inherit);
        cursor: pointer;
        font: inherit;
        --mdc-icon-size: 24px;
        transition: background-color 0.15s ease;
      }

      :host([size="sm"]) button {
        width: 40px;
        height: 40px;
        --mdc-icon-size: 20px;
      }

      @media (pointer: coarse) {
        :host([size="sm"]) button {
          width: var(--rs-touch);
          height: var(--rs-touch);
        }
      }

      button:hover:not(:disabled) {
        background: var(--rs-icon-button-hover, var(--rs-fill-strong));
      }

      button:focus-visible {
        outline: 2px solid var(--primary-color);
        outline-offset: 1px;
      }

      button:disabled {
        opacity: 0.35;
        cursor: default;
      }
    `,
  ];

  focus(options?: FocusOptions) {
    this.renderRoot.querySelector("button")?.focus(options);
  }

  /** Focus without showing the tooltip, e.g. when a menu hands the focus back. */
  focusQuietly() {
    this.focus();
    this.renderRoot.querySelector("rs-tooltip")?.hide();
  }

  render() {
    return html`
      <rs-tooltip mode="label" .text=${this.label} .disabled=${this.disabled}>
        <button
          type="button"
          aria-label=${this.label}
          aria-pressed=${ifDefined(this.pressed === undefined ? undefined : String(this.pressed))}
          aria-haspopup=${ifDefined(this.haspopup || undefined)}
          aria-expanded=${ifDefined(this.haspopup ? String(this.expanded) : undefined)}
          ?disabled=${this.disabled}
        >
          <ha-icon .icon=${this.icon}></ha-icon>
        </button>
      </rs-tooltip>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-icon-button": RsIconButton;
  }
}
