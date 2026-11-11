/**
 * rs-settings-valve – Valve protection settings.
 */
import { html, nothing } from "lit";
import { RsSettingsBase } from "./rs-settings-base";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";

@customElement("rs-settings-valve")
export class RsSettingsValve extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public valveProtectionEnabled = false;
  @property({ type: Number }) public valveProtectionInterval = 7;

  render() {
    const l = this.hass.language;

    return html`
      <div class="settings-section first">
        <rs-list-row
          switch
          wrap
          .heading=${localize("valve_protection.title", l)}
          .secondary=${localize("valve_protection.hint", l)}
          .checked=${this.valveProtectionEnabled}
          @toggle-changed=${(e: CustomEvent<boolean>) =>
            this._fire("valveProtectionEnabled", e.detail)}
        ></rs-list-row>
      </div>

      ${
        this.valveProtectionEnabled
          ? html`
              <div class="settings-section">
                <div class="threshold-grid">
                  <div class="threshold-field">
                    <ha-textfield
                      .value=${String(this.valveProtectionInterval)}
                      .label=${localize("valve_protection.interval_label", l)}
                      .suffix=${localize("valve_protection.interval_suffix", l)}
                      type="number"
                      step="1"
                      min="1"
                      max="90"
                      @change=${(e: Event) => {
                        const v = parseInt((e.target as HTMLInputElement).value, 10);
                        if (!isNaN(v) && v >= 1 && v <= 90)
                          this._fire("valveProtectionInterval", v);
                      }}
                    ></ha-textfield>
                    <span class="field-hint">${localize("valve_protection.interval_hint", l)}</span>
                  </div>
                </div>
              </div>
            `
          : nothing
      }
    `;
  }

  static styles = [RsSettingsBase.settingsBaseStyles];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-valve": RsSettingsValve;
  }
}
