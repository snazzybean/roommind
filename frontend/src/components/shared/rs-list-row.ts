import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import { tokens } from "../../styles/tokens";
import "./rs-tooltip";

/**
 * List row in Home Assistant's settings style: icon in a circle, heading, secondary line and
 * a trailing value, chevron or switch.
 *
 * - `clickable`: the row is a button (`row-click`); `href` makes it a link instead.
 * - `switch`: a trailing `ha-switch`; a click anywhere on the row flips it (`toggle-changed`
 *   with the new state).
 * - `icon-label`: the icon becomes its own button (`icon-click`), e.g. Home Assistant's
 *   more-info for the entity, named by the shared tooltip.
 * - Slots: `secondary` (rich second line), `end` (extra controls after the value, outside the
 *   row button).
 */
@customElement("rs-list-row")
export class RsListRow extends LitElement {
  @property({ type: String }) public icon = "";
  @property({ type: String }) public heading = "";
  @property({ type: String }) public secondary = "";
  @property({ type: String }) public value = "";
  @property({ type: Boolean, reflect: true }) public clickable = false;
  @property({ type: String }) public href = "";
  @property({ type: Boolean }) public chevron = false;
  @property({ type: Boolean, reflect: true }) public switch = false;
  @property({ type: Boolean }) public checked = false;
  @property({ type: Boolean, reflect: true }) public disabled = false;
  @property({ type: String, attribute: "icon-label" }) public iconLabel = "";
  /** `danger` colours heading and icon (destructive), `primary` for an "add" row, `warn`. */
  @property({ type: String, reflect: true }) public variant:
    "default" | "danger" | "primary" | "warn" = "default";
  /** Colour of the icon (and its circle tint), e.g. `var(--rs-heat)`; default neutral. */
  @property({ type: String, attribute: "icon-color" }) public iconColor = "";
  /** Small icon without circle, e.g. for an "add" row. */
  @property({ type: Boolean, attribute: "plain-icon" }) public plainIcon = false;

  static styles = [
    tokens,
    css`
      :host {
        display: block;
        min-width: 0;
        --row-icon: var(--rs-row-icon-color, var(--secondary-text-color));
      }

      :host([variant="danger"]) {
        --row-icon: var(--rs-err);
      }

      :host([variant="primary"]) {
        --row-icon: var(--primary-color);
      }

      :host([variant="warn"]) {
        --row-icon: var(--rs-warn);
      }

      .row {
        display: flex;
        align-items: center;
        gap: var(--rs-space-4);
        min-height: 56px;
        padding: 0 var(--rs-list-row-padding, var(--rs-space-4));
        box-sizing: border-box;
        min-width: 0;
      }

      .main {
        flex: 1;
        min-width: 0;
        align-self: stretch;
        display: flex;
        align-items: center;
        gap: var(--rs-space-4);
        padding: var(--rs-space-2) 0;
        margin: 0;
        border: none;
        background: none;
        color: inherit;
        font: inherit;
        text-align: start;
        text-decoration: none;
      }

      button.main,
      a.main,
      .row.toggle .main {
        cursor: pointer;
      }

      /* the whole row reacts, the focus ring hugs the row */
      .row:has(button.main:hover, a.main:hover),
      .row.toggle:hover {
        background: var(--rs-fill);
      }

      button.main:focus-visible,
      a.main:focus-visible {
        outline: none;
      }

      .row:has(button.main:focus-visible, a.main:focus-visible) {
        box-shadow: inset 0 0 0 2px var(--primary-color);
        border-radius: var(--rs-radius-sm);
      }

      :host([disabled]) .main {
        opacity: 0.5;
        cursor: default;
      }

      .ic {
        width: 40px;
        height: 40px;
        border-radius: 50%;
        flex: none;
        display: grid;
        place-items: center;
        background: var(--rs-fill);
        color: var(--row-icon);
        --mdc-icon-size: 22px;
        border: none;
        padding: 0;
        margin: 0;
        font: inherit;
      }

      .ic.tinted {
        background: color-mix(in srgb, var(--row-icon) 14%, transparent);
      }

      .ic.plain {
        background: none;
        width: 40px;
        --mdc-icon-size: 24px;
      }

      button.ic {
        cursor: pointer;
        position: relative;
      }

      button.ic:hover {
        background: var(--rs-fill-strong);
      }

      button.ic:focus-visible {
        outline: 2px solid var(--primary-color);
        outline-offset: 1px;
      }

      @media (pointer: coarse) {
        button.ic::before {
          content: "";
          position: absolute;
          inset: -2px;
        }
      }

      .txt {
        flex: 1;
        min-width: 0;
      }

      .heading {
        font-size: var(--rs-font-md);
        color: var(--primary-text-color);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      :host([variant="danger"]) .heading {
        color: var(--rs-err);
      }

      :host([variant="primary"]) .heading {
        color: var(--primary-color);
        font-weight: 500;
      }

      .secondary {
        font-size: var(--rs-font-sm);
        color: var(--secondary-text-color);
        margin-top: 2px;
        line-height: 1.4;
        overflow-wrap: anywhere;
      }

      .secondary:empty {
        display: none;
      }

      .value {
        flex: none;
        max-width: 45%;
        font-size: var(--rs-font-md);
        color: var(--secondary-text-color);
        text-align: end;
        font-variant-numeric: tabular-nums;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .chev {
        flex: none;
        color: var(--secondary-text-color);
        --mdc-icon-size: 22px;
        display: inline-flex;
      }

      ::slotted([slot="end"]) {
        flex: none;
      }

      ha-switch {
        flex: none;
      }
    `,
  ];

  render() {
    const icon = this._renderIcon();
    const body = html`
      <span class="txt">
        <div class="heading">${this.heading}</div>
        <div class="secondary">${this.secondary}<slot name="secondary"></slot></div>
      </span>
      ${this.value ? html`<span class="value">${this.value}</span>` : nothing}
      ${
        this.chevron
          ? html`<ha-icon class="chev" icon="mdi:chevron-right" aria-hidden="true"></ha-icon>`
          : nothing
      }
    `;

    if (this.switch) {
      return html`<div class="row toggle">
        ${icon}
        <div class="main" @click=${this._onToggleRowClick}>${body}</div>
        <slot name="end"></slot>
        <ha-switch
          .checked=${this.checked}
          .disabled=${this.disabled}
          aria-label=${this.heading}
          @change=${this._onSwitchChange}
        ></ha-switch>
      </div>`;
    }

    let main;
    if (this.href && !this.disabled) {
      main = html`<a class="main" href=${this.href}>${body}</a>`;
    } else if (this.clickable) {
      main = html`<button
        type="button"
        class="main"
        ?disabled=${this.disabled}
        @click=${this._onRowClick}
      >
        ${body}
      </button>`;
    } else {
      main = html`<div class="main">${body}</div>`;
    }
    return html`<div class="row">${icon}${main}<slot name="end"></slot></div>`;
  }

  private _renderIcon() {
    if (!this.icon) return nothing;
    const cls = `ic ${this.plainIcon ? "plain" : ""} ${this.iconColor ? "tinted" : ""}`;
    const style = this.iconColor ? `--row-icon: ${this.iconColor}` : "";
    if (this.iconLabel) {
      return html`<rs-tooltip mode="label" .text=${this.iconLabel}>
        <button
          type="button"
          class=${cls}
          style=${style}
          aria-label=${`${this.iconLabel}: ${this.heading}`}
          @click=${this._onIconClick}
        >
          <ha-icon .icon=${this.icon}></ha-icon>
        </button>
      </rs-tooltip>`;
    }
    return html`<span class=${cls} style=${style} aria-hidden="true"
      ><ha-icon .icon=${this.icon}></ha-icon
    ></span>`;
  }

  /** Not composed: the component that renders the row listens on it directly. */
  private _fire(name: string, detail?: unknown) {
    this.dispatchEvent(new CustomEvent(name, { detail, bubbles: true }));
  }

  private _onRowClick(e: Event) {
    e.stopPropagation();
    if (!this.disabled) this._fire("row-click");
  }

  private _onIconClick(e: Event) {
    e.stopPropagation();
    this._fire("icon-click");
  }

  private _onToggleRowClick() {
    if (this.disabled) return;
    this._fire("toggle-changed", !this.checked);
  }

  private _onSwitchChange(e: Event) {
    e.stopPropagation();
    const sw = e.target as HTMLInputElement;
    const next = sw.checked;
    // The parent owns the state: hand the change up and show the bound value until it lands.
    sw.checked = this.checked;
    this._fire("toggle-changed", next);
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-list-row": RsListRow;
  }
}
