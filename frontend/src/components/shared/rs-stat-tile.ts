import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import { tokens } from "../../styles/tokens";
import "./rs-info-icon";

/**
 * Key figure tile: icon and label on top, the value, an optional sub line and a mini visual
 * (`visual` slot) at the bottom. `info` opens in the shared info tooltip; extra lines for it
 * go into the `info` slot. `pending` dims the value ("—" until there is enough data).
 * `tone` colours the icon only.
 */
@customElement("rs-stat-tile")
export class RsStatTile extends LitElement {
  @property({ type: String }) public icon = "";
  @property({ type: String }) public label = "";
  @property({ type: String }) public value = "";
  @property({ type: String }) public sub = "";
  @property({ type: String }) public info = "";
  @property({ type: Boolean, reflect: true }) public pending = false;
  @property({ type: String, reflect: true }) public tone: "default" | "heat" | "cool" | "ok" =
    "default";

  static styles = [
    tokens,
    css`
      :host {
        display: flex;
        min-width: 0;
        --tile-icon: var(--secondary-text-color);
      }

      :host([tone="heat"]) {
        --tile-icon: var(--rs-heat);
      }
      :host([tone="cool"]) {
        --tile-icon: var(--rs-cool);
      }
      :host([tone="ok"]) {
        --tile-icon: var(--rs-ok);
      }

      .tile {
        flex: 1;
        min-width: 0;
        display: flex;
        flex-direction: column;
        box-sizing: border-box;
        padding: var(--rs-space-3) 14px;
        border: 1px solid var(--rs-border);
        border-radius: var(--rs-radius);
      }

      .head {
        display: flex;
        align-items: center;
        gap: 6px;
        min-height: 24px;
        font-size: var(--rs-font-sm);
        color: var(--secondary-text-color);
      }

      .head ha-icon {
        --mdc-icon-size: 16px;
        color: var(--tile-icon);
        flex: none;
      }

      .label {
        flex: 1;
        min-width: 0;
        overflow-wrap: break-word;
        hyphens: auto;
      }

      rs-info-icon {
        flex: none;
        margin: -4px -6px -4px 0;
      }

      .value {
        margin-top: var(--rs-space-1);
        font-size: 22px;
        line-height: 28px;
        font-variant-numeric: tabular-nums;
        overflow-wrap: break-word;
        color: var(--primary-text-color);
      }

      :host([pending]) .value {
        color: var(--disabled-text-color, var(--secondary-text-color));
        opacity: 0.6;
      }

      .sub {
        margin-top: 2px;
        font-size: var(--rs-font-sm);
        line-height: 1.4;
        color: var(--secondary-text-color);
        font-variant-numeric: tabular-nums;
        overflow-wrap: anywhere;
      }

      .visual {
        margin-top: auto;
        padding-top: var(--rs-space-2);
      }

      .visual:not(.filled) {
        display: none;
      }

      ::slotted([slot="info"]) {
        display: block;
        margin-top: 6px;
      }
    `,
  ];

  render() {
    return html`<div class="tile">
      <div class="head">
        ${this.icon ? html`<ha-icon .icon=${this.icon} aria-hidden="true"></ha-icon>` : nothing}
        <span class="label">${this.label}</span>
        ${
          this.info
            ? html`<rs-info-icon>${this.info}<slot name="info"></slot></rs-info-icon>`
            : nothing
        }
      </div>
      <div class="value">${this.value}</div>
      ${this.sub ? html`<div class="sub">${this.sub}</div>` : nothing}
      <div class="visual"><slot name="visual" @slotchange=${this._onVisualSlot}></slot></div>
    </div>`;
  }

  private _onVisualSlot(e: Event) {
    const slot = e.target as HTMLSlotElement;
    slot.parentElement?.classList.toggle("filled", slot.assignedNodes().length > 0);
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-stat-tile": RsStatTile;
  }
}
