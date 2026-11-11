/**
 * rs-badge – Small pill badge (e.g. "Beta") for section headers.
 * Used in list card and settings page headers. With `tooltip` the hint opens in the shared
 * tooltip (a focusable button); without it stays a `title`, for headers that are themselves
 * clickable (an expansion panel must not contain a second control).
 */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import "./rs-tooltip";

@customElement("rs-badge")
export class RsBadge extends LitElement {
  @property({ type: String }) public label = "";
  @property({ type: String }) public hint = "";
  @property({ type: Boolean }) public tooltip = false;

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

    button.badge {
      border: none;
      font-family: inherit;
      line-height: inherit;
      cursor: help;
    }

    button.badge:focus-visible {
      outline: 2px solid var(--primary-color);
      outline-offset: 1px;
    }
  `;

  render() {
    if (!this.hint || !this.tooltip) {
      return html`<span class="badge" title=${this.hint || nothing}>${this.label}</span>`;
    }
    return html`<rs-tooltip .text=${this.hint}>
      <button type="button" class="badge" aria-label=${`${this.label}: ${this.hint}`}>
        ${this.label}
      </button>
    </rs-tooltip>`;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-badge": RsBadge;
  }
}
