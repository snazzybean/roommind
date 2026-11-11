/**
 * rs-settings-vacation – Vacation mode settings.
 */
import { css, html, nothing } from "lit";
import { RsSettingsBase } from "./rs-settings-base";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";
import { toDisplay, toCelsius, tempUnit, tempStep, tempRange } from "../../utils/temperature";

@customElement("rs-settings-vacation")
export class RsSettingsVacation extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public vacationActive = false;
  @property({ type: Number }) public vacationTemp = 15;
  @property({ type: String }) public vacationUntil = "";

  render() {
    const l = this.hass.language;

    return html`
      <div class="settings-section first">
        <rs-list-row
          switch
          wrap
          .heading=${localize("vacation.title", l)}
          .secondary=${localize("vacation.hint", l)}
          .checked=${this.vacationActive}
          @toggle-changed=${(e: CustomEvent<boolean>) => {
            const active = e.detail;
            this._fire("vacationActive", active);
            if (!active) this._fire("vacationUntil", "");
          }}
        ></rs-list-row>
      </div>

      ${
        this.vacationActive
          ? html`
              <div class="settings-section">
                <div class="threshold-grid" style="align-items: end">
                  <div class="threshold-field">
                    <label class="field-label" for="vacation-until"
                      >${localize("vacation.end_date", l)}</label
                    >
                    <ha-textfield
                      id="vacation-until"
                      .value=${this.vacationUntil}
                      aria-label=${localize("vacation.end_date", l)}
                      type="datetime-local"
                      @change=${(e: Event) =>
                        this._fire("vacationUntil", (e.target as HTMLInputElement).value)}
                    ></ha-textfield>
                  </div>
                  <div class="threshold-field">
                    <ha-textfield
                      .value=${String(toDisplay(this.vacationTemp, this.hass))}
                      .label=${localize("vacation.setback_temp", l)}
                      .suffix=${tempUnit(this.hass)}
                      type="number"
                      step=${tempStep(this.hass)}
                      min=${tempRange(5, 25, this.hass).min}
                      max=${tempRange(5, 25, this.hass).max}
                      @change=${(e: Event) => {
                        const v = parseFloat((e.target as HTMLInputElement).value);
                        if (!isNaN(v)) this._fire("vacationTemp", toCelsius(v, this.hass));
                      }}
                    ></ha-textfield>
                  </div>
                </div>
              </div>
            `
          : nothing
      }
    `;
  }

  static styles = [
    RsSettingsBase.settingsBaseStyles,
    css`
      .threshold-field .field-label {
        margin: 0;
        color: var(--secondary-text-color);
        font-size: var(--rs-font-sm);
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-vacation": RsSettingsVacation;
  }
}
