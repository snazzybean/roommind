/**
 * rs-settings-control – Control settings: mode, comfort weight, thresholds, prediction.
 */
import { html, css } from "lit";
import { RsSettingsBase } from "./rs-settings-base";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";
import { getSelectValue } from "../../utils/events";
import { toDisplay, toCelsius, tempUnit, tempStep, tempRange } from "../../utils/temperature";

const CONTROL_DOCS_URL =
  "https://github.com/snazzybean/roommind/blob/main/docs/control-and-devices.md";

@customElement("rs-settings-control")
export class RsSettingsControl extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: String }) public controlMode: "mpc" | "bangbang" = "mpc";
  @property({ type: Number }) public comfortWeight = 70;
  @property({ type: Number }) public outdoorCoolingMin = 16;
  @property({ type: Number }) public outdoorHeatingMax = 22;
  @property({ type: Boolean }) public predictionEnabled = true;
  @property({ type: String }) public scheduleOffAction: "eco" | "off" = "eco";

  render() {
    const l = this.hass.language;

    return html`
      <div class="settings-section first">
        <p class="hint">${localize("settings.control_mode_hint", l)}</p>
        <div class="radio-group">
          <label class="radio-option" @click=${() => this._setControlMode("mpc")}>
            <ha-radio name="control_mode" .checked=${this.controlMode === "mpc"}></ha-radio>
            <span>${localize("settings.control_mode_mpc", l)}</span>
          </label>
          <label class="radio-option" @click=${() => this._setControlMode("bangbang")}>
            <ha-radio name="control_mode" .checked=${this.controlMode === "bangbang"}></ha-radio>
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
        <p class="hint helper-text">${localize("settings.comfort_weight_hint", l)}</p>
        <a class="helper-link" href=${CONTROL_DOCS_URL} target="_blank" rel="noreferrer">
          ${localize("common.learn_more", l)}
        </a>
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
            @change=${(e: Event) =>
              this._fire("predictionEnabled", (e.target as HTMLInputElement).checked)}
          ></ha-switch>
        </div>
      </div>

      <div class="settings-section">
        <ha-select
          .label=${localize("schedule.off_action_label", l)}
          .value=${this.scheduleOffAction}
          .options=${[
            { value: "eco", label: localize("schedule.off_action_eco", l) },
            { value: "off", label: localize("schedule.off_action_off", l) },
          ]}
          fixedMenuPosition
          @selected=${(e: Event) => {
            const val = getSelectValue(e) as "eco" | "off";
            if (val && val !== this.scheduleOffAction) this._fire("scheduleOffAction", val);
          }}
          @closed=${(e: Event) => e.stopPropagation()}
        >
          <ha-list-item value="eco">${localize("schedule.off_action_eco", l)}</ha-list-item>
          <ha-list-item value="off">${localize("schedule.off_action_off", l)}</ha-list-item>
        </ha-select>
      </div>
    `;
  }

  private _setControlMode(mode: "mpc" | "bangbang") {
    if (this.controlMode === mode) return;
    this._fire("controlMode", mode);
  }

  static styles = [
    RsSettingsBase.settingsBaseStyles,
    css`
      .hint {
        color: var(--secondary-text-color);
        font-size: 13px;
        margin: 0 0 12px;
      }
      .helper-text {
        margin: 10px 0 0;
      }
      .section-label {
        display: block;
        margin-bottom: 8px;
        font-size: 14px;
        color: var(--primary-text-color);
      }

      .radio-group {
        display: flex;
        flex-direction: column;
        gap: 8px;
      }
      .radio-option {
        display: flex;
        align-items: center;
        gap: 8px;
        cursor: pointer;
      }

      .slider-row {
        display: flex;
        align-items: center;
        gap: 8px;
      }
      .slider-row input[type="range"] {
        flex: 1;
        accent-color: var(--primary-color);
      }
      .slider-label {
        font-size: 12px;
        color: var(--secondary-text-color);
        white-space: nowrap;
      }
      .helper-link {
        display: inline-block;
        margin-top: 6px;
        font-size: 12px;
        color: var(--primary-color);
        text-decoration: none;
      }
      .helper-link:hover {
        text-decoration: underline;
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-control": RsSettingsControl;
  }
}
