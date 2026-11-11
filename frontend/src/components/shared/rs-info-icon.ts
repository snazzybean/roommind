import { LitElement, html, css } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { localize, uiLanguage } from "../../utils/localize";
import "./rs-tooltip";

/**
 * Info button whose explanation opens in the shared `rs-tooltip` (text or slotted content).
 * `disclosure`: for texts too long for a tooltip; the button only toggles (`aria-expanded` from
 * `expanded`) and fires `info-toggle`, the parent shows the text in its own panel.
 */
@customElement("rs-info-icon")
export class RsInfoIcon extends LitElement {
  @property({ type: String }) public text = "";
  @property({ type: String }) public icon = "mdi:information-outline";
  @property({ type: Boolean }) public disclosure = false;
  @property({ type: Boolean }) public expanded = false;
  /** Accessible name; a localized "More information" when empty. */
  @property({ type: String }) public label = "";

  @state() private _open = false;

  static styles = css`
    :host {
      display: inline-flex;
      position: relative;
      vertical-align: middle;
      line-height: 0;
    }

    button {
      background: none;
      border: none;
      padding: 2px;
      margin: 0;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      color: var(--secondary-text-color);
      opacity: 0.65;
      transition:
        opacity 0.15s,
        color 0.15s,
        background 0.15s;
      border-radius: 50%;
      line-height: 0;
    }

    button:hover,
    button:focus-visible {
      opacity: 1;
      color: var(--primary-color);
      background: color-mix(in srgb, var(--primary-color) 10%, transparent);
      outline: none;
    }

    button:focus-visible {
      box-shadow: 0 0 0 2px var(--primary-color);
    }

    button.open {
      opacity: 1;
      color: var(--primary-color);
      background: color-mix(in srgb, var(--primary-color) 12%, transparent);
    }

    ha-icon {
      --mdc-icon-size: 16px;
    }
  `;

  render() {
    if (this.disclosure) {
      return html`<button
        type="button"
        class=${this.expanded ? "open" : ""}
        aria-label=${this.label || localize("common.info", uiLanguage())}
        aria-expanded=${this.expanded ? "true" : "false"}
        @click=${() => this.dispatchEvent(new CustomEvent("info-toggle"))}
      >
        <ha-icon .icon=${this.icon}></ha-icon>
      </button>`;
    }
    return html`
      <rs-tooltip
        .text=${this.text}
        @tooltip-toggle=${(e: CustomEvent<{ open: boolean }>) => {
          this._open = e.detail.open;
        }}
      >
        <button
          type="button"
          class=${this._open ? "open" : ""}
          aria-label=${this.label || localize("common.info", uiLanguage())}
          aria-expanded=${this._open ? "true" : "false"}
        >
          <ha-icon .icon=${this.icon}></ha-icon>
        </button>
        <slot slot="content"></slot>
      </rs-tooltip>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-info-icon": RsInfoIcon;
  }
}
