/**
 * rs-settings-central-heating – Central heating: a boiler switched by the number of rooms demanding heat.
 */
import { html, nothing } from "lit";
import { RsSettingsBase } from "./rs-settings-base";
import { customElement, property } from "lit/decorators.js";
import type { CentralHeatingSettings, HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";
import "../shared/rs-list-row";
import "../shared/rs-number-field";
import "../shared/rs-segmented";
import "../shared/rs-field";

export const DEFAULT_CENTRAL_HEATING: CentralHeatingSettings = {
  enabled: false,
  entity_id: "",
  min_rooms: 1,
  start_delay_s: 0,
  stop_delay_s: 0,
  on_temperature: null,
  off_temperature: null,
  climate_off_mode: "temperature",
};

@customElement("rs-settings-central-heating")
export class RsSettingsCentralHeating extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public centralHeating: CentralHeatingSettings =
    DEFAULT_CENTRAL_HEATING;

  render() {
    const l = this.hass.language;
    const c = this.centralHeating;

    return html`
      <div class="settings-section first">
        <rs-list-row
          switch
          wrap
          .heading=${localize("central_heating.enabled", l)}
          .secondary=${localize("central_heating.enabled_hint", l)}
          .checked=${c.enabled}
          @toggle-changed=${(e: CustomEvent<boolean>) => this._update({ enabled: e.detail })}
        ></rs-list-row>
      </div>

      ${
        c.enabled
          ? html`
              <div class="settings-section">
                <ha-entity-picker
                  .hass=${this.hass}
                  .value=${c.entity_id}
                  .includeDomains=${["switch", "input_boolean", "climate"]}
                  .entityFilter=${this._entityFilter}
                  .label=${localize("central_heating.entity", l)}
                  @value-changed=${(e: CustomEvent) => {
                    const v = (e.detail?.value as string) ?? "";
                    if (v !== c.entity_id) this._update({ entity_id: v });
                  }}
                ></ha-entity-picker>
                <span class="field-hint">${localize("central_heating.entity_hint", l)}</span>
              </div>

              <div class="settings-section">
                <div class="threshold-grid">
                  <rs-number-field
                    .label=${localize("central_heating.min_rooms", l)}
                    .min=${1}
                    .max=${50}
                    .step=${1}
                    .value=${c.min_rooms}
                    @value-changed=${(e: CustomEvent<{ value: number }>) =>
                      this._update({ min_rooms: e.detail.value })}
                  ></rs-number-field>
                  <rs-number-field
                    .label=${localize("central_heating.start_delay", l)}
                    suffix="s"
                    .min=${0}
                    .max=${3600}
                    .step=${1}
                    .value=${c.start_delay_s}
                    @value-changed=${(e: CustomEvent<{ value: number }>) =>
                      this._update({ start_delay_s: e.detail.value })}
                  ></rs-number-field>
                  <rs-number-field
                    .label=${localize("central_heating.stop_delay", l)}
                    suffix="s"
                    .min=${0}
                    .max=${3600}
                    .step=${1}
                    .value=${c.stop_delay_s}
                    @value-changed=${(e: CustomEvent<{ value: number }>) =>
                      this._update({ stop_delay_s: e.detail.value })}
                  ></rs-number-field>
                </div>
                <span class="field-hint">${localize("central_heating.delays_hint", l)}</span>
              </div>

              ${c.entity_id.startsWith("climate.") ? this._renderThermostat(l) : nothing}
            `
          : nothing
      }
    `;
  }

  private _renderThermostat(l: string) {
    const c = this.centralHeating;
    return html`
      <div class="settings-section">
        <div class="threshold-grid">
          <rs-number-field
            kind="temperature"
            allow-empty
            .hass=${this.hass}
            .label=${localize("central_heating.on_temperature", l)}
            .min=${5}
            .max=${90}
            .value=${c.on_temperature}
            @value-changed=${(e: CustomEvent<{ value: number | null }>) =>
              this._update({ on_temperature: e.detail.value })}
          ></rs-number-field>
          <rs-number-field
            kind="temperature"
            allow-empty
            .hass=${this.hass}
            .label=${localize("central_heating.off_temperature", l)}
            .min=${5}
            .max=${90}
            .value=${c.off_temperature}
            @value-changed=${(e: CustomEvent<{ value: number | null }>) =>
              this._update({ off_temperature: e.detail.value })}
          ></rs-number-field>
        </div>
        <span class="field-hint">${localize("central_heating.temperatures_hint", l)}</span>
      </div>
      <div class="settings-section">
        <rs-field .label=${localize("central_heating.off_mode", l)}>
          <rs-segmented
            wrap
            .label=${localize("central_heating.off_mode", l)}
            .options=${[
              { value: "temperature", label: localize("central_heating.off_mode_temperature", l) },
              { value: "off", label: localize("central_heating.off_mode_off", l) },
            ]}
            .value=${c.climate_off_mode}
            @value-changed=${(e: CustomEvent<{ value: string }>) => {
              const v = e.detail.value as CentralHeatingSettings["climate_off_mode"];
              if (v && v !== this.centralHeating.climate_off_mode)
                this._update({ climate_off_mode: v });
            }}
          ></rs-segmented>
        </rs-field>
      </div>
    `;
  }

  private _entityFilter = (entity: { entity_id: string }): boolean =>
    !entity.entity_id.substring(entity.entity_id.indexOf(".") + 1).startsWith("roommind_");

  private _update(changes: Partial<CentralHeatingSettings>) {
    this._fire("centralHeating", { ...this.centralHeating, ...changes });
  }

  static styles = [RsSettingsBase.settingsBaseStyles];
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-central-heating": RsSettingsCentralHeating;
  }
}
