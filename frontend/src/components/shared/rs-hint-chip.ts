import { LitElement, html, css } from "lit";
import { customElement, property } from "lit/decorators.js";
import { tokens } from "../../styles/tokens";
import "./rs-tooltip";

/**
 * Status hint: icon plus text, or icon only with the text as tooltip and accessible name.
 * `variant` colours warnings (`warn`), dangers (`error`) and a reached state (`ok`, e.g. "MPC
 * active"); everything else stays neutral.
 * `info`: an explanation the text chip shows as tooltip (hover, focus, tap).
 */
@customElement("rs-hint-chip")
export class RsHintChip extends LitElement {
  @property({ type: String }) public icon = "";
  @property({ type: String }) public text = "";
  @property({ type: String, reflect: true }) public variant: "default" | "warn" | "error" | "ok" =
    "default";
  @property({ type: Boolean, reflect: true, attribute: "icon-only" }) public iconOnly = false;
  /** Icon-only chips: a short text (e.g. "+2") in place of the icon. */
  @property({ type: String }) public short = "";
  @property({ type: String }) public info = "";

  static styles = [
    tokens,
    css`
      :host {
        display: inline-flex;
        min-width: 0;
        flex: 0 1 auto;
        --chip-color: var(--secondary-text-color);
      }

      :host([icon-only]) {
        flex: none;
      }

      :host([variant="warn"]) {
        --chip-color: var(--rs-warn);
      }

      :host([variant="error"]) {
        --chip-color: var(--rs-err);
      }

      :host([variant="ok"]) {
        --chip-color: var(--rs-ok);
      }

      .chip {
        height: 26px;
        box-sizing: border-box;
        display: inline-flex;
        align-items: center;
        gap: 5px;
        min-width: 0;
        max-width: 100%;
        padding: 0 10px 0 7px;
        border-radius: 13px;
        border: 1px solid var(--divider-color);
        background: color-mix(in srgb, var(--card-background-color, transparent) 85%, transparent);
        color: var(--primary-text-color);
        font: inherit;
        font-size: var(--rs-font-sm);
        line-height: 1;
        --mdc-icon-size: 15px;
      }

      :host([variant="warn"]) .chip,
      :host([variant="error"]) .chip,
      :host([variant="ok"]) .chip {
        border-color: color-mix(in srgb, var(--chip-color) 55%, transparent);
        background: color-mix(
          in srgb,
          var(--chip-color) 14%,
          var(--card-background-color, transparent)
        );
      }

      ha-icon {
        color: var(--chip-color);
        flex: none;
        display: inline-flex;
      }

      .text {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        min-width: 0;
      }

      .short {
        padding: 0 6px;
        font-size: 11px;
        font-weight: 500;
        color: var(--secondary-text-color);
        font-variant-numeric: tabular-nums;
      }

      button.chip.info {
        cursor: pointer;
        padding: 0 8px 0 7px;
      }

      .info-mark {
        --mdc-icon-size: 13px;
        color: var(--secondary-text-color);
        opacity: 0.8;
      }

      button.chip:not(.info) {
        min-width: 26px;
        padding: 0;
        justify-content: center;
        cursor: pointer;
        position: relative;
      }

      /* 26 px chip, 44 px tap target on touch */
      @media (pointer: coarse) {
        button.chip::before {
          content: "";
          position: absolute;
          inset: -9px;
        }
      }

      button.chip:focus-visible {
        outline: 2px solid var(--primary-color);
        outline-offset: 1px;
      }
    `,
  ];

  render() {
    if (this.iconOnly) {
      return html`<rs-tooltip .text=${this.text}>
        <button type="button" class="chip" aria-label=${this.text}>
          ${this.short ? html`<span class="short">${this.short}</span>` : html`<ha-icon .icon=${this.icon}></ha-icon>`}
        </button>
      </rs-tooltip>`;
    }
    if (this.info) {
      return html`<rs-tooltip .text=${this.info}>
        <button type="button" class="chip info" aria-label=${`${this.text}. ${this.info}`}>
          <ha-icon .icon=${this.icon}></ha-icon><span class="text">${this.text}</span
          ><ha-icon class="info-mark" icon="mdi:information-outline"></ha-icon>
        </button>
      </rs-tooltip>`;
    }
    return html`<span class="chip">
      <ha-icon .icon=${this.icon}></ha-icon><span class="text">${this.text}</span>
    </span>`;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-hint-chip": RsHintChip;
  }
}
