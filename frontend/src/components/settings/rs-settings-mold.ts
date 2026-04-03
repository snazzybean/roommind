/**
 * rs-settings-mold – Mold risk detection & prevention settings.
 */
import { html, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import { RsSettingsBase } from "./rs-settings-base";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";
import { getSelectValue } from "../../utils/events";
import { tempUnit, toDisplayDelta } from "../../utils/temperature";

@customElement("rs-settings-mold")
export class RsSettingsMold extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public moldDetectionEnabled = false;
  @property({ type: Number }) public moldHumidityThreshold = 70;
  @property({ type: Number }) public moldSustainedMinutes = 30;
  @property({ type: Boolean }) public moldPreventionEnabled = false;
  @property({ type: String }) public moldPreventionIntensity: "light" | "medium" | "strong" =
    "medium";

  render() {
    const l = this.hass.language;

    return html`
      <!-- Detection section -->
      <div class="settings-section first">
        <div class="toggle-row">
          <div class="toggle-text">
            <span class="toggle-label">
              <ha-icon
                icon="mdi:bell-alert"
                style="--mdc-icon-size: 18px; vertical-align: middle; margin-right: 4px"
              ></ha-icon>
              ${localize("mold.detection", l)}
            </span>
            <span class="toggle-hint">${localize("mold.detection_desc", l)}</span>
          </div>
          <ha-switch
            .checked=${this.moldDetectionEnabled}
            @change=${(e: Event) =>
              this._fire("moldDetectionEnabled", (e.target as HTMLInputElement).checked)}
          ></ha-switch>
        </div>
        ${this.moldDetectionEnabled
          ? html`
              <div class="threshold-grid" style="margin-top: 12px">
                <div class="threshold-field">
                  <ha-textfield
                    .value=${String(this.moldHumidityThreshold)}
                    .label=${localize("mold.threshold", l)}
                    .suffix=${"%"}
                    type="number"
                    step="1"
                    min="50"
                    max="90"
                    @change=${(e: Event) => {
                      const v = parseFloat((e.target as HTMLInputElement).value);
                      if (!isNaN(v) && v >= 50 && v <= 90) this._fire("moldHumidityThreshold", v);
                    }}
                  ></ha-textfield>
                  <span class="field-hint">${localize("mold.threshold_hint", l)}</span>
                </div>
                <div class="threshold-field">
                  <ha-textfield
                    .value=${String(this.moldSustainedMinutes)}
                    .label=${localize("mold.sustained", l)}
                    .suffix=${"min"}
                    type="number"
                    step="5"
                    min="5"
                    max="120"
                    @change=${(e: Event) => {
                      const v = parseInt((e.target as HTMLInputElement).value, 10);
                      if (!isNaN(v) && v >= 5 && v <= 120) this._fire("moldSustainedMinutes", v);
                    }}
                  ></ha-textfield>
                  <span class="field-hint">${localize("mold.sustained_hint", l)}</span>
                </div>
              </div>
            `
          : nothing}
      </div>

      <!-- Prevention section -->
      <div class="settings-section">
        <div class="toggle-row">
          <div class="toggle-text">
            <span class="toggle-label">
              <ha-icon
                icon="mdi:shield-check"
                style="--mdc-icon-size: 18px; vertical-align: middle; margin-right: 4px"
              ></ha-icon>
              ${localize("mold.prevention", l)}
            </span>
            <span class="toggle-hint">${localize("mold.prevention_desc", l)}</span>
          </div>
          <ha-switch
            .checked=${this.moldPreventionEnabled}
            @change=${(e: Event) =>
              this._fire("moldPreventionEnabled", (e.target as HTMLInputElement).checked)}
          ></ha-switch>
        </div>
        ${this.moldPreventionEnabled
          ? html`
              <div style="margin-top: 12px; display: flex; flex-direction: column; gap: 4px;">
                <ha-select
                  style="width: 100%;"
                  .value=${this.moldPreventionIntensity}
                  .label=${localize("mold.intensity", l)}
                  .options=${[
                    {
                      value: "light",
                      label: localize("mold.intensity_light", l, {
                        delta: String(toDisplayDelta(1, this.hass)),
                        unit: tempUnit(this.hass),
                      }),
                    },
                    {
                      value: "medium",
                      label: localize("mold.intensity_medium", l, {
                        delta: String(toDisplayDelta(2, this.hass)),
                        unit: tempUnit(this.hass),
                      }),
                    },
                    {
                      value: "strong",
                      label: localize("mold.intensity_strong", l, {
                        delta: String(toDisplayDelta(3, this.hass)),
                        unit: tempUnit(this.hass),
                      }),
                    },
                  ]}
                  fixedMenuPosition
                  @selected=${(e: Event) => {
                    const v = getSelectValue(e) as "light" | "medium" | "strong";
                    if (v && v !== this.moldPreventionIntensity)
                      this._fire("moldPreventionIntensity", v);
                  }}
                  @closed=${(e: Event) => e.stopPropagation()}
                >
                  <ha-list-item value="light"
                    >${localize("mold.intensity_light", l, {
                      delta: String(toDisplayDelta(1, this.hass)),
                      unit: tempUnit(this.hass),
                    })}</ha-list-item
                  >
                  <ha-list-item value="medium"
                    >${localize("mold.intensity_medium", l, {
                      delta: String(toDisplayDelta(2, this.hass)),
                      unit: tempUnit(this.hass),
                    })}</ha-list-item
                  >
                  <ha-list-item value="strong"
                    >${localize("mold.intensity_strong", l, {
                      delta: String(toDisplayDelta(3, this.hass)),
                      unit: tempUnit(this.hass),
                    })}</ha-list-item
                  >
                </ha-select>
                <span class="field-hint">${localize("mold.intensity_hint", l)}</span>
              </div>
            `
          : nothing}
      </div>
    `;
  }

  static styles = [RsSettingsBase.settingsBaseStyles];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-mold": RsSettingsMold;
  }
}
