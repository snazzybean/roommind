/**
 * rs-settings-general – General settings: climate control, display options.
 */
import { html, nothing } from "lit";
import { RsSettingsBase } from "./rs-settings-base";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";
import { hasFloors } from "../../utils/dashboard";
import "../shared/rs-info-icon";

@customElement("rs-settings-general")
export class RsSettingsGeneral extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public groupByFloor = false;
  @property({ type: Boolean }) public climateControlActive = true;

  render() {
    const l = this.hass.language;
    return html`
      <div class="settings-section first">
        <rs-list-row
          switch
          wrap
          .heading=${localize("settings.climate_control_active", l)}
          .checked=${this.climateControlActive}
          @toggle-changed=${(e: CustomEvent<boolean>) =>
            this._fire("climateControlActive", e.detail)}
        >
          <rs-info-icon
            slot="end"
            .text=${localize("settings.climate_control_hint", l)}
          ></rs-info-icon>
        </rs-list-row>
      </div>
      ${
        hasFloors(this.hass)
          ? html`<div class="settings-section">
              <rs-list-row
                switch
                wrap
                .heading=${localize("settings.group_by_floor", l)}
                .checked=${this.groupByFloor}
                @toggle-changed=${(e: CustomEvent<boolean>) => this._fire("groupByFloor", e.detail)}
              ></rs-list-row>
            </div>`
          : nothing
      }
    `;
  }

  static styles = [RsSettingsBase.settingsBaseStyles];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-general": RsSettingsGeneral;
  }
}
