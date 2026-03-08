import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";

@customElement("rs-threshold-field")
export class RsThresholdField extends LitElement {
  @property({ type: String }) public label = "";
  @property({ type: String }) public suffix = "";
  @property({ type: Number }) public value: number | undefined;
  @property({ type: Number }) public min: number | undefined;
  @property({ type: Number }) public max: number | undefined;
  @property({ type: Number }) public step: number | undefined;
  @property({ type: String }) public hint = "";

  static styles = css`
    :host {
      display: block;
    }

    ha-textfield {
      display: block;
      width: 100%;
    }

    .hint {
      font-size: 13px;
      color: var(--secondary-text-color);
      margin-top: 4px;
    }
  `;

  render() {
    return html`
      <ha-textfield
        .label=${this.label}
        .suffix=${this.suffix}
        .value=${this.value != null ? String(this.value) : ""}
        .min=${this.min != null ? String(this.min) : ""}
        .max=${this.max != null ? String(this.max) : ""}
        .step=${this.step != null ? String(this.step) : ""}
        type="number"
        @input=${this._onInput}
      ></ha-textfield>
      ${this.hint
        ? html`<div class="hint">${this.hint}</div>`
        : nothing}
    `;
  }

  private _onInput(e: Event) {
    const val = parseFloat((e.target as HTMLInputElement).value);
    if (!isNaN(val)) {
      this.dispatchEvent(
        new CustomEvent("value-changed", {
          detail: val,
          bubbles: true,
          composed: true,
        })
      );
    }
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-threshold-field": RsThresholdField;
  }
}
