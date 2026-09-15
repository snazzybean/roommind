import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import { inputStyles } from "../../styles/input-styles";
import type { HomeAssistant } from "../../types";

@customElement("rs-entity-picker-field")
export class RsEntityPickerField extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: String }) public label = "";
  @property({ type: String }) public value = "";
  @property({ type: Array }) public includeDomains: string[] = [];
  @property({ type: String }) public currentValue = "";
  @property({ type: String }) public currentValueLabel = "";

  static styles = [
    inputStyles,
    css`
      :host {
        display: block;
      }

      ha-entity-picker {
        width: 100%;
      }

      .current-value {
        font-size: 13px;
        color: var(--secondary-text-color);
        margin-top: 4px;
      }
    `,
  ];

  render() {
    return html`
      <ha-entity-picker
        .hass=${this.hass}
        .label=${this.label}
        .value=${this.value}
        .includeDomains=${this.includeDomains}
        allow-custom-entity
        @value-changed=${this._onValueChanged}
      ></ha-entity-picker>
      ${
        this.currentValue
          ? html`<div class="current-value">
              ${this.currentValueLabel ? html`${this.currentValueLabel}: ` : nothing}${
                this.currentValue
              }
            </div>`
          : nothing
      }
    `;
  }

  private _onValueChanged(e: CustomEvent) {
    e.stopPropagation();
    this.dispatchEvent(
      new CustomEvent("value-changed", {
        detail: e.detail.value ?? "",
        bubbles: true,
        composed: true,
      }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-entity-picker-field": RsEntityPickerField;
  }
}
