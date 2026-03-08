/**
 * rs-badge – Small pill badge (e.g. "Beta") for section headers.
 * Reused in rs-section-card and rs-settings-panel.
 */
import { LitElement, html, css } from "lit";
import { customElement, property } from "lit/decorators.js";

@customElement("rs-badge")
export class RsBadge extends LitElement {
  @property({ type: String }) public label = "";
  @property({ type: String }) public hint = "";

  static styles = css`
    :host {
      display: inline-block;
    }

    .badge {
      font-size: 10px;
      font-weight: 600;
      color: var(--primary-color);
      background: color-mix(in srgb, var(--primary-color) 12%, transparent);
      padding: 2px 6px;
      border-radius: 4px;
      letter-spacing: 0.5px;
      text-transform: uppercase;
      cursor: default;
    }
  `;

  render() {
    return html`<span class="badge" title=${this.hint}>${this.label}</span>`;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-badge": RsBadge;
  }
}
