/**
 * rs-settings-control – Control settings: mode, comfort weight, thresholds, prediction.
 */
import { html, css, nothing } from "lit";
import { RsSettingsBase } from "./rs-settings-base";
import "../shared/rs-number-field";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";
import { preheatLeadHours } from "../../utils/constants";
import { formatHours } from "../../utils/format";
import "../shared/rs-segmented";

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
  /** Slider position while dragging, so the pre-heat line follows before the value is saved. */
  @state() private _dragWeight: number | null = null;

  render() {
    const l = this.hass.language;

    return html`
      <div class="settings-section first">
        <span class="field-label">${localize("settings.control_mode", l)}</span>
        <rs-segmented
          .label=${localize("settings.control_mode", l)}
          .options=${[
            {
              value: "mpc",
              label: localize("settings.control_mode_mpc", l),
              icon: "mdi:brain",
            },
            {
              value: "bangbang",
              label: localize("settings.control_mode_simple", l),
              icon: "mdi:toggle-switch-outline",
            },
          ]}
          .value=${this.controlMode}
          @value-changed=${(e: CustomEvent<{ value: string }>) =>
            this._setControlMode(e.detail.value as "mpc" | "bangbang")}
        ></rs-segmented>
        <p class="hint">${localize("settings.control_mode_hint", l)}</p>
      </div>

      <div class="settings-section">
        <span class="field-label">${localize("settings.comfort_weight", l)}</span>
        <div class="slider-row">
          <span class="slider-label">${localize("settings.comfort_weight_efficiency", l)}</span>
          <input
            type="range"
            aria-label=${localize("settings.comfort_weight", l)}
            min="0"
            max="100"
            step="5"
            .value=${String(this.comfortWeight)}
            @input=${(e: Event) => {
              const v = parseInt((e.target as HTMLInputElement).value, 10);
              this._dragWeight = isNaN(v) ? null : v;
            }}
            @change=${(e: Event) => {
              const v = parseInt((e.target as HTMLInputElement).value, 10);
              this._dragWeight = null;
              if (!isNaN(v) && v !== this.comfortWeight) this._fire("comfortWeight", v);
            }}
          />
          <span class="slider-label">${localize("settings.comfort_weight_comfort", l)}</span>
        </div>
        ${this.controlMode === "mpc" ? html`<p class="preheat-lead">${this._preheatLeadText(l)}</p>` : nothing}
        <p class="hint helper-text">${localize("settings.comfort_weight_hint", l)}</p>
        <a class="helper-link" href=${CONTROL_DOCS_URL} target="_blank" rel="noreferrer">
          ${localize("common.learn_more", l)}
        </a>
      </div>

      <div class="settings-section">
        <p class="hint">${localize("settings.smart_control_hint", l)}</p>
        <div class="threshold-grid">
          <rs-number-field
            .hass=${this.hass}
            kind="temperature"
            .label=${localize("settings.outdoor_cooling_min", l)}
            .hint=${localize("settings.outdoor_cooling_min_hint", l)}
            .min=${-10}
            .max=${40}
            .value=${this.outdoorCoolingMin}
            @value-changed=${(e: CustomEvent<{ value: number }>) =>
              this._fire("outdoorCoolingMin", e.detail.value)}
          ></rs-number-field>
          <rs-number-field
            .hass=${this.hass}
            kind="temperature"
            .label=${localize("settings.outdoor_heating_max", l)}
            .hint=${localize("settings.outdoor_heating_max_hint", l)}
            .min=${0}
            .max=${40}
            .value=${this.outdoorHeatingMax}
            @value-changed=${(e: CustomEvent<{ value: number }>) =>
              this._fire("outdoorHeatingMax", e.detail.value)}
          ></rs-number-field>
        </div>
      </div>

      <div class="settings-section">
        <rs-list-row
          switch
          wrap
          .heading=${localize("settings.prediction_enabled", l)}
          .secondary=${localize("settings.prediction_enabled_hint", l)}
          .checked=${this.predictionEnabled}
          @toggle-changed=${(e: CustomEvent<boolean>) => this._fire("predictionEnabled", e.detail)}
        ></rs-list-row>
      </div>

      <div class="settings-section">
        <span class="field-label">${localize("schedule.off_action_label", l)}</span>
        <rs-segmented
          wrap
          .label=${localize("schedule.off_action_label", l)}
          .options=${[
            { value: "eco", label: localize("schedule.off_action_eco", l), icon: "mdi:leaf" },
            { value: "off", label: localize("schedule.off_action_off", l), icon: "mdi:power" },
          ]}
          .value=${this.scheduleOffAction}
          @value-changed=${(e: CustomEvent<{ value: string }>) => {
            const val = e.detail.value as "eco" | "off";
            if (val && val !== this.scheduleOffAction) this._fire("scheduleOffAction", val);
          }}
        ></rs-segmented>
      </div>
    `;
  }

  private _preheatLeadText(l: string): string {
    const hours = preheatLeadHours(this._dragWeight ?? this.comfortWeight);
    if (hours <= 0) return localize("settings.preheat_lead_none", l);
    return localize("settings.preheat_lead", l, {
      time: formatHours(hours, l),
    });
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
        line-height: 1.5;
        margin: var(--rs-space-3) 0 0;
      }
      .settings-section > .hint:first-child {
        margin: 0 0 var(--rs-space-3);
      }
      .helper-text {
        margin: 10px 0 0;
      }
      .preheat-lead {
        margin: 10px 0 0;
        font-size: 13px;
        font-weight: 500;
        color: var(--primary-text-color);
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
