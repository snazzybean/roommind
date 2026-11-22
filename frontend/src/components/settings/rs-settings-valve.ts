/**
 * rs-settings-valve – Valve protection settings.
 */
import { html, nothing } from "lit";
import { RsSettingsBase } from "./rs-settings-base";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";
import "../shared/rs-info-icon";
import { numberRow } from "../shared/number-row";

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
          .checked=${this.valveProtectionEnabled}
          @toggle-changed=${(e: CustomEvent<boolean>) =>
            this._fire("valveProtectionEnabled", e.detail)}
        >
          <rs-info-icon slot="end" .text=${localize("valve_protection.hint", l)}></rs-info-icon>
        </rs-list-row>
      </div>

      ${
        this.valveProtectionEnabled
          ? html`
              <div class="settings-section">
                ${numberRow({
                  hass: this.hass,
                  label: localize("valve_protection.interval_label", l),
                  info: localize("valve_protection.interval_hint", l),
                  unit: localize("valve_protection.interval_suffix", l),
                  min: 1,
                  max: 90,
                  value: this.valveProtectionInterval,
                  onChange: (v) => this._fire("valveProtectionInterval", v),
                })}
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
