/**
 * rs-settings-control – Control settings card: mode, comfort weight, thresholds, prediction.
 */
import { LitElement, html, css } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";
import { toDisplay, toCelsius, tempUnit, tempStep, tempRange } from "../../utils/temperature";

@customElement("rs-settings-control")
export class RsSettingsControl extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: String }) public controlMode: "mpc" | "bangbang" = "mpc";
  @property({ type: Number }) public comfortWeight = 70;
  @property({ type: Number }) public outdoorCoolingMin = 16;
  @property({ type: Number }) public outdoorHeatingMax = 22;
  @property({ type: Boolean }) public predictionEnabled = true;

  private _fire(key: string, value: unknown) {
    this.dispatchEvent(new CustomEvent("setting-changed", {
      detail: { key, value },
      bubbles: true,
      composed: true,
    }));
  }

  render() {
    const l = this.hass.language;

    return html`
      <ha-card>
        <div class="card-header">
          <div class="header-title">
            <ha-icon icon="mdi:tune-variant"></ha-icon>
            <span>${localize("settings.control_title", l)}</span>
          </div>
        </div>
        <div class="card-content">
          <div class="settings-section">
            <p class="hint">${localize("settings.control_mode_hint", l)}</p>
            <div class="radio-group">
              <label class="radio-option" @click=${() => this._setControlMode("mpc")}>
                <ha-radio
                  name="control_mode"
                  .checked=${this.controlMode === "mpc"}
                ></ha-radio>
                <span>${localize("settings.control_mode_mpc", l)}</span>
              </label>
              <label class="radio-option" @click=${() => this._setControlMode("bangbang")}>
                <ha-radio
                  name="control_mode"
                  .checked=${this.controlMode === "bangbang"}
                ></ha-radio>
                <span>${localize("settings.control_mode_simple", l)}</span>
              </label>
            </div>
          </div>

          <div class="settings-section">
            <label class="section-label">${localize("settings.comfort_weight", l)}</label>
            <div class="slider-row">
              <span class="slider-label">${localize("settings.comfort_weight_efficiency", l)}</span>
              <input
                type="range"
                min="0"
                max="100"
                step="5"
                .value=${String(this.comfortWeight)}
                @change=${(e: Event) => {
                  const v = parseInt((e.target as HTMLInputElement).value, 10);
                  if (!isNaN(v) && v !== this.comfortWeight) this._fire("comfortWeight", v);
                }}
              />
              <span class="slider-label">${localize("settings.comfort_weight_comfort", l)}</span>
            </div>
          </div>

          <div class="settings-section">
            <p class="hint">${localize("settings.smart_control_hint", l)}</p>
            <div class="threshold-grid">
              <div class="threshold-field">
                <ha-textfield
                  .value=${String(toDisplay(this.outdoorCoolingMin, this.hass))}
                  .label=${localize("settings.outdoor_cooling_min", l)}
                  .suffix=${tempUnit(this.hass)}
                  type="number"
                  step=${tempStep(this.hass)}
                  min=${tempRange(-10, 40, this.hass).min}
                  max=${tempRange(-10, 40, this.hass).max}
                  @change=${(e: Event) => {
                    const v = parseFloat((e.target as HTMLInputElement).value);
                    if (!isNaN(v)) this._fire("outdoorCoolingMin", toCelsius(v, this.hass));
                  }}
                ></ha-textfield>
                <span class="field-hint">${localize("settings.outdoor_cooling_min_hint", l)}</span>
              </div>
              <div class="threshold-field">
                <ha-textfield
                  .value=${String(toDisplay(this.outdoorHeatingMax, this.hass))}
                  .label=${localize("settings.outdoor_heating_max", l)}
                  .suffix=${tempUnit(this.hass)}
                  type="number"
                  step=${tempStep(this.hass)}
                  min=${tempRange(0, 40, this.hass).min}
                  max=${tempRange(0, 40, this.hass).max}
                  @change=${(e: Event) => {
                    const v = parseFloat((e.target as HTMLInputElement).value);
                    if (!isNaN(v)) this._fire("outdoorHeatingMax", toCelsius(v, this.hass));
                  }}
                ></ha-textfield>
                <span class="field-hint">${localize("settings.outdoor_heating_max_hint", l)}</span>
              </div>
            </div>
          </div>

          <div class="settings-section">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">${localize("settings.prediction_enabled", l)}</span>
                <span class="toggle-hint">${localize("settings.prediction_enabled_hint", l)}</span>
              </div>
              <ha-switch
                .checked=${this.predictionEnabled}
                @change=${(e: Event) => this._fire("predictionEnabled", (e.target as HTMLInputElement).checked)}
              ></ha-switch>
            </div>
          </div>
        </div>
      </ha-card>
    `;
  }

  private _setControlMode(mode: "mpc" | "bangbang") {
    if (this.controlMode === mode) return;
    this._fire("controlMode", mode);
  }

  static styles = css`
    :host { display: block; }

    .card-header {
      display: flex; justify-content: space-between; align-items: center;
      padding: 16px 16px 0; font-size: 16px; font-weight: 500;
    }
    .header-title { display: flex; align-items: center; gap: 8px; --mdc-icon-size: 20px; }
    .card-content { padding: 8px 16px 16px; }

    .settings-section { padding: 16px 0; border-top: 1px solid var(--divider-color); }
    .settings-section:first-child { border-top: none; }

    .hint { color: var(--secondary-text-color); font-size: 13px; margin: 0 0 12px; }
    .section-label { display: block; margin-bottom: 8px; font-size: 14px; color: var(--primary-text-color); }

    .toggle-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
    .toggle-text { display: flex; flex-direction: column; gap: 4px; flex: 1; }
    .toggle-label { font-size: 14px; font-weight: 500; color: var(--primary-text-color); }
    .toggle-hint { font-size: 13px; color: var(--secondary-text-color); line-height: 1.4; }

    .radio-group { display: flex; flex-direction: column; gap: 8px; }
    .radio-option { display: flex; align-items: center; gap: 8px; cursor: pointer; }

    .slider-row { display: flex; align-items: center; gap: 8px; }
    .slider-row input[type="range"] { flex: 1; accent-color: var(--primary-color); }
    .slider-label { font-size: 12px; color: var(--secondary-text-color); white-space: nowrap; }

    .threshold-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .threshold-field { display: flex; flex-direction: column; gap: 4px; }
    .threshold-field ha-textfield { width: 100%; }
    .field-hint { color: var(--secondary-text-color); font-size: 12px; }

    @media (max-width: 600px) {
      .threshold-grid { grid-template-columns: 1fr; }
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-control": RsSettingsControl;
  }
}
