/**
 * rs-settings-sensors – Sensors & data sources settings.
 */
import { html, css, nothing } from "lit";
import { RsSettingsBase } from "./rs-settings-base";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant, HassEntity } from "../../types";
import { localize } from "../../utils/localize";
import { tempUnit } from "../../utils/temperature";

@customElement("rs-settings-sensors")
export class RsSettingsSensors extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: String }) public outdoorTempSensor = "";
  @property({ type: String }) public outdoorHumiditySensor = "";
  @property({ type: String }) public weatherEntity = "";

  private _filterTemperature = (entity: HassEntity): boolean => {
    return entity.attributes?.device_class === "temperature";
  };

  private _filterHumidity = (entity: HassEntity): boolean => {
    return entity.attributes?.device_class === "humidity";
  };

  private _getSensorValue(entityId: string): number | null {
    const state = this.hass.states[entityId];
    if (!state || state.state === "unavailable" || state.state === "unknown") return null;
    const val = parseFloat(state.state);
    return isNaN(val) ? null : Math.round(val * 10) / 10;
  }

  render() {
    const l = this.hass.language;
    const outdoorTemp = this.outdoorTempSensor
      ? this._getSensorValue(this.outdoorTempSensor)
      : null;
    const outdoorHumidity = this.outdoorHumiditySensor
      ? this._getSensorValue(this.outdoorHumiditySensor)
      : null;

    return html`
      <div class="settings-section first">
        <div class="sensor-grid">
          <div class="sensor-field">
            <ha-entity-picker
              .hass=${this.hass}
              .value=${this.outdoorTempSensor}
              .includeDomains=${["sensor"]}
              .entityFilter=${this._filterTemperature}
              .label=${localize("settings.outdoor_sensor_label", l)}
              allow-custom-entity
              @value-changed=${(e: CustomEvent) => {
                const v = (e.detail?.value as string) ?? "";
                if (v !== this.outdoorTempSensor) this._fire("outdoorTempSensor", v);
              }}
            ></ha-entity-picker>
            ${outdoorTemp !== null
              ? html`<div class="current-value">
                  ${localize("settings.outdoor_current", l, {
                    temp: outdoorTemp.toFixed(1),
                    unit: tempUnit(this.hass),
                  })}
                </div>`
              : this.outdoorTempSensor
                ? html`<div class="current-value muted">
                    ${localize("settings.outdoor_waiting", l)}
                  </div>`
                : nothing}
          </div>
          <div class="sensor-field">
            <ha-entity-picker
              .hass=${this.hass}
              .value=${this.outdoorHumiditySensor}
              .includeDomains=${["sensor"]}
              .entityFilter=${this._filterHumidity}
              .label=${localize("settings.outdoor_humidity_label", l)}
              allow-custom-entity
              @value-changed=${(e: CustomEvent) => {
                const v = (e.detail?.value as string) ?? "";
                if (v !== this.outdoorHumiditySensor) this._fire("outdoorHumiditySensor", v);
              }}
            ></ha-entity-picker>
            ${outdoorHumidity !== null
              ? html`<div class="current-value">
                  ${localize("settings.outdoor_humidity_current", l, {
                    value: String(outdoorHumidity),
                  })}
                </div>`
              : this.outdoorHumiditySensor
                ? html`<div class="current-value muted">
                    ${localize("settings.outdoor_waiting", l)}
                  </div>`
                : nothing}
          </div>
        </div>
      </div>

      <div class="settings-section">
        <ha-entity-picker
          .hass=${this.hass}
          .value=${this.weatherEntity}
          .includeDomains=${["weather"]}
          .label=${localize("settings.weather_entity", l)}
          allow-custom-entity
          @value-changed=${(e: CustomEvent) => {
            const v = (e.detail?.value as string) ?? "";
            if (v !== this.weatherEntity) this._fire("weatherEntity", v);
          }}
        ></ha-entity-picker>
        <span class="field-hint">${localize("settings.weather_entity_hint", l)}</span>
      </div>
    `;
  }

  static styles = [
    RsSettingsBase.settingsBaseStyles,
    css`
      .sensor-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 16px;
      }
      .current-value {
        margin-top: 8px;
        font-size: 14px;
        color: var(--primary-text-color);
      }
      .current-value.muted {
        color: var(--secondary-text-color);
      }

      @media (max-width: 600px) {
        .sensor-grid {
          grid-template-columns: 1fr;
        }
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-sensors": RsSettingsSensors;
  }
}
