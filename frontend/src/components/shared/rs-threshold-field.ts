import { LitElement, html, css } from "lit";
import { customElement, property } from "lit/decorators.js";
import { inputStyles } from "../../styles/input-styles";
import "./rs-field";

@customElement("rs-threshold-field")
export class RsThresholdField extends LitElement {
  @property({ type: String }) public label = "";
  @property({ type: String }) public suffix = "";
  @property({ type: Number }) public value: number | undefined;
  @property({ type: Number }) public min: number | undefined;
  @property({ type: Number }) public max: number | undefined;
  @property({ type: Number }) public step: number | undefined;
  @property({ type: String }) public hint = "";

  static styles = [
    inputStyles,
    css`
      :host {
        display: block;
      }

      ha-textfield {
        display: block;
        width: 100%;
      }
    `,
  ];

  render() {
    return html`
      <rs-field .info=${this.hint}>
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
      </rs-field>
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
        }),
      );
    }
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-threshold-field": RsThresholdField;
  }
}
