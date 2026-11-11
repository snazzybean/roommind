import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import { tokens } from "../../styles/tokens";
import "./rs-info-icon";

/**
 * One setting in a form. With `label`: a label line with the info icon above the control
 * (segmented choices and other controls without their own label). Without: the control with
 * the info icon beside it (selects and text fields carry a floating label). `hint` adds a
 * short line under the control. The control goes into the default slot.
 */
@customElement("rs-field")
export class RsField extends LitElement {
  @property({ type: String }) public label = "";
  @property({ type: String }) public info = "";
  @property({ type: String }) public hint = "";

  static styles = [
    tokens,
    css`
      :host {
        display: block;
        min-width: 0;
      }

      .head {
        display: flex;
        align-items: center;
        gap: var(--rs-space-1);
        /* keeps the info icon's touch area off the control below */
        margin-bottom: var(--rs-space-3);
        font-size: var(--rs-font-md);
        color: var(--primary-text-color);
      }

      /* 12 px keep the info icon's touch area off the control beside it */
      .inline {
        display: flex;
        align-items: center;
        gap: var(--rs-space-3);
      }

      .control {
        flex: 1;
        min-width: 0;
      }

      rs-info-icon {
        flex: none;
      }

      .hint {
        margin-top: var(--rs-space-1);
        font-size: var(--rs-font-sm);
        line-height: 1.4;
        color: var(--secondary-text-color);
      }
    `,
  ];

  render() {
    const info = this.info ? html`<rs-info-icon .text=${this.info}></rs-info-icon>` : nothing;
    const hint = this.hint ? html`<div class="hint">${this.hint}</div>` : nothing;
    if (this.label) {
      return html`<div class="head"><span>${this.label}</span>${info}</div>
        <slot></slot>
        ${hint}`;
    }
    return html`<div class="inline">
        <div class="control"><slot></slot></div>
        ${info}
      </div>
      ${hint}`;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-field": RsField;
  }
}
