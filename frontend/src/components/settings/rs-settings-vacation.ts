/**
 * rs-settings-vacation – Vacation mode settings.
 */
import { html, nothing } from "lit";
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
      <div class="toggle-row">
        <div class="toggle-text">
          <span class="toggle-label">${localize("vacation.title", l)}</span>
          <span class="toggle-hint">${localize("vacation.hint", l)}</span>
        </div>
        <ha-switch
          .checked=${this.vacationActive}
          @change=${(e: Event) => {
            const active = (e.target as HTMLInputElement).checked;
            this._fire("vacationActive", active);
            if (!active) this._fire("vacationUntil", "");
          }}
        ></ha-switch>
      </div>

      ${this.vacationActive
        ? html`
            <div class="threshold-grid" style="margin-top: 12px">
              <div class="threshold-field">
                <ha-textfield
                  .value=${this.vacationUntil}
                  .label=${localize("vacation.end_date", l)}
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
          `
        : nothing}
    `;
  }

  static styles = [RsSettingsBase.settingsBaseStyles];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-vacation": RsSettingsVacation;
  }
}
