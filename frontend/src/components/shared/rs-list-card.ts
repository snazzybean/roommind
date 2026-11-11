import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import { tokens } from "../../styles/tokens";
import "./rs-info-icon";

/**
 * Card holding `rs-list-row`s: optional header with heading, info icon (`info` text or the
 * `info` slot), an aside text on the right, the `header-extras` slot (badges, buttons after the
 * heading) and the `header-end` slot (e.g. an overflow menu at the right edge).
 * Rows go into the default slot. `unclipped`: content may reach past the card (popups and
 * chart tooltips positioned inside it); the card then does not clip row hovers at its corners.
 */
@customElement("rs-list-card")
export class RsListCard extends LitElement {
  @property({ type: String }) public heading = "";
  @property({ type: String }) public aside = "";
  @property({ type: String }) public info = "";
  @property({ type: Boolean, reflect: true }) public unclipped = false;

  static styles = [
    tokens,
    css`
      :host {
        display: block;
        min-width: 0;
      }

      ha-card {
        overflow: hidden;
        padding-bottom: var(--rs-space-2);
      }

      :host([unclipped]) ha-card {
        overflow: visible;
      }

      ha-card.headless {
        padding-top: var(--rs-space-2);
      }

      .head {
        display: flex;
        align-items: center;
        gap: var(--rs-space-2);
        padding: var(--rs-space-4) var(--rs-space-4) var(--rs-space-1);
        min-height: 28px;
      }

      h3 {
        margin: 0;
        font-size: var(--rs-font-lg);
        font-weight: 500;
        line-height: 24px;
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .grow {
        flex: 1;
      }

      .aside {
        font-size: var(--rs-font-sm);
        color: var(--secondary-text-color);
        white-space: nowrap;
        font-variant-numeric: tabular-nums;
      }
    `,
  ];

  render() {
    if (!this.heading) {
      return html`<ha-card class="headless"><slot></slot></ha-card>`;
    }
    return html`<ha-card>
      <div class="head">
        <h3>${this.heading}</h3>
        ${this.info ? html`<rs-info-icon .text=${this.info}></rs-info-icon>` : nothing}
        <slot name="header-extras"></slot>
        <span class="grow"></span>
        ${this.aside ? html`<span class="aside">${this.aside}</span>` : nothing}
        <slot name="header-end"></slot>
      </div>
      <slot></slot>
    </ha-card>`;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-list-card": RsListCard;
  }
}
